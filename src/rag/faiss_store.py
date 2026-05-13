import json
from pathlib import Path
from typing import Dict, List

import faiss
import numpy as np
from openai import OpenAI

from src.config.secrets import require_secret


DEFAULT_EMBED_MODEL = "text-embedding-3-small"


class FaissStoreBuilder:
    """
    Build and query a FAISS index from text chunks using OpenAI embeddings.
    """

    def __init__(self, embedding_model: str = DEFAULT_EMBED_MODEL):
        api_key = require_secret("OPENAI_API_KEY")

        self.client = OpenAI(api_key=api_key)
        self.embedding_model = embedding_model

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
                encoding_format="float",
            )
            vectors.extend([item.embedding for item in response.data])

        matrix = np.array(vectors, dtype=np.float32)
        return matrix

    def build_index(self, chunks: List[Dict]):
        if not chunks:
            raise ValueError("No chunks provided to build_index().")

        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embed_texts(texts)

        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        records = []
        for i, chunk in enumerate(chunks):
            records.append(
                {
                    "vector_id": i,
                    "chunk_id": chunk.get("chunk_id", ""),
                    "text": chunk.get("text", ""),
                    "metadata": chunk.get("metadata", {}),
                }
            )

        return index, records

    @staticmethod
    def save_index(index, records: List[Dict], output_dir: str):
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        index_path = out_dir / "index.faiss"
        metadata_path = out_dir / "metadata.json"

        faiss.write_index(index, str(index_path))
        metadata_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

        return str(index_path), str(metadata_path)

    @staticmethod
    def load_index(output_dir: str):
        out_dir = Path(output_dir)
        index_path = out_dir / "index.faiss"
        metadata_path = out_dir / "metadata.json"

        if not index_path.exists():
            raise FileNotFoundError(f"Missing FAISS index file: {index_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"Missing metadata file: {metadata_path}")

        index = faiss.read_index(str(index_path))
        records = json.loads(metadata_path.read_text(encoding="utf-8"))
        return index, records

    def search(self, query: str, index, records: List[Dict], top_k: int = 5) -> List[Dict]:
        query_vector = self.embed_texts([query])
        distances, indices = index.search(query_vector, top_k)

        results = []
        for rank, vector_id in enumerate(indices[0]):
            if vector_id < 0 or vector_id >= len(records):
                continue
            record = records[vector_id]
            results.append(
                {
                    "rank": rank + 1,
                    "distance": float(distances[0][rank]),
                    "chunk_id": record.get("chunk_id", ""),
                    "text": record.get("text", ""),
                    "metadata": record.get("metadata", {}),
                }
            )
        return results
