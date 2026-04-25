import chromadb
from chromadb.config import Settings
from rag.embedder import CodeEmbedder


class CodeStore:
    def __init__(self, persist_dir: str = ".chroma"):
        self.embedder = CodeEmbedder()
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="code_snippets",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, snippets: list[str], ids: list[str] = None, metadatas: list[dict] = None):
        if not snippets:
            return
        ids = ids or [str(i) for i in range(self.collection.count(), self.collection.count() + len(snippets))]
        vecs = self.embedder.embed(snippets).tolist()
        self.collection.add(documents=snippets, embeddings=vecs, ids=ids, metadatas=metadatas or [{"source": "unknown"} for _ in snippets])

    def query(self, code: str, top_k: int = 3) -> list[dict]:
        vec = self.embedder.embed_one(code).tolist()
        results = self.collection.query(query_embeddings=[vec], n_results=min(top_k, self.collection.count()))
        docs = results["documents"][0]
        scores = results["distances"][0]
        metas = results["metadatas"][0]
        return [{"snippet": d, "score": s, "meta": m} for d, s, m in zip(docs, scores, metas)]

    def count(self) -> int:
        return self.collection.count()


if __name__ == "__main__":
    store = CodeStore(persist_dir=".chroma_test")

    snippets = [
        "def add(a, b):\n    return a + b",
        "def subtract(a, b):\n    return a - b",
        "def bubble_sort(arr):\n    for i in range(len(arr)):\n        for j in range(len(arr)-i-1):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]",
        "class BinaryTree:\n    def __init__(self, val):\n        self.val = val\n        self.left = None\n        self.right = None",
    ]

    store.add(snippets, ids=["add", "subtract", "bubble_sort", "binary_tree"])
    print(f"Indexed {store.count()} snippets")

    results = store.query("def merge_sort(arr): ...", top_k=2)
    print("\nQuery: merge_sort")
    for r in results:
        print(f"  score={r['score']:.4f} | {r['snippet'][:60]}")
