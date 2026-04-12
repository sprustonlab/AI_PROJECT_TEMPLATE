# Docstring Coverage

**Overall: 76.4%** (1,208 covered / 1,581 total, 373 missing)

Generated with [interrogate](https://interrogate.readthedocs.io/) on the `claudechic` package.

---

## Per-Module Summary

Sorted worst-to-best. Modules at 100% are grouped at the end.

### Needs Attention (below 70%)

| Module | Total | Missing | Covered | Cover% |
|--------|------:|--------:|--------:|-------:|
| screens/chicsession.py | 17 | 12 | 5 | 29% |
| screens/session.py | 13 | 8 | 5 | 38% |
| screens/chat.py | 12 | 7 | 5 | 42% |
| checks/builtins.py | 15 | 8 | 7 | 47% |
| chicsessions.py | 14 | 7 | 7 | 50% |
| guardrails/parsers.py | 12 | 6 | 6 | 50% |
| widgets/layout/reviews.py | 16 | 8 | 8 | 50% |
| widgets/reports/usage.py | 8 | 4 | 4 | 50% |
| messages.py | 15 | 7 | 8 | 53% |
| screens/rewind.py | 15 | 7 | 8 | 53% |
| widgets/content/todo.py | 13 | 6 | 7 | 54% |
| widgets/prompts.py | 68 | 30 | 38 | 56% |
| guardrails/hits.py | 7 | 3 | 4 | 57% |
| widgets/modals/process_modal.py | 7 | 3 | 4 | 57% |
| widgets/primitives/spinner.py | 7 | 3 | 4 | 57% |
| hints/types.py | 26 | 11 | 15 | 58% |
| features/diff/widgets.py | 59 | 24 | 35 | 59% |
| _patches.py | 5 | 2 | 3 | 60% |
| checks/parsers.py | 5 | 2 | 3 | 60% |
| widgets/layout/indicators.py | 15 | 6 | 9 | 60% |
| widgets/primitives/button.py | 5 | 2 | 3 | 60% |
| widgets/layout/sidebar.py | 74 | 28 | 46 | 62% |
| widgets/modals/diagnostics.py | 8 | 3 | 5 | 62% |
| widgets/layout/processes.py | 11 | 4 | 7 | 64% |
| widgets/content/tools.py | 47 | 16 | 31 | 66% |
| guardrails/hooks.py | 3 | 1 | 2 | 67% |
| hints/engine.py | 3 | 1 | 2 | 67% |
| tasks.py | 3 | 1 | 2 | 67% |
| widgets/welcome.py | 16 | 5 | 11 | 69% |

### Acceptable (70%--89%)

| Module | Total | Missing | Covered | Cover% |
|--------|------:|--------:|--------:|-------:|
| widgets/modals/process_detail.py | 10 | 3 | 7 | 70% |
| features/roborev/models.py | 7 | 2 | 5 | 71% |
| widgets/content/message.py | 59 | 16 | 43 | 73% |
| widgets/modals/profile.py | 11 | 3 | 8 | 73% |
| widgets/layout/footer.py | 23 | 6 | 17 | 74% |
| \_\_main\_\_.py | 4 | 1 | 3 | 75% |
| widgets/content/collapsed_turn.py | 4 | 1 | 3 | 75% |
| app.py | 198 | 47 | 151 | 76% |
| sampling.py | 29 | 7 | 22 | 76% |
| profiling.py | 9 | 2 | 7 | 78% |
| widgets/input/history_search.py | 18 | 4 | 14 | 78% |
| widgets/reports/context.py | 9 | 2 | 7 | 78% |
| hints/state.py | 42 | 9 | 33 | 79% |
| widgets/input/autocomplete.py | 40 | 8 | 32 | 80% |
| screens/diff.py | 11 | 2 | 9 | 82% |
| workflows/engine.py | 17 | 3 | 14 | 82% |
| compact.py | 6 | 1 | 5 | 83% |
| errors.py | 6 | 1 | 5 | 83% |
| help_data.py | 6 | 1 | 5 | 83% |
| hints/parsers.py | 6 | 1 | 5 | 83% |
| checks/protocol.py | 6 | 1 | 5 | 83% |
| widgets/primitives/collapsible.py | 6 | 1 | 5 | 83% |
| enums.py | 8 | 1 | 7 | 88% |
| file_index.py | 8 | 1 | 7 | 88% |
| guardrails/tokens.py | 8 | 1 | 7 | 88% |
| workflows/parsers.py | 8 | 1 | 7 | 88% |
| agent.py | 56 | 6 | 50 | 89% |

### Good (90%--99%)

| Module | Total | Missing | Covered | Cover% |
|--------|------:|--------:|--------:|-------:|
| remote.py | 10 | 1 | 9 | 90% |
| usage.py | 10 | 1 | 9 | 90% |
| chicsession_cmd.py | 11 | 1 | 10 | 91% |
| widgets/content/diff.py | 25 | 2 | 23 | 92% |
| commands.py | 30 | 2 | 28 | 93% |
| widgets/primitives/scroll.py | 14 | 1 | 13 | 93% |
| mcp.py | 33 | 2 | 31 | 94% |
| features/worktree/git.py | 34 | 2 | 32 | 94% |
| workflows/loader.py | 16 | 1 | 15 | 94% |
| widgets/input/vi_mode.py | 20 | 1 | 19 | 95% |
| protocols.py | 24 | 1 | 23 | 96% |
| widgets/layout/chat_view.py | 25 | 1 | 24 | 96% |

### Full Coverage (100%)

agent_manager.py, analytics.py, checkpoints.py, config.py, filters.py,
formatting.py, history.py, onboarding.py, permissions.py, processes.py,
sessions.py, shell_complete.py, shell_runner.py, theme.py,
checks/adapter.py, features/diff/git.py, features/roborev/cli.py,
features/worktree/commands.py, guardrails/rules.py, guardrails/test_poc.py,
workflows/agent_folders.py, workflows/phases.py

---

## Patterns in Missing Docstrings

The 373 missing docstrings fall into a few recurring categories:

### 1. `__init__` methods (~120 items)

The single largest category. Nearly every class's `__init__` lacks a docstring.
This is common in Textual widget code where `__init__` parameters are
self-documenting or documented at the class level.

Examples: `Agent.__init__`, `ChatApp.__init__`, `Sampler.__init__`,
every widget constructor.

If excluded via `--ignore-init-method`, overall coverage would jump to ~85%+.

### 2. Textual widget `compose`/`render`/`on_click` (~80 items)

UI boilerplate methods in Textual widgets. These follow a standard Textual
pattern and their behavior is defined by the framework contract, not by
what the method does.

Examples: `DiffFileItem.compose`, `ChatScreen.compose`,
`HunkSeparator.render`, `EditIcon.on_click`.

### 3. Nested closures and callbacks (~50 items)

Inner functions used as callbacks, event handlers, or scoped helpers.
These are implementation details not part of the public API.

Examples: `Agent.interrupt._yield_then_drain`,
`ChatApp._prompt_chicsession_name.on_dismiss`,
`ChatApp._make_persist_fn.persist`.

### 4. Property setters (~15 items)

Interrogate counts property getters and setters separately. Setters
rarely need their own docstring when the getter is documented.

Examples: `ChatApp.client` (setter), `ChatApp.session_id` (setter),
`ChatApp.sdk_cwd` (setter).

### 5. Textual message `__init__` methods (~15 items)

Message dataclasses where the class docstring covers the purpose and
the `__init__` just sets attributes.

Examples: All 7 classes in `messages.py`, `WelcomeScreen.Selected.__init__`,
`HistorySearch.Selected.__init__`.

### 6. Actual gaps worth filling (~60 items)

Business logic functions and methods that would genuinely benefit from
docstrings, not just boilerplate.

Notable: `app.py` has 47 missing items. While many are widget boilerplate,
several are complex methods like `on_mount`, `on_chat_input_submitted`,
`action_clear`, `action_quit` that would benefit from documentation.

---

## Recommended Configuration

To get a more meaningful coverage number, consider this `pyproject.toml` config:

```toml
[tool.interrogate]
ignore-init-method = true
ignore-init-module = true
ignore-nested-functions = true
ignore-property-decorators = true
fail-under = 80
exclude = ["submodules/claudechic/claudechic/guardrails/test_poc.py"]
```

This would exclude the structural boilerplate (init, closures, property setters)
and focus the metric on functions and methods that genuinely need documentation.
