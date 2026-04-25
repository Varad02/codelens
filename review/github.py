import os
import re
import requests
from dataclasses import dataclass


@dataclass
class FileDiff:
    filename: str
    patch: str


def _parse_pr_url(url: str) -> tuple[str, str, int]:
    match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not match:
        raise ValueError(f"Not a valid GitHub PR URL: {url}")
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def fetch_pr_diff(pr_url: str) -> list[FileDiff]:
    owner, repo, number = _parse_pr_url(pr_url)

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files",
        headers=headers,
    )
    resp.raise_for_status()

    diffs = []
    for f in resp.json():
        patch = f.get("patch", "")
        if patch:
            diffs.append(FileDiff(filename=f["filename"], patch=patch))

    return diffs


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/torvalds/linux/pull/1"
    try:
        diffs = fetch_pr_diff(url)
        for d in diffs:
            print(f"\n--- {d.filename} ---")
            print(d.patch[:300])
    except Exception as e:
        print(f"Error: {e}")
