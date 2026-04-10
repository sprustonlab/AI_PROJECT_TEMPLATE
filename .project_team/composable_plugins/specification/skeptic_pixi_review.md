# Skeptic Review: Pixi Migration

## Verdict: PASS — Adopt for v1

The HPC validation results are real evidence, not speculation. Pixi deletes ~700 lines of custom Python. pixi-pack solves the offline gap better than SLC's custom cache. The migration risk is low because pixi reads conda specs natively. Three items need attention during implementation.

---

## 1. Does pixi-pack Actually Solve the Offline Problem?

**YES — it's better than SLC's approach.**

SLC's offline workflow:
```
Phase 1 (online):  conda create --download-only → cache dir + DOWNLOAD_COMPLETE_FILE marker
Phase 2 (offline): conda create --offline → install from cache
Problem: Two phases, marker file, cache directory per platform, ~280 lines of require_env
```

Pixi-pack's offline workflow:
```
Phase 1 (online):  pixi-pack pack --platform linux-64 → environment.tar (self-contained)
Phase 2 (offline): pixi-pack unpack environment.tar → env/ + activate.sh
```

The tar contains a local conda channel with all packages. It's a single artifact, not a cache directory with a marker file. This is simpler and more portable (you can scp a tar; you can't easily scp a cache directory tree with platform-specific paths).

**One edge case:** The editable install workaround (build wheel → `--inject`) adds a step that SLC didn't need. SLC preserved editable paths in lockfiles natively. With pixi-pack, editable local packages must be pre-built to wheels before packing. The spec documents this (`pixi run pip wheel --no-deps` + `--inject`), and the validation confirmed it works, but it IS extra friction for the pack workflow. Not a blocker — just a step to document in the contributor guide.

---

## 2. Migration Risk

**LOW.** Here's why:

**What we're deleting:**
- `install_env.py` (~200 lines) — replaced by `pixi install`
- `lock_env.py` (~300 lines) — replaced by `pixi lock`
- `install_SLC.py` — replaced by installing a single pixi binary
- `require_env` complexity (~280 lines) — simplified to `pixi run`

**What we're keeping:**
- `activate` script (simplified but same role)
- `commands/<name>` wrapper pattern (same structure, `pixi run` instead of `conda activate`)
- `envs/*.yml` spec format (pixi reads conda ymls via `pixi init --import`)

**Why it's lower risk than it looks:**
1. We're replacing custom code with a maintained tool. Custom code has bugs we own. Pixi bugs are prefix.dev's problem.
2. Pixi reads existing conda specs natively — no manual rewrite of `envs/*.yml`.
3. The 4-verb contract (spec→install→lock→activate) is preserved exactly — same operations, different tool.
4. The user has already validated the critical path (NFS, editables, cross-platform pack, offline unpack).

**The only risk I see:** Pixi is younger than conda/mamba (2023 vs 2012). If pixi has a breaking release, we're exposed. Mitigation: pin the pixi version in the template's bootstrap script. The SLC scripts are retained as documented fallback, which is sufficient.

---

## 3. HPC Validation

The spec lists 6 validation results (§3.1.1), all passing. It also lists a validation checklist (§3.1.1 bottom) with unchecked items:

```
- [ ] Test pixi binary on target HPC clusters (SLURM nodes)
- [ ] Test pixi on NFS/Lustre shared filesystems (concurrent access patterns)
- [ ] Test pixi-pack offline workflow on air-gapped compute nodes
- [ ] Validate cross-platform lockfile
- [ ] Confirm pixi works alongside existing module systems
```

**Inconsistency:** The validation results at the top show NFS passed, cross-platform passed, offline unpack passed — but the checklist at the bottom still shows these unchecked. The spec should reconcile: check off what passed, leave unchecked only what's genuinely untested.

**What's actually untested (based on the results table):**
- Concurrent access patterns (multiple users/jobs hitting same NFS pixi env simultaneously)
- SLURM job submission context (does `pixi run` work inside a `sbatch` script?)
- `module load` coexistence (does pixi's PATH setup conflict with HPC module systems?)

These are real risks for production HPC use but not blockers for v1. They can be validated during implementation by running test jobs on the cluster. If any fail, the SLC fallback covers it.

---

## 4. Fallback Strategy

**The spec says:** SLC scripts remain as a documented fallback. Both backends read `envs/*.yml`.

**This is sufficient.** The key property is that the spec file format (`envs/*.yml`) works with both backends. A user on a locked-down system can:
1. Keep `install_env.py` and `lock_env.py` (not deleted from git history)
2. Use them exactly as before
3. The command wrapper pattern works either way (swap `pixi run -e <name>` for `source require_env <name>`)

**I do NOT recommend runtime auto-detect** (check for pixi binary → use pixi, else → use SLC). That's the backend dispatch infrastructure I rejected in my previous review. The project either uses pixi or uses SLC. The choice is made at project creation time (Copier question or manual setup), not at runtime.

---

## 5. Is This the Right Scope for v1?

**YES — but sequence it correctly.**

The concern: pixi migration is a significant change on top of composability + onboarding. Is this too much change surface?

The answer: pixi migration actually **reduces** the change surface. The spec deletes ~700 lines of custom Python and replaces them with tool invocations. The Copier template is simpler with pixi (fewer files to conditionally include, simpler command wrappers). The `activate` script is simpler (pixi handles env discovery).

**Recommended implementation sequence:**
1. First: get the Copier template working with SLC (current code, known to work)
2. Second: swap SLC for pixi in the template (delete install_env.py/lock_env.py, simplify activate)
3. Third: validate end-to-end (copier copy → source activate → pixi install → pixi run)

This way, if pixi integration hits snags, you can ship with SLC and add pixi later. The seam is clean — the swap is localized to the env management files.

---

## 6. Spec Consistency Issue (Must Fix)

The spec has a contradiction between §3.1.1 and §8:

**§3.1.1** says pixi replaces install_env.py, lock_env.py (deleted), simplifies require_env and activate.

**§8 (Code Changes Required)** does not list the pixi migration as a code change. It still shows the original 7 changes from v2 spec. The pixi migration should be change #8:

```
| 8 | **Pixi migration** — replace install_env.py/lock_env.py with pixi | install_env.py (deleted), lock_env.py (deleted), activate, require_env, commands/* | Medium |
```

Also, §1.3 Architecture still says `install_env.py, lock_env.py, require_env` in the base box — this should be updated to reflect pixi.

**Severity:** Medium. Won't cause implementation failure but creates confusion about what the implementer should actually build.

---

## Summary

| Question | Answer |
|----------|--------|
| Does pixi-pack solve offline? | **Yes** — single tar, simpler than SLC's cache+marker system |
| Migration risk? | **Low** — pixi reads conda specs, replaces custom code with maintained tool |
| HPC validation sufficient? | **Mostly** — reconcile checked/unchecked items. Concurrent access and SLURM untested but not v1 blockers |
| Fallback strategy? | **Sufficient** — SLC scripts as documented fallback, no runtime auto-detect |
| Right scope for v1? | **Yes** — net reduction in code and complexity. Sequence: SLC first, swap to pixi second |
| Spec consistency? | **Must fix** — §8 and §1.3 don't reflect the pixi migration |
