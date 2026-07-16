# API Sobrio — Lot B. Contexte de build = RACINE du repo (cf. docker-compose.dev.yml).
# Le compose monte ./api et ./warehouse en volumes par-dessus pour le reload.
FROM python:3.12-slim

COPY contracts/ /repo/contracts/
COPY warehouse/ /repo/warehouse/
COPY api/ /repo/api/

RUN pip install --no-cache-dir -r /repo/api/requirements.txt -e /repo/warehouse

WORKDIR /repo/api
EXPOSE 8000

# RÈGLE n°5 : aucun secret dans l'image — tout vient de l'environnement.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
