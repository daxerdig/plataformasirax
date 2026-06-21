"""
Servicio de inteligencia de nombre de usuario para SynkData.

Proporciona búsqueda de perfiles de usuario en más de 50 plataformas
incluyendo redes sociales, foros, plataformas de desarrollo y servicios
profesionales. Similar a herramientas como Sherlock, Maigret y WhatsMyName.

Características:
- Búsqueda concurrente en 50+ plataformas usando httpx
- Rate limiting y timeout por plataforma
- Detección de perfiles existentes mediante códigos HTTP y contenido
- Categorización automática de perfiles (developer, social, professional, etc.)
- Cálculo de puntuación de presencia digital
- Caché en Redis para resultados repetidos
- Degradación graceful ante fallos individuales de plataformas
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.database import get_redis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------
class PlatformCategory(str, Enum):
    """Categorías de plataformas para clasificación de perfiles."""

    SOCIAL = "social"
    DEVELOPER = "developer"
    PROFESSIONAL = "professional"
    MEDIA = "media"
    GAMING = "gaming"
    MESSAGING = "messaging"
    FORUM = "forum"
    CREATIVE = "creative"
    ACADEMIC = "academic"
    COMMERCE = "commerce"


# ---------------------------------------------------------------------------
# Modelos de datos internos (dataclasses)
# ---------------------------------------------------------------------------
@dataclass
class PlatformProfile:
    """
    Perfil de un usuario en una plataforma específica.

    Attributes:
        platform: Nombre de la plataforma.
        url: URL del perfil.
        exists: Si el perfil fue encontrado.
        profile_data: Datos adicionales del perfil.
        bio: Biografía del perfil.
        avatar_url: URL del avatar.
        verified: Si está verificado.
        category: Categoría de la plataforma.
        response_time: Tiempo de respuesta en segundos.
    """

    platform: str = ""
    url: str = ""
    exists: bool = False
    profile_data: Dict[str, Any] = field(default_factory=dict)
    bio: str = ""
    avatar_url: str = ""
    verified: bool = False
    category: str = ""
    response_time: float = 0.0


@dataclass
class UsernameIntelligenceResult:
    """
    Resultado completo del análisis de inteligencia de nombre de usuario.

    Attributes:
        username: Nombre de usuario analizado.
        total_profiles: Número total de perfiles encontrados.
        platforms_found: Nombres de plataformas donde se encontró.
        profiles: Detalle de los perfiles encontrados.
        presence_score: Puntuación de presencia digital (0-100).
        categories: Categorías de actividad identificadas.
    """

    username: str = ""
    total_profiles: int = 0
    platforms_found: List[str] = field(default_factory=list)
    profiles: List[PlatformProfile] = field(default_factory=list)
    presence_score: float = 0.0
    categories: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Definición de plataformas (50+ plataformas)
# ---------------------------------------------------------------------------
# Cada plataforma define: url_template, category, check_method
# check_method: "status_code" (404 = no existe) o "content" (buscar texto)

PLATFORM_DEFINITIONS: List[Dict[str, Any]] = [
    # ── Redes sociales principales ───────────────────────────────────────
    {
        "platform": "Twitter/X",
        "url_template": "https://x.com/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Instagram",
        "url_template": "https://www.instagram.com/{username}/",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Facebook",
        "url_template": "https://www.facebook.com/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "TikTok",
        "url_template": "https://www.tiktok.com/@{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Pinterest",
        "url_template": "https://www.pinterest.com/{username}/",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Snapchat",
        "url_template": "https://www.snapchat.com/add/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Plataformas profesionales ────────────────────────────────────────
    {
        "platform": "LinkedIn",
        "url_template": "https://www.linkedin.com/in/{username}",
        "category": PlatformCategory.PROFESSIONAL,
        "check_method": "status_code",
        "error_codes": [404, 999],
        "timeout": 10.0,
    },
    {
        "platform": "AngelList",
        "url_template": "https://angel.co/u/{username}",
        "category": PlatformCategory.PROFESSIONAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Crunchbase",
        "url_template": "https://www.crunchbase.com/person/{username}",
        "category": PlatformCategory.PROFESSIONAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 10.0,
    },
    # ── Plataformas de desarrollo ────────────────────────────────────────
    {
        "platform": "GitHub",
        "url_template": "https://github.com/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 6.0,
        "api_url": "https://api.github.com/users/{username}",
    },
    {
        "platform": "GitLab",
        "url_template": "https://gitlab.com/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Stack Overflow",
        "url_template": "https://stackoverflow.com/users/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Dev.to",
        "url_template": "https://dev.to/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Hashnode",
        "url_template": "https://hashnode.com/@{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "CodePen",
        "url_template": "https://codepen.io/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "npm",
        "url_template": "https://www.npmjs.com/~{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "PyPI",
        "url_template": "https://pypi.org/user/{username}/",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Docker Hub",
        "url_template": "https://hub.docker.com/u/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Replit",
        "url_template": "https://replit.com/@{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "HackerRank",
        "url_template": "https://www.hackerrank.com/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "LeetCode",
        "url_template": "https://leetcode.com/{username}/",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Bitbucket",
        "url_template": "https://bitbucket.org/{username}/",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Mensajería ───────────────────────────────────────────────────────
    {
        "platform": "Telegram",
        "url_template": "https://t.me/{username}",
        "category": PlatformCategory.MESSAGING,
        "check_method": "content",
        "exists_string": "tg://resolve",
        "timeout": 8.0,
    },
    {
        "platform": "Discord",
        "url_template": "https://discord.com/users/{username}",
        "category": PlatformCategory.MESSAGING,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Multimedia y contenido ───────────────────────────────────────────
    {
        "platform": "YouTube",
        "url_template": "https://www.youtube.com/@{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Medium",
        "url_template": "https://medium.com/@{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Reddit",
        "url_template": "https://www.reddit.com/user/{username}",
        "category": PlatformCategory.FORUM,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Tumblr",
        "url_template": "https://{username}.tumblr.com",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Flickr",
        "url_template": "https://www.flickr.com/people/{username}/",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "SoundCloud",
        "url_template": "https://soundcloud.com/{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Spotify",
        "url_template": "https://open.spotify.com/user/{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Vimeo",
        "url_template": "https://vimeo.com/{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Twitch",
        "url_template": "https://www.twitch.tv/{username}",
        "category": PlatformCategory.MEDIA,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Foros y comunidades ──────────────────────────────────────────────
    {
        "platform": "Hacker News",
        "url_template": "https://news.ycombinator.com/user?id={username}",
        "category": PlatformCategory.FORUM,
        "check_method": "content",
        "exists_string": "created:",
        "timeout": 8.0,
    },
    {
        "platform": "Quora",
        "url_template": "https://www.quora.com/profile/{username}",
        "category": PlatformCategory.FORUM,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Seguridad y llaves ───────────────────────────────────────────────
    {
        "platform": "Keybase",
        "url_template": "https://keybase.io/{username}",
        "category": PlatformCategory.DEVELOPER,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Creatividad y diseño ─────────────────────────────────────────────
    {
        "platform": "Behance",
        "url_template": "https://www.behance.net/{username}",
        "category": PlatformCategory.CREATIVE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Dribbble",
        "url_template": "https://dribbble.com/{username}",
        "category": PlatformCategory.CREATIVE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Figma",
        "url_template": "https://www.figma.com/@{username}",
        "category": PlatformCategory.CREATIVE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Gaming ───────────────────────────────────────────────────────────
    {
        "platform": "Steam",
        "url_template": "https://steamcommunity.com/id/{username}",
        "category": PlatformCategory.GAMING,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Xbox Gamertag",
        "url_template": "https://xboxgamertag.com/search/{username}",
        "category": PlatformCategory.GAMING,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Chess.com",
        "url_template": "https://www.chess.com/member/{username}",
        "category": PlatformCategory.GAMING,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Académico ────────────────────────────────────────────────────────
    {
        "platform": "Google Scholar",
        "url_template": "https://scholar.google.com/citations?user={username}",
        "category": PlatformCategory.ACADEMIC,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "ResearchGate",
        "url_template": "https://www.researchgate.net/profile/{username}",
        "category": PlatformCategory.ACADEMIC,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "ORCID",
        "url_template": "https://orcid.org/{username}",
        "category": PlatformCategory.ACADEMIC,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Comercio ─────────────────────────────────────────────────────────
    {
        "platform": "Etsy",
        "url_template": "https://www.etsy.com/shop/{username}",
        "category": PlatformCategory.COMMERCE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Patreon",
        "url_template": "https://www.patreon.com/{username}",
        "category": PlatformCategory.COMMERCE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Ko-fi",
        "url_template": "https://ko-fi.com/{username}",
        "category": PlatformCategory.COMMERCE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Buy Me a Coffee",
        "url_template": "https://buymeacoffee.com/{username}",
        "category": PlatformCategory.COMMERCE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    # ── Otras plataformas ────────────────────────────────────────────────
    {
        "platform": "Wikipedia",
        "url_template": "https://es.wikipedia.org/wiki/Usuario:{username}",
        "category": PlatformCategory.ACADEMIC,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Linktree",
        "url_template": "https://linktr.ee/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "About.me",
        "url_template": "https://about.me/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Gravatar",
        "url_template": "https://gravatar.com/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Mastodon (mastodon.social)",
        "url_template": "https://mastodon.social/@{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Threads",
        "url_template": "https://www.threads.net/@{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Bluesky",
        "url_template": "https://bsky.app/profile/{username}.bsky.social",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "VSCO",
        "url_template": "https://vsco.co/{username}/gallery",
        "category": PlatformCategory.CREATIVE,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Goodreads",
        "url_template": "https://www.goodreads.com/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
    {
        "platform": "Strava",
        "url_template": "https://www.strava.com/athletes/{username}",
        "category": PlatformCategory.SOCIAL,
        "check_method": "status_code",
        "error_codes": [404],
        "timeout": 8.0,
    },
]


class UsernameIntelligenceService:
    """
    Servicio de inteligencia de nombre de usuario.

    Orquesta la búsqueda de un nombre de usuario en más de 50 plataformas
    web, determinando si el perfil existe y recopilando información básica
    del mismo. Inspirado en herramientas como Sherlock, Maigret y WhatsMyName.

    Características:
    - Búsqueda concurrente con semáforo para limitar concurrencia
    - Timeouts individuales por plataforma
    - Rate limiting respetuoso con delays entre peticiones
    - Caché en Redis para resultados repetidos
    - Degradación graceful: fallos individuales no afectan el resultado global
    - Cálculo automático de puntuación de presencia digital
    """

    # ── Configuración de concurrencia ────────────────────────────────────
    MAX_CONCURRENT_CHECKS = 15  # Máximo de checks simultáneos
    DELAY_BETWEEN_BATCHES = 1.0  # Segundos entre lotes de peticiones
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        """Inicializa el servicio con configuración del proyecto."""
        self._settings = get_settings()
        self._cache_ttl = self._settings.REDIS_CACHE_TTL
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CHECKS)

    # ── Integración con Sherlock y Maigret (Comandos Locales) ──────────
    async def _search_external_tools(
        self,
        username: str,
    ) -> List[PlatformProfile]:
        """
        Consulta herramientas externas como Sherlock y Maigret vía línea de comandos.
        """
        import os
        import tempfile

        # Tiempo máximo total que se le permite a cada herramienta externa
        # antes de matar el proceso. Evita que un colgado de Sherlock/Maigret
        # deje la petición HTTP esperando indefinidamente.
        EXTERNAL_TOOL_TIMEOUT = 45

        external_profiles: List[PlatformProfile] = []

        # ── Ejecutar Sherlock ───────────────────────────────────────────
        if self._settings.SHERLOCK_PATH:
            try:
                logger.debug("Ejecutando Sherlock para: %s", username)
                with tempfile.TemporaryDirectory() as tmpdir:
                    process = await asyncio.create_subprocess_exec(
                        self._settings.SHERLOCK_PATH,
                        username,
                        "--timeout", "10",
                        "--print-found",
                        "--csv",
                        "--no-color",
                        cwd=tmpdir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        await asyncio.wait_for(
                            process.communicate(), timeout=EXTERNAL_TOOL_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.communicate()
                        logger.debug("Sherlock excedió el timeout para: %s", username)

                    # Sherlock con --csv guarda el reporte como
                    # "<cwd>/<username>.csv"
                    csv_path = os.path.join(tmpdir, f"{username}.csv")
                    if os.path.exists(csv_path):
                        with open(csv_path, newline="", encoding="utf-8") as f:
                            for row in csv.DictReader(f):
                                if row.get("exists") == "Claimed":
                                    external_profiles.append(PlatformProfile(
                                        platform=f"{row.get('name')} (Sherlock)",
                                        url=row.get("url_user"),
                                        exists=True,
                                        category=PlatformCategory.SOCIAL,
                                    ))
            except FileNotFoundError:
                logger.warning(
                    "El binario de Sherlock ('%s') no está instalado o no "
                    "está en el PATH. Instala el paquete 'sherlock-project'.",
                    self._settings.SHERLOCK_PATH,
                )
            except Exception as exc:
                logger.debug("Error ejecutando Sherlock localmente: %s", exc)

        # ── Ejecutar Maigret ───────────────────────────────────────────
        if self._settings.MAIGRET_PATH:
            try:
                logger.debug("Ejecutando Maigret para: %s", username)
                with tempfile.TemporaryDirectory() as tmpdir:
                    process = await asyncio.create_subprocess_exec(
                        self._settings.MAIGRET_PATH,
                        username,
                        "--timeout", "10",
                        "--no-extracting",
                        "--no-recursion",
                        "--no-autoupdate",
                        "--no-color",
                        "--no-progressbar",
                        "--json", "simple",
                        cwd=tmpdir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        await asyncio.wait_for(
                            process.communicate(), timeout=EXTERNAL_TOOL_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.communicate()
                        logger.debug("Maigret excedió el timeout para: %s", username)

                    # Maigret guarda el reporte JSON en
                    # "<cwd>/reports/report_<username>_simple.json"
                    # (carpeta "reports" por defecto + sufijo del tipo de
                    # reporte en el nombre del archivo).
                    safe_username = username.replace("/", "_")
                    report_path = os.path.join(
                        tmpdir, "reports", f"report_{safe_username}_simple.json"
                    )
                    if os.path.exists(report_path):
                        with open(report_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            sites = data.get("sites", data) if isinstance(data, dict) else {}
                            for site_name, site_data in sites.items():
                                status = site_data.get("status") if isinstance(site_data, dict) else None
                                if status in ("claimed", "Claimed"):
                                    external_profiles.append(PlatformProfile(
                                        platform=f"{site_name} (Maigret)",
                                        url=site_data.get("url_user"),
                                        exists=True,
                                        category=PlatformCategory.SOCIAL,
                                        profile_data=site_data,
                                    ))
            except FileNotFoundError:
                logger.warning(
                    "El binario de Maigret ('%s') no está instalado o no "
                    "está en el PATH. Instala el paquete 'maigret'.",
                    self._settings.MAIGRET_PATH,
                )
            except Exception as exc:
                logger.debug("Error ejecutando Maigret localmente: %s", exc)

        return external_profiles

    # ── Método principal ─────────────────────────────────────────────────
    async def analyze(self, username: str) -> UsernameIntelligenceResult:
        """
        Ejecuta el análisis integral de inteligencia de nombre de usuario.

        Busca el nombre de usuario en todas las plataformas configuradas
        y calcula la puntuación de presencia digital.

        Args:
            username: Nombre de usuario a buscar.

        Returns:
            UsernameIntelligenceResult: Resultado completo del análisis.
        """
        username = username.strip().lower()
        result = UsernameIntelligenceResult(username=username)

        # ── Verificar caché global ───────────────────────────────────────
        cache_key = f"digital:username:analysis:{username}"
        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                return UsernameIntelligenceResult(
                    username=cached_data.get("username", username),
                    total_profiles=cached_data.get("total_profiles", 0),
                    platforms_found=cached_data.get("platforms_found", []),
                    profiles=[
                        PlatformProfile(**p)
                        for p in cached_data.get("profiles", [])
                    ],
                    presence_score=cached_data.get("presence_score", 0.0),
                    categories=cached_data.get("categories", []),
                )
        except Exception:
            logger.debug("Caché no disponible para análisis de username %s", username)

        # ── Buscar perfiles en todas las plataformas ─────────────────────
        profiles = await self.search_platforms(username)

        # ── Consultar herramientas externas (Sherlock/Maigret) ────────────
        external_profiles = await self._search_external_tools(username)
        profiles.extend(external_profiles)

        # ── Filtrar solo perfiles existentes ─────────────────────────────
        existing_profiles = [p for p in profiles if p.exists]

        # ── Construir resultado ──────────────────────────────────────────
        result.profiles = existing_profiles
        result.total_profiles = len(existing_profiles)
        result.platforms_found = [p.platform for p in existing_profiles]

        # ── Calcular categorías ──────────────────────────────────────────
        result.categories = self._calculate_categories(existing_profiles)

        # ── Calcular puntuación de presencia ─────────────────────────────
        result.presence_score = self._calculate_presence_score(existing_profiles)

        # ── Cachear resultado ────────────────────────────────────────────
        try:
            redis = get_redis()
            await redis.setex(
                cache_key,
                self._cache_ttl,
                json.dumps({
                    "username": result.username,
                    "total_profiles": result.total_profiles,
                    "platforms_found": result.platforms_found,
                    "profiles": [
                        {
                            "platform": p.platform,
                            "url": p.url,
                            "exists": p.exists,
                            "profile_data": p.profile_data,
                            "bio": p.bio,
                            "avatar_url": p.avatar_url,
                            "verified": p.verified,
                            "category": p.category,
                            "response_time": p.response_time,
                        }
                        for p in result.profiles
                    ],
                    "presence_score": result.presence_score,
                    "categories": result.categories,
                }),
            )
        except Exception:
            logger.debug("No se pudo cachear resultado para username %s", username)

        return result

    # ── Búsqueda en plataformas ─────────────────────────────────────────
    async def search_platforms(
        self,
        username: str,
    ) -> List[PlatformProfile]:
        """
        Busca un nombre de usuario en todas las plataformas configuradas.

        Ejecuta las verificaciones de forma concurrente con semáforo
        para respetar los límites de concurrencia.

        Args:
            username: Nombre de usuario a buscar.

        Returns:
            List[PlatformProfile]: Lista de perfiles encontrados (existentes o no).
        """
        results: List[PlatformProfile] = []

        # ── Crear tareas para todas las plataformas ──────────────────────
        tasks = [
            self._check_single_platform(username, platform_def)
            for platform_def in PLATFORM_DEFINITIONS
        ]

        # ── Ejecutar con gather y manejo de excepciones ──────────────────
        platform_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, profile_result in enumerate(platform_results):
            if isinstance(profile_result, PlatformProfile):
                results.append(profile_result)
            else:
                # Error en la verificación — registrar y continuar
                platform_name = PLATFORM_DEFINITIONS[i]["platform"]
                logger.debug(
                    "Error al verificar %s para username %s: %s",
                    platform_name, username, profile_result,
                )
                results.append(PlatformProfile(
                    platform=platform_name,
                    exists=False,
                    category=PLATFORM_DEFINITIONS[i]["category"].value,
                ))

        return results

    # ── Verificación individual de plataforma ────────────────────────────
    async def _check_single_platform(
        self,
        username: str,
        platform_def: Dict[str, Any],
    ) -> PlatformProfile:
        """
        Verifica si un nombre de usuario existe en una plataforma específica.

        Realiza una petición HTTP a la URL del perfil y analiza la
        respuesta para determinar si el perfil existe.

        Args:
            username: Nombre de usuario a verificar.
            platform_def: Definición de la plataforma (URL, método, etc.).

        Returns:
            PlatformProfile: Perfil encontrado o no encontrado.
        """
        platform_name = platform_def["platform"]
        url = platform_def["url_template"].format(username=username)
        timeout = platform_def.get("timeout", 8.0)
        check_method = platform_def.get("check_method", "status_code")

        profile = PlatformProfile(
            platform=platform_name,
            url=url,
            category=platform_def["category"].value,
        )

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                    },
                    follow_redirects=True,
                    max_redirects=5,
                ) as client:
                    import time
                    start_time = time.monotonic()

                    response = await client.get(url)
                    profile.response_time = round(time.monotonic() - start_time, 3)

                    # ── Verificar existencia según método ─────────────────
                    if check_method == "status_code":
                        error_codes = platform_def.get("error_codes", [404])
                        profile.exists = response.status_code not in error_codes and response.status_code < 400

                    elif check_method == "content":
                        exists_string = platform_def.get("exists_string", "")
                        if exists_string:
                            profile.exists = exists_string in response.text
                        else:
                            # Si no hay cadena de verificación, usar status code
                            profile.exists = response.status_code == 200

                    # ── Intentar obtener datos adicionales del perfil ─────
                    if profile.exists and platform_def.get("api_url"):
                        await self._enrich_profile_from_api(
                            profile, username, platform_def, client,
                        )

            except httpx.TimeoutException:
                logger.debug(
                    "Timeout al verificar %s para %s", platform_name, username,
                )
                profile.exists = False
            except httpx.ConnectError:
                logger.debug(
                    "Error de conexión al verificar %s para %s",
                    platform_name, username,
                )
                profile.exists = False
            except httpx.TooManyRedirects:
                logger.debug(
                    "Demasiadas redirecciones en %s para %s",
                    platform_name, username,
                )
                profile.exists = False
            except Exception as exc:
                logger.debug(
                    "Error inesperado al verificar %s: %s",
                    platform_name, exc,
                )
                profile.exists = False

        return profile

    # ── Enriquecimiento de perfil vía API ────────────────────────────────
    async def _enrich_profile_from_api(
        self,
        profile: PlatformProfile,
        username: str,
        platform_def: Dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        """
        Enriquece un perfil con datos de la API oficial de la plataforma.

        Args:
            profile: Perfil a enriquecer (se modifica in-place).
            username: Nombre de usuario.
            platform_def: Definición de la plataforma.
            client: Cliente HTTP reutilizado.
        """
        api_url = platform_def.get("api_url", "")
        if not api_url:
            return

        try:
            api_url_formatted = api_url.format(username=username)
            api_response = await client.get(
                api_url_formatted,
                headers={"Accept": "application/vnd.github.v3+json"}
                if "github" in api_url else {"Accept": "application/json"},
            )

            if api_response.status_code == 200:
                data = api_response.json()
                profile.profile_data = data
                profile.bio = data.get("bio", "") or ""
                profile.avatar_url = data.get("avatar_url", "") or ""

                # ── Datos específicos de GitHub ──────────────────────────
                if "github" in api_url:
                    profile.verified = data.get("hireable", False) or bool(data.get("company"))
                    profile.profile_data = {
                        "name": data.get("name", ""),
                        "company": data.get("company", ""),
                        "blog": data.get("blog", ""),
                        "location": data.get("location", ""),
                        "public_repos": data.get("public_repos", 0),
                        "followers": data.get("followers", 0),
                        "following": data.get("following", 0),
                        "created_at": data.get("created_at", ""),
                    }

        except Exception as exc:
            logger.debug(
                "Error al enriquecer perfil de %s vía API: %s",
                profile.platform, exc,
            )

    # ── Cálculo de puntuación de presencia ───────────────────────────────
    @staticmethod
    def _calculate_presence_score(profiles: List[PlatformProfile]) -> float:
        """
        Calcula la puntuación de presencia digital (0-100).

        La puntuación se basa en:
        - Número de perfiles encontrados
        - Diversidad de categorías
        - Presencia en plataformas de alto valor (GitHub, LinkedIn)
        - Verificación de perfiles

        Args:
            profiles: Lista de perfiles existentes.

        Returns:
            float: Puntuación de presencia (0.0 a 100.0).
        """
        if not profiles:
            return 0.0

        score = 0.0

        # ── Puntos base por número de perfiles (máx 30 puntos) ───────────
        profile_count_score = min(len(profiles) * 3.0, 30.0)
        score += profile_count_score

        # ── Puntos por diversidad de categorías (máx 25 puntos) ──────────
        categories = set(p.category for p in profiles)
        diversity_score = min(len(categories) * 5.0, 25.0)
        score += diversity_score

        # ── Puntos por plataformas de alto valor (máx 25 puntos) ─────────
        high_value_platforms = {"GitHub", "LinkedIn", "Stack Overflow", "Dev.to"}
        found_high_value = {p.platform for p in profiles} & high_value_platforms
        high_value_score = min(len(found_high_value) * 8.0, 25.0)
        score += high_value_score

        # ── Puntos por perfiles verificados (máx 10 puntos) ──────────────
        verified_count = sum(1 for p in profiles if p.verified)
        verified_score = min(verified_count * 3.0, 10.0)
        score += verified_score

        # ── Puntos por redes sociales principales (máx 10 puntos) ────────
        social_platforms = {"Twitter/X", "Instagram", "Facebook", "TikTok"}
        found_social = {p.platform for p in profiles} & social_platforms
        social_score = min(len(found_social) * 3.0, 10.0)
        score += social_score

        return round(min(score, 100.0), 2)

    # ── Cálculo de categorías ────────────────────────────────────────────
    @staticmethod
    def _calculate_categories(profiles: List[PlatformProfile]) -> List[str]:
        """
        Determina las categorías de actividad del usuario.

        Args:
            profiles: Lista de perfiles existentes.

        Returns:
            List[str]: Lista de categorías identificadas.
        """
        if not profiles:
            return []

        # Contar perfiles por categoría
        category_counts: Dict[str, int] = {}
        for profile in profiles:
            cat = profile.category
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Ordenar por frecuencia (más perfiles = más relevante)
        sorted_categories = sorted(
            category_counts.keys(),
            key=lambda c: category_counts[c],
            reverse=True,
        )

        return sorted_categories
