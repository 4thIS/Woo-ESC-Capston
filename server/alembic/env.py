"""Alembic env. SERVER_DB env 가 있으면 그 파일로. 모델은 app.db.Base 하나에 모인다."""

import os

from sqlalchemy import engine_from_config, pool

import app.domain.models
import app.lora_service.models  # noqa: F401
from alembic import context
from app.db import Base

config = context.config
if os.environ.get("SERVER_DB"):
    config.set_main_option("sqlalchemy.url", f"sqlite:///{os.environ['SERVER_DB']}")
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
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
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
