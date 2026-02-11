"""
Phase 4: Memorial Submission API Routes

4 endpoints for PDF memorial upload, status tracking, and analysis results.
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import os
import shutil
import uuid

from backend.services.memorial_analysis_service import MemorialAnalysisService
from backend.database import get_db


router = APIRouter(
    prefix="/api/competitions",
    tags=["memorial-submission"]
)

# Upload configuration
UPLOAD_DIR = "uploads/memorials"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_PAGES = 50
ALLOWED_EXTENSIONS = {".pdf"}


def ensure_upload_dir(competition_id: int):
    """Ensure upload directory exists for competition."""
    path = os.path.join(UPLOAD_DIR, str(competition_id))
    os.makedirs(path, exist_ok=True)
    return path


def get_current_user():
    """
    Get current authenticated user from token.
    Placeholder - replace with actual auth dependency.
    """
    return {
        "id": 1,
        "role": "team_captain",
        "team_id": 1,
        "is_captain": True
    }


def require_team_captain(user: dict, team_id: int):
    """Validate user is captain of specified team."""
    if not user.get("is_captain"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team captains can submit memorials"
        )
    if user.get("team_id") != team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit for your own team"
        )


def require_judge_or_team_member(user: dict, team_id: int):
    """Validate user is judge or member of specified team."""
    is_judge = user.get("role") == "judge"
    is_team_member = user.get("team_id") == team_id
    
    if not (is_judge or is_team_member):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )


def validate_pdf_file(file: UploadFile) -> tuple[bool, str]:
    """
    Validate uploaded file is a valid PDF.
    
    Returns:
        (is_valid, error_message)
    """
    # Check extension
    filename = file.filename.lower()
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return False, "Only PDF files are allowed"
    
    # Check content type
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        return False, "Invalid file type"
    
    return True, ""


@router.post("/{competition_id}/memorials")
async def upload_memorial(
    competition_id: int,
    file: UploadFile = File(...),
    team_id: int = Form(...),
    submission_notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a memorial PDF for AI analysis.
    
    Args:
        competition_id: Competition ID
        file: PDF file upload
        team_id: Team submitting the memorial
        submission_notes: Optional notes (max 500 chars)
        db: Database session
        current_user: Authenticated team captain
    
    Returns:
        Memorial upload confirmation with analysis status
    """
    # Permission check: Team captain only
    require_team_captain(current_user, team_id)
    
    # Validate file
    is_valid, error_msg = validate_pdf_file(file)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # Read file content for validation
    content = await file.read()
    
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
        )
    
    # Save file
    upload_path = ensure_upload_dir(competition_id)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{team_id}_{timestamp}.pdf"
    file_path = os.path.join(upload_path, filename)
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Extract text and count pages
    try:
        text, page_count = MemorialAnalysisService.extract_text_and_pages(file_path)
        if page_count > MAX_PAGES:
            os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PDF has {page_count} pages. Maximum is {MAX_PAGES} pages."
            )
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not process PDF: {str(e)}"
        )
    
    # Validate notes length
    if submission_notes and len(submission_notes) > 500:
        submission_notes = submission_notes[:500]
    
    # Create memorial record (simplified - would use ORM model in production)
    upload_id = f"mem_{uuid.uuid4().hex[:12]}"
    
    memorial_data = {
        "id": 1,  # Would be auto-generated
        "competition_id": competition_id,
        "team_id": team_id,
        "file_path": file_path,
        "filename": filename,
        "file_size": len(content),
        "page_count": page_count,
        "submission_notes": submission_notes,
        "status": "uploaded",
        "upload_id": upload_id,
        "uploaded_by": current_user["id"],
        "uploaded_at": datetime.utcnow().isoformat()
    }
    
    # TODO: Save to database
    # TODO: Queue AI analysis task (background)
    
    return {
        "id": memorial_data["id"],
        "competition_id": competition_id,
        "team_id": team_id,
        "file_path": file_path,
        "status": "uploaded",
        "upload_id": upload_id,
        "page_count": page_count,
        "file_size_mb": round(len(content) / (1024*1024), 2),
        "message": "Memorial uploaded successfully. AI analysis in progress...",
        "estimated_analysis_time": "30-60 seconds"
    }


@router.get("/{competition_id}/memorials/{memorial_id}/status")
async def get_memorial_status(
    competition_id: int,
    memorial_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get memorial upload and analysis status.
    
    Args:
        competition_id: Competition ID
        memorial_id: Memorial ID
        db: Database session
        current_user: Authenticated user
    
    Returns:
        Current status and progress information
    """
    # TODO: Fetch from database
    # For now, return mock status
    
    return {
        "id": memorial_id,
        "status": "processing",
        "progress": 65,
        "stage": "analyzing_legal_reasoning",
        "estimated_time_remaining": "00:00:23",
        "message": "AI Judge is analyzing page 18 of 30...",
        "stages_completed": [
            "pdf_extraction",
            "citation_check"
        ],
        "stages_remaining": [
            "doctrine_analysis",
            "feedback_generation"
        ]
    }


@router.get("/{competition_id}/memorials/{memorial_id}/analysis")
async def get_memorial_analysis(
    competition_id: int,
    memorial_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get AI analysis results for a memorial.
    
    Args:
        competition_id: Competition ID
        memorial_id: Memorial ID
        db: Database session
        current_user: Authenticated user
    
    Returns:
        Complete analysis results with scores and feedback
    """
    # TODO: Check permission and fetch from database
    # For now, return mock analysis
    
    return {
        "id": memorial_id,
        "competition_id": competition_id,
        "team_id": 1,
        "status": "completed",
        "scores": {
            "irac_structure": 4,
            "citation_format": 5,
            "legal_reasoning": 3,
            "overall": 4.0,
            "percentage": 80
        },
        "feedback": {
            "strengths": [
                "Perfect SCC citation format throughout",
                "Clear issue identification in IRAC structure",
                "Strong application of Maneka precedent"
            ],
            "improvements": [
                {
                    "issue": "Need proportionality test analysis",
                    "suggestion": "Apply Puttaswamy para 184 proportionality test to your Article 21 arguments",
                    "priority": "high"
                },
                {
                    "issue": "Missing basic structure doctrine",
                    "suggestion": "Include Kesavananda basic structure analysis for constitutional challenges",
                    "priority": "high"
                },
                {
                    "issue": "Time management in arguments",
                    "suggestion": "Some sections are overly verbose - focus on key precedents",
                    "priority": "medium"
                }
            ],
            "case_citations": [
                {
                    "name": "Puttaswamy (2017) 10 SCC 1",
                    "context": "Privacy as fundamental right under Article 21",
                    "usage_count": 3,
                    "status": "verified"
                },
                {
                    "name": "Maneka (1978) 1 SCC 248",
                    "context": "Procedure established by law test",
                    "usage_count": 3,
                    "status": "verified"
                },
                {
                    "name": "Kesavananda (1973) 4 SCC 225",
                    "context": "Basic structure doctrine",
                    "usage_count": 1,
                    "status": "mentioned_not_analyzed"
                }
            ],
            "doctrine_gaps": [
                {
                    "doctrine": "Proportionality Test",
                    "status": "missing",
                    "importance": "Required for Article 21 challenges",
                    "reference": "Puttaswamy para 184"
                },
                {
                    "doctrine": "Basic Structure",
                    "status": "present",
                    "importance": "Correctly applied"
                }
            ],
            "recommendations": [
                {
                    "type": "additional_citation",
                    "suggestion": "Consider citing Navtej Singh (2018) for dignity-based arguments",
                    "priority": "medium"
                },
                {
                    "type": "oral_argument",
                    "suggestion": "Focus on proportionality in rejoinder since missing in memorial",
                    "priority": "high"
                }
            ]
        },
        "completed_at": datetime.utcnow().isoformat(),
        "analysis_version": "1.0"
    }


@router.get("/{competition_id}/teams/{team_id}/memorials")
async def list_team_memorials(
    competition_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all memorial submissions for a team.
    
    Args:
        competition_id: Competition ID
        team_id: Team ID
        db: Database session
        current_user: Authenticated user
    
    Returns:
        List of memorial submissions with status and scores
    """
    # Permission check
    require_judge_or_team_member(current_user, team_id)
    
    # TODO: Fetch from database
    # For now, return mock list
    
    return [
        {
            "id": 1,
            "competition_id": competition_id,
            "team_id": team_id,
            "filename": "team1_20260211143000.pdf",
            "uploaded_at": "2026-02-11T14:30:00Z",
            "status": "completed",
            "page_count": 24,
            "file_size_mb": 2.4,
            "scores": {
                "overall": 4.0,
                "irac_structure": 4,
                "citation_format": 5,
                "legal_reasoning": 3
            },
            "download_url": f"/api/competitions/{competition_id}/memorials/1/download",
            "analysis_url": f"/api/competitions/{competition_id}/memorials/1/analysis"
        },
        {
            "id": 2,
            "competition_id": competition_id,
            "team_id": team_id,
            "filename": "team1_20260210101500.pdf",
            "uploaded_at": "2026-02-10T10:15:00Z",
            "status": "completed",
            "page_count": 28,
            "file_size_mb": 2.8,
            "scores": {
                "overall": 3.5,
                "irac_structure": 3,
                "citation_format": 4,
                "legal_reasoning": 3
            },
            "download_url": f"/api/competitions/{competition_id}/memorials/2/download",
            "analysis_url": f"/api/competitions/{competition_id}/memorials/2/analysis"
        }
    ]


@router.get("/{competition_id}/memorials/{memorial_id}/download")
async def download_memorial(
    competition_id: int,
    memorial_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Download a memorial PDF file.
    
    Args:
        competition_id: Competition ID
        memorial_id: Memorial ID
        db: Database session
        current_user: Authenticated user
    
    Returns:
        PDF file download
    """
    # TODO: Fetch file path from database and verify permissions
    # For now, return mock response
    
    file_path = f"uploads/memorials/{competition_id}/1_20260211143000.pdf"
    
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    return FileResponse(
        path=file_path,
        filename=f"memorial_{memorial_id}.pdf",
        media_type="application/pdf"
    )
