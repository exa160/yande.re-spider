import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from src.models.database.yande import Base
target_metadata = Base.metadata

try:
    from src.common.constant import path_constant
    from src.common.settings import load_config
    app_config = load_config(path_constant.config_file)
    use_mariadb = app_config.database.enable and app_config.database.host
    if use_mariadb:
        from sqlalchemy import URL
        url = URL.create(
            drivername="mariadb+mariadbconnector",
            username=app_config.database.user,
            password=app_config.database.password.get_secret_value(),
            host=app_config.database.host,
            port=app_config.database.port,
            database=app_config.database.schema_name
        )
        config.set_main_option("sqlalchemy.url", str(url))
    else:
        config.set_main_option("sqlalchemy.url", f"sqlite:///{path_constant.sqlite_file}")
except Exception:
    pass


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
