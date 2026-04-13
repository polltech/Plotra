"""
Plotra Platform - Database Migration for Phone Verification
Run this script to add phone verification columns to the user table.

Changes:
1. Adds phone_verified boolean column to users table
2. Adds phone_verified_at timestamp column
3. Adds verification_token string column

Usage:
    python scripts/migrate_phone_verification.py
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def migrate():
    """Run phone verification migration"""
    
    database_url = settings.database.async_url
    is_sqlite = database_url.startswith("sqlite")
    
    print(f"Using database: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    print(f"Database URL: {database_url}")
    
    engine = create_async_engine(
        database_url,
        echo=True
    )
    
    async with engine.connect() as conn:
        
        # Check existing columns
        if is_sqlite:
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = {row[1] for row in result.fetchall()}
        else:
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
            ))
            columns = {row[0] for row in result.fetchall()}
        
        print(f"Existing columns: {columns}")
        
        changes = []
        
        # Add phone_verified column if not exists
        if 'phone_verified' not in columns:
            if is_sqlite:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT 0"
                ))
            else:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT FALSE"
                ))
            changes.append("phone_verified")
        
        # Add phone_verified_at column if not exists
        if 'phone_verified_at' not in columns:
            if is_sqlite:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP"
                ))
            else:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP"
                ))
            changes.append("phone_verified_at")
        
        # Add verification_token column if not exists
        if 'verification_token' not in columns:
            if is_sqlite:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN verification_token VARCHAR(500)"
                ))
            else:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN verification_token VARCHAR(500)"
                ))
            changes.append("verification_token")
        
        await conn.commit()
        
        if changes:
            print(f"\n✓ Added columns: {', '.join(changes)}")
        else:
            print("\n✓ Migration skipped - columns already exist")
        
        print("\n✓ Migration completed successfully!")
    
    await engine.dispose()


if __name__ == "__main__":
    print("Plotra Platform - Phone Verification Migration")
    print("=" * 50)
    asyncio.run(migrate())