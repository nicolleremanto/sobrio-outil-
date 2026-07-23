"""R6 Lot 4 — triple verrou de l'étage 2 en E2E API (spec §3, §10.2, §10.3).

Matrice 8 cas env × policy × texte (§3.4) : l'étage 2 (SPY injecté) n'est
invoqué QUE dans le cas tout-ouvert ; dans TOUS les autres, décision étage 1
et texte jamais transmis (spy jamais appelé, `prompt_text=None` dans les
signaux réellement construits par la route). Politiques mal typées → verrou
fermé, 200, jamais de 500.

Cascade fail-soft (§2.2) TESTÉE avec le VRAI `EmbedRouter` : le geste
fondateur n'ayant pas eu lieu (sha encodeur `None`, modèle absent), sa
construction échoue AUJOURD'HUI en `EmbedLoadError` — c'est le comportement
de PRODUCTION attendu : org opt-in embed_v0 → repli étage 1 (ml_v05) servi
proprement, puis étage 1 KO → heuristique. API 200 dans tous les cas.

Jeton sentinelle ALÉATOIRE, aucun texte type prompt (convention chantier).
"""

from __future__ import annotations

import logging

import pytest
import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body
from sobrio_router import Decision, Router
from sobrio_router import embed as embed_module
from sobrio_router import ml as ml_module

from app import router_bridge, routes
from app.router_bridge import _stage2_unlocked

_SENTINELLE = "JETON_SENTINELLE_R6_LOT4_9b1f4c7e"

_POLICY_COMPLETE = '\'{"router_version": "embed_v0", "send_prompt_text": true}\''
# Incomplète : `send_prompt_text` ABSENT (défaut par contrat : false) — l'une
# des deux clés du verrou 2 manque (§3.2).
_POLICY_INCOMPLETE = '\'{"router_version": "embed_v0"}\''


def _poser_policy(test_engine, policy_sql: str) -> None:
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE orgs SET policy_json = {policy_sql}::jsonb WHERE org_id = 'demo'")
        )


def _reset_policy(test_engine) -> None:
    _poser_policy(test_engine, "'{}'")


class _FauxEtage1(Router):
    """Double déterministe de MLRouter : conf 0.5 (< 0.75 → arbitrage ouvert)."""

    def __init__(self, *args, **kwargs) -> None:  # signature MLRouter(PROMOTED_DIR)
        pass

    def decide(self, signals) -> Decision:
        return Decision(model="claude-haiku-4-5", confidence=0.5, rule="ml:v05")


class _SpyEtage2(Router):
    """Spy injecté à la place d'EmbedRouter : trace construction ET invocations."""

    instances: list[_SpyEtage2] = []

    def __init__(self, *args, **kwargs) -> None:
        self.textes_recus: list[str | None] = []
        type(self).instances.append(self)

    def decide(self, signals) -> Decision:
        self.textes_recus.append(signals.prompt.prompt_text)
        return Decision(model="claude-sonnet-5", confidence=0.72, rule="embed:v0")


@pytest.fixture()
def bridge_propre():
    """lru_cache purgé AVANT et APRÈS chaque cas : env et policy varient,
    la clé de cache (version) ne varie pas — sans purge, un cas fuirait
    dans le suivant."""
    router_bridge._router_for_version.cache_clear()
    yield
    router_bridge._router_for_version.cache_clear()


@pytest.fixture()
def etages_factices(monkeypatch):
    """Étage 1 déterministe + spy étage 2, registre remis à zéro."""
    _SpyEtage2.instances = []
    monkeypatch.setattr(ml_module, "MLRouter", _FauxEtage1)
    monkeypatch.setattr(embed_module, "EmbedRouter", _SpyEtage2)


@pytest.fixture()
def textes_transmis(monkeypatch):
    """Espionne `features_to_signals` TEL QU'APPELÉ par la route : capture le
    `prompt_text` réellement attaché aux signaux (None = texte détruit)."""
    captures: list[str | None] = []
    original = routes.features_to_signals

    def _espion(features, *, prompt_text=None):
        captures.append(prompt_text)
        return original(features, prompt_text=prompt_text)

    monkeypatch.setattr(routes, "features_to_signals", _espion)
    return captures


# ---------------------------------------------------------------------------
# Matrice §3.4 — 8 combinaisons env × policy × texte (spec §10.2).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texte_present", [False, True], ids=["texte-absent", "texte-present"])
@pytest.mark.parametrize("policy_complete", [False, True], ids=["policy-incomplete", "policy-ok"])
@pytest.mark.parametrize("env_on", [False, True], ids=["env-off", "env-on"])
def test_matrice_triple_verrou_8_cas(
    client,
    test_engine,
    monkeypatch,
    bridge_propre,
    etages_factices,
    textes_transmis,
    env_on,
    policy_complete,
    texte_present,
):
    if env_on:
        monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    else:
        monkeypatch.delenv("SOBRIO_EMBED_STAGE2", raising=False)
    _poser_policy(test_engine, _POLICY_COMPLETE if policy_complete else _POLICY_INCOMPLETE)
    body = make_recommend_body(token_est=50)
    if texte_present:
        body["prompt_text"] = _SENTINELLE
    try:
        response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 200  # jamais de 500, quel que soit l'état
        assert _SENTINELLE not in response.text

        appels_spy = [t for spy in _SpyEtage2.instances for t in spy.textes_recus]
        tout_ouvert = env_on and policy_complete and texte_present
        if tout_ouvert:
            # SEUL cas où l'étage 2 voit le texte (§3.4 ligne 4).
            assert response.json()["rule"] == "embed:v0"
            assert appels_spy == [_SENTINELLE]
            assert textes_transmis == [_SENTINELLE]
        else:
            # Étage 1 seul répond ; le texte n'atteint JAMAIS les signaux.
            assert response.json()["rule"] == "ml:v05"
            assert appels_spy == []
            assert textes_transmis == [None]
        if not env_on:
            # OFF par env PRIME sur la politique : étage 2 JAMAIS instancié
            # (§2.2.1) — pas seulement jamais invoqué.
            assert _SpyEtage2.instances == []
    finally:
        _reset_policy(test_engine)


# ---------------------------------------------------------------------------
# Politiques mal typées (§10.2) : verrou fermé, 200, jamais de 500.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "policy_sql",
    [
        '\'{"router_version": "embed_v0", "send_prompt_text": "yes"}\'',
        '\'{"router_version": "embed_v0", "send_prompt_text": 1}\'',
        '\'{"router_version": "embed_v0", "send_prompt_text": null}\'',
    ],
    ids=["send-str", "send-int-1", "send-null"],
)
def test_send_prompt_text_mal_type_verrou_ferme(
    client,
    test_engine,
    monkeypatch,
    bridge_propre,
    etages_factices,
    textes_transmis,
    policy_sql,
):
    """`send_prompt_text` non strictement `true` (str, 1, null) → texte détruit.

    Le cas `1` tue la mutation `== True` → truthy : en Python `1 == True`,
    seul `is True` ferme ce verrou."""
    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    _poser_policy(test_engine, policy_sql)
    body = make_recommend_body(token_est=50)
    body["prompt_text"] = _SENTINELLE
    try:
        response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["rule"] == "ml:v05"  # étage 1 seul
        assert [t for spy in _SpyEtage2.instances for t in spy.textes_recus] == []
        assert textes_transmis == [None]
        assert _SENTINELLE not in response.text
    finally:
        _reset_policy(test_engine)


def test_policy_non_dict_avec_env_ouvert_verrou_ferme(
    client, test_engine, monkeypatch, bridge_propre, etages_factices, textes_transmis
):
    """policy_json non-objet + env ouvert + texte : verrou fermé, heuristique
    par défaut (version inconnue), 200 — jamais de 500 (règle 3)."""
    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    _poser_policy(test_engine, "'[1, 2, 3]'")
    body = make_recommend_body(token_est=50)
    body["prompt_text"] = _SENTINELLE
    try:
        response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["rule"] == "heuristic:short_simple"
        assert [t for spy in _SpyEtage2.instances for t in spy.textes_recus] == []
        assert textes_transmis == [None]
    finally:
        _reset_policy(test_engine)


def test_stage2_unlocked_matrice_unitaire(monkeypatch):
    """La fonction PURE du verrou 1+2 (§3.3) — matrice unitaire complète."""
    # Env fermé : la politique n'a AUCUN pouvoir.
    monkeypatch.delenv("SOBRIO_EMBED_STAGE2", raising=False)
    ouverte = {"router_version": "embed_v0", "send_prompt_text": True}
    assert _stage2_unlocked(ouverte) is False
    # Env à une autre valeur que "1" exactement : fermé (patron dataset).
    for valeur in ("0", "true", "yes", " 1", "1 "):
        monkeypatch.setenv("SOBRIO_EMBED_STAGE2", valeur)
        assert _stage2_unlocked(ouverte) is False
    # Env ouvert : les DEUX clés policy sont requises, strictement typées.
    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    assert _stage2_unlocked(ouverte) is True
    fermees = (
        None,
        [1, 2],
        "embed_v0",
        {},
        {"router_version": "embed_v0"},
        {"send_prompt_text": True},
        {"router_version": "ml_v05", "send_prompt_text": True},
        {"router_version": "embed_v0", "send_prompt_text": "yes"},
        {"router_version": "embed_v0", "send_prompt_text": 1},
        {"router_version": "embed_v0", "send_prompt_text": None},
        {"router_version": 42, "send_prompt_text": True},
    )
    for policy in fermees:
        assert _stage2_unlocked(policy) is False, policy


# ---------------------------------------------------------------------------
# Cascade fail-soft §2.2 avec le VRAI EmbedRouter (geste fondateur non
# advenu : la construction échoue AUJOURD'HUI — comportement de production).
# ---------------------------------------------------------------------------


def test_embed_router_reel_echoue_en_embed_load_error_aujourdhui():
    """Préalable de la cascade : AVANT le geste fondateur, la construction
    réelle échoue TOUJOURS proprement (deps absentes, encodeur absent ou sha
    normatifs `None`) — jamais un autre type d'exception."""
    with pytest.raises(embed_module.EmbedLoadError):
        embed_module.EmbedRouter()


def test_cascade_fail_soft_embed_ko_sert_etage1(
    client, test_engine, db, monkeypatch, bridge_propre, caplog, capsys
):
    """Org opt-in embed_v0, triple verrou OUVERT, EmbedRouter RÉEL en échec
    de chargement → l'étage 1 (ml_v05) répond proprement, texte jamais
    traité ni fui, API 200 (§2.2.2 — cas nominal jusqu'au geste fondateur)."""
    caplog.set_level(logging.DEBUG)
    tentatives: list[bool] = []
    constructeur_reel = embed_module.EmbedRouter

    def _constructeur_espionne(*args, **kwargs):
        tentatives.append(True)
        return constructeur_reel(*args, **kwargs)  # lève EmbedLoadError aujourd'hui

    monkeypatch.setattr(embed_module, "EmbedRouter", _constructeur_espionne)
    monkeypatch.setattr(ml_module, "MLRouter", _FauxEtage1)  # étage 1 déterministe
    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    _poser_policy(test_engine, _POLICY_COMPLETE)
    body = make_recommend_body(token_est=50)
    body["prompt_text"] = _SENTINELLE
    try:
        response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["rule"] == "ml:v05"  # repli fin : rule étage 1
        assert tentatives == [True]  # la cascade a bien TENTÉ l'étage 2
        # Le texte n'a fui nulle part : réponse, logs, sorties, DB entière.
        assert _SENTINELLE not in response.text
        assert _SENTINELLE not in caplog.text
        for record in caplog.records:
            assert _SENTINELLE not in repr(record.__dict__)
        sortie = capsys.readouterr()
        assert _SENTINELLE not in sortie.out + sortie.err
        lignes = db.execute(sa.text("SELECT row_to_json(t)::text FROM events_reco t")).scalars()
        for ligne in lignes:
            assert _SENTINELLE not in ligne
    finally:
        _reset_policy(test_engine)


def test_cascade_fail_soft_etage1_ko_aussi_sert_heuristique(
    client, test_engine, monkeypatch, bridge_propre, tmp_path
):
    """Étage 2 KO (réel) PUIS étage 1 KO (PROMOTED_DIR vide) : l'échec de
    MLRouter PROPAGE (§2.2.3), la garde lru_cache sert SafeRouter(None) →
    `fallback:heuristic`, API 200 — chaîne de repli complète (§2.2)."""
    monkeypatch.setattr(ml_module, "PROMOTED_DIR", tmp_path / "promoted-vide")
    monkeypatch.setenv("SOBRIO_EMBED_STAGE2", "1")
    _poser_policy(test_engine, _POLICY_COMPLETE)
    body = make_recommend_body(token_est=50)
    body["prompt_text"] = _SENTINELLE
    try:
        response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 200
        payload = response.json()
        assert payload["rule"] == "fallback:heuristic"
        assert 0 <= payload["confidence"] <= 1
        assert _SENTINELLE not in response.text
    finally:
        _reset_policy(test_engine)


def test_env_off_embed_v0_identique_a_ml_v05(
    client, test_engine, monkeypatch, bridge_propre, etages_factices
):
    """Env fermé, org embed_v0 SANS texte : servi comme ml_v05 (§3.4 ligne 1)
    — même rule, même modèle que la version ml_v05 explicite."""
    monkeypatch.delenv("SOBRIO_EMBED_STAGE2", raising=False)
    _poser_policy(test_engine, _POLICY_COMPLETE)
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["rule"] == "ml:v05"
        assert _SpyEtage2.instances == []  # étage 2 jamais instancié
    finally:
        _reset_policy(test_engine)
