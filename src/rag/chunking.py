from typing import Dict, List


def split_text_into_chunks(text: str, chunk_size: int = 900, chunk_overlap: int = 180) -> List[str]:
    """
    Simple character-based chunking with overlap.
    """
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_length:
            break
        start = end - chunk_overlap

    return chunks


def chunk_documents(documents: List[Dict], chunk_size: int = 900, chunk_overlap: int = 180) -> List[Dict]:
    """
    Create normalized chunks with metadata preserved.
    Metadata always includes:
    - title, category, content_type, page_id
    - attachment_name (None for page-level chunks)
    """
    all_chunks = []
    chunk_counter = 0

    for doc in documents:
        base_metadata = {
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "content_type": doc.get("content_type", ""),
            "page_id": doc.get("page_id", ""),
        }

        # 1) Page-level chunks
        page_text = doc.get("page_content", "") or ""
        page_chunks = split_text_into_chunks(page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for idx, text in enumerate(page_chunks):
            chunk_counter += 1
            all_chunks.append(
                {
                    "chunk_id": f"chunk_{chunk_counter:06d}",
                    "text": text,
                    "metadata": {
                        **base_metadata,
                        "attachment_name": None,
                        "attachment_type": None,
                        "source_type": "page_content",
                        "chunk_in_source": idx,
                    },
                }
            )

        # 2) Attachment-level chunks (if extracted text exists)
        for attachment in doc.get("attachments", []):
            attachment_text = attachment.get("extracted_text", "") or ""
            if not attachment_text.strip():
                continue

            attachment_chunks = split_text_into_chunks(
                attachment_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            for idx, text in enumerate(attachment_chunks):
                chunk_counter += 1
                all_chunks.append(
                    {
                        "chunk_id": f"chunk_{chunk_counter:06d}",
                        "text": text,
                        "metadata": {
                            **base_metadata,
                            "attachment_name": attachment.get("attachment_name", ""),
                            "attachment_type": attachment.get("attachment_type", ""),
                            "source_type": "attachment",
                            "chunk_in_source": idx,
                        },
                    }
                )

    return all_chunks
