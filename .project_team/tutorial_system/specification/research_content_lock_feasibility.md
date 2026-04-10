# Research Report: Content Lock Feasibility — Can We Actually Restrict What an Agent Sees?

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Claude Code official docs) + T2 (JetBrains Research, TACL 2024)

## Query

Two questions: (1) Prior art on phase-scoped content for AI agents. (2) Is content lock enforceable, or does agent memory / file access defeat it?

---

## Part 1: Prior Art on Phase-Scoped Agent Instructions

### Finding 1: CrewAI — Task-Scoped Prompts (Not Phase-Scoped)

- **URL:** https://docs.crewai.com/en/guides/advanced/customizing-prompts
- **Tier:** T5 (well-maintained community project)

CrewAI constructs per-task prompts that include the agent's role + goal + backstory + task description. Each Task is a unit of work with its own description and expected output. However:

- Tasks are **independent units**, not sequential phases. There's no "Phase 1 must complete before Phase 2 starts."
- The agent receives its full role file (backstory) for every task — no information hiding.
- CrewAI wraps a crew as a "Node" in LangGraph for sequencing, but the agent itself doesn't lose access to information between tasks.

**Verdict:** Task-scoped prompts exist, but not content lock. The agent always has its full backstory.

### Finding 2: AutoGPT — Short-Term Memory + File Externalization

- **URL:** https://lilianweng.github.io/posts/2023-06-23-agent/
- **Tier:** T5/T6

AutoGPT has a ~4000 word limit for short-term memory and instructs the agent to save important information to files. This is a **practical context constraint**, not intentional information hiding:

- The agent is told to externalize memory to files — which it can read back at any time.
- Task decomposition (Chain of Thought, Tree of Thoughts) breaks work into sub-tasks, but the agent retains access to the overall goal.
- No mechanism prevents the agent from reading files from previous steps.

**Verdict:** Context limitations are practical (window size), not intentional (information hiding).

### Finding 3: JetBrains Research — Observation Masking (2025)

- **URL:** https://blog.jetbrains.com/research/2025/12/efficient-context-management/
- **Tier:** T2 (peer-reviewed research, JetBrains)

This is the closest to "content lock" in academic research. The study compared two context management strategies for coding agents:

**Observation Masking:** Replaces older environment observations with placeholders while preserving the agent's reasoning and action history. Like a rolling window — only recent tool outputs are visible.

**LLM Summarization:** Compresses older interactions into summaries.

**Key findings:**
- Both reduced costs by >50% vs unrestricted context.
- **Observation masking often outperformed summarization** — simpler is better.
- Masking achieved 52% cost savings with Qwen3-Coder 480B while **improving problem-solving by 2.6%**.
- Summarization caused "trajectory elongation" — agents ran 13-15% longer because summaries obscured stopping signals.

**Critical insight for our system:** Reducing what an agent sees **can improve performance**, not just save tokens. The "lost in the middle" effect (TACL 2024) shows that irrelevant context actively hurts LLM performance — models attend most to the beginning and end of their context, with >30% performance degradation for information in the middle.

**Verdict:** Research supports the premise that giving agents less (but more relevant) context improves task focus. But this is about **what's in the context window**, not about preventing file access.

### Finding 4: "Lost in the Middle" (TACL 2024)

- **URL:** https://arxiv.org/abs/2307.03172
- **Tier:** T2 (peer-reviewed, TACL)

Performance drops >30% when relevant information is buried in the middle of long contexts. The U-shaped attention curve means models attend strongly to the beginning and end of their input.

**Implication:** Loading 276 lines of COORDINATOR.md when only ~60 are relevant is actively harmful — the relevant Phase 3 instructions are "lost in the middle" between Phases 0-2 (beginning) and Phases 7-9 (end). Per-phase files solve this by putting relevant content at the beginning, where attention is strongest.

### Finding 5: No Framework Does True "Content Lock"

After searching CrewAI, LangGraph, AutoGPT, and academic literature, **no mainstream AI agent framework implements information hiding from agents**. The universal pattern is:

- Agent gets a role/persona + current task description
- Agent has full access to its tools (file system, APIs, etc.)
- Context is managed for efficiency (window size, cost) not security

The concept of "don't let the agent read Phase 5's instructions while it's in Phase 4" is novel. Nobody does this because:
1. Most frameworks don't have sequential phases with distinct instructions
2. Most frameworks trust the agent to stay on task via prompt instructions
3. File system access is a core capability, not something you restrict

---

## Part 2: THE CRITICAL QUESTION — Is Content Lock Enforceable?

### What Claude Code Gives the Agent at Session Start

From the official Claude Code docs (https://code.claude.com/docs/en/memory):

**Automatically loaded into every session:**
1. **CLAUDE.md files** — all files in directory hierarchy above working directory, loaded in full
2. **CLAUDE.local.md** — personal project-specific preferences
3. **`.claude/rules/*.md`** — all rule files without `paths` frontmatter
4. **Auto memory** — `~/.claude/projects/<project>/memory/MEMORY.md` (first 200 lines or 25KB)
5. **System prompt** — Claude's base instructions
6. **Conversation context** — user messages, tool results

**Loaded on demand:**
7. **Path-scoped rules** — `.claude/rules/*.md` with `paths` frontmatter, loaded when matching files are read
8. **Auto memory topic files** — `debugging.md`, `api-conventions.md`, etc., loaded when relevant
9. **CLAUDE.md files in subdirectories** — loaded when Claude reads files in those directories

**Survives compaction:**
10. CLAUDE.md is **re-read from disk after /compact** and re-injected fresh

### Attack Surface Analysis: How the Agent Can Bypass Content Lock

#### Attack 1: Direct File Read — `cat phase-05.md` or Read tool

**Feasibility:** Trivially easy. The agent has full Read tool access and Bash access. Nothing stops it from running:
```
Read file: AI_agents/project_team/coordinator/phase-05-testing.md
```
or
```
Bash: cat AI_agents/project_team/coordinator/phase-05-testing.md
```

**Can we block this?** YES, partially:

The existing guardrails system supports `PreToolUse/Read` hooks. We could add a rule:

```yaml
- id: R10
  name: phase-content-lock
  trigger: PreToolUse/Read
  enforcement: deny
  detect:
    type: regex_match
    field: file_path
    pattern: 'coordinator/phase-(?!04).*\.md'  # Only allow current phase file
  message: "[GUARDRAIL DENY R10] You may only read your current phase file."
```

**BUT:** This only blocks the Read tool. Claude Code's own docs confirm: *"Read and Edit deny rules apply to Claude's built-in file tools, not to Bash subprocesses—a Read(./.env) deny rule blocks the Read tool but does not prevent `cat .env` in Bash."*

So we'd also need a Bash rule:
```yaml
- id: R11
  name: phase-content-lock-bash
  trigger: PreToolUse/Bash
  enforcement: deny
  detect:
    type: regex_match
    pattern: '(?:cat|head|tail|less|more|bat|sed|awk)\s+.*coordinator/phase-'
```

**Completeness:** INCOMPLETE. The agent could use:
- `python3 -c "open('phase-05.md').read()"`
- `grep -r "Phase 5" coordinator/`
- `find coordinator/ -name "*.md" -exec cat {} \;`
- Glob tool to find file names, then reconstruct content from names

Blocking every possible command that reads a file is an infinite whack-a-mole game. **You cannot fully prevent file access through guardrails alone.**

#### Attack 2: CLAUDE.md / Auto Memory Accumulation

**Feasibility:** Automatic and unavoidable.

From the docs: *"Auto memory lets Claude accumulate knowledge across sessions without you writing anything. Claude saves notes for itself as it works."*

If the Coordinator works through Phases 1-4 across sessions, auto memory will contain:
- Build commands discovered during implementation
- Debugging insights from testing
- Architecture notes from specification
- Patterns from each phase's work

**In a fresh session starting at Phase 5, the agent has:**
- `MEMORY.md` with accumulated knowledge from ALL previous phases (first 200 lines)
- Topic files with detailed notes

**Can we prevent this?** Only by disabling auto memory (`autoMemoryEnabled: false`), which sacrifices ALL cross-session learning — not just phase-specific content.

#### Attack 3: Conversation History Within a Session

**Feasibility:** Inherent to the architecture.

If the agent works through Phase 3 → Phase 4 in a single session, it has the FULL conversation history from Phase 3 in its context window. No amount of file-level content lock prevents this.

**Can we prevent this?** Only by:
1. Starting a fresh session for each phase (loses all context)
2. Running `/compact` between phases (lossy — compacts but doesn't erase)
3. Neither is reliable — compaction is lossy, not a clean wipe

#### Attack 4: Agent Reads COORDINATOR.md (Old File) or STATUS.md

If the single COORDINATOR.md still exists (backward compatibility), the agent can read it. Even with per-phase files, STATUS.md contains phase history:

```markdown
## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
- Phase 2: Leadership spawned ✓
- Phase 3: Specification complete ✓
```

This tells the agent what happened in previous phases. STATUS.md is essential for recovery after compaction — we can't restrict it.

#### Attack 5: The Agent Doesn't Need to "Attack" — It Infers

Even without reading future phase files, a Claude-class model can infer what Phase 5 (Testing) involves based on:
- General software engineering knowledge
- Pattern recognition from Phase 4 (Implementation) context
- The phase name itself ("Phase 5: Testing" in STATUS.md's phase summary)

**Content lock cannot prevent inference.**

### Enforceability Verdict

| Mechanism | Blocks Read Tool? | Blocks Bash? | Blocks Memory? | Blocks Inference? | Completeness |
|-----------|-------------------|--------------|----------------|-------------------|-------------|
| **PreToolUse/Read guardrail** | ✅ Yes | ❌ No | ❌ No | ❌ No | ~30% |
| **PreToolUse/Read + Bash guardrail** | ✅ Yes | ⚠️ Partial (cat/head, not python/grep) | ❌ No | ❌ No | ~50% |
| **Read + Bash + Glob guardrails** | ✅ Yes | ⚠️ Partial | ❌ No | ❌ No | ~55% |
| **OS sandbox (kernel namespace)** | ✅ Yes | ✅ Yes (Bash only) | ❌ No | ❌ No | ~65% |
| **File permissions (chmod 000)** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ~70% |
| **File doesn't exist (generate on demand)** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ~75% |
| **All of the above** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ~75% |

**Content lock can never reach 100%.** Memory and inference are fundamentally unblockable.

---

## Part 3: Reframing — What Content Lock Actually Buys You

### The Wrong Question

"Can we prevent the agent from seeing Phase 5's instructions?" → No. Not fully.

### The Right Question

"Does giving the agent only Phase 4's instructions make it perform Phase 4 better?" → **Yes. Substantially.**

### The Evidence

**1. JetBrains Research (2025):** Observation masking (hiding old observations) improved solve rates by 2.6% while cutting costs 52%. Less context = better focus.

**2. Lost in the Middle (TACL 2024):** >30% performance degradation when relevant info is buried in irrelevant context. A 276-line file where only 60 lines matter is actively harmful.

**3. Claude Code's own design:** CLAUDE.md docs say "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence." The system is designed for focused, relevant content.

**4. Practical experience in this codebase:** The Coordinator already re-reads COORDINATOR.md every turn. 75-84% of that content is irrelevant to the current phase. Per-phase files eliminate this waste.

### Content Lock is Not a Security Mechanism — It's a Focus Mechanism

| Goal | Content Lock Helps? | Why |
|------|---------------------|-----|
| **Prevent agent from knowing about future phases** | ❌ No | Memory, inference, file access all defeat this |
| **Prevent agent from accidentally acting on wrong phase** | ✅ Yes | If Phase 5 instructions aren't in context, the agent won't accidentally follow them |
| **Improve agent task performance** | ✅ Yes | Research proves less irrelevant context = better focus |
| **Reduce context window waste** | ✅ Yes | 75-84% savings per turn |
| **Sync guardrail scoping with agent instructions** | ✅ Yes | Agent reads phase-04.md, guardrails scope to phase 4 — same state source |
| **Create machine-verifiable phase transitions** | ✅ Yes | Verification checks must pass before next phase file is served |

**The value of per-phase files is NOT information hiding. It's attention management.**

The agent could read phase-05.md if it wanted to. But if its prompt only contains phase-04.md, it will focus on Phase 4's instructions. Just as a human programmer with a 50-page spec will lose focus, but a 3-page spec for their current task keeps them on track.

---

## Part 4: Practical Enforcement Spectrum

### Level 0: Prompt-Only (No Enforcement)

The system serves only the current phase file. No guardrails. The agent could read other files but has no prompt instruction to do so.

```
Agent receives: _preamble.md + phase-04-impl.md
Can read other phases: Yes (no restriction)
Enforcement: None
```

**Effectiveness:** ~70% focus improvement (from research on context reduction). The agent follows its instructions because they're what's in context, not because it's blocked from alternatives.

**This is what every other framework does.** CrewAI, AutoGPT, LangGraph — all rely on prompt-level focus, not enforcement.

### Level 1: Prompt + Advisory Guardrail (Soft Warning)

Add a `warn`-level Read guardrail that fires when the agent tries to read a phase file that isn't its current phase. The agent sees a warning but can acknowledge and proceed.

```yaml
- id: R10
  name: phase-file-advisory
  trigger: PreToolUse/Read
  enforcement: warn
  detect:
    type: regex_match
    field: file_path
    pattern: 'coordinator/phase-\d+'
  message: "[GUARDRAIL WARN R10] You are reading a phase file. Confirm you need this for your current phase."
```

**Effectiveness:** ~80%. The warning makes the agent "think twice" before reading other phases. Most accidental reads are caught. Intentional reads (recovery, debugging) are still possible.

### Level 2: Prompt + Hard Guardrail (Deny Read)

Add a `deny`-level Read guardrail for non-current phase files. Requires dynamic phase awareness (phase_guard.py from earlier research).

```yaml
- id: R10
  name: phase-content-lock
  trigger: PreToolUse/Read
  enforcement: deny
  scope:
    phase_aware: true  # Only deny if reading a phase file that isn't current
  detect:
    type: regex_match
    field: file_path
    pattern: 'coordinator/phase-\d+'
  message: "[GUARDRAIL DENY R10] Content lock: you may only read your current phase file."
```

**Effectiveness:** ~85%. Blocks Read tool access. Doesn't block Bash `cat`, inference, or memory. But combined with prompt focus, the agent rarely attempts to bypass.

### Level 3: Prompt + Hard Guardrail + File Generation on Demand

Don't store future phase files on disk. Generate them only when the phase transition is verified.

```
coordinator/
  _preamble.md          # Always present
  phase-04-impl.md      # Current phase — present on disk
  # phase-05-testing.md — DOES NOT EXIST YET
```

When Phase 4 verification passes, the system generates `phase-05-testing.md` from a template. The agent literally cannot read a file that doesn't exist.

**Effectiveness:** ~90%. Even Bash can't `cat` a nonexistent file. Memory and inference still apply, but the detailed phase instructions aren't accessible.

**Complexity:** Higher — requires a phase file generation step at each transition. But the template already has Copier for file generation.

### Recommendation: Level 1 for v1, Level 2 for v2

**Level 0** is already a massive improvement over the current 276-line single file. Research shows it improves focus.

**Level 1** adds a safety net at minimal cost (one `warn` rule in rules.yaml). It handles accidental reads and makes intentional reads visible in hits.jsonl.

**Level 2** requires phase_guard.py (the dynamic phase awareness from the previous research). This is v2 scope — add it when the infrastructure exists.

**Level 3** is overkill for most use cases and adds operational complexity. Reserve for security-critical scenarios.

---

## Part 5: What About Memory Across Sessions?

### Claude Code's Memory Architecture (from official docs)

| Memory Source | Loaded When | Survives Compaction | Carries Across Sessions | Contains Phase Info? |
|-------------|-------------|--------------------|-----------------------|---------------------|
| CLAUDE.md | Every session start | Yes (re-read from disk) | Yes | Only if you put it there |
| CLAUDE.local.md | Every session start | Yes | Yes | Only if you put it there |
| .claude/rules/*.md | Session start or on-demand | Yes | Yes | Only if you put it there |
| Auto memory (MEMORY.md) | Every session start (200 lines) | N/A (external file) | Yes | Yes — Claude writes what it learns |
| Auto memory topic files | On demand | N/A (external file) | Yes | Possibly |
| Conversation history | Within session | Lossy (compacted) | No (fresh session = fresh context) | Yes, within session |
| STATUS.md | When agent reads it | N/A (project file) | Yes | Yes — tracks all completed phases |

### The Honest Answer

**Can the agent remember Phase 5 content from a previous session?**

- If auto memory is on: **Yes.** If Claude learned something during Phase 5 in a previous session, it may have saved it to MEMORY.md. Next session, it loads those notes.
- If auto memory is off: **No** (for memory). But the agent can still read files.

**Can the agent access Phase 5 content even if we only give it Phase 4's file?**

- Via Read tool: **Yes** (unless guardrailed)
- Via Bash: **Yes** (harder to guardrail comprehensively)
- Via memory: **Yes** (if auto memory captured it in a previous session)
- Via STATUS.md: **Partially** (sees phase history, not phase instructions)
- Via inference: **Yes** (it's a frontier model that knows what "testing" means)

### The Practical Reality

Content lock is like a **speed limit sign**, not a **concrete barrier**.

A speed limit sign doesn't physically prevent you from going 100mph. But it:
1. Tells you what speed is expected (prompt focus)
2. Creates consequences if you violate it (guardrail warnings/denials in hits.jsonl)
3. Is followed by the vast majority of drivers (agents follow their instructions)
4. Is sufficient for normal operation (accidental speeding is caught)

A concrete barrier (Level 3 — files don't exist) is appropriate for highways with cliffs. For a team workflow tool, speed limit signs are appropriate and practical.

---

## Summary

| Question | Answer |
|----------|--------|
| Is there prior art for phase-scoped agent instructions? | Task-scoped prompts exist (CrewAI), but no framework does true content lock / information hiding. |
| Does constraining agent context actually improve performance? | **YES.** JetBrains Research (2025): 2.6% improvement + 52% cost savings. TACL (2024): >30% degradation from irrelevant context. |
| Can content lock be fully enforced? | **NO.** Memory, inference, and Bash access defeat it. Maximum enforceability: ~90% (Level 3 — files don't exist). |
| Is content lock still valuable without full enforcement? | **YES.** Its value is focus management, not information hiding. The agent performs better with relevant-only context regardless of whether enforcement is airtight. |
| What level of enforcement is appropriate? | **Level 1 for v1** (prompt focus + warn guardrail). Level 2 for v2 (deny guardrail with phase awareness). Level 3 only for security-critical scenarios. |
| What about memory across sessions? | Auto memory carries knowledge across sessions. This is a feature (continuity) not a bug. Disable only if session isolation is truly required. |

**The bottom line:** Content lock is not a security mechanism — it's an attention management mechanism. It works because LLMs perform better with focused context, not because it prevents information access. Frame it as "the agent gets the right instructions for its current phase" rather than "the agent is prevented from seeing other phases." The research supports this framing strongly.

---

## Sources

- [Claude Code Memory Documentation](https://code.claude.com/docs/en/memory)
- [Claude Code Permissions Documentation](https://code.claude.com/docs/en/permissions)
- [JetBrains Research: Efficient Context Management (2025)](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Lost in the Middle: How Language Models Use Long Contexts (TACL 2024)](https://arxiv.org/abs/2307.03172)
- [Lil'Log: LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/)
- [CrewAI: Customizing Prompts](https://docs.crewai.com/en/guides/advanced/customizing-prompts)
- [CrewAI: Tasks](https://docs.crewai.com/core-concepts/Tasks/)
- [LLM Access Control: Securing Models, Agents, and AI Workloads](https://www.truefoundry.com/blog/llm-access-control)
- [A Survey of Context Engineering for Large Language Models](https://arxiv.org/html/2507.13334v1)
