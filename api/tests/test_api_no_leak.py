"""TEST ANTI-FUITE (règle n°1) : le texte du prompt ne sort JAMAIS de la mémoire.

On envoie une sentinelle via `prompt_text` (champ optionnel du contrat) et on
vérifie qu'elle n'apparaît :
- NI dans les logs (caplog niveau DEBUG sur le root logger + capsys),
- NI dans aucune colonne de events_reco (features_json et toutes les
  colonnes texte, via row_to_json sur la table entière).

R6 Lot 4 (MAJOR-2, spec §10.1) : extension aux CHEMINS D'ERREUR — le chemin
200 ne couvrait pas les 422/500. Trois cas E2E, chacun avec la triple
assertion « sentinelle absente des logs (caplog + capsys, récursif sur les
extras), absente de la DB (events_reco ET toute autre table), absente du
corps de la réponse » :
1. 422 champ invalide avec `prompt_text` VALIDE porteur de la sentinelle ;
2. 422 sentinelle dans un champ extra interdit (`promt_text`,
   `extra="forbid"`) — pydantic v2 embarque la VALEUR dans `input`, le
   handler global de `main.py` doit l'avoir caviardée ;
3. 500 DB monkeypatchée levant pendant que le texte est encore en variables
   locales de `recommend` (traceback SQLAlchemy `[parameters: …]` compris).

Sentinelles = jetons ALÉATOIRES, aucun texte type prompt (convention R6).
"""

from __future__ import annotations

import logging
import traceback

import pytest
import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body
from sqlalchemy.orm import Session

SENTINEL = "TEXTE_SECRET_SENTINELLE_XYZ"

# Jetons aléatoires dédiés aux chemins d'erreur (un par cas : toute fuite
# est attribuable à SON chemin).
_SENTINELLE_422_CHAMP = "JETON_ERR422A_R6_L4_f04c31d9"
_SENTINELLE_422_EXTRA = "JETON_ERR422B_R6_L4_a8e27b53"
_SENTINELLE_500_DB = "JETON_ERR500_R6_L4_63d90efa"


def _db_entiere_serialisee(db) -> str:
    """Sérialise TOUTES les lignes de TOUTES les tables du schéma public —
    « absente de la DB (events_reco ET toute autre table) » (spec §10.1)."""
    morceaux: list[str] = []
    tables = (
        db.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        .scalars()
        .all()
    )
    assert tables, "le schéma de test doit exposer au moins une table"
    for table in tables:
        lignes = db.execute(sa.text(f'SELECT row_to_json(t)::text FROM "{table}" t')).scalars()
        morceaux.extend(lignes)
    return "\n".join(morceaux)


def _assert_sentinelle_absente_partout(sentinelle, response, caplog, capsys, db):
    """Triple assertion commune des cas d'erreur (spec §10.1, MAJOR-2)."""
    assert sentinelle not in response.text
    assert sentinelle not in caplog.text
    for record in caplog.records:
        assert sentinelle not in repr(record.__dict__)  # extras récursifs
    sortie = capsys.readouterr()
    assert sentinelle not in sortie.out + sortie.err
    assert sentinelle not in _db_entiere_serialisee(db)


def test_prompt_text_never_logged_nor_stored(client, db, caplog, capsys):
    caplog.set_level(logging.DEBUG)  # root logger, tout niveau

    body = make_recommend_body(token_est=42)
    body["prompt_text"] = SENTINEL
    response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    assert response.status_code == 200
    reco_id = response.json()["reco_id"]

    # 1) La sentinelle n'apparaît dans AUCUN log capturé (message, args, extra).
    assert SENTINEL not in caplog.text
    for record in caplog.records:
        assert SENTINEL not in repr(record.__dict__)

    # 2) Ni sur stdout/stderr.
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err

    # 3) Ni dans la réponse elle-même (elle ne renvoie que la décision).
    assert SENTINEL not in response.text

    # 4) Ni dans AUCUNE colonne de events_reco : la ligne entière est
    # sérialisée en JSON (features_json et colonnes texte incluses).
    rows = db.execute(sa.text("SELECT row_to_json(t)::text FROM events_reco t")).scalars().all()
    assert rows, "la recommandation doit avoir été insérée"
    for serialized_row in rows:
        assert SENTINEL not in serialized_row

    # La ligne créée existe bien et ses features sont celles du contrat, sans texte.
    features = db.execute(
        sa.text("SELECT features_json FROM events_reco WHERE reco_id = :id"),
        {"id": reco_id},
    ).scalar_one()
    assert "prompt_text" not in features
    assert set(features.keys()) == {
        "char_len",
        "token_est",
        "lang",
        "has_code",
        "has_attachment_hint",
        "keyword_flags",
    }


def test_scrub_filter_redacts_forbidden_extra_keys(caplog):
    """Le filtre de scrubbing neutralise une clé interdite passée en extra.

    Garde-fou de dernier recours : même si un code fautif loggait un
    `prompt_text` en extra, la valeur serait remplacée avant émission.
    """
    from app.logging_conf import ContentScrubFilter

    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("sobrio.test_scrub")
    logger.addFilter(ContentScrubFilter())
    try:
        logger.info("evenement", extra={"prompt_text": SENTINEL, "org_id": "demo"})
    finally:
        logger.filters.clear()

    assert SENTINEL not in caplog.text
    record = caplog.records[-1]
    assert record.prompt_text == "[scrubbé — règle n°1]"
    assert record.org_id == "demo"  # les clés légitimes restent intactes


# ---------------------------------------------------------------------------
# R6 Lot 4 (MAJOR-2) — chemins d'ERREUR : la sentinelle ne fuit pas non plus
# quand la requête échoue (422 ×2, 500 DB).
# ---------------------------------------------------------------------------


def test_422_champ_invalide_texte_valide_sans_echo(client, db, caplog, capsys):
    """Cas 1 (§10.1) : `prompt_text` VALIDE porteur de la sentinelle + un
    AUTRE champ invalide → 422 ; le détail pydantic ne ré-échoïse la
    sentinelle nulle part (réponse, logs, DB)."""
    caplog.set_level(logging.DEBUG)
    body = make_recommend_body()
    body["prompt_text"] = _SENTINELLE_422_CHAMP
    body["features"]["token_est"] = "quarante"  # mal typé → 422
    response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    assert response.status_code == 422
    _assert_sentinelle_absente_partout(_SENTINELLE_422_CHAMP, response, caplog, capsys, db)
    # Le débogage contractuel reste possible : loc/msg/type présents.
    details = response.json()["detail"]
    assert any("token_est" in detail["loc"] for detail in details)


def test_422_sentinelle_champ_extra_interdit_caviardee(client, db, caplog, capsys):
    """Cas 2 (§10.1) : sentinelle dans un champ INCONNU (`promt_text`, faute
    de frappe — `extra="forbid"`) → 422. pydantic v2 embarque la VALEUR du
    champ dans `input` : le handler global doit l'avoir caviardée. Mutation :
    retirer le caviardage de `main.py` fait échouer CE test."""
    caplog.set_level(logging.DEBUG)
    body = make_recommend_body()
    body["promt_text"] = _SENTINELLE_422_EXTRA  # champ extra interdit
    response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    assert response.status_code == 422
    _assert_sentinelle_absente_partout(_SENTINELLE_422_EXTRA, response, caplog, capsys, db)
    # Assertion dédiée : `input` absent OU caviardé dans CHAQUE détail du
    # corps 422 — jamais la valeur reçue ; loc/msg/type conservés.
    details = response.json()["detail"]
    assert details, "le 422 doit porter au moins un détail"
    extra = [detail for detail in details if "promt_text" in detail["loc"]]
    assert extra, "le champ extra fautif doit être localisé (loc)"
    for detail in details:
        assert set(detail) <= {"loc", "msg", "type", "input", "ctx"}
        assert detail.get("input", "<redacted>") == "<redacted>"
        assert detail.get("ctx", "<redacted>") == "<redacted>"
        assert {"loc", "msg", "type"} <= set(detail)


def _executer_en_levant_sur_insert(original_execute):
    """Fabrique un `Session.execute` qui LÈVE sur l'INSERT events_reco avec
    une VRAIE exception SQLAlchemy (dont le rendu sérialise le SQL et
    `[parameters: …]` — le risque exact visé par le cas 3), et délègue tout
    le reste (l'auth continue de fonctionner)."""

    def _piege(self, statement, *args, **kwargs):
        if "INSERT INTO events_reco" in str(statement):
            parametres = args[0] if args else kwargs.get("params")
            raise sa.exc.OperationalError(
                str(statement), parametres, RuntimeError("panne DB simulee (test R6 Lot 4)")
            )
        return original_execute(self, statement, *args, **kwargs)

    return _piege


@pytest.fixture()
def _verrous_ouverts_db_en_panne(test_engine, monkeypatch):
    """Cas 3 : triple verrou OUVERT (le texte est réellement en variables
    locales de `recommend` via les signaux) + INSERT qui lève."""
    from app import router_bridge

    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE orgs SET policy_json = "
                """'{"router_version": "embed_v0", "send_prompt_text": true}'::jsonb """
                "WHERE org_id = 'demo'"
            )
        )
    monkeypatch.setattr(Session, "execute", _executer_en_levant_sur_insert(Session.execute))
    router_bridge._router_for_version.cache_clear()
    yield
    router_bridge._router_for_version.cache_clear()
    with test_engine.begin() as conn:
        conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))


def test_500_db_en_panne_sans_fuite(db, caplog, capsys, _verrous_ouverts_db_en_panne):
    """Cas 3 (§10.1) : la DB lève pendant que le texte vit encore dans les
    locales de `recommend` → 500 générique ; sentinelle absente de la
    réponse, des logs, de la DB ET du traceback complet capturé (chaîne
    d'exceptions SQLAlchemy incluse, `[parameters: …]` compris)."""
    from fastapi.testclient import TestClient

    from app.main import app

    caplog.set_level(logging.DEBUG)
    body = make_recommend_body()
    body["prompt_text"] = _SENTINELLE_500_DB

    # a) Vue CLIENT : réponse 500 générique, sans écho du corps reçu.
    with TestClient(app, raise_server_exceptions=False) as client_500:
        response = client_500.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    assert response.status_code == 500
    assert response.text == "Internal Server Error"  # corps générique starlette
    _assert_sentinelle_absente_partout(_SENTINELLE_500_DB, response, caplog, capsys, db)

    # b) Vue SERVEUR : le traceback INTÉGRAL (ce qu'uvicorn loggerait) est
    # capturé et scruté — chaîne de causes comprise.
    with TestClient(app) as client_brut:  # raise_server_exceptions=True (défaut)
        with pytest.raises(sa.exc.OperationalError) as excinfo:
            client_brut.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    rendu_traceback = "".join(traceback.format_exception(excinfo.value))
    assert "INSERT INTO events_reco" in rendu_traceback  # le piège a bien mordu
    assert "parameters" in rendu_traceback  # le rendu SQLAlchemy est bien exercé
    assert _SENTINELLE_500_DB not in rendu_traceback
    assert _SENTINELLE_500_DB not in repr(excinfo.value)
    assert _SENTINELLE_500_DB not in _db_entiere_serialisee(db)


# ---------------------------------------------------------------------------
# R6 Lot 4 (MAJOR-2) — test unitaire du handler de caviardage (mutation :
# retirer le caviardage fait AUSSI échouer le cas 2 E2E ci-dessus).
# ---------------------------------------------------------------------------


def test_handler_caviardage_unitaire():
    """`_caviarder_details_validation` : liste blanche loc/msg/type,
    input/ctx remplacés par `<redacted>`, clés inconnues omises."""
    import json as json_module

    from app.main import _REDACTED, _caviarder_details_validation

    jeton = "JETON_UNITAIRE_R6_L4_5c17be02"
    erreurs = [
        {
            "type": "extra_forbidden",
            "loc": ("body", "promt_text"),
            "msg": "Extra inputs are not permitted",
            "input": jeton,
            "url": "https://errors.pydantic.dev/2/v/extra_forbidden",
        },
        {
            "type": "int_parsing",
            "loc": ("body", "features", "token_est"),
            "msg": "Input should be a valid integer",
            "input": jeton,
            "ctx": {"erreur": jeton},
        },
        {"type": "missing", "loc": ("body", "features"), "msg": "Field required"},
    ]
    details = _caviarder_details_validation(erreurs)
    # Sérialisable ET sans le jeton, où qu'il ait été embarqué.
    assert jeton not in json_module.dumps(details)
    assert details[0] == {
        "loc": ["body", "promt_text"],
        "msg": "Extra inputs are not permitted",
        "type": "extra_forbidden",
        "input": _REDACTED,
    }  # `url` (hors liste blanche) omise, `input` caviardé, loc/msg/type intacts
    assert details[1]["input"] == _REDACTED
    assert details[1]["ctx"] == _REDACTED
    assert details[2] == {"loc": ["body", "features"], "msg": "Field required", "type": "missing"}


def test_handler_caviardage_enregistre_globalement():
    """Le handler est bien BRANCHÉ sur l'app (mesure structurelle, pas un
    utilitaire mort) : `RequestValidationError` figure dans les handlers."""
    from fastapi.exceptions import RequestValidationError

    from app.main import _handler_validation_caviarde, app

    assert app.exception_handlers.get(RequestValidationError) is _handler_validation_caviarde
