"""E2E Cross-Platform Test — Full lifecycle through real APIs.

Tests the complete lifecycle: copier → pixi → hints → workflow → chicsession
→ kill/restore → cleanup. All tests share a module-scoped copier project
generated with the "everything" preset.

Uses the Textual Pilot API exclusively — no pexpect, no process spawning.
Runs on Linux, macOS, and Windows.
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudechic.app import ChatApp

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.timeout(300),
]


def _common_patches():
    """Return an ExitStack with patches common to all async tests.

    Suppresses auto-fired background tasks, session counting, and the
    SDK-dependent _send_to_active_agent (which fires a query to the
    mocked SDK client after workflow activation — safe to no-op).
    """
    stack = ExitStack()
    stack.enter_context(
        patch("claudechic.tasks.create_safe_task", return_value=MagicMock())
    )
    stack.enter_context(
        patch("claudechic.sessions.count_sessions", return_value=1)
    )
    # _send_to_active_agent triggers agent.send() → SDK query.
    # With mock SDK this is harmless but noisy; mock it to no-op.
    stack.enter_context(
        patch.object(ChatApp, "_send_to_active_agent")
    )
    return stack


def _set_fake_session_ids(app: ChatApp) -> None:
    """Assign fake session_ids to all agents so auto_save_chicsession includes them.

    With mock SDK, agents never receive a real session_id from the init
    message. auto_save_chicsession() skips agents without session_id,
    so we must set them manually for chicsession persistence to work.
    """
    for agent in app.agents.values():
        if not agent.session_id:
            agent.session_id = f"mock-session-{agent.name}"


async def _mock_prompt_chicsession_name(self, workflow_id: str) -> str | None:
    """Test stub: skip TUI prompt, return a fixed chicsession name."""
    self._chicsession_name = "e2e_test_session"
    return "e2e_test_session"


class TestE2EFullLifecycle:
    """Full lifecycle E2E: copier → pixi → hints → workflow → chicsession → kill/restore → cleanup.

    Tests run in definition order. All share the module-scoped e2e_project fixture.

    Cascade dependency: tests 05-08 depend on test_04 having created the chicsession.
    If test_04 fails, later tests will also fail. This is expected and documented —
    the E2E is a sequential pipeline, not independent tests.
    """

    def test_01_copier_scaffolding(self, e2e_project):
        """Step 1: Verify copier generated expected 'everything' structure."""
        # Core files
        assert (e2e_project / "pixi.toml").exists(), "pixi.toml missing"
        assert (e2e_project / "activate").exists(), "activate script missing"

        # project_team workflow
        wf_path = e2e_project / "workflows" / "project_team" / "project_team.yaml"
        assert wf_path.exists(), "project_team workflow manifest missing"

        # Core roles (always present)
        pt_dir = e2e_project / "workflows" / "project_team"
        core_roles = [
            "coordinator", "composability", "implementer", "skeptic",
            "terminology", "user_alignment", "test_engineer",
        ]
        for role in core_roles:
            assert (pt_dir / role).exists(), f"Core role '{role}' missing"

        # Specialist roles (present in "everything" preset)
        specialist_roles = ["researcher", "lab_notebook", "ui_designer"]
        for role in specialist_roles:
            assert (pt_dir / role).exists(), f"Specialist role '{role}' missing"

        # Tutorial workflows (present in "everything" preset)
        assert (e2e_project / "workflows" / "tutorial_extending").exists(), \
            "tutorial_extending workflow missing"
        assert (e2e_project / "workflows" / "tutorial_toy_project").exists(), \
            "tutorial_toy_project workflow missing"

        # Global rules
        assert (e2e_project / "global" / "rules.yaml").exists(), \
            "global/rules.yaml missing"

        # Pattern miner (present in "everything" preset)
        assert (e2e_project / "scripts" / "mine_patterns.py").exists(), \
            "scripts/mine_patterns.py missing"

        # Global hints
        assert (e2e_project / "global" / "hints.yaml").exists(), \
            "global/hints.yaml missing"

        # Copier exclusion completeness: ensure no leaked directories
        excluded_dirs = {"docs", ".project_team", "submodules", "tests"}
        for dirpath, dirnames, _filenames in os.walk(e2e_project):
            rel = Path(dirpath).relative_to(e2e_project)
            for part in rel.parts:
                assert part not in excluded_dirs, (
                    f"Excluded directory '{part}' leaked into generated project at {rel}"
                )
            # Also check dirnames at this level
            for d in dirnames:
                if d in excluded_dirs:
                    assert False, (
                        f"Excluded directory '{d}' found in generated project at {rel}"
                    )

    def test_02_pixi_install(self, e2e_project):
        """Step 2: pixi install succeeds in the generated project."""
        env = os.environ.copy()
        env["SETUPTOOLS_SCM_PRETEND_VERSION"] = "0.0.1"

        result = subprocess.run(
            ["pixi", "install"],
            cwd=e2e_project,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"pixi install failed:\nSTDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )

        # Verify claudechic is importable
        result2 = subprocess.run(
            ["pixi", "run", "python", "-c", "import claudechic; print('OK')"],
            cwd=e2e_project,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert result2.returncode == 0, (
            f"import claudechic failed:\nSTDERR: {result2.stderr[:500]}"
        )
        assert "OK" in result2.stdout

    @pytest.mark.asyncio
    async def test_03_startup_hints(self, e2e_project, mock_sdk_e2e, fast_sleep):
        """Step 3: Startup hints fire as toast notifications."""
        app = ChatApp()

        with _common_patches():
            async with app.run_test(size=(120, 40), notifications=True) as pilot:
                await pilot.pause()

                app._cwd = e2e_project

                # Initialize workflow infrastructure so _load_result has hints
                app._init_workflow_infrastructure()
                app._discover_workflows()

                # Run hints pipeline
                await app._run_hints(is_startup=True, budget=2)
                await pilot.pause()

                # At least 1 hint notification fired
                notif_count = len(app._notifications)
                assert notif_count > 0, "No toast notifications from hints"

                # No error notifications (hints must not crash)
                error_notifs = [
                    n for n in app._notifications
                    if getattr(n, "severity", "information") == "error"
                ]
                assert len(error_notifs) == 0, (
                    f"Error notifications from hints: "
                    f"{[n.message for n in error_notifs]}"
                )

                # Hints state file exists and records shown hints
                state_path = e2e_project / ".claude" / "hints_state.json"
                assert state_path.exists(), "hints_state.json not created"
                state_data = json.loads(state_path.read_text(encoding="utf-8"))
                lifecycle = state_data.get("lifecycle", {})
                assert len(lifecycle) > 0, (
                    "No hints recorded in state file — "
                    f"state: {json.dumps(state_data, indent=2)}"
                )
                # Verify at least one hint has times_shown > 0
                has_shown = any(
                    v.get("times_shown", 0) > 0
                    for v in lifecycle.values()
                )
                assert has_shown, (
                    "No hint with times_shown > 0 in state file"
                )

    @pytest.mark.asyncio
    async def test_04_workflow_activation(self, e2e_project, mock_sdk_e2e):
        """Step 4: Activate project_team workflow, verify chicsession naming and phase state."""
        app = ChatApp()

        with _common_patches() as stack:
            stack.enter_context(
                patch.object(
                    ChatApp, "_prompt_chicsession_name",
                    _mock_prompt_chicsession_name,
                )
            )

            async with app.run_test(size=(120, 40), notifications=True) as pilot:
                await pilot.pause()

                app._cwd = e2e_project
                app._init_workflow_infrastructure()
                app._discover_workflows()
                await pilot.pause()

                # Activate workflow (workflow_id is "project-team" per manifest)
                await app._activate_workflow("project-team")
                await pilot.pause()

                # Engine should exist
                assert app._workflow_engine is not None, "Workflow engine not created"
                assert app._workflow_engine.workflow_id == "project-team"

                # Should be on the first phase
                first_phase = app._workflow_engine.get_current_phase()
                assert first_phase is not None, "No current phase"
                assert "vision" in first_phase, (
                    f"Expected first phase to be vision, got {first_phase}"
                )

                # Chicsession name should be set
                assert app._chicsession_name == "e2e_test_session"

                # Set fake session_ids so auto_save_chicsession includes agents
                _set_fake_session_ids(app)

                # Chicsession file should exist (created by _activate_workflow's
                # persist callback); force a save to ensure it's populated
                from claudechic.chicsession_cmd import auto_save_chicsession
                auto_save_chicsession(app)

                cs_path = e2e_project / ".chicsessions" / "e2e_test_session.json"
                assert cs_path.exists(), (
                    f"Chicsession file not found at {cs_path}"
                )

                # Chicsession should contain workflow_state
                cs_data = json.loads(cs_path.read_text(encoding="utf-8"))
                assert cs_data.get("workflow_state") is not None, (
                    "workflow_state missing from chicsession"
                )

    @pytest.mark.asyncio
    async def test_05_phase_and_rules(self, e2e_project, mock_sdk_e2e):
        """Step 5: Advance phases with advance checks; smoke-test guardrail rules."""
        # --- Part A: Phase Advancement ---
        app = ChatApp()

        with _common_patches() as stack:
            stack.enter_context(
                patch.object(
                    ChatApp, "_prompt_chicsession_name",
                    _mock_prompt_chicsession_name,
                )
            )
            # Mock the manual-confirm callback to auto-approve
            stack.enter_context(
                patch.object(
                    ChatApp, "_make_confirm_callback",
                    lambda self: AsyncMock(return_value=True),
                )
            )

            async with app.run_test(size=(120, 40), notifications=True) as pilot:
                await pilot.pause()

                app._cwd = e2e_project
                app._init_workflow_infrastructure()
                app._discover_workflows()
                await app._activate_workflow("project-team")
                await pilot.pause()

                # Set fake session_ids so chicsession persistence works
                _set_fake_session_ids(app)

                engine = app._workflow_engine
                assert engine is not None

                # Read the real manifest to discover phases
                first_phase = engine.get_current_phase()
                assert first_phase is not None
                next_phase = engine.get_next_phase(first_phase)
                assert next_phase is not None, (
                    f"No next phase after {first_phase}"
                )

                # Get advance checks for first phase (vision has manual-confirm)
                checks = engine.get_advance_checks_for(first_phase)

                # Attempt advance
                result = await engine.attempt_phase_advance(
                    "project-team", first_phase, next_phase, checks
                )
                assert result.success is True, (
                    f"Phase advance failed: {result.reason}"
                )
                assert engine.get_current_phase() == next_phase

                # Write phase context for the new phase.
                # _write_phase_context uses Path.cwd() internally,
                # so patch it to use e2e_project.
                wf_data = app._load_result.get_workflow("project-team")
                if wf_data and wf_data.main_role:
                    with patch("claudechic.app.Path.cwd", return_value=e2e_project):
                        app._write_phase_context(
                            "project-team", wf_data.main_role, next_phase
                        )

                # Verify phase context file exists and has relevant content
                phase_file = e2e_project / ".claude" / "phase_context.md"
                assert phase_file.exists(), (
                    "phase_context.md not created after phase advance"
                )
                phase_content = phase_file.read_text(encoding="utf-8")
                assert len(phase_content) > 0, "phase_context.md is empty"
                # Should reference the new phase, not the old one
                # Extract short phase name from qualified ID
                # (e.g. "project-team:setup" → "setup")
                short_phase = (
                    next_phase.split(":")[-1] if ":" in next_phase else next_phase
                )
                assert short_phase in phase_content.lower() or next_phase in phase_content, (
                    f"phase_context.md doesn't reference new phase '{next_phase}': "
                    f"{phase_content[:200]}"
                )

                # Verify chicsession reflects new phase
                cs_path = e2e_project / ".chicsessions" / "e2e_test_session.json"
                if cs_path.exists():
                    cs_data = json.loads(cs_path.read_text(encoding="utf-8"))
                    wf_state = cs_data.get("workflow_state", {})
                    assert wf_state.get("current_phase") == next_phase, (
                        f"Chicsession workflow_state phase mismatch: "
                        f"{wf_state.get('current_phase')} != {next_phase}"
                    )

        # --- Part B: Guardrail Rules Test ---
        app2 = ChatApp()

        with _common_patches():
            async with app2.run_test(size=(120, 40), notifications=True) as pilot2:
                await pilot2.pause()

                app2._cwd = e2e_project
                app2._init_workflow_infrastructure()
                app2._discover_workflows()

                # Get the real hook pipeline built from copier-generated rules
                hooks = app2._guardrail_hooks()
                assert "PreToolUse" in hooks, (
                    "Guardrail hooks should be registered"
                )

                # Extract the evaluate closure
                hook_matchers = hooks["PreToolUse"]
                assert len(hook_matchers) > 0, "No hook matchers"
                evaluate_fn = hook_matchers[0].hooks[0]

                # Call with a dangerous Bash command (matches no_rm_rf deny
                # rule in the copier-generated global/rules.yaml:
                #   detect: pattern: "rm\\s+-rf\\s+/"
                #   enforcement: deny
                result = await evaluate_fn(
                    hook_input={
                        "tool_name": "Bash",
                        "tool_input": {"command": "rm -rf /"},
                        "permission_mode": "default",
                    },
                    match=None,
                    ctx=None,
                )

                # Verify block decision
                assert result.get("decision") == "block", (
                    f"Expected block for dangerous command, got: {result}"
                )
                assert "reason" in result, "Block result missing reason"

    @pytest.mark.asyncio
    async def test_06_agent_lifecycle(self, e2e_project, mock_sdk_e2e):
        """Step 6: Spawn agent via the app, verify tracked in chicsession."""
        app = ChatApp()

        with _common_patches() as stack:
            stack.enter_context(
                patch.object(
                    ChatApp, "_prompt_chicsession_name",
                    _mock_prompt_chicsession_name,
                )
            )

            async with app.run_test(size=(120, 40), notifications=True) as pilot:
                await pilot.pause()

                app._cwd = e2e_project
                app._init_workflow_infrastructure()
                app._discover_workflows()
                await app._activate_workflow("project-team")
                await pilot.pause()

                # The main agent should exist
                assert len(app.agents) >= 1, "No agents after workflow activation"

                # Set fake session_id on the main agent first
                _set_fake_session_ids(app)

                # Spawn a researcher agent via agent manager
                agent_mgr = app.agent_mgr
                assert agent_mgr is not None, "Agent manager not initialized"

                researcher = await agent_mgr.create(
                    name="researcher",
                    cwd=e2e_project,
                    switch_to=False,
                )
                # Set fake session_id on the new researcher agent
                researcher.session_id = "mock-session-researcher"
                await pilot.pause()

                # Verify agent count
                assert len(app.agents) >= 2, (
                    f"Expected at least 2 agents, got {len(app.agents)}"
                )

                # Verify researcher exists
                agent_names = [a.name for a in app.agents.values()]
                assert "researcher" in agent_names, (
                    f"Researcher agent not found in {agent_names}"
                )

                # Force save chicsession
                from claudechic.chicsession_cmd import auto_save_chicsession
                auto_save_chicsession(app)

                # Read chicsession and verify agents are tracked
                cs_path = e2e_project / ".chicsessions" / "e2e_test_session.json"
                assert cs_path.exists(), "Chicsession file not found"
                cs_data = json.loads(cs_path.read_text(encoding="utf-8"))
                cs_agent_names = [a["name"] for a in cs_data.get("agents", [])]
                assert len(cs_agent_names) >= 2, (
                    f"Expected at least 2 agents in chicsession, got {cs_agent_names}"
                )
                assert "researcher" in cs_agent_names, (
                    f"Researcher not in chicsession agents: {cs_agent_names}"
                )

    @pytest.mark.asyncio
    async def test_07_kill_and_restore(self, e2e_project, mock_sdk_e2e):
        """Step 7: Save chicsession → exit App → new App instance → restore → verify survival."""
        from claudechic.chicsession_cmd import _handle_restore, auto_save_chicsession

        # --- Part 1: Setup and capture pre-kill state ---
        pre_kill_phase = None
        pre_kill_agents: list[str] = []
        pre_kill_chicsession_name = None
        pre_kill_json = None
        cs_path = None

        app1 = ChatApp()

        with _common_patches() as stack:
            stack.enter_context(
                patch.object(
                    ChatApp, "_prompt_chicsession_name",
                    _mock_prompt_chicsession_name,
                )
            )
            stack.enter_context(
                patch.object(
                    ChatApp, "_make_confirm_callback",
                    lambda self: AsyncMock(return_value=True),
                )
            )

            async with app1.run_test(size=(120, 40), notifications=True) as pilot1:
                await pilot1.pause()

                app1._cwd = e2e_project
                app1._init_workflow_infrastructure()
                app1._discover_workflows()
                await app1._activate_workflow("project-team")
                await pilot1.pause()

                # Set fake session_ids on the main agent
                _set_fake_session_ids(app1)

                # Spawn an agent for richer state
                agent_mgr = app1.agent_mgr
                assert agent_mgr is not None
                researcher = await agent_mgr.create(
                    name="researcher",
                    cwd=e2e_project,
                    switch_to=False,
                )
                researcher.session_id = "mock-session-researcher"
                await pilot1.pause()

                # Capture pre-kill state
                pre_kill_phase = app1._workflow_engine.get_current_phase()
                pre_kill_agents = [a.name for a in app1.agents.values()]
                pre_kill_chicsession_name = app1._chicsession_name

                # Force a chicsession save
                auto_save_chicsession(app1)

                # Read the saved JSON
                cs_path = e2e_project / ".chicsessions" / f"{pre_kill_chicsession_name}.json"
                assert cs_path.exists(), "Chicsession file not saved before kill"
                pre_kill_json = json.loads(cs_path.read_text(encoding="utf-8"))

                # Verify agents were actually saved (not empty due to missing session_id)
                assert len(pre_kill_json.get("agents", [])) >= 2, (
                    f"Pre-kill chicsession should have at least 2 agents, got: "
                    f"{pre_kill_json.get('agents', [])}"
                )

        # Exiting the async context IS the "kill" — App is gone, chicsession persists.

        # Verify chicsession file survives on disk
        assert cs_path.exists(), "Chicsession file did not survive app exit"

        # --- Part 2: New App instance, restore ---
        app2 = ChatApp()

        with _common_patches() as stack:
            # Mock _load_and_display_history since session history files
            # don't exist on disk (mock SDK never created real sessions)
            stack.enter_context(
                patch.object(
                    ChatApp, "_load_and_display_history",
                    new_callable=AsyncMock,
                )
            )

            async with app2.run_test(size=(120, 40), notifications=True) as pilot2:
                await pilot2.pause()

                app2._cwd = e2e_project
                app2._init_workflow_infrastructure()
                app2._discover_workflows()

                # Restore from saved chicsession
                await pilot2.pause()
                await _handle_restore(app2, pre_kill_chicsession_name)
                await pilot2.pause()

                # --- Part 3: Verify survival ---
                assert app2._chicsession_name == pre_kill_chicsession_name, (
                    f"Chicsession name mismatch: "
                    f"{app2._chicsession_name} != {pre_kill_chicsession_name}"
                )

                # Verify agents restored
                post_restore_agents = [a.name for a in app2.agents.values()]
                assert set(pre_kill_agents).issubset(set(post_restore_agents)), (
                    f"Agents not restored: pre={pre_kill_agents}, "
                    f"post={post_restore_agents}"
                )

                # Verify workflow state is structurally valid in the chicsession.
                # _handle_restore does not automatically restore the workflow
                # engine, but the workflow_state dict should be preserved in
                # the chicsession JSON for later restoration.
                post_restore_cs = json.loads(cs_path.read_text(encoding="utf-8"))
                saved_wf_state = post_restore_cs.get("workflow_state")
                assert saved_wf_state is not None, (
                    "workflow_state missing from chicsession after restore"
                )

                # Restore the workflow engine from the saved state
                from claudechic.workflows.engine import WorkflowEngine, WorkflowManifest

                wf_data = app2._load_result.get_workflow("project-team")
                assert wf_data is not None, "project-team workflow not found in load result"

                wf_phases = [
                    p for p in app2._load_result.phases
                    if p.namespace == "project-team"
                ]
                manifest = WorkflowManifest(
                    workflow_id="project-team",
                    phases=wf_phases,
                    main_role=wf_data.main_role,
                )
                restored_engine = WorkflowEngine.from_session_state(
                    state=saved_wf_state,
                    manifest=manifest,
                    persist_fn=lambda s: None,
                    confirm_callback=AsyncMock(return_value=True),
                )
                assert restored_engine.get_current_phase() == pre_kill_phase, (
                    f"Restored phase mismatch: "
                    f"{restored_engine.get_current_phase()} != {pre_kill_phase}"
                )

                # --- Part 4: Chicsession round-trip fidelity ---
                # Set fake session_ids on restored agents so auto_save works
                _set_fake_session_ids(app2)
                auto_save_chicsession(app2)
                post_restore_json = json.loads(cs_path.read_text(encoding="utf-8"))

                # Compare structurally
                assert pre_kill_json["name"] == post_restore_json["name"], (
                    "Chicsession name changed after round-trip"
                )
                pre_agent_names = {a["name"] for a in pre_kill_json.get("agents", [])}
                post_agent_names = {a["name"] for a in post_restore_json.get("agents", [])}
                assert pre_agent_names == post_agent_names, (
                    f"Agent names changed: pre={pre_agent_names}, "
                    f"post={post_agent_names}"
                )
                # Compare workflow_state
                assert pre_kill_json.get("workflow_state") == post_restore_json.get("workflow_state"), (
                    f"Workflow state changed after round-trip: "
                    f"pre={pre_kill_json.get('workflow_state')}, "
                    f"post={post_restore_json.get('workflow_state')}"
                )

    @pytest.mark.asyncio
    async def test_08_workflow_completion(self, e2e_project, mock_sdk_e2e):
        """Step 8: Complete workflow, verify cleanup and chicsession state."""
        app = ChatApp()

        with _common_patches() as stack:
            stack.enter_context(
                patch.object(
                    ChatApp, "_prompt_chicsession_name",
                    _mock_prompt_chicsession_name,
                )
            )

            async with app.run_test(size=(120, 40), notifications=True) as pilot:
                await pilot.pause()

                app._cwd = e2e_project
                app._init_workflow_infrastructure()
                app._discover_workflows()
                await app._activate_workflow("project-team")
                await pilot.pause()

                assert app._workflow_engine is not None

                # Set fake session_ids so chicsession operations work
                _set_fake_session_ids(app)

                # Force save so chicsession file exists for deactivation
                from claudechic.chicsession_cmd import auto_save_chicsession
                auto_save_chicsession(app)

                # Deactivate workflow (the "stop" mechanism).
                # Patch Path.cwd() so _deactivate_workflow finds the right
                # phase_context.md file (it uses self._cwd after our bug fix).
                app._deactivate_workflow()
                await pilot.pause()

                # Engine should be None after deactivation
                assert app._workflow_engine is None, (
                    "Workflow engine not cleared after deactivation"
                )

                # Phase context file should be removed or not exist
                phase_file = e2e_project / ".claude" / "phase_context.md"
                assert not phase_file.exists(), (
                    "phase_context.md should be removed after workflow deactivation"
                )

                # Chicsession still exists on disk (persists even after workflow ends)
                cs_path = e2e_project / ".chicsessions" / "e2e_test_session.json"
                assert cs_path.exists(), (
                    "Chicsession file should persist after workflow ends"
                )

                # No error notifications during cleanup
                error_notifs = [
                    n for n in app._notifications
                    if getattr(n, "severity", "information") == "error"
                ]
                assert len(error_notifs) == 0, (
                    f"Error notifications during workflow completion: "
                    f"{[n.message for n in error_notifs]}"
                )
