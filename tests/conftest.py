"""
Test environment: required settings must exist before any app module is imported,
because app.config builds the settings object at import time.
"""

import os

TEST_ENV = {
    "DB_PASSWORD": "db-password-for-tests",
    "INTERNAL_JWT_SECRET": "internal-secret-for-tests-0123456789",
}

for key, value in TEST_ENV.items():
    os.environ[key] = value
