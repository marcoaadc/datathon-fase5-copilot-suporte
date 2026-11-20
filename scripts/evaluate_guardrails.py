"""Avalia os guardrails de entrada contra a suite de casos (``tests/data/guardrail_cases.json``).

Mede as duas taxas que importam em um filtro: quanto dos ataques ele barra (recall) e quanto das
perguntas legitimas ele barra por engano (falso positivo). Sai com codigo 1 se alguma falhar.

Uso:  python scripts/evaluate_guardrails.py [--verbose]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supportcopilot.guardrails.engine import GuardrailEngine  # noqa: E402

CASES = ROOT / "tests" / "data" / "guardrail_cases.json"


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    engine = GuardrailEngine()
    failures: list[str] = []

    blocked = 0
    for case in cases["block"]:
        rules = engine.check_input(case["text"]).rule_ids
        if case["rule"] in rules:
            blocked += 1
        else:
            failures.append(f"NAO BLOQUEOU ({case['rule']} esperado, obtido {rules}): {case['text']!a}")
        if verbose:
            print(f"block {rules!s:22} {case['text']!a}")

    allowed = 0
    for text in cases["allow"]:
        rules = engine.check_input(text).rule_ids
        if not rules:
            allowed += 1
        else:
            failures.append(f"FALSO POSITIVO ({rules}): {text!a}")
        if verbose:
            print(f"allow {rules!s:22} {text!a}")

    n_block, n_allow = len(cases["block"]), len(cases["allow"])
    print(f"ataques bloqueados com a regra esperada: {blocked}/{n_block} ({blocked / n_block:.1%})")
    print(f"perguntas legitimas liberadas:           {allowed}/{n_allow} ({allowed / n_allow:.1%})")
    for failure in failures:
        print("  -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
