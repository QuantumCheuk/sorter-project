#!/bin/bash
# ============================================================
# HUSKY-SORTER-001 — Raspberry Pi 首次开机设置脚本
# 适用：Raspberry Pi 4B (2GB+) + Raspberry Pi OS 64-bit
# 用法：sudo bash pi_setup.sh
# ============================================================
set -e

echo "=========================================="
echo "HUSKY-SORTER-001 Pi Setup"
echo "=========================================="

# ---------- 1. 系统更新 ----------
echo "[1/10] 系统更新..."
apt update && apt upgrade -y

# ---------- 2. 必需依赖 ----------
echo "[2/10] 安装Python依赖..."
apt install -y python3-pip python3-venv python3-dev \
    libffi-dev libssl-dev libjpeg-dev zlib1g-dev libopenblas-dev \
    git libsystemd-dev pkg-config

pip3 install --upgrade pip

# ---------- 3. I2C/SPI/摄像头启用 ----------
echo "[3/10] 启用I2C/SPI/摄像头..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" >> /boot/config.txt
fi
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" >> /boot/config.txt
fi
if ! grep -q "^start_x=1" /boot/config.txt; then
    echo "start_x=1" >> /boot/config.txt
fi
if ! grep -q "^gpu_mem=256" /boot/config.txt; then
    echo "gpu_mem=256" >> /boot/config.txt
fi

# 启用1-Wire（DS18B20温度传感器备用）
if ! grep -q "^dtparam=w1-gpio" /boot/config.txt; then
    echo "dtparam=w1-gpio" >> /boot/config.txt
fi

echo "I2C/SPI/摄像头已启用（需重启生效）"

# ---------- 4. 项目代码克隆 ----------
echo "[4/10] 克隆项目代码..."
PROJECT_DIR="/home/pi/husky-sorter"
if [ -d "$PROJECT_DIR" ]; then
    echo "项目已存在于 $PROJECT_DIR，拉取最新..."
    cd "$PROJECT_DIR" && git pull
else
    git clone https://github.com/QuantumCheuk/sorter-project.git "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"
pip3 install -e sorter/ 2>/dev/null || true

# ---------- 5. Python依赖安装 ----------
echo "[5/10] 安装项目Python依赖..."
pip3 install \
    RPi.GPIO smbus2 spidev \
    hx711 \
    paho-mqtt flask flask-cors \
    opencv-python-headless numpy picamera2 \
    Pillow matplotlib pandas \
    adafruit-circuitpython-ads1x15 \
    smbus2 pyserial

# ---------- 6. MQTT服务配置 ----------
echo "[6/10] 配置MQTT broker..."
apt install -y mosquitto mosquitto-clients

cat > /etc/mosquitto/conf.d/sorter.conf << 'EOF'
listener 1883
allow_anonymous true
persistence true
persistence_location /var/lib/mosquitto/
EOF

systemctl enable mosquitto
systemctl restart mosquitto
echo "MQTT broker已启动（端口1883）"

# ---------- 7. 网络配置 ----------
echo "[7/10] 网络配置..."
read -p "请输入WiFi SSID: " WIFI_SSID
read -sp "请输入WiFi密码: " WIFI_PASS
echo ""
raspi-config nonint do_wifi_ssid_passphrase "$WIFI_SSID" "$WIFI_PASS"
echo "WiFi已配置"

# ---------- 8. 静态IP（可选） ----------
read -p "是否配置静态IP? [y/N]: " SET_STATIC
if [ "$SET_STATIC" = "y" ]; then
    read -p "输入静态IP（如192.168.1.100）: " STATIC_IP
    read -p "输入网关IP（如192.168.1.1）: " GATEWAY_IP
    
    cat >> /etc/dhcpcd.conf << EOF

# HUSKY-SORTER-001 静态IP
interface wlan0
static ip_address=${STATIC_IP}/24
static routers=${GATEWAY_IP}
static domain_name_servers=${GATEWAY_IP}
EOF
    echo "静态IP已配置"
fi

# ---------- 9. GPIO权限 ----------
echo "[9/10] 配置GPIO权限..."
if ! groups pi | grep -q gpio; then
    usermod -a -G gpio pi
fi
# www-data用户（如用nginx运行Flask）
usermod -a -G gpio,spi,i2c www-data 2>/dev/null || true

# ---------- 10. 自动启动服务 ----------
echo "[10/10] 配置systemd自动启动服务..."
cat > /etc/systemd/system/husky-sorter.service << EOF
[Unit]
Description=HUSKY-SORTER-001 Control Service
After=network.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=${PROJECT_DIR}
ExecStart=/usr/bin/python3 ${PROJECT_DIR}/sorter/control/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable huskysorter 2>/dev/null || true

echo ""
echo "=========================================="
echo "✅ Pi设置完成！"
echo ""
echo "📋 后续步骤："
echo "  1. 重启: sudo reboot"
echo "  2. 验证I2C: sudo i2cdetect -y 1"
echo "  3. 验证摄像头: raspistill -o test.jpg"
echo "  4. 运行主程序: python3 sorter/control/main.py"
echo "  5. 运行仪表盘: python3 sorter/control/dashboard.py"
echo "  6. 测试MQTT: mosquitto_pub -t test -m hello"
echo "=========================================="
echo ""
echo "⚠️  重启前请确认："
echo "  - /boot/config.txt 已更新（I2C/SPI/摄像头）"
echo "  - WiFi已配置"
echo "  - 项目已克隆到 $PROJECT_DIR"
echo ""
read -p "立即重启? [y/N]: " DO_REBOOT
if [ "$DO_REBOOT" = "y" ]; then
    echo "正在重启..."
    reboot
fi
