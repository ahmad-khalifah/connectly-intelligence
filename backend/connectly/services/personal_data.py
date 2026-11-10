"""Guard against personal data about community members entering free-text fields.

Connectly stores facts about places, never about individual residents. Free text that
contains a phone number or e-mail address is refused. Names cannot be detected reliably,
so the entry forms also state the rule.
"""

import re

_PATTERNS = {
    "a phone number": re.compile(
        r"(?<!\d)(?:\+?234[\s-]?|0)[789][01]\d(?:[\s-]?\d){7}(?!\d)"  # Nigerian mobile
        r"|(?<!\d)\+\d[\d\s-]{8,}\d(?!\d)"  # any international number
    ),
    "an e-mail address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
}


def personal_data_found(*texts: str | None) -> list[str]:
    found = []
    for label, pattern in _PATTERNS.items():
        if any(t and pattern.search(t) for t in texts):
            found.append(label)
    return found
