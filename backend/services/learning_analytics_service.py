"""
backend/services/learning_analytics_service.py
Learning Analytics & Intelligence Service

PHASE 10: Pure backend intelligence layer for learning insights

PURPOSE:
- Interpret user progress data
- Detect strengths & weaknesses
- Generate actionable insights
- Provide foundation for future AI tutoring

DESIGN PRINCIPLES:
- Read-only operations (no data mutation)
- Deterministic rules (no AI/LLM calls)
- Reusable by future systems
- No HTTP logic (pure business logic)
- Database-agnostic interfaces

INTELLIGENCE RULES:
- Accuracy < 50% → WEAK
- Accuracy 50-75% → AVERAGE
- Accuracy > 75% → STRONG
- Completion < 60% → Needs revision
- High time + low accuracy → Conceptual gap
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import joinedload

from backend.orm.user import User
from backend.orm.subject import Subject
from backend.orm.content_module import ContentModule, ModuleType
from backend.orm.learn_content import LearnContent
from backend.orm.case_content import CaseContent
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.user_content_progress import UserContentProgress, ContentType
from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.subject_progress import SubjectProgress

logger = logging.getLogger(__name__)


# ================= CLASSIFICATION ENUMS =================

class StrengthLevel(str, Enum):
    """Subject/topic strength classification"""
    WEAK = "weak"           # < 50% accuracy
    AVERAGE = "average"     # 50-75% accuracy
    STRONG = "strong"       # > 75% accuracy
    UNSTARTED = "unstarted" # No attempts yet


class RevisionPriority(str, Enum):
    """Revision urgency classification"""
    HIGH = "high"       # Weak + incomplete
    MEDIUM = "medium"   # Average or incomplete
    LOW = "low"         # Strong + complete
    NONE = "none"       # Perfect performance


class StudyConsistency(str, Enum):
    """Study pattern classification"""
    EXCELLENT = "excellent"  # Daily activity, steady progress
    GOOD = "good"           # Regular activity, good progress
    IRREGULAR = "irregular" # Sporadic activity
    INACTIVE = "inactive"   # No recent activity


# ================= ANALYTICS SERVICE =================

class LearningAnalyticsService:
    """
    Core service for learning intelligence.
    
    All methods are stateless and reusable.
    No HTTP logic - pure business logic only.
    """
    
    # Intelligence thresholds (centralized for easy tuning)
    ACCURACY_WEAK_THRESHOLD = 50.0
    ACCURACY_AVERAGE_THRESHOLD = 75.0
    COMPLETION_LOW_THRESHOLD = 60.0
    TIME_SPENT_HIGH_THRESHOLD = 600  # 10 minutes
    RECENT_ACTIVITY_DAYS = 7
    INACTIVE_DAYS = 14
    MIN_ATTEMPTS_FOR_ACCURACY = 3
    
    def __init__(self, db: AsyncSession):
        """
        Initialize service with database session.
        
        Args:
            db: AsyncSession for database queries
        """
        self.db = db
    
    # ================= USER SNAPSHOT =================
    
    async def get_user_learning_snapshot(
        self,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Generate comprehensive learning snapshot for user.
        
        Combines all analytics into single overview.
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with all key metrics
        """
        logger.info(f"Generating learning snapshot for user {user_id}")
        
        # Fetch all subject progress
        subject_progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == user_id
        )
        subject_progress_result = await self.db.execute(subject_progress_stmt)
        all_progress = subject_progress_result.scalars().all()
        
        # Calculate overall metrics
        total_subjects = len(all_progress)
        
        if total_subjects == 0:
            return {
                "total_subjects": 0,
                "overall_completion": 0.0,
                "overall_accuracy": None,
                "study_consistency": StudyConsistency.INACTIVE.value,
                "weak_subjects_count": 0,
                "strong_subjects_count": 0,
                "needs_revision_count": 0
            }
        
        # Overall completion
        overall_completion = round(
            sum(p.completion_percentage for p in all_progress) / total_subjects,
            2
        )
        
        # Overall accuracy
        overall_accuracy = await self._calculate_overall_accuracy(user_id)
        
        # Study consistency
        consistency = await self._calculate_study_consistency(user_id)
        
        # Subject classifications
        strength_map = await self.get_subject_strength_map(user_id)
        weak_count = sum(1 for s in strength_map if s["strength"] == StrengthLevel.WEAK.value)
        strong_count = sum(1 for s in strength_map if s["strength"] == StrengthLevel.STRONG.value)
        
        # Revision needs
        revision_recs = await self.get_revision_recommendations(user_id)
        high_priority_count = sum(1 for r in revision_recs if r["priority"] == RevisionPriority.HIGH.value)
        
        snapshot = {
            "total_subjects": total_subjects,
            "overall_completion": overall_completion,
            "overall_accuracy": overall_accuracy,
            "study_consistency": consistency.value,
            "weak_subjects_count": weak_count,
            "strong_subjects_count": strong_count,
            "needs_revision_count": high_priority_count,
            "last_activity": await self._get_last_activity_time(user_id)
        }
        
        logger.info(f"Snapshot generated: user={user_id}, completion={overall_completion}%")
        return snapshot
    
    # ================= SUBJECT STRENGTH ANALYSIS =================
    
    async def get_subject_strength_map(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Classify each subject by strength level.
        
        Logic:
        - Accuracy > 75% → STRONG
        - Accuracy 50-75% → AVERAGE
        - Accuracy < 50% → WEAK
        - No attempts → UNSTARTED
        
        Args:
            user_id: User ID
        
        Returns:
            List of subjects with strength classification
        """
        logger.info(f"Calculating subject strength map for user {user_id}")
        
        # Get all subject progress
        progress_stmt = (
            select(SubjectProgress)
            .options(joinedload(SubjectProgress.subject))
            .where(SubjectProgress.user_id == user_id)
        )
        progress_result = await self.db.execute(progress_stmt)
        all_progress = progress_result.scalars().all()
        
        strength_map = []
        
        for progress in all_progress:
            subject = progress.subject
            
            # Calculate accuracy for this subject
            accuracy = await self._calculate_subject_accuracy(user_id, subject.id)
            
            # Classify strength
            if accuracy is None:
                strength = StrengthLevel.UNSTARTED
            elif accuracy < self.ACCURACY_WEAK_THRESHOLD:
                strength = StrengthLevel.WEAK
            elif accuracy < self.ACCURACY_AVERAGE_THRESHOLD:
                strength = StrengthLevel.AVERAGE
            else:
                strength = StrengthLevel.STRONG
            
            strength_map.append({
                "subject_id": subject.id,
                "subject_title": subject.title,
                "completion_percentage": progress.completion_percentage,
                "accuracy": accuracy,
                "strength": strength.value,
                "total_items": progress.total_items,
                "completed_items": progress.completed_items
            })
        
        # Sort by strength (weak first) then by accuracy
        strength_order = {
            StrengthLevel.WEAK.value: 0,
            StrengthLevel.AVERAGE.value: 1,
            StrengthLevel.UNSTARTED.value: 2,
            StrengthLevel.STRONG.value: 3
        }
        
        strength_map.sort(key=lambda x: (
            strength_order.get(x["strength"], 99),
            x["accuracy"] if x["accuracy"] is not None else -1
        ))
        
        logger.info(f"Strength map calculated: {len(strength_map)} subjects")
        return strength_map
    
    # ================= PRACTICE ACCURACY ANALYSIS =================
    
    async def get_practice_accuracy(
        self,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Detailed practice accuracy breakdown.
        
        Provides:
        - Overall MCQ accuracy
        - Per-subject accuracy
        - Per-difficulty accuracy
        - Recent vs historical accuracy
        
        Args:
            user_id: User ID
        
        Returns:
            Comprehensive accuracy metrics
        """
        logger.info(f"Calculating practice accuracy for user {user_id}")
        
        # Overall accuracy
        total_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct.isnot(None)
        )
        total_attempts = (await self.db.execute(total_stmt)).scalar() or 0
        
        if total_attempts == 0:
            return {
                "overall_accuracy": None,
                "total_attempts": 0,
                "correct_attempts": 0,
                "by_difficulty": {},
                "recent_accuracy": None,
                "trend": "insufficient_data"
            }
        
        correct_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct == True
        )
        correct_attempts = (await self.db.execute(correct_stmt)).scalar() or 0
        
        overall_accuracy = round((correct_attempts / total_attempts) * 100, 2)
        
        # By difficulty
        by_difficulty = await self._calculate_accuracy_by_difficulty(user_id)
        
        # Recent accuracy (last 7 days)
        recent_accuracy = await self._calculate_recent_accuracy(user_id)
        
        # Trend analysis
        trend = self._analyze_accuracy_trend(overall_accuracy, recent_accuracy)
        
        return {
            "overall_accuracy": overall_accuracy,
            "total_attempts": total_attempts,
            "correct_attempts": correct_attempts,
            "by_difficulty": by_difficulty,
            "recent_accuracy": recent_accuracy,
            "trend": trend
        }
    
    # ================= REVISION RECOMMENDATIONS =================
    
    async def get_revision_recommendations(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Generate prioritized revision recommendations.
        
        Priority Rules:
        - HIGH: Weak accuracy (< 50%) AND low completion (< 60%)
        - MEDIUM: Average accuracy OR incomplete
        - LOW: Strong accuracy (> 75%) AND complete
        - NONE: Perfect performance
        
        Args:
            user_id: User ID
        
        Returns:
            List of subjects with revision priority
        """
        logger.info(f"Generating revision recommendations for user {user_id}")
        
        strength_map = await self.get_subject_strength_map(user_id)
        
        recommendations = []
        
        for subject_data in strength_map:
            accuracy = subject_data["accuracy"]
            completion = subject_data["completion_percentage"]
            strength = subject_data["strength"]
            
            # Determine priority
            if strength == StrengthLevel.WEAK.value and completion < self.COMPLETION_LOW_THRESHOLD:
                priority = RevisionPriority.HIGH
                reason = "Low accuracy and incomplete"
            elif strength == StrengthLevel.WEAK.value:
                priority = RevisionPriority.HIGH
                reason = "Needs accuracy improvement"
            elif completion < self.COMPLETION_LOW_THRESHOLD:
                priority = RevisionPriority.MEDIUM
                reason = "Incomplete content"
            elif strength == StrengthLevel.AVERAGE.value:
                priority = RevisionPriority.MEDIUM
                reason = "Average performance"
            elif strength == StrengthLevel.STRONG.value and completion >= 90:
                priority = RevisionPriority.NONE
                reason = "Excellent performance"
            else:
                priority = RevisionPriority.LOW
                reason = "Good progress"
            
            # Calculate time investment
            time_spent = await self._calculate_subject_time_spent(
                user_id,
                subject_data["subject_id"]
            )
            
            # Detect conceptual gaps (high time + low accuracy)
            has_conceptual_gap = (
                time_spent > self.TIME_SPENT_HIGH_THRESHOLD and
                accuracy is not None and
                accuracy < self.ACCURACY_WEAK_THRESHOLD
            )
            
            recommendations.append({
                "subject_id": subject_data["subject_id"],
                "subject_title": subject_data["subject_title"],
                "priority": priority.value,
                "reason": reason,
                "completion_percentage": completion,
                "accuracy": accuracy,
                "strength": strength,
                "time_spent_seconds": time_spent,
                "has_conceptual_gap": has_conceptual_gap
            })
        
        # Sort by priority (high first)
        priority_order = {
            RevisionPriority.HIGH.value: 0,
            RevisionPriority.MEDIUM.value: 1,
            RevisionPriority.LOW.value: 2,
            RevisionPriority.NONE.value: 3
        }
        
        recommendations.sort(key=lambda x: (
            priority_order.get(x["priority"], 99),
            -x["completion_percentage"]
        ))
        
        logger.info(f"Generated {len(recommendations)} recommendations")
        return recommendations
    
    # ================= STUDY CONSISTENCY METRICS =================
    
    async def get_study_consistency_metrics(
        self,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Analyze study patterns and consistency.
        
        Metrics:
        - Days active (last 30 days)
        - Streak (consecutive days)
        - Average session time
        - Study pattern (morning/evening/irregular)
        
        Args:
            user_id: User ID
        
        Returns:
            Study consistency analysis
        """
        logger.info(f"Calculating study consistency for user {user_id}")
        
        # Get all content progress with timestamps
        progress_stmt = select(UserContentProgress).where(
            UserContentProgress.user_id == user_id
        ).order_by(UserContentProgress.last_viewed_at.desc())
        
        progress_result = await self.db.execute(progress_stmt)
        all_progress = progress_result.scalars().all()
        
        if not all_progress:
            return {
                "consistency_level": StudyConsistency.INACTIVE.value,
                "days_active_last_30": 0,
                "current_streak": 0,
                "average_session_time_minutes": 0,
                "total_time_spent_hours": 0,
                "last_activity_date": None
            }
        
        # Last activity
        last_activity = all_progress[0].last_viewed_at
        days_since_activity = (datetime.utcnow() - last_activity).days
        
        # Calculate days active in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_progress = [
            p for p in all_progress
            if p.last_viewed_at >= thirty_days_ago
        ]
        
        # Get unique days
        unique_days = set()
        for p in recent_progress:
            day_key = p.last_viewed_at.date()
            unique_days.add(day_key)
        
        days_active_last_30 = len(unique_days)
        
        # Calculate current streak
        current_streak = await self._calculate_learning_streak(user_id)
        
        # Calculate average session time
        total_time = sum(
            p.time_spent_seconds or 0
            for p in all_progress
        )
        
        avg_session_time = 0
        if all_progress:
            avg_session_time = round(total_time / len(all_progress) / 60, 1)
        
        total_hours = round(total_time / 3600, 2)
        
        # Determine consistency level
        if days_since_activity > self.INACTIVE_DAYS:
            consistency = StudyConsistency.INACTIVE
        elif days_active_last_30 >= 20 and current_streak >= 5:
            consistency = StudyConsistency.EXCELLENT
        elif days_active_last_30 >= 10:
            consistency = StudyConsistency.GOOD
        else:
            consistency = StudyConsistency.IRREGULAR
        
        return {
            "consistency_level": consistency.value,
            "days_active_last_30": days_active_last_30,
            "current_streak": current_streak,
            "average_session_time_minutes": avg_session_time,
            "total_time_spent_hours": total_hours,
            "last_activity_date": last_activity.isoformat() if last_activity else None
        }
    
    # ================= PRIVATE HELPER METHODS =================
    
    async def _calculate_overall_accuracy(
        self,
        user_id: int
    ) -> Optional[float]:
        """Calculate overall practice accuracy across all subjects"""
        total_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct.isnot(None)
        )
        total = (await self.db.execute(total_stmt)).scalar() or 0
        
        if total < self.MIN_ATTEMPTS_FOR_ACCURACY:
            return None
        
        correct_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct == True
        )
        correct = (await self.db.execute(correct_stmt)).scalar() or 0
        
        return round((correct / total) * 100, 2)
    
    async def _calculate_subject_accuracy(
        self,
        user_id: int,
        subject_id: int
    ) -> Optional[float]:
        """Calculate accuracy for specific subject"""
        # Get practice questions for subject
        modules_stmt = select(ContentModule.id).where(
            ContentModule.subject_id == subject_id,
            ContentModule.module_type == ModuleType.PRACTICE
        )
        module_ids = [row[0] for row in (await self.db.execute(modules_stmt)).fetchall()]
        
        if not module_ids:
            return None
        
        question_ids_stmt = select(PracticeQuestion.id).where(
            PracticeQuestion.module_id.in_(module_ids)
        )
        question_ids = [row[0] for row in (await self.db.execute(question_ids_stmt)).fetchall()]
        
        if not question_ids:
            return None
        
        # Count attempts
        total_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct.isnot(None)
        )
        total = (await self.db.execute(total_stmt)).scalar() or 0
        
        if total < self.MIN_ATTEMPTS_FOR_ACCURACY:
            return None
        
        correct_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.practice_question_id.in_(question_ids),
            PracticeAttempt.is_correct == True
        )
        correct = (await self.db.execute(correct_stmt)).scalar() or 0
        
        return round((correct / total) * 100, 2)
    
    async def _calculate_accuracy_by_difficulty(
        self,
        user_id: int
    ) -> Dict[str, float]:
        """Calculate accuracy broken down by difficulty level"""
        from backend.orm.practice_question import Difficulty
        
        by_difficulty = {}
        
        for difficulty in Difficulty:
            # Get questions of this difficulty
            questions_stmt = select(PracticeQuestion.id).where(
                PracticeQuestion.difficulty == difficulty
            )
            question_ids = [row[0] for row in (await self.db.execute(questions_stmt)).fetchall()]
            
            if not question_ids:
                continue
            
            # Count attempts
            total_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user_id,
                PracticeAttempt.practice_question_id.in_(question_ids),
                PracticeAttempt.is_correct.isnot(None)
            )
            total = (await self.db.execute(total_stmt)).scalar() or 0
            
            if total == 0:
                continue
            
            correct_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user_id,
                PracticeAttempt.practice_question_id.in_(question_ids),
                PracticeAttempt.is_correct == True
            )
            correct = (await self.db.execute(correct_stmt)).scalar() or 0
            
            accuracy = round((correct / total) * 100, 2)
            by_difficulty[difficulty.value] = accuracy
        
        return by_difficulty
    
    async def _calculate_recent_accuracy(
        self,
        user_id: int
    ) -> Optional[float]:
        """Calculate accuracy for recent attempts (last 7 days)"""
        recent_date = datetime.utcnow() - timedelta(days=self.RECENT_ACTIVITY_DAYS)
        
        total_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct.isnot(None),
            PracticeAttempt.attempted_at >= recent_date
        )
        total = (await self.db.execute(total_stmt)).scalar() or 0
        
        if total < self.MIN_ATTEMPTS_FOR_ACCURACY:
            return None
        
        correct_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.is_correct == True,
            PracticeAttempt.attempted_at >= recent_date
        )
        correct = (await self.db.execute(correct_stmt)).scalar() or 0
        
        return round((correct / total) * 100, 2)
    
    def _analyze_accuracy_trend(
        self,
        overall: Optional[float],
        recent: Optional[float]
    ) -> str:
        """Determine if accuracy is improving, declining, or stable"""
        if overall is None or recent is None:
            return "insufficient_data"
        
        diff = recent - overall
        
        if diff > 10:
            return "improving"
        elif diff < -10:
            return "declining"
        else:
            return "stable"
    
    async def _calculate_subject_time_spent(
        self,
        user_id: int,
        subject_id: int
    ) -> int:
        """Calculate total time spent on subject (seconds)"""
        # Get all modules for subject
        modules_stmt = select(ContentModule.id).where(
            ContentModule.subject_id == subject_id
        )
        module_ids = [row[0] for row in (await self.db.execute(modules_stmt)).fetchall()]
        
        if not module_ids:
            return 0
        
        # Get content IDs for each type
        total_time = 0
        
        # Learn content
        learn_ids_stmt = select(LearnContent.id).where(
            LearnContent.module_id.in_(module_ids)
        )
        learn_ids = [row[0] for row in (await self.db.execute(learn_ids_stmt)).fetchall()]
        
        if learn_ids:
            time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.LEARN,
                UserContentProgress.content_id.in_(learn_ids)
            )
            total_time += (await self.db.execute(time_stmt)).scalar() or 0
        
        # Case content
        case_ids_stmt = select(CaseContent.id).where(
            CaseContent.module_id.in_(module_ids)
        )
        case_ids = [row[0] for row in (await self.db.execute(case_ids_stmt)).fetchall()]
        
        if case_ids:
            time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_type == ContentType.CASE,
                UserContentProgress.content_id.in_(case_ids)
            )
            total_time += (await self.db.execute(time_stmt)).scalar() or 0
        
        # Practice attempts
        practice_ids_stmt = select(PracticeQuestion.id).where(
            PracticeQuestion.module_id.in_(module_ids)
        )
        practice_ids = [row[0] for row in (await self.db.execute(practice_ids_stmt)).fetchall()]
        
        if practice_ids:
            time_stmt = select(func.sum(PracticeAttempt.time_taken_seconds)).where(
                PracticeAttempt.user_id == user_id,
                PracticeAttempt.practice_question_id.in_(practice_ids)
            )
            total_time += (await self.db.execute(time_stmt)).scalar() or 0
        
        return total_time
    
    async def _calculate_learning_streak(
        self,
        user_id: int
    ) -> int:
        """Calculate current learning streak (consecutive days)"""
        # Get all content progress ordered by date
        progress_stmt = select(UserContentProgress).where(
            UserContentProgress.user_id == user_id
        ).order_by(UserContentProgress.last_viewed_at.desc())
        
        progress_result = await self.db.execute(progress_stmt)
        all_progress = progress_result.scalars().all()
        
        if not all_progress:
            return 0
        
        # Check if user was active today or yesterday
        today = datetime.utcnow().date()
        last_activity = all_progress[0].last_viewed_at.date()
        
        # Streak broken if no activity for 2+ days
        if (today - last_activity).days > 1:
            return 0
        
        # Count consecutive days
        streak = 1
        current_date = last_activity
        
        # Get unique activity dates
        activity_dates = set()
        for p in all_progress:
            activity_dates.add(p.last_viewed_at.date())
        
        # Count backwards
        while True:
            current_date = current_date - timedelta(days=1)
            if current_date in activity_dates:
                streak += 1
            else:
                break
        
        return streak
    
    async def _calculate_study_consistency(
        self,
        user_id: int
    ) -> StudyConsistency:
        """Determine overall study consistency level"""
        metrics = await self.get_study_consistency_metrics(user_id)
        return StudyConsistency(metrics["consistency_level"])
    
    async def _get_last_activity_time(
        self,
        user_id: int
    ) -> Optional[str]:
        """Get timestamp of last learning activity"""
        progress_stmt = select(UserContentProgress).where(
            UserContentProgress.user_id == user_id
        ).order_by(UserContentProgress.last_viewed_at.desc()).limit(1)
        
        progress_result = await self.db.execute(progress_stmt)
        last_progress = progress_result.scalar_one_or_none()
        
        if last_progress:
            return last_progress.last_viewed_at.isoformat()
        
        return None


# ================= FACTORY FUNCTION =================

def get_learning_analytics_service(db: AsyncSession) -> LearningAnalyticsService:
    """
    Factory function to create analytics service instance.
    
    Args:
        db: Database session
    
    Returns:
        LearningAnalyticsService instance
    """
    return LearningAnalyticsService(db)