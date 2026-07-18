"""Golden set FIGÉ (chantier R2) — hash, intégrité, anti-fuite.

Le golden set est le juge de paix : il départage les candidats (gate R3) et ne
sert JAMAIS à l'entraînement. Ces tests le verrouillent :
- le hash committé (`GOLDEN_SHA256`) correspond au fichier — toute modification
  du set doit passer par `generate_golden.py` + re-figeage EXPLICITE ;
- chaque entrée est bien formée (schéma, ids uniques, labels visibles, zéro
  texte de prompt) ;
- ANTI-FUITE : aucun id `gold-*` n'apparaît dans les corpus d'entraînement
  (`router/data/`), présents ou futurs.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from sobrio_router import VISIBLE_MODELS

_GOLDEN_DIR = pathlib.Path(__file__).resolve().parents[1] / "eval" / "golden"
_GOLDEN = _GOLDEN_DIR / "golden.jsonl"
_SHA_FILE = _GOLDEN_DIR / "GOLDEN_SHA256"
_DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"

# Champs EXACTS attendus (RFC-0001) — aucun texte libre, jamais prompt_text.
_PROMPT_KEYS = {"char_len", "token_est", "lang", "has_code", "has_math", "keyword_flags"}
_CONV_KEYS = {
    "msg_count",
    "context_token_est",
    "seen_code",
    "seen_math",
    "seen_reasoning",
    "current_model",
    "recos_shown",
    "recos_followed",
    "derogations_up",
}


def _entries() -> list[dict]:
    return [json.loads(line) for line in _GOLDEN.read_text().splitlines()]


def test_golden_hash_is_frozen():
    """Le sha256 du fichier == GOLDEN_SHA256 committé (set FIGÉ)."""
    expected = _SHA_FILE.read_text().split()[0]
    actual = hashlib.sha256(_GOLDEN.read_bytes()).hexdigest()
    assert actual == expected, (
        "golden.jsonl a changé sans re-figeage explicite — passer par "
        "generate_golden.py PUIS mettre à jour GOLDEN_SHA256 (cf. HUMAN_REVIEW_WELCOME.md)"
    )


def test_golden_entries_well_formed():
    entries = _entries()
    assert 150 <= len(entries) <= 200
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "ids gold-* dupliqués"
    for e in entries:
        assert set(e["signals"]["prompt"].keys()) == _PROMPT_KEYS, e["id"]
        assert set(e["signals"]["conversation"].keys()) == _CONV_KEYS, e["id"]
        assert e["label"] in VISIBLE_MODELS, e["id"]  # jamais claude-fable-5
        # Zéro texte de prompt nulle part (règle n°1).
        assert "prompt_text" not in json.dumps(e), e["id"]
        # La double-revue est tracée (plus aucun "pending" après arbitrage).
        assert set(e["review"].keys()) == {"ml_architect", "eval_scientist"}, e["id"]
        assert "pending" not in e["review"].values(), e["id"]


def _scan_for_gold_ids(data_dir: pathlib.Path) -> list[str]:
    """Cherche des ids gold-* dans un répertoire de corpus (anti-fuite).

    Seuil de 200 Mo : évite de charger en mémoire un très gros parquet/binaire ;
    les corpus R4 sont attendus BIEN en dessous (le test échouerait d'ailleurs
    à l'ouverture d'un binaire non-texte via errors="ignore" sans le seuil, il
    ne fait que borner le coût). NB : cette garde attrape la fuite d'IDS ; la
    déduplication au niveau SIGNAUX (vecteurs quasi-dupliqués golden↔train)
    relève du pipeline R4/R5 (data-quality-auditor).
    """
    offenders: list[str] = []
    if not data_dir.exists():
        return offenders
    for path in data_dir.rglob("*"):
        if not path.is_file() or path.stat().st_size > 200_000_000:
            continue
        try:
            content = path.read_text(errors="ignore")
        except (OSError, UnicodeError):
            continue
        if "gold-" in content:
            offenders.append(str(path))
    return offenders


def test_golden_never_leaks_into_training_data():
    """ANTI-FUITE : aucun id gold-* dans router/data/ (corpus d'entraînement).

    Vacuité assumée tant que router/data/ n'existe pas (R4) — la garde est
    PROUVÉE ACTIVE par le test de fixture ci-dessous (correction ronde 0,
    eval-scientist : un garde jamais déclenché ne prouve rien).
    """
    offenders = _scan_for_gold_ids(_DATA_DIR)
    assert not offenders, f"ids du golden set trouvés dans les corpus : {offenders}"


def test_leak_guard_actually_fires(tmp_path):
    """Fixture : la garde DÉTECTE réellement un id gold-* planté dans un corpus."""
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text('{"id": "train-1", "source": "copie interdite de gold-0042"}\n')
    offenders = _scan_for_gold_ids(tmp_path)
    assert offenders == [str(corpus)]
    # Et un corpus propre ne déclenche rien.
    corpus.write_text('{"id": "train-1", "source": "synthétique"}\n')
    assert _scan_for_gold_ids(tmp_path) == []
