#!/usr/bin/env python3
"""role_guard.py — Role-based permission checks for claudechic guardrail hooks.

Framework file: do not edit per-project. Project rules live in rules.yaml.
Generated hooks import this module at runtime via sys.path; it can also be
called standalone via the ``ack`` subcommand.

Key entry points:
    get_my_role(): Resolve current agent's role from session marker.
    check_role(): Evaluate a role gate (allow/block + enforcement level).
    check_write_ack(): Validate a TTL-scoped ack token for Write/Edit tools.
    __main__ ack: Write an ack token from the CLI for warn-level Write/Edit hooks.

Key env vars:

    CLAUDE_AGENT_NAME  — agent instance identity (set by claudechic for all agents).
                         Used by: Coordinator mapping, ack token filenames, routing.
    CLAUDE_AGENT_ROLE  — agent type for role matching (set from spawn_agent(type=...)).
                         Used by: allow/block list matching in check_role().
                         Not set → role checks are inactive for that agent. No fallback.
    AGENT_SESSION_PID  — session PID (replaces CLAUDECHIC_APP_PID, with fallback).

    Exception: the Coordinator (main session agent) has no CLAUDE_AGENT_ROLE — it is
    identified by get_my_role() returning "Coordinator" via the session marker.

Team mode: active when a session marker exists at
    .claude/guardrails/sessions/ao_<AGENT_SESSION_PID>
written by setup_ao_mode.sh. Path is configurable via the GUARDRAILS_DIR env var.

Message prefix conventions (all diagnostic output goes to stderr):
    [GUARDRAIL NOTE]      — informational; allow-through, no rejection (exit 0).
    [GUARDRAIL ADVISORY]  — rejection advisory; agent must correct before retrying (exit 2).
    [GUARDRAIL WARN RXX]  — rule-level warn enforcement; ack available (exit 2).
    [GUARDRAIL DENY RXX]  — rule-level deny enforcement; no ack (exit 2).
"""
import json
import os
import sys
from pathlib import Path

# Reserved role group names — cannot be used as agent spawn names or type values.
_ROLE_GROUPS = frozenset({'Agent', 'TeamAgent', 'Subagent'})


def _role_matches(
    role_type: str,
    role_entry: str,
    in_team_mode: bool,
    is_coordinator: bool,
) -> bool:
    """Return True if role_type is covered by a role entry (group or named).

    Args:
        role_type: The agent's role type for matching. ``"Coordinator"`` for the
            main session agent (identified via session marker), or the explicit
            type from ``CLAUDE_AGENT_ROLE`` for spawned sub-agents.
            Never derived from ``CLAUDE_AGENT_NAME`` — no fallback.
        role_entry: A single entry from an ``allow:`` or ``block:`` list.
        in_team_mode: True when a session marker is present.
        is_coordinator: True when ``role_type == "Coordinator"``.

    Returns:
        True if the current agent is covered by this role entry.
    """
    if role_entry == 'Agent':
        return True                               # all agents with CLAUDE_AGENT_NAME set
    if role_entry == 'TeamAgent':
        return in_team_mode                       # Coordinator + sub-agents in team mode
    if role_entry == 'Subagent':
        return in_team_mode and not is_coordinator  # sub-agents only; Coordinator exempt
    return role_type == role_entry                # exact type match


def get_my_role() -> 'str | None':
    """Return the current agent's role type, or None when not in team mode.

    Team mode is active when a session marker exists at
    ``<GUARDRAILS_DIR>/sessions/ao_<AGENT_SESSION_PID>``. The marker is written
    by ``setup_ao_mode.sh`` when a team skill activates and deleted by
    ``teardown_ao_mode.sh`` on clean exit. Markers from prior sessions are
    automatically ignored — each claudechic session has a distinct PID.

    Reads ``AGENT_SESSION_PID`` with fallback to ``CLAUDECHIC_APP_PID``
    for backward compatibility.

    The main session agent (whose ``CLAUDE_AGENT_NAME`` equals the ``coordinator``
    field in the session marker) is mapped to ``"Coordinator"``. Spawned sub-agents
    return their ``CLAUDE_AGENT_NAME`` directly (used only for ``in_team_mode`` /
    ``is_coordinator`` logic — role type for matching always comes from
    ``CLAUDE_AGENT_ROLE``).

    Returns:
        ``None`` in any of these cases:
            - ``CLAUDE_AGENT_NAME`` is unset (not under claudechic)
            - ``AGENT_SESSION_PID`` (and ``CLAUDECHIC_APP_PID``) is unset
            - Session marker is absent (solo / non-team session)
            - Session marker is unreadable or invalid JSON (fail-open)
        ``"Coordinator"`` when the marker's ``coordinator`` field matches
            ``CLAUDE_AGENT_NAME``.
        ``CLAUDE_AGENT_NAME`` for spawned sub-agents (instance name, not role type).
    """
    name = os.environ.get('CLAUDE_AGENT_NAME')
    if not name:
        return None  # not under claudechic
    app_pid = os.environ.get('AGENT_SESSION_PID') or os.environ.get('CLAUDECHIC_APP_PID')
    if not app_pid:
        return None  # not running under claudechic
    guardrails_dir = Path(os.environ.get('GUARDRAILS_DIR', '.claude/guardrails'))
    marker = guardrails_dir / 'sessions' / f'ao_{app_pid}'
    if not marker.exists():
        return None  # no active team session → solo mode
    try:
        session = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # unreadable marker → fail-open
    # Main session agent → Coordinator (session marker records their name)
    if session.get('coordinator') == name:
        return 'Coordinator'
    # Spawned sub-agent → return instance name (used for in_team_mode / is_coordinator)
    return name


def check_role(
    allow: 'list[str] | None' = None,
    block: 'list[str] | None' = None,
    enforce: str = 'warn',
    message: str = '',
) -> 'tuple[int, str]':
    """Check whether the current agent passes a role gate.

    Called by generated hooks with ``allow``/``block`` lists **inlined** as
    Python literals at generation time — no file I/O at hook runtime. All data
    is baked in when ``generate_hooks.py`` runs.

    Internal return codes (NOT final exit codes — the hook dispatch layer handles
    exit behaviour):

        0 = allow   (no match → proceed)
        1 = deny    (hard block, exit 2, no ack option)
        2 = warn    (exit 2, ack available)
        3 = log     (exit 0, record to hits.jsonl only)
        4 = inject  (exit 0, proceed with modified input)

    Role groups in ``allow``/``block`` lists:

        Agent     — matches all agents with ``CLAUDE_AGENT_NAME`` set (solo + team)
        TeamAgent — matches Coordinator + sub-agents in team mode only
        Subagent  — matches sub-agents in team mode only (Coordinator exempt)

    ``CLAUDE_AGENT_ROLE`` is the sole source for role matching. No fallback to
    ``CLAUDE_AGENT_NAME``. Named roles are matched exactly against
    ``CLAUDE_AGENT_ROLE``.

    Args:
        allow: Role allowlist. If present, agents NOT in the list receive the
            enforcement level. Mutually exclusive with ``block``
            (caller ensures this via generate_hooks.py).
        block: Role blocklist. If present, agents IN the list receive the
            enforcement level. Mutually exclusive with ``allow``.
        enforce: Enforcement level string from the rule: ``'log'``, ``'warn'``,
            ``'deny'``, or ``'inject'``. Default: ``'warn'``.
        message: Message string returned when enforcement fires.

    Returns:
        A ``(internal_code, message_string)`` tuple.

    Raises:
        AssertionError: If neither ``allow`` nor ``block`` is supplied — this
            indicates a generator bug; this path is unreachable from generated hooks.
    """
    # No CLAUDE_AGENT_NAME → not running under claudechic → nothing fires.
    claude_name = os.environ.get('CLAUDE_AGENT_NAME')
    if not claude_name:
        return 0, ''

    # Determine team mode and Coordinator status via session marker.
    my_role = get_my_role()
    in_team_mode = my_role is not None
    is_coordinator = (my_role == 'Coordinator')

    # Solo-mode path: check BOTH allow and block lists for any Agent-group entry.
    # This ensures block: [Agent] rules fire in solo mode even when
    # CLAUDE_AGENT_ROLE is unset. _role_matches() returns True unconditionally
    # for 'Agent' — role_type is not used and can be None safely here.
    if not in_team_mode:
        all_entries = (allow or []) + (block or [])
        if not any(e == 'Agent' for e in all_entries):
            return 0, ''  # no Agent-group entry → skip in solo mode
        role_type = None  # unused: Agent group matches unconditionally

    # Team mode: resolve role type for matching.
    # CLAUDE_AGENT_ROLE is the explicit type (set via spawn_agent(type=...)).
    # No fallback to CLAUDE_AGENT_NAME — type must be set explicitly.
    # Exception: Coordinator has no CLAUDE_AGENT_ROLE — identified via session marker.
    else:
        if is_coordinator:
            role_type = 'Coordinator'
        else:
            role_type = os.environ.get('CLAUDE_AGENT_ROLE')
            if not role_type:
                print(
                    '[GUARDRAIL NOTE] CLAUDE_AGENT_ROLE is unset. '
                    'Role checks are inactive for this agent. '
                    'Spawn agent with type= to activate.',
                    file=sys.stderr,
                )
                return 0, ''

    # Map enforcement level string to internal code.
    _code_map = {'deny': 1, 'warn': 2, 'log': 3, 'inject': 4}

    def _matches(role_entry: str) -> bool:
        return _role_matches(role_type, role_entry, in_team_mode, is_coordinator)

    # Caller ensures allow and block are mutually exclusive (caught at generation time).
    if block is not None:
        if any(_matches(r) for r in block):
            return _code_map[enforce], message
        return 0, ''  # not in block list → passes

    if allow is not None:
        if any(_matches(r) for r in allow):
            return 0, ''
        return _code_map[enforce], message

    # Neither allow nor block — unreachable from generated hooks; generator bug guard.
    raise AssertionError(
        'check_role() called without allow or block — this is a generator bug. '
        'Generated hooks must always supply at least one of allow/block.'
    )


def check_write_ack(rule_id: str, file_path: str, ttl_seconds: int = 60) -> bool:
    """Check a TTL-scoped write/edit ack token for a warn-level Write/Edit rule.

    Write and Edit tool triggers cannot use the ``# ack:<RULE_ID>`` Bash prefix
    because the Claude Code hook protocol provides a file path, not a command
    string. Instead, the agent writes an ack token to a per-agent per-rule file
    in ``.claude/guardrails/acks/`` via a Bash command, then retries the write.
    This function reads and validates the token.

    The token is **not** deleted on a successful match — it persists until TTL
    expires, allowing multiple writes to the same path within the
    ``ack_ttl_seconds`` window without re-acking.

    On any invalid token (expired OR field mismatch), the stale file is deleted
    unconditionally before returning False.

    Token file: ``acks/ack_<CLAUDE_AGENT_NAME>_<rule_id>.json``
    One writer per file (per-agent keying) — no locking needed, NFS-safe.

    ``ttl_seconds`` is passed by generated hooks — baked from ``rules.yaml``'s
    top-level ``ack_ttl_seconds`` at generation time. No file I/O for TTL here.

    Args:
        rule_id: The rule ID that was warned (e.g., ``'R23'``).
        file_path: The file path being written or edited.
        ttl_seconds: Max age in seconds for the token. Passed by generated hooks
            from ``rules.yaml``'s ``ack_ttl_seconds`` field. Default: 60.

    Returns:
        True if a valid, matching, in-TTL token was found.
        False otherwise (no token, wrong rule/path/agent, expired, or any error).
    """
    from datetime import datetime, timezone

    # Agent name: use resolved role in team mode; raw CLAUDE_AGENT_NAME in solo mode.
    agent_name = get_my_role() or os.environ.get('CLAUDE_AGENT_NAME') or 'unknown'
    guardrails_dir = Path(os.environ.get('GUARDRAILS_DIR', '.claude/guardrails'))
    acks_dir = guardrails_dir / 'acks'
    ack_path = acks_dir / f'ack_{agent_name}_{rule_id}.json'

    if not ack_path.exists():
        return False

    try:
        ack = json.loads(ack_path.read_text(encoding="utf-8"))

        # Field validation — all three must match exactly.
        valid = (
            ack.get('rule_id') == rule_id
            and ack.get('file_path') == file_path
            and ack.get('agent_name') == agent_name
        )

        # TTL validation — only checked when fields match and ttl_seconds > 0.
        if valid and ttl_seconds > 0:
            try:
                ts = datetime.fromisoformat(ack['ts'].replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                valid = age <= ttl_seconds
            except (KeyError, ValueError):
                valid = False

        if not valid:
            # Delete unconditionally on ANY invalid token (mismatch or expired).
            ack_path.unlink(missing_ok=True)
            return False

        # Valid token: leave in place — persists until TTL expires.
        return True

    except Exception:
        # Fail-open: missing dir, permissions error, JSON parse failure, etc.
        return False


if __name__ == '__main__':
    import time as _time

    subcommand = sys.argv[1] if len(sys.argv) > 1 else ''

    if subcommand == 'ack':
        # Write a TTL-scoped ack token for a warn-level Write/Edit rule.
        # Usage: python3 role_guard.py ack <RULE_ID> <FILE_PATH>
        # Reads CLAUDE_AGENT_NAME from env. Atomic write via temp+rename (NFS-safe).
        # Temp file is scoped per-agent in the same directory as the final token
        # (same filesystem — required for atomic rename on NFS).
        if len(sys.argv) < 4:
            print('Usage: python3 role_guard.py ack <RULE_ID> <FILE_PATH>', file=sys.stderr)
            sys.exit(1)

        _rule_id = sys.argv[2]
        _file_path = sys.argv[3]
        _agent_name = get_my_role() or os.environ.get('CLAUDE_AGENT_NAME') or 'unknown'
        _guardrails_dir = Path(os.environ.get('GUARDRAILS_DIR', '.claude/guardrails'))
        _acks_dir = _guardrails_dir / 'acks'
        _acks_dir.mkdir(parents=True, exist_ok=True)

        _tok = {
            'rule_id': _rule_id,
            'agent_name': _agent_name,
            'file_path': _file_path,
            'ts': _time.strftime('%Y-%m-%dT%H:%M:%SZ', _time.gmtime()),
        }

        # Temp file in the same directory as the final token — same filesystem
        # → atomic rename works correctly on NFS.
        _tmp = _acks_dir / f'.tmp_ack_{_agent_name}_{_rule_id}'
        _tmp.write_text(json.dumps(_tok), encoding="utf-8")
        _token_path = _acks_dir / f'ack_{_agent_name}_{_rule_id}.json'
        _tmp.rename(_token_path)
        print(f'[GUARDRAIL NOTE] ack token written: {_token_path}')
        sys.exit(0)

    else:
        print('Usage: python3 role_guard.py ack <RULE_ID> <FILE_PATH>', file=sys.stderr)
        sys.exit(1)
