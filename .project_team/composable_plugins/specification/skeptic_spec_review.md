# Skeptic Spec Review — SPECIFICATION.md

**Verdict: CONDITIONAL PASS — 3 issues must be resolved, 4 minor concerns noted.**

The spec is well-constructed and stays true to the "manifest + convention" principle. It correctly avoided a plugin framework. Most of my Phase 2 concerns are addressed. The issues below are specific and fixable.

---

## 1. Lightweight Check: Any Framework Creep?

**PASS with one concern.**

What's right:
- No plugin base class, no event bus, no dynamic discovery (§14 explicitly lists these as excluded)
- Fixed `_PLUGIN_ORDER` array instead of runtime plugin scanning (§5.3 line 415)
- Shell scripts + YAML manifest, not Python plugin loaders
- Copier handles generation; activate handles runtime — clean separation

**Concern: `plugin.yaml` is over-specified for its consumers.**

§4 defines `plugin.yaml` with fields: `name`, `version`, `category`, `description`, `depends_on`, `env_sets`, `env_reads`, `commands`, `files`, `scripts`. That's 10 fields.

Who reads `plugin.yaml` at runtime?
- The activate dispatcher reads `project.yaml` (not `plugin.yaml`) to check enabled status
- Copier reads `copier.yml` (not `plugin.yaml`) for conditional file inclusion
- The `_plugin_deps` function (§10.1) would need to parse `plugin.yaml` for `depends_on`

So 9 of 10 fields (`env_sets`, `env_reads`, `commands`, `files`, `version`, `category`, `description`, `name`) have **no runtime consumer**. They're documentation masquerading as machine-readable config. This is harmless but misleading — someone will try to build tooling that reads these fields, and then we're back to framework territory.

**Recommendation:** Either (a) remove `plugin.yaml` and put `depends_on` directly in the activate script as comments/a hardcoded map (it's 5 plugins — `declare -A DEPS=([claudechic]="python-env" [project-team]="claudechic")` is simpler than parsing YAML), or (b) keep `plugin.yaml` but strip it to just `name`, `depends_on`, `description`. The `env_sets`/`env_reads`/`commands`/`files` fields are inventorying things that are already visible from the directory structure.

**Severity:** Minor. Not a blocker.

---

## 2. Existing-Codebase Failure Scenarios: All 4 Addressed?

**PASS — all four scenarios addressed in §8.3.**

| Scenario | Addressed? | Assessment |
|----------|-----------|------------|
| File conflicts | Yes — Copier conflict resolution + `.claude/` merge | Adequate |
| Path assumptions | Yes — `require_env` relaxation (§8.4) | Concrete code shown |
| Env collision | Yes — SLC uses its own `envs/SLCenv/` directory | Adequate |
| Nested repos | Yes — `activate` resolves from script location | Adequate |

**One gap:** §8.2 step 4 says "merge `.claude/` directory" but the merge algorithm is underspecified. What happens when:
- Both repos define hooks in `.claude/settings.json` `PreToolUse`? Are they concatenated? Does order matter?
- The existing repo has a `.claude/commands/init.md` that conflicts with a template command name?

**Recommendation:** Specify merge behavior for `.claude/settings.json` concretely. At minimum: "template entries are appended to existing arrays; scalar conflicts emit a warning and preserve the user's value."

**Severity:** Medium. The merge is the hardest part of integration and needs implementation detail before coding.

---

## 3. Pattern Miner JSONL Mitigations: All 5 Included?

**4 of 5 included. One missing.**

| Mitigation | Included? | Section |
|------------|----------|---------|
| Isolate JSONL parsing into single module | Yes | §9.2.1 |
| Format version checking | Yes | §9.2.2 |
| Validation mode (`--validate`) | Yes | §9.2.4 |
| Configurable project directories (no hard-coding) | Yes | §9.2.3 |
| Integration tests with snapshot JSONL files | **NO** | Not mentioned |

**MUST FIX:** The snapshot test mitigation is the one that catches regressions. The idea: commit a known-good JSONL session file (anonymized) as a test fixture. The test parses it and asserts expected output. When Claude Code updates and the format changes, this test fails immediately instead of the miner silently producing garbage.

Without this, all other mitigations are reactive — they warn at runtime but don't prevent shipping a broken parser.

**Recommendation:** Add to §9 or to the Implementation Plan (Phase 2, step 8):
> Include at least one snapshot JSONL test file (`tests/fixtures/session_v2.1.59.jsonl`) with expected parse output. Test: `parse_session(fixture_path)` returns expected message count, roles, and text content.

**Severity:** High. This is the mitigation that makes all others verifiable.

---

## 4. Over-Engineering Check

**PASS overall.** Two items to flag:

### 4a. `plugin.yaml` (repeated from §1)
See above. 10 fields with 1 runtime consumer is spec-weight for 5 plugins.

### 4b. Dependency resolution at activate time (§10.1)

The `_plugin_deps` function parses `plugin.yaml` to get `depends_on`. For 5 plugins with exactly 2 dependency edges (`claudechic→python-env`, `project-team→claudechic`), this is:

```bash
# What the spec proposes (§10.1):
for _dep in $(_plugin_deps "$_plugin"); do  # parses plugin.yaml
    if ! _plugin_enabled "$MANIFEST" "$_dep"; then
        echo "  ⚠️  $_plugin requires $_dep (disabled) — skipping"
        continue 2
    fi
done

# What would be simpler and equally correct:
declare -A _PLUGIN_DEPS=(
    [claudechic]="python-env"
    [project-team]="claudechic"
)
```

The hardcoded map is 3 lines. The YAML-parsing function is a function definition + awk/grep + error handling. For 5 plugins, the map is simpler and more verifiable.

**Recommendation:** Use the hardcoded map. When plugin count exceeds ~10, revisit.

**Severity:** Minor.

---

## 5. Activate Script Decomposition: Sound?

**PASS — the design is sound.**

The fixed `_PLUGIN_ORDER` array (§5.3 line 415) is the right call. It avoids topological sort complexity for a known graph. The category-based ordering (infrastructure first, runtime second, post-hoc last) matches the actual dependency flow.

**One correctness concern:** The `_plugin_enabled` awk function (§5.4):

```awk
$0 ~ "^  " plugin ":$" { found=1; next }
found && /enabled: true/ { print "yes"; exit }
found && /^  [^ ]/ { exit }  # New plugin section — stop looking
```

This matches `^  python-env:$` — note the 2-space indent is hardcoded. If `project.yaml` uses tabs, or 4 spaces, or if a YAML-generating tool reformats the file, this breaks silently (plugin appears disabled). The awk also uses `~` regex match with the plugin name — safe for current names but if a plugin name contained `.` or `*` it would be a regex bug.

**Recommendation:** Add a comment in `project.yaml.jinja` template: `# WARNING: Activate script parses this file with awk. Maintain exact 2-space indent under 'plugins:'.` Or better: use `grep -A2` instead of awk for simpler intent.

**Severity:** Low — current plugin names are safe, and the template controls the format. But worth documenting.

---

## 6. Copier Integration: Risks?

**PASS with two risks to acknowledge.**

### Risk 1: Copier is a Python dependency

Users must have `pip install copier` before they can generate a project. On HPC systems (which this is — NFS paths confirm it), Python/pip availability varies. The bootstrap sequence is:

1. User has Python 3 + pip → `pip install copier` → `copier copy <url> my-project` → `source activate`

If the user doesn't have pip, they can't create a project. But `install_SLC.py` also requires Python 3, so this is a pre-existing assumption.

**Mitigation:** Document this prerequisite clearly. Consider a `create-project.sh` bootstrapper that installs copier into a temporary venv.

### Risk 2: `copier update` and user modifications

When users modify generated files (e.g., edit `activate`, add to `project.yaml`), `copier update` may overwrite their changes. Copier handles this with conflict resolution, but users need to know this.

**Mitigation:** Already implicitly handled — `.copier-answers.yml` tracks state. Document: "If you manually edit generated files, `copier update` will show conflicts for resolution."

### Risk 3: Template directory structure duplication

The spec has `plugins/` both in the template repo (§2.1, the source) and in the generated project (§12.1, the output). In the generated project, `plugins/<name>/` only contains `activate.sh` — but the source repo's `plugins/<name>/` contains `plugin.yaml`, `setup.sh`, `check.sh`, and `files/`. Are `setup.sh`, `check.sh`, and `plugin.yaml` copied to the generated project?

Looking at §5.3 line 422: `_activate_script="$BASEDIR/plugins/$_plugin/activate.sh"` — the dispatcher expects `plugins/` in the generated project. But §2.2 (generated layout) does NOT show a `plugins/` directory at the top level.

**This is an inconsistency.** Either the generated project has `plugins/` (and the dispatcher works) or it doesn't (and line 422 breaks).

**MUST FIX:** Clarify whether `plugins/` directories are part of the generated output. Based on §12.1 they are (conditional inclusion). Update §2.2 to show `plugins/` in the generated layout.

**Severity:** Medium — this will cause implementation confusion.

---

## 7. Env Var Abstraction: Minimal Enough?

**PASS.**

One rename: `CLAUDECHIC_APP_PID` → `AGENT_SESSION_PID`. Backward-compatible fallback with `or` (§6.3). `CLAUDE_AGENT_NAME` and `CLAUDE_AGENT_ROLE` correctly left unchanged (they're Claude Code's variables). The behavior matrix (§11.2) for guardrails standalone mode is well-defined.

No concerns.

---

## Summary

| Criterion | Verdict | Issues |
|-----------|---------|--------|
| 1. Lightweight | **PASS** | `plugin.yaml` over-specified (minor) |
| 2. Existing-codebase scenarios | **PASS** | `.claude/` merge algorithm underspecified (medium) |
| 3. Pattern miner mitigations | **4/5** | **Missing: snapshot JSONL integration tests (high)** |
| 4. Over-engineering | **PASS** | Hardcode dep map instead of parsing plugin.yaml (minor) |
| 5. Activate decomposition | **PASS** | Document awk indent sensitivity (low) |
| 6. Copier integration | **PASS** | **`plugins/` directory missing from §2.2 generated layout (medium)** |
| 7. Env var abstraction | **PASS** | No issues |

### Must-Fix Before Implementation (3 items)

1. **Add snapshot JSONL test to §9 or implementation plan** — without this, the parser has no regression safety net
2. **Specify `.claude/settings.json` merge behavior** in §8.2 — "merge" is not a spec, it's a wish
3. **Add `plugins/` to §2.2 generated layout** — the activate dispatcher references it but the layout diagram omits it

### Recommended Simplifications (not blocking)

4. Strip `plugin.yaml` to `name`, `depends_on`, `description` — or replace with a hardcoded bash map
5. Hardcode dependency map in activate script instead of parsing YAML at runtime
6. Add indent-sensitivity comment to `project.yaml.jinja` template

**Overall: The spec is well-structured, stays lightweight, and addresses most concerns from Phase 2. Fix the 3 must-fix items and it's ready for implementation.**
