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

# 4. Run copier (project_name is passed so copier won't re-ask)
echo ""
echo "Copier will now ask you a few questions to configure your project."
echo ""
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust --vcs-ref develop -d "project_name=$PROJECT_NAME" "$TEMPLATE_URL" "$PROJECT_DIR"

# 5. Install environments
echo ""
echo "Installing environments..."
cd "$PROJECT_DIR"
pixi install

# 6. Check Claude Code is installed and authenticated
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
