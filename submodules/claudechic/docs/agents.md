# Multi-Agent Workflows

Run multiple Claude agents simultaneously, each with its own context and working directory.

## Agents

Traditionally, one `claude` session is bound to one `agent`.  If you want to work on multiple things, you create multiple `claude` sessions in multiple terminals.

With Claude Chic, you type `/agent some-new-name` and a new agent starts running in your session with access to all the same files.  You can switch back and forth between these agents easily.

-  Many agents in parallel
-  Agents persist in normal Claude storage
-  Agents can run in different directories / git worktrees
-  Agents can start other agents
-  Agents can ask questions of other agents

### Example: Review

**Situation:** you've done lots of work and want a fresh agent to review this
work (not the one who helped you in the first place)

!!! user ""
    /agent reviewer

!!! user ""
    Please review the ongoing work in this branch with a critical eye.

    Tell the other agent running what you think when you're done.

When you call `/agent` you create a new agent and the UI immediately moves you
there.  That agent is in the same directory and can see all of your work, but
isn't biased by the context of your previous agent.

### Example: Review (automatic)

!!! user ""
    Start a new reviewing agent and have it review our work.  Ask it what it thinks

Claude Chic comes with a small MCP server that gives Claude the ability to use
the `/agent` and related commands.

## Agent Commands

| Command | Description |
|---------|-------------|
| `/agent` | List all running agents |
| `/agent <name>` | Create new agent in current directory |
| `/agent <name> <path>` | Create new agent in specified directory |
| `/agent close` | Close the current agent |
| `/agent close <name>` | Close agent by name |

You can also switch between agents or close them by clicking in the sidebar.

## Worktrees

[Git worktrees](https://git-scm.com/docs/git-worktree) create a git branch and a directory with a shared lifecycle.  They make it easy to run multiple copies of your repository so that multiple agents can edit/test/commit safely in parallel.

```
~/projects/
├── myrepo/            # Main worktree (main branch)
├── myrepo-feature-1/  # Some feature you're working on
├── myrepo-feature-2/  # Some feature you're working on
├── ...
└── myrepo-feature-n/  # Some feature you're working on
```

The lifecycle of the directory and the branch are linked, so as you clean up the git worktree/branch the directory is cleaned up as well.

Worktrees are great, but they're rarely-used enough that few people are familiar with how they work (or at least that was true of the library authors).  And so, we automated them into Claude Chic.

## Worktree Commands

| Command | Description |
|---------|-------------|
| `/worktree` | Show worktree picker modal |
| `/worktree <name>` | Create or switch to worktree |
| `/worktree finish` | Rebase, merge, and cleanup current worktree |
| `/worktree cleanup` | Remove stale worktrees |
| `/worktree cleanup <name>` | Remove specific worktree |

## Example: Worktree Workflow

**Situation:** You have an idea for a quick fix but you don't want to stop your
current work.  You branch off you repository into a new worktree and start
development in parallel with a new agent.

!!! user ""
    /worktree my-new-feature

!!! claude ""
    Created worktree 'my-new-feature' at ../myproject-my-new-feature with new agent

!!! user ""
    Let's start work building my new feature

!!! user ""
    ...

!!! user ""
    /worktree finish

Claude Chic sets up worktrees for you and runs new agents in them.  When you're done, the `/worktree finish` command safely handles the rebase/merge process so you have nice linear history, despite all of the concurrent development you're doing.

## Concurrent development

Used together, agents and worktrees make it trivial to have many ongoing threads of work, all neatly managed for you.  You can start a new thread any time and then leave it for days.  You can bounce between agents as they're busy or idle as you like.

In practice this also helps with agent context, creating many agents, each with a small task avoids context bloat and, anecdotally, may improve agent focus and performance.

## Example: Deep Review and Many Tasks

**Situation:** You ask Claude to do a deep review on your project and it
generates a lot of work.  You spawn all of that work in separate worktrees.

!!! user ""
    Do an in-depth review of this project, paying particular attention to
    organization and cleanliness.  Think hard and propose improvements

!!! claude ""
    This project is great, but has many issues.  Here are some:

    1.  ...
    2.  ...
    3.  ...
    4.  ...

!!! user ""
    Thank you, start worktrees for tasks 1, 2, and 4.

Then several new streams of work are created and you can engage with them
individually as they progress.  As they finish, run `/worktree finish` and
they'll be incorporated into the originating branch.

## Resuming work

When you restart Claude Chic, your worktrees will be listed in the agent list on the right sidebar.  When you click on them we'll resume the largest session in that worktree for you.  All of your state is, as always, stored in Claude state in `~/.claude/projects/`, just like any other Claude session.

In practice this means you can start work freely without worrying about
finishing it soon (or ever).  It is free to keep agents and worktrees around.
You can close your session and open it up again next week and all your agents
will be ready for you.

## Example: Chess

*Just for fun, you can ask Claude to play Chess against itself.  This doesn't
use worktrees, but does use multiple agents:*

<video src="https://github.com/user-attachments/assets/735ebc91-335e-4476-8fde-f49ce1df056a" autoplay loop muted playsinline style="max-width: 100%"></video>

## FAQ

??? question "How does this relate to normal SubAgents or Tasks?"

    Claude normally can launch subagents or tasks for parallel work .  These let Claude delegate work to other claude agents in parallel before bringing their summary back to the main agent.  This helps to parallelize and avoid context bloat.

    Claude Chic's use of agents differs in three ways:

    1.  You can interact with the agents as they do work
    2.  They can interact with each other
    3.  You can start and stop agents as you like, rather than always use a broadcast/collect pattern.

    In general Claude Chic gives you access to full agents, while SubAgents are somewhat limited.

??? question "I've heard of Git Worktrees but never used them."

    Yeah, you're in good company.

    Universally this was the answer when doing beta-testing on this project.  People like the idea, but worktrees are sufficiently foreign that no one uses them.  It's ok, you don't need to know how to.  Claude can handle that for you.

??? question "What kinds of multi-agent workflows do you recommend?"

    This is green field.  We encourage you to play and find out.  Common patterns (reviewing, worktrees, parallel research) are in this doc.
