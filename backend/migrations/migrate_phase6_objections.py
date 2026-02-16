"""
Phase 6 — Objection & Procedural Control Engine Migration

Creates:
- PostgreSQL ENUMs: objectiontype, objectionstate
- live_objections table with cryptographic hash
- Partial unique index for single pending objection
- PostgreSQL triggers for immutability
- Adds is_timer_paused to live_turns
"""
import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)


def migrate_phase6_objections(engine):
    """
    Execute Phase 6 migration for Objection & Procedural Control Engine.
    """
    with engine.connect() as conn:
        inspector = inspect(engine)
        dialect = engine.dialect.name
        
        # =====================================================================
        # PostgreSQL: Create ENUMs
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Creating PostgreSQL ENUM types...")
            
            # Check if objectiontype exists
            result = conn.execute(text("""
                SELECT 1 FROM pg_type WHERE typname = 'objectiontype'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TYPE objectiontype AS ENUM (
                        'leading',
                        'irrelevant',
                        'misrepresentation',
                        'speculation',
                        'procedural'
                    )
                """))
                logger.info("Created objectiontype ENUM")
            
            # Check if objectionstate exists
            result = conn.execute(text("""
                SELECT 1 FROM pg_type WHERE typname = 'objectionstate'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TYPE objectionstate AS ENUM (
                        'pending',
                        'sustained',
                        'overruled'
                    )
                """))
                logger.info("Created objectionstate ENUM")
            
            conn.commit()
        
        # =====================================================================
        # Add is_timer_paused to live_turns (Phase 6 enhancement)
        # =====================================================================
        logger.info("Adding is_timer_paused to live_turns...")
        columns = [c['name'] for c in inspector.get_columns('live_turns')]
        
        if 'is_timer_paused' not in columns:
            if dialect == 'postgresql':
                conn.execute(text("""
                    ALTER TABLE live_turns
                    ADD COLUMN is_timer_paused BOOLEAN NOT NULL DEFAULT FALSE
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE live_turns
                    ADD COLUMN is_timer_paused BOOLEAN DEFAULT 0
                """))
            logger.info("Added is_timer_paused column")
            conn.commit()
        
        # =====================================================================
        # Create live_objections table
        # =====================================================================
        logger.info("Creating live_objections table...")
        
        if 'live_objections' not in inspector.get_table_names():
            if dialect == 'postgresql':
                conn.execute(text("""
                    CREATE TABLE live_objections (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
                        turn_id INTEGER NOT NULL REFERENCES live_turns(id) ON DELETE RESTRICT,
                        raised_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                        ruled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        objection_type objectiontype NOT NULL,
                        state objectionstate NOT NULL DEFAULT 'pending',
                        reason_text VARCHAR(500),
                        ruling_reason_text VARCHAR(500),
                        raised_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        ruled_at TIMESTAMP,
                        objection_hash VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                """))
            else:
                # SQLite fallback with TEXT for ENUMs
                conn.execute(text("""
                    CREATE TABLE live_objections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
                        turn_id INTEGER NOT NULL REFERENCES live_turns(id) ON DELETE RESTRICT,
                        raised_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                        ruled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        objection_type VARCHAR(20) NOT NULL,
                        state VARCHAR(20) NOT NULL DEFAULT 'pending',
                        reason_text VARCHAR(500),
                        ruling_reason_text VARCHAR(500),
                        raised_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        ruled_at TIMESTAMP,
                        objection_hash VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        
                        CHECK (objection_type IN ('leading', 'irrelevant', 'misrepresentation', 'speculation', 'procedural')),
                        CHECK (state IN ('pending', 'sustained', 'overruled'))
                    )
                """))
            logger.info("Created live_objections table")
            conn.commit()
        
        # =====================================================================
        # Create indexes
        # =====================================================================
        logger.info("Creating indexes...")
        
        indexes = inspector.get_indexes('live_objections') if 'live_objections' in inspector.get_table_names() else []
        index_names = [i['name'] for i in indexes]
        
        # Session index
        if 'idx_objection_session' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_objection_session ON live_objections(session_id)
            """))
            logger.info("Created idx_objection_session")
        
        # Turn index
        if 'idx_objection_turn' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_objection_turn ON live_objections(turn_id)
            """))
            logger.info("Created idx_objection_turn")
        
        # State index
        if 'idx_objection_state' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_objection_state ON live_objections(state)
            """))
            logger.info("Created idx_objection_state")
        
        conn.commit()
        
        # =====================================================================
        # PostgreSQL: Partial unique index for single pending objection
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Creating partial unique index...")
            
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE indexname = 'uq_single_pending_objection'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE UNIQUE INDEX uq_single_pending_objection
                    ON live_objections(turn_id)
                    WHERE state = 'pending'
                """))
                logger.info("Created uq_single_pending_objection index")
                conn.commit()
        
        # =====================================================================
        # PostgreSQL: Immutability Triggers
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Creating PostgreSQL triggers...")
            
            # Function to prevent objection modification if session completed
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION prevent_objection_modification_if_completed()
                RETURNS TRIGGER AS $$
                DECLARE
                    v_status livecourtstatus;
                BEGIN
                    SELECT status INTO v_status
                    FROM live_court_sessions
                    WHERE id = NEW.session_id;
                    
                    IF v_status = 'completed' THEN
                        RAISE EXCEPTION 'Cannot modify objection after session completed';
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))
            
            # Attach BEFORE INSERT
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'objection_insert_guard'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER objection_insert_guard
                    BEFORE INSERT ON live_objections
                    FOR EACH ROW EXECUTE FUNCTION prevent_objection_modification_if_completed()
                """))
                logger.info("Created objection_insert_guard trigger")
            
            # Attach BEFORE UPDATE
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'objection_update_guard'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER objection_update_guard
                    BEFORE UPDATE ON live_objections
                    FOR EACH ROW EXECUTE FUNCTION prevent_objection_modification_if_completed()
                """))
                logger.info("Created objection_update_guard trigger")
            
            # Function to block delete after ruling
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION prevent_objection_delete_after_ruling()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF OLD.state IN ('sustained', 'overruled') THEN
                        RAISE EXCEPTION 'Cannot delete objection after ruling';
                    END IF;
                    
                    -- Also check session status
                    DECLARE
                        v_status livecourtstatus;
                    BEGIN
                        SELECT status INTO v_status
                        FROM live_court_sessions
                        WHERE id = OLD.session_id;
                        
                        IF v_status = 'completed' THEN
                            RAISE EXCEPTION 'Cannot delete objection after session completed';
                        END IF;
                    END;
                    
                    RETURN OLD;
                END;
                $$ LANGUAGE plpgsql
            """))
            
            # Attach BEFORE DELETE
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'objection_delete_guard'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER objection_delete_guard
                    BEFORE DELETE ON live_objections
                    FOR EACH ROW EXECUTE FUNCTION prevent_objection_delete_after_ruling()
                """))
                logger.info("Created objection_delete_guard trigger")
            
            conn.commit()
        
        logger.info("Phase 6 migration completed successfully")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/Users/vanshrana/Desktop/IEEE')
    
    from backend.database import engine
    migrate_phase6_objections(engine)
