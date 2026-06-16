"""
Grafo de conocimiento e inteligencia relacional para SynkData.

Gestiona la construcción y consulta del grafo de relaciones entre entidades
de identidad (personas, empresas, teléfonos, correos, direcciones, cuentas,
dominios) utilizando Neo4j como motor de almacenamiento.

Incluye:
- Construcción de grafos de relación a partir de datos de identidad
- Búsqueda de caminos entre entidades
- Detección de redes ocultas
- Identificación de patrones sospechosos
- Generación de grafos compatibles con Cytoscape.js

Tipos de entidad soportados:
    Person, Company, Phone, Email, Address, Account, Domain

Tipos de relación soportados:
    OWNS, WORKS_AT, KNOWS, SHARES_ADDRESS, SHARES_PHONE,
    SHARES_EMAIL, RELATED_TO, DIRECTOR_OF

Patrones sospechosos detectados:
    - Direcciones/teléfonos compartidos entre personas no relacionadas
    - Cadenas de empresas fachada (shell companies)
    - Patrones de propiedad circular
    - Muchas personas conectadas a una sola entidad
    - Camino corto hacia entidades sancionadas

Todas las consultas Cypher utilizan parámetros para prevenir inyección.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.database import get_neo4j_session, get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class EntityType(str, Enum):
    """Tipos de entidad soportados en el grafo de conocimiento."""

    PERSON = "Person"
    COMPANY = "Company"
    PHONE = "Phone"
    EMAIL = "Email"
    ADDRESS = "Address"
    ACCOUNT = "Account"
    DOMAIN = "Domain"


class RelationshipType(str, Enum):
    """Tipos de relación soportados en el grafo de conocimiento."""

    OWNS = "OWNS"
    WORKS_AT = "WORKS_AT"
    KNOWS = "KNOWS"
    SHARES_ADDRESS = "SHARES_ADDRESS"
    SHARES_PHONE = "SHARES_PHONE"
    SHARES_EMAIL = "SHARES_EMAIL"
    RELATED_TO = "RELATED_TO"
    DIRECTOR_OF = "DIRECTOR_OF"


class PatternType(str, Enum):
    """Tipos de patrones sospechosos detectables."""

    SHARED_CONTACT_AMONG_UNRELATED = "shared_contact_among_unrelated"
    SHELL_COMPANY_CHAIN = "shell_company_chain"
    CIRCULAR_OWNERSHIP = "circular_ownership"
    HIGH_CONNECTIVITY = "high_connectivity"
    PROXIMITY_TO_SANCTIONED = "proximity_to_sanctioned"


# ---------------------------------------------------------------------------
# Modelos de datos de resultado
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GraphStatistics:
    """
    Estadísticas del grafo de relaciones.

    Attributes:
        node_count: Número total de nodos en el grafo.
        edge_count: Número total de aristas en el grafo.
        density: Densidad del grafo (0.0 a 1.0).
    """

    node_count: int
    edge_count: int
    density: float


@dataclass(frozen=True, slots=True)
class GraphResult:
    """
    Resultado de la construcción de un grafo de relaciones.

    Attributes:
        nodes: Lista de nodos en formato Cytoscape.js.
        edges: Lista de aristas en formato Cytoscape.js.
        statistics: Estadísticas del grafo.
    """

    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    statistics: GraphStatistics


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    """
    Resultado de la búsqueda de camino entre dos entidades.

    Attributes:
        found: Si se encontró un camino entre las entidades.
        path: Lista de IDs de entidades en el camino.
        path_length: Longitud del camino (número de aristas).
        entities: Datos de las entidades en el camino.
        relationships: Datos de las relaciones en el camino.
    """

    found: bool
    path: List[str]
    path_length: int
    entities: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SubGraph:
    """
    Subgrafo detectado dentro de una red.

    Attributes:
        id: Identificador único del subgrafo.
        nodes: Lista de IDs de nodos en el subgrafo.
        edges: Lista de aristas en el subgrafo.
        node_count: Número de nodos.
        edge_count: Número de aristas.
        risk_indicators: Indicadores de riesgo del subgrafo.
    """

    id: str
    nodes: List[str]
    edges: List[Dict[str, Any]]
    node_count: int
    edge_count: int
    risk_indicators: List[str]


@dataclass(frozen=True, slots=True)
class NetworkResult:
    """
    Resultado de la detección de redes ocultas.

    Attributes:
        networks: Lista de subgrafos detectados.
        risk_indicators: Indicadores de riesgo globales.
    """

    networks: List[SubGraph]
    risk_indicators: List[str]


@dataclass(frozen=True, slots=True)
class SuspiciousPattern:
    """
    Patrón sospechoso detectado en el grafo.

    Attributes:
        pattern_type: Tipo de patrón detectado.
        description: Descripción del patrón en español.
        severity: Severidad del patrón (critical, high, medium, low).
        entities: Entidades involucradas en el patrón.
        evidence: Evidencia que respalda la detección.
    """

    pattern_type: PatternType
    description: str
    severity: str
    entities: List[str]
    evidence: List[Dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SuspiciousPatternsResult:
    """
    Resultado de la identificación de patrones sospechosos.

    Attributes:
        patterns: Lista de patrones sospechosos detectados.
        risk_score: Puntuación de riesgo global (0-100).
        details: Detalles adicionales del análisis.
    """

    patterns: List[SuspiciousPattern]
    risk_score: float
    details: Dict[str, Any]


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_ENTITY_COLOR_MAP: Dict[str, str] = {
    EntityType.PERSON.value: "#4A90D9",
    EntityType.COMPANY.value: "#7B68EE",
    EntityType.PHONE.value: "#50C878",
    EntityType.EMAIL.value: "#FF6B6B",
    EntityType.ADDRESS.value: "#FFA500",
    EntityType.ACCOUNT.value: "#20B2AA",
    EntityType.DOMAIN.value: "#DDA0DD",
}

_RELATIONSHIP_COLOR_MAP: Dict[str, str] = {
    RelationshipType.OWNS.value: "#E74C3C",
    RelationshipType.WORKS_AT.value: "#3498DB",
    RelationshipType.KNOWS.value: "#2ECC71",
    RelationshipType.SHARES_ADDRESS.value: "#F39C12",
    RelationshipType.SHARES_PHONE.value: "#9B59B6",
    RelationshipType.SHARES_EMAIL.value: "#1ABC9C",
    RelationshipType.RELATED_TO.value: "#95A5A6",
    RelationshipType.DIRECTOR_OF.value: "#E67E22",
}

_CACHE_PREFIX = "kg:"
_CACHE_TTL = 600  # 10 minutos


# ---------------------------------------------------------------------------
# Servicio de grafo de conocimiento
# ---------------------------------------------------------------------------
class KnowledgeGraphService:
    """
    Servicio de grafo de conocimiento e inteligencia relacional.

    Gestiona la construcción, consulta y análisis del grafo de relaciones
    entre entidades de identidad utilizando Neo4j como motor de almacenamiento.

    Todos los métodos son asíncronos y utilizan sesiones Neo4j parametrizadas
    para prevenir inyección Cypher. Los resultados se cachean en Redis
    para consultas frecuentes.

    Example:
        >>> service = KnowledgeGraphService()
        >>> entity_id = await service.add_entity("Person", {"name": "Juan Pérez"})
        >>> graph = await service.build_graph(entity_id, {"name": "Juan Pérez"})
    """

    def __init__(self) -> None:
        """Inicializa el servicio con la configuración del proyecto."""
        self._settings = get_settings()

    # ── Construcción de grafo ─────────────────────────────────────────────

    async def build_graph(
        self, entity_id: str, entity_data: dict
    ) -> GraphResult:
        """
        Construye el grafo de relaciones para una entidad dada.

        Recupera la entidad y todas sus relaciones directas e indirectas
        desde Neo4j, generando un grafo compatible con Cytoscape.js.

        Args:
            entity_id: Identificador único de la entidad central.
            entity_data: Datos de la entidad para enriquecer el grafo.

        Returns:
            GraphResult: Grafo con nodos, aristas y estadísticas.
        """
        cache_key = f"{_CACHE_PREFIX}graph:{entity_id}"

        # Intentar obtener desde caché
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                data = json.loads(cached)
                logger.debug("Grafo obtenido desde caché: %s", entity_id)
                return GraphResult(
                    nodes=data["nodes"],
                    edges=data["edges"],
                    statistics=GraphStatistics(**data["statistics"]),
                )
        except Exception as exc:
            logger.warning("Error leyendo caché de grafo: %s", exc)

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[str] = set()

        try:
            async with get_neo4j_session() as session:
                # Consultar la entidad central y sus relaciones directas
                result = await session.run(
                    """
                    MATCH (center {entity_id: $entity_id})
                    OPTIONAL MATCH (center)-[r1]-(neighbor1)
                    OPTIONAL MATCH (neighbor1)-[r2]-(neighbor2)
                    WHERE neighbor2 <> center
                    RETURN center, r1, neighbor1, r2, neighbor2
                    """,
                    entity_id=entity_id,
                )
                records = await result.data()

                for record in records:
                    # Procesar nodo central
                    self._add_node_from_record(
                        record, "center", nodes, seen_nodes
                    )
                    # Procesar vecinos de primer nivel
                    self._add_node_from_record(
                        record, "neighbor1", nodes, seen_nodes
                    )
                    self._add_edge_from_record(
                        record, "r1", edges, seen_edges
                    )
                    # Procesar vecinos de segundo nivel
                    self._add_node_from_record(
                        record, "neighbor2", nodes, seen_nodes
                    )
                    self._add_edge_from_record(
                        record, "r2", edges, seen_edges
                    )

        except Exception as exc:
            logger.error(
                "Error construyendo grafo para entidad %s: %s",
                entity_id,
                exc,
            )
            # Retornar grafo mínimo con solo la entidad central
            nodes = [self._make_node(entity_id, entity_data)]
            edges = []

        # Calcular estadísticas
        node_count = len(nodes)
        edge_count = len(edges)
        max_edges = node_count * (node_count - 1) if node_count > 1 else 1
        density = edge_count / max_edges if max_edges > 0 else 0.0
        statistics = GraphStatistics(
            node_count=node_count,
            edge_count=edge_count,
            density=round(density, 4),
        )

        graph_result = GraphResult(
            nodes=nodes, edges=edges, statistics=statistics
        )

        # Cachear resultado
        try:
            redis = get_redis()
            import json

            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps(
                    {
                        "nodes": nodes,
                        "edges": edges,
                        "statistics": {
                            "node_count": statistics.node_count,
                            "edge_count": statistics.edge_count,
                            "density": statistics.density,
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando grafo: %s", exc)

        logger.info(
            "Grafo construido para %s: %d nodos, %d aristas, densidad=%.4f",
            entity_id,
            node_count,
            edge_count,
            density,
        )

        return graph_result

    # ── Búsqueda de conexiones ────────────────────────────────────────────

    async def find_connections(
        self, entity_id_1: str, entity_id_2: str
    ) -> ConnectionResult:
        """
        Encuentra el camino más corto entre dos entidades en el grafo.

        Utiliza el algoritmo de camino más corto de Neo4j para encontrar
        la ruta de conexión entre dos entidades, incluyendo todos los
        nodos y relaciones intermedios.

        Args:
            entity_id_1: Identificador de la primera entidad.
            entity_id_2: Identificador de la segunda entidad.

        Returns:
            ConnectionResult: Camino encontrado con entidades y relaciones.
        """
        cache_key = f"{_CACHE_PREFIX}conn:{entity_id_1}:{entity_id_2}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                data = json.loads(cached)
                return ConnectionResult(
                    found=data["found"],
                    path=data["path"],
                    path_length=data["path_length"],
                    entities=data["entities"],
                    relationships=data["relationships"],
                )
        except Exception as exc:
            logger.warning("Error leyendo caché de conexiones: %s", exc)

        try:
            async with get_neo4j_session() as session:
                result = await session.run(
                    """
                    MATCH (e1 {entity_id: $entity_id_1}),
                          (e2 {entity_id: $entity_id_2})
                    MATCH path = shortestPath((e1)-[*..6]-(e2))
                    RETURN path
                    """,
                    entity_id_1=entity_id_1,
                    entity_id_2=entity_id_2,
                )
                records = await result.data()

                if not records:
                    connection = ConnectionResult(
                        found=False,
                        path=[],
                        path_length=0,
                        entities=[],
                        relationships=[],
                    )
                else:
                    path_data = records[0].get("path", {})

                    # Extraer nodos y relaciones del camino
                    path_nodes: List[str] = []
                    path_entities: List[Dict[str, Any]] = []
                    path_relationships: List[Dict[str, Any]] = []

                    # Los nodos vienen en path.start y path.end, y los
                    # segmentos en path.segments (depende del driver)
                    segments = path_data.get("segments", [])

                    for segment in segments:
                        start = segment.get("start", {})
                        end = segment.get("end", {})
                        rel = segment.get("relationship", {})

                        start_id = start.get("properties", {}).get(
                            "entity_id", start.get("identity", "")
                        )
                        end_id = end.get("properties", {}).get(
                            "entity_id", end.get("identity", "")
                        )

                        if start_id not in path_nodes:
                            path_nodes.append(start_id)
                            path_entities.append(
                                {
                                    "entity_id": start_id,
                                    "labels": start.get("labels", []),
                                    "properties": start.get("properties", {}),
                                }
                            )

                        if end_id not in path_nodes:
                            path_nodes.append(end_id)
                            path_entities.append(
                                {
                                    "entity_id": end_id,
                                    "labels": end.get("labels", []),
                                    "properties": end.get("properties", {}),
                                }
                            )

                        path_relationships.append(
                            {
                                "type": rel.get("type", "UNKNOWN"),
                                "properties": rel.get("properties", {}),
                                "start_id": start_id,
                                "end_id": end_id,
                            }
                        )

                    connection = ConnectionResult(
                        found=True,
                        path=path_nodes,
                        path_length=len(path_relationships),
                        entities=path_entities,
                        relationships=path_relationships,
                    )

        except Exception as exc:
            logger.error(
                "Error buscando conexiones entre %s y %s: %s",
                entity_id_1,
                entity_id_2,
                exc,
            )
            connection = ConnectionResult(
                found=False,
                path=[],
                path_length=0,
                entities=[],
                relationships=[],
            )

        # Cachear resultado
        try:
            redis = get_redis()
            import json

            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps(
                    {
                        "found": connection.found,
                        "path": connection.path,
                        "path_length": connection.path_length,
                        "entities": connection.entities,
                        "relationships": connection.relationships,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Error cacheando conexión: %s", exc)

        return connection

    # ── Detección de redes ────────────────────────────────────────────────

    async def detect_networks(
        self, entity_id: str, depth: int = 3
    ) -> NetworkResult:
        """
        Detecta redes ocultas alrededor de una entidad.

        Analiza el vecindario de la entidad hasta la profundidad
        especificada para identificar clusters de entidades con
        alta conectividad que podrían indicar redes organizadas.

        Args:
            entity_id: Identificador de la entidad central.
            depth: Profundidad de búsqueda (1-5, por defecto 3).

        Returns:
            NetworkResult: Redes detectadas e indicadores de riesgo.
        """
        depth = max(1, min(5, depth))
        cache_key = f"{_CACHE_PREFIX}networks:{entity_id}:{depth}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                data = json.loads(cached)
                networks = [
                    SubGraph(
                        id=n["id"],
                        nodes=n["nodes"],
                        edges=n["edges"],
                        node_count=n["node_count"],
                        edge_count=n["edge_count"],
                        risk_indicators=n["risk_indicators"],
                    )
                    for n in data["networks"]
                ]
                return NetworkResult(
                    networks=networks,
                    risk_indicators=data["risk_indicators"],
                )
        except Exception as exc:
            logger.warning("Error leyendo caché de redes: %s", exc)

        networks: List[SubGraph] = []
        risk_indicators: List[str] = []

        try:
            async with get_neo4j_session() as session:
                # Detectar clusters usando conectividad
                result = await session.run(
                    """
                    MATCH (center {entity_id: $entity_id})
                    CALL apoc.path.subgraphAll(center, {
                        maxLevel: $depth,
                        relationshipFilter: null,
                        minDegree: 2
                    })
                    YIELD nodes, relationships
                    RETURN nodes, relationships
                    """,
                    entity_id=entity_id,
                    depth=depth,
                )
                records = await result.data()

                if records:
                    for idx, record in enumerate(records):
                        raw_nodes = record.get("nodes", [])
                        raw_rels = record.get("relationships", [])

                        if len(raw_nodes) < 2:
                            continue

                        node_ids: List[str] = []
                        edge_list: List[Dict[str, Any]] = []
                        indicators: List[str] = []

                        for node in raw_nodes:
                            node_id = node.get("properties", {}).get(
                                "entity_id", str(node.get("identity", ""))
                            )
                            node_ids.append(node_id)

                        for rel in raw_rels:
                            edge_list.append(
                                {
                                    "type": rel.get("type", "UNKNOWN"),
                                    "properties": rel.get("properties", {}),
                                }
                            )

                        # Analizar indicadores de riesgo del cluster
                        person_count = sum(
                            1
                            for n in raw_nodes
                            if "Person" in n.get("labels", [])
                        )
                        company_count = sum(
                            1
                            for n in raw_nodes
                            if "Company" in n.get("labels", [])
                        )

                        if person_count > 5:
                            indicators.append(
                                "Grupo con muchas personas conectadas"
                            )
                        if company_count > 3 and person_count < 2:
                            indicators.append(
                                "Posible red de empresas fachada"
                            )
                        if len(edge_list) > len(raw_nodes) * 2:
                            indicators.append(
                                "Alta densidad de conexiones"
                            )

                        networks.append(
                            SubGraph(
                                id=f"network_{idx}_{uuid.uuid4().hex[:8]}",
                                nodes=node_ids,
                                edges=edge_list,
                                node_count=len(node_ids),
                                edge_count=len(edge_list),
                                risk_indicators=indicators,
                            )
                        )

                        risk_indicators.extend(indicators)

        except Exception as exc:
            logger.error(
                "Error detectando redes para %s: %s", entity_id, exc
            )
            # Si APOC no está disponible, usar consulta alternativa simple
            networks = await self._detect_networks_fallback(
                entity_id, depth
            )

        network_result = NetworkResult(
            networks=networks,
            risk_indicators=list(set(risk_indicators)),
        )

        # Cachear resultado
        try:
            redis = get_redis()
            import json

            serialized = {
                "networks": [
                    {
                        "id": n.id,
                        "nodes": n.nodes,
                        "edges": n.edges,
                        "node_count": n.node_count,
                        "edge_count": n.edge_count,
                        "risk_indicators": n.risk_indicators,
                    }
                    for n in networks
                ],
                "risk_indicators": list(set(risk_indicators)),
            }
            await redis.setex(
                cache_key, _CACHE_TTL, json.dumps(serialized, ensure_ascii=False)
            )
        except Exception as exc:
            logger.warning("Error cacheando redes: %s", exc)

        logger.info(
            "Redes detectadas para %s: %d redes, %d indicadores de riesgo",
            entity_id,
            len(networks),
            len(risk_indicators),
        )

        return network_result

    # ── Patrones sospechosos ──────────────────────────────────────────────

    async def identify_suspicious_patterns(
        self, entity_id: str
    ) -> SuspiciousPatternsResult:
        """
        Identifica patrones sospechosos en las relaciones de una entidad.

        Analiza el grafo de relaciones para detectar:
        - Direcciones/teléfonos compartidos entre personas no relacionadas
        - Cadenas de empresas fachada (shell companies)
        - Patrones de propiedad circular
        - Muchas personas conectadas a una sola entidad
        - Camino corto hacia entidades sancionadas

        Args:
            entity_id: Identificador de la entidad a analizar.

        Returns:
            SuspiciousPatternsResult: Patrones detectados con puntuación de riesgo.
        """
        cache_key = f"{_CACHE_PREFIX}patterns:{entity_id}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                data = json.loads(cached)
                patterns = [
                    SuspiciousPattern(
                        pattern_type=PatternType(p["pattern_type"]),
                        description=p["description"],
                        severity=p["severity"],
                        entities=p["entities"],
                        evidence=p["evidence"],
                    )
                    for p in data["patterns"]
                ]
                return SuspiciousPatternsResult(
                    patterns=patterns,
                    risk_score=data["risk_score"],
                    details=data["details"],
                )
        except Exception as exc:
            logger.warning("Error leyendo caché de patrones: %s", exc)

        patterns: List[SuspiciousPattern] = []
        risk_score = 0.0

        try:
            async with get_neo4j_session() as session:
                # 1. Direcciones/teléfonos compartidos entre personas no
                #    relacionadas
                patterns.extend(
                    await self._detect_shared_contacts(session, entity_id)
                )

                # 2. Cadenas de empresas fachada
                patterns.extend(
                    await self._detect_shell_companies(session, entity_id)
                )

                # 3. Patrones de propiedad circular
                patterns.extend(
                    await self._detect_circular_ownership(session, entity_id)
                )

                # 4. Alta conectividad
                patterns.extend(
                    await self._detect_high_connectivity(session, entity_id)
                )

                # 5. Proximidad a entidades sancionadas
                patterns.extend(
                    await self._detect_sanctioned_proximity(session, entity_id)
                )

        except Exception as exc:
            logger.error(
                "Error identificando patrones sospechosos para %s: %s",
                entity_id,
                exc,
            )

        # Calcular puntuación de riesgo basada en patrones encontrados
        severity_scores = {"critical": 30, "high": 20, "medium": 10, "low": 5}
        risk_score = sum(
            severity_scores.get(p.severity, 5) for p in patterns
        )
        risk_score = min(100.0, risk_score)

        result = SuspiciousPatternsResult(
            patterns=patterns,
            risk_score=round(risk_score, 2),
            details={
                "entity_id": entity_id,
                "patterns_found": len(patterns),
                "critical_count": sum(
                    1 for p in patterns if p.severity == "critical"
                ),
                "high_count": sum(
                    1 for p in patterns if p.severity == "high"
                ),
                "medium_count": sum(
                    1 for p in patterns if p.severity == "medium"
                ),
                "low_count": sum(
                    1 for p in patterns if p.severity == "low"
                ),
            },
        )

        # Cachear resultado
        try:
            redis = get_redis()
            import json

            serialized = {
                "patterns": [
                    {
                        "pattern_type": p.pattern_type.value,
                        "description": p.description,
                        "severity": p.severity,
                        "entities": p.entities,
                        "evidence": p.evidence,
                    }
                    for p in patterns
                ],
                "risk_score": result.risk_score,
                "details": result.details,
            }
            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps(serialized, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("Error cacheando patrones: %s", exc)

        logger.info(
            "Patrones sospechosos para %s: %d patrones, risk_score=%.1f",
            entity_id,
            len(patterns),
            risk_score,
        )

        return result

    # ── Operaciones de escritura ──────────────────────────────────────────

    async def add_entity(self, entity_type: str, entity_data: dict) -> str:
        """
        Agrega un nodo al grafo de conocimiento en Neo4j.

        Crea una entidad del tipo especificado con las propiedades dadas.
        El identificador único se genera automáticamente si no se proporciona.

        Args:
            entity_type: Tipo de entidad (Person, Company, Phone, etc.).
            entity_data: Propiedades de la entidad.

        Returns:
            str: Identificador único de la entidad creada.

        Raises:
            ValueError: Si el tipo de entidad no es válido.
        """
        # Validar tipo de entidad
        valid_types = {e.value for e in EntityType}
        if entity_type not in valid_types:
            raise ValueError(
                f"Tipo de entidad inválido: '{entity_type}'. "
                f"Tipos válidos: {', '.join(sorted(valid_types))}"
            )

        entity_id = entity_data.get("entity_id", str(uuid.uuid4()))
        entity_data["entity_id"] = entity_id

        try:
            async with get_neo4j_session() as session:
                # Construir consulta parametrizada dinámica
                props_keys = list(entity_data.keys())
                props_pattern = ", ".join(
                    f"{k}: ${k}" for k in props_keys
                )

                query = (
                    f"MERGE (n:{entity_type} {{ {props_pattern} }}) "
                    f"RETURN n.entity_id AS entity_id"
                )

                result = await session.run(query, **entity_data)
                records = await result.data()

                created_id = (
                    records[0]["entity_id"]
                    if records
                    else entity_id
                )

                # Invalidar caché relacionado
                await self._invalidate_cache(entity_id)

                logger.info(
                    "Entidad creada: %s (tipo=%s)", created_id, entity_type
                )
                return created_id

        except Exception as exc:
            logger.error(
                "Error creando entidad tipo %s: %s", entity_type, exc
            )
            raise

    async def add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: Optional[dict] = None,
    ) -> None:
        """
        Agrega una relación entre dos entidades en el grafo.

        Crea una arista dirigida del tipo especificado entre las entidades
        identificadas por from_id y to_id, con las propiedades dadas.

        Args:
            from_id: Identificador de la entidad origen.
            to_id: Identificador de la entidad destino.
            rel_type: Tipo de relación (OWNS, WORKS_AT, etc.).
            properties: Propiedades opcionales de la relación.

        Raises:
            ValueError: Si el tipo de relación no es válido.
        """
        # Validar tipo de relación
        valid_rels = {r.value for r in RelationshipType}
        if rel_type not in valid_rels:
            raise ValueError(
                f"Tipo de relación inválido: '{rel_type}'. "
                f"Tipos válidos: {', '.join(sorted(valid_rels))}"
            )

        rel_props = properties or {}

        try:
            async with get_neo4j_session() as session:
                # Construir SET de propiedades si existen
                set_clause = ""
                params: Dict[str, Any] = {
                    "from_id": from_id,
                    "to_id": to_id,
                }

                if rel_props:
                    set_parts = []
                    for key, value in rel_props.items():
                        param_name = f"rel_{key}"
                        set_parts.append(f"r.{key} = ${param_name}")
                        params[param_name] = value
                    set_clause = " SET " + ", ".join(set_parts)

                query = (
                    f"MATCH (a {{entity_id: $from_id}}), "
                    f"(b {{entity_id: $to_id}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b)"
                    f"{set_clause} "
                    f"RETURN type(r) AS rel_type"
                )

                await session.run(query, **params)

                # Invalidar caché de ambas entidades
                await self._invalidate_cache(from_id)
                await self._invalidate_cache(to_id)

                logger.info(
                    "Relación creada: %s -[%s]-> %s", from_id, rel_type, to_id
                )

        except Exception as exc:
            logger.error(
                "Error creando relación %s de %s a %s: %s",
                rel_type,
                from_id,
                to_id,
                exc,
            )
            raise

    # ── Visualización de grafo ────────────────────────────────────────────

    async def get_entity_graph(
        self, entity_id: str, depth: int = 2
    ) -> dict:
        """
        Retorna el grafo de una entidad para visualización en el frontend.

        Genera un grafo en formato compatible con Cytoscape.js que incluye
        la entidad central y sus vecinos hasta la profundidad especificada.

        Args:
            entity_id: Identificador de la entidad central.
            depth: Profundidad de expansión (1-4, por defecto 2).

        Returns:
            dict: Grafo en formato Cytoscape.js con 'elements'.
        """
        depth = max(1, min(4, depth))
        cache_key = f"{_CACHE_PREFIX}viz:{entity_id}:{depth}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                import json

                return json.loads(cached)
        except Exception as exc:
            logger.warning("Error leyendo caché de visualización: %s", exc)

        elements: Dict[str, List[Dict[str, Any]]] = {
            "nodes": [],
            "edges": [],
        }
        seen_node_ids: set[str] = set()
        seen_edge_ids: set[str] = set()

        try:
            async with get_neo4j_session() as session:
                result = await session.run(
                    """
                    MATCH path = (center {entity_id: $entity_id})-[*..$depth]-(neighbor)
                    RETURN path
                    """,
                    entity_id=entity_id,
                    depth=depth,
                )
                records = await result.data()

                for record in records:
                    path_data = record.get("path", {})
                    segments = path_data.get("segments", [])

                    for segment in segments:
                        # Procesar nodo de inicio
                        start = segment.get("start", {})
                        start_id = start.get("properties", {}).get(
                            "entity_id", str(start.get("identity", ""))
                        )
                        if start_id and start_id not in seen_node_ids:
                            seen_node_ids.add(start_id)
                            elements["nodes"].append(
                                self._to_cytoscape_node(start, start_id)
                            )

                        # Procesar nodo final
                        end = segment.get("end", {})
                        end_id = end.get("properties", {}).get(
                            "entity_id", str(end.get("identity", ""))
                        )
                        if end_id and end_id not in seen_node_ids:
                            seen_node_ids.add(end_id)
                            elements["nodes"].append(
                                self._to_cytoscape_node(end, end_id)
                            )

                        # Procesar relación
                        rel = segment.get("relationship", {})
                        edge_id = str(rel.get("identity", ""))
                        if edge_id and edge_id not in seen_edge_ids:
                            seen_edge_ids.add(edge_id)
                            elements["edges"].append(
                                {
                                    "data": {
                                        "id": edge_id,
                                        "source": start_id,
                                        "target": end_id,
                                        "label": rel.get("type", ""),
                                        "color": _RELATIONSHIP_COLOR_MAP.get(
                                            rel.get("type", ""), "#95A5A6"
                                        ),
                                    }
                                }
                            )

        except Exception as exc:
            logger.error(
                "Error obteniendo grafo de visualización para %s: %s",
                entity_id,
                exc,
            )

        graph_data = {"elements": elements}

        # Cachear resultado
        try:
            redis = get_redis()
            import json

            await redis.setex(
                cache_key,
                _CACHE_TTL,
                json.dumps(graph_data, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("Error cacheando visualización: %s", exc)

        return graph_data

    # ── Métodos privados de detección de patrones ─────────────────────────

    async def _detect_shared_contacts(
        self, session, entity_id: str
    ) -> List[SuspiciousPattern]:
        """
        Detecta direcciones o teléfonos compartidos entre personas no
        relacionadas.

        Args:
            session: Sesión activa de Neo4j.
            entity_id: ID de la entidad a analizar.

        Returns:
            Lista de patrones sospechosos detectados.
        """
        patterns: List[SuspiciousPattern] = []

        try:
            # Buscar direcciones compartidas por personas sin relación KNOWS
            result = await session.run(
                """
                MATCH (p1:Person)-[:SHARES_ADDRESS]->(addr:Address)<-[:SHARES_ADDRESS]-(p2:Person)
                WHERE p1.entity_id = $entity_id
                  AND NOT (p1)-[:KNOWS]-(p2)
                  AND p1.entity_id < p2.entity_id
                RETURN p1.entity_id AS person1, p2.entity_id AS person2,
                       addr.entity_id AS shared_address, addr.full_address AS address_text
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                patterns.append(
                    SuspiciousPattern(
                        pattern_type=PatternType.SHARED_CONTACT_AMONG_UNRELATED,
                        description=(
                            f"Dirección compartida entre personas no relacionadas: "
                            f"{record.get('address_text', 'N/A')}"
                        ),
                        severity="high",
                        entities=[
                            record["person1"],
                            record["person2"],
                            record["shared_address"],
                        ],
                        evidence=[record],
                    )
                )

            # Buscar teléfonos compartidos por personas sin relación KNOWS
            result = await session.run(
                """
                MATCH (p1:Person)-[:SHARES_PHONE]->(ph:Phone)<-[:SHARES_PHONE]-(p2:Person)
                WHERE p1.entity_id = $entity_id
                  AND NOT (p1)-[:KNOWS]-(p2)
                  AND p1.entity_id < p2.entity_id
                RETURN p1.entity_id AS person1, p2.entity_id AS person2,
                       ph.entity_id AS shared_phone, ph.number AS phone_number
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                patterns.append(
                    SuspiciousPattern(
                        pattern_type=PatternType.SHARED_CONTACT_AMONG_UNRELATED,
                        description=(
                            f"Teléfono compartido entre personas no relacionadas: "
                            f"{record.get('phone_number', 'N/A')}"
                        ),
                        severity="high",
                        entities=[
                            record["person1"],
                            record["person2"],
                            record["shared_phone"],
                        ],
                        evidence=[record],
                    )
                )

        except Exception as exc:
            logger.warning("Error detectando contactos compartidos: %s", exc)

        return patterns

    async def _detect_shell_companies(
        self, session, entity_id: str
    ) -> List[SuspiciousPattern]:
        """
        Detecta cadenas de empresas fachada (shell companies).

        Una empresa fachada se identifica cuando:
        - Una empresa es propiedad de otra empresa
        - La cadena de propiedad tiene más de 2 niveles
        - Las empresas no tienen empleados registrados

        Args:
            session: Sesión activa de Neo4j.
            entity_id: ID de la entidad a analizar.

        Returns:
            Lista de patrones sospechosos detectados.
        """
        patterns: List[SuspiciousPattern] = []

        try:
            result = await session.run(
                """
                MATCH path = (c1:Company)-[:OWNS*2..4]->(c2:Company)
                WHERE c1.entity_id = $entity_id
                  AND NOT exists((c2)<-[:WORKS_AT]-(:Person))
                RETURN [n IN nodes(path) | n.entity_id] AS chain,
                       [r IN relationships(path) | type(r)] AS rels,
                       length(path) AS chain_length
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                chain = record.get("chain", [])
                patterns.append(
                    SuspiciousPattern(
                        pattern_type=PatternType.SHELL_COMPANY_CHAIN,
                        description=(
                            f"Cadena de empresas fachada detectada "
                            f"(longitud: {record.get('chain_length', 0)}). "
                            f"Las empresas en la cadena no tienen empleados registrados."
                        ),
                        severity="critical",
                        entities=chain,
                        evidence=[record],
                    )
                )

        except Exception as exc:
            logger.warning("Error detectando empresas fachada: %s", exc)

        return patterns

    async def _detect_circular_ownership(
        self, session, entity_id: str
    ) -> List[SuspiciousPattern]:
        """
        Detecta patrones de propiedad circular.

        La propiedad circular ocurre cuando una cadena de propiedad
        regresa a la entidad de origen, creando un ciclo.

        Args:
            session: Sesión activa de Neo4j.
            entity_id: ID de la entidad a analizar.

        Returns:
            Lista de patrones sospechosos detectados.
        """
        patterns: List[SuspiciousPattern] = []

        try:
            result = await session.run(
                """
                MATCH path = (c1:Company)-[:OWNS*2..5]->(c1)
                WHERE c1.entity_id = $entity_id
                RETURN [n IN nodes(path) | n.entity_id] AS cycle,
                       length(path) AS cycle_length
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                cycle = record.get("cycle", [])
                # Eliminar duplicados del ciclo
                unique_entities = list(dict.fromkeys(cycle))
                patterns.append(
                    SuspiciousPattern(
                        pattern_type=PatternType.CIRCULAR_OWNERSHIP,
                        description=(
                            f"Patrón de propiedad circular detectado "
                            f"(longitud del ciclo: {record.get('cycle_length', 0)}). "
                            f"Esto puede indicar una estructura de control oculta."
                        ),
                        severity="critical",
                        entities=unique_entities,
                        evidence=[record],
                    )
                )

        except Exception as exc:
            logger.warning(
                "Error detectando propiedad circular: %s", exc
            )

        return patterns

    async def _detect_high_connectivity(
        self, session, entity_id: str
    ) -> List[SuspiciousPattern]:
        """
        Detecta entidades con alta conectividad (muchas personas conectadas).

        Una entidad con demasiadas personas conectadas puede indicar
        un nodo de coordinación sospechoso.

        Args:
            session: Sesión activa de Neo4j.
            entity_id: ID de la entidad a analizar.

        Returns:
            Lista de patrones sospechosos detectados.
        """
        patterns: List[SuspiciousPattern] = []

        try:
            # Contar personas conectadas a la entidad
            result = await session.run(
                """
                MATCH (center {entity_id: $entity_id})--(p:Person)
                RETURN count(p) AS person_count,
                       collect(p.entity_id)[0..10] AS sample_persons
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                person_count = record.get("person_count", 0)
                if person_count > 8:
                    severity = "critical" if person_count > 15 else "high"
                    patterns.append(
                        SuspiciousPattern(
                            pattern_type=PatternType.HIGH_CONNECTIVITY,
                            description=(
                                f"Entidad con alta conectividad: "
                                f"{person_count} personas conectadas. "
                                f"Esto puede indicar un nodo de coordinación."
                            ),
                            severity=severity,
                            entities=record.get("sample_persons", []) + [entity_id],
                            evidence=[record],
                        )
                    )

        except Exception as exc:
            logger.warning(
                "Error detectando alta conectividad: %s", exc
            )

        return patterns

    async def _detect_sanctioned_proximity(
        self, session, entity_id: str
    ) -> List[SuspiciousPattern]:
        """
        Detecta proximidad a entidades sancionadas.

        Busca caminos cortos (hasta 3 saltos) entre la entidad
        y entidades marcadas como sancionadas.

        Args:
            session: Sesión activa de Neo4j.
            entity_id: ID de la entidad a analizar.

        Returns:
            Lista de patrones sospechosos detectados.
        """
        patterns: List[SuspiciousPattern] = []

        try:
            result = await session.run(
                """
                MATCH path = shortestPath(
                    (e {entity_id: $entity_id})-[*..3]-(s:Person)
                )
                WHERE s.sanctioned = true OR s.ofac_listed = true
                RETURN e.entity_id AS entity,
                       s.entity_id AS sanctioned_entity,
                       s.name AS sanctioned_name,
                       length(path) AS distance
                """,
                entity_id=entity_id,
            )
            records = await result.data()

            for record in records:
                distance = record.get("distance", 99)
                if distance <= 3:
                    severity = "critical" if distance <= 1 else "high" if distance <= 2 else "medium"
                    patterns.append(
                        SuspiciousPattern(
                            pattern_type=PatternType.PROXIMITY_TO_SANCTIONED,
                            description=(
                                f"Entidad a {distance} saltos de entidad sancionada: "
                                f"{record.get('sanctioned_name', 'N/A')}. "
                                f"La proximidad a personas sancionadas aumenta el riesgo."
                            ),
                            severity=severity,
                            entities=[
                                record.get("entity", entity_id),
                                record.get("sanctioned_entity", ""),
                            ],
                            evidence=[record],
                        )
                    )

        except Exception as exc:
            logger.warning(
                "Error detectando proximidad a sancionados: %s", exc
            )

        return patterns

    # ── Métodos privados auxiliares ───────────────────────────────────────

    async def _detect_networks_fallback(
        self, entity_id: str, depth: int
    ) -> List[SubGraph]:
        """
        Método alternativo de detección de redes cuando APOC no está
        disponible en Neo4j.

        Args:
            entity_id: ID de la entidad central.
            depth: Profundidad de búsqueda.

        Returns:
            Lista de subgrafos detectados.
        """
        networks: List[SubGraph] = []

        try:
            async with get_neo4j_session() as session:
                result = await session.run(
                    """
                    MATCH (center {entity_id: $entity_id})-[*..$depth]-(neighbor)
                    WITH collect(DISTINCT neighbor) AS neighbors
                    UNWIND neighbors AS n
                    MATCH (n)-[r]-(m) WHERE m IN neighbors
                    RETURN collect(DISTINCT {
                        node_id: n.entity_id,
                        node_labels: labels(n),
                        rel_type: type(r)
                    }) AS connections
                    """,
                    entity_id=entity_id,
                    depth=depth,
                )
                records = await result.data()

                if records:
                    all_nodes: List[str] = []
                    all_edges: List[Dict[str, Any]] = []

                    for record in records:
                        connections = record.get("connections", [])
                        for conn in connections:
                            node_id = conn.get("node_id", "")
                            if node_id and node_id not in all_nodes:
                                all_nodes.append(node_id)
                            all_edges.append(
                                {"type": conn.get("rel_type", "UNKNOWN")}
                            )

                    if all_nodes:
                        networks.append(
                            SubGraph(
                                id=f"network_fallback_{uuid.uuid4().hex[:8]}",
                                nodes=all_nodes,
                                edges=all_edges,
                                node_count=len(all_nodes),
                                edge_count=len(all_edges),
                                risk_indicators=[],
                            )
                        )

        except Exception as exc:
            logger.error(
                "Error en detección de redes fallback: %s", exc
            )

        return networks

    def _add_node_from_record(
        self,
        record: dict,
        key: str,
        nodes: List[Dict[str, Any]],
        seen: set[str],
    ) -> None:
        """
        Agrega un nodo a la lista si no existe ya, extrayéndolo del
        registro de Neo4j.

        Args:
            record: Registro de resultado de Neo4j.
            key: Clave del registro que contiene el nodo.
            nodes: Lista de nodos acumulada.
            seen: Conjunto de IDs ya procesados.
        """
        node_data = record.get(key)
        if not node_data:
            return

        node_id = node_data.get("properties", {}).get(
            "entity_id", str(node_data.get("identity", ""))
        )
        if not node_id or node_id in seen:
            return

        seen.add(node_id)
        nodes.append(self._to_cytoscape_node(node_data, node_id))

    def _add_edge_from_record(
        self,
        record: dict,
        key: str,
        edges: List[Dict[str, Any]],
        seen: set[str],
    ) -> None:
        """
        Agrega una arista a la lista si no existe ya, extrayéndola del
        registro de Neo4j.

        Args:
            record: Registro de resultado de Neo4j.
            key: Clave del registro que contiene la relación.
            edges: Lista de aristas acumulada.
            seen: Conjunto de IDs ya procesados.
        """
        rel_data = record.get(key)
        if not rel_data:
            return

        edge_id = str(rel_data.get("identity", ""))
        if not edge_id or edge_id in seen:
            return

        seen.add(edge_id)
        start_id = str(
            rel_data.get("start", rel_data.get("startNode", ""))
        )
        end_id = str(rel_data.get("end", rel_data.get("endNode", "")))

        edges.append(
            {
                "data": {
                    "id": edge_id,
                    "source": start_id,
                    "target": end_id,
                    "label": rel_data.get("type", ""),
                    "color": _RELATIONSHIP_COLOR_MAP.get(
                        rel_data.get("type", ""), "#95A5A6"
                    ),
                }
            }
        )

    def _to_cytoscape_node(self, node_data: dict, node_id: str) -> dict:
        """
        Convierte un nodo de Neo4j a formato Cytoscape.js.

        Args:
            node_data: Datos del nodo desde Neo4j.
            node_id: Identificador del nodo.

        Returns:
            dict: Nodo en formato Cytoscape.js.
        """
        labels = node_data.get("labels", [])
        properties = node_data.get("properties", {})
        label = labels[0] if labels else "Unknown"
        display_name = properties.get("name", properties.get("full_address", node_id))

        return {
            "data": {
                "id": node_id,
                "label": display_name,
                "type": label,
                "color": _ENTITY_COLOR_MAP.get(label, "#95A5A6"),
                **properties,
            }
        }

    def _make_node(self, entity_id: str, entity_data: dict) -> dict:
        """
        Crea un nodo Cytoscape.js a partir de datos simples.

        Args:
            entity_id: Identificador de la entidad.
            entity_data: Datos de la entidad.

        Returns:
            dict: Nodo en formato Cytoscape.js.
        """
        entity_type = entity_data.get("type", "Unknown")
        return {
            "data": {
                "id": entity_id,
                "label": entity_data.get("name", entity_id),
                "type": entity_type,
                "color": _ENTITY_COLOR_MAP.get(entity_type, "#95A5A6"),
                **entity_data,
            }
        }

    async def _invalidate_cache(self, entity_id: str) -> None:
        """
        Invalida las entradas de caché relacionadas con una entidad.

        Args:
            entity_id: Identificador de la entidad modificada.
        """
        try:
            redis = get_redis()
            keys_to_delete = []

            # Buscar todas las claves de caché relacionadas
            async for key in redis.scan_iter(match=f"{_CACHE_PREFIX}*{entity_id}*"):
                keys_to_delete.append(key)

            if keys_to_delete:
                await redis.delete(*keys_to_delete)
                logger.debug(
                    "Caché invalidado: %d claves para %s",
                    len(keys_to_delete),
                    entity_id,
                )
        except Exception as exc:
            logger.warning("Error invalidando caché: %s", exc)
