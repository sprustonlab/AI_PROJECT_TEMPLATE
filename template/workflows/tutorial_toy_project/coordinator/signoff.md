# Sign-off Phase

Present the finished labmeta tool to the user and wrap up the tutorial.

## Step 1: Verify Everything Works

Before presenting, do a final sanity check:
1. Run `labmeta validate` on the example data
2. Run `labmeta resolve mouse_001_session_20260406` to show merged output
3. Run `labmeta tree` to show the protocol-session hierarchy
4. Confirm all tests still pass

## Step 2: Present to User

Tell the user what was built:

> **labmeta is complete!** Here's what you built using the Project Team workflow:
>
> **4 Python modules** (~380 lines total):
> - `store.py` -- YAML file I/O and discovery
> - `schema.py` -- config validation against schema.yaml
> - `resolver.py` -- protocol + session inheritance merge
> - `cli.py` -- 7 CLI commands (init, create, validate, resolve, lock, tree, dependents)
>
> **Example data:**
> - `protocols/examples/mouse_surgery_protocol.yaml` -- cranial window protocol
> - `sessions/examples/mouse_001_session_20260406.yaml` -- mouse_001 session
> - `protocols/schema.yaml` -- validation schema
>
> **Tests:** Full test suite covering all 4 modules
>
> **Try it:**
> ```bash
> python -m labmeta tree
> python -m labmeta resolve mouse_001_session_20260406
> python -m labmeta validate
> ```

## Step 3: Tutorial Debrief

Explain what the user experienced:

> **What you saw in this tutorial:**
> 1. **Vision phase** -- pre-selected goal, user confirmation
> 2. **Specification phase** -- 4 Leadership agents analyzed the project simultaneously
> 3. **Implementation phase** -- Implementer agents built the code (you didn't write any!)
> 4. **Testing phase** -- TestEngineer verified everything
> 5. **Sign-off phase** -- final review
>
> **Workflow features exercised:**
> - Phase-gated transitions with advance checks (file-exists + manual-confirm)
> - workflow rules (deny, warn enforcement)
> - Multi-agent delegation (spawn, ask, tell)
> - Role-based permissions
> - Hints and phase-scoped instructions
>
> **Next steps:**
> - Run `/project-team` to build your own project with the full agent team
> - Run `/tutorial` to learn about rules, injections, and hints in depth
> - Edit workflow YAML files to customize the process

## Step 4: Close Agents

Close all spawned agents (Implementers, TestEngineer, Leadership). Then tell the user to run `/tutorial-toy-project stop` to deactivate the workflow.
