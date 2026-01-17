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

# 1. Клонирование с исключением папки models
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Cloning repository without models directory..."
    
    # Создаем временный файл конфигурации sparse-checkout
    mkdir -p /tmp/git_sparse
    echo "/*" > /tmp/git_sparse/sparse-checkout
    echo "!models/" >> /tmp/git_sparse/sparse-checkout
    
    # Клонируем с настройками sparse-checkout
    git clone --no-checkout --depth 1 "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    git config core.sparseCheckout true
    git sparse-checkout init
    mv /tmp/git_sparse/sparse-checkout .git/info/sparse-checkout
    git checkout main || git checkout master
    rm -rf /tmp/git_sparse
else
    cd "$PROJECT_DIR"
fi

# 2. Проверка LFS (исключаем models)
git lfs pull --exclude="models/*"

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

# 4. Дополнительные зависимости для Python пакетов
echo "Installing additional dependencies for Python packages..."
sudo apt update
sudo apt-get update
sudo apt-get install -y mpg123 alsa-utils
sudo apt install -y portaudio19-dev python3-dev

# 5. Включение SSH (для Raspberry Pi)
if command -v raspi-config > /dev/null; then
    echo "Enabling SSH..."
    sudo raspi-config nonint do_ssh 0  # Используем неинтерактивный режим
    echo "SSH has been enabled via raspi-config."
else
    echo "Note: raspi-config not found. Skipping SSH enable."
fi

# 6. Virtual env
cd requirements
python3 -m venv venv
source venv/bin/activate

# 7. Установка Python зависимостей
pip install --upgrade pip
pip install setuptools wheel

# Установка всех зависимостей из requirements.txt
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "ERROR: requirements.txt not found!"
    exit 1
fi

# 8. Настройка journald и создание systemd сервисов
echo "Configuring systemd services..."

# Получаем абсолютный путь к проекту
cd ..
PROJECT_FULL_PATH="$(pwd)"
echo "Project path: $PROJECT_FULL_PATH"

# Создаем journald.conf для ограничения логов
echo "Creating /etc/systemd/journald.conf..."
sudo tee /etc/systemd/journald.conf > /dev/null << 'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=50M
RuntimeMaxFileSize=10M
MaxRetentionSec=2day
EOF

# Функция для создания сервиса
create_service() {
    local service_name=$1
    local description=$2
    local working_dir=$3
    local exec_script=$4
    
    echo "Creating service: $service_name"
    
    sudo tee /etc/systemd/system/$service_name > /dev/null << EOF
[Unit]
Description=$description
After=network.target

[Service]
Type=simple
User=sm
WorkingDirectory=$PROJECT_FULL_PATH/$working_dir
Environment="PYTHONPATH=$PROJECT_FULL_PATH"
ExecStart=$PROJECT_FULL_PATH/requirements/venv/bin/python $exec_script
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

# Создаем все сервисы
create_service "cyber_casir.service" "Cyber Chief - Casir Timer Service" "casir_timer" "casir_timer.py"
create_service "cyber_cooc.service" "Cyber Chief - Cooc Timer Service" "cooc_timer" "cook_timer.py"
create_service "cyber_monitor.service" "Cyber Chief - Monitoring System Service" "monitoring_system" "monitoring_system_main.py"
create_service "cyber_scale.service" "Cyber Chief - Scale Counter Service" "scale_counter" "scale_counter.py"
create_service "cyber_client.service" "Cyber Chief - Client Timer Service" "client_timer" "client_monitoring.py"
create_service "cyber_people.service" "Cyber Chief - People Counter Service" "people_counter" "people_counter.py"

# Обновляем конфигурацию Systemd
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Включаем автозагрузку сервисов
echo "Enabling services..."
sudo systemctl enable cyber_casir.service
sudo systemctl enable cyber_cooc.service
sudo systemctl enable cyber_monitor.service
sudo systemctl enable cyber_scale.service
sudo systemctl enable cyber_client.service
sudo systemctl enable cyber_people.service

echo "=== INSTALL COMPLETE ==="
echo "Systemd services have been created and enabled."
echo "To start services manually, use:"
echo "  sudo systemctl start cyber_casir"
echo "  sudo systemctl start cyber_cooc"
echo "  etc."
echo ""
echo "To check service status:"
echo "  sudo systemctl status cyber_casir"
echo ""
echo "To activate virtual environment:"
echo "cd $PROJECT_DIR/requirements"
echo "source venv/bin/activate"
