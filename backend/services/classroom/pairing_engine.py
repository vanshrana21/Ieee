"""
Pairing Engine - Phase 7
Intelligent student pairing for classroom moot court rounds.
Supports random, manual, skill-based, and AI-fallback modes.
"""
import random
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.classroom_session import ClassroomSession, ParticipantRole
from backend.orm.classroom_participant import ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound, PairingMode
from backend.orm.user import User
from backend.state_machines.round_state import RoundStateMachine

logger = logging.getLogger(__name__)


@dataclass
class Student:
    """Student representation for pairing algorithms."""
    user_id: int
    name: str
    skill_rating: Optional[float] = None
    institution_id: Optional[int] = None
    win_rate: Optional[float] = None
    previous_partners: List[int] = None
    
    def __post_init__(self):
        if self.previous_partners is None:
            self.previous_partners = []


@dataclass
class RoundPair:
    """A pairing of two students for a round."""
    petitioner: Student
    respondent: Student
    judge_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "petitioner_id": self.petitioner.user_id,
            "respondent_id": self.respondent.user_id,
            "judge_id": self.judge_id,
            "skill_delta": abs(
                (self.petitioner.skill_rating or 0) - 
                (self.respondent.skill_rating or 0)
            )
        }


class PairingEngine:
    """
    Intelligent pairing engine for classroom moot court.
    
    Supports multiple pairing strategies with fairness optimization
    and duplicate pairing prevention.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def pair_participants(
        self,
        session_id: int,
        mode: PairingMode,
        manual_pairs: Optional[List[Dict]] = None,
        avoid_duplicates: bool = True
    ) -> List[RoundPair]:
        """
        Main entry point for pairing participants.
        
        Args:
            session_id: Classroom session ID
            mode: Pairing strategy (random, manual, skill, ai_fallback)
            manual_pairs: Pre-defined pairs (for manual mode)
            avoid_duplicates: Try to avoid previous pairings
            
        Returns:
            List of RoundPair objects
        """
        # Get approved participants
        students = await self._get_session_students(session_id)
        
        if len(students) < 2:
            logger.warning(f"Not enough students ({len(students)}) for pairing in session {session_id}")
            return []
        
        logger.info(f"Pairing {len(students)} students in mode {mode.value} for session {session_id}")
        
        if mode == PairingMode.RANDOM:
            return await self._random_pairing(students, session_id, avoid_duplicates)
        elif mode == PairingMode.MANUAL:
            return await self._manual_pairing(students, manual_pairs)
        elif mode == PairingMode.SKILL:
            return await self._skill_based_pairing(students, session_id, avoid_duplicates)
        elif mode == PairingMode.AI_FALLBACK:
            return await self._ai_fallback_pairing(students, session_id)
        else:
            raise ValueError(f"Unknown pairing mode: {mode}")
    
    async def _get_session_students(self, session_id: int) -> List[Student]:
        """Fetch and prepare student data for pairing."""
        result = await self.db.execute(
            select(ClassroomParticipant, User)
            .join(User, ClassroomParticipant.user_id == User.id)
            .where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.approved == True,
                ClassroomParticipant.is_active == True,
                ClassroomParticipant.role == ParticipantRole.STUDENT.value
            )
        )
        
        students = []
        rows = result.all()
        
        for participant, user in rows:
            # Get user's skill rating if available
            skill_rating = getattr(user, 'skill_rating', None)
            
            # Get previous opponents for this user in this session
            previous = await self._get_previous_opponents(session_id, user.id)
            
            student = Student(
                user_id=user.id,
                name=user.full_name or user.email,
                skill_rating=skill_rating,
                institution_id=user.institution_id,
                win_rate=getattr(user, 'win_rate', None),
                previous_partners=previous
            )
            students.append(student)
        
        return students
    
    async def _get_previous_opponents(self, session_id: int, user_id: int) -> List[int]:
        """Get list of previous opponents for a student in this session."""
        # Query rounds where this user was petitioner or respondent
        petitioner_query = select(ClassroomRound.respondent_id).where(
            ClassroomRound.session_id == session_id,
            ClassroomRound.petitioner_id == user_id
        )
        
        respondent_query = select(ClassroomRound.petitioner_id).where(
            ClassroomRound.session_id == session_id,
            ClassroomRound.respondent_id == user_id
        )
        
        petitioner_result = await self.db.execute(petitioner_query)
        respondent_result = await self.db.execute(respondent_query)
        
        opponents = list(petitioner_result.scalars().all()) + list(respondent_result.scalars().all())
        return opponents
    
    async def _random_pairing(
        self, 
        students: List[Student], 
        session_id: int,
        avoid_duplicates: bool
    ) -> List[RoundPair]:
        """
        Random pairing strategy.
        
        Shuffles students and pairs sequentially. Optionally
        avoids previous pairings by retrying shuffle.
        """
        pairs = []
        available = students.copy()
        
        # Use cryptographically secure random for fairness
        randomizer = random.SystemRandom()
        
        max_retries = 10 if avoid_duplicates else 1
        
        while len(available) >= 2:
            # Shuffle available students
            randomizer.shuffle(available)
            
            # Try to find a valid pair
            pair_found = False
            
            for i in range(len(available) - 1):
                petitioner = available[i]
                respondent = available[i + 1]
                
                # Check if they've been paired before
                if avoid_duplicates:
                    if respondent.user_id in petitioner.previous_partners:
                        continue
                
                # Create pair
                pair = RoundPair(
                    petitioner=petitioner,
                    respondent=respondent
                )
                pairs.append(pair)
                
                # Remove from available
                available.remove(respondent)
                available.remove(petitioner)
                pair_found = True
                break
            
            if not pair_found:
                # Couldn't find non-duplicate pair, use first two anyway
                if len(available) >= 2:
                    petitioner = available[0]
                    respondent = available[1]
                    
                    pair = RoundPair(
                        petitioner=petitioner,
                        respondent=respondent
                    )
                    pairs.append(pair)
                    
                    available = available[2:]
                break
            
            max_retries -= 1
            if max_retries <= 0:
                break
        
        # Handle odd student (assign to AI or observer)
        if available:
            logger.info(f"Odd student {available[0].user_id} will be paired with AI or assigned as observer")
        
        return pairs
    
    async def _manual_pairing(
        self, 
        students: List[Student], 
        manual_pairs: Optional[List[Dict]]
    ) -> List[RoundPair]:
        """
        Manual pairing strategy.
        
        Uses teacher-specified pairings.
        """
        if not manual_pairs:
            raise ValueError("Manual pairing requires manual_pairs list")
        
        # Create lookup for students
        student_map = {s.user_id: s for s in students}
        
        pairs = []
        
        for pair_def in manual_pairs:
            petitioner_id = pair_def.get('petitioner_id')
            respondent_id = pair_def.get('respondent_id')
            judge_id = pair_def.get('judge_id')
            
            if petitioner_id not in student_map or respondent_id not in student_map:
                logger.warning(f"Invalid manual pair: {petitioner_id} vs {respondent_id}")
                continue
            
            pair = RoundPair(
                petitioner=student_map[petitioner_id],
                respondent=student_map[respondent_id],
                judge_id=judge_id
            )
            pairs.append(pair)
        
        return pairs
    
    async def _skill_based_pairing(
        self, 
        students: List[Student], 
        session_id: int,
        avoid_duplicates: bool
    ) -> List[RoundPair]:
        """
        Skill-based pairing strategy.
        
        Pairs students with similar skill ratings (ELO-based).
        Uses a greedy algorithm to minimize skill deltas while
        avoiding duplicate pairings.
        """
        if not any(s.skill_rating for s in students):
            logger.warning("No skill ratings available, falling back to random pairing")
            return await self._random_pairing(students, session_id, avoid_duplicates)
        
        # Sort by skill rating
        sorted_students = sorted(
            students, 
            key=lambda s: s.skill_rating or 0
        )
        
        pairs = []
        used = set()
        
        for i, student in enumerate(sorted_students):
            if student.user_id in used:
                continue
            
            # Find best match (nearest skill rating, not previously paired)
            best_match = None
            best_delta = float('inf')
            
            for j, opponent in enumerate(sorted_students):
                if opponent.user_id in used or opponent.user_id == student.user_id:
                    continue
                
                # Check duplicates
                if avoid_duplicates and opponent.user_id in student.previous_partners:
                    continue
                
                # Calculate skill delta
                delta = abs(
                    (student.skill_rating or 0) - 
                    (opponent.skill_rating or 0)
                )
                
                if delta < best_delta:
                    best_delta = delta
                    best_match = opponent
            
            if best_match:
                # Determine petitioner/respondent (can randomize or use rating)
                if random.choice([True, False]):
                    pair = RoundPair(
                        petitioner=student,
                        respondent=best_match
                    )
                else:
                    pair = RoundPair(
                        petitioner=best_match,
                        respondent=student
                    )
                
                pairs.append(pair)
                used.add(student.user_id)
                used.add(best_match.user_id)
        
        return pairs
    
    async def _ai_fallback_pairing(
        self, 
        students: List[Student], 
        session_id: int
    ) -> List[RoundPair]:
        """
        AI fallback pairing strategy.
        
        Similar to random, but odd students are paired with AI opponent.
        Can also fill in for disconnected students mid-round.
        """
        pairs = []
        available = students.copy()
        
        # First, create human pairs
        while len(available) >= 2:
            random.shuffle(available)
            
            petitioner = available.pop()
            respondent = available.pop()
            
            pair = RoundPair(
                petitioner=petitioner,
                respondent=respondent
            )
            pairs.append(pair)
        
        # Handle odd student with AI
        if available:
            odd_student = available[0]
            
            # Create AI opponent placeholder
            ai_opponent = Student(
                user_id=-1,  # Sentinel for AI
                name="AI Opponent",
                skill_rating=odd_student.skill_rating  # Match skill
            )
            
            pair = RoundPair(
                petitioner=odd_student,
                respondent=ai_opponent
            )
            pairs.append(pair)
            
            logger.info(f"Paired student {odd_student.user_id} with AI opponent")
        
        return pairs
    
    async def create_rounds_from_pairs(
        self,
        session_id: int,
        pairs: List[RoundPair],
        creator_id: int = 0
    ) -> List[ClassroomRound]:
        """
        Persist pairings as ClassroomRound records.
        
        Args:
            session_id: Session ID
            pairs: List of RoundPair objects
            creator_id: User creating the rounds
            
        Returns:
            List of created ClassroomRound objects
        """
        rounds = []
        
        for i, pair in enumerate(pairs, 1):
            # Handle AI opponent
            respondent_id = pair.respondent.user_id
            respondent_is_ai = respondent_id < 0
            
            if respondent_is_ai:
                # Create AI opponent session
                # This would integrate with your AI opponent system
                respondent_id = None
            
            round_obj = await RoundStateMachine.create_round(
                db=self.db,
                session_id=session_id,
                round_number=i,
                petitioner_id=pair.petitioner.user_id,
                respondent_id=respondent_id or pair.respondent.user_id,
                judge_id=pair.judge_id,
                pairing_mode="random",  # Could track actual mode
                creator_id=creator_id
            )
            
            # Mark AI participants
            if respondent_is_ai:
                round_obj.respondent_is_ai = True
            
            rounds.append(round_obj)
        
        await self.db.flush()
        
        logger.info(f"Created {len(rounds)} rounds for session {session_id}")
        
        return rounds
    
    async def get_pairing_stats(self, session_id: int) -> Dict[str, Any]:
        """Get statistics about pairings for a session."""
        # Count participants
        participant_count = await self.db.scalar(
            select(func.count(ClassroomParticipant.id))
            .where(
                ClassroomParticipant.session_id == session_id,
                ClassroomParticipant.approved == True
            )
        )
        
        # Count rounds
        round_count = await self.db.scalar(
            select(func.count(ClassroomRound.id))
            .where(ClassroomRound.session_id == session_id)
        )
        
        # Get AI vs Human rounds
        ai_rounds = await self.db.scalar(
            select(func.count(ClassroomRound.id))
            .where(
                ClassroomRound.session_id == session_id,
                ClassroomRound.respondent_is_ai == True
            )
        )
        
        return {
            "participant_count": participant_count,
            "round_count": round_count,
            "ai_rounds": ai_rounds,
            "human_rounds": round_count - ai_rounds,
            "optimal_rounds": participant_count // 2 if participant_count else 0
        }


class PairingValidator:
    """Validation utilities for pairings."""
    
    @staticmethod
    def validate_manual_pairs(students: List[Student], pairs: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate manual pair definitions.
        
        Returns:
            (is_valid, list of error messages)
        """
        errors = []
        student_ids = {s.user_id for s in students}
        used_students = set()
        
        for i, pair in enumerate(pairs):
            petitioner_id = pair.get('petitioner_id')
            respondent_id = pair.get('respondent_id')
            
            # Check existence
            if petitioner_id not in student_ids:
                errors.append(f"Pair {i+1}: Petitioner {petitioner_id} not found in session")
            
            if respondent_id not in student_ids:
                errors.append(f"Pair {i+1}: Respondent {respondent_id} not found in session")
            
            # Check duplicates
            if petitioner_id in used_students:
                errors.append(f"Pair {i+1}: Petitioner {petitioner_id} already paired")
            
            if respondent_id in used_students:
                errors.append(f"Pair {i+1}: Respondent {respondent_id} already paired")
            
            used_students.add(petitioner_id)
            used_students.add(respondent_id)
        
        return len(errors) == 0, errors
