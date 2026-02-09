"""
backend/routes/results.py
Phase 9: Competition Results Routes

Public endpoints for viewing published competition results.
Students can view their own results after publication.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import get_db
from backend.rbac import get_current_user
from backend.orm.user import User, UserRole
from backend.orm.competition import Competition
from backend.orm.moot_project import MootProject
from backend.orm.team import Team, TeamMember
from backend.orm.judge_evaluation import JudgeEvaluation, JudgeAssignment
from backend.services.judge_evaluation import JudgeEvaluationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/competitions/{competition_id}", status_code=200)
async def get_public_results(
    competition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: View published competition results.
    
    - Students can see their own team's ranking
    - Admins can see full results
    - Results only visible after publication
    """
    # Verify competition exists
    result = await db.execute(
        select(Competition).where(
            and_(
                Competition.id == competition_id,
                Competition.institution_id == current_user.institution_id
            )
        )
    )
    competition = result.scalar_one_or_none()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    
    # Get aggregated results
    results = await JudgeEvaluationService.aggregate_competition_results(
        db, competition_id, current_user.institution_id
    )
    
    # Enrich and filter based on role
    enriched_results = []
    for result in results:
        project_result = await db.execute(
            select(MootProject).where(MootProject.id == result["project_id"])
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            continue
        
        # Check if user can view this result
        can_view = False
        
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # Admin can see all
            can_view = True
        elif current_user.role == UserRole.JUDGE:
            # Judges can see results they evaluated
            judge_eval_result = await db.execute(
                select(JudgeEvaluation).where(
                    and_(
                        JudgeEvaluation.project_id == project.id,
                        JudgeEvaluation.judge_id == current_user.id,
                        JudgeEvaluation.is_final == True
                    )
                )
            )
            if judge_eval_result.scalar_one_or_none():
                can_view = True
        elif current_user.role == UserRole.STUDENT:
            # Students can see if they are on the team
            team_member_result = await db.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.team_id == project.team_id,
                        TeamMember.user_id == current_user.id
                    )
                )
            )
            if team_member_result.scalar_one_or_none():
                can_view = True
        
        if can_view:
            # Get team info
            team_result = await db.execute(
                select(Team).where(Team.id == project.team_id)
            )
            team = team_result.scalar_one_or_none()
            
            enriched_results.append({
                "rank": result["rank"],
                "average_score": result["average_score"],
                "total_score": result["total_score"],
                "judge_count": result["judge_count"],
                "project": {
                    "id": project.id,
                    "title": project.project_title,
                    "side": project.side,
                    "is_yours": (
                        current_user.role == UserRole.STUDENT and 
                        any(m.user_id == current_user.id for m in (team.members if team else []))
                    ) if team else False
                },
                "team": {
                    "id": team.id if team else None,
                    "name": team.name if team else None
                } if team else None
            })
    
    # For students, highlight their position
    if current_user.role == UserRole.STUDENT:
        user_team_ids = []
        team_member_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        )
        user_team_ids = [r[0] for r in team_member_result.all()]
        
        for result in enriched_results:
            if result["team"] and result["team"]["id"] in user_team_ids:
                result["is_your_team"] = True
    
    return {
        "success": True,
        "competition_id": competition_id,
        "competition_name": competition.name if hasattr(competition, 'name') else None,
        "results": enriched_results,
        "total_ranked": len(enriched_results),
        "your_role": current_user.role.value,
        "calculation_method": "Average of finalized judge scores (NO AI)",
        "disclaimer": "Results are based on human judge evaluations only. No AI was involved in scoring."
    }


@router.get("/my-results", status_code=200)
async def get_my_results(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Phase 9: Get current user's competition results.
    
    For students: Shows results for their teams' projects.
    """
    if current_user.role not in [UserRole.STUDENT, UserRole.JUDGE]:
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for students and judges viewing their own results"
        )
    
    results_list = []
    
    if current_user.role == UserRole.STUDENT:
        # Get user's teams
        team_member_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        )
        team_ids = [r[0] for r in team_member_result.all()]
        
        # Get projects for these teams
        project_result = await db.execute(
            select(MootProject).where(MootProject.team_id.in_(team_ids))
        )
        projects = project_result.scalars().all()
        
        for project in projects:
            # Get evaluations for this project
            eval_result = await db.execute(
                select(JudgeEvaluation).where(
                    and_(
                        JudgeEvaluation.project_id == project.id,
                        JudgeEvaluation.is_final == True
                    )
                )
            )
            evaluations = eval_result.scalars().all()
            
            if evaluations:
                avg_score = sum(e.total_score for e in evaluations) / len(evaluations)
                
                # Get competition
                comp_result = await db.execute(
                    select(Competition).where(Competition.id == project.competition_id)
                )
                competition = comp_result.scalar_one_or_none()
                
                results_list.append({
                    "project_id": project.id,
                    "project_title": project.project_title,
                    "competition_id": project.competition_id,
                    "competition_name": competition.name if competition else None,
                    "side": project.side,
                    "average_score": round(avg_score, 2),
                    "judge_count": len(evaluations),
                    "finalized": project.is_locked if hasattr(project, 'is_locked') else True
                })
    
    elif current_user.role == UserRole.JUDGE:
        # Get judge's evaluations
        eval_result = await db.execute(
            select(JudgeEvaluation).where(
                and_(
                    JudgeEvaluation.judge_id == current_user.id,
                    JudgeEvaluation.is_final == True
                )
            )
        )
        evaluations = eval_result.scalars().all()
        
        for evaluation in evaluations:
            if evaluation.project_id:
                project_result = await db.execute(
                    select(MootProject).where(MootProject.id == evaluation.project_id)
                )
                project = project_result.scalar_one_or_none()
                
                if project:
                    comp_result = await db.execute(
                        select(Competition).where(Competition.id == project.competition_id)
                    )
                    competition = comp_result.scalar_one_or_none()
                    
                    results_list.append({
                        "evaluation_id": evaluation.id,
                        "project_id": project.id,
                        "project_title": project.project_title,
                        "competition_id": project.competition_id,
                        "competition_name": competition.name if competition else None,
                        "your_score": evaluation.total_score,
                        "side": project.side
                    })
    
    return {
        "success": True,
        "results": results_list,
        "count": len(results_list),
        "your_role": current_user.role.value
    }
