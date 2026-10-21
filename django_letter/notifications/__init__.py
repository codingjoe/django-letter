"""Optional notification preferences and signed unsubscribe links."""

from .api import (
    Notification,
    NotificationImproperlyConfigured,
    hash_email,
    sign_email_hash,
    subscribe,
    unsign_email_hash,
)

__all__ = [
    "Notification",
    "NotificationImproperlyConfigured",
    "hash_email",
    "sign_email_hash",
    "subscribe",
    "unsign_email_hash",
]
