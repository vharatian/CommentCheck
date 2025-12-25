import os
import json
import re
import shutil
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TextIO

import requests
from dotenv import load_dotenv
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from tqdm import tqdm


# =========================
# Configuration
# =========================

# GitHub API configuration
GITHUB_API_URL = "https://api.github.com/graphql"

# Path to the repos list (one `owner/repo` per line)
REPOS_LIST_PATH = "/home/vahid/Desktop/CommentCheck/files/repos.txt"

# Output directory (one JSON per repo)
OUTPUT_DIR = "/home/vahid/Desktop/CommentCheck/files/comments"

# Directory for cloned git repositories
CLONES_DIR = "/home/vahid/Desktop/CommentCheck/files/clones"

# Maximum number of comments per repo to collect.
# If set to None, script will collect all available comments.
MAX_COMMENTS_PER_REPO: Optional[int] = 1000

# Only consider pull requests created on or before this ISO timestamp (UTC).
# Example format: "2025-12-01T00:00:00Z"
PR_CREATED_BEFORE_ISO = "2025-12-01T00:00:00Z"

# GraphQL pagination sizes – tuned to reduce number of requests.
PRS_PER_PAGE = 25
THREADS_PER_PAGE = 25
COMMENTS_PER_THREAD_PAGE = 50

# Number of parallel workers for processing repositories
MAX_WORKERS = 4

# Method to use for fetching PR diffs: "git" or "rest_api"
# "git": Use local git repository (requires cloning repos, but avoids REST API rate limits)
# "rest_api": Use GitHub REST API (no local repos needed, but uses API quota)
USE_GIT_FOR_DIFFS = True

# Rate limiting configuration
# Maximum requests per hour across all threads (set to 4800 to stay under 5000 limit)
MAX_REQUESTS_PER_HOUR = 4800

# Path to external GraphQL query template
PR_THREADS_QUERY_PATH = "/home/vahid/Desktop/CommentCheck/queries/query_pull_request_threads.graphql"

# Global rate limiter (shared across all threads)
_rate_limiter_lock = threading.Lock()
_rate_limiter: Optional[FixedWindowRateLimiter] = None


def get_rate_limiter() -> FixedWindowRateLimiter:
    """
    Get or create the shared rate limiter instance.
    Thread-safe singleton pattern.
    """
    global _rate_limiter
    if _rate_limiter is None:
        with _rate_limiter_lock:
            if _rate_limiter is None:
                storage = MemoryStorage()
                _rate_limiter = FixedWindowRateLimiter(storage)
    return _rate_limiter


def wait_for_rate_limit(limiter: FixedWindowRateLimiter, key: str = "github_api") -> None:
    """
    Wait if necessary to respect rate limits.
    Blocks until the request can be made without exceeding the limit.
    """
    limit_str = f"{MAX_REQUESTS_PER_HOUR}/hour"
    limits = parse_many(limit_str)
    
    for limit in limits:
        if not limiter.test(limit, key):
            # Calculate how long to wait
            reset_time = limiter.get_window_stats(limit, key).reset_time
            if reset_time:
                wait_seconds = (reset_time - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
            else:
                # Fallback: wait a small amount
                time.sleep(0.1)
    
    # Hit the limit (increment counter)
    for limit in limits:
        limiter.hit(limit, key)


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


def graphql_request(session: requests.Session, query: str, variables: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
    """
    Send a GraphQL request with retry logic and rate limiting.
    Retries on failures with 1 second delay between attempts.
    """
    limiter = get_rate_limiter()
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            # Wait for rate limit before making request
            wait_for_rate_limit(limiter, "github_api")
            
            response = session.post(
                GITHUB_API_URL,
                json={"query": query, "variables": variables},
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    # Check for rate limit errors
                    error_messages = [e.get("message", "") for e in data.get("errors", [])]
                    if any("rate limit" in msg.lower() for msg in error_messages):
                        if attempt < max_retries - 1:
                            time.sleep(1)
                            continue
                    raise RuntimeError(f"GitHub GraphQL returned errors: {data['errors']}")
                return data["data"]
            elif response.status_code == 403 or response.status_code == 429:
                # Rate limit or forbidden - retry with delay
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            elif response.status_code >= 500:
                # Server error - retry with delay
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            
            last_exception = RuntimeError(f"GitHub GraphQL HTTP {response.status_code}: {response.text}")
            
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
    
    # If we get here, all retries failed
    raise last_exception or RuntimeError("GraphQL request failed after all retries")


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
    os.makedirs(CLONES_DIR, exist_ok=True)


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


def fetch_pr_diffs_from_rest_api(
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
    limiter = get_rate_limiter()

    while True:
        # Retry logic for REST API calls
        max_retries = 3
        resp = None
        for attempt in range(max_retries):
            try:
                # Wait for rate limit before making request
                wait_for_rate_limit(limiter, "github_api")
                
                resp = session.get(base_url, params={"page": page, "per_page": per_page})
                
                if resp.status_code == 200:
                    break
                elif resp.status_code == 403 or resp.status_code == 429:
                    # Rate limit - retry with delay
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                elif resp.status_code >= 500:
                    # Server error - retry with delay
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                
                # If we get here and status is not 200, raise error
                raise RuntimeError(
                    f"GitHub REST HTTP {resp.status_code} while fetching PR files: {resp.text}"
                )
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise RuntimeError(f"GitHub REST API request failed: {e}")
        
        if resp is None or resp.status_code != 200:
            raise RuntimeError(
                f"GitHub REST HTTP {resp.status_code if resp else 'unknown'} while fetching PR files"
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


def ensure_repo_cloned(owner: str, name: str, token: Optional[str] = None, retry_clone: bool = True) -> str:
    """
    Ensure the repository is cloned locally with all required refs.
    Fetches PR refs (refs/pull/*/head and refs/pull/*/merge) to handle PRs from forks.
    If the repository already exists, fetches refs to ensure they're up to date.

    Returns the path to the cloned repository.
    """
    repo_path = os.path.join(CLONES_DIR, f"{owner}_{name}")
    repo_url = f"https://github.com/{owner}/{name}.git"
    
    # Set up environment for git commands with token if provided
    env = os.environ.copy()
    if token:
        # Use token in URL for authentication
        repo_url = f"https://{token}@github.com/{owner}/{name}.git"
        # Also set GIT_ASKPASS to avoid prompts
        env["GIT_TERMINAL_PROMPT"] = "0"

    # Check if repo exists and is a valid git repository
    git_dir = os.path.join(repo_path, ".git")
    if os.path.exists(repo_path):
        # Verify it's a valid git repository by checking for .git directory
        if os.path.exists(git_dir) or os.path.exists(os.path.join(repo_path, "config")):
            # Verify repository is working by running git log
            try:
                subprocess.run(
                    ["git", "-C", repo_path, "log", "-1", "--oneline"],
                    check=True,
                    capture_output=True,
                    env=env,
                )
                print(f"[{owner}/{name}] Repository already exists and is valid, fetching refs...")
            except subprocess.CalledProcessError as e:
                # git log failed, repository is corrupted, remove and clone fresh
                error_msg = e.stderr.decode() if e.stderr else str(e)
                print(f"[{owner}/{name}] Repository exists but git log failed, removing corrupted repository and cloning fresh...")
                print(f"[{owner}/{name}] Git log error: {error_msg}")
                shutil.rmtree(repo_path)
            else:
                # Repository is valid, fetch refs - PR refs are critical, must succeed
                try:
                    # Fetch all branches and tags from origin
                    subprocess.run(
                        ["git", "-C", repo_path, "fetch", "origin"],
                        check=True,
                        capture_output=True,
                        env=env,
                    )
                    # Fetch PR refs explicitly (refs/pull/*/head and refs/pull/*/merge)
                    # These are critical - if they fail, the repository won't work for PR diffs
                    result_head = subprocess.run(
                        ["git", "-C", repo_path, "fetch", "origin", "+refs/pull/*/head:refs/pull/*/head"],
                        check=False,
                        capture_output=True,
                        env=env,
                    )
                    result_merge = subprocess.run(
                        ["git", "-C", repo_path, "fetch", "origin", "+refs/pull/*/merge:refs/pull/*/merge"],
                        check=False,
                        capture_output=True,
                        env=env,
                    )
                    
                    # Check if PR ref fetch failed - this is critical for PR diffs
                    if result_head.returncode != 0 or result_merge.returncode != 0:
                        error_parts = []
                        if result_head.returncode != 0:
                            error_parts.append(f"PR head refs: {result_head.stderr.decode() if result_head.stderr else 'unknown error'}")
                        if result_merge.returncode != 0:
                            error_parts.append(f"PR merge refs: {result_merge.stderr.decode() if result_merge.stderr else 'unknown error'}")
                        full_error = "\n".join(error_parts)
                        print(f"[{owner}/{name}] ERROR: PR ref fetch failed - repository cannot be used for PR diffs")
                        print(f"[{owner}/{name}] Full error:\n{full_error}")
                        raise RuntimeError(f"PR ref fetch failed for {owner}/{name}. All diffs are from PRs, so this repository cannot be used.\nFull error:\n{full_error}")
                    
                    print(f"[{owner}/{name}] Refs fetched successfully.")
                except RuntimeError:
                    # Re-raise RuntimeError from PR ref fetch failure
                    raise
                except subprocess.CalledProcessError as e:
                    # Other fetch failures are also critical
                    error_msg = e.stderr.decode() if e.stderr else str(e)
                    print(f"[{owner}/{name}] ERROR: Git fetch failed - repository cannot be used")
                    print(f"[{owner}/{name}] Full error: {error_msg}")
                    raise RuntimeError(f"Git fetch failed for {owner}/{name}. Repository cannot be used for PR diffs.\nFull error: {error_msg}")
                return repo_path
        else:
            # Directory exists but isn't a valid git repo, remove it and clone fresh
            print(f"[{owner}/{name}] Directory exists but is not a valid git repository, removing and cloning fresh...")
            shutil.rmtree(repo_path)

    # Clone the repository normally (not mirror)
    print(f"[{owner}/{name}] Cloning repository (this may take a while for large repos)...")
    try:
        subprocess.run(
            ["git", "clone", repo_url, repo_path],
            check=True,
            capture_output=True,
            env=env,
        )
        print(f"[{owner}/{name}] Repository cloned successfully.")
        
        # Verify the clone is working by running git log
        try:
            subprocess.run(
                ["git", "-C", repo_path, "log", "-1", "--oneline"],
                check=True,
                capture_output=True,
                env=env,
            )
            print(f"[{owner}/{name}] Repository verified (git log successful).")
        except subprocess.CalledProcessError as e:
            # Clone completed but git log failed, repository is corrupted
            # Remove the directory and retry cloning if we haven't already retried
            error_msg = e.stderr.decode() if e.stderr else str(e)
            print(f"[{owner}/{name}] Git log failed after clone, removing corrupted repository...")
            print(f"[{owner}/{name}] Git log error: {error_msg}")
            if os.path.exists(repo_path):
                try:
                    shutil.rmtree(repo_path)
                except Exception:
                    pass
            
            if retry_clone:
                print(f"[{owner}/{name}] Retrying clone...")
                return ensure_repo_cloned(owner, name, token, retry_clone=False)
            else:
                raise RuntimeError(f"Git clone verification failed for {owner}/{name} after retry: {error_msg}")
            
    except subprocess.CalledProcessError as e:
        # Clean up partial clone on error
        if os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
            except Exception:
                pass
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise RuntimeError(f"Git clone failed for {owner}/{name}: {error_msg}")

    # After cloning, fetch PR refs - these are critical, must succeed
    print(f"[{owner}/{name}] Fetching PR refs...")
    try:
        # Fetch all branches and tags from origin
        subprocess.run(
            ["git", "-C", repo_path, "fetch", "origin"],
            check=True,
            capture_output=True,
            env=env,
        )
        # Fetch PR refs explicitly (refs/pull/*/head and refs/pull/*/merge)
        # These are critical - if they fail, the repository won't work for PR diffs
        result_head = subprocess.run(
            ["git", "-C", repo_path, "fetch", "origin", "+refs/pull/*/head:refs/pull/*/head"],
            check=False,
            capture_output=True,
            env=env,
        )
        result_merge = subprocess.run(
            ["git", "-C", repo_path, "fetch", "origin", "+refs/pull/*/merge:refs/pull/*/merge"],
            check=False,
            capture_output=True,
            env=env,
        )
        
        # Check if PR ref fetch failed - this is critical for PR diffs
        if result_head.returncode != 0 or result_merge.returncode != 0:
            error_parts = []
            if result_head.returncode != 0:
                error_parts.append(f"PR head refs: {result_head.stderr.decode() if result_head.stderr else 'unknown error'}")
            if result_merge.returncode != 0:
                error_parts.append(f"PR merge refs: {result_merge.stderr.decode() if result_merge.stderr else 'unknown error'}")
            full_error = "\n".join(error_parts)
            print(f"[{owner}/{name}] ERROR: PR ref fetch failed - repository cannot be used for PR diffs")
            print(f"[{owner}/{name}] Full error:\n{full_error}")
            raise RuntimeError(f"PR ref fetch failed for {owner}/{name}. All diffs are from PRs, so this repository cannot be used.\nFull error:\n{full_error}")
        
        print(f"[{owner}/{name}] PR refs fetched successfully.")
    except RuntimeError:
        # Re-raise RuntimeError from PR ref fetch failure
        raise
    except subprocess.CalledProcessError as e:
        # Other fetch failures are also critical
        error_msg = e.stderr.decode() if e.stderr else str(e)
        print(f"[{owner}/{name}] ERROR: Git fetch failed - repository cannot be used")
        print(f"[{owner}/{name}] Full error: {error_msg}")
        raise RuntimeError(f"Git fetch failed for {owner}/{name}. Repository cannot be used for PR diffs.\nFull error: {error_msg}")

    return repo_path


def fetch_pr_diffs_from_git(
    repo_path: str,
    base_commit: str,
    head_commit: str,
) -> Dict[str, Any]:
    """
    Fetch the full diff for a PR and per-file patches using local git repository.

    Args:
        repo_path: Path to the local git repository
        base_commit: Base commit SHA (baseRefOid)
        head_commit: Head commit SHA (headRefOid)

    Returns a dict:
      {
        "prDiff": "<full patch text for the PR>",
        "fileDiffs": {
            "path/to/file.py": "<full patch text for that file>",
            ...
        }
      }
    """
    file_diffs: Dict[str, Optional[str]] = {}

    try:
        # First, verify commits exist locally
        missing_commits = []
        for commit in [base_commit, head_commit]:
            if not commit:
                missing_commits.append(commit)
                continue
            result = subprocess.run(
                ["git", "-C", repo_path, "cat-file", "-e", commit],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                missing_commits.append(commit)
                # Commit doesn't exist, try to fetch it
                try:
                    subprocess.run(
                        ["git", "-C", repo_path, "fetch", "origin", commit],
                        check=False,
                        capture_output=True,
                    )
                    # Verify it was fetched successfully
                    verify_result = subprocess.run(
                        ["git", "-C", repo_path, "cat-file", "-e", commit],
                        check=False,
                        capture_output=True,
                    )
                    if verify_result.returncode != 0:
                        missing_commits.append(commit)
                except Exception as e:
                    # Other errors fetching commit
                    print(f"Warning: Could not fetch commit {commit[:8]}...: {e}")
                    missing_commits.append(commit)

        # If we're missing commits, we can't generate a proper diff
        if missing_commits:
            print(f"Warning: Missing commits {[c[:8] + '...' if c else 'None' for c in missing_commits]}, returning empty diff")
            return {
                "prDiff": "",
                "fileDiffs": {},
            }

        # Get list of changed files
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", f"{base_commit}..{head_commit}"],
            check=True,
            capture_output=True,
            text=True,
        )
        changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        # Get full PR diff
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", f"{base_commit}..{head_commit}"],
            check=True,
            capture_output=True,
            text=True,
        )
        full_pr_diff = result.stdout

        # Get per-file diffs
        for filepath in changed_files:
            try:
                result = subprocess.run(
                    ["git", "-C", repo_path, "diff", f"{base_commit}..{head_commit}", "--", filepath],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                file_diffs[filepath] = result.stdout if result.stdout.strip() else None
            except subprocess.CalledProcessError as e:
                # Skip this file if diff fails
                print(f"Warning: Could not generate diff for {filepath}: {e}")
                file_diffs[filepath] = None
    except subprocess.CalledProcessError as e:
        # If we can't generate the diff, return empty diffs
        print(f"Warning: Could not generate diff for {base_commit[:8]}..{head_commit[:8]}: {e.stderr.decode() if e.stderr else str(e)}")
        return {
            "prDiff": "",
            "fileDiffs": {},
        }
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Warning: Unexpected error generating diff for {base_commit[:8]}..{head_commit[:8]}: {e}")
        return {
            "prDiff": "",
            "fileDiffs": {},
        }

    return {
        "prDiff": full_pr_diff,
        "fileDiffs": file_diffs,
    }


def collect_repo_comments(
    token: str, owner: str, name: str, output_file: TextIO, progress_bar: Optional[tqdm] = None
) -> Tuple[str, str, int, Optional[str]]:
    """
    Collect structured review comments that are attached to specific lines of code.
    Uses GitHub GraphQL reviewThreads to avoid fetching unrelated general comments.
    Writes comments incrementally to output_file in JSONL format.

    Returns: (owner, name, comment_count, error_message)
    """
    # Create a session per worker (thread-safe)
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )

    # Ensure repository is cloned locally if using git for diffs
    repo_path: Optional[str] = None
    if USE_GIT_FOR_DIFFS:
        try:
            repo_path = ensure_repo_cloned(owner, name, token)
        except Exception as e:
            # If git clone fails, skip this repository
            error_msg = str(e)
            print(f"[{owner}/{name}] Git clone failed, skipping repository: {error_msg}")
            return (owner, name, 0, f"Failed to clone repository: {error_msg}")

    comment_count = 0

    after_pr: Optional[str] = None
    total_prs_processed = 0

    pr_threads_query = load_pr_threads_query()
    pr_diff_cache: Dict[int, Dict[str, Any]] = {}

    while True:
        if MAX_COMMENTS_PER_REPO is not None and comment_count >= MAX_COMMENTS_PER_REPO:
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
                if USE_GIT_FOR_DIFFS:
                    if repo_path is None:
                        # This shouldn't happen if USE_GIT_FOR_DIFFS is True, but handle it gracefully
                        return (owner, name, comment_count, "Repository path not available for git diff")
                    pr_diff_cache[pr_number] = fetch_pr_diffs_from_git(
                        repo_path, base_commit, head_commit
                    )
                else:
                    pr_diff_cache[pr_number] = fetch_pr_diffs_from_rest_api(
                        session, owner, name, pr_number
                    )

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
                    # If GitHub doesn't provide a diff hunk (or it's empty),
                    # skip this comment – it doesn't have a concrete code context.
                    if not diff_hunk or not str(diff_hunk).strip():
                        continue

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

                    # Write immediately to JSONL file (incremental writing)
                    try:
                        output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
                        output_file.flush()  # Ensure data is written to disk
                        comment_count += 1
                    except Exception as e:
                        return (owner, name, comment_count, f"Failed to write comment: {e}")

                    # Update progress bar if provided (every 10 comments to reduce overhead)
                    if progress_bar and comment_count % 10 == 0:
                        progress_bar.set_postfix(
                            {
                                "comments": comment_count,
                                "PRs": total_prs_processed,
                            },
                            refresh=False,
                        )
                        progress_bar.n = comment_count
                        progress_bar.refresh()

                    if MAX_COMMENTS_PER_REPO is not None and comment_count >= MAX_COMMENTS_PER_REPO:
                        break

                if MAX_COMMENTS_PER_REPO is not None and comment_count >= MAX_COMMENTS_PER_REPO:
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

            if MAX_COMMENTS_PER_REPO is not None and comment_count >= MAX_COMMENTS_PER_REPO:
                break

        if not prs["pageInfo"]["hasNextPage"]:
            break
        after_pr = prs["pageInfo"]["endCursor"]

    return (owner, name, comment_count, None)


def process_single_repo(
    repo: str, token: str, repo_progress_bars: Dict[str, tqdm], output_dir: str
) -> Tuple[str, str, int, Optional[str]]:
    """
    Worker function to process a single repository.
    Returns: (owner, name, comment_count, error_message)
    """
    try:
        owner, name = repo.split("/", 1)
    except ValueError:
        return (repo, "", 0, f"Invalid repo identifier: {repo}")

    repo_key = f"{owner}/{name}"
    progress_bar = repo_progress_bars.get(repo_key)
    
    # Open output file for this repo (JSONL format)
    output_path = os.path.join(output_dir, f"{owner}_{name}_comments.jsonl")
    try:
        with open(output_path, "w", encoding="utf-8") as output_file:
            try:
                return collect_repo_comments(token, owner, name, output_file, progress_bar)
            except Exception as exc:
                return (owner, name, 0, str(exc))
    except Exception as exc:
        return (owner, name, 0, f"Failed to open output file: {exc}")


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to a human-readable string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs:.1f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:.1f}s"
    else:
        return f"{secs:.1f}s"


def main() -> None:
    # Start timing
    start_time = time.perf_counter()
    
    load_dotenv()

    ensure_output_dir()

    token = load_github_token()

    repos = read_repos_list(REPOS_LIST_PATH)
    if not repos:
        print(f"No repositories found in {REPOS_LIST_PATH}. Nothing to do.")
        return

    print(f"Found {len(repos)} repositories to process.")
    print(f"Using {MAX_WORKERS} parallel workers.\n")

    # Create progress bars for each repo
    repo_progress_bars: Dict[str, tqdm] = {}
    for repo in repos:
        try:
            owner, name = repo.split("/", 1)
            repo_key = f"{owner}/{name}"
            # Create a progress bar for this repo (will be updated as comments are collected)
            repo_progress_bars[repo_key] = tqdm(
                total=MAX_COMMENTS_PER_REPO if MAX_COMMENTS_PER_REPO else None,
                desc=f"{repo_key[:35]:<35}",
                position=len(repo_progress_bars),
                leave=True,
                unit="comment",
                dynamic_ncols=True,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{postfix}]",
            )
        except ValueError:
            continue

    # Overall progress bar
    overall_pbar = tqdm(
        total=len(repos),
        desc="Overall Progress",
        position=len(repo_progress_bars),
        leave=True,
        unit="repo",
    )

    # Process repos in parallel
    results: List[Tuple[str, str, int, Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(process_single_repo, repo, token, repo_progress_bars, OUTPUT_DIR): repo
            for repo in repos
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                result = future.result()
                results.append(result)
                overall_pbar.update(1)
            except Exception as exc:
                try:
                    owner, name = repo.split("/", 1)
                except ValueError:
                    owner, name = repo, ""
                results.append((owner, name, 0, str(exc)))
                overall_pbar.update(1)

    # Final update and close all progress bars
    for repo_key, pbar in repo_progress_bars.items():
        # Find the result for this repo to get final count
        for owner, name, comment_count, _ in results:
            if f"{owner}/{name}" == repo_key:
                pbar.n = comment_count
                pbar.set_postfix({"comments": comment_count, "PRs": "done"})
                pbar.refresh()
                break
        pbar.close()
    overall_pbar.close()

    # Print summary (files are already written incrementally)
    print("\n" + "=" * 60)
    print("Processing Summary")
    print("=" * 60)

    for owner, name, comment_count, error in results:
        if error:
            print(f"[{owner}/{name}] ERROR: {error}")
            continue

        output_path = os.path.join(OUTPUT_DIR, f"{owner}_{name}_comments.jsonl")
        if comment_count > 0:
            print(f"[{owner}/{name}] ✓ Collected {comment_count} comments (saved to {output_path})")
        else:
            print(f"[{owner}/{name}] No comments collected.")

    # Calculate and display total execution time
    end_time = time.perf_counter()
    total_duration = end_time - start_time
    
    print("\n" + "=" * 60)
    print("All repositories processed!")
    print(f"Total execution time: {format_duration(total_duration)}")
    print("=" * 60)


if __name__ == "__main__":
    main()



