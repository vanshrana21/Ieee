"""
backend/knowledge_base/problems.py
Phase 3: Pre-loaded Indian Moot Problems for Validation

3 Indian moot problems for Phase 3 student validation testing.
These match the MootProject structure and integrate with Phase 1 knowledge base.
"""
from typing import List, Dict


# Pre-loaded validation problems for Phase 3
VALIDATION_PROBLEMS: List[Dict] = [
    {
        "id": 1,
        "title": "Aadhaar Mandatory for NFSA Food Grains",
        "facts": "Government made Aadhaar authentication mandatory for NFSA food grains. Tribal woman denied grains due to biometric failure. Argues violation of Article 21 right to food + privacy (Puttaswamy). State argues national interest.",
        "legal_issues": [
            "Does mandatory Aadhaar violate Puttaswamy proportionality test?",
            "Does it render right to food illusory?"
        ],
        "petitioner_key_cases": [
            "Puttaswamy (2017) 10 SCC 1",
            "PUCL (2001) 5 SCC 572"
        ],
        "respondent_key_cases": [
            "Justice K.S. Puttaswamy (Aadhaar bench) (2019) 1 SCC 1"
        ],
        "domain": "privacy",
        "key_statutes": ["Article 21", "Aadhaar Act 2016", "NFSA 2013"]
    },
    {
        "id": 2,
        "title": "AI-Generated Deepfake Defamation",
        "facts": "Influencer posted AI deepfake video showing minister accepting bribes. Minister filed FIR under Sections 499/500 IPC. Influencer claims fair comment + Article 19(1)(a).",
        "legal_issues": [
            "Does AI-generated content qualify as 'publication' under Section 499?",
            "Does fair comment exception apply to synthetic media?"
        ],
        "petitioner_key_cases": [
            "Subramanian Swamy (2016) 7 SCC 221"
        ],
        "respondent_key_cases": [
            "Shreya Singhal (2015) 5 SCC 1"
        ],
        "domain": "defamation",
        "key_statutes": ["Section 499 IPC", "Section 500 IPC", "Article 19(1)(a)"]
    },
    {
        "id": 3,
        "title": "Religious Sentiments vs. Free Speech",
        "facts": "Comedian's stand-up routine critiquing religious practices went viral. FIR under Section 295A IPC for 'deliberate and malicious acts'. Claims Article 19(1)(a) protection.",
        "legal_issues": [
            "Is Section 295A vague and overbroad?",
            "Does 'deliberate and malicious' requirement from Ramji Lal Modi satisfied?"
        ],
        "petitioner_key_cases": [
            "Ramji Lal Modi (1957) SCR 874"
        ],
        "respondent_key_cases": [
            "Shreya Singhal (2015) 5 SCC 1"
        ],
        "domain": "free_speech",
        "key_statutes": ["Section 295A IPC", "Article 19(1)(a)", "Article 19(2)"]
    }
]


def get_validation_problems() -> List[Dict]:
    """
    Return all 3 pre-loaded validation problems.
    
    Returns:
        List of 3 problem dictionaries with IDs 1, 2, 3
    """
    return VALIDATION_PROBLEMS


def get_problem_by_id(problem_id: int) -> Dict | None:
    """
    Get a specific validation problem by ID.
    
    Args:
        problem_id: Problem ID (1, 2, or 3)
    
    Returns:
        Problem dict or None if not found
    """
    for problem in VALIDATION_PROBLEMS:
        if problem["id"] == problem_id:
            return problem
    return None


def get_problem_cases_by_side(problem_id: int, side: str) -> List[str]:
    """
    Get landmark cases for a specific problem and side.
    
    Args:
        problem_id: Problem ID (1, 2, or 3)
        side: "petitioner" or "respondent"
    
    Returns:
        List of case citations
    """
    problem = get_problem_by_id(problem_id)
    if not problem:
        return []
    
    key = f"{side}_key_cases"
    return problem.get(key, [])
