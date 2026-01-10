# install.sh

#!/bin/bash
set -e

REPO_URL="https://github.com/Maxxx-VS/CYBER_CHIEF_DOWNLOAD.git"
PROJECT_DIR="cyber_chief"

echo "=== CYBER_CHIEF INSTALLER ==="

# 0. Проверка Git LFS
if ! command -v git-lfs &> /dev/null; then
    echo "Installing git-lfs..."
    sudo apt update
    sudo apt install git-lfs -y
    git lfs install
fi

# 1. Клонирование
if [ ! -d "$PROJECT_DIR" ]; then
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 2. Проверка LFS
git lfs pull

# 3. Virtual env
cd requirements
python3 -m venv venv
source venv/bin/activate

# 4. Install deps
pip install --upgrade pip
pip install -r requirements.txt

echo "=== INSTALL COMPLETE ==="
