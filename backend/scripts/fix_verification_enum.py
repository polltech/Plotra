"""
Plotra Platform - Fix VerificationStatus Enum Values in PostgreSQL
Run this script to update the verificationstatus enum to use uppercase values.

Usage:
    python scripts/fix_verification_enum.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def fix_enum():
    """Fix verificationstatus enum values in PostgreSQL"""
    
    database_url = settings.database.async_url
    is_sqlite = database_url.startswith("sqlite")
    
    if is_sqlite:
        print("SQLite detected - no enum fix needed")
        return
    
    print(f"Using PostgreSQL database")
    print(f"Database URL: {database_url}")
    
    engine = create_async_engine(database_url, echo=True)
    
    async with engine.connect() as conn:
        # Check if verificationstatus enum exists
        result = await conn.execute(text("""
            SELECT t.typname, e.enumlabel 
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid  
            WHERE t.typname = 'verificationstatus'
            ORDER BY e.enumsortorder
        """))
        rows = result.fetchall()
        
        print(f"\nCurrent verificationstatus enum values:")
        for row in rows:
            print(f"  {row[1]}")
        
        # Check if the lowercase values exist
        has_lowercase = any('draft' in row[1].lower() for row in rows)
        
        if not rows:
            print("\nNo verificationstatus enum found - nothing to fix")
        elif not has_lowercase:
            print("\nEnum already uses uppercase values - nothing to fix")
        else:
            print("\nUpdating enum values to uppercase...")
            
            # Start transaction
            await conn.execute(text("BEGIN"))
            
            try:
                # Add uppercase values
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'DRAFT'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'SUBMITTED'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'COOPERATIVE_APPROVED'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'ADMIN_APPROVED'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'EUDR_SUBMITTED'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'CERTIFIED'
                """))
                await conn.execute(text("""
                    ALTER TYPE verificationstatus ADD VALUE IF NOT EXISTS 'REJECTED'
                """))
                
                # Update existing records to use uppercase
                await conn.execute(text("""
                    UPDATE farms 
                    SET verification_status = 'DRAFT'::verificationstatus 
                    WHERE verification_status = 'draft'::verificationstatus
                """))
                
                await conn.execute(text("""
                    UPDATE land_parcels 
                    SET verification_status = 'DRAFT'::verificationstatus 
                    WHERE verification_status = 'draft'::verificationstatus
                """))
                
                await conn.execute(text("""
                    UPDATE verification_records 
                    SET current_status = 'DRAFT'::verificationstatus 
                    WHERE current_status = 'draft'::verificationstatus
                """))
                
                await conn.execute(text("""
                    COMMIT
                """))
                
                print("Enum values updated successfully!")
                
            except Exception as e:
                await conn.execute(text("ROLLBACK"))
                print(f"Error updating enum: {e}")
                raise
        
        # Verify the fix
        result = await conn.execute(text("""
            SELECT t.typname, e.enumlabel 
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid  
            WHERE t.typname = 'verificationstatus'
            ORDER BY e.enumsortorder
        """))
        rows = result.fetchall()
        
        print(f"\nUpdated verificationstatus enum values:")
        for row in rows:
            print(f"  {row[1]}")
    
    await engine.dispose()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(fix_enum())
