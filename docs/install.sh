#!/bin/bash
set -euo pipefail

PROJECT_NAME="${1:?Usage: curl ... | bash -s <project-name> [install-dir]}"
INSTALL_DIR="${2:-.}"  # default: current directory
TEMPLATE_URL="https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI_PROJECT_TEMPLATE — project setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Install pixi if not present
if ! command -v pixi &> /dev/null; then
    echo "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# 2. Run copier in ephemeral pixi env (pinned version)
echo "Creating project '$PROJECT_NAME'..."
pixi exec --spec "copier>=9,<10" -- copier copy "$TEMPLATE_URL" "$INSTALL_DIR/$PROJECT_NAME"

# 3. Install environments
echo "Installing environments..."
cd "$INSTALL_DIR/$PROJECT_NAME"
pixi install

echo ""
echo "✔ Project '$PROJECT_NAME' is ready!"
echo "  cd $INSTALL_DIR/$PROJECT_NAME && source activate"
