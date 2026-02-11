"""
backend/services/analytics_calculator.py
Phase 5: Analytics calculation service
Isolated service - NEW FILE
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import json

from backend.orm.user_skill_progress import UserSkillProgress, SkillType, get_skill_type_display
from backend.orm.cohort_benchmark import CohortBenchmark
from backend.orm.ai_judge_evaluation import AIJudgeEvaluation
from backend.orm.oral_round_score import OralRoundScore


class AnalyticsCalculator:
    """
    Calculates skill progress, weaknesses, strengths, and cohort benchmarks.
    Reads from existing tables, writes to analytics tables only.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_user_skill_progress(
        self, 
        user_id: int, 
        skill_type: SkillType,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Calculate skill progress for a user from AI evaluations and scores.
        Returns list of progress records with history.
        """
        # Default to last 90 days if no dates provided
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=90)
        
        # Query existing progress records
        result = await self.db.execute(
            select(UserSkillProgress)
            .where(
                and_(
                    UserSkillProgress.user_id == user_id,
                    UserSkillProgress.skill_type == skill_type,
                    UserSkillProgress.measurement_date >= start_date,
                    UserSkillProgress.measurement_date <= end_date
                )
            )
            .order_by(asc(UserSkillProgress.measurement_date))
        )
        records = result.scalars().all()
        
        return [record.to_dict() for record in records]
    
    async def analyze_weaknesses(self, user_id: int) -> Dict:
        """
        Analyze user weaknesses from skill progress data.
        Returns patterns of consistent errors with examples.
        """
        # Get all skill progress for user
        result = await self.db.execute(
            select(UserSkillProgress)
            .where(
                and_(
                    UserSkillProgress.user_id == user_id,
                    UserSkillProgress.weakness_flag == True
                )
            )
            .order_by(desc(UserSkillProgress.measurement_date))
        )
        weakness_records = result.scalars().all()
        
        weaknesses = []
        for record in weakness_records[:5]:  # Top 5 recent weaknesses
            weakness_data = self._generate_weakness_insight(record)
            weaknesses.append(weakness_data)
        
        # Get strengths (high scores without weakness flag)
        result = await self.db.execute(
            select(UserSkillProgress)
            .where(
                and_(
                    UserSkillProgress.user_id == user_id,
                    UserSkillProgress.score_value >= 4.0,
                    UserSkillProgress.weakness_flag == False
                )
            )
            .order_by(desc(UserSkillProgress.score_value))
        )
        strength_records = result.scalars().all()
        
        strengths = []
        for record in strength_records[:3]:  # Top 3 strengths
            strength_data = self._generate_strength_insight(record)
            strengths.append(strength_data)
        
        return {
            "user_id": user_id,
            "weaknesses": weaknesses,
            "strengths": strengths
        }
    
    def _generate_weakness_insight(self, record: UserSkillProgress) -> Dict:
        """Generate human-readable weakness insight"""
        insight_patterns = {
            SkillType.CITATION_ACCURACY: {
                "pattern": "Missing volume numbers in SCC citations",
                "example": "Cited 'Puttaswamy (2017) SCC 1' instead of '(2017) 10 SCC 1'",
                "remediation": "Always include volume number before 'SCC'"
            },
            SkillType.ETIQUETTE_COMPLIANCE: {
                "pattern": "Inconsistent formal address usage",
                "example": "Started argument without 'My Lord'",
                "remediation": "Begin every argument with 'My Lord' or 'My Lords'"
            },
            SkillType.LEGAL_REASONING: {
                "pattern": "Weak application of precedent to facts",
                "example": "Cited case but didn't apply facts of current moot",
                "remediation": "Use IRAC format: clearly distinguish Rule from Application"
            },
            SkillType.DOCTRINE_MASTERY: {
                "pattern": "Incomplete doctrine application",
                "example": "Mentioned proportionality without applying all 4 prongs",
                "remediation": "Apply all elements: legitimate aim, suitability, necessity, proportionality"
            },
            SkillType.TIME_MANAGEMENT: {
                "pattern": "Arguments exceed time limits",
                "example": "Used 12 minutes for 10-minute slot",
                "remediation": "Practice with timer. Allocate: 2min intro, 6min arguments, 2min conclusion"
            }
        }
        
        default_insight = {
            "pattern": f"Needs improvement in {get_skill_type_display(record.skill_type)}",
            "example": "Recent scores below threshold",
            "remediation": "Practice more with AI judge feedback"
        }
        
        insight = insight_patterns.get(record.skill_type, default_insight)
        
        # Calculate frequency from improvement delta if available
        frequency = "Recent pattern"
        if record.improvement_delta is not None:
            if record.improvement_delta < 0:
                frequency = f"Declining trend ({abs(record.improvement_delta):.1f} points)"
            elif record.improvement_delta > 0:
                frequency = "Improving trend"
        
        return {
            "skill_type": record.skill_type.value,
            "skill_display": get_skill_type_display(record.skill_type),
            "pattern": insight["pattern"],
            "example": insight["example"],
            "remediation": insight["remediation"],
            "frequency": frequency,
            "current_score": record.score_value
        }
    
    def _generate_strength_insight(self, record: UserSkillProgress) -> Dict:
        """Generate human-readable strength insight"""
        strength_patterns = {
            SkillType.CITATION_ACCURACY: {
                "pattern": "Consistently cites cases in correct SCC format",
                "note": "Strong grasp of legal citation standards"
            },
            SkillType.ETIQUETTE_COMPLIANCE: {
                "pattern": "Consistently uses 'My Lord' at argument start",
                "note": "Excellent courtroom etiquette"
            },
            SkillType.LEGAL_REASONING: {
                "pattern": "Clear IRAC structure in arguments",
                "note": "Strong analytical framework"
            },
            SkillType.DOCTRINE_MASTERY: {
                "pattern": "Accurate application of legal doctrines",
                "note": "Deep understanding of constitutional principles"
            },
            SkillType.TIME_MANAGEMENT: {
                "pattern": "Stays within time limits consistently",
                "note": "Good pacing and prioritization"
            }
        }
        
        default_strength = {
            "pattern": f"Strong performance in {get_skill_type_display(record.skill_type)}",
            "note": "Consistently high scores"
        }
        
        insight = strength_patterns.get(record.skill_type, default_strength)
        
        return {
            "skill_type": record.skill_type.value,
            "skill_display": get_skill_type_display(record.skill_type),
            "pattern": insight["pattern"],
            "note": insight["note"],
            "current_score": record.score_value,
            "percentile": record.percentile_rank
        }
    
    async def calculate_cohort_benchmarks(
        self,
        skill_type: SkillType,
        institution_id: Optional[int] = None,
        course_id: Optional[int] = None,
        semester: Optional[str] = None,
        measurement_period: str = "Last 30 days"
    ) -> Optional[CohortBenchmark]:
        """
        Calculate cohort benchmarks for a specific skill type.
        Returns CohortBenchmark object or None if insufficient data.
        """
        # Determine date range based on measurement period
        end_date = date.today()
        if measurement_period == "Last 7 days":
            start_date = end_date - timedelta(days=7)
        elif measurement_period == "Last 30 days":
            start_date = end_date - timedelta(days=30)
        elif measurement_period == "Current semester":
            # Assume semester is roughly 4 months
            start_date = end_date - timedelta(days=120)
        else:  # All time
            start_date = date.min
        
        # Build query with filters
        query = select(UserSkillProgress).where(
            and_(
                UserSkillProgress.skill_type == skill_type,
                UserSkillProgress.measurement_date >= start_date,
                UserSkillProgress.measurement_date <= end_date
            )
        )
        
        # Note: Institution/course filters would require joining to users table
        # For now, we calculate on all users and filter post-query if needed
        
        result = await self.db.execute(query)
        records = result.scalars().all()
        
        # Filter by institution/course if specified (post-query for now)
        if institution_id or course_id:
            # This would need proper joins in production
            # For this implementation, we'll use all records
            pass
        
        if len(records) < 5:
            return None  # Insufficient data for meaningful benchmark
        
        # Calculate statistics
        scores = [r.score_value for r in records]
        scores.sort()
        
        n = len(scores)
        percentile_25 = scores[int(n * 0.25)]
        percentile_50 = scores[int(n * 0.50)]  # Median
        percentile_75 = scores[int(n * 0.75)]
        mean_score = sum(scores) / n
        
        # Create or update benchmark
        benchmark = CohortBenchmark(
            skill_type=skill_type,
            percentile_25=percentile_25,
            percentile_50=percentile_50,
            percentile_75=percentile_75,
            mean_score=mean_score,
            sample_size=n,
            measurement_period=measurement_period,
            institution_id=institution_id,
            course_id=course_id,
            semester=semester
        )
        
        return benchmark
    
    async def generate_personalized_insights(self, user_id: int) -> List[str]:
        """
        Generate personalized insights for a user based on their skill data.
        Returns list of insight strings.
        """
        insights = []
        
        # Get recent progress data
        thirty_days_ago = date.today() - timedelta(days=30)
        result = await self.db.execute(
            select(UserSkillProgress)
            .where(
                and_(
                    UserSkillProgress.user_id == user_id,
                    UserSkillProgress.measurement_date >= thirty_days_ago
                )
            )
            .order_by(desc(UserSkillProgress.measurement_date))
        )
        recent_records = result.scalars().all()
        
        if not recent_records:
            return ["Start practicing to see your skill analytics!"]
        
        # Check for improvements
        for record in recent_records:
            if record.improvement_delta and record.improvement_delta > 0.5:
                skill_name = get_skill_type_display(record.skill_type)
                improvement_pct = int((record.improvement_delta / record.score_value) * 100) if record.score_value > 0 else 0
                insights.append(f"Your {skill_name.lower()} improved {improvement_pct}% this month!")
        
        # Check for high performers
        high_scores = [r for r in recent_records if r.score_value >= 4.0 and r.percentile_rank >= 80]
        if high_scores:
            skill_names = [get_skill_type_display(r.skill_type).lower() for r in high_scores[:2]]
            insights.append(f"You're in the top 20% for {', '.join(skill_names)}. Excellent work!")
        
        # Check for areas needing attention
        low_scores = [r for r in recent_records if r.score_value < 2.5]
        if low_scores:
            skill_names = [get_skill_type_display(r.skill_type) for r in low_scores[:2]]
            insights.append(f"Focus on improving: {', '.join(skill_names)}")
        
        # Citation-specific insight
        citation_record = next((r for r in recent_records if r.skill_type == SkillType.CITATION_ACCURACY), None)
        if citation_record:
            if citation_record.score_value >= 4.0:
                insights.append("You consistently cite cases correctly in written submissions.")
            elif citation_record.score_value < 3.0:
                insights.append("Practice SCC citation format: (Year) Volume SCC Page")
        
        # Etiquette insight
        etiquette_record = next((r for r in recent_records if r.skill_type == SkillType.ETIQUETTE_COMPLIANCE), None)
        if etiquette_record and etiquette_record.score_value >= 4.5:
            insights.append("Perfect courtroom etiquette! You always address the bench properly.")
        
        if not insights:
            insights.append("Keep practicing! Your skills are developing steadily.")
        
        return insights[:5]  # Max 5 insights
    
    async def calculate_competition_analytics(self, competition_id: int) -> Dict:
        """
        Calculate admin-level competition analytics.
        Returns participation metrics, top cases, doctrine mastery, etc.
        """
        # This would aggregate data from multiple tables
        # For now, return mock structure that would be populated with real queries
        
        return {
            "competition_id": competition_id,
            "participation_rate": "87%",
            "avg_citation_score": 4.2,
            "top_cited_cases": [
                {"case": "Puttaswamy (2017) 10 SCC 1", "count": 42},
                {"case": "Maneka (1978) 1 SCC 248", "count": 28},
                {"case": "Kesavananda (1973) 4 SCC 225", "count": 24},
                {"case": "Navtej (2018) 10 SCC 1", "count": 19}
            ],
            "doctrine_mastery": {
                "proportionality_test": "76% mastery",
                "basic_structure": "68% mastery",
                "right_to_privacy": "82% mastery",
                "reasonable_restriction": "71% mastery"
            },
            "completion_rate": "92%",
            "avg_scores_by_criteria": {
                "legal_accuracy": 4.1,
                "citation": 4.2,
                "etiquette": 4.5,
                "structure": 3.9,
                "persuasiveness": 4.0
            }
        }
