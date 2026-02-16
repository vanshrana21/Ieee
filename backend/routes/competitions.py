from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from typing import List, Optional
import os
import uuid
from pydantic import BaseModel, validator

from backend.database import get_db
from backend.orm.competition import Competition, CompetitionStatus
from backend.orm.team import Team, TeamMember, TeamRole
from backend.orm.memorial import MemorialSubmission, MemorialStatus
from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject
from backend.routes.auth import get_current_user
from backend.services.ai_judge_service import AIJudgeEngine as AIJudgeService

router = APIRouter(prefix="/api/competitions", tags=["competitions"])

UPLOAD_DIR = "uploads/memorials"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class CompetitionCreate(BaseModel):
    title: str
    description: str
    problem_id: int
    start_date: str
    memorial_deadline: str
    oral_start_date: str
    oral_end_date: str
    max_team_size: int = 4
    
    @validator('start_date', 'memorial_deadline', 'oral_start_date', 'oral_end_date')
    def validate_datetime(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Invalid datetime format. Use ISO 8601 (e.g., 2026-02-10T14:30:00)")

class CompetitionResponse(BaseModel):
    id: int
    title: str
    description: str
    problem_id: int
    start_date: str
    memorial_deadline: str
    oral_start_date: str
    oral_end_date: str
    max_team_size: int
    status: str
    teams_count: int
    created_by_id: int

class TeamCreate(BaseModel):
    name: str
    side: str
    
    @validator('side')
    def validate_side(cls, v):
        if v not in ["petitioner", "respondent"]:
            raise ValueError("Side must be 'petitioner' or 'respondent'")
        return v

class MemorialResponse(BaseModel):
    id: int
    status: str
    submitted_at: str
    score_overall: Optional[float]
    badges_earned: List[str]

@router.post("/", response_model=CompetitionResponse)
async def create_competition(
    comp: CompetitionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role not in [UserRole.teacher, UserRole.teacher, UserRole.teacher]:
        raise HTTPException(status_code=403, detail="Only admins/faculty can create competitions")
    
    result = await db.execute(select(MootProject).where(MootProject.id == comp.problem_id))
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    
    new_comp = Competition(
        title=comp.title,
        description=comp.description,
        problem_id=comp.problem_id,
        start_date=datetime.fromisoformat(comp.start_date.replace('Z', '+00:00')),
        memorial_deadline=datetime.fromisoformat(comp.memorial_deadline.replace('Z', '+00:00')),
        oral_start_date=datetime.fromisoformat(comp.oral_start_date.replace('Z', '+00:00')),
        oral_end_date=datetime.fromisoformat(comp.oral_end_date.replace('Z', '+00:00')),
        max_team_size=comp.max_team_size,
        status=CompetitionStatus.DRAFT,
        created_by_id=current_user.id
    )
    
    db.add(new_comp)
    await db.commit()
    await db.refresh(new_comp)
    
    team_count = 0
    
    return CompetitionResponse(
        id=new_comp.id,
        title=new_comp.title,
        description=new_comp.description,
        problem_id=new_comp.problem_id,
        start_date=new_comp.start_date.isoformat(),
        memorial_deadline=new_comp.memorial_deadline.isoformat(),
        oral_start_date=new_comp.oral_start_date.isoformat(),
        oral_end_date=new_comp.oral_end_date.isoformat(),
        max_team_size=new_comp.max_team_size,
        status=new_comp.status.value,
        teams_count=team_count,
        created_by_id=new_comp.created_by_id
    )

@router.get("/", response_model=List[CompetitionResponse])
async def list_competitions(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Competition).order_by(Competition.start_date.desc())
    
    if status and status in [s.value for s in CompetitionStatus]:
        query = query.where(Competition.status == status)
    
    result = await db.execute(query)
    competitions = result.scalars().all()
    
    responses = []
    for comp in competitions:
        team_count_result = await db.execute(
            select(func.count(Team.id)).where(Team.competition_id == comp.id)
        )
        team_count = team_count_result.scalar()
        
        responses.append(CompetitionResponse(
            id=comp.id,
            title=comp.title,
            description=comp.description,
            problem_id=comp.problem_id,
            start_date=comp.start_date.isoformat(),
            memorial_deadline=comp.memorial_deadline.isoformat(),
            oral_start_date=comp.oral_start_date.isoformat(),
            oral_end_date=comp.oral_end_date.isoformat(),
            max_team_size=comp.max_team_size,
            status=comp.status.value,
            teams_count=team_count,
            created_by_id=comp.created_by_id
        ))
    
    return responses

@router.get("/{comp_id}", response_model=CompetitionResponse)
async def get_competition(
    comp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Competition).where(Competition.id == comp_id))
    comp = result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    team_count_result = await db.execute(
        select(func.count(Team.id)).where(Team.competition_id == comp_id)
    )
    team_count = team_count_result.scalar()
    
    return CompetitionResponse(
        id=comp.id,
        title=comp.title,
        description=comp.description,
        problem_id=comp.problem_id,
        start_date=comp.start_date.isoformat(),
        memorial_deadline=comp.memorial_deadline.isoformat(),
        oral_start_date=comp.oral_start_date.isoformat(),
        oral_end_date=comp.oral_end_date.isoformat(),
        max_team_size=comp.max_team_size,
        status=comp.status.value,
        teams_count=team_count,
        created_by_id=comp.created_by_id
    )

@router.post("/{comp_id}/teams", response_model=dict)
async def create_team(
    comp_id: int,
    team: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    comp_result = await db.execute(select(Competition).where(Competition.id == comp_id))
    comp = comp_result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    if comp.status != CompetitionStatus.LIVE:
        raise HTTPException(status_code=400, detail="Competition is not live")
    
    existing_result = await db.execute(
        select(TeamMember).join(Team).where(
            TeamMember.user_id == current_user.id,
            Team.competition_id == comp_id
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You are already in a team for this competition")
    
    new_team = Team(
        competition_id=comp_id,
        name=team.name,
        side=team.side
    )
    db.add(new_team)
    await db.commit()
    await db.refresh(new_team)
    
    captain = TeamMember(
        team_id=new_team.id,
        user_id=current_user.id,
        role=TeamRole.SPEAKER_1,
        is_captain=True
    )
    db.add(captain)
    await db.commit()
    
    return {"message": "Team created successfully", "team_id": new_team.id, "team_name": new_team.name}

@router.post("/{comp_id}/teams/{team_id}/join", response_model=dict)
async def join_team(
    comp_id: int,
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team_result = await db.execute(
        select(Team).where(Team.id == team_id, Team.competition_id == comp_id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    member_count_result = await db.execute(
        select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)
    )
    if member_count_result.scalar() >= team.competition.max_team_size:
        raise HTTPException(status_code=400, detail="Team is full")
    
    existing_result = await db.execute(
        select(TeamMember).join(Team).where(
            TeamMember.user_id == current_user.id,
            Team.competition_id == comp_id
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You are already in a team for this competition")
    
    new_member = TeamMember(
        team_id=team_id,
        user_id=current_user.id,
        role=TeamRole.RESEARCHER_1,
        is_captain=False
    )
    db.add(new_member)
    await db.commit()
    
    return {"message": "Joined team successfully", "team_id": team_id}

@router.post("/{comp_id}/teams/{team_id}/memorials", response_model=dict)
async def submit_memorial(
    comp_id: int,
    team_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team_result = await db.execute(
        select(Team).where(Team.id == team_id, Team.competition_id == comp_id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    member_result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
            TeamMember.is_captain == True
        )
    )
    if not member_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Only team captain can submit memorials")
    
    comp_result = await db.execute(select(Competition).where(Competition.id == comp_id))
    comp = comp_result.scalar_one_or_none()
    if datetime.now(timezone.utc) > comp.memorial_deadline.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Memorial deadline has passed")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    if len(await file.read()) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")
    await file.seek(0)
    
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    memorial = MemorialSubmission(
        team_id=team_id,
        file_path=file_path,
        original_filename=file.filename,
        status=MemorialStatus.PENDING
    )
    db.add(memorial)
    await db.commit()
    await db.refresh(memorial)
    
    await analyze_memorial_background(memorial.id, db)
    
    return {
        "message": "Memorial submitted successfully. AI analysis in progress...",
        "memorial_id": memorial.id,
        "status": memorial.status.value
    }

@router.get("/{comp_id}/teams/{team_id}/memorials", response_model=List[MemorialResponse])
async def get_team_memorials(
    comp_id: int,
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member_result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id
        )
    )
    if not member_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this team")
    
    result = await db.execute(
        select(MemorialSubmission).where(MemorialSubmission.team_id == team_id)
    )
    memorials = result.scalars().all()
    
    return [{
        "id": m.id,
        "status": m.status.value,
        "submitted_at": m.submitted_at.isoformat(),
        "score_overall": m.score_overall,
        "badges_earned": m.badges_earned.split(",") if m.badges_earned else []
    } for m in memorials]

async def analyze_memorial_background(memorial_id: int, db: AsyncSession):
    from sqlalchemy import select
    from backend.orm.memorial import MemorialSubmission, MemorialStatus
    from backend.orm.team import Team
    
    try:
        result = await db.execute(
            select(MemorialSubmission).where(MemorialSubmission.id == memorial_id)
        )
        memorial = result.scalar_one_or_none()
        if not memorial:
            return
        
        if not os.path.exists(memorial.file_path):
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = "File not found"
            await db.commit()
            return
        
        with open(memorial.file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:5000]
        
        team_result = await db.execute(select(Team).where(Team.id == memorial.team_id))
        team = team_result.scalar_one_or_none()
        side = team.side if team else "petitioner"
        
        ai_judge = AIJudgeService()
        analysis = ai_judge.analyze_argument(content, side)
        
        scores = analysis.get("scores", analysis.get("score_breakdown", {}))
        irac_score = scores.get("legal_accuracy", 3)
        citation_score = scores.get("citation", 3)
        structure_score = scores.get("etiquette", 3)
        overall = (irac_score + citation_score + structure_score) / 3.0
        
        badges = []
        behavior = analysis.get("behavior_data", {})
        if behavior.get("has_my_lord"):
            badges.append("Etiquette_Master")
        if behavior.get("valid_scc_citation"):
            badges.append("SCC_Format_Expert")
        if not behavior.get("needs_proportionality", True):
            badges.append("Proportionality_Pro")
        
        memorial.status = MemorialStatus.ACCEPTED
        memorial.ai_feedback = analysis.get("feedback", "Analysis complete")[:1000]
        memorial.score_irac = min(5, max(1, int(irac_score)))
        memorial.score_citation = min(5, max(1, int(citation_score)))
        memorial.score_structure = min(5, max(1, int(structure_score)))
        memorial.score_overall = round(overall, 2)
        memorial.badges_earned = ",".join(badges) if badges else None
        memorial.processed_at = datetime.now(timezone.utc)
        
        await db.commit()
        
    except Exception as e:
        if memorial:
            memorial.status = MemorialStatus.REJECTED
            memorial.ai_feedback = f"Analysis failed: {str(e)[:500]}"
            await db.commit()
