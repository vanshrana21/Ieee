# verify_phase2.py
from backend.utils.case_extractor import extract_full_case_details

def test_extraction():
    dummy_raw_data = {
        "case_name": "Test Case vs. State",
        "citation": "2026 INSC 123",
        "court": "Supreme Court of India",
        "judgment_date": "2026-01-22",
        "facts": "<p>These are the facts of the case.</p><p>Multiple paragraphs included.</p>",
        "issues": "Whether the appeal is maintainable.",
        "arguments": "Petitioner argues for X. Respondent argues for Y.",
        "judgment_text": "The court finds that... <br> Full judgment content.",
        "ratio": "The ratio is that X must equal Y."
    }

    print("Running Extraction...")
    extracted = extract_full_case_details(dummy_raw_data)
    
    expected_keys = [
        "case_name", "citation", "court", "year", 
        "facts", "issues", "arguments", "judgment", "ratio"
    ]
    
    print("\n--- Extracted Data ---")
    for key in expected_keys:
        val = extracted.get(key, "MISSING")
        print(f"{key}: {val[:50]}..." if isinstance(val, str) and len(val) > 50 else f"{key}: {val}")

    # Validation
    assert all(key in extracted for key in expected_keys), "Missing keys in extracted data"
    assert "2026" in extracted["year"], "Year extraction failed"
    assert "<p>" not in extracted["facts"], "HTML cleaning failed"
    assert "\n\n" in extracted["facts"], "Paragraph preservation failed"
    
    print("\n✅ Phase 2 Verification Successful!")

if __name__ == "__main__":
    test_extraction()
