#!/usr/bin/env python3
"""
Script de seeding de la base de datos para SynkData Identity Intelligence Platform.

Puebla la base de datos con datos de prueba para:
- Entradas en listas restrictivas (watchlist) para testing de screening
- Eventos de verificación de muestra para analítica
- Alertas del sistema
- Datos de grafo Neo4j (nodos y relaciones de identidad)

Uso:
    python -m scripts.seed_data
    python -m scripts.seed_data --reset   # Limpiar datos existentes antes de sembrar
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

# Configurar logging antes de importar la app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("seed_data")


# ---------------------------------------------------------------------------
# Datos de muestra — Watchlist entries
# ---------------------------------------------------------------------------
WATCHLIST_ENTRIES: List[Dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "name": "CARLOS ENRIQUE RAMÍREZ SALINAS",
        "aliases": ["CARLOS RAMÍREZ", "ENRIQUE SALINAS"],
        "source": "ofac",
        "list_name": "SDN",
        "program": "SDGT",
        "country": "MX",
        "match_score": 1.0,
        "entity_data": {
            "type": "individual",
            "date_of_birth": "1975-03-15",
            "nationality": "MX",
            "id_number": "RASC750315HDFRRN09",
        },
    },
    {
        "id": str(uuid.uuid4()),
        "name": "MARÍA ELENA TORRES VEGA",
        "aliases": ["MARÍA TORRES", "ELENA VEGA"],
        "source": "interpol",
        "list_name": "Red Notice",
        "program": "INTERPOL_WANTED",
        "country": "MX",
        "match_score": 1.0,
        "entity_data": {
            "type": "individual",
            "date_of_birth": "1982-07-22",
            "nationality": "MX",
            "notice_type": "red",
        },
    },
    {
        "id": str(uuid.uuid4()),
        "name": "ROBERTO GONZÁLEZ HERRERA",
        "aliases": ["ROBERTO GONZÁLEZ", "GONZÁLEZ HERRERA"],
        "source": "un",
        "list_name": "UNSC Consolidated List",
        "program": "UN_SANCTIONS",
        "country": "MX",
        "match_score": 1.0,
        "entity_data": {
            "type": "individual",
            "date_of_birth": "1968-11-05",
            "nationality": "MX",
        },
    },
    {
        "id": str(uuid.uuid4()),
        "name": "CORPORATIVO ALFA S.A. DE C.V.",
        "aliases": ["CORPORATIVO ALFA", "ALFA CORP"],
        "source": "ofac",
        "list_name": "SDN",
        "program": "SDGT",
        "country": "MX",
        "match_score": 1.0,
        "entity_data": {
            "type": "entity",
            "incorporation_date": "2010-04-20",
            "tax_id": "CAF100420XYZ",
        },
    },
    {
        "id": str(uuid.uuid4()),
        "name": "JOSÉ ANTONIO MUÑOZ CASTILLO",
        "aliases": ["JOSÉ MUÑOZ", "ANTONIO CASTILLO"],
        "source": "opensanctions",
        "list_name": "OpenSanctions",
        "program": "PEP",
        "country": "MX",
        "match_score": 0.95,
        "entity_data": {
            "type": "individual",
            "date_of_birth": "1970-09-12",
            "nationality": "MX",
            "position": "Ex-Senador de la República",
            "pep_level": "national",
        },
    },
]


# ---------------------------------------------------------------------------
# Datos de muestra — Eventos de verificación
# ---------------------------------------------------------------------------
def _generate_verification_events(count: int = 50) -> List[Dict[str, Any]]:
    """Genera eventos de verificación aleatorios para testing de analítica."""
    events = []
    names = [
        "JUAN GOMEZ RODRIGUEZ", "MARIA LOPEZ MARTINEZ", "CARLOS PEREZ HERNANDEZ",
        "ANA RODRIGUEZ GARCIA", "ROBERTO MARTINEZ LOPEZ", "LAURA HERNANDEZ PEREZ",
        "MIGUEL GARCIA RODRIGUEZ", "PATRICIA SANCHEZ TORRES", "JOSE RAMIREZ FLORES",
        "ROSALIA DIAZ MORALES", "FRANCISCO TORRES JIMENEZ", "ELENA FLORES DIAZ",
        "DANIEL MORALES SANCHEZ", "SILVIA JIMENEZ RAMIREZ", "ALEJANDRO CRUZ ORTIZ",
    ]
    states = ["DF", "NL", "JL", "MC", "PN", "GR", "CH", "SL", "SR", "VZ"]
    recommendations = ["APPROVE", "APPROVE", "APPROVE", "REVIEW", "REVIEW", "REJECT"]

    import random
    random.seed(42)

    for i in range(count):
        name = random.choice(names)
        state = random.choice(states)
        recommendation = random.choice(recommendations)
        days_ago = random.randint(1, 90)

        risk_score = {
            "APPROVE": random.uniform(0, 15),
            "REVIEW": random.uniform(16, 40),
            "REJECT": random.uniform(41, 100),
        }[recommendation]

        trust_score = {
            "APPROVE": random.uniform(70, 100),
            "REVIEW": random.uniform(40, 70),
            "REJECT": random.uniform(0, 40),
        }[recommendation]

        event = {
            "id": str(uuid.uuid4()),
            "name": name,
            "curp": f"{name.split()[-1][:2]}{name.split()[-2][1] if len(name.split()) > 1 else 'X'}{random.randint(60,99)}0101{random.choice(['H','M'])}{state}XXX0{random.randint(0,9)}",
            "rfc": f"{name.split()[-1][:2]}{name.split()[-2][1] if len(name.split()) > 1 else 'X'}{random.randint(60,99)}0101ABC",
            "state": state,
            "recommendation": recommendation,
            "risk_score": round(risk_score, 2),
            "trust_score": round(trust_score, 2),
            "processing_time_ms": random.randint(50, 500),
            "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        }
        events.append(event)

    return events


# ---------------------------------------------------------------------------
# Datos de muestra — Alertas
# ---------------------------------------------------------------------------
ALERTS: List[Dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "severity": "critical",
        "title": "Coincidencia OFAC detectada",
        "description": "Se detectó una coincidencia en la lista OFAC SDN para CARLOS ENRIQUE RAMÍREZ SALINAS con score 0.95.",
        "source": "screening",
        "status": "active",
        "entity_name": "CARLOS ENRIQUE RAMÍREZ SALINAS",
    },
    {
        "id": str(uuid.uuid4()),
        "severity": "high",
        "title": "Aviso rojo de Interpol",
        "description": "Se encontró un aviso rojo de Interpol para MARÍA ELENA TORRES VEGA.",
        "source": "screening",
        "status": "active",
        "entity_name": "MARÍA ELENA TORRES VEGA",
    },
    {
        "id": str(uuid.uuid4()),
        "severity": "high",
        "title": "Identidad inconsistente detectada",
        "description": "La CURP y el RFC proporcionados tienen iniciales diferentes, lo que sugiere posible suplantación de identidad.",
        "source": "correlation",
        "status": "active",
        "entity_name": "Unknown",
    },
    {
        "id": str(uuid.uuid4()),
        "severity": "medium",
        "title": "Correo electrónico desechable",
        "description": "Se detectó el uso de un correo electrónico temporal/desechable en la verificación.",
        "source": "correlation",
        "status": "reviewed",
        "entity_name": "Unknown",
    },
    {
        "id": str(uuid.uuid4()),
        "severity": "low",
        "title": "Sin presencia digital",
        "description": "No se encontró presencia digital para la identidad verificada.",
        "source": "digital_intelligence",
        "status": "reviewed",
        "entity_name": "Unknown",
    },
]


# ---------------------------------------------------------------------------
# Datos de muestra — Grafo Neo4j
# ---------------------------------------------------------------------------
NEO4J_SAMPLE_DATA = {
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
    ],
    "relationships": [
        {
            "from_curp": "GOME850101HDFRRN09",
            "to_company": "Empresa Corporativo S.A. de C.V.",
            "type": "WORKS_AT",
            "role": "Gerente de Tecnología",
            "since": "2020-03-01",
        },
        {
            "from_curp": "PERH920820HMCLLN07",
            "to_company": "Empresa Corporativo S.A. de C.V.",
            "type": "WORKS_AT",
            "role": "Desarrollador Senior",
            "since": "2021-06-15",
        },
        {
            "from_curp": "LOPM900615MDFRRN05",
            "to_company": "Otra Empresa S.A.",
            "type": "WORKS_AT",
            "role": "Directora de Operaciones",
            "since": "2019-01-10",
        },
        {
            "from_curp": "GOME850101HDFRRN09",
            "to_curp": "PERH920820HMCLLN07",
            "type": "COWORKER",
            "context": "Misma empresa",
        },
        {
            "from_curp": "GOME850101HDFRRN09",
            "to_curp": "LOPM900615MDFRRN05",
            "type": "KNOWS",
            "context": "Contacto profesional",
        },
    ],
}


# ---------------------------------------------------------------------------
# Funciones de seeding
# ---------------------------------------------------------------------------
async def seed_watchlist(redis_client) -> int:
    """
    Siembra entradas de watchlist en Redis para testing de screening.

    Args:
        redis_client: Cliente Redis asíncrono.

    Returns:
        int: Número de entradas sembradas.
    """
    logger.info("Sembrando entradas de watchlist...")

    count = 0
    for entry in WATCHLIST_ENTRIES:
        key = f"watchlist:{entry['source']}:{entry['id']}"
        value = json.dumps(entry, ensure_ascii=False)
        await redis_client.set(key, value)

        # También crear un índice por nombre para búsquedas rápidas
        name_key = f"watchlist_name:{entry['source']}:{entry['name'].upper()}"
        await redis_client.set(name_key, entry["id"])

        count += 1

    logger.info("✅ %d entradas de watchlist sembradas.", count)
    return count


async def seed_verification_events(redis_client) -> int:
    """
    Siembra eventos de verificación en Redis para testing de analítica.

    Args:
        redis_client: Cliente Redis asíncrono.

    Returns:
        int: Número de eventos sembrados.
    """
    logger.info("Sembrando eventos de verificación...")

    events = _generate_verification_events(count=50)
    count = 0

    for event in events:
        key = f"verification_event:{event['id']}"
        value = json.dumps(event, ensure_ascii=False)
        await redis_client.set(key, value, ex=86400 * 90)  # TTL: 90 días

        # Índice por fecha para consultas de analítica
        date_key = f"verification_by_date:{event['created_at'][:10]}"
        await redis_client.rpush(date_key, event["id"])
        await redis_client.expire(date_key, 86400 * 90)

        count += 1

    logger.info("✅ %d eventos de verificación sembrados.", count)
    return count


async def seed_alerts(redis_client) -> int:
    """
    Siembra alertas del sistema en Redis.

    Args:
        redis_client: Cliente Redis asíncrono.

    Returns:
        int: Número de alertas sembradas.
    """
    logger.info("Sembrando alertas del sistema...")

    count = 0
    for alert in ALERTS:
        key = f"alert:{alert['id']}"
        value = json.dumps(alert, ensure_ascii=False)
        await redis_client.set(key, value)

        # Índice por severidad
        severity_key = f"alerts_by_severity:{alert['severity']}"
        await redis_client.rpush(severity_key, alert["id"])

        # Índice por estado
        status_key = f"alerts_by_status:{alert['status']}"
        await redis_client.rpush(status_key, alert["id"])

        count += 1

    logger.info("✅ %d alertas sembradas.", count)
    return count


async def seed_neo4j_graph(neo4j_driver) -> int:
    """
    Siembra datos de grafo en Neo4j para testing de conocimiento de identidad.

    Crea nodos de personas, empresas y relaciones entre ellos.

    Args:
        neo4j_driver: Driver asíncrono de Neo4j.

    Returns:
        int: Número total de nodos creados.
    """
    logger.info("Sembrando datos de grafo Neo4j...")

    total_nodes = 0

    async with neo4j_driver.session(database="neo4j") as session:
        # Crear nodos de personas
        for person in NEO4J_SAMPLE_DATA["persons"]:
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
            total_nodes += 1

        # Crear nodos de empresas
        for company in NEO4J_SAMPLE_DATA["companies"]:
            query = """
            MERGE (c:Company {rfc: $rfc})
            SET c.name = $name,
                c.domain = $domain,
                c.industry = $industry,
                c.updated_at = datetime()
            """
            await session.run(query, **company)
            total_nodes += 1

        # Crear relaciones
        for rel in NEO4J_SAMPLE_DATA["relationships"]:
            if rel["type"] == "WORKS_AT":
                query = """
                MATCH (p:Person {curp: $from_curp})
                MATCH (c:Company {name: $to_company})
                MERGE (p)-[r:WORKS_AT]->(c)
                SET r.role = $role,
                    r.since = $since
                """
                await session.run(
                    query,
                    from_curp=rel["from_curp"],
                    to_company=rel["to_company"],
                    role=rel["role"],
                    since=rel["since"],
                )

            elif rel["type"] == "COWORKER":
                query = """
                MATCH (p1:Person {curp: $from_curp})
                MATCH (p2:Person {curp: $to_curp})
                MERGE (p1)-[r:COWORKER]-(p2)
                SET r.context = $context
                """
                await session.run(
                    query,
                    from_curp=rel["from_curp"],
                    to_curp=rel["to_curp"],
                    context=rel.get("context", ""),
                )

            elif rel["type"] == "KNOWS":
                query = """
                MATCH (p1:Person {curp: $from_curp})
                MATCH (p2:Person {curp: $to_curp})
                MERGE (p1)-[r:KNOWS]-(p2)
                SET r.context = $context
                """
                await session.run(
                    query,
                    from_curp=rel["from_curp"],
                    to_curp=rel["to_curp"],
                    context=rel.get("context", ""),
                )

    logger.info("✅ %d nodos y relaciones sembrados en Neo4j.", total_nodes)
    return total_nodes


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
async def main(reset: bool = False) -> None:
    """
    Punto de entrada principal del script de seeding.

    Inicializa las conexiones a las bases de datos, opcionalmente
    limpia los datos existentes y siembra los datos de prueba.

    Args:
        reset: Si True, limpia los datos existentes antes de sembrar.
    """
    logger.info("=" * 60)
    logger.info("SynkData Identity Intelligence Platform — Seed Data")
    logger.info("=" * 60)

    # Importar la configuración y las conexiones
    from app.config import get_settings
    from app.database import init_neo4j, init_redis

    settings = get_settings()

    # Inicializar conexiones
    logger.info("Inicializando conexiones...")
    init_redis()
    init_neo4j()

    from app.database import get_redis

    redis_client = get_redis()

    if reset:
        logger.warning("⚠️  Modo RESET: limpiando datos existentes...")
        # Limpiar claves de watchlist
        async for key in redis_client.scan_iter("watchlist:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter("watchlist_name:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter("verification_event:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter("verification_by_date:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter("alert:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter("alerts_by_*"):
            await redis_client.delete(key)
        logger.info("✅ Datos existentes limpiados.")

    # Sembrar datos
    watchlist_count = await seed_watchlist(redis_client)
    events_count = await seed_verification_events(redis_client)
    alerts_count = await seed_alerts(redis_client)

    # Intentar sembrar Neo4j (puede fallar si no está disponible)
    neo4j_count = 0
    try:
        from app.database import _neo4j_driver

        if _neo4j_driver is not None:
            neo4j_count = await seed_neo4j_graph(_neo4j_driver)
        else:
            logger.warning("⚠️  Neo4j no disponible — omitiendo seeding de grafo.")
    except Exception as exc:
        logger.warning("⚠️  Error al sembrar Neo4j: %s", exc)

    # Resumen
    logger.info("=" * 60)
    logger.info("Resumen de seeding:")
    logger.info("  - Watchlist entries: %d", watchlist_count)
    logger.info("  - Eventos de verificación: %d", events_count)
    logger.info("  - Alertas: %d", alerts_count)
    logger.info("  - Nodos Neo4j: %d", neo4j_count)
    logger.info("=" * 60)

    # Cerrar conexiones
    from app.database import close_db, close_neo4j, close_redis

    await close_redis()
    await close_neo4j()
    await close_db()

    logger.info("✅ Seeding completado exitosamente.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SynkData Database Seeding Script")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Limpiar datos existentes antes de sembrar.",
    )
    args = parser.parse_args()

    asyncio.run(main(reset=args.reset))
