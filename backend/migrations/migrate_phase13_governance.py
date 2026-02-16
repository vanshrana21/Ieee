"""
Phase 13 — Institutional Governance & Multi-Tenant SaaS Control Layer

Migration script for hard tenant isolation and governance controls.

Security Level: Maximum
Isolation Level: Hard Multi-Tenant
"""
from sqlalchemy import text, inspect
from backend.database import engine, Base


async def migrate():
    """Execute Phase 13 migration."""
    async with engine.begin() as conn:
        # Check if tables exist
        inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))
        existing_tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names())
        
        # =================================================================
        # 1. institutions (Expanded SaaS Control)
        # =================================================================
        if 'institutions' not in existing_tables:
            await conn.execute(text("""
                CREATE TABLE institutions (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    max_tournaments INTEGER NOT NULL DEFAULT 5,
                    max_concurrent_sessions INTEGER NOT NULL DEFAULT 10,
                    allow_audit_export BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create indexes
            await conn.execute(text("""
                CREATE INDEX idx_institutions_slug ON institutions(slug)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_institutions_status ON institutions(status)
            """))
            
            print("✓ Created institutions table")
        else:
            print("- institutions table already exists")
        
        # =================================================================
        # 2. institution_roles (Separate role control)
        # =================================================================
        if 'institution_roles' not in existing_tables:
            await conn.execute(text("""
                CREATE TABLE institution_roles (
                    id SERIAL PRIMARY KEY,
                    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    role VARCHAR(30) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(institution_id, user_id),
                    CHECK (role IN ('institution_admin', 'faculty', 'judge', 'participant'))
                )
            """))
            
            # Create indexes
            await conn.execute(text("""
                CREATE INDEX idx_institution_roles_institution ON institution_roles(institution_id)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_institution_roles_user ON institution_roles(user_id)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_institution_roles_lookup ON institution_roles(institution_id, user_id, role)
            """))
            
            print("✓ Created institution_roles table")
        else:
            print("- institution_roles table already exists")
        
        # =================================================================
        # 3. institution_audit_log (Append-Only)
        # =================================================================
        if 'institution_audit_log' not in existing_tables:
            await conn.execute(text("""
                CREATE TABLE institution_audit_log (
                    id SERIAL PRIMARY KEY,
                    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
                    actor_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    action_type VARCHAR(50) NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id INTEGER,
                    payload_json JSONB NOT NULL,
                    payload_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create indexes
            await conn.execute(text("""
                CREATE INDEX idx_inst_audit_institution ON institution_audit_log(institution_id)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_inst_audit_actor ON institution_audit_log(actor_user_id)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_inst_audit_created ON institution_audit_log(created_at)
            """))
            await conn.execute(text("""
                CREATE INDEX idx_inst_audit_action ON institution_audit_log(institution_id, action_type, created_at)
            """))
            
            print("✓ Created institution_audit_log table")
        else:
            print("- institution_audit_log table already exists")
        
        # =================================================================
        # 4. Append-Only Triggers
        # =================================================================
        
        # Create trigger function for UPDATE prevention
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_institution_audit_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Institution audit log is append-only: updates not allowed';
            END;
            $$ LANGUAGE plpgsql
        """))
        
        # Create trigger function for DELETE prevention
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_institution_audit_deletion()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Institution audit log is append-only: deletes not allowed';
            END;
            $$ LANGUAGE plpgsql
        """))
        
        # Check if triggers exist before creating
        trigger_check = await conn.execute(text("""
            SELECT trigger_name FROM information_schema.triggers
            WHERE trigger_name IN ('institution_audit_guard_update', 'institution_audit_guard_delete')
            AND event_object_table = 'institution_audit_log'
        """))
        existing_triggers = [row[0] for row in trigger_check.fetchall()]
        
        if 'institution_audit_guard_update' not in existing_triggers:
            await conn.execute(text("""
                CREATE TRIGGER institution_audit_guard_update
                BEFORE UPDATE ON institution_audit_log
                FOR EACH ROW EXECUTE FUNCTION prevent_institution_audit_modification()
            """))
            print("✓ Created UPDATE prevention trigger")
        else:
            print("- UPDATE trigger already exists")
        
        if 'institution_audit_guard_delete' not in existing_triggers:
            await conn.execute(text("""
                CREATE TRIGGER institution_audit_guard_delete
                BEFORE DELETE ON institution_audit_log
                FOR EACH ROW EXECUTE FUNCTION prevent_institution_audit_deletion()
            """))
            print("✓ Created DELETE prevention trigger")
        else:
            print("- DELETE trigger already exists")
        
        # =================================================================
        # 5. Update users table to add super_admin flag
        # =================================================================
        try:
            # Check if column exists
            result = await conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'is_super_admin'
            """))
            
            if not result.fetchone():
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT FALSE
                """))
                
                # Create index
                await conn.execute(text("""
                    CREATE INDEX idx_users_super_admin ON users(is_super_admin)
                """))
                
                print("✓ Added is_super_admin column to users")
            else:
                print("- is_super_admin column already exists")
        except Exception as e:
            print(f"Warning: Could not add super_admin column: {e}")
        
        print("\n=== Phase 13 Migration Complete ===")
        print("Institutional Governance & Multi-Tenant SaaS Control Layer ready.")


async def verify():
    """Verify Phase 13 migration."""
    async with engine.connect() as conn:
        # Verify tables
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name IN ('institutions', 'institution_roles', 'institution_audit_log')
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        
        print("\n=== Verification ===")
        print(f"Tables created: {tables}")
        
        # Verify triggers
        result = await conn.execute(text("""
            SELECT trigger_name FROM information_schema.triggers
            WHERE event_object_table = 'institution_audit_log'
        """))
        triggers = [row[0] for row in result.fetchall()]
        
        print(f"Triggers created: {triggers}")
        
        # Verify columns
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'is_super_admin'
        """))
        
        if result.fetchone():
            print("✓ super_admin column exists in users")
        else:
            print("✗ super_admin column missing")
        
        # Count check constraints
        result = await conn.execute(text("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'institution_roles'::regclass
            AND contype = 'c'
        """))
        constraints = [row[0] for row in result.fetchall()]
        
        print(f"Check constraints: {constraints}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
    asyncio.run(verify())
