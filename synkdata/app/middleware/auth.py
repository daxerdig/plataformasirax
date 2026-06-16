"""
Middleware de autenticación JWT para la plataforma SynkData.

Proporciona:
- Verificación de tokens JWT usando python-jose
- Dependencia ``get_current_user`` para obtener el usuario actual
- Fábrica de dependencias ``require_role`` para autorización por roles
- Función ``create_access_token`` para emitir tokens
- Modelo ``Token`` con metadatos de expiración

Maneja los siguientes escenarios de error:
- Token expirado (ExpiredSignatureError)
- Token inválido (JWTError)
- Token ausente o malformado
- Rol insuficiente (PermissionError)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Esquema de seguridad Bearer
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class Token(BaseModel):
    """
    Modelo que representa un token JWT con metadatos.

    Attributes:
        access_token: El token JWT codificado.
        token_type: Tipo de token (siempre 'bearer').
        expires_in: Segundos hasta la expiración del token.
        issued_at: Fecha y hora de emisión (ISO 8601).
        expires_at: Fecha y hora de expiración (ISO 8601).
    """

    access_token: str = Field(..., description="Token JWT codificado.")
    token_type: str = Field(
        default="bearer",
        description="Tipo de token.",
    )
    expires_in: int = Field(
        ...,
        description="Segundos hasta la expiración del token.",
    )
    issued_at: str = Field(
        ...,
        description="Fecha y hora de emisión (ISO 8601).",
    )
    expires_at: str = Field(
        ...,
        description="Fecha y hora de expiración (ISO 8601).",
    )


class TokenData(BaseModel):
    """
    Datos decodificados del payload del JWT.

    Attributes:
        sub: Identificador del sujeto (user_id).
        email: Correo electrónico del usuario.
        role: Rol del usuario (admin, analyst, viewer).
        exp: Timestamp de expiración.
        iat: Timestamp de emisión.
        iss: Emisor del token.
    """

    sub: str = Field(..., description="Identificador del usuario.")
    email: Optional[str] = Field(default=None, description="Correo electrónico.")
    role: str = Field(default="viewer", description="Rol del usuario.")
    exp: Optional[int] = Field(default=None, description="Timestamp de expiración.")
    iat: Optional[int] = Field(default=None, description="Timestamp de emisión.")
    iss: Optional[str] = Field(default=None, description="Emisor del token.")


# ---------------------------------------------------------------------------
# Funciones de creación de tokens
# ---------------------------------------------------------------------------
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> Token:
    """
    Crea un token JWT firmado con los datos proporcionados.

    El payload del token incluye:
    - ``sub``: Identificador del usuario (obligatorio)
    - ``email``: Correo del usuario (opcional)
    - ``role``: Rol del usuario (opcional, por defecto 'viewer')
    - ``exp``: Timestamp de expiración
    - ``iat``: Timestamp de emisión
    - ``iss``: Emisor del token (synkdata.io)

    Args:
        data: Diccionario con los datos a incluir en el payload.
            Debe contener al menos la clave ``sub``.
        expires_delta: Tiempo hasta la expiración. Si no se proporciona,
            se usa el valor de configuración JWT_ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Token: Objeto con el token codificado y metadatos.

    Raises:
        ValueError: Si ``data`` no contiene la clave ``sub``.

    Example:
        >>> token = create_access_token({"sub": "user123", "role": "admin"})
        >>> token.token_type
        'bearer'
    """
    if "sub" not in data:
        raise ValueError("El campo 'sub' (identificador de usuario) es obligatorio.")

    settings = get_settings()

    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        **data,
        "exp": expire,
        "iat": now,
        "iss": settings.JWT_ISSUER,
    }

    # Asegurar que el rol tenga un valor por defecto
    if "role" not in payload:
        payload["role"] = "viewer"

    encoded_jwt = jwt.encode(
        claims=payload,
        key=settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return Token(
        access_token=encoded_jwt,
        token_type="bearer",
        expires_in=int((expire - now).total_seconds()),
        issued_at=now.isoformat(),
        expires_at=expire.isoformat(),
    )


# ---------------------------------------------------------------------------
# Dependencias de FastAPI
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    """
    Dependencia de FastAPI que decodifica y valida un token JWT.

    Extrae el token del header ``Authorization: Bearer <token>``,
    lo decodifica, verifica la firma y la expiración, y retorna
    los datos del usuario como un diccionario.

    Args:
        credentials: Credenciales extraídas del header Authorization
            por el esquema HTTPBearer.

    Returns:
        dict: Datos del usuario decodificados del JWT. Incluye al menos
            ``sub`` (user_id), ``email``, ``role``, ``iss``.

    Raises:
        HTTPException 401: Si el token está ausente, expirado o es inválido.

    Example:
        @router.get("/me")
        async def me(user: dict = Depends(get_current_user)):
            return {"user_id": user["sub"]}
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación no proporcionado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        settings = get_settings()
        payload = jwt.decode(
            token=token,
            key=settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iss": True,
                "verify_sub": True,
            },
            issuer=settings.JWT_ISSUER,
        )

        # Verificar que el payload contenga el identificador del sujeto
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: falta el identificador de usuario.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.debug(
            "Token JWT decodificado exitosamente — sub=%s, role=%s",
            user_id,
            payload.get("role"),
        )

        return {
            "sub": user_id,
            "email": payload.get("email"),
            "role": payload.get("role", "viewer"),
            "iss": payload.get("iss"),
            "iat": payload.get("iat"),
            "exp": payload.get("exp"),
        }

    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expirado detectado.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Inicie sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except jwt.JWTClaimsError as exc:
        logger.warning("Claims del JWT inválidos: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Claims del token inválidos: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError as exc:
        logger.warning("Token JWT inválido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido. Verifique sus credenciales.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*roles: str):
    """
    Fábrica de dependencias que verifica que el usuario tenga uno de
    los roles permitidos.

    Retorna una dependencia de FastAPI que primero obtiene el usuario
    actual (validando el JWT) y luego verifica que su rol esté en la
    lista de roles permitidos.

    Args:
        *roles: Roles permitidos (ej. 'admin', 'analyst', 'viewer').

    Returns:
        Callable: Dependencia de FastAPI que verifica el rol.

    Raises:
        HTTPException 403: Si el usuario no tiene un rol permitido.

    Example:
        @router.delete("/users/{user_id}")
        async def delete_user(
            user_id: str,
            user: dict = Depends(require_role("admin")),
        ):
            # Solo administradores pueden ejecutar este endpoint
            ...
    """
    if not roles:
        raise ValueError("Debe especificar al menos un rol permitido.")

    async def role_checker(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_role = current_user.get("role", "viewer")

        if user_role not in roles:
            logger.warning(
                "Acceso denegado — usuario=%s, rol=%s, roles_requeridos=%s",
                current_user.get("sub"),
                user_role,
                roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Acceso denegado. Se requiere uno de los siguientes roles: "
                    f"{', '.join(roles)}. Su rol actual es '{user_role}'."
                ),
            )

        return current_user

    return role_checker
