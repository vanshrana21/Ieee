"""
Phase 14 — Crash Recovery Module

Handles server restart and restoration of LIVE matches.
Should be called on application startup.
"""
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.phase14_timer_service import TimerService
from backend.services.phase14_match_service import MatchService
from backend.database import AsyncSessionLocal


logger = logging.getLogger(__name__)


class CrashRecovery:
    """
    Crash recovery for Phase 14 round engine.
    
    On server restart:
    1. Detect LIVE matches
    2. Restore timer state
    3. Resume active turns
    4. Broadcast recovery events
    """
    
    @staticmethod
    async def run_recovery() -> Dict[str, Any]:
        """
        Run crash recovery on startup.
        
        Returns:
            Recovery summary with LIVE match count
        """
        logger.info("🔧 Phase 14 Crash Recovery: Starting...")
        
        async with AsyncSessionLocal() as db:
            try:
                # Find all LIVE matches
                live_matches = await TimerService.restore_live_matches(db=db)
                
                if not live_matches:
                    logger.info("✅ Phase 14 Crash Recovery: No LIVE matches found")
                    return {
                        "recovered": 0,
                        "matches": [],
                        "status": "no_live_matches"
                    }
                
                logger.warning(f"⚠️ Phase 14 Crash Recovery: Found {len(live_matches)} LIVE matches")
                
                recovered_matches = []
                for match_data in live_matches:
                    match_id = match_data["match_id"]
                    timer_data = match_data.get("timer", {})
                    active_turn = match_data.get("active_turn")
                    
                    logger.info(f"🔄 Recovering match {match_id}")
                    
                    # Check if timer was running or paused
                    was_paused = timer_data.get("paused", True)
                    last_tick = timer_data.get("last_tick")
                    remaining_seconds = timer_data.get("remaining_seconds", 0)
                    
                    # If timer was running, calculate elapsed time since last tick
                    if not was_paused and last_tick:
                        try:
                            last_tick_time = datetime.fromisoformat(last_tick.replace('Z', '+00:00'))
                            elapsed = (datetime.utcnow() - last_tick_time).total_seconds()
                            remaining_seconds = max(0, remaining_seconds - int(elapsed))
                            
                            logger.info(f"  ⏱️ Elapsed since last tick: {elapsed:.1f}s")
                            logger.info(f"  ⏱️ Adjusted remaining: {remaining_seconds}s")
                        except Exception as e:
                            logger.error(f"  ❌ Error calculating elapsed time: {e}")
                            # Play it safe - pause the timer
                            remaining_seconds = timer_data.get("remaining_seconds", 0)
                            was_paused = True
                    
                    # If time expired during downtime, auto-complete
                    if remaining_seconds <= 0 and active_turn:
                        logger.warning(f"  ⏰ Time expired during downtime. Auto-completing turn {active_turn['id']}")
                        # Import here to avoid circular dependency
                        from sqlalchemy import select as sa_select
                        from backend.orm.phase14_round_engine import MatchSpeakerTurn, TurnStatus
                        
                        turn_result = await db.execute(
                            sa_select(MatchSpeakerTurn).where(
                                MatchSpeakerTurn.id == active_turn["id"]
                            )
                        )
                        turn = turn_result.scalar_one_or_none()
                        
                        if turn and turn.status == TurnStatus.ACTIVE.value:
                            turn.status = TurnStatus.COMPLETED.value
                            turn.ended_at = datetime.utcnow()
                            await db.commit()
                            logger.info(f"  ✅ Turn {turn.id} auto-completed")
                        
                        recovered_matches.append({
                            "match_id": match_id,
                            "status": "turn_auto_completed",
                            "turn_id": active_turn["id"],
                            "previous_remaining": timer_data.get("remaining_seconds", 0),
                            "adjusted_remaining": 0
                        })
                    else:
                        recovered_matches.append({
                            "match_id": match_id,
                            "status": "recovered",
                            "timer_paused": was_paused,
                            "remaining_seconds": remaining_seconds,
                            "active_turn": active_turn
                        })
                
                await db.commit()
                
                logger.info(f"✅ Phase 14 Crash Recovery: Recovered {len(recovered_matches)} matches")
                
                return {
                    "recovered": len(recovered_matches),
                    "matches": recovered_matches,
                    "status": "recovery_complete"
                }
                
            except Exception as e:
                logger.error(f"❌ Phase 14 Crash Recovery Failed: {e}")
                await db.rollback()
                raise


async def startup_recovery():
    """
    Convenience function to run recovery on startup.
    Call this in main.py during application startup.
    """
    try:
        result = await CrashRecovery.run_recovery()
        return result
    except Exception as e:
        logger.error(f"Crash recovery failed: {e}")
        # Don't fail startup - log and continue
        return {
            "recovered": 0,
            "matches": [],
            "status": "recovery_failed",
            "error": str(e)
        }
