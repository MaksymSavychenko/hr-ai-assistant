from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.chunking import chunk_documents
from src.rag.faiss_store import FaissStoreBuilder
from src.rag.notion_loader import load_active_notion_documents


OUTPUT_DIR = "vector_store/faiss_index"


def main():
    print("Loading active Notion documents...")
    documents = load_active_notion_documents()
    print(f"Loaded documents: {len(documents)}")

    print("Chunking documents...")
    chunks = chunk_documents(documents, chunk_size=900, chunk_overlap=180)
    print(f"Generated chunks: {len(chunks)}")

    print("Building FAISS index with OpenAI embeddings...")
    builder = FaissStoreBuilder()
    index, records = builder.build_index(chunks)

    index_path, metadata_path = builder.save_index(index, records, OUTPUT_DIR)
    print("FAISS index build complete.")
    print(f"Index file: {index_path}")
    print(f"Metadata file: {metadata_path}")


if __name__ == "__main__":
    main()
