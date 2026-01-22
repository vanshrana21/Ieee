
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())

# Mock environment variables
os.environ["KANOON_API_KEY"] = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

from backend.services.case_summarizer import normalize_case_identifier
from backend.services.kannon_service import search_case_in_kannon, fetch_case_from_kannon

def test_resolution(query):
    print(f"\n--- Testing Query: {query} ---")
    normalized = normalize_case_identifier(query)
    print(f"Normalized: '{normalized}'")
    
    result = search_case_in_kannon(normalized)
    if result:
        print(f"Search Result ID: {result.get('id')}")
        print(f"Search Result Title: {result.get('title')}")
    else:
        print("Search failed to return results.")

if __name__ == "__main__":
    test_resolution("Maneka Gandhi v. Union of India")
    test_resolution("Kesavananda Bharati v. State of Kerala")
