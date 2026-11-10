# Milestone 9: Open-source AI layer

Completed 10 November 2026.

## What was built

- **Retrieval and deterministic briefs** (`backend/connectly/ai/brief.py`, `POST /api/v1/intelligence/brief`).
  - Evidence items are numbered.
  - The brief has ten sections. Each statement is tagged as fact, derived, recommendation or data gap, and cites its evidence ids.
  - An optional question runs PostgreSQL full-text search over claims, data gaps and the directory.
- **Optional self-hosted model.** The `none`, `ollama` and `openai_compatible` providers are configured through environment variables. No paid API is used and none is needed.
- **Summary validator.** A model's summary is accepted only if:
  - every sentence cites evidence that exists;
  - every number appears in the evidence that sentence cites.

  Anything else is discarded with the reasons. An accepted summary is labelled AI-generated. The model is never called when evidence is insufficient.
- **Status endpoint** (`GET /api/v1/intelligence/status`), which reports whether a model is configured without calling it.
- **Intelligence page.** Choose an area picker and sector, optionally add a question and an AI summary. The brief shows citation links to a numbered evidence list, with value types, verification and sources.
- **Documentation:** `docs/ai.md`.

## Tests

- **Backend:** 146 tests pass (9 new). They cover:
  - the brief's sections, and that every non-gap statement cites evidence that exists;
  - adoption barriers derived from indicator thresholds;
  - full-text search hits;
  - summaries with a stand-in model: accepted, uncited, nonexistent id, invented number;
  - provider errors, disabled and insufficient evidence;
  - number normalisation;
  - provider selection, and refusal of unknown providers;
  - the API.
- **Browser walkthrough** of the intelligence page for Bille ward (healthcare): it shows the loaded facts, data gaps and search results about mobile money agents.

## Not verified here

No live model was run, because the build environment cannot reach Ollama. See `docs/ai.md` for the local check.
