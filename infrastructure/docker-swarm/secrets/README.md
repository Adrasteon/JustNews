# JustNews Docker Swarm Secrets
# These files contain the actual secret values
# They should be created using: echo "secret_value" | docker secret create secret_name -

# Example commands to create secrets:
# echo "my_secure_postgres_password" | docker secret create postgres_password -
# echo "my_secure_redis_password" | docker secret create redis_password -
# echo "admin" | docker secret create grafana_admin_user -
# echo "my_secure_grafana_password" | docker secret create grafana_admin_password -

# For production, use strong, randomly generated passwords