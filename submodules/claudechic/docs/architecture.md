# Architecture

Claude Chic combines two libraries:

- **[Textual](https://textual.textualize.io/)** - Modern TUI framework for Python
- **[claude-agent-sdk](https://docs.anthropic.com/en/docs/claude-code)** - Official SDK for Claude Code

## Claude Agent SDK

In late 2025 Anthropic released their Agent SDK, which exposes the core logic of Claude Code and makes it easy to work into other tools like IDEs.

This SDK is the heart of Claude Code and handles all of the logic of execution, including ...

-  User prompts
-  Claude responses
-  Tool uses
-  Hooks
-  Skills
-  Context management
-  Session management
-  ... and more

Really it's everything *except* the TypeScript-based command line interface wrapper.  This allows us to build our own wrapper around the brains of Claude and experiment with different user interfaces.

## Textual

Many Python developers know [`rich`](https://github.com/Textualize/rich), the wonderful library for rich-client interfaces.  Rich makes the terminal look beautiful.

Textual is made by the same authors, and focuses on interactivity, turning the terminal into a platform to rival the web browser.  Textual gives the terminal features like ...

-  Responsive rendering
-  Mouse actions
-  Modern Layout
-  CSS
-  ... and more

The only reason Claude Chic looks good is because Textual makes it really easy to make the terminal look good.

## Hackability and Openness

And now, as a result, it's very easy to screw around and play with new terminal interfaces for Claude.

-  Want to click on tool uses to expand them?  Sure!
-  Want to center content on the screen?  Sure!
-  Want to add a TODO list sidebar?  Sure!
-  Want to design your own automatic compact logic?  Sure!
-  Want Bash tool uses to pop out a new terminal to run the command yourself if you click on it?  Sure!
-  Want to rebuild the whole thing in React + Electron?  Sure!

It's trivial to add features to Claude Chic, or to build your own version.   Please enjoy playing with code.
