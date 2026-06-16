"""
Servicio de descubrimiento social y profesional para SynkData.

Proporciona descubrimiento integral de perfiles sociales y profesionales
incluyendo:
- Búsqueda en LinkedIn (perfiles profesionales)
- Búsqueda en GitHub (perfiles de desarrollador)
- Cálculo de puntuación profesional
- Cálculo de huella digital
- Agregación de resultados de múltiples fuentes

Características:
- Ejecución paralela de búsquedas en múltiples fuentes
- Caché en Redis para resultados repetidos
- Degradación graceful: si una fuente falla, se retorna resultado parcial
- Puntuación profesional basada en múltiples factores
- Integración con servicios de username y email intelligence
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.database import get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modelos de datos internos (dataclasses)
# ---------------------------------------------------------------------------
@dataclass
class LinkedInProfile:
    """
    Perfil de LinkedIn de una persona.

    Attributes:
        name: Nombre completo.
        headline: Título/encabezado profesional.
        company: Empresa actual.
        location: Ubicación geográfica.
        connections: Número de conexiones.
        profile_url: URL del perfil.
    """

    name: str = ""
    headline: str = ""
    company: str = ""
    location: str = ""
    connections: int = 0
    profile_url: str = ""


@dataclass
class GitHubProfile:
    """
    Perfil de GitHub de un usuario.

    Attributes:
        username: Nombre de usuario en GitHub.
        name: Nombre completo.
        bio: Biografía del perfil.
        repos: Número de repositorios públicos.
        followers: Número de seguidores.
        contributions: Contribuciones en el último año.
        languages: Lenguajes de programación principales.
        profile_url: URL del perfil.
    """

    username: str = ""
    name: str = ""
    bio: str = ""
    repos: int = 0
    followers: int = 0
    contributions: int = 0
    languages: List[str] = field(default_factory=list)
    profile_url: str = ""


@dataclass
class ProfessionalScore:
    """
    Puntuación profesional calculada a partir de perfiles encontrados.

    Attributes:
        score: Puntuación global (0-100).
        factors: Factores que contribuyen a la puntuación.
    """

    score: float = 0.0
    factors: Dict[str, float] = field(default_factory=dict)


@dataclass
class SocialDiscoveryResult:
    """
    Resultado completo del descubrimiento social y profesional.

    Attributes:
        profiles_found: Número total de perfiles encontrados.
        social_profiles: Lista de perfiles sociales.
        professional_score: Puntuación profesional.
        digital_footprint_score: Puntuación de huella digital.
        presence_score: Puntuación de presencia digital.
        linkedin_profiles: Perfiles de LinkedIn.
        github_profile: Perfil de GitHub.
    """

    profiles_found: int = 0
    social_profiles: List[Dict[str, Any]] = field(default_factory=list)
    professional_score: ProfessionalScore = field(default_factory=ProfessionalScore)
    digital_footprint_score: float = 0.0
    presence_score: float = 0.0
    linkedin_profiles: List[LinkedInProfile] = field(default_factory=list)
    github_profile: Optional[GitHubProfile] = None


class SocialDiscoveryService:
    """
    Servicio de descubrimiento social y profesional.

    Orquesta la búsqueda y agregación de información de una persona
    en múltiples redes sociales y plataformas profesionales, calculando
    puntuaciones de profesionalismo y huella digital.

    Características:
    - Búsqueda paralela en LinkedIn y GitHub
    - Cálculo de puntuación profesional multi-factor
    - Cálculo de huella digital
    - Caché en Redis con TTL configurable
    - Degradación graceful ante fallos de APIs
    """

    def __init__(self) -> None:
        """Inicializa el servicio con configuración del proyecto."""
        self._settings = get_settings()
        self._cache_ttl = self._settings.REDIS_CACHE_TTL
        self._http_timeout = 15.0

    # ── Método principal ─────────────────────────────────────────────────
    async def discover(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
    ) -> SocialDiscoveryResult:
        """
        Ejecuta el descubrimiento social y profesional de una persona.

        Busca información en múltiples fuentes basándose en el nombre,
        correo electrónico, teléfono y/o nombre de usuario proporcionados.

        Args:
            name: Nombre completo de la persona.
            email: Correo electrónico (opcional).
            phone: Número telefónico (opcional).
            username: Nombre de usuario (opcional).

        Returns:
            SocialDiscoveryResult: Resultado del descubrimiento social.
        """
        result = SocialDiscoveryResult()

        # ── Verificar caché global ───────────────────────────────────────
        cache_key_parts = [f"name:{name}"]
        if email:
            cache_key_parts.append(f"email:{email}")
        if username:
            cache_key_parts.append(f"username:{username}")
        cache_key = f"digital:social:discover:{':'.join(cache_key_parts)}"

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return self._deserialize_result(cached_data)
        except Exception:
            logger.debug("Caché no disponible para descubrimiento social de %s", name)

        # ── Preparar tareas de búsqueda ──────────────────────────────────
        tasks = []

        # Búsqueda en LinkedIn por nombre
        tasks.append(self.search_linkedin(name))

        # Búsqueda en GitHub por username
        if username:
            tasks.append(self.search_github(username))

        # ── Ejecutar búsquedas en paralelo ───────────────────────────────
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        # ── Procesar resultados de LinkedIn ──────────────────────────────
        for search_result in search_results:
            if isinstance(search_result, list):
                # Resultado de LinkedIn
                for item in search_result:
                    if isinstance(item, LinkedInProfile):
                        result.linkedin_profiles.append(item)
            elif isinstance(search_result, GitHubProfile):
                result.github_profile = search_result
            else:
                logger.debug("Resultado de búsqueda inesperado: %s", type(search_result))

        # ── Agregar perfiles de GitHub a social_profiles ─────────────────
        if result.github_profile:
            result.social_profiles.append({
                "platform": "GitHub",
                "username": result.github_profile.username,
                "name": result.github_profile.name,
                "bio": result.github_profile.bio,
                "url": result.github_profile.profile_url,
                "repos": result.github_profile.repos,
                "followers": result.github_profile.followers,
                "languages": result.github_profile.languages,
                "category": "developer",
            })

        # ── Agregar perfiles de LinkedIn a social_profiles ───────────────
        for li_profile in result.linkedin_profiles:
            result.social_profiles.append({
                "platform": "LinkedIn",
                "name": li_profile.name,
                "headline": li_profile.headline,
                "company": li_profile.company,
                "location": li_profile.location,
                "connections": li_profile.connections,
                "url": li_profile.profile_url,
                "category": "professional",
            })

        # ── Calcular número total de perfiles ────────────────────────────
        result.profiles_found = len(result.social_profiles)

        # ── Calcular puntuación profesional ──────────────────────────────
        result.professional_score = await self.calculate_professional_score(
            result.social_profiles,
        )

        # ── Calcular huella digital ──────────────────────────────────────
        result.digital_footprint_score = self._calculate_digital_footprint(result)

        # ── Calcular puntuación de presencia ─────────────────────────────
        result.presence_score = self._calculate_presence_score(result)

        # ── Cachear resultado ────────────────────────────────────────────
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                self._cache_ttl,
                json.dumps(self._serialize_result(result)),
            )
        except Exception:
            logger.debug("No se pudo cachear resultado de descubrimiento social para %s", name)

        return result

    # ── Búsqueda en LinkedIn ─────────────────────────────────────────────
    async def search_linkedin(
        self,
        name: str,
        company: Optional[str] = None,
    ) -> List[LinkedInProfile]:
        """
        Busca perfiles de LinkedIn por nombre y opcionalmente por empresa.

        Utiliza la API de LinkedIn (o un servicio proxy) para buscar
        perfiles profesionales. En ausencia de API key, retorna una
        lista vacía con degradación graceful.

        Args:
            name: Nombre completo de la persona a buscar.
            company: Nombre de la empresa para filtrar (opcional).

        Returns:
            List[LinkedInProfile]: Lista de perfiles de LinkedIn encontrados.
        """
        cache_key = f"digital:social:linkedin:{name}:{company or ''}"

        # ── Verificar caché ──────────────────────────────────────────────
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return [
                    LinkedInProfile(**p) for p in cached_data
                ]
        except Exception:
            logger.debug("Caché no disponible para LinkedIn de %s", name)

        profiles: List[LinkedInProfile] = []

        # ── Nota: La API oficial de LinkedIn requiere OAuth 2.0 y aprobación ─
        # En producción se puede usar:
        # - LinkedIn People Search API (requiere Partnership)
        # - Proxycurl API (https://nubela.co/proxycurl/)
        # - SerpAPI (Google search de perfiles LinkedIn)
        # - PhantomBuster
        #
        # Aquí implementamos la estructura con un fallback a búsqueda web.

        try:
            # ── Intentar con Proxycurl / SerpAPI si está configurado ─────
            linkedin_api_key = getattr(
                self._settings, "LINKEDIN_API_KEY", "",
            )
            linkedin_api_url = getattr(
                self._settings, "LINKEDIN_API_URL", "https://nubela.co/proxycurl/api/v2",
            )

            if linkedin_api_key:
                async with httpx.AsyncClient(
                    timeout=self._http_timeout,
                    headers={"Authorization": f"Bearer {linkedin_api_key}"},
                ) as client:
                    # ── Búsqueda de persona en LinkedIn ────────────────────
                    search_params: Dict[str, Any] = {
                        "first_name": name.split()[0] if name else "",
                        "last_name": name.split()[-1] if len(name.split()) > 1 else "",
                    }
                    if company:
                        search_params["company"] = company

                    response = await client.get(
                        f"{linkedin_api_url}/linkedin/profile",
                        params=search_params,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        profile_data = data.get("profile", data)

                        li_profile = LinkedInProfile(
                            name=profile_data.get("full_name", ""),
                            headline=profile_data.get("headline", ""),
                            company=profile_data.get("current_company", {}).get("name", ""),
                            location=profile_data.get("location", ""),
                            connections=profile_data.get("connections", 0),
                            profile_url=profile_data.get("profile_url", ""),
                        )
                        profiles.append(li_profile)

            else:
                # ── Fallback: Construir URL de búsqueda ──────────────────
                # Sin API key, generamos URLs de búsqueda pero no ejecutamos
                logger.debug(
                    "LinkedIn API key no configurada. "
                    "Se recomienda configurar SYNKDATA_LINKEDIN_API_KEY "
                    "para habilitar la búsqueda en LinkedIn."
                )

                # Construir URL de búsqueda pública como referencia
                search_query = name.replace(" ", "+")
                if company:
                    search_query += f"+{company}"
                profile_url = (
                    f"https://www.linkedin.com/pub/dir?"
                    f"firstName={name.split()[0] if name else ''}"
                    f"&lastName={name.split()[-1] if len(name.split()) > 1 else ''}"
                )

                # Crear perfil placeholder con la URL de búsqueda
                profiles.append(LinkedInProfile(
                    name=name,
                    profile_url=profile_url,
                ))

        except httpx.TimeoutException:
            logger.warning("Timeout al buscar en LinkedIn para %s", name)
        except httpx.ConnectError:
            logger.warning("Error de conexión a LinkedIn para %s", name)
        except Exception as exc:
            logger.error("Error inesperado al buscar en LinkedIn: %s", exc)

        # ── Cachear resultado ────────────────────────────────────────────
        if profiles:
            try:
                redis = get_redis()
                await redis.setex(
                    cache_key,
                    self._cache_ttl * 2,
                    json.dumps([
                        {
                            "name": p.name,
                            "headline": p.headline,
                            "company": p.company,
                            "location": p.location,
                            "connections": p.connections,
                            "profile_url": p.profile_url,
                        }
                        for p in profiles
                    ]),
                )
            except Exception:
                logger.debug("No se pudo cachear resultado de LinkedIn para %s", name)

        return profiles

    # ── Búsqueda en GitHub ───────────────────────────────────────────────
    async def search_github(self, username: str) -> GitHubProfile:
        """
        Busca el perfil de GitHub de un usuario.

        Utiliza la API pública de GitHub para obtener información
        detallada del perfil, incluyendo repositorios, seguidores
        y lenguajes de programación.

        Args:
            username: Nombre de usuario en GitHub.

        Returns:
            GitHubProfile: Perfil de GitHub encontrado.
        """
        cache_key = f"digital:social:github:{username}"

        # ── Verificar caché ──────────────────────────────────────────────
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return GitHubProfile(**cached_data)
        except Exception:
            logger.debug("Caché no disponible para GitHub de %s", username)

        profile = GitHubProfile(
            username=username,
            profile_url=f"https://github.com/{username}",
        )

        try:
            async with httpx.AsyncClient(
                timeout=self._http_timeout,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "SynkData-Intelligence-Platform",
                },
            ) as client:
                # ── Obtener perfil del usuario ────────────────────────────
                response = await client.get(
                    f"https://api.github.com/users/{username}",
                )

                if response.status_code == 200:
                    data = response.json()
                    profile.name = data.get("name", "") or ""
                    profile.bio = data.get("bio", "") or ""
                    profile.repos = data.get("public_repos", 0)
                    profile.followers = data.get("followers", 0)

                    # ── Obtener lenguajes de los repositorios ─────────────
                    languages = await self._fetch_github_languages(
                        username, client,
                    )
                    profile.languages = languages

                    # ── Estimar contribuciones ─────────────────────────────
                    # La API de GitHub no expone contribuciones directamente,
                    # pero podemos estimarlas por los eventos recientes
                    profile.contributions = await self._estimate_github_contributions(
                        username, client,
                    )

                elif response.status_code == 404:
                    logger.debug("Usuario %s no encontrado en GitHub", username)
                    profile.username = ""  # Marcar como no encontrado
                elif response.status_code == 403:
                    logger.warning("Rate limit de GitHub API alcanzado para %s", username)
                else:
                    logger.debug(
                        "Respuesta inesperada de GitHub API: %d para %s",
                        response.status_code, username,
                    )

        except httpx.TimeoutException:
            logger.warning("Timeout al consultar GitHub API para %s", username)
        except httpx.ConnectError:
            logger.warning("Error de conexión a GitHub API para %s", username)
        except Exception as exc:
            logger.error("Error inesperado al consultar GitHub API: %s", exc)

        # ── Cachear resultado ────────────────────────────────────────────
        if profile.username:  # Solo cachear si se encontró
            try:
                redis = get_redis()
                await redis.setex(
                    cache_key,
                    self._cache_ttl * 6,  # TTL largo (perfil estable)
                    json.dumps({
                        "username": profile.username,
                        "name": profile.name,
                        "bio": profile.bio,
                        "repos": profile.repos,
                        "followers": profile.followers,
                        "contributions": profile.contributions,
                        "languages": profile.languages,
                        "profile_url": profile.profile_url,
                    }),
                )
            except Exception:
                logger.debug("No se pudo cachear resultado de GitHub para %s", username)

        return profile

    # ── Cálculo de puntuación profesional ────────────────────────────────
    async def calculate_professional_score(
        self,
        profiles: List[Dict[str, Any]],
    ) -> ProfessionalScore:
        """
        Calcula la puntuación profesional basada en los perfiles encontrados.

        Evalúa múltiples factores para determinar el nivel de
        profesionalismo de la presencia digital de una persona:
        - Presencia en LinkedIn
        - Actividad en GitHub
        - Dominios profesionales (correo corporativo)
        - Consistencia social
        - Completitud del perfil

        Args:
            profiles: Lista de perfiles encontrados.

        Returns:
            ProfessionalScore: Puntuación profesional con desglose de factores.
        """
        score = ProfessionalScore()
        total_score = 0.0

        # ── Factor 1: Presencia en LinkedIn (máx 25 puntos) ──────────────
        linkedin_profiles = [
            p for p in profiles if p.get("platform") == "LinkedIn"
        ]
        if linkedin_profiles:
            li_factor = 15.0
            # Bonus por headline y empresa
            for lp in linkedin_profiles:
                if lp.get("headline"):
                    li_factor += 3.0
                if lp.get("company"):
                    li_factor += 4.0
                if lp.get("connections", 0) > 100:
                    li_factor += 3.0
            total_score += min(li_factor, 25.0)
            score.factors["linkedin_presence"] = min(li_factor, 25.0)
        else:
            score.factors["linkedin_presence"] = 0.0

        # ── Factor 2: Actividad en GitHub (máx 25 puntos) ────────────────
        github_profiles = [
            p for p in profiles if p.get("platform") == "GitHub"
        ]
        if github_profiles:
            gh_factor = 10.0
            gp = github_profiles[0]
            if gp.get("repos", 0) > 5:
                gh_factor += 5.0
            if gp.get("repos", 0) > 20:
                gh_factor += 3.0
            if gp.get("followers", 0) > 10:
                gh_factor += 4.0
            if gp.get("followers", 0) > 100:
                gh_factor += 3.0
            if gp.get("languages"):
                gh_factor += 2.0  # Diversidad de lenguajes
            total_score += min(gh_factor, 25.0)
            score.factors["github_activity"] = min(gh_factor, 25.0)
        else:
            score.factors["github_activity"] = 0.0

        # ── Factor 3: Dominios profesionales (máx 20 puntos) ─────────────
        professional_platforms = {"LinkedIn", "GitHub", "Stack Overflow", "Dev.to"}
        professional_count = sum(
            1 for p in profiles
            if p.get("platform") in professional_platforms
        )
        prof_factor = min(professional_count * 7.0, 20.0)
        total_score += prof_factor
        score.factors["professional_domains"] = prof_factor

        # ── Factor 4: Consistencia social (máx 15 puntos) ────────────────
        total_profiles = len(profiles)
        if total_profiles >= 3:
            consistency_factor = 10.0
            if total_profiles >= 5:
                consistency_factor += 5.0
            total_score += consistency_factor
            score.factors["social_consistency"] = consistency_factor
        else:
            score.factors["social_consistency"] = total_profiles * 3.0

        # ── Factor 5: Completitud del perfil (máx 15 puntos) ─────────────
        completeness_score = 0.0
        for p in profiles:
            fields_filled = sum(
                1 for key in ["name", "bio", "company", "location", "headline"]
                if p.get(key)
            )
            completeness_score += fields_filled / 5.0 * 3.0
        completeness_score = min(completeness_score, 15.0)
        total_score += completeness_score
        score.factors["profile_completeness"] = completeness_score

        # ── Puntuación final ─────────────────────────────────────────────
        score.score = round(min(total_score, 100.0), 2)

        return score

    # ── Métodos auxiliares privados ──────────────────────────────────────
    async def _fetch_github_languages(
        self,
        username: str,
        client: httpx.AsyncClient,
    ) -> List[str]:
        """
        Obtiene los lenguajes de programación principales de un usuario de GitHub.

        Consulta la API de GitHub para listar los repositorios y extraer
        los lenguajes más utilizados.

        Args:
            username: Nombre de usuario en GitHub.
            client: Cliente HTTP reutilizado.

        Returns:
            List[str]: Lista de lenguajes principales.
        """
        languages: List[str] = []
        language_counts: Dict[str, int] = {}

        try:
            response = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "sort": "updated"},
            )

            if response.status_code == 200:
                repos = response.json()
                for repo in repos:
                    lang = repo.get("language")
                    if lang:
                        language_counts[lang] = language_counts.get(lang, 0) + 1

                # Ordenar por frecuencia y tomar los top 5
                sorted_languages = sorted(
                    language_counts.keys(),
                    key=lambda l: language_counts[l],
                    reverse=True,
                )
                languages = sorted_languages[:5]

        except Exception as exc:
            logger.debug(
                "Error al obtener lenguajes de GitHub para %s: %s",
                username, exc,
            )

        return languages

    async def _estimate_github_contributions(
        self,
        username: str,
        client: httpx.AsyncClient,
    ) -> int:
        """
        Estima las contribuciones anuales de un usuario de GitHub.

        Usa la API de eventos para contar actividad reciente como
        aproximación de las contribuciones.

        Args:
            username: Nombre de usuario en GitHub.
            client: Cliente HTTP reutilizado.

        Returns:
            int: Número estimado de contribuciones.
        """
        contribution_estimate = 0

        try:
            response = await client.get(
                f"https://api.github.com/users/{username}/events/public",
                params={"per_page": 100},
            )

            if response.status_code == 200:
                events = response.json()
                # Contar eventos de PushEvent y PullRequestEvent como contribuciones
                push_events = sum(
                    1 for e in events
                    if e.get("type") in ("PushEvent", "PullRequestEvent")
                )
                # Extrapolación anual: si tenemos 100 eventos recientes,
                # estimamos que representa ~2 semanas de actividad
                if len(events) > 0:
                    # Estimación conservadora: multiplicamos por 26 (52 semanas / 2)
                    contribution_estimate = push_events * 26
                else:
                    contribution_estimate = 0

        except Exception as exc:
            logger.debug(
                "Error al estimar contribuciones de GitHub para %s: %s",
                username, exc,
            )

        return contribution_estimate

    def _calculate_digital_footprint(self, result: SocialDiscoveryResult) -> float:
        """
        Calcula la puntuación de huella digital (0-100).

        Evalúa la extensión y profundidad de la presencia digital
        de la persona basándose en los perfiles encontrados.

        Args:
            result: Resultado del descubrimiento social.

        Returns:
            float: Puntuación de huella digital (0 a 100).
        """
        score = 0.0

        # ── Cantidad de perfiles sociales (máx 25 puntos) ────────────────
        social_count = len(result.social_profiles)
        score += min(social_count * 5.0, 25.0)

        # ── Perfiles de desarrollador (máx 25 puntos) ────────────────────
        developer_profiles = [
            p for p in result.social_profiles
            if p.get("category") == "developer"
        ]
        if developer_profiles:
            score += 15.0
            # Bonus por actividad en GitHub
            for dp in developer_profiles:
                if dp.get("repos", 0) > 0:
                    score += 5.0
                if dp.get("followers", 0) > 0:
                    score += 5.0
        score = min(score, 50.0)  # Cap temporal

        # ── Presencia comercial (máx 25 puntos) ──────────────────────────
        commercial_platforms = {"LinkedIn", "Crunchbase", "AngelList"}
        commercial_count = sum(
            1 for p in result.social_profiles
            if p.get("platform") in commercial_platforms
        )
        score += min(commercial_count * 10.0, 25.0)

        return round(min(score, 100.0), 2)

    @staticmethod
    def _calculate_presence_score(result: SocialDiscoveryResult) -> float:
        """
        Calcula la puntuación de presencia digital (0-100).

        Args:
            result: Resultado del descubrimiento social.

        Returns:
            float: Puntuación de presencia (0 a 100).
        """
        score = 0.0

        # ── Perfiles totales (máx 30 puntos) ─────────────────────────────
        score += min(result.profiles_found * 6.0, 30.0)

        # ── Presencia en LinkedIn (máx 30 puntos) ────────────────────────
        if result.linkedin_profiles:
            score += 20.0
            if any(lp.headline for lp in result.linkedin_profiles):
                score += 5.0
            if any(lp.company for lp in result.linkedin_profiles):
                score += 5.0

        # ── Presencia en GitHub (máx 25 puntos) ──────────────────────────
        if result.github_profile and result.github_profile.username:
            score += 15.0
            if result.github_profile.repos > 0:
                score += 5.0
            if result.github_profile.followers > 10:
                score += 5.0

        # ── Diversidad (máx 15 puntos) ───────────────────────────────────
        categories = set()
        for p in result.social_profiles:
            cat = p.get("category", "")
            if cat:
                categories.add(cat)
        score += min(len(categories) * 5.0, 15.0)

        return round(min(score, 100.0), 2)

    # ── Serialización / deserialización para caché ───────────────────────
    @staticmethod
    def _serialize_result(result: SocialDiscoveryResult) -> Dict[str, Any]:
        """
        Serializa el resultado para almacenamiento en caché Redis.

        Args:
            result: Resultado a serializar.

        Returns:
            Dict[str, Any]: Datos serializables a JSON.
        """
        return {
            "profiles_found": result.profiles_found,
            "social_profiles": result.social_profiles,
            "professional_score": {
                "score": result.professional_score.score,
                "factors": result.professional_score.factors,
            },
            "digital_footprint_score": result.digital_footprint_score,
            "presence_score": result.presence_score,
            "linkedin_profiles": [
                {
                    "name": p.name,
                    "headline": p.headline,
                    "company": p.company,
                    "location": p.location,
                    "connections": p.connections,
                    "profile_url": p.profile_url,
                }
                for p in result.linkedin_profiles
            ],
            "github_profile": {
                "username": result.github_profile.username,
                "name": result.github_profile.name,
                "bio": result.github_profile.bio,
                "repos": result.github_profile.repos,
                "followers": result.github_profile.followers,
                "contributions": result.github_profile.contributions,
                "languages": result.github_profile.languages,
                "profile_url": result.github_profile.profile_url,
            } if result.github_profile else None,
        }

    @staticmethod
    def _deserialize_result(data: Dict[str, Any]) -> SocialDiscoveryResult:
        """
        Deserializa un resultado desde caché Redis.

        Args:
            data: Datos serializados.

        Returns:
            SocialDiscoveryResult: Resultado reconstruido.
        """
        result = SocialDiscoveryResult(
            profiles_found=data.get("profiles_found", 0),
            social_profiles=data.get("social_profiles", []),
            digital_footprint_score=data.get("digital_footprint_score", 0.0),
            presence_score=data.get("presence_score", 0.0),
        )

        # ── Reconstruir puntuación profesional ────────────────────────────
        prof_data = data.get("professional_score", {})
        result.professional_score = ProfessionalScore(
            score=prof_data.get("score", 0.0),
            factors=prof_data.get("factors", {}),
        )

        # ── Reconstruir perfiles de LinkedIn ──────────────────────────────
        result.linkedin_profiles = [
            LinkedInProfile(**p)
            for p in data.get("linkedin_profiles", [])
        ]

        # ── Reconstruir perfil de GitHub ─────────────────────────────────
        gh_data = data.get("github_profile")
        if gh_data:
            result.github_profile = GitHubProfile(**gh_data)

        return result
