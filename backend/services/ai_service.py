import logging
import os
import json
import hashlib
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
import google.generativeai as genai
from backend.models.search import SearchRequest, SearchResult, CaseDetail

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    logger.error("GEMINI_API_KEY not found in environment")
    model = None

# Log file path
TUTOR_LOG_FILE = "backend/logging/tutor_calls.log"

async def call_gemini_deterministic(
    prompt: str, 
    user_id: int, 
    endpoint: str = "/api/tutor/chat",
    response_mime_type: str = "application/json"
) -> Dict[str, Any]:
    """
    Deterministic AI call wrapper with logging and hashing.
    """
    if not model:
        return {"error": "AI service uninitialized", "success": False}

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    start_time = time.time()
    
    try:
        # Temperature=0 for determinism
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,
                response_mime_type=response_mime_type
            )
        )
        
        latency = time.time() - start_time
        response_text = response.text
        response_hash = hashlib.sha256(response_text.encode()).hexdigest()
        
        # Log the call
        log_entry = (
            f"{datetime.utcnow().isoformat()} | user_id={user_id} | endpoint={endpoint} | "
            f"prompt_hash={prompt_hash} | response_hash={response_hash} | "
            f"latency={latency:.2f}s | model=gemini-1.5-flash\n"
        )
        
        with open(TUTOR_LOG_FILE, "a") as f:
            f.write(log_entry)
            
        return {
            "success": True,
            "text": response_text,
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "latency": latency,
            "model": "gemini-1.5-flash"
        }
        
    except Exception as e:
        logger.error(f"AI Service Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "fallback": "AI service unavailable"
        }

# Existing mock functions maintained for compatibility
MOCK_CASES = [
    {
        "id": "case-001",
        "title": "State v. Kumar",
        "court": "Supreme Court of India",
        "year": 2024,
        "summary": "Landmark judgment on digital privacy rights in India.",
        "citations": 45,
        "tags": ["Privacy", "Digital Rights", "Constitutional Law"],
    },
    {
        "id": "case-002",
        "title": "Sharma v. Union of India",
        "court": "Delhi High Court",
        "year": 2023,
        "summary": "Environmental compliance case.",
        "citations": 23,
        "tags": ["Environmental Law"],
    },
]

async def search_cases(search_request: SearchRequest) -> List[SearchResult]:
    logger.info(f"Searching cases with query: '{search_request.query}'")
    results = []
    query = search_request.query.lower()
    for case in MOCK_CASES:
        if query in case["title"].lower() or query in case["summary"].lower():
            results.append(SearchResult(
                id=case["id"],
                title=case["title"],
                court=case["court"],
                year=case["year"],
                summary=case["summary"],
                citations=case["citations"],
                tags=case["tags"],
                relevance_score=10.0
            ))
    return results

async def get_case_by_id(case_id: str) -> Optional[CaseDetail]:
    for case in MOCK_CASES:
        if case["id"] == case_id:
            return CaseDetail(
                id=case["id"],
                title=case["title"],
                court=case["court"],
                year=case["year"],
                summary=case["summary"],
                citations=case["citations"],
                tags=case["tags"],
                holdings="Mock holding",
                key_points=["Point 1", "Point 2"]
            )
    return None

async def generate_ai_summary(case: CaseDetail) -> Dict[str, Any]:
    return {
        "summary": f"AI summary for {case.title} (mock)",
        "key_points": ["Mock point 1", "Mock point 2"]
    }
