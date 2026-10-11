from alembic import command
from alembic.config import Config

import pytest
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture
def empty_postgres_db(monkeypatch):
    with PostgresContainer() as container:
        monkeypatch.setenv('POSTGRES_USER', container.username)
        monkeypatch.setenv('POSTGRES_PASSWORD', container.password)
        monkeypatch.setenv('POSTGRES_DB', container.dbname)
        monkeypatch.setenv('POSTGRES_HOST', container.get_container_host_ip())
        monkeypatch.setenv('POSTGRES_PORT', str(container.get_exposed_port(container.port)))
        yield


@pytest.mark.migration
@pytest.mark.integration
class TestMigrations:
    def test_migrated_schema_matches_orm_models(self, empty_postgres_db):
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.check(cfg)

    def test_downgrade_schema_matches_orm_models(self, empty_postgres_db):
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        command.check(cfg)
