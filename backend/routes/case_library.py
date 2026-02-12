"""
Case Library API Routes (GET Only)

Provides read-only access to moot court cases.
Features:
- Case search with validation
- Category filtering
- Pagination support
- Input sanitization
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field, validator
import re
import logging

from backend.database import get_db
from backend.orm.classroom_session import SessionCategory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])

# Schemas
class CaseResponse(BaseModel):
    """Response schema for moot court cases."""
    id: int
    title: str
    category: str
    summary: str
    full_text: Optional[str] = None
    precedents: List[str] = []
    relevant_articles: List[str] = []
    difficulty: str = "intermediate"
    
    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    """Response schema for paginated case list."""
    cases: List[CaseResponse]
    total: int
    page: int
    per_page: int
    

class CaseSearchRequest(BaseModel):
    """Request schema for case search."""
    query: str = Field(..., min_length=2, max_length=100)
    category: Optional[str] = None
    
    @validator('query')
    def sanitize_query(cls, v):
        """Sanitize search query."""
        # Remove special characters that could be used for injection
        v = re.sub(r'[<>"\'%;()&+]', '', v)
        return v.strip()


# Routes
@router.get("", response_model=CaseListResponse)
async def list_cases(
    category: Optional[str] = Query(None, description="Filter by category"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    search: Optional[str] = Query(None, max_length=100, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    List moot court cases with optional filtering.
    
    - Pagination: Default 20 per page, max 100
    - Search: Sanitized to prevent injection
    - Categories: constitutional, criminal, cyber, civil, corporate
    """
    try:
        # Note: This assumes a MootCase model exists
        # Since user is handling case population separately, we return placeholder structure
        # Replace with actual query when cases are populated
        
        # Placeholder response for now
        sample_cases = [
            {
                "id": 1,
                "title": "Right to Privacy vs National Security",
                "category": "constitutional",
                "summary": "Aadhaar biometric data collection challenge under Article 21",
                "difficulty": "advanced",
                "precedents": ["Puttaswamy (2017)", "Maneka Gandhi (1978)"],
                "relevant_articles": ["Article 21", "Article 19(1)(a)", "Article 14"]
            },
            {
                "id": 2,
                "title": "Defamation and Free Speech",
                "category": "constitutional",
                "summary": "Criminal defamation laws vs freedom of speech and expression",
                "difficulty": "intermediate",
                "precedents": ["Rangarajan (1989)", "Shreya Singhal (2015)"],
                "relevant_articles": ["Article 19(1)(a)", "Article 19(2)"]
            },
            {
                "id": 3,
                "title": "Cyber Crime and Data Protection",
                "category": "cyber",
                "summary": "IT Act provisions and right to be forgotten",
                "difficulty": "intermediate",
                "precedents": ["Justice K.S. Puttaswamy (2017)"],
                "relevant_articles": ["Section 66A IT Act", "Article 21"]
            },
            {
                "id": 4,
                "title": "Corporate Fraud and Insider Trading",
                "category": "corporate",
                "summary": "SEBI regulations and corporate governance obligations",
                "difficulty": "advanced",
                "precedents": ["SEBI v. Sahara (2012)"],
                "relevant_articles": ["SEBI Act 1992", "Companies Act 2013"]
            },
            {
                "id": 5,
                "title": "Murder and Self-Defense",
                "category": "criminal",
                "summary": "IPC Section 302 and right to private defense",
                "difficulty": "beginner",
                "precededents": ["R v. Clegg (1995)"],
                "relevant_articles": ["IPC Section 302", "IPC Section 100"]
            }
        ]
        
        # Apply filters
        filtered_cases = sample_cases
        
        if category:
            category = category.lower().strip()
            valid_categories = [c.value for c in SessionCategory]
            if category not in valid_categories:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category. Valid: {', '.join(valid_categories)}"
                )
            filtered_cases = [c for c in filtered_cases if c["category"] == category]
        
        if difficulty:
            filtered_cases = [c for c in filtered_cases if c.get("difficulty") == difficulty]
        
        if search:
            # Sanitize search
            search = re.sub(r'[<>"\'%;()&+]', '', search).lower()
            filtered_cases = [
                c for c in filtered_cases 
                if search in c["title"].lower() or search in c["summary"].lower()
            ]
        
        # Pagination
        total = len(filtered_cases)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_cases = filtered_cases[start:end]
        
        return CaseListResponse(
            cases=[CaseResponse(**c) for c in paginated_cases],
            total=total,
            page=page,
            per_page=per_page
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Case listing failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list cases")


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed case information by ID."""
    try:
        # Placeholder - replace with actual DB query
        sample_cases = {
            1: {
                "id": 1,
                "title": "Right to Privacy vs National Security",
                "category": "constitutional",
                "summary": "Aadhaar biometric data collection challenge under Article 21",
                "full_text": """FULL MOOT PROPOSITION:

The Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act, 2016 was challenged on grounds of violating the right to privacy under Article 21 of the Constitution.

The petitioners argue that:
1. Biometric data collection violates privacy as a fundamental right
2. The Act lacks sufficient safeguards against data breaches
3. The mandatory nature infringes on individual autonomy

The respondents (Union of India) argue that:
1. Privacy is not an absolute right and can be restricted for legitimate state interests
2. Aadhaar ensures efficient delivery of welfare benefits
3. Robust security measures are in place""",
                "difficulty": "advanced",
                "precedents": ["Justice K.S. Puttaswamy v. Union of India (2017)", "Maneka Gandhi v. Union of India (1978)"],
                "relevant_articles": ["Article 21", "Article 19(1)(a)", "Article 14", "Article 300A"]
            },
            2: {
                "id": 2,
                "title": "Defamation and Free Speech",
                "category": "constitutional",
                "summary": "Criminal defamation laws vs freedom of speech and expression",
                "full_text": """FULL MOOT PROPOSITION:

Section 499 and 500 of the Indian Penal Code, which criminalize defamation, are challenged as unconstitutional restrictions on free speech under Article 19(1)(a).

Issues:
1. Are criminal defamation laws disproportionate restrictions?
2. Do they have a chilling effect on free speech?
3. Is the defense of truth unduly burdensome?""",
                "difficulty": "intermediate",
                "precedents": ["Rangarajan v. P. Jagajeevan Ram (1989)", "Shreya Singhal v. Union of India (2015)"],
                "relevant_articles": ["Article 19(1)(a)", "Article 19(2)"]
            }
        }
        
        case = sample_cases.get(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        return CaseResponse(**case)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Case retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve case")


@router.get("/categories")
async def get_categories():
    """Get list of valid case categories."""
    return {
        "categories": [
            {"id": "constitutional", "name": "Constitutional Law", "case_count": 0},
            {"id": "criminal", "name": "Criminal Law", "case_count": 0},
            {"id": "cyber", "name": "Cyber Law", "case_count": 0},
            {"id": "civil", "name": "Civil Law", "case_count": 0},
            {"id": "corporate", "name": "Corporate Law", "case_count": 0}
        ]
    }
