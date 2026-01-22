import asyncio
from sqlalchemy import select
from backend.database import init_db, get_db, SessionLocal
from backend.orm.unit import Unit

async def test():
    await init_db()
    async with SessionLocal() as db:
        stmt = select(Unit).limit(5)
        result = await db.execute(stmt)
        units = result.scalars().all()
        print(f"Found {len(units)} units")
        for u in units:
            print(f"ID: {u.id}, Title: {u.title}, Order: {u.sequence_order}")

if __name__ == "__main__":
    asyncio.run(test())
