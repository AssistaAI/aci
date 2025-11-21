#!/usr/bin/env python3
"""
Test script to debug migration issues
Run this in the migration job container to see what's failing
"""
import os
import sys

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

print("=" * 60, flush=True)
print("MIGRATION DEBUG TEST STARTING", flush=True)
print("=" * 60, flush=True)

# Check environment variables
print("\n1. Checking filesystem:", flush=True)
try:
    import subprocess
    result = subprocess.run(["ls", "-la", "/workdir/"], capture_output=True, text=True)
    print(f"   /workdir/ contents:\n{result.stdout}", flush=True)

    result = subprocess.run(["ls", "-la", "/workdir/.venv/"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"   /workdir/.venv/ exists:\n{result.stdout[:500]}", flush=True)
    else:
        print(f"   /workdir/.venv/ DOES NOT EXIST", flush=True)

    result = subprocess.run(["which", "python3"], capture_output=True, text=True)
    print(f"   which python3: {result.stdout.strip()}", flush=True)

    result = subprocess.run(["python3", "-c", "import sys; print(sys.path)"], capture_output=True, text=True)
    print(f"   sys.path: {result.stdout.strip()}", flush=True)
except Exception as e:
    print(f"   Error checking filesystem: {e}", flush=True)

print("\n2. Checking environment variables:", flush=True)
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
        print(f"   {var}: {'SET' if value else 'NOT SET'} (length={len(value) if value else 0})", flush=True)
    else:
        print(f"   {var}: {value}", flush=True)

# Try to import alembic
print("\n3. Testing alembic import:", flush=True)
try:
    import alembic
    print(f"   ✓ Alembic version: {alembic.__version__}", flush=True)
except Exception as e:
    print(f"   ✗ Failed to import alembic: {e}", flush=True)
    sys.exit(1)

# Try to connect to database
print("\n4. Testing database connection:", flush=True)
try:
    from sqlalchemy import create_engine, text

    DB_SCHEME = os.getenv("ALEMBIC_DB_SCHEME")
    DB_USER = os.getenv("ALEMBIC_DB_USER")
    DB_PASSWORD = os.getenv("ALEMBIC_DB_PASSWORD")
    DB_HOST = os.getenv("ALEMBIC_DB_HOST")
    DB_PORT = os.getenv("ALEMBIC_DB_PORT")
    DB_NAME = os.getenv("ALEMBIC_DB_NAME")

    db_url = f"{DB_SCHEME}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"   Connecting to: {DB_SCHEME}://{DB_USER}:***@{DB_HOST}:{DB_PORT}/{DB_NAME}", flush=True)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.scalar()
        print(f"   ✓ Connected! PostgreSQL version: {version[:50]}", flush=True)

        # Check if pgvector is installed
        result = conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        if row:
            print(f"   ✓ pgvector extension installed: version {row[1]}", flush=True)
        else:
            print(f"   ⚠ pgvector extension NOT installed", flush=True)

except Exception as e:
    print(f"   ✗ Database connection failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try to run alembic command
print("\n5. Testing alembic current:", flush=True)
try:
    import subprocess
    result = subprocess.run(
        ["alembic", "current"],
        capture_output=True,
        text=True,
        timeout=30
    )
    print(f"   Return code: {result.returncode}", flush=True)
    if result.stdout:
        print(f"   stdout: {result.stdout}", flush=True)
    if result.stderr:
        print(f"   stderr: {result.stderr}", flush=True)
except Exception as e:
    print(f"   ✗ Alembic current failed: {e}", flush=True)
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60, flush=True)
print("DEBUG TEST COMPLETE", flush=True)
print("=" * 60, flush=True)
