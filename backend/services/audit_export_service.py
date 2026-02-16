"""
Phase 12 — Audit Export Bundle Service

Generates deterministic export bundles of complete tournament data.
All exports are cryptographically verifiable.
"""
import os
import io
import json
import zipfile
from typing import Dict, List, Any, Optional
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.national_network import NationalTournament
from backend.orm.tournament_results import (
    TournamentTeamResult,
    TournamentSpeakerResult,
    TournamentResultsFreeze,
    TournamentAuditSnapshot
)
from backend.orm.tournament_pairings import TournamentPairing
from backend.orm.judge_panels import JudgePanel
from backend.orm.oral_rounds import OralEvaluation
from backend.orm.exhibit import SessionExhibit
from backend.orm.live_court import LiveCourtSession, LiveEventLog
from backend.orm.live_objection import LiveObjection


def _dumps(obj: Any) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(obj, sort_keys=True, indent=2, separators=(',', ': '))


async def export_tournament_bundle(
    tournament_id: int,
    db: AsyncSession,
    include_events: bool = True
) -> bytes:
    """
    Generate deterministic export bundle as ZIP file.
    
    Bundle structure:
    tournament_{id}_audit_bundle.zip
     ├─ snapshot.json       # Audit snapshot
     ├─ results.json        # Team and speaker results
     ├─ pairings.json       # All tournament pairings
     ├─ panels.json         # Judge panels
     ├─ exhibits.json       # Session exhibits
     ├─ events/             # Live session events
     │    ├─ session_1.json
     │    ├─ session_2.json
     ├─ audit_root.txt      # Root hash for quick reference
     └─ certificate.json    # Generated certificate
    
    Args:
        tournament_id: Tournament to export
        db: Database session
        include_events: Include live session events
        
    Returns:
        ZIP file as bytes
    """
    # Get tournament info
    tournament = await db.execute(
        select(NationalTournament)
        .where(NationalTournament.id == tournament_id)
    )
    tournament = tournament.scalar_one_or_none()
    
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Add audit snapshot
        await _add_snapshot_json(zip_file, tournament_id, db)
        
        # 2. Add results
        await _add_results_json(zip_file, tournament_id, db)
        
        # 3. Add pairings
        await _add_pairings_json(zip_file, tournament_id, db)
        
        # 4. Add panels
        await _add_panels_json(zip_file, tournament_id, db)
        
        # 5. Add exhibits
        await _add_exhibits_json(zip_file, tournament_id, db)
        
        # 6. Add events if requested
        if include_events:
            await _add_events_folder(zip_file, tournament_id, db)
        
        # 7. Add audit root text file
        await _add_audit_root_txt(zip_file, tournament_id, db)
        
        # 8. Add certificate
        await _add_certificate_json(zip_file, tournament_id, tournament.name, db)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


async def _add_snapshot_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add audit snapshot to bundle."""
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    if snapshot:
        data = {
            "audit_root_hash": snapshot.audit_root_hash,
            "generated_at": snapshot.generated_at.isoformat() if snapshot.generated_at else None,
            "generated_by": snapshot.generated_by,
            "signature_hmac": snapshot.signature_hmac,
            "snapshot_json": snapshot.snapshot_json,
            "tournament_id": snapshot.tournament_id
        }
    else:
        data = {"error": "No audit snapshot found"}
    
    zip_file.writestr("snapshot.json", _dumps(data))


async def _add_results_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add team and speaker results to bundle."""
    # Team results
    team_result = await db.execute(
        select(TournamentTeamResult)
        .where(TournamentTeamResult.tournament_id == tournament_id)
        .order_by(TournamentTeamResult.final_rank)
    )
    teams = [row.to_dict() for row in team_result.scalars().all()]
    
    # Speaker results
    speaker_result = await db.execute(
        select(TournamentSpeakerResult)
        .where(TournamentSpeakerResult.tournament_id == tournament_id)
        .order_by(TournamentSpeakerResult.final_rank)
    )
    speakers = [row.to_dict() for row in speaker_result.scalars().all()]
    
    # Results freeze
    freeze = await db.execute(
        select(TournamentResultsFreeze)
        .where(TournamentResultsFreeze.tournament_id == tournament_id)
    )
    freeze = freeze.scalar_one_or_none()
    
    data = {
        "teams": teams,
        "speakers": speakers,
        "checksum": freeze.results_checksum if freeze else None,
        "frozen_at": freeze.frozen_at.isoformat() if freeze and freeze.frozen_at else None
    }
    
    zip_file.writestr("results.json", _dumps(data))


async def _add_pairings_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add tournament pairings to bundle."""
    result = await db.execute(
        select(TournamentPairing)
        .where(TournamentPairing.tournament_id == tournament_id)
        .order_by(TournamentPairing.round_number, TournamentPairing.id)
    )
    
    pairings = []
    for row in result.scalars().all():
        pairings.append({
            "id": row.id,
            "round_number": row.round_number,
            "team1_id": row.team1_id,
            "team2_id": row.team2_id,
            "room_assignment": row.room_assignment,
            "pairing_checksum": row.pairing_checksum
        })
    
    data = {
        "tournament_id": tournament_id,
        "pairings": pairings,
        "count": len(pairings)
    }
    
    zip_file.writestr("pairings.json", _dumps(data))


async def _add_panels_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add judge panels to bundle."""
    result = await db.execute(
        select(JudgePanel)
        .where(JudgePanel.tournament_id == tournament_id)
        .order_by(JudgePanel.id)
    )
    
    panels = []
    for row in result.scalars().all():
        panels.append({
            "id": row.id,
            "judge1_id": row.judge1_id,
            "judge2_id": row.judge2_id,
            "judge3_id": row.judge3_id,
            "panel_checksum": row.panel_checksum
        })
    
    data = {
        "tournament_id": tournament_id,
        "panels": panels,
        "count": len(panels)
    }
    
    zip_file.writestr("panels.json", _dumps(data))


async def _add_exhibits_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add session exhibits to bundle."""
    result = await db.execute(
        select(SessionExhibit)
        .join(LiveCourtSession)
        .where(LiveCourtSession.tournament_id == tournament_id)
        .order_by(SessionExhibit.exhibit_number)
    )
    
    exhibits = []
    for row in result.scalars().all():
        exhibits.append({
            "id": row.id,
            "exhibit_number": row.exhibit_number,
            "exhibit_hash": row.exhibit_hash,
            "file_name": row.file_name,
            "state": row.state.value if row.state else None
        })
    
    data = {
        "tournament_id": tournament_id,
        "exhibits": exhibits,
        "count": len(exhibits)
    }
    
    zip_file.writestr("exhibits.json", _dumps(data))


async def _add_events_folder(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add live session events to bundle."""
    # Get all completed sessions
    sessions = await db.execute(
        select(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.tournament_id == tournament_id,
                LiveCourtSession.session_status == "COMPLETED"
            )
        )
        .order_by(LiveCourtSession.id)
    )
    
    for i, session in enumerate(sessions.scalars().all(), 1):
        # Get events for this session
        events_result = await db.execute(
            select(LiveEventLog)
            .where(LiveEventLog.session_id == session.id)
            .order_by(LiveEventLog.sequence_number)
        )
        
        events = []
        for event in events_result.scalars().all():
            events.append({
                "sequence_number": event.sequence_number,
                "event_type": event.event_type,
                "event_hash": event.event_hash,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None
            })
        
        data = {
            "session_id": session.id,
            "session_status": session.session_status.value if session.session_status else None,
            "events": events,
            "event_count": len(events)
        }
        
        zip_file.writestr(f"events/session_{i}.json", _dumps(data))


async def _add_audit_root_txt(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    db: AsyncSession
) -> None:
    """Add audit root hash text file."""
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    if snapshot:
        content = f"""Tournament Audit Root Hash
==========================

Tournament ID: {tournament_id}
Audit Root:    {snapshot.audit_root_hash}
Signature:     {snapshot.signature_hmac}
Generated:     {snapshot.generated_at.isoformat() if snapshot.generated_at else 'N/A'}

This hash represents the Merkle root of all tournament components.
Any modification to tournament data will change this hash.
"""
    else:
        content = f"No audit snapshot found for tournament {tournament_id}"
    
    zip_file.writestr("audit_root.txt", content)


async def _add_certificate_json(
    zip_file: zipfile.ZipFile,
    tournament_id: int,
    tournament_name: str,
    db: AsyncSession
) -> None:
    """Add certificate JSON to bundle."""
    # Get winner
    winner_result = await db.execute(
        select(TournamentTeamResult)
        .where(
            and_(
                TournamentTeamResult.tournament_id == tournament_id,
                TournamentTeamResult.final_rank == 1
            )
        )
    )
    winner = winner_result.scalar_one_or_none()
    
    # Get snapshot
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    data = {
        "tournament_id": tournament_id,
        "tournament_name": tournament_name,
        "winner": winner.team_id if winner else None,
        "audit_root_hash": snapshot.audit_root_hash if snapshot else None,
        "signature": snapshot.signature_hmac if snapshot else None,
        "generated_at": snapshot.generated_at.isoformat() if snapshot and snapshot.generated_at else None
    }
    
    zip_file.writestr("certificate.json", _dumps(data))
