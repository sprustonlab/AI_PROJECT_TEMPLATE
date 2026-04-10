# UI Design: Hints System

> Authored by: **UIDesigner**
> References: composability.md, terminology.md, skeptic_review.md, user_alignment.md
> Consistency baseline: `claudechic/app.py` existing toast usage

---

## 1. Toast Notification Design

### Severity Mapping

Hints use **only two** of Textual's three severity levels:

| Severity | Use Case | Icon | Example |
|----------|----------|------|---------|
| `"information"` | Feature discovery, suggestions | 💡 | "Drop Python files into `mcp_tools/` for custom tools" |
| `"warning"` | Missing setup that blocks workflows | ⚠️ | "No git repo detected — launch a Git agent to set one up" |

**Never use `"error"` for hints.** Errors are reserved for real failures (existing convention in `app.py`: failed attaches, missing agents, SDK errors). Hints are advisory, never alarming.

### Timeout Durations

Based on existing `app.py` patterns (most toasts use Textual's default ~5s; explicit `timeout=5` for warnings, `timeout=1-2` for confirmations):

| Hint Severity | Timeout | Rationale |
|---------------|---------|-----------|
| `"information"` | 7 seconds | Longer than default — user needs time to read advice and decide whether to act |
| `"warning"` | 10 seconds | Actionable setup hints need more reading time; matches the "permission disabled" warning pattern |

These are slightly longer than existing app toasts because hints carry novel information. Existing toasts confirm known actions ("Copied", "Resumed") and can be shorter.

### Toast Text Format

```
[icon] [short headline]
[one-line explanation or suggested action]
```

**Examples:**

```
💡 Custom tools
  Drop Python files into mcp_tools/ to add your own tools

⚠️ No git repo
  Launch a Git agent to set one up — try /agent git

💡 Pattern Miner
  Find recurring corrections in your sessions — run the Pattern Miner

💡 Project Team
  Try /ao_project_team to launch a multi-agent team for complex tasks

💡 Guardrails
  Your guardrails only have the default rule — add project-specific rules

💡 Cluster backend
  Your cluster backend is configured and ready to use
```

### Text Style Rules

1. **Advisory tone** — "Try", "Consider", "You can" — never imperative ("Do this", "You must")
2. **No jargon** — Say "custom tools" not "MCP tools" in hint text (per terminology.md). Say "Pattern Miner" and briefly explain what it does on first mention.
3. **Actionable** — Every hint includes either a command to run or a path to look at
4. **Short** — Max 2 lines. No paragraphs. If it needs more explanation, that's what `/hints` is for.
5. **No emoji in body text** — Only the severity icon prefix (💡 or ⚠️). Consistent with existing app toast style which uses emoji sparingly (only the "⚠️ Permission checks disabled" toast uses one).

---

## 2. The `/hints` Command

### Why It Exists

The Skeptic correctly flagged that toasts are ephemeral — users may read a hint, not act immediately, and lose the information. `/hints` completes the UX loop by letting users re-surface and browse hints.

### Interaction Flow

```
User types: /hints

┌─────────────────────────────────────────────────────┐
│  Hints                                               │
│                                                     │
│  ⚠️  No git repo                            [new]   │
│     Launch a Git agent — try /agent git              │
│                                                     │
│  💡 Custom tools                             [new]   │
│     Drop Python files into mcp_tools/                │
│                                                     │
│  💡 Pattern Miner                        [seen ×1]   │
│     Find recurring corrections — run Pattern Miner   │
│                                                     │
│  ── Dismissed ──────────────────────────────────     │
│  💡 Guardrails                          [dismissed]  │
│     Add project-specific rules                       │
│                                                     │
│  [d] Dismiss selected  [a] Dismiss all  [q] Close   │
└─────────────────────────────────────────────────────┘
```

### Behavior

1. **Lists all hints whose triggers currently fire** — re-evaluates triggers at command time, so resolved hints (e.g., git repo now exists) disappear automatically
2. **Groups by state** — Active hints first (sorted by priority), then dismissed hints below a separator
3. **Status badges** — `[new]` (never shown as toast), `[seen ×N]` (shown N times), `[dismissed]` (user explicitly dismissed)
4. **Dismiss action** — `d` key dismisses the selected hint (records in hint state, won't toast again). `a` dismisses all.
5. **No pagination** — With ~6 built-in hints and a max practical total of ~15, a flat list suffices

### Implementation Note

This should be rendered as a simple command output in the chat view (like `/agent` list output), NOT as a modal screen. Keeps it lightweight and consistent with existing commands. If we later need richer interaction (filtering, searching), we can promote it to a screen.

---

## 3. Toggle UX

### How Users Disable Hints

**Primary mechanism:** `.claudechic.yaml` config flag (follows existing pattern — the file already has `experimental.*` flags and feature toggles).

```yaml
# In ~/.claude/.claudechic.yaml
hints:
  enabled: true    # default; set to false to disable all hints
```

**Convenience command:** `/hints off` and `/hints on` as shortcuts that modify the config.

```
User types: /hints off

  💡 Hints disabled. Re-enable with /hints on

User types: /hints on

  💡 Hints enabled.

User types: /hints status

  Hints: enabled
  Hints shown this session: 1 of 2
  Pending hints: 3
  Use /hints to browse, /hints off to disable.
```

### Per-Hint Dismissal vs. Global Toggle

- **Global toggle** (`/hints off`) — silences all hints. For experienced users who don't need guidance.
- **Per-hint dismissal** (via `/hints` → `d` key) — silences one hint. For users who want hints in general but find a specific one irrelevant.
- **No per-hint override in YAML** — Skeptic's simplification advice: don't build per-hint config toggles in v1. The `/hints` dismiss UX handles the 90% case. If needed later, add `hints.disabled_hints: [git-setup, mcp-tools-empty]` to YAML.

### Discovery of the Toggle

The very first hint toast in a session should include a subtle suffix:

```
💡 Custom tools
  Drop Python files into mcp_tools/ — disable with /hints off
```

Only the **first** toast per session gets this suffix. Subsequent toasts are clean. This teaches the toggle without being repetitive.

---

## 4. Priority, Throttling, and Session Rotation

### The Core Problem

A fresh project may fire 4-6 triggers simultaneously. We show max 2 toasts per session. Which 2?

### Priority Scheme

Each hint definition includes a static `priority` (integer, lower = higher priority):

| Priority | Category | Example Hints |
|----------|----------|---------------|
| 1 | **Blocking setup** — project can't function well without this | Git repo missing |
| 2 | **High-value discovery** — features with high impact, low discoverability | Guardrails customization, Project Team |
| 3 | **Enhancement** — nice-to-know, not urgent | Custom tools, Pattern Miner, Cluster readiness |
| 4 | **Command discovery** — teach a slash command the user hasn't tried | `/resume`, `/agent`, `/shell`, `/compactish` |

### Session Budget Algorithm

```
On app startup (and each 2-hour cycle):
  1. Evaluate all triggers → list of fired hints
  2. Filter out: disabled (global toggle), dismissed (per-hint state)
  3. Filter out: hints shown >= max_show_count (lifecycle exhausted)
  4. Filter out: hints in cooldown (shown too recently)
  5. Sort by: priority ASC, then last_shown ASC (least-recently-shown first)
  6. Take top N → show as toasts (N=2 at startup, N=1 at 2h cycles)
  7. Record shown hints + timestamp in hint state
```

### Rotation Across Sessions

The sort key `(priority, last_shown_timestamp)` naturally rotates hints:

- **Session 1:** Git (priority 1), Guardrails (priority 2) — both never shown, picked by priority
- **Session 2:** Git resolved (trigger no longer fires). Project Team (priority 2, never shown) gets a slot. Custom tools (priority 3, never shown) gets the other.
- **Session 3:** Project Team was shown in S2. If still firing, Pattern Miner (priority 3, never shown) and Cluster (priority 3, never shown) compete for slots. Least-recently-shown wins.

This ensures:
- Higher-priority hints always take precedence
- Within the same priority, hints rotate fairly
- Resolved hints drop out automatically (trigger returns false)
- No hint monopolizes the toast budget

### Cooldown

A hint that was shown in the **previous session** enters a 1-session cooldown if it's priority 3 (enhancement). Priority 1-2 hints have no cooldown — if git is still missing, we remind every session.

### Session Budget Configuration

```yaml
# In ~/.claude/.claudechic.yaml (optional override)
hints:
  enabled: true
  max_hints_per_session: 2   # default: 2
```

---

## 5. Toast Timing Within a Session

### Startup Delivery

Hints should not fire the instant the app launches — the user hasn't oriented yet.

```
App launch
  ├── t+0s:   App renders, SDK connects, history loads
  ├── t+2s:   First hint toast appears (if any)
  └── t+8s:   Second hint toast appears (if any)
```

- **2-second initial delay** — lets the UI settle and the user read any resume/connection toasts first (existing toasts like "Resuming abc123..." and "⚠️ Permission checks disabled" fire immediately on mount)
- **6-second gap between hint toasts** — avoids stacking. Second toast appears after the first has been visible for ~6s (first toast timeout is 7-10s, so there's brief overlap — that's fine, Textual stacks toasts)
- **Toasts persist even if the user types** — hints are small and non-intrusive; they expire naturally on their timeout. No cancellation on user input.

### 2-Hour Re-evaluation Cycle

Long sessions benefit from periodic hint refresh — the user may have resolved triggers since startup (set up git, added tools) and new hints become relevant.

```
Session timeline
  ├── t+0s:     Startup hints (up to 2 toasts, 2s delay)
  ├── t+2h:     First re-evaluation (1 toast, 5s delay)
  ├── t+4h:     Second re-evaluation (1 toast, 5s delay)
  └── ...        Every 2 hours thereafter
```

**Key UX differences from startup:**

| Aspect | Startup | 2-Hour Cycle |
|--------|---------|--------------|
| Budget | 2 toasts | 1 toast |
| Initial delay | 2 seconds | 5 seconds |
| User state | Orienting, receptive | Deep in work, less receptive |
| Re-evaluation | First check | Re-runs all triggers (resolved hints drop out) |

- **1 toast, not 2** — at the 2-hour mark the user is deep in work. One hint respects their flow while still surfacing value.
- **5-second delay** — longer than startup because we can't assume the user is idle. The extra seconds increase the chance the toast lands in a natural lull.
- **No mid-conversation special handling** — per existing design, toasts persist through user input and expire naturally. Same rule here. The toast is small, in the corner, non-blocking.
- **Visually identical to startup hints** — same 💡/⚠️ prefix, same timeout (7s/10s). No "periodic" badge or different styling. From the user's perspective, a hint is a hint regardless of when it fires.
- **The re-evaluation is the real value** — the user set up git at hour 1. At the 2h mark, the git hint no longer fires, and a previously-suppressed lower-priority hint gets its slot. This feels natural: "oh, it noticed I fixed that and is telling me something new."

### Implementation Pattern

Use `asyncio.sleep()` in a worker, matching the existing pattern:

```python
# Existing pattern from app.py line 1834-1836:
async def show_tip_after_delay() -> None:
    await asyncio.sleep(1.0)
    self.notify("Tip: Use -i flag for interactive commands", timeout=5)
```

For the 2-hour cycle, use a periodic timer (Textual's `set_interval` or an async loop with `asyncio.sleep(7200)`) that calls the same hint evaluation pipeline with `budget=1`.

---

## 6. Command Discovery Hints

### Purpose

A special hint category that teaches one slash command per session. Rotates through commands the user hasn't tried, building familiarity over time.

### Toast Text Format

```
💡 Try: /command
  [When you'd use it — not what it does mechanically]
```

### Command Rotation Order

Canonical list (agreed with Composability). Ordered by daily workflow value:

| Order | Command | Toast Text |
|-------|---------|------------|
| 1 | `/diff` | "💡 Try: /diff — see what changed since your last commit" |
| 2 | `/resume` | "💡 Try: /resume — pick up a previous conversation where you left off" |
| 3 | `/worktree` | "💡 Try: /worktree — work on a branch in isolation without stashing" |
| 4 | `/compact` | "💡 Try: /compact — summarize the conversation to free up context" |
| 5 | `/model` | "💡 Try: /model — switch between Claude models mid-conversation" |
| 6 | `/shell` | "💡 Try: /shell — open a shell without leaving the TUI" |

**What's excluded and why:**
- `/ao_project_team` — covered by state hint (`project-team-discovery`, priority 2). If dismissed there, we respect that decision across all hint mechanisms (no seam leak between Activation axis and learn-command trigger).
- `/init_project` — one-time action, not a recurring workflow command.
- `/theme`, `/vim` — niche/cosmetic preferences; users who want them will find them.
- `/analytics` — nice-to-know but not actionable in the moment.
- `Ctrl+R` — keyboard shortcut, not a slash command. Mixing categories is confusing. Keybinding hints are a potential future category.
- `/hints` — self-referential. First toast already teaches `/hints off`; no need to teach `/hints` via a hint.

### Selection Rules

1. **Skip commands the user has already used.** Check session history / hint state for command usage. A user who already uses `/resume` daily shouldn't see that hint.
2. **One command per evaluation cycle.** At startup, the command hint fills a slot only if budget remains after state-triggered hints (priority 1-3). At 2-hour cycles, the single slot may go to either a state hint or a command hint — state hints win on priority.
3. **Priority 4** — always lower than state hints. Command hints never displace "Git repo missing" or "Guardrails" hints.
4. **Show-once lifecycle** — each command is taught once. After cycling through all 6 commands, command discovery hints stop firing.

### Why "when you'd use it" not "what it does"

Users don't need a manual entry — they need to recognize the *moment* a command is useful. "Pick up where you left off" connects to a feeling ("I was working on this yesterday..."). "/resume: Resume a previous session" reads like `--help` output and doesn't stick.

---

## 7. Consistency with Existing Toast Usage

### Audit of Current Patterns

From `app.py`, existing toasts fall into these categories:

| Category | Examples | Severity | Timeout |
|----------|----------|----------|---------|
| **Confirmation** | "Copied", "New session started", "Resumed ..." | information | default or 1-2s |
| **Mode change** | "Mode: Auto-edit", "Switching to ..." | information | default |
| **Warning** | "⚠️ Permission checks disabled", "Cannot rewind while busy" | warning | 5s |
| **Error** | "No active agent", "Failed to attach" | error | default |
| **Tip** | "Tip: Use -i flag for interactive commands" | information | 5s |

Our hints are closest to the **Tip** category. The existing tip (line 1836) uses `timeout=5` and `information` severity. Our hints extend this pattern with slightly longer timeouts (7-10s) because they carry more information.

### Prefix Convention

Existing toasts use no prefix (confirmations) or `⚠️` (warnings). We add `💡` for informational hints to visually distinguish hint toasts from operational confirmations. This ensures users can tell at a glance: "that's a hint, not a status update."

---

## 8. Accessibility Notes

- **No color-only meaning** — severity is conveyed by icon (💡/⚠️) and text, not just toast background color
- **Timeout is generous** — 7-10s gives time to read; users who need more time can use `/hints` to re-read
- **Keyboard accessible** — `/hints` is a typed command, `/hints off` is a typed command. No mouse-only interactions.
- **Screen reader compatible** — Textual's `notify()` uses Textual's built-in notification system which is accessible by default

---

## 9. Summary: Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hint severity | `information` or `warning` only | Errors reserved for failures |
| Toast timeout | 7s (info), 10s (warning) | Longer than existing toasts — novel info needs reading time |
| Max at startup | 2 toasts | Skeptic-validated constraint; configurable |
| Max at 2h cycle | 1 toast | User is deep in work; respect flow |
| 2h cycle delay | 5 seconds (vs 2s at startup) | Can't assume user is idle mid-session |
| Selection algorithm | Priority ASC, then least-recently-shown | Fair rotation, high-priority always wins |
| Priority tiers | 1=blocking, 2=high-value, 3=enhancement, 4=command discovery | State hints always outrank command hints |
| Command hints | Rotate through unused commands, one per cycle | Teach "when you'd use it", not "what it does" |
| Re-surfacing | `/hints` command | Completes the ephemeral toast UX loop |
| Toggle | `.claudechic.yaml` + `/hints` command | Follows existing config pattern |
| Delivery timing | 2s delay, 6s gap; persist through user input | Toasts are small/non-intrusive; expire naturally |
| Text tone | Advisory ("Try", "Consider") | Never imperative; user is in control |
| Jargon | "custom tools" not "MCP tools"; explain Pattern Miner | Per terminology.md newcomer-blocker rules |
| First-toast suffix | "disable with /hints off" | Teaches toggle without nag |

---

## Open Questions

1. **Should `/hints` output be scrollable?** If we ever have >10 hints (custom hint definitions), a flat chat output may be long. For v1 with ~6 hints, not an issue.
2. **Should dismissed hints auto-expire?** If a hint is dismissed but 6 months later the trigger still fires, should it resurface? Leaning no for v1 — respect the dismissal permanently.
3. **Should we show a hint count in the status footer?** E.g., "3 hints" badge. Adds discoverability but also visual clutter. Recommend: skip for v1, add if users miss `/hints`.
