"""Client-IP hashing for rate-limit counting (SPEC §6, #9).

Keyed with a dedicated IP_HASH_SECRET (not the web->api key) so rate-limit
counting works while the raw IP stays unrecoverable, and the two secrets rotate
independently. Lives in its own module so both the chat and admin-login paths
can hash without importing the heavy chat pipeline.
"""

import hashlib
import hmac

from citebear_api.config import get_settings


def hash_ip(ip: str) -> str:
    key = get_settings().ip_hash_secret.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()
