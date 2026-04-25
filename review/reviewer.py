import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from review.github import fetch_pr_diff
from rag.store import CodeStore

load_dotenv()

MODEL = "api-gpt-oss-120b"
SYSTEM_PROMPT = """\
You are an expert code reviewer. Given a code diff and optionally similar code examples for context, \
return a JSON object with this exact structure:
{
  "summary": "one sentence overall assessment",
  "issues": [
    {
      "type": "bug" | "suggestion" | "style",
      "line": <line number from diff or null>,
      "message": "clear, actionable description"
    }
  ]
}
Return only valid JSON. No markdown, no extra text."""


def _build_prompt(filename: str, patch: str, context_snippets: list[dict]) -> str:
    prompt = f"File: {filename}\n\nDiff:\n```\n{patch}\n```"
    if context_snippets:
        prompt += "\n\nSimilar code from the codebase for reference:\n"
        for i, s in enumerate(context_snippets, 1):
            prompt += f"\n[{i}] {s['snippet'][:300]}\n"
    return prompt


def review_pr(pr_url: str, top_k: int = 3) -> list[dict]:
    store = CodeStore()
    client = OpenAI(
        base_url="https://tritonai-api.ucsd.edu/v1",
        api_key=os.environ["TRITON_API_KEY"],
    )

    diffs = fetch_pr_diff(pr_url)
    if not diffs:
        return [{"error": "No diffs found for this PR"}]

    reviews = []
    for diff in diffs:
        context = store.query(diff.patch, top_k=top_k) if store.count() > 0 else []
        prompt = _build_prompt(diff.filename, diff.patch, context)

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content.strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"summary": raw, "issues": []}

        reviews.append({"file": diff.filename, **result})

    return reviews


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m review.reviewer <pr_url>")
        sys.exit(1)

    results = review_pr(sys.argv[1])
    print(json.dumps(results, indent=2))
