from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.faiss_store import FaissStoreBuilder


INDEX_DIR = "vector_store/faiss_index"


def main():
    query = "What is the policy for birthday leave and probation?"
    top_k = 5

    print(f"Loading FAISS index from: {INDEX_DIR}")
    builder = FaissStoreBuilder()
    index, records = builder.load_index(INDEX_DIR)
    print(f"Loaded vectors: {index.ntotal}")
    print(f"Loaded metadata records: {len(records)}")

    print(f"\nQuery: {query}\n")
    results = builder.search(query, index, records, top_k=top_k)

    if not results:
        print("No results found.")
        return

    for result in results:
        meta = result["metadata"]
        preview = result["text"][:260].replace("\n", " ").strip()
        print(f"Rank #{result['rank']} | distance={result['distance']:.4f}")
        print(
            f"  title={meta.get('title', '')} | category={meta.get('category', '')} | "
            f"content_type={meta.get('content_type', '')}"
        )
        print(
            f"  page_id={meta.get('page_id', '')} | attachment_name={meta.get('attachment_name', '')}"
        )
        print(f"  preview={preview}")
        print()


if __name__ == "__main__":
    main()
