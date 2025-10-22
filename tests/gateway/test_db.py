"""
Tests for database module.

Tests database engine, sessionmaker, and health check functionality.
Current coverage: 54% → Target: 90%+
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

import services.gateway.app.db as db_module
from services.gateway.app.db import (
    _normalize_database_url,
    get_engine,
    get_sessionmaker,
    check_database_health,
    Base,
)


class TestNormalizeDatabaseUrl:
    """Test _normalize_database_url function."""

    def test_normalize_postgresql_url(self):
        """Test that postgresql:// is converted to postgresql+psycopg://."""
        url = "postgresql://user:pass@localhost:5432/db"
        result = _normalize_database_url(url)

        assert result == "postgresql+psycopg://user:pass@localhost:5432/db"

    def test_normalize_already_normalized_url(self):
        """Test that already normalized URLs are not changed."""
        url = "postgresql+psycopg://user:pass@localhost:5432/db"
        result = _normalize_database_url(url)

        assert result == "postgresql+psycopg://user:pass@localhost:5432/db"

    def test_normalize_sqlite_url_unchanged(self):
        """Test that SQLite URLs are not changed."""
        url = "sqlite:///./test.db"
        result = _normalize_database_url(url)

        assert result == "sqlite:///./test.db"

    def test_normalize_postgres_async_url_unchanged(self):
        """Test that postgresql+asyncpg:// URLs are not changed."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        result = _normalize_database_url(url)

        # Should not change URLs that already have a driver
        assert result == "postgresql+asyncpg://user:pass@localhost:5432/db"


class TestGetEngine:
    """Test get_engine function."""

    def setup_method(self):
        """Reset global engine before each test."""
        db_module._engine = None

    def teardown_method(self):
        """Clean up global engine after each test."""
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = None

    def test_get_engine_creates_postgresql_engine(self):
        """Test that get_engine creates PostgreSQL engine."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}):
            with patch("services.gateway.app.db.create_engine") as mock_create:
                mock_engine = Mock()
                mock_create.return_value = mock_engine

                engine = get_engine()

                # Should create engine with normalized URL
                assert mock_create.called
                call_args = mock_create.call_args
                assert call_args[0][0] == "postgresql+psycopg://localhost/test"

                # Should configure for PostgreSQL (pool_pre_ping, etc.)
                assert call_args[1]["pool_pre_ping"] is True
                assert call_args[1]["pool_size"] == 5
                assert call_args[1]["max_overflow"] == 5

                assert engine == mock_engine

    def test_get_engine_creates_sqlite_engine(self):
        """Test that get_engine creates SQLite engine with StaticPool."""
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"}):
            with patch("services.gateway.app.db.create_engine") as mock_create:
                mock_engine = Mock()
                mock_create.return_value = mock_engine

                engine = get_engine()

                # Should create engine with SQLite configuration
                assert mock_create.called
                call_args = mock_create.call_args
                assert call_args[0][0] == "sqlite:///test.db"

                # Should use StaticPool for SQLite
                assert "poolclass" in call_args[1]
                assert call_args[1]["connect_args"] == {"check_same_thread": False}

                assert engine == mock_engine

    def test_get_engine_uses_default_database_url(self):
        """Test that get_engine uses default URL when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("services.gateway.app.db.create_engine") as mock_create:
                mock_engine = Mock()
                mock_create.return_value = mock_engine

                engine = get_engine()

                # Should use default PostgreSQL URL
                call_args = mock_create.call_args
                assert "postgresql+psycopg://" in call_args[0][0]
                assert "localhost" in call_args[0][0]

    def test_get_engine_returns_cached_engine(self):
        """Test that get_engine returns cached engine on subsequent calls."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}):
            with patch("services.gateway.app.db.create_engine") as mock_create:
                mock_engine = Mock()
                mock_create.return_value = mock_engine

                # First call creates engine
                engine1 = get_engine()
                # Second call should return cached
                engine2 = get_engine()

                # Should only create once
                assert mock_create.call_count == 1
                assert engine1 == engine2


class TestGetSessionmaker:
    """Test get_sessionmaker function."""

    def setup_method(self):
        """Reset globals before each test."""
        db_module._engine = None
        db_module._SessionLocal = None

    def teardown_method(self):
        """Clean up globals after each test."""
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = None
        db_module._SessionLocal = None

    def test_get_sessionmaker_creates_sessionmaker(self):
        """Test that get_sessionmaker creates sessionmaker."""
        with patch("services.gateway.app.db.get_engine") as mock_get_engine:
            with patch("services.gateway.app.db.sessionmaker") as mock_sessionmaker_class:
                mock_engine = Mock()
                mock_get_engine.return_value = mock_engine

                mock_sessionmaker = Mock()
                mock_sessionmaker_class.return_value = mock_sessionmaker

                result = get_sessionmaker()

                # Should create sessionmaker with engine
                mock_sessionmaker_class.assert_called_once_with(
                    bind=mock_engine,
                    expire_on_commit=False,
                    future=True
                )

                assert result == mock_sessionmaker

    def test_get_sessionmaker_returns_cached_sessionmaker(self):
        """Test that get_sessionmaker returns cached sessionmaker."""
        with patch("services.gateway.app.db.get_engine") as mock_get_engine:
            with patch("services.gateway.app.db.sessionmaker") as mock_sessionmaker_class:
                mock_engine = Mock()
                mock_get_engine.return_value = mock_engine

                mock_sessionmaker = Mock()
                mock_sessionmaker_class.return_value = mock_sessionmaker

                # First call creates sessionmaker
                sm1 = get_sessionmaker()
                # Second call should return cached
                sm2 = get_sessionmaker()

                # Should only create once
                assert mock_sessionmaker_class.call_count == 1
                assert sm1 == sm2


class TestCheckDatabaseHealth:
    """Test check_database_health function."""

    def setup_method(self):
        """Reset global engine before each test."""
        db_module._engine = None

    def teardown_method(self):
        """Clean up global engine after each test."""
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = None

    def test_check_database_health_success(self):
        """Test check_database_health when database is healthy."""
        with patch("services.gateway.app.db.get_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_connection = Mock()
            mock_result = Mock()
            mock_result.scalar.return_value = 1

            mock_connection.execute.return_value = mock_result
            mock_connection.__enter__ = Mock(return_value=mock_connection)
            mock_connection.__exit__ = Mock(return_value=None)

            mock_engine.connect.return_value = mock_connection
            mock_get_engine.return_value = mock_engine

            result = check_database_health()

            assert result["ok"] is True
            assert result["details"] == "ok"
            mock_connection.execute.assert_called_once()

    def test_check_database_health_failure(self):
        """Test check_database_health when database check fails."""
        with patch("services.gateway.app.db.get_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_connection = Mock()

            # Simulate database error
            mock_connection.execute.side_effect = Exception("Connection refused")
            mock_connection.__enter__ = Mock(return_value=mock_connection)
            mock_connection.__exit__ = Mock(return_value=None)

            mock_engine.connect.return_value = mock_connection
            mock_get_engine.return_value = mock_engine

            result = check_database_health()

            assert result["ok"] is False
            assert "Connection refused" in result["details"]

    def test_check_database_health_unexpected_result(self):
        """Test check_database_health when query returns unexpected result."""
        with patch("services.gateway.app.db.get_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_connection = Mock()
            mock_result = Mock()
            mock_result.scalar.return_value = 0  # Unexpected (not 1)

            mock_connection.execute.return_value = mock_result
            mock_connection.__enter__ = Mock(return_value=mock_connection)
            mock_connection.__exit__ = Mock(return_value=None)

            mock_engine.connect.return_value = mock_connection
            mock_get_engine.return_value = mock_engine

            result = check_database_health()

            assert result["ok"] is False
            assert result["details"] == "unexpected result"


class TestBase:
    """Test Base declarative base."""

    def test_base_is_declarative_base(self):
        """Test that Base is a DeclarativeBase instance."""
        from sqlalchemy.orm import DeclarativeBase

        assert issubclass(Base, DeclarativeBase)
