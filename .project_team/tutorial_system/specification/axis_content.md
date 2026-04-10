# Content Axis Specification

## Overview

The Content axis defines how tutorial authors create new tutorials using only markdown and YAML — with zero engine changes. A tutorial is a directory containing a `tutorial.yaml` manifest and one or more step markdown files. The engine auto-discovers tutorials by scanning `tutorials/content/`.

This axis follows the same composability patterns as the existing hints system: frozen data structures, protocol-based seams, and declarative configuration that the engine consumes without coupling.

---

## 1. Directory Structure

Each tutorial is a self-contained directory under `tutorials/content/`:

```
tutorials/content/
  ssh-cluster/
    tutorial.yaml                  # Manifest — metadata + step ordering + config
    step-01-generate-key.md        # Step content (markdown + YAML frontmatter)
    step-02-copy-key.md
    step-03-test-connection.md
  github-signup/
    tutorial.yaml
    step-01-create-account.md
    step-02-configure-profile.md
  git-config-ssh-keys/
    tutorial.yaml
    step-01-set-name-email.md
    step-02-generate-ssh-key.md
    step-03-add-to-github.md
```

**Convention:** Step filenames follow `step-NN-<slug>.md`. The numeric prefix determines default ordering; the slug is for human readability. The manifest's `steps` list is the canonical ordering (filenames are just a convention).

**Auto-discovery rule:** Any directory under `tutorials/content/` containing a `tutorial.yaml` file is a tutorial. No registration code is needed.

---

## 2. Tutorial Manifest Format (`tutorial.yaml`)

The manifest is the single source of truth for a tutorial's structure. It declares metadata, step ordering, and per-step configuration (verification, hints, guardrails) — but never contains content or verification logic inline.

### Schema

```yaml
# tutorial.yaml — Full schema with comments
# -------------------------------------------

# Required metadata
id: ssh-cluster                    # Unique identifier (matches directory name)
title: "SSH into a Cluster"        # Human-readable title
description: >
  Learn to generate an SSH key pair, copy it to a remote cluster,
  and verify your connection works.

# Optional metadata
difficulty: beginner               # beginner | intermediate | advanced
estimated_time: "15 minutes"       # Human-readable estimate
tags: [ssh, cluster, remote]       # For filtering/search
prerequisites: []                  # List of tutorial IDs that should be completed first
  # Example: ["git-config-ssh-keys"]

# Progression model (how the user moves through steps)
progression: checkpoint-gated      # linear | branching | checkpoint-gated
  # linear:            Steps proceed in order; user can advance freely
  # checkpoint-gated:  User must pass verification before advancing
  # branching:         Steps can fork based on conditions (see branching_rules below)

# Step definitions — ordered list referencing step markdown files
steps:
  - id: generate-key
    file: step-01-generate-key.md        # Relative to this directory

    # Verification config — what to check, not how to check it
    verification:
      type: command-output-check          # References a built-in verification strategy
      params:
        command: "ls -la ~/.ssh/id_ed25519"
        expected_pattern: "id_ed25519"
        failure_message: "SSH key not found at ~/.ssh/id_ed25519"

    # Hints for this step — registered into the existing hints pipeline
    hints:
      - id: ssh-keygen-hint
        trigger: manual                   # manual | timed | on-failure
        delay_seconds: 120                # For timed triggers
        message: "Try: ssh-keygen -t ed25519 -C 'your_email@example.com'"
        severity: info
        lifecycle: show-until-resolved

      - id: ssh-passphrase-hint
        trigger: timed
        delay_seconds: 180
        message: "You can press Enter for no passphrase, or set one for extra security."
        severity: info
        lifecycle: show-once

    # Guardrail rule IDs active during this step (references rules in rules.yaml)
    guardrails:
      - T-SSH-001                         # "Don't delete existing SSH keys"

  - id: copy-key
    file: step-02-copy-key.md
    verification:
      type: command-output-check
      params:
        command: "ssh -o BatchMode=yes -o ConnectTimeout=5 ${CLUSTER_HOST} echo ok 2>&1 || true"
        expected_pattern: "ok|Permission denied"
        failure_message: "Cannot reach cluster. Check your network connection."
    hints:
      - id: ssh-copy-id-hint
        trigger: on-failure               # Fires when verification fails
        message: "Try: ssh-copy-id ${CLUSTER_USER}@${CLUSTER_HOST}"
        severity: info
        lifecycle: show-until-resolved
    guardrails: []

  - id: test-connection
    file: step-03-test-connection.md
    verification:
      type: command-output-check
      params:
        command: "ssh -o BatchMode=yes -o ConnectTimeout=10 ${CLUSTER_HOST} echo 'connection-verified'"
        expected_pattern: "connection-verified"
        failure_message: "SSH connection failed. Review previous steps."
    hints:
      - id: ssh-config-hint
        trigger: on-failure
        message: >
          If ssh-copy-id didn't work, manually append your public key to
          ~/.ssh/authorized_keys on the remote host.
        severity: warning
        lifecycle: show-until-resolved
    guardrails:
      - T-SSH-001

# Optional: branching rules (only used when progression: branching)
# branching_rules:
#   - from: step-id
#     condition: "verification.result == 'already-configured'"
#     goto: skip-to-step-id
```

### Schema Validation Rules

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `id` | `string` (slug) | yes | — |
| `title` | `string` | yes | — |
| `description` | `string` | yes | — |
| `difficulty` | `enum` | no | `beginner` |
| `estimated_time` | `string` | no | `null` |
| `tags` | `list[string]` | no | `[]` |
| `prerequisites` | `list[string]` | no | `[]` |
| `progression` | `enum` | no | `linear` |
| `steps` | `list[StepConfig]` | yes | — |
| `steps[].id` | `string` (slug) | yes | — |
| `steps[].file` | `string` (path) | yes | — |
| `steps[].verification` | `VerificationConfig` | no | `{ type: manual-confirm }` |
| `steps[].verification.type` | `string` | yes (if verification present) | — |
| `steps[].verification.params` | `dict` | no | `{}` |
| `steps[].hints` | `list[HintConfig]` | no | `[]` |
| `steps[].hints[].id` | `string` | yes | — |
| `steps[].hints[].trigger` | `enum` | yes | — |
| `steps[].hints[].message` | `string` | yes | — |
| `steps[].hints[].severity` | `enum` | no | `info` |
| `steps[].hints[].lifecycle` | `enum` | no | `show-until-resolved` |
| `steps[].hints[].delay_seconds` | `int` | no (required if trigger=timed) | — |
| `steps[].guardrails` | `list[string]` | no | `[]` |

---

## 3. Step Markdown Format

Each step file uses YAML frontmatter for metadata and standard markdown for content. The frontmatter is minimal — most configuration lives in `tutorial.yaml` to keep the single-source-of-truth in one place. Step files are primarily about *content*.

### Structure

```markdown
---
# YAML frontmatter — step identity (must match tutorial.yaml)
id: generate-key
title: "Generate an SSH Key Pair"
---

# Generate an SSH Key Pair

An SSH key pair lets you authenticate with remote servers without typing
a password every time. You'll generate a key pair using the modern
Ed25519 algorithm.

## What you'll do

1. Check if you already have an SSH key
2. Generate a new Ed25519 key pair
3. Verify the key was created

## Instructions

First, check whether you already have an SSH key:

```run
ls -la ~/.ssh/
```

If you see `id_ed25519` and `id_ed25519.pub`, you already have a key
and can skip to the next step.

To generate a new key:

```run
ssh-keygen -t ed25519 -C "your_email@example.com"
```

Accept the default file location (`~/.ssh/id_ed25519`) and optionally
set a passphrase.

> **Note:** A passphrase adds an extra layer of security. If you're on
> a shared machine, it's recommended.

## Verify it worked

Check that both files now exist:

```run
ls -la ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
```

You should see two files: `id_ed25519` (private key) and
`id_ed25519.pub` (public key).

<!-- checkpoint: generate-key -->

Once verified, the tutorial will advance to the next step.
```

### Conventions

#### Code Block Types

Code blocks use the fenced syntax with language identifiers to distinguish purpose:

| Fence Tag | Meaning | Engine Behavior |
|-----------|---------|-----------------|
| `` ```run `` | Command the user should execute | Engine may offer to run it, or present it as a copyable command |
| `` ```bash `` / `` ```python `` / etc. | Example/reference code | Rendered as-is, no execution affordance |
| `` ```output `` | Expected output example | Shown as reference for what the user should see |
| `` ```config `` | Configuration file content | Shown as a copyable block |

The `run` tag is the key distinction: it signals "this is an action the user should take" vs. "this is just an illustration." The engine can use this to provide copy buttons, auto-run prompts, or agent-assisted execution — but the content itself is presentation-agnostic.

#### Checkpoint References

HTML comments mark verification checkpoints within the prose:

```markdown
<!-- checkpoint: step-id -->
```

This is a semantic marker — it tells the engine "verification should occur here in the flow." It maps to the `verification` config in `tutorial.yaml` for this step. The content doesn't specify *what* to verify; it just marks *where* verification is relevant in the narrative.

#### Frontmatter Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | `string` | yes | Must match the step's `id` in `tutorial.yaml` |
| `title` | `string` | yes | Human-readable step title |

The frontmatter is intentionally minimal. All configuration (verification, hints, guardrails) lives in `tutorial.yaml`. The step file's job is *content*, not config.

---

## 4. Content ↔ Verification Seam

Content references verifications **declaratively** — it names a verification type and provides parameters, but never implements verification logic.

### How the seam works

```
tutorial.yaml (Content axis)          _verification.py (Verification axis)
─────────────────────────────          ───────────────────────────────────
verification:                          class CommandOutputCheck:
  type: command-output-check    ──────►    def check(self, ctx):
  params:                                      output = run(ctx.params["command"])
    command: "ls ~/.ssh/id_ed25519"            return match(output, ctx.params["expected_pattern"])
    expected_pattern: "id_ed25519"
    failure_message: "Key not found"
```

**The contract:**
1. Content declares `type` — a string that maps to a registered `Verification` implementation
2. Content provides `params` — a flat dict that the verification type knows how to interpret
3. Content provides `failure_message` — a human-readable explanation if verification fails
4. The engine resolves `type` → implementation at load time (registry pattern, like hints)
5. Verification never reads content markdown; content never calls verification code

**Built-in verification types** (defined by the Verification axis, referenced by Content):

| Type | Required Params | Description |
|------|----------------|-------------|
| `command-output-check` | `command`, `expected_pattern` | Runs command, matches output against regex |
| `file-exists-check` | `path` | Checks file/directory exists |
| `config-value-check` | `command`, `key`, `expected_value` | Checks a config value matches expected |
| `manual-confirm` | (none) | Asks user to self-report completion |
| `compound` | `operator` (and/or), `checks` (list) | Combines multiple verifications |

**Params can use environment variables** (`${CLUSTER_HOST}`) which the engine resolves at runtime from tutorial context.

---

## 5. Content ↔ Guidance Seam

Content declares hints for each step; the engine registers them into the existing hints pipeline. Content never creates `HintSpec` objects directly — it provides declarative YAML that the engine translates.

### Translation from YAML to HintSpec

```yaml
# In tutorial.yaml (Content axis)
hints:
  - id: ssh-keygen-hint
    trigger: timed
    delay_seconds: 120
    message: "Try: ssh-keygen -t ed25519"
    severity: info
    lifecycle: show-until-resolved
```

The engine translates this to:

```python
# Engine creates this at tutorial load time (Guidance axis)
HintSpec(
    id="tutorial:ssh-cluster:generate-key:ssh-keygen-hint",  # namespaced
    trigger=TutorialTimedTrigger(step_id="generate-key", delay_seconds=120),
    message="Try: ssh-keygen -t ed25519",
    severity="info",
    lifecycle=ShowUntilResolved(),
)
```

### Hint trigger types available in tutorial content

| YAML `trigger` value | Meaning | Engine maps to |
|----------------------|---------|---------------|
| `manual` | Never fires automatically; available on-demand | No-op trigger, surfaced by agent-assist |
| `timed` | Fires after `delay_seconds` on the current step | `TutorialTimedTrigger` (tutorial-specific) |
| `on-failure` | Fires when this step's verification fails | `TutorialVerificationFailedTrigger` |

### Namespacing

All tutorial hints are namespaced to avoid collisions with built-in hints:

```
tutorial:{tutorial_id}:{step_id}:{hint_id}
```

This allows multiple tutorials to use the same local hint IDs without conflict.

### Integration with existing hints pipeline

Tutorial hints are **additive** — they're appended to the list returned by `get_hints()` when a tutorial is active. When the tutorial ends, they're removed. The existing hints engine doesn't need modification; it just evaluates a larger list.

---

## 6. Extensibility — Adding a New Tutorial

Adding a tutorial requires **zero code changes**:

1. Create a new directory under `tutorials/content/`:
   ```
   tutorials/content/my-new-tutorial/
   ```

2. Write a `tutorial.yaml` manifest (following the schema above)

3. Write step markdown files (referenced by the manifest)

4. Done. The engine discovers it automatically.

### Auto-discovery mechanism

The engine scans `tutorials/content/*/tutorial.yaml` at startup (or on-demand). This mirrors how:
- The guardrails system scans `rules.d/*.yaml` for additional rules
- The hints system calls `get_hints()` to discover registered hints

```python
# Pseudocode for auto-discovery
def discover_tutorials(content_dir: Path) -> list[TutorialManifest]:
    tutorials = []
    for tutorial_dir in sorted(content_dir.iterdir()):
        manifest_path = tutorial_dir / "tutorial.yaml"
        if manifest_path.exists():
            manifest = load_and_validate(manifest_path)
            tutorials.append(manifest)
    return tutorials
```

### Validation at load time

The engine validates manifests on discovery:
- All referenced step files exist
- Step IDs are unique within the tutorial
- Frontmatter `id` in each step file matches the manifest's step `id`
- Verification types reference known implementations
- Prerequisites reference existing tutorial IDs
- Hint trigger types are valid

Validation errors produce clear messages: `"Tutorial 'my-tutorial': step 'step-03' references file 'step-03-foo.md' which does not exist"`

---

## 7. Complete Example Tutorial

### `tutorials/content/ssh-cluster/tutorial.yaml`

```yaml
id: ssh-cluster
title: "SSH into a Cluster"
description: >
  Generate an SSH key pair, copy your public key to a remote cluster,
  and verify you can connect without a password. Essential for running
  jobs on shared compute infrastructure.
difficulty: beginner
estimated_time: "15 minutes"
tags: [ssh, cluster, remote, setup]
prerequisites: []

progression: checkpoint-gated

steps:
  - id: generate-key
    file: step-01-generate-key.md
    verification:
      type: file-exists-check
      params:
        path: "~/.ssh/id_ed25519"
        failure_message: "No SSH key found at ~/.ssh/id_ed25519"
    hints:
      - id: keygen-command
        trigger: timed
        delay_seconds: 120
        message: "Try: ssh-keygen -t ed25519 -C 'your_email@example.com'"
        severity: info
        lifecycle: show-until-resolved
      - id: passphrase-tip
        trigger: timed
        delay_seconds: 180
        message: >
          When prompted for a passphrase, you can press Enter for none,
          or type one for extra security on shared machines.
        severity: info
        lifecycle: show-once
    guardrails:
      - T-SSH-001

  - id: copy-key
    file: step-02-copy-key.md
    verification:
      type: command-output-check
      params:
        command: "ssh -o BatchMode=yes -o ConnectTimeout=5 ${CLUSTER_HOST} echo ok 2>&1 || true"
        expected_pattern: "ok"
        failure_message: "Key-based authentication not working yet."
    hints:
      - id: copy-id-command
        trigger: on-failure
        message: "Try: ssh-copy-id ${CLUSTER_USER}@${CLUSTER_HOST}"
        severity: info
        lifecycle: show-until-resolved
      - id: manual-copy-fallback
        trigger: timed
        delay_seconds: 300
        message: >
          If ssh-copy-id isn't available, manually copy your key:
          cat ~/.ssh/id_ed25519.pub | ssh user@host 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'
        severity: warning
        lifecycle: show-once
    guardrails: []

  - id: test-connection
    file: step-03-test-connection.md
    verification:
      type: command-output-check
      params:
        command: "ssh -o BatchMode=yes -o ConnectTimeout=10 ${CLUSTER_HOST} hostname"
        expected_pattern: ".+"
        failure_message: "SSH connection failed. The cluster didn't return a hostname."
    hints:
      - id: ssh-config-tip
        trigger: on-failure
        message: >
          Add a host alias to ~/.ssh/config for easier access:
            Host cluster
              HostName your.cluster.edu
              User your_username
        severity: info
        lifecycle: show-once
    guardrails:
      - T-SSH-001
```

### `tutorials/content/ssh-cluster/step-01-generate-key.md`

```markdown
---
id: generate-key
title: "Generate an SSH Key Pair"
---

# Generate an SSH Key Pair

An SSH key pair lets you prove your identity to remote servers without
typing a password. You'll create a key using the Ed25519 algorithm —
it's modern, fast, and secure.

## What you'll do

1. Check for an existing SSH key
2. Generate a new key pair (if needed)
3. Verify the key files were created

## Check for existing keys

First, see if you already have an SSH key:

```run
ls -la ~/.ssh/
```

```output
drwx------  2 user user 4096 Jan  1 12:00 .
-rw-------  1 user user  411 Jan  1 12:00 id_ed25519
-rw-r--r--  1 user user   97 Jan  1 12:00 id_ed25519.pub
```

If you see `id_ed25519` and `id_ed25519.pub`, you already have a key.
You can skip ahead — the checkpoint will pass automatically.

## Generate a new key

If no key exists, generate one:

```run
ssh-keygen -t ed25519 -C "your_email@example.com"
```

When prompted:
- **File location:** Press Enter to accept the default (`~/.ssh/id_ed25519`)
- **Passphrase:** Press Enter for no passphrase, or type one for extra
  security (recommended on shared machines)

> **Why Ed25519?** It's the current best practice — smaller keys, faster
> operations, and strong security. RSA keys still work but Ed25519 is
> preferred for new setups.

## Verify the key was created

Confirm both files exist:

```run
ls -la ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
```

You should see two files:
- `id_ed25519` — your **private** key (never share this!)
- `id_ed25519.pub` — your **public** key (safe to share)

<!-- checkpoint: generate-key -->
```

---

## Design Decisions & Rationale

### Why YAML manifest + separate markdown files (not all-in-one)?

1. **Separation of concerns:** The manifest is *structure* (what steps, what order, what verification). Markdown files are *content* (what the user reads). Mixing them would couple config changes to content edits.
2. **Tooling:** Markdown files get syntax highlighting, preview, and linting in any editor. YAML manifests get schema validation.
3. **Reusability:** A step file could theoretically be shared across tutorials (e.g., "generate SSH key" is useful in both `ssh-cluster` and `git-config-ssh-keys`). The manifest references files by path, enabling this.

### Why configuration in manifest, not in step frontmatter?

Step frontmatter is intentionally minimal (`id` + `title`). Verification, hints, and guardrails live in the manifest because:
1. **Single source of truth:** An author can see the entire tutorial's structure — all steps, all verifications, all hints — in one file.
2. **Seam clarity:** The manifest is the Content axis's interface to other axes. Step files are pure content.
3. **Diffability:** Changing verification config shows up as a manifest diff, not scattered across N step files.

### Why `run` fence tag instead of a custom directive?

Standard markdown renderers ignore unknown fence tags, so `run` degrades gracefully. Custom directives (`:::run`) require markdown extensions. The `run` tag works in any context while still being machine-parseable.

### Why environment variables in verification params?

Tutorial context varies per user (different cluster hostnames, usernames). Rather than templating the markdown, verification params use `${VAR}` syntax that the engine resolves at runtime. This keeps content static and reusable while verification adapts to the user's environment.

---

## Summary

| Component | Format | Responsibility |
|-----------|--------|---------------|
| `tutorial.yaml` | YAML | Structure, ordering, verification config, hint declarations, guardrail refs |
| `step-NN-*.md` | Markdown + frontmatter | User-facing instruction content |
| `<!-- checkpoint -->` | HTML comment in markdown | Semantic marker for "verify here" |
| `` ```run `` blocks | Fenced code | Commands the user should execute |
| Verification seam | `type` + `params` in YAML | Declarative reference to verification strategies |
| Guidance seam | `hints` list in YAML | Declarative hint specs translated to `HintSpec` objects |
| Extensibility | Directory + files | Drop a new directory, engine auto-discovers it |
