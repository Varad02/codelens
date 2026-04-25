import argparse
import json
import sys
from pathlib import Path
from rag.store import CodeStore
from review.reviewer import review_pr


def cmd_review(args):
    results = review_pr(args.pr, top_k=args.top_k)
    print(json.dumps(results, indent=2))


def cmd_index(args):
    store = CodeStore()
    paths = list(Path(args.dir).rglob("*.py"))
    if not paths:
        print(f"No .py files found in {args.dir}")
        sys.exit(1)

    snippets, ids = [], []
    for path in paths:
        try:
            code = path.read_text(errors="ignore")
            if code.strip():
                snippets.append(code[:2000])
                ids.append(str(path))
        except Exception:
            continue

    store.add(snippets, ids=ids, metadatas=[{"file": i} for i in ids])
    print(f"Indexed {len(snippets)} files from {args.dir}")


def main():
    parser = argparse.ArgumentParser(prog="codelens", description="RAG-powered code review")
    sub = parser.add_subparsers(dest="command", required=True)

    review_parser = sub.add_parser("review", help="Review a GitHub PR")
    review_parser.add_argument("pr", help="GitHub PR URL")
    review_parser.add_argument("--top-k", type=int, default=3, help="RAG context snippets to retrieve")
    review_parser.set_defaults(func=cmd_review)

    index_parser = sub.add_parser("index", help="Index a local codebase into the RAG store")
    index_parser.add_argument("dir", help="Directory to index")
    index_parser.set_defaults(func=cmd_index)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
