"""Étage 2 — cœur embeddings : `EmbedHead` + `EmbedRouter` (spec R6 §5, §6).

`EmbedHead` est STDLIB PURE (tête linéaire 3×384 + biais, produits scalaires
en boucles Python) et porte la chaîne de confiance COMPLÈTE §5.2bis —
softmax → min(brut, iso) → clamp [0, 1] → min(·, confidence_cap) — définie
UNE SEULE fois : `predict()` est la SEULE porte de sortie d'une confiance de
tête, consommée À L'IDENTIQUE par `EmbedRouter.decide` (service) et par le
harnais embed (§9.1) — leçon ML-R4-m2/DQ-R4-m2 appliquée à la confiance
elle-même (correction MAJOR-1, 2026-07-23). La calibration réutilise
`_validate_calibrator`/`interp_conf` de `ml.py` (mêmes bornes, même
interpolation — zéro réimplémentation).

`EmbedRouter` encode le texte (e5 ONNX) puis délègue à `EmbedHead.predict`.
onnxruntime/tokenizers/numpy sont importés PARESSEUSEMENT dans `__init__`
UNIQUEMENT (§1.3, jamais au niveau module, jamais dans `EmbedHead`) :
`from sobrio_router.embed import EmbedRouter` réussit sans aucune dépendance
embed installée ; seule la CONSTRUCTION échoue (`EmbedLoadError`), exactement
là où le bridge la guette. TOUJOURS derrière `TwoStageRouter` puis
`SafeRouter` en production (invariant §5.2).

RECADRAGE (ledger, décision 2026-07-23 — premier fetch = GESTE FONDATEUR) :
aucune source d'encodeur n'est approuvée à ce jour — les littéraux sha
ci-dessous valent `None` (miroir du manifest à sources null) et TOUT
chargement d'encodeur local échoue fail-closed en `EmbedLoadError` propre
(jamais un traceback nu). Le geste fondateur renseignera manifest et
littéraux dans le même commit.

Texte EN MÉMOIRE SEULEMENT (règle n°1) : jamais stocké, loggé, sérialisé ni
inclus dans un message d'exception — les messages de ce module sont composés
de chemins, de hash et de comptes UNIQUEMENT.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Sequence
from pathlib import Path

from .interface import Router
from .ml import LABEL_ORDER, MLRouterLoadError, _validate_calibrator, interp_conf
from .types import Decision, Signals

EMBED_SPEC_VERSION: str = "1"

_DIM = 384
_N_LABELS = len(LABEL_ORDER)  # 3

# Littéraux NORMATIFS des sha de l'encodeur (§6.1 : = manifest int8).
# RECADRAGE 2026-07-23 : geste fondateur non advenu, manifest à sources null
# => None. L'intégrité §5.1.3 (sha octets == spec) échoue alors sur TOUT
# fichier local : l'encodeur réel est inexécutable tant que le fondateur n'a
# pas approuvé la source (fail-closed, EmbedLoadError).
_ENCODER_SHA256: str | None = None
_TOKENIZER_SHA256: str | None = None

# Chemins d'artefacts PAR DÉFAUT (§4.2, §6.3) — gitignorés via
# router/artifacts/*. Valides en installation éditable (venv racine).
EMBED_ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "embed"
ENCODER_DIR = EMBED_ARTIFACTS_DIR / "encoder"
HEADS_DIR = EMBED_ARTIFACTS_DIR / "heads"
CANDIDATE_HEAD_DIR = HEADS_DIR / "candidate"
PROMOTED_HEAD_DIR = HEADS_DIR / "promoted"
PREVIOUS_HEAD_DIR = HEADS_DIR / "previous"

_EMBED_ARTIFACTS_DIR_ENV = "SOBRIO_EMBED_ARTIFACTS_DIR"
_HEAD_FILES = ("head.json", "calibrator.json", "metadata.json")
_ENCODER_FILES = ("model.onnx", "tokenizer.json")

_MAX_CHARS = 4000  # D11 : borne mémoire/CPU AVANT tokenisation (§5.2.2)
_E5_PREFIX = "query: "  # convention d'entraînement e5 (§5.2.3)


class EmbedLoadError(RuntimeError):
    """Échec de chargement d'un artefact étage 2 (manquant, corrompu, dérivé)."""


class EmbedRefusal(ValueError):
    """Refus de l'étage 2 : opt-in texte non satisfait (défense en profondeur §5.2.1)."""


def expected_embed_spec() -> dict[str, object]:
    """Constructeur UNIQUE du spec d'embedding (§6.1, patron feature_spec R5).

    Consommé par les DEUX côtés du contrat : écrit par le train dans
    `metadata.json` (Lot 5) et exigé À L'IDENTIQUE par `EmbedHead.load`
    (égalité de dict stricte — clé absente, valeur modifiée, clé en trop,
    non-dict : TOUT écart refuse l'artefact). Pinné en littéral intégral dans
    un test stdlib toujours exécuté (patron QA-R5-m1). Changer encodeur,
    variante, pooling ou max_tokens ⇒ bump `EMBED_SPEC_VERSION` ⇒ tout
    artefact de tête antérieur est REFUSÉ au chargement.
    """
    return {
        "encoder": "multilingual-e5-small",
        "onnx_variant": "int8",
        "encoder_sha256": _ENCODER_SHA256,
        "tokenizer_sha256": _TOKENIZER_SHA256,
        "dim": _DIM,
        "pooling": "mean_masked",
        "normalize": "l2",
        "prefix": _E5_PREFIX,
        # 256 = valeur CANDIDATE NON MESURÉE (recadrage ledger 2026-07-23) :
        # le spike de latence de fin de Lot 2 est différé au geste fondateur
        # — aucune mesure réelle possible avant. Confirmée ou abaissée
        # (192/128) à ce moment-là, via bump EMBED_SPEC_VERSION (§6.1/§11).
        "max_tokens": 256,
        "labels": list(LABEL_ORDER),
        "version": EMBED_SPEC_VERSION,
    }


def _est_nombre_fini(valeur: object) -> bool:
    """Nombre réel fini — bool explicitement exclu (True est un int en Python)."""
    return (
        not isinstance(valeur, bool)
        and isinstance(valeur, (int, float))
        and math.isfinite(float(valeur))
    )


def _lire_json(path: Path, nom: str) -> object:
    """Parse un JSON d'artefact ; échec de lecture/parse → `EmbedLoadError`."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmbedLoadError(f"{nom} illisible : {path} ({exc.__class__.__name__})") from exc


def _softmax(logits: list[float]) -> list[float]:
    """Softmax numériquement stable (soustraction du max) — stdlib pure."""
    plafond = max(logits)
    exps = [math.exp(v - plafond) for v in logits]
    total = sum(exps)
    return [v / total for v in exps]


class EmbedHead:
    """Tête linéaire 3×384 + chaîne de confiance COMPLÈTE §5.2bis — stdlib pure.

    Chargée par `EmbedHead.load(head_dir)` : `head.json` (W, b),
    `calibrator.json` (validé par `_validate_calibrator` de ml.py) et
    `confidence_cap` depuis `metadata.json` (NORMATIF fail-closed §6.3 —
    c'est la SEULE source du plafond D3, le code n'en porte aucun littéral).
    """

    def __init__(
        self,
        poids: list[list[float]],
        biais: list[float],
        calib_x: list[float],
        calib_y: list[float],
        confidence_cap: float,
    ) -> None:
        self._poids = poids
        self._biais = biais
        self._calib_x = calib_x
        self._calib_y = calib_y
        self._confidence_cap = confidence_cap

    @classmethod
    def load(cls, head_dir: Path | str) -> EmbedHead:
        """Chargement fail-closed d'un artefact de tête (§5.1.7, patron ml.py).

        Gardes DANS L'ORDRE : présence des trois fichiers → intégrité sha256
        → dérive `embed_spec` (égalité stricte avec `expected_embed_spec()`)
        → dérive `label_mapping` (dérivé de `LABEL_ORDER`, source unique) →
        `confidence_cap` normatif → structure de `head.json` → calibrateur.
        Toute violation → `EmbedLoadError` (chemins/hash/comptes uniquement).
        """
        directory = Path(head_dir)
        for nom in _HEAD_FILES:
            if not (directory / nom).is_file():
                raise EmbedLoadError(f"artefact de tete incomplet : {directory / nom} absent")

        metadata_path = directory / "metadata.json"
        metadata = _lire_json(metadata_path, "metadata.json")
        if not isinstance(metadata, dict):
            raise EmbedLoadError(f"metadata.json non-objet : {metadata_path}")

        # Intégrité AVANT tout chargement (§5.1.3, patron ml.py) : les octets
        # de chaque fichier == sha consignés dans metadata.json.
        for fichier, cle in (
            ("head.json", "sha256_head_json"),
            ("calibrator.json", "sha256_calibrator_json"),
        ):
            attendu = metadata.get(cle)
            reel = hashlib.sha256((directory / fichier).read_bytes()).hexdigest()
            if reel != attendu:
                raise EmbedLoadError(
                    f"integrite : {cle} attendu {str(attendu)[:12]} != octets {reel[:12]} "
                    f"({directory / fichier})"
                )

        # Gardes de dérive artefact/code (§5.1.4) — même patron fail-closed
        # que feature_spec/label_mapping R5 : l'égalité de dict stricte
        # refuse TOUT écart, clé par clé, valeur par valeur.
        if metadata.get("embed_spec") != expected_embed_spec():
            raise EmbedLoadError(f"embed_spec deviant : {metadata_path}")
        mapping_attendu = {label: index for index, label in enumerate(LABEL_ORDER)}
        if metadata.get("label_mapping") != mapping_attendu:
            raise EmbedLoadError(f"label_mapping deviant : {metadata_path}")

        # confidence_cap NORMATIF (§6.3) : absent, non-fini ou hors ]0, 1]
        # → refus. SEULE source du plafond D3 (0.74 en v0) — le retirer en
        # v1 = nouvel artefact, pas un patch de code.
        cap = metadata.get("confidence_cap")
        if not _est_nombre_fini(cap) or not (0.0 < float(cap) <= 1.0):
            raise EmbedLoadError(f"confidence_cap absent ou hors ]0, 1] : {metadata_path}")

        head_path = directory / "head.json"
        head = _lire_json(head_path, "head.json")
        if not isinstance(head, dict):
            raise EmbedLoadError(f"head.json non-objet : {head_path}")
        poids = head.get("w")
        biais = head.get("b")
        if not isinstance(poids, list) or len(poids) != _N_LABELS:
            raise EmbedLoadError(f"head.json : w sans {_N_LABELS} lignes : {head_path}")
        for ligne in poids:
            if not isinstance(ligne, list) or len(ligne) != _DIM:
                raise EmbedLoadError(f"head.json : ligne de w sans {_DIM} valeurs : {head_path}")
        if not isinstance(biais, list) or len(biais) != _N_LABELS:
            raise EmbedLoadError(f"head.json : b sans {_N_LABELS} valeurs : {head_path}")
        for valeur in (*(v for ligne in poids for v in ligne), *biais):
            if not _est_nombre_fini(valeur):
                raise EmbedLoadError(f"head.json : valeur non finie : {head_path}")

        # Calibrateur : réutilisation de `_validate_calibrator` (§6 R5 —
        # mêmes bornes, même interpolation servie, zéro réimplémentation) ;
        # son refus est re-typé EmbedLoadError (message inchangé : chemin).
        calibrator_path = directory / "calibrator.json"
        calibrator = _lire_json(calibrator_path, "calibrator.json")
        try:
            calib_x, calib_y = _validate_calibrator(calibrator, calibrator_path)
        except MLRouterLoadError as exc:
            raise EmbedLoadError(str(exc)) from exc

        return cls(
            [[float(v) for v in ligne] for ligne in poids],
            [float(v) for v in biais],
            calib_x,
            calib_y,
            float(cap),
        )

    def _logits(self, embedding: list[float]) -> list[float]:
        """W·e + b en boucles Python pures (3×384 : coût négligeable)."""
        return [
            sum(w * x for w, x in zip(ligne, embedding, strict=True)) + b
            for ligne, b in zip(self._poids, self._biais, strict=True)
        ]

    def predict(self, embedding: Sequence[float]) -> tuple[str, float]:
        """Chaîne de confiance UNIQUE §5.2bis — la SEULE porte de sortie.

        1. softmax ; 2. calibration conservatrice `min(brut, iso(brut))` ;
        3. clamp [0, 1] défensif ; 4. plafond `confidence_cap` du metadata.
        Probas non finies / mauvaise arité → `ValueError` (comptes
        uniquement) — attrapé par `TwoStageRouter` (repli étage 1).
        """
        valeurs: list[float] = []
        for v in embedding:
            # Type non numérique (bool compris) → refus immédiat ; les
            # non-finis (inf/NaN) passent et sont attrapés par le contrôle
            # des probas ci-dessous (§5.2.7 : « probas non finies »).
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError("embedding invalide : valeur non numerique")
            valeurs.append(float(v))
        if len(valeurs) != _DIM:
            raise ValueError(f"embedding invalide : {len(valeurs)} valeurs != {_DIM}")
        probs = _softmax(self._logits(valeurs))  # 1. softmax
        if any(not math.isfinite(p) for p in probs):
            raise ValueError(f"probas non finies : {len(probs)} valeurs")
        idx = max(range(_N_LABELS), key=probs.__getitem__)
        brut = probs[idx]
        conf = min(brut, interp_conf(brut, self._calib_x, self._calib_y))  # 2. min(brut, iso)
        conf = min(max(conf, 0.0), 1.0)  # 3. clamp [0, 1]
        conf = min(conf, self._confidence_cap)  # 4. plafond metadata (D3)
        return LABEL_ORDER[idx], conf


class EmbedRouter(Router):
    """Étage 2 : tokenise → encode (e5 ONNX) → poole → tête calibrée.

    `rule="embed:v0"` constant (vocabulaire système, cohérent avec `ml:v05` ;
    v1 émettra `embed:v1-<org>`). Ne détient AUCUNE logique de calibration
    ni de plafond propre : la chaîne §5.2bis vit intégralement dans
    `EmbedHead.predict` (correction MAJOR-1, 2026-07-23).
    """

    def __init__(
        self,
        encoder_dir: Path | str | None = None,
        head_dir: Path | str | None = None,
    ) -> None:
        # La racine est résolue À LA CONSTRUCTION, pas à l'import : après
        # déploiement d'un artefact, une purge du cache du bridge suffit.
        surcharge = os.environ.get(_EMBED_ARTIFACTS_DIR_ENV)
        artifacts_directory = Path(surcharge) if surcharge is not None else None
        if encoder_dir is not None:
            encoder_directory = Path(encoder_dir)
        elif artifacts_directory is not None:
            encoder_directory = artifacts_directory / "encoder"
        else:
            encoder_directory = ENCODER_DIR
        if head_dir is not None:
            head_directory = Path(head_dir)
        elif artifacts_directory is not None:
            head_directory = artifacts_directory / "heads" / "promoted"
        else:
            head_directory = PROMOTED_HEAD_DIR

        # 1. Imports PARESSEUX (§5.1.1) — absents => EmbedLoadError, jamais
        # un ImportError nu (le bridge et les tests s'y fient).
        try:
            import numpy
            import onnxruntime
            import tokenizers
        except ImportError as exc:
            raise EmbedLoadError(
                f"dependances embed indisponibles : {exc.__class__.__name__}"
            ) from exc

        # 2. Présence des fichiers encodeur (§5.1.2) — chemin seul en message.
        for nom in _ENCODER_FILES:
            if not (encoder_directory / nom).is_file():
                raise EmbedLoadError(f"encodeur incomplet : {encoder_directory / nom} absent")

        # 3. Intégrité de l'encodeur (§5.1.3) : sha256 des octets == littéraux
        # du spec (= manifest int8). RECADRAGE 2026-07-23 : littéraux None
        # tant que le geste fondateur n'a pas eu lieu — TOUT encodeur local
        # est refusé ici, fail-closed.
        spec = expected_embed_spec()
        for fichier, cle in (
            ("model.onnx", "encoder_sha256"),
            ("tokenizer.json", "tokenizer_sha256"),
        ):
            attendu = spec[cle]
            reel = hashlib.sha256((encoder_directory / fichier).read_bytes()).hexdigest()
            if reel != attendu:
                raise EmbedLoadError(
                    f"integrite : {cle} attendu {str(attendu)[:12]} != octets {reel[:12]} "
                    f"({encoder_directory / fichier})"
                )

        # 4+7. Tête (§5.1.7) : EmbedHead.load porte LUI-MÊME les gardes de
        # dérive §5.1.4 (embed_spec, label_mapping, confidence_cap) — chargée
        # AVANT la session ORT : échouer sur une dérive ne paie jamais le
        # coût du chargement du modèle.
        self._head = EmbedHead.load(head_directory)

        # 5. Session ORT déterministe (§5.1.5) : CPU seul, 1 thread intra et
        # inter (parité num_threads=1 LightGBM — latence prévisible).
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        try:
            self._session = onnxruntime.InferenceSession(
                str(encoder_directory / "model.onnx"),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise EmbedLoadError(
                f"model.onnx invalide : {encoder_directory / 'model.onnx'} "
                f"({exc.__class__.__name__})"
            ) from exc

        # 6. Tokenizer (§5.1.6), troncature au max_tokens du spec (D12).
        try:
            tokenizer = tokenizers.Tokenizer.from_file(str(encoder_directory / "tokenizer.json"))
        except Exception as exc:
            raise EmbedLoadError(
                f"tokenizer.json invalide : {encoder_directory / 'tokenizer.json'} "
                f"({exc.__class__.__name__})"
            ) from exc
        tokenizer.enable_truncation(max_length=int(spec["max_tokens"]))  # type: ignore[arg-type]
        self._tokenizer = tokenizer
        self._np = numpy
        self._noms_entrees = {entree.name for entree in self._session.get_inputs()}

    def _embed(self, texte: str) -> list[float]:
        """Texte (déjà préfixé/tronqué) → embedding 384-d L2-normalisé (§5.2.4-6).

        Ids de tokens, tenseurs et embedding sont des VARIABLES LOCALES :
        jamais affectés à `self`, jamais inclus dans une exception.
        """
        np = self._np
        encodage = self._tokenizer.encode(texte)
        input_ids = np.asarray([encodage.ids], dtype=np.int64)
        attention_mask = np.asarray([encodage.attention_mask], dtype=np.int64)
        entrees = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._noms_entrees:
            # XLM-R n'utilise pas de segments : zéros si l'export les exige.
            entrees["token_type_ids"] = np.zeros_like(input_ids)
        hidden = self._session.run(None, entrees)[0]  # (1, L, 384)
        # Mean pooling MASQUÉ puis normalisation L2 (convention e5 canonique).
        masque = attention_mask[..., None].astype(hidden.dtype)  # (1, L, 1)
        somme = (hidden * masque).sum(axis=1)[0]  # (384,)
        compte = float(masque.sum())
        pooled = somme / max(compte, 1.0)
        norme = float(np.sqrt((pooled * pooled).sum()))
        if norme > 0.0:
            pooled = pooled / norme
        return [float(v) for v in pooled]

    def decide(self, signals: Signals) -> Decision:
        """Texte en mémoire seulement (§5.2) — UN SEUL appel `predict` (§5.2.7)."""
        texte = signals.prompt.prompt_text
        if texte is None:
            # Défense en profondeur (§5.2.1) : TwoStageRouter court-circuite
            # AVANT d'invoquer l'étage 2 — message FIXE, sans contenu.
            raise EmbedRefusal("prompt_text absent — étage 2 opt-in non satisfait")
        # §5.2.2 troncature mémoire (D11) puis §5.2.3 préfixe e5.
        prefixe = _E5_PREFIX + texte[:_MAX_CHARS]
        del texte
        embedding = self._embed(prefixe)
        del prefixe  # hygiène §5.2.9 : le texte préfixé meurt AVANT le retour
        # §5.2.7 : l'INTÉGRALITÉ de la chaîne §5.2bis vit dans predict —
        # decide ne recalcule, ne re-calibre et ne re-plafonne RIEN.
        label, confiance = self._head.predict(embedding)
        return Decision(model=label, confidence=confiance, rule="embed:v0")
