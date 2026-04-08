#!/bin/bash
set -euo pipefail

TEMPLATE_URL="https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI Project Template — setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Check git is available (required for claudechic install)
if ! command -v git &> /dev/null; then
    echo "Error: git is required but not found. Please install git first:"
    echo "  https://git-scm.com/downloads"
    exit 1
fi

# 1b. Verify GitHub access (claudechic is a private dependency)
PRIVATE_REPO="https://github.com/sprustonlab/claudechic.git"
if ! git ls-remote "$PRIVATE_REPO" HEAD &>/dev/null 2>&1; then
    echo ""
    echo "Error: Cannot access sprustonlab/claudechic (private repository)."
    echo ""
    echo "This template requires access to a private GitHub repo."
    echo "Please authenticate with GitHub first, then re-run this installer."
    echo ""
    case "$(uname -s)" in
        Darwin*)
            echo "  macOS:"
            echo "    brew install gh          # install GitHub CLI"
            echo "    gh auth login            # authenticate (opens browser)"
            echo "    gh auth setup-git        # configure git credentials"
            ;;
        Linux*)
            if command -v apt-get &> /dev/null; then
                echo "  Ubuntu/Debian:"
                echo "    sudo apt install gh      # install GitHub CLI"
            elif command -v dnf &> /dev/null; then
                echo "  Fedora/RHEL:"
                echo "    sudo dnf install gh      # install GitHub CLI"
            else
                echo "  Linux:"
                echo "    See https://github.com/cli/cli#installation"
            fi
            echo "    gh auth login            # authenticate (opens browser)"
            echo "    gh auth setup-git        # configure git credentials"
            ;;
    esac
    echo ""
    exit 1
fi

# 2. Ask where to create the project and what to name it
read -rp "Where should the project be created? [$(pwd)] " INSTALL_DIR < /dev/tty
INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"  # resolve to absolute path
read -rp "Project name: " PROJECT_NAME < /dev/tty
if [ -z "$PROJECT_NAME" ]; then
    echo "Error: project name is required."
    exit 1
fi

PROJECT_DIR="$INSTALL_DIR/$PROJECT_NAME"
if [ -d "$PROJECT_DIR" ]; then
    echo "Error: $PROJECT_DIR already exists."
    exit 1
fi

# 3. Install pixi if not present
if ! command -v pixi &> /dev/null; then
    echo "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# 4. Pick a quick-start preset
echo ""
echo "How much starter content should your project include?"
echo ""
echo "  Your project always ships with the full infrastructure: workflows"
echo "  (phase-gated processes with guardrails) and the Project Team"
echo "  (multi-agent collaboration). This choice controls how many"
echo "  EXAMPLES are pre-loaded."
echo ""
echo "  1) Everything  — all example content included (learning mode)"
echo "  2) Defaults    — sensible defaults (recommended for first project)"
echo "  3) Empty       — minimal skeleton (experienced user)"
echo "  4) Custom      — ask me about each option individually"
echo ""
read -rp "Pick a preset [1-4, default=2]: " PRESET_CHOICE < /dev/tty
case "${PRESET_CHOICE:-2}" in
    1) QUICK_START="everything" ;;
    2) QUICK_START="defaults"   ;;
    3) QUICK_START="empty"      ;;
    4) QUICK_START="custom"     ;;
    *) echo "Invalid choice, using defaults."; QUICK_START="defaults" ;;
esac

# 5. Run copier (project_name + quick_start passed so copier skips those)
echo ""
if [ "$QUICK_START" = "custom" ]; then
    echo "Copier will now ask you about each option individually."
else
    echo "Using '$QUICK_START' preset. Copier will ask a few remaining questions."
fi
echo ""
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust --vcs-ref develop \
    -d "project_name=$PROJECT_NAME" \
    -d "quick_start=$QUICK_START" \
    "$TEMPLATE_URL" "$PROJECT_DIR"

# 6. Install environments
echo ""
echo "Installing environments..."
cd "$PROJECT_DIR"
pixi install

# 7. Check Claude Code is installed and authenticated
if ! command -v claude &> /dev/null; then
    echo ""
    echo "✔ Project is ready!"
    echo ""
    echo "Claude Code is not installed. To get started:"
    echo ""
    echo "  npm install -g @anthropic-ai/claude-code"
    echo "  claude login"
    echo "  cd $PROJECT_DIR"
    echo "  source activate"
    echo "  pixi run claudechic"
    exit 0
fi

CLAUDE_AUTH=$(claude auth status 2>/dev/null || echo '{"loggedIn": false}')
if echo "$CLAUDE_AUTH" | grep -q '"loggedIn": false'; then
    echo ""
    echo "✔ Project is ready!"
    echo ""
    echo "Claude Code is installed but not logged in. To get started:"
    echo ""
    echo "  claude login"
    echo "  cd $PROJECT_DIR"
    echo "  source activate"
    echo "  pixi run claudechic"
    exit 0
fi

echo ""
echo "✔ Project is ready! Launching claudechic..."
echo ""
cd "$PROJECT_DIR"
source activate
pixi run claudechic
