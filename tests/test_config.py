import pytest

from app.config import ConfigError, load_settings
from tests.conftest import TEST_ENV


@pytest.fixture
def env(monkeypatch):
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_settings_load_with_required_secrets(env):
    s = load_settings()
    assert s.DB_PASSWORD == TEST_ENV["DB_PASSWORD"]


@pytest.mark.parametrize("name", list(TEST_ENV))
def test_startup_fails_when_secret_missing(env, name):
    env.delenv(name)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert name in str(exc.value)


@pytest.mark.parametrize("name", list(TEST_ENV))
def test_startup_fails_when_secret_blank(env, name):
    env.setenv(name, "   ")
    with pytest.raises(ConfigError):
        load_settings()


def test_startup_fails_when_internal_secret_too_short(env):
    env.setenv("INTERNAL_JWT_SECRET", "y" * 31)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "INTERNAL_JWT_SECRET" in str(exc.value)


def test_no_hardcoded_db_password_fallback(env):
    env.delenv("DB_PASSWORD")
    with pytest.raises(ConfigError):
        load_settings()


def test_error_does_not_leak_values(env):
    env.delenv("DB_PASSWORD")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    for value in TEST_ENV.values():
        assert value not in str(exc.value)
