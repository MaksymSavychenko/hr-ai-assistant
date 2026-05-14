from pathlib import Path
import sys


# Allow running this script directly from project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.notion_loader import load_active_notion_documents


def main():
    documents = load_active_notion_documents()

    print(f"Loaded active Notion documents: {len(documents)}\n")

    for index, doc in enumerate(documents, start=1):
        print(f"--- Document #{index} ---")
        print(f"Title: {doc['title']}")
        print(f"Category: {doc['category']}")
        print(f"Content Type: {doc['content_type']}")
        print(f"Page ID: {doc['page_id']}")

        attachment_names = [item.get("attachment_name", "unnamed_attachment") for item in doc["attachments"]]
        print(f"Attachment count: {len(attachment_names)}")
        if attachment_names:
            print("Attachment names:")
            for name in attachment_names:
                print(f" - {name}")
        else:
            print("Attachment names: none")

        preview = doc["page_content"][:300].replace("\n", " ").strip()
        if not preview:
            preview = "(no extracted page text)"
        print(f"Text preview: {preview}")

        if doc["attachments"]:
            print("Attachment extracted text preview:")
            for attachment in doc["attachments"]:
                attachment_type = attachment.get("attachment_type", "other")
                if attachment_type not in {"pdf", "eml"}:
                    continue

                extracted_preview = attachment.get("extracted_text", "")[:220].replace("\n", " ").strip()
                if not extracted_preview:
                    extracted_preview = "(no extracted text)"

                if attachment_type == "eml":
                    print(
                        f" - {attachment.get('attachment_name', 'unnamed_attachment')} [eml]"
                    )
                    print(f"   email_subject: {attachment.get('email_subject', '')}")
                    print(f"   email_from: {attachment.get('email_from', '')}")
                    print(f"   email_to: {attachment.get('email_to', '')}")
                    print(f"   email_date: {attachment.get('email_date', '')}")
                    print(f"   text_preview: {extracted_preview}")
                else:
                    print(
                        f" - {attachment.get('attachment_name', 'unnamed_attachment')} "
                        f"[{attachment_type}] -> {extracted_preview}"
                    )
        print()


if __name__ == "__main__":
    main()
