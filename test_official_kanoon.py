
import requests

TOKEN = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

def test_indian_kanoon():
    url = "https://api.indiankanoon.org/search/"
    headers = {
        "Authorization": f"Token {TOKEN}",
        "Accept": "application/json"
    }
    params = {
        "formInput": "Maneka Gandhi v. Union of India",
        "pagenum": 0
    }
    
    print("Testing official Indian Kanoon API...")
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        print("Success!")
        data = resp.json()
        results = data.get("results", [])
        if results:
            print(f"Found {len(results)} results.")
            print(f"First Result: {results[0].get('title')} (ID: {results[0].get('tid')})")
        else:
            print("No results found.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    test_indian_kanoon()
