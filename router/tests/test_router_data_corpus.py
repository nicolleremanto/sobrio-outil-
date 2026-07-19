"""Tests du générateur de corpus + rapport data-quality (chantier R4).

Convention d'import : `router/data/` n'est pas un paquet installé (même
esprit que `router/eval/`, cf. `loader.py`) — on ajoute son chemin à
`sys.path` explicitement, ainsi que `router/eval/` pour comparer contre le
golden set FIGÉ (anti-fuite par signature).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import generate_corpus  # noqa: E402
from generate_corpus import generate  # noqa: E402
from loader import golden_signatures, load_golden, signal_signature  # noqa: E402
from quality_report import analyze  # noqa: E402

from sobrio_router import VISIBLE_MODELS, ConversationSignals, PromptSignals  # noqa: E402

_GENERATE_CORPUS_PATH = Path(__file__).resolve().parents[1] / "data" / "generate_corpus.py"
_QUALITY_REPORT_PATH = Path(__file__).resolve().parents[1] / "data" / "quality_report.py"


def _corpus_hash(rows: list[dict]) -> str:
    payload = "".join(json.dumps(r, sort_keys=True) for r in rows)
    return hashlib.sha256(payload.encode()).hexdigest()


def _run_cli(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Déterminisme
# ---------------------------------------------------------------------------


def test_generate_is_deterministic_same_seed():
    """Deux runs, même (n, seed, bruit) -> sha256 identique (§5.6)."""
    rows1, stats1, bruit_ids1 = generate(200, seed=4242, bruit_rate=0.03)
    rows2, stats2, bruit_ids2 = generate(200, seed=4242, bruit_rate=0.03)
    assert _corpus_hash(rows1) == _corpus_hash(rows2)
    assert stats1 == stats2
    assert bruit_ids1 == bruit_ids2


def test_generate_differs_with_different_seed():
    """Contrôle négatif : un seed différent change le corpus (le test positif ne triche pas)."""
    rows1, _, _ = generate(200, seed=4242, bruit_rate=0.03)
    rows2, _, _ = generate(200, seed=777, bruit_rate=0.03)
    assert _corpus_hash(rows1) != _corpus_hash(rows2)


def test_default_seed_differs_from_golden_seed():
    """Le seed par défaut (4242) est bien différent du seed du golden (2026) — cf. docstring.

    RAPPEL (reformulation ronde 0, M1) : cette différence de seed est une
    précaution SUPPLÉMENTAIRE — ce n'est PAS elle qui garantit l'absence de
    chevauchement (voir `test_no_exact_signal_signature_overlap_with_golden_at_delivered_n`
    ci-dessous, qui prouve la garantie RÉELLE : gabarits distincts + re-tirage actif).
    """
    assert generate_corpus.DEFAULT_SEED == 4242
    assert generate_corpus.DEFAULT_SEED != 2026


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------


def test_rows_load_as_signals_without_error():
    """Chaque ligne échantillonnée se charge en `Signals` via `sobrio_router.types`."""
    rows, _, _ = generate(300, seed=4242, bruit_rate=0.03)
    for row in rows:
        prompt = PromptSignals(**row["signals"]["prompt"])
        conversation = ConversationSignals(**row["signals"]["conversation"])
        assert prompt.prompt_text is None
        assert isinstance(conversation.msg_count, int)


def test_labels_are_visible_models():
    rows, _, _ = generate(300, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert row["label"] in VISIBLE_MODELS


def test_ids_are_corp_prefixed_and_unique():
    rows, _, _ = generate(300, seed=4242, bruit_rate=0.03)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for row_id in ids:
        assert row_id.startswith("corp-")
        assert not row_id.startswith("gold-")


def test_no_prompt_text_anywhere():
    rows, _, _ = generate(300, seed=4242, bruit_rate=0.03)
    dump = json.dumps(rows)
    assert "prompt_text" not in dump


def test_row_shape_is_exact():
    """Chaque ligne = exactement {id, category, label, signals}, rien de plus.

    Prouve aussi que la clé transitoire interne `_bruit` (mécanisme M3, voir
    `generate_corpus.generate`) ne fuite JAMAIS dans une ligne livrée.
    """
    rows, _, _ = generate(50, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert set(row.keys()) == {"id", "category", "label", "signals"}
        assert set(row["signals"].keys()) == {"prompt", "conversation"}


def test_recos_followed_never_exceeds_recos_shown():
    rows, _, _ = generate(2000, seed=4242, bruit_rate=0.03)
    for row in rows:
        c = row["signals"]["conversation"]
        assert c["recos_followed"] <= c["recos_shown"]


# ---------------------------------------------------------------------------
# Validation d'entrée (M7, correction ronde 0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_n", [0, -1, -1000])
def test_generate_rejects_non_positive_n(bad_n):
    with pytest.raises(ValueError, match="n doit être"):
        generate(bad_n)


@pytest.mark.parametrize("bad_bruit", [-0.01, 1.01, -1.0, 2.0])
def test_generate_rejects_bruit_out_of_range(bad_bruit):
    with pytest.raises(ValueError, match="bruit_rate"):
        generate(100, bruit_rate=bad_bruit)


def test_generate_accepts_bruit_boundaries_inclusive():
    """`--bruit` dans [0, 1] STRICT (M7) : les bornes 0 et 1 sont valides, pas juste l'intérieur."""
    rows0, stats0, _ = generate(50, bruit_rate=0.0)
    assert stats0["bruit_rate_effectif"] == 0.0
    rows1, stats1, _ = generate(50, bruit_rate=1.0)
    assert len(rows1) == 50  # génère toujours, même bruit total


def test_allocate_rejects_negative_total():
    """M7 : `_allocate` levait un défaut SILENCIEUX sur total négatif (slicing négatif Python) —
    `order[:remainder]` avec `remainder < 0` retournait un sous-ensemble depuis la FIN de la
    liste sans jamais lever d'erreur. Garde interne ajoutée : `ValueError` explicite."""
    with pytest.raises(ValueError, match="total doit être"):
        generate_corpus._allocate(-3, {"a": 1.0, "b": 1.0})


def test_allocate_zero_total_is_valid_and_returns_all_zero():
    result = generate_corpus._allocate(0, {"a": 1.0, "b": 2.0})
    assert result == {"a": 0, "b": 0}


def test_allocate_negative_total_previously_produced_silent_wrong_result():
    """Contrôle négatif : reproduit le calcul SANS la garde pour prouver que le défaut était réel
    (pas seulement une garde ajoutée par prudence sans bug sous-jacent). Poids INÉGAUX requis :
    avec des poids égaux, la troncature vers zéro de `int()` compense exactement (remainder=0)."""
    weights = {"a": 1.0, "b": 2.0}
    total = -5
    keys = list(weights)
    total_weight = sum(weights.values())
    raw = {k: total * weights[k] / total_weight for k in keys}
    base = {k: int(raw[k]) for k in keys}
    remainder = total - sum(base.values())
    assert remainder < 0  # confirme la précondition du bug
    order = sorted(keys, key=lambda k: raw[k] - base[k], reverse=True)
    # `order[:remainder]` avec remainder négatif ne lève RIEN : slicing Python
    # valide qui retourne un sous-ensemble depuis la fin — silencieux et faux.
    poisoned = dict(base)
    for k in order[:remainder]:
        poisoned[k] += 1
    assert poisoned != base  # le résultat a bien été altéré silencieusement (le bug)


# ---------------------------------------------------------------------------
# CLI (M7, correction ronde 0) — sous-processus réel, comme
# `test_router_eval_gate_hardening.py` (message propre + exit 2, pas de
# traceback).
# ---------------------------------------------------------------------------


def test_cli_rejects_non_positive_n(tmp_path):
    proc = _run_cli(_GENERATE_CORPUS_PATH, ["--n", "0", "--out-dir", str(tmp_path)])
    assert proc.returncode == 2
    assert "--n" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_rejects_bruit_out_of_range(tmp_path):
    proc = _run_cli(
        _GENERATE_CORPUS_PATH, ["--n", "50", "--bruit", "1.5", "--out-dir", str(tmp_path)]
    )
    assert proc.returncode == 2
    assert "--bruit" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_rejects_negative_bruit(tmp_path):
    proc = _run_cli(
        _GENERATE_CORPUS_PATH, ["--n", "50", "--bruit", "-0.5", "--out-dir", str(tmp_path)]
    )
    assert proc.returncode == 2
    assert "--bruit" in proc.stderr


def test_cli_rejects_out_dir_colliding_with_existing_file(tmp_path):
    """`--out-dir` pointant vers un chemin qui EST déjà un fichier (pas un dossier) : message
    propre + exit 2, pas le `FileExistsError`/`NotADirectoryError` brut de `Path.mkdir`."""
    blocked = tmp_path / "blocked"
    blocked.write_text("je suis un fichier, pas un dossier", encoding="utf-8")
    proc = _run_cli(_GENERATE_CORPUS_PATH, ["--n", "50", "--out-dir", str(blocked)])
    assert proc.returncode == 2
    assert "--out-dir" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_valid_args_writes_bruit_annexe(tmp_path):
    """Preuve que la CLI écrit bien l'annexe `corpus-v1.bruit.json` (M3b)."""
    proc = _run_cli(_GENERATE_CORPUS_PATH, ["--n", "200", "--out-dir", str(tmp_path)])
    assert proc.returncode == 0, proc.stderr
    bruit_path = tmp_path / "corpus-v1.bruit.json"
    assert bruit_path.exists()
    payload = json.loads(bruit_path.read_text(encoding="utf-8"))
    assert "bruit_ids" in payload
    assert all(bid.startswith("corp-") for bid in payload["bruit_ids"])


def test_quality_report_cli_rejects_missing_corpus(tmp_path):
    proc = _run_cli(_QUALITY_REPORT_PATH, ["--corpus", str(tmp_path / "inexistant.jsonl.gz")])
    assert proc.returncode == 2
    assert "introuvable" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_quality_report_cli_rejects_unreadable_corpus(tmp_path):
    """Fichier présent mais illisible (pas un gzip valide) : message propre + exit 2."""
    bogus = tmp_path / "corpus-v1.jsonl.gz"
    bogus.write_bytes(b"pas du gzip valide")
    proc = _run_cli(_QUALITY_REPORT_PATH, ["--corpus", str(bogus)])
    assert proc.returncode == 2
    assert "illisible" in proc.stderr
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# Anti-fuite (M1) + anti-contradiction (M3), correction ronde 0
# ---------------------------------------------------------------------------


def test_no_exact_signal_signature_overlap_with_golden_fast():
    """Test RAPIDE (boucle courte, n=5000) — garanti par le même mécanisme de re-tirage
    que le test au N LIVRÉ ci-dessous, juste sur un échantillon plus petit."""
    golden_sigs = golden_signatures()
    rows, _, _ = generate(5000, seed=4242, bruit_rate=0.03)
    corpus_sigs = {
        signal_signature(r["signals"]["prompt"], r["signals"]["conversation"]) for r in rows
    }
    overlap = golden_sigs & corpus_sigs
    assert not overlap, f"signatures partagées golden/corpus : {overlap}"


def test_no_exact_signal_signature_overlap_with_golden_at_delivered_n():
    """CORRECTION STRUCTURELLE (M1, ronde 0) : le test tournait AVANT à n=5000 — intersection
    vide « à vide », le corpus livré (30 000) n'était JAMAIS vérifié. Ce test régénère le N
    LIVRÉ EN MÉMOIRE (aucune écriture disque) et prouve l'intersection vide, chronométré
    (cf. assertion de budget EN FIN de test) — la garde anti-fuite par re-tirage rend le
    docstring de `generate_corpus.py` VRAI par construction, plus seulement plausible par
    rareté.
    """
    golden_sigs = golden_signatures()
    start = time.perf_counter()
    rows, stats, _ = generate(generate_corpus.DEFAULT_N, seed=generate_corpus.DEFAULT_SEED)
    elapsed = time.perf_counter() - start
    assert stats["n"] == generate_corpus.DEFAULT_N

    corpus_sigs = {
        signal_signature(r["signals"]["prompt"], r["signals"]["conversation"]) for r in rows
    }
    overlap = golden_sigs & corpus_sigs
    assert not overlap, f"signatures partagées golden/corpus au N LIVRÉ : {overlap}"

    # Chrono APRÈS la preuve substantielle (minor sentinelles r3) : l'ancien
    # seuil de 2,0 s placé AVANT l'intersection a flaké sous suite chargée
    # (2,37 s mesuré) et empêchait la preuve anti-fuite de s'exécuter. Marge
    # documentée : 5,0 s ≈ 2x le pire mesuré — le budget de boucle reste
    # surveillé sans plus jamais masquer l'assertion d'intersection vide.
    assert elapsed < 5.0, f"régénération 30 000 lignes trop lente pour la boucle : {elapsed:.2f}s"


def test_golden_signatures_matches_local_reconstruction():
    """`loader.golden_signatures()` (partagée, M1) reconstruit la MÊME chose qu'un calcul
    indépendant via `load_golden()` — contrôle croisé de la fonction de hachage partagée."""
    golden_entries = load_golden()
    local = {
        signal_signature(
            {
                "char_len": e.signals.prompt.char_len,
                "token_est": e.signals.prompt.token_est,
                "lang": e.signals.prompt.lang,
                "has_code": e.signals.prompt.has_code,
                "has_math": e.signals.prompt.has_math,
                "keyword_flags": list(e.signals.prompt.keyword_flags),
            },
            {
                "msg_count": e.signals.conversation.msg_count,
                "context_token_est": e.signals.conversation.context_token_est,
                "seen_code": e.signals.conversation.seen_code,
                "seen_math": e.signals.conversation.seen_math,
                "seen_reasoning": e.signals.conversation.seen_reasoning,
                "current_model": e.signals.conversation.current_model,
                "recos_shown": e.signals.conversation.recos_shown,
                "recos_followed": e.signals.conversation.recos_followed,
                "derogations_up": e.signals.conversation.derogations_up,
            },
        )
        for e in golden_entries
    }
    assert golden_signatures() == local


def test_no_gold_ids_in_corpus():
    """Aucun id `gold-*` n'apparaît dans le corpus généré (anti-fuite d'ids)."""
    rows, _, _ = generate(2000, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert not row["id"].startswith("gold-")
    assert "gold-" not in json.dumps(rows)


def test_generate_stats_expose_anti_fuite_and_contradiction_counters():
    """Les compteurs M1/M3 existent TOUJOURS dans `stats`, même à 0 (jamais silencieux)."""
    _, stats, _ = generate(2000, seed=4242, bruit_rate=0.03)
    for key in (
        "n_rejets_anti_fuite",
        "n_rejets_contradiction",
        "n_abandons_anti_fuite",
        "n_abandons_contradiction",
        "n_abandons",
    ):
        assert key in stats
        assert stats[key] >= 0
    assert stats["n_abandons"] == stats["n_abandons_anti_fuite"] + stats["n_abandons_contradiction"]


def test_delivered_corpus_abandons_stay_negligible():
    """Au N livré (seed par défaut), les abandons restent NÉGLIGEABLES (< 1 % de n) — un taux
    élevé signalerait un plafond de tentatives trop bas ou un espace de signaux trop pauvre."""
    _, stats, _ = generate(generate_corpus.DEFAULT_N, seed=generate_corpus.DEFAULT_SEED)
    assert stats["n_abandons"] < 0.01 * generate_corpus.DEFAULT_N


def test_generate_forces_abandon_when_every_candidate_collides_with_golden(monkeypatch):
    """Preuve par exécution du PLAFOND de re-tirage (M1) : un golden factice qui contient
    TOUJOURS la signature testée force l'épuisement de `_MAX_RETIRAGE_ATTEMPTS` puis
    l'ABANDON — la ligne n'apparaît jamais dans le corpus livré, comptée, jamais silencieuse.
    """

    class _AlwaysCollides:
        def __contains__(self, item):
            return True

    monkeypatch.setattr(generate_corpus, "golden_signatures", lambda: _AlwaysCollides())
    rows, stats, _ = generate(5, seed=1, bruit_rate=0.0)
    assert rows == []
    assert stats["n_abandons_anti_fuite"] == 5
    assert stats["n_rejets_anti_fuite"] == 5 * generate_corpus._MAX_RETIRAGE_ATTEMPTS
    assert stats["n_abandons_contradiction"] == 0


def test_generate_forces_abandon_on_forced_contradiction(monkeypatch):
    """Preuve par exécution de la garde anti-contradiction (M3) : une signature CONSTANTE
    force chaque nouveau label distinct à contredire le premier label vu — retiré puis
    abandonné, sans jamais laisser deux labels différents cohabiter sous la même signature."""
    monkeypatch.setattr(generate_corpus, "golden_signatures", lambda: frozenset())
    monkeypatch.setattr(
        generate_corpus, "signal_signature", lambda prompt, conversation: ("const",)
    )
    rows, stats, _ = generate(500, seed=4242, bruit_rate=0.0)
    assert stats["n_rejets_contradiction"] > 0
    assert stats["n_abandons_contradiction"] > 0
    # Un SEUL label vérité a pu s'installer sur la signature constante : toutes les lignes
    # ACCEPTÉES (label vérité, avant tout bruit — désactivé ici, bruit_rate=0.0) partagent
    # donc le même label.
    accepted_labels = {r["label"] for r in rows}
    assert len(accepted_labels) == 1


# ---------------------------------------------------------------------------
# M2 (correction ronde 0) — descriptions de gabarits STRUCTURELLEMENT
# distinctes du golden set, jamais copiées ni quasi-paraphrasées.
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    """Distance d'édition classique (stdlib pure, `router/` reste sans dépendance)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _import_generate_golden():
    golden_dir = str(Path(__file__).resolve().parents[1] / "eval" / "golden")
    if golden_dir not in sys.path:
        sys.path.insert(0, golden_dir)
    import generate_golden

    return generate_golden


def test_corpus_template_notes_share_no_exact_string_with_golden():
    """Aucune chaîne `note` du corpus n'apparaît EXACTEMENT dans les notes golden (M2)."""
    generate_golden = _import_generate_golden()
    corpus_notes = {t.note for t in generate_corpus.TEMPLATES}
    golden_notes = {g.note for g in generate_golden.GABARITS}
    assert corpus_notes.isdisjoint(golden_notes), corpus_notes & golden_notes


def test_corpus_template_notes_are_not_near_paraphrases_of_golden():
    """Distance d'édition NORMALISÉE raisonnable entre chaque note corpus et sa plus proche
    voisine golden (M2 : « 3 notes mot pour mot + ~18 quasi-paraphrases » avant correction).
    Seuil 0.55 : les notes réécrites (M2) adoptent un style PARAMÉTRIQUE/statistique
    structurellement différent du style narratif du golden — largement au-dessus du seuil
    en pratique (voir les 5 plus proches imprimées ci-dessous en cas d'échec, preuve versée
    au ledger)."""
    generate_golden = _import_generate_golden()
    corpus_notes = [t.note for t in generate_corpus.TEMPLATES]
    golden_notes = [g.note for g in generate_golden.GABARITS]

    ranked: list[tuple[float, str, str]] = []
    for note in corpus_notes:
        best_ratio = 1.0
        best_golden = ""
        for g in golden_notes:
            ratio = _levenshtein(note, g) / max(len(note), len(g))
            if ratio < best_ratio:
                best_ratio, best_golden = ratio, g
        ranked.append((best_ratio, note, best_golden))
    ranked.sort(key=lambda x: x[0])

    cinq_plus_proches = "\n".join(
        f"  ratio={ratio:.2f}\n    corpus : {note!r}\n    golden : {golden!r}"
        for ratio, note, golden in ranked[:5]
    )
    for ratio, note, golden in ranked:
        assert ratio > 0.55, (
            f"note du corpus trop proche d'une note golden (distance normalisée {ratio:.2f}) "
            f"— 5 plus proches de tout le set :\n{cinq_plus_proches}\n\n"
            f"CETTE paire :\n  corpus : {note!r}\n  golden : {golden!r}"
        )


# ---------------------------------------------------------------------------
# M4 (correction ronde 0) — poids opus juridique_contrat rééquilibré ~18-20 %.
# ---------------------------------------------------------------------------


def test_juridique_contrat_opus_share_is_in_target_range():
    """La part opus de `juridique_contrat` doit rester ~18-20 % — PAS 39,6 % (avant M4),
    cohérente avec code (~20,7 %) et maths (~17 %), cf. rationale dans generate_corpus.py."""
    templates = [t for t in generate_corpus.TEMPLATES if t.category == "juridique_contrat"]
    total_weight = sum(t.weight for t in templates)
    opus_weight = sum(t.weight for t in templates if t.label == "claude-opus-4-8")
    share = opus_weight / total_weight
    assert 0.15 <= share <= 0.25, f"part opus juridique_contrat hors cible : {share:.2%}"


def test_delivered_corpus_juridique_contrat_opus_share_matches_target():
    """Vérifie la cible M4 sur le corpus RÉELLEMENT généré (pas seulement les poids déclarés)."""
    rows, _, _ = generate(generate_corpus.DEFAULT_N, seed=generate_corpus.DEFAULT_SEED)
    juridique = [r for r in rows if r["category"] == "juridique_contrat"]
    opus = [r for r in juridique if r["label"] == "claude-opus-4-8"]
    share = len(opus) / len(juridique)
    assert 0.15 <= share <= 0.25, f"part opus juridique_contrat livrée hors cible : {share:.2%}"


# ---------------------------------------------------------------------------
# quality_report — doublons/contradictions (M3) + reste
# ---------------------------------------------------------------------------


def test_quality_report_healthy_corpus_is_ok():
    rows, _, bruit_ids = generate(1000, seed=4242, bruit_rate=0.03)
    report = analyze(rows, frozenset(bruit_ids))
    assert report["verdict"]["ok"] is True, report["verdict"]["alertes"]


def test_quality_report_flags_duplicates_and_imbalance():
    """Corpus FABRIQUÉ (doublons massifs + déséquilibre extrême) -> alertes."""
    dup_signals = {
        "prompt": {
            "char_len": 100,
            "token_est": 40,
            "lang": "fr",
            "has_code": False,
            "has_math": False,
            "keyword_flags": [],
        },
        "conversation": {
            "msg_count": 0,
            "context_token_est": 0,
            "seen_code": False,
            "seen_math": False,
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }
    rows = [
        {
            "id": f"corp-{i:06d}",
            "category": "redaction_simple",
            "label": "claude-haiku-4-5",
            "signals": dup_signals,
        }
        for i in range(1, 96)
    ] + [
        {
            "id": f"corp-{i:06d}",
            "category": "redaction_simple",
            "label": "claude-opus-4-8",
            "signals": {**dup_signals, "prompt": {**dup_signals["prompt"], "char_len": 100 + i}},
        }
        for i in range(96, 101)
    ]
    report = analyze(rows)
    assert report["verdict"]["ok"] is False
    assert report["taux_doublons_signature"] > 0.05
    assert any("doublons" in a for a in report["verdict"]["alertes"])
    assert any("cellules" in a or "déséquilibre" in a for a in report["verdict"]["alertes"])
    # Les 95 lignes dupliquées partagent TOUTES le même label : doublons
    # inoffensifs, PAS des contradictions.
    assert report["doublons_detail"]["n_doublons_meme_label"] == 94
    assert report["doublons_detail"]["n_contradictions_bruit"] == 0
    assert report["doublons_detail"]["n_contradictions_hors_bruit"] == 0


def test_quality_report_empty_corpus():
    report = analyze([])
    assert report["verdict"]["ok"] is False


def test_quality_report_flags_contradiction_without_bruit_annexe():
    """Sans annexe bruit (`bruit_ids=None`) : toute contradiction est comptée HORS bruit par
    défaut (conservateur, fail-visible) — deux lignes, signature identique, labels différents,
    AUCUN moyen de savoir si c'est du bruit -> alerte."""
    signals = {
        "prompt": {
            "char_len": 100,
            "token_est": 40,
            "lang": "fr",
            "has_code": False,
            "has_math": False,
            "keyword_flags": [],
        },
        "conversation": {
            "msg_count": 0,
            "context_token_est": 0,
            "seen_code": False,
            "seen_math": False,
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }
    rows = [
        {"id": "corp-000001", "category": "code", "label": "claude-haiku-4-5", "signals": signals},
        {"id": "corp-000002", "category": "code", "label": "claude-opus-4-8", "signals": signals},
    ]
    report = analyze(rows)  # pas d'annexe bruit
    assert report["doublons_detail"]["annexe_bruit_disponible"] is False
    assert report["doublons_detail"]["n_contradictions_hors_bruit"] == 1
    assert report["verdict"]["ok"] is False
    assert any("HORS bruit" in a or "hors-bruit" in a.lower() for a in report["verdict"]["alertes"])


def test_quality_report_distinguishes_bruit_from_hors_bruit_contradiction():
    """Avec annexe bruit : une contradiction EXPLIQUÉE par le bruit (une des deux lignes est
    dans `bruit_ids`) ne déclenche PAS l'alerte hors-bruit ; une contradiction NON expliquée le
    fait toujours."""
    signals = {
        "prompt": {
            "char_len": 100,
            "token_est": 40,
            "lang": "fr",
            "has_code": False,
            "has_math": False,
            "keyword_flags": [],
        },
        "conversation": {
            "msg_count": 0,
            "context_token_est": 0,
            "seen_code": False,
            "seen_math": False,
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }
    rows = [
        {"id": "corp-000001", "category": "code", "label": "claude-haiku-4-5", "signals": signals},
        {"id": "corp-000002", "category": "code", "label": "claude-opus-4-8", "signals": signals},
    ]
    # corp-000002 est marqué bruité : la contradiction est EXPLIQUÉE. (Le taux
    # de doublons GLOBAL déclenche quand même l'alerte historique à 5 % sur
    # cet échantillon minuscule de 2 lignes — non spécifique à M3, cf.
    # `taux_doublons_signature` — donc on vérifie l'ABSENCE de l'alerte
    # HORS-bruit précisément, pas le verdict global.)
    report_explained = analyze(rows, frozenset({"corp-000002"}))
    assert report_explained["doublons_detail"]["n_contradictions_bruit"] == 1
    assert report_explained["doublons_detail"]["n_contradictions_hors_bruit"] == 0
    assert not any("HORS bruit" in a for a in report_explained["verdict"]["alertes"])

    # Un troisième label, sur une ligne NON bruitée, cohabite : contradiction
    # HORS bruit désormais présente malgré l'annexe.
    rows_hors_bruit = rows + [
        {
            "id": "corp-000003",
            "category": "code",
            "label": "claude-sonnet-5",
            "signals": signals,
        }
    ]
    report_mixed = analyze(rows_hors_bruit, frozenset({"corp-000002"}))
    assert report_mixed["doublons_detail"]["n_contradictions_hors_bruit"] > 0
    assert report_mixed["verdict"]["ok"] is False


def test_delivered_corpus_has_zero_structural_contradictions():
    """Preuve directe (M3) sur le corpus RÉELLEMENT généré au N livré : la garde
    anti-contradiction du générateur garantit 0 contradiction hors-bruit."""
    rows, stats, bruit_ids = generate(generate_corpus.DEFAULT_N, seed=generate_corpus.DEFAULT_SEED)
    report = analyze(rows, frozenset(bruit_ids))
    assert report["doublons_detail"]["n_contradictions_hors_bruit"] == 0
    assert report["verdict"]["ok"] is True, report["verdict"]["alertes"]


def test_reference_artifacts_locked_to_regeneration():
    """Minor eval r1 : rien ne verrouillait les artefacts de référence commités.
    Régénère AU N LIVRÉ avec les paramètres de référence et compare le sha du
    .gz canonique + la version du générateur à ceux de reference/metadata."""
    import hashlib

    meta = json.loads(
        (
            Path(__file__).resolve().parents[1] / "data" / "reference" / "corpus-v1.metadata.json"
        ).read_text()
    )
    rows, stats, _bruit_ids = generate_corpus.generate(
        meta["n"], seed=meta["seed"], bruit_rate=meta["bruit_rate_parametre"]
    )
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    compressed = gzip.compress(payload.encode("utf-8"), compresslevel=9, mtime=0)
    assert hashlib.sha256(compressed).hexdigest() == meta["sha256_gz"]
    assert meta["generator_version"] == generate_corpus.__version__
    assert stats["n_abandons"] == meta["n_abandons"] == 0


def test_guard_detects_real_golden_drift(tmp_path):
    """Garde de couplage v2 (major r2 : la v1 comparait GOLDEN_SHA256 à
    lui-même — tautologie prouvée par les juges). Ici, DÉRIVE RÉELLE, zéro
    monkeypatch : copie du dossier golden, golden.jsonl muté SANS re-figer
    GOLDEN_SHA256 → la garde recalcule les octets et refuse."""
    import shutil

    golden_dir = Path(generate_corpus.__file__).resolve().parents[1] / "eval" / "golden"
    copy = tmp_path / "golden"
    copy.mkdir()
    for name in ("golden.jsonl", "GOLDEN_SHA256"):
        shutil.copy(golden_dir / name, copy / name)

    # Intact : la garde passe.
    generate_corpus._verifier_golden_fige(copy)

    # Dérive réelle (ligne ajoutée, sha committé inchangé) : refus bruyant.
    with (copy / "golden.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"id": "gold-9999", "category": "code", "label": "claude-haiku-4-5"}\n')
    with pytest.raises(RuntimeError, match="dérivé"):
        generate_corpus._verifier_golden_fige(copy)

    # Sens MIROIR (minor dq r3) : golden.jsonl intact, GOLDEN_SHA256 muté.
    shutil.copy(golden_dir / "golden.jsonl", copy / "golden.jsonl")
    (copy / "GOLDEN_SHA256").write_text("f" * 64 + "  golden.jsonl\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="dérivé"):
        generate_corpus._verifier_golden_fige(copy)

    # Fichier sha vide/malformé (minor eval r3) : RuntimeError propre, pas IndexError.
    (copy / "GOLDEN_SHA256").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="malformé"):
        generate_corpus._verifier_golden_fige(copy)


def test_guard_wired_into_generate(monkeypatch):
    """La garde v2 est APPELÉE par generate() — et SANS argument, donc sur le
    _GOLDEN_DIR réel par défaut (minor qa r3 : le spy verrouille les args)."""
    calls = []
    monkeypatch.setattr(
        generate_corpus,
        "_verifier_golden_fige",
        lambda *a, **k: calls.append((a, k)),
    )
    generate_corpus.generate(20, seed=4242, bruit_rate=0.0)
    assert calls == [((), {})]


def test_cli_end_to_end_refuses_derived_golden(tmp_path):
    """Bout-en-bout (major qa r3) : le VRAI chemin CLI (subprocess, comme
    make router-corpus) sur une copie sandbox de router/ au golden dérivé →
    « REFUS » propre exit 2, pas de traceback — le test qui aurait révélé le
    major (la garde levait, main() ne rattrapait pas)."""
    import shutil as _shutil

    src = Path(generate_corpus.__file__).resolve().parents[1]
    sandbox = tmp_path / "router"
    _shutil.copytree(
        src,
        sandbox,
        ignore=_shutil.ignore_patterns(
            "artifacts", "tests", "__pycache__", "*.egg-info", ".pytest_cache"
        ),
    )
    with (sandbox / "eval" / "golden" / "golden.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"id": "gold-9998", "category": "resume", "label": "claude-haiku-4-5"}\n')

    proc = subprocess.run(
        [
            sys.executable,
            str(sandbox / "data" / "generate_corpus.py"),
            "--n",
            "20",
            "--out-dir",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2
    assert "REFUS" in proc.stderr and "dérivé" in proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize(
    ("anti_fuite", "contradiction", "attendu"),
    [
        (49, 1, "anti_fuite"),  # dominante anti-fuite (le cas du minor r1)
        (1, 49, "contradiction"),
        (25, 25, "anti_fuite"),  # égalité → la garde la plus critique
    ],
)
def test_abandon_attribution_by_dominant_cause(anti_fuite, contradiction, attendu):
    """Chemin d'abandon latent (0 abandon sur le corpus livré) : la règle
    d'attribution est verrouillée unitairement (minor eval/qa r2)."""
    assert generate_corpus._attribuer_abandon(anti_fuite, contradiction) == attendu
