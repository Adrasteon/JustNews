job "justnews-agents" {
  datacenters = ["dc1"]
  type = "service"

  # MCP Bus - Central coordination service
  group "mcp-bus" {
    count = 1

    network {
      port "http" {
        to = 8000
      }
    }

    service {
      name = "mcp-bus"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "mcp-bus" {
      driver = "docker"

      config {
        image = "justnews/mcp-bus:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        POSTGRES_HOST = "postgres.service.consul"
        POSTGRES_DB = "justnews"
        POSTGRES_USER = "justnews"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 512
        memory = 1024
      }
    }
  }

  # Scout Agent - Content discovery
  group "scout" {
    count = 3  # Replicated for high availability

    network {
      port "http" {
        to = 8001
      }
    }

    service {
      name = "scout"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "scout" {
      driver = "docker"

      config {
        image = "justnews/scout:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  # Memory Agent - Knowledge management
  group "memory" {
    count = 2

    network {
      port "http" {
        to = 8002
      }
    }

    service {
      name = "memory"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "memory" {
      driver = "docker"

      config {
        image = "justnews/memory:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  # Reasoning Agent - Logic and analysis
  group "reasoning" {
    count = 2

    network {
      port "http" {
        to = 8003
      }
    }

    service {
      name = "reasoning"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "reasoning" {
      driver = "docker"

      config {
        image = "justnews/reasoning:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 512
        memory = 1024
      }
    }
  }

  # Balancer Agent - Load distribution
  group "balancer" {
    count = 2

    network {
      port "http" {
        to = 8004
      }
    }

    service {
      name = "balancer"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "balancer" {
      driver = "docker"

      config {
        image = "justnews/balancer:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  # GPU-enabled agents - Deploy to GPU-capable nodes
  group "analyst" {
    count = 1

    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "="
      value     = "gpu-node-01"  # Specify GPU node
    }

    network {
      port "http" {
        to = 8005
      }
    }

    service {
      name = "analyst"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "analyst" {
      driver = "docker"

      config {
        image = "justnews/analyst:latest"
        ports = ["http"]

        # GPU access
        device "nvidia.com/gpu" {
          count = 1
        }
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
        NVIDIA_VISIBLE_DEVICES = "all"
      }

      resources {
        cpu    = 1024
        memory = 2048
      }
    }
  }

  group "synthesizer" {
    count = 1

    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "="
      value     = "gpu-node-01"
    }

    network {
      port "http" {
        to = 8006
      }
    }

    service {
      name = "synthesizer"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "synthesizer" {
      driver = "docker"

      config {
        image = "justnews/synthesizer:latest"
        ports = ["http"]

        device "nvidia.com/gpu" {
          count = 1
        }
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
        NVIDIA_VISIBLE_DEVICES = "all"
      }

      resources {
        cpu    = 1024
        memory = 2048
      }
    }
  }

  group "fact-checker" {
    count = 1

    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "="
      value     = "gpu-node-01"
    }

    network {
      port "http" {
        to = 8007
      }
    }

    service {
      name = "fact-checker"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "fact-checker" {
      driver = "docker"

      config {
        image = "justnews/fact-checker:latest"
        ports = ["http"]

        device "nvidia.com/gpu" {
          count = 1
        }
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
        NVIDIA_VISIBLE_DEVICES = "all"
      }

      resources {
        cpu    = 1024
        memory = 2048
      }
    }
  }

  group "newsreader" {
    count = 1

    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "="
      value     = "gpu-node-01"
    }

    network {
      port "http" {
        to = 8008
      }
    }

    service {
      name = "newsreader"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "newsreader" {
      driver = "docker"

      config {
        image = "justnews/newsreader:latest"
        ports = ["http"]

        device "nvidia.com/gpu" {
          count = 1
        }
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
        NVIDIA_VISIBLE_DEVICES = "all"
      }

      resources {
        cpu    = 1024
        memory = 2048
      }
    }
  }

  # Additional agents (non-GPU)
  group "chief-editor" {
    count = 1

    network {
      port "http" {
        to = 8009
      }
    }

    service {
      name = "chief-editor"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "chief-editor" {
      driver = "docker"

      config {
        image = "justnews/chief-editor:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 512
        memory = 1024
      }
    }
  }

  group "critic" {
    count = 1

    network {
      port "http" {
        to = 8010
      }
    }

    service {
      name = "critic"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "critic" {
      driver = "docker"

      config {
        image = "justnews/critic:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 512
        memory = 1024
      }
    }
  }

  group "auth" {
    count = 1

    network {
      port "http" {
        to = 8011
      }
    }

    service {
      name = "auth"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "auth" {
      driver = "docker"

      config {
        image = "justnews/auth:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  group "crawler" {
    count = 2

    network {
      port "http" {
        to = 8012
      }
    }

    service {
      name = "crawler"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "crawler" {
      driver = "docker"

      config {
        image = "justnews/crawler:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  group "crawler-control" {
    count = 1

    network {
      port "http" {
        to = 8013
      }
    }

    service {
      name = "crawler-control"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "crawler-control" {
      driver = "docker"

      config {
        image = "justnews/crawler-control:latest"
        ports = ["http"]
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
      }

      resources {
        cpu    = 256
        memory = 512
      }
    }
  }

  group "gpu-orchestrator" {
    count = 1

    constraint {
      attribute = "${attr.unique.hostname}"
      operator  = "="
      value     = "gpu-node-01"
    }

    network {
      port "http" {
        to = 8014
      }
    }

    service {
      name = "gpu-orchestrator"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "30s"
        timeout  = "2s"
      }
    }

    task "gpu-orchestrator" {
      driver = "docker"

      config {
        image = "justnews/gpu-orchestrator:latest"
        ports = ["http"]

        device "nvidia.com/gpu" {
          count = 1
        }
      }

      env {
        DEPLOY_ENV = "production"
        LOG_LEVEL = "INFO"
        MCP_BUS_URL = "http://mcp-bus.service.consul:8000"
        POSTGRES_HOST = "postgres.service.consul"
        REDIS_HOST = "redis.service.consul"
        NVIDIA_VISIBLE_DEVICES = "all"
      }

      resources {
        cpu    = 512
        memory = 1024
      }
    }
  }
}