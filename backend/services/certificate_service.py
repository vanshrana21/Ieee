"""
Phase 12 — Tournament Certificate Service

Generates signed certificates with cryptographic verification.
Deterministic JSON format with HMAC-SHA256 signatures.
"""
import os
import json
import hmac
import hashlib
from typing import Dict, Any, Optional
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.national_network import NationalTournament
from backend.orm.tournament_results import (
    TournamentTeamResult,
    TournamentSpeakerResult,
    TournamentAuditSnapshot
)


def compute_signature(data: str, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature.
    
    Args:
        data: Data to sign
        secret: HMAC secret key
        
    Returns:
        64-char hex signature
    """
    return hmac.new(
        secret.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()


async def generate_tournament_certificate(
    tournament_id: int,
    db: AsyncSession,
    secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate deterministic tournament certificate.
    
    Certificate format:
    {
        "tournament_id": int,
        "tournament_name": str,
        "institution_id": int,
        "winner": {
            "team_id": int,
            "total_score": str,  # Decimal as string
            "sos": str
        },
        "runner_up": {
            "team_id": int,
            "total_score": str
        },
        "best_speaker": {
            "speaker_id": int,
            "average_score": str
        },
        "audit_root_hash": str,
        "signature": str,
        "generated_at": str  # ISO timestamp from snapshot
    }
    
    Args:
        tournament_id: Tournament ID
        db: Database session
        secret: HMAC secret (defaults to SECRET_KEY env var)
        
    Returns:
        Certificate dictionary
        
    Raises:
        ValueError: Tournament not found or no audit snapshot
    """
    if secret is None:
        secret = os.environ.get("SECRET_KEY", "dev-secret-key")
    
    # Get tournament
    tournament = await db.execute(
        select(NationalTournament)
        .where(NationalTournament.id == tournament_id)
    )
    tournament = tournament.scalar_one_or_none()
    
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")
    
    # Get audit snapshot
    snapshot = await db.execute(
        select(TournamentAuditSnapshot)
        .where(TournamentAuditSnapshot.tournament_id == tournament_id)
    )
    snapshot = snapshot.scalar_one_or_none()
    
    if not snapshot:
        raise ValueError(f"No audit snapshot for tournament {tournament_id}")
    
    # Get winner (rank 1)
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
    
    # Get runner-up (rank 2)
    runner_up_result = await db.execute(
        select(TournamentTeamResult)
        .where(
            and_(
                TournamentTeamResult.tournament_id == tournament_id,
                TournamentTeamResult.final_rank == 2
            )
        )
    )
    runner_up = runner_up_result.scalar_one_or_none()
    
    # Get best speaker (rank 1)
    best_speaker_result = await db.execute(
        select(TournamentSpeakerResult)
        .where(
            and_(
                TournamentSpeakerResult.tournament_id == tournament_id,
                TournamentSpeakerResult.final_rank == 1
            )
        )
    )
    best_speaker = best_speaker_result.scalar_one_or_none()
    
    # Build certificate (deterministic ordering)
    certificate = {
        "tournament_id": tournament_id,
        "tournament_name": tournament.name,
        "institution_id": tournament.institution_id,
    }
    
    # Add winner info
    if winner:
        certificate["winner"] = {
            "team_id": winner.team_id,
            "total_score": str(Decimal(str(winner.total_score)).quantize(Decimal("0.01"))),
            "sos": str(Decimal(str(winner.strength_of_schedule)).quantize(Decimal("0.0001")))
        }
    
    # Add runner-up info
    if runner_up:
        certificate["runner_up"] = {
            "team_id": runner_up.team_id,
            "total_score": str(Decimal(str(runner_up.total_score)).quantize(Decimal("0.01")))
        }
    
    # Add best speaker info
    if best_speaker:
        certificate["best_speaker"] = {
            "speaker_id": best_speaker.speaker_id,
            "average_score": str(Decimal(str(best_speaker.average_score)).quantize(Decimal("0.0001")))
        }
    
    # Add audit info
    certificate["audit_root_hash"] = snapshot.audit_root_hash
    certificate["generated_at"] = snapshot.generated_at.isoformat() if snapshot.generated_at else None
    
    # Sort keys for determinism before signing
    cert_json = json.dumps(certificate, sort_keys=True, separators=(',', ':'))
    
    # Sign the certificate
    signature = compute_signature(cert_json, secret)
    certificate["signature"] = signature
    
    return certificate


async def verify_certificate(
    certificate: Dict[str, Any],
    expected_root_hash: str,
    secret: Optional[str] = None
) -> Dict[str, bool]:
    """
    Verify tournament certificate integrity.
    
    Args:
        certificate: Certificate dictionary
        expected_root_hash: Expected audit root hash
        secret: HMAC secret for signature verification
        
    Returns:
        {
            "valid": bool,
            "signature_valid": bool,
            "root_hash_match": bool
        }
    """
    if secret is None:
        secret = os.environ.get("SECRET_KEY", "dev-secret-key")
    
    # Extract signature
    provided_signature = certificate.pop("signature", None)
    
    # Recompute signature
    cert_json = json.dumps(certificate, sort_keys=True, separators=(',', ':'))
    expected_signature = compute_signature(cert_json, secret)
    
    # Restore signature
    certificate["signature"] = provided_signature
    
    # Verify
    signature_valid = hmac.compare_digest(expected_signature, provided_signature)
    root_match = certificate.get("audit_root_hash") == expected_root_hash
    
    return {
        "valid": signature_valid and root_match,
        "signature_valid": signature_valid,
        "root_hash_match": root_match
    }


def format_certificate_text(certificate: Dict[str, Any]) -> str:
    """
    Format certificate as human-readable text.
    
    Args:
        certificate: Certificate dictionary
        
    Returns:
        Formatted text
    """
    lines = [
        "=" * 60,
        "        MOOT COURT TOURNAMENT CERTIFICATE",
        "=" * 60,
        "",
        f"Tournament: {certificate.get('tournament_name', 'N/A')}",
        f"ID: {certificate.get('tournament_id', 'N/A')}",
        "",
        "-" * 60,
        "                      WINNERS",
        "-" * 60,
    ]
    
    winner = certificate.get("winner")
    if winner:
        lines.extend([
            f"Winner:       Team {winner.get('team_id')}",
            f"Score:        {winner.get('total_score')}",
            f"SOS:          {winner.get('sos')}",
        ])
    
    runner_up = certificate.get("runner_up")
    if runner_up:
        lines.extend([
            f"Runner-up:    Team {runner_up.get('team_id')}",
            f"Score:        {runner_up.get('total_score')}",
        ])
    
    best_speaker = certificate.get("best_speaker")
    if best_speaker:
        lines.extend([
            f"Best Speaker: Participant {best_speaker.get('speaker_id')}",
            f"Avg Score:    {best_speaker.get('average_score')}",
        ])
    
    lines.extend([
        "",
        "-" * 60,
        "                    VERIFICATION",
        "-" * 60,
        f"Audit Root:   {certificate.get('audit_root_hash', 'N/A')}",
        f"Signature:    {certificate.get('signature', 'N/A')[:32]}...",
        f"Generated:    {certificate.get('generated_at', 'N/A')}",
        "",
        "This certificate is cryptographically signed and",
        "can be verified against the audit ledger.",
        "=" * 60,
    ])
    
    return "\n".join(lines)
