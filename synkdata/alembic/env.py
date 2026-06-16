"""
Configuración de Alembic para SynkData Identity Intelligence Platform.

Gestiona las migraciones del esquema de PostgreSQL utilizando
SQLAlchemy de forma síncrona (psycopg2) para compatibilidad con Alembic.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Añadir la raíz del proyecto al path para poder importar ``app``
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import get_settings
from app.models.base import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración de Alembic
# ---------------------------------------------------------------------------
config = context.config

# Interpretar el archivo de configuración de logging de Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sobreescribir la URL de la base de datos con la configuración del proyecto
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

# MetaData de los modelos para autogeneración de migraciones
target_metadata = Base.metadata

logger = logging.getLogger("alembic.env")


# ---------------------------------------------------------------------------
# Migraciones offline (generar SQL sin conexión a la BD)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Ejecuta migraciones en modo 'offline'.

    Genera scripts SQL sin necesidad de conectarse a la base de datos.
    Útil para revisión manual o para entornos CI/CD.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Migraciones online (conectado a la BD)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """
    Ejecuta migraciones en modo 'online'.

    Se conecta a la base de datos utilizando el motor síncrono
    de SQLAlchemy y aplica las migraciones pendientes.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            # Comparación de tipos para autogeneración precisa
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    logger.info("Ejecutando migraciones en modo offline...")
    run_migrations_offline()
else:
    logger.info("Ejecutando migraciones en modo online...")
    run_migrations_online()
