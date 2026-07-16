"""Test de bout en bout : base dédiée sobrio_test_report -> requêtes -> PDF.

Ne touche JAMAIS à la base partagée « sobrio » (Lot D en parallèle) : la
fixture ``base_test_url`` recrée une base dédiée avec le schéma des contrats
et un seed minimal pour 2026-06.
"""

import pytest
from sqlalchemy import create_engine

import generate


def test_requetes_sur_base_dediee(base_test_url):
    """Les requêtes versionnées retournent des chiffres cohérents avec le seed."""
    engine = create_engine(base_test_url)
    try:
        resultats = generate.run_queries(engine, "demo", "2026-06")
    finally:
        engine.dispose()

    total = resultats["monthly_total"]
    assert len(total) == 1
    assert float(total[0]["cost_usd"]) == 1842.50
    assert float(total[0]["energy_wh_min"]) <= float(total[0]["energy_wh_max"])

    assert {ligne["model"] for ligne in resultats["by_model"]} == {
        "haiku-4-5",
        "sonnet-4-6",
        "opus-4-8",
    }
    assert len(resultats["by_workspace"]) == 2

    adoption = resultats["reco_adoption"][0]
    # 5 événements en juin (celui de mai est hors fenêtre), 3 suivis, 4 tranchés.
    assert adoption["n_events"] == 5
    assert adoption["n_followed"] == 3
    assert adoption["n_decided"] == 4
    assert float(adoption["adoption_rate_pct"]) == 75.0

    savings = resultats["reco_savings"][0]
    assert savings["n_followed"] == 3
    assert float(savings["savings_eur_min"]) == pytest.approx(0.009)
    assert float(savings["savings_eur_max"]) == pytest.approx(0.042)

    avoided = resultats["footprint_avoided"][0]
    assert float(avoided["avoided_wh_min"]) == pytest.approx(1.6)
    assert float(avoided["avoided_wh_max"]) == pytest.approx(6.4)
    # Fourchette valide (règle n°3) : min <= max.
    assert float(avoided["avoided_wh_min"]) <= float(avoided["avoided_wh_max"])


def test_generation_pdf_de_bout_en_bout(base_test_url, tmp_path):
    """Pipeline complet : le PDF existe et commence par %PDF."""
    sortie = tmp_path / "rapport_demo_2026-06.pdf"
    chemin = generate.run("demo", "2026-06", database_url=base_test_url, out=sortie)
    assert chemin == sortie
    assert chemin.exists()
    assert chemin.stat().st_size > 1000
    assert chemin.read_bytes()[:5] == b"%PDF-"


def test_echec_clair_si_mois_absent(base_test_url, tmp_path):
    """Mois sans agrégat : échec propre avec message explicite (pas de PDF vide)."""
    with pytest.raises(SystemExit, match="monthly_agg est vide"):
        generate.run("demo", "2031-01", database_url=base_test_url, out=tmp_path / "x.pdf")
    assert not (tmp_path / "x.pdf").exists()
