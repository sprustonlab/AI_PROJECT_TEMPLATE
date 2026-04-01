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
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust -d "project_name=$PROJECT_NAME" "$TEMPLATE_URL" "$PROJECT_DIR"

# 5. Install environments
echo ""
echo "Installing environments..."
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
