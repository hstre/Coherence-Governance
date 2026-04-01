#!/usr/bin/env python3
"""
Coherence Governance for LLM Conversations — Demo Implementation
Based on: Rentschler, H.-S. (2026). Technical Specification v1.0

Pipeline: CAPTURE → VALIDATE → SEAL → RENDER
"""

import re
import sys
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

def validate(container: Container, key: str, value: str,
             state: GovernanceState, op: str = "add") -> tuple:
    """
    Three-tier validation.

    Tier A  — Hard checks: seal locks, container hierarchy, slot collisions
    Tier B  — Semantic conflict detection (keyword-based approximation)
    Tier C  — Adversarial check: does any existing entry negate this?

    Returns (Decision, reason_str)
    """
    store = state.store(container)

    # ── Priority / Lock Rules (before table lookup) ───────────────────────
    # A1: Sealed Lock
    if key in store and op in ("add", "modify"):
        existing = store[key]
        if existing.seal in (SealLevel.HARD, SealLevel.MILESTONE):
            if existing.value != value:
                return (Decision.PATCH_REQUIRED,
                        f"'{key}' is {existing.seal}-sealed; changes require explicit patch")

    # A2: Container Hierarchy
    if container == Container.R:
        if key in store and store[key].value != value and op == "add":
            return (Decision.STOP,
                    f"Rule collision on '{key}': '{store[key].value}' ≠ '{value}'")

    if container == Container.D:
        if key in store and store[key].value != value and op == "add":
            return (Decision.STOP,
                    f"Definition drift on '{key}' — use MODIFY patch")

    # ── Tier A: Direct Slot Collision ─────────────────────────────────────
    if key in store and op == "add":
        existing = store[key]
        if existing.status == Status.ACTIVE and existing.value != value:
            evidence = "strong" if container in (Container.F, Container.D, Container.R) else "weak"
            impact   = "high"
            return _decision_from_table(evidence, impact, state,
                                        f"direct key collision on '{key}'")

    # ── Tier B: Semantic Similarity ────────────────────────────────────────
    result = _tier_b_semantic(container, key, value, store, state)
    if result:
        return result

    # ── Tier C: Adversarial Check ─────────────────────────────────────────
    result = _tier_c_adversarial(container, key, value, store, state)
    if result:
        return result

    return (Decision.OK, "no conflict detected")


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
                    f"semantic tension with {container.value}:{k} "
                    f"('{existing.value[:50]}')")
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
                    f"[Tier C] counterexample found in {container.value}:{k}")
    return None


def _decision_from_table(evidence: str, impact: str,
                          state: GovernanceState, reason: str) -> tuple:
    """Decision tables B1–B3 from the spec."""
    mode = state.conflict
    risk = state.risk

    if evidence == "strong":
        if mode == "branch":
            return (Decision.BRANCH, reason)
        return (Decision.STOP, reason)

    if evidence == "weak":
        if impact == "high":
            if mode == "branch":
                return (Decision.BRANCH, reason)
            return (Decision.REQUIRE_USER, reason)
        # med/low impact
        return (Decision.FLAG, f"{reason} [tension noted]")

    return (Decision.FLAG, reason)


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

        decision, reason = validate(container, key, value, state, op)
        dec_col = DECISION_COLOR.get(decision, RESET)
        print(f" VALIDATE: {c(dec_col, decision.value)}  — {reason}")

        applied, msg, delta = seal_apply(state, container, key, value,
                                         op, decision, opts)

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


# ─── Demo Scenario (Appendix B + extended) ───────────────────────────────────

DEMO_SCENARIO = [
    # Appendix B walkthrough
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


def run_demo(state: GovernanceState):
    print(c(CYAN, "\n Running Appendix B walkthrough + extended scenarios\n"))
    for turn_num, (description, command) in enumerate(DEMO_SCENARIO, 1):
        print(c(GRAY, f" ▸ {description}"))
        process_turn(command, state, turn_num)

    print(render_state(state))

    print(c(BOLD, f"\n{'─'*62}"))
    print(c(BOLD, f" Patch Log  ({len(state.patches)} recorded)"))
    for p in state.patches:
        col = DECISION_COLOR.get(p.decision, RESET)
        print(f"   {c(GRAY, p.id)}  {p.op:10s}  "
              f"{p.container.value}:{p.key[:35]:<35}  {c(col, p.decision.value)}")


def run_interactive(state: GovernanceState):
    print(c(BOLD, "\n── Interactive Mode ─────────────────────────────────────────"))
    print(c(GRAY, " Supported commands:"))
    print(c(GRAY, "   @META mode=analysis conflict=branch seal=manual risk=strict"))
    print(c(GRAY, "   @PATCH + R key = value | seal=hard"))
    print(c(GRAY, "   @F/@D/@R/@H/@S <statement>  (inline markers)"))
    print(c(GRAY, "   @SEAL F,D,R scope=global"))
    print(c(GRAY, "   state   — show current state"))
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
        turn_num += 1
        process_turn(text, state, turn_num)


def main():
    state = GovernanceState()
    print_banner()

    args = sys.argv[1:]
    if "-i" in args or "--interactive" in args:
        run_interactive(state)
    elif "-di" in args or "--demo-interactive" in args:
        run_demo(state)
        run_interactive(state)
    else:
        run_demo(state)
        print(c(GRAY, "\n Run with -i for interactive mode, "
                       "-di for demo + interactive mode"))


if __name__ == "__main__":
    main()
