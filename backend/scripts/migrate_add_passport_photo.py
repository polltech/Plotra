"""
Migration script to add passport_photo column to users table
Run: docker exec plotra-backend python scripts/migrate_add_passport_photo.py
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine


async def migrate():
    """Add passport_photo column to users table"""
    async with engine.begin() as conn:
        print("Adding passport_photo column to users table...")
        
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_photo VARCHAR(500);
            """))
            print("  - passport_photo column added successfully")
        except Exception as e:
            print(f"  - Error: {e}")
        
        print("\n✓ Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())