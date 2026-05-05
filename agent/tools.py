from pathlib import Path
from langchain.tools import tool
from review.github import fetch_pr_diff as _fetch_pr_diff

_store = None


def get_store():
    global _store
    if _store is None:
        from rag.store import CodeStore
        _store = CodeStore()
    return _store


@tool
def fetch_pr_diff(pr_url: str) -> str:
    """Fetch the full diff for a GitHub PR. Returns each changed file's name and patch."""
    try:
        diffs = _fetch_pr_diff(pr_url)
        if not diffs:
            return "No diffs found for this PR."
        parts = [f"File: {d.filename}\n```\n{d.patch}\n```" for d in diffs]
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error fetching PR diff: {e}"


@tool
def list_pr_files(pr_url: str) -> str:
    """List the filenames changed in a GitHub PR without fetching full diffs."""
    try:
        diffs = _fetch_pr_diff(pr_url)
        if not diffs:
            return "No files found in this PR."
        return "\n".join(f"- {d.filename}" for d in diffs)
    except Exception as e:
        return f"Error listing PR files: {e}"


@tool
def query_codebase(query: str, top_k: int = 3) -> str:
    """Search the indexed codebase for code similar to the query string. Use this to find relevant context before reviewing a diff."""
    store = get_store()
    if store.count() == 0:
        return "No codebase indexed yet. Ask the user to run index_directory first."
    results = store.query(query, top_k=top_k)
    if not results:
        return "No similar code found."
    parts = [f"[{i}] score={r['score']:.3f}\n{r['snippet'][:400]}" for i, r in enumerate(results, 1)]
    return "\n\n".join(parts)


@tool
def index_directory(directory: str) -> str:
    """Index all Python files in a local directory into the codebase store for RAG retrieval."""
    store = get_store()
    paths = list(Path(directory).rglob("*.py"))
    if not paths:
        return f"No .py files found in {directory}"
    snippets, ids = [], []
    for path in paths:
        try:
            code = path.read_text(errors="ignore")
            if code.strip():
                snippets.append(code[:2000])
                ids.append(str(path))
        except Exception:
            continue
    store.add(snippets, ids=ids, metadatas=[{"file": p} for p in ids])
    return f"Indexed {len(snippets)} files from {directory}"


AUTONOMOUS_TOOLS = [fetch_pr_diff, list_pr_files, query_codebase, index_directory]
