"""Command handler for /chicsession slash command.

Subcommands:
    /chicsession save <name>       — Snapshot all active agents
    /chicsession restore [name]    — Restore agents (shows picker if no name)
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from claudechic.chicsessions import (
    Chicsession,
    ChicsessionEntry,
    ChicsessionManager,
)

if TYPE_CHECKING:
    from claudechic.app import ChatApp

log = logging.getLogger(__name__)


def handle_chicsession_command(app: ChatApp, command: str) -> bool:
    """Route /chicsession subcommands. Returns True if handled."""
    parts = command.split(maxsplit=2)

    if len(parts) < 2:
        _show_usage(app)
        return True

    subcommand = parts[1]

    if subcommand == "save":
        name = parts[2] if len(parts) > 2 else None
        if not name:
            app.notify("Usage: /chicsession save <name>", severity="error")
            return True
        _handle_save(app, name)
        return True

    if subcommand == "restore":
        name = parts[2] if len(parts) > 2 else None
        if name:
            app.run_worker(_handle_restore(app, name))
        else:
            _show_restore_picker(app)
        return True

    _show_usage(app)
    return True


def _show_usage(app: ChatApp) -> None:
    """Display chicsession usage help."""
    from claudechic.widgets import ChatMessage

    text = (
        "**Usage:** `/chicsession <subcommand>`\n\n"
        "| Subcommand | Description |\n"
        "|------------|-------------|\n"
        "| `save <name>` | Snapshot all active agents |\n"
        "| `restore [name]` | Restore agents (shows picker if no name) |"
    )
    chat_view = app._chat_view
    if chat_view:
        msg = ChatMessage(text)
        msg.add_class("system-message")
        chat_view.mount(msg)
        chat_view.scroll_if_tailing()


def _update_sidebar_label(app: ChatApp, name: str | None) -> None:
    """Update the ChicsessionLabel in the sidebar."""
    from claudechic.widgets.layout.sidebar import ChicsessionLabel

    try:
        label = app.query_one("#chicsession-label", ChicsessionLabel)
        label.name_text = name or ""
    except Exception:
        pass  # Widget not mounted yet


def _get_root() -> Path:
    """Return git root if in a repo, else PWD."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _get_manager() -> ChicsessionManager:
    """Create a ChicsessionManager rooted at git root / cwd."""
    return ChicsessionManager(_get_root())


def _handle_save(app: ChatApp, name: str) -> None:
    """Snapshot all active agents into a chicsession."""
    agent_mgr = app.agent_mgr
    if not agent_mgr:
        app.notify("Agent manager not initialized", severity="error")
        return

    # Build entries from all active agents
    entries: list[ChicsessionEntry] = []
    for agent in agent_mgr.agents.values():
        if not agent.session_id:
            log.warning("Skipping agent '%s': no session_id yet", agent.name)
            continue
        entries.append(
            ChicsessionEntry(
                name=agent.name,
                session_id=agent.session_id,
                cwd=str(agent.cwd),
            )
        )

    if not entries:
        app.notify("No agents with sessions to save", severity="error")
        return

    # Determine active agent name
    active = agent_mgr.active
    active_name = active.name if active else entries[0].name

    cs = Chicsession(name=name, active_agent=active_name, agents=entries)
    mgr = _get_manager()
    mgr.save(cs)

    # Activate auto-save: future agent create/close will update this file
    app._chicsession_name = name
    _update_sidebar_label(app, name)

    app.notify(f"Chicsession '{name}' saved — {len(entries)} agent(s)")
    log.info("Saved chicsession '%s' with %d agents", name, len(entries))


def _show_restore_picker(app: ChatApp) -> None:
    """Show the chicsession picker screen."""
    from claudechic.screens import ChicsessionScreen

    root = _get_root()

    def on_dismiss(name: str | None) -> None:
        if name:
            app.run_worker(_handle_restore(app, name))
        if hasattr(app, "chat_input") and app.chat_input:
            app.chat_input.focus()

    app.push_screen(ChicsessionScreen(root), on_dismiss)


async def _handle_restore(app: ChatApp, name: str) -> None:
    """Load a chicsession and restore all agents."""
    mgr = _get_manager()
    try:
        cs = mgr.load(name)
    except FileNotFoundError:
        app.notify(f"Chicsession '{name}' not found", severity="error")
        return
    except ValueError as e:
        app.notify(str(e), severity="error")
        return

    agent_mgr = app.agent_mgr
    if agent_mgr is None:
        app.notify("Agent manager not initialized", severity="error")
        return

    restored = 0
    failed = 0
    for entry in cs.agents:
        if not entry.session_id:
            log.warning("Skipping agent '%s': no session_id", entry.name)
            continue

        cwd = Path(entry.cwd) if entry.cwd else Path.cwd()

        # If an agent with this name already exists, reconnect it to the saved session
        existing = agent_mgr.find_by_name(entry.name)
        if existing:
            try:
                await app._reconnect_agent(existing, entry.session_id)
                existing.session_id = entry.session_id
                # Clear and reload history in the chat view
                chat_view = app._chat_views.get(existing.id)
                if chat_view:
                    chat_view.clear()
                await app._load_and_display_history(
                    entry.session_id, cwd=cwd, agent=existing
                )
                restored += 1
                log.info("Reconnected existing agent '%s' to saved session", entry.name)
            except Exception as exc:
                log.warning("Failed to reconnect agent '%s': %s", entry.name, exc)
                failed += 1
            continue

        try:
            agent = await agent_mgr.create(
                name=entry.name,
                cwd=cwd,
                resume=entry.session_id,
                switch_to=False,
            )
            await app._load_and_display_history(
                entry.session_id, cwd=cwd, agent=agent
            )
            restored += 1
            log.info("Restored agent '%s' from chicsession", entry.name)
        except Exception as exc:
            log.warning("Failed to restore agent '%s': %s", entry.name, exc)
            failed += 1

    # Switch to the originally-active agent
    if cs.active_agent:
        target = agent_mgr.find_by_name(cs.active_agent)
        if target:
            agent_mgr.switch(target.id)

    # Activate auto-save: future agent create/close will update this file
    app._chicsession_name = name
    _update_sidebar_label(app, name)

    msg = f"Chicsession '{name}' restored — {restored} agent(s)"
    if failed:
        msg += f", {failed} failed"
    app.notify(msg)


def auto_save_chicsession(app: ChatApp) -> None:
    """Re-snapshot all active agents and save to the active chicsession.

    Called from app.py hooks (on_agent_created, on_agent_closed, on_system_message)
    when ``app._chicsession_name`` is set. No-op otherwise.
    """
    name = getattr(app, "_chicsession_name", None)
    if not name:
        return

    agent_mgr = app.agent_mgr
    if not agent_mgr:
        return

    entries: list[ChicsessionEntry] = []
    for agent in agent_mgr.agents.values():
        if not agent.session_id:
            continue
        entries.append(
            ChicsessionEntry(
                name=agent.name,
                session_id=agent.session_id,
                cwd=str(agent.cwd),
            )
        )

    if not entries:
        return

    active = agent_mgr.active
    active_name = active.name if active else entries[0].name

    cs = Chicsession(name=name, active_agent=active_name, agents=entries)
    try:
        _get_manager().save(cs)
        log.debug("Auto-saved chicsession '%s' (%d agents)", name, len(entries))
    except Exception as exc:
        log.warning("Failed to auto-save chicsession '%s': %s", name, exc)
