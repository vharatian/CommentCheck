import json
import os

def split_comments_by_resolved(filename, output_folder='comments'):
    """Splits a JSON file into 'resolved' and 'unresolved' files."""

    os.makedirs(output_folder, exist_ok=True)
    
    with open(filename, 'r') as f:
        data = json.load(f)
    
    resolved = [item for item in data if item.get('resolved') is True]
    unresolved = [item for item in data if item.get('resolved') is False]
    
    with open(os.path.join(output_folder, 'resolved_comments.json'), 'w') as f:
        json.dump(resolved, f, indent=2)
        
    with open(os.path.join(output_folder, 'unresolved_comments.json'), 'w') as f:
        json.dump(unresolved, f, indent=2)

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(current_dir, '..', 'data', 'all_comments.json')    
    output_path = os.path.join(current_dir, 'comments')
    print(f"Saving to:    {output_path}")
    split_comments_by_resolved(data_path, output_path)