import json
import os

def get_json_length(filename):
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return

    with open(filename, 'r') as f:
        data = json.load(f)

    if isinstance(data, list):
        print(f"Total items: {len(data)}")
    elif isinstance(data, dict):
        print(f"Keys in dictionary: {list(data.keys())}")
        print(f"Length (number of keys): {len(data)}")
    else:
        print("Unknown JSON format.")
        return -1
    return len(data)
