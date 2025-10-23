"""
JustNewsAgent Security Framework

A comprehensive security framework providing authentication, authorization,
encryption, compliance monitoring, and security event tracking.
"""

from .security_manager import SecurityManager, SecurityConfig, SecurityContext, AuthenticationError, AuthorizationError, SecurityError
from .authentication.service import AuthenticationService, AuthenticationError as AuthError
from .authorization.service import AuthorizationService, AuthorizationError as AuthzError
from .encryption.service import EncryptionService, EncryptionError
from .compliance.service import ComplianceService, ComplianceError
from .monitoring.service import SecurityMonitor

__version__ = "1.0.0"
__all__ = [
    "SecurityManager",
    "SecurityConfig",
    "SecurityContext",
    "AuthenticationError",
    "AuthorizationError",
    "SecurityError",
    "AuthenticationService",
    "AuthError",
    "AuthorizationService",
    "AuthzError",
    "EncryptionService",
    "EncryptionError",
    "ComplianceService",
    "ComplianceError",
    "SecurityMonitor"
]