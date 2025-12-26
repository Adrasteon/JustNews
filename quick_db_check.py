#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add repo root to sys.path dynamically instead of a hard-coded absolute path
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))

# Set correct MariaDB environment variables
os.environ["MARIADB_HOST"] = "127.0.0.1"
os.environ["MARIADB_USER"] = "justnews"
os.environ["MARIADB_PASSWORD"] = "migration_password_2024"
os.environ["MARIADB_DB"] = "justnews"
os.environ["MARIADB_PORT"] = "3306"

try:
    from database.utils.migrated_database_utils import create_database_service

    service = create_database_service()
    cursor = service.mb_conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM articles")
    result = cursor.fetchone()
    cursor.close()
    service.close()
    print(f"Articles in database: {result[0] if result else 0}")
except Exception as e:
    print(f"Error: {e}")
