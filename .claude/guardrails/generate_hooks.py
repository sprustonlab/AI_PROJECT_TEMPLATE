#!/usr/bin/env python3
"""
Generate hook scripts from rules.yaml.

Reads .claude/guardrails/rules.yaml (the single source of truth) and emits
self-contained hook scripts into .claude/guardrails/hooks/.

Usage (developer workflow — regenerate hooks after editing rules.yaml):
    python3 .claude/guardrails/generate_hooks.py

Usage (CI / pre-commit drift check):
    python3 .claude/guardrails/generate_hooks.py --check

Usage (role × action matrix):
    python3 .claude/guardrails/generate_hooks.py --matrix

The --check mode generates to a temp dir, compares byte-for-byte, and exits
non-zero if any hook script differs from the committed version.

The --matrix mode prints a markdown role × action matrix to stdout showing
each role's enforcement level for every role-gated rule.

Architecture: Option C (code generation) — analogous to
prism/dashboard/state/param_generator.py.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
RULES_YAML = SCRIPT_DIR / "rules.yaml"
HOOKS_DIR = SCRIPT_DIR / "hooks"
MESSAGES_DIR = SCRIPT_DIR / "messages"

# Trigger → output filename mapping
TRIGGER_TO_FILE = {
    "PreToolUse/Bash": "bash_guard.py",
    "PreToolUse/Read": "read_guard.py",
    "PreToolUse/Glob": "glob_guard.py",
    "PreToolUse/Write": "write_guard.py",
    "PreToolUse/Edit": "write_guard.py",   # Write and Edit share a hook script
    "SessionStart/compact": "post_compact_injector.py",
}

# Enforcement hierarchy for documentation only.
# Dispatch priority in generated hooks uses explicit if/elif: deny > warn > inject > log.
# Do NOT use max(ENFORCEMENT_RANK) for dispatch decisions.
ENFORCEMENT_RANK = {"log": 0, "warn": 1, "deny": 2, "inject": 3}

# Generator-time mapping: enforcement name → internal pcode stored in _matched_rules tuples.
# Must stay in sync with role_guard.py's _code_map: {'deny': 1, 'warn': 2, 'log': 3, 'inject': 4}.
_ENFORCE_TO_PCODE = {"deny": 1, "warn": 2, "log": 3, "inject": 4}

# Triggers that use the ack token flow instead of the Bash # ack: comment prefix.
_WRITE_EDIT_TRIGGERS = {"PreToolUse/Write", "PreToolUse/Edit"}

# Valid enforcement values (enforced by validate_rules).
_VALID_ENFORCEMENT = frozenset(ENFORCEMENT_RANK)

# Regex flag name → Python re module constant
FLAG_MAP = {
    "IGNORECASE": "re.IGNORECASE",
    "DOTALL": "re.DOTALL",
    "MULTILINE": "re.MULTILINE",
}


# ---------------------------------------------------------------------------
# YAML loader (stdlib only — no PyYAML dependency for hook scripts)
# ---------------------------------------------------------------------------

def load_rules_yaml(path: Path) -> dict[str, Any]:
    """Load rules.yaml. Uses PyYAML if available, falls back to a simple parser."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        # Fallback: use a minimal YAML subset parser for CI environments
        raise SystemExit(
            "PyYAML is required. Install via: pip install pyyaml\n"
            "Or use: conda run -n decode_prism python3 .claude/guardrails/generate_hooks.py"
        )


# ---------------------------------------------------------------------------
# Message resolvers
# ---------------------------------------------------------------------------

def read_message(message_path: str) -> str:
    """Read a message file relative to the repo root."""
    # message_path is relative to repo root, e.g. ".claude/guardrails/messages/R01.md"
    repo_root = SCRIPT_DIR.parent.parent  # .claude/guardrails -> .claude -> repo root
    full_path = repo_root / message_path
    if not full_path.exists():
        raise FileNotFoundError(f"Message file not found: {full_path}")
    return full_path.read_text().strip()


def get_message_text(rule: dict) -> str:
    """Resolve message text: file path (.md) or inline string.

    Args:
        rule: Rule dict with a 'message' field.

    Returns:
        The resolved message text, stripped.
    """
    msg = rule.get("message", "")
    if not msg:
        return ""
    # If it looks like a file path, read from file; otherwise treat as inline string.
    if msg.endswith(".md") or msg.startswith(".claude/") or msg.startswith("messages/"):
        return read_message(msg)
    return msg.strip()


# ---------------------------------------------------------------------------
# Code generation helpers
# ---------------------------------------------------------------------------

def python_flags(flags: list[str] | None) -> str:
    """Convert YAML flags list to Python re flags expression."""
    if not flags:
        return ""
    parts = [FLAG_MAP[f] for f in flags if f in FLAG_MAP]
    return " | ".join(parts) if parts else ""


def escape_for_python(s: str) -> str:
    """Escape a string for embedding in a Python triple-quoted string."""
    return s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def indent(text: str, prefix: str = "    ") -> str:
    """Indent all lines of text."""
    return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# strip_contexts function (inlined into generated scripts that need it)
# ---------------------------------------------------------------------------

STRIP_CONTEXTS_FUNC = '''\
def strip_contexts(command: str, contexts: list) -> str:
    result = command
    if 'python_dash_c' in contexts:
        # Strip inline Python: python3 -c "..." or python3 -c '...'
        result = re.sub(
            r\\'\\'\\'\\bpython3?\\s+-c\\s+(?:"[^"]*"|\\x27[^\\x27]*\\x27)\\'\\'\\'',
            'PYTHON_INLINE_STRIPPED',
            result,
        )
    if 'python_heredoc' in contexts:
        # Strip Python heredoc body: python3 << 'WORD' ... WORD
        result = re.sub(
            r\\'\\'\\'\\bpython3?\\s+<<\\s*[\\x27"]?\\w+[\\x27"]?\\n.*?^\\w+\\'\\'\\'',
            'PYTHON_HEREDOC_STRIPPED',
            result,
            flags=re.MULTILINE | re.DOTALL,
        )
    return result
'''

# A cleaner version for embedding in generated Python:
STRIP_CONTEXTS_CLEAN = '''def strip_contexts(command, contexts):
    result = command
    if 'python_dash_c' in contexts:
        result = re.sub(
            r"""\\bpython3?\\s+-c\\s+(?:"[^"]*"|'[^']*')""",
            'PYTHON_INLINE_STRIPPED',
            result,
        )
    if 'python_heredoc' in contexts:
        result = re.sub(
            r"""\\bpython3?\\s+<<\\s*['"]?\\w+['"]?\\n.*?^\\w+""",
            'PYTHON_HEREDOC_STRIPPED',
            result,
            flags=re.MULTILINE | re.DOTALL,
        )
    return result
'''


# ---------------------------------------------------------------------------
# log_hit() template with enriched fields (agent_name, session_name)
# ---------------------------------------------------------------------------

LOG_HIT_TEMPLATE = '''\
def derive_session_name(session_id, ts, cwd):
    """Derive human-readable name from session's first user message."""
    import pathlib
    date_prefix = ts[:10]
    cache_path = pathlib.Path(os.environ.get('GUARDRAILS_DIR', '')) / 'session_names.json'
    # Check cache
    try:
        if cache_path.exists():
            with open(cache_path) as _cf:
                _cache = json.loads(_cf.read())
            if session_id in _cache:
                return _cache[session_id]
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    # Derive from JSONL
    cwd_hash = cwd.lstrip('/').replace('/', '-')
    jsonl_path = pathlib.Path.home() / f'.claude/projects/{cwd_hash}/{session_id}.jsonl'
    if not jsonl_path.exists():
        return f"{date_prefix}_{session_id[:8]}"
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    if rec.get('type') == 'human' or (
                        rec.get('message', {}).get('role') == 'user'
                    ):
                        content = rec.get('message', {}).get('content', '')
                        if isinstance(content, list):
                            text = ' '.join(
                                b.get('text', '') for b in content
                                if isinstance(b, dict) and b.get('type') == 'text'
                            )
                        else:
                            text = str(content)
                        if text.strip():
                            slug = re.sub(r'[^a-z0-9]+', '_', text.strip().lower())[:50]
                            slug = slug.strip('_')
                            name = f"{date_prefix}_{slug}"
                            # Write to cache
                            try:
                                _cache_data = {}
                                if cache_path.exists():
                                    with open(cache_path) as _cf2:
                                        _cache_data = json.loads(_cf2.read())
                                _cache_data[session_id] = name
                                with open(cache_path, 'w') as _cf3:
                                    _cf3.write(json.dumps(_cache_data, indent=2))
                            except OSError:
                                pass
                            return name
                except (json.JSONDecodeError, KeyError):
                    continue
    except OSError:
        pass
    return f"{date_prefix}_{session_id[:8]}"


def log_hit(rule_id, enforcement, tool_name, target):
    if not hits_file:
        return
    _sname = derive_session_name(session_id, ts, cwd)
    _aname = os.environ.get('CLAUDE_AGENT_NAME', '')
    rec = json.dumps({
        'ts': ts,
        'rule_id': rule_id,
        'session_id': session_id,
        'session_name': _sname,
        'agent_name': _aname,
        'enforcement': enforcement,
        'tool': tool_name,
        'target': target[:120],
    })
    try:
        with open(hits_file, 'a') as fh:
            fh.write(rec + '\\n')
    except OSError:
        pass
'''


# ---------------------------------------------------------------------------
# Framework helpers — used by generate_all() to condition code generation
# ---------------------------------------------------------------------------

def needs_role_guard_import(rules: list[dict]) -> bool:
    """Return True if the generated hook needs ``import role_guard as _rg``.

    True when any rule has ``allow:``/``block:`` (needs ``check_role()``) OR any
    rule has a Write/Edit trigger with ``enforcement: warn`` (needs
    ``check_write_ack()``).

    Trigger normalization: a rule's ``trigger`` field may be a string or a list.
    ``set("PreToolUse/Write")`` iterates characters, not the whole string, so we
    normalise with ``{_t} if isinstance(_t, str) else set(_t)`` before
    intersecting with ``_WRITE_EDIT_TRIGGERS``.

    Args:
        rules: Rules list for this hook's trigger group.

    Returns:
        True if the role_guard module must be imported.
    """
    for r in rules:
        # Role-gated rules (check_role() needed)
        if r.get('allow') or r.get('block'):
            return True
        # Write/Edit warn rules (check_write_ack() needed)
        _t = r.get("trigger", [])
        _trigger_set = {_t} if isinstance(_t, str) else set(_t)
        if (_trigger_set & _WRITE_EDIT_TRIGGERS
                and r.get("enforcement") == "warn"):
            return True
    return False


def validate_rules(rules: list[dict], ack_ttl: int) -> None:
    """Validate rule schema before code generation; exit with error on violations.

    Implements spec §5.3 Item 5. Errors call ``sys.exit()``; warnings print to
    stderr with the ``[GUARDRAIL NOTE]`` prefix.

    Args:
        rules: Full rules list from rules.yaml.
        ack_ttl: Value of ``ack_ttl_seconds`` from rules.yaml top-level; must be > 0.

    Raises:
        SystemExit: On any schema violation or invalid ack_ttl.
    """
    if ack_ttl <= 0:
        sys.exit(
            f"ERROR: ack_ttl_seconds must be > 0 (got {ack_ttl}). "
            "Use a large value (e.g., 86400) for long TTLs."
        )

    _RESERVED_ROLES = frozenset({'Agent', 'TeamAgent', 'Subagent', 'Coordinator'})
    _agents_dir = Path('AI_agents')

    for _rule in rules:
        _rid = _rule.get('id', '?')
        _enforcement = _rule.get('enforcement', 'warn')
        _has_allow = 'allow' in _rule and _rule['allow'] is not None
        _has_block = 'block' in _rule and _rule['block'] is not None
        _detect_type = _rule.get('detect', {}).get('type', 'regex')
        _triggers = _rule.get('trigger', [])
        if isinstance(_triggers, str):
            _triggers = [_triggers]

        # ERROR: invalid enforcement value (catches legacy 'block')
        if _enforcement not in _VALID_ENFORCEMENT:
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has enforcement: '{_enforcement}'. "
                f"Valid values are: {sorted(_VALID_ENFORCEMENT)}. "
                "If using legacy 'block', replace with 'deny'."
            )

        # ERROR: both allow: and block: present — mutually exclusive
        if _has_allow and _has_block:
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has both allow: and block:. "
                "Use one list per rule — they are mutually exclusive."
            )

        # ERROR: empty allow: list — silently blocks everyone
        if _has_allow and len(_rule['allow']) == 0:
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has an empty allow: list. "
                "An empty allow: list blocks every agent. Use block: [Agent] instead."
            )

        # ERROR: empty block: list — has no effect
        if _has_block and len(_rule['block']) == 0:
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has an empty block: list. "
                "An empty block: list has no effect. Remove it or add role entries."
            )

        # ERROR: allow: [Agent] — always passes, no-op allowlist
        if _has_allow and 'Agent' in _rule['allow']:
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has allow: [Agent]. "
                "'Agent' in an allowlist always passes for everyone — it is a no-op. "
                "Remove the allow: list, or use block: to restrict specific roles instead."
            )

        # WARNING: block: [Agent] + enforcement: deny/inject — broad effect, confirm intentional
        if _has_block and 'Agent' in _rule['block']:
            if _enforcement == 'deny':
                print(
                    f"[GUARDRAIL NOTE] generate_hooks: rule '{_rid}' has block: [Agent] with "
                    "enforcement: deny. This hard-blocks every agent with no ack option. "
                    "Confirm this is intentional before deploying.",
                    file=sys.stderr,
                )
            elif _enforcement == 'inject':
                print(
                    f"[GUARDRAIL NOTE] generate_hooks: rule '{_rid}' has block: [Agent] with "
                    "enforcement: inject. This modifies tool input for every agent. "
                    "Confirm this is intentional before deploying.",
                    file=sys.stderr,
                )

        # ERROR: type:regex/regex_match/regex_miss with no pattern field
        if (_detect_type in ('regex', 'regex_match', 'regex_miss')
                and 'pattern' not in _rule.get('detect', {})):
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has detect.type: {_detect_type} but no pattern: field. "
                "Add a pattern: field to the detect: section."
            )

        # ERROR: type:regex_match or regex_miss on an MCP trigger with no field:
        # MCP tools have no trigger-default field — field: is required.
        if (_detect_type in ('regex_match', 'regex_miss')
                and not _rule.get('detect', {}).get('field')):
            for _tr in _triggers:
                if _tr.startswith('mcp__'):
                    sys.exit(
                        f"ERROR: rules.yaml rule '{_rid}' has detect.type: {_detect_type} on "
                        f"MCP trigger '{_tr}' without field: — MCP tools have no default field. "
                        "Add field: <fieldname> to the detect: section."
                    )

        # ERROR: type:spawn_type_defined on a non-mcp__chic__spawn_agent trigger
        if _detect_type == 'spawn_type_defined':
            for _tr in _triggers:
                if _tr != 'mcp__chic__spawn_agent':
                    sys.exit(
                        f"ERROR: rules.yaml rule '{_rid}' has detect.type: spawn_type_defined "
                        f"on trigger '{_tr}'. spawn_type_defined is only valid on "
                        "trigger: mcp__chic__spawn_agent."
                    )

        # ERROR: type:always with no allow/block — fires universally.
        # Exception: inject enforcement and SessionStart/* triggers are intentionally universal.
        if (_detect_type == 'always'
                and not _has_allow and not _has_block
                and _enforcement != 'inject'
                and not any(t.startswith('SessionStart/') for t in _triggers)):
            sys.exit(
                f"ERROR: rules.yaml rule '{_rid}' has detect.type: always but no allow:/block:. "
                "type: always without a role gate fires for everyone — use type: regex_match instead, "
                "or add allow:/block: to gate by role."
            )

        # WARNING: named role in allow/block not found in AI_agents/ definition files
        _all_entries = list(_rule.get('allow') or []) + list(_rule.get('block') or [])
        for _entry in _all_entries:
            if _entry in _RESERVED_ROLES:
                continue
            # CamelCase → UPPER_SNAKE (two-pass; handles UIDesigner → UI_DESIGNER)
            _s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', _entry)
            _s = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', _s)
            _expected = f'{_s.upper()}.md'
            if _agents_dir.exists() and not list(_agents_dir.rglob(_expected)):
                print(
                    f"[GUARDRAIL NOTE] generate_hooks: rule '{_rid}' references role '{_entry}' "
                    f"but no agent definition file found at AI_agents/**/{_expected}. "
                    "This role name will never match any agent. Check for typos.",
                    file=sys.stderr,
                )

        # WARNING: unknown trigger value (typo silently produces no hook)
        for _tr in _triggers:
            if _tr not in TRIGGER_TO_FILE and not _tr.startswith('mcp__'):
                print(
                    f"[GUARDRAIL NOTE] generate_hooks: rule '{_rid}' has trigger '{_tr}' "
                    "which is not in TRIGGER_TO_FILE and does not start with 'mcp__'. "
                    "Check for typos — an unrecognized trigger silently produces no hook.",
                    file=sys.stderr,
                )


def generate_matrix(rules: list[dict], catalog_version: str) -> str:
    """Generate a markdown role × action matrix from rules.yaml.

    Rows: every role found in ``AI_agents/project_team/*.md``.
    Columns: every role-gated rule (has ``allow:`` or ``block:``).
    Cells: the effective enforcement level for that role.

    Run before committing Phase D rules to verify coverage:
        python3 .claude/guardrails/generate_hooks.py --matrix > role_matrix.md

    Args:
        rules: Full rules list from rules.yaml.
        catalog_version: The catalog_version string from rules.yaml.

    Returns:
        Markdown table string.
    """
    # Collect role names from AI_agents/project_team/*.md (UPPER_SNAKE → CamelCase)
    agents_dir = Path('AI_agents/project_team')
    role_names: list[str] = []
    if agents_dir.exists():
        for md in sorted(agents_dir.glob('*.md')):
            parts = md.stem.split('_')
            role_name = ''.join(p.capitalize() for p in parts)
            role_names.append(role_name)

    if not role_names:
        role_names = ['(no roles found in AI_agents/project_team/)']

    # Collect role-gated rules
    gated_rules = [r for r in rules if r.get('allow') or r.get('block')]
    if not gated_rules:
        return (
            f"# Role × Action Matrix (catalog_version: {catalog_version})\n\n"
            "No role-gated rules found in rules.yaml.\n"
        )

    _RESERVED = frozenset({'Agent', 'TeamAgent', 'Subagent'})

    def _cell(role: str, rule: dict) -> str:
        """Return the effective enforcement cell for a role × rule intersection."""
        allow_list = rule.get('allow') or []
        block_list = rule.get('block') or []
        enforcement = rule.get('enforcement', 'warn')
        _GROUP_NAMES = frozenset({'Agent', 'TeamAgent', 'Subagent'})

        if allow_list:
            # Role in allow list → allow; not in list → enforcement level
            # Any group name (Agent, TeamAgent, Subagent) expands to all roles
            role_matches = (role in allow_list or any(
                e in _GROUP_NAMES for e in allow_list
            ))
            return '**allow**' if role_matches else enforcement
        elif block_list:
            # Role in block list → enforcement; not in list → allow
            # Any group name (Agent, TeamAgent, Subagent) expands to all roles
            role_matches = (role in block_list or any(
                e in _GROUP_NAMES for e in block_list
            ))
            return enforcement if role_matches else '**allow**'
        return '(universal)'

    # Build column headers
    col_headers = [f"{r['id']}" for r in gated_rules]
    col_names = [f"{r['name']}" for r in gated_rules]

    lines = [
        f"# Role × Action Matrix",
        f"",
        f"catalog_version: {catalog_version}  ",
        f"*Generated by `python3 .claude/guardrails/generate_hooks.py --matrix`*",
        f"",
        f"Rows: roles from `AI_agents/project_team/`. "
        f"Cells: effective enforcement for that role.",
        f"",
    ]

    # Table header
    header = "| Role | " + " | ".join(col_headers) + " |"
    sub_header = "|      | " + " | ".join(col_names) + " |"
    separator = "|------|" + "|".join([":---:"] * len(gated_rules)) + "|"
    lines.extend([header, sub_header, separator])

    for role in role_names:
        cells = [_cell(role, r) for r in gated_rules]
        lines.append(f"| {role} | " + " | ".join(cells) + " |")

    # Unlisted roles
    unlisted_cells = [_cell('__unlisted__', r) for r in gated_rules]
    lines.append(f"| *(unlisted role)* | " + " | ".join(unlisted_cells) + " |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Script generation — one function per trigger type
# ---------------------------------------------------------------------------

def group_rules_by_trigger(rules: list[dict]) -> dict[str, list[dict]]:
    """Group enabled rules by their trigger(s)."""
    groups: dict[str, list[dict]] = {}
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        triggers = rule["trigger"]
        if isinstance(triggers, str):
            triggers = [triggers]
        for trigger in triggers:
            groups.setdefault(trigger, []).append(rule)
    return groups


def needs_strip_contexts(rules: list[dict]) -> bool:
    """Check if any rule in this trigger group uses exclude_contexts."""
    for rule in rules:
        detect = rule.get("detect", {})
        if detect.get("exclude_contexts"):
            return True
    return False


def generate_bash_guard(rules: list[dict], catalog_version: str, ack_ttl: int = 60) -> str:
    """Generate bash_guard.py content for PreToolUse/Bash rules.

    Pure Python hook — no bash wrapper. Cross-platform.

    Args:
        rules: Bash trigger rules from rules.yaml.
        catalog_version: The catalog_version string.
        ack_ttl: ack_ttl_seconds from rules.yaml top-level (default 60).

    Returns:
        Generated bash_guard.py content string.
    """
    rule_ids = ", ".join(r["id"] for r in rules)

    # Determine which helper functions are needed
    has_strip_contexts = needs_strip_contexts(rules)
    has_role_guard = needs_role_guard_import(rules)

    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""bash_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import re")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("# Path resolution (pure Python — no bash dependency)")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("command = data.get('tool_input', {}).get('command', '')")
    lines.append("cwd = data.get('cwd', os.getcwd())")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("")

    # Emit log_hit (kept for backward compat; new dispatch uses spec-format hits.jsonl loop)
    lines.append(LOG_HIT_TEMPLATE)
    lines.append("")

    # Emit strip_contexts if needed
    if has_strip_contexts:
        lines.append(STRIP_CONTEXTS_CLEAN)
        lines.append("")

    # Emit role_guard import if needed
    if has_role_guard:
        lines.append("# --- role_guard import for role-gated rules ---")
        lines.append("sys.path.insert(0, _guardrails_dir)")
        lines.append("import role_guard as _rg")
        lines.append(f"_ACK_TTL_SECONDS = {ack_ttl}  # baked from rules.yaml ack_ttl_seconds")
        lines.append("")

    # --- Multi-match enforcement logic ---
    lines.append("# ---------------------------------------------------------------------------")
    lines.append("# Rule evaluation — deny > warn > inject > log priority")
    lines.append("# _matched_rules: list of (pcode, rule_id, enforcement_str, message)")
    lines.append("# pcode: 1=deny, 2=warn, 3=log, 4=inject  (role_guard._code_map)")
    lines.append("# ---------------------------------------------------------------------------")
    lines.append("")
    lines.append("_matched_rules = []")
    lines.append("")

    for rule in rules:
        rule_id = rule["id"]
        enforcement = rule.get("enforcement", "warn")
        detect = rule.get("detect", {})
        detect_type = detect.get("type", "regex")
        message_text = get_message_text(rule)
        exclude_if = rule.get("exclude_if_matches")

        has_allow = bool(rule.get('allow'))
        has_block = bool(rule.get('block'))

        pcode = _ENFORCE_TO_PCODE.get(enforcement, 2)
        msg_escaped = escape_for_python(message_text)

        lines.append(f"# --- {rule_id}: {rule['name']} ({enforcement}) ---")

        if detect_type in ("regex", "regex_match") and (has_allow or has_block):
            # type:regex_match + role gate — pattern match then check_role()
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            exclude_contexts = detect.get("exclude_contexts")
            field = detect.get("field")

            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            elif exclude_contexts:
                lines.append(f"_match_text_{rule_id} = strip_contexts(command, {exclude_contexts!r})")
                target_var = f"_match_text_{rule_id}"
            else:
                target_var = "command"

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', command) and "

            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}):")

            lines.append(f"    _pcode, _pmsg = _rg.check_role(")
            lines.append(f"        allow={allow_repr}, block={block_repr},")
            lines.append(f"        enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"    if _pcode != 0:")
            if enforcement == "warn":
                ack_note = escape_for_python(
                    f"\n\nTo acknowledge and proceed, prefix your command with:"
                    f"\n  # ack:{rule_id} <your command>"
                )
                lines.append(
                    f"        _full_msg = (_pmsg or \"\"\"{msg_escaped}\"\"\") + \"\"\"{ack_note}\"\"\""
                )
                lines.append(
                    f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _full_msg))"
                )
            else:
                lines.append(
                    f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
                )
            lines.append("")

        elif detect_type == "always":
            # type:always — role check on every trigger (no pattern match)
            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            lines.append(f"_pcode, _pmsg = _rg.check_role(")
            lines.append(f"    allow={allow_repr}, block={block_repr},")
            lines.append(f"    enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"if _pcode != 0:")
            if enforcement == "warn":
                ack_note = escape_for_python(
                    f"\n\nTo acknowledge and proceed, prefix your command with:"
                    f"\n  # ack:{rule_id} <your command>"
                )
                lines.append(
                    f"    _full_msg = (_pmsg or \"\"\"{msg_escaped}\"\"\") + \"\"\"{ack_note}\"\"\""
                )
                lines.append(
                    f"    _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _full_msg))"
                )
            else:
                lines.append(
                    f"    _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
                )
            lines.append("")

        elif detect_type == "regex_miss" and (has_allow or has_block):
            # type:regex_miss + role gate — fires when pattern does NOT match, then check_role()
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            exclude_contexts = detect.get("exclude_contexts")
            field = detect.get("field")

            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            elif exclude_contexts:
                lines.append(f"_match_text_{rule_id} = strip_contexts(command, {exclude_contexts!r})")
                target_var = f"_match_text_{rule_id}"
            else:
                target_var = "command"

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', command) and "

            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}not any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}):")

            lines.append(f"    _pcode, _pmsg = _rg.check_role(")
            lines.append(f"        allow={allow_repr}, block={block_repr},")
            lines.append(f"        enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"    if _pcode != 0:")
            if enforcement == "warn":
                ack_note = escape_for_python(
                    f"\n\nTo acknowledge and proceed, prefix your command with:"
                    f"\n  # ack:{rule_id} <your command>"
                )
                lines.append(
                    f"        _full_msg = (_pmsg or \"\"\"{msg_escaped}\"\"\") + \"\"\"{ack_note}\"\"\""
                )
                lines.append(
                    f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _full_msg))"
                )
            else:
                lines.append(
                    f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
                )
            lines.append("")

        elif detect_type in ("regex", "regex_match"):
            # type:regex_match, no allow/block — universal rule, fires for everyone
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            exclude_contexts = detect.get("exclude_contexts")
            field = detect.get("field")

            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            elif exclude_contexts:
                lines.append(f"_match_text_{rule_id} = strip_contexts(command, {exclude_contexts!r})")
                target_var = f"_match_text_{rule_id}"
            else:
                target_var = "command"

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', command) and "

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}):")

            if enforcement == "warn":
                ack_note = escape_for_python(
                    f"\n\nTo acknowledge and proceed, prefix your command with:"
                    f"\n  # ack:{rule_id} <your command>"
                )
                full_msg = msg_escaped + ack_note
            else:
                full_msg = msg_escaped

            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{full_msg}\"\"\"))")

        elif detect_type == "regex_miss":
            # type:regex_miss, no allow/block — universal inverted rule, fires when NO match
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            exclude_contexts = detect.get("exclude_contexts")
            field = detect.get("field")

            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            elif exclude_contexts:
                lines.append(f"_match_text_{rule_id} = strip_contexts(command, {exclude_contexts!r})")
                target_var = f"_match_text_{rule_id}"
            else:
                target_var = "command"

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', command) and "

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}not any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}):")

            if enforcement == "warn":
                ack_note = escape_for_python(
                    f"\n\nTo acknowledge and proceed, prefix your command with:"
                    f"\n  # ack:{rule_id} <your command>"
                )
                full_msg = msg_escaped + ack_note
            else:
                full_msg = msg_escaped

            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{full_msg}\"\"\"))")
            lines.append("")

    # Bash ack: extract acked rule ID from command prefix
    lines.append("# --- Bash ack: '# ack:<RULE_ID>' prefix suppresses a warn-level match ---")
    lines.append("_ack_match = re.match(r'^#\\s*ack:(\\S+)', command)")
    lines.append("_acked_rule = _ack_match.group(1) if _ack_match else None")
    lines.append("")

    # hits.jsonl logging — best-effort, before dispatch
    lines.append("# --- hits.jsonl logging (spec §5.3 Item 6 — best-effort, never blocks) ---")
    lines.append("_guardrails_dir = os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')")
    lines.append("for _pcode, _rid, _enf, _msg in _matched_rules:")
    lines.append("    try:")
    lines.append("        with open(_guardrails_dir + '/hits.jsonl', 'a') as _hf:")
    lines.append("            _hf.write(json.dumps({")
    lines.append('                "ts": ts, "rule_id": _rid, "enforcement": _enf,')
    lines.append('                "tool": "Bash",')
    lines.append('                "agent": os.environ.get("CLAUDE_AGENT_NAME", "unknown"),')
    lines.append('                "target": command[:120],')
    lines.append("            }) + '\\n')")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("")

    # Dispatch block: deny > warn > inject > log
    lines.append("# --- Enforcement dispatch: deny > warn > inject > log ---")
    lines.append("if _matched_rules:")
    lines.append("    _deny_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 1]")
    lines.append("    _warn_msgs = [")
    lines.append("        _msg for _pcode, _rid, _enf, _msg in _matched_rules")
    lines.append("        if _pcode == 2 and _rid != _acked_rule")
    lines.append("    ]")
    lines.append("    _inject_rules = [(_rid, _enf, _msg) for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 4]")
    lines.append("    if _deny_msgs:")
    lines.append("        print('\\n\\n'.join(_deny_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _warn_msgs:")
    lines.append("        print('\\n\\n'.join(_warn_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _inject_rules:")
    lines.append("        pass  # inject_transform already applied before this block; proceed")
    lines.append("    # log-only (_pcode == 3): recorded to hits.jsonl above; no stderr output")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


def generate_read_guard(rules: list[dict], catalog_version: str) -> str:
    """Generate read_guard.py content for PreToolUse/Read rules.

    Pure Python hook — no bash wrapper. Cross-platform.

    Args:
        rules: Rules with PreToolUse/Read trigger.
        catalog_version: The catalog_version string.

    Returns:
        Generated read_guard.py content string.
    """
    rule_ids = ", ".join(r["id"] for r in rules)
    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""read_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import re")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("file_path = data.get('tool_input', {}).get('file_path', '')")
    lines.append("cwd = data.get('cwd', os.getcwd())")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("tool_name = 'Read'")
    lines.append("")
    lines.append(LOG_HIT_TEMPLATE)
    lines.append("")
    lines.append("_matched_rules = []")
    lines.append("")

    for rule in rules:
        rule_id = rule["id"]
        enforcement = rule["enforcement"]
        pcode = _ENFORCE_TO_PCODE.get(enforcement, 2)
        detect = rule.get("detect", {})
        detect_type = detect.get("type", "regex_match")
        pattern = detect.get("pattern")
        flags = detect.get("flags")
        flags_str = python_flags(flags)
        field = detect.get("field")
        target = detect.get("target", "file_path")
        message_text = get_message_text(rule)
        msg_escaped = escape_for_python(message_text)

        lines.append(f"# --- {rule_id}: {rule['name']} ({enforcement}) ---")

        if field:
            target_var = f"_field_{rule_id}"
            lines.append(f"{target_var} = data.get('tool_input', {{}}).get('{field}', '')")
        else:
            target_var = target  # e.g. "file_path"

        if detect_type in ("regex", "regex_match"):
            if isinstance(pattern, list):
                conds = []
                for p in pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if re.search(r'''{pattern}''', {target_var}):")
            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")

        elif detect_type == "regex_miss":
            if isinstance(pattern, list):
                conds = []
                for p in pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if not any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if not re.search(r'''{pattern}''', {target_var}):")
            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")

        lines.append("")

    # hits.jsonl logging — best-effort, before dispatch
    lines.append("# --- hits.jsonl logging (best-effort, never blocks) ---")
    lines.append("_guardrails_dir = os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')")
    lines.append("for _pcode, _rid, _enf, _msg in _matched_rules:")
    lines.append("    try:")
    lines.append("        with open(_guardrails_dir + '/hits.jsonl', 'a') as _hf:")
    lines.append("            _hf.write(json.dumps({")
    lines.append('                "ts": ts, "rule_id": _rid, "enforcement": _enf,')
    lines.append('                "tool": tool_name,')
    lines.append('                "agent": os.environ.get("CLAUDE_AGENT_NAME", "unknown"),')
    lines.append('                "target": file_path,')
    lines.append("            }) + '\\n')")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("")

    # Dispatch block: deny > warn > log
    lines.append("# --- Enforcement dispatch: deny > warn > log ---")
    lines.append("if _matched_rules:")
    lines.append("    _deny_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 1]")
    lines.append("    _warn_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 2]")
    lines.append("    if _deny_msgs:")
    lines.append("        print('\\n\\n'.join(_deny_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _warn_msgs:")
    lines.append("        print('\\n\\n'.join(_warn_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    # log-only (_pcode == 3): recorded to hits.jsonl above; no stderr output")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


def generate_glob_guard(rules: list[dict], catalog_version: str) -> str:
    """Generate glob_guard.py content for PreToolUse/Glob rules.

    Pure Python hook — no bash wrapper. Cross-platform.

    Args:
        rules: Rules with PreToolUse/Glob trigger.
        catalog_version: The catalog_version string.

    Returns:
        Generated glob_guard.py content string.
    """
    rule_ids = ", ".join(r["id"] for r in rules)
    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""glob_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import re")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("pattern = data.get('tool_input', {}).get('pattern', '')")
    lines.append("path = data.get('tool_input', {}).get('path', '')")
    lines.append("cwd = data.get('cwd', os.getcwd())")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("tool_name = 'Glob'")
    lines.append("")
    lines.append(LOG_HIT_TEMPLATE)
    lines.append("")
    lines.append("_matched_rules = []")
    lines.append("")

    for rule in rules:
        rule_id = rule["id"]
        enforcement = rule["enforcement"]
        pcode = _ENFORCE_TO_PCODE.get(enforcement, 2)
        detect = rule.get("detect", {})
        detect_type = detect.get("type", "regex_match")
        detect_pattern = detect.get("pattern")
        target = detect.get("target", "pattern")
        conditions = detect.get("conditions", {})
        flags_str = python_flags(detect.get("flags"))
        message_text = get_message_text(rule)
        msg_escaped = escape_for_python(message_text)

        lines.append(f"# --- {rule_id}: {rule['name']} ({enforcement}) ---")

        if conditions.get("path_is_root"):
            # Special condition: only fire when path is empty, ".", or CWD
            lines.append("_root_paths = {'', '.', None}")
            lines.append("if cwd:")
            lines.append("    _root_paths.add(cwd)")
            lines.append("    _root_paths.add(cwd.rstrip('/'))")
            lines.append(f"_has_pattern = '**' in {target}")
            lines.append("_is_root = path in _root_paths")
            lines.append("if _has_pattern and _is_root:")
        elif detect_type in ("regex", "regex_match"):
            if isinstance(detect_pattern, list):
                conds = []
                for p in detect_pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target})")
                lines.append(f"if any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if re.search(r'''{detect_pattern}''', {target}, {flags_str}):")
                else:
                    lines.append(f"if re.search(r'''{detect_pattern}''', {target}):")
        elif detect_type == "regex_miss":
            if isinstance(detect_pattern, list):
                conds = []
                for p in detect_pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target})")
                lines.append(f"if not any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if not re.search(r'''{detect_pattern}''', {target}, {flags_str}):")
                else:
                    lines.append(f"if not re.search(r'''{detect_pattern}''', {target}):")

        lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")
        lines.append("")

    # hits.jsonl logging — best-effort, before dispatch
    lines.append("# --- hits.jsonl logging (best-effort, never blocks) ---")
    lines.append("_guardrails_dir = os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')")
    lines.append("for _pcode, _rid, _enf, _msg in _matched_rules:")
    lines.append("    try:")
    lines.append("        with open(_guardrails_dir + '/hits.jsonl', 'a') as _hf:")
    lines.append("            _hf.write(json.dumps({")
    lines.append('                "ts": ts, "rule_id": _rid, "enforcement": _enf,')
    lines.append('                "tool": tool_name,')
    lines.append('                "agent": os.environ.get("CLAUDE_AGENT_NAME", "unknown"),')
    lines.append('                "target": f"pattern={pattern!r} path={path!r}",')
    lines.append("            }) + '\\n')")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("")

    # Dispatch block: deny > warn > log
    lines.append("# --- Enforcement dispatch: deny > warn > log ---")
    lines.append("if _matched_rules:")
    lines.append("    _deny_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 1]")
    lines.append("    _warn_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 2]")
    lines.append("    if _deny_msgs:")
    lines.append("        print('\\n\\n'.join(_deny_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _warn_msgs:")
    lines.append("        print('\\n\\n'.join(_warn_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    # log-only (_pcode == 3): recorded to hits.jsonl above; no stderr output")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


def generate_write_guard(write_rules: list[dict], edit_rules: list[dict],
                         catalog_version: str, ack_ttl: int = 60) -> str:
    """Generate write_guard.py content for PreToolUse/Write and PreToolUse/Edit rules.

    Pure Python hook — no bash wrapper. Cross-platform.
    Write and Edit share a single hook script. Rules are deduplicated by ID.

    Args:
        write_rules: Rules with PreToolUse/Write trigger.
        edit_rules: Rules with PreToolUse/Edit trigger.
        catalog_version: The catalog_version string.
        ack_ttl: ack_ttl_seconds from rules.yaml top-level (default 60).

    Returns:
        Generated write_guard.py content string.
    """
    # Merge and deduplicate rules (same rule may appear for both Write and Edit)
    seen_ids: set[str] = set()
    rules: list[dict] = []
    for rule in write_rules + edit_rules:
        if rule["id"] not in seen_ids:
            seen_ids.add(rule["id"])
            rules.append(rule)

    rule_ids = ", ".join(r["id"] for r in rules)
    has_role_guard = needs_role_guard_import(rules)

    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""write_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import re")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("tool_name = data.get('tool_name', 'Write')")
    # Handle both Write (file_path) and Edit (path) tool input keys
    lines.append("_ti = data.get('tool_input', {})")
    lines.append("file_path = _ti.get('file_path') or _ti.get('path') or ''")
    lines.append("cwd = data.get('cwd', os.getcwd())")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("")
    lines.append(LOG_HIT_TEMPLATE)
    lines.append("")

    # Compute relative path (used by multiple rules for pattern matching)
    lines.append("# Compute relative path for pattern matching")
    lines.append("rel_path = file_path")
    lines.append("try:")
    lines.append("    _abs = Path(file_path)")
    lines.append("    if not _abs.is_absolute() and cwd:")
    lines.append("        _abs = (Path(cwd) / _abs).resolve()")
    lines.append("    if cwd:")
    lines.append("        rel_path = str(_abs.relative_to(Path(cwd).resolve()))")
    lines.append("except (ValueError, TypeError, OSError):")
    lines.append("    pass")
    lines.append("")

    # Emit role_guard import if needed
    if has_role_guard:
        lines.append("# --- role_guard import for role-gated rules and ack token checks ---")
        lines.append("sys.path.insert(0, _guardrails_dir)")
        lines.append("import role_guard as _rg")
        lines.append(f"_ACK_TTL_SECONDS = {ack_ttl}  # baked from rules.yaml ack_ttl_seconds")
        lines.append("")

    # Multi-match collection
    lines.append("# ---------------------------------------------------------------------------")
    lines.append("# Rule evaluation — deny > warn > inject > log priority")
    lines.append("# _matched_rules: list of (pcode, rule_id, enforcement_str, message)")
    lines.append("# pcode: 1=deny, 2=warn, 3=log, 4=inject  (role_guard._code_map)")
    lines.append("# ---------------------------------------------------------------------------")
    lines.append("")
    lines.append("_matched_rules = []")
    lines.append("")

    # Process each rule
    for rule in rules:
        rule_id = rule["id"]
        enforcement = rule.get("enforcement", "warn")
        detect = rule.get("detect", {})
        detect_type = detect.get("type", "regex")
        message_text = get_message_text(rule)
        msg_escaped = escape_for_python(message_text)
        exclude_if = rule.get("exclude_if_matches")

        has_allow = bool(rule.get('allow'))
        has_block = bool(rule.get('block'))
        pcode = _ENFORCE_TO_PCODE.get(enforcement, 2)
        is_warn = enforcement == "warn"

        lines.append(f"# --- {rule_id}: {rule['name']} ({enforcement}) ---")

        if detect_type in ("regex", "regex_match") and (has_allow or has_block):
            # type:regex_match + role gate — pattern match then check_role() + optional ack token
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            field = detect.get("field")
            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            else:
                target = detect.get("target", "file_path")
                target_var = "rel_path" if target == "file_path" else target

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', rel_path) and "

            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}):")

            lines.append(f"    _pcode, _pmsg = _rg.check_role(")
            lines.append(f"        allow={allow_repr}, block={block_repr},")
            lines.append(f"        enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"    if _pcode == 2:  # warn — ack token flow available")
            lines.append(f"        if _rg.check_write_ack('{rule_id}', file_path, _ACK_TTL_SECONDS):")
            lines.append(f"            pass  # ack token valid — allow")
            lines.append(f"        else:")
            lines.append(f"            _ack_cmd = f'python3 .claude/guardrails/role_guard.py ack {rule_id} {{file_path}}'")
            lines.append(f"            _matched_rules.append((")
            lines.append(f"                2, '{rule_id}', '{enforcement}',")
            lines.append(f"                (_pmsg or \"\"\"{msg_escaped}\"\"\")")
            lines.append(f"                + f'\\n\\nTo acknowledge and proceed:\\n  {{_ack_cmd}}'")
            lines.append(f"                + f'\\nThen retry within {{_ACK_TTL_SECONDS}} seconds.'")
            lines.append(f"                + '\\n(If the retry still rejects, the ack token may have expired — re-run the ack command.)'")
            lines.append(f"            ))")
            lines.append(f"    elif _pcode == 1:  # deny — no ack option")
            lines.append(
                f"        _matched_rules.append((1, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append(f"    elif _pcode not in (0, 2, 1):")
            lines.append(
                f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append("")

        elif detect_type == "always":
            # type:always + role gate — fires on every trigger; role gate is the filter
            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            lines.append(f"_pcode, _pmsg = _rg.check_role(")
            lines.append(f"    allow={allow_repr}, block={block_repr},")
            lines.append(f"    enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"if _pcode == 2:  # warn — ack token flow")
            lines.append(f"    if _rg.check_write_ack('{rule_id}', file_path, _ACK_TTL_SECONDS):")
            lines.append(f"        pass")
            lines.append(f"    else:")
            lines.append(f"        _ack_cmd = f'python3 .claude/guardrails/role_guard.py ack {rule_id} {{file_path}}'")
            lines.append(f"        _matched_rules.append((")
            lines.append(f"            2, '{rule_id}', '{enforcement}',")
            lines.append(f"            (_pmsg or \"\"\"{msg_escaped}\"\"\")")
            lines.append(f"            + f'\\n\\nTo acknowledge and proceed:\\n  {{_ack_cmd}}'")
            lines.append(f"            + f'\\nThen retry within {{_ACK_TTL_SECONDS}} seconds.'")
            lines.append(f"            + '\\n(If the retry still rejects, the ack token may have expired — re-run the ack command.)'")
            lines.append(f"        ))")
            lines.append(f"elif _pcode == 1:")
            lines.append(
                f"    _matched_rules.append((1, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append(f"elif _pcode not in (0, 1, 2):")
            lines.append(
                f"    _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append("")

        elif detect_type == "regex_miss" and (has_allow or has_block):
            # type:regex_miss + role gate — fires when pattern does NOT match
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            field = detect.get("field")
            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            else:
                target = detect.get("target", "file_path")
                target_var = "rel_path" if target == "file_path" else target

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', rel_path) and "

            allow_repr = repr(rule.get('allow'))
            block_repr = repr(rule.get('block'))

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}not any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}):")

            lines.append(f"    _pcode, _pmsg = _rg.check_role(")
            lines.append(f"        allow={allow_repr}, block={block_repr},")
            lines.append(f"        enforce={enforcement!r}, message={message_text!r})")
            lines.append(f"    if _pcode == 2:  # warn — ack token flow available")
            lines.append(f"        if _rg.check_write_ack('{rule_id}', file_path, _ACK_TTL_SECONDS):")
            lines.append(f"            pass  # ack token valid — allow")
            lines.append(f"        else:")
            lines.append(f"            _ack_cmd = f'python3 .claude/guardrails/role_guard.py ack {rule_id} {{file_path}}'")
            lines.append(f"            _matched_rules.append((")
            lines.append(f"                2, '{rule_id}', '{enforcement}',")
            lines.append(f"                (_pmsg or \"\"\"{msg_escaped}\"\"\")")
            lines.append(f"                + f'\\n\\nTo acknowledge and proceed:\\n  {{_ack_cmd}}'")
            lines.append(f"                + f'\\nThen retry within {{_ACK_TTL_SECONDS}} seconds.'")
            lines.append(f"                + '\\n(If the retry still rejects, the ack token may have expired — re-run the ack command.)'")
            lines.append(f"            ))")
            lines.append(f"    elif _pcode == 1:  # deny — no ack option")
            lines.append(
                f"        _matched_rules.append((1, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append(f"    elif _pcode not in (0, 2, 1):")
            lines.append(
                f"        _matched_rules.append((_pcode, '{rule_id}', '{enforcement}', _pmsg or \"\"\"{msg_escaped}\"\"\"))"
            )
            lines.append("")

        elif detect_type in ("regex", "regex_match"):
            # type:regex_match, no allow/block — universal rule
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            field = detect.get("field")
            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            else:
                target = detect.get("target", "file_path")
                target_var = "rel_path" if target == "file_path" else target

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', rel_path) and "

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}re.search(r'''{pattern}''', {target_var}):")

            if is_warn:
                # Universal warn Write/Edit: ack token flow
                lines.append(f"    if _rg.check_write_ack('{rule_id}', file_path, _ACK_TTL_SECONDS):")
                lines.append(f"        pass  # ack token valid — allow")
                lines.append(f"    else:")
                lines.append(f"        _ack_cmd = f'python3 .claude/guardrails/role_guard.py ack {rule_id} {{file_path}}'")
                lines.append(f"        _matched_rules.append((")
                lines.append(f"            2, '{rule_id}', '{enforcement}',")
                lines.append(f"            \"\"\"{msg_escaped}\"\"\"")
                lines.append(f"            + f'\\n\\nTo acknowledge and proceed:\\n  {{_ack_cmd}}'")
                lines.append(f"            + f'\\nThen retry within {{_ACK_TTL_SECONDS}} seconds.'")
                lines.append(f"            + '\\n(If the retry still rejects, the ack token may have expired — re-run the ack command.)'")
                lines.append(f"        ))")
            else:
                lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")
            lines.append("")

        elif detect_type == "regex_miss":
            # type:regex_miss, no allow/block — universal rule (inverted match)
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            field = detect.get("field")
            if field:
                target_var = f"_field_{rule_id}"
                lines.append(f"_field_{rule_id} = data.get('tool_input', {{}}).get('{field}', '')")
            else:
                target = detect.get("target", "file_path")
                target_var = "rel_path" if target == "file_path" else target

            excl_check = ""
            if exclude_if:
                excl_check = f"not re.search(r'''{exclude_if}''', rel_path) and "

            if isinstance(pattern, list):
                conditions = []
                for p in pattern:
                    if flags_str:
                        conditions.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conditions.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if {excl_check}not any([{', '.join(conditions)}]):")
            else:
                if flags_str:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if {excl_check}not re.search(r'''{pattern}''', {target_var}):")

            if is_warn:
                lines.append(f"    if _rg.check_write_ack('{rule_id}', file_path, _ACK_TTL_SECONDS):")
                lines.append(f"        pass  # ack token valid — allow")
                lines.append(f"    else:")
                lines.append(f"        _ack_cmd = f'python3 .claude/guardrails/role_guard.py ack {rule_id} {{file_path}}'")
                lines.append(f"        _matched_rules.append((")
                lines.append(f"            2, '{rule_id}', '{enforcement}',")
                lines.append(f"            \"\"\"{msg_escaped}\"\"\"")
                lines.append(f"            + f'\\n\\nTo acknowledge and proceed:\\n  {{_ack_cmd}}'")
                lines.append(f"            + f'\\nThen retry within {{_ACK_TTL_SECONDS}} seconds.'")
                lines.append(f"            + '\\n(If the retry still rejects, the ack token may have expired — re-run the ack command.)'")
                lines.append(f"        ))")
            else:
                lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")
            lines.append("")

    # hits.jsonl logging — best-effort, before dispatch
    lines.append("# --- hits.jsonl logging (spec §5.3 Item 6 — best-effort, never blocks) ---")
    lines.append("_guardrails_dir = os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')")
    lines.append("for _pcode, _rid, _enf, _msg in _matched_rules:")
    lines.append("    try:")
    lines.append("        with open(_guardrails_dir + '/hits.jsonl', 'a') as _hf:")
    lines.append("            _hf.write(json.dumps({")
    lines.append('                "ts": ts, "rule_id": _rid, "enforcement": _enf,')
    lines.append('                "tool": tool_name,')
    lines.append('                "agent": os.environ.get("CLAUDE_AGENT_NAME", "unknown"),')
    lines.append('                "target": file_path,')
    lines.append("            }) + '\\n')")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("")

    # Dispatch block: deny > warn > inject > log
    lines.append("# --- Enforcement dispatch: deny > warn > inject > log ---")
    lines.append("if _matched_rules:")
    lines.append("    _deny_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 1]")
    lines.append("    _warn_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 2]")
    lines.append("    _inject_rules = [(_rid, _enf, _msg) for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 4]")
    lines.append("    if _deny_msgs:")
    lines.append("        print('\\n\\n'.join(_deny_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _warn_msgs:")
    lines.append("        print('\\n\\n'.join(_warn_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _inject_rules:")
    lines.append("        pass  # inject_transform already applied; proceed")
    lines.append("    # log-only (_pcode == 3): recorded to hits.jsonl above; no stderr output")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


def generate_post_compact_injector(rules: list[dict], catalog_version: str) -> str:
    """Generate post_compact_injector.py for SessionStart/compact rules.

    Pure Python hook — no bash wrapper. Cross-platform.
    """
    rule_ids = ", ".join(r["id"] for r in rules)
    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""post_compact_injector.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("")

    # Log hits for each rule
    lines.append("# Log hits")
    lines.append("try:")
    for rule in rules:
        rule_id = rule["id"]
        lines.append(f"    with open(hits_file, 'a') as _hf:")
        lines.append(f"        _hf.write(json.dumps({{")
        lines.append(f'            "ts": ts, "rule_id": "{rule_id}", "session_id": session_id,')
        lines.append(f'            "enforcement": "inject", "tool": "SessionStart", "snippet": "compact"')
        lines.append(f"        }}) + '\\n')")
    lines.append("except Exception:")
    lines.append("    pass")
    lines.append("")

    # Emit message content to stdout
    lines.append("# Emit injection content")
    for rule in rules:
        message_text = get_message_text(rule)
        msg_escaped = escape_for_python(message_text)
        lines.append(f'print("""{msg_escaped}""")')
    lines.append("")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP trigger hook generation
# ---------------------------------------------------------------------------

def trigger_to_hook_filename(trigger: str) -> str:
    """Convert an MCP trigger name to its hook filename.

    Example: 'mcp__chic__spawn_agent' → 'mcp__chic__spawn_agent_guard.py'

    Args:
        trigger: The MCP trigger name.

    Returns:
        The hook filename (without directory path).
    """
    return f"{trigger}_guard.py"


def generate_mcp_guard(trigger: str, rules: list[dict], catalog_version: str) -> str:
    """Generate a pure Python hook script for an MCP tool trigger.

    Pure Python hook — no bash wrapper. Cross-platform.
    MCP tools have no ack mechanism and no default input field.
    Rules with MCP triggers must use field: in their detect section.

    Args:
        trigger: The MCP trigger name (e.g., 'mcp__chic__spawn_agent').
        rules: Rules with this trigger.
        catalog_version: The catalog_version string.

    Returns:
        Generated hook script content string.
    """
    filename = trigger_to_hook_filename(trigger)
    rule_ids = ", ".join(r["id"] for r in rules)
    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'"""{filename} — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT')
    lines.append(f"")
    lines.append(f"Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py")
    lines.append(f"catalog_version: {catalog_version}")
    lines.append(f'Rules: {rule_ids}"""')
    lines.append("")
    lines.append("import json")
    lines.append("import os")
    lines.append("import re")
    lines.append("import sys")
    lines.append("from datetime import datetime, timezone")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("_script_dir = Path(__file__).resolve().parent")
    lines.append("_guardrails_dir = str(_script_dir.parent)")
    lines.append("os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)")
    lines.append("hits_file = str(_script_dir.parent / 'hits.jsonl')")
    lines.append("")
    lines.append("data = json.loads(sys.stdin.read())")
    lines.append("session_id = data.get('session_id', 'unknown')")
    lines.append("tool_input = data.get('tool_input', {})")
    lines.append("cwd = data.get('cwd', os.getcwd())")
    lines.append(f"tool_name = {trigger!r}")
    lines.append("ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')")
    lines.append("")
    lines.append(LOG_HIT_TEMPLATE)
    lines.append("")
    lines.append("_matched_rules = []")
    lines.append("")

    for rule in rules:
        rule_id = rule["id"]
        enforcement = rule["enforcement"]
        pcode = _ENFORCE_TO_PCODE.get(enforcement, 2)
        detect = rule.get("detect", {})
        detect_type = detect.get("type", "regex_match")
        message_text = get_message_text(rule)
        msg_escaped = escape_for_python(message_text)

        lines.append(f"# --- {rule_id}: {rule['name']} ({enforcement}) ---")

        if detect_type in ("regex", "regex_match"):
            field = detect.get("field")
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            target_var = f"_field_{rule_id}" if field else "str(tool_input)"
            if field:
                lines.append(f"{target_var} = tool_input.get('{field}', '')")
            if isinstance(pattern, list):
                conds = []
                for p in pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if re.search(r'''{pattern}''', {target_var}):")
            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")

        elif detect_type == "regex_miss":
            field = detect.get("field")
            pattern = detect.get("pattern")
            flags = detect.get("flags")
            flags_str = python_flags(flags)
            target_var = f"_field_{rule_id}" if field else "str(tool_input)"
            if field:
                lines.append(f"{target_var} = tool_input.get('{field}', '')")
            if isinstance(pattern, list):
                conds = []
                for p in pattern:
                    if flags_str:
                        conds.append(f"re.search(r'''{p}''', {target_var}, {flags_str})")
                    else:
                        conds.append(f"re.search(r'''{p}''', {target_var})")
                lines.append(f"if not any([{', '.join(conds)}]):")
            else:
                if flags_str:
                    lines.append(f"if not re.search(r'''{pattern}''', {target_var}, {flags_str}):")
                else:
                    lines.append(f"if not re.search(r'''{pattern}''', {target_var}):")
            lines.append(f"    _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', \"\"\"{msg_escaped}\"\"\"))")

        elif detect_type == "spawn_type_defined":
            # CamelCase → UPPER_SNAKE check in AI_agents/**/<UPPER_SNAKE>.md
            # Only fires when type field is non-empty and no definition file found.
            # Message may contain {type}/{UPPER_SNAKE} runtime placeholders.
            fmsg = (message_text
                    .replace('{', '{{')
                    .replace('}', '}}')
                    .replace('{{type}}', '{_type_val}')
                    .replace('{{UPPER_SNAKE}}', '{_upper_snake}'))
            fmsg_escaped = escape_for_python(fmsg)
            lines.append("_type_val = tool_input.get('type', '')")
            lines.append("if _type_val:")
            lines.append("    _s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\\1_\\2', _type_val)")
            lines.append("    _s = re.sub(r'([a-z\\d])([A-Z])', r'\\1_\\2', _s)")
            lines.append("    _upper_snake = _s.upper()")
            lines.append("    _agents_dir = Path(os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')).parent.parent / 'AI_agents'")
            lines.append("    if _agents_dir.exists():")
            lines.append("        _found = list(_agents_dir.rglob(f'{_upper_snake}.md'))")
            lines.append("        if not _found:")
            lines.append(f"            _type_msg = f\"\"\"{fmsg_escaped}\"\"\"")
            lines.append(f"            _matched_rules.append(({pcode}, '{rule_id}', '{enforcement}', _type_msg))")

        lines.append("")

    # hits.jsonl logging — best-effort, before dispatch
    lines.append("# --- hits.jsonl logging (best-effort, never blocks) ---")
    lines.append("_guardrails_dir = os.environ.get('GUARDRAILS_DIR', '.claude/guardrails')")
    lines.append("for _pcode, _rid, _enf, _msg in _matched_rules:")
    lines.append("    try:")
    lines.append("        with open(_guardrails_dir + '/hits.jsonl', 'a') as _hf:")
    lines.append("            _hf.write(json.dumps({")
    lines.append('                "ts": ts, "rule_id": _rid, "enforcement": _enf,')
    lines.append('                "tool": tool_name,')
    lines.append('                "agent": os.environ.get("CLAUDE_AGENT_NAME", "unknown"),')
    lines.append('                "target": str(tool_input),')
    lines.append("            }) + '\\n')")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("")

    # Dispatch block: deny > warn > log (no inject for MCP guards)
    lines.append("# --- Enforcement dispatch: deny > warn > log ---")
    lines.append("if _matched_rules:")
    lines.append("    _deny_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 1]")
    lines.append("    _warn_msgs = [_msg for _pcode, _rid, _enf, _msg in _matched_rules if _pcode == 2]")
    lines.append("    if _deny_msgs:")
    lines.append("        print('\\n\\n'.join(_deny_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    elif _warn_msgs:")
    lines.append("        print('\\n\\n'.join(_warn_msgs), file=sys.stderr)")
    lines.append("        sys.exit(2)")
    lines.append("    # log-only (_pcode == 3): recorded to hits.jsonl above; no stderr output")
    lines.append("sys.exit(0)")
    lines.append("")

    return "\n".join(lines)


def update_settings_json(new_triggers: list[str]) -> None:
    """Add/update PreToolUse hook entries in .claude/settings.json for MCP triggers.

    Only manages entries for triggers not in the hardcoded TRIGGER_TO_FILE set.
    Existing Bash/Read/Glob/Write/Edit entries are left untouched.
    If a matching entry exists with a stale command, it is updated in-place.

    Args:
        new_triggers: List of MCP trigger names to add/update in settings.json.
    """
    settings_path = Path('.claude/settings.json')
    if not settings_path.exists():
        return

    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[GUARDRAIL NOTE] Could not read .claude/settings.json: {e}", file=sys.stderr)
        return

    pre_tool_use = settings.setdefault('hooks', {}).setdefault('PreToolUse', [])
    changed = False

    for trigger in new_triggers:
        hook_filename = trigger_to_hook_filename(trigger)
        hook_cmd = f'python3 "$CLAUDE_PROJECT_DIR"/.claude/guardrails/hooks/{hook_filename}'
        existing = next((e for e in pre_tool_use if e.get('matcher') == trigger), None)
        if existing:
            current_cmd = (existing.get('hooks') or [{}])[0].get('command', '')
            if current_cmd != hook_cmd:
                existing['hooks'] = [{'type': 'command', 'command': hook_cmd}]
                changed = True
        else:
            pre_tool_use.append({
                'matcher': trigger,
                'hooks': [{'type': 'command', 'command': hook_cmd}]
            })
            changed = True

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2) + '\n')
        print(f"[GUARDRAIL NOTE] Updated .claude/settings.json for triggers: {new_triggers}")


# ---------------------------------------------------------------------------
# Main generation pipeline
# ---------------------------------------------------------------------------

def load_rules_d(rules_d_dir: Path) -> list[dict]:
    """Load and merge contributed rule sets from rules.d/*.yaml.

    Each file must have a top-level ``rules:`` list. Rules are appended
    in sorted filename order.

    Args:
        rules_d_dir: Path to the rules.d/ directory.

    Returns:
        List of rule dicts from all files, in sorted filename order.
    """
    if not rules_d_dir.is_dir():
        return []

    extra_rules: list[dict] = []
    for yaml_file in sorted(rules_d_dir.glob("*.yaml")):
        try:
            data = load_rules_yaml(yaml_file)
            file_rules = data.get("rules", [])
            if not isinstance(file_rules, list):
                sys.exit(
                    f"ERROR: {yaml_file} has 'rules:' but it is not a list. "
                    "Each rules.d/*.yaml file must have a top-level 'rules:' list."
                )
            extra_rules.extend(file_rules)
            print(f"  Loaded {len(file_rules)} rules from {yaml_file.name}")
        except Exception as e:
            sys.exit(f"ERROR: Failed to load {yaml_file}: {e}")

    return extra_rules


def check_id_collisions(rules: list[dict]) -> None:
    """Check for duplicate rule IDs across core and contributed rules.

    Exits non-zero if any ID collision is found.

    Args:
        rules: Full merged rules list.
    """
    seen: dict[str, int] = {}
    for rule in rules:
        rid = rule.get("id", "?")
        if rid in seen:
            sys.exit(
                f"ERROR: Duplicate rule ID '{rid}' found. "
                f"First occurrence at index {seen[rid]}, duplicate in merged rules. "
                "Core rules use R01-R99. Contributed rule sets must use their own "
                "prefix (e.g., HPC01, BIO01, SCI01) to avoid collisions."
            )
        seen[rid] = len(seen)


def generate_all(output_dir: Path) -> dict[str, str]:
    """Generate all hook scripts and return {filename: content}."""
    catalog = load_rules_yaml(RULES_YAML)
    catalog_version = catalog.get("catalog_version", "?")
    rules = catalog.get("rules", [])

    # Merge rules.d/*.yaml contributed rule sets
    rules_d_dir = SCRIPT_DIR / "rules.d"
    extra_rules = load_rules_d(rules_d_dir)
    if extra_rules:
        rules = rules + extra_rules
        print(f"  Merged {len(extra_rules)} contributed rules from rules.d/")

    # Check for ID collisions across core + contributed rules
    check_id_collisions(rules)

    # Read and validate ack_ttl_seconds
    ack_ttl = int(catalog.get("ack_ttl_seconds", 60))

    # Validate all rules before generating
    validate_rules(rules, ack_ttl)

    groups = group_rules_by_trigger(rules)

    generated: dict[str, str] = {}

    # Bash guard
    bash_rules = groups.get("PreToolUse/Bash", [])
    if bash_rules:
        generated["bash_guard.py"] = generate_bash_guard(bash_rules, catalog_version, ack_ttl)

    # Read guard
    read_rules = groups.get("PreToolUse/Read", [])
    if read_rules:
        generated["read_guard.py"] = generate_read_guard(read_rules, catalog_version)

    # Glob guard
    glob_rules = groups.get("PreToolUse/Glob", [])
    if glob_rules:
        generated["glob_guard.py"] = generate_glob_guard(glob_rules, catalog_version)

    # Write/Edit guard (merged into write_guard.py)
    write_rules = groups.get("PreToolUse/Write", [])
    edit_rules = groups.get("PreToolUse/Edit", [])
    if write_rules or edit_rules:
        generated["write_guard.py"] = generate_write_guard(
            write_rules, edit_rules, catalog_version, ack_ttl
        )

    # Post-compact injector
    compact_rules = groups.get("SessionStart/compact", [])
    if compact_rules:
        generated["post_compact_injector.py"] = generate_post_compact_injector(
            compact_rules, catalog_version
        )

    # MCP trigger guards — any trigger not in the hardcoded TRIGGER_TO_FILE set
    _hardcoded = set(TRIGGER_TO_FILE.keys())
    mcp_triggers = sorted(t for t in groups if t not in _hardcoded)
    for mcp_trigger in mcp_triggers:
        mcp_rules = groups[mcp_trigger]
        mcp_filename = trigger_to_hook_filename(mcp_trigger)
        generated[mcp_filename] = generate_mcp_guard(mcp_trigger, mcp_rules, catalog_version)

    # Write files
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in generated.items():
        filepath = output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        filepath.chmod(0o755)

    # Update settings.json for any new MCP trigger hooks
    if mcp_triggers:
        update_settings_json(mcp_triggers)

    return generated


def check_mode() -> bool:
    """Run --check: generate to temp dir, compare byte-for-byte. Returns True if clean."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        generated = generate_all(tmp_path)

        all_clean = True
        for filename, new_content in generated.items():
            committed = HOOKS_DIR / filename
            if not committed.exists():
                print(f"MISSING: {committed} (would be generated)")
                all_clean = False
                continue

            old_content = committed.read_text()
            if old_content != new_content:
                print(f"DRIFT: {committed}")
                # Show a brief diff
                diff = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=f"committed/{filename}",
                    tofile=f"generated/{filename}",
                    n=3,
                )
                diff_lines = list(diff)
                for line in diff_lines[:50]:  # limit diff output
                    print(line, end="")
                if len(diff_lines) > 50:
                    print(f"\n  ... ({len(diff_lines) - 50} more lines)")
                all_clean = False

        if all_clean:
            print("OK: all generated hooks match committed scripts.")
        return all_clean


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate hook scripts from rules.yaml"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if committed hooks match rules.yaml (exit non-zero if drift detected)",
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help=(
            "Print a markdown role × action matrix to stdout. "
            "Every role in AI_agents/project_team/ appears as a row; "
            "every role-gated rule as a column."
        ),
    )
    args = parser.parse_args()

    if args.matrix:
        catalog = load_rules_yaml(RULES_YAML)
        catalog_version = catalog.get("catalog_version", "?")
        rules = catalog.get("rules", [])
        print(generate_matrix(rules, catalog_version))
        return 0

    if args.check:
        return 0 if check_mode() else 1

    # Normal mode: generate and write
    generated = generate_all(HOOKS_DIR)
    print(f"Generated {len(generated)} hook scripts in {HOOKS_DIR}:")
    for filename in sorted(generated):
        print(f"  {filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
