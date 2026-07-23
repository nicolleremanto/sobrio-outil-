"""Récupération du modèle encodeur pré-exporté (étage 2, chantier R6) — spec §4.4, D9.

SEUL module du repo autorisé à importer `urllib.request`, et UNIQUEMENT dans
le corps de `_download()` (garde AST, spec §10.7) — l'invariant « zéro motif
réseau » reste prouvable par glob partout ailleurs. La garde de flag est
vérifiée AVANT tout import réseau (patron exact
`public_datasets._require_download_flag`).

RECADRAGE D'ORCHESTRATION (décision datée 2026-07-23) : le PREMIER FETCH du
modèle est un GESTE FONDATEUR — le choix et l'approbation du dépôt source de
l'export ONNX int8 de `multilingual-e5-small` appartiennent au fondateur,
pas à un agent. Le manifest committé (`embed_model_manifest.json`) porte
donc des champs `url`/`sha256`/`source_repo` à `null` : ce CLI REFUSE
(« source non approuvée : geste fondateur requis », exit 2) toute exécution
tant que le fondateur n'a pas renseigné et approuvé la source. Le chemin
réseau ci-dessous existe dans le code mais est INEXÉCUTABLE aujourd'hui —
c'est voulu.

Contrat CLI (fail-closed, style `train_v05.py`) :

1. `SOBRIO_ALLOW_MODEL_DOWNLOAD` doit valoir EXACTEMENT `"1"` — sinon REFUS
   exit 2 sans le moindre accès réseau (message renvoyant à LICENSES.md).
2. Manifest COMPLET exigé pour la variante demandée : `source_repo`,
   `source_license`, `source_verified_date` renseignés, et pour CHAQUE
   fichier `url` + `sha256` (64 hex) + `size_bytes` > 0 — sinon REFUS
   « source non approuvée : geste fondateur requis » exit 2.
3. Espace disque vérifié AVANT téléchargement (tailles manifest + marge
   200 Mo — contrainte machine, MEMORY « disk near full »).
4. Téléchargement dans un fichier TEMPORAIRE, sha256 calculé PUIS comparé au
   manifest : écart → suppression du fichier + REFUS exit 2 (message =
   hash/chemins uniquement). Jamais d'écrasement silencieux d'un fichier
   local existant.
5. Destination : `router/artifacts/embed/encoder/` (gitignoré via
   `router/artifacts/*`, spec §4.2). Sortie : nombres/chemins/hash
   uniquement. JAMAIS appelé en CI, JAMAIS à l'import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_FLAG_ENV = "SOBRIO_ALLOW_MODEL_DOWNLOAD"

_TOOLS_DIR = Path(__file__).resolve().parent
_ROUTER_DIR = _TOOLS_DIR.parent

DEFAULT_MANIFEST_PATH = _TOOLS_DIR / "embed_model_manifest.json"
DEFAULT_DEST_DIR = _ROUTER_DIR / "artifacts" / "embed" / "encoder"

VARIANTES = ("int8", "fp32")
_FICHIERS_ATTENDUS = ("model.onnx", "tokenizer.json")
# Marge disque au-delà de la taille annoncée par le manifest (spec §4.4).
_MARGE_DISQUE_OCTETS = 200 * 1024 * 1024
_SCHEMES_AUTORISES = ("https://", "http://", "file://")

_REFUS_SOURCE_NON_APPROUVEE = "source non approuvée : geste fondateur requis"


class RefusError(RuntimeError):
    """Refus fail-closed du CLI (exit 2) — même patron que `train_v05.RefusError`."""


def _require_download_flag() -> None:
    """Lève si `SOBRIO_ALLOW_MODEL_DOWNLOAD` n'est pas EXACTEMENT '1' (défaut : refus).

    Vérifiée AVANT toute lecture de manifest et AVANT tout import réseau
    (patron `public_datasets._require_download_flag`).
    """
    if os.environ.get(_FLAG_ENV) != "1":
        raise RefusError(
            f"téléchargement du modèle refusé : {_FLAG_ENV} doit valoir '1' "
            "(défaut : désactivé). Statut (voir router/data/LICENSES.md) : source de "
            "l'export ONNX À APPROUVER PAR LE FONDATEUR — le premier fetch est un "
            "geste fondateur, jamais un défaut ni un acte de CI."
        )


def _load_manifest(manifest_path: Path) -> dict:
    """Charge le manifest JSON — introuvable/illisible/non-objet → `RefusError`."""
    try:
        contenu = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefusError(
            f"manifest introuvable : {manifest_path} ({exc.__class__.__name__})"
        ) from exc
    try:
        manifest = json.loads(contenu)
    except ValueError as exc:
        raise RefusError(f"manifest illisible (JSON invalide) : {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise RefusError(f"manifest invalide (objet JSON attendu) : {manifest_path}")
    return manifest


def _est_sha256_hex(valeur: object) -> bool:
    return (
        isinstance(valeur, str)
        and len(valeur) == 64
        and all(c in "0123456789abcdef" for c in valeur)
    )


def _fichiers_approuves(manifest: dict, variant: str) -> dict[str, dict]:
    """Extrait les fichiers de la variante ET exige une source APPROUVÉE complète.

    Toute lacune (variante absente, `source_*` non renseigné, `url` absente ou
    de schéma inconnu, `sha256` non hexadécimal, `size_bytes` non positif) →
    `RefusError` « source non approuvée : geste fondateur requis » : le
    manifest committé du repo (champs `null`) tombe ici PAR CONSTRUCTION.
    """
    variants = manifest.get("variants")
    if not isinstance(variants, dict) or not isinstance(variants.get(variant), dict):
        raise RefusError(
            f"{_REFUS_SOURCE_NON_APPROUVEE} — variante '{variant}' absente du manifest"
        )
    donnees = variants[variant]
    for champ in ("source_repo", "source_license", "source_verified_date"):
        valeur = donnees.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            raise RefusError(
                f"{_REFUS_SOURCE_NON_APPROUVEE} — champ '{champ}' non renseigné "
                f"pour la variante '{variant}'"
            )
    fichiers = donnees.get("files")
    if not isinstance(fichiers, dict):
        raise RefusError(
            f"{_REFUS_SOURCE_NON_APPROUVEE} — bloc 'files' absent pour la variante '{variant}'"
        )
    valides: dict[str, dict] = {}
    for nom in _FICHIERS_ATTENDUS:
        entree = fichiers.get(nom)
        if not isinstance(entree, dict):
            raise RefusError(
                f"{_REFUS_SOURCE_NON_APPROUVEE} — fichier '{nom}' absent du manifest "
                f"(variante '{variant}')"
            )
        url = entree.get("url")
        if not isinstance(url, str) or not url.startswith(_SCHEMES_AUTORISES):
            raise RefusError(
                f"{_REFUS_SOURCE_NON_APPROUVEE} — url manquante ou invalide pour "
                f"'{nom}' (variante '{variant}')"
            )
        if not _est_sha256_hex(entree.get("sha256")):
            raise RefusError(
                f"{_REFUS_SOURCE_NON_APPROUVEE} — sha256 manquant ou invalide pour "
                f"'{nom}' (variante '{variant}')"
            )
        size = entree.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise RefusError(
                f"{_REFUS_SOURCE_NON_APPROUVEE} — size_bytes manquant ou invalide pour "
                f"'{nom}' (variante '{variant}')"
            )
        valides[nom] = entree
    return valides


def _check_disk_space(dest_dir: Path, taille_totale: int) -> None:
    """Refuse si l'espace libre < taille annoncée + marge (AVANT tout téléchargement)."""
    sonde = dest_dir
    while not sonde.exists():
        sonde = sonde.parent
    libre = shutil.disk_usage(sonde).free
    requis = taille_totale + _MARGE_DISQUE_OCTETS
    if libre < requis:
        raise RefusError(
            f"espace disque insuffisant : {libre} octets libres < {requis} requis "
            f"({taille_totale} annoncés par le manifest + {_MARGE_DISQUE_OCTETS} de marge) "
            f"sous {sonde}"
        )


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as flux:
        for bloc in iter(lambda: flux.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    """SEUL point d'entrée réseau du repo (garde AST, spec §10.7).

    `urllib.request` est importé PARESSEUSEMENT ici — jamais au niveau
    module — et ce corps n'est atteignable qu'APRÈS la garde de flag ET la
    validation d'une source approuvée (manifest complet). Aujourd'hui le
    manifest committé est incomplet : ce chemin est INEXÉCUTABLE (voulu).
    """
    import urllib.request

    with urllib.request.urlopen(url) as reponse, dest.open("wb") as sortie:
        shutil.copyfileobj(reponse, sortie)


def _fetch_fichier(nom: str, entree: dict, dest_dir: Path) -> tuple[Path, str, str]:
    """Récupère UN fichier : temporaire → sha256 → comparaison → dépôt atomique.

    Retourne `(chemin final, sha256, statut)` avec statut ∈
    {"telecharge", "deja_present"}. Écart de sha → fichier temporaire
    SUPPRIMÉ + `RefusError` (hash/chemins uniquement). Fichier local existant
    divergent → REFUS (jamais d'écrasement silencieux).
    """
    attendu = entree["sha256"]
    final = dest_dir / nom
    if final.exists():
        local = _sha256_fichier(final)
        if local == attendu:
            return final, local, "deja_present"
        raise RefusError(
            f"fichier local divergent (jamais d'écrasement silencieux) : {final} "
            f"sha256 local {local} != manifest {attendu} — supprimer manuellement "
            "avant de relancer"
        )
    descripteur, tmp_nom = tempfile.mkstemp(prefix=f"{nom}.", suffix=".part", dir=dest_dir)
    os.close(descripteur)
    tmp = Path(tmp_nom)
    try:
        _download(entree["url"], tmp)
        obtenu = _sha256_fichier(tmp)
        if obtenu != attendu:
            raise RefusError(
                f"sha256 divergent pour {nom} : obtenu {obtenu} != manifest {attendu} "
                f"— fichier temporaire supprimé, rien n'est écrit sous {dest_dir}"
            )
        os.replace(tmp, final)
    finally:
        tmp.unlink(missing_ok=True)
    return final, attendu, "telecharge"


def run_fetch(variant: str, dest_dir: Path, manifest_path: Path) -> list[tuple[Path, str, str]]:
    """Pipeline complet §4.4 : flag → manifest approuvé → disque → fetch + sha.

    Lève `RefusError` sur toute garde fail-closed. L'ORDRE est normatif : la
    garde de flag PRÉCÈDE la lecture du manifest (et donc tout le reste).
    """
    _require_download_flag()
    manifest = _load_manifest(manifest_path)
    fichiers = _fichiers_approuves(manifest, variant)
    dest_dir.mkdir(parents=True, exist_ok=True)
    taille_totale = sum(e["size_bytes"] for e in fichiers.values())
    _check_disk_space(dest_dir, taille_totale)
    return [_fetch_fichier(nom, entree, dest_dir) for nom, entree in fichiers.items()]


def main(argv: list[str] | None = None) -> int:
    """CLI — sortie : chemins/hash/statuts uniquement ; refus propres exit 2."""
    parser = argparse.ArgumentParser(
        description=(
            "Récupère l'encodeur e5 pré-exporté ONNX (étage 2, R6) — flag explicite, "
            "sha256 du manifest obligatoires, jamais en CI."
        )
    )
    parser.add_argument(
        "--variant",
        choices=VARIANTES,
        default="int8",
        help="variante du manifest (défaut : int8, spec D5)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="répertoire de destination (défaut : router/artifacts/embed/encoder/, gitignoré)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest à utiliser (défaut : router/tools/embed_model_manifest.json)",
    )
    args = parser.parse_args(argv)

    dest_dir = args.dest if args.dest is not None else DEFAULT_DEST_DIR
    manifest_path = args.manifest if args.manifest is not None else DEFAULT_MANIFEST_PATH

    try:
        resultats = run_fetch(args.variant, dest_dir, manifest_path)
    except RefusError as exc:
        print(f"REFUS : {exc}", file=sys.stderr)
        return 2

    for chemin, sha, statut in resultats:
        print(f"{statut} : {chemin} sha256={sha}")
    print(f"variante {args.variant} : {len(resultats)} fichiers vérifiés sous {dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
