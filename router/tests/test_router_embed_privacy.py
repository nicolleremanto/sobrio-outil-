"""Verrous privacy R6 — Lot 1 (EXIGENCE R6 du ledger l.154-159 ; spec §6.2, §10.1, D7).

Trois gardes complémentaires, chacune prouvée dans les deux sens :
- verrou DUR : `__reduce__` conditionnel sur `PromptSignals` — porteur de
  texte, toute sérialisation (pickle, `copy.deepcopy` via `__reduce_ex__`)
  LÈVE TypeError sans jamais inclure le contenu ; sans texte, comportement
  d'origine inchangé (mutation : ôter le verrou fait échouer les tests
  « porteur de texte », le rendre inconditionnel fait échouer la branche
  compat) ;
- garde PRÉVENTIVE : scan statique en GLOB du code de production (jamais de
  liste figée — leçon du transfert R5), aucun motif de sérialisation des
  signaux ; contrôle négatif par injection dans une copie temporaire
  (patron M6 des gardes réseau) ;
- protocole SECRET_LEAK (R1) étendu : rendus repr/str/f-string/format sur
  `PromptSignals` ET `Signals` porteurs de texte, plus le nouveau chemin
  d'exception du verrou.

Adaptateur : `features_to_signals` sans kwarg reste bit-identique à R5 ;
avec `prompt_text=`, le texte est attaché TEL QUEL, jamais loggé.

Jeton sentinelle aléatoire, AUCUN texte type prompt (convention chantier).
Lot 100 % stdlib : aucune dépendance embed requise (l'encodeur ONNX
n'arrive qu'au Lot 2 — aucun skip nécessaire ici).
"""

from __future__ import annotations

import copy
import logging
import pickle
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from sobrio_router import ConversationSignals, PromptSignals, Signals
from sobrio_router.adapter import features_to_signals

_SENTINELLE = "SECRET_LEAK_TEST_R6_LOT1_c9f2"

# ---------------------------------------------------------------------------
# Scan statique (spec §10.1) : périmètre en GLOB — tout module futur des
# répertoires de production est couvert D'OFFICE (`router/tools/` n'existe
# pas encore, Lot 2 : le glob le couvrira dès sa création, sans édition ici).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCAN_DIRS = (
    _REPO_ROOT / "router" / "sobrio_router",
    _REPO_ROOT / "router" / "eval",
    _REPO_ROOT / "router" / "train",
    _REPO_ROOT / "router" / "tools",
    _REPO_ROOT / "api" / "app",
)

_SCAN_FILES = sorted(p for d in _SCAN_DIRS for p in d.glob("*.py"))

# Forme import : ancrée en début de ligne (patron M6) — détecte `import
# pickle` ET `from pickle import X`, jamais une mention en prose.
_PICKLE_IMPORT_RE = re.compile(r"^\s*(import|from)\s+pickle\b", re.MULTILINE)
# Forme appel : accès d'attribut au module pickle, et appels asdict/astuple/
# vars — `\basdict\s*\(` attrape aussi la forme qualifiée `dataclasses.…`.
_SERIALISATION_CALL_RE = re.compile(r"\bpickle\.|\b(asdict|astuple|vars)\s*\(")


@pytest.mark.parametrize("module_path", _SCAN_FILES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_aucun_motif_de_serialisation_dans_le_code_de_production(module_path):
    source = module_path.read_text(encoding="utf-8")
    match = _PICKLE_IMPORT_RE.search(source) or _SERIALISATION_CALL_RE.search(source)
    assert match is None, (
        f"motif de sérialisation interdit dans {module_path.name} : {match.group(0)!r}"
    )


def test_scan_couvre_les_modules_attendus():
    """Garde-fou du garde-fou : un dossier déplacé ou vidé rendrait le scan
    silencieusement inerte — on vérifie que les globs voient bien les
    modules clés de CHAQUE répertoire du périmètre existant."""
    noms = {str(p.relative_to(_REPO_ROOT)) for p in _SCAN_FILES}
    assert {
        "router/sobrio_router/types.py",
        "router/sobrio_router/adapter.py",
        "router/sobrio_router/ml.py",
        "router/sobrio_router/safe.py",
        "router/eval/harness.py",
        "router/eval/gate.py",
        "router/train/promote.py",
        "router/train/train_v05.py",
        "api/app/routes.py",
        "api/app/main.py",
        "api/app/router_bridge.py",
        "api/app/schemas.py",
    } <= noms


def test_regex_import_pickle_detecte_les_deux_formes_et_ignore_la_prose():
    """La regex d'import DOIT voir `import X` ET `from X import Y` (patron
    M6) — et ne PAS se déclencher sur une mention en prose de docstring."""
    assert _PICKLE_IMPORT_RE.search("import pickle\n") is not None
    assert _PICKLE_IMPORT_RE.search("    from pickle import dumps\n") is not None
    assert _PICKLE_IMPORT_RE.search("# la sérialisation pickle des signaux est interdite\n") is None
    assert _SERIALISATION_CALL_RE.search("# pickle est interdit sur les signaux\n") is None


_POISONS = (
    "import pickle\n",
    "from pickle import dumps\n",
    "payload = pickle.dumps(signals)\n",
    "d = dataclasses.asdict(signals.prompt)\n",
    "d = asdict(signals.prompt)\n",
    "t = astuple(signals.prompt)\n",
    "d = vars(signals.prompt)\n",
)


@pytest.mark.parametrize("poison", _POISONS, ids=lambda s: s.strip()[:36])
def test_controle_negatif_le_scan_detecte_chaque_motif_injecte(tmp_path, poison):
    """Contrôle négatif par injection (patron M6) : copie temporaire d'un
    module RÉEL empoisonnée d'un motif — le scan doit la détecter, alors
    qu'il laisse passer la source propre."""
    source_propre = (_REPO_ROOT / "router" / "sobrio_router" / "types.py").read_text(
        encoding="utf-8"
    )
    assert _PICKLE_IMPORT_RE.search(source_propre) is None
    assert _SERIALISATION_CALL_RE.search(source_propre) is None

    chemin = tmp_path / "types_poisoned.py"
    chemin.write_text(source_propre + "\n" + poison, encoding="utf-8")
    empoisonne = chemin.read_text(encoding="utf-8")
    detection = _PICKLE_IMPORT_RE.search(empoisonne) or _SERIALISATION_CALL_RE.search(empoisonne)
    assert detection is not None, f"motif non détecté : {poison!r}"


# ---------------------------------------------------------------------------
# Verrou __reduce__ (D7, spec §6.2) : les DEUX branches.
# ---------------------------------------------------------------------------


def _prompt_avec_texte() -> PromptSignals:
    return PromptSignals(
        char_len=28,
        token_est=9,
        lang="fr",
        has_code=False,
        has_math=False,
        keyword_flags=(),
        prompt_text=_SENTINELLE,
    )


@pytest.mark.parametrize("protocole", range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle_prompt_signals_porteur_de_texte_leve_sans_le_texte(protocole):
    prompt = _prompt_avec_texte()
    with pytest.raises(TypeError) as excinfo:
        pickle.dumps(prompt, protocol=protocole)
    assert _SENTINELLE not in str(excinfo.value)
    assert _SENTINELLE not in repr(excinfo.value)


@pytest.mark.parametrize("protocole", range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle_signals_contenant_le_texte_leve_aussi(protocole):
    """Le verrou tient aussi en IMBRIQUÉ : sérialiser le bundle `Signals`
    sérialise le `PromptSignals` qu'il contient — même refus, même hygiène."""
    bundle = Signals(prompt=_prompt_avec_texte(), conversation=ConversationSignals())
    with pytest.raises(TypeError) as excinfo:
        pickle.dumps(bundle, protocol=protocole)
    assert _SENTINELLE not in str(excinfo.value)
    assert _SENTINELLE not in repr(excinfo.value)


def test_deepcopy_porteur_de_texte_leve_via_reduce_ex():
    """`copy.deepcopy` passe par `__reduce_ex__` → même verrou, sans code en plus."""
    prompt = _prompt_avec_texte()
    bundle = Signals(prompt=prompt, conversation=ConversationSignals())
    for porteur in (prompt, bundle):
        with pytest.raises(TypeError) as excinfo:
            copy.deepcopy(porteur)
        assert _SENTINELLE not in str(excinfo.value)


def test_pickle_et_deepcopy_sans_texte_restent_fonctionnels():
    """Branche compat : sans texte, round-trip INTACT (un verrou devenu
    inconditionnel casserait ce test ; un verrou ôté casse les tests
    « porteur de texte » ci-dessus — les deux mutations sont tuées)."""
    prompt = PromptSignals(
        char_len=5,
        token_est=2,
        lang="en",
        has_code=True,
        has_math=False,
        keyword_flags=("code",),
    )
    bundle = Signals(prompt=prompt, conversation=ConversationSignals(msg_count=3))
    assert pickle.loads(pickle.dumps(prompt)) == prompt
    assert pickle.loads(pickle.dumps(bundle)) == bundle
    assert copy.deepcopy(prompt) == prompt
    assert copy.deepcopy(bundle) == bundle


# ---------------------------------------------------------------------------
# Protocole SECRET_LEAK (R1) étendu — rendus texte et chemin d'exception.
# ---------------------------------------------------------------------------


def test_secret_leak_protocole_etendu_sur_les_rendus():
    """Re-déroulé R6 du protocole R1 : aucun rendu ne sérialise le texte —
    repr/str/f-string (déjà couverts R1) PLUS format() et conversions !r/!s
    imbriquées sur le bundle. Le champ reste LISIBLE par l'étage 2."""
    prompt = _prompt_avec_texte()
    bundle = Signals(prompt=prompt, conversation=ConversationSignals())
    rendus = (
        repr(prompt),
        str(prompt),
        f"{prompt}",
        format(prompt),
        repr(bundle),
        str(bundle),
        f"{bundle}",
        f"{bundle!r}",
        f"{bundle!s}",
        format(bundle),
    )
    for rendu in rendus:
        assert _SENTINELLE not in rendu
    assert prompt.prompt_text == _SENTINELLE


def test_secret_leak_exception_du_verrou_sans_contenu():
    """Le message du verrou est FIXE (aucune interpolation) : ni le texte ni
    sa longueur ne fuient par l'exception — nouveau chemin d'erreur R6."""
    with pytest.raises(TypeError) as excinfo:
        pickle.dumps(_prompt_avec_texte())
    message = str(excinfo.value)
    assert message == ("PromptSignals porteur de texte : sérialisation interdite (règle n°1, R6)")
    assert _SENTINELLE not in message


# ---------------------------------------------------------------------------
# Adaptateur : kwarg `prompt_text` (spec §1.2) — iso-comportement sans kwarg.
# ---------------------------------------------------------------------------


@dataclass
class _FakeFeatures:
    """Double léger de `app.schemas.Features` — même patron que test_router_adapter."""

    char_len: int
    token_est: int
    lang: str
    has_code: bool
    has_attachment_hint: bool
    keyword_flags: list[str]


def _features() -> _FakeFeatures:
    return _FakeFeatures(
        char_len=42,
        token_est=17,
        lang="fr",
        has_code=False,
        has_attachment_hint=False,
        keyword_flags=["resume"],
    )


def test_adaptateur_sans_kwarg_bit_identique_a_r5():
    """Sans kwarg : `prompt_text is None` et mapping INCHANGÉ champ à champ
    (égalité stricte avec le `Signals` attendu ET avec l'appel explicite
    `prompt_text=None`)."""
    signals = features_to_signals(_features())
    attendu = Signals(
        prompt=PromptSignals(
            char_len=42,
            token_est=17,
            lang="fr",
            has_code=False,
            has_math=False,
            keyword_flags=("resume",),
        ),
        conversation=ConversationSignals(),
    )
    assert signals.prompt.prompt_text is None
    assert signals == attendu
    assert signals == features_to_signals(_features(), prompt_text=None)


def test_adaptateur_prompt_text_est_keyword_only():
    """Le passage POSITIONNEL est refusé : impossible d'alimenter le texte
    par accident depuis un site d'appel existant."""
    with pytest.raises(TypeError):
        features_to_signals(_features(), _SENTINELLE)  # appel volontairement positionnel


def test_adaptateur_avec_kwarg_attache_tel_quel_jamais_logge(caplog, capsys):
    """Avec kwarg : le texte est attaché par IDENTITÉ (aucune validation ni
    transformation), seul `prompt_text` diffère du chemin sans kwarg, et
    RIEN n'est loggé/imprimé/rendu."""
    caplog.set_level(logging.DEBUG)
    signals = features_to_signals(_features(), prompt_text=_SENTINELLE)
    assert signals.prompt.prompt_text is _SENTINELLE
    # Seul prompt_text diffère : en le neutralisant, on retombe bit-identique
    # sur le chemin sans kwarg (conversation comprise).
    sans_kwarg = features_to_signals(_features())
    assert replace(signals.prompt, prompt_text=None) == sans_kwarg.prompt
    assert signals.conversation == sans_kwarg.conversation
    # Jamais loggé, jamais imprimé, jamais visible dans un rendu.
    assert _SENTINELLE not in caplog.text
    sortie = capsys.readouterr()
    assert _SENTINELLE not in sortie.out + sortie.err
    assert _SENTINELLE not in repr(signals)
