#!/usr/bin/env python3
"""
Test script to debug migration issues
Run this in the migration job container to see what's failing
"""
import os
import sys

print("=" * 60)
print("MIGRATION DEBUG TEST")
print("=" * 60)

# Check environment variables
print("\n1. Checking environment variables:")
env_vars = [
    "ALEMBIC_DB_SCHEME",
    "ALEMBIC_DB_HOST",
    "ALEMBIC_DB_PORT",
    "ALEMBIC_DB_USER",
    "ALEMBIC_DB_PASSWORD",
    "ALEMBIC_DB_NAME",
    "PATH",
    "PYTHONPATH",
]

for var in env_vars:
    value = os.getenv(var)
    if var == "ALEMBIC_DB_PASSWORD":
        print(f"   {var}: {'SET' if value else 'NOT SET'} (length={len(value) if value else 0})")
    else:
        print(f"   {var}: {value}")

# Try to import alembic
print("\n2. Testing alembic import:")
try:
    import alembic
    print(f"   ✓ Alembic version: {alembic.__version__}")
except Exception as e:
    print(f"   ✗ Failed to import alembic: {e}")
    sys.exit(1)

# Try to connect to database
print("\n3. Testing database connection:")
try:
    from sqlalchemy import create_engine, text

    DB_SCHEME = os.getenv("ALEMBIC_DB_SCHEME")
    DB_USER = os.getenv("ALEMBIC_DB_USER")
    DB_PASSWORD = os.getenv("ALEMBIC_DB_PASSWORD")
    DB_HOST = os.getenv("ALEMBIC_DB_HOST")
    DB_PORT = os.getenv("ALEMBIC_DB_PORT")
    DB_NAME = os.getenv("ALEMBIC_DB_NAME")

    db_url = f"{DB_SCHEME}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"   Connecting to: {DB_SCHEME}://{DB_USER}:***@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.scalar()
        print(f"   ✓ Connected! PostgreSQL version: {version[:50]}")

        # Check if pgvector is installed
        result = conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        if row:
            print(f"   ✓ pgvector extension installed: version {row[1]}")
        else:
            print(f"   ⚠ pgvector extension NOT installed")

except Exception as e:
    print(f"   ✗ Database connection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try to run alembic command
print("\n4. Testing alembic current:")
try:
    import subprocess
    result = subprocess.run(
        ["alembic", "current"],
        capture_output=True,
        text=True,
        timeout=30
    )
    print(f"   Return code: {result.returncode}")
    if result.stdout:
        print(f"   stdout: {result.stdout}")
    if result.stderr:
        print(f"   stderr: {result.stderr}")
except Exception as e:
    print(f"   ✗ Alembic current failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DEBUG TEST COMPLETE")
print("=" * 60)
