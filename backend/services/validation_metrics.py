"""
backend/services/validation_metrics.py
Phase 3: Validation Metrics Tracking

Track session completion rate and feedback relevance for student validation.
In-memory storage for MVP (resets on server restart).
"""
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationMetrics:
    """
    Track validation metrics for Phase 3 student testing.
    
    Metrics stored in memory only (dict) - resets on server restart.
    """
    
    def __init__(self):
        """Initialize in-memory metrics storage."""
        self.sessions: Dict[str, dict] = {}  # session_id -> session data
        self.feedback_ratings: List[dict] = []  # student feedback ratings
        
    def track_session_completion(
        self, 
        session_id: str, 
        turns_completed: int, 
        max_turns: int = 3
    ):
        """
        Track session completion progress.
        
        Args:
            session_id: Unique session identifier
            turns_completed: Number of turns completed (0-3)
            max_turns: Maximum turns allowed (default 3)
        """
        self.sessions[session_id] = {
            "turns_completed": turns_completed,
            "max_turns": max_turns,
            "completed": turns_completed >= max_turns,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Session {session_id}: {turns_completed}/{max_turns} turns completed")
        
    def track_feedback_relevance(self, session_id: str, student_rating: int):
        """
        Track student feedback relevance rating.
        
        Args:
            session_id: Session that received feedback
            student_rating: 1-5 scale from student survey (1=poor, 5=excellent)
        """
        self.feedback_ratings.append({
            "session_id": session_id,
            "rating": student_rating,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Feedback rating for {session_id}: {student_rating}/5")
    
    def calculate_completion_rate(self) -> float:
        """
        Calculate percentage of sessions with 3/3 turns completed.
        
        Returns:
            Completion rate as percentage (0-100)
        """
        if not self.sessions:
            return 0.0
        
        completed = sum(1 for s in self.sessions.values() if s["completed"])
        total = len(self.sessions)
        
        rate = (completed / total) * 100
        logger.info(f"Completion rate: {completed}/{total} = {rate:.1f}%")
        return rate
    
    def calculate_avg_feedback_rating(self) -> float:
        """
        Calculate average feedback relevance score.
        
        Returns:
            Average rating (1-5 scale), or 0 if no ratings
        """
        if not self.feedback_ratings:
            return 0.0
        
        avg = sum(r["rating"] for r in self.feedback_ratings) / len(self.feedback_ratings)
        return round(avg, 2)
    
    def export_validation_report(self) -> dict:
        """
        Export validation summary for Phase 3 decision gate.
        
        Returns:
            Dict with completion rate, feedback scores, and decision recommendation
        """
        completion_rate = self.calculate_completion_rate()
        avg_rating = self.calculate_avg_feedback_rating()
        total_sessions = len(self.sessions)
        total_ratings = len(self.feedback_ratings)
        
        # Decision gate: proceed to Phase 4 if ≥60% completion
        should_proceed = completion_rate >= 60
        
        report = {
            "phase": "Phase 3 Validation",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "total_sessions": total_sessions,
                "completion_rate_percent": round(completion_rate, 1),
                "sessions_completed_3_turns": sum(1 for s in self.sessions.values() if s["completed"]),
                "avg_feedback_rating": avg_rating,
                "total_feedback_ratings": total_ratings
            },
            "decision_gate": {
                "threshold": "60% completion rate",
                "actual": f"{completion_rate:.1f}%",
                "recommendation": "PROCEED to Phase 4" if should_proceed else "ITERATE and retest",
                "should_proceed": should_proceed
            },
            "all_sessions": self.sessions,
            "all_ratings": self.feedback_ratings
        }
        
        logger.info(f"Validation report: {report['decision_gate']['recommendation']}")
        return report
    
    def reset(self):
        """Reset all metrics (for testing)."""
        self.sessions = {}
        self.feedback_ratings = []
        logger.info("Validation metrics reset")


# Global instance for easy import
validation_metrics = ValidationMetrics()
