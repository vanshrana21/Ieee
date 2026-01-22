# verify_phase3.py
from backend.utils.ai_preparer import prepare_ai_input, CanonicalAIInput
import json

def test_phase3_completion():
    print("Verifying Phase 3: Canonical AI Input Structure...")
    
    # Input from Phase 2
    dummy_phase2_output = {
        "case_name": "Marbury v. Madison",
        "citation": "5 U.S. 137",
        "court": "US Supreme Court",
        "year": "1803",
        "facts": "Headnote: Legal principles here.\n\nFacts of the case regarding judicial review.",
        "issues": "Can the Supreme Court issue a mandamus?",
        "arguments": "Petitioner argued X. Respondent argued Y.",
        "judgment": "Digitally signed.\n\nThe court has the power to declare laws unconstitutional.",
        "ratio": "It is emphatically the province and duty of the judicial department to say what the law is."
    }
    
    # Execute Phase 3
    try:
        canonical_output = prepare_ai_input(dummy_phase2_output)
        
        # 1. Check mapping
        print(f"✓ Mapping logic: {list(canonical_output.keys())}")
        
        # 2. Check field exclusion (arguments should be out of scope)
        if "arguments" not in canonical_output:
            print("✓ Field exclusion: 'arguments' removed correctly.")
        else:
            print("✗ Field exclusion: 'arguments' still present!")
            
        # 3. Check reduction logic (Headnote and Metadata should be gone)
        if "Headnote:" not in canonical_output["facts"] and "Digitally signed" not in canonical_output["judgment"]:
            print("✓ Reduction logic: Metadata removed successfully.")
        else:
            print("✗ Reduction logic: Metadata still present.")
            
        # 4. Validation strategy check
        # We try to create an object with extra fields to see if Pydantic blocks it (it won't by default unless Config.extra='forbid')
        # But we check if the returned dict matches CanonicalAIInput
        try:
            CanonicalAIInput(**canonical_output)
            print("✓ Validation strategy: Conforms to CanonicalAIInput Pydantic model.")
        except Exception as e:
            print(f"✗ Validation strategy failure: {e}")

        print("\nExample Canonical Object:")
        print(json.dumps(canonical_output, indent=2))
        
    except Exception as e:
        print(f"Phase 3 Verification FAILED: {e}")

if __name__ == "__main__":
    test_phase3_completion()
