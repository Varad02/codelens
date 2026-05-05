import os
import requests
from langchain.tools import tool
from review.github import _parse_pr_url

# Actions the agent must refuse regardless of user request
PROHIBITED = {
    "merge", "merge pr", "merge pull request",
    "delete branch", "delete_branch",
    "push", "force push", "git push",
    "close pr", "close pull request",
}


def is_prohibited(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(phrase in lowered for phrase in PROHIBITED)


def _ask_confirmation(description: str) -> bool:
    print(f"\n[CONFIRMATION REQUIRED]\n{description}")
    try:
        answer = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer == "y"


@tool
def post_github_review(pr_url: str, body: str) -> str:
    """Post a review comment to a GitHub PR. Will ask the user to confirm before posting because this is a public, irreversible action."""
    preview = body[:300] + ("..." if len(body) > 300 else "")
    if not _ask_confirmation(f"About to post this review to {pr_url}:\n\n{preview}"):
        return "Cancelled — no comment was posted."

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "Error: GITHUB_TOKEN not set. Cannot post to GitHub."

    try:
        owner, repo, number = _parse_pr_url(pr_url)
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
        }
        resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
            headers=headers,
            json={"body": body},
        )
        resp.raise_for_status()
        url = resp.json().get("html_url", "unknown")
        return f"Review posted successfully: {url}"
    except Exception as e:
        return f"Error posting review: {e}"


CONFIRMATION_TOOLS = [post_github_review]
