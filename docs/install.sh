#!/bin/bash
set -euo pipefail

TEMPLATE_URL="https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI Project Template — setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Ask where to create the project
read -rp "Where should the project be created? [$(pwd)] " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-.}"

# 2. Install pixi if not present
if ! command -v pixi &> /dev/null; then
    echo "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# 3. Run copier (asks project name and all other questions)
echo ""
echo "Copier will now ask you a few questions to configure your project."
echo ""
cd "$INSTALL_DIR"
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust "$TEMPLATE_URL" .

# 4. Find the created project (most recent directory)
PROJECT_DIR=$(ls -td */ 2>/dev/null | head -1)
if [ -z "$PROJECT_DIR" ]; then
    echo "Error: No project directory created."
    exit 1
fi

# 5. Install environments
echo ""
echo "Installing environments..."
cd "$PROJECT_DIR"
pixi install

echo ""
echo "✔ Project is ready! Launching claudechic..."
echo ""
source activate
pixi run claudechic
