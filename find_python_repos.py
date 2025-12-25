import os
import csv
import time
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

# =========================
# Configuration
# =========================

# GitHub API configuration
GITHUB_API_URL = "https://api.github.com/graphql"

# GraphQL query file path
SEARCH_QUERY_PATH = "/home/vahid/Desktop/CommentCheck/queries/query_search_repositories.graphql"

# Output CSV file base path (timestamp will be added automatically)
OUTPUT_CSV_BASE_PATH = "/home/vahid/Desktop/CommentCheck/files/repos/repos"

# Search parameters
PYTHON_PERCENTAGE_THRESHOLD = 95.0  # Minimum Python percentage (95%)
REPOSITORY_THRESHOLD = 20  # Stop after finding this many repositories
REPOSITORIES_PER_PAGE = 50  # Number of repos per GraphQL query page (reduced to avoid resource limits)
MIN_STARS = 1000  # Minimum stars to consider (adjust as needed)
MIN_ISSUES = 5000  # Minimum number of issues required
MIN_PRS = 5000  # Minimum number of PRs required
ISSUE_ACTIVITY_MONTHS = 24  # Consider issues "active" if updated within this many months

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Debug logging
ENABLE_DEBUG_LOGS = False  # Set to False to reduce log verbosity


def load_github_token() -> str:
    """
    Load GITHUB_TOKEN from environment (.env already read via dotenv).
    Fail fast if not present.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set in environment or .env file.")
    return token


def load_search_query() -> str:
    """
    Load the GraphQL query from the external file.
    """
    if ENABLE_DEBUG_LOGS:
        print(f"[DEBUG] Loading GraphQL query from: {SEARCH_QUERY_PATH}")
    if not os.path.exists(SEARCH_QUERY_PATH):
        raise FileNotFoundError(f"GraphQL query file not found: {SEARCH_QUERY_PATH}")
    
    with open(SEARCH_QUERY_PATH, "r", encoding="utf-8") as f:
        query = f.read()
    
    if ENABLE_DEBUG_LOGS:
        print(f"[DEBUG] Query loaded successfully ({len(query)} characters)")
    return query


def graphql_request(
    session: requests.Session,
    query: str,
    variables: Dict[str, Any],
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Send a GraphQL request with retry logic.
    """
    try:
        if ENABLE_DEBUG_LOGS:
            print(f"\n[DEBUG] Sending GraphQL request (attempt {retry_count + 1})...")
            print(f"[DEBUG] Variables: {json.dumps(variables, indent=2)}")
        
        response = session.post(
            GITHUB_API_URL,
            json={"query": query, "variables": variables},
        )
        
        if ENABLE_DEBUG_LOGS:
            print(f"[DEBUG] Response status code: {response.status_code}")
        
        if response.status_code != 200:
            if ENABLE_DEBUG_LOGS:
                print(f"[DEBUG] Error response body: {response.text}")
            if retry_count < MAX_RETRIES:
                print(f"  HTTP {response.status_code}, retrying ({retry_count + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
                return graphql_request(session, query, variables, retry_count + 1)
            raise RuntimeError(f"GitHub GraphQL HTTP {response.status_code}: {response.text}")

        data = response.json()
        if ENABLE_DEBUG_LOGS:
            print(f"[DEBUG] Response data keys: {list(data.keys())}")
        
        if "errors" in data:
            if ENABLE_DEBUG_LOGS:
                print(f"[DEBUG] GraphQL errors found:")
            # Check if errors are critical (non-resource-limit errors)
            critical_errors = []
            resource_limit_errors = []
            
            for error in data["errors"]:
                error_type = error.get("type", "")
                error_msg = error.get("message", "")
                if ENABLE_DEBUG_LOGS:
                    print(f"  - {json.dumps(error, indent=2)}")
                
                if error_type == "RESOURCE_LIMITS_EXCEEDED":
                    resource_limit_errors.append(error)
                else:
                    critical_errors.append(error)
            
            # If we have critical errors, fail
            if critical_errors:
                if retry_count < MAX_RETRIES:
                    print(f"  Critical GraphQL errors, retrying ({retry_count + 1}/{MAX_RETRIES})...")
                    time.sleep(RETRY_DELAY)
                    return graphql_request(session, query, variables, retry_count + 1)
                
                error_messages = []
                for error in critical_errors:
                    msg = error.get("message", "Unknown error")
                    locations = error.get("locations", [])
                    path = error.get("path", [])
                    error_messages.append(f"Message: {msg}, Locations: {locations}, Path: {path}")
                
                raise RuntimeError(f"GitHub GraphQL returned critical errors:\n" + "\n".join(error_messages))
            
            # If only resource limit errors, we can still process the data that was returned
            # (some nodes may have failed, but others may have succeeded)
            if resource_limit_errors:
                print(f"[WARNING] Resource limit errors occurred for some repositories, but continuing with available data...")
                if ENABLE_DEBUG_LOGS:
                    print(f"  Affected paths: {[err.get('path', []) for err in resource_limit_errors]}")
        
        if "data" not in data:
            if ENABLE_DEBUG_LOGS:
                print(f"[DEBUG] No 'data' key in response. Full response: {json.dumps(data, indent=2)}")
            raise RuntimeError(f"Unexpected response format: {json.dumps(data, indent=2)}")
            
        if ENABLE_DEBUG_LOGS:
            print(f"[DEBUG] Request successful")
        return data["data"]
    
    except requests.RequestException as e:
        if ENABLE_DEBUG_LOGS:
            print(f"[DEBUG] Request exception type: {type(e).__name__}: {str(e)}")
        if retry_count < MAX_RETRIES:
            print(f"  Request exception: {e}, retrying ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(RETRY_DELAY)
            return graphql_request(session, query, variables, retry_count + 1)
        raise
    except json.JSONDecodeError as e:
        if ENABLE_DEBUG_LOGS:
            print(f"[DEBUG] JSON decode error: {e}")
            print(f"[DEBUG] Response text: {response.text if 'response' in locals() else 'N/A'}")
        raise RuntimeError(f"Failed to parse JSON response: {e}")


def calculate_python_percentage(languages_data: Dict[str, Any]) -> Optional[float]:
    """
    Calculate the percentage of Python code in the repository.
    Returns None if no language data is available.
    """
    if not languages_data or "edges" not in languages_data:
        return None
    
    edges = languages_data["edges"]
    if not edges:
        return None
    
    total_size = languages_data.get("totalSize", 0)
    if total_size == 0:
        return None
    
    # Find Python language size
    python_size = 0
    for edge in edges:
        lang_name = edge.get("node", {}).get("name", "")
        if lang_name.lower() == "python":
            python_size = edge.get("size", 0)
            break
    
    if python_size == 0:
        return 0.0
    
    percentage = (python_size / total_size) * 100.0
    return percentage


def is_actively_using_issues(issues_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Determine if repository is actively using issues based on recent activity.
    Returns (is_active, last_updated_date).
    A repository is considered active if:
    - Has at least one issue
    - The most recently updated issue was updated within ISSUE_ACTIVITY_MONTHS months
    """
    if not issues_data:
        return False, None
    
    total_count = issues_data.get("totalCount", 0)
    if total_count == 0:
        return False, None
    
    nodes = issues_data.get("nodes", [])
    if not nodes or len(nodes) == 0:
        # Has issues but can't determine activity (shouldn't happen, but safe)
        return True, None
    
    # Get the most recently updated issue
    most_recent = nodes[0]
    updated_at_str = most_recent.get("updatedAt")
    
    if not updated_at_str:
        return True, None
    
    # Parse the ISO 8601 datetime
    try:
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        cutoff_date = datetime.now(updated_at.tzinfo) - timedelta(days=ISSUE_ACTIVITY_MONTHS * 30)
        
        is_active = updated_at >= cutoff_date
        return is_active, updated_at_str
    except (ValueError, AttributeError):
        # If parsing fails, assume active since they have issues
        return True, updated_at_str


def generate_csv_path() -> str:
    """
    Generate a timestamped CSV file path.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"{OUTPUT_CSV_BASE_PATH}_{timestamp}.csv"
    return csv_path


def ensure_csv_file_exists(csv_path: str):
    """
    Initialize the CSV file with headers. Always creates a new file.
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    # Always create a new file with headers
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Repository",
            "Stars",
            "Python_Percentage",
            "PR_Count",
            "Issue_Count",
            "Issues_Active",
            "Last_Issue_Updated"
        ])


def write_repo_to_csv(csv_path: str, repo_info: Dict[str, Any]):
    """
    Append a single repository to the CSV file.
    """
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            repo_info["nameWithOwner"],
            repo_info["stars"],
            f"{repo_info['python_percentage']:.2f}",
            repo_info["pr_count"],
            repo_info["issue_count"],
            "Yes" if repo_info["issues_active"] else "No",
            repo_info["last_issue_updated"] or ""
        ])


def search_python_repositories(session: requests.Session, query_template: str) -> None:
    """
    Search for repositories that are at least 95% Python, sorted by popularity.
    """
    # Generate timestamped CSV file path
    csv_path = generate_csv_path()
    ensure_csv_file_exists(csv_path)
    
    filtered_count = 0
    pages_traversed = 0
    after_cursor: Optional[str] = None
    
    # Search query: repositories with Python language, sorted by stars
    search_query_string = f"language:python stars:>={MIN_STARS} sort:stars-desc"
    
    print(f"Starting search for Python repositories (>= {PYTHON_PERCENTAGE_THRESHOLD}% Python)...")
    print(f"Search query: {search_query_string}")
    print(f"Filters: >= {MIN_ISSUES} issues, >= {MIN_PRS} PRs")
    print(f"Target: Find {REPOSITORY_THRESHOLD} repositories")
    print(f"Output CSV: {csv_path}")
    print("-" * 60)
    
    while filtered_count < REPOSITORY_THRESHOLD:
        pages_traversed += 1
        
        variables = {
            "query": search_query_string,
            "first": REPOSITORIES_PER_PAGE,
            "after": after_cursor
        }
        
        print(f"\n[Page {pages_traversed}] Fetching {REPOSITORIES_PER_PAGE} repositories...")
        
        try:
            data = graphql_request(session, query_template, variables)
        except Exception as e:
            print(f"  Error fetching page {pages_traversed}: {e}")
            break
        
        search_results = data.get("search", {})
        repositories = search_results.get("nodes", [])
        page_info = search_results.get("pageInfo", {})
        has_next_page = page_info.get("hasNextPage", False)
        after_cursor = page_info.get("endCursor")
        
        if not repositories:
            print("  No more repositories found.")
            break
        
        print(f"  Processing {len(repositories)} repositories from this page...")
        
        for repo in repositories:
            if filtered_count >= REPOSITORY_THRESHOLD:
                break
            
            # Skip if repository data is None (may happen due to resource limit errors)
            if repo is None:
                print(f"    ⚠ Skipping repository with null data (may be due to resource limits)")
                continue
            
            name_with_owner = repo.get("nameWithOwner", "")
            if not name_with_owner:
                print(f"    ⚠ Skipping repository with missing nameWithOwner")
                continue
            
            stars = repo.get("stargazerCount", 0)
            languages = repo.get("languages", {})
            pr_count = repo.get("pullRequests", {}).get("totalCount", 0)
            issues_data = repo.get("issues")
            
            # Handle case where issues data might be None due to resource limits
            if issues_data is None:
                print(f"    ⚠ {name_with_owner}: Issues data unavailable (resource limit)")
                continue
            
            issue_count = issues_data.get("totalCount", 0)
            
            # Filter: Check minimum PRs
            if pr_count < MIN_PRS:
                print(f"    ✗ {name_with_owner}: {pr_count} PRs (below {MIN_PRS} threshold)")
                continue
            
            # Filter: Check minimum issues
            if issue_count < MIN_ISSUES:
                print(f"    ✗ {name_with_owner}: {issue_count} issues (below {MIN_ISSUES} threshold)")
                continue
            
            # Calculate Python percentage
            python_percentage = calculate_python_percentage(languages)
            
            if python_percentage is None:
                print(f"    ⚠ {name_with_owner}: No language data available")
                continue
            
            if python_percentage < PYTHON_PERCENTAGE_THRESHOLD:
                print(f"    ✗ {name_with_owner}: {python_percentage:.2f}% Python (below threshold)")
                continue
            
            # Check if actively using issues
            issues_active, last_issue_updated = is_actively_using_issues(issues_data)
            
            # Repository meets all criteria
            filtered_count += 1
            repo_info = {
                "nameWithOwner": name_with_owner,
                "stars": stars,
                "python_percentage": python_percentage,
                "pr_count": pr_count,
                "issue_count": issue_count,
                "issues_active": issues_active,
                "last_issue_updated": last_issue_updated
            }
            
            # Write to CSV immediately
            write_repo_to_csv(csv_path, repo_info)
            
            active_status = "active" if issues_active else "inactive"
            print(f"    ✓ [{filtered_count}/{REPOSITORY_THRESHOLD}] {name_with_owner}: "
                  f"{stars} stars, {python_percentage:.2f}% Python, {pr_count} PRs, "
                  f"{issue_count} issues ({active_status})")
        
        print(f"\n  Progress: {filtered_count} repositories found so far")
        
        if not has_next_page:
            print("\n  No more pages available.")
            break
        
        if filtered_count >= REPOSITORY_THRESHOLD:
            break
        
        # Rate limiting: GitHub API allows 5000 requests/hour for authenticated users
        # We're being conservative with a small delay
        time.sleep(0.5)
    
    print("\n" + "=" * 60)
    print(f"Search completed!")
    print(f"  Total pages traversed: {pages_traversed}")
    print(f"  Repositories found: {filtered_count}")
    print(f"  Output saved to: {csv_path}")


def main() -> None:
    """
    Main entry point.
    """
    # Load environment variables
    load_dotenv()
    
    # Load GitHub token
    token = load_github_token()
    
    # Load GraphQL query
    query_template = load_search_query()
    
    # Create session with authentication
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    
    # Start searching
    try:
        search_python_repositories(session, query_template)
    except KeyboardInterrupt:
        print("\n\nSearch interrupted by user.")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
