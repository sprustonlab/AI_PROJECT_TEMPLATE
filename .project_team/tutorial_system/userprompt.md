# Tutorial System

## User Request
Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task. Tutorial ideas include: signing up for GitHub, SSH-ing into a cluster for the first time, learning a coding feature, setting up git config & SSH keys, creating a first project from the template, understanding pixi environments, writing and running a first test with pytest.

## Vision Summary

**Goal:** Add a "tutorial" system to the template that guides users through common tasks using a combination of markdown content, agent teams, hints, and guardrails — all working together in a dedicated tutorial mode.

**Value:** New users (especially scientists) often struggle with foundational dev tasks (GitHub signup, SSH setup, coding patterns). Instead of external docs, the template itself teaches them interactively with AI guidance and safety rails.

**Domain terms:** tutorial, tutorial mode, tutorial step, tutorial guardrails, checkpoint guardrail

**Success looks like:** A user types a command, picks "SSH into my cluster," and gets a guided, interactive walkthrough — with agents helping, hints nudging, and guardrails both preventing mistakes AND verifying that each step was actually completed (e.g., "did the SSH key actually get added to the agent?" "does `git remote -v` actually return a GitHub URL?"). The agent can't just say "done" — the guardrails prove it.

**Failure looks like:** Tutorials that are just static markdown rendered by an agent (no interactivity, no guardrails, no hints integration). Or tutorials where the agent claims success without verification — the user thinks they're set up but nothing actually works.
