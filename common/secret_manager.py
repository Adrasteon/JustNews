#!/usr/bin/env python3
"""
Secret Management System for JustNewsAgent

This module provides enterprise-grade secret management with multiple backends:
- Environment variables (primary)
- Local encrypted vault (secondary)
- External secret managers (future)

Usage:
    from common.secret_manager import SecretManager

    # Initialize
    secrets = SecretManager()

    # Get database password
    db_password = secrets.get('database.password')

    # Set a new secret
    secrets.set('api.openai_key', 'sk-...', encrypt=True)
"""

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from common.observability import get_logger

logger = get_logger(__name__)

class SecretManager:
    """Enterprise-grade secret management system"""

    def __init__(self, vault_path: str | None = None):
        self.vault_path = vault_path or self._get_default_vault_path()
        self._key: bytes | None = None
        self._vault: dict[str, Any] = {}
        self._load_vault()

    def _get_default_vault_path(self) -> str:
        """Get default encrypted vault path"""
        return str(Path.home() / '.justnews' / 'secrets.vault')

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password using PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def unlock_vault(self, password: str) -> bool:
        """Unlock the encrypted vault with password"""
        try:
            if not os.path.exists(self.vault_path):
                logger.warning("Vault file does not exist")
                return False

            with open(self.vault_path, 'rb') as f:
                encrypted_data = f.read()

            # Extract salt from encrypted data (first 16 bytes)
            salt = encrypted_data[:16]
            encrypted_vault = encrypted_data[16:]

            # Derive key from password
            self._key = self._derive_key(password, salt)

            # Decrypt vault
            fernet = Fernet(self._key)
            decrypted_data = fernet.decrypt(encrypted_vault)
            self._vault = json.loads(decrypted_data.decode())

            logger.info("✅ Vault unlocked successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to unlock vault: {e}")
            return False

    def _load_vault(self):
        """Load vault if not encrypted or already unlocked"""
        if os.path.exists(self.vault_path) and not self._key:
            # Try to load unencrypted vault (for development)
            try:
                with open(self.vault_path) as f:
                    self._vault = json.load(f)
                logger.info("Loaded unencrypted vault (development mode)")
            except Exception:
                logger.info("Encrypted vault detected - use unlock_vault() to access")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a secret value with fallback to environment variables"""
        # First try environment variable
        env_key = key.upper().replace('.', '_')
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return env_value

        # Then try vault
        if key in self._vault:
            return self._vault[key]

        # Return default
        return default

    def set(self, key: str, value: Any, encrypt: bool = True):
        """Set a secret value"""
        self._vault[key] = value

        if encrypt and self._key:
            self._save_encrypted_vault()
        elif not encrypt:
            self._save_plaintext_vault()
        else:
            logger.warning("Vault not encrypted - secrets stored in plaintext")

    def _save_encrypted_vault(self):
        """Save vault in encrypted format"""
        if not self._key:
            raise ValueError("Vault must be unlocked before saving encrypted data")

        try:
            # Ensure vault directory exists
            os.makedirs(os.path.dirname(self.vault_path), exist_ok=True)

            # Serialize vault data
            vault_data = json.dumps(self._vault, indent=2).encode()

            # Encrypt data
            fernet = Fernet(self._key)
            encrypted_data = fernet.encrypt(vault_data)

            # Generate new salt for additional security
            salt = os.urandom(16)

            # Combine salt + encrypted data
            final_data = salt + encrypted_data

            # Save to file
            with open(self.vault_path, 'wb') as f:
                f.write(final_data)

            logger.info("✅ Encrypted vault saved")

        except Exception as e:
            logger.error(f"Failed to save encrypted vault: {e}")
            raise

    def _save_plaintext_vault(self):
        """Save vault in plaintext format (development only)"""
        try:
            os.makedirs(os.path.dirname(self.vault_path), exist_ok=True)
            with open(self.vault_path, 'w') as f:
                json.dump(self._vault, f, indent=2)
            logger.warning("⚠️ Vault saved in plaintext - NOT SECURE for production")
        except Exception as e:
            logger.error(f"Failed to save plaintext vault: {e}")
            raise

    def list_secrets(self) -> dict[str, str]:
        """List all available secrets (masked for security)"""
        result = {}

        # Environment variables
        for key, value in os.environ.items():
            if any(secret in key.lower() for secret in ['password', 'secret', 'key', 'token']):
                result[f"env:{key}"] = self._mask_secret(value)

        # Vault secrets
        for key, value in self._vault.items():
            result[f"vault:{key}"] = self._mask_secret(str(value))

        return result

    def _mask_secret(self, value: str) -> str:
        """Mask a secret value for display"""
        if len(value) <= 4:
            return '*' * len(value)
        return value[:2] + '*' * (len(value) - 4) + value[-2:]

    def validate_security(self) -> dict[str, Any]:
        """Validate security configuration"""
        issues = []
        warnings = []

        # Check for plaintext secrets in config files
        config_files = [
            'config/system_config.json',
            'config/gpu/gpu_config.json',
            'config/gpu/environment_config.json'
        ]

        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file) as f:
                        content = f.read().lower()
                        if any(word in content for word in ['password', 'secret', 'key', 'token']):
                            issues.append(f"Potential secrets found in {config_file}")
                except Exception as e:
                    warnings.append(f"Could not check {config_file}: {e}")

        # Check vault encryption
        if os.path.exists(self.vault_path) and not self._key:
            warnings.append("Vault exists but is not encrypted")

        # Check environment variables
        sensitive_env_vars = []
        for key, value in os.environ.items():
            if any(secret in key.lower() for secret in ['password', 'secret', 'key', 'token']):
                if len(value) < 8:
                    warnings.append(f"Weak secret in {key}")
                sensitive_env_vars.append(key)

        return {
            'issues': issues,
            'warnings': warnings,
            'sensitive_env_vars': sensitive_env_vars,
            'vault_encrypted': self._key is not None,
            'vault_exists': os.path.exists(self.vault_path)
        }


# Global instance
_secret_manager = None

def get_secret_manager() -> SecretManager:
    """Get the global secret manager instance"""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager

# Convenience functions
def get_secret(key: str, default: Any = None) -> Any:
    """Get a secret value"""
    return get_secret_manager().get(key, default)

def set_secret(key: str, value: Any, encrypt: bool = True):
    """Set a secret value"""
    return get_secret_manager().set(key, value, encrypt)

def list_secrets() -> dict[str, str]:
    """List all available secrets (masked)"""
    return get_secret_manager().list_secrets()

def validate_secrets() -> dict[str, Any]:
    """Validate security configuration"""
    return get_secret_manager().validate_security()


if __name__ == "__main__":
    # Test the secret management system
    secrets = get_secret_manager()

    print("=== JustNewsAgent Secret Management System ===")
    print(f"Vault Path: {secrets.vault_path}")
    print(f"Vault Encrypted: {secrets._key is not None}")
    print(f"Vault Exists: {os.path.exists(secrets.vault_path)}")

    # List available secrets
    available_secrets = secrets.list_secrets()
    if available_secrets:
        print("\nAvailable Secrets:")
        for key, masked_value in available_secrets.items():
            print(f"  {key}: {masked_value}")
    else:
        print("\nNo secrets found")

    # Validate security
    security_check = secrets.validate_security()
    if security_check['issues']:
        print("\n🚨 Security Issues:")
        for issue in security_check['issues']:
            print(f"  • {issue}")

    if security_check['warnings']:
        print("\n⚠️ Security Warnings:")
        for warning in security_check['warnings']:
            print(f"  • {warning}")

    print("\n✅ Secret management system initialized")
