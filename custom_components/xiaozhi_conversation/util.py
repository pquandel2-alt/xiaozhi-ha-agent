"""Shared helpers for XiaoZhi Conversation integration."""

import hashlib


def tts_cache_key(text: str) -> str:
    """Stable key for matching a conversation response text to its audio."""
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()
