# Consul Server Configuration
# This configuration is for Consul servers in the cluster

datacenter = "dc1"
data_dir = "/opt/consul/data"
bind_addr = "0.0.0.0"
client_addr = "0.0.0.0"
advertise_addr = "{{ GetInterfaceIP \"eth0\" }}"
advertise_addr_wan = "{{ GetInterfaceIP \"eth0\" }}"

# Enable server mode
server = true
bootstrap_expect = 3  # Number of server nodes

# Server to server communication
retry_join = ["consul-server-01", "consul-server-02", "consul-server-03"]
retry_max = 3
retry_interval = "15s"

# UI configuration
ui_config {
  enabled = true
  content_path = "/"
}

# Performance settings
performance {
  raft_multiplier = 1
}

# Telemetry for monitoring
telemetry {
  prometheus_retention_time = "24h"
  disable_hostname = false
}

# Service mesh (optional)
connect {
  enabled = false
}

# ACL configuration (recommended for production)
# acl {
#   enabled = true
#   default_policy = "deny"
#   enable_token_persistence = true
# }

# TLS configuration (recommended for production)
# tls {
#   defaults {
#     ca_file = "/opt/consul/tls/ca.pem"
#     cert_file = "/opt/consul/tls/consul.pem"
#     key_file = "/opt/consul/tls/consul-key.pem"
#     verify_incoming = true
#     verify_outgoing = true
#   }
#   internal_rpc {
#     verify_server_hostname = true
#   }
# }

# Logging
log_level = "INFO"
log_json = true

# Ports
ports {
  grpc = 8502
  https = -1  # Disable HTTPS
}