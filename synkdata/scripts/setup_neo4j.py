#!/usr/bin/env python3
"""
Script de configuración de Neo4j para SynkData Identity Intelligence Platform.

Crea:
- Índices y restricciones para consultas eficientes
- Nodos y relaciones de muestra para testing
- Verifica la conectividad con la base de datos

Uso:
    python -m scripts.setup_neo4j
    python -m scripts.setup_neo4j --verify   # Solo verificar conectividad
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("setup_neo4j")


# ---------------------------------------------------------------------------
# Definición de índices y restricciones
# ---------------------------------------------------------------------------
INDEXES_AND_CONSTRAINTS = [
    # ── Restricciones de unicidad ──────────────────────────────────────
    {
        "name": "unique_person_curp",
        "query": """
        CREATE CONSTRAINT unique_person_curp IF NOT EXISTS
        FOR (p:Person) REQUIRE p.curp IS UNIQUE
        """,
        "description": "CURP única por nodo Persona",
    },
    {
        "name": "unique_company_rfc",
        "query": """
        CREATE CONSTRAINT unique_company_rfc IF NOT EXISTS
        FOR (c:Company) REQUIRE p.rfc IS UNIQUE
        """,
        "description": "RFC único por nodo Empresa",
    },
    # ── Índices para búsqueda eficiente ────────────────────────────────
    {
        "name": "index_person_name",
        "query": """
        CREATE INDEX index_person_name IF NOT EXISTS
        FOR (p:Person) ON (p.name)
        """,
        "description": "Índice sobre nombre de persona para búsquedas",
    },
    {
        "name": "index_person_rfc",
        "query": """
        CREATE INDEX index_person_rfc IF NOT EXISTS
        FOR (p:Person) ON (p.rfc)
        """,
        "description": "Índice sobre RFC de persona",
    },
    {
        "name": "index_person_email",
        "query": """
        CREATE INDEX index_person_email IF NOT EXISTS
        FOR (p:Person) ON (p.email)
        """,
        "description": "Índice sobre correo electrónico de persona",
    },
    {
        "name": "index_person_state",
        "query": """
        CREATE INDEX index_person_state IF NOT EXISTS
        FOR (p:Person) ON (p.state)
        """,
        "description": "Índice sobre estado de nacimiento de persona",
    },
    {
        "name": "index_company_name",
        "query": """
        CREATE INDEX index_company_name IF NOT EXISTS
        FOR (c:Company) ON (c.name)
        """,
        "description": "Índice sobre nombre de empresa",
    },
    {
        "name": "index_company_domain",
        "query": """
        CREATE INDEX index_company_domain IF NOT EXISTS
        FOR (c:Company) ON (c.domain)
        """,
        "description": "Índice sobre dominio de empresa",
    },
    {
        "name": "index_company_industry",
        "query": """
        CREATE INDEX index_company_industry IF NOT EXISTS
        FOR (c:Company) ON (c.industry)
        """,
        "description": "Índice sobre industria de empresa",
    },
    # ── Índices de texto completo para búsqueda ────────────────────────
    {
        "name": "fulltext_person_names",
        "query": """
        CREATE FULLTEXT INDEX fulltext_person_names IF NOT EXISTS
        FOR (p:Person) ON EACH [p.name, p.email]
        """,
        "description": "Índice de texto completo para búsqueda de personas",
    },
    {
        "name": "fulltext_company_names",
        "query": """
        CREATE FULLTEXT INDEX fulltext_company_names IF NOT EXISTS
        FOR (c:Company) ON EACH [c.name, c.domain]
        """,
        "description": "Índice de texto completo para búsqueda de empresas",
    },
]


# ---------------------------------------------------------------------------
# Datos de muestra — Nodos y relaciones
# ---------------------------------------------------------------------------
SAMPLE_NODES = {
    "persons": [
        {
            "curp": "GOME850101HDFRRN09",
            "name": "JUAN GOMEZ RODRIGUEZ",
            "birth_date": "1985-01-01",
            "gender": "H",
            "state": "DF",
            "rfc": "GOME850101ABC",
            "email": "juan.gomez@empresa.com.mx",
            "phone": "+525512345678",
        },
        {
            "curp": "LOPM900615MDFRRN05",
            "name": "MARIA LOPEZ MARTINEZ",
            "birth_date": "1990-06-15",
            "gender": "M",
            "state": "DF",
            "rfc": "LOPM900615XYZ",
            "email": "maria.lopez@otraempresa.com",
            "phone": "+525598765432",
        },
        {
            "curp": "PERH920820HMCLLN07",
            "name": "CARLOS PEREZ HERNANDEZ",
            "birth_date": "1992-08-20",
            "gender": "H",
            "state": "MC",
            "rfc": "PERH920820DEF",
            "email": "carlos.perez@empresa.com.mx",
            "phone": "+525511122233",
        },
        {
            "curp": "RODJ880315HMCLLN04",
            "name": "ROBERTO RODRIGUEZ JIMENEZ",
            "birth_date": "1988-03-15",
            "gender": "H",
            "state": "MC",
            "rfc": "RODJ880315GHI",
            "email": "roberto.rodriguez@consultora.com",
            "phone": "+525544455566",
        },
    ],
    "companies": [
        {
            "name": "Empresa Corporativo S.A. de C.V.",
            "rfc": "ECO100420XYZ",
            "domain": "empresa.com.mx",
            "industry": "Tecnología",
        },
        {
            "name": "Otra Empresa S.A.",
            "rfc": "OEM150830ABC",
            "domain": "otraempresa.com",
            "industry": "Consultoría",
        },
        {
            "name": "Consultora Patito S.C.",
            "rfc": "CPS050715DEF",
            "domain": "consultora.com",
            "industry": "Consultoría",
        },
    ],
}

SAMPLE_RELATIONSHIPS = [
    {
        "from_curp": "GOME850101HDFRRN09",
        "to_company": "Empresa Corporativo S.A. de C.V.",
        "type": "WORKS_AT",
        "properties": {"role": "Gerente de Tecnología", "since": "2020-03-01"},
    },
    {
        "from_curp": "PERH920820HMCLLN07",
        "to_company": "Empresa Corporativo S.A. de C.V.",
        "type": "WORKS_AT",
        "properties": {"role": "Desarrollador Senior", "since": "2021-06-15"},
    },
    {
        "from_curp": "LOPM900615MDFRRN05",
        "to_company": "Otra Empresa S.A.",
        "type": "WORKS_AT",
        "properties": {"role": "Directora de Operaciones", "since": "2019-01-10"},
    },
    {
        "from_curp": "RODJ880315HMCLLN04",
        "to_company": "Consultora Patito S.C.",
        "type": "WORKS_AT",
        "properties": {"role": "Consultor Senior", "since": "2022-02-01"},
    },
    {
        "from_curp": "GOME850101HDFRRN09",
        "to_curp": "PERH920820HMCLLN07",
        "type": "COWORKER",
        "properties": {"context": "Misma empresa: Empresa Corporativo"},
    },
    {
        "from_curp": "GOME850101HDFRRN09",
        "to_curp": "LOPM900615MDFRRN05",
        "type": "KNOWS",
        "properties": {"context": "Contacto profesional"},
    },
    {
        "from_curp": "LOPM900615MDFRRN05",
        "to_curp": "RODJ880315HMCLLN04",
        "type": "KNOWS",
        "properties": {"context": "Ex-compañeros de universidad"},
    },
]


# ---------------------------------------------------------------------------
# Funciones de setup
# ---------------------------------------------------------------------------
async def verify_connectivity(driver) -> bool:
    """
    Verifica la conectividad con la base de datos Neo4j.

    Args:
        driver: Driver asíncrono de Neo4j.

    Returns:
        bool: True si la conexión es exitosa.
    """
    try:
        async with driver.session(database="neo4j") as session:
            result = await session.run("RETURN 1 AS test")
            records = await result.data()
            return len(records) > 0 and records[0]["test"] == 1
    except Exception as exc:
        logger.error("❌ Error de conectividad con Neo4j: %s", exc)
        return False


async def create_indexes_and_constraints(driver) -> int:
    """
    Crea los índices y restricciones necesarios para el grafo de identidad.

    Args:
        driver: Driver asíncrono de Neo4j.

    Returns:
        int: Número de índices/restricciones creados exitosamente.
    """
    logger.info("Creando índices y restricciones...")

    created = 0
    async with driver.session(database="neo4j") as session:
        for item in INDEXES_AND_CONSTRAINTS:
            try:
                await session.run(item["query"])
                logger.info(
                    "  ✅ %s — %s",
                    item["name"],
                    item["description"],
                )
                created += 1
            except Exception as exc:
                logger.warning(
                    "  ⚠️  %s — Error: %s",
                    item["name"],
                    str(exc)[:100],
                )

    logger.info("Índices y restricciones creados: %d/%d", created, len(INDEXES_AND_CONSTRAINTS))
    return created


async def create_sample_nodes(driver) -> int:
    """
    Crea los nodos de muestra para testing.

    Args:
        driver: Driver asíncrono de Neo4j.

    Returns:
        int: Número de nodos creados.
    """
    logger.info("Creando nodos de muestra...")

    total = 0
    async with driver.session(database="neo4j") as session:
        # Crear personas
        for person in SAMPLE_NODES["persons"]:
            query = """
            MERGE (p:Person {curp: $curp})
            SET p.name = $name,
                p.birth_date = $birth_date,
                p.gender = $gender,
                p.state = $state,
                p.rfc = $rfc,
                p.email = $email,
                p.phone = $phone,
                p.updated_at = datetime()
            """
            await session.run(query, **person)
            total += 1
            logger.info("  ✅ Persona: %s (%s)", person["name"], person["curp"])

        # Crear empresas
        for company in SAMPLE_NODES["companies"]:
            query = """
            MERGE (c:Company {rfc: $rfc})
            SET c.name = $name,
                c.domain = $domain,
                c.industry = $industry,
                c.updated_at = datetime()
            """
            await session.run(query, **company)
            total += 1
            logger.info("  ✅ Empresa: %s (%s)", company["name"], company["rfc"])

    logger.info("Nodos creados: %d", total)
    return total


async def create_sample_relationships(driver) -> int:
    """
    Crea las relaciones de muestra entre nodos.

    Args:
        driver: Driver asíncrono de Neo4j.

    Returns:
        int: Número de relaciones creadas.
    """
    logger.info("Creando relaciones de muestra...")

    total = 0
    async with driver.session(database="neo4j") as session:
        for rel in SAMPLE_RELATIONSHIPS:
            try:
                if rel["type"] == "WORKS_AT":
                    query = """
                    MATCH (p:Person {curp: $from_curp})
                    MATCH (c:Company {name: $to_company})
                    MERGE (p)-[r:WORKS_AT]->(c)
                    SET r += $properties
                    """
                    await session.run(
                        query,
                        from_curp=rel["from_curp"],
                        to_company=rel["to_company"],
                        properties=rel["properties"],
                    )

                elif rel["type"] == "COWORKER":
                    query = """
                    MATCH (p1:Person {curp: $from_curp})
                    MATCH (p2:Person {curp: $to_curp})
                    MERGE (p1)-[r:COWORKER]-(p2)
                    SET r += $properties
                    """
                    await session.run(
                        query,
                        from_curp=rel["from_curp"],
                        to_curp=rel["to_curp"],
                        properties=rel["properties"],
                    )

                elif rel["type"] == "KNOWS":
                    query = """
                    MATCH (p1:Person {curp: $from_curp})
                    MATCH (p2:Person {curp: $to_curp})
                    MERGE (p1)-[r:KNOWS]-(p2)
                    SET r += $properties
                    """
                    await session.run(
                        query,
                        from_curp=rel["from_curp"],
                        to_curp=rel["to_curp"],
                        properties=rel["properties"],
                    )

                total += 1
                logger.info(
                    "  ✅ %s: %s → %s",
                    rel["type"],
                    rel["from_curp"][:10] + "...",
                    rel.get("to_company", rel.get("to_curp", "")[:10] + "..."),
                )

            except Exception as exc:
                logger.warning("  ⚠️  Error creando relación: %s", str(exc)[:100])

    logger.info("Relaciones creadas: %d", total)
    return total


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
async def main(verify_only: bool = False) -> None:
    """
    Punto de entrada principal del script de configuración de Neo4j.

    Args:
        verify_only: Si True, solo verifica la conectividad sin crear datos.
    """
    logger.info("=" * 60)
    logger.info("SynkData — Neo4j Setup Script")
    logger.info("=" * 60)

    from app.config import get_settings
    from app.database import init_neo4j

    settings = get_settings()

    logger.info("Conectando a Neo4j: %s", settings.NEO4J_URI)
    init_neo4j()

    from app.database import _neo4j_driver

    if _neo4j_driver is None:
        logger.error("❌ No se pudo inicializar el driver de Neo4j.")
        sys.exit(1)

    # Verificar conectividad
    logger.info("Verificando conectividad...")
    is_connected = await verify_connectivity(_neo4j_driver)

    if not is_connected:
        logger.error("❌ No se pudo conectar a Neo4j. Verifique la configuración.")
        sys.exit(1)

    logger.info("✅ Conectividad verificada exitosamente.")

    if verify_only:
        logger.info("Modo verify-only completado.")
        await _neo4j_driver.close()
        return

    # Crear índices y restricciones
    indexes_created = await create_indexes_and_constraints(_neo4j_driver)

    # Crear nodos de muestra
    nodes_created = await create_sample_nodes(_neo4j_driver)

    # Crear relaciones de muestra
    relationships_created = await create_sample_relationships(_neo4j_driver)

    # Verificar resultado final
    logger.info("Verificando estructura del grafo...")
    async with _neo4j_driver.session(database="neo4j") as session:
        # Contar nodos
        result = await session.run("MATCH (n) RETURN labels(n) AS label, count(n) AS count")
        records = await result.data()
        for record in records:
            logger.info(
                "  📊 Nodos %s: %d",
                record["label"],
                record["count"],
            )

        # Contar relaciones
        result = await session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count"
        )
        records = await result.data()
        for record in records:
            logger.info(
                "  📊 Relaciones %s: %d",
                record["type"],
                record["count"],
            )

    # Cerrar conexión
    await _neo4j_driver.close()

    # Resumen
    logger.info("=" * 60)
    logger.info("Resumen del setup:")
    logger.info("  - Índices/Restricciones: %d", indexes_created)
    logger.info("  - Nodos creados: %d", nodes_created)
    logger.info("  - Relaciones creadas: %d", relationships_created)
    logger.info("=" * 60)
    logger.info("✅ Setup de Neo4j completado exitosamente.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SynkData Neo4j Setup Script")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Solo verificar la conectividad sin crear datos.",
    )
    args = parser.parse_args()

    asyncio.run(main(verify_only=args.verify))
