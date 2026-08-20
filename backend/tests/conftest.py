from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-with-more-than-thirty-two-characters-123")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "TestPassword@123")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret-with-enough-length")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("DEMO_DATA_ENABLED", "false")
