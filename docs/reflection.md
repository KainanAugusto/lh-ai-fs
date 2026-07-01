# Reflection — design decisions & tradeoffs

## What I built

A 5-agent pipeline with **typed contracts between every stage** (Pydantic, see
[`backend/schemas.py`](../backend/schemas.py)) — agents never hand each other raw text:

1. **Extractor** — pulls citations + factual claims from the MSJ. Extraction only, no judgment.
2. **Citation Verifier** — assesses whether each authority supports its proposition and whether quotes are accurate.
3. **Consistency Checker** — cross-checks the MSJ's facts against the police report, medical records, and witness statement.
4. **Confidence Scorer** — assigns calibrated confidence and ranks all flags.
5. **Judicial Memo** — synthesizes the top findings into one paragraph for a judge.

Orchestration ([`backend/pipeline.py`](../backend/pipeline.py)) runs agents 2 and 3 concurrently and
degrades gracefully — a failing agent becomes an entry in `report.errors`, never a 500.

## Decisions and why

- **Grounding everything in verbatim quotes.** Every consistency finding carries the exact text from the
  source document, and every citation flag carries the exact MSJ text. This is what makes the output
  trustworthy and what makes the **deterministic hallucination metric** possible (substring-check the
  quote against the source — no LLM judge needed). This was a deliberate, central choice, reinforced by
  feedback during the build.
- **"Unverifiable" over guessing.** The verifier is told that if it cannot confirm a case exists or what
  it holds, it must return `unverifiable` — asserting a conclusion without the precedent is itself
  fabrication. This visibly fixed a real failure: the six fictional footnote cases went from being
  falsely labeled `overstated` to correctly `unverifiable`.
- **Confidence by evidence strength.** The scorer weights findings anchored to verbatim document
  evidence (high) above citation verdicts that rely on the model's legal knowledge (low). So the
  strongest, most defensible findings naturally rise to the top.
- **Provider-agnostic LLM layer.** The code uses the OpenAI SDK but is fully `.env`-driven
  ([`backend/config.py`](../backend/config.py)), so it ran on Google Gemini's tier during
  development while reviewers can run it on OpenAI with zero code changes.
- **Plain-Python orchestration**, not a framework (LangGraph/etc.). For a 5-agent DAG, explicit
  `asyncio` is more transparent, has zero extra dependencies, and is easier to defend in review.
- **Batched citation verification** (one call for all citations) to conserve model quota, at a small
  cost to per-citation isolation.

## The honest limitation

**Citation verification has no real source of truth.** Without the actual opinions, the
`supports`/`overstated` verdicts rest on the model's parametric legal knowledge. The design mitigates
this (force `unverifiable` when unsure; down-weight such verdicts in scoring) but does not remove it.
This is exactly why the **cross-document consistency findings are the product's strongest output** —
they are grounded in real document text — and why the production plan's #1 quality investment is
integrating an authoritative case-law source (CourtListener / commercial). I'd rather ship a tool that
says "could not verify" honestly than one that fabricates confident holdings.

## Eval approach

Golden set of 6 hand-annotated defects with documented origins
([`backend/evals/golden.json`](../backend/evals/golden.json)). Three metrics, chosen for honesty:
- **Recall** — keyword-"signal" matching, robust to the LLM's wording drift between runs.
- **Precision (golden lower bound)** — labeled as a lower bound, because the brief has more real issues
  than the 6 curated ones, so genuine extra flags count against it. I preferred an honest lower bound to
  an inflated number.
- **Hallucination rate** — fully deterministic (verbatim grounding), no LLM judge.

Current results: **recall 100% (6/6), precision 82% lower-bound, hallucination 0%** on
`gemini-2.5-flash`. The 0% is the one I care about most — every flag is backed by text that actually
appears in the documents.

**Model choice is itself a measurable quality lever.** Running the same pipeline on the weaker
`gemini-2.5-flash-lite` dropped it to recall 83% / hallucination 17% — the lite model spliced two
non-contiguous passages of the police report into one "verbatim" quote, which the deterministic
grounding check caught immediately. That single experiment is the best argument for both the eval
(it surfaced a real regression) and the production plan's emphasis on eval gates before any model swap.

A note on determinism: Gemini is not perfectly deterministic even at `temperature=0`, so finding counts
vary slightly run-to-run; the signal-based eval is designed to absorb that. One eval refinement came out
of this: quotes where the model *declines* to quote (e.g. literally "Not specified in the brief.") are
treated as "no quote", not as fabrications — only quotes that look real but aren't in the source count
against the hallucination rate.

## Hardening (making the prototype production-lean)

A few reliability lessons surfaced while running the pipeline across five providers (OpenAI-compatible:
Gemini, Groq, OpenRouter, SiliconFlow):

- **The grounding check moved from eval-only to a runtime guardrail** ([`backend/grounding.py`](../backend/grounding.py)):
  findings whose quote is not verbatim in the source are dropped/stripped *before* the report is built.
  "Nothing invented" is now enforced live, not just measured — and the eval imports the same check, so
  there is one definition of "grounded".
- **Failure is explicit.** A required-stage failure returns `status: "failed"` (never an empty
  "no issues" report); a downstream failure returns `partial`. The UI keys off `status`, so a rate-limit
  or timeout can't masquerade as a clean bill of health — the dangerous false negative for a BS detector.
- **`max_tokens` must not be forced on reasoning models.** Setting a high ceiling made `gemini-2.5-flash`
  think up to it and blow past the request timeout; leaving it unset (provider default) kept it fast.
  The setting is now env-configurable and off by default. Small config choices have outsized latency/cost
  effects on thinking models.

## What I'd do differently / next

- Integrate a real case-law source so citation verdicts are grounded, not parametric (top priority).
- Store character offsets for each evidence quote to enable UI deep-linking into the document.
- Add an LLM-judge as a *secondary* precision metric to complement the keyword recall matcher.
- Expand the golden set and add adversarial cases (prompt-injection in a document).
- Chunking/streaming for matters far larger than this 4-document sample.

## Time

Built incrementally in six verified steps (foundations → agents 1–3 → agents 4–5 + orchestration →
eval harness → frontend → docs), each tested before moving on. Implementation landed roughly within the
recommended ~6h pipeline + ~2–3h plan timebox; the deliberate extra investment went into the
grounding/anti-hallucination posture and the eval honesty, which is where this product lives or dies.
