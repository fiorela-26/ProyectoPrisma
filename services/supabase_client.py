"""Clientes de Supabase.

En Windows, el HTTP/2 de httpx dispara WinError 10035 si varios hilos
(el worker de jobs y una petición Flask) comparten la misma conexión.
Por eso: HTTP/1.1 y un cliente por hilo.
"""
import threading

import httpx
from supabase import Client, ClientOptions, create_client

from config import settings

_tls = threading.local()


def _httpx_cliente() -> httpx.Client:
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=10.0),
    )


def _crear(clave: str) -> Client:
    return create_client(
        settings.SUPABASE_URL,
        clave,
        options=ClientOptions(httpx_client=_httpx_cliente()),
    )


def get_anon_client() -> Client:
    """Cliente con anon key: respeta RLS. Usar en peticiones de usuario."""
    c = getattr(_tls, "anon", None)
    if c is None:
        c = _crear(settings.SUPABASE_ANON_KEY)
        _tls.anon = c
    return c


def get_service_client() -> Client:
    """Cliente con service key: salta RLS. Solo servidor y jobs, nunca al navegador."""
    c = getattr(_tls, "service", None)
    if c is None:
        c = _crear(settings.SUPABASE_SERVICE_KEY)
        _tls.service = c
    return c


def invalidar_clientes() -> None:
    """Tira las conexiones del hilo actual (tras un corte de red)."""
    for attr in ("anon", "service"):
        setattr(_tls, attr, None)


def user_client(access_token: str) -> Client:
    """Cliente anon que actúa como el usuario autenticado, para que RLS aplique sus permisos."""
    client = _crear(settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client
