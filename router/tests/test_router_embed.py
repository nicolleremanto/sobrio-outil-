"""Tests du cœur de l'étage 2 (`sobrio_router/embed.py`) — R6 Lot 3, spec §10.4.

Couvre : pin littéral INTÉGRAL du embed_spec (patron QA-R5-m1), chargement
fail-closed champ par champ (patron feature_spec/label_mapping R5),
`confidence_cap` NORMATIF §6.3, chaîne de confiance §5.2bis maillon par
maillon, ISO-CONFIANCE harnais/service (correction MAJOR-1), le segment
NORMATIF encode→poole→normalise de `_embed` à session/tokenizer FACTICES
(QA-R6-M1, ronde 0), refus sans texte (défense en profondeur), hygiène des
exceptions (jamais de contenu).

Stdlib partout SAUF les tests de `_embed` (QA-R6-M1) : ils exécutent
RÉELLEMENT le pooling masqué + L2 et n'exigent que numpy (importorskip —
installé via requirements-ml) ; ailleurs `EmbedHead` est pur et l'encodeur
est monkeypatché (le modèle réel attend le geste fondateur, recadrage ledger
2026-07-23). Textes de test = soupe de mots-vides + sentinelle aléatoire
(convention chantier, JAMAIS de texte type prompt).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest_helpers import make_signals

from sobrio_router import Signals
from sobrio_router import embed as embed_module
from sobrio_router.embed import (
    _DIM,
    _E5_PREFIX,
    _MAX_CHARS,
    EMBED_SPEC_VERSION,
    EmbedHead,
    EmbedLoadError,
    EmbedRefusal,
    EmbedRouter,
    expected_embed_spec,
)
from sobrio_router.ml import LABEL_ORDER

_SOUPE = "des les aux par sur dans avec pour sans sous vers chez donc or ni car"
_SENTINELLE = "SECRET_LEAK_TEST_R6_LOT3_e7a1"


def _signals_avec_texte(texte: str | None) -> Signals:
    """Bundle de signaux neutres portant (ou non) un texte — via `replace`."""
    base = make_signals()
    return replace(base, prompt=replace(base.prompt, prompt_text=texte))


# ---------------------------------------------------------------------------
# Fabrique d'artefacts de tête valides (miroir §6.3) — sha COHÉRENTS calculés
# sur les octets réellement écrits (aucune réparation nécessaire ensuite).
# ---------------------------------------------------------------------------


def _w_selecteur() -> list[list[float]]:
    """W « sélecteur » : la ligne i lit la coordonnée i — logits pilotables."""
    return [[1.0 if j == i else 0.0 for j in range(_DIM)] for i in range(3)]


def _ecrire_tete(
    directory: Path,
    *,
    w: list | None = None,
    b: list | None = None,
    calibrator: object = None,
    confidence_cap: object = 0.74,
    metadata_extra: dict | None = None,
    supprimer_metadata: tuple[str, ...] = (),
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    head = {"w": w if w is not None else _w_selecteur(), "b": b if b is not None else [0.0] * 3}
    head_octets = json.dumps(head).encode("utf-8")
    (directory / "head.json").write_bytes(head_octets)
    calib = calibrator if calibrator is not None else {"x": [0.0, 1.0], "y": [0.0, 1.0]}
    calib_octets = json.dumps(calib).encode("utf-8")
    (directory / "calibrator.json").write_bytes(calib_octets)
    metadata: dict = {
        "artefact": "embed_head_v0",
        "date_train": "2026-07-23",
        "seed": 4242,
        "git_sha": "0" * 12,
        "train_source": "synthetic_embed_fixtures",
        "train_seed": 20260723,
        "eval_seed": 20260724,
        "label_mapping": {label: index for index, label in enumerate(LABEL_ORDER)},
        "embed_spec": expected_embed_spec(),
        "calibration": {"method": "isotonic_top_conservative", "n_points": 2},
        "confidence_cap": confidence_cap,
        "sha256_head_json": hashlib.sha256(head_octets).hexdigest(),
        "sha256_calibrator_json": hashlib.sha256(calib_octets).hexdigest(),
        "head_reelle_attend_telemetrie_v1": True,
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    for cle in supprimer_metadata:
        metadata.pop(cle, None)
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return directory


def _muter_metadata(directory: Path, **changements: object) -> None:
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(changements)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _remplacer_head_json(directory: Path, contenu: object) -> None:
    """Réécrit head.json ET répare son sha : atteint la VALIDATION de
    structure, pas la garde d'intégrité en amont (patron test_router_ml)."""
    octets = json.dumps(contenu).encode("utf-8")
    (directory / "head.json").write_bytes(octets)
    _muter_metadata(directory, sha256_head_json=hashlib.sha256(octets).hexdigest())


def _routeur_service(tete: object, embedding: list[float] | None = None) -> EmbedRouter:
    """Chemin SERVICE sans dépendances : instance sans __init__, encodeur
    monkeypatché restituant l'embedding (patron §10.4 — iso-confiance)."""
    routeur = EmbedRouter.__new__(EmbedRouter)
    routeur._head = tete
    if embedding is not None:
        routeur._embed = lambda prefixe: list(embedding)
    return routeur


def test_sobrio_embed_artifacts_dir_charge_encodeur_et_tete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """La racine surchargée est lue à la construction pour l'encodeur et la tête."""
    racine = tmp_path / "artefacts-embed"
    encodeur = racine / "encoder"
    encodeur.mkdir(parents=True)
    model_octets = b"modele-factice"
    tokenizer_octets = b"{}"
    (encodeur / "model.onnx").write_bytes(model_octets)
    (encodeur / "tokenizer.json").write_bytes(tokenizer_octets)
    monkeypatch.setattr(embed_module, "_ENCODER_SHA256", hashlib.sha256(model_octets).hexdigest())
    monkeypatch.setattr(
        embed_module,
        "_TOKENIZER_SHA256",
        hashlib.sha256(tokenizer_octets).hexdigest(),
    )
    _ecrire_tete(racine / "heads" / "promoted")

    chemins_charges: dict[str, str] = {}

    class _OptionsFactices:
        intra_op_num_threads = 0
        inter_op_num_threads = 0

    class _SessionFactice:
        def __init__(self, path, *, sess_options, providers):
            chemins_charges["modele"] = path

        def get_inputs(self):
            return []

    class _TokeniseurFactice:
        def enable_truncation(self, *, max_length):
            self.max_length = max_length

    class _FabriqueTokeniseur:
        @staticmethod
        def from_file(path):
            chemins_charges["tokenizer"] = path
            return _TokeniseurFactice()

    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        SimpleNamespace(SessionOptions=_OptionsFactices, InferenceSession=_SessionFactice),
    )
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=_FabriqueTokeniseur))
    monkeypatch.setenv("SOBRIO_EMBED_ARTIFACTS_DIR", str(racine))

    routeur = EmbedRouter()
    assert chemins_charges == {
        "modele": str(encodeur / "model.onnx"),
        "tokenizer": str(encodeur / "tokenizer.json"),
    }
    assert routeur._head.predict([5.0] + [0.0] * (_DIM - 1)) == (
        "claude-haiku-4-5",
        0.74,
    )


# ---------------------------------------------------------------------------
# Pin littéral INTÉGRAL (patron QA-R5-m1, spec §6.1/§10.4) — stdlib, toujours
# exécuté : muter n'importe quelle valeur du constructeur fait échouer.
# ---------------------------------------------------------------------------


def test_embed_spec_pin_litteral_integral():
    """Le embed_spec v1 INTÉGRAL, pinné en littéral dur dès sa création.

    - `encoder_sha256`/`tokenizer_sha256` = None : RECADRAGE ledger
      2026-07-23 — le premier fetch du modèle est un GESTE FONDATEUR qui n'a
      pas eu lieu ; le manifest est à sources null et AUCUN encodeur n'est
      approuvé (fail-closed prouvé plus bas). Le geste fondateur renseignera
      manifest + littéraux + CE pin dans le même mouvement.
    - `max_tokens` = 256 : valeur CANDIDATE NON MESURÉE (même recadrage — le
      spike de latence de fin de Lot 2 est différé au geste fondateur) ;
      confirmée ou abaissée (192/128) alors, via bump EMBED_SPEC_VERSION.
    Un bump volontaire du spec ÉDITE ce littéral en même temps que le
    constructeur — c'est le prix, voulu, du pin (patron QA-R5-m1).
    """
    assert expected_embed_spec() == {
        "encoder": "multilingual-e5-small",
        "onnx_variant": "int8",
        "encoder_sha256": None,
        "tokenizer_sha256": None,
        "dim": 384,
        "pooling": "mean_masked",
        "normalize": "l2",
        "prefix": "query: ",
        "max_tokens": 256,
        "labels": ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"],
        "version": "1",
    }
    assert EMBED_SPEC_VERSION == "1"


def test_embed_spec_retourne_un_dict_neuf_a_chaque_appel():
    """Constructeur, pas constante partagée : muter un retour n'altère pas
    le suivant (sinon un consommateur pourrait corrompre la garde de dérive)."""
    premier = expected_embed_spec()
    assert premier is not expected_embed_spec()
    premier["dim"] = 999
    assert expected_embed_spec()["dim"] == 384


# ---------------------------------------------------------------------------
# Chargement nominal + contrat de predict.
# ---------------------------------------------------------------------------


def test_chargement_tete_valide_et_contrat_predict(tmp_path: Path):
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    label, conf = tete.predict([5.0] + [0.0] * (_DIM - 1))
    assert label == "claude-haiku-4-5"
    # brut ≈ 0.987 → iso identité → clamp → plafond 0.74 : cap EXACT émis.
    assert conf == 0.74


def test_confidence_cap_borne_074_passe_075_clampe(tmp_path: Path):
    """Cas à la borne (§10.3/§10.4) : 0.74 est émissible EXACTEMENT ; un brut
    au-dessus (≈0.75+) est clampé à 0.74 — jamais d'auto-bascule RFC-0003."""
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    # logits [2, 0, 0] → brut ≈ 0.787 > 0.74 → clampé exactement au cap.
    _, conf_clampee = tete.predict([2.0] + [0.0] * (_DIM - 1))
    assert math.exp(2.0) / (math.exp(2.0) + 2.0) > 0.74
    assert conf_clampee == 0.74
    # logits [1.0, 0, 0] → brut ≈ 0.576 < 0.74 → passe SOUS le cap, intact.
    _, conf_libre = tete.predict([1.0] + [0.0] * (_DIM - 1))
    assert conf_libre == pytest.approx(math.exp(1.0) / (math.exp(1.0) + 2.0))
    assert conf_libre < 0.74


def test_chaine_maillon_2_min_brut_iso(tmp_path: Path):
    """Maillon 2 : calibrateur compressif → conf == iso(brut) < brut ;
    calibrateur au-dessus du brut → conf == brut (le min protège toujours)."""
    brut = math.exp(1.0) / (math.exp(1.0) + 2.0)  # ≈ 0.576, sous le cap
    e = [1.0] + [0.0] * (_DIM - 1)
    compressif = _ecrire_tete(
        tmp_path / "compressif", calibrator={"x": [0.0, 1.0], "y": [0.0, 0.5]}
    )
    _, conf = EmbedHead.load(compressif).predict(e)
    assert conf == pytest.approx(0.5 * brut)
    assert conf < brut
    optimiste = _ecrire_tete(tmp_path / "optimiste", calibrator={"x": [0.0, 1.0], "y": [1.0, 1.0]})
    _, conf = EmbedHead.load(optimiste).predict(e)
    assert conf == pytest.approx(brut)  # min(brut, 1.0) = brut


def test_toutes_les_confiances_emises_sont_bornees_par_le_cap(tmp_path: Path):
    """Sur un panel seedé de 40 embeddings : 0 ≤ conf ≤ confidence_cap et
    conf ≤ brut (propriété conservatrice §5.2bis), labels dans LABEL_ORDER."""
    rng = random.Random(20260723)
    w = [[rng.gauss(0.0, 1.0) for _ in range(_DIM)] for _ in range(3)]
    directory = _ecrire_tete(tmp_path / "tete", w=w, b=[0.1, -0.2, 0.05])
    tete = EmbedHead.load(directory)
    for _ in range(40):
        e = [rng.gauss(0.0, 1.0) for _ in range(_DIM)]
        norme = math.sqrt(sum(x * x for x in e)) or 1.0
        e = [x / norme for x in e]
        label, conf = tete.predict(e)
        assert label in LABEL_ORDER
        assert 0.0 <= conf <= 0.74


# ---------------------------------------------------------------------------
# Iso-confiance harnais/service (§10.4, correction MAJOR-1) : même embedding
# → confiance BIT-IDENTIQUE via `EmbedHead.predict` (chemin harnais §9.1) et
# via `EmbedRouter.decide` (chemin service, encodeur monkeypatché).
# ---------------------------------------------------------------------------


def test_iso_confiance_harnais_service_bit_identique(tmp_path: Path):
    rng = random.Random(20260724)
    w = [[rng.gauss(0.0, 1.5) for _ in range(_DIM)] for _ in range(3)]
    directory = _ecrire_tete(
        tmp_path / "tete",
        w=w,
        b=[0.3, 0.0, -0.3],
        calibrator={"x": [0.0, 0.5, 1.0], "y": [0.0, 0.42, 0.9]},
        confidence_cap=0.74,
    )
    tete = EmbedHead.load(directory)
    for _ in range(25):
        e = [rng.gauss(0.0, 1.0) for _ in range(_DIM)]
        norme = math.sqrt(sum(x * x for x in e)) or 1.0
        e = [x / norme for x in e]
        label_harnais, conf_harnais = tete.predict(e)  # chemin HARNAIS §9.1
        decision = _routeur_service(tete, e).decide(_signals_avec_texte(_SOUPE))
        assert decision.confidence == conf_harnais  # BIT-identique, pas approx
        assert decision.model == label_harnais
        assert decision.rule == "embed:v0"


def test_decide_un_seul_appel_predict_ne_recalcule_rien():
    """Mutation-killer MAJOR-1 : `decide` émet EXACTEMENT la sortie de
    `predict` (un re-plafonnage, une re-calibration ou un second appel dans
    `decide` ferait diverger valeur ou compteur). La confiance espionne
    (0.618…) est volontairement au-dessus d'aucun cap : si `decide`
    plafonnait/clampait de son côté, la valeur émise changerait."""

    class _TeteEspionne:
        def __init__(self) -> None:
            self.appels = 0

        def predict(self, embedding):
            self.appels += 1
            return ("claude-opus-4-8", 0.6180339887498949)

    espionne = _TeteEspionne()
    routeur = _routeur_service(espionne, [0.0] * _DIM)
    decision = routeur.decide(_signals_avec_texte(_SOUPE))
    assert espionne.appels == 1
    assert decision.model == "claude-opus-4-8"
    assert decision.confidence == 0.6180339887498949
    assert decision.rule == "embed:v0"


def test_decide_prefixe_e5_et_troncature_4000(tmp_path: Path):
    """§5.2.2/§5.2.3 (D11/D12) : l'encodeur reçoit `query: ` + texte tronqué
    à 4000 caractères — jamais plus, préfixe toujours présent."""
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    recu: dict[str, str] = {}
    routeur = EmbedRouter.__new__(EmbedRouter)
    routeur._head = tete

    def _embed_espion(prefixe: str) -> list[float]:
        recu["texte"] = prefixe
        return [1.0] + [0.0] * (_DIM - 1)

    routeur._embed = _embed_espion
    soupe_longue = (_SOUPE + " ") * 400  # > 4000 caractères de mots-vides
    assert len(soupe_longue) > _MAX_CHARS
    decision = routeur.decide(_signals_avec_texte(soupe_longue))
    assert recu["texte"] == _E5_PREFIX + soupe_longue[:_MAX_CHARS]
    assert len(recu["texte"]) == len(_E5_PREFIX) + _MAX_CHARS
    assert decision.rule == "embed:v0"


# ---------------------------------------------------------------------------
# Refus sans texte (§5.2.1) — défense en profondeur.
# ---------------------------------------------------------------------------


def test_decide_sans_texte_leve_embed_refusal_message_fixe():
    routeur = EmbedRouter.__new__(EmbedRouter)  # aucun attribut requis avant le verrou
    with pytest.raises(EmbedRefusal) as excinfo:
        routeur.decide(_signals_avec_texte(None))
    assert str(excinfo.value) == "prompt_text absent — étage 2 opt-in non satisfait"
    assert issubclass(EmbedRefusal, ValueError)


# ---------------------------------------------------------------------------
# Dérive du embed_spec, clé par clé (§10.4) — CHAQUE clé du spec, y compris
# version et sha encodeur ; l'assert d'exhaustivité verrouille le paramétrage
# sur le spec COURANT (une clé ajoutée demain sans cas de dérive = échec).
# ---------------------------------------------------------------------------

_DERIVES_EMBED_SPEC: dict[str, object] = {
    "encoder": "autre-encodeur",
    "onnx_variant": "fp32",
    "encoder_sha256": "0" * 64,
    "tokenizer_sha256": "1" * 64,
    "dim": 512,
    "pooling": "cls",
    "normalize": "aucune",
    "prefix": "passage: ",
    "max_tokens": 128,
    "labels": list(reversed(LABEL_ORDER)),
    "version": "2",
}


def test_derives_couvrent_chaque_cle_du_spec():
    assert set(_DERIVES_EMBED_SPEC) == set(expected_embed_spec())
    for cle, valeur in _DERIVES_EMBED_SPEC.items():
        assert expected_embed_spec()[cle] != valeur, cle


@pytest.mark.parametrize("cle", sorted(_DERIVES_EMBED_SPEC), ids=str)
def test_embed_spec_mute_cle_par_cle_fail_closed(tmp_path: Path, cle: str):
    directory = _ecrire_tete(tmp_path / cle)
    spec = expected_embed_spec()
    spec[cle] = _DERIVES_EMBED_SPEC[cle]
    _muter_metadata(directory, embed_spec=spec)
    with pytest.raises(EmbedLoadError, match="embed_spec"):
        EmbedHead.load(directory)


@pytest.mark.parametrize(
    "cas, spec_mutant",
    [
        ("cle_supprimee", {c: v for c, v in expected_embed_spec().items() if c != "pooling"}),
        ("cle_en_trop", {**expected_embed_spec(), "intruse": 1}),
        ("spec_non_objet", ["multilingual-e5-small"]),
        ("spec_absent", None),
    ],
    ids=str,
)
def test_embed_spec_structure_deviante_fail_closed(tmp_path: Path, cas: str, spec_mutant: object):
    directory = _ecrire_tete(tmp_path / cas)
    if cas == "spec_absent":
        metadata_path = directory / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        del metadata["embed_spec"]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        _muter_metadata(directory, embed_spec=spec_mutant)
    with pytest.raises(EmbedLoadError, match="embed_spec"):
        EmbedHead.load(directory)


# ---------------------------------------------------------------------------
# Autres gardes fail-closed : label_mapping, intégrité, fichiers, JSON,
# structure de head.json, calibrateur (réutilisation `_validate_calibrator`).
# ---------------------------------------------------------------------------


def test_label_mapping_deviant_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "mapping")
    _muter_metadata(
        directory,
        label_mapping={"claude-haiku-4-5": 2, "claude-sonnet-5": 1, "claude-opus-4-8": 0},
    )
    with pytest.raises(EmbedLoadError, match="label_mapping"):
        EmbedHead.load(directory)


@pytest.mark.parametrize("cle", ["sha256_head_json", "sha256_calibrator_json"], ids=str)
def test_sha_divergent_fail_closed(tmp_path: Path, cle: str):
    directory = _ecrire_tete(tmp_path / cle)
    _muter_metadata(directory, **{cle: "0" * 64})
    with pytest.raises(EmbedLoadError, match="integrite"):
        EmbedHead.load(directory)


def test_head_json_altere_sans_reparer_le_sha_fail_closed(tmp_path: Path):
    """La garde d'INTÉGRITÉ voit toute altération d'octets AVANT le parseur."""
    directory = _ecrire_tete(tmp_path / "octets")
    head = json.loads((directory / "head.json").read_text(encoding="utf-8"))
    head["b"][0] = 9.9
    (directory / "head.json").write_text(json.dumps(head), encoding="utf-8")
    with pytest.raises(EmbedLoadError, match="integrite"):
        EmbedHead.load(directory)


@pytest.mark.parametrize("manquant", ["head.json", "calibrator.json", "metadata.json"], ids=str)
def test_fichier_manquant_fail_closed(tmp_path: Path, manquant: str):
    directory = _ecrire_tete(tmp_path / manquant.replace(".", "-"))
    (directory / manquant).unlink()
    with pytest.raises(EmbedLoadError, match="absent") as excinfo:
        EmbedHead.load(directory)
    assert manquant in str(excinfo.value)


def test_metadata_json_corrompu_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "meta-corrompu")
    (directory / "metadata.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(EmbedLoadError, match="illisible"):
        EmbedHead.load(directory)


def test_metadata_non_objet_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "meta-liste")
    (directory / "metadata.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(EmbedLoadError, match="non-objet"):
        EmbedHead.load(directory)


def test_head_json_corrompu_sha_repare_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "head-corrompu")
    octets = b"{pas du json"
    (directory / "head.json").write_bytes(octets)
    _muter_metadata(directory, sha256_head_json=hashlib.sha256(octets).hexdigest())
    with pytest.raises(EmbedLoadError, match="illisible"):
        EmbedHead.load(directory)


_HEADS_MALFORMES: dict[str, object] = {
    "non_objet": [[0.0] * 384] * 3,
    "w_absent": {"b": [0.0] * 3},
    "w_2_lignes": {"w": [[0.0] * 384] * 2, "b": [0.0] * 3},
    "w_ligne_383": {"w": [[0.0] * 383] + [[0.0] * 384] * 2, "b": [0.0] * 3},
    "w_ligne_non_liste": {"w": ["x", [0.0] * 384, [0.0] * 384], "b": [0.0] * 3},
    "b_2_valeurs": {"w": [[0.0] * 384] * 3, "b": [0.0] * 2},
    "valeur_non_finie": {"w": [[0.0] * 384] * 3, "b": [0.0, float("inf"), 0.0]},
    "valeur_bool": {"w": [[0.0] * 384] * 3, "b": [0.0, True, 0.0]},
}


@pytest.mark.parametrize("cas", sorted(_HEADS_MALFORMES), ids=str)
def test_head_json_malforme_fail_closed(tmp_path: Path, cas: str):
    directory = _ecrire_tete(tmp_path / cas)
    _remplacer_head_json(directory, _HEADS_MALFORMES[cas])
    with pytest.raises(EmbedLoadError, match="head.json"):
        EmbedHead.load(directory)


# Réutilisation des cas `_validate_calibrator` (§10.4) — mêmes refus que R5,
# re-typés EmbedLoadError par le chargeur de tête.
_CALIBRATEURS_INVALIDES: dict[str, object] = {
    "non_objet": [0.0, 1.0],
    "x_absent": {"y": [0.0, 1.0]},
    "longueurs_inegales": {"x": [0.0, 0.5, 1.0], "y": [0.0, 1.0]},
    "un_seul_point": {"x": [0.5], "y": [0.5]},
    "valeur_non_finie": {"x": [0.0, float("inf")], "y": [0.0, 1.0]},
    "x_non_croissant": {"x": [0.9, 0.1], "y": [0.1, 0.9]},
    "y_hors_bornes": {"x": [0.0, 1.0], "y": [0.0, 1.5]},
}


@pytest.mark.parametrize("cas", sorted(_CALIBRATEURS_INVALIDES), ids=str)
def test_calibrateur_invalide_fail_closed(tmp_path: Path, cas: str):
    directory = _ecrire_tete(tmp_path / cas, calibrator=_CALIBRATEURS_INVALIDES[cas])
    with pytest.raises(EmbedLoadError, match="calibrator.json"):
        EmbedHead.load(directory)


def test_calibrator_json_corrompu_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "calib-corrompu")
    octets = b"{pas du json"
    (directory / "calibrator.json").write_bytes(octets)
    _muter_metadata(directory, sha256_calibrator_json=hashlib.sha256(octets).hexdigest())
    with pytest.raises(EmbedLoadError, match="illisible"):
        EmbedHead.load(directory)


# ---------------------------------------------------------------------------
# confidence_cap NORMATIF (§6.3) : fail-closed champ par champ.
# ---------------------------------------------------------------------------

_CAPS_INVALIDES: dict[str, object] = {
    "none": None,
    "chaine": "0.74",
    "bool": True,
    "nan": float("nan"),
    "inf": float("inf"),
    "zero": 0.0,
    "negatif": -0.5,
    "sup_1": 1.0000001,
    "deux": 2,
}


@pytest.mark.parametrize("cas", sorted(_CAPS_INVALIDES), ids=str)
def test_confidence_cap_invalide_fail_closed(tmp_path: Path, cas: str):
    directory = _ecrire_tete(tmp_path / cas, confidence_cap=_CAPS_INVALIDES[cas])
    with pytest.raises(EmbedLoadError, match="confidence_cap"):
        EmbedHead.load(directory)


def test_confidence_cap_absent_fail_closed(tmp_path: Path):
    directory = _ecrire_tete(tmp_path / "cap-absent", supprimer_metadata=("confidence_cap",))
    with pytest.raises(EmbedLoadError, match="confidence_cap"):
        EmbedHead.load(directory)


def test_confidence_cap_bornes_valides(tmp_path: Path):
    """]0, 1] : 1.0 inclus (borne), epsilon > 0 inclus — chargent tous deux."""
    tete_un = EmbedHead.load(_ecrire_tete(tmp_path / "cap-1", confidence_cap=1.0))
    _, conf = tete_un.predict([9.0] + [0.0] * (_DIM - 1))
    assert conf <= 1.0
    tete_eps = EmbedHead.load(_ecrire_tete(tmp_path / "cap-eps", confidence_cap=1e-9))
    _, conf = tete_eps.predict([9.0] + [0.0] * (_DIM - 1))
    assert conf == 1e-9  # le plafond domine toute la chaîne


# ---------------------------------------------------------------------------
# predict : refus bruyants (comptes uniquement) — attrapés par TwoStageRouter.
# ---------------------------------------------------------------------------


def test_predict_arite_fausse_valeur_error_compte_seul(tmp_path: Path):
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    with pytest.raises(ValueError) as excinfo:
        tete.predict([0.0] * (_DIM - 1))
    assert re.fullmatch(r"embedding invalide : 383 valeurs != 384", str(excinfo.value))
    with pytest.raises(ValueError):
        tete.predict([])


def test_predict_probas_non_finies_valeur_error(tmp_path: Path):
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    with pytest.raises(ValueError) as excinfo:
        tete.predict([float("inf")] * _DIM)
    assert re.fullmatch(r"probas non finies : 3 valeurs", str(excinfo.value))
    with pytest.raises(ValueError):
        tete.predict([float("nan")] * _DIM)


def test_predict_valeur_non_numerique_message_fixe(tmp_path: Path):
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    for intrus in ("0.5", None, True):
        with pytest.raises(ValueError) as excinfo:
            tete.predict([intrus] + [0.0] * (_DIM - 1))
        assert str(excinfo.value) == "embedding invalide : valeur non numerique"


# ---------------------------------------------------------------------------
# EmbedRouter : constructeur fail-closed (sans modèle / sans dépendances) —
# TOUJOURS EmbedLoadError, jamais un traceback d'un autre type, que les
# dépendances embed soient installées ou non (recadrage : sha None ⇒ tout
# encodeur local est refusé même présent).
# ---------------------------------------------------------------------------


def test_embed_router_sans_encodeur_echoue_proprement(tmp_path: Path):
    _ecrire_tete(tmp_path / "tete")
    with pytest.raises(EmbedLoadError):
        EmbedRouter(encoder_dir=tmp_path / "encodeur-absent", head_dir=tmp_path / "tete")


def test_embed_router_refuse_tout_encodeur_local_avant_geste_fondateur(tmp_path: Path):
    """RECADRAGE 2026-07-23 : même avec des fichiers encodeur PRÉSENTS, les
    littéraux sha à None refusent le chargement (source non approuvée) —
    deps absentes aujourd'hui : refus dès l'import paresseux ; deps
    présentes demain : refus à l'intégrité. Les DEUX branches sont
    EmbedLoadError."""
    encodeur = tmp_path / "encodeur"
    encodeur.mkdir()
    (encodeur / "model.onnx").write_bytes(b"octets factices")
    (encodeur / "tokenizer.json").write_text("{}", encoding="utf-8")
    _ecrire_tete(tmp_path / "tete")
    with pytest.raises(EmbedLoadError):
        EmbedRouter(encoder_dir=encodeur, head_dir=tmp_path / "tete")


@pytest.mark.parametrize("manquant", ["model.onnx", "tokenizer.json"], ids=str)
def test_fichier_encodeur_manquant_fail_closed(tmp_path: Path, manquant: str):
    """§10.4 « fichier manquant, paramétré sur les 5 » — volet encodeur (2/5).

    La branche présence (§5.1.2) n'est atteignable qu'APRÈS les imports
    paresseux : skip tant que les deps embed ne sont pas installées
    (recadrage 2026-07-23 — elles arrivent avec le geste fondateur)."""
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    pytest.importorskip("numpy")
    encodeur = tmp_path / "encodeur"
    encodeur.mkdir()
    for nom in ("model.onnx", "tokenizer.json"):
        if nom != manquant:
            (encodeur / nom).write_bytes(b"octets factices")
    _ecrire_tete(tmp_path / "tete")
    with pytest.raises(EmbedLoadError, match="absent") as excinfo:
        EmbedRouter(encoder_dir=encodeur, head_dir=tmp_path / "tete")
    assert manquant in str(excinfo.value)


def test_integrite_encodeur_sha_divergent_fail_closed(tmp_path: Path):
    """§10.4 sha encodeur/tokenizer divergents : la branche intégrité §5.1.3
    refuse (littéraux None aujourd'hui ⇒ TOUT octet diverge). Skip sans deps
    embed — la variante sans-deps est couverte par le test « refuse tout
    encodeur local » ci-dessus."""
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    pytest.importorskip("numpy")
    encodeur = tmp_path / "encodeur"
    encodeur.mkdir()
    (encodeur / "model.onnx").write_bytes(b"octets factices")
    (encodeur / "tokenizer.json").write_text("{}", encoding="utf-8")
    _ecrire_tete(tmp_path / "tete")
    with pytest.raises(EmbedLoadError, match="integrite"):
        EmbedRouter(encoder_dir=encodeur, head_dir=tmp_path / "tete")


# ---------------------------------------------------------------------------
# Segment NORMATIF encode→poole→normalise (§5.2.4-6) — QA-R6-M1 (ronde 0) :
# `_embed` exécuté RÉELLEMENT à session/tokenizer FACTICES (instance via
# `EmbedRouter.__new__` + attributs `_np`/`_tokenizer`/`_session`/
# `_noms_entrees` injectés — numpy seul requis, exécutable dès aujourd'hui
# comme en local post-geste). Les valeurs attendues sont calculées À LA MAIN
# dans chaque test : un mutant « masque ignoré » ou « L2 supprimée » échoue
# sur des nombres exacts.
# ---------------------------------------------------------------------------


class _EncodageFactice:
    """Sortie minimale d'un tokenizer HF : `ids` + `attention_mask`."""

    def __init__(self, ids: list[int], attention_mask: list[int]) -> None:
        self.ids = ids
        self.attention_mask = attention_mask


class _TokenizerFactice:
    def __init__(self, encodage: _EncodageFactice) -> None:
        self._encodage = encodage

    def encode(self, texte: str) -> _EncodageFactice:
        return self._encodage


class _SessionFactice:
    """Restitue un hidden_state ARTISANAL et enregistre les entrées reçues."""

    def __init__(self, hidden: object) -> None:
        self._hidden = hidden
        self.entrees_recues: dict | None = None

    def run(self, sorties: object, entrees: dict) -> list[object]:
        self.entrees_recues = entrees
        return [self._hidden]


def _routeur_embed_factice(
    hidden: list, ids: list[int], masque: list[int], noms_entrees: set[str]
) -> tuple[EmbedRouter, _SessionFactice]:
    numpy = pytest.importorskip("numpy")
    routeur = EmbedRouter.__new__(EmbedRouter)
    routeur._np = numpy
    routeur._tokenizer = _TokenizerFactice(_EncodageFactice(ids, masque))
    session = _SessionFactice(numpy.asarray(hidden, dtype=numpy.float32))
    routeur._session = session
    routeur._noms_entrees = noms_entrees
    return routeur, session


def test_embed_mean_pooling_masque_ignore_le_padding():
    """§5.2.6 NORMATIF : les positions de PADDING (masque 0) ne pèsent PAS
    dans la moyenne. À la main : positions actives h0 = 3·e0 et h1 = 4·e1,
    position de padding h2 = 100 PARTOUT (empoisonnée) ; moyenne masquée =
    (h0 + h1) / 2 = [1.5, 2.0, 0, …], norme = √(1.5² + 2²) = 2.5, embedding
    = [0.6, 0.8, 0, …]. Un mutant « masque retiré » embarquerait les 100 du
    padding sur TOUTES les coordonnées (aucune ne resterait nulle)."""
    h0 = [0.0] * _DIM
    h0[0] = 3.0
    h1 = [0.0] * _DIM
    h1[1] = 4.0
    h2 = [100.0] * _DIM  # padding empoisonné : détecte tout maillon muté
    routeur, session = _routeur_embed_factice(
        [[h0, h1, h2]],
        ids=[5, 7, 0],
        masque=[1, 1, 0],
        noms_entrees={"input_ids", "attention_mask"},
    )
    embedding = routeur._embed(_SOUPE)
    assert len(embedding) == _DIM
    assert embedding[0] == pytest.approx(0.6)  # 1.5 / 2.5 — calcul à la main
    assert embedding[1] == pytest.approx(0.8)  # 2.0 / 2.5 — calcul à la main
    assert all(v == 0.0 for v in embedding[2:])  # le padding n'a PAS fui
    assert sum(v * v for v in embedding) == pytest.approx(1.0)  # norme L2 == 1
    # La session a reçu les tenseurs attendus (batch 1, int64, pas de
    # token_type_ids quand l'export ne les exige pas).
    entrees = session.entrees_recues
    assert set(entrees) == {"input_ids", "attention_mask"}
    assert entrees["input_ids"].tolist() == [[5, 7, 0]]
    assert entrees["attention_mask"].tolist() == [[1, 1, 0]]
    # ML-R6r1-m2 : dtype NORMATIF (§5.2.4) asserté — un export ONNX réel
    # refuse int32 ; le test doit l'attraper avant le runtime.
    assert str(entrees["input_ids"].dtype) == "int64"
    assert str(entrees["attention_mask"].dtype) == "int64"


def test_embed_normalisation_l2_norme_1_valeurs_a_la_main():
    """§5.2.6 : normalisation L2 finale. À la main : h0 = [1, 2, 2, 0, …] et
    h1 = [3, 0, 2, 0, …] actifs tous deux ; moyenne = [2, 1, 2, 0, …],
    norme = √(4 + 1 + 4) = 3 ; embedding = [2/3, 1/3, 2/3, 0, …]. Un mutant
    « L2 supprimée » émettrait [2, 1, 2, …] (norme 3 ≠ 1)."""
    h0 = [0.0] * _DIM
    h0[0], h0[1], h0[2] = 1.0, 2.0, 2.0
    h1 = [0.0] * _DIM
    h1[0], h1[2] = 3.0, 2.0
    routeur, _ = _routeur_embed_factice(
        [[h0, h1]],
        ids=[5, 7],
        masque=[1, 1],
        noms_entrees={"input_ids", "attention_mask"},
    )
    embedding = routeur._embed(_SOUPE)
    assert embedding[0] == pytest.approx(2.0 / 3.0)
    assert embedding[1] == pytest.approx(1.0 / 3.0)
    assert embedding[2] == pytest.approx(2.0 / 3.0)
    assert all(v == 0.0 for v in embedding[3:])
    assert sum(v * v for v in embedding) == pytest.approx(1.0)


def test_embed_masque_tout_zero_comportement_defini_sans_division_par_zero():
    """Cas DÉGÉNÉRÉ : masque tout-zéro (aucune position active). Comportement
    défini : somme masquée nulle, dénominateur `max(compte, 1.0)` = 1 (pas de
    0/0), norme 0 ⇒ la normalisation est SAUTÉE — embedding [0.0] * 384,
    aucune division par zéro, aucun NaN/inf."""
    hidden = [[[7.0] * _DIM, [-3.0] * _DIM]]
    routeur, _ = _routeur_embed_factice(
        hidden, ids=[0, 0], masque=[0, 0], noms_entrees={"input_ids", "attention_mask"}
    )
    embedding = routeur._embed(_SOUPE)
    assert embedding == [0.0] * _DIM
    assert all(math.isfinite(v) for v in embedding)


def test_embed_branche_token_type_ids_zeros_si_exiges():
    """§5.2.5 : si l'export exige `token_type_ids`, `_embed` fournit des
    ZÉROS de la forme (et du dtype) d'input_ids — XLM-R n'utilise pas de
    segments. À la main : une seule position active de valeur 5 sur e0 ⇒
    moyenne = 5·e0, norme 5, embedding = e0 exactement."""
    h0 = [0.0] * _DIM
    h0[0] = 5.0
    routeur, session = _routeur_embed_factice(
        [[h0]],
        ids=[9],
        masque=[1],
        noms_entrees={"input_ids", "attention_mask", "token_type_ids"},
    )
    embedding = routeur._embed(_SOUPE)
    entrees = session.entrees_recues
    assert set(entrees) == {"input_ids", "attention_mask", "token_type_ids"}
    assert entrees["token_type_ids"].tolist() == [[0]]
    assert entrees["token_type_ids"].dtype == entrees["input_ids"].dtype
    assert embedding[0] == pytest.approx(1.0)
    assert all(v == 0.0 for v in embedding[1:])


# ---------------------------------------------------------------------------
# Privacy (§10.1, périmètre Lot 3) : aucun texte dans les exceptions ni les
# logs du nouveau code — site par site sur le chemin decide.
# ---------------------------------------------------------------------------


def test_exception_de_predict_via_decide_sans_le_texte(tmp_path: Path, caplog, capsys):
    """Sentinelle en prompt_text, tête qui refuse (mauvaise arité restituée
    par l'encodeur espion) : l'exception remonte SANS le texte, rien n'est
    loggé ni imprimé."""
    caplog.set_level(logging.DEBUG)
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    routeur = _routeur_service(tete, [0.0] * (_DIM - 1))  # arité fausse
    with pytest.raises(ValueError) as excinfo:
        routeur.decide(_signals_avec_texte(_SENTINELLE))
    assert _SENTINELLE not in str(excinfo.value)
    assert _SENTINELLE not in repr(excinfo.value)
    assert _SENTINELLE not in caplog.text
    sortie = capsys.readouterr()
    assert _SENTINELLE not in sortie.out + sortie.err


def test_messages_de_chargement_sans_recopie_de_contenu(tmp_path: Path):
    """Les messages des sites de raise du chargement sont composés de
    chemins/hash/comptes : un metadata déviant PORTEUR d'une sentinelle
    (spec trafiqué, cap trafiqué) n'est jamais recopié dans l'exception."""
    directory = _ecrire_tete(tmp_path / "spec-deviant")
    _muter_metadata(directory, embed_spec={"version": _SENTINELLE})
    with pytest.raises(EmbedLoadError) as excinfo:
        EmbedHead.load(directory)
    # Le message de dérive ne recopie PAS le spec déviant (chemin seul).
    assert _SENTINELLE not in str(excinfo.value)
    directory = _ecrire_tete(tmp_path / "cap-deviant", confidence_cap=_SENTINELLE)
    with pytest.raises(EmbedLoadError) as excinfo:
        EmbedHead.load(directory)
    assert _SENTINELLE not in str(excinfo.value)


def test_decide_nominal_ne_logge_ni_n_imprime_rien(tmp_path: Path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    tete = EmbedHead.load(_ecrire_tete(tmp_path / "tete"))
    routeur = _routeur_service(tete, [1.0] + [0.0] * (_DIM - 1))
    decision = routeur.decide(_signals_avec_texte(_SENTINELLE))
    assert decision.rule == "embed:v0"
    assert _SENTINELLE not in caplog.text
    sortie = capsys.readouterr()
    assert _SENTINELLE not in sortie.out + sortie.err
    assert _SENTINELLE not in repr(decision)
