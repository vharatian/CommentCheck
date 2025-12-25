#!/usr/bin/env python3
"""
Script to analyze comment files and create a balanced validation dataset.

This script:
1. Analyzes all JSON files in files/comments/ folder
2. Provides an overview of resolved vs unresolved comments per repository
3. Creates a balanced dataset with specified number of samples per repository
4. Saves the balanced dataset to validation.csv
"""

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from tqdm import tqdm

# =========================
# Configuration Constants
# =========================

# Input directory containing comment JSON files
COMMENTS_DIR = "/home/vahid/Desktop/CommentCheck/files/comments"

# Output CSV file path
OUTPUT_CSV = "/home/vahid/Desktop/CommentCheck/files/validation.csv"

# Number of samples per dataset (should be even to allow equal resolved/unresolved split)
# For example: 16 means 8 resolved + 8 unresolved per repository
SAMPLES_PER_DATASET = 16

# Random seed for reproducibility
RANDOM_SEED = 42


def extract_repo_name_from_filename(filename: str) -> str:
    """
    Extract repository name from filename.
    
    Filename format: {owner}_{repo}_comments.json
    Returns: {owner}/{repo}
    """
    # Remove .json extension and _comments suffix
    base_name = filename.replace("_comments.json", "")
    # Replace last underscore with / to get owner/repo format
    parts = base_name.rsplit("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return base_name


def load_comments_from_file(file_path: Path) -> List[Dict]:
    """Load comments from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_comments() -> Tuple[Dict[str, Dict], Dict[str, List[Dict]]]:
    """
    Analyze all comment files and return statistics and organized comments.
    
    Returns:
        - stats: Dictionary with repo_name -> {resolved: int, unresolved: int, total: int}
        - comments_by_repo: Dictionary with repo_name -> list of all comments
    """
    comments_dir = Path(COMMENTS_DIR)
    if not comments_dir.exists():
        raise FileNotFoundError(f"Comments directory not found: {COMMENTS_DIR}")
    
    stats: Dict[str, Dict] = {}
    comments_by_repo: Dict[str, List[Dict]] = {}
    
    # Get all JSON files
    json_files = list(comments_dir.glob("*_comments.json"))
    
    print(f"\n{'='*60}")
    print(f"Analyzing {len(json_files)} comment files...")
    print(f"{'='*60}\n")
    
    for json_file in tqdm(json_files, desc="Loading comment files"):
        repo_name = extract_repo_name_from_filename(json_file.name)
        
        try:
            comments = load_comments_from_file(json_file)
            
            # Count resolved vs unresolved
            resolved_count = sum(1 for c in comments if c.get("resolved", False))
            unresolved_count = sum(1 for c in comments if not c.get("resolved", False))
            total_count = len(comments)
            
            stats[repo_name] = {
                "resolved": resolved_count,
                "unresolved": unresolved_count,
                "total": total_count,
            }
            comments_by_repo[repo_name] = comments
            
        except Exception as e:
            print(f"\nError loading {json_file.name}: {e}")
            continue
    
    return stats, comments_by_repo


def print_overview(stats: Dict[str, Dict]):
    """Print overview statistics."""
    print(f"\n{'='*60}")
    print("OVERVIEW: Resolved vs Unresolved Comments")
    print(f"{'='*60}\n")
    
    # Print per-repository statistics
    print(f"{'Repository':<40} {'Resolved':<12} {'Unresolved':<12} {'Total':<12}")
    print("-" * 76)
    
    total_resolved = 0
    total_unresolved = 0
    total_comments = 0
    
    for repo_name in sorted(stats.keys()):
        repo_stats = stats[repo_name]
        resolved = repo_stats["resolved"]
        unresolved = repo_stats["unresolved"]
        total = repo_stats["total"]
        
        print(f"{repo_name:<40} {resolved:<12} {unresolved:<12} {total:<12}")
        
        total_resolved += resolved
        total_unresolved += unresolved
        total_comments += total
    
    # Print totals
    print("-" * 76)
    print(f"{'TOTAL':<40} {total_resolved:<12} {total_unresolved:<12} {total_comments:<12}")
    print(f"\nOverall: {total_resolved} resolved, {total_unresolved} unresolved, {total_comments} total")


def create_balanced_dataset(
    comments_by_repo: Dict[str, List[Dict]],
    stats: Dict[str, Dict]
) -> pd.DataFrame:
    """
    Create a balanced dataset with specified number of samples per repository.
    
    Args:
        comments_by_repo: Dictionary mapping repo names to lists of comments
        stats: Dictionary with statistics per repository
    
    Returns:
        DataFrame with columns: reponame, PR_link, comment_link, resolved
    """
    # Set random seed for reproducibility
    random.seed(RANDOM_SEED)
    
    samples_per_class = SAMPLES_PER_DATASET // 2  # Half resolved, half unresolved
    
    balanced_data = []
    
    print(f"\n{'='*60}")
    print(f"Creating balanced dataset: {SAMPLES_PER_DATASET} samples per repository")
    print(f"({samples_per_class} resolved + {samples_per_class} unresolved)")
    print(f"{'='*60}\n")
    
    for repo_name in tqdm(sorted(comments_by_repo.keys()), desc="Sampling comments"):
        comments = comments_by_repo[repo_name]
        repo_stats = stats[repo_name]
        
        # Separate resolved and unresolved comments
        resolved_comments = [c for c in comments if c.get("resolved", False)]
        unresolved_comments = [c for c in comments if not c.get("resolved", False)]
        
        # Check if we have enough samples
        available_resolved = len(resolved_comments)
        available_unresolved = len(unresolved_comments)
        
        # Sample resolved comments
        if available_resolved >= samples_per_class:
            sampled_resolved = random.sample(resolved_comments, samples_per_class)
        else:
            print(f"\nWarning: {repo_name} has only {available_resolved} resolved comments, "
                  f"using all {available_resolved} instead of {samples_per_class}")
            sampled_resolved = resolved_comments
        
        # Sample unresolved comments
        if available_unresolved >= samples_per_class:
            sampled_unresolved = random.sample(unresolved_comments, samples_per_class)
        else:
            print(f"\nWarning: {repo_name} has only {available_unresolved} unresolved comments, "
                  f"using all {available_unresolved} instead of {samples_per_class}")
            sampled_unresolved = unresolved_comments
        
        # Add to balanced dataset
        for comment in sampled_resolved + sampled_unresolved:
            balanced_data.append({
                "reponame": repo_name,
                "PR_link": comment.get("pullRequestUrl", ""),
                "comment_link": comment.get("commentUrl", ""),
                "resolved": comment.get("resolved", False)
            })
    
    # Create DataFrame
    df = pd.DataFrame(balanced_data)
    
    return df


def main():
    """Main function to run the analysis and dataset creation."""
    print(f"\n{'='*60}")
    print("Comment Analysis and Balanced Dataset Creation")
    print(f"{'='*60}")
    
    # Analyze comments
    stats, comments_by_repo = analyze_comments()
    
    # Print overview
    print_overview(stats)
    
    # Create balanced dataset
    balanced_df = create_balanced_dataset(comments_by_repo, stats)
    
    # Save to CSV
    output_path = Path(OUTPUT_CSV)
    balanced_df.to_csv(output_path, index=False)
    
    print(f"\n{'='*60}")
    print(f"Balanced dataset saved to: {output_path}")
    print(f"Total samples: {len(balanced_df)}")
    print(f"Repositories: {balanced_df['reponame'].nunique()}")
    print(f"Resolved: {balanced_df['resolved'].sum()}")
    print(f"Unresolved: {(~balanced_df['resolved']).sum()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

