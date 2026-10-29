"""
Test environment: required settings must exist before any app module is imported,
because app.config builds the settings object at import time.
"""

import os

TEST_ENV = {
    "DB_PASSWORD": "db-password-for-tests",
    "ANALYTICS_API_KEY": "analytics-key-for-tests",
}

for key, value in TEST_ENV.items():
    os.environ[key] = value
