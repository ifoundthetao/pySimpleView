"""API-key storage backed by the OS keychain (macOS Keychain), with env override.

Keys are stored per provider under the keyring service ``pySimpleView`` with the
provider key as the account, so nothing secret is ever written to settings.json.
An environment variable ``PYSIMPLEVIEW_<PROVIDER>_API_KEY`` takes precedence.
"""

from __future__ import annotations

import os

SERVICE = "pySimpleView"


def _env_var(provider_key: str) -> str:
    return f"PYSIMPLEVIEW_{provider_key.upper()}_API_KEY"


def get_api_key(provider_key: str) -> str:
    env = os.environ.get(_env_var(provider_key))
    if env:
        return env
    try:
        import keyring

        return keyring.get_password(SERVICE, provider_key) or ""
    except Exception:
        return ""


def set_api_key(provider_key: str, key: str) -> bool:
    """Store (or clear, if empty) the key in the keychain. Returns success."""
    try:
        import keyring

        if key:
            keyring.set_password(SERVICE, provider_key, key)
        else:
            try:
                keyring.delete_password(SERVICE, provider_key)
            except Exception:
                pass
        return True
    except Exception:
        return False


def has_api_key(provider_key: str) -> bool:
    return bool(get_api_key(provider_key))
