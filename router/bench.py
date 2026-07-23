"""Bench de l'étage 1 (SafeRouter + HeuristicRouter) — preuve du budget §7.

Budget : p95 ≤ 5 ms CPU (docs/decisions/ROUTEUR_CLASSIFIEUR.md). AUCUN texte
de prompt généré ni manipulé : uniquement des nombres, booléens et flags de
vocabulaire fermé (règle n°1). Seed fixée (42) pour la reproductibilité
(invariant « reproductibilité », même doc). Écrit un petit rapport JSON
VERSIONNÉ dans `router/artifacts/bench/latest.json` (à distinguer des futurs
gros artefacts de modèles, R5, qui seront eux ignorés — cf. .gitignore).
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sobrio_router import ConversationSignals, HeuristicRouter, PromptSignals, SafeRouter, Signals

_SEED = 42
_N_SIGNALS = 5000
_N_WARMUP = 200
_P95_BUDGET_MS = 5.0

_LANGS = ("fr", "en", "other")
_FLAGS = ("contrat", "analyse", "code", "resume", "traduction", "demonstration")
_CURRENT_MODELS = ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8", None)

_ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "bench" / "latest.json"


def _git_sha() -> str:
    """Sha court du commit courant ; "unknown" hors dépôt git (ne doit jamais planter le bench)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _random_signals(rng: random.Random) -> Signals:
    """Un jeu de signaux aléatoire — QUE des nombres/booléens/flags, jamais de texte."""
    flags = tuple(rng.sample(_FLAGS, k=rng.randint(0, 2)))
    prompt = PromptSignals(
        char_len=rng.randint(0, 20_000),
        token_est=rng.randint(0, 6_000),
        lang=rng.choice(_LANGS),
        has_code=rng.random() < 0.2,
        has_math=rng.random() < 0.2,
        keyword_flags=flags,
    )
    conversation = ConversationSignals(
        msg_count=rng.randint(0, 40),
        context_token_est=rng.randint(0, 10_000),
        seen_code=rng.random() < 0.2,
        seen_math=rng.random() < 0.2,
        seen_reasoning=rng.random() < 0.2,
        current_model=rng.choice(_CURRENT_MODELS),
        recos_shown=rng.randint(0, 20),
        recos_followed=rng.randint(0, 20),
        derogations_up=rng.randint(0, 5),
    )
    return Signals(prompt=prompt, conversation=conversation)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentile par rang le plus proche — pas d'interpolation, suffisant pour un bench."""
    n = len(sorted_values)
    index = min(int(n * pct), n - 1)
    return sorted_values[index]


def main() -> int:
    rng = random.Random(_SEED)
    signals_pool = [_random_signals(rng) for _ in range(_N_SIGNALS)]

    router = SafeRouter(HeuristicRouter())

    # Warmup : stabilise l'exécuteur de threads (démarrage des workers), hors mesure.
    for signals in signals_pool[:_N_WARMUP]:
        router.decide(signals)

    latencies_ms: list[float] = []
    for signals in signals_pool:
        start = time.perf_counter()
        router.decide(signals)
        latencies_ms.append((time.perf_counter() - start) * 1000)
    latencies_ms.sort()

    report = {
        "n": len(latencies_ms),
        "p50_ms": round(_percentile(latencies_ms, 0.50), 4),
        "p95_ms": round(_percentile(latencies_ms, 0.95), 4),
        "date": datetime.now(tz=UTC).isoformat(),
        "git_sha": _git_sha(),
    }

    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report["p95_ms"] >= _P95_BUDGET_MS:
        print(
            f"ÉCHEC : p95={report['p95_ms']} ms >= budget {_P95_BUDGET_MS} ms (§7)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
