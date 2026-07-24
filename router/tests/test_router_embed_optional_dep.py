"""Tests « sans dépendances embed » RÉELS (spec R6 §1.3/§10.6) — R6 Lot 3.

Patron `test_router_ml_optional_dep` : un meta-path finder en tête de
`sys.meta_path` BLOQUE onnxruntime, tokenizers ET numpy dans un interpréteur
frais. `import sobrio_router` (TwoStageRouter compris) doit rester pleinement
fonctionnel, `from sobrio_router.embed import EmbedRouter` doit réussir
(imports paresseux §1.3), `EmbedHead` doit être CHARGEABLE ET EXÉCUTABLE
(stdlib pure §1.3) et SEULE la construction d'`EmbedRouter` doit échouer —
en `EmbedLoadError`, jamais en `ImportError` nu (le bridge s'y fiera, Lot 4).

Simulations in-process complémentaires (§10.6 b/c/d) : encodeur absent, tête
absente, clone-frais total — chaque branche échoue en `EmbedLoadError`
propre, que les dépendances embed soient installées ou non (aujourd'hui
elles ne le sont pas : recadrage 2026-07-23, geste fondateur non advenu).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sobrio_router.embed import EmbedHead, EmbedLoadError, EmbedRouter

_SCRIPT = """
import hashlib
import json
import sys
from pathlib import Path


class _BloqueurDepsEmbed:
    _RACINES = ("onnxruntime", "tokenizers", "numpy")

    def find_spec(self, name, path=None, target=None):
        for racine in self._RACINES:
            if name == racine or name.startswith(racine + "."):
                raise ImportError(f"{racine} bloque (simulation absence)")
        return None


sys.meta_path.insert(0, _BloqueurDepsEmbed())

# 1. Le paquet s'importe et TwoStageRouter fonctionne SANS deps embed.
import sobrio_router
from sobrio_router import ConversationSignals, HeuristicRouter, PromptSignals
from sobrio_router import Signals, TwoStageRouter

signals = Signals(
    prompt=PromptSignals(
        char_len=100, token_est=40, lang="fr", has_code=False, has_math=False, keyword_flags=()
    ),
    conversation=ConversationSignals(),
)
decision = TwoStageRouter(HeuristicRouter(), None).decide(signals)
assert decision.rule.startswith("heuristic:"), decision

# 2. L'import du MODULE embed reste possible (deps paresseuses, §1.3).
from sobrio_router.embed import EmbedHead, EmbedLoadError, EmbedRouter, expected_embed_spec
from sobrio_router.ml import LABEL_ORDER

# 3. EmbedHead est STDLIB PURE : chargeable ET exécutable sans AUCUNE dep.
tete_dir = Path(sys.argv[1]) / "tete"
tete_dir.mkdir(parents=True)
head = {
    "w": [[1.0 if j == i else 0.0 for j in range(384)] for i in range(3)],
    "b": [0.0, 0.0, 0.0],
}
head_octets = json.dumps(head).encode("utf-8")
(tete_dir / "head.json").write_bytes(head_octets)
calib_octets = json.dumps({"x": [0.0, 1.0], "y": [0.0, 1.0]}).encode("utf-8")
(tete_dir / "calibrator.json").write_bytes(calib_octets)
metadata = {
    "label_mapping": {label: index for index, label in enumerate(LABEL_ORDER)},
    "embed_spec": expected_embed_spec(),
    "confidence_cap": 0.74,
    "sha256_head_json": hashlib.sha256(head_octets).hexdigest(),
    "sha256_calibrator_json": hashlib.sha256(calib_octets).hexdigest(),
}
(tete_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
tete = EmbedHead.load(tete_dir)
label, conf = tete.predict([5.0] + [0.0] * 383)
assert label == LABEL_ORDER[0], label
assert conf == 0.74, conf  # chaîne §5.2bis complète, plafond compris

# 4. SEULE la construction d'EmbedRouter échoue — EmbedLoadError, pas ImportError.
try:
    EmbedRouter(encoder_dir=Path(sys.argv[1]) / "encodeur-absent", head_dir=tete_dir)
except EmbedLoadError:
    print("OK-sans-deps-embed")
except ImportError as exc:
    raise SystemExit(f"ImportError nu au lieu d'EmbedLoadError : {exc}")
else:
    raise SystemExit("construction inattendue sans deps embed")
"""


def test_import_sans_deps_embed(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK-sans-deps-embed" in proc.stdout
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# Simulations §10.6 (b)/(c)/(d) in-process — refus propres, jamais un
# traceback d'un autre type, valables avec OU sans deps embed installées.
# ---------------------------------------------------------------------------


def test_simulation_encodeur_absent(tmp_path: Path):
    """(b) : la tête seule ne suffit pas — construction refusée proprement."""
    from test_router_embed import _ecrire_tete

    _ecrire_tete(tmp_path / "tete")
    with pytest.raises(EmbedLoadError):
        EmbedRouter(encoder_dir=tmp_path / "encodeur", head_dir=tmp_path / "tete")


def test_simulation_tete_absente(tmp_path: Path):
    """(c) : `EmbedHead.load` sur dossier vide → EmbedLoadError chemin seul
    (branche testable SANS ambiguïté deps, EmbedHead étant stdlib pure)."""
    with pytest.raises(EmbedLoadError) as excinfo:
        EmbedHead.load(tmp_path / "tete-absente")
    assert "absent" in str(excinfo.value)
    assert "tete-absente" in str(excinfo.value)


def test_simulation_clone_frais_total(tmp_path: Path):
    """(d) : ni encodeur, ni tête, ni (aujourd'hui) deps — EmbedLoadError."""
    with pytest.raises(EmbedLoadError):
        EmbedRouter(encoder_dir=tmp_path / "encodeur", head_dir=tmp_path / "tete")


def test_repertoires_artefacts_embed_du_poste_sont_gitignores(monkeypatch):
    """Garde D4 : `heads/promoted/` du repo reste VIDE à la clôture R6 — si
    un artefact promu apparaissait ici, il vivrait sous `router/artifacts/*`
    (gitignoré, prouvé au Lot 2) ; on fige au moins l'invariant de chemin."""
    from sobrio_router.embed import ENCODER_DIR, PROMOTED_HEAD_DIR

    monkeypatch.delenv("SOBRIO_EMBED_ARTIFACTS_DIR", raising=False)
    racine = Path(__file__).resolve().parents[1] / "artifacts"
    assert ENCODER_DIR == racine / "embed" / "encoder"
    assert PROMOTED_HEAD_DIR == racine / "embed" / "heads" / "promoted"
