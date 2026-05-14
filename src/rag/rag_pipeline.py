from pathlib import Path
from typing import Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from src.rag.faiss_store import FaissStoreBuilder
from src.rag.chunking import chunk_documents
from src.rag.notion_loader import load_active_notion_documents
from src.rag.prompts import get_hr_rag_prompt


INDEX_DIR = "vector_store/faiss_index"
SALES_DEPARTMENT_NAME = "sales"


def _format_context_with_sources(retrieved_chunks: List[Dict]) -> str:
    """
    Format chunks into source-grounded context blocks for the LLM prompt.
    """
    blocks = []
    for idx, item in enumerate(retrieved_chunks, start=1):
        meta = item.get("metadata", {})
        title = meta.get("title", "")
        category = meta.get("category", "")
        content_type = meta.get("content_type", "")
        page_id = meta.get("page_id", "")
        attachment_name = meta.get("attachment_name", "")
        chunk_text = item.get("text", "")

        blocks.append(
            "\n".join(
                [
                    f"[S{idx}]",
                    f"title: {title}",
                    f"category: {category}",
                    f"content_type: {content_type}",
                    f"page_id: {page_id}",
                    f"attachment_name: {attachment_name}",
                    f"content: {chunk_text}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _build_unique_sources(retrieved_chunks: List[Dict]) -> List[Dict]:
    """
    Build unique source list from chunk metadata.
    """
    seen = set()
    sources = []

    for item in retrieved_chunks:
        meta = item.get("metadata", {})
        key = (
            meta.get("title", ""),
            meta.get("category", ""),
            meta.get("content_type", ""),
            meta.get("page_id", ""),
            meta.get("attachment_name", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "title": meta.get("title", ""),
                "category": meta.get("category", ""),
                "content_type": meta.get("content_type", ""),
                "page_id": meta.get("page_id", ""),
                "attachment_name": meta.get("attachment_name", ""),
            }
        )

    return sources


def _get_employee_department(employee_context: dict | None) -> str:
    if not employee_context:
        return ""
    return str(employee_context.get("department", "")).strip().lower()


def _is_sales_specific_chunk(chunk: Dict) -> bool:
    """
    Lightweight heuristic: detect chunks clearly specific to Sales team/department.
    """
    metadata = chunk.get("metadata", {})
    text = str(chunk.get("text", "") or "").lower()
    title = str(metadata.get("title", "") or "").lower()
    category = str(metadata.get("category", "") or "").lower()
    content_type = str(metadata.get("content_type", "") or "").lower()
    attachment_name = str(metadata.get("attachment_name", "") or "").lower()

    combined = " ".join([text, title, category, content_type, attachment_name])
    sales_specific_markers = [
        "sales team",
        "sales department",
        "sales teams",
        "for sales",
        "sales vacation",
        "june sales",
    ]
    return any(marker in combined for marker in sales_specific_markers)


def _is_general_policy_or_faq_chunk(chunk: Dict) -> bool:
    """
    General chunks are used as fallback when department filtering removes all chunks.
    """
    metadata = chunk.get("metadata", {})
    title = str(metadata.get("title", "") or "").lower()
    category = str(metadata.get("category", "") or "").lower()
    content_type = str(metadata.get("content_type", "") or "").lower()
    attachment_name = str(metadata.get("attachment_name", "") or "").lower()

    combined = " ".join([title, category, content_type, attachment_name])
    return (
        "faq" in combined
        or "policy" in combined
        or "handbook" in combined
        or "notion" in combined
        or "pdf" in combined
    )


def filter_retrieved_chunks_by_employee_context(chunks: List[Dict], employee_context: dict | None) -> List[Dict]:
    """
    Department-aware filtering for Flow 1:
    - Sales-specific chunks are shown only to Sales employees.
    - General policy/FAQ chunks remain available for everyone.
    """
    department = _get_employee_department(employee_context)
    if not department:
        return chunks

    if department == SALES_DEPARTMENT_NAME:
        return chunks

    filtered = [chunk for chunk in chunks if not _is_sales_specific_chunk(chunk)]
    if filtered:
        return filtered

    # If all chunks were filtered out, keep only general policy/FAQ chunks if present.
    general_fallback = [chunk for chunk in chunks if _is_general_policy_or_faq_chunk(chunk)]
    return general_fallback


def is_faiss_index_ready(index_dir: str = INDEX_DIR) -> bool:
    """Check if FAISS index files exist."""
    base_path = Path(index_dir)
    return (base_path / "index.faiss").exists() and (base_path / "metadata.json").exists()


def ensure_faiss_index_ready(index_dir: str = INDEX_DIR) -> bool:
    """
    Ensure FAISS index exists.
    Returns True if index was built in this call, False if it already existed.
    """
    if is_faiss_index_ready(index_dir):
        return False

    documents = load_active_notion_documents()
    chunks = chunk_documents(documents, chunk_size=900, chunk_overlap=180)
    if not chunks:
        raise ValueError("Could not build FAISS index: no chunks were generated from Notion documents.")

    builder = FaissStoreBuilder()
    index, records = builder.build_index(chunks)
    builder.save_index(index, records, index_dir)
    return True


def ask_hr_knowledge_base(
    question: str,
    employee_context: dict | None = None,
    top_k: int = 5,
    model_name: str = "gpt-4o-mini",
) -> Dict:
    """
    End-to-end RAG answering:
    1) load FAISS store
    2) retrieve top chunks
    3) build grounded prompt
    4) call ChatOpenAI
    5) return answer + sources + chunks
    """
    if not question or not question.strip():
        raise ValueError("Question must not be empty.")

    # Make index available on demand (cloud-friendly startup).
    ensure_faiss_index_ready(INDEX_DIR)

    # STEP 1 + STEP 2: load store and retrieve chunks
    retriever = FaissStoreBuilder()
    index, records = retriever.load_index(INDEX_DIR)
    retrieved_chunks = retriever.search(question, index, records, top_k=top_k)
    retrieved_chunks = filter_retrieved_chunks_by_employee_context(retrieved_chunks, employee_context)

    if not retrieved_chunks:
        return {
            "answer": "I could not find relevant policy information for your profile in the provided HR knowledge base context.",
            "sources": [],
            "retrieved_chunks": [],
        }

    # STEP 3: grounded prompt
    context_text = _format_context_with_sources(retrieved_chunks)
    prompt = get_hr_rag_prompt()

    # STEP 4: LCEL chain with ChatOpenAI
    llm = ChatOpenAI(model=model_name, temperature=0)
    chain = (
        {
            "question": RunnableLambda(lambda x: x["question"]),
            "context": RunnableLambda(lambda x: x["context"]),
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    final_answer = chain.invoke(
        {
            "question": question,
            "context": context_text,
        }
    )

    # STEP 5: return answer + sources + chunks
    sources = _build_unique_sources(retrieved_chunks)
    return {
        "answer": final_answer,
        "sources": sources,
        "retrieved_chunks": retrieved_chunks,
    }
