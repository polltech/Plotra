"""
Migration script to add new columns for EUDR compliance
Run: docker exec plotra-backend python scripts/migrate_new_columns.py
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine


async def migrate():
    """Add new columns for EUDR compliance"""
    async with engine.begin() as conn:
        # 1. Add columns to users table
        print("Adding columns to users table...")
        
        # gender column
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(10);
            """))
            print("  - gender column added")
        except Exception as e:
            print(f"  - gender: {e}")
        
        # payout_recipient_id column
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_recipient_id VARCHAR(50);
            """))
            print("  - payout_recipient_id column added")
        except Exception as e:
            print(f"  - payout_recipient_id: {e}")
        
        # consent_timestamp column
        try:
            await conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_timestamp TIMESTAMP;
            """))
            print("  - consent_timestamp column added")
        except Exception as e:
            print(f"  - consent_timestamp: {e}")
        
        # 2. Add columns to land_parcels table
        print("\nAdding columns to land_parcels table...")
        
        # heritage_score column
        try:
            await conn.execute(text("""
                ALTER TABLE land_parcels ADD COLUMN IF NOT EXISTS heritage_score FLOAT;
            """))
            print("  - heritage_score column added")
        except Exception as e:
            print(f"  - heritage_score: {e}")
        
        # agroforestry_start_year column
        try:
            await conn.execute(text("""
                ALTER TABLE land_parcels ADD COLUMN IF NOT EXISTS agroforestry_start_year INTEGER;
            """))
            print("  - agroforestry_start_year column added")
        except Exception as e:
            print(f"  - agroforestry_start_year: {e}")
        
        # previous_land_use column
        try:
            await conn.execute(text("""
                ALTER TABLE land_parcels ADD COLUMN IF NOT EXISTS previous_land_use VARCHAR(50);
            """))
            print("  - previous_land_use column added")
        except Exception as e:
            print(f"  - previous_land_use: {e}")
        
        # programme_support JSON column
        try:
            await conn.execute(text("""
                ALTER TABLE land_parcels ADD COLUMN IF NOT EXISTS programme_support JSONB;
            """))
            print("  - programme_support column added")
        except Exception as e:
            print(f"  - programme_support: {e}")
        
        # 3. Add membership_number to cooperative_members table
        print("\nAdding columns to cooperative_members table...")
        
        try:
            await conn.execute(text("""
                ALTER TABLE cooperative_members ADD COLUMN IF NOT EXISTS membership_number VARCHAR(50);
            """))
            print("  - membership_number column added")
        except Exception as e:
            print(f"  - membership_number: {e}")
        
        print("\n✓ Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())