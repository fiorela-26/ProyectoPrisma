"""Límite simple en memoria por usuario. Suficiente en una sola instancia Flask."""
from collections import defaultdict, deque
import time

_ventanas: dict[str, deque[float]] = defaultdict(deque)


class DemasiadoRapido(Exception):
    pass


def comprobar(clave: str, maximo: int, ventana_s: int = 60) -> None:
    ahora = time.monotonic()
    cola = _ventanas[clave]
    while cola and ahora - cola[0] > ventana_s:
        cola.popleft()
    if len(cola) >= maximo:
        raise DemasiadoRapido("Espera un momento antes de repetir esta acción.")
    cola.append(ahora)


def reiniciar() -> None:
    _ventanas.clear()
