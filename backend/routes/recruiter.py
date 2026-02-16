"""
Recruiter API Routes — Phase 9

Performance Intelligence & Talent Signal Layer API.

Security:
- RECRUITER, ADMIN, SUPER_ADMIN only
- All access logged in recruiter_access_logs
- Institution-scoped responses
- Deterministic ordering

Features:
- Candidate profile viewing
- Search with filters
- National rankings access
- Checksum verification
"""
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.orm.user import User, UserRole
from backend.orm.performance_intelligence import (
    CandidateSkillVector, NationalCandidateRanking,
    RecruiterAccessLog, PerformanceNormalizationStats
)
from backend.orm.institutional_governance import AcademicYear, Institution
from backend.services.performance_intelligence_service import (
    verify_candidate_ranking, get_institution_performance_summary
)

router = APIRouter(prefix="/recruiter", tags=["Recruiter Intelligence"])

# =============================================================================
# Helper Functions
# =============================================================================

async def log_recruiter_access(
    recruiter_user_id: int,
    candidate_user_id: int,
    access_type: str,
    db: AsyncSession
) -> RecruiterAccessLog:
    """
    Log recruiter access to candidate data.
    
    All access is append-only logged for compliance.
    """
    log = RecruiterAccessLog(
        recruiter_user_id=recruiter_user_id,
        candidate_user_id=candidate_user_id,
        access_type=access_type,
        accessed_at=datetime.utcnow()
    )
    db.add(log)
    await db.flush()
    return log


def check_recruiter_permissions(user: User) -> bool:
    """Check if user has recruiter access permissions."""
    allowed_roles = [
        UserRole.RECRUITER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    return user.role in allowed_roles


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/candidate/{candidate_id}", status_code=status.HTTP_200_OK)
async def get_candidate_profile(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Get candidate skill vector and ranking information.
    
    Returns:
        - Skill vector with all metrics
        - National ranking if available
        - Institution context
        
    Access Type: profile_view
    """
    # Verify candidate exists
    result = await db.execute(
        select(User).where(
            and_(User.id == candidate_id, User.is_active == True)
        )
    )
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found"
        )
    
    # Log access
    await log_recruiter_access(
        recruiter_user_id=current_user.id,
        candidate_user_id=candidate_id,
        access_type="profile_view",
        db=db
    )
    
    # Get skill vector
    result = await db.execute(
        select(CandidateSkillVector).where(
            CandidateSkillVector.user_id == candidate_id
        )
    )
    skill_vector = result.scalar_one_or_none()
    
    if not skill_vector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No performance data available for candidate {candidate_id}"
        )
    
    # Get latest national ranking
    result = await db.execute(
        select(NationalCandidateRanking)
        .where(NationalCandidateRanking.user_id == candidate_id)
        .order_by(NationalCandidateRanking.computed_at.desc())
        .limit(1)
    )
    ranking = result.scalar_one_or_none()
    
    # Get institution info
    result = await db.execute(
        select(Institution).where(Institution.id == candidate.institution_id)
    )
    institution = result.scalar_one_or_none()
    
    return {
        "candidate": {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "institution": {
                "id": institution.id if institution else None,
                "name": institution.name if institution else None
            }
        },
        "skill_vector": skill_vector.to_dict() if skill_vector else None,
        "national_ranking": ranking.to_dict() if ranking else None,
        "access_logged": True,
        "accessed_at": datetime.utcnow().isoformat()
    }


@router.get("/search", status_code=status.HTTP_200_OK)
async def search_candidates(
    percentile_gt: Optional[float] = Query(None, description="Minimum percentile threshold"),
    institution_id: Optional[int] = Query(None, description="Filter by institution"),
    min_sessions: Optional[int] = Query(5, description="Minimum sessions analyzed"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Search candidates by performance criteria.
    
    Query Parameters:
    - percentile_gt: Minimum national percentile (0-100)
    - institution_id: Filter to specific institution
    - min_sessions: Minimum number of sessions (default 5)
    - limit: Results per page (1-100, default 50)
    - offset: Pagination offset
    
    Returns:
        Paginated list of matching candidates
    """
    # Build query
    query = select(
        CandidateSkillVector,
        User,
        NationalCandidateRanking
    ).join(
        User, CandidateSkillVector.user_id == User.id
    ).outerjoin(
        NationalCandidateRanking,
        and_(
            NationalCandidateRanking.user_id == CandidateSkillVector.user_id,
        )
    ).where(
        and_(
            User.is_active == True,
            CandidateSkillVector.total_sessions_analyzed >= min_sessions
        )
    )
    
    # Apply filters
    if institution_id:
        query = query.where(CandidateSkillVector.institution_id == institution_id)
    
    if percentile_gt is not None:
        percentile_decimal = Decimal(str(percentile_gt))
        query = query.where(
            or_(
                NationalCandidateRanking.percentile >= percentile_decimal,
                NationalCandidateRanking.percentile.is_(None)  # Include if no ranking yet
            )
        )
    
    # Order deterministically
    query = query.order_by(
        CandidateSkillVector.oral_advocacy_score.desc(),
        CandidateSkillVector.confidence_index.desc(),
        User.id.asc()
    )
    
    # Apply pagination
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Log search access (bulk log for search)
    log = RecruiterAccessLog(
        recruiter_user_id=current_user.id,
        candidate_user_id=0,  # 0 indicates search operation
        access_type="search_query",
        accessed_at=datetime.utcnow()
    )
    db.add(log)
    await db.flush()
    
    # Format results
    candidates = []
    for vector, user, ranking in rows:
        candidates.append({
            "candidate_id": user.id,
            "full_name": user.full_name,
            "institution_id": vector.institution_id,
            "skill_summary": {
                "oral_advocacy_score": str(vector.oral_advocacy_score),
                "consistency_factor": str(vector.consistency_factor),
                "confidence_index": str(vector.confidence_index),
                "total_sessions": vector.total_sessions_analyzed
            },
            "national_rank": ranking.national_rank if ranking else None,
            "percentile": str(ranking.percentile) if ranking else None
        })
    
    return {
        "candidates": candidates,
        "total_returned": len(candidates),
        "limit": limit,
        "offset": offset,
        "filters": {
            "percentile_gt": percentile_gt,
            "institution_id": institution_id,
            "min_sessions": min_sessions
        },
        "search_logged": True
    }


@router.get("/national-rankings", status_code=status.HTTP_200_OK)
async def get_national_rankings(
    academic_year_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Get paginated national rankings for an academic year.
    
    Args:
        academic_year_id: Academic year context
        limit: Results per page (1-500, default 100)
        offset: Pagination offset
        
    Returns:
        Deterministically ordered national rankings
    """
    # Verify academic year exists
    result = await db.execute(
        select(AcademicYear).where(AcademicYear.id == academic_year_id)
    )
    academic_year = result.scalar_one_or_none()
    
    if not academic_year:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Academic year {academic_year_id} not found"
        )
    
    # Get rankings with user info
    query = select(
        NationalCandidateRanking,
        User,
        Institution
    ).join(
        User, NationalCandidateRanking.user_id == User.id
    ).join(
        Institution, User.institution_id == Institution.id
    ).where(
        NationalCandidateRanking.academic_year_id == academic_year_id
    ).order_by(
        NationalCandidateRanking.national_rank.asc(),
        NationalCandidateRanking.user_id.asc()  # Deterministic tiebreaker
    ).limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Log bulk access
    log = RecruiterAccessLog(
        recruiter_user_id=current_user.id,
        candidate_user_id=0,  # Bulk access
        access_type="ranking_view",
        accessed_at=datetime.utcnow()
    )
    db.add(log)
    await db.flush()
    
    # Format rankings
    rankings = []
    for ranking, user, institution in rows:
        rankings.append({
            "rank": ranking.national_rank,
            "candidate": {
                "id": user.id,
                "full_name": user.full_name,
                "institution": {
                    "id": institution.id,
                    "name": institution.name
                }
            },
            "composite_score": str(ranking.composite_score),
            "percentile": str(ranking.percentile),
            "tournaments_participated": ranking.tournaments_participated,
            "checksum": ranking.checksum,
            "is_final": ranking.is_final
        })
    
    # Get total count
    result = await db.execute(
        select(func.count(NationalCandidateRanking.id))
        .where(NationalCandidateRanking.academic_year_id == academic_year_id)
    )
    total_count = result.scalar() or 0
    
    return {
        "academic_year": {
            "id": academic_year.id,
            "name": academic_year.name
        },
        "rankings": rankings,
        "total_count": total_count,
        "returned_count": len(rankings),
        "limit": limit,
        "offset": offset,
        "access_logged": True
    }


@router.get("/verify/{candidate_id}", status_code=status.HTTP_200_OK)
async def verify_candidate_checksum(
    candidate_id: int,
    academic_year_id: Optional[int] = Query(None, description="Academic year for ranking context"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Verify a candidate's ranking checksum.
    
    Recomputes checksum and verifies against stored value.
    This endpoint provides cryptographic proof of ranking integrity.
    
    Args:
        candidate_id: Candidate user ID
        academic_year_id: Optional academic year context
        
    Returns:
        Verification result with stored vs computed checksum
    """
    # If no academic year specified, use latest
    if academic_year_id is None:
        result = await db.execute(
            select(NationalCandidateRanking.academic_year_id)
            .where(NationalCandidateRanking.user_id == candidate_id)
            .order_by(NationalCandidateRanking.computed_at.desc())
            .limit(1)
        )
        academic_year_id = result.scalar()
        
        if not academic_year_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No ranking found for candidate {candidate_id}"
            )
    
    # Log verification access
    await log_recruiter_access(
        recruiter_user_id=current_user.id,
        candidate_user_id=candidate_id,
        access_type="checksum_verification",
        db=db
    )
    
    # Perform verification
    verification = await verify_candidate_ranking(
        academic_year_id=academic_year_id,
        user_id=candidate_id,
        db=db
    )
    
    return {
        "candidate_id": candidate_id,
        "academic_year_id": academic_year_id,
        "verification": verification,
        "verified_at": datetime.utcnow().isoformat(),
        "verified_by": current_user.id
    }


@router.get("/institution/{institution_id}/performance", status_code=status.HTTP_200_OK)
async def get_institution_performance(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Get performance summary for an institution.
    
    Includes:
    - Candidate count
    - Normalization metrics
    - Fairness audit flags
    
    Args:
        institution_id: Institution ID
        
    Returns:
        Institution performance summary
    """
    # Log access
    log = RecruiterAccessLog(
        recruiter_user_id=current_user.id,
        candidate_user_id=0,  # Institution-level access
        access_type="institution_summary",
        accessed_at=datetime.utcnow()
    )
    db.add(log)
    await db.flush()
    
    # Get summary
    summary = await get_institution_performance_summary(institution_id, db)
    
    return {
        "institution_id": institution_id,
        "summary": summary,
        "access_logged": True,
        "accessed_at": datetime.utcnow().isoformat()
    }


@router.get("/my-access-logs", status_code=status.HTTP_200_OK)
async def get_my_access_logs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Get access logs for the current recruiter.
    
    Returns:
        List of access logs for compliance review
    """
    query = select(RecruiterAccessLog).where(
        RecruiterAccessLog.recruiter_user_id == current_user.id
    ).order_by(
        RecruiterAccessLog.accessed_at.desc()
    ).limit(limit).offset(offset)
    
    result = await db.execute(query)
    logs = list(result.scalars().all())
    
    # Get total count
    result = await db.execute(
        select(func.count(RecruiterAccessLog.id))
        .where(RecruiterAccessLog.recruiter_user_id == current_user.id)
    )
    total_count = result.scalar() or 0
    
    return {
        "logs": [log.to_dict() for log in logs],
        "total_count": total_count,
        "returned_count": len(logs),
        "limit": limit,
        "offset": offset
    }


@router.get("/stats/summary", status_code=status.HTTP_200_OK)
async def get_recruiter_platform_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPER_ADMIN]))
) -> Dict[str, Any]:
    """
    Get platform-wide statistics for recruiter dashboard.
    
    Returns:
        Aggregate statistics about candidates and rankings
    """
    # Total candidates with skill vectors
    result = await db.execute(
        select(func.count(CandidateSkillVector.id))
    )
    total_candidates = result.scalar() or 0
    
    # Total institutions
    result = await db.execute(
        select(func.count(func.distinct(CandidateSkillVector.institution_id)))
    )
    total_institutions = result.scalar() or 0
    
    # Candidates by percentile bucket
    result = await db.execute(
        select(
            func.case(
                (NationalCandidateRanking.percentile >= Decimal("90"), "90-100"),
                (NationalCandidateRanking.percentile >= Decimal("75"), "75-90"),
                (NationalCandidateRanking.percentile >= Decimal("50"), "50-75"),
                (NationalCandidateRanking.percentile >= Decimal("25"), "25-50"),
                else_="0-25"
            ).label("percentile_bucket"),
            func.count(NationalCandidateRanking.id)
        )
        .group_by("percentile_bucket")
    )
    percentile_distribution = {bucket: count for bucket, count in result.all()}
    
    # Log access
    log = RecruiterAccessLog(
        recruiter_user_id=current_user.id,
        candidate_user_id=0,
        access_type="platform_stats",
        accessed_at=datetime.utcnow()
    )
    db.add(log)
    await db.flush()
    
    return {
        "platform_stats": {
            "total_candidates": total_candidates,
            "total_institutions": total_institutions,
            "percentile_distribution": percentile_distribution
        },
        "accessed_at": datetime.utcnow().isoformat()
    }
