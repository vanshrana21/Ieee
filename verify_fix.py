
import os
import sys
import logging

# Configure logging to see our new logs
logging.basicConfig(level=logging.INFO)

# Add backend to path
sys.path.append(os.getcwd())

# Mock environment variables
os.environ["KANOON_API_KEY"] = "f7dc53039ebb47c1cd9c4e8326c6d77efc85f839"

from backend.services.case_summarizer import normalize_case_identifier
from backend.services.kannon_service import search_case_in_kannon

def test_resolution(query):
    print(f"\n--- Testing Query: {query} ---")
    normalized = normalize_case_identifier(query)
    print(f"Normalized: '{normalized}'")
    
    result = search_case_in_kannon(normalized)
    if result:
        print(f"✅ Resolved to ID: {result.get('id')}")
        print(f"✅ Title: {result.get('title')}")
    else:
        print("❌ Search correctly rejected irrelevant results or found no match.")

if __name__ == "__main__":
    # Test 1: Landmark case that should ideally resolve to SC if data exists, 
    # but at least should NOT resolve to PHHC random case anymore.
    test_resolution("Maneka Gandhi v. Union of India (1978)")
    
    # Test 2: Another case
    test_resolution("Kesavananda Bharati Supreme Court")
    
    # Test 3: Direct ID (should still work)
    test_resolution("PHHC01-077584-2017")
