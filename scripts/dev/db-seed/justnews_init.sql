-- DB seed for JustNews E2E PoC
-- Creates test database, user and minimal schema used by E2E tests.

CREATE DATABASE IF NOT EXISTS justnews_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'justnews'@'%' IDENTIFIED BY 'test';
GRANT ALL PRIVILEGES ON justnews_test.* TO 'justnews'@'%';
FLUSH PRIVILEGES;

USE justnews_test;

-- orchestrator_leases
CREATE TABLE IF NOT EXISTS orchestrator_leases (
  token VARCHAR(64) PRIMARY KEY,
  agent_name VARCHAR(255) NOT NULL,
  gpu_index INT NULL,
  mode VARCHAR(16) NOT NULL DEFAULT 'gpu',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  metadata JSON NULL
) ENGINE=InnoDB;

-- worker_pools
CREATE TABLE IF NOT EXISTS worker_pools (
  pool_id VARCHAR(128) PRIMARY KEY,
  agent_name VARCHAR(255) NULL,
  model_id VARCHAR(255) NULL,
  adapter VARCHAR(255) NULL,
  desired_workers INT NOT NULL DEFAULT 0,
  spawned_workers INT NOT NULL DEFAULT 0,
  started_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'starting',
  hold_seconds INT NOT NULL DEFAULT 600,
  metadata JSON NULL
) ENGINE=InnoDB;

-- orchestrator_jobs
CREATE TABLE IF NOT EXISTS orchestrator_jobs (
  job_id VARCHAR(128) PRIMARY KEY,
  type VARCHAR(64) NOT NULL,
  payload JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  owner_pool VARCHAR(128) NULL,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL,
  last_error TEXT NULL
) ENGINE=InnoDB;

-- crawler_jobs
CREATE TABLE IF NOT EXISTS crawler_jobs (
  job_id VARCHAR(64) PRIMARY KEY,
  status VARCHAR(32) NOT NULL,
  result TEXT NULL,
  error TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
