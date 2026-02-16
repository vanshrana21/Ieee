#!/usr/bin/env python3
"""
Create all database tables for the LegalAI application.
Run this script to initialize the database schema.
"""
import asyncio
import sys
import os

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from backend.database import engine
from backend.orm.base import Base
import backend.orm  # Import all models to register them

async def create_tables():
    """Create all tables defined in the ORM."""
    print("Creating database tables...")
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("✓ All tables created successfully")
        
        # List all tables to verify
        from sqlalchemy import text
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = result.fetchall()
        print(f"\n✓ Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_tables())
