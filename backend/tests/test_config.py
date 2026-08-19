from app.config import Settings


def test_database_url_normalizes_bare_postgres_scheme():
    s = Settings(database_url="postgres://user:pass@host:5432/dbname")
    assert s.database_url == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_database_url_normalizes_driverless_postgresql_scheme():
    s = Settings(database_url="postgresql://user:pass@host:5432/dbname")
    assert s.database_url == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_database_url_leaves_explicit_driver_untouched():
    s = Settings(database_url="postgresql+psycopg2://user:pass@host:5432/dbname")
    assert s.database_url == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_database_url_leaves_sqlite_untouched():
    s = Settings(database_url="sqlite:///:memory:")
    assert s.database_url == "sqlite:///:memory:"
