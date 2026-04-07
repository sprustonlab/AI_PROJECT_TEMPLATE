# Landscape Survey: Composable AI Project Templates & Plugin Systems

**Requested by:** Coordinator
**Date:** 2026-03-29
**Tier of best sources found:** T1 (official docs), T3 (official org repos), T5 (well-maintained community repos)

---

## 1. Project Scaffolding & Templating Tools

### Source 1: Copier — Code Lifecycle Management

- **URL:** https://github.com/copier-org/copier
- **Tier:** T5 (well-maintained community repo with strong docs)
- **License:** MIT
- **Tests:** Yes (CI passing)
- **Stars:** ~2,500+
- **Relevance:** **Strongest match for AI_PROJECT_TEMPLATE's needs.** Copier is not just a scaffolding tool — it's a *code lifecycle management* tool. Key capabilities:
  - Templates are plain git repos (no special packaging required)
  - `copier update` intelligently merges three states: old template, user modifications, new template version
  - Jinja2 templating with conditional file inclusion (perfect for plugin selection)
  - Interactive questionnaire system (maps directly to our onboarding flow)
  - Pre/post-generation hooks (can run `activate`, install plugins, etc.)
  - Answers stored in `.copier-answers.yml` (tracks which plugins were selected)
- **Risks:** Python-only CLI. Web-based onboarding would need a separate layer on top.
- **Recommendation:** **Primary candidate** for the template engine underlying our plugin system. Copier's update mechanism solves the "template evolves, projects stay current" problem that cookiecutter cannot.

### Source 2: Cookiecutter — Industry Standard Scaffolding

- **URL:** https://github.com/cookiecutter/cookiecutter
- **Tier:** T5
- **License:** BSD-3-Clause
- **Tests:** Yes (CI passing)
- **Stars:** ~22,000+
- **Relevance:** Most widely adopted scaffolding tool with 6,000+ community templates. Jinja2-based. Simple mental model: answer questions, get files.
- **Risks:** **One-shot only** — no `update` mechanism. Once you generate a project, the template and project diverge permanently. This is a dealbreaker for a plugin system that needs to evolve.
- **Recommendation:** Learn from its template ecosystem and community patterns, but **do not adopt** as core engine. Copier is strictly better for our use case.

### Source 3: Yeoman — JavaScript Scaffolding with Generators

- **URL:** https://github.com/yeoman/yeoman
- **Tier:** T5
- **License:** BSD-2-Clause
- **Tests:** Yes
- **Stars:** ~9,600+
- **Relevance:** Pioneered the "generator" pattern — composable sub-generators that can be mixed. Generators can programmatically generate files, run transforms, and compose with other generators. The `composeWith()` API is conceptually close to our plugin composition.
- **Risks:** JavaScript/npm ecosystem. Declining activity. Generators require npm publishing. Heavyweight for our use case.
- **Recommendation:** **Borrow the composable generator pattern** (sub-generators that compose), but don't adopt the tool itself.

### Source 4: Degit / Tiged — Lightweight Git Template Cloning

- **URL:** https://github.com/Rich-Harris/degit (original), https://github.com/tiged/tiged (maintained fork)
- **Tier:** T5 (tiged), T8 (degit — unmaintained since 2020)
- **License:** MIT
- **Tests:** Yes (tiged)
- **Stars:** ~7,500+ (degit)
- **Relevance:** Simplest possible scaffolding: clone a git repo without `.git` history. Tiged adds subdirectory extraction — could be used to pull individual plugin directories from a monorepo.
- **Risks:** No templating, no variable substitution, no update mechanism. Too simple for our needs alone.
- **Recommendation:** Could serve as the *transport layer* for pulling plugin packages from git, but not as the primary scaffolding engine.

### Source 5: Projen — Programmatic Project Configuration

- **URL:** https://github.com/projen/projen
- **Tier:** T3 (AWS/CDK organization)
- **License:** Apache-2.0
- **Tests:** Yes (CI passing)
- **Stars:** ~2,700+
- **Relevance:** Radical approach: project configuration is *code*, not templates. You write a TypeScript/Python program that *generates* your project files. Changes to config re-synthesize all managed files. Supports "components" that compose.
- **Risks:** Heavy mental model shift. TypeScript-centric. Managed files are not meant to be hand-edited (they get overwritten on synth). Overkill for our use case.
- **Recommendation:** **Borrow the "configuration as code" idea** for plugin manifests, but don't adopt projen itself. Our users need to hand-edit generated files.

### Source 6: Nx Generators — Monorepo Plugin System

- **URL:** https://nx.dev/
- **Tier:** T3 (Nrwl organization)
- **License:** MIT
- **Tests:** Yes (CI passing)
- **Stars:** ~24,000+
- **Relevance:** Nx generators are the gold standard for *composable code generation within a monorepo*. Key patterns:
  - Generators can read/modify the project graph
  - Perform AST-level transforms (not just file copying)
  - Compose with other generators
  - Module boundary rules enforce separation between plugins
  - Plugin-based architecture where each capability is a separate `@nx/` package
- **Risks:** JavaScript/TypeScript monorepo ecosystem. Very heavyweight. Wrong language ecosystem.
- **Recommendation:** **Study the plugin architecture patterns** (manifest-based discovery, composable generators, module boundaries) but don't adopt the tool.

---

## 2. Plugin Architecture Patterns

### What Works in Practice — Cross-Ecosystem Analysis

| System | Discovery | Interface | Composition | Lazy Loading |
|--------|-----------|-----------|-------------|-------------|
| **VS Code Extensions** | `package.json` manifest + marketplace | Activation events + API surface | Extensions are isolated processes (Extension Host) | Yes — `activationEvents` in manifest |
| **pytest / pluggy** | Entry points or `conftest.py` | `@hookspec` / `@hookimpl` decorators | 1:N hook calling, result collection | Yes — on first hook call |
| **ESLint configs** | `extends` array in config | Rule interface (create/meta) | Configs extend and override | Per-rule |
| **Babel plugins** | Plugin array in config | Visitor pattern on AST nodes | Plugins compose as pipeline | Per-transform |
| **stevedore** | setuptools entry points | Named driver/hook interfaces | Manager classes (DriverManager, HookManager, etc.) | On-demand loading |

### Source 7: Pluggy — Minimalist Production Plugin System

- **URL:** https://github.com/pytest-dev/pluggy
- **Tier:** T3 (pytest-dev organization)
- **License:** MIT
- **Tests:** Yes (CI passing, extensive)
- **Stars:** ~1,400+
- **Relevance:** **Most directly applicable pattern for AI_PROJECT_TEMPLATE.** Core concepts:
  - **Hook specifications** (`@hookspec`): Host declares extension points with typed signatures
  - **Hook implementations** (`@hookimpl`): Plugins provide implementations
  - **Plugin Manager**: Coordinates registration, validates signatures, calls hooks
  - **1:N calling**: Multiple plugins can implement the same hook; results are collected
  - **Dynamic argument pruning**: New parameters can be added to hooks without breaking existing plugins
  - Used by pytest, tox, devpi — battle-tested at scale
- **Risks:** Python-only. May be more infrastructure than needed if our "plugins" are mostly file-based (dirs with manifests).
- **Recommendation:** **Adopt pluggy's mental model** (hookspecs define extension points, plugins register implementations). For AI_PROJECT_TEMPLATE, the "hooks" would be things like `on_init`, `on_activate`, `register_commands`, `register_agents`, `register_guardrail_rules`. Whether we use pluggy itself or a simpler file-based equivalent depends on implementation complexity.

### Source 8: Stevedore — Entry Point Plugin Management

- **URL:** https://github.com/openstack/stevedore
- **Tier:** T3 (OpenStack organization)
- **License:** Apache-2.0
- **Tests:** Yes (CI passing)
- **Stars:** ~250+
- **Relevance:** Built on setuptools entry points. Provides manager classes for common patterns: DriverManager (pick one), NamedExtensionManager (pick several), HookManager (call all). Very Pythonic, well-documented.
- **Risks:** Requires pip-installable packages (entry points need `setup.py`/`pyproject.toml`). Heavier distribution model than we likely need.
- **Recommendation:** **Useful reference** for manager patterns, but too tied to Python packaging for our git-repo-based plugins.

### Source 9: VS Code Extension Architecture

- **URL:** https://code.visualstudio.com/api/references/activation-events
- **Tier:** T1 (official documentation)
- **License:** N/A (architecture reference)
- **Relevance:** The most successful plugin system in developer tools. Key reusable patterns:
  - **Manifest-driven**: `package.json` declares everything (activation events, contributions, dependencies)
  - **Lazy activation**: Extensions load only when their trigger fires (e.g., `onLanguage:python`, `workspaceContains:**/activate`)
  - **Contribution points**: Extensions "contribute" to shared registries (commands, views, languages)
  - **Isolated execution**: Each extension runs in its own context
- **Risks:** JavaScript-specific implementation details.
- **Recommendation:** **Adopt the manifest + contribution points + lazy activation pattern.** Each AI_PROJECT_TEMPLATE plugin should have a `plugin.yaml` manifest declaring what it contributes (commands, agents, guardrail rules, env specs) and when it activates.

### Recommended Plugin Architecture for AI_PROJECT_TEMPLATE

Based on cross-ecosystem analysis, the recommended pattern is:

```
plugins/
  python-env/
    plugin.yaml          # Manifest: name, version, contributes, depends_on
    setup.sh             # on_init hook
    activate.sh          # on_activate hook (sourced by main activate)
    files/               # Files to copy/template into project
  claudechic/
    plugin.yaml
    setup.sh
    files/
  project-team/
    plugin.yaml
    files/
  guardrails/
    plugin.yaml
    files/
  pattern-miner/
    plugin.yaml
    files/
```

**Key design decisions borrowed from prior art:**
1. **From VS Code**: Manifest-driven discovery (`plugin.yaml`), contribution points, lazy activation
2. **From pluggy**: Hook specifications (well-defined extension points), 1:N composition
3. **From Copier**: Template evolution (`copier update` equivalent for plugin upgrades)
4. **From Nx**: Module boundary enforcement (plugins declare dependencies, not assume them)

---

## 3. AI-Specific Tooling & Multi-Agent Frameworks

### Source 10: Everything Claude Code (ECC)

- **URL:** https://github.com/hesreallyhim/awesome-claude-code
- **Tier:** T5 (well-maintained community repo)
- **License:** MIT
- **Tests:** Varies by component
- **Stars:** Community-curated, 100K+ stars on Claude Code itself
- **Relevance:** **Directly relevant ecosystem.** As of March 2026:
  - 28 specialized agents, 119 skills, 60 slash commands
  - v1.9.0 introduced "selective install architecture" — users pick which components to install
  - 15+ language ecosystems supported
  - This is the closest existing project to what AI_PROJECT_TEMPLATE is building
- **Risks:** JavaScript/TypeScript-centric. May overlap or compete with our approach.
- **Recommendation:** **Study ECC's selective install architecture closely.** Their component selection UX is prior art for our onboarding flow. Consider whether AI_PROJECT_TEMPLATE plugins could be distributed as ECC-compatible packages for broader reach.

### Source 11: awesome-claude-code-toolkit

- **URL:** https://github.com/rohitg00/awesome-claude-code-toolkit
- **Tier:** T5
- **License:** MIT
- **Stars:** Growing community resource
- **Relevance:** 135 agents, 35 curated skills (+400K via SkillKit), 42 commands, 150+ plugins, 19 hooks, 15 rules, 7 templates, 8 MCP configs. Demonstrates the sheer scale of the Claude Code extension ecosystem.
- **Recommendation:** **Reference for plugin categorization** and understanding what users expect from a Claude Code plugin system.

### Source 12: CrewAI — Role-Based Multi-Agent Orchestration

- **URL:** https://github.com/crewAIInc/crewAI
- **Tier:** T5
- **License:** MIT
- **Tests:** Yes (CI passing)
- **Stars:** ~25,000+
- **Relevance:** CrewAI's model — role-playing agents with defined roles, backstories, and goals assembled into "crews" — is architecturally similar to AI_PROJECT_TEMPLATE's Project Team. Key patterns:
  - Agent = role + goal + backstory + tools
  - Task = description + expected output + assigned agent
  - Crew = agents + tasks + process type (sequential/hierarchical)
  - Built-in memory (short-term, long-term, entity)
- **Risks:** Heavy Python framework. Different execution model (API-calling agents vs. Claude Code sub-processes).
- **Recommendation:** **Validate our agent team design against CrewAI's patterns.** Our COORDINATOR.md / role-file approach is lighter weight but conceptually similar. We should ensure our plugin system allows custom agent roles to be added as plugins.

### Source 13: LangGraph — Graph-Based Agent Workflows

- **URL:** https://github.com/langchain-ai/langgraph
- **Tier:** T3 (LangChain organization)
- **License:** MIT
- **Tests:** Yes (CI passing)
- **Stars:** ~10,000+
- **Relevance:** Reached v1.0 in late 2025. Graph-based state machines for agent workflows with durable execution, checkpointing, and conditional branching. LangGraph's concept of "tool nodes" and "conditional edges" could inform how plugins interact.
- **Risks:** Heavy framework dependency. Different paradigm than Claude Code's sub-process model.
- **Recommendation:** **Borrow the state machine concept** for plugin lifecycle (init -> configured -> active -> teardown), but don't adopt the framework.

### Source 14: OpenAI Agents SDK

- **URL:** https://github.com/openai/openai-agents-python
- **Tier:** T3 (OpenAI organization)
- **License:** MIT
- **Tests:** Yes
- **Stars:** Growing
- **Relevance:** Three built-in primitives worth studying: **Handoffs** (agent-to-agent transfer), **Guardrails** (input/output validation), **Tracing** (end-to-end observability). Our guardrails plugin maps to their Guardrails primitive.
- **Recommendation:** **Validate our guardrails design** against OpenAI's approach. Their tracing primitive suggests an observability plugin opportunity.

### Source 15: Superagent — Guardrails for Agentic AI

- **URL:** https://github.com/superagent-ai/superagent (community-driven)
- **Tier:** T5
- **License:** MIT
- **Relevance:** Open-source framework specifically for building agents *with safety built into the workflow*. Focuses on controlling what agents can do, access, and how they behave. Directly relevant to our guardrails plugin.
- **Recommendation:** **Reference for guardrails patterns** — compare their permission model with our role x action system.

### Conversation Pattern Mining — Limited Prior Art

- **Tier of best source:** T6 (blog posts and Microsoft's commercial tooling)
- **Findings:** Microsoft's Conversation Knowledge Mining Solution uses Azure services for topic modeling and key phrase extraction from conversation data. Academic work exists on error correction in conversational AI (MDPI, 2023). However, **no open-source tool does what our Pattern Miner does** — scanning JSONL Claude sessions to extract user corrections and feed them back into PATTERNS.md.
- **Recommendation:** **This is a genuine innovation.** The pattern miner plugin has no close open-source equivalent. It should be a first-class plugin and potentially a standalone tool that could attract external contributors.

---

## 4. Recommended Additional Plugins

Based on landscape analysis, here are concrete plugin recommendations ranked by value:

### High Priority (fill clear gaps)

| Plugin | Rationale | Prior Art |
|--------|-----------|-----------|
| **CI/CD Templates** | Every scaffolded project needs CI. GitHub Actions workflows for testing, linting, and deployment are table stakes. | Nx generators, ECC's CI skills, cookiecutter-pypackage |
| **Documentation Generator** | Auto-generate docs from code, agent roles, and plugin manifests. MkDocs/Sphinx setup + API docs. | Projen's docs component, ECC's documentation skills |
| **Observability / Tracing** | Track agent interactions, hook invocations, costs, and latencies. OpenAI SDK's Tracing primitive validates this need. | OpenAI Agents SDK tracing, LangSmith, Weights & Biases |
| **Linting / Code Quality** | Pre-configured ruff, mypy, pre-commit hooks. Pairs with guardrails for enforcement. | ECC's linting skills, cookiecutter linting templates |

### Medium Priority (valuable extensions)

| Plugin | Rationale | Prior Art |
|--------|-----------|-----------|
| **Git Hooks / Pre-commit** | Standardized pre-commit config with formatters, linters, secret scanners. | pre-commit framework, ECC hooks ecosystem |
| **Secrets Management** | `.env` handling, secret detection, vault integration patterns. | dotenv, git-secrets, detect-secrets |
| **Container / Docker** | Dockerfile + docker-compose templates for reproducible dev environments. Complements conda env plugin. | cookiecutter-docker, devcontainers |
| **Notebook / Jupyter** | Jupyter environment plugin with kernel management, nbstripout, papermill integration. | Already partially exists in `envs/jupyter.yml` |
| **MCP Server Templates** | Scaffold custom MCP servers for project-specific tool access. Growing ecosystem need. | Claude Code MCP docs, awesome-claude-code MCP configs |

### Lower Priority (nice to have)

| Plugin | Rationale | Prior Art |
|--------|-----------|-----------|
| **Release / Changelog** | Automated versioning, changelog generation, release workflows. | Nx Release, semantic-release, conventional-commits |
| **Monitoring Dashboard** | Web UI for viewing agent activity, guardrail hits, pattern miner output. | LangSmith, CrewAI dashboard |
| **Multi-Language Support** | Extend beyond Python — Node.js, Rust env management plugins. | Nx multi-language, ECC's 15 language ecosystems |
| **Data Pipeline Templates** | For data science projects: DVC, MLflow, experiment tracking scaffolding. | cookiecutter-data-science, DVC |

---

## 5. Key Recommendations Summary

### Architecture Decisions Supported by Prior Art

1. **Use Copier (not cookiecutter) as the template engine** — its `update` mechanism enables plugin evolution. Copier's questionnaire maps to our onboarding flow. (T5, MIT, tested, active)

2. **Adopt a manifest-based plugin system** inspired by VS Code extensions and Nx generators:
   - Each plugin has a `plugin.yaml` declaring metadata, contributions, dependencies, and hooks
   - Discovery is filesystem-based (scan `plugins/` directory)
   - Activation is lazy (plugins loaded only when needed)

3. **Use pluggy's hookspec/hookimpl pattern** for defining extension points:
   - `on_init`, `on_activate`, `register_commands`, `register_agents`, `register_guardrails`
   - Plugins implement only the hooks they need
   - 1:N composition (multiple plugins can contribute commands, agents, etc.)

4. **The Pattern Miner is a genuine innovation** — no close open-source equivalent exists. Prioritize it as a showcase plugin.

5. **Study Everything Claude Code's selective install architecture** — they've solved the "pick your components" UX problem. Our onboarding should learn from their approach.

6. **Validate against CrewAI's agent model** — our role-file approach is lighter but should support the same concepts (role, goal, tools, memory).

### What NOT to Do (Negative Results)

| Approach | Why Not |
|----------|---------|
| **Cookiecutter for templating** | No update mechanism — projects diverge from template permanently |
| **Projen for config management** | Overwrites hand-edited files on synth. Our users need to edit generated code. |
| **Full pluggy/stevedore for plugins** | Over-engineered for file-based plugins. A simpler YAML manifest + shell hooks system is sufficient. |
| **Adopt CrewAI/LangGraph directly** | Wrong execution model. Our agents are Claude Code sub-processes, not API-calling Python objects. |
| **Build a custom plugin registry/marketplace** | Premature. Start with local filesystem plugins, evolve to git-based distribution if adoption warrants it. |

---

## Not Recommended (Sources Found but Rejected)

| Source | Reason for Rejection |
|--------|---------------------|
| **Hygen** (template generator) | Limited community, no update mechanism, Node.js only |
| **Plop.js** (micro-generator) | Very limited — only string append/prepend. Turborepo wraps it and it's still insufficient. |
| **Ansible roles** (as plugin model) | Wrong abstraction level — infrastructure provisioning, not project scaffolding |
| **Terraform modules** (as plugin model) | Same as Ansible — infrastructure, not developer workflow |
| **Random "AI project template" repos on GitHub** | T8 sources — mostly abandoned cookiecutter templates with no tests or maintenance |

---

## Sources

- [Copier documentation](https://copier.readthedocs.io/en/stable/)
- [Copier comparisons](https://copier.readthedocs.io/en/stable/comparisons/)
- [Cookiecutter alternatives](https://www.cookiecutter.io/article-post/cookiecutter-alternatives)
- [Nx vs Turborepo](https://nx.dev/docs/guides/adopting-nx/nx-vs-turborepo)
- [Pluggy — pytest plugin system](https://github.com/pytest-dev/pluggy)
- [Stevedore documentation](https://docs.openstack.org/stevedore/latest/)
- [VS Code Activation Events](https://code.visualstudio.com/api/references/activation-events)
- [VS Code Extension Host](https://code.visualstudio.com/api/advanced-topics/extension-host)
- [Everything Claude Code](https://github.com/hesreallyhim/awesome-claude-code)
- [awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit)
- [CrewAI](https://crewai.com/open-source)
- [LangGraph vs CrewAI vs AutoGen comparison](https://dev.to/pockit_tools/langgraph-vs-crewai-vs-autogen-the-complete-multi-agent-ai-orchestration-guide-for-2026-2d63)
- [OpenAI Agents SDK](https://openai.com/index/introducing-agentkit/)
- [Superagent framework](https://www.helpnetsecurity.com/2025/12/29/superagent-framework-guardrails-agentic-ai/)
- [Degit](https://github.com/Rich-Harris/degit) / [Tiged](https://github.com/tiged/tiged)
- [Projen](https://github.com/projen/projen)
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Skills docs](https://code.claude.com/docs/en/skills)
- [Python plugin architecture patterns](https://sedimental.org/plugin_systems.html)
- [Microsoft Conversation Knowledge Mining](https://github.com/microsoft/Conversation-Knowledge-Mining-Solution-Accelerator)
