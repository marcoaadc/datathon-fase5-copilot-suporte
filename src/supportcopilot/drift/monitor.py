"""Monitor de drift em producao: janela deslizante de requisicoes comparada com a referencia.

A cada chamado triado, a API registra as features monitoradas (nunca o texto). O monitor mantem
as ultimas ``window_size`` observacoes e calcula o PSI de cada feature contra o perfil de
referencia gerado no treino. O resultado alimenta ``GET /drift`` e as metricas do Prometheus.

O estado vive na memoria de cada replica: e um sinal de alerta rapido. O relatorio do Evidently
(``supportcopilot.pipelines.drift_report``) e a analise completa, feita em lote.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from supportcopilot.drift.statistics import profile_psi

OK, WARNING, CRITICAL, INSUFFICIENT = "ok", "warning", "critical", "insufficient_data"
DRIFT_SHARE_ALERT = 1 / 3


def level_for(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return CRITICAL
    if value >= warning:
        return WARNING
    return OK


class DriftMonitor:
    def __init__(
        self,
        profile: dict[str, Any] | None,
        window_size: int = 500,
        min_samples: int = 100,
        psi_warning: float = 0.10,
        psi_critical: float = 0.25,
    ) -> None:
        self._features: dict[str, Any] = (profile or {}).get("features", {})
        self._n_reference = int((profile or {}).get("n_reference", 0))
        self._window: deque[dict[str, Any]] = deque(maxlen=window_size)
        self._min_samples = min_samples
        self._warning = psi_warning
        self._critical = psi_critical
        self._lock = threading.Lock()
        self._total = 0

    @property
    def enabled(self) -> bool:
        return bool(self._features)

    def observe(self, features: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._window.append({name: features[name] for name in self._features if name in features})
            self._total += 1

    def status(self) -> dict[str, Any]:
        with self._lock:
            window = list(self._window)
            total = self._total
        base = {
            "enabled": self.enabled,
            "window_size": len(window),
            "window_capacity": self._window.maxlen,
            "min_samples": self._min_samples,
            "total_observed": total,
            "reference_size": self._n_reference,
            "thresholds": {"psi_warning": self._warning, "psi_critical": self._critical},
        }
        if not self.enabled or len(window) < self._min_samples:
            return {**base, "status": INSUFFICIENT, "drift_detected": False, "features": {}, "drifted_features": []}

        features: dict[str, Any] = {}
        for name, profile in self._features.items():
            values = [row[name] for row in window if name in row]
            value = profile_psi(profile, values)
            features[name] = {"psi": round(value, 4), "level": level_for(value, self._warning, self._critical)}
        drifted = sorted(name for name, item in features.items() if item["level"] != OK)
        critical = any(item["level"] == CRITICAL for item in features.values())
        share = len(drifted) / len(features)
        status = CRITICAL if critical else WARNING if share >= DRIFT_SHARE_ALERT else OK
        return {
            **base,
            "status": status,
            "drift_detected": status != OK,
            "share_drifted": round(share, 4),
            "drifted_features": drifted,
            "features": features,
        }
