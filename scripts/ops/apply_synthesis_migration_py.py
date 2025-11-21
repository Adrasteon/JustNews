#!/usr/bin/env python3
"""Apply synthesis migration SQL files using Python DB connector.

This is used as a fallback when the system mysql/mariadb client can't be
used (for example plugin/auth issues). It reads migrations paths and applies
them sequentially against the configured MariaDB instance.

Usage: source global.env; python3 scripts/ops/apply_synthesis_migration_py.py
"""
import os
import sys
import time
import logging
from pathlib import Path

try:
    import mysql.connector
except Exception as e:
    print('Missing mysql.connector in environment – install python mysql-connector or mysqlclient', file=sys.stderr)
    raise


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    REPO_ROOT / 'database' / 'migrations' / '004_add_synthesis_fields.sql',
    REPO_ROOT / 'database' / 'migrations' / '005_create_synthesized_articles_table.sql',
    REPO_ROOT / 'database' / 'migrations' / '006_create_synthesizer_jobs_table.sql',
]

LOG_DIR = REPO_ROOT / 'logs' / 'operations' / 'migrations'
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
log_file = LOG_DIR / f'migration_{timestamp}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)]
)


def get_conn_cfg():
    # prefer JUSTNEWS_DB_URL if provided
    db_url = os.environ.get('JUSTNEWS_DB_URL') or os.environ.get('DB_URL')
    if db_url:
        # attempt simplistic parsing assuming mysql://user:pass@host:port/db
        if db_url.startswith('mysql://') or db_url.startswith('mariadb://'):
            parsed = db_url.split('://', 1)[1]
            userpass, hostpath = parsed.split('@', 1) if '@' in parsed else ('', parsed)
            user, password = (userpass.split(':', 1) + [''])[:2] if userpass else ('', '')
            hostport, dbname = (hostpath.split('/', 1) + [''])[:2]
            host, port = (hostport.split(':', 1) + ['3306'])[:2]
            return dict(user=user or os.environ.get('MARIADB_USER', ''),
                        password=password or os.environ.get('MARIADB_PASSWORD', ''),
                        host=host or os.environ.get('MARIADB_HOST', '127.0.0.1'),
                        port=int(port or os.environ.get('MARIADB_PORT', 3306)),
                        database=dbname or os.environ.get('MARIADB_DB', 'justnews'))

    # fallback to MARIADB_* env vars in global.env
    return dict(
        user=os.environ.get('MARIADB_USER', 'justnews'),
        password=os.environ.get('MARIADB_PASSWORD', ''),
        host=os.environ.get('MARIADB_HOST', '127.0.0.1'),
        port=int(os.environ.get('MARIADB_PORT', 3306)),
        database=os.environ.get('MARIADB_DB', 'justnews'),
    )


def run():
    cfg = get_conn_cfg()

    logging.info('Using DB host=%s port=%s db=%s user=%s', cfg['host'], cfg['port'], cfg['database'], cfg['user'])

    try:
        conn = mysql.connector.connect(host=cfg['host'], port=cfg['port'], user=cfg['user'], password=cfg['password'], database=cfg['database'])
        conn.autocommit = False
    except Exception as e:
        logging.exception('Could not connect to MariaDB: %s', e)
        sys.exit(2)

    cursor = conn.cursor()

    try:
        for migration in MIGRATIONS:
            migration = Path(migration)
            if not migration.exists():
                logging.error('Migration file not found: %s', migration)
                continue
            logging.info('Applying %s', migration)
            sql = migration.read_text(encoding='utf-8')
            try:
                # mysql.connector supports multi according to default
                for result in cursor.execute(sql, multi=True):
                    # iterate to consume results, errors raise
                    pass
                conn.commit()
                logging.info('Applied %s', migration)
            except Exception:
                logging.exception('Failed to apply %s', migration)
                conn.rollback()
                raise

    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    run()
