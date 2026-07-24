"""Vérification exécutable de la CI (`.github/workflows/ci.yml`) — R6 Lot 7, §10.7/§12.3.

MINOR-1 (2026-07-23) : la CI réelle vit dans `.github/workflows/ci.yml`
(`ops/` ne contient que README et docker-compose.prod.yml). Ces tests
rendent les critères cost-guard du chantier vérifiables PAR la suite — que
la CI exécute elle-même (auto-vérification) :

- aucune AFFECTATION de flag `SOBRIO_*` (ni bloc `env:` YAML, ni `X=` shell) ;
- jamais de téléchargement de modèle (`fetch_embed_model`, cible make) ;
- `requirements-embed` (et `requirements-ml`) jamais installés ;
- la suite COMPLÈTE (router+api+connector+warehouse+report) est exécutée —
  les tests embed y skippent proprement sans deps, et les simulations
  clone-frais/sans-deps §10.6 sont DES TESTS de cette suite ;
- la garde EXÉCUTABLE R6 (flags + deps embed) est présente dans le workflow.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _ci_source() -> str:
    return _CI_PATH.read_text(encoding="utf-8")


def test_ci_au_chemin_reel_minor_1():
    """Le workflow vit bien au chemin corrigé — un déplacement rendrait tous
    les tests de ce fichier silencieusement inertes (garde-fou du garde-fou)."""
    assert _CI_PATH.is_file(), _CI_PATH
    assert not (_REPO_ROOT / "ops" / "ci.yml").exists()
    assert "jobs:" in _ci_source()


def test_ci_ne_pose_aucun_flag_sobrio():
    """Aucune affectation `SOBRIO_X:` (env YAML) ni `SOBRIO_X=` (shell) dans
    tout le workflow — la garde grep `^SOBRIO_` du job n'est PAS une
    affectation et ne déclenche pas ce motif."""
    assert re.search(r"SOBRIO_[A-Z0-9_]+\s*[:=]", _ci_source()) is None


def test_ci_ne_telecharge_jamais_de_modele():
    source = _ci_source()
    assert "fetch_embed_model" not in source
    assert "router-embed-model" not in source


def test_ci_n_installe_pas_les_requirements_optionnels():
    """`pip install -r ...requirements-embed/-ml` interdit : les dépendances
    embed/ml sont OPTIONNELLES au runtime et n'entrent jamais en CI."""
    assert re.search(r"-r\s+\S*requirements-(embed|ml)\b", _ci_source()) is None


def test_ci_execute_la_suite_complete():
    """§12.1 : la suite router+api (et tous les lots Python) tourne en CI —
    les simulations §10.6 et les gardes privacy/réseau en font partie."""
    assert (
        "pytest router/tests api/tests connector/tests warehouse/tests report/tests" in _ci_source()
    )


def test_ci_porte_la_garde_executable_r6():
    """La garde n'est pas qu'un commentaire : étape nommée, grep des flags,
    contrôle d'absence des modules embed — la retirer fait échouer ici."""
    source = _ci_source()
    assert "Garde R6" in source
    assert "env | grep '^SOBRIO_'" in source
    assert '"onnxruntime"' in source
    assert '"tokenizers"' in source
