
import requests

TOKEN = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

def test_indian_kanoon_no_slash():
    # Documentation often shows trailing slash, but let's try without.
    url = "https://api.indiankanoon.org/search"
    headers = {
        "Authorization": f"Token {TOKEN}",
        "Accept": "application/json"
    }
    params = {
        "formInput": "Maneka Gandhi",
        "pagenum": 0
    }
    
    print("Testing official Indian Kanoon API (No trailing slash)...")
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        print("Success!")
        data = resp.json()
        print(f"Found {len(data.get('results', []))} results.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    test_indian_kanoon_no_slash()
