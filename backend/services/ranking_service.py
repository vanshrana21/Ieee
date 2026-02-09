"""
backend/services/ranking_service.py
Phase 5E: Ranking computation, tie-break rules, and leaderboard generation
"""
import logging
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from statistics import mean, stdev
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from backend.orm.ranking import TeamRanking, RankingType, RankStatus, Leaderboard, WinnerSelection, TieBreakRule
from backend.orm.scoring import JudgeScore, EvaluationStatus
from backend.orm.team import Team
from backend.orm.competition import Competition, CompetitionRound

logger = logging.getLogger(__name__)


class RankingService:
    """
    Phase 5E: Service for computing team rankings from judge scores.
    Handles aggregation, tie-breaking, and leaderboard generation.
    """
    
    # Default tie-break order (criterion priority)
    DEFAULT_TIE_BREAK_ORDER = [
        "legal_reasoning_score",
        "issue_framing_score", 
        "use_of_authority_score",
        "structure_clarity_score",
        "oral_advocacy_score",
        "responsiveness_score"
    ]
    
    @staticmethod
    async def compute_team_rankings(
        competition_id: int,
        ranking_type: RankingType,
        round_id: Optional[int] = None,
        db: AsyncSession = None,
        computed_by: int = 0  # 0 = system
    ) -> List[TeamRanking]:
        """
        Phase 5E: Compute rankings for all teams in a competition.
        Aggregates judge scores and applies tie-break rules.
        """
        logger.info(f"Computing rankings for competition {competition_id}, type {ranking_type.value}")
        
        # Get all teams in competition
        teams_result = await db.execute(
            select(Team).where(Team.competition_id == competition_id)
        )
        teams = teams_result.scalars().all()
        
        if not teams:
            logger.warning(f"No teams found for competition {competition_id}")
            return []
        
        # Get all published judge scores for this competition
        scores_query = select(JudgeScore).where(
            and_(
                JudgeScore.competition_id == competition_id,
                JudgeScore.is_published == True,
                JudgeScore.is_final == True
            )
        )
        
        if round_id:
            scores_query = scores_query.where(JudgeScore.slot_id.in_(
                select(SubmissionSlot.id).where(SubmissionSlot.round_id == round_id)
            ))
        
        scores_result = await db.execute(scores_query)
        all_scores = scores_result.scalars().all()
        
        # Group scores by team
        team_scores = defaultdict(list)
        for score in all_scores:
            team_scores[score.team_id].append(score)
        
        # Compute aggregated scores for each team
        team_aggregates = []
        for team in teams:
            scores = team_scores.get(team.id, [])
            
            if not scores:
                # Team has no scores yet
                aggregate = {
                    "team_id": team.id,
                    "has_scores": False,
                    "total_score": 0,
                    "normalized_score": 0
                }
            else:
                # Aggregate scores across all judges
                aggregate = RankingService._aggregate_scores(team.id, scores)
                aggregate["has_scores"] = True
            
            team_aggregates.append(aggregate)
        
        # Sort by total score (descending)
        team_aggregates.sort(key=lambda x: x.get("normalized_score", 0), reverse=True)
        
        # Apply tie-breaking
        ranked_teams = await RankingService._apply_tie_breaking(
            competition_id, team_aggregates, db
        )
        
        # Create/update TeamRanking records
        rankings = []
        current_rank = 1
        
        for i, team_data in enumerate(ranked_teams):
            # Check for ties
            is_tied = team_data.get("is_tied", False)
            
            # Determine actual rank
            if i > 0 and not is_tied:
                # If previous team was tied with others, skip ranks accordingly
                prev_team = ranked_teams[i-1]
                if prev_team.get("is_tied"):
                    # Find how many teams were tied at previous rank
                    tied_count = sum(1 for t in ranked_teams[:i] if t.get("rank") == prev_team.get("rank"))
                    current_rank = prev_team.get("rank", 1) + tied_count
                else:
                    current_rank = i + 1
            elif not is_tied:
                current_rank = i + 1
            
            team_data["rank"] = current_rank
            
            # Check for existing ranking
            existing_result = await db.execute(
                select(TeamRanking).where(
                    and_(
                        TeamRanking.competition_id == competition_id,
                        TeamRanking.team_id == team_data["team_id"],
                        TeamRanking.ranking_type == ranking_type
                    )
                )
            )
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                # Update existing
                existing.rank = current_rank
                existing.total_score = team_data.get("total_score")
                existing.normalized_score = team_data.get("normalized_score")
                existing.issue_framing_avg = team_data.get("issue_framing_avg")
                existing.legal_reasoning_avg = team_data.get("legal_reasoning_avg")
                existing.use_of_authority_avg = team_data.get("use_of_authority_avg")
                existing.structure_clarity_avg = team_data.get("structure_clarity_avg")
                existing.oral_advocacy_avg = team_data.get("oral_advocacy_avg")
                existing.responsiveness_avg = team_data.get("responsiveness_avg")
                existing.is_tied = is_tied
                existing.tied_with_team_ids = team_data.get("tied_with", [])
                existing.tie_break_reason = team_data.get("tie_break_reason")
                existing.tie_break_applied = team_data.get("tie_break_applied")
                existing.computed_at = datetime.utcnow()
                existing.computed_by = computed_by
                
                ranking = existing
            else:
                # Create new
                ranking = TeamRanking(
                    institution_id=team.institution_id,
                    competition_id=competition_id,
                    round_id=round_id,
                    team_id=team_data["team_id"],
                    ranking_type=ranking_type,
                    rank=current_rank,
                    total_score=team_data.get("total_score"),
                    normalized_score=team_data.get("normalized_score"),
                    issue_framing_avg=team_data.get("issue_framing_avg"),
                    legal_reasoning_avg=team_data.get("legal_reasoning_avg"),
                    use_of_authority_avg=team_data.get("use_of_authority_avg"),
                    structure_clarity_avg=team_data.get("structure_clarity_avg"),
                    oral_advocacy_avg=team_data.get("oral_advocacy_avg"),
                    responsiveness_avg=team_data.get("responsiveness_avg"),
                    is_tied=is_tied,
                    tied_with_team_ids=team_data.get("tied_with", []),
                    tie_break_reason=team_data.get("tie_break_reason"),
                    tie_break_applied=team_data.get("tie_break_applied"),
                    status=RankStatus.DRAFT,
                    is_published=False,
                    computed_at=datetime.utcnow(),
                    computed_by=computed_by
                )
                db.add(ranking)
            
            rankings.append(ranking)
        
        await db.commit()
        
        logger.info(f"Rankings computed: {len(rankings)} teams ranked")
        return rankings
    
    @staticmethod
    def _aggregate_scores(team_id: int, scores: List[JudgeScore]) -> Dict:
        """
        Aggregate scores from multiple judges for a single team.
        """
        # Collect all criterion scores
        criterion_scores = {
            "issue_framing": [],
            "legal_reasoning": [],
            "use_of_authority": [],
            "structure_clarity": [],
            "oral_advocacy": [],
            "responsiveness": []
        }
        
        total_scores = []
        
        for score in scores:
            if score.issue_framing_score is not None:
                criterion_scores["issue_framing"].append(score.issue_framing_score)
            if score.legal_reasoning_score is not None:
                criterion_scores["legal_reasoning"].append(score.legal_reasoning_score)
            if score.use_of_authority_score is not None:
                criterion_scores["use_of_authority"].append(score.use_of_authority_score)
            if score.structure_clarity_score is not None:
                criterion_scores["structure_clarity"].append(score.structure_clarity_score)
            if score.oral_advocacy_score is not None:
                criterion_scores["oral_advocacy"].append(score.oral_advocacy_score)
            if score.responsiveness_score is not None:
                criterion_scores["responsiveness"].append(score.responsiveness_score)
            
            if score.total_score is not None:
                total_scores.append(score.total_score)
        
        # Calculate averages
        aggregate = {
            "team_id": team_id,
            "judge_count": len(scores),
            "issue_framing_avg": mean(criterion_scores["issue_framing"]) if criterion_scores["issue_framing"] else None,
            "legal_reasoning_avg": mean(criterion_scores["legal_reasoning"]) if criterion_scores["legal_reasoning"] else None,
            "use_of_authority_avg": mean(criterion_scores["use_of_authority"]) if criterion_scores["use_of_authority"] else None,
            "structure_clarity_avg": mean(criterion_scores["structure_clarity"]) if criterion_scores["structure_clarity"] else None,
            "oral_advocacy_avg": mean(criterion_scores["oral_advocacy"]) if criterion_scores["oral_advocacy"] else None,
            "responsiveness_avg": mean(criterion_scores["responsiveness"]) if criterion_scores["responsiveness"] else None,
            "total_score": mean(total_scores) if total_scores else 0,
            "raw_score": sum(total_scores) if total_scores else 0
        }
        
        # Calculate normalized score (0-100)
        # Max possible per judge = 60 (6 criteria × 10)
        # Normalized = (average_total / 60) × 100
        if aggregate["total_score"]:
            aggregate["normalized_score"] = (aggregate["total_score"] / 60) * 100
        else:
            aggregate["normalized_score"] = 0
        
        return aggregate
    
    @staticmethod
    async def _apply_tie_breaking(
        competition_id: int,
        team_aggregates: List[Dict],
        db: AsyncSession
    ) -> List[Dict]:
        """
        Phase 5E: Apply tie-break rules when teams have equal scores.
        """
        # Get custom tie-break rules for competition
        rules_result = await db.execute(
            select(TieBreakRule).where(
                and_(
                    TieBreakRule.competition_id == competition_id,
                    TieBreakRule.is_active == True
                )
            ).order_by(TieBreakRule.rule_order)
        )
        custom_rules = rules_result.scalars().all()
        
        # Group teams by score for tie detection
        score_groups = defaultdict(list)
        for team in team_aggregates:
            # Round to 2 decimal places for comparison
            score_key = round(team.get("normalized_score", 0), 2)
            score_groups[score_key].append(team)
        
        # Process ties
        for score, tied_teams in score_groups.items():
            if len(tied_teams) > 1:
                # We have a tie!
                tied_team_ids = [t["team_id"] for t in tied_teams]
                
                # Try to break tie using rules
                broken_teams = await RankingService._break_tie(
                    tied_teams, custom_rules, db
                )
                
                # Mark all as tied initially
                for team in tied_teams:
                    team["is_tied"] = True
                    team["tied_with"] = tied_team_ids
                
                # Update with break results
                if broken_teams:
                    for i, team in enumerate(broken_teams):
                        team["tie_rank"] = i + 1
                        if i == 0:
                            team["tie_break_reason"] = "Won tie-break"
                            team["tie_break_applied"] = custom_rules[0].rule_name if custom_rules else "criterion_comparison"
                        else:
                            team["tie_break_reason"] = f"Lost tie-break at position {i+1}"
        
        # Sort by score, then by tie_rank if present
        team_aggregates.sort(key=lambda x: (
            x.get("normalized_score", 0),
            -x.get("tie_rank", 1)  # Higher tie_rank = lower actual rank
        ), reverse=True)
        
        return team_aggregates
    
    @staticmethod
    async def _break_tie(
        tied_teams: List[Dict],
        custom_rules: List[TieBreakRule],
        db: AsyncSession
    ) -> List[Dict]:
        """
        Break a tie between teams using available rules.
        Returns teams sorted by tie-break result.
        """
        if not custom_rules:
            # Use default criterion comparison
            custom_rules = [
                TieBreakRule(
                    rule_name=f"higher_{crit}",
                    criterion=crit,
                    comparison="higher",
                    rule_order=i+1
                )
                for i, crit in enumerate(RankingService.DEFAULT_TIE_BREAK_ORDER)
            ]
        
        # Try each rule
        remaining_teams = tied_teams.copy()
        result_order = []
        
        for rule in custom_rules:
            if len(remaining_teams) <= 1:
                break
            
            # Sort by this criterion
            if rule.comparison == "higher":
                remaining_teams.sort(
                    key=lambda x: x.get(f"{rule.criterion}_avg", 0),
                    reverse=True
                )
            else:
                remaining_teams.sort(
                    key=lambda x: x.get(f"{rule.criterion}_avg", 0)
                )
            
            # Find best score
            best_score = remaining_teams[0].get(f"{rule.criterion}_avg", 0)
            
            # Teams with best score win this tie-break
            winners = [t for t in remaining_teams if t.get(f"{rule.criterion}_avg", 0) == best_score]
            losers = [t for t in remaining_teams if t.get(f"{rule.criterion}_avg", 0) != best_score]
            
            # Add losers to result (they rank lower)
            result_order.extend(losers)
            
            # Continue with winners for next rule
            remaining_teams = winners
        
        # Add remaining teams (still tied after all rules)
        result_order.extend(remaining_teams)
        
        return result_order
    
    @staticmethod
    async def generate_leaderboard(
        competition_id: int,
        ranking_type: RankingType,
        db: AsyncSession,
        title: str = None,
        description: str = None
    ) -> Leaderboard:
        """
        Phase 5E: Generate a leaderboard view for a competition.
        """
        # Get rankings
        rankings_result = await db.execute(
            select(TeamRanking).where(
                and_(
                    TeamRanking.competition_id == competition_id,
                    TeamRanking.ranking_type == ranking_type,
                    TeamRanking.is_published == True
                )
            ).order_by(TeamRanking.rank)
        )
        rankings = rankings_result.scalars().all()
        
        if not rankings:
            logger.warning(f"No published rankings found for leaderboard")
            return None
        
        # Build entries
        entries = []
        for r in rankings:
            entry = {
                "rank": r.rank,
                "rank_display": r.get_rank_display(),
                "team_id": r.team_id,
                "total_score": round(r.total_score, 2) if r.total_score else None,
                "normalized_score": round(r.normalized_score, 1) if r.normalized_score else None,
                "medal": r.medal,
                "is_tied": r.is_tied
            }
            entries.append(entry)
        
        # Get competition for title
        comp_result = await db.execute(
            select(Competition).where(Competition.id == competition_id)
        )
        competition = comp_result.scalar_one_or_none()
        
        if not title:
            title = f"{competition.title} - {ranking_type.value.title()} Rankings"
        
        # Check for existing leaderboard
        existing_result = await db.execute(
            select(Leaderboard).where(
                and_(
                    Leaderboard.competition_id == competition_id,
                    Leaderboard.ranking_type == ranking_type
                )
            )
        )
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            # Update
            existing.entries = entries
            existing.last_computed_at = datetime.utcnow()
            existing.title = title
            existing.description = description
            leaderboard = existing
        else:
            # Create new
            leaderboard = Leaderboard(
                institution_id=competition.institution_id,
                competition_id=competition_id,
                ranking_type=ranking_type,
                title=title,
                description=description,
                entries=entries,
                last_computed_at=datetime.utcnow(),
                is_published=False
            )
            db.add(leaderboard)
        
        await db.commit()
        await db.refresh(leaderboard)
        
        logger.info(f"Leaderboard generated: {len(entries)} entries")
        return leaderboard
    
    @staticmethod
    async def select_winners(
        competition_id: int,
        round_id: Optional[int],
        db: AsyncSession,
        selected_by: int
    ) -> List[WinnerSelection]:
        """
        Phase 5E: Select official winners based on rankings.
        """
        # Get top 3 rankings
        rankings_result = await db.execute(
            select(TeamRanking).where(
                and_(
                    TeamRanking.competition_id == competition_id,
                    TeamRanking.round_id == round_id,
                    TeamRanking.is_published == True,
                    TeamRanking.rank <= 3
                )
            ).order_by(TeamRanking.rank)
        )
        top_rankings = rankings_result.scalars().all()
        
        winners = []
        medals = ["gold", "silver", "bronze"]
        titles = ["Winner", "Runner-up", "Third Place"]
        
        for i, ranking in enumerate(top_rankings[:3]):
            # Check for existing winner selection
            existing_result = await db.execute(
                select(WinnerSelection).where(
                    and_(
                        WinnerSelection.competition_id == competition_id,
                        WinnerSelection.round_id == round_id,
                        WinnerSelection.team_id == ranking.team_id
                    )
                )
            )
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                # Update
                existing.rank = ranking.rank
                existing.title = titles[i] if i < len(titles) else f"{ranking.get_rank_display()} Place"
                existing.medal = medals[i] if i < len(medals) else None
                existing.is_official = True
                existing.selected_by = selected_by
                winner = existing
            else:
                # Create new
                winner = WinnerSelection(
                    institution_id=ranking.institution_id,
                    competition_id=competition_id,
                    round_id=round_id,
                    team_id=ranking.team_id,
                    rank=ranking.rank,
                    title=titles[i] if i < len(titles) else f"{ranking.get_rank_display()} Place",
                    medal=medals[i] if i < len(medals) else None,
                    selection_method="ranking",
                    selected_by=selected_by,
                    is_official=True,
                    selected_at=datetime.utcnow()
                )
                db.add(winner)
            
            winners.append(winner)
            
            # Update team ranking with medal info
            ranking.medal = medals[i] if i < len(medals) else None
            if i == 0:
                ranking.is_winner = True
            elif i == 1:
                ranking.is_runner_up = True
            elif i == 2:
                ranking.is_semifinalist = True
        
        await db.commit()
        
        logger.info(f"Winners selected: {len(winners)} for competition {competition_id}")
        return winners
