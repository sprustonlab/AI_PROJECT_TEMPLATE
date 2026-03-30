# Research Report: Scientific Use of AI — Landscape Survey for AI_PROJECT_TEMPLATE

**Requested by:** Coordinator (via user request)
**Date:** 2026-03-29
**Tier of best sources found:** T1 (Anthropic research blog), T2 (published peer-reviewed papers), T3 (official org repos)

---

## Query

How are scientists actually using AI coding assistants, multi-agent systems, and related tooling in research workflows? What patterns, guardrails, and scaffolding exist? How should these findings inform AI_PROJECT_TEMPLATE's plugin system and onboarding for scientific users?

---

## Findings

### Area 1: Scientists Using AI Coding Assistants in Research

#### Source 1: "Long-Running Claude for Scientific Computing" — Anthropic Research Blog

- **URL:** https://www.anthropic.com/research/long-running-Claude
- **Tier:** T1 (official Anthropic research)
- **License:** N/A (blog post / case study)
- **Tests:** N/A
- **Relevance:** **The single most relevant source for AI_PROJECT_TEMPLATE.** Describes exactly how scientists use Claude Code on HPC clusters for long-running autonomous research tasks. Key patterns discovered:

  **Infrastructure patterns:**
  - Scientists run Claude Code on **HPC clusters with SLURM** job scheduling
  - Sessions launched inside **tmux** on compute nodes — researchers detach and monitor remotely (even from phone)
  - 48-hour GPU allocations (e.g., H100-32 GPUs) for multi-day autonomous work

  **Coordination patterns (directly relevant to our plugins):**
  - **CLAUDE.md as master instructions** — persistent project goals, design decisions, success criteria. Claude treats this specially, keeping it in context and updating it as work progresses
  - **CHANGELOG.md as agent memory** — "lab notes" tracking completed tasks, failed approaches, accuracy metrics, known limitations. Failed strategies documented to prevent re-attempting dead ends
  - **Test oracles** — scientific code requires clear success metrics (reference implementations, quantifiable objectives). Agents continuously expand tests to prevent regressions
  - **Git-based coordination** — agents commit after meaningful work units, providing recoverable history
  - **"Ralph Loop" pattern** — re-prompts agents when they claim completion, asking if they're truly done. Combats "agentic laziness"

  **Case study — Boltzmann Solver:**
  - Claude Opus 4.6 implemented a differentiable cosmological Boltzmann solver in JAX
  - Reached sub-percent agreement with reference CLASS implementation in days (normally months of expert time)
  - Single-agent sequential work with subagent spawning proved better than parallel farming for deeply coupled pipelines
  - Agent made domain-naive mistakes (gauge conventions) that experts spot instantly

- **Risks:** Single case study from a cosmology expert. Patterns may not generalize to all scientific domains.
- **Recommendation:** **These patterns should directly inform plugin design.** The CLAUDE.md + CHANGELOG.md + test oracle + git commit patterns are exactly what AI_PROJECT_TEMPLATE should scaffold. A "Scientific Computing" plugin should set up this infrastructure automatically.

#### Source 2: "How Scientists Are Using Claude to Accelerate Research" — Anthropic

- **URL:** https://www.anthropic.com/news/accelerating-scientific-research
- **Tier:** T1 (official Anthropic)
- **Relevance:** Claude functions as collaborator across all research stages. Embeds into workflows via connectors to Benchling, 10x Genomics, PubMed, Medidata, ClinicalTrials.gov. Eliminates bottlenecks in tasks requiring deep knowledge that couldn't scale before.
- **Recommendation:** The connector pattern (domain-specific MCP servers) suggests a plugin category we should support.

#### Source 3: Claude Scientific Skills — K-Dense-AI

- **URL:** https://github.com/K-Dense-AI/claude-scientific-skills
- **Tier:** T5 (well-maintained community repo)
- **License:** Open source (check repo for specific license)
- **Tests:** Varies by skill
- **Stars:** Growing community adoption
- **Relevance:** **170+ curated scientific skills** across: genomics, drug discovery, molecular dynamics, RNA velocity, geospatial science, time series forecasting, medical imaging, physics, advanced data analysis. Skills are drop-in `.md` files that Claude Code auto-discovers. Covers 40+ models, 250+ scientific databases.
- **Risks:** Quality varies across skills. Not all skills have been validated for domain correctness.
- **Recommendation:** **Model our scientific plugin after this approach.** Skills as `.md` files in a discoverable directory is the same pattern AI_PROJECT_TEMPLATE already uses for agent roles. Our plugin system should make it trivial to install domain-specific skill packs. Consider: should AI_PROJECT_TEMPLATE plugins be compatible with Claude Scientific Skills format?

#### Source 4: Cookiecutter Data Science (CCDS)

- **URL:** https://github.com/drivendataorg/cookiecutter-data-science
- **Tier:** T5 (well-maintained, widely adopted)
- **License:** MIT
- **Tests:** Yes
- **Stars:** ~8,000+
- **Relevance:** The de facto standard for scientific Python project structure. Version 2 (2024) provides: separated raw/processed data, models, notebooks, reports folders. Reproducibility-first design. Pre-built scripts for common data science workflows.
- **Risks:** Cookiecutter-based (no update mechanism — see landscape survey). Python/data-science focused only.
- **Recommendation:** **Study CCDS's directory conventions** for our data science plugin. Their `data/raw`, `data/processed`, `models/`, `notebooks/`, `reports/` structure is widely recognized. Our onboarding should ask "Is this a data science project?" and offer a CCDS-like layout plugin.

#### Source 5: Cookiecutter Reproducible Science Templates

- **URL:** https://github.com/miguelarbesu/cookiecutter-reproducible-science, https://github.com/timtroendle/cookiecutter-reproducible-research
- **Tier:** T8 (small community repos)
- **License:** MIT
- **Tests:** Minimal
- **Relevance:** Templates focused on reproducible science: Python + conda + Snakemake + pandoc for generating HTML/PDF reports from raw data, code, and Markdown. The philosophy aligns with AI_PROJECT_TEMPLATE's env management plugin.
- **Risks:** Small repos, limited maintenance. Inspiration only.
- **Recommendation:** The Snakemake/workflow manager integration pattern is worth considering as a plugin.

---

### Area 2: Multi-Agent Systems in Scientific Research

#### Source 6: "Ten Simple Rules for Optimal and Careful Use of Generative AI in Science" — Helmy et al. (2025)

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC12561928/
- **Tier:** T2 (peer-reviewed, PLOS Computational Biology)
- **License:** N/A (published paper)
- **Citations:** Recent publication, accumulating citations
- **Relevance:** **Establishes the FOCUS Framework** — a structured approach to GenAI in science. Key rules mapped to AI_PROJECT_TEMPLATE:

  | FOCUS Rule | AI_PROJECT_TEMPLATE Implication |
  |-----------|-------------------------------|
  | Rule 1: Define Goals | Onboarding should ask users to define research goals upfront |
  | Rule 2: Understand Limitations | Guardrails plugin should surface AI limitations contextually |
  | Rule 3: Develop Communication Skills | Pattern Miner plugin mines corrections → improves prompts |
  | Rule 5: Automate Repetitive Tasks | Plugin system enables domain-specific automation |
  | Rule 6: Validate Iteratively | Test oracle pattern from Long-Running Claude |
  | Rule 7: Maintain Scientific Rigor | Guardrails should flag when AI makes domain claims |
  | Rule 9: Disclose Transparently | **New plugin opportunity**: AI contribution tracker |
  | Rule 10: Adhere to Guidelines | Guardrails can encode institutional AI policies |

  **Nine risks identified:** fabricated data, hallucinated citations, bias amplification, IP exposure, skill erosion. All directly addressable through guardrails.

  **Governance landscape:** Reviewed 100+ policies from governments, funders, universities, publishers. NIH/ERC prohibit AI in grant review. All major publishers require disclosure.

- **Risks:** Framework is advisory, not technical. Needs translation into concrete tooling.
- **Recommendation:** **The FOCUS Framework should inform our guardrails plugin design for scientific users.** Specifically: (1) AI contribution tracking/disclosure, (2) citation validation hooks, (3) data provenance enforcement, (4) institutional policy templates.

#### Source 7: Sakana AI's "The AI Scientist" — Automated Research Pipeline

- **URL:** https://github.com/SakanaAI/AI-Scientist (v1), https://github.com/SakanaAI/AI-Scientist-v2 (v2)
- **Tier:** T4 (code accompanying arXiv paper, now published in Nature)
- **License:** Apache-2.0
- **Tests:** Yes (Docker sandbox required)
- **Stars:** ~10,000+ (v1)
- **Relevance:** Fully automated end-to-end research pipeline: idea generation → literature search → experiment planning → code execution → figure generation → manuscript writing → peer review. Key findings:
  - v2 uses **agentic tree search** — branches into parallel experiments, picks promising results, backtracks on dead ends
  - Runs in Docker sandbox — **secure execution of LLM-generated code is non-negotiable**
  - Average cost: $6 per manuscript
  - **But**: 42% of experiments failed due to coding errors in evaluation; results sometimes logically flawed
  - v2 produced first fully AI-generated paper to pass rigorous human peer review
- **Risks:** High failure rate (42% coding errors). Not production-ready for most labs. Reproducibility concerns documented in independent evaluation (arxiv:2502.14297).
- **Recommendation:** **Don't adopt, but learn from the architecture.** The tree-search experimentation pattern and Docker sandboxing are relevant. A "sandbox execution" plugin for AI_PROJECT_TEMPLATE could provide safe code execution for scientific agents. The failure rate reinforces why guardrails and test oracles matter.

#### Source 8: FutureHouse Robin — Multi-Agent Scientific Discovery

- **URL:** https://github.com/Future-House/robin
- **Tier:** T3 (FutureHouse organization, published results)
- **License:** Open source
- **Stars:** Growing
- **Relevance:** **Most impressive multi-agent scientific system to date.** Robin autonomously:
  - Generated hypotheses for dry age-related macular degeneration treatment
  - Designed experiments (humans executed physically)
  - Analyzed results, iterated
  - Identified ripasudil as novel therapeutic candidate (7.5x increase in phagocytosis)
  - Entire concept-to-submission in 2.5 months

  **Component agents:** Crow, Falcon, Owl (literature), Phoenix (chemical synthesis), Finch (data analysis). Each specialized.

  **Successor — Kosmos (Edison Scientific):** Processes 1,500 papers and 42,000 lines of analysis code in a single run. Work equivalent to 6 months of PhD/postdoc in one session.

- **Risks:** Commercial spinout (Edison Scientific, $70M seed). Open-source availability may narrow. Biomedical-focused.
- **Recommendation:** **Robin validates AI_PROJECT_TEMPLATE's multi-agent approach for science.** Our Project Team agents (Coordinator, Implementer, Researcher, etc.) map to Robin's specialized agents. The key insight: **domain-specialized agents >> general-purpose agents** for scientific work. Our plugin system should support adding domain-specific agent roles (e.g., a "Bioinformatics Agent" plugin, a "Physics Simulation Agent" plugin).

#### Source 9: "Agentic AI for Scientific Discovery" — Survey Paper (2025)

- **URL:** https://arxiv.org/html/2503.08979v1
- **Tier:** T2 (arXiv survey, comprehensive)
- **Relevance:** Comprehensive survey covering the landscape. Key insights:
  - **Self-driving laboratories (SDLs)** — autonomous experiment execution and analysis, enhancing reproducibility
  - **STELLA** — biomedical agent that autonomously improves by dynamically expanding its library of tools and reasoning templates. Accuracy nearly doubled with operational experience. **This is what Pattern Miner does for Claude sessions.**
  - Frameworks like LitSearch, ResearchArena, ResearchAgent, Agent Laboratory automate research sub-workflows (citation management, survey generation, etc.)
  - Key challenges: reliability, reproducibility, auditability, safety, equitable access
- **Recommendation:** The self-improving agent pattern (STELLA) cross-references with our Pattern Miner plugin. The SDL concept suggests a "Lab Automation" plugin category.

#### Source 10: "From AI for Science to Agentic Science" — Survey (2025)

- **URL:** https://arxiv.org/html/2508.14111v1
- **Tier:** T2 (arXiv survey)
- **Relevance:** Documents the shift from "AI as tool" to "AI as autonomous researcher." Frameworks now automate the entire pipeline: idea → discovery → reporting. The AI Scientist and Robin are landmark examples. Gartner reports 1,445% surge in multi-agent system inquiries (Q1 2024 to Q2 2025).
- **Recommendation:** AI_PROJECT_TEMPLATE is well-positioned in this trend. The plugin architecture should support both "AI as tool" (simple skill plugins) and "AI as autonomous agent" (full agent role plugins with guardrails).

---

### Area 3: Guardrails & Safety for AI in Scientific Computing

#### Source 11: International AI Safety Report 2026

- **URL:** https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026
- **Tier:** T1 (international governmental report)
- **Relevance:** AI capabilities continue improving in math and coding (gold-medal IMO performance, agents complete 30-min tasks). **But**: systems still fabricate information and produce flawed code. Current techniques reduce but don't eliminate failure rates. Defence-in-depth (layered safeguards) is the recommended approach. Multi-turn prompt attacks achieve ~60% success rates on open-weight models.
- **Recommendation:** **Defence-in-depth validates our layered guardrails approach.** Scientific guardrails should layer: (1) role-based permissions, (2) domain-specific validation hooks, (3) citation/data provenance checks, (4) human review checkpoints.

#### Source 12: AI Guardrails Production Patterns (2026)

- **URL:** https://iterathon.tech/blog/ai-guardrails-production-implementation-guide-2026
- **Tier:** T6 (technical blog, recognized source)
- **Relevance:** Guardrails evolved from optional add-on to essential component in 2026. EU AI Act (effective 2025) classifies systems by risk level with strict requirements for high-risk applications. Data guardrails (input quality, bias removal, sensitive data filtering) form the foundation.
- **Recommendation:** Our guardrails plugin should include **scientific data guardrails**: prevent upload of patient data, enforce data anonymization, validate that training data meets institutional requirements.

---

### Area 4: Templating/Scaffolding for Scientific AI Projects

#### Source 13: pyds-cli — Modern Scientific Python Scaffolding

- **URL:** Referenced in Data Science Bootstrap Notes (https://ericmjl.github.io/blog/2025/9/2/the-data-science-bootstrap-notes-a-major-upgrade-for-2025/)
- **Tier:** T6 (expert blog)
- **Relevance:** New tool (2025) that scaffolds data science projects using cookiecutter + pixi, creating complete project structure with environment management, testing, docs, and CI/CD pre-configured. Shows the market need for opinionated scientific project scaffolding.
- **Recommendation:** Validates our approach. AI_PROJECT_TEMPLATE with plugins is the more composable version of this.

#### Source 14: Anthropic's "How AI is Transforming Work" — Internal Agent Patterns

- **URL:** https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic
- **Tier:** T1 (official Anthropic research)
- **Relevance:** Documents how Anthropic's own researchers use Claude Code sessions that average increasingly longer autonomous runs (from 25 min to 45+ min between Oct 2025 and Jan 2026). The key quote reframes the opportunity: *"every night you don't have agents working for you is potential progress left on the table."*
- **Recommendation:** Our onboarding for scientific users should highlight autonomous overnight/weekend runs as a primary use case. The HPC/SLURM plugin becomes essential.

---

## Recommendations — How This Informs AI_PROJECT_TEMPLATE

### Plugin Recommendations for Scientific Users

Based on all findings, here are **concrete new plugin recommendations** specific to scientific use:

#### High Priority — Validated by Multiple Sources

| Plugin | What It Does | Evidence |
|--------|-------------|----------|
| **Scientific Computing Setup** | Scaffolds CLAUDE.md with research goals, CHANGELOG.md as agent memory, test oracle directory, git commit patterns for autonomous runs | Long-Running Claude (Source 1), FOCUS Framework (Source 6) |
| **HPC/SLURM Integration** | SLURM job templates, tmux session management, GPU allocation scripts, remote monitoring setup | Long-Running Claude (Source 1) — scientists already doing this manually |
| **AI Contribution Tracker** | Logs which outputs were AI-generated, with model version, prompt hashes, timestamps. Generates disclosure statements for papers. | FOCUS Rule 9 (Source 6), publisher requirements across Nature/JAMA/PLoS/etc. |
| **Citation Validator** | Hook that checks AI-generated references against PubMed/DOI resolution. Prevents hallucinated citations. | FOCUS Rule 6 (Source 6), AI Scientist's 42% failure rate (Source 7) |
| **Domain Skill Packs** | Installable sets of domain-specific Claude skills (genomics, physics, chemistry, etc.) following Claude Scientific Skills format | K-Dense-AI (Source 3), Robin's specialized agents (Source 8) |

#### Medium Priority — Supported by Evidence

| Plugin | What It Does | Evidence |
|--------|-------------|----------|
| **Data Science Layout** | CCDS-compatible directory structure (data/raw, data/processed, models, notebooks, reports) | Cookiecutter Data Science (Source 4) |
| **Sandbox Execution** | Docker/container-based safe execution for AI-generated scientific code | AI Scientist (Source 7), AI Safety Report (Source 11) |
| **Scientific Guardrails** | Domain-specific safety rules: prevent patient data upload, enforce anonymization, validate statistical methods, flag extraordinary claims | FOCUS Framework (Source 6), Int'l AI Safety Report (Source 11) |
| **Experiment Tracker** | Integration with MLflow/Weights&Biases/DVC for experiment logging and reproducibility | Self-driving lab concept (Source 9), reproducibility concerns throughout |
| **Workflow Manager** | Snakemake/Nextflow templates for reproducible analysis pipelines | Cookiecutter Reproducible Research (Source 5), SDL concept (Source 9) |

#### Lower Priority — Forward-Looking

| Plugin | What It Does | Evidence |
|--------|-------------|----------|
| **MCP Connectors for Science** | Templates for connecting to PubMed, Benchling, 10x Genomics, domain DBs | Anthropic integrations (Source 2), K-Dense's 250+ DB access (Source 3) |
| **Paper Writing Assistant** | Agent role + templates for drafting methods, results, and figures sections | AI Scientist (Source 7), FOCUS Framework disclosure rules (Source 6) |
| **Domain Agent Roles** | Pluggable agent role definitions: Bioinformatics Agent, Physics Simulation Agent, Statistics Reviewer Agent | Robin's specialized agents (Source 8), STELLA's self-improvement (Source 9) |

### Onboarding Implications

Based on how scientists actually use these tools, the onboarding flow should include:

1. **"What kind of science?"** — Select domain (biology, physics, chemistry, data science, etc.) to auto-suggest relevant plugin bundles
2. **"Do you use HPC?"** — If yes, install SLURM + tmux + GPU management plugins
3. **"Do you need reproducibility tracking?"** — If yes, install AI contribution tracker + experiment tracker + data provenance plugins
4. **"Will agents run autonomously?"** — If yes, install scientific computing setup (CLAUDE.md patterns, test oracles, git commit hooks) + guardrails for autonomous operation
5. **"Do you publish papers?"** — If yes, install citation validator + AI disclosure generator + publisher policy templates

### Key Insight: The "Overnight Agent" Pattern

The most transformative pattern across all sources is **autonomous overnight/weekend agent runs on HPC**. Scientists submit SLURM jobs that launch Claude Code sessions running for hours or days, implementing solvers, processing data, or running experiments. AI_PROJECT_TEMPLATE should make this pattern first-class:

- Plugin that generates SLURM job scripts with proper resource allocation
- CLAUDE.md templates with clear success criteria and checkpointing
- CHANGELOG.md as structured agent memory (prevents re-exploring dead ends)
- Test oracle framework that agents can use to validate their own work
- Guardrails that are especially strict for autonomous (unattended) operation

### Key Insight: Pattern Miner is Validated by STELLA

The STELLA system (Source 9) autonomously improves its performance by dynamically expanding its library of tools and reasoning templates. This is conceptually identical to our Pattern Miner: scan sessions → extract corrections → update PATTERNS.md → improve future behavior. **Our Pattern Miner is not just a nice-to-have — it's implementing a validated self-improvement pattern that leading research systems use.**

---

## Not Recommended (Sources Found but Rejected)

| Source | Reason for Rejection |
|--------|---------------------|
| **K-Dense Web (commercial)** | Commercial platform built on open-source skills. Use the open-source skills repo, not the paid product. |
| **AI Scientist as template** | Too narrow (ML paper generation only), high failure rate (42%), Docker-only execution model |
| **Generic "AI coding assistant" blog posts** | T7-T8 sources that describe basic Copilot/Claude usage without scientific rigor |
| **LangChain for scientific agents** | Heavy framework dependency. Our sub-process model (Claude Code spawning) is lighter and more appropriate for HPC environments |

---

## ⚠️ Domain Validation Required

1. **HPC/SLURM patterns** — The job script patterns described in Source 1 are from a single cosmology lab. Other scientific domains (biology, chemistry) may have different HPC patterns. **Recommend: validate with users from 2-3 different scientific domains before finalizing the HPC plugin.**

2. **Citation validation** — Checking references against PubMed/DOI is straightforward for biomedical fields but may not cover all citation databases (e.g., ADS for astronomy, INSPIRE for particle physics). **Recommend: make the citation validator plugin configurable for different databases.**

3. **Scientific guardrails** — What constitutes an "extraordinary claim" varies by domain. Statistical thresholds (p-values, effect sizes) are domain-dependent. **Recommend: guardrail rules should be templated per domain, not hardcoded.**

---

## Sources

- [Long-Running Claude for Scientific Computing](https://www.anthropic.com/research/long-running-Claude) — Anthropic Research
- [How Scientists Are Using Claude](https://www.anthropic.com/news/accelerating-scientific-research) — Anthropic
- [Claude Scientific Skills](https://github.com/K-Dense-AI/claude-scientific-skills) — K-Dense-AI
- [Cookiecutter Data Science](https://github.com/drivendataorg/cookiecutter-data-science) — DrivenData
- [Ten Simple Rules for GenAI in Science](https://pmc.ncbi.nlm.nih.gov/articles/PMC12561928/) — Helmy et al., PLOS Comp Bio 2025
- [The AI Scientist](https://github.com/SakanaAI/AI-Scientist) — Sakana AI (published in Nature)
- [The AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2) — Sakana AI
- [FutureHouse Robin](https://github.com/Future-House/robin) — FutureHouse
- [Kosmos / Edison Scientific](https://edisonscientific.com/articles/announcing-kosmos) — Edison Scientific
- [Agentic AI for Scientific Discovery Survey](https://arxiv.org/html/2503.08979v1) — arXiv 2025
- [From AI for Science to Agentic Science](https://arxiv.org/html/2508.14111v1) — arXiv 2025
- [International AI Safety Report 2026](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026)
- [AI Guardrails Production Guide 2026](https://iterathon.tech/blog/ai-guardrails-production-implementation-guide-2026)
- [Anthropic: How AI is Transforming Work](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic)
- [Cookiecutter Reproducible Science](https://github.com/miguelarbesu/cookiecutter-reproducible-science)
- [Data Science Bootstrap Notes 2025](https://ericmjl.github.io/blog/2025/9/2/the-data-science-bootstrap-notes-a-major-upgrade-for-2025/)
