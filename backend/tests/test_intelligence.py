from dataclasses import dataclass

import pytest

from connectly.ai import brief as B
from connectly.ai.providers import ProviderError, get_provider
from connectly.core.config import Settings
from tests.test_matching import m  # noqa: F401


@dataclass
class Fake:
    reply: str | Exception
    name: str = "fake"
    model: str = "fake-model"

    def complete(self, system, user):
        assert "[E1]" in user and "Use only the numbered evidence" in system
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def brief(m, session):
    return B.build_brief(session, m["ids"]["West North"], "health", question="Hausa speakers")


def section(b, key):
    return next(s["statements"] for s in b["sections"] if s["key"] == key)


def test_brief_sections_cite_evidence(brief):
    keys = [s["key"] for s in brief["sections"]]
    assert keys[:11] == [
        "profile",
        "infrastructure",
        "gaps",
        "beneficiaries",
        "barriers",
        "solutions",
        "opportunities",
        "research",
        "limitations",
        "confidence",
        "sources",
    ]
    ids = {e["id"] for e in brief["evidence"]}
    for s in brief["sections"]:
        for st in s["statements"]:
            assert st["kind"] in {"fact", "derived", "recommendation", "gap"}
            assert set(st["cites"]) <= ids
            if st["kind"] != "gap" and s["key"] != "confidence":
                assert st["cites"], st
    assert section(brief, "profile")[0]["kind"] == "gap"  # no population loaded for synthetic LGAs
    assert "1 health facilities" in section(brief, "infrastructure")[0]["text"]
    barriers = " ".join(x["text"] for x in section(brief, "barriers"))
    assert "mobile phone ownership" in barriers and "electricity access" in barriers
    assert "SMS Clinic" in section(brief, "solutions")[0]["text"]
    assert section(brief, "opportunities")[0]["kind"] == "recommendation"
    assert "Hausa" in section(brief, "related")[0]["text"]  # full-text search hit on the claim
    assert brief["sufficient_evidence"]


def _good(brief):
    gap = next(e for e in brief["evidence"] if e["kind"] == "gap_score")
    phone = next(e for e in brief["evidence"] if "mobile phone" in e["text"])
    return gap["id"], phone["id"]


def test_narrative_accepted_when_fully_supported(brief):
    g, p = _good(brief)
    reply = (
        f"West North has fewer health facilities than comparable LGAs [{g}]. "
        f"About 60% of households own a mobile phone [{p}]."
    )
    out = B.narrative(brief, Fake(reply))
    assert out["status"] == "accepted" and out["value_type"] == "ai_generated"


@pytest.mark.parametrize(
    "reply, problem",
    [
        ("Health access is poor here.", "uncited sentence"),
        ("Health access is poor here [E999].", "does not exist"),
        ("{phone_sentence_with_invented_number}", "numbers not in the cited evidence"),
    ],
)
def test_narrative_rejected(brief, reply, problem):
    _, p = _good(brief)
    reply = reply.replace(
        "{phone_sentence_with_invented_number}", f"85% of households own a phone [{p}]."
    )
    out = B.narrative(brief, Fake(reply))
    assert out["status"] == "rejected" and out["text"] is None
    assert any(problem in x for x in out["problems"])


def test_narrative_disabled_error_and_insufficient(brief, m, session):
    assert B.narrative(brief, None, use_default=False)["status"] == "disabled"
    assert B.narrative(brief, Fake(ProviderError("down")))["status"] == "error"
    thin = B.build_brief(session, m["ids"]["East North"], "agriculture")
    assert not thin["sufficient_evidence"]
    assert B.narrative(thin, Fake("unused"))["status"] == "insufficient"


def test_numbers_normalised():
    ev = [{"id": "E1", "text": "Population: 12,867 (95% interval 8,342 to 19,288)."}]
    assert B.validate_narrative("About 12867 people live here [E1].", ev) == []
    assert B.validate_narrative("The interval is 8,342 to 19,288 [E1].", ev) == []
    assert B.validate_narrative("About 13,000 people live here [E1].", ev)


def test_provider_selection():
    assert get_provider(Settings(ai_provider="none")) is None
    assert get_provider(Settings(ai_provider="ollama")).name == "ollama"
    assert get_provider(Settings(ai_provider="openai_compatible")).name == "openai_compatible"
    with pytest.raises(ProviderError):
        get_provider(Settings(ai_provider="paid-cloud"))


def test_api(m):
    c, h = m["c"], m["h"]
    assert c.get("/api/v1/intelligence/status", headers=h).json()["enabled"] is False
    r = c.post(
        "/api/v1/intelligence/brief",
        headers=h,
        json={"area_id": m["ids"]["West North"], "sector": "health"},
    )
    assert r.status_code == 200 and r.json()["narrative"]["status"] == "disabled"
    assert (
        c.post(
            "/api/v1/intelligence/brief", headers=h, json={"area_id": 999999, "sector": "health"}
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/api/v1/intelligence/brief",
            headers=h,
            json={"area_id": m["ids"]["Testland"], "sector": "health"},
        ).status_code
        == 422
    )
