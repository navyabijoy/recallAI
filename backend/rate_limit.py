"""Shared slowapi Limiter instance, importable from main.py and auth.py without a circular import."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
