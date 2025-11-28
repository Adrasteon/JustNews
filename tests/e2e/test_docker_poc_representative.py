import os
import uuid
import json
import time

import mysql.connector
import redis


def get_db_conn():
    host = os.environ.get("MARIADB_HOST", "127.0.0.1")
    port = int(os.environ.get("MARIADB_PORT", 13306))
    user = os.environ.get("MARIADB_USER", "justnews")
    passwd = os.environ.get("MARIADB_PASSWORD", "test")
    db = os.environ.get("MARIADB_DB", "justnews_test")
    return mysql.connector.connect(host=host, port=port, user=user, password=passwd, database=db)


def test_seed_job_present():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT job_id, type, status FROM orchestrator_jobs WHERE job_id = 'seed-job-1'")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert rows and rows[0][0] == 'seed-job-1'


def test_can_insert_and_read_job_row():
    conn = get_db_conn()
    cur = conn.cursor()
    new_id = f"poc-job-{uuid.uuid4().hex[:8]}"
    payload = json.dumps({"value": "representative"})
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, created_at) VALUES (%s, %s, %s, %s, NOW())", (new_id, 'inference', payload, 'pending'))
    conn.commit()

    cur.execute("SELECT job_id, payload FROM orchestrator_jobs WHERE job_id = %s", (new_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert rows and rows[0][0] == new_id
    assert json.loads(rows[0][1])['value'] == 'representative'


def test_redis_stream_basic_ops():
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:16379")
    r = redis.from_url(redis_url, decode_responses=True)
    # ping
    assert r.ping() is True

    stream = "stream:representative:test"
    msg_id = r.xadd(stream, {"field": "hello"})
    # allow short time for stream to have the entry
    time.sleep(0.1)
    entries = r.xrange(stream, min=msg_id, max=msg_id)
    assert entries and entries[0][0] == msg_id
