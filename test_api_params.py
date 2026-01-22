
import os
import sys
import requests

# Add backend to path
sys.path.append(os.getcwd())

# Mock environment variables
KANOON_API_KEY = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"
KANOON_API_BASE = "https://api.kanoon.dev/v1"

def test_api(query_text):
    print(f"\n--- Testing API for: {query_text} ---")
    
    # Try with 'text' parameter as suggested by docs
    params_text = {
        "text": query_text,
        "token": KANOON_API_KEY,
        "limit": 5
    }
    
    # Try with 'query' parameter as currently implemented
    params_query = {
        "query": query_text,
        "token": KANOON_API_KEY,
        "limit": 5
    }
    
    print("Testing with 'text' parameter...")
    resp = requests.get(f"{KANOON_API_BASE}/search/cases", params=params_text)
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            print(f"Found {len(data)} results. First ID: {data[0].get('id')} Title: {data[0].get('title')}")
        else:
            print("No results found with 'text'.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

    print("\nTesting with 'query' parameter...")
    resp = requests.get(f"{KANOON_API_BASE}/search/cases", params=params_query)
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            print(f"Found {len(data)} results. First ID: {data[0].get('id')} Title: {data[0].get('title')}")
        else:
            print("No results found with 'query'.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    test_api("Maneka Gandhi")
