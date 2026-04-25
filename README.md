# CodeLens

A transformer-powered code review system that combines a GPT-style decoder built from scratch with a RAG pipeline to deliver context-aware PR reviews.

```
GitHub PR URL
      │
      ▼
 fetch_pr_diff()          ┌─────────────────────┐
 (GitHub Files API)       │   RAG Pipeline       │
      │                   │                      │
      ├──── file patch ──►│  CodeEmbedder        │
      │                   │  (all-MiniLM-L6-v2)  │
      │                   │        │             │
      │                   │        ▼             │
      │                   │   ChromaDB Store     │
      │                   │        │             │
      │                   │  top-k similar       │
      │                   │  snippets            │
      │                   └─────────┬───────────┘
      │                             │
      └──── diff + context ────────►│
                                    ▼
                           Triton LLM API
                          (api-gpt-oss-120b)
                                    │
                                    ▼
                          Structured JSON Review
                       { summary, issues: [bug|suggestion|style] }
```

## Architecture

| Component | Details |
|---|---|
| **Transformer** | GPT-style decoder implemented from scratch in PyTorch — multi-head attention, causal mask, positional embeddings, N decoder blocks |
| **Embeddings** | `all-MiniLM-L6-v2` via sentence-transformers, normalized cosine similarity |
| **Vector Store** | ChromaDB (persistent, local) with HNSW indexing |
| **LLM** | `api-gpt-oss-120b` via OpenAI-compatible Triton API |
| **GitHub** | GitHub Files API — per-file patches, optional token auth |

## Setup

```bash
conda create -n codelens python=3.11 -y
conda activate codelens
pip install -r requirements.txt
```

Create a `.env` file:
```
TRITON_API_KEY=your_key_here
GITHUB_TOKEN=your_github_token  # optional, avoids rate limits
```

## Usage

**Index a codebase into the RAG store:**
```bash
python cli.py index ./path/to/repo
```

**Review a GitHub PR:**
```bash
python cli.py review https://github.com/owner/repo/pull/123
```

**Example output:**
```json
[
  {
    "file": "src/auth.py",
    "summary": "Adds JWT validation but missing expiry check.",
    "issues": [
      {
        "type": "bug",
        "line": 42,
        "message": "Token expiry is never validated — expired tokens will be accepted."
      },
      {
        "type": "suggestion",
        "line": 57,
        "message": "Extract secret key from config rather than hardcoding."
      }
    ]
  }
]
```

## Project Structure

```
codelens/
├── model/
│   └── transformer.py    # GPT decoder from scratch (PyTorch)
├── rag/
│   ├── embedder.py       # code embeddings
│   └── store.py          # ChromaDB vector store + retrieval
├── review/
│   ├── github.py         # GitHub PR diff fetcher
│   └── reviewer.py       # RAG + LLM review engine
└── cli.py                # CLI entrypoint
```

## Tech Stack

`PyTorch` · `sentence-transformers` · `ChromaDB` · `OpenAI SDK` · `GitHub API`
