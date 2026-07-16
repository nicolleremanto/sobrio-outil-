"""Logs structurés JSON (stdlib uniquement) SANS contenu de prompt.

RÈGLE n°1 (non négociable) : jamais de contenu de prompt loggé — ni en base,
ni dans les logs, ni dans un tracker d'erreurs. Ce module encode la règle :

- un filtre de scrubbing supprime toute clé de type contenu (`prompt_text`,
  `text`, `content`, `body`, ...) passée par erreur dans les `extra` ;
- aucun middleware de log du corps des requêtes n'est activé, nulle part.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

# Clés interdites dans les extra de logs : tout champ texte libre susceptible
# de contenir du contenu utilisateur. Liste volontairement large.
_FORBIDDEN_KEYS = frozenset(
    {"prompt_text", "prompt", "text", "content", "body", "payload", "raw", "message_text"}
)

# Attributs standard d'un LogRecord (à ne pas sérialiser comme extra).
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
    | {"message", "asctime", "taskName"}
)


class ContentScrubFilter(logging.Filter):
    """Supprime des `extra` toute clé pouvant contenir du contenu de prompt.

    Garde-fou de dernier recours : le code applicatif ne doit JAMAIS logger
    de texte libre ; si une clé interdite arrive quand même, elle est
    remplacée par un marqueur, jamais émise.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__.keys()):
            if key in _STANDARD_ATTRS:
                continue
            if key in _FORBIDDEN_KEYS or "prompt" in key.lower():
                record.__dict__[key] = "[scrubbé — règle n°1]"
        return True


class JsonFormatter(logging.Formatter):
    """Formateur JSON minimal : horodatage, niveau, logger, message, extra."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                entry[key] = value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure le logger racine : sortie JSON + filtre de scrubbing.

    Idempotent (réutilise le handler existant si déjà configuré).
    """
    root = logging.getLogger()
    root.setLevel(level)
    scrub = ContentScrubFilter()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(scrub)
        root.addHandler(handler)
    # Le filtre est aussi posé sur le logger racine lui-même pour couvrir les
    # appels directs à logging.getLogger().log(...) (le filtre de handler
    # couvre déjà tous les enregistrements propagés).
    if not any(isinstance(f, ContentScrubFilter) for f in root.filters):
        root.addFilter(scrub)
