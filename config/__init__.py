# JustNewsAgent Unified Configuration System
# Phase 2B: Configuration Management Refactoring

"""
Unified Configuration System for JustNewsAgent

Provides a complete configuration management solution with:
- Type-safe configuration models with Pydantic validation
- Environment abstraction and inheritance
- Centralized configuration management
- Comprehensive validation and testing
- Legacy migration support
- Runtime configuration updates
"""

from typing import Any, Dict, Optional, Tuple

from .core import *
from .environments import *
from .legacy import *
from .schemas import *
from .validation import *

# Re-export key classes and functions for convenience
__all__ = [
    # Schema exports
    'JustNewsConfig',
    'Environment',
    'SystemConfig',
    'MCPBusConfig',
    'DatabaseConfig',
    'CrawlingConfig',
    'GPUConfig',
    'AgentsConfig',
    'TrainingConfig',
    'SecurityConfig',
    'MonitoringConfig',
    'DataMinimizationConfig',
    'PerformanceConfig',
    'ExternalServicesConfig',
    'load_config_from_file',
    'save_config_to_file',
    'create_default_config',

    # Core manager exports
    'ConfigurationManager',
    'ConfigurationError',
    'ConfigurationValidationError',
    'ConfigurationNotFoundError',
    'get_config_manager',
    'get_config',
    'get_system_config',
    'get_database_config',
    'get_gpu_config',
    'get_crawling_config',
    'is_production',
    'is_debug_mode',

    # Environment profile exports
    'EnvironmentProfile',
    'EnvironmentProfileManager',
    'get_profile_manager',

    # Validation exports
    'ValidationResult',
    'ConfigurationValidator',
    'ConfigurationTester',
    'ConfigurationMigrationValidator',
    'validate_configuration_file',
    'simulate_system_startup',
    'benchmark_configuration',

    # Legacy migration exports
    'LegacyConfigFile',
    'MigrationPlan',
    'LegacyConfigurationMigrator',
    'discover_and_migrate_configs',
    'create_legacy_compatibility_layer'
]

# ============================================================================
# QUICK START HELPERS
# ============================================================================

def quick_start_development() -> ConfigurationManager:
    """
    Quick start for development environment

    Returns:
        ConfigurationManager: Initialized configuration manager
    """
    manager = ConfigurationManager(environment=Environment.DEVELOPMENT)
    return manager

def quick_start_production() -> ConfigurationManager:
    """
    Quick start for production environment

    Returns:
        ConfigurationManager: Initialized configuration manager
    """
    manager = ConfigurationManager(environment=Environment.PRODUCTION)
    return manager

def validate_current_setup() -> ValidationResult:
    """
    Validate current configuration setup

    Returns:
        ValidationResult: Validation results
    """
    try:
        config = get_config()
        validator = ConfigurationValidator()
        return validator.validate(config)
    except Exception as e:
        return ValidationResult(
            is_valid=False,
            errors=[f"Setup validation failed: {e}"],
            warnings=[],
            info=[],
            duration_ms=0
        )

# ============================================================================
# MIGRATION HELPERS
# ============================================================================

def migrate_from_legacy(dry_run: bool = True) -> tuple[MigrationPlan, ValidationResult | None]:
    """
    Migrate from legacy configuration files

    Args:
        dry_run: If True, only create migration plan without executing

    Returns:
        Tuple[MigrationPlan, Optional[ValidationResult]]: Migration plan and execution result
    """
    plan, result = discover_and_migrate_configs(
        target_environment=Environment.DEVELOPMENT,
        execute=not dry_run,
        backup=True
    )
    return plan, result

# ============================================================================
# VERSION INFORMATION
# ============================================================================

__version__ = "1.0.0"
__description__ = "Unified Configuration System for JustNewsAgent"
__author__ = "JustNewsAgent Team"

def get_system_info() -> dict[str, Any]:
    """Get system configuration information"""
    try:
        manager = get_config_manager()
        return {
            "version": __version__,
            "config_file": str(manager.config_file),
            "environment": manager.environment.value if manager.environment else None,
            "last_load_time": manager._last_load_time.isoformat() if manager._last_load_time else None,
            "config_hash": manager._config_hash
        }
    except Exception as e:
        return {
            "error": f"Failed to get system info: {e}",
            "version": __version__
        }
