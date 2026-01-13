"""
backend/services/recommendations.py
Rule-Based Learning Recommendation Engine

PHASE 8: Intelligent Learning Engine - Component 2

PURPOSE:
Provide deterministic, actionable study recommendations based on:
- Completion percentage
- Practice accuracy
- Last activity timestamp
- Subject-specific performance

NO ML/TRAINING INVOLVED - Pure rule-based logic.

RECOMMENDATION TYPES:
- Urgent: Low accuracy, critical gaps
- Important: Incomplete modules, weak areas
- Suggested: Revision, next steps
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.subject_progress import SubjectProgress
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.curriculum import CourseCurriculum

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Deterministic study recommendation engine.
    
    All decisions based on if/else rules, no machine learning.
    """
    
    # ========== THRESHOLDS ==========
    
    ACCURACY_THRESHOLD_LOW = 0.60      # Below 60% = needs practice
    ACCURACY_THRESHOLD_HIGH = 0.80     # Above 80% = proficient
    COMPLETION_THRESHOLD_LOW = 0.30    # Below 30% = just started
    COMPLETION_THRESHOLD_HIGH = 0.90   # Above 90% = nearly complete
    INACTIVITY_DAYS_THRESHOLD = 7      # 7+ days = needs revision
    MIN_ATTEMPTS_THRESHOLD = 3         # < 3 attempts = insufficient practice
    
    # ========== DECISION RULES ==========
    
    @staticmethod
    def analyze_subject_status(
        subject_progress: SubjectProgress,
        practice_accuracy: Optional[float],
        days_since_activity: int,
        total_attempts: int
    ) -> List[Dict[str, Any]]:
        """
        Apply decision rules for a single subject.
        
        Args:
            subject_progress: Subject completion data
            practice_accuracy: MCQ accuracy (0-100) or None
            days_since_activity: Days since last interaction
            total_attempts: Total practice attempts
        
        Returns:
            List of recommendations with priority
        """
        recommendations = []
        completion = subject_progress.completion_percentage / 100.0
        accuracy = (practice_accuracy / 100.0) if practice_accuracy else None
        
        # RULE 1: Low completion + Low accuracy = URGENT practice needed
        if completion < RecommendationEngine.COMPLETION_THRESHOLD_LOW and \
           accuracy and accuracy < RecommendationEngine.ACCURACY_THRESHOLD_LOW:
            recommendations.append({
                "priority": "urgent",
                "type": "practice",
                "subject_id": subject_progress.subject_id,
                "reason": f"Low accuracy ({practice_accuracy:.1f}%) indicates gaps in understanding",
                "action": "Complete practice questions to identify weak areas"
            })
        
        # RULE 2: High completion + Low accuracy = URGENT targeted practice
        elif completion >= RecommendationEngine.COMPLETION_THRESHOLD_LOW and \
             accuracy and accuracy < RecommendationEngine.ACCURACY_THRESHOLD_LOW:
            recommendations.append({
                "priority": "urgent",
                "type": "practice_weak_areas",
                "subject_id": subject_progress.subject_id,
                "reason": f"Despite {completion*100:.0f}% completion, accuracy is only {practice_accuracy:.1f}%",
                "action": "Focus on practice questions in weak topics"
            })
        
        # RULE 3: Low completion + No accuracy data = IMPORTANT study needed
        elif completion < RecommendationEngine.COMPLETION_THRESHOLD_LOW:
            recommendations.append({
                "priority": "important",
                "type": "study",
                "subject_id": subject_progress.subject_id,
                "reason": f"Only {completion*100:.0f}% complete",
                "action": "Complete remaining learning modules"
            })
        
        # RULE 4: Moderate completion + Insufficient attempts = IMPORTANT practice
        elif completion >= RecommendationEngine.COMPLETION_THRESHOLD_LOW and \
             completion < RecommendationEngine.COMPLETION_THRESHOLD_HIGH and \
             total_attempts < RecommendationEngine.MIN_ATTEMPTS_THRESHOLD:
            recommendations.append({
                "priority": "important",
                "type": "practice_more",
                "subject_id": subject_progress.subject_id,
                "reason": f"Only {total_attempts} practice attempts so far",
                "action": "Attempt more questions to test understanding"
            })
        
        # RULE 5: Long inactivity = IMPORTANT revision
        if days_since_activity >= RecommendationEngine.INACTIVITY_DAYS_THRESHOLD:
            recommendations.append({
                "priority": "important" if days_since_activity >= 14 else "suggested",
                "type": "revise",
                "subject_id": subject_progress.subject_id,
                "reason": f"Last activity {days_since_activity} days ago",
                "action": "Quick revision to maintain retention"
            })
        
        # RULE 6: High completion + High accuracy = SUGGESTED advance
        if completion >= RecommendationEngine.COMPLETION_THRESHOLD_HIGH and \
           accuracy and accuracy >= RecommendationEngine.ACCURACY_THRESHOLD_HIGH:
            recommendations.append({
                "priority": "suggested",
                "type": "advance",
                "subject_id": subject_progress.subject_id,
                "reason": f"Excellent progress: {completion*100:.0f}% complete, {practice_accuracy:.1f}% accuracy",
                "action": "Ready to move to next subject"
            })
        
        # RULE 7: Moderate progress = SUGGESTED continue
        if RecommendationEngine.COMPLETION_THRESHOLD_LOW <= completion < RecommendationEngine.COMPLETION_THRESHOLD_HIGH and \
           not any(r["priority"] == "urgent" for r in recommendations):
            recommendations.append({
                "priority": "suggested",
                "type": "continue",
                "subject_id": subject_progress.subject_id,
                "reason": f"Good progress: {completion*100:.0f}% complete",
                "action": "Continue with current pace"
            })
        
        return recommendations
    
    # ========== DATA FETCHING ==========
    
    @staticmethod
    async def fetch_subject_metrics(
        db: AsyncSession,
        user_id: int,
        subject_id: int
    ) -> Dict[str, Any]:
        """
        Fetch all metrics needed for subject recommendations.
        
        Returns:
            {
                "completion": float,
                "accuracy": Optional[float],
                "days_since_activity": int,
                "total_attempts": int
            }
        """
        # Get subject progress
        progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == user_id,
            SubjectProgress.subject_id == subject_id
        )
        progress_result = await db.execute(progress_stmt)
        progress = progress_result.scalar_one_or_none()
        
        if not progress:
            return {
                "completion": 0.0,
                "accuracy": None,
                "days_since_activity": 999,
                "total_attempts": 0
            }
        
        # Calculate days since last activity
        days_since = (datetime.utcnow() - progress.last_activity_at).days
        
        # Get practice modules for subject
        modules_stmt = select(ContentModule.id).where(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.PRACTICE
        )
        module_ids = [row[0] for row in (await db.execute(modules_stmt)).fetchall()]
        
        if not module_ids:
            return {
                "completion": progress.completion_percentage,
                "accuracy": None,
                "days_since_activity": days_since,
                "total_attempts": 0
            }
        
        # Get practice question IDs
        from backend.orm.practice_question import PracticeQuestion
        question_ids_stmt = select(PracticeQuestion.id).where(
            PracticeQuestion.module_id.in_(module_ids)
        )
        question_ids = [row[0] for row in (await db.execute(question_ids_stmt)).fetchall()]
        
        if not question_ids:
            return {
                "completion": progress.completion_percentage,
                "accuracy": None,
                "days_since_activity": days_since,
                "total_attempts": 0
            }
        
        # Count total attempts
        total_attempts_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids)
        )
        total_attempts = (await db.execute(total_attempts_stmt)).scalar() or 0
        
        # Calculate accuracy (MCQs only)
        correct_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct == True
        )
        correct_count = (await db.execute(correct_stmt)).scalar() or 0
        
        mcq_attempts_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct.isnot(None)
        )
        mcq_attempts = (await db.execute(mcq_attempts_stmt)).scalar() or 0
        
        accuracy = (correct_count / mcq_attempts * 100) if mcq_attempts > 0 else None
        
        return {
            "completion": progress.completion_percentage,
            "accuracy": accuracy,
            "days_since_activity": days_since,
            "total_attempts": total_attempts
        }
    
    # ========== MAIN RECOMMENDATION METHODS ==========
    
    @staticmethod
    async def get_recommendations(
        user: User,
        db: AsyncSession
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate all recommendations for user.
        
        Args:
            user: Current user
            db: Database session
        
        Returns:
            {
                "urgent": [...],
                "important": [...],
                "suggested": [...]
            }
        """
        logger.info(f"Generating recommendations for user: {user.email}")
        
        if not user.course_id or not user.current_semester:
            logger.warning(f"User {user.email} not enrolled")
            return {"urgent": [], "important": [], "suggested": []}
        
        # Get all subjects user can access
        curriculum_stmt = select(CourseCurriculum).where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.semester_number <= user.current_semester,
            CourseCurriculum.is_active == True
        )
        curriculum_items = (await db.execute(curriculum_stmt)).scalars().all()
        subject_ids = [item.subject_id for item in curriculum_items]
        
        if not subject_ids:
            return {"urgent": [], "important": [], "suggested": []}
        
        # Get subject names
        subjects_stmt = select(Subject).where(Subject.id.in_(subject_ids))
        subjects = {s.id: s for s in (await db.execute(subjects_stmt)).scalars().all()}
        
        # Analyze each subject
        all_recommendations = []
        
        for subject_id in subject_ids:
            # Get subject progress
            progress_stmt = select(SubjectProgress).where(
                SubjectProgress.user_id == user.id,
                SubjectProgress.subject_id == subject_id
            )
            progress = (await db.execute(progress_stmt)).scalar_one_or_none()
            
            if not progress:
                # No progress = recommend starting
                all_recommendations.append({
                    "priority": "important",
                    "type": "start",
                    "subject_id": subject_id,
                    "subject_name": subjects[subject_id].title,
                    "reason": "Not started yet",
                    "action": "Begin with learning modules"
                })
                continue
            
            # Fetch metrics
            metrics = await RecommendationEngine.fetch_subject_metrics(
                db, user.id, subject_id
            )
            
            # Apply decision rules
            subject_recs = RecommendationEngine.analyze_subject_status(
                progress,
                metrics["accuracy"],
                metrics["days_since_activity"],
                metrics["total_attempts"]
            )
            
            # Add subject name
            for rec in subject_recs:
                rec["subject_name"] = subjects[subject_id].title
            
            all_recommendations.extend(subject_recs)
        
        # Group by priority
        grouped = {
            "urgent": [r for r in all_recommendations if r["priority"] == "urgent"],
            "important": [r for r in all_recommendations if r["priority"] == "important"],
            "suggested": [r for r in all_recommendations if r["priority"] == "suggested"]
        }
        
        logger.info(
            f"Generated recommendations: "
            f"{len(grouped['urgent'])} urgent, "
            f"{len(grouped['important'])} important, "
            f"{len(grouped['suggested'])} suggested"
        )
        
        return grouped
    
    @staticmethod
    async def get_next_action(
        user: User,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Get single most important next action.
        
        Returns highest priority recommendation.
        """
        all_recs = await RecommendationEngine.get_recommendations(user, db)
        
        # Return first urgent, or first important, or first suggested
        if all_recs["urgent"]:
            return all_recs["urgent"][0]
        elif all_recs["important"]:
            return all_recs["important"][0]
        elif all_recs["suggested"]:
            return all_recs["suggested"][0]
        
        return None