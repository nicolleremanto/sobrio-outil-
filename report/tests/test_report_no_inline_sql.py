"""Garde-fou : chaque chiffre provient d'une requête versionnée de report/queries/.

generate.py ne doit contenir AUCUN SQL inline — pas de mot-clé de requête dans
le code de génération. Les requêtes vivent dans des fichiers .sql avec en-tête
(mesure, périmètre, limites) et paramètres nommés SQLAlchemy.
"""

import re
from pathlib import Path

import generate

REQUETES_ATTENDUES = {
    "monthly_total",
    "by_model",
    "by_workspace",
    "reco_adoption",
    "reco_savings",
    "footprint_avoided",
}


def test_pas_de_sql_inline_dans_generate():
    """Pas de SELECT (ni autre mot-clé de requête) dans generate.py."""
    source = Path(generate.__file__).read_text(encoding="utf-8")
    for mot_cle in (r"\bselect\b", r"\binsert\b", r"\bupdate\b", r"\bdelete\b"):
        assert not re.search(mot_cle, source, re.IGNORECASE), (
            f"SQL inline détecté dans generate.py : motif {mot_cle}"
        )


def test_les_requetes_versionnees_existent():
    stems = {p.stem for p in Path(generate.QUERIES_DIR).glob("*.sql")}
    manquantes = REQUETES_ATTENDUES - stems
    assert not manquantes, f"Requêtes manquantes dans report/queries/ : {manquantes}"


def test_chaque_requete_a_un_en_tete_et_des_parametres_nommes():
    for chemin in Path(generate.QUERIES_DIR).glob("*.sql"):
        texte = chemin.read_text(encoding="utf-8")
        assert texte.lstrip().startswith("--"), f"{chemin.name} : en-tête de commentaire absent"
        entete = texte.lower()
        assert "périmètre" in entete or "perimetre" in entete, (
            f"{chemin.name} : le périmètre doit être documenté dans l'en-tête"
        )
        assert ":org_id" in texte, f"{chemin.name} : paramètre nommé :org_id absent"
        assert ":month" in texte, f"{chemin.name} : paramètre nommé :month absent"


def test_le_contexte_est_construit_depuis_les_requetes(resultats_factices):
    """Les clés du contexte proviennent des fichiers de report/queries/ (stems)."""
    contexte = generate.build_context("demo", "2026-06", resultats_factices)
    # Chaque famille de chiffres du contexte est adossée à une requête versionnée.
    assert set(resultats_factices) == REQUETES_ATTENDUES
    assert contexte["total"]["cost_usd"] == 1842.50
    assert contexte["savings"]["eur_min"] == 0.009
    assert contexte["avoided"]["wh_max"] == 6.4
