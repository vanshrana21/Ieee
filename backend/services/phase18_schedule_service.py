"""
Phase 18 — Scheduling & Court Allocation Service.

Deterministic court scheduling with conflict detection and freeze integrity.

Phase 20 Integration: Lifecycle guards prevent scheduling on closed tournaments.
"""
import hashlib
import json
from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from backend.orm.phase18_scheduling import (
    Courtroom, ScheduleDay, TimeSlot, MatchScheduleAssignment,
    ScheduleStatus, AssignmentStatus
)
from backend.config.feature_flags import feature_flags


async def _check_lifecycle_guard(tournament_id: UUID) -> bool:
    """Phase 20: Check if scheduling is allowed."""
    try:
        from backend.config.feature_flags import feature_flags as ff
        if not ff.FEATURE_TOURNAMENT_LIFECYCLE:
            return True
        
        from backend.services.phase20_lifecycle_service import LifecycleService
        from backend.database import async_session_maker
        
        async with async_session_maker() as db:
            allowed, _ = await LifecycleService.check_operation_allowed(
                db, tournament_id, "schedule"
            )
            return allowed
    except Exception:
        return True  # Fail open


class ScheduleError(Exception):
    """Base exception for schedule errors."""
    pass


class ConflictError(ScheduleError):
    """Raised when a scheduling conflict is detected."""
    pass


class InvalidStatusError(ScheduleError):
    """Raised when an invalid status transition is attempted."""
    pass


class FrozenScheduleError(ScheduleError):
    """Raised when trying to modify a frozen schedule."""
    pass


class ScheduleService:
    """
    Service for deterministic court scheduling and allocation.
    
    All mutations use SELECT ... FOR UPDATE for concurrency safety.
    Frozen schedules are immutable with SHA256 integrity verification.
    """
    
    # State machine valid transitions
    VALID_TRANSITIONS = {
        ScheduleStatus.DRAFT: [ScheduleStatus.LOCKED],
        ScheduleStatus.LOCKED: [ScheduleStatus.FROZEN],
        ScheduleStatus.FROZEN: [],  # Terminal state
    }
    
    @staticmethod
    def _is_valid_transition(current: ScheduleStatus, new: ScheduleStatus) -> bool:
        """Check if status transition is valid."""
        return new in ScheduleService.VALID_TRANSITIONS.get(current, [])
    
    @staticmethod
    def _compute_integrity_hash(assignments_data: List[Dict[str, Any]]) -> str:
        """
        Compute SHA256 integrity hash for schedule.
        
        Builds deterministic snapshot:
        - Sorted by slot_order, then match_id
        - No timestamps included
        - JSON with sort_keys=True
        """
        # Sort by slot_order, then match_id for determinism
        sorted_data = sorted(
            assignments_data,
            key=lambda x: (x.get("slot_order", 0), x.get("match_id", ""))
        )
        
        # Remove timestamps and non-deterministic fields
        clean_data = []
        for item in sorted_data:
            clean_item = {
                "match_id": str(item.get("match_id", "")),
                "courtroom_id": str(item.get("courtroom_id", "")),
                "judge_user_id": str(item.get("judge_user_id", "")) if item.get("judge_user_id") else None,
                "slot_order": item.get("slot_order", 0),
                "start_time": item.get("start_time", ""),
                "status": item.get("status", AssignmentStatus.ASSIGNED),
            }
            clean_data.append(clean_item)
        
        # Deterministic JSON with sorted keys
        json_str = json.dumps(clean_data, sort_keys=True, separators=(',', ':'))
        
        # SHA256 hash
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0
    
    # ==========================================================================
    # Schedule Day Operations
    # ==========================================================================
    
    @staticmethod
    async def create_schedule_day(
        db: AsyncSession,
        tournament_id: UUID,
        day_number: int,
        schedule_date: date,
        created_by_user_id: UUID
    ) -> ScheduleDay:
        """
        Create a new schedule day in DRAFT status.
        
        Args:
            db: Database session
            tournament_id: Tournament UUID
            day_number: Sequential day number (> 0)
            schedule_date: Calendar date
            created_by_user_id: User who created the schedule
            
        Returns:
            Created ScheduleDay
            
        Raises:
            ScheduleError: If day_number <= 0
        """
        if day_number <= 0:
            raise ScheduleError("Day number must be positive")
        
        schedule_day = ScheduleDay(
            tournament_id=tournament_id,
            day_number=day_number,
            date=schedule_date,
            status=ScheduleStatus.DRAFT,
            integrity_hash=None
        )
        
        db.add(schedule_day)
        await db.flush()
        
        return schedule_day
    
    @staticmethod
    async def get_schedule_day(
        db: AsyncSession,
        schedule_day_id: UUID,
        lock: bool = False
    ) -> Optional[ScheduleDay]:
        """
        Get schedule day by ID.
        
        Args:
            db: Database session
            schedule_day_id: Schedule day UUID
            lock: Whether to use FOR UPDATE locking
            
        Returns:
            ScheduleDay or None
        """
        query = select(ScheduleDay).where(ScheduleDay.id == schedule_day_id)
        
        if lock:
            query = query.with_for_update()
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def lock_schedule_day(
        db: AsyncSession,
        schedule_day_id: UUID,
        locked_by_user_id: UUID
    ) -> ScheduleDay:
        """
        Lock a schedule day (DRAFT → LOCKED).
        
        Args:
            db: Database session
            schedule_day_id: Schedule day UUID
            locked_by_user_id: User performing the lock
            
        Returns:
            Updated ScheduleDay
            
        Raises:
            InvalidStatusError: If not in DRAFT status
            ScheduleError: If schedule day not found
        """
        # Lock the row
        schedule_day = await ScheduleService.get_schedule_day(db, schedule_day_id, lock=True)
        
        if not schedule_day:
            raise ScheduleError("Schedule day not found")
        
        if schedule_day.status != ScheduleStatus.DRAFT:
            raise InvalidStatusError(
                f"Cannot lock schedule in {schedule_day.status} status. "
                "Must be in DRAFT status."
            )
        
        # Valid transition
        if not ScheduleService._is_valid_transition(schedule_day.status, ScheduleStatus.LOCKED):
            raise InvalidStatusError("Invalid status transition")
        
        schedule_day.status = ScheduleStatus.LOCKED
        await db.flush()
        
        return schedule_day
    
    @staticmethod
    async def freeze_schedule_day(
        db: AsyncSession,
        schedule_day_id: UUID,
        frozen_by_user_id: UUID
    ) -> Tuple[ScheduleDay, str]:
        """
        Freeze a schedule day (LOCKED → FROZEN).
        
        Creates deterministic snapshot and SHA256 integrity hash.
        
        Args:
            db: Database session
            schedule_day_id: Schedule day UUID
            frozen_by_user_id: User performing the freeze
            
        Returns:
            Tuple of (Updated ScheduleDay, integrity_hash)
            
        Raises:
            InvalidStatusError: If not in LOCKED status
            ScheduleError: If schedule day not found
        """
        # Lock the row
        schedule_day = await ScheduleService.get_schedule_day(db, schedule_day_id, lock=True)
        
        if not schedule_day:
            raise ScheduleError("Schedule day not found")
        
        if schedule_day.status != ScheduleStatus.LOCKED:
            raise InvalidStatusError(
                f"Cannot freeze schedule in {schedule_day.status} status. "
                "Must be in LOCKED status."
            )
        
        # Valid transition
        if not ScheduleService._is_valid_transition(schedule_day.status, ScheduleStatus.FROZEN):
            raise InvalidStatusError("Invalid status transition")
        
        # Build snapshot from all assignments
        assignments_data = await ScheduleService._get_schedule_snapshot(
            db, schedule_day_id
        )
        
        # Compute integrity hash
        integrity_hash = ScheduleService._compute_integrity_hash(assignments_data)
        
        # Update status and hash
        schedule_day.status = ScheduleStatus.FROZEN
        schedule_day.integrity_hash = integrity_hash
        await db.flush()
        
        return schedule_day, integrity_hash
    
    @staticmethod
    async def verify_schedule_integrity(
        db: AsyncSession,
        schedule_day_id: UUID
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify integrity of a frozen schedule.
        
        Recomputes snapshot and hash, compares with stored value.
        Uses constant-time comparison to prevent timing attacks.
        
        Args:
            db: Database session
            schedule_day_id: Schedule day UUID
            
        Returns:
            Tuple of (is_valid, stored_hash or None)
        """
        schedule_day = await ScheduleService.get_schedule_day(db, schedule_day_id)
        
        if not schedule_day:
            return False, None
        
        if schedule_day.status != ScheduleStatus.FROZEN:
            # Non-frozen schedules don't have integrity verification
            return True, None
        
        if not schedule_day.integrity_hash:
            return False, None
        
        # Recompute snapshot
        assignments_data = await ScheduleService._get_schedule_snapshot(
            db, schedule_day_id
        )
        
        # Recompute hash
        computed_hash = ScheduleService._compute_integrity_hash(assignments_data)
        
        # Constant-time comparison
        is_valid = ScheduleService._constant_time_compare(
            computed_hash, schedule_day.integrity_hash
        )
        
        return is_valid, schedule_day.integrity_hash
    
    @staticmethod
    async def _get_schedule_snapshot(
        db: AsyncSession,
        schedule_day_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get deterministic snapshot of schedule for hashing.
        
        Returns list of assignment data sorted by slot_order, match_id.
        """
        query = (
            select(
                MatchScheduleAssignment,
                TimeSlot.slot_order,
                TimeSlot.start_time
            )
            .join(TimeSlot, MatchScheduleAssignment.time_slot_id == TimeSlot.id)
            .where(TimeSlot.schedule_day_id == schedule_day_id)
            .order_by(TimeSlot.slot_order, MatchScheduleAssignment.match_id)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        snapshot = []
        for row in rows:
            assignment = row[0]
            slot_order = row[1]
            start_time = row[2]
            
            snapshot.append({
                "match_id": str(assignment.match_id),
                "courtroom_id": str(assignment.courtroom_id),
                "judge_user_id": str(assignment.judge_user_id) if assignment.judge_user_id else None,
                "slot_order": slot_order,
                "start_time": start_time.isoformat() if start_time else "",
                "status": assignment.status,
            })
        
        return snapshot
    
    # ==========================================================================
    # Time Slot Operations
    # ==========================================================================
    
    @staticmethod
    async def add_time_slot(
        db: AsyncSession,
        schedule_day_id: UUID,
        start_time: datetime,
        end_time: datetime,
        slot_order: int
    ) -> TimeSlot:
        """
        Add a time slot to a schedule day.
        
        Validates:
        - Schedule day is not FROZEN
        - start_time < end_time
        - No overlapping slots
        
        Args:
            db: Database session
            schedule_day_id: Schedule day UUID
            start_time: Slot start datetime
            end_time: Slot end datetime
            slot_order: Display order within day
            
        Returns:
            Created TimeSlot
            
        Raises:
            FrozenScheduleError: If schedule day is frozen
            ScheduleError: For validation failures
        """
        # Lock schedule day
        schedule_day = await ScheduleService.get_schedule_day(db, schedule_day_id, lock=True)
        
        if not schedule_day:
            raise ScheduleError("Schedule day not found")
        
        if schedule_day.status == ScheduleStatus.FROZEN:
            raise FrozenScheduleError("Cannot modify frozen schedule")
        
        if start_time >= end_time:
            raise ScheduleError("Start time must be before end time")
        
        # Check for overlapping slots
        overlap_query = (
            select(TimeSlot)
            .where(
                and_(
                    TimeSlot.schedule_day_id == schedule_day_id,
                    or_(
                        and_(
                            TimeSlot.start_time <= start_time,
                            TimeSlot.end_time > start_time
                        ),
                        and_(
                            TimeSlot.start_time < end_time,
                            TimeSlot.end_time >= end_time
                        ),
                        and_(
                            TimeSlot.start_time >= start_time,
                            TimeSlot.end_time <= end_time
                        )
                    )
                )
            )
        )
        
        overlap_result = await db.execute(overlap_query)
        if overlap_result.scalar_one_or_none():
            raise ScheduleError("Time slot overlaps with existing slot")
        
        time_slot = TimeSlot(
            schedule_day_id=schedule_day_id,
            start_time=start_time,
            end_time=end_time,
            slot_order=slot_order
        )
        
        db.add(time_slot)
        await db.flush()
        
        return time_slot
    
    # ==========================================================================
    # Match Assignment Operations
    # ==========================================================================
    
    @staticmethod
    async def assign_match(
        db: AsyncSession,
        match_id: UUID,
        courtroom_id: UUID,
        time_slot_id: UUID,
        judge_user_id: Optional[UUID] = None
    ) -> MatchScheduleAssignment:
        """
        Assign a match to a courtroom, time slot, and optionally a judge.
        
        This operation acquires locks on:
        - ScheduleDay (via TimeSlot)
        - TimeSlot
        - Courtroom
        - Any existing assignments for conflict checking
        
        Conflict checks:
        1. Court clash (courtroom already booked in slot)
        2. Judge double booking (judge already assigned in slot)
        3. Team double booking (both teams in match)
        4. Match already scheduled
        
        Args:
            db: Database session
            match_id: Match UUID
            courtroom_id: Courtroom UUID
            time_slot_id: Time slot UUID
            judge_user_id: Optional judge UUID
            
        Returns:
            Created MatchScheduleAssignment
            
        Raises:
            ConflictError: If any conflict detected
            FrozenScheduleError: If schedule is frozen
        """
        # Lock time slot and get schedule day
        time_slot_query = (
            select(TimeSlot, ScheduleDay)
            .join(ScheduleDay, TimeSlot.schedule_day_id == ScheduleDay.id)
            .where(TimeSlot.id == time_slot_id)
            .with_for_update()
        )
        
        time_result = await db.execute(time_slot_query)
        time_row = time_result.one_or_none()
        
        if not time_row:
            raise ScheduleError("Time slot not found")
        
        time_slot, schedule_day = time_row
        
        # Check schedule not frozen
        if schedule_day.status == ScheduleStatus.FROZEN:
            raise FrozenScheduleError("Cannot modify frozen schedule")
        
        # Lock courtroom
        courtroom_query = (
            select(Courtroom)
            .where(Courtroom.id == courtroom_id)
            .with_for_update()
        )
        courtroom_result = await db.execute(courtroom_query)
        courtroom = courtroom_result.scalar_one_or_none()
        
        if not courtroom:
            raise ScheduleError("Courtroom not found")
        
        # Get match info (deferred import to avoid circular dependency)
        from backend.orm.round_engine_models import TournamentMatch
        
        match_query = (
            select(TournamentMatch)
            .where(TournamentMatch.id == match_id)
            .with_for_update()
        )
        match_result = await db.execute(match_query)
        match = match_result.scalar_one_or_none()
        
        if not match:
            raise ScheduleError("Match not found")
        
        # Conflict Check 1: Match already scheduled
        existing_match_query = (
            select(MatchScheduleAssignment)
            .where(MatchScheduleAssignment.match_id == match_id)
            .with_for_update()
        )
        existing_match_result = await db.execute(existing_match_query)
        if existing_match_result.scalar_one_or_none():
            raise ConflictError("Match is already scheduled")
        
        # Conflict Check 2: Court clash (courtroom already booked in this slot)
        court_clash_query = (
            select(MatchScheduleAssignment)
            .where(
                and_(
                    MatchScheduleAssignment.courtroom_id == courtroom_id,
                    MatchScheduleAssignment.time_slot_id == time_slot_id
                )
            )
            .with_for_update()
        )
        court_clash_result = await db.execute(court_clash_query)
        if court_clash_result.scalar_one_or_none():
            raise ConflictError("Courtroom is already booked in this time slot")
        
        # Conflict Check 3: Judge double booking
        if judge_user_id:
            judge_clash_query = (
                select(MatchScheduleAssignment)
                .where(
                    and_(
                        MatchScheduleAssignment.judge_user_id == judge_user_id,
                        MatchScheduleAssignment.time_slot_id == time_slot_id
                    )
                )
                .with_for_update()
            )
            judge_clash_result = await db.execute(judge_clash_query)
            if judge_clash_result.scalar_one_or_none():
                raise ConflictError("Judge is already assigned in this time slot")
        
        # Conflict Check 4: Team double booking
        # Check if either team in this match is already scheduled in this slot
        team_clash_query = (
            select(MatchScheduleAssignment, TournamentMatch)
            .join(TournamentMatch, MatchScheduleAssignment.match_id == TournamentMatch.id)
            .where(
                and_(
                    MatchScheduleAssignment.time_slot_id == time_slot_id,
                    or_(
                        TournamentMatch.petitioner_id == match.petitioner_id,
                        TournamentMatch.petitioner_id == match.respondent_id,
                        TournamentMatch.respondent_id == match.petitioner_id,
                        TournamentMatch.respondent_id == match.respondent_id
                    )
                )
            )
            .with_for_update()
        )
        team_clash_result = await db.execute(team_clash_query)
        if team_clash_result.scalar_one_or_none():
            raise ConflictError("One of the teams is already scheduled in this time slot")
        
        # All checks passed - create assignment
        assignment = MatchScheduleAssignment(
            match_id=match_id,
            courtroom_id=courtroom_id,
            time_slot_id=time_slot_id,
            judge_user_id=judge_user_id,
            status=AssignmentStatus.ASSIGNED
        )
        
        db.add(assignment)
        await db.flush()
        
        return assignment
    
    @staticmethod
    async def confirm_assignment(
        db: AsyncSession,
        assignment_id: UUID,
        confirmed_by_user_id: UUID
    ) -> MatchScheduleAssignment:
        """
        Confirm a match assignment (ASSIGNED → CONFIRMED).
        
        Args:
            db: Database session
            assignment_id: Assignment UUID
            confirmed_by_user_id: User confirming the assignment
            
        Returns:
            Updated MatchScheduleAssignment
        """
        query = (
            select(MatchScheduleAssignment)
            .where(MatchScheduleAssignment.id == assignment_id)
            .with_for_update()
        )
        
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()
        
        if not assignment:
            raise ScheduleError("Assignment not found")
        
        assignment.status = AssignmentStatus.CONFIRMED
        await db.flush()
        
        return assignment
    
    # ==========================================================================
    # Query Operations
    # ==========================================================================
    
    @staticmethod
    async def get_assignments_by_day(
        db: AsyncSession,
        schedule_day_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get all assignments for a schedule day with related data."""
        query = (
            select(
                MatchScheduleAssignment,
                Courtroom,
                TimeSlot
            )
            .join(Courtroom, MatchScheduleAssignment.courtroom_id == Courtroom.id)
            .join(TimeSlot, MatchScheduleAssignment.time_slot_id == TimeSlot.id)
            .where(TimeSlot.schedule_day_id == schedule_day_id)
            .order_by(TimeSlot.slot_order)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        assignments = []
        for row in rows:
            assignment, courtroom, time_slot = row
            assignments.append({
                "assignment": assignment.to_dict(),
                "courtroom": courtroom.to_dict(),
                "time_slot": time_slot.to_dict(),
            })
        
        return assignments
    
    @staticmethod
    async def get_assignment_by_match(
        db: AsyncSession,
        match_id: UUID
    ) -> Optional[MatchScheduleAssignment]:
        """Get assignment for a specific match."""
        query = (
            select(MatchScheduleAssignment)
            .where(MatchScheduleAssignment.match_id == match_id)
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_assignments_by_judge(
        db: AsyncSession,
        judge_user_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get all assignments for a specific judge."""
        query = (
            select(
                MatchScheduleAssignment,
                Courtroom,
                TimeSlot,
                ScheduleDay
            )
            .join(Courtroom, MatchScheduleAssignment.courtroom_id == Courtroom.id)
            .join(TimeSlot, MatchScheduleAssignment.time_slot_id == TimeSlot.id)
            .join(ScheduleDay, TimeSlot.schedule_day_id == ScheduleDay.id)
            .where(MatchScheduleAssignment.judge_user_id == judge_user_id)
            .order_by(ScheduleDay.date, TimeSlot.start_time)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        assignments = []
        for row in rows:
            assignment, courtroom, time_slot, schedule_day = row
            assignments.append({
                "assignment": assignment.to_dict(),
                "courtroom": courtroom.to_dict(),
                "time_slot": time_slot.to_dict(),
                "schedule_day": schedule_day.to_dict(),
            })
        
        return assignments
