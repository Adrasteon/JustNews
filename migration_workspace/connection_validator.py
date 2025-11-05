#!/usr/bin/env python3
"""
JustNews Migration Connection Validator

Simple script to validate database connections before migration.
Tests PostgreSQL, MariaDB, and ChromaDB connectivity.
"""

import os
import sys
import json
import time
from pathlib import Path

def load_config(config_path: str) -> dict:
    """Load migration configuration"""
    with open(config_path, 'r') as f:
        return json.load(f)

def test_postgresql_connection(config: dict) -> tuple:
    """Test PostgreSQL connection"""
    try:
        import psycopg2

        pg_config = config['postgresql']
        password = os.getenv(pg_config['password_env_var'])

        if not password:
            return False, "PostgreSQL password not found in environment"

        conn = psycopg2.connect(
            host=pg_config['host'],
            port=pg_config['port'],
            user=pg_config['user'],
            password=password,
            database=pg_config['database']
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]

        conn.close()
        return True, f"Connected successfully - {version[:50]}..."

    except ImportError:
        return False, "psycopg2 not installed"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

def test_mariadb_connection(config: dict) -> tuple:
    """Test MariaDB connection"""
    try:
        import mysql.connector

        mb_config = config['mariadb']
        password = os.getenv(mb_config['password_env_var'])

        if not password:
            return False, "MariaDB password not found in environment"

        conn = mysql.connector.connect(
            host=mb_config['host'],
            port=mb_config['port'],
            user=mb_config['user'],
            password=password,
            database=mb_config['database']
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]

        conn.close()
        return True, f"Connected successfully - {version}"

    except ImportError:
        return False, "mysql-connector-python not installed"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

def test_chromadb_connection(config: dict) -> tuple:
    """Test ChromaDB connection"""
    try:
        import chromadb

        chroma_config = config['chromadb']

        client = chromadb.HttpClient(
            host=chroma_config['host'],
            port=chroma_config['port']
        )

        heartbeat = client.heartbeat()
        collections = client.list_collections()

        return True, f"Connected successfully - Heartbeat: {heartbeat}, Collections: {len(collections)}"

    except ImportError:
        return False, "chromadb not installed"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

def main():
    config_path = "/home/adra/JustNewsAgent/migration_workspace/migration_config.json"

    if not Path(config_path).exists():
        print("❌ Configuration file not found")
        sys.exit(1)

    config = load_config(config_path)

    # Set environment variables (in production, these should be set securely)
    os.environ['POSTGRESQL_PASSWORD'] = 'password123'  # From global.env
    os.environ['MARIADB_PASSWORD'] = 'migration_password_2024'

    print("🔍 JustNews Migration Connection Validator")
    print("=" * 50)

    tests = [
        ("PostgreSQL", test_postgresql_connection),
        ("MariaDB", test_mariadb_connection),
        ("ChromaDB", test_chromadb_connection)
    ]

    results = []
    all_passed = True

    for name, test_func in tests:
        print(f"\nTesting {name} connection...")
        start_time = time.time()

        success, message = test_func(config)
        duration = time.time() - start_time

        if success:
            print(f"✅ {name}: {message} ({duration:.2f}s)")
            results.append((name, "PASS", message))
        else:
            print(f"❌ {name}: {message} ({duration:.2f}s)")
            results.append((name, "FAIL", message))
            all_passed = False

    print("\n" + "=" * 50)
    print("SUMMARY:")

    for name, status, message in results:
        print(f"  {name}: {status}")

    if all_passed:
        print("\n🎉 All connections successful! Ready for migration.")
        sys.exit(0)
    else:
        print("\n⚠️  Some connections failed. Please check configuration and try again.")
        sys.exit(1)

if __name__ == '__main__':
    main()