import re
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlparse

import requests
from notion_client import Client
from pypdf import PdfReader

from src.config.secrets import require_secret


DOWNLOAD_DIR = Path("data/tmp/notion_downloads")


class NotionLoader:
    """
    MVP Notion loader for HR knowledge base ingestion.
    - loads active records
    - reads page text blocks
    - downloads PDF/EML attachments
    - extracts attachment text
    """

    def __init__(self, notion_token=None, database_id=None):
        self.notion_token = notion_token or require_secret("NOTION_TOKEN")
        self.database_id = database_id or require_secret("NOTION_DATABASE_ID")

        if not self.notion_token:
            raise ValueError("NOTION_TOKEN is missing. Provide it in .env or Streamlit secrets.")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID is missing. Provide it in .env or Streamlit secrets.")

        self.client = Client(auth=self.notion_token)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _rich_text_to_plain(rich_text_items):
        return "".join(item.get("plain_text", "") for item in rich_text_items or [])

    def _property_to_text(self, prop):
        if not prop:
            return ""

        prop_type = prop.get("type")

        if prop_type == "title":
            return self._rich_text_to_plain(prop.get("title", []))
        if prop_type == "rich_text":
            return self._rich_text_to_plain(prop.get("rich_text", []))
        if prop_type == "select":
            selected = prop.get("select")
            return selected.get("name", "") if selected else ""
        if prop_type == "multi_select":
            values = prop.get("multi_select", [])
            return ", ".join(v.get("name", "") for v in values)
        if prop_type == "status":
            status = prop.get("status")
            return status.get("name", "") if status else ""
        if prop_type == "url":
            return prop.get("url", "") or ""
        if prop_type == "number":
            value = prop.get("number")
            return "" if value is None else str(value)

        return ""

    @staticmethod
    def _guess_name_from_url(url_value):
        if not url_value:
            return "unnamed_attachment"
        parsed = urlparse(url_value)
        if parsed.path:
            filename = parsed.path.rsplit("/", 1)[-1]
            return filename or "unnamed_attachment"
        return "unnamed_attachment"

    @staticmethod
    def _safe_filename(filename):
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "unnamed_attachment")
        return cleaned[:200]

    @staticmethod
    def _detect_attachment_type(name, url_value):
        text = f"{name} {url_value}".lower()
        if ".pdf" in text:
            return "pdf"
        if ".eml" in text:
            return "eml"
        return "other"

    def _normalize_attachment(self, raw_attachment, source):
        name = raw_attachment.get("name", "") or ""
        url_value = ""

        attachment_type = raw_attachment.get("type")
        if attachment_type == "file":
            url_value = raw_attachment.get("file", {}).get("url", "")
        elif attachment_type == "external":
            url_value = raw_attachment.get("external", {}).get("url", "")

        if not name:
            name = self._guess_name_from_url(url_value)

        detected_type = self._detect_attachment_type(name, url_value)

        return {
            "name": name,
            "url": url_value,
            "source": source,
            "attachment_type": detected_type,
        }

    def _extract_property_attachments(self, properties):
        attachments = []
        for prop_name, prop in properties.items():
            if prop.get("type") != "files":
                continue

            for file_item in prop.get("files", []):
                attachments.append(self._normalize_attachment(file_item, f"property:{prop_name}"))

        return attachments

    def _extract_attachments_from_block(self, block):
        block_type = block.get("type")
        attachments = []

        file_block_types = {"file", "pdf", "image", "video", "audio"}
        if block_type in file_block_types:
            block_payload = block.get(block_type, {})
            normalized = self._normalize_attachment(block_payload, f"block:{block_type}")
            attachments.append(normalized)

        return attachments

    def _extract_text_from_block(self, block):
        block_type = block.get("type")
        payload = block.get(block_type, {})

        rich_text = payload.get("rich_text")
        if isinstance(rich_text, list):
            return self._rich_text_to_plain(rich_text)

        caption = payload.get("caption")
        if isinstance(caption, list):
            return self._rich_text_to_plain(caption)

        return ""

    def _get_page_blocks(self, page_id):
        blocks = []
        cursor = None

        while True:
            params = {"block_id": page_id, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            response = self.client.blocks.children.list(**params)
            blocks.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return blocks

    @staticmethod
    def _deduplicate_attachments(attachments):
        seen = set()
        unique = []
        for item in attachments:
            key = (item.get("name", ""), item.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _download_attachment(self, attachment):
        url_value = attachment.get("url", "")
        if not url_value:
            return None

        filename = self._safe_filename(attachment.get("name", "unnamed_attachment"))
        local_path = DOWNLOAD_DIR / filename

        response = requests.get(url_value, timeout=45)
        response.raise_for_status()
        local_path.write_bytes(response.content)
        return local_path

    @staticmethod
    def _extract_pdf_text(file_path):
        text_parts = []
        reader = PdfReader(str(file_path))
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts).strip()

    @staticmethod
    def _extract_eml_data(file_path):
        """
        Extract standard email headers and clean body text from .eml file.
        Returns:
        - combined_text_for_embedding
        - email_metadata (dict)
        """
        raw_bytes = file_path.read_bytes()
        message = BytesParser(policy=policy.default).parsebytes(raw_bytes)

        subject = (message.get("subject", "") or "").strip()
        sender = (message.get("from", "") or "").strip()
        recipient = (message.get("to", "") or "").strip()
        sent_date = (message.get("date", "") or "").strip()
        message_id = (message.get("message-id", "") or "").strip()

        body_parts = []
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                content_disposition = part.get_content_disposition()

                # Keep only plain text body parts and skip attached files.
                if content_type == "text/plain" and content_disposition != "attachment":
                    body_parts.append(part.get_content() or "")
        else:
            body_parts.append(message.get_content() or "")

        body_text = "\n".join(body_parts).strip()
        header_text = (
            f"EMAIL SUBJECT: {subject}\n"
            f"EMAIL FROM: {sender}\n"
            f"EMAIL TO: {recipient}\n"
            f"EMAIL DATE: {sent_date}\n"
            f"EMAIL MESSAGE-ID: {message_id}"
        )
        combined_text = f"{header_text}\n\n{body_text}".strip()

        email_metadata = {
            "email_subject": subject,
            "email_from": sender,
            "email_to": recipient,
            "email_date": sent_date,
            "email_message_id": message_id,
        }
        return combined_text, email_metadata

    def _extract_attachment_text(self, attachment, local_path):
        attachment_type = attachment.get("attachment_type", "other")

        if not local_path:
            return "", {}

        if attachment_type == "pdf":
            return self._extract_pdf_text(local_path), {}
        if attachment_type == "eml":
            return self._extract_eml_data(local_path)

        return "", {}

    def _query_all_records_from_database_endpoint(self):
        results = []
        cursor = None
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        while True:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor

            response = requests.post(
                f"https://api.notion.com/v1/databases/{self.database_id}/query",
                json=payload,
                headers=headers,
                timeout=30,
            )
            if response.status_code >= 400:
                response.raise_for_status()

            data = response.json()
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return results

    def _resolve_data_source_id(self):
        try:
            db = self.client.databases.retrieve(database_id=self.database_id)
            data_sources = db.get("data_sources", [])
            if data_sources:
                return data_sources[0].get("id")
        except Exception:
            return self.database_id
        return self.database_id

    def _query_all_records(self):
        try:
            return self._query_all_records_from_database_endpoint()
        except Exception:
            pass

        results = []
        cursor = None
        data_source_id = self._resolve_data_source_id()

        while True:
            params = {"data_source_id": data_source_id, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            response = self.client.data_sources.query(**params)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return results

    def load_active_documents(self):
        """
        Load active Notion records and normalize to:
        {
          "title": "...",
          "category": "...",
          "content_type": "...",
          "page_content": "...",
          "attachments": [...]
        }
        """
        pages = self._query_all_records()
        documents = []

        for page in pages:
            properties = page.get("properties", {})
            status_value = self._property_to_text(properties.get("Status"))
            if status_value.strip().lower() != "active":
                continue

            title = self._property_to_text(properties.get("Title")) or "Untitled"
            category = self._property_to_text(properties.get("Category"))
            content_type = self._property_to_text(properties.get("Content Type"))
            page_id = page.get("id", "")

            blocks = self._get_page_blocks(page_id)
            page_text_parts = []
            attachments = []

            for block in blocks:
                block_text = self._extract_text_from_block(block).strip()
                if block_text:
                    page_text_parts.append(block_text)
                attachments.extend(self._extract_attachments_from_block(block))

            attachments.extend(self._extract_property_attachments(properties))
            attachments = self._deduplicate_attachments(attachments)

            attachment_text_parts = []
            enriched_attachments = []

            for attachment in attachments:
                if attachment.get("attachment_type") not in {"pdf", "eml"}:
                    continue

                print(
                    f"[NotionLoader] Found attachment: {attachment.get('name')} "
                    f"(type={attachment.get('attachment_type')}, page_id={page_id})"
                )

                local_path = None
                extracted_text = ""
                email_metadata = {}

                try:
                    local_path = self._download_attachment(attachment)
                    extracted_text, email_metadata = self._extract_attachment_text(attachment, local_path)
                except Exception as error:
                    extracted_text = f"[Attachment extraction failed: {error}]"
                    email_metadata = {}

                if extracted_text:
                    attachment_text_parts.append(extracted_text)

                enriched_attachments.append(
                    {
                        "attachment_name": attachment.get("name", ""),
                        "attachment_type": attachment.get("attachment_type", "other"),
                        "attachment_url": attachment.get("url", ""),
                        "local_path": str(local_path) if local_path else "",
                        "source": attachment.get("source", ""),
                        "extracted_text": extracted_text,
                        "email_subject": email_metadata.get("email_subject", ""),
                        "email_from": email_metadata.get("email_from", ""),
                        "email_to": email_metadata.get("email_to", ""),
                        "email_date": email_metadata.get("email_date", ""),
                        "email_message_id": email_metadata.get("email_message_id", ""),
                        "title": title,
                        "category": category,
                        "content_type": content_type,
                        "page_id": page_id,
                    }
                )

            page_body_text = "\n".join(page_text_parts).strip()
            attachments_text = "\n".join(attachment_text_parts).strip()
            combined_text = f"{page_body_text}\n\n{attachments_text}".strip()

            documents.append(
                {
                    "title": title,
                    "category": category,
                    "content_type": content_type,
                    "page_id": page_id,
                    "page_content": combined_text,
                    "attachments": enriched_attachments,
                }
            )

        return documents


def load_active_notion_documents():
    loader = NotionLoader()
    return loader.load_active_documents()
