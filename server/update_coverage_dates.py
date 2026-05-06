import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE members SET coverage_effective_date = '2026-03-01'")
        )
        await session.commit()
        print("UPDATE done.")

        result = await session.execute(
            text("SELECT member_number, coverage_effective_date FROM members LIMIT 5")
        )
        rows = result.fetchall()
        print("Verification (first 5 rows):")
        for row in rows:
            print(f"  member_number={row[0]!r}, coverage_effective_date={row[1]!r}")


if __name__ == "__main__":
    asyncio.run(main())
