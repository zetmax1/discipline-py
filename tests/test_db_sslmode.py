import pytest

from app.config import ConfigError, load_settings


def test_sslmode_defaults_to_require(monkeypatch):
    monkeypatch.delenv("DB_SSLMODE", raising=False)
    s = load_settings()
    assert s.DB_SSLMODE == "require"
    assert s.DATABASE_URL.query["sslmode"] == "require"


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"])
def test_sslmode_accepts_libpq_modes(monkeypatch, mode):
    monkeypatch.setenv("DB_SSLMODE", mode)
    assert load_settings().DATABASE_URL.query["sslmode"] == mode


def test_sslmode_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("DB_SSLMODE", "maybe")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "DB_SSLMODE" in str(exc.value)


def test_engine_uses_sslmode(monkeypatch):
    from app.config import settings
    from app.database import engine
    assert engine.url.query.get("sslmode") == settings.DB_SSLMODE


def test_database_url_escapes_password(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "p@ss/word:1")
    url = load_settings().DATABASE_URL
    assert url.password == "p@ss/word:1"
    assert url.host == load_settings().DB_HOST
