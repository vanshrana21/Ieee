"""
Phase 11 — Tournament CLI Commands

Tournament management: list, finalize, results
"""
import sys
import asyncio
from typing import Optional


class TournamentCommand:
    """Tournament CLI command handler."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute(self, args) -> int:
        """Execute tournament command."""
        if args.tournament_action == "list":
            return self._list(args)
        elif args.tournament_action == "finalize":
            return self._finalize(args)
        elif args.tournament_action == "results":
            return self._results(args)
        else:
            print("Error: Unknown tournament action")
            return 1
    
    def _list(self, args) -> int:
        """List tournaments."""
        print("=== Tournaments ===")
        
        try:
            asyncio.run(self._async_list(status=args.status))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_list(self, status: Optional[str] = None) -> None:
        """Async list tournaments."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import select
        from backend.orm.national_network import NationalTournament
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with engine.connect() as conn:
            query = select(NationalTournament)
            
            if status:
                # Add status filter if implemented
                pass
            
            result = await conn.execute(query)
            tournaments = result.all()
            
            if not tournaments:
                print("No tournaments found")
                return
            
            print(f"\n{'ID':<5} {'Name':<40} {'Status':<10}")
            print("-" * 60)
            
            for t in tournaments:
                # Determine status based on dates
                tournament_status = "active"  # Simplified
                print(f"{t.id:<5} {t.name[:38]:<40} {tournament_status:<10}")
        
        await engine.dispose()
    
    def _finalize(self, args) -> int:
        """Finalize tournament results."""
        tournament_id = args.id
        admin_id = args.admin_id
        
        print(f"=== Finalize Tournament {tournament_id} ===")
        
        if self.dry_run:
            print(f"[DRY RUN] Would finalize tournament {tournament_id}")
            return 0
        
        try:
            asyncio.run(self._async_finalize(tournament_id, admin_id))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_finalize(self, tournament_id: int, admin_id: int) -> None:
        """Async finalize tournament."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with AsyncSession(engine) as session:
            try:
                from backend.services.results_service import finalize_tournament_results
                
                freeze = await finalize_tournament_results(
                    tournament_id=tournament_id,
                    user_id=admin_id,
                    db=session
                )
                
                print(f"✓ Tournament {tournament_id} finalized")
                print(f"  Frozen at: {freeze.frozen_at}")
                print(f"  Checksum: {freeze.results_checksum[:16]}...")
                
            except Exception as e:
                print(f"✗ Finalization failed: {e}")
                raise
        
        await engine.dispose()
    
    def _results(self, args) -> int:
        """Show tournament results."""
        tournament_id = args.id
        
        print(f"=== Tournament {tournament_id} Results ===")
        
        try:
            asyncio.run(self._async_results(tournament_id, verify=args.verify))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_results(self, tournament_id: int, verify: bool = False) -> None:
        """Async get tournament results."""
        import os
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import select
        from backend.orm.tournament_results import TournamentTeamResult, TournamentResultsFreeze
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        async with engine.connect() as conn:
            # Check if frozen
            result = await conn.execute(
                select(TournamentResultsFreeze)
                .where(TournamentResultsFreeze.tournament_id == tournament_id)
            )
            freeze = result.scalar_one_or_none()
            
            if not freeze:
                print("Tournament not yet finalized")
                return
            
            print(f"\nFrozen at: {freeze.frozen_at}")
            print(f"Checksum: {freeze.results_checksum}")
            
            # Get team results
            result = await conn.execute(
                select(TournamentTeamResult)
                .where(TournamentTeamResult.tournament_id == tournament_id)
                .order_by(TournamentTeamResult.final_rank.asc())
            )
            team_results = result.all()
            
            if not team_results:
                print("No results found")
                return
            
            print(f"\n{'Rank':<6} {'Team':<8} {'Score':<10} {'SOS':<10} {'Hash':<20}")
            print("-" * 60)
            
            for tr in team_results:
                print(f"{tr.final_rank:<6} {tr.team_id:<8} {float(tr.total_score):<10.2f} {float(tr.strength_of_schedule):<10.4f} {tr.result_hash[:18]}...")
            
            # Verify if requested
            if verify:
                print("\n=== Integrity Verification ===")
                
                all_valid = True
                for tr in team_results:
                    computed = tr.compute_hash()
                    if computed != tr.result_hash:
                        print(f"✗ Team {tr.team_id}: Hash mismatch!")
                        all_valid = False
                
                if all_valid:
                    print("✓ All result hashes valid")
        
        await engine.dispose()
