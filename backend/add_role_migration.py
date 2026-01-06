"""
Database migration script to add role column to users table

Run this script once to update your existing database:
python add_role_migration.py

This will:
1. Add the 'role' column to the users table
2. Set a default role for existing users (you can change this)
3. Make the role column non-nullable
"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def migrate():
    """Add role column to users table"""
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        print("Starting migration...")
        
        # Step 1: Add role column as nullable first
        print("Adding role column...")
        await conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS role VARCHAR(20)
        """))
        
        # Step 2: Set default role for existing users
        # You can change 'lawyer' to 'student' if most existing users are students
        print("Setting default role for existing users...")
        await conn.execute(text("""
            UPDATE users 
            SET role = 'lawyer' 
            WHERE role IS NULL
        """))
        
        # Step 3: Make role non-nullable
        print("Making role column non-nullable...")
        await conn.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN role SET NOT NULL
        """))
        
        # Step 4: Add index on role for faster queries
        print("Adding index on role...")
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_role 
            ON users(role)
        """))
        
        print("Migration completed successfully!")
        
        # Verify the changes
        result = await conn.execute(text("""
            SELECT COUNT(*), role 
            FROM users 
            GROUP BY role
        """))
        
        print("\nUser count by role:")
        for row in result:
            print(f"  {row[1]}: {row[0]} users")
    
    await engine.dispose()

if __name__ == "__main__":
    print("=" * 60)
    print("ROLE MIGRATION SCRIPT")
    print("=" * 60)
    print("\nThis will add a 'role' column to your users table.")
    print("All existing users will be set to 'lawyer' by default.")
    print("\nPress Ctrl+C to cancel, or press Enter to continue...")
    
    try:
        input()
        asyncio.run(migrate())
    except KeyboardInterrupt:
        print("\nMigration cancelled.")