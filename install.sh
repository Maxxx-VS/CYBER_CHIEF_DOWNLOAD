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

# 3. Установка системных зависимостей
echo "Installing system dependencies..."
sudo apt update

# Для ARM архитектуры (Raspberry Pi)
if [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "armv7l" ]; then
    echo "ARM architecture detected, installing optimized dependencies..."
    sudo apt install -y portaudio19-dev python3-dev libopenblas-dev liblapack-dev libhdf5-dev
    sudo apt install -y libjpeg-dev libtiff5-dev libpng-dev libwebp-dev libopenexr-dev
    sudo apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
    sudo apt install -y libavcodec-dev libavformat-dev libswscale-dev libv4l-dev
else
    sudo apt install -y portaudio19-dev python3-dev libopenblas-dev liblapack-dev libatlas-base-dev libhdf5-dev
    sudo apt install -y libjpeg-dev libtiff5-dev libpng-dev libwebp-dev libopenexr-dev
    sudo apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
fi

# 4. Virtual env
cd requirements
python3 -m venv venv
source venv/bin/activate

# 5. Установка Python зависимостей
pip install --upgrade pip
pip install setuptools wheel

# Для ARM используем совместимые версии
if [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "armv7l" ]; then
    echo "Installing ARM-compatible packages..."
    pip install numpy==2.2.6
else
    pip install numpy==1.24.3
fi

pip install pillow python-dotenv pyserial schedule sqlalchemy requests tqdm

# Установка opencv-python
pip install opencv-python==4.8.1.78  # Более новая версия для ARM

# Установка pyaudio
pip install pyaudio

# Остальные зависимости
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "=== INSTALL COMPLETE ==="
echo "To activate virtual environment:"
echo "cd $PROJECT_DIR/requirements"
echo "source venv/bin/activate"
