"""Tests des fixtures synthétiques d'embeddings (R6 Lot 5, spec §7/§10.8 — D6).

100 % stdlib, TOUJOURS exécutés : déterminisme bit-identique du générateur,
sha canonique == pin committé du manifest (`EMBED_GOLDEN_SHA256`),
étanchéité train/éval (intersection vide, SANS assert d'horloge — leçon du
flake consigné à l'audit de reprise), distribution des labels, normalisation
L2 (miroir §5.2.6), ZÉRO texte (aucun champ texte libre dans les entrées),
manifest committé < 5 Ko et cohérent avec les constantes du module.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import embed_fixtures
import pytest
from embed_fixtures import (
    DEFAULT_SIGMA,
    DIM,
    EVAL_N,
    EVAL_SEED,
    K_MOTIFS,
    MANIFEST_PATH,
    TRAIN_N,
    TRAIN_SEED,
    canonical_eval_set,
    canonical_sha256,
    canonical_train_set,
    embed_golden_sha256,
    generate,
)

from sobrio_router.ml import LABEL_ORDER

# ---------------------------------------------------------------------------
# Déterminisme (§10.8) — double run bit-identique, sha canonique épinglé.
# ---------------------------------------------------------------------------


def test_double_generate_bit_identique():
    """Mêmes (n, seed, sigma) => mêmes lignes, à l'octet de la sérialisation."""
    a = generate(60, 12345)
    b = generate(60, 12345)
    assert a == b
    assert canonical_sha256(a) == canonical_sha256(b)


def test_seed_different_change_les_lignes():
    """Contrôle négatif du déterminisme : un autre seed change les vecteurs."""
    assert canonical_sha256(generate(30, 1)) != canonical_sha256(generate(30, 2))


def test_sigma_controle_le_chevauchement():
    """Sigma est un paramètre EFFECTIF : le changer change les points."""
    assert canonical_sha256(generate(30, 7, sigma=0.2)) != canonical_sha256(
        generate(30, 7, sigma=0.5)
    )


def test_sha_canonique_egal_au_pin_du_manifest():
    """Le juge de paix : la matrice régénérée == le hash COMMITTÉ (toujours exécuté).

    Même rôle que `test_router_golden_frozen` pour l'étage 1 : toute dérive
    du générateur (seed, sigma, K, arrondi, ordre) casse ce test — le gate
    `--suite embed` refuse alors les rapports issus du set dérivé.
    """
    assert canonical_sha256(canonical_eval_set()) == embed_golden_sha256()


def test_pin_manifest_malforme_fail_closed(tmp_path: Path):
    """Manifest absent / illisible / pin non-hex => ValueError propre."""
    with pytest.raises(ValueError):
        embed_golden_sha256(tmp_path / "absent.json")
    mauvais = tmp_path / "manifest.json"
    mauvais.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ValueError):
        embed_golden_sha256(mauvais)
    mauvais.write_text(json.dumps({"embed_golden_sha256": "zz" * 32}), encoding="utf-8")
    with pytest.raises(ValueError):
        embed_golden_sha256(mauvais)


# ---------------------------------------------------------------------------
# Étanchéité train/éval (§7.1, patron anti-fuite R4 — SANS assert d'horloge).
# ---------------------------------------------------------------------------


def test_seeds_train_eval_distincts_par_construction():
    assert TRAIN_SEED != EVAL_SEED


def test_etancheite_train_eval_intersection_vide():
    """Aucun vecteur commun entre le set d'entraînement et le set d'éval."""
    train_vecteurs = {row.embedding for row in canonical_train_set()}
    eval_vecteurs = {row.embedding for row in canonical_eval_set()}
    assert not (train_vecteurs & eval_vecteurs)


# ---------------------------------------------------------------------------
# Propriétés géométriques et distribution (§7.1).
# ---------------------------------------------------------------------------


def test_dimensions_et_normalisation_l2():
    """384-d, norme L2 == 1 (miroir de la sortie réelle du pipeline §5.2.6)."""
    for row in canonical_eval_set():
        assert len(row.embedding) == DIM == 384
        norme = math.sqrt(sum(v * v for v in row.embedding))
        assert abs(norme - 1.0) < 1e-9


def test_distribution_des_labels_canonique():
    """Éval : 240 lignes, 80 par label ; train : 3000, 1000 par label."""
    eval_rows = canonical_eval_set()
    assert len(eval_rows) == EVAL_N == 240
    train_rows = canonical_train_set()
    assert len(train_rows) == TRAIN_N == 3000
    for label in LABEL_ORDER:
        assert sum(1 for r in eval_rows if r.label == label) == 80
        assert sum(1 for r in train_rows if r.label == label) == 1000


def test_aucun_texte_dans_les_fixtures():
    """D6 : vocabulaire FERMÉ — labels catalogue, catégories `motif_<k>`,
    vecteurs de floats finis. Aucun champ texte libre nulle part."""
    for row in canonical_eval_set():
        assert row.label in LABEL_ORDER
        assert row.categorie in {f"motif_{k}" for k in range(K_MOTIFS)}
        assert all(isinstance(v, float) and math.isfinite(v) for v in row.embedding)
        assert set(type(row).__dataclass_fields__) == {"embedding", "label", "categorie"}


def test_parametres_invalides_refuses():
    with pytest.raises(ValueError):
        generate(0, 1)
    with pytest.raises(ValueError):
        generate(-3, 1)
    with pytest.raises(ValueError):
        generate(10, 1, sigma=0.0)
    with pytest.raises(ValueError):
        generate(10, 1, sigma=float("nan"))


# ---------------------------------------------------------------------------
# Manifest committé (§7.1) : < 5 Ko, cohérent avec les constantes du module.
# ---------------------------------------------------------------------------


def test_manifest_committe_moins_de_5ko():
    assert MANIFEST_PATH.is_file()
    assert MANIFEST_PATH.stat().st_size < 5 * 1024


def test_manifest_coherent_avec_le_module():
    """Les paramètres épinglés du manifest == constantes du générateur (une
    seule source de vérité : muter l'un sans l'autre fait échouer)."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["n"] == EVAL_N
    assert manifest["seed"] == EVAL_SEED
    assert manifest["train_seed"] == TRAIN_SEED
    assert manifest["train_n"] == TRAIN_N
    assert manifest["centroid_seed"] == embed_fixtures.CENTROID_SEED
    assert manifest["k_motifs"] == K_MOTIFS
    assert manifest["sigma"] == DEFAULT_SIGMA
    assert manifest["dim"] == DIM
    assert manifest["float_decimales"] == embed_fixtures.FLOAT_DECIMALES
    assert manifest["labels_distribution"] == {label: 80 for label in LABEL_ORDER}
    # Statut d'honnêteté (D4/§7.2) consigné dans le manifest lui-même.
    assert "qualité sémantique" in manifest["statut"]
    assert "télémétrie v1" in manifest["statut"]
