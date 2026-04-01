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

# 1b. Ensure a credential helper is configured (needed for private deps)
if [ -z "$(git config --global credential.helper 2>/dev/null)" ]; then
    case "$(uname -s)" in
        Darwin*)
            echo "Configuring git credential helper (osxkeychain)..."
            git config --global credential.helper osxkeychain
            ;;
        Linux*)
            # Use cache with 1-hour timeout as fallback
            echo "Configuring git credential helper (cache)..."
            git config --global credential.helper 'cache --timeout=3600'
            ;;
    esac
fi

# 1c. Verify GitHub credentials are cached (claudechic is a private dependency)
#     Do a test fetch BEFORE copier runs — this lets the user authenticate
#     interactively so the credential helper stores the token for later.
PRIVATE_REPO="https://github.com/sprustonlab/claudechic.git"
if ! git ls-remote "$PRIVATE_REPO" HEAD &>/dev/null; then
    echo ""
    echo "This template requires access to a private GitHub repository."
    echo "Please authenticate when prompted (credentials will be saved)."
    echo ""
    if ! git ls-remote "$PRIVATE_REPO" HEAD < /dev/tty; then
        echo ""
        echo "Error: Could not access $PRIVATE_REPO"
        echo "  You need read access to sprustonlab/claudechic."
        echo "  Tip: create a Personal Access Token at https://github.com/settings/tokens"
        echo "       with 'repo' scope, then use it as your password."
        exit 1
    fi
    echo "Authentication successful — credentials saved."
fi

# 2. Ask where to create the project and what to name it
read -rp "Where should the project be created? [$(pwd)] " INSTALL_DIR < /dev/tty
INSTALL_DIR="${INSTALL_DIR:-.}"
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
echo "[debug] TEMPLATE_URL=$TEMPLATE_URL"
echo "[debug] PROJECT_DIR=$PROJECT_DIR"
echo "[debug] git version: $(git --version)"
echo "[debug] credential.helper: $(git config --global credential.helper 2>/dev/null || echo 'not set')"
echo "[debug] GIT_ASKPASS: ${GIT_ASKPASS:-not set}"
echo "[debug] GIT_TERMINAL_PROMPT: ${GIT_TERMINAL_PROMPT:-not set}"

# Credentials are already cached from step 1c — copier and pixi can use them.

echo "[debug] Starting copier copy..."
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust -d "project_name=$PROJECT_NAME" "$TEMPLATE_URL" "$PROJECT_DIR"
echo "[debug] Copier copy completed."

# 5. Install environments
echo ""
echo "Installing environments..."
echo "[debug] Running pixi install in $PROJECT_DIR"
cd "$PROJECT_DIR"
pixi install

# Generate guardrail hooks (needs pixi env for PyYAML)
if [ -f .claude/guardrails/generate_hooks.py ]; then
    echo "Generating guardrail hooks..."
    pixi run -e claudechic python .claude/guardrails/generate_hooks.py
fi

echo ""
echo "✔ Project is ready! Launching claudechic..."
echo ""
source activate
pixi run claudechic
