# ManifestSection[T] Protocol & Loader Architecture

Deep-dive specification for the unified manifest loader, section parser protocol, and related design decisions.

---

## 1. ManifestSection[T] Protocol

### Protocol Definition

```python
from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")


class ManifestSection(Protocol[T]):
    """Protocol for typed manifest section parsers.

    Each section type (rules, checks, hints, phases) implements this protocol.
    The loader dispatches raw YAML sections to the appropriate parser without
    knowing section semantics. Adding a new section type = implementing this
    protocol + registering the key.
    """

    @property
    def section_key(self) -> str:
        """The YAML key this parser handles (e.g. 'rules', 'checks', 'hints', 'phases')."""
        ...

    def parse(
        self,
        raw: list[dict[str, Any]],
        *,
        namespace: str,
        source_path: str,
    ) -> list[T]:
        """Parse a raw YAML section into typed objects.

        Args:
            raw: The list of dicts from yaml.safe_load for this section key.
            namespace: The namespace prefix for ID qualification.
                       '_global' for global.yaml, workflow_id for workflow manifests.
            source_path: Path to the manifest file (for error messages only).

        Returns:
            List of parsed typed objects. Items that fail validation are skipped
            (logged, not raised) — fail open for individual items.

        Raises:
            Nothing. Individual item failures are logged and skipped.
            The parser never raises — it returns what it can parse.
        """
        ...
```

### T for Each Section Type

| Section Key | T (parsed type) | Description |
|-------------|-----------------|-------------|
| `rules` | `Rule` | Guardrail rule (existing dataclass in `guardrails/rules.py`, extended with qualified ID) |
| `checks` | `CheckSpec` | Check specification — type + params, not the executable check itself |
| `hints` | `HintDecl` | Hint declaration — message + lifecycle + scope metadata |
| `phases` | `Phase` | Phase definition — id, file reference, advance_checks, nested hints |

### Parse Method Contract

**What the parser validates (section-specific):**
- Required fields present (e.g., rules need `id`, `trigger`, `enforcement`)
- Field value types (e.g., `enforcement` is one of `deny|user_confirm|warn|log`)
- Regex compilation (detect patterns, check patterns)
- Raw IDs don't contain `:` (namespace separator reserved for the loader)
- Section-specific semantics (e.g., `detect.field` is a recognized field name)

**What the parser does NOT validate (loader's responsibility):**
- Duplicate IDs across sections/manifests (needs cross-manifest view)
- Phase reference validity (`phase_block`/`phase_allow` targets exist)
- Cross-section references (advance_checks referencing check IDs)

**Namespace prefixing happens IN the parser:** The parser receives `namespace` and prefixes every `id` field. This is deliberate — the parser knows the structure of its items, the loader doesn't.

---

## 2. Loader Architecture

### Core Principle: Single Code Path with Filter

There are NOT two separate modes (full-load vs. rules-only). The loader always loads all manifests and parses all sections. Callers filter what they need:

```python
# Hot path (every tool call) — same loader, just use .rules
result = loader.load()
active_rules = result.rules

# Full load (startup, phase transitions) — use everything
result = loader.load()
all_checks = result.checks
all_phases = result.phases
all_hints = result.hints
```

**Why:** Two code paths means two places for bugs, two places to update when the manifest schema changes, and a subtle coupling (the "rules-only" mode must know which sections are rules). One path, filter at the call site.

### Data Types

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LoadResult:
    """Complete result of loading all manifests."""

    rules: list[Rule] = field(default_factory=list)
    checks: list[CheckSpec] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    errors: list[LoadError] = field(default_factory=list)


@dataclass(frozen=True)
class LoadError:
    """A non-fatal error encountered during loading."""

    source: str  # file path or "discovery"
    message: str
    section: str | None = None  # which section key, if applicable
    item_id: str | None = None  # which item, if applicable
```

### Manifest Discovery Algorithm

```python
def discover_manifests(workflows_dir: Path) -> list[Path]:
    """Discover all manifest files under workflows/.

    Returns paths in load order:
    1. workflows/global.yaml (if exists)
    2. workflows/*/workflow_name.yaml (sorted alphabetically by workflow name)

    The workflow manifest filename must match its parent directory name.
    Example: workflows/project_team/project_team.yaml ✓
             workflows/project_team/other.yaml ✗ (ignored)
    """
    manifests: list[Path] = []

    # 1. Global manifest
    global_path = workflows_dir / "global.yaml"
    if global_path.is_file():
        manifests.append(global_path)

    # 2. Workflow manifests — scan subdirectories
    if workflows_dir.is_dir():
        for child in sorted(workflows_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                manifest = child / f"{child.name}.yaml"
                if manifest.is_file():
                    manifests.append(manifest)

    return manifests
```

**Key decisions:**
- Manifest filename MUST match directory name. This is the "folder name = identity" convention.
- Alphabetical sort for deterministic load order across NFS nodes.
- Hidden directories (`.name`) are skipped.
- No recursive scanning — exactly one level deep under `workflows/`.

### Load Order

1. `workflows/global.yaml` → namespace `_global`
2. `workflows/project_team/project_team.yaml` → namespace from `workflow_id` field in YAML (e.g., `project-team`)
3. Additional workflow manifests in alphabetical directory order

Global loads first so that startup validation can report conflicts (global rule ID shadows workflow rule ID, etc.).

### The `load()` Function

```python
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Registry: section_key -> parser instance
_PARSERS: dict[str, ManifestSection] = {}


def register_parser(parser: ManifestSection) -> None:
    """Register a section parser. Called at module import time."""
    _PARSERS[parser.section_key] = parser


class ManifestLoader:
    """Unified manifest loader.

    Discovers manifests, parses all sections via registered parsers,
    validates cross-manifest constraints, returns LoadResult.
    """

    def __init__(self, workflows_dir: Path) -> None:
        self._workflows_dir = workflows_dir

    def load(self) -> LoadResult:
        """Load all manifests and return unified result.

        Error handling:
        - workflows/ unreadable → fail closed (return LoadResult with
          a single FATAL error and empty lists — callers treat empty
          rules as "block everything" when error is present)
        - Individual manifest malformed → fail open (skip it, log error)
        - Individual item malformed → fail open (skip it, log error)
        """
        errors: list[LoadError] = []

        # Phase 1: Discover manifests
        try:
            manifest_paths = discover_manifests(self._workflows_dir)
        except OSError as e:
            # workflows/ unreadable → fail closed
            return LoadResult(
                errors=[LoadError(
                    source="discovery",
                    message=f"Cannot read workflows directory: {e}",
                )],
            )

        # Phase 2: Parse each manifest through all registered parsers
        all_items: dict[str, list] = {key: [] for key in _PARSERS}

        for path in manifest_paths:
            items, file_errors = self._load_one_manifest(path)
            errors.extend(file_errors)
            for key, parsed in items.items():
                all_items[key].extend(parsed)

        # Phase 3: Cross-manifest validation
        validation_errors = self._validate_cross_manifest(all_items)
        errors.extend(validation_errors)

        return LoadResult(
            rules=all_items.get("rules", []),
            checks=all_items.get("checks", []),
            hints=all_items.get("hints", []),
            phases=all_items.get("phases", []),
            errors=errors,
        )

    def _load_one_manifest(
        self, path: Path
    ) -> tuple[dict[str, list], list[LoadError]]:
        """Load a single manifest file. Returns parsed items + errors."""
        errors: list[LoadError] = []

        try:
            with path.open() as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            # Malformed manifest → fail open (skip entire file)
            return {}, [LoadError(
                source=str(path),
                message=f"Cannot parse manifest: {e}",
            )]

        if not isinstance(data, dict):
            return {}, [LoadError(
                source=str(path),
                message="Manifest is not a YAML mapping",
            )]

        # Determine namespace
        namespace = self._resolve_namespace(path, data)

        # Dispatch each section to its registered parser
        items: dict[str, list] = {}
        for key, parser in _PARSERS.items():
            raw_section = data.get(key)
            if raw_section is None:
                continue
            if not isinstance(raw_section, list):
                errors.append(LoadError(
                    source=str(path),
                    section=key,
                    message=f"Section '{key}' must be a list",
                ))
                continue

            parsed = parser.parse(
                raw_section,
                namespace=namespace,
                source_path=str(path),
            )
            items[key] = parsed

        # Handle nested hints inside phases (phases parser extracts these)
        # The phases parser returns Phase objects; hints nested under phases
        # are extracted and returned separately (see PhaseParser below).

        return items, errors

    def _resolve_namespace(self, path: Path, data: dict) -> str:
        """Determine namespace for a manifest.

        - global.yaml → '_global'
        - Workflow manifests → workflow_id field, falling back to directory name
        """
        if path.name == "global.yaml":
            return "_global"

        workflow_id = data.get("workflow_id")
        if workflow_id:
            return str(workflow_id)

        # Fallback: use parent directory name
        return path.parent.name

    def _validate_cross_manifest(
        self, all_items: dict[str, list]
    ) -> list[LoadError]:
        """Validate constraints that span multiple manifests.

        1. Duplicate ID detection (after namespace prefixing)
        2. Phase reference validation (phase_block/phase_allow targets exist)
        """
        errors: list[LoadError] = []

        # 1. Duplicate ID detection
        seen_ids: dict[str, str] = {}  # id -> first source
        for key, items in all_items.items():
            for item in items:
                item_id = getattr(item, "id", None)
                if item_id is None:
                    continue
                if item_id in seen_ids:
                    errors.append(LoadError(
                        source="validation",
                        section=key,
                        item_id=item_id,
                        message=(
                            f"Duplicate ID '{item_id}' "
                            f"(first seen in {seen_ids[item_id]})"
                        ),
                    ))
                else:
                    seen_ids[item_id] = key

        # 2. Phase reference validation
        known_phases: set[str] = set()
        for phase in all_items.get("phases", []):
            known_phases.add(phase.id)  # Already namespace-prefixed

        for rule in all_items.get("rules", []):
            for ref in getattr(rule, "phase_block", []):
                if ref not in known_phases:
                    errors.append(LoadError(
                        source="validation",
                        section="rules",
                        item_id=rule.id,
                        message=f"phase_block references unknown phase '{ref}'",
                    ))
            for ref in getattr(rule, "phase_allow", []):
                if ref not in known_phases:
                    errors.append(LoadError(
                        source="validation",
                        section="rules",
                        item_id=rule.id,
                        message=f"phase_allow references unknown phase '{ref}'",
                    ))

        return errors
```

### Namespace Prefixing

Bare IDs in YAML become qualified `namespace:id` at parse time. The validation that raw IDs don't contain `:` happens in the parser.

```
YAML:           id: pip_block      (in global.yaml)
After parse:    id: _global:pip_block

YAML:           id: close_agent    (in project_team.yaml with workflow_id: project-team)
After parse:    id: project-team:close_agent

YAML:           id: testing        (phase in project_team.yaml)
After parse:    id: project-team:testing
```

**Phase references are already qualified in YAML:** `phase_block: ["project-team:testing"]`. The parser does NOT prefix these — they are already namespace-qualified by convention. The loader validates them against known phase IDs after all manifests are loaded.

---

## 3. NFS Performance

### The Problem

Rules are loaded fresh on every tool call. No mtime caching — NFS mtime is unreliable on HPC clusters. This means YAML I/O on EVERY `PreToolUse` hook invocation.

### Cost Analysis

A typical `global.yaml` + one workflow manifest = ~2 small YAML files. `yaml.safe_load` on a 50-line YAML file takes ~0.5ms. Two files = ~1ms. The regex compilation for detect patterns is the expensive part, but with the single-code-path approach, we're parsing ALL sections every time.

### Design for the Hot Path

**Recommendation: Keep it simple. Accept the I/O cost.**

Rationale:
1. The YAML files are small (tens of lines, not thousands)
2. `yaml.safe_load` is fast for small files
3. NFS read caching at the OS level will help in practice (even if mtime is unreliable, the kernel page cache still works for reads within the same second)
4. The alternative (content hashing) adds complexity for marginal gain — you still have to read the file to hash it
5. Profile before optimizing. If profiling shows the YAML I/O is a bottleneck, optimize then.

**If optimization is needed later (in priority order):**

1. **Content hash cache:** Read file contents, SHA256 hash, compare to cached hash. If unchanged, return cached parse result. This is ~0.1ms (hash) vs ~0.5ms (yaml.safe_load) — marginal. Only helps if there are many manifests.

2. **Compiled regex cache:** The real cost may be `re.compile()` on every load. Cache compiled regexes keyed by pattern string (a module-level dict). This is safe and simple.

3. **Lazy section parsing:** Parse only the `rules:` section on the hot path. This breaks the "single code path" principle, so it should be a last resort.

```python
# Optimization 2: Compiled regex cache (safe, simple, recommended)
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}

def cached_compile(pattern: str) -> re.Pattern[str]:
    """Compile regex with caching. Safe for concurrent reads."""
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern)
    return _REGEX_CACHE[pattern]
```

**The recommendation stands:** Single code path with filter. `loader.load().rules` on the hot path. Profile before adding complexity. The regex cache is worth adding from day one since it's zero-risk.

---

## 4. Hints Scoping Clarification

### The Ambiguity

The USER_PROMPT.md shows:
- `global.yaml` → top-level hints (always active)
- Workflow manifests → hints nested under `phases[].hints` (phase-scoped)

**Question:** Can workflow manifests ALSO declare top-level (workflow-wide) hints?

### Analysis

Looking at the manifest example in USER_PROMPT.md:

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - ...

phases:
  - id: implementation
    hints:
      - message: "Focus on writing code..."
        lifecycle: show-once
```

There is no top-level `hints:` section in the workflow manifest example. Hints appear only under phases.

### Recommendation: Support Top-Level Hints in Workflow Manifests

**Yes, support it.** Here's why:

1. **Composability:** If `global.yaml` can have a top-level `hints:` section, workflow manifests should too. Asymmetric behavior is a composability smell.

2. **Use case:** Workflow-wide hints that aren't phase-specific. Example: "This workflow uses pixi for all dependency management" — relevant in every phase, not worth duplicating under each phase entry.

3. **How it fits ManifestSection[T]:** The `HintsParser` handles the top-level `hints:` section the same way for both global and workflow manifests. Phase-nested hints are extracted by the `PhasesParser` and added to the hints list with phase scope metadata attached.

### Hint Scoping Model

```
Scope Level          Source Location                    Active When
─────────────        ───────────────                    ───────────
Global               global.yaml → hints:               Always
Workflow-wide        workflow.yaml → hints:              Whenever workflow is active
Phase-scoped         workflow.yaml → phases[].hints:     Only during that phase
```

### How Phase-Nested Hints Work with ManifestSection[T]

The `PhasesParser` handles `phases:` sections. When it encounters `hints:` nested under a phase, it:
1. Creates the `Phase` object (its primary responsibility)
2. Extracts nested hints and attaches phase scope metadata

But this creates a problem: the `PhasesParser` returns `list[Phase]`, not hints. Two approaches:

**Approach A (recommended): PhasesParser extracts hints into Phase.hints field**

```python
@dataclass(frozen=True)
class Phase:
    id: str  # namespace-qualified
    file: str
    advance_checks: list[dict[str, Any]] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)  # phase-scoped hints
```

The loader then collects all phase-scoped hints from all Phase objects and merges them into the main hints list (with phase scope set). This keeps the PhasesParser focused on phases while the loader handles the flattening.

**Approach B: Duplicate parse** — The `HintsParser` also scans inside `phases[].hints`. Rejected: this means the hints parser needs to understand phase structure, violating separation.

### HintDecl Type

```python
@dataclass(frozen=True)
class HintDecl:
    """A hint declaration from a manifest."""

    id: str  # namespace-qualified, auto-generated if not explicit
    message: str
    lifecycle: str  # "show-once" | "show-until-resolved" | "show-every-session" | "cooldown"
    cooldown_seconds: int | None = None  # only if lifecycle == "cooldown"
    phase: str | None = None  # qualified phase ID, or None for unscoped
    namespace: str = ""  # which namespace this came from
```

- `phase=None` → global or workflow-wide hint (always active when workflow active)
- `phase="project-team:implementation"` → phase-scoped hint

---

## 5. Error Handling

### Error Strategy Matrix

| Failure | Behavior | Rationale |
|---------|----------|-----------|
| `workflows/` directory unreadable | **Fail closed** — return empty rules + fatal error. Callers treat "empty rules with errors" as "block everything". | If we can't read the guardrails, we can't enforce them. Failing open would silently disable all protection. |
| Individual manifest YAML parse error | **Fail open** — skip that manifest, load the rest. Log error. | One bad manifest shouldn't disable global rules from other manifests. |
| Individual item bad regex | **Fail open** — skip that item, parse rest of section. Log error. | One bad rule shouldn't disable sibling rules. |
| Duplicate ID (after prefixing) | **Warn** — log the duplicate, keep the first occurrence. | Duplicates are likely authoring errors. Keeping first-wins is predictable. |
| Invalid phase reference | **Warn** — log the bad reference. Rule still loads (phase filter becomes vacuously false for unknown phases, meaning the rule never activates on phase grounds). | The rule is still valid; it just references a phase that doesn't exist yet. Could be a typo or a future phase. |
| Raw ID contains `:` | **Fail open** — skip that item, log error. | This is an authoring error. The `:` is reserved for namespace qualification. |

### Concrete Error Flow

```python
def _parse_rule_item(
    entry: dict[str, Any],
    namespace: str,
    source_path: str,
) -> Rule | LoadError:
    """Parse a single rule entry. Returns Rule or LoadError."""

    # 1. Required field: id
    raw_id = entry.get("id")
    if not raw_id or not isinstance(raw_id, str):
        return LoadError(
            source=source_path,
            section="rules",
            message="Rule missing required 'id' field",
        )

    # 2. Validate no colon in raw ID
    if ":" in raw_id:
        return LoadError(
            source=source_path,
            section="rules",
            item_id=raw_id,
            message=f"Raw ID '{raw_id}' contains ':' — IDs must be bare (namespace is added automatically)",
        )

    # 3. Namespace prefix
    qualified_id = f"{namespace}:{raw_id}"

    # 4. Compile regex (may fail)
    detect = entry.get("detect", {})
    detect_pattern = None
    if detect and detect.get("pattern"):
        try:
            detect_pattern = cached_compile(detect["pattern"])
        except re.error as e:
            return LoadError(
                source=source_path,
                section="rules",
                item_id=qualified_id,
                message=f"Invalid detect regex: {e}",
            )

    # 5. Validate enforcement value
    enforcement = entry.get("enforcement", "deny")
    if enforcement not in ("deny", "user_confirm", "warn", "log"):
        return LoadError(
            source=source_path,
            section="rules",
            item_id=qualified_id,
            message=f"Unknown enforcement '{enforcement}'",
        )

    # 6. Build Rule (remaining fields have safe defaults)
    # ... (parse trigger, roles, phases — same pattern as existing rules.py)

    return Rule(
        id=qualified_id,
        # ... all fields
    )
```

### Fail-Closed Detection at the Call Site

```python
# In the SDK hook closure (hot path):
result = loader.load()

if result.errors and not result.rules:
    # Possible fail-closed scenario: errors present, no rules loaded.
    # Check if the error is a fatal discovery error.
    fatal = any(e.source == "discovery" for e in result.errors)
    if fatal:
        # Cannot read workflows/ → block everything
        return {"decision": "block", "message": "Guardrails unavailable — workflows/ unreadable"}

# Normal path: evaluate rules
for rule in result.rules:
    ...
```

---

## 6. Concrete Code Sketches

### The ManifestSection Protocol (complete)

```python
from __future__ import annotations

import re
from typing import Any, Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class ManifestSection(Protocol[T_co]):
    """Protocol for typed manifest section parsers."""

    @property
    def section_key(self) -> str: ...

    def parse(
        self,
        raw: list[dict[str, Any]],
        *,
        namespace: str,
        source_path: str,
    ) -> list[T_co]: ...
```

### Rules Parser (ManifestSection[Rule] implementation)

```python
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Regex cache — survives across load() calls, safe for the hot path
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def cached_compile(pattern: str) -> re.Pattern[str]:
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern)
    return _REGEX_CACHE[pattern]


@dataclass(frozen=True)
class Rule:
    """A single guardrail rule. IDs are namespace-qualified."""

    id: str  # e.g. "_global:pip_block" or "project-team:close_agent"
    namespace: str  # e.g. "_global" or "project-team"
    trigger: list[str]
    enforcement: str
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"
    exclude_pattern: re.Pattern[str] | None = None
    message: str = ""
    block_roles: list[str] = field(default_factory=list)
    allow_roles: list[str] = field(default_factory=list)
    phase_block: list[str] = field(default_factory=list)
    phase_allow: list[str] = field(default_factory=list)


class RulesParser:
    """Parses the 'rules' section of manifests into Rule objects."""

    @property
    def section_key(self) -> str:
        return "rules"

    def parse(
        self,
        raw: list[dict[str, Any]],
        *,
        namespace: str,
        source_path: str,
    ) -> list[Rule]:
        rules: list[Rule] = []

        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                logger.warning(
                    "Skipping non-dict rule entry #%d in %s", i, source_path
                )
                continue

            result = self._parse_one(entry, namespace, source_path)
            if isinstance(result, Rule):
                rules.append(result)
            else:
                logger.warning(
                    "Skipping rule in %s: %s", source_path, result
                )

        return rules

    def _parse_one(
        self,
        entry: dict[str, Any],
        namespace: str,
        source_path: str,
    ) -> Rule | str:
        """Parse one rule entry. Returns Rule or error string."""

        # --- ID ---
        raw_id = entry.get("id")
        if not raw_id or not isinstance(raw_id, str):
            return "missing 'id' field"

        if ":" in raw_id:
            return f"raw ID '{raw_id}' contains ':' — use bare IDs only"

        qualified_id = f"{namespace}:{raw_id}"

        # --- Trigger ---
        raw_trigger = entry.get("trigger", "")
        if isinstance(raw_trigger, str):
            triggers = [raw_trigger] if raw_trigger else []
        elif isinstance(raw_trigger, list):
            triggers = [str(t) for t in raw_trigger]
        else:
            return f"invalid trigger type for rule '{raw_id}'"

        if not triggers:
            return f"rule '{raw_id}' has no trigger"

        # --- Enforcement ---
        enforcement = entry.get("enforcement", "deny")
        valid_enforcements = {"deny", "user_confirm", "warn", "log"}
        if enforcement not in valid_enforcements:
            return f"unknown enforcement '{enforcement}' for rule '{raw_id}'"

        # --- Detect pattern ---
        detect = entry.get("detect", {})
        detect_pattern = None
        detect_field = "command"
        if isinstance(detect, dict) and detect.get("pattern"):
            try:
                detect_pattern = cached_compile(detect["pattern"])
            except re.error as e:
                return f"invalid detect regex for rule '{raw_id}': {e}"
            detect_field = detect.get("field", "command")

        # --- Exclude pattern ---
        exclude_pattern = None
        exclude_str = entry.get("exclude_if_matches", "")
        if exclude_str:
            try:
                exclude_pattern = cached_compile(exclude_str)
            except re.error as e:
                return f"invalid exclude regex for rule '{raw_id}': {e}"

        # --- Role restrictions (NOT namespace-prefixed — roles are global names) ---
        block_roles = _as_list(entry.get("block_roles", []))
        allow_roles = _as_list(entry.get("allow_roles", []))

        # --- Phase restrictions (already qualified in YAML — NOT prefixed here) ---
        phase_block = _as_list(entry.get("phase_block", []))
        phase_allow = _as_list(entry.get("phase_allow", []))

        return Rule(
            id=qualified_id,
            namespace=namespace,
            trigger=triggers,
            enforcement=enforcement,
            detect_pattern=detect_pattern,
            detect_field=detect_field,
            exclude_pattern=exclude_pattern,
            message=entry.get("message", ""),
            block_roles=block_roles,
            allow_roles=allow_roles,
            phase_block=phase_block,
            phase_allow=phase_allow,
        )


def _as_list(val: Any) -> list[str]:
    """Coerce a value to a list of strings."""
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(v) for v in val]
    return []
```

### Loader main `load()` Function (complete)

```python
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ManifestLoader:
    """Unified manifest loader — single code path, callers filter."""

    def __init__(self, workflows_dir: Path) -> None:
        self._workflows_dir = workflows_dir
        self._parsers: dict[str, ManifestSection] = {}

    def register(self, parser: ManifestSection) -> None:
        self._parsers[parser.section_key] = parser

    def load(self) -> LoadResult:
        errors: list[LoadError] = []

        # 1. Discover
        try:
            paths = self._discover()
        except OSError as e:
            logger.error("Cannot read workflows/: %s", e)
            return LoadResult(errors=[
                LoadError(source="discovery", message=str(e))
            ])

        # 2. Parse all manifests
        collected: dict[str, list] = {k: [] for k in self._parsers}
        for path in paths:
            namespace = self._namespace_for(path)
            try:
                with path.open() as f:
                    data = yaml.safe_load(f)
            except (OSError, yaml.YAMLError) as e:
                errors.append(LoadError(source=str(path), message=str(e)))
                continue

            if not isinstance(data, dict):
                errors.append(LoadError(
                    source=str(path), message="not a YAML mapping"
                ))
                continue

            # Override namespace from workflow_id if present
            if path.name != "global.yaml":
                wf_id = data.get("workflow_id")
                if wf_id:
                    namespace = str(wf_id)

            for key, parser in self._parsers.items():
                section = data.get(key)
                if section is None:
                    continue
                if not isinstance(section, list):
                    errors.append(LoadError(
                        source=str(path), section=key,
                        message=f"'{key}' must be a list",
                    ))
                    continue
                parsed = parser.parse(
                    section, namespace=namespace, source_path=str(path)
                )
                collected[key].extend(parsed)

            # Extract phase-nested hints (Approach A from section 4)
            for phase in collected.get("phases", []):
                if hasattr(phase, "hints") and phase.hints:
                    collected.setdefault("hints", []).extend(phase.hints)

        # 3. Cross-manifest validation
        errors.extend(self._validate(collected))

        return LoadResult(
            rules=collected.get("rules", []),
            checks=collected.get("checks", []),
            hints=collected.get("hints", []),
            phases=collected.get("phases", []),
            errors=errors,
        )

    def _discover(self) -> list[Path]:
        paths: list[Path] = []
        gp = self._workflows_dir / "global.yaml"
        if gp.is_file():
            paths.append(gp)
        if self._workflows_dir.is_dir():
            for child in sorted(self._workflows_dir.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    mf = child / f"{child.name}.yaml"
                    if mf.is_file():
                        paths.append(mf)
        return paths

    def _namespace_for(self, path: Path) -> str:
        if path.name == "global.yaml":
            return "_global"
        return path.parent.name

    def _validate(self, collected: dict[str, list]) -> list[LoadError]:
        errors: list[LoadError] = []

        # Duplicate IDs
        seen: dict[str, str] = {}
        for key, items in collected.items():
            for item in items:
                iid = getattr(item, "id", None)
                if iid is None:
                    continue
                if iid in seen:
                    errors.append(LoadError(
                        source="validation", section=key, item_id=iid,
                        message=f"duplicate ID (first in {seen[iid]})",
                    ))
                else:
                    seen[iid] = key

        # Phase references
        known_phases = {p.id for p in collected.get("phases", [])}
        for rule in collected.get("rules", []):
            for ref in getattr(rule, "phase_block", []):
                if ref not in known_phases:
                    errors.append(LoadError(
                        source="validation", section="rules",
                        item_id=rule.id,
                        message=f"unknown phase ref '{ref}' in phase_block",
                    ))
            for ref in getattr(rule, "phase_allow", []):
                if ref not in known_phases:
                    errors.append(LoadError(
                        source="validation", section="rules",
                        item_id=rule.id,
                        message=f"unknown phase ref '{ref}' in phase_allow",
                    ))

        return errors
```

### Namespace Prefixing Example (in parser)

```python
# In RulesParser._parse_one():
raw_id = entry.get("id")           # e.g. "pip_block"
qualified_id = f"{namespace}:{raw_id}"  # e.g. "_global:pip_block"

# Phase refs are NOT prefixed — they're already qualified in YAML:
phase_block = entry.get("phase_block", [])
# e.g. ["project-team:testing"] — used as-is

# The loader validates these against known phase IDs after all manifests load.
```

---

## Design Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Loader modes | Single code path + filter | Preserves composability, avoids dual-path bugs |
| NFS caching | No mtime cache, no content hash | Accept I/O cost for simplicity; add regex cache only |
| Namespace prefixing | Parser prefixes IDs, NOT the loader | Parser knows item structure; loader is generic |
| Phase references in YAML | Already qualified (no auto-prefixing) | Explicit > implicit; avoids ambiguity for global rules |
| Raw ID validation | Parser rejects IDs containing `:` | Prevents double-prefixing silently |
| Workflow-wide hints | Supported via top-level `hints:` in workflow manifests | Compositional symmetry with global.yaml |
| Phase-nested hints | Extracted by PhasesParser into Phase.hints, flattened by loader | Keeps parser focused; loader handles cross-section concerns |
| Fail closed | Only for `workflows/` unreadable | Nuclear option reserved for the most dangerous failure |
| Fail open | For individual manifests and items | Resilience — one bad rule doesn't disable all guardrails |
| Regex caching | Module-level dict, keyed by pattern string | Zero-risk optimization for the hot path |
