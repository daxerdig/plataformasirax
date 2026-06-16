-- =============================================================================
-- SynkData Identity Intelligence Platform — Inicialización de PostgreSQL
-- =============================================================================
-- Este script se ejecuta automáticamente al crear el contenedor de Docker.
-- =============================================================================

-- Extensión para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Extensión para búsqueda de texto completo
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Extensión para cifrado
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Esquema por defecto
SET search_path TO public;
