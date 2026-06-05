"""Add pipeline_mode column to opa_cases.

Backfills from the linked claims row so existing cases carry the correct
discriminator. Pre-pay cases created before this migration will get 'pre_pay';
all others default to 'post_pay'.

Run once after pulling this schema change:
    cd backend && python ../migrate_add_case_pipeline_mode.py
"""
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Add column (no-op if it already exists — SQLite doesn't support IF NOT EXISTS
        # on ADD COLUMN in older versions, so we catch the error).
        try:
            await db.execute(text(
                "ALTER TABLE opa_cases ADD COLUMN pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'post_pay'"
            ))
            print("Column added.")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("Column already exists — skipping ALTER.")
            else:
                raise

        # Backfill from the linked claim's pipeline_mode.
        result = await db.execute(text("""
            UPDATE opa_cases
            SET pipeline_mode = (
                SELECT pipeline_mode FROM claims
                WHERE claims.claim_id = opa_cases.claim_id
            )
            WHERE EXISTS (
                SELECT 1 FROM claims WHERE claims.claim_id = opa_cases.claim_id
            )
        """))
        print(f"Backfilled {result.rowcount} rows.")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
