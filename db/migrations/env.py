from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.base import Base
from db.persistence_logging import PersistenceLogger
import db.models.persistence  # noqa: F401 - ensure tables are registered on Base.metadata
from shared.settings import get_settings

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
logger = PersistenceLogger()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import model modules here as they are introduced so Alembic can see their tables.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    logger.migration_event("migration_offline_start", {"url": config.get_main_option("sqlalchemy.url")})
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()
    logger.migration_event("migration_offline_complete")


def run_migrations_online() -> None:
    logger.migration_event("migration_online_start")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()
    logger.migration_event("migration_online_complete")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
