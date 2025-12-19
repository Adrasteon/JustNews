#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add the project root to Python path FIRST
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.common.auth_models import create_user_tables  # noqa: E402
from agents.common.database import (  # noqa: E402
    execute_query,
    initialize_connection_pool,
)
from common.observability import get_logger  # noqa: E402

"""
Database initialization script for JustNews Authentication System

Creates all necessary tables for user authentication, sessions, and password resets.
Run this script once to set up the authentication database schema.
"""

# Set up logging
logger = get_logger(__name__)

def create_initial_admin_user():
    """Create an initial admin user for testing"""
    from agents.common.auth_models import (
        UserCreate,
        UserRole,
        create_user,
        get_user_by_username_or_email,
    )

    try:
        existing = get_user_by_username_or_email("admin@justnews.com")
        if existing:
            logger.info("Admin user already exists; skipping creation")
            return

        admin_user = UserCreate(
            email="admin@justnews.com",
            username="admin",
            full_name="System Administrator",
            password="Admin123!@#",
            role=UserRole.ADMIN
        )

        user_id = create_user(admin_user)
        if user_id:
            logger.info(f"✅ Created initial admin user with ID: {user_id}")
            logger.info("   Username: admin")
            logger.info("   Email: admin@justnews.com")
            logger.info("   Password: Admin123!@#")
            logger.info("   ⚠️  Please change this password after first login!")
        else:
            logger.warning("⚠️  Failed to create initial admin user")

    except Exception as e:
        logger.error(f"❌ Error creating initial admin user: {e}")

def create_knowledge_graph_tables():
    """Create/align knowledge graph and supporting tables for MariaDB."""

    def table_exists(name: str) -> bool:
        rows = execute_query("SHOW TABLES LIKE %s", (name,)) or []
        return len(rows) > 0

    def column_exists(table: str, column: str) -> bool:
        rows = execute_query(f"SHOW COLUMNS FROM {table} LIKE %s", (column,)) or []
        return len(rows) > 0

    def run_ddl(sql: str, label: str):
        try:
            execute_query(sql, fetch=False)
            logger.info(f"✅ {label}")
        except Exception as e:
            logger.error(f"❌ {label}: {e}")
            raise

    # Entities baseline table (aligns with migrations 007/008)
    if not table_exists("entities"):
        run_ddl(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                confidence_score DECIMAL(5,3) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                canonical_name VARCHAR(255) DEFAULT NULL,
                detection_source VARCHAR(128) DEFAULT NULL,
                UNIQUE KEY unique_entity (name, entity_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            "entities table ready"
        )
    else:
        if not column_exists("entities", "canonical_name"):
            run_ddl("ALTER TABLE entities ADD COLUMN canonical_name VARCHAR(255) DEFAULT NULL", "entities.canonical_name added")
        if not column_exists("entities", "detection_source"):
            run_ddl("ALTER TABLE entities ADD COLUMN detection_source VARCHAR(128) DEFAULT NULL", "entities.detection_source added")

    # Junction table linking articles to entities
    if not table_exists("article_entities"):
        run_ddl(
            """
            CREATE TABLE IF NOT EXISTS article_entities (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                article_id BIGINT UNSIGNED NOT NULL,
                entity_id BIGINT NOT NULL,
                relevance_score DECIMAL(5,3) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_article_entity (article_id, entity_id),
                CONSTRAINT fk_article_fk FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                CONSTRAINT fk_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            "article_entities table ready"
        )

    # KG audit log
    if not table_exists("kg_audit"):
        run_ddl(
            """
            CREATE TABLE IF NOT EXISTS kg_audit (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                operation VARCHAR(50) NOT NULL,
                actor VARCHAR(255) DEFAULT NULL,
                target_type VARCHAR(50) DEFAULT NULL,
                target_id BIGINT DEFAULT NULL,
                details JSON DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            "kg_audit table ready"
        )

    # Training examples + model metrics for downstream ML tasks
    if not table_exists("training_examples"):
        run_ddl(
            """
            CREATE TABLE IF NOT EXISTS training_examples (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                article_id BIGINT UNSIGNED NULL,
                task VARCHAR(255) NULL,
                input LONGTEXT NULL,
                input_text LONGTEXT NULL,
                output LONGTEXT NULL,
                output_label VARCHAR(100) NULL,
                model_version VARCHAR(50) NULL,
                confidence_score DECIMAL(5,3) NULL,
                critique TEXT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_training_article FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            "training_examples table ready"
        )

    if not table_exists("model_metrics"):
        run_ddl(
            """
            CREATE TABLE IF NOT EXISTS model_metrics (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                model_name VARCHAR(100) NOT NULL,
                model_version VARCHAR(50) NOT NULL,
                metric_name VARCHAR(100) NOT NULL,
                metric_value DECIMAL(10,4),
                dataset_size INT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_metric (model_name, model_version, metric_name, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            "model_metrics table ready"
        )

    # Create orchestrator_leases table for GPU orchestrator durable leases
    lease_query = """
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
    """
    try:
        execute_query(lease_query, fetch=False)
        logger.info("✅ orchestrator_leases table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating orchestrator_leases table: {e}")
        raise

    # Create worker_pools table for orchestrator persistent worker pools
    pools_query = """
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
    """
    try:
        execute_query(pools_query, fetch=False)
        logger.info("✅ worker_pools table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating worker_pools table: {e}")
        raise

    # Create orchestrator_jobs table for persistent job store
    jobs_query = """
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
    """
    try:
        execute_query(jobs_query, fetch=False)
        logger.info("✅ orchestrator_jobs table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating orchestrator_jobs table: {e}")
        raise


def create_crawler_jobs_table():
    """Create crawler job table used by crawler job_store."""
    query = """
    CREATE TABLE IF NOT EXISTS crawler_jobs (
        job_id VARCHAR(64) PRIMARY KEY,
        status VARCHAR(32) NOT NULL,
        result TEXT NULL,
        error TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """
    try:
        execute_query(query, fetch=False)
        logger.info("✅ crawler_jobs table created or already exists")
    except Exception as e:
        logger.error(f"❌ Error creating crawler_jobs table: {e}")
        raise

def main():
    """Main initialization function"""
    logger.info("🚀 Starting JustNews Database Initialization")
    logger.info("=" * 60)

    # Load environment variables from global.env
    from common.env_loader import load_global_env
    load_global_env(logger=logger)

    # Check environment variables
    required_env_vars = [
        "MARIADB_HOST",
        "MARIADB_DB",
        "MARIADB_USER",
        "MARIADB_PASSWORD"
    ]

    missing_vars = [var for var in required_env_vars if var not in os.environ]
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these environment variables before running this script:")
        for var in missing_vars:
            logger.error(f"  export {var}=<value>")
        sys.exit(1)

    logger.info("✅ Environment variables configured")

    try:
        # Initialize connection pool
        logger.info("🔌 Initializing database connection pool...")
        initialize_connection_pool()
        logger.info("✅ Database connection pool initialized")

        # Create authentication tables
        logger.info("🔐 Creating authentication tables...")
        create_user_tables()
        logger.info("✅ Authentication tables created")

        # Create knowledge graph tables
        logger.info("🕸️  Creating knowledge graph tables...")
        create_knowledge_graph_tables()
        logger.info("✅ Knowledge graph tables created")

        # Create crawler jobs table
        logger.info("🗄️  Creating crawler jobs table (job store)...")
        create_crawler_jobs_table()
        logger.info("✅ crawler jobs table created")

        # Create initial admin user
        logger.info("👤 Creating initial admin user...")
        create_initial_admin_user()

        logger.info("=" * 60)
        logger.info("🎉 Database initialization completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Start the API server: python -m agents.archive.archive_api")
        logger.info("2. Test authentication: POST /auth/login with admin credentials")
        logger.info("3. Access API docs: http://localhost:8021/docs")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("Please check your database configuration and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
