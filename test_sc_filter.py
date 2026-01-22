
import requests

KANOON_API_KEY = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"
KANOON_API_BASE = "https://api.kanoon.dev/v1"

def test_sc_filter():
    print("\n--- Testing API with SC filter ---")
    
    # Try with 'query' filter and 'text' search
    params = {
        "query": "court_id:SC",
        "text": "Maneka Gandhi",
        "token": KANOON_API_KEY,
        "limit": 5
    }
    
    resp = requests.get(f"{KANOON_API_BASE}/search/cases", params=params)
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            print(f"Found {len(data)} results.")
            for d in data:
                print(f"ID: {d.get('id')} Title: {d.get('title')} Court: {d.get('court_id')} Year: {d.get('filed_at', '')[:4]}")
        else:
            print("No results found with SC filter.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    test_sc_filter()
