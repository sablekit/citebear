"""Test environment defaults.

Settings are validated at app startup; unit tests never reach a real
database or gateway, so placeholder values are sufficient.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://citebear:citebear@localhost:5432/citebear")
os.environ.setdefault("GATEWAY_API_KEY", "test-gateway-key")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
