import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


# =========================
# Configuration
# =========================

# GitHub API configuration
GITHUB_API_URL = "https://api.github.com/graphql"

# Path to the repos list (one `owner/repo` per line)
REPOS_LIST_PATH = "/home/vahid/Desktop/CommentCheck/files/repos.txt"

# Output directory (one JSON per repo)
OUTPUT_DIR = "/home/vahid/Desktop/CommentCheck/files/comments"

# Maximum number of comments per repo to collect.
# If set to None, script will collect all available comments.
MAX_COMMENTS_PER_REPO: Optional[int] = 10

# Only consider pull requests created on or before this ISO timestamp (UTC).
# Example format: "2025-12-01T00:00:00Z"
PR_CREATED_BEFORE_ISO = "2025-12-01T00:00:00Z"

# GraphQL pagination sizes – tuned to reduce number of requests.
PRS_PER_PAGE = 25
THREADS_PER_PAGE = 25
COMMENTS_PER_THREAD_PAGE = 50

# Path to external GraphQL query template
PR_THREADS_QUERY_PATH = "/home/vahid/Desktop/CommentCheck/queries/query_pull_request_threads.graphql"


def parse_iso8601(dt: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 timestamp from GitHub (YYYY-MM-DDTHH:MM:SSZ) into
    a timezone-aware datetime in UTC.
    """
    if not dt:
        return None
    return datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_github_token() -> str:
    """
    Load GITHUB_TOKEN from environment (.env already read via dotenv).
    Fail fast if not present.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set in environment or .env file.")
    return token


def graphql_request(session: requests.Session, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a GraphQL request and handle basic errors.
    """
    response = session.post(
        GITHUB_API_URL,
        json={"query": query, "variables": variables},
    )
    if response.status_code != 200:
        raise RuntimeError(f"GitHub GraphQL HTTP {response.status_code}: {response.text}")

    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL returned errors: {data['errors']}")
    return data["data"]


def load_pr_threads_query() -> str:
    """
    Load the PullRequestThreads GraphQL query from an external .graphql file
    and replace simple <PLACEHOLDER> tokens with configured values.

    We keep owner/name/cursor as GraphQL variables to minimize string
    interpolation while still letting you see/edit the core query separately.
    """
    with open(PR_THREADS_QUERY_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    replacements = {
        "<PRS_PER_PAGE>": str(PRS_PER_PAGE),
        "<THREADS_PER_PAGE>": str(THREADS_PER_PAGE),
        "<COMMENTS_PER_THREAD_PAGE>": str(COMMENTS_PER_THREAD_PAGE),
    }
    query = template
    for placeholder, value in replacements.items():
        query = query.replace(placeholder, value)
    return query


def ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def read_repos_list(path: str) -> List[str]:
    """
    Read repositories from the given path, one `owner/repo` per line.
    Ignores empty lines and comments starting with '#'.
    """
    repos: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            repos.append(stripped)
    return repos


def extract_linked_issues_from_text(text: str, owner: str, name: str) -> List[Dict[str, str]]:
    """
    Heuristic to extract linked issues from PR title/body text.

    We look for:
      - `#123`
      - `owner/repo#123`
      - URLs that end with `/issues/123`
    """
    issues: Dict[str, Dict[str, str]] = {}

    # owner/repo#123
    pattern_full_ref = re.compile(r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<num>\d+)")
    for m in pattern_full_ref.finditer(text or ""):
        num = m.group("num")
        full_owner = m.group("owner")
        repo = m.group("repo")
        key = f"{full_owner}/{repo}#{num}"
        if key not in issues:
            issues[key] = {
                "reference": key,
                "url": f"https://github.com/{full_owner}/{repo}/issues/{num}",
            }

    # bare #123, assume current repo
    pattern_local = re.compile(r"(?<![A-Za-z0-9_/.-])#(?P<num>\d+)")
    for m in pattern_local.finditer(text or ""):
        num = m.group("num")
        key = f"{owner}/{name}#{num}"
        if key not in issues:
            issues[key] = {
                "reference": f"#{num}",
                "url": f"https://github.com/{owner}/{name}/issues/{num}",
            }

    # URLs containing /issues/123
    pattern_url = re.compile(
        r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/issues/(?P<num>\d+)"
    )
    for m in pattern_url.finditer(text or ""):
        num = m.group("num")
        full_owner = m.group("owner")
        repo = m.group("repo")
        key = f"{full_owner}/{repo}#{num}"
        if key not in issues:
            issues[key] = {
                "reference": key,
                "url": m.group(0),
            }

    return list(issues.values())


def fetch_pr_diffs(
    session: requests.Session,
    owner: str,
    name: str,
    pr_number: int,
) -> Dict[str, Any]:
    """
    Fetch the full diff for a PR and per-file patches via the REST API.

    Returns a dict:
      {
        "prDiff": "<full patch text for the PR>",
        "fileDiffs": {
            "path/to/file.py": "<full patch text for that file>",
            ...
        }
      }
    """
    base_url = f"https://api.github.com/repos/{owner}/{name}/pulls/{pr_number}/files"
    page = 1
    per_page = 100
    all_files: List[Dict[str, Any]] = []

    while True:
        resp = session.get(base_url, params={"page": page, "per_page": per_page})
        if resp.status_code != 200:
            raise RuntimeError(
                f"GitHub REST HTTP {resp.status_code} while fetching PR files: {resp.text}"
            )
        batch = resp.json()
        if not batch:
            break
        all_files.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    file_diffs: Dict[str, Optional[str]] = {}
    full_pr_diff_parts: List[str] = []
    for f in all_files:
        filename = f.get("filename")
        patch = f.get("patch")
        if filename:
            file_diffs[filename] = patch
        if patch:
            full_pr_diff_parts.append(patch)

    return {
        "prDiff": "\n".join(full_pr_diff_parts),
        "fileDiffs": file_diffs,
    }


def collect_repo_comments(session: requests.Session, owner: str, name: str) -> List[Dict[str, Any]]:
    """
    Collect structured review comments that are attached to specific lines of code.
    Uses GitHub GraphQL reviewThreads to avoid fetching unrelated general comments.
    """
    print(f"[repo {owner}/{name}] starting collection...")

    collected: List[Dict[str, Any]] = []

    after_pr: Optional[str] = None
    total_prs_processed = 0

    pr_threads_query = load_pr_threads_query()
    pr_diff_cache: Dict[int, Dict[str, Any]] = {}

    while True:
        if MAX_COMMENTS_PER_REPO is not None and len(collected) >= MAX_COMMENTS_PER_REPO:
            print(f"[repo {owner}/{name}] reached MAX_COMMENTS_PER_REPO={MAX_COMMENTS_PER_REPO}, stopping.")
            break

        variables = {
            "owner": owner,
            "name": name,
            "afterPR": after_pr,
            "afterThread": None,
            "afterComment": None,
        }

        data = graphql_request(session, pr_threads_query, variables)
        repo_data = data.get("repository")
        if not repo_data:
            print(f"[repo {owner}/{name}] repository not found or inaccessible.")
            break

        prs = repo_data["pullRequests"]
        for pr in prs["nodes"]:
            total_prs_processed += 1
            pr_number = pr["number"]
            base_commit = pr.get("baseRefOid")
            head_commit = pr.get("headRefOid")
            pr_title = pr.get("title") or ""
            pr_body = pr.get("body") or ""
            pr_url = pr.get("url")
            pr_created_at = pr.get("createdAt")

            # Skip PRs created after the configured cutoff.
            cutoff_dt = parse_iso8601(PR_CREATED_BEFORE_ISO)
            pr_created_dt = parse_iso8601(pr_created_at)
            if cutoff_dt is not None and pr_created_dt is not None and pr_created_dt > cutoff_dt:
                continue

            linked_issues = extract_linked_issues_from_text(pr_title + "\n" + pr_body, owner, name)

            # Fetch full PR diff and per-file diffs once per PR and reuse.
            if pr_number not in pr_diff_cache:
                pr_diff_cache[pr_number] = fetch_pr_diffs(session, owner, name, pr_number)

            pr_diff_info = pr_diff_cache[pr_number]
            pr_full_diff = pr_diff_info.get("prDiff")
            file_diffs: Dict[str, Optional[str]] = pr_diff_info.get("fileDiffs", {})

            after_thread: Optional[str] = None
            pr_thread_page = pr["reviewThreads"]
            while True:
                for thread in pr_thread_page["nodes"]:
                    # Threads on specific lines have `path` and line info set.
                    path = thread.get("path")
                    if not path:
                        # Skip threads not tied to a particular file line.
                        continue

                    comments_conn = thread["comments"]
                    thread_comments = comments_conn["nodes"]
                    if not thread_comments:
                        continue

                    # Only count and export if there is at least one comment.
                    first_comment = thread_comments[0]
                    first_comment_id = first_comment.get("id")
                    first_comment_url = first_comment.get("url")
                    comment_text = first_comment.get("body") or ""

                    # Boolean: was there any reply (more than one comment in thread)?
                    has_reply = len(thread_comments) > 1

                    # GitHub UI shows "Outdated" when the underlying code has changed.
                    # We expose this as a `resolved` flag; true means the line changed
                    # before the PR was merged (i.e. GitHub marks it outdated).
                    resolved = bool(first_comment.get("outdated"))

                    # Whole thread serialized as simple list of messages
                    serialized_thread = []
                    for c in thread_comments:
                        serialized_thread.append(
                            {
                                "author": (c.get("author") or {}).get("login"),
                                "body": c.get("body"),
                                "createdAt": c.get("createdAt"),
                                "url": c.get("url"),
                            }
                        )

                    # Commit SHA for the first comment (where it was placed)
                    commit_obj = first_comment.get("commit")
                    comment_commit = commit_obj.get("oid") if commit_obj else None

                    # diffHunk is already the specific hunk for this comment.
                    diff_hunk = first_comment.get("diffHunk")

                    # Full diff for this specific file within the PR.
                    file_full_diff = file_diffs.get(path)

                    item = {
                        "commentText": comment_text,
                        "hasReply": has_reply,
                        "thread": serialized_thread,
                        "filePath": path,
                        "commentId": first_comment_id,
                        "commentUrl": first_comment_url,
                        "commentCommit": comment_commit,
                        "diffHunk": diff_hunk,
                        "fileDiff": file_full_diff,
                        "pullRequestDiff": pr_full_diff,
                        "resolved": resolved,
                        "pullRequestNumber": pr_number,
                        "pullRequestUrl": pr_url,
                        "pullRequestBaseCommit": base_commit,
                        "pullRequestHeadCommit": head_commit,
                        "pullRequestTitle": pr_title,
                        "pullRequestBody": pr_body,
                        "pullRequestCreatedAt": pr_created_at,
                        "linkedIssues": linked_issues,
                        "commentCreatedAt": first_comment.get("createdAt"),
                    }

                    collected.append(item)

                    if len(collected) % 20 == 0:
                        print(
                            f"[repo {owner}/{name}] collected {len(collected)} comments "
                            f"(processed {total_prs_processed} PRs so far)..."
                        )

                    if MAX_COMMENTS_PER_REPO is not None and len(collected) >= MAX_COMMENTS_PER_REPO:
                        break

                if MAX_COMMENTS_PER_REPO is not None and len(collected) >= MAX_COMMENTS_PER_REPO:
                    break

                # Pagination for comments inside threads is not deeply exploited here
                # because most review threads are short; for large threads we rely
                # on COMMENTS_PER_THREAD_PAGE.
                if not pr_thread_page["pageInfo"]["hasNextPage"]:
                    break
                after_thread = pr_thread_page["pageInfo"]["endCursor"]
                variables = {
                    "owner": owner,
                    "name": name,
                    "afterPR": after_pr,
                    "afterThread": after_thread,
                    "afterComment": None,
                }
                data = graphql_request(session, pr_threads_query, variables)
                pr_thread_page = data["repository"]["pullRequests"]["nodes"][0]["reviewThreads"]

            if MAX_COMMENTS_PER_REPO is not None and len(collected) >= MAX_COMMENTS_PER_REPO:
                break

        if not prs["pageInfo"]["hasNextPage"]:
            break
        after_pr = prs["pageInfo"]["endCursor"]
        print(f"[repo {owner}/{name}] moving to next page of PRs...")

    print(f"[repo {owner}/{name}] finished with {len(collected)} comments collected.")
    return collected


def main() -> None:
    load_dotenv()

    ensure_output_dir()

    token = load_github_token()

    repos = read_repos_list(REPOS_LIST_PATH)
    if not repos:
        print(f"No repositories found in {REPOS_LIST_PATH}. Nothing to do.")
        return

    print(f"Found {len(repos)} repositories to process.")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )

    for repo in repos:
        try:
            owner, name = repo.split("/", 1)
        except ValueError:
            print(f"Skipping invalid repo identifier: {repo}")
            continue

        try:
            comments = collect_repo_comments(session, owner, name)
        except Exception as exc:
            print(f"[repo {owner}/{name}] ERROR during collection: {exc}")
            continue

        output_path = os.path.join(OUTPUT_DIR, f"{owner}_{name}_comments.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, indent=2)

        print(f"[repo {owner}/{name}] wrote {len(comments)} comments to {output_path}")


if __name__ == "__main__":
    main()



