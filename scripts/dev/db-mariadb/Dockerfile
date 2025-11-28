# Use upstream MariaDB and copy the seed SQL into the init directory so
# the DB is pre-populated on first container startup. The build context is
# expected to be the 'scripts/dev' folder in docker-compose scenarios.
FROM mariadb:10.6

# Pre-seed the test database and user so E2E CI doesn't need to apply schema every run.
# COPY uses paths relative to the build context. With the recommended compose
# context of scripts/dev the source file is db-seed/justnews_init.sql.
COPY db-seed/justnews_init.sql /docker-entrypoint-initdb.d/justnews_init.sql

# Ensure permissions are correct
RUN chmod 644 /docker-entrypoint-initdb.d/justnews_init.sql || true

EXPOSE 3306
