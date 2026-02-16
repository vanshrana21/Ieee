"""
Phase 7 — Evidence & Exhibit Management Layer Migration

Creates:
- PostgreSQL ENUM: exhibitstate
- session_exhibits table with cryptographic hash
- Unique deterministic numbering index
- PostgreSQL triggers for immutability
"""
import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)


def migrate_phase7_exhibits(engine):
    """
    Execute Phase 7 migration for Evidence & Exhibit Management Layer.
    """
    with engine.connect() as conn:
        inspector = inspect(engine)
        dialect = engine.dialect.name
        
        # =====================================================================
        # PostgreSQL: Create ENUMs
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Creating PostgreSQL ENUM types...")
            
            # Check if exhibitstate exists
            result = conn.execute(text("""
                SELECT 1 FROM pg_type WHERE typname = 'exhibitstate'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TYPE exhibitstate AS ENUM (
                        'uploaded',
                        'marked',
                        'tendered',
                        'admitted',
                        'rejected'
                    )
                """))
                logger.info("Created exhibitstate ENUM")
            
            conn.commit()
        
        # =====================================================================
        # Create session_exhibits table
        # =====================================================================
        logger.info("Creating session_exhibits table...")
        
        if 'session_exhibits' not in inspector.get_table_names():
            if dialect == 'postgresql':
                conn.execute(text("""
                    CREATE TABLE session_exhibits (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
                        turn_id INTEGER REFERENCES live_turns(id) ON DELETE RESTRICT,
                        institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
                        side oralside NOT NULL,
                        exhibit_number INTEGER NOT NULL,
                        original_filename VARCHAR(255) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        file_hash_sha256 VARCHAR(64) NOT NULL,
                        state exhibitstate NOT NULL DEFAULT 'uploaded',
                        marked_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                        ruled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        marked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ruled_at TIMESTAMP,
                        exhibit_hash VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        
                        UNIQUE(session_id, side, exhibit_number)
                    )
                """))
            else:
                # SQLite fallback with TEXT for ENUMs
                conn.execute(text("""
                    CREATE TABLE session_exhibits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL REFERENCES live_court_sessions(id) ON DELETE RESTRICT,
                        turn_id INTEGER REFERENCES live_turns(id) ON DELETE RESTRICT,
                        institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
                        side VARCHAR(20) NOT NULL,
                        exhibit_number INTEGER NOT NULL,
                        original_filename VARCHAR(255) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        file_hash_sha256 VARCHAR(64) NOT NULL,
                        state VARCHAR(20) NOT NULL DEFAULT 'uploaded',
                        marked_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                        ruled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        marked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ruled_at TIMESTAMP,
                        exhibit_hash VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        
                        UNIQUE(session_id, side, exhibit_number),
                        
                        CHECK (side IN ('petitioner', 'respondent')),
                        CHECK (state IN ('uploaded', 'marked', 'tendered', 'admitted', 'rejected'))
                    )
                """))
            logger.info("Created session_exhibits table")
            conn.commit()
        
        # =====================================================================
        # Create indexes
        # =====================================================================
        logger.info("Creating indexes...")
        
        indexes = inspector.get_indexes('session_exhibits') if 'session_exhibits' in inspector.get_table_names() else []
        index_names = [i['name'] for i in indexes]
        
        # Session index
        if 'idx_exhibit_session' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_exhibit_session ON session_exhibits(session_id)
            """))
            logger.info("Created idx_exhibit_session")
        
        # Turn index
        if 'idx_exhibit_turn' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_exhibit_turn ON session_exhibits(turn_id)
            """))
            logger.info("Created idx_exhibit_turn")
        
        # State index
        if 'idx_exhibit_state' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_exhibit_state ON session_exhibits(state)
            """))
            logger.info("Created idx_exhibit_state")
        
        # Institution index
        if 'idx_exhibit_institution' not in index_names:
            conn.execute(text("""
                CREATE INDEX idx_exhibit_institution ON session_exhibits(institution_id)
            """))
            logger.info("Created idx_exhibit_institution")
        
        conn.commit()
        
        # =====================================================================
        # PostgreSQL: Unique deterministic numbering index
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Verifying unique numbering index...")
            
            # The UNIQUE constraint already covers this, but let's verify
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE indexname = 'u_q_session_exhibits_session_id_side_exhibit_number'
            """))
            if result.scalar():
                logger.info("Unique numbering index exists")
        
        # =====================================================================
        # PostgreSQL: Immutability Triggers
        # =====================================================================
        if dialect == 'postgresql':
            logger.info("Creating PostgreSQL triggers...")
            
            # Function to prevent exhibit modification if session completed
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION prevent_exhibit_modification_if_session_completed()
                RETURNS TRIGGER AS $$
                DECLARE
                    v_status livecourtstatus;
                BEGIN
                    SELECT status INTO v_status
                    FROM live_court_sessions
                    WHERE id = NEW.session_id;
                    
                    IF v_status = 'completed' THEN
                        RAISE EXCEPTION 'Cannot modify exhibit after session completion';
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))
            
            # Attach BEFORE INSERT
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'exhibit_insert_guard'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER exhibit_insert_guard
                    BEFORE INSERT ON session_exhibits
                    FOR EACH ROW EXECUTE FUNCTION prevent_exhibit_modification_if_session_completed()
                """))
                logger.info("Created exhibit_insert_guard trigger")
            
            # Attach BEFORE UPDATE
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'exhibit_update_guard_session'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER exhibit_update_guard_session
                    BEFORE UPDATE ON session_exhibits
                    FOR EACH ROW EXECUTE FUNCTION prevent_exhibit_modification_if_session_completed()
                """))
                logger.info("Created exhibit_update_guard_session trigger")
            
            # Function to prevent modification after ruling
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION prevent_exhibit_modification_after_ruling()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF OLD.state IN ('admitted', 'rejected') THEN
                        RAISE EXCEPTION 'Exhibit locked after ruling';
                    END IF;
                    
                    -- Also check session status
                    DECLARE
                        v_status livecourtstatus;
                    BEGIN
                        SELECT status INTO v_status
                        FROM live_court_sessions
                        WHERE id = OLD.session_id;
                        
                        IF v_status = 'completed' THEN
                            RAISE EXCEPTION 'Cannot modify exhibit after session completion';
                        END IF;
                    END;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))
            
            # Attach BEFORE UPDATE for ruling protection
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'exhibit_update_guard_ruling'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER exhibit_update_guard_ruling
                    BEFORE UPDATE ON session_exhibits
                    FOR EACH ROW EXECUTE FUNCTION prevent_exhibit_modification_after_ruling()
                """))
                logger.info("Created exhibit_update_guard_ruling trigger")
            
            # Attach BEFORE DELETE
            result = conn.execute(text("""
                SELECT 1 FROM pg_trigger WHERE tgname = 'exhibit_delete_guard'
            """))
            if result.scalar() is None:
                conn.execute(text("""
                    CREATE TRIGGER exhibit_delete_guard
                    BEFORE DELETE ON session_exhibits
                    FOR EACH ROW EXECUTE FUNCTION prevent_exhibit_modification_after_ruling()
                """))
                logger.info("Created exhibit_delete_guard trigger")
            
            conn.commit()
        
        logger.info("Phase 7 migration completed successfully")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/Users/vanshrana/Desktop/IEEE')
    
    from backend.database import engine
    migrate_phase7_exhibits(engine)
