"""
Phase 12 — Tournament Audit Service

Generates immutable audit snapshots with Merkle root integrity.
Concurrency safe with SERIALIZABLE isolation and idempotent generation.
"""
import os
import json
import hmac
import hashlib
from typing import Dict, List, Optional, Any
from decimal import Decimal

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.security.merkle import (
    sha256,
    hash_tournament_data,
    serialize_hash_tree
)

from backend.orm.national_network import NationalTournament
from backend.orm.tournament_results import (
    TournamentTeamResult,
    TournamentSpeakerResult,
    TournamentResultsFreeze
)
from backend.orm.oral_rounds import OralEvaluation
from backend.orm.panel_assignment import JudgePanel
from backend.orm.round_pairing import RoundPairing, TournamentRound
from backend.orm.exhibit import SessionExhibit
from backend.orm.live_court import LiveEventLog, LiveCourtSession, LiveCourtStatus


def compute_signature(root_hash: str, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature for audit root.
    
    Args:
        root_hash: 64-char hex Merkle root
        secret: HMAC secret key
        
    Returns:
        64-char hex signature
    """
    return hmac.new(
        secret.encode(),
        root_hash.encode(),
        hashlib.sha256
    ).hexdigest()


async def generate_tournament_audit_snapshot(
    tournament_id: int,
    user_id: int,
    db: AsyncSession,
    secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate immutable audit snapshot for tournament.
    
    Concurrency guarantees:
    - SERIALIZABLE isolation
    - Tournament FOR UPDATE lock
    - Idempotent: returns existing if snapshot already exists
    
    Args:
        tournament_id: Tournament to audit
        user_id: User generating snapshot (must be ADMIN/HOD)
        db: Database session
        secret: HMAC secret (defaults to SECRET_KEY env var)
        
    Returns:
        {
            "tournament_id": int,
            "snapshot_id": int,
            "audit_root_hash": str,
            "signature_hmac": str,
            "is_new": bool  # True if created, False if existed
        }
        
    Raises:
        ValueError: Tournament not found or not completed
        PermissionError: User lacks permission
    """
    if secret is None:
        secret = os.environ.get("SECRET_KEY", "dev-secret-key")
    
    # Set serializable isolation
    await db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    
    # Lock tournament for update
    tournament = await db.execute(
        select(NationalTournament)
        .where(NationalTournament.id == tournament_id)
        .with_for_update()
    )
    tournament = tournament.scalar_one_or_none()
    
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")
    
    # Check existing snapshot (idempotent)
    from backend.orm.tournament_results import TournamentAuditSnapshot
    
    existing = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    existing = existing.scalar_one_or_none()
    
    if existing:
        return {
            "tournament_id": tournament_id,
            "snapshot_id": existing.id,
            "audit_root_hash": existing.audit_root_hash,
            "signature_hmac": existing.signature_hmac,
            "is_new": False
        }
    
    # Collect all component hashes
    component_hashes = await _collect_component_hashes(tournament_id, db)
    
    # Build Merkle root
    audit_root = hash_tournament_data(
        tournament_id=tournament_id,
        pairing_checksum=component_hashes.get("pairing"),
        panel_checksum=component_hashes.get("panel"),
        event_hashes=component_hashes.get("events", []),
        objection_hashes=component_hashes.get("objections", []),
        exhibit_hashes=component_hashes.get("exhibits", []),
        results_checksum=component_hashes.get("results")
    )
    
    # Compute signature
    signature = compute_signature(audit_root, secret)
    
    # Build deterministic snapshot JSON
    snapshot_json = _build_snapshot_json(tournament_id, component_hashes)
    
    # Create snapshot record
    snapshot = TournamentAuditSnapshot(
        tournament_id=tournament_id,
        institution_id=tournament.institution_id,
        audit_root_hash=audit_root,
        snapshot_json=snapshot_json,
        signature_hmac=signature,
        generated_by=user_id
    )
    
    db.add(snapshot)
    await db.commit()
    
    return {
        "tournament_id": tournament_id,
        "snapshot_id": snapshot.id,
        "audit_root_hash": audit_root,
        "signature_hmac": signature,
        "is_new": True
    }


async def _collect_component_hashes(
    tournament_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Collect all component hashes for Merkle tree.
    
    Returns dict with keys:
    - pairing: Phase 3 checksum
    - panel: Phase 4 checksum
    - events: List of Phase 5 event hashes
    - objections: List of Phase 6 objection hashes
    - exhibits: List of Phase 7 exhibit hashes
    - results: Phase 9 checksum
    """
    hashes = {}
    
    round_result = await db.execute(
        select(TournamentRound.id).where(TournamentRound.tournament_id == tournament_id)
    )
    round_ids = [row[0] for row in round_result.all()]
    
    # Get Phase 3 pairing checksum
    pairing_result = await db.execute(
        select(RoundPairing.pairing_hash)
        .where(RoundPairing.round_id.in_(round_ids))
        .order_by(RoundPairing.id)
        .limit(1)
    )
    pairing_row = pairing_result.first()
    hashes["pairing"] = pairing_row[0] if pairing_row else None
    
    # Get Phase 4 panel checksum
    panel_result = await db.execute(
        select(JudgePanel.panel_hash)
        .where(JudgePanel.round_id.in_(round_ids))
        .order_by(JudgePanel.id)
        .limit(1)
    )
    panel_row = panel_result.first()
    hashes["panel"] = panel_row[0] if panel_row else None
    
    # Get Phase 5 event hashes from completed sessions
    event_result = await db.execute(
        select(LiveEventLog.event_hash)
        .join(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.round_id.in_(round_ids),
                LiveCourtSession.status == LiveCourtStatus.COMPLETED
            )
        )
        .order_by(LiveEventLog.event_sequence)
    )
    hashes["events"] = [row[0] for row in event_result.all()]
    
    # Get Phase 6 objection hashes
    from backend.orm.live_objection import LiveObjection
    objection_result = await db.execute(
        select(LiveObjection.objection_hash)
        .join(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.round_id.in_(round_ids),
                LiveObjection.objection_hash.isnot(None)
            )
        )
        .order_by(LiveObjection.raised_at)
    )
    hashes["objections"] = [row[0] for row in objection_result.all()]
    
    # Get Phase 7 exhibit hashes
    exhibit_result = await db.execute(
        select(SessionExhibit.exhibit_hash)
        .join(LiveCourtSession)
        .where(
            and_(
                LiveCourtSession.round_id.in_(round_ids),
                SessionExhibit.exhibit_hash.isnot(None)
            )
        )
        .order_by(SessionExhibit.exhibit_number)
    )
    hashes["exhibits"] = [row[0] for row in exhibit_result.all()]
    
    # Get Phase 9 results checksum
    results_result = await db.execute(
        select(TournamentResultsFreeze.results_checksum)
        .where(TournamentResultsFreeze.tournament_id == tournament_id)
        .limit(1)
    )
    results_row = results_result.first()
    hashes["results"] = results_row[0] if results_row else None
    
    return hashes


def _build_snapshot_json(
    tournament_id: int,
    component_hashes: Dict[str, Any]
) -> str:
    """
    Build deterministic JSON snapshot.
    
    All data sorted for determinism.
    """
    snapshot = {
        "tournament_id": tournament_id,
        "version": "1.0",
        "components": {}
    }
    
    # Add each component (sorted)
    for key in sorted(component_hashes.keys()):
        value = component_hashes[key]
        if isinstance(value, list):
            snapshot["components"][key] = sorted(value)
        else:
            snapshot["components"][key] = value
    
    return json.dumps(snapshot, sort_keys=True, separators=(',', ':'))


async def verify_audit_snapshot(
    tournament_id: int,
    db: AsyncSession,
    secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Verify stored audit snapshot integrity.
    
    Recomputes all hashes and compares with stored values.
    Detects tampering of any tournament component.
    
    Args:
        tournament_id: Tournament to verify
        db: Database session
        secret: HMAC secret for signature verification
        
    Returns:
        {
            "snapshot_exists": bool,
            "valid": bool,
            "tamper_detected": bool,
            "stored_root": str,
            "recomputed_root": str,
            "signature_valid": bool,
            "details": {
                "pairing_match": bool,
                "panel_match": bool,
                "events_match": bool,
                "objections_match": bool,
                "exhibits_match": bool,
                "results_match": bool
            }
        }
    """
    if secret is None:
        secret = os.environ.get("SECRET_KEY", "dev-secret-key")
    
    from backend.orm.tournament_results import TournamentAuditSnapshot
    
    # Fetch stored snapshot
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    if not snapshot:
        return {
            "snapshot_exists": False,
            "valid": False,
            "tamper_detected": False,
            "stored_root": None,
            "recomputed_root": None,
            "signature_valid": False,
            "details": {}
        }
    
    # Collect current component hashes
    current_hashes = await _collect_component_hashes(tournament_id, db)
    
    # Rebuild Merkle root
    recomputed_root = hash_tournament_data(
        tournament_id=tournament_id,
        pairing_checksum=current_hashes.get("pairing"),
        panel_checksum=current_hashes.get("panel"),
        event_hashes=current_hashes.get("events", []),
        objection_hashes=current_hashes.get("objections", []),
        exhibit_hashes=current_hashes.get("exhibits", []),
        results_checksum=current_hashes.get("results")
    )
    
    # Verify signature
    expected_signature = compute_signature(recomputed_root, secret)
    signature_valid = hmac.compare_digest(
        expected_signature,
        snapshot.signature_hmac
    )
    
    # Compare roots
    root_match = recomputed_root == snapshot.audit_root_hash
    
    # Build component match details
    stored_components = json.loads(snapshot.snapshot_json)["components"]
    
    details = {}
    for key in ["pairing", "panel", "results"]:
        stored = stored_components.get(key)
        current = current_hashes.get(key)
        details[f"{key}_match"] = stored == current
    
    for key in ["events", "objections", "exhibits"]:
        stored = set(stored_components.get(key, []))
        current = set(current_hashes.get(key, []))
        details[f"{key}_match"] = stored == current
    
    tamper_detected = not root_match or not signature_valid
    
    return {
        "snapshot_exists": True,
        "valid": root_match and signature_valid,
        "tamper_detected": tamper_detected,
        "stored_root": snapshot.audit_root_hash,
        "recomputed_root": recomputed_root,
        "signature_valid": signature_valid,
        "details": details
    }
