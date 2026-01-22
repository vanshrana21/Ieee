
import requests
import json
import sys

def verify_contract(case_identifier):
    url = f"http://127.0.0.1:8000/api/case-simplifier/{case_identifier}"
    print(f"Testing URL: {url}")
    try:
        response = requests.get(url, timeout=60)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return False
            
        data = response.json()
        
        # Mandatory top-level keys
        required_keys = ["raw_case", "ai_structured_summary"]
        actual_keys = list(data.keys())
        
        print(f"Keys found: {actual_keys}")
        
        # Check for unexpected top-level keys
        extra_keys = set(actual_keys) - set(required_keys)
        if extra_keys:
            print(f"FAILED: Found unexpected keys: {extra_keys}")
            return False
            
        # Check for missing required keys
        missing_keys = set(required_keys) - set(actual_keys)
        if missing_keys:
            print(f"FAILED: Missing mandatory keys: {missing_keys}")
            return False
            
        # Verify raw_case is present
        if not data["raw_case"]:
            print("FAILED: raw_case is null/empty")
            return False
            
        print("CONTRACT VERIFIED: Response structure matches Phase 5 requirements.")
        return True
        
    except Exception as e:
        print(f"Exception during verification: {e}")
        return False

if __name__ == "__main__":
    case = "Maneka Gandhi"
    if len(sys.argv) > 1:
        case = sys.argv[1]
    success = verify_contract(case)
    sys.exit(0 if success else 1)
