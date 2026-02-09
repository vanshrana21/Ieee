"""
backend/services/judge_evaluation.py
Phase 9: Judging, Evaluation & Competition Scoring System

Core service for judge evaluations with blind evaluation support,
score calculation, and audit logging. Zero AI involvement.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from backend.orm.user import User, UserRole
from backend.orm.moot_project import MootProject
from backend.orm.judge_evaluation import (
    JudgeAssignment, EvaluationRubric, JudgeEvaluation, EvaluationAuditLog, EvaluationAction
)

logger = logging.getLogger(__name__)


class EvaluationError(Exception):
    """Raised when evaluation operation fails"""
    def __init__(self, message: str, code: str = "EVALUATION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class JudgeEvaluationService:
    """
    Phase 9: Central service for judge evaluations.
    
    Responsibilities:
    - Blind evaluation preparation (strip student identities)
    - Score calculation and validation
    - Finalization (immutable)
    - Audit logging
    - Score aggregation for results
    """
    
    @staticmethod
    async def get_blind_project_view(
        db: AsyncSession,
        assignment: JudgeAssignment
    ) -> Dict[str, Any]:
        """
        Phase 9: Prepare blind project view for judge evaluation.
        
        Strips all student-identifying information.
        Returns only the content needed for evaluation.
        """
        if not assignment.project_id:
            raise EvaluationError("No project assigned to this assignment")
        
        # Load project
        result = await db.execute(
            select(MootProject).where(MootProject.id == assignment.project_id)
        )
        project = result.scalar_one_or_none()
        
        if not project:
            raise EvaluationError("Project not found")
        
        # Build blind view - NO student names, NO team names, NO emails
        blind_view = {
            "project_id": project.id,  # Judge needs this to identify internally
            "competition_id": project.competition_id,
            "side": project.side,
            "submission_status": project.submission_status,
            "title": project.project_title if not assignment.is_blind else f"Project #{project.id}",
            "issues": [],
            "irac_summary": {},
            "oral_rounds": [],
            "blind_warnings": [
                "Student identities are hidden for fair evaluation",
                "Do not attempt to identify students based on content",
                "Evaluate on merit only"
            ] if assignment.is_blind else []
        }
        
        # Include issues (without author info)
        if hasattr(project, 'issues') and project.issues:
            blind_view["issues"] = [
                {
                    "id": issue.id,
                    "title": issue.title,
                    "description": issue.description,
                    "order": issue.issue_order
                }
                for issue in project.issues
            ]
        
        # Include IRAC blocks (without editor info)
        if hasattr(project, 'irac_blocks') and project.irac_blocks:
            irac_by_issue = {}
            for block in project.irac_blocks:
                if block.issue_id not in irac_by_issue:
                    irac_by_issue[block.issue_id] = []
                irac_by_issue[block.issue_id].append({
                    "type": block.block_type,
                    "content": block.content,
                    "version": block.version
                })
            blind_view["irac_summary"] = irac_by_issue
        
        return blind_view
    
    @staticmethod
    async def calculate_total_score(
        scores: Dict[str, int],
        rubric_criteria: List[Dict[str, Any]]
    ) -> int:
        """
        Phase 9: Calculate total score from individual criterion scores.
        Simple summation - NO AI, NO weighting by default.
        """
        total = 0
        for criterion in rubric_criteria:
            key = criterion.get("key")
            score = scores.get(key, 0)
            total += score
        return total
    
    @staticmethod
    async def validate_scores(
        scores: Dict[str, int],
        rubric_criteria: List[Dict[str, Any]]
    ) -> tuple[bool, Optional[str]]:
        """
        Phase 9: Validate scores against rubric criteria.
        
        Returns: (is_valid, error_message)
        """
        for criterion in rubric_criteria:
            key = criterion.get("key")
            max_score = criterion.get("max")
            label = criterion.get("label", key)
            
            if key not in scores:
                return False, f"Missing score for criterion: {label}"
            
            score = scores[key]
            if not isinstance(score, int) or score < 0 or score > max_score:
                return False, f"Score for {label} ({score}) must be between 0 and {max_score}"
        
        return True, None
    
    @staticmethod
    async def log_evaluation_action(
        db: AsyncSession,
        institution_id: int,
        judge_id: int,
        evaluation_id: int,
        action: EvaluationAction,
        ip_address: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> EvaluationAuditLog:
        """
        Phase 9: Log evaluation action to audit trail.
        """
        log_entry = EvaluationAuditLog(
            institution_id=institution_id,
            judge_id=judge_id,
            evaluation_id=evaluation_id,
            action=action,
            timestamp=datetime.utcnow(),
            ip_address=ip_address,
            context=context
        )
        
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        
        return log_entry
    
    @staticmethod
    async def aggregate_competition_results(
        db: AsyncSession,
        competition_id: int,
        institution_id: int
    ) -> List[Dict[str, Any]]:
        """
        Phase 9: Aggregate final scores for competition results.
        
        Calculates:
        - Average score per team/project
        - Judge count per team
        - Rankings
        
        NO AI involvement - simple mathematical aggregation.
        """
        # Get all finalized evaluations for competition
        result = await db.execute(
            select(JudgeEvaluation)
            .where(
                and_(
                    JudgeEvaluation.institution_id == institution_id,
                    JudgeEvaluation.is_final == True,
                    JudgeEvaluation.assignment_id.in_(
                        select(JudgeAssignment.id)
                        .where(
                            and_(
                                JudgeAssignment.competition_id == competition_id,
                                JudgeAssignment.institution_id == institution_id
                            )
                        )
                    )
                )
            )
        )
        
        evaluations = result.scalars().all()
        
        # Group by project
        project_scores = {}
        for eval in evaluations:
            if eval.project_id not in project_scores:
                project_scores[eval.project_id] = {
                    "scores": [],
                    "total_score": 0,
                    "judge_count": 0
                }
            
            project_scores[eval.project_id]["scores"].append(eval.total_score)
            project_scores[eval.project_id]["total_score"] += eval.total_score
            project_scores[eval.project_id]["judge_count"] += 1
        
        # Calculate averages
        results = []
        for project_id, data in project_scores.items():
            if data["judge_count"] > 0:
                avg_score = data["total_score"] / data["judge_count"]
                results.append({
                    "project_id": project_id,
                    "total_score": data["total_score"],
                    "average_score": round(avg_score, 2),
                    "judge_count": data["judge_count"],
                    "rank": 0  # Will be assigned after sorting
                })
        
        # Sort by average score descending and assign ranks
        results.sort(key=lambda x: x["average_score"], reverse=True)
        for i, result in enumerate(results, 1):
            result["rank"] = i
        
        return results
    
    @staticmethod
    async def can_judge_edit_evaluation(
        evaluation: JudgeEvaluation,
        judge_id: int
    ) -> tuple[bool, Optional[str]]:
        """
        Phase 9: Check if judge can edit an evaluation.
        
        Returns: (can_edit, reason_if_not)
        """
        # Check ownership
        if evaluation.judge_id != judge_id:
            return False, "You can only edit your own evaluations"
        
        # Check if finalized
        if evaluation.is_final:
            return False, "Evaluation is finalized and cannot be edited"
        
        return True, None
    
    @staticmethod
    async def get_default_rubric(
        db: AsyncSession,
        institution_id: int
    ) -> Optional[EvaluationRubric]:
        """
        Phase 9: Get default rubric for institution.
        Creates one if none exists.
        """
        result = await db.execute(
            select(EvaluationRubric)
            .where(
                and_(
                    EvaluationRubric.institution_id == institution_id,
                    EvaluationRubric.is_default == True,
                    EvaluationRubric.is_active == True
                )
            )
        )
        
        rubric = result.scalar_one_or_none()
        
        if not rubric:
            # Create default rubric
            default_criteria = [
                {"key": "issue_framing", "label": "Issue Framing", "max": 10, "description": "Clarity and precision in identifying issues"},
                {"key": "legal_reasoning", "label": "Legal Reasoning", "max": 20, "description": "Quality of legal analysis and argumentation"},
                {"key": "use_of_authority", "label": "Use of Authority", "max": 15, "description": "Effective use of case law and statutes"},
                {"key": "oral_advocacy", "label": "Oral Advocacy", "max": 25, "description": "Presentation skills and persuasiveness"},
                {"key": "responsiveness", "label": "Responsiveness", "max": 20, "description": "Ability to address questions and counter-arguments"},
                {"key": "court_manner", "label": "Court Manner", "max": 10, "description": "Professionalism and etiquette"}
            ]
            
            total = sum(c["max"] for c in default_criteria)
            
            rubric = EvaluationRubric(
                institution_id=institution_id,
                title="Standard Moot Court Rubric",
                description="Default rubric for moot court evaluations",
                criteria=default_criteria,
                total_score=total,
                is_active=True,
                is_default=True
            )
            
            db.add(rubric)
            await db.commit()
            await db.refresh(rubric)
        
        return rubric
