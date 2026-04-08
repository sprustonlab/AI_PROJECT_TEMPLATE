# Vision Phase

## Welcome

Start by welcoming the user and framing this tutorial:

> "Welcome to the **tutorial-toy-project** workflow!
>
> This tutorial walks you through building a real project — **labmeta** — using the same multi-agent workflow that powers the full Project Team. You'll experience every stage of the process firsthand.
>
> The Project Team workflow has 4 main phases:
>
> | Phase | What happens | Who does the work |
> |-------|-------------|-------------------|
> | **Vision** | Define the project goal and scope | You + Coordinator |
> | **Specification** | Analyze requirements, design the architecture | Leadership agents (Composability, Terminology, Skeptic, UserAlignment) |
> | **Implementation** | Write the code | Implementer agents |
> | **Testing** | Verify everything works | TestEngineer agent |
>
> The Coordinator (me) orchestrates the team — I delegate tasks to specialist agents, I don't write code myself. You'll see how each phase transitions to the next using advance checks (gates that must pass before moving on).
>
> We're in **Phase 1: Vision** right now. Let's start!"

## Present the Project

The project goal is pre-selected for this tutorial. Present it to the user by focusing on the **problem** and **why it matters** — not implementation details:

> **Project: labmeta — Animal Experiment Metadata Manager**
>
> **The problem:** In neuroscience labs, every experiment session (a surgery, an imaging run, a behavioral trial) has metadata — the mouse strain, stereotactic coordinates, drug doses, equipment settings. Right now this lives in spreadsheets, paper notebooks, or ad-hoc YAML files with no structure. When a lab runs the same procedure on 50 mice, the metadata is copy-pasted and drifts. There's no way to enforce consistency, no inheritance, and no protection against accidentally editing a completed experiment's records.
>
> **The vision:** A tool where you define a **protocol** once (e.g. "cranial window surgery v2") and then create per-animal **session records** that inherit from it. If the protocol says "use isoflurane at 1.5%", every session gets that default — but a specific session can override it ("this mouse needed 2%"). Once an experiment is done, the record is **locked** so nobody accidentally changes it. The tool **validates** everything against a schema so you can't enter "mouse" where a strain name is expected.
>
> **Why this project for the tutorial?** It's small enough to build in one session (~380 lines) but exercises every Project Team feature: multi-agent delegation, workflow rules, advance checks, and phase transitions. And it's a real problem that labs actually face.
>
> **In the Vision phase, we're answering:** What should this tool do? Who is it for? What are the key concepts? We're NOT designing the code yet — that comes in Specification.

## After User Confirms

Once the user approves, call `advance_phase` to move to the specification phase.

## If User Wants Changes

This is a tutorial with a pre-selected project. Gently explain that the project is fixed for this tutorial, but they can build their own project using the full Project Team workflow (`/project-team`) after completing this tutorial.
