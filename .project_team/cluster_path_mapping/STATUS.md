# Project: cluster_path_mapping

## Phase: Setup

## Vision
Improve cluster MCP tools' cross-platform path handling (SMB mounts, Windows, WSL) so more users can use them. Ensure the model is aware of config options to guide users. TDD approach — failing tests first, then implement.

## Approach
Test-Driven Development: write failing tests that define expected behavior, then implement until they pass.

## Key Deliverables
- `remote_cwd` config option for cluster tools
- `path_map` bidirectional local↔cluster path translation
- Windows/POSIX/UNC/WSL path normalization
- Model-facing documentation for config options
- Comprehensive test coverage (written first)

## Agents
(not yet spawned)
