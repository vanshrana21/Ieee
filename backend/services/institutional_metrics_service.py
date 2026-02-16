"""
Institution Metrics Service — Phase 6 (Monitoring & Observability)

Provides running counters for institutional operations monitoring.

Features:
- Daily metric aggregation
- Automatic counter incrementing
- Institution-scoped metrics isolation
- Metrics retrieval for admin dashboards

Rules:
- Metrics are cumulative (never reset)
- New row created per day per institution
- All counters default to 0
- UTC timestamps only
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.institutional_governance import InstitutionMetrics

logger = logging.getLogger(__name__)


async def get_or_create_daily_metrics(
    institution_id: int,
    db: AsyncSession,
    metric_date: Optional[date] = None
) -> InstitutionMetrics:
    """
    Get or create daily metrics record for an institution.
    
    If no date provided, uses current UTC date.
    Creates new record if none exists for the date.
    """
    if metric_date is None:
        metric_date = datetime.utcnow().date()
    
    # Convert date to datetime for comparison
    date_start = datetime.combine(metric_date, datetime.min.time())
    
    # Try to find existing record
    result = await db.execute(
        select(InstitutionMetrics)
        .where(
            and_(
                InstitutionMetrics.institution_id == institution_id,
                func.date(InstitutionMetrics.metric_date) == metric_date
            )
        )
    )
    metrics = result.scalar_one_or_none()
    
    if metrics:
        return metrics
    
    # Create new record
    metrics = InstitutionMetrics(
        institution_id=institution_id,
        metric_date=date_start,
        freeze_attempts=0,
        freeze_successes=0,
        freeze_failures=0,
        integrity_failures=0,
        override_count=0,
        concurrency_conflicts=0,
        review_approvals=0,
        review_rejections=0,
        review_modifications=0,
        approval_grants=0,
        approval_rejections=0,
        publications=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(metrics)
    await db.flush()
    
    logger.info(f"Created daily metrics for institution {institution_id} on {metric_date}")
    
    return metrics


async def increment_metric(
    institution_id: int,
    metric_name: str,
    db: AsyncSession,
    increment: int = 1
) -> None:
    """
    Increment a specific metric counter.
    
    Args:
        institution_id: Institution scope
        metric_name: Name of the metric field to increment
        increment: Amount to increment (default 1)
        db: Database session
    """
    metrics = await get_or_create_daily_metrics(institution_id, None, db)
    
    # Validate metric name
    valid_metrics = [
        'freeze_attempts', 'freeze_successes', 'freeze_failures',
        'integrity_failures', 'override_count', 'concurrency_conflicts',
        'review_approvals', 'review_rejections', 'review_modifications',
        'approval_grants', 'approval_rejections', 'publications'
    ]
    
    if metric_name not in valid_metrics:
        logger.error(f"Invalid metric name: {metric_name}")
        return
    
    # Increment the counter
    current_value = getattr(metrics, metric_name, 0)
    setattr(metrics, metric_name, current_value + increment)
    metrics.updated_at = datetime.utcnow()
    
    logger.debug(f"Incremented {metric_name} for institution {institution_id}: {current_value} -> {current_value + increment}")


# =============================================================================
# Convenience Functions for Common Metrics
# =============================================================================

async def log_freeze_attempt(institution_id: int, db: AsyncSession) -> None:
    """Log a freeze attempt."""
    await increment_metric(institution_id, 'freeze_attempts', db, 1)


async def log_freeze_success(institution_id: int, db: AsyncSession) -> None:
    """Log a successful freeze."""
    await increment_metric(institution_id, 'freeze_successes', db, 1)


async def log_freeze_failure(institution_id: int, db: AsyncSession) -> None:
    """Log a failed freeze."""
    await increment_metric(institution_id, 'freeze_failures', db, 1)


async def log_integrity_failure(institution_id: int, db: AsyncSession) -> None:
    """Log an integrity check failure."""
    await increment_metric(institution_id, 'integrity_failures', db, 1)
    logger.error(f"Integrity failure logged for institution {institution_id}")


async def log_override(institution_id: int, db: AsyncSession) -> None:
    """Log an evaluation override."""
    await increment_metric(institution_id, 'override_count', db, 1)


async def log_concurrency_conflict(institution_id: int, db: AsyncSession) -> None:
    """Log a concurrency conflict (idempotent freeze hit)."""
    await increment_metric(institution_id, 'concurrency_conflicts', db, 1)


async def log_review_approval(institution_id: int, db: AsyncSession) -> None:
    """Log an approved review."""
    await increment_metric(institution_id, 'review_approvals', db, 1)


async def log_review_rejection(institution_id: int, db: AsyncSession) -> None:
    """Log a rejected review."""
    await increment_metric(institution_id, 'review_rejections', db, 1)


async def log_review_modification(institution_id: int, db: AsyncSession) -> None:
    """Log a review requiring modification."""
    await increment_metric(institution_id, 'review_modifications', db, 1)


async def log_approval_grant(institution_id: int, db: AsyncSession) -> None:
    """Log an approval grant."""
    await increment_metric(institution_id, 'approval_grants', db, 1)


async def log_approval_rejection(institution_id: int, db: AsyncSession) -> None:
    """Log an approval rejection."""
    await increment_metric(institution_id, 'approval_rejections', db, 1)


async def log_publication(institution_id: int, db: AsyncSession) -> None:
    """Log a leaderboard publication."""
    await increment_metric(institution_id, 'publications', db, 1)


# =============================================================================
# Metrics Retrieval Functions
# =============================================================================

async def get_institution_metrics(
    institution_id: int,
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Get metrics for an institution within a date range.
    
    Args:
        institution_id: Institution to query
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        db: Database session
        
    Returns:
        List of daily metric records
    """
    query = select(InstitutionMetrics).where(
        InstitutionMetrics.institution_id == institution_id
    )
    
    if start_date:
        query = query.where(InstitutionMetrics.metric_date >= start_date)
    
    if end_date:
        query = query.where(InstitutionMetrics.metric_date <= end_date)
    
    query = query.order_by(InstitutionMetrics.metric_date.desc())
    
    result = await db.execute(query)
    records = result.scalars().all()
    
    return [record.to_dict() for record in records]


async def get_aggregated_metrics(
    institution_id: int,
    db: AsyncSession,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregated metrics summary for an institution.
    
    Args:
        institution_id: Institution to query
        days: Number of days to aggregate (default 30)
        db: Database session
        
    Returns:
        Aggregated metrics dictionary
    """
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(
            func.sum(InstitutionMetrics.freeze_attempts).label('total_freeze_attempts'),
            func.sum(InstitutionMetrics.freeze_successes).label('total_freeze_successes'),
            func.sum(InstitutionMetrics.freeze_failures).label('total_freeze_failures'),
            func.sum(InstitutionMetrics.integrity_failures).label('total_integrity_failures'),
            func.sum(InstitutionMetrics.override_count).label('total_overrides'),
            func.sum(InstitutionMetrics.concurrency_conflicts).label('total_concurrency_conflicts'),
            func.sum(InstitutionMetrics.review_approvals).label('total_review_approvals'),
            func.sum(InstitutionMetrics.review_rejections).label('total_review_rejections'),
            func.sum(InstitutionMetrics.approval_grants).label('total_approval_grants'),
            func.sum(InstitutionMetrics.approval_rejections).label('total_approval_rejections'),
            func.sum(InstitutionMetrics.publications).label('total_publications'),
            func.count().label('days_with_activity')
        )
        .where(
            and_(
                InstitutionMetrics.institution_id == institution_id,
                InstitutionMetrics.metric_date >= cutoff_date
            )
        )
    )
    
    row = result.one()
    
    # Calculate success rate
    total_attempts = row.total_freeze_attempts or 0
    total_successes = row.total_freeze_successes or 0
    success_rate = (total_successes / total_attempts * 100) if total_attempts > 0 else 0
    
    return {
        "institution_id": institution_id,
        "period_days": days,
        "freeze_metrics": {
            "attempts": row.total_freeze_attempts or 0,
            "successes": row.total_freeze_successes or 0,
            "failures": row.total_freeze_failures or 0,
            "success_rate_percent": round(success_rate, 2)
        },
        "integrity_metrics": {
            "failures": row.total_integrity_failures or 0
        },
        "override_metrics": {
            "total_overrides": row.total_overrides or 0
        },
        "concurrency_metrics": {
            "conflicts": row.total_concurrency_conflicts or 0
        },
        "review_metrics": {
            "approvals": row.total_review_approvals or 0,
            "rejections": row.total_review_rejections or 0
        },
        "approval_metrics": {
            "grants": row.total_approval_grants or 0,
            "rejections": row.total_approval_rejections or 0
        },
        "publication_metrics": {
            "total_publications": row.total_publications or 0
        },
        "activity_summary": {
            "days_with_activity": row.days_with_activity or 0
        }
    }


async def get_system_wide_metrics(
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Get aggregated metrics across all institutions.
    
    For SUPER_ADMIN dashboard.
    """
    result = await db.execute(
        select(
            func.count(func.distinct(InstitutionMetrics.institution_id)).label('active_institutions'),
            func.sum(InstitutionMetrics.freeze_attempts).label('total_freeze_attempts'),
            func.sum(InstitutionMetrics.freeze_successes).label('total_freeze_successes'),
            func.sum(InstitutionMetrics.integrity_failures).label('total_integrity_failures'),
            func.sum(InstitutionMetrics.publications).label('total_publications')
        )
    )
    
    row = result.one()
    
    return {
        "active_institutions": row.active_institutions or 0,
        "total_freeze_attempts": row.total_freeze_attempts or 0,
        "total_freeze_successes": row.total_freeze_successes or 0,
        "total_integrity_failures": row.total_integrity_failures or 0,
        "total_publications": row.total_publications or 0
    }
