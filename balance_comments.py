#!/usr/bin/env python3
"""
Script to analyze and balance comment datasets.
Reads all JSON files from the comments folder, provides statistics,
and creates a balanced dataset with equal numbers of resolved and unresolved comments.
"""

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Any

from tqdm import tqdm

# =========================
# Configuration Constants
# =========================

# Input directory containing comment JSON files
INPUT_DIR = "/home/vahid/Desktop/CommentCheck/files/comments"

# Output directory for balanced datasets
OUTPUT_DIR = "/home/vahid/Desktop/CommentCheck/files/comments_balanced"

# Random seed for reproducibility
RANDOM_SEED = 42


def load_comments_file(file_path: Path) -> List[Dict[str, Any]]:
    """Load comments from a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_comments_file(comments: List[Dict[str, Any]], file_path: Path) -> None:
    """Save comments to a JSON file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(comments, f, indent=2, ensure_ascii=False)


def analyze_comments(comments: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count resolved and unresolved comments."""
    resolved = sum(1 for comment in comments if comment.get("resolved", False))
    unresolved = len(comments) - resolved
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "total": len(comments)
    }


def balance_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create a balanced dataset with equal numbers of resolved and unresolved comments."""
    resolved_comments = [c for c in comments if c.get("resolved", False)]
    unresolved_comments = [c for c in comments if not c.get("resolved", False)]
    
    resolved_count = len(resolved_comments)
    unresolved_count = len(unresolved_comments)
    
    # Determine which class is the minority
    if resolved_count < unresolved_count:
        # Resolved is minority, sample from unresolved
        target_count = resolved_count
        sampled_unresolved = random.sample(unresolved_comments, target_count)
        balanced_comments = resolved_comments + sampled_unresolved
    elif unresolved_count < resolved_count:
        # Unresolved is minority, sample from resolved
        target_count = unresolved_count
        sampled_resolved = random.sample(resolved_comments, target_count)
        balanced_comments = sampled_resolved + unresolved_comments
    else:
        # Already balanced
        balanced_comments = comments
    
    # Shuffle to avoid ordering bias
    random.shuffle(balanced_comments)
    
    return balanced_comments


def main():
    """Main function to process all comment files."""
    # Set random seed for reproducibility
    random.seed(RANDOM_SEED)
    
    # Create output directory if it doesn't exist
    output_path = Path(OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Get all JSON files from input directory
    input_path = Path(INPUT_DIR)
    json_files = list(input_path.glob("*.json"))
    
    if not json_files:
        print(f"No JSON files found in {INPUT_DIR}")
        return
    
    print(f"Found {len(json_files)} JSON file(s) to process\n")
    
    # Overall statistics
    total_resolved = 0
    total_unresolved = 0
    total_comments = 0
    file_stats = []
    
    # Process each file
    for json_file in tqdm(json_files, desc="Processing files", unit="file"):
        # Load comments
        comments = load_comments_file(json_file)
        
        # Analyze current file
        stats = analyze_comments(comments)
        total_resolved += stats["resolved"]
        total_unresolved += stats["unresolved"]
        total_comments += stats["total"]
        file_stats.append((json_file.name, stats))
        
        # Create balanced dataset
        balanced_comments = balance_comments(comments)
        
        # Save balanced dataset with same filename
        output_file = output_path / json_file.name
        save_comments_file(balanced_comments, output_file)
    
    # Print per-file statistics
    print("\n" + "="*60)
    print("PER-FILE STATISTICS")
    print("="*60)
    for filename, stats in file_stats:
        print(f"\n{filename}:")
        print(f"  Total: {stats['total']:,}")
        print(f"  Resolved: {stats['resolved']:,} ({100*stats['resolved']/stats['total']:.2f}%)")
        print(f"  Unresolved: {stats['unresolved']:,} ({100*stats['unresolved']/stats['total']:.2f}%)")
    
    # Print overall statistics
    print("\n" + "="*60)
    print("OVERALL STATISTICS")
    print("="*60)
    print(f"Total comments: {total_comments:,}")
    print(f"Resolved comments: {total_resolved:,} ({100*total_resolved/total_comments:.2f}%)")
    print(f"Unresolved comments: {total_unresolved:,} ({100*total_unresolved/total_comments:.2f}%)")
    print("="*60)
    
    # Determine which class is majority
    if total_resolved > total_unresolved:
        majority = "resolved"
        majority_count = total_resolved
        minority_count = total_unresolved
    else:
        majority = "unresolved"
        majority_count = total_unresolved
        minority_count = total_resolved
    
    print(f"\nMajority class: {majority} ({majority_count:,} comments)")
    print(f"Minority class: {minority_count:,} comments")
    print(f"\nBalanced dataset will contain {minority_count:,} comments from each class")
    print(f"Total balanced dataset size: {minority_count * 2:,} comments")
    print(f"\nBalanced datasets saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

