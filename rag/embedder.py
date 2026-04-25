from sentence_transformers import SentenceTransformer
import numpy as np


MODEL_NAME = "all-MiniLM-L6-v2"


class CodeEmbedder:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model = SentenceTransformer(model_name)

    def embed(self, snippets: list[str]) -> np.ndarray:
        return self.model.encode(snippets, normalize_embeddings=True, show_progress_bar=False)

    def embed_one(self, snippet: str) -> np.ndarray:
        return self.embed([snippet])[0]


if __name__ == "__main__":
    embedder = CodeEmbedder()

    snippets = [
        "def add(a, b):\n    return a + b",
        "def multiply(x, y):\n    return x * y",
        "SELECT * FROM users WHERE id = ?",
    ]

    vecs = embedder.embed(snippets)
    print(f"Embedding shape: {vecs.shape}")  # (3, 384)

    # cosine similarity between the two Python functions should be high
    sim = float(np.dot(vecs[0], vecs[1]))
    print(f"Python↔Python similarity: {sim:.4f}")
    sim2 = float(np.dot(vecs[0], vecs[2]))
    print(f"Python↔SQL similarity:    {sim2:.4f}")
