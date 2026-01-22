
import requests

TOKEN = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

def test_indian_kanoon_post():
    url = "https://api.indiankanoon.org/search/"
    headers = {
        "Authorization": f"Token {TOKEN}",
        "Accept": "application/json"
    }
    data = {
        "formInput": "Maneka Gandhi v. Union of India",
        "pagenum": 0
    }
    
    print("Testing official Indian Kanoon API with POST...")
    resp = requests.post(url, headers=headers, data=data)
    if resp.status_code == 200:
        print("Success!")
        res = resp.json()
        results = res.get("results", [])
        if results:
            print(f"Found {len(results)} results.")
            print(f"First Result: {results[0].get('title')} (ID: {results[0].get('tid')})")
        else:
            print("No results found.")
    else:
        print(f"Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    test_indian_kanoon_post()
