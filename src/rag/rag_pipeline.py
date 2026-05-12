from typing import Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from src.rag.faiss_store import FaissStoreBuilder
from src.rag.prompts import get_hr_rag_prompt


INDEX_DIR = "vector_store/faiss_index"


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


def ask_hr_knowledge_base(question: str, top_k: int = 6, model_name: str = "gpt-4o-mini") -> Dict:
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

    # STEP 1 + STEP 2: load store and retrieve chunks
    retriever = FaissStoreBuilder()
    index, records = retriever.load_index(INDEX_DIR)
    retrieved_chunks = retriever.search(question, index, records, top_k=top_k)

    if not retrieved_chunks:
        return {
            "answer": "I could not find this information in the provided HR knowledge base context.",
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
    final_answer = chain.invoke({"question": question, "context": context_text})

    # STEP 5: return answer + sources + chunks
    sources = _build_unique_sources(retrieved_chunks)
    return {
        "answer": final_answer,
        "sources": sources,
        "retrieved_chunks": retrieved_chunks,
    }
