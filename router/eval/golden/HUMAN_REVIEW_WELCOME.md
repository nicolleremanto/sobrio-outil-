# Relecture humaine bienvenue — golden set du routeur

Ce dossier contient le **juge de paix** du routeur Sobrio : 175 scénarios
étiquetés (`golden.jsonl`), générés par gabarits (`generate_golden.py`),
**doublement relus** par deux agents indépendants (ml-architect, eval-scientist)
puis arbitrés — la trace de revue est dans le champ `review` de chaque entrée
et dans `coverage_report.json`.

**Les fondateurs peuvent relire et amender ce set à tout moment** (non
bloquant pour les chantiers en cours) :

1. Modifier le gabarit concerné dans `generate_golden.py` (étiquette `label`,
   justification `note`) — jamais `golden.jsonl` à la main.
2. Régénérer : `.venv/bin/python router/eval/golden/generate_golden.py`.
3. Re-figer : `shasum -a 256 golden.jsonl` → mettre à jour `GOLDEN_SHA256`.
4. Le test `router/tests/test_router_golden_frozen.py` doit rester vert.

Principe d'étiquetage : **le modèle le moins cher qui SUFFIT réellement** à la
tâche décrite par les signaux (sobriété) ; `claude-fable-5` exclu (RFC-0002).
Le set ne contient AUCUN texte de prompt (règle n°1) — uniquement des signaux
numériques et des descriptions abstraites de scénarios.

⚠️ Ce set ne sert JAMAIS à l'entraînement (anti-fuite testée) : il départage
les candidats (gate de promotion, chantier R3).
