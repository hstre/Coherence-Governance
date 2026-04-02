#!/usr/bin/env python3
"""
Coherence Governance for LLM Conversations — Demo Implementation
Based on: Rentschler, H.-S. (2026). Technical Specification v1.0

Pipeline: CAPTURE → VALIDATE → SEAL → RENDER
"""

import re
import sys
import argparse
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# ─── ANSI colors ─────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"

def c(color, text): return f"{color}{text}{RESET}"


# ─── Data Model ───────────────────────────────────────────────────────────────

class Container(str, Enum):
    F  = "F"   # Facts / Canon
    D  = "D"   # Definitions
    R  = "R"   # Rules / Constraints
    H  = "H"   # Hypotheses
    S  = "S"   # Style / Rhetoric
    M1 = "M1"  # Meta-Instructions (patchable)

CONTAINER_NAMES = {
    Container.F:  "Facts/Canon",
    Container.D:  "Definitions",
    Container.R:  "Rules/Constraints",
    Container.H:  "Hypotheses",
    Container.S:  "Style/Rhetoric",
    Container.M1: "Meta-Instructions",
}

class SealLevel(str, Enum):
    NONE      = "none"
    SOFT      = "soft"
    HARD      = "hard"
    MILESTONE = "milestone"

class Status(str, Enum):
    PROPOSED   = "proposed"
    ACTIVE     = "active"
    DEPRECATED = "deprecated"

class Decision(str, Enum):
    OK             = "OK"
    FLAG           = "FLAG"
    BRANCH         = "BRANCH"
    STOP           = "STOP"
    REQUIRE_USER   = "REQUIRE_USER"
    PATCH_REQUIRED = "PATCH_REQUIRED"

DECISION_COLOR = {
    Decision.OK:             GREEN,
    Decision.FLAG:           YELLOW,
    Decision.BRANCH:         CYAN,
    Decision.STOP:           RED,
    Decision.REQUIRE_USER:   YELLOW,
    Decision.PATCH_REQUIRED: YELLOW,
}

@dataclass
class Entry:
    key:       str
    value:     str
    container: Container
    seal:      SealLevel = SealLevel.SOFT
    scope:     str       = "global"
    status:    Status    = Status.ACTIVE
    branch:    str       = "main"
    actor:     str       = "user"

@dataclass
class PatchRecord:
    id:        str
    op:        str
    container: Container
    key:       str
    value:     str
    actor:     str
    decision:  Decision


# ─── Conversation State ───────────────────────────────────────────────────────

@dataclass
class GovernanceState:
    # containers[Container][branch_name][key] = Entry
    containers:    dict = field(default_factory=lambda: {c: {"main": {}} for c in Container})
    current_branch: str = "main"
    branches:      list = field(default_factory=lambda: ["main"])
    patch_counter:  int = 0
    patches:       list = field(default_factory=list)

    # META config (M0 kernel enforced, M1 patchable)
    mode:     str = "analysis"
    conflict: str = "branch"
    seal:     str = "manual"
    risk:     str = "strict"

    def store(self, container: Container, branch: str = None) -> dict:
        branch = branch or self.current_branch
        return self.containers[container].setdefault(branch, {})

    def active_entries(self, branch: str = None) -> list:
        branch = branch or self.current_branch
        result = []
        for cont in Container:
            for e in self.containers[cont].get(branch, {}).values():
                if e.status != Status.DEPRECATED:
                    result.append(e)
        return result

    def next_patch_id(self) -> str:
        self.patch_counter += 1
        return f"P-{date.today().isoformat()}-{self.patch_counter:03d}"

    def create_branch(self, name: str) -> str:
        if name not in self.branches:
            self.branches.append(name)
        src = self.current_branch
        for cont in Container:
            src_store = self.containers[cont].get(src, {})
            self.containers[cont][name] = {
                k: Entry(**vars(v)) for k, v in src_store.items()
            }
        return name


# ─── Layer I: CAPTURE ─────────────────────────────────────────────────────────

def capture(text: str) -> tuple:
    """
    Classify input into epistemic layer.
    Returns (cmd_type, container, key, value, opts).

    cmd_type: "meta" | "patch" | "seal_cmd" | "inline" | "text"
    """
    text = text.strip()

    # @META mode=analysis conflict=branch ...
    m = re.match(r'^@META\s+(.*)', text, re.IGNORECASE)
    if m:
        opts = _parse_opts(m.group(1))
        return ("meta", None, None, m.group(1), opts)

    # @PATCH + F key = value | seal=hard ...
    m = re.match(
        r'^@PATCH\s+([+~\-\^])\s+([A-Z0-9]+)\s+(\S+)\s*(?:=\s*(.+?))?(?:\s*\|\s*(.*))?$',
        text, re.IGNORECASE
    )
    if m:
        op_sym, cont_str, key, value, opts_str = m.groups()
        op = {'+': 'add', '~': 'modify', '-': 'deprecate', '^': 'branch'}[op_sym]
        try:
            container = Container(cont_str.upper())
        except ValueError:
            container = Container.F
        value = (value or "true").strip().strip('"')
        opts = _parse_opts(opts_str or "")
        return ("patch", container, key, value, {"op": op, **opts})

    # @SEAL F,D,R scope=global
    m = re.match(r'^@SEAL\s+(.*)', text, re.IGNORECASE)
    if m:
        return ("seal_cmd", None, None, m.group(1), {})

    # Inline markers: @F, @D, @R, @H, @S
    m = re.match(r'^@([FDRHSM])\s+(.*)', text, re.IGNORECASE)
    if m:
        label = m.group(1).upper()
        content = m.group(2).strip()
        container = Container(label) if label != 'M' else Container.M1
        key = _auto_key(content)
        return ("inline", container, key, content, {"op": "add"})

    return ("text", None, None, text, {})


def _parse_opts(s: str) -> dict:
    opts = {}
    for token in s.split():
        if '=' in token:
            k, v = token.split('=', 1)
            opts[k.strip()] = v.strip()
        else:
            opts[token.strip()] = True
    return opts

def _auto_key(text: str) -> str:
    words = re.sub(r'[^a-zA-Z0-9 ]', '', text.lower()).split()
    return '_'.join(words[:6])


# ─── Layer II: VALIDATE ───────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    decision:     Decision
    tier:         str   # "A-seal" | "A-hierarchy" | "A-collision" | "B" | "C" | "ok"
    evidence:     str   # "strong" | "weak" | "none"
    conflict_key: str   # key of conflicting entry (or "")
    conflict_val: str   # value of conflicting entry (or "")
    reason:       str   # human-readable one-line explanation


def validate(container: Container, key: str, value: str,
             state: GovernanceState, op: str = "add") -> ValidationResult:
    """
    Three-tier validation.

    Tier A  — Hard checks: seal locks, container hierarchy, slot collisions
    Tier B  — Semantic conflict detection (keyword-based approximation)
    Tier C  — Adversarial check: does any existing entry negate this?

    Returns ValidationResult
    """
    store = state.store(container)

    # ── Priority / Lock Rules (before table lookup) ───────────────────────
    # A1: Sealed Lock
    if key in store and op in ("add", "modify"):
        existing = store[key]
        if existing.seal in (SealLevel.HARD, SealLevel.MILESTONE):
            if existing.value != value:
                return ValidationResult(
                    decision=Decision.PATCH_REQUIRED,
                    tier="A-seal",
                    evidence="strong",
                    conflict_key=key,
                    conflict_val=existing.value,
                    reason=f"'{key}' is {existing.seal}-sealed; changes require explicit patch")

    # A2: Container Hierarchy
    if container == Container.R:
        if key in store and store[key].value != value and op == "add":
            existing = store[key]
            return ValidationResult(
                decision=Decision.STOP,
                tier="A-hierarchy",
                evidence="strong",
                conflict_key=key,
                conflict_val=existing.value,
                reason=f"Rule collision on '{key}': '{existing.value}' ≠ '{value}'")

    if container == Container.D:
        if key in store and store[key].value != value and op == "add":
            existing = store[key]
            return ValidationResult(
                decision=Decision.STOP,
                tier="A-hierarchy",
                evidence="strong",
                conflict_key=key,
                conflict_val=existing.value,
                reason=f"Definition drift on '{key}' — use MODIFY patch")

    # ── Tier A: Direct Slot Collision ─────────────────────────────────────
    if key in store and op == "add":
        existing = store[key]
        if existing.status == Status.ACTIVE and existing.value != value:
            evidence = "strong" if container in (Container.F, Container.D, Container.R) else "weak"
            impact   = "high"
            return _decision_from_table(evidence, impact, state,
                                        f"direct key collision on '{key}'",
                                        tier="A-collision",
                                        conflict_key=key,
                                        conflict_val=existing.value)

    # ── Tier B: Semantic Similarity ────────────────────────────────────────
    result = _tier_b_semantic(container, key, value, store, state)
    if result:
        return result

    # ── Tier C: Adversarial Check ─────────────────────────────────────────
    result = _tier_c_adversarial(container, key, value, store, state)
    if result:
        return result

    return ValidationResult(
        decision=Decision.OK,
        tier="ok",
        evidence="none",
        conflict_key="",
        conflict_val="",
        reason="no conflict detected")


# ── Negation heuristic words ──
_NEG = {"no", "not", "never", "cannot", "don't", "doesnt", "isn't",
        "aren't", "without", "lack", "impossible", "false", "zero"}
_STOP_WORDS = {"the", "a", "an", "is", "are", "of", "in", "it", "to",
               "and", "or", "that", "this", "with", "for", "be"}

def _words(text: str) -> set:
    return set(re.sub(r"[^a-z ]", "", text.lower()).split()) - _STOP_WORDS

def _has_negation(words: set) -> bool:
    return bool(words & _NEG)

def _tier_b_semantic(container, key, value, store, state):
    """Tier B: paraphrase comparison with negation detection."""
    if container not in (Container.F, Container.R):
        return None
    v_words = _words(value)
    for k, existing in store.items():
        if existing.status == Status.DEPRECATED:
            continue
        e_words = _words(existing.value)
        shared = v_words & e_words
        if len(shared) >= 2:
            v_neg = _has_negation(v_words)
            e_neg = _has_negation(e_words)
            if v_neg != e_neg:
                impact = "high" if container == Container.F else "med"
                return _decision_from_table(
                    "weak", impact, state,
                    f"semantic negation",
                    tier="B",
                    conflict_key=k,
                    conflict_val=existing.value,
                    shared_words=shared)
    return None

def _tier_c_adversarial(container, key, value, store, state):
    """
    Tier C: Adversarial Validator.
    Looks for minimal counterexamples: entries where the new claim
    would require contradictory silent assumptions.
    """
    if container != Container.F:
        return None
    v_words = _words(value)
    for k, existing in store.items():
        if existing.status == Status.DEPRECATED or k == key:
            continue
        e_words = _words(existing.value)
        # If > 60% of content words overlap but negation polarity differs
        overlap_ratio = len(v_words & e_words) / max(len(v_words), 1)
        if overlap_ratio > 0.5:
            v_neg = _has_negation(v_words)
            e_neg = _has_negation(e_words)
            if v_neg != e_neg:
                return _decision_from_table(
                    "strong", "high", state,
                    f"counterexample found in {container.value}:{k}",
                    tier="C",
                    conflict_key=k,
                    conflict_val=existing.value)
    return None


def _decision_from_table(evidence: str, impact: str,
                          state: GovernanceState, reason: str,
                          tier: str = "B",
                          conflict_key: str = "",
                          conflict_val: str = "",
                          shared_words: set = None) -> ValidationResult:
    """Decision tables B1–B3 from the spec."""
    mode = state.conflict

    if evidence == "strong":
        if mode == "branch":
            decision = Decision.BRANCH
        else:
            decision = Decision.STOP
        return ValidationResult(decision=decision, tier=tier, evidence=evidence,
                                conflict_key=conflict_key, conflict_val=conflict_val,
                                reason=reason)

    if evidence == "weak":
        if impact == "high":
            if mode == "branch":
                decision = Decision.BRANCH
            else:
                decision = Decision.REQUIRE_USER
            return ValidationResult(decision=decision, tier=tier, evidence=evidence,
                                    conflict_key=conflict_key, conflict_val=conflict_val,
                                    reason=reason)
        # med/low impact
        return ValidationResult(decision=Decision.FLAG, tier=tier, evidence=evidence,
                                conflict_key=conflict_key, conflict_val=conflict_val,
                                reason=f"{reason} [tension noted]")

    return ValidationResult(decision=Decision.FLAG, tier=tier, evidence=evidence,
                            conflict_key=conflict_key, conflict_val=conflict_val,
                            reason=reason)


# ─── Layer III: SEAL ──────────────────────────────────────────────────────────

def seal_apply(state: GovernanceState, container: Container, key: str,
               value: str, op: str, decision: Decision,
               opts: dict, actor: str = "user") -> tuple:
    """
    Apply patch if decision allows it.
    Returns (applied: bool, message: str, delta: list[str])
    """
    branch = state.current_branch
    store  = state.store(container)
    delta  = []

    # ── BRANCH: fork the state ────────────────────────────────────────────
    if decision == Decision.BRANCH:
        branch_name = f"Branch_{len(state.branches)}"
        state.create_branch(branch_name)
        new_store = state.store(container, branch_name)
        seal_level = SealLevel(opts.get("seal", "soft"))
        new_store[key] = Entry(key=key, value=value, container=container,
                               seal=seal_level, branch=branch_name,
                               status=Status.ACTIVE, actor=actor)
        state.patches.append(PatchRecord(
            id=state.next_patch_id(), op="branch", container=container,
            key=key, value=value, actor=actor, decision=decision))
        delta.append(f"^BRANCH {branch_name} ← conflict isolated")
        return True, f"Branched as '{branch_name}'", delta

    # ── Blocked decisions ─────────────────────────────────────────────────
    if decision in (Decision.STOP, Decision.REQUIRE_USER, Decision.PATCH_REQUIRED):
        return False, f"Blocked — {decision.value}", delta

    # ── OK / FLAG: apply the patch ─────────────────────────────────────────
    seal_level = SealLevel(opts.get("seal", "soft"))

    if op in ("add", "modify"):
        status = Status.ACTIVE
        store[key] = Entry(key=key, value=value, container=container,
                           seal=seal_level, branch=branch,
                           status=status, actor=actor)
        sym = "+" if op == "add" else "~"
        flag_tag = " [FLAGGED]" if decision == Decision.FLAG else ""
        delta.append(f"{sym}{container.value}:{key} ({seal_level.value}){flag_tag}")

    elif op == "deprecate":
        if key in store:
            store[key].status = Status.DEPRECATED
            delta.append(f"-{container.value}:{key} (deprecated)")

    state.patches.append(PatchRecord(
        id=state.next_patch_id(), op=op, container=container,
        key=key, value=value, actor=actor, decision=decision))

    return True, "Applied", delta


def seal_command(args_str: str, state: GovernanceState) -> list:
    """@SEAL F,D,R scope=global → hard-seal specified containers."""
    parts = args_str.strip().split()
    containers_str = parts[0] if parts else "F,D,R"
    try:
        containers = [Container(s.strip()) for s in containers_str.split(",")]
    except ValueError:
        containers = [Container.F]

    delta = []
    branch = state.current_branch
    for cont in containers:
        for key, entry in state.containers[cont].get(branch, {}).items():
            if entry.status != Status.DEPRECATED:
                entry.seal = SealLevel.HARD
                delta.append(f"@SEAL {cont.value}:{key} → hard")
    return delta


# ─── Layer IV: RENDER ─────────────────────────────────────────────────────────

def render_state(state: GovernanceState) -> str:
    """Project current validated state (RENDER layer)."""
    lines = [c(BOLD, f"\n{'═'*62}")]
    lines.append(c(BOLD, f"  Active State  [{state.current_branch}]  "
                         f"mode={state.mode}  risk={state.risk}"))
    lines.append(c(BOLD, f"{'═'*62}"))

    for cont in [Container.F, Container.D, Container.R,
                 Container.H, Container.S, Container.M1]:
        branch = state.current_branch
        active = {k: v for k, v in state.containers[cont].get(branch, {}).items()
                  if v.status != Status.DEPRECATED}
        if not active:
            continue
        lines.append(c(BLUE, f"\n  [{cont.value}] {CONTAINER_NAMES[cont]}"))
        for key, entry in active.items():
            seal_tag = f" [{entry.seal.value}]" if entry.seal != SealLevel.SOFT else ""
            status_tag = f" ({entry.status.value})" if entry.status == Status.PROPOSED else ""
            lines.append(f"    {c(BOLD, key)} = \"{entry.value}\"{seal_tag}{status_tag}")

    if len(state.branches) > 1:
        lines.append(c(CYAN, f"\n  Branches: {', '.join(state.branches)}"))
        for b in state.branches[1:]:
            lines.append(c(GRAY, f"    [{b}]: diverged state (conflict isolated)"))

    lines.append(c(BOLD, f"{'═'*62}"))
    return "\n".join(lines)


# ─── Main Processing Loop ─────────────────────────────────────────────────────

def process_turn(text: str, state: GovernanceState, turn_num: int) -> list:
    """Single conversation turn: CAPTURE → VALIDATE → SEAL → RENDER."""
    print(c(BOLD, f"\n{'─'*62}"))
    print(c(BOLD, f" Turn {turn_num}") + c(GRAY, f"   branch: {state.current_branch}"))
    print(c(GRAY,  f" Input: {text}"))

    cmd_type, container, key, value, opts = capture(text)

    # ── @META ─────────────────────────────────────────────────────────────
    if cmd_type == "meta":
        print(c(BLUE, " [CAPTURE] META configuration"))
        for k, v in opts.items():
            if hasattr(state, k):
                setattr(state, k, v)
        print(f" META → mode={state.mode}  conflict={state.conflict}  "
              f"seal={state.seal}  risk={state.risk}")
        return []

    # ── @SEAL command ─────────────────────────────────────────────────────
    if cmd_type == "seal_cmd":
        print(c(BLUE, " [CAPTURE] SEAL command"))
        delta = seal_command(value, state)
        for d in delta:
            print(c(GREEN, f"   {d}"))
        if not delta:
            print(c(GRAY, "   (nothing to seal)"))
        return delta

    # ── @PATCH / inline marker ────────────────────────────────────────────
    if cmd_type in ("patch", "inline"):
        op = opts.get("op", "add")
        print(c(BLUE,   f" [CAPTURE]  container={container.value}  op={op}  key={key}"))
        print(c(GRAY,   f"            value=\"{value[:60]}\""))

        print(c(YELLOW, f" [VALIDATE] checking '{key}'..."))

        # M0 kernel: no modifications to M0
        if container == Container.M1 and key.startswith("M0"):
            print(c(RED, " VALIDATE: STOP — M0 kernel is immutable"))
            return []

        vr = validate(container, key, value, state, op)
        decision = vr.decision
        dec_col = DECISION_COLOR.get(decision, RESET)

        # Tier label for display
        tier_labels = {
            "A-seal": "Tier A — sealed lock",
            "A-hierarchy": "Tier A — container hierarchy",
            "A-collision": "Tier A — direct slot collision",
            "B": "Tier B — semantic negation",
            "C": "Tier C — adversarial counterexample",
            "ok": "no conflict",
        }
        tier_label = tier_labels.get(vr.tier, vr.tier)

        print(f" [VALIDATE] {c(dec_col, decision.value)} — {tier_label}")
        if vr.conflict_key:
            print(f"   conflict:  {container.value}:{vr.conflict_key}")
            print(f"              = \"{vr.conflict_val[:80]}\"")
        if vr.tier == "B" and vr.conflict_key:
            # compute shared words for display
            v_words = _words(value)
            e_words = _words(vr.conflict_val)
            shared = v_words & e_words
            if shared:
                print(f"   shared:    {{{', '.join(sorted(shared))}}}")
        impact_str = "high" if vr.tier in ("B", "C", "A-collision") else "n/a"
        if vr.tier != "ok":
            table_ref = {"BRANCH": "Table B3: BRANCH",
                         "STOP": "Table B2: STOP",
                         "FLAG": "Table B1: FLAG",
                         "PATCH_REQUIRED": "Table A1: PATCH_REQUIRED",
                         "REQUIRE_USER": "Table B2: REQUIRE_USER"}.get(decision.value, "")
            print(f"   evidence:  {vr.evidence}  →  impact: {impact_str}  →  {table_ref}")

        applied, msg, delta = seal_apply(state, container, key, value,
                                         op, vr.decision, opts)

        if delta:
            print(c(GREEN, f" [SEAL]    Applied"))
            print(f" StateD: {c(BOLD, '  '.join(delta))}")
        else:
            print(c(RED,   f" [SEAL]    {msg}"))

        if decision == Decision.BRANCH:
            print(c(CYAN, f" Branches now: {state.branches}"))

        return delta

    # ── Plain text ─────────────────────────────────────────────────────────
    if cmd_type == "text":
        print(c(BLUE, " [CAPTURE] plain text — no epistemic marker"))
        print(c(GRAY, " [RENDER]  speaking from active state:"))
        # RENDER: projection only, no new facts generated
        entries = state.active_entries()
        if entries:
            print(f" {c(BOLD, value[:120])}")
            print(c(GRAY, f"   (rendered from {len(entries)} active state entries)"))
        else:
            print(f" {c(BOLD, value[:120])}")
        return []

    return []


# ─── Scenarios ────────────────────────────────────────────────────────────────

SCENARIOS = {
    "silent_overwrite": (
        "Silent Overwriting",
        [
            ("Initialize governance",
             "@META mode=analysis conflict=branch seal=manual risk=strict"),
            ("Hard-seal: no silent overwriting",
             "@PATCH + R no_silent_overwrite = true | seal=hard"),
            ("First fact: pipeline is sequential",
             "@PATCH + F pipeline_order = sequential: each request processed one at a time | seal=soft"),
            ("Contradictory update — same key, different value → triggers BRANCH (Tier A: slot collision)",
             "@PATCH + F pipeline_order = parallel: all requests processed simultaneously"),
            ("Seal all facts globally",
             "@SEAL F scope=global"),
        ]
    ),

    "definition_drift": (
        "Definition Drift",
        [
            ("Initialize governance",
             "@META mode=analysis conflict=stop seal=manual risk=strict"),
            ("Define coherence (first definition)",
             "@PATCH + D coherence = consistent maintenance of claims across turns | seal=hard"),
            ("Redefine coherence — triggers STOP (definition drift)",
             "@PATCH + D coherence = stylistic uniformity in output formatting"),
        ]
    ),

    "rule_violation": (
        "Rule Violation",
        [
            ("Initialize governance",
             "@META mode=analysis conflict=stop seal=manual risk=strict"),
            ("Establish rule (soft seal): conflict_strategy = branch",
             "@PATCH + R conflict_strategy = branch"),
            ("Attempt rule collision on UNSEALED rule → STOP (Tier A2: container hierarchy)",
             "@PATCH + R conflict_strategy = stop"),
            ("Hard-seal the rule (same value, just sealing)",
             "@PATCH ~ R conflict_strategy = branch | seal=hard"),
            ("Attempt change on SEALED rule → PATCH_REQUIRED (Tier A1: sealed lock)",
             "@PATCH ~ R conflict_strategy = prefer | seal=hard"),
        ]
    ),

    "hypothesis_coexistence": (
        "Hypothesis Coexistence",
        [
            ("Initialize governance",
             "@META mode=analysis conflict=branch seal=manual risk=strict"),
            ("Hypothesis 1: memory bottleneck",
             "@H The primary bottleneck is insufficient memory capacity."),
            ("Hypothesis 2: attention limitations — NOT branched (H can coexist)",
             "@H The primary bottleneck is attention mechanism limitations, not memory."),
            ("Hypothesis 3: both factors — coexists with contradictory hypotheses",
             "@H Both memory and attention contribute equally to the bottleneck."),
        ]
    ),

    "appendix_b": (
        "Appendix B Walkthrough",
        [
            ("B.1 — Initialize governance",
             "@META mode=analysis conflict=branch seal=manual risk=strict"),
            ("B.2 — Hard-seal: no silent overwriting",
             "@PATCH + R no_silent_overwrite = true | seal=hard"),
            ("       Add second hard rule",
             "@PATCH + R sealed_requires_patch = true | seal=hard"),
            ("B.3 — Define VALIDATE as Risk Controller",
             "@PATCH + D VALIDATE = Risk Controller | seal=hard"),
            ("B.3 — Introduce fact: LLMs lack explicit state",
             "@F LLMs lose coherence because they have no explicit state."),
            ("B.4 — Contradictory fact → should BRANCH",
             "@F Modern LLMs implicitly do have a stable state."),
            ("       Style preference",
             "@S Use concise analytical language without passive constructions."),
            ("       Hypothesis about solution",
             "@H Explicit state management could reduce coherence failures by 40%."),
            ("B.5 — Try to overwrite a hard-sealed rule → BLOCKED",
             "@PATCH ~ R no_silent_overwrite = false | seal=none"),
            ("B.6 — Seal all facts globally",
             "@SEAL F scope=global"),
            ("       Try to overwrite sealed fact → PATCH_REQUIRED",
             "@PATCH ~ F llms_lose_coherence_because_they_have_no_explicit_state = "
             "LLMs always maintain perfect coherence. | seal=hard"),
            ("       Proper deprecate + replace",
             "@PATCH - F llms_lose_coherence_because_they_have_no_explicit_state "
             "| repl=llms_lack_persistent_state"),
            ("       Plain text output (RENDER layer)",
             "Given the established facts, coherence governance addresses the core "
             "architectural gap in LLM conversation management."),
        ]
    ),
}


# ─── Layer IV: RENDER ─────────────────────────────────────────────────────────

def render_state(state: GovernanceState) -> str:
    """Project current validated state (RENDER layer)."""
    lines = [c(BOLD, f"\n{'═'*62}")]
    lines.append(c(BOLD, f"  Active State  [{state.current_branch}]  "
                         f"mode={state.mode}  risk={state.risk}"))
    lines.append(c(BOLD, f"{'═'*62}"))

    for cont in [Container.F, Container.D, Container.R,
                 Container.H, Container.S, Container.M1]:
        branch = state.current_branch
        active = {k: v for k, v in state.containers[cont].get(branch, {}).items()
                  if v.status != Status.DEPRECATED}
        if not active:
            continue
        lines.append(c(BLUE, f"\n  [{cont.value}] {CONTAINER_NAMES[cont]}"))
        for key, entry in active.items():
            seal_tag = f" [{entry.seal.value}]" if entry.seal != SealLevel.SOFT else ""
            status_tag = f" ({entry.status.value})" if entry.status == Status.PROPOSED else ""
            lines.append(f"    {c(BOLD, key)} = \"{entry.value}\"{seal_tag}{status_tag}")

    if len(state.branches) > 1:
        lines.append(c(CYAN, f"\n  Branches: {', '.join(state.branches)}"))
        for b in state.branches[1:]:
            lines.append(c(GRAY, f"    [{b}]: diverged state (conflict isolated)"))

    lines.append(c(BOLD, f"{'═'*62}"))
    return "\n".join(lines)


def render_all_branches(state: GovernanceState) -> str:
    """Show each branch separately, marking entries that differ from main."""
    lines = []

    # Collect all keys per container for main
    def get_active(branch, cont):
        return {k: v for k, v in state.containers[cont].get(branch, {}).items()
                if v.status != Status.DEPRECATED}

    for branch in state.branches:
        is_active = branch == state.current_branch
        active_tag = "[active]" if is_active else f"[diverged at {_branch_diverge_point(state, branch)}]"

        lines.append(c(BOLD, f"\n{'═'*62}"))
        lines.append(c(BOLD, f"  Branch: {branch:<30} {active_tag}"))
        lines.append(c(BOLD, f"{'═'*62}"))

        for cont in [Container.F, Container.D, Container.R,
                     Container.H, Container.S, Container.M1]:
            active = get_active(branch, cont)
            if not active:
                continue
            lines.append(c(BLUE, f"\n  [{cont.value}] {CONTAINER_NAMES[cont]}"))
            main_active = get_active("main", cont)
            for key, entry in active.items():
                seal_tag = f" [{entry.seal.value}]" if entry.seal != SealLevel.SOFT else ""
                differs = ""
                if branch != "main":
                    main_entry = main_active.get(key)
                    if main_entry is None or main_entry.value != entry.value:
                        differs = c(CYAN, "  ← differs from main")
                lines.append(f"    {c(BOLD, key)} = \"{entry.value}\"{seal_tag}{differs}")

    return "\n".join(lines)


def _branch_diverge_point(state: GovernanceState, branch: str) -> str:
    """Find the key where a branch diverged from main."""
    for cont in Container:
        main_store = state.containers[cont].get("main", {})
        branch_store = state.containers[cont].get(branch, {})
        for key, entry in branch_store.items():
            main_entry = main_store.get(key)
            if main_entry is None or main_entry.value != entry.value:
                return f"{cont.value}:{key}"
    return "unknown"


# ─── Before/After Comparison ──────────────────────────────────────────────────

class NaiveChat:
    def __init__(self): self.log = {}
    def add(self, key, value): self.log[key] = value  # silently overwrites!


def run_before_after():
    print(c(BOLD, f"\n{'═'*62}"))
    print(c(BOLD, "  BEFORE / AFTER: Naive vs. Governance"))
    print(c(BOLD, f"{'═'*62}"))

    sequence = [
        ("architecture_layers", "The architecture has three layers.",
         "statement_1: architecture has three layers"),
        ("architecture_layers", "The architecture has four layers.",
         "statement_2: architecture has FOUR layers  ← contradiction"),
        ("pipeline_order",      "The pipeline order is CAPTURE first.",
         "statement_3: pipeline order is CAPTURE first"),
        ("pipeline_order",      "The pipeline order is RENDER first.",
         "statement_4: pipeline order is RENDER first  ← contradiction"),
    ]

    # ── NAIVE MODE ────────────────────────────────────────────────────────
    print(c(YELLOW, f"\n{'─'*62}"))
    print(c(YELLOW, "  NAIVE MODE  (no governance — dict with silent overwrites)"))
    print(c(YELLOW, f"{'─'*62}"))

    naive = NaiveChat()
    for key, value, desc in sequence:
        print(c(GRAY, f"  + {desc}"))
        naive.add(key, value)

    print(c(RED, "\n  Final naive state (contradictions silently lost):"))
    for k, v in naive.log.items():
        print(f"    {c(BOLD, k)} = \"{v}\"")

    # ── GOVERNANCE MODE ───────────────────────────────────────────────────
    print(c(CYAN, f"\n{'─'*62}"))
    print(c(CYAN, "  GOVERNANCE MODE  (GovernanceState — conflicts detected)"))
    print(c(CYAN, f"{'─'*62}"))

    gov = GovernanceState()
    gov.conflict = "branch"
    gov.risk = "strict"
    turn_num = 1
    for key, value, desc in sequence:
        print(c(GRAY, f"\n  + {desc}"))
        vr = validate(Container.F, key, value, gov, "add")
        decision = vr.decision
        dec_col = DECISION_COLOR.get(decision, RESET)
        print(f"    VALIDATE: {c(dec_col, decision.value)}  — {vr.reason}")
        opts = {}
        seal_apply(gov, Container.F, key, value, "add", decision, opts)
        turn_num += 1

    print(c(GREEN, "\n  Final governance state:"))
    for cont in [Container.F]:
        for branch in gov.branches:
            active = {k: v for k, v in gov.containers[cont].get(branch, {}).items()
                      if v.status != Status.DEPRECATED}
            if active:
                tag = "[active]" if branch == gov.current_branch else "[branched]"
                print(c(BLUE, f"    Branch: {branch}  {tag}"))
                for k, entry in active.items():
                    print(f"      {c(BOLD, k)} = \"{entry.value}\"")

    print(c(GREEN, "\n  Contradictions preserved in branches, not silently overwritten."))
    print(render_all_branches(gov))


# ─── Test Suite ───────────────────────────────────────────────────────────────

TEST_CASES = [
    ("H with no existing entries → OK",
     [],
     (Container.H, "bottleneck", "memory capacity", "add"),
     Decision.OK),

    ("New R (no collision) → OK",
     [],
     (Container.R, "output_mode", "analytical", "add"),
     Decision.OK),

    ("R collision (same key, different value) → STOP",
     [(Container.R, "output_mode", "analytical", "add")],
     (Container.R, "output_mode", "creative", "add"),
     Decision.STOP),

    ("New F (no canon) → OK",
     [],
     (Container.F, "system_type", "stateless LLM", "add"),
     Decision.OK),

    ("F direct key collision → BRANCH",
     [(Container.F, "system_type", "stateless LLM", "add")],
     (Container.F, "system_type", "stateful system", "add"),
     Decision.BRANCH),

    ("Hard-sealed F modify → PATCH_REQUIRED",
     [(Container.F, "fact_x", "original value", "add")],  # then hard-seal it
     (Container.F, "fact_x", "new value", "modify"),
     Decision.PATCH_REQUIRED),

    ("Two contradictory F (semantic) → BRANCH",
     [(Container.F, "coherence_f1", "LLMs have no persistent state and lose coherence over time.", "add")],
     (Container.F, "coherence_f2", "LLMs maintain persistent state and preserve coherence over time.", "add"),
     Decision.BRANCH),

    ("Two contradictory H → OK (hypotheses coexist)",
     [(Container.H, "hyp_1", "memory is the bottleneck not attention", "add")],
     (Container.H, "hyp_2", "attention is the bottleneck not memory", "add"),
     Decision.OK),
]


def run_tests():
    print(c(BOLD, f"\n{'═'*62}"))
    print(c(BOLD, "  Test Suite"))
    print(c(BOLD, f"{'═'*62}"))

    passed = 0
    failed = 0

    for name, setup_ops, test_op, expected_decision in TEST_CASES:
        state = GovernanceState()
        state.conflict = "branch"
        state.risk = "strict"

        # Apply setup operations
        for (cont, key, val, op) in setup_ops:
            vr = validate(cont, key, val, state, op)
            seal_apply(state, cont, key, val, op, vr.decision, {})

        # Special case: hard-seal test
        if name.startswith("Hard-sealed"):
            # After setup, hard-seal the fact_x entry
            store = state.store(Container.F)
            if "fact_x" in store:
                store["fact_x"].seal = SealLevel.HARD

        # Run the test operation
        t_cont, t_key, t_val, t_op = test_op
        vr = validate(t_cont, t_key, t_val, state, t_op)
        got = vr.decision

        if got == expected_decision:
            print(c(GREEN, f" [PASS] {name}"))
            passed += 1
        else:
            print(c(RED,
                    f" [FAIL] {name}"
                    f"  expected={expected_decision.value}"
                    f"  got={got.value}"))
            failed += 1

    print(c(BOLD, f"\n Tests: {passed} passed, {failed} failed"))
    return failed == 0


# ─── Scenario Runner ──────────────────────────────────────────────────────────

def run_scenario(name: str):
    if name not in SCENARIOS:
        print(c(RED, f" Unknown scenario '{name}'. Available: {', '.join(SCENARIOS)}"))
        return

    title, steps = SCENARIOS[name]
    state = GovernanceState()

    print(c(BOLD, f"\n{'═'*62}"))
    print(c(BOLD, f"  SCENARIO: {title}"))
    print(c(BOLD, f"{'═'*62}"))

    for turn_num, (description, command) in enumerate(steps, 1):
        print(c(GRAY, f"\n ▸ {description}"))
        process_turn(command, state, turn_num)

    print(render_state(state))

    if len(state.branches) > 1:
        print(render_all_branches(state))

    # Special post-run note for hypothesis_coexistence
    if name == "hypothesis_coexistence":
        print(c(GREEN, "\n  Note: all three H entries coexist — none were branched or blocked."))
        h_store = state.containers[Container.H].get("main", {})
        print(c(GREEN, f"  H entries in main branch: {len(h_store)}"))
        for k, e in h_store.items():
            if e.status != Status.DEPRECATED:
                print(c(GREEN, f"    {k}: \"{e.value}\""))


def run_all_scenarios():
    for name in SCENARIOS:
        run_scenario(name)
        print()


# ─── Entry Points ─────────────────────────────────────────────────────────────

def print_banner():
    print(c(BOLD, """
╔══════════════════════════════════════════════════════════════╗
║   Coherence Governance for LLM Conversations                ║
║   Demo Implementation  —  v1.0                              ║
║   Rentschler, H.-S. (2026)                                  ║
╠══════════════════════════════════════════════════════════════╣
║   Pipeline:  CAPTURE → VALIDATE → SEAL → RENDER             ║
║   Epistemic layers:  F  D  R  H  S  M1                      ║
╚══════════════════════════════════════════════════════════════╝"""))


def run_interactive(state: GovernanceState):
    print(c(BOLD, "\n── Interactive Mode ─────────────────────────────────────────"))
    print(c(GRAY, " Supported commands:"))
    print(c(GRAY, "   @META mode=analysis conflict=branch seal=manual risk=strict"))
    print(c(GRAY, "   @PATCH + R key = value | seal=hard"))
    print(c(GRAY, "   @F/@D/@R/@H/@S <statement>  (inline markers)"))
    print(c(GRAY, "   @SEAL F,D,R scope=global"))
    print(c(GRAY, "   state   — show current state"))
    print(c(GRAY, "   branches — show all branches"))
    print(c(GRAY, "   quit    — exit\n"))

    turn_num = 100
    while True:
        try:
            text = input(c(BOLD, ">> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break
        if text.lower() in ("state", "show"):
            print(render_state(state))
            continue
        if text.lower() in ("branches", "branch"):
            print(render_all_branches(state))
            continue
        turn_num += 1
        process_turn(text, state, turn_num)


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="Coherence Governance Demo",
        add_help=True)
    parser.add_argument("--scenario", metavar="NAME",
                        help="Run one scenario: "
                             "silent_overwrite, definition_drift, rule_violation, "
                             "hypothesis_coexistence, appendix_b")
    parser.add_argument("--before-after", action="store_true",
                        help="Run before/after comparison")
    parser.add_argument("--test", action="store_true",
                        help="Run test suite")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Interactive mode")
    parser.add_argument("-di", "--demo-interactive", action="store_true",
                        help="All scenarios + interactive mode")

    args = parser.parse_args()

    if args.test:
        run_tests()
    elif args.before_after:
        run_before_after()
    elif args.scenario:
        run_scenario(args.scenario)
    elif args.interactive:
        state = GovernanceState()
        run_interactive(state)
    elif args.demo_interactive:
        run_all_scenarios()
        state = GovernanceState()
        run_interactive(state)
    else:
        # Default: run all scenarios
        run_all_scenarios()
        print(c(GRAY, "\n Run with --help for options: "
                      "--scenario NAME, --before-after, --test, -i, -di"))


if __name__ == "__main__":
    main()
