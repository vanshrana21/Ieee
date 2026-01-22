
import json
from typing import List, Dict, Optional

# Mocking the data contract as defined in the task
def verify_subject_json(subject: Dict):
    required_keys = ["id", "title", "unit_count", "units"]
    for key in required_keys:
        if key not in subject:
            raise AssertionError(f"Missing required key: {key}")
    
    if not isinstance(subject["units"], list):
        raise AssertionError("units must be a list")
    
    if not isinstance(subject["unit_count"], int):
        raise AssertionError("unit_count must be an integer")
    
    print(f"Verified subject: {subject['title']} ({subject['unit_count']} units)")

# Sample data based on our implementation
sample_subject = {
    "id": 101,
    "title": "General and Legal English",
    "unit_count": 2,
    "units": [
        {"id": 1, "title": "Unit I", "sequence_order": 1, "description": "Desc 1"},
        {"id": 2, "title": "Unit II", "sequence_order": 2, "description": "Desc 2"}
    ]
}

try:
    verify_subject_json(sample_subject)
    print("Data contract verification passed!")
except Exception as e:
    print(f"Data contract verification failed: {e}")
