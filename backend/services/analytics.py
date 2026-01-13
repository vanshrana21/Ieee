"""
backend/services/analytics.py
Learning Analytics & Insights Generator

PHASE 8: Intelligent Learning Engine - Component 3

PURPOSE:
Generate backend-calculated metrics for dashboards:
- Overall progress summary
- Subject-level insights
- Performance trends
- Strong vs weak areas
- Time tracking

ALL DATA READ-ONLY - No database writes.
"""
import logging
from typing import Dict, List, Any, Optional
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


class LearningAnalytics:
    """
    Calculate learning analytics from existing progress data.
    
    No new database writes - pure computation.
    """
    
    # ========== OVERALL METRICS ==========
    
    @staticmethod
    async def get_overall_progress(
        user: User,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Calculate overall learning metrics.
        
        Returns:
            {
                "completion_percentage": float,
                "practice_accuracy": Optional[float],
                "total_time_spent_hours": float,
                "subjects_completed": int,
                "subjects_in_progress": int,
                "subjects_not_started": int,
                "total_practice_attempts": int,
                "total_items_completed": int
            }
        """
        logger.info(f"Calculating overall progress for user: {user.email}")
        
        if not user.course_id:
            return {
                "completion_percentage": 0.0,
                "practice_accuracy": None,
                "total_time_spent_hours": 0.0,
                "subjects_completed": 0,
                "subjects_in_progress": 0,
                "subjects_not_started": 0,
                "total_practice_attempts": 0,
                "total_items_completed": 0
            }
        
        # Get all accessible subjects
        curriculum_stmt = select(CourseCurriculum.subject_id).where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.semester_number <= user.current_semester,
            CourseCurriculum.is_active == True
        )
        accessible_subject_ids = [row[0] for row in (await db.execute(curriculum_stmt)).fetchall()]
        total_subjects = len(accessible_subject_ids)
        
        # Get subject progress records
        progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == user.id,
            SubjectProgress.subject_id.in_(accessible_subject_ids)
        )
        progress_records = (await db.execute(progress_stmt)).scalars().all()
        
        # Calculate subject counts
        subjects_completed = sum(1 for p in progress_records if p.completion_percentage >= 100)
        subjects_in_progress = sum(1 for p in progress_records if 0 < p.completion_percentage < 100)
        subjects_not_started = total_subjects - len(progress_records)
        
        # Calculate average completion
        if progress_records:
            avg_completion = sum(p.completion_percentage for p in progress_records) / len(progress_records)
        else:
            avg_completion = 0.0
        
        # Calculate total time spent
        time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
            UserContentProgress.user_id == user.id
        )
        total_seconds = (await db.execute(time_stmt)).scalar() or 0
        total_hours = round(total_seconds / 3600, 1)
        
        # Calculate overall practice accuracy
        total_attempts_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user.id,
            PracticeAttempt.is_correct.isnot(None)
        )
        total_mcq_attempts = (await db.execute(total_attempts_stmt)).scalar() or 0
        
        if total_mcq_attempts > 0:
            correct_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user.id,
                PracticeAttempt.is_correct == True
            )
            correct_attempts = (await db.execute(correct_stmt)).scalar() or 0
            practice_accuracy = round((correct_attempts / total_mcq_attempts) * 100, 2)
        else:
            practice_accuracy = None
        
        # Total completed items
        completed_items_stmt = select(func.count(UserContentProgress.id)).where(
            UserContentProgress.user_id == user.id,
            UserContentProgress.is_completed == True
        )
        total_completed = (await db.execute(completed_items_stmt)).scalar() or 0
        
        # Total practice attempts (all types)
        all_attempts_stmt = select(func.count(PracticeAttempt.id)).where(
            PracticeAttempt.user_id == user.id
        )
        total_attempts = (await db.execute(all_attempts_stmt)).scalar() or 0
        
        return {
            "completion_percentage": round(avg_completion, 2),
            "practice_accuracy": practice_accuracy,
            "total_time_spent_hours": total_hours,
            "subjects_completed": subjects_completed,
            "subjects_in_progress": subjects_in_progress,
            "subjects_not_started": subjects_not_started,
            "total_practice_attempts": total_attempts,
            "total_items_completed": total_completed
        }
    
    # ========== SUBJECT-LEVEL INSIGHTS ==========
    
    @staticmethod
    async def get_subject_insights(
        user: User,
        subject_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Generate detailed insights for a specific subject.
        
        Returns:
            {
                "subject_id": int,
                "subject_name": str,
                "status": "strong" | "moderate" | "weak" | "not_started",
                "completion": float,
                "accuracy": Optional[float],
                "time_spent_minutes": int,
                "last_activity": str,
                "weak_topics": List[str],
                "strong_topics": List[str],
                "module_breakdown": {...}
            }
        """
        logger.info(f"Calculating subject insights: subject_id={subject_id}")
        
        # Get subject details
        subject_stmt = select(Subject).where(Subject.id == subject_id)
        subject = (await db.execute(subject_stmt)).scalar_one_or_none()
        
        if not subject:
            raise ValueError(f"Subject {subject_id} not found")
        
        # Get subject progress
        progress_stmt = select(SubjectProgress).where(
            SubjectProgress.user_id == user.id,
            SubjectProgress.subject_id == subject_id
        )
        progress = (await db.execute(progress_stmt)).scalar_one_or_none()
        
        if not progress:
            return {
                "subject_id": subject_id,
                "subject_name": subject.title,
                "status": "not_started",
                "completion": 0.0,
                "accuracy": None,
                "time_spent_minutes": 0,
                "last_activity": None,
                "weak_topics": [],
                "strong_topics": [],
                "module_breakdown": {}
            }
        
        # Get modules for subject
        modules_stmt = select(ContentModule).where(
            ContentModule.subject_id == subject_id
        )
        modules = (await db.execute(modules_stmt)).scalars().all()
        
        # Calculate time spent
        module_ids = [m.id for m in modules]
        
        # Get all content IDs
        from backend.orm.learn_content import LearnContent
        from backend.orm.case_content import CaseContent
        from backend.orm.practice_question import PracticeQuestion
        
        learn_ids = []
        case_ids = []
        practice_ids = []
        
        for module in modules:
            if module.module_type == ModuleType.LEARN:
                ids_stmt = select(LearnContent.id).where(LearnContent.module_id == module.id)
                learn_ids.extend([row[0] for row in (await db.execute(ids_stmt)).fetchall()])
            elif module.module_type == ModuleType.CASES:
                ids_stmt = select(CaseContent.id).where(CaseContent.module_id == module.id)
                case_ids.extend([row[0] for row in (await db.execute(ids_stmt)).fetchall()])
            elif module.module_type == ModuleType.PRACTICE:
                ids_stmt = select(PracticeQuestion.id).where(PracticeQuestion.module_id == module.id)
                practice_ids.extend([row[0] for row in (await db.execute(ids_stmt)).fetchall()])
        
        # Calculate time spent
        time_conditions = []
        if learn_ids:
            time_conditions.append(
                and_(
                    UserContentProgress.content_type == ContentType.LEARN,
                    UserContentProgress.content_id.in_(learn_ids)
                )
            )
        if case_ids:
            time_conditions.append(
                and_(
                    UserContentProgress.content_type == ContentType.CASE,
                    UserContentProgress.content_id.in_(case_ids)
                )
            )
        if practice_ids:
            time_conditions.append(
                and_(
                    UserContentProgress.content_type == ContentType.PRACTICE,
                    UserContentProgress.content_id.in_(practice_ids)
                )
            )
        
        if time_conditions:
            from sqlalchemy import or_
            time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
                UserContentProgress.user_id == user.id,
                or_(*time_conditions)
            )
            total_seconds = (await db.execute(time_stmt)).scalar() or 0
            time_spent_minutes = round(total_seconds / 60)
        else:
            time_spent_minutes = 0
        
        # Calculate practice accuracy
        if practice_ids:
            total_mcq_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user.id,
                PracticeAttempt.practice_question_id.in_(practice_ids),
                PracticeAttempt.is_correct.isnot(None)
            )
            total_mcq = (await db.execute(total_mcq_stmt)).scalar() or 0
            
            if total_mcq > 0:
                correct_stmt = select(func.count(PracticeAttempt.id)).where(
                    PracticeAttempt.user_id == user.id,
                    PracticeAttempt.practice_question_id.in_(practice_ids),
                    PracticeAttempt.is_correct == True
                )
                correct = (await db.execute(correct_stmt)).scalar() or 0
                accuracy = round((correct / total_mcq) * 100, 2)
            else:
                accuracy = None
        else:
            accuracy = None
        
        # Determine status
        completion = progress.completion_percentage
        if completion == 0:
            status = "not_started"
        elif accuracy is not None:
            if accuracy >= 80 and completion >= 70:
                status = "strong"
            elif accuracy >= 60 and completion >= 40:
                status = "moderate"
            else:
                status = "weak"
        else:
            if completion >= 70:
                status = "strong"
            elif completion >= 40:
                status = "moderate"
            else:
                status = "weak"
        
        # TODO: Implement weak_topics and strong_topics analysis
        # Requires per-topic tracking (future enhancement)
        weak_topics = []
        strong_topics = []
        
        # Module breakdown
        module_breakdown = {}
        for module in modules:
            module_breakdown[module.module_type.value] = {
                "title": module.title,
                "status": module.status.value,
                "item_count": module.get_item_count()
            }
        
        # Format last activity
        last_activity = progress.last_activity_at.isoformat() if progress.last_activity_at else None
        
        return {
            "subject_id": subject_id,
            "subject_name": subject.title,
            "status": status,
            "completion": completion,
            "accuracy": accuracy,
            "time_spent_minutes": time_spent_minutes,
            "last_activity": last_activity,
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
            "module_breakdown": module_breakdown
        }
    
    # ========== PERFORMANCE TRENDS ==========
    
    @staticmethod
    async def get_performance_trends(
        user: User,
        db: AsyncSession,
        weeks: int = 4
    ) -> Dict[str, Any]:
        """
        Calculate weekly activity and accuracy trends.
        
        Args:
            user: Current user
            db: Database session
            weeks: Number of weeks to analyze
        
        Returns:
            {
                "weekly_activity": [...],
                "accuracy_trend": {...}
            }
        """
        logger.info(f"Calculating performance trends for user: {user.email}")
        
        # Calculate week boundaries
        today = datetime.utcnow()
        weeks_data = []
        
        for i in range(weeks):
            week_start = today - timedelta(weeks=i+1)
            week_end = today - timedelta(weeks=i)
            
            # Count attempts in this week
            attempts_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user.id,
                PracticeAttempt.attempted_at >= week_start,
                PracticeAttempt.attempted_at < week_end
            )
            attempts = (await db.execute(attempts_stmt)).scalar() or 0
            
            # Calculate accuracy for this week
            mcq_stmt = select(func.count(PracticeAttempt.id)).where(
                PracticeAttempt.user_id == user.id,
                PracticeAttempt.attempted_at >= week_start,
                PracticeAttempt.attempted_at < week_end,
                PracticeAttempt.is_correct.isnot(None)
            )
            mcq_count = (await db.execute(mcq_stmt)).scalar() or 0
            
            if mcq_count > 0:
                correct_stmt = select(func.count(PracticeAttempt.id)).where(
                    PracticeAttempt.user_id == user.id,
                    PracticeAttempt.attempted_at >= week_start,
                    PracticeAttempt.attempted_at < week_end,
                    PracticeAttempt.is_correct == True
                )
                correct = (await db.execute(correct_stmt)).scalar() or 0
                accuracy = round((correct / mcq_count) * 100, 1)
            else:
                accuracy = None
            
            # Calculate time spent (approximate from content progress)
            time_stmt = select(func.sum(UserContentProgress.time_spent_seconds)).where(
                UserContentProgress.user_id == user.id,
                UserContentProgress.last_viewed_at >= week_start,
                UserContentProgress.last_viewed_at < week_end
            )
            seconds = (await db.execute(time_stmt)).scalar() or 0
            hours = round(seconds / 3600, 1)
            
            weeks_data.append({
                "week": f"{week_start.year}-W{week_start.isocalendar()[1]:02d}",
                "hours": hours,
                "questions_attempted": attempts,
                "accuracy": accuracy
            })
        
        weeks_data.reverse()  # Oldest to newest
        
        # Calculate accuracy trend
        accuracies = [w["accuracy"] for w in weeks_data if w["accuracy"] is not None]
        if len(accuracies) >= 2:
            current_accuracy = accuracies[-1]
            previous_accuracy = accuracies[-2]
            if current_accuracy > previous_accuracy:
                direction = "improving"
            elif current_accuracy < previous_accuracy:
                direction = "declining"
            else:
                direction = "stable"
        else:
            direction = "insufficient_data"
        
        return {
            "weekly_activity": weeks_data,
            "accuracy_trend": {
                "current_week": accuracies[-1] if accuracies else None,
                "last_week": accuracies[-2] if len(accuracies) >= 2 else None,
                "direction": direction
            }
        }
    
    # ========== SUBJECT COMPARISON ==========
    
    @staticmethod
    async def get_subject_comparison(
        user: User,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Compare performance across all subjects.
        
        Returns ranked list of subjects by performance.
        """
        if not user.course_id:
            return []
        
        # Get all accessible subjects
        curriculum_stmt = select(CourseCurriculum).where(
            CourseCurriculum.course_id == user.course_id,
            CourseCurriculum.semester_number <= user.current_semester,
            CourseCurriculum.is_active == True
        ).options(joinedload(CourseCurriculum.subject))
        curriculum_items = (await db.execute(curriculum_stmt)).scalars().all()
        
        subject_scores = []
        
        for item in curriculum_items:
            subject = item.subject
            
            # Get progress
            progress_stmt = select(SubjectProgress).where(
                SubjectProgress.user_id == user.id,
                SubjectProgress.subject_id == subject.id
            )
            progress = (await db.execute(progress_stmt)).scalar_one_or_none()
            
            if not progress:
                subject_scores.append({
                    "subject_id": subject.id,
                    "subject_name": subject.title,
                    "score": 0.0,
                    "completion": 0.0,
                    "accuracy": None
                })
                continue
            
            # Get accuracy
            insights = await LearningAnalytics.get_subject_insights(user, subject.id, db)
            
            # Calculate composite score (weighted average)
            # 60% completion + 40% accuracy
            completion_score = progress.completion_percentage
            accuracy_score = insights["accuracy"] if insights["accuracy"] else 50.0
            
            composite_score = (0.6 * completion_score) + (0.4 * accuracy_score)
            
            subject_scores.append({
                "subject_id": subject.id,
                "subject_name": subject.title,
                "score": round(composite_score, 2),
                "completion": progress.completion_percentage,
                "accuracy": insights["accuracy"]
            })
        
        # Sort by score (descending)
        subject_scores.sort(key=lambda x: x["score"], reverse=True)
        
        return subject_scores