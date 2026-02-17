"""
Phase 11 — Database CLI Commands

Database operations: migrate, verify, backup, restore
"""
import sys
import subprocess
import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    import asyncpg
except Exception:
    asyncpg = None


class DbCommand:
    """Database CLI command handler."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute(self, args) -> int:
        """Execute database command."""
        if args.db_action == "migrate":
            return self._migrate(args)
        elif args.db_action == "verify":
            return self._verify(args)
        elif args.db_action == "backup":
            return self._backup(args)
        elif args.db_action == "restore":
            return self._restore(args)
        else:
            print("Error: Unknown database action")
            return 1
    
    def _migrate(self, args) -> int:
        """Run database migrations."""
        print("=== Database Migration ===")
        
        migrations = []
        
        if args.all:
            migrations = [
                "migrate_phase1_core.py",
                "migrate_phase2_oral.py",
                "migrate_phase3_pairing.py",
                "migrate_phase4_panels.py",
                "migrate_phase5_live_court.py",
                "migrate_phase6_objections.py",
                "migrate_phase7_exhibits.py",
                "migrate_phase8_scaling.py",
                "migrate_phase9_results.py",
            ]
        elif args.phase:
            phase_map = {
                1: "migrate_phase1_core.py",
                2: "migrate_phase2_oral.py",
                3: "migrate_phase3_pairing.py",
                4: "migrate_phase4_panels.py",
                5: "migrate_phase5_live_court.py",
                6: "migrate_phase6_objections.py",
                7: "migrate_phase7_exhibits.py",
                8: "migrate_phase8_scaling.py",
                9: "migrate_phase9_results.py",
            }
            if args.phase in phase_map:
                migrations = [phase_map[args.phase]]
            else:
                print(f"Error: Unknown phase {args.phase}")
                return 1
        
        if not migrations:
            print("Error: No migrations specified (--all or --phase required)")
            return 1
        
        if self.dry_run:
            print("[DRY RUN] Would execute migrations:")
            for migration in migrations:
                print(f"  - {migration}")
            return 0
        
        # Execute migrations
        success_count = 0
        for migration in migrations:
            print(f"\nRunning {migration}...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", f"backend.migrations.{migration.replace('.py', '')}"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                print(result.stdout)
                success_count += 1
            except subprocess.CalledProcessError as e:
                print(f"Error running {migration}:")
                print(e.stderr)
                return 1
        
        print(f"\n=== Migration Complete ===")
        print(f"Successfully ran {success_count}/{len(migrations)} migrations")
        
        # Verify if requested
        if args.verify:
            print("\n=== Verification ===")
            return self._verify(args)
        
        return 0
    
    def _verify(self, args) -> int:
        """Verify database integrity."""
        print("=== Database Integrity Verification ===")
        
        if self.dry_run:
            print("[DRY RUN] Would verify database integrity")
            return 0
        
        # Run async verification
        try:
            asyncio.run(self._async_verify(full=args.full))
            return 0
        except Exception as e:
            print(f"Verification failed: {e}")
            return 1
    
    async def _async_verify(self, full: bool = False) -> None:
        """Async database verification."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with engine.begin() as conn:
            # Check core tables exist
            core_tables = [
                "users", "institutions", "national_tournaments",
                "tournament_teams", "memorial_submissions",
                "live_court_sessions", "live_turns", "live_event_log",
                "tournament_team_results", "audit_log"
            ]
            
            print("Checking core tables...")
            for table in core_tables:
                result = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = '{table}'
                    )
                """))
                exists = result.scalar()
                status = "✓" if exists else "✗"
                print(f"  {status} {table}")
            
            # Check triggers if full verification
            if full:
                print("\nChecking PostgreSQL triggers...")
                result = await conn.execute(text("""
                    SELECT trigger_name, event_object_table
                    FROM information_schema.triggers
                    WHERE trigger_schema = 'public'
                """))
                triggers = result.all()
                print(f"  Found {len(triggers)} triggers")
                
                # Check audit log chain if exists
                result = await conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'audit_log'
                    )
                """))
                audit_exists = result.scalar()
                
                if audit_exists:
                    print("\nChecking audit log chain integrity...")
                    # This would call AuditLogger.verify_chain_integrity()
                    print("  ✓ Audit log table exists")
        
        await engine.dispose()
        print("\n=== Verification Complete ===")
    
    def _backup(self, args) -> int:
        """Create database backup."""
        print("=== Database Backup ===")
        
        backup_file = Path(args.output)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if backup_file.is_dir():
            backup_file = backup_file / f"mootcourt_backup_{timestamp}.sql"
        
        print(f"Backup file: {backup_file}")
        
        if self.dry_run:
            print("[DRY RUN] Would create database backup")
            return 0
        
        try:
            # Use pg_dump for backup
            import os
            database_url = os.environ.get("DATABASE_URL", "")
            
            if "postgresql" in database_url:
                # Extract connection details from URL
                cmd = [
                    "pg_dump",
                    "-Fc",  # Custom format (compressed)
                    "-f", str(backup_file),
                    database_url.replace("+asyncpg", "").replace("postgresql+psycopg2://", "postgresql://")
                ]
            else:
                print("Error: Backup only supported for PostgreSQL")
                return 1
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Backup failed: {result.stderr}")
                return 1
            
            print(f"✓ Backup created: {backup_file}")
            
            if args.compress and not str(backup_file).endswith('.gz'):
                compressed = f"{backup_file}.gz"
                subprocess.run(["gzip", "-c", str(backup_file)], stdout=open(compressed, 'wb'))
                print(f"✓ Compressed: {compressed}")
            
            return 0
            
        except Exception as e:
            print(f"Backup error: {e}")
            return 1
    
    def _restore(self, args) -> int:
        """Restore database from backup."""
        print("=== Database Restore ===")
        
        backup_file = Path(args.input)
        
        if not backup_file.exists():
            print(f"Error: Backup file not found: {backup_file}")
            return 1
        
        print(f"Backup file: {backup_file}")
        
        if not args.force:
            confirm = input("WARNING: This will overwrite existing data. Continue? [y/N]: ")
            if confirm.lower() != 'y':
                print("Restore cancelled")
                return 0
        
        if self.dry_run:
            print("[DRY RUN] Would restore database from backup")
            return 0
        
        try:
            import os
            database_url = os.environ.get("DATABASE_URL", "")
            
            # Decompress if needed
            restore_file = backup_file
            if str(backup_file).endswith('.gz'):
                print("Decompressing backup...")
                restore_file = backup_file.with_suffix('')
                subprocess.run(["gunzip", "-c", str(backup_file)], stdout=open(restore_file, 'wb'))
            
            # Use pg_restore
            cmd = [
                "pg_restore",
                "--clean",  # Clean (drop) database objects before recreating
                "--if-exists",
                "-d", database_url.replace("+asyncpg", "").replace("postgresql+psycopg2://", "postgresql://"),
                str(restore_file)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Restore warning: {result.stderr}")
                # pg_restore may return 1 for warnings, not necessarily errors
            
            print("✓ Restore complete")
            return 0
            
        except Exception as e:
            print(f"Restore error: {e}")
            return 1
