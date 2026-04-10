# Research Report: Prior Art in Interactive Tutorial Systems with Step Verification

**Requested by:** Coordinator
**Date:** 2026-04-03
**Tier of best source found:** T3 (Official organization repos)

## Query

Investigate prior art in interactive tutorial/learning systems that verify step completion. Extract: content format, verification mechanism, progression model, and what we can adopt for our tutorial system (which uses guardrails as checkpoint verifiers in a Claude Code agent context).

---

## Findings

### Source 1: Rustlings (Rust Language Official)

- **URL:** https://github.com/rust-lang/rustlings
- **Tier:** T3 (Official organization repo — `rust-lang/`)
- **License:** MIT
- **Tests:** Yes (CI passing)
- **Stars:** 62.4k+
- **Relevance:** The closest analog to our "verification as progression gate" model. Rustlings is the gold standard for CLI-based learn-by-doing with automated verification.

#### Content Format
- Individual `.rs` exercise files organized by topic in `exercises/<topic>/` directories
- Each topic directory has a `README.md` with resources
- Exercise ordering and metadata defined in a central manifest (previously `info.toml`, now integrated into the Rust source)
- Each exercise has a `mode` attribute: either `"compile"` (must compile) or `"test"` (must compile AND pass tests)

#### Verification Mechanism
- **Two-tier verification:**
  1. **Compilation check** — `rustc` attempts to compile the exercise. If it fails, the compiler error IS the feedback.
  2. **Test execution** — For `mode: "test"` exercises, the compiled binary's built-in test suite runs. Tests pass = exercise complete.
- **Sentinel marker:** Exercises historically used an `"I AM NOT DONE"` comment — rustlings wouldn't advance past an exercise until the student removed this marker. This is a manual "opt-in to verification" gate.
- Under the hood, rustlings is a thin wrapper around `rustc` — `src/verify.rs` handles compilation, `src/run.rs` handles execution.

#### Progression Model
- **Linear, ordered sequence** — exercises run in a predetermined order optimized for newcomers
- **Watch mode** — `rustlings` (default command) monitors the filesystem; any file change triggers re-compilation/re-test automatically
- **Interactive list** — pressing `l` shows all exercises with completion status; students can jump to any exercise or reset individual ones
- **Hints** — pressing `h` in watch mode shows built-in hints per exercise

#### What We Can Steal
| Concept | Adaptation for Our System |
|---------|--------------------------|
| **Compiler-as-verifier** | Our `command-output-check` verification type is the direct analog — run a command, check exit code + output |
| **Watch mode with auto-recheck** | Tutorial engine could re-run verification when relevant files change |
| **Two-tier verification (compile then test)** | Map to `compound` verification: first `file-exists-check`, then `command-output-check` |
| **Hints system (press 'h')** | Direct integration with our existing hints pipeline — tutorial steps register hints |
| **Sentinel marker ("I AM NOT DONE")** | Interesting opt-in pattern, but our agent-conversational model handles this more naturally through dialogue |
| **Central manifest ordering exercises** | Our `tutorial.yaml` manifest serves the same role |

---

### Source 2: Exercism

- **URL:** https://github.com/exercism/cli / https://exercism.org/docs/building/tooling/test-runners
- **Tier:** T3/T5 (Organization repo, well-maintained community)
- **License:** MIT (CLI), AGPL-3.0 (website)
- **Tests:** Yes (CI passing, Docker-based test infrastructure)
- **Stars:** 3.6k (CLI), exercism org has 100+ repos
- **Relevance:** Excellent architecture for language-agnostic test execution with standardized output. Their test runner interface is a clean protocol we should study.

#### Content Format
- Each exercise is a directory with: `README.md`, test files, stub/solution files, `.meta/config.json` (metadata)
- `.meta/config.json` specifies which files are tests (`.files.test`) and which are solutions (`.files.solution`)
- Exercises downloaded via `exercism download --exercise=<slug> --track=<track>`

#### Verification Mechanism
- **Language-agnostic test runner protocol:**
  - Each language track has its own Test Runner (written in that language)
  - Test Runner is packaged as a Docker container
  - Runner takes a solution directory → runs all tests → writes `results.json` to output directory
  - **Standardized output:** `results.json` with structured pass/fail per test case
  - Exit code 0 = runner succeeded (regardless of test pass/fail). Non-zero = runner itself broke.
- **Local verification:** `exercism test` invokes track-specific test command (e.g., `pytest` for Python, `bats` for Bash)
- **Additional automated tooling:**
  - **Analyzers** — examine solution for style/pattern issues, return predefined comments
  - **Representers** — normalize solutions (strip comments, rename variables) for pattern matching

#### Progression Model
- **Non-linear, learner-driven** — students choose which exercises to tackle
- **Submit-and-verify loop:** work locally → tests pass → `exercism submit` → server-side verification → solution page
- Supports incomplete submissions for mentoring/peer review

#### What We Can Steal
| Concept | Adaptation for Our System |
|---------|--------------------------|
| **Standardized `results.json` output** | Our `VerificationResult` dataclass mirrors this: `passed`, `message`, `evidence` |
| **Language-agnostic runner protocol** | Our `Verification` protocol is the same pattern: any check that returns `VerificationResult` |
| **Separate runner exit code from test result** | Critical distinction: "verification ran successfully" vs "verification passed". Our system should differentiate runner errors from failed checks |
| **Docker-containerized runners** | Overkill for us, but the isolation principle matters — verifications should not have side effects |
| **Analyzer pattern** | Could inspire a "tutorial advisor" that examines user's work style beyond pass/fail |

---

### Source 3: GitHub Learning Lab → GitHub Skills

- **URL:** https://github.com/skills / https://skills.github.com/content-model
- **Tier:** T3 (Official GitHub organization)
- **License:** MIT (individual course repos)
- **Tests:** Yes (Actions-based CI)
- **Stars:** Varies per course (introduction-to-github has significant usage)
- **Relevance:** The most architecturally relevant model — uses real platform events as verification triggers, which is analogous to using real command output as verification in our system.

#### Content Format
- **Template repository** — each course is a GitHub template repo that students "Use this template" to create their own copy
- **README.md** — structured with Header, Start Step, Footer sections
- **`.github/steps/`** — 3-5 markdown files, one per step, with instructions
- **`.github/workflows/`** — Actions workflow files named `N-brief-summary.yml` (numbered for ordering)

#### Verification Mechanism
- **GitHub Actions as verification checkpoints:**
  - Each step has a corresponding workflow file triggered by specific GitHub events
  - Events include: `push` (commit/branch creation), `pull_request` (opened/synchronize/reopened), workflow completion, issue events
  - Workflow runs → checks conditions → if verification passes, updates README to show next step
  - The platform itself IS the verification environment — creating a branch IS the proof that the student learned to create a branch
- **Event-driven progression:** The student's real actions in the repository (push, PR, merge) trigger workflows that advance the tutorial
- **~20 second feedback loop** — after student action, workflow runs and updates within seconds

#### Progression Model
- **Linear, event-gated** — each step must trigger its workflow successfully before the next step is revealed
- **Self-contained** — everything lives in the student's own repo copy
- **Automate non-learning tasks** — "Only have users complete tasks that help them learn, automate the rest"
- Courses target 30-45 minutes completion time

#### What We Can Steal
| Concept | Adaptation for Our System |
|---------|--------------------------|
| **"The action IS the proof"** | Our verification should check real system state, not ask the user to confirm. `ssh -T git@github.com` succeeding IS the proof SSH works. |
| **Event-driven step advancement** | Agent detects user actions → triggers verification → advances tutorial. Not timer-based, not polling. |
| **Numbered workflow files for ordering** | Our `tutorial.yaml` step ordering serves the same role, but the naming convention `N-summary.yml` is good for content authoring |
| **Template-as-course** | The AI_PROJECT_TEMPLATE itself is the "template" — tutorials teach you how to use IT |
| **"Automate non-learning tasks"** | Agent should auto-handle boilerplate. If the tutorial teaches SSH key generation, the agent can auto-open the right file — the user just needs to do the key steps |

---

### Source 4: Katacoda (O'Reilly, now defunct)

- **URL:** https://www.katacoda.community/essentials/scenario-syntax.html / https://github.com/katacoda/scenario-examples/tree/master/verified-steps
- **Tier:** T5/T6 (Community archive of shutdown platform)
- **License:** N/A (platform shut down 2022)
- **Tests:** N/A
- **Stars:** N/A
- **Relevance:** Best prior art for CLI-terminal-based step verification with shell scripts. The verification model is almost exactly what our `command-output-check` needs to do.

#### Content Format
- **`index.json`** — scenario manifest defining: title, description, difficulty, time estimate, steps array, environment config
- **Each step:** `{ title, text: "step-N.md", verify: "step-N-verify.sh", background: "...", foreground: "..." }`
- **Markdown content files** — one per step with interactive elements (clickable code blocks execute in terminal)
- **Assets** — files uploaded to the tutorial environment with chmod permissions

#### Verification Mechanism
- **Shell script exit codes:**
  - Each step has a `verify` field pointing to a verification shell script
  - Exit code `0` = step passes, user can proceed
  - Non-zero exit code = step fails, user must retry
- **Solver utility pattern:** `verifications.sh` file with functions named `verify_task_n` for each step
- **Verification ordering best practice:** "General validation to final details" — e.g., first check file exists, then check file content
- This is the most direct analog to our `command-output-check` verification type

#### Progression Model
- **Linear, verification-gated** — must pass verification script to proceed
- **Browser-based terminal** — real terminal environment in the browser
- Steps can have background scripts (setup) and foreground scripts (commands that run in user's terminal)

#### What We Can Steal
| Concept | Adaptation for Our System |
|---------|--------------------------|
| **Shell script exit codes as verification** | Direct implementation pattern for `command-output-check`: run script, check exit code, capture output as evidence |
| **`verify_task_n` naming convention** | Clean pattern for organizing verification functions per step |
| **"General to specific" verification ordering** | Our `compound` verification type should check prerequisites first (file exists?) then details (file has correct content?) |
| **`index.json` manifest structure** | Our `tutorial.yaml` serves the same role; the step schema with `verify` field is a direct parallel |
| **Background/foreground scripts** | Tutorial steps could have setup actions (background) that prepare the environment before user interaction |

---

### Source 5: Tour of Nix

- **URL:** https://nixcloud.io/tour/ / https://github.com/nixcloud/tour_of_nix
- **Tier:** T5 (Community project)
- **License:** GPL-2.0
- **Tests:** No formal test suite
- **Stars:** ~150
- **Relevance:** Interesting technical approach (in-browser language interpreter) but limited relevance to our CLI-based system.

#### Content Format
- **`questions.json`** — all exercises defined in a single JSON file
- Each exercise has description, code template, expected output
- Standalone Electron version available for offline use

#### Verification Mechanism
- **In-browser Nix interpreter** — `nix-instantiate` compiled to JavaScript via Emscripten
- User writes Nix expression → evaluates in browser → output compared to expected result
- No server-side verification — everything runs client-side

#### Progression Model
- **Linear sequence** through exercises
- No explicit gating — user can navigate freely

#### What We Can Steal
| Concept | Adaptation for Our System |
|---------|--------------------------|
| **Expected output comparison** | Basic pattern for `command-output-check`: run expression, compare to expected output |
| **Single manifest file for all exercises** | Validates our `tutorial.yaml` approach, though we prefer one-file-per-step for content |

**Note:** GPL-2.0 license — cannot recommend for direct code reuse. Conceptual inspiration only.

---

## Not Recommended (and why)

| Source | Reason for Rejection |
|--------|---------------------|
| **Codecademy / freeCodeCamp** | Web-based, not CLI-based. Verification is server-side with sandboxed environments. Not relevant to our agent-in-terminal model. |
| **Katacoda (as a platform)** | Shut down in 2022. Only the archived community docs and scenario syntax remain. Useful as a design reference but no living code. |
| **Tour of Nix (for code reuse)** | GPL-2.0 license. No tests. Interesting concept but not suitable as a reference implementation. |
| **Generic "learn X the hard way" books** | Static content with no automated verification. Not relevant. |

---

## Cross-Cutting Patterns (Synthesis)

### Pattern 1: Verification as Exit Code
**Found in:** Rustlings (compiler exit code), Katacoda (shell script exit code), Exercism (test runner exit code)

Every system ultimately reduces verification to: **run something → check exit code → capture output**. This validates our `command-output-check` as the foundational verification primitive. Other types (`file-exists-check`, `config-value-check`) are syntactic sugar over this pattern.

### Pattern 2: Evidence Capture
**Found in:** Exercism (`results.json`), Katacoda (script output), Rustlings (compiler errors)

Verification isn't just pass/fail — the **output itself is teaching material**. Compiler errors teach Rust. Test failure messages teach the API. Our `VerificationResult.evidence` field should capture the raw command output because:
- It proves the check ran against real state
- It provides diagnostic information when the check fails
- The agent can use it to generate targeted guidance

### Pattern 3: Manifest-Driven Content
**Found in:** Rustlings (`info.toml`), Katacoda (`index.json`), Exercism (`.meta/config.json`), GitHub Skills (numbered workflow files)

Every system separates content from ordering/metadata. A central manifest defines: step order, verification type, metadata. Content lives in separate files. This directly validates our `tutorial.yaml` + `step-NN.md` approach.

### Pattern 4: Watch/React Mode
**Found in:** Rustlings (filesystem watch), GitHub Skills (event-driven Actions)

The best systems don't require the user to explicitly say "check me" — they detect relevant changes and auto-verify. In our agent context, this means: the agent should monitor for completion signals (user says "done", file changes, command execution) and proactively run verification.

### Pattern 5: Automate the Unimportant
**Found in:** GitHub Skills ("automate any task that isn't relevant to your course's learning goals")

The tutorial agent should handle setup, boilerplate, and navigation. The user should only do the steps that teach them something. This is a key UX principle.

---

## Recommendation

### Primary design influences (in priority order):

1. **Katacoda's verification model** — Shell scripts with exit codes as step gates. This maps most directly to our `command-output-check` type and the `Verification` protocol. The `verify_task_n` pattern and general-to-specific ordering are directly adoptable.

2. **Rustlings' watch mode + hints integration** — The auto-recheck-on-change pattern and per-exercise hints map cleanly to our filesystem monitoring + hints pipeline integration.

3. **Exercism's test runner interface** — The `results.json` standardized output validates our `VerificationResult` dataclass. The distinction between "runner succeeded" and "test passed" is critical for our system to adopt.

4. **GitHub Skills' "action IS proof" philosophy** — Verification should check real system state (`ssh -T git@github.com`, `git remote -v`, file existence) rather than asking users to self-report. This is the core insight that makes guardrails-as-verifiers work.

### Key architectural validation:

Our composability analysis (Content x Progression x Verification x Guidance x Safety x Presentation) is validated by the prior art:
- Every system separates content format from verification mechanism (Content ⊥ Verification)
- Every system separates progression logic from what's being checked (Progression ⊥ Verification)
- No system couples hints/guidance to verification internals (Guidance ⊥ Verification)

The `Verification` protocol (`check(context) -> VerificationResult`) is the right abstraction — it's the pattern every successful system converges on, whether they use compiler exit codes, test runner JSON, or shell script returns.

---

## Sources

- [Rustlings — GitHub](https://github.com/rust-lang/rustlings)
- [Rustlings Usage](https://rustlings.rust-lang.org/usage/)
- [Exercism — Working Locally](https://exercism.org/docs/using/solving-exercises/working-locally)
- [Exercism — Test Runner Interface](https://exercism.org/docs/building/tooling/test-runners/interface)
- [Exercism — Test Runners Overview](https://exercism.org/docs/building/tooling/test-runners)
- [GitHub Skills](https://skills.github.com/)
- [GitHub Skills Content Model](https://skills.github.com/content-model)
- [GitHub Skills — Introduction to GitHub](https://github.com/skills/introduction-to-github)
- [Katacoda Scenario Syntax](https://www.katacoda.community/essentials/scenario-syntax.html)
- [Katacoda Verified Steps Example](https://github.com/katacoda/scenario-examples/tree/master/verified-steps)
- [Tour of Nix](https://nixcloud.io/tour/)
- [Tour of Nix — GitHub](https://github.com/nixcloud/tour_of_nix)
- [Interactive CLI Tutorials — DEV Community](https://dev.to/buildvr/interactive-cli-tutorials-teaching-developers-without-docs-p5a)
