"""TEST ANTI-FUITE (règle n°1) : le texte du prompt ne sort JAMAIS de la mémoire.

On envoie une sentinelle via `prompt_text` (champ optionnel du contrat) et on
vérifie qu'elle n'apparaît :
- NI dans les logs (caplog niveau DEBUG sur le root logger + capsys),
- NI dans aucune colonne de events_reco (features_json et toutes les
  colonnes texte, via row_to_json sur la table entière).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body

SENTINEL = "TEXTE_SECRET_SENTINELLE_XYZ"


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
