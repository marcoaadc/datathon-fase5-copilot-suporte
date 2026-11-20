"""Avalia a busca do RAG no conjunto ``tests/data/rag_golden.json`` e grava ``reports/rag``.

Tres perguntas que a avaliacao responde:

1. a busca encontra a secao certa? (hit@1, hit@k e MRR, comparando densa, lexical e hibrida);
2. o limiar de relevancia separa pergunta respondivel de pergunta fora do escopo?
3. qual limiar escolher? (varredura do limiar com a taxa de acerto de cada lado)

Avalia apenas a *recuperacao*: nao chama LLM e por isso roda sem chave. A qualidade da resposta
gerada depende do provedor configurado e nao e medida aqui.

Uso:  python scripts/evaluate_rag.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supportcopilot.config.settings import get_settings  # noqa: E402
from supportcopilot.guardrails.engine import GuardrailEngine  # noqa: E402
from supportcopilot.rag.bootstrap import build_knowledge_base  # noqa: E402
from supportcopilot.rag.index import DENSE, HYBRID, LEXICAL  # noqa: E402

GOLDEN = ROOT / "tests" / "data" / "rag_golden.json"
THRESHOLDS = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)


def _rank(sections: list[str], expected: str) -> int | None:
    for position, section in enumerate(sections, start=1):
        if section.split(" ")[0] == expected:
            return position
    return None


def evaluate() -> dict:
    settings = get_settings()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    knowledge_base, report = build_knowledge_base(settings, GuardrailEngine())
    k, candidates = settings.retrieval_k, settings.retrieval_candidates

    modes: dict[str, dict] = {}
    misses: list[dict] = []
    for mode in (HYBRID, DENSE, LEXICAL):
        ranks = []
        for case in golden["in_scope"]:
            results = knowledge_base.search(case["question"], k=k, candidates=candidates, mode=mode)
            rank = _rank([chunk.section for chunk in results], case["section"])
            ranks.append(rank)
            if mode == HYBRID and rank is None:
                misses.append({**case, "retrieved": [chunk.section for chunk in results]})
        n = len(ranks)
        modes[mode] = {
            "hit_at_1": sum(rank == 1 for rank in ranks) / n,
            f"hit_at_{k}": sum(rank is not None for rank in ranks) / n,
            "mrr": sum(1 / rank for rank in ranks if rank) / n,
        }

    def top_similarity(question: str) -> float:
        results = knowledge_base.search(question, k=k, candidates=candidates)
        return max((chunk.similarity for chunk in results), default=0.0)

    inside = [top_similarity(case["question"]) for case in golden["in_scope"]]
    outside = [top_similarity(question) for question in golden["out_of_scope"]]
    sweep = [
        {
            "threshold": threshold,
            "in_scope_passed": sum(value >= threshold for value in inside) / len(inside),
            "out_of_scope_refused": sum(value < threshold for value in outside) / len(outside),
        }
        for threshold in THRESHOLDS
    ]
    return {
        "embedding_model": settings.embedding_model,
        "chunks": report.chunks_indexed,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "k": k,
        "n_in_scope": len(inside),
        "n_out_of_scope": len(outside),
        "modes": modes,
        "similarity": {
            "in_scope_min": min(inside),
            "in_scope_mean": sum(inside) / len(inside),
            "out_of_scope_max": max(outside),
            "out_of_scope_mean": sum(outside) / len(outside),
        },
        "min_relevance": settings.min_relevance,
        "threshold_sweep": sweep,
        "misses_hybrid": misses,
    }


def to_markdown(result: dict) -> str:
    k = result["k"]
    lines = [
        "# Avaliacao da busca do RAG",
        "",
        f"Modelo de embeddings `{result['embedding_model']}` | {result['chunks']} chunks "
        f"(tamanho {result['chunk_size']}, sobreposicao {result['chunk_overlap']}) | k = {k} | "
        f"{result['n_in_scope']} perguntas respondiveis e {result['n_out_of_scope']} fora do escopo.",
        "",
        f"| Estrategia | hit@1 | hit@{k} | MRR |",
        "|---|---|---|---|",
    ]
    for mode, metrics in result["modes"].items():
        lines.append(f"| {mode} | {metrics['hit_at_1']:.1%} | {metrics[f'hit_at_{k}']:.1%} | {metrics['mrr']:.3f} |")
    similarity = result["similarity"]
    lines += [
        "",
        "## Limiar de relevancia",
        "",
        f"Similaridade do melhor trecho: perguntas respondiveis de {similarity['in_scope_min']:.3f} "
        f"(minimo) a media {similarity['in_scope_mean']:.3f}; fora do escopo, media "
        f"{similarity['out_of_scope_mean']:.3f} e maximo {similarity['out_of_scope_max']:.3f}. "
        f"Limiar em uso: {result['min_relevance']}.",
        "",
        "| Limiar | Respondiveis que passam | Fora do escopo recusadas |",
        "|---|---|---|",
    ]
    for row in result["threshold_sweep"]:
        marker = " (em uso)" if abs(row["threshold"] - result["min_relevance"]) < 1e-9 else ""
        lines.append(
            f"| {row['threshold']:.2f}{marker} | {row['in_scope_passed']:.1%} | {row['out_of_scope_refused']:.1%} |"
        )
    if result["misses_hybrid"]:
        lines += ["", f"## Perguntas em que a secao esperada ficou fora do top {k} (hibrida)", ""]
        lines += [
            f"- {m['question']} (esperada {m['section']}; veio {', '.join(m['retrieved'])})"
            for m in result["misses_hybrid"]
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    result = evaluate()
    out_dir = get_settings().reports_dir / "rag"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retrieval_eval.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    markdown = to_markdown(result)
    (out_dir / "retrieval_eval.md").write_text(markdown, encoding="utf-8", newline="\n")
    sys.stdout.buffer.write(markdown.encode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
