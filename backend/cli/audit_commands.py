"""
Phase 12 — Audit CLI Commands

Tournament compliance operations: snapshot, verify, export, certificate
"""
import sys
import asyncio
from typing import Optional
from pathlib import Path


class AuditCommand:
    """Audit CLI command handler for Phase 12."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute(self, args) -> int:
        """Execute audit command."""
        if args.audit_action == "generate":
            return self._generate_snapshot(args)
        elif args.audit_action == "verify":
            return self._verify(args)
        elif args.audit_action == "export":
            return self._export(args)
        elif args.audit_action == "certificate":
            return self._certificate(args)
        else:
            print("Error: Unknown audit action")
            return 1
    
    def _generate_snapshot(self, args) -> int:
        """Generate tournament audit snapshot."""
        tournament_id = args.tournament
        
        print(f"=== Generate Audit Snapshot for Tournament {tournament_id} ===")
        
        if self.dry_run:
            print(f"[DRY RUN] Would generate snapshot for tournament {tournament_id}")
            return 0
        
        try:
            asyncio.run(self._async_generate_snapshot(tournament_id))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_generate_snapshot(self, tournament_id: int) -> None:
        """Async generate tournament audit snapshot."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from backend.services.audit_service import generate_tournament_audit_snapshot
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with AsyncSession(engine) as session:
            # Get admin user ID from environment or use 1
            admin_id = int(os.environ.get("ADMIN_USER_ID", "1"))
            
            result = await generate_tournament_audit_snapshot(
                tournament_id=tournament_id,
                user_id=admin_id,
                db=session
            )
            
            print(f"✓ Snapshot generated")
            print(f"  Tournament ID: {result['tournament_id']}")
            print(f"  Snapshot ID: {result['snapshot_id']}")
            print(f"  Audit Root: {result['audit_root_hash'][:32]}...")
            print(f"  Signature: {result['signature_hmac'][:32]}...")
            print(f"  Is New: {result['is_new']}")
        
        await engine.dispose()
    
    def _verify(self, args) -> int:
        """Verify tournament audit snapshot."""
        tournament_id = args.tournament
        
        print(f"=== Verify Tournament {tournament_id} ===")
        
        if self.dry_run:
            print(f"[DRY RUN] Would verify tournament {tournament_id}")
            return 0
        
        try:
            asyncio.run(self._async_verify(tournament_id))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_verify(self, tournament_id: int) -> None:
        """Async verify tournament snapshot."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from backend.services.audit_service import verify_audit_snapshot
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with AsyncSession(engine) as session:
            result = await verify_audit_snapshot(tournament_id, session)
            
            if not result["snapshot_exists"]:
                print(f"✗ No snapshot found for tournament {tournament_id}")
                return
            
            print(f"\nSnapshot Status: {'✓ Valid' if result['valid'] else '✗ Invalid'}")
            print(f"Tamper Detected: {'✗ YES' if result['tamper_detected'] else '✓ No'}")
            print(f"Signature Valid: {'✓ Yes' if result['signature_valid'] else '✗ No'}")
            
            print(f"\nStored Root:    {result['stored_root'][:32]}...")
            print(f"Recomputed:     {result['recomputed_root'][:32]}...")
            
            if result["details"]:
                print("\nComponent Verification:")
                for component, valid in sorted(result["details"].items()):
                    status = "✓" if valid else "✗"
                    print(f"  {status} {component}")
        
        await engine.dispose()
    
    def _export(self, args) -> int:
        """Export tournament audit bundle."""
        tournament_id = args.tournament
        output = args.output
        
        print(f"=== Export Tournament {tournament_id} ===")
        
        if self.dry_run:
            print(f"[DRY RUN] Would export tournament {tournament_id} to {output}")
            return 0
        
        try:
            asyncio.run(self._async_export(tournament_id, output))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_export(self, tournament_id: int, output_path: str) -> None:
        """Async export tournament bundle."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from backend.services.audit_export_service import export_tournament_bundle
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with AsyncSession(engine) as session:
            bundle_bytes = await export_tournament_bundle(
                tournament_id=tournament_id,
                db=session,
                include_events=True
            )
            
            # Write to file
            output_file = Path(output_path)
            if output_file.is_dir():
                output_file = output_file / f"tournament_{tournament_id}_audit_bundle.zip"
            
            with open(output_file, 'wb') as f:
                f.write(bundle_bytes)
            
            print(f"✓ Bundle exported")
            print(f"  Size: {len(bundle_bytes):,} bytes")
            print(f"  Path: {output_file.absolute()}")
        
        await engine.dispose()
    
    def _certificate(self, args) -> int:
        """Generate tournament certificate."""
        tournament_id = args.tournament
        format_type = args.format
        
        print(f"=== Tournament Certificate {tournament_id} ===")
        
        if self.dry_run:
            print(f"[DRY RUN] Would generate certificate for tournament {tournament_id}")
            return 0
        
        try:
            asyncio.run(self._async_certificate(tournament_id, format_type))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_certificate(self, tournament_id: int, format_type: str) -> None:
        """Async generate certificate."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from backend.services.certificate_service import (
            generate_tournament_certificate,
            format_certificate_text
        )
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with AsyncSession(engine) as session:
            certificate = await generate_tournament_certificate(tournament_id, session)
            
            if format_type == "text":
                print(format_certificate_text(certificate))
            else:
                import json
                print(json.dumps(certificate, indent=2, sort_keys=True))
        
        await engine.dispose()
