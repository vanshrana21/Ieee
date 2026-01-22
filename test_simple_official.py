
import requests

TOKEN = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

def test_simple_official():
    url = "https://api.indiankanoon.org/search/"
    headers = {
        "Authorization": f"Token {TOKEN}",
        "Accept": "application/json"
    }
    # Official API likes 'formInput'
    params = {
        "formInput": "maneka gandhi",
        "pagenum": 0
    }
    
    print("Testing official API with simple query...")
    # Trying POST first as it seemed to 'Success' last time
    resp = requests.post(url, headers=headers, data=params)
    print(f"POST Result: {resp.status_code}")
    if resp.status_code == 200:
        print(resp.json().get("results", [])[:1])
    
    # Trying GET too just in case
    resp_get = requests.get(url, headers=headers, params=params)
    print(f"GET Result: {resp_get.status_code}")
    if resp_get.status_code == 200:
        print(resp_get.json().get("results", [])[:1])

if __name__ == "__main__":
    test_simple_official()
