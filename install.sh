#!/bin/bash
set -euo pipefail

# Local install — run from inside the AI_PROJECT_TEMPLATE repo clone
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI Project Template — local setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Check git is available
if ! command -v git &> /dev/null; then
    echo "Error: git is required but not found. Please install git first:"
    echo "  https://git-scm.com/downloads"
    exit 1
fi

# 2. Ask where to create the project
read -rp "Where should the project be created? [$(pwd)] " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-.}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 3. Ask for the project name upfront (used as subdirectory name)
read -rp "Project name: " PROJECT_NAME
if [ -z "$PROJECT_NAME" ]; then
    echo "Error: project name is required."
    exit 1
fi

if [ -d "$PROJECT_NAME" ]; then
    echo "Error: directory '$PROJECT_NAME' already exists."
    exit 1
fi

# 4. Install pixi if not present
if ! command -v pixi &> /dev/null; then
    echo "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# 5. Run copier — project_name is pre-filled, copier asks the rest
echo ""
echo "Copier will now ask you a few more questions to configure your project."
echo ""
pixi exec --spec "copier>=9,<10" --spec git -- \
    copier copy --trust --data "project_name=$PROJECT_NAME" "$TEMPLATE_DIR" "$PROJECT_NAME"

# 6. Install environments
echo ""
echo "Installing environments..."
cd "$PROJECT_NAME"
pixi install

# 7. Generate guardrail hooks (needs pixi env for PyYAML)
if [ -f .claude/guardrails/generate_hooks.py ]; then
    echo "Generating guardrail hooks..."
    pixi run -e claudechic python .claude/guardrails/generate_hooks.py
fi

# 8. Launch claudechic
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✔ Project ready at: $(pwd)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next time, start with:"
echo "  cd $(pwd) && source activate && pixi run claudechic"
echo ""
echo "Launching claudechic..."
echo ""
pixi run claudechic
