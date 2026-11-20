"""Controles de acesso da API: chave de API opcional e limite de requisicoes por cliente.

Os dois sao a ultima linha de defesa dentro da aplicacao. Em nuvem, autenticacao e limite de taxa
ficam na borda (API Gateway / WAF), que protege todas as replicas de uma vez; o limitador daqui e
por processo e existe para o caso de a borda falhar e para o uso local.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque

API_KEY_HEADER = "X-API-Key"


def api_key_matches(provided: str | None, expected: str) -> bool:
    """Comparacao em tempo constante: nao vaza, pelo tempo de resposta, quantos caracteres batem."""
    return provided is not None and secrets.compare_digest(provided.encode(), expected.encode())


class RateLimiter:
    """Janela deslizante de 60 segundos por cliente."""

    def __init__(self, limit_per_minute: int, window_seconds: float = 60.0, max_clients: int = 10_000) -> None:
        self._limit = limit_per_minute
        self._window = window_seconds
        self._max_clients = max_clients
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def allow(self, client: str, now: float | None = None) -> tuple[bool, int]:
        """Devolve ``(permitido, segundos_ate_liberar)``."""
        if not self.enabled:
            return True, 0
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._hits) > self._max_clients:
                self._evict(now)
            hits = self._hits[client]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False, max(1, int(self._window - (now - hits[0])) + 1)
            hits.append(now)
            return True, 0

    def _evict(self, now: float) -> None:
        stale = [client for client, hits in self._hits.items() if not hits or now - hits[-1] >= self._window]
        for client in stale:
            del self._hits[client]
