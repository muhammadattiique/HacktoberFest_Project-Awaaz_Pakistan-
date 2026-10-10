"""
Administrative authentication for Awaaz Pakistan.

The Price Magistrate command portal is deliberately isolated from the public
citizen site, but "hidden URL" is not access control. Every administrative and
state-mutating endpoint therefore requires the shared secret sent by the
frontend in the ``X-API-Key`` header.
"""

import hmac
import logging
from fastapi import Header, HTTPException, status

from config import settings

logger = logging.getLogger(__name__)

# Endpoints that must stay public (the health probe is polled by container
# orchestrators and the citizen dashboard, which have no admin key).
PUBLIC_ADMIN_PATHS = {"/api/admin/health"}


def verify_admin_api_key(x_api_key: str = Header(default=None)) -> None:
    """FastAPI dependency enforcing the administrative API key.

    Raises:
        HTTPException: 401 when the header is missing, 403 when it is wrong.
    """
    expected = (settings.ADMIN_API_KEY or "").strip()

    # If no key is configured the deployment has opted out of admin auth.
    if not expected:
        return

    provided = (x_api_key or "").strip()
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing administrative credentials. Provide the X-API-Key header.",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    # Constant-time comparison avoids leaking the key via timing side channels.
    if not hmac.compare_digest(provided, expected):
        logger.warning("Rejected administrative request with an invalid API key.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrative API key.",
        )
