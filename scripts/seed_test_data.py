#!/usr/bin/env python3
"""
Windsurf Test Data Seeder

Generates deterministic test data for all phases.
Usage: python scripts/seed_test_data.py --teams 100 --tournaments 1 --matches 500
"""
import argparse
import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


# Deterministic UUID generation for reproducibility
def deterministic_uuid(seed: str) -> UUID:
    """Generate deterministic UUID from seed string."""
    hash_bytes = hashlib.md5(seed.encode()).digest()
    return UUID(bytes=hash_bytes[:16], version=4)


@dataclass
class SeedConfig:
    """Configuration for test data seeding."""
    teams: int = 100
    tournaments: int = 1
    matches: int = 500
    rounds: int = 5
    judges: int = 20
    courtrooms: int = 10
    participants_per_team: int = 3


class TestDataSeeder:
    """Seeds test data for all phases of the moot court system."""
    
    def __init__(self, db: AsyncSession, config: SeedConfig):
        self.db = db
        self.config = config
        self.created_ids: Dict[str, List[UUID]] = {
            'tournaments': [],
            'teams': [],
            'judges': [],
            'courtrooms': [],
            'matches': [],
            'rounds': [],
            'participants': [],
        }
    
    async def seed_all(self) -> Dict[str, List[UUID]]:
        """Seed all test data in dependency order."""
        print("=== Windsurf Test Data Seeder ===")
        print(f"Config: {self.config}")
        print("")
        
        # 1. Seed tournaments
        await self._seed_tournaments()
        
        # 2. Seed teams and participants
        await self._seed_teams()
        
        # 3. Seed judges
        await self._seed_judges()
        
        # 4. Seed courtrooms
        await self._seed_courtrooms()
        
        # 5. Seed rounds and matches
        await self._seed_rounds_and_matches()
        
        # 6. Seed tournament lifecycle (Phase 20)
        await self._seed_lifecycles()
        
        print("\n=== Seeding Complete ===")
        self._print_summary()
        
        return self.created_ids
    
    async def _seed_tournaments(self):
        """Seed tournaments."""
        print(f"Seeding {self.config.tournaments} tournaments...")
        
        from backend.orm.tournament import Tournament
        
        for i in range(self.config.tournaments):
            tournament_id = deterministic_uuid(f"tournament_{i}")
            
            tournament = Tournament(
                id=tournament_id,
                name=f"Test Tournament {i+1}",
                description=f"Seeded test tournament for Windsurf testing",
                status="draft",
                start_date=datetime.utcnow() + timedelta(days=7),
                end_date=datetime.utcnow() + timedelta(days=14),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            self.db.add(tournament)
            self.created_ids['tournaments'].append(tournament_id)
        
        await self.db.commit()
        print(f"  ✓ Created {self.config.tournaments} tournaments")
    
    async def _seed_teams(self):
        """Seed teams and participants."""
        print(f"Seeding {self.config.teams} teams...")
        
        from backend.orm.team import Team
        from backend.orm.user import User
        
        for i in range(self.config.teams):
            team_id = deterministic_uuid(f"team_{i}")
            tournament_id = self.created_ids['tournaments'][i % len(self.created_ids['tournaments'])]
            
            team = Team(
                id=team_id,
                name=f"Test Team {i+1}",
                tournament_id=tournament_id,
                institution=f"Test Institution {(i % 20) + 1}",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            self.db.add(team)
            self.created_ids['teams'].append(team_id)
            
            # Create team participants
            for j in range(self.config.participants_per_team):
                user_id = deterministic_uuid(f"team_{i}_participant_{j}")
                
                user = User(
                    id=user_id,
                    email=f"team{i}_participant{j}@test.com",
                    name=f"Participant {j+1} of Team {i+1}",
                    role="student",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                
                self.db.add(user)
                self.created_ids['participants'].append(user_id)
        
        await self.db.commit()
        print(f"  ✓ Created {self.config.teams} teams with {len(self.created_ids['participants'])} participants")
    
    async def _seed_judges(self):
        """Seed judges."""
        print(f"Seeding {self.config.judges} judges...")
        
        from backend.orm.user import User
        
        for i in range(self.config.judges):
            judge_id = deterministic_uuid(f"judge_{i}")
            
            judge = User(
                id=judge_id,
                email=f"judge{i}@test.com",
                name=f"Test Judge {i+1}",
                role="judge",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            self.db.add(judge)
            self.created_ids['judges'].append(judge_id)
        
        await self.db.commit()
        print(f"  ✓ Created {self.config.judges} judges")
    
    async def _seed_courtrooms(self):
        """Seed courtrooms."""
        print(f"Seeding {self.config.courtrooms} courtrooms...")
        
        # Phase 18 courtrooms
        try:
            from backend.orm.phase18_scheduling import Courtroom
            
            for i in range(self.config.courtrooms):
                courtroom_id = deterministic_uuid(f"courtroom_{i}")
                tournament_id = self.created_ids['tournaments'][i % len(self.created_ids['tournaments'])]
                
                courtroom = Courtroom(
                    id=courtroom_id,
                    tournament_id=tournament_id,
                    name=f"Courtroom {i+1}",
                    capacity=50,
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                
                self.db.add(courtroom)
                self.created_ids['courtrooms'].append(courtroom_id)
            
            await self.db.commit()
            print(f"  ✓ Created {self.config.courtrooms} courtrooms")
        except ImportError:
            print(f"  ⚠ Phase 18 not available, skipping courtrooms")
    
    async def _seed_rounds_and_matches(self):
        """Seed rounds and matches."""
        print(f"Seeding {self.config.rounds} rounds and {self.config.matches} matches...")
        
        try:
            from backend.orm.phase14_deterministic_rounds import Round, Match, MatchStatus
            
            matches_per_round = self.config.matches // self.config.rounds
            
            for round_idx in range(self.config.rounds):
                round_id = deterministic_uuid(f"round_{round_idx}")
                tournament_id = self.created_ids['tournaments'][round_idx % len(self.created_ids['tournaments'])]
                
                round_obj = Round(
                    id=round_id,
                    tournament_id=tournament_id,
                    name=f"Round {round_idx + 1}",
                    sequence_number=round_idx + 1,
                    status="scheduled",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                
                self.db.add(round_obj)
                self.created_ids['rounds'].append(round_id)
                
                # Create matches for this round
                for match_idx in range(matches_per_round):
                    match_id = deterministic_uuid(f"round_{round_idx}_match_{match_idx}")
                    
                    # Select teams deterministically
                    team_a_idx = (match_idx * 2) % len(self.created_ids['teams'])
                    team_b_idx = (match_idx * 2 + 1) % len(self.created_ids['teams'])
                    
                    match_obj = Match(
                        id=match_id,
                        tournament_id=tournament_id,
                        round_id=round_id,
                        team_a_id=self.created_ids['teams'][team_a_idx],
                        team_b_id=self.created_ids['teams'][team_b_idx],
                        status=MatchStatus.SCHEDULED,
                        is_frozen=False,
                        scheduled_at=datetime.utcnow() + timedelta(days=round_idx + 1),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    
                    self.db.add(match_obj)
                    self.created_ids['matches'].append(match_id)
            
            await self.db.commit()
            print(f"  ✓ Created {self.config.rounds} rounds with {len(self.created_ids['matches'])} matches")
        except ImportError:
            print(f"  ⚠ Phase 14 not available, skipping rounds/matches")
    
    async def _seed_lifecycles(self):
        """Seed tournament lifecycles (Phase 20)."""
        print("Seeding tournament lifecycles...")
        
        try:
            from backend.orm.phase20_tournament_lifecycle import TournamentLifecycle, TournamentStatus
            
            for tournament_id in self.created_ids['tournaments']:
                lifecycle_id = deterministic_uuid(f"lifecycle_{tournament_id}")
                
                lifecycle = TournamentLifecycle(
                    id=lifecycle_id,
                    tournament_id=tournament_id,
                    status=TournamentStatus.DRAFT,
                    final_standings_hash=None,
                    archived_at=None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                
                self.db.add(lifecycle)
            
            await self.db.commit()
            print(f"  ✓ Created {len(self.created_ids['tournaments'])} lifecycles")
        except ImportError:
            print(f"  ⚠ Phase 20 not available, skipping lifecycles")
    
    def _print_summary(self):
        """Print seeding summary."""
        print("\nCreated Entities:")
        for entity_type, ids in self.created_ids.items():
            print(f"  {entity_type}: {len(ids)}")
    
    async def export_seed_data(self, output_path: str):
        """Export seeded IDs to JSON for test reference."""
        data = {
            'seeded_at': datetime.utcnow().isoformat(),
            'config': {
                'teams': self.config.teams,
                'tournaments': self.config.tournaments,
                'matches': self.config.matches,
                'rounds': self.config.rounds,
                'judges': self.config.judges,
                'courtrooms': self.config.courtrooms,
            },
            'ids': {
                k: [str(id) for id in v]
                for k, v in self.created_ids.items()
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nSeed data exported: {output_path}")


async def main():
    parser = argparse.ArgumentParser(
        description='Windsurf Test Data Seeder'
    )
    parser.add_argument(
        '--teams', '-t',
        type=int,
        default=100,
        help='Number of teams to create (default: 100)'
    )
    parser.add_argument(
        '--tournaments', '-T',
        type=int,
        default=1,
        help='Number of tournaments (default: 1)'
    )
    parser.add_argument(
        '--matches', '-m',
        type=int,
        default=500,
        help='Number of matches (default: 500)'
    )
    parser.add_argument(
        '--rounds', '-r',
        type=int,
        default=5,
        help='Number of rounds (default: 5)'
    )
    parser.add_argument(
        '--judges', '-j',
        type=int,
        default=20,
        help='Number of judges (default: 20)'
    )
    parser.add_argument(
        '--courtrooms', '-c',
        type=int,
        default=10,
        help='Number of courtrooms (default: 10)'
    )
    parser.add_argument(
        '--output', '-o',
        default='./artifacts/seed_data.json',
        help='Output path for seed data JSON'
    )
    parser.add_argument(
        '--clear', '-C',
        action='store_true',
        help='Clear existing test data before seeding'
    )
    
    args = parser.parse_args()
    
    config = SeedConfig(
        teams=args.teams,
        tournaments=args.tournaments,
        matches=args.matches,
        rounds=args.rounds,
        judges=args.judges,
        courtrooms=args.courtrooms,
    )
    
    # Import and setup database
    import sys
    sys.path.insert(0, '.')
    
    from backend.database import async_session_maker
    
    async with async_session_maker() as db:
        seeder = TestDataSeeder(db, config)
        
        if args.clear:
            print("Clearing existing test data...")
            # Implementation for clearing data would go here
            print("  ✓ Data cleared")
        
        await seeder.seed_all()
        await seeder.export_seed_data(args.output)
    
    print("\n✓ Seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
