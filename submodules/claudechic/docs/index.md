# Claude Chic

A stylish terminal UI for [Claude Code](https://docs.anthropic.com/en/docs/claude-code), built with [Textual](https://textual.textualize.io/).

```bash
uvx claudechic /welcome
```

Claude Code, but ...

-  **Stylish** - designed to remove clutter and focus attention
-  **Multi-Agent** - run several Claude agents in parallel
-  **Hackable** - easily extensible with Python Code
-  **Claude-forward** - with the same Claude Code agent you trust

This leverages the [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) to provide the same Claude intelligence with a different UX.

<div class="video-container">
<iframe src="https://www.youtube-nocookie.com/embed/2HcORToX5sU?autoplay=0&mute=0&loop=0&playlist=2HcORToX5sU" title="Claude Chic Introduction" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
</div>

## Get Started

```bash
uv tool install claudechic --upgrade
```

or

```bash
pip install claudechic --upgrade
```

Use Claude to log in with your subscription:

```bash
claude /login
```

And then run

```bash
claudechic
```

## FAQ

??? question "Does this replace Claude Code?"

    It replaces the `claude` CLI, but it wraps the same underlying `claude-agent-sdk` that the `claude` CLI uses.

    Additionally, you need `claude` to log in and for advanced configuration.

??? question "Can I use my existing Claude Code sessions?"

    Yes. This stores and loads all Claude state in exactly the way `claude` does.

??? question "Does it work with MCP servers?"

    Yes. This stores and loads all Claude state in exactly the way `claude` does.

??? question "Does it work with my Hooks and Skills?"

    Yes. This stores and loads all Claude state in exactly the way `claude` does.

??? question "How does this relate to OpenCode?"

    OpenCode is more impressive.  OpenCode supports many different models and is way more mature.

    OpenCode designed their own Agent logic.  Claude Chic reuses Claude Code's agent logic, which some people prefer.  This project is generally more thin.  You should try both.  You should try lots of things.

??? question "How do you make money?"

    This is an open source hobby project.  We do not currently have commercial aspirations

??? question "How mature is this project?"

    Not at all mature!  Expect bugs.  [Report issues](https://github.com/mrocklin/claudechic/issues/new).
