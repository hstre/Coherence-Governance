# Coherence-Governance
Epistemic layer architecture for coherence-enforced LLM conversations. Four-layer state discipline: CAPTURE → VALIDATE → SEAL → RENDER.
# Coherence Governance for LLM Conversations

**A four-layer architecture with state discipline**  
*Technical Specification v1.0 — Hanns-Steffen Rentschler, February 2026*

-----

## The Problem

Large Language Models process conversations as unstructured text streams — without persistent state. Coherence in long dialogues is therefore a statistical byproduct, not a guaranteed system property.

Three failure classes dominate:

- **Silent Overwriting** — a new statement implicitly replaces an earlier one without the contradiction being detected or documented
- **Coherence Theater** — eloquent but internally contradictory output that appears superficially consistent
- **Layer Conflation** — facts, hypotheses, style decisions, and rules compete undifferentiated for influence

## The Architecture

Coherence Governance introduces a strict top-down processing pipeline with four sequential layers:

```
CAPTURE → VALIDATE → SEAL → RENDER
```

**Fundamental Invariant:** Nothing downstream may decide what upstream has not permitted. RENDER may only speak from the currently active state. The state may only change through explicit patches.

### Layer I — CAPTURE

Epistemic classification of every input into one of six layers:

|Label|Layer              |Description                                    |
|-----|-------------------|-----------------------------------------------|
|F    |Facts / Canon      |Secured, binding statements                    |
|D    |Definitions        |Term definitions that serve as anchors         |
|R    |Rules / Constraints|Restrictions governing system behavior         |
|H    |Hypotheses         |Working hypotheses, exploratory, revocable     |
|S    |Style / Rhetoric   |Tonality, formatting preferences               |
|M    |Meta-Instructions  |Governance level: how the system should operate|

### Layer II — VALIDATE

Operates not on content but on state. Checks whether new inputs are compatible with the existing state via three tiers:

- **Tier A — Hard Checks:** Deterministic slot collision, scope, and constraint violations
- **Tier B — Semantic Entailment:** Multi-pass contradiction detection with uncertainty budget
- **Tier C — Adversarial Validator:** A second process deliberately attempts to find counterexamples

Result is never text — always a decision: `OK | CONFLICT | AMBIGUOUS | REQUIRES USER DECISION`

### Layer III — SEAL

Binding state changes through four explicit operations only:

- `ADD` — new entry (proposed → active)
- `MODIFY` — targeted change with justification and compat classification
- `DEPRECATE` — invalidate without deleting (history remains visible)
- `BRANCH` — clean fork when contradictions need to coexist

No silent overwriting. No implicit forgetting.

### Layer IV — RENDER

Output generation — exclusively a projection of the currently active, validated state. RENDER may not generate new facts. Uncertainty is explicitly marked.

-----

## Patch DSL

State changes use a minimal formal syntax:

```yaml
op:        add | modify | deprecate | branch
container: F | D | R | H | S | M
key:       subject::predicate::object#qualifiers
scope:     local | block:<n> | global
seal:      none | soft | hard | milestone
```

**Chat shorthand:**

```
@META mode=analysis conflict=branch seal=manual risk=strict

@PATCH + R no_silent_overwrite = true | seal=hard
@PATCH + D VALIDATE = "Risk Controller" | seal=hard
@PATCH ~ F pipeline_order = "new value" | seal=hard ev=user
@PATCH - F pipeline_order | repl=pipeline_order_v2
@PATCH ^ P VariantB | at=pipeline_order copy=shallow
```

**Inline epistemic markers:**

```
@F The earth is round        → patched as proposed fact
@R No passive constructions  → patched as rule
@H Maybe X is the case       → stored as hypothesis
@SEAL F,D,R scope=global     → hard-seal all active canon
```

-----

## What This Is Not

The framework explicitly does **not** solve:

- Intentional hallucinations (it enforces traceability, not truth)
- Malicious user patches (it protects against implicit errors, not authorized ones)
- Cross-conversation coherence (state is conversation-local by design)
- Moral or normative correctness (it regulates coherence, not values)

-----

## Differentiation

|Approach                            |Focus                                   |Gap                                 |
|------------------------------------|----------------------------------------|------------------------------------|
|StateFlow / StateLM                 |State machines for task execution       |No epistemic layer separation       |
|MemoryBank, GOLF                    |Memory via retrieval + forgetting curves|No state validation, no patch system|
|NeMo Guardrails                     |Input/output safety filtering           |No content coherence across turns   |
|Structured Cognitive Loop (Kim 2025)|Agent action governance                 |Not epistemic; no F/D/R/H layers    |

Novel contribution: epistemic layer separation as a governance primitive, top-down validation before every output, and explicit patch operations as conversation version control.

-----

## Status

- [x] Formal specification (v1.0)
- [x] Patch DSL with four operations
- [x] Three-tier VALIDATE architecture
- [x] Chat mode with @META / @PATCH / inline markers
- [x] Threat model and non-goals
- [x] Annotated walkthrough (Appendix B)
- [ ] Reference implementation (next step)

-----

## Related Work

Part of a broader epistemic infrastructure program:

- [Alexandria Protocol](https://github.com/hstre/Alexandria-Protokoll) — tamper-proof knowledge infrastructure for AI agent societies
- [Alexandria Semantic Projection Layer](https://github.com/hstre/Alexandria-Semantic-Projection-Layer) — NLP backend for semantic claim matching
- Persistent Epistemic Supervisor (PES) — SSRN Abstract ID 6272258

-----

## License

© Hanns-Steffen Rentschler, 2026. All rights reserved.
