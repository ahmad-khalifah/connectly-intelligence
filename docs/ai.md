# AI layer

Connectly Intelligence does not depend on a language model. Every score, match, market entry
finding and brief is computed from the database by documented rules (`docs/methodology.md`).
A language model is optional, and is used for one thing only: a short summary of the evidence
in an intelligence brief.

## How a brief is built

The architecture is retrieval first, generation optional (`backend/connectly/ai/brief.py`).

1. **Retrieval.** The platform gathers numbered evidence items (E1, E2...) from its own
   database for the chosen area and sector:
   - profile values, and state or LGA values labelled as context;
   - facility counts, or the fact that no facility data covers the state;
   - gap-score statements from the needs assessment;
   - solutions from the matching engine;
   - community claims;
   - recorded data gaps.

   If the user asks a question, PostgreSQL full-text search (English stemming, any word)
   also searches community claims, data gaps and the published directory. No external
   service is involved.
2. **Deterministic brief.** The brief's ten sections (profile, infrastructure, service gaps,
   beneficiary groups, adoption barriers, solutions, opportunities, data limitations,
   confidence, sources) are assembled by fixed rules. Every statement cites its evidence ids
   and is tagged as *fact*, *derived*, *recommendation* or *data gap*.
3. **Optional summary.** If a model is configured, it receives only the numbered evidence and
   is instructed to cite it. Its reply is **checked before it is shown**:
   - every sentence must cite at least one evidence id, and every id must exist;
   - every number in a sentence must appear in the evidence that sentence cites (thousands
     separators and trailing zeros are normalised).

   A failing reply is discarded and the reasons are listed. An accepted reply is labelled
   *AI-generated* with the model name.

   The model is not called at all when the area has no sector evidence beyond population;
   the page says the evidence is insufficient instead.

## Configuration (free, self-hosted)

| Variable | Values |
| --- | --- |
| `CONNECTLY_AI_PROVIDER` | `none` (default), `ollama`, `openai_compatible` |
| `CONNECTLY_AI_BASE_URL` | e.g. `http://localhost:11434` (Ollama) or `http://localhost:8080` (llama.cpp server) |
| `CONNECTLY_AI_MODEL` | e.g. `llama3.1:8b`, `qwen2.5:7b`, `mistral` |
| `CONNECTLY_AI_API_KEY` | only if your local server requires one |

With Ollama:

```bash
# install from https://ollama.com (free), then:
ollama pull llama3.1:8b
# in backend/.env
CONNECTLY_AI_PROVIDER=ollama
CONNECTLY_AI_MODEL=llama3.1:8b
```

Restart the API. The Intelligence page then offers "Add an AI summary".

**Do not point `CONNECTLY_AI_BASE_URL` at a hosted API that charges.** The project's budget
rules exclude paid APIs; the `openai_compatible` option exists for local servers that use that
API shape.

## What was and was not tested here

The build environment cannot reach Ollama or model downloads, so no live model was run. The
provider clients are simple HTTP calls. The following are covered by tests with a stand-in
model:

- the validation rules: accepted, uncited, unknown id and invented-number replies;
- provider errors;
- the "disabled" and "insufficient evidence" paths.

Run a live check after installing Ollama.
