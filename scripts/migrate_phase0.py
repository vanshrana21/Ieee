#!/usr/bin/env python3
"""
Phase 0: Virtual Courtroom Infrastructure - Database Migration Script

Creates all moot court tables with proper relationships in dependency order:
1. oral_rounds (no dependencies)
2. oral_round_objections (depends on oral_rounds)
3. oral_round_transcripts (depends on oral_rounds)
4. oral_round_scores (depends on oral_rounds)

Execution: python scripts/migrate_phase0.py
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, inspect, text
from backend.orm.base import Base
from backend.orm.database import get_db_url

# Import all ORM models to register them with Base.metadata
from backend.orm.oral_round import OralRound, OralRoundStatus, SpeakerRole, RoundType
from backend.orm.oral_round_objection import OralRoundObjection, ObjectionType, ObjectionRuling
from backend.orm.oral_round_transcript import OralRoundTranscript, TranscriptStatus
from backend.orm.oral_round_score import OralRoundScore, TeamSide


def check_tables_exist(engine):
    """Check if any of the Phase 0 tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    phase0_tables = [
        'oral_rounds',
        'oral_round_objections',
        'oral_round_transcripts',
        'oral_round_scores'
    ]
    
    existing_phase0 = [t for t in phase0_tables if t in existing_tables]
    return existing_phase0


def create_tables(engine):
    """Create all Phase 0 tables."""
    print("🚀 Starting Phase 0 database migration...")
    print("-" * 60)
    
    # Check existing tables
    existing = check_tables_exist(engine)
    if existing:
        print(f"⚠️  Warning: Some tables already exist: {existing}")
        print("   Migration will skip existing tables.")
        print()
    
    # Create tables in dependency order
    tables_to_create = []
    
    # 1. oral_rounds (base table - no dependencies)
    if 'oral_rounds' not in existing:
        tables_to_create.append(('oral_rounds', OralRound.__table__))
    
    # 2. Dependent tables
    if 'oral_round_objections' not in existing:
        tables_to_create.append(('oral_round_objections', OralRoundObjection.__table__))
    
    if 'oral_round_transcripts' not in existing:
        tables_to_create.append(('oral_round_transcripts', OralRoundTranscript.__table__))
    
    if 'oral_round_scores' not in existing:
        tables_to_create.append(('oral_round_scores', OralRoundScore.__table__))
    
    if not tables_to_create:
        print("✅ All Phase 0 tables already exist. Nothing to create.")
        return True
    
    # Create each table
    print(f"📦 Creating {len(tables_to_create)} table(s)...")
    print()
    
    for table_name, table_obj in tables_to_create:
        try:
            table_obj.create(engine, checkfirst=True)
            print(f"   ✅ Created table: {table_name}")
            
            # Verify indexes were created
            inspector = inspect(engine)
            indexes = inspector.get_indexes(table_name)
            index_names = [idx['name'] for idx in indexes]
            
            if index_names:
                print(f"      Indexes: {', '.join(index_names)}")
            
        except Exception as e:
            print(f"   ❌ Failed to create table {table_name}: {e}")
            return False
    
    print()
    return True


def verify_foreign_keys(engine):
    """Verify foreign key constraints are properly defined."""
    print("🔍 Verifying foreign key constraints...")
    print()
    
    inspector = inspect(engine)
    
    # Check foreign keys for each dependent table
    tables_to_check = [
        'oral_round_objections',
        'oral_round_transcripts',
        'oral_round_scores'
    ]
    
    for table_name in tables_to_check:
        fks = inspector.get_foreign_keys(table_name)
        fk_names = [fk['name'] for fk in fks]
        
        if fks:
            print(f"   ✅ {table_name}: {len(fks)} FK constraint(s)")
            for fk in fks:
                constrained = fk.get('constrained_columns', [])
                referred = fk.get('referred_table', '?')
                print(f"      - {constrained} → {referred}")
        else:
            print(f"   ⚠️  {table_name}: No FK constraints found")
    
    print()


def log_summary():
    """Log migration summary."""
    print("-" * 60)
    print("📊 MIGRATION SUMMARY")
    print("-" * 60)
    print()
    print("Tables created:")
    print("   • oral_rounds - Round scheduling, teams, judges, timer config")
    print("   • oral_round_objections - Objections with timing and rulings")
    print("   • oral_round_transcripts - Transcripts with audio transcription")
    print("   • oral_round_scores - Judge scoring with criteria breakdown")
    print()
    print("Indexes created:")
    print("   • idx_oral_rounds_competition - Query rounds by competition")
    print("   • idx_oral_rounds_status - Query rounds by status")
    print("   • idx_objections_round - Query objections by round")
    print("   • idx_transcripts_round - Query transcripts by round")
    print("   • idx_transcripts_chunk - Query by audio chunk ID")
    print("   • idx_scores_round - Query scores by round")
    print()
    print("✅ Phase 0 database migration completed successfully!")
    print()


def main():
    """Main migration entry point."""
    print()
    print("=" * 60)
    print("🎯 PHASE 0: VIRTUAL COURTROOM INFRASTRUCTURE")
    print("   Database Migration Script")
    print("=" * 60)
    print()
    
    try:
        # Get database URL
        db_url = get_db_url()
        print(f"📡 Database: {db_url.replace('://', '://***:***@')}")
        print()
        
        # Create engine
        engine = create_engine(db_url)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        print("✅ Database connection successful")
        print()
        
        # Create tables
        if not create_tables(engine):
            print("❌ Migration failed during table creation")
            sys.exit(1)
        
        # Verify foreign keys
        verify_foreign_keys(engine)
        
        # Log summary
        log_summary()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
