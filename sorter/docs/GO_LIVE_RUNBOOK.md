# HUSKY-SORTER-001 首-batch Go-Live 运行手册

| 文档信息 | |
|---|---|
| 文档编号 | HSKY-DOC-007 |
| 版本 | v1.0 |
| 适用机型 | HUSKY-SORTER-001 |
| 编写日期 | 2026-05-15 |
| 预计硬件到位 | ~2026-07-13（HQ Camera + 涡轮鼓风机 60d） |
| 预计 Go-Live | ~2026-07-24 |

---

## 目录

1. [概述](#1-概述)
2. [Go-Live 前检查清单（硬件到位前）](#2-go-live-前检查清单硬件到位前)
3. [开箱验货（Day 0）](#3-开箱验货-day-0)
4. [硬件组装（Day 1）](#4-硬件组装-day-1)
5. [软件安装与配置（Day 1）](#5-软件安装与配置-day-1)
6. [传感器标定（Day 2）](#6-传感器标定-day-2)
7. [空机联调测试（Day 2）](#7-空机联调测试-day-2)
8. [首-batch 测试运行（Day 3）](#8-首-batch-测试运行-day-3)
9. [首-batch 生产运行（Day 3）](#9-首-batch-生产运行-day-3)
10. [Go-Live 判定标准](#10-go-live-判定标准)
11. [Go-Live 后检查清单](#11-go-live-后检查清单)
12. [常见问题与应急处理](#12-常见问题与应急处理)
13. [Go-Live 里程碑记录](#13-go-live-里程碑记录)

---

## 1. 概述

### 1.1 目的

本手册为 HUSKY-SORTER-001 交付后，从开箱验货到首次成功生产批次运行（First Batch Go-Live）的完整操作指南。确保所有软件、硬件、传感器和执行器在投入生产前经过正确安装、标定和验证。

### 1.2 预期时间线

| 阶段 | 内容 | 预计时长 |
|------|------|---------|
| Day 0（下午） | 开箱验货 + 初步检查 | 2-3h |
| Day 1（全天） | 硬件组装 + 软件安装 | 6-8h |
| Day 2（上午） | 传感器标定 | 3-4h |
| Day 2（下午） | 空机联调测试 | 2-3h |
| Day 3（上午） | 首-batch 测试运行 | 2-3h |
| Day 3（下午） | 首-batch 生产运行 + Go-Live | 2-3h |

### 1.3 所需人员

- **机械装配**：1人（具备3D打印件组装经验）
- **电气接线**：1人（具备电子设备接线经验）
- **软件操作**：1人（熟悉 Linux/Raspberry Pi）
- **咖啡质量判别**：1人（SCA 杯测基础，可选）

### 1.4 所需工具

| 工具 | 规格 | 备注 |
|------|------|------|
| 内六角扳手套装 | M2/M2.5/M3/M4 | 3D打印件组装 |
| 十字螺丝刀 | PH0/PH1/PH2 | 电气接线 |
| 剥线钳 | 0.2-2.5mm² | 线缆处理 |
| 数字万用表 | DMM ≥ 4.5位 | 电气检测 |
| 示波器（可选） | 20MHz+ | 时序调试 |
| USB-A 转 Micro-USB 线 | 1m | ESP32 编程 |
| HDMI 显示器 | 1080p | Pi 图形界面 |
| USB 键盘 + 鼠标 | 标准布局 | Pi 操作 |
| 压缩空气 | 0.5MPa + 油水分离器 | 气路测试 |
| Reference coffee sample | ≥500g SCA 标样 | 颜色/缺陷标定 |

### 1.5 系统架构总览

```
[入料斗]
    ↓
[缓冲仓 + 螺旋给料]
    ↓
[旋转分配器] → [通道1] / [通道2] / [通道3]
    ↓
[光电传感器 T1] → [Top Camera] 拍摄
    ↓
[透明通道窗口]
    ↓
[光电传感器 T2] → [Bottom Camera] 拍摄
    ↓
[称重传感器 HX711]
    ↓
[密度分离区（涡轮鼓风机）]
    ↓
[含水率传感器 AD7746]
    ↓
[气喷剔除阀] → [缺陷豆出口]
    ↓
[合格豆出口]
```

---

## 2. Go-Live 前检查清单（硬件到位前）

> ⚠️ 以下工作可在硬件到位前完成，无需等待实物到达。

### 2.1 软件准备

- [ ] **Raspberry Pi OS** 烧录至 SD 卡（推荐 32GB A2 级）
  ```bash
  # 使用 Raspberry Pi Imager
  # 选择 Raspberry Pi OS (64-bit) with desktop
  # 配置：主机名=sorter-001，用户=pi，WiFi，SSH 启用
  ```

- [ ] **克隆项目代码**
  ```bash
  ssh pi@sorter-001.local
  git clone https://github.com/QuantumCheuk/sorter-project.git
  cd sorter-project
  ```

- [ ] **安装 Python 依赖**
  ```bash
  pip install -r requirements.txt
  # 关键依赖：RPi.GPIO smbus2 flask paho-mqtt numpy opencv-python
  ```

- [ ] **运行 CI 管道验证**
  ```bash
  cd sorter-project
  PYTHONPATH=. python3 sorter/tests/ci_pipeline.py
  # 目标：10/10 PASS
  ```

- [ ] **安装 MQTT Broker（Mosquitto）**
  ```bash
  sudo apt install -y mosquitto mosquitto-clients
  sudo systemctl enable mosquitto
  ```

- [ ] **烧录 ESP32 固件**（备用）
  ```bash
  cd sorter-project/firmware/sorter_esp32/
  platformio run --target upload --environment esp32dev
  ```

### 2.2 场地确认

- [ ] **电气**：确认 220V/10A 专用回路可用，接地端子已连接
- [ ] **空间**：机台位置已标记，400×300×500mm，周边 ≥500mm 操作空间
- [ ] **网络**：Pi 已连接 WiFi 或以太网，可远程 SSH
- [ ] **压缩空气**：空压机就位，出口压力 0.5-0.8MPa，油水分离器已安装
- [ ] **照明**：操作区域照明 ≥500 lux（颜色检测对光照敏感）
- [ ] **温湿度**：环境温度 18-30°C，相对湿度 40-70%（含水率传感器敏感）

### 2.3 参考样本准备

- [ ] **SCA 认证参考豆**：≥500g，标称缺陷率 0%（用于验证分选精度）
- [ ] **缺陷样本收集**：各类缺陷豆（发霉/发酵/黑豆/碎豆/虫蛀）各 ≥50g
- [ ] **Grade A 商业豆**：≥2kg，用于首-batch 测试

---

## 3. 开箱验货（Day 0）

### 3.1 开箱步骤

1. **记录外包装状态**
   - 拍摄外包装6面照片（特别是破损/变形处）
   - 测量包装尺寸：长×宽×高cm
   - 测量总重量：kg（含木箱）
   - 对照 PROCUREMENT_GUIDE.md 包装清单

2. **逐件核查**
   
   | 类别 | 核查项目 | 核对依据 |
   |------|---------|---------|
   | 机械 | 3D 打印件（19种）全部到位 | manufacturing_readiness.py 清单 |
   | 机械 | 孔板×5级（激光切割 PMMA） | 尺寸规格 |
   | 机械 | 涡轮鼓风机 | 型号标签 |
   | 电气 | Raspberry Pi 4 Model B | 4GB 版本 |
   | 电气 | ESP32 DevKit V1 | 引脚数量确认 |
   | 电气 | HQ Camera IMX477 | 序列号记录 |
   | 电气 | USB Camera（C270） | 数量×2 |
   | 电气 | HX711 模块×3 | 数量确认 |
   | 电气 | AD7746 模块 | 含水率传感器 |
   | 电气 | Nema17 步进电机×3 | 型号确认 |
   | 电气 | 28BYJ-48 步进电机 | 数量确认 |
   | 电气 | 杜邦线套装 | 母对母/公对母 |
   | 气动 | 电磁阀×4 | 5V/12V 确认 |
   | 气动 | 气管 4mm | 长度确认 |
   | 其他 | 电源适配器套装 | 5V/12V |
   | 其他 | 备用螺丝/螺母套装 | 规格对照 |

3. **外观检查（每件）**
   - 3D 打印件：检查层间粘合、开裂、变形
   - 电机轴：检查同心度、转动平滑
   - 相机镜头：检查划痕、污染
   - 传感器模块：检查焊点、PCB 完整性

4. **记录异常**
   - 如有任何短缺或损坏，立即拍照
   - 联系供应商（保留发票/订单号）
   - 填写 `INCOMING_INSPECTION_REPORT.md`

### 3.2 拍照存档要求

每件主要设备拍摄以下角度：
- 正面（设备标签清晰可见）
- 侧面（接口侧）
- 序列号/型号特写
- 任何异常/损坏处特写

---

## 4. 硬件组装（Day 1）

> 参考：`sorter/docs/WIRING_GUIDE.md` + `sorter/docs/COMMISSIONING_GUIDE.md`

### 4.1 机构组装顺序

**Phase 1：机架与底座**
1. 安装底部承重板（MDF/铝板，400×300×10mm）
2. 安装4个支撑柱（M5 螺纹杆，h=400mm）
3. 安装顶板（安装相机支架、LED 支架）

**Phase 2：入料与缓冲系统**
4. 安装入料斗（顶部，容量 ≥1kg）
5. 安装缓冲仓（8格设计，3D 打印 PETG）
6. 安装螺旋给料器（φ20mm 螺旋，28BYJ-48 驱动）

**Phase 3：分选通道**
7. 安装孔板分选机构（5级阶梯形，3D 打印 PLA）
8. 安装单文件通道管（垂直 3D 打印，内径 20mm）
9. 安装顶部相机支架（HQ Camera IMX477，M12 6mm 镜头）
10. 安装底部相机支架（USB Camera，透明亚克力窗口）

**Phase 4：传感器安装**
11. 安装光电传感器 T1/T2（红外遮断式，支架 3D 打印）
12. 安装称重传感器（HX711 + 称重杯支架）
13. 安装含水率传感器（AD7746 + 探头，<5cm 引线）
14. 安装密度传感器（涡轮鼓风机 + 气流管道）

**Phase 5：执行器安装**
15. 安装电磁阀×4（气路连接，5V 驱动）
16. 安装气喷嘴（φ2mm，位置对准通道）
17. 安装 Nema17 步进电机（孔板驱动）
18. 安装 28BYJ-48 步进电机（螺旋给料、分配器）

**Phase 6：电气安装**
19. 连接所有 GPIO 线缆（参考 WIRING_GUIDE.md）
20. 连接 I2C 总线（SDA/SCL，所有传感器菊花链）
21. 连接 SPI 总线（HX711，硬件 SPI）
22. 安装 FAIL-SAFE 安全回路（E-STOP 继电器）

### 4.2 关键注意事项

⚠️ **GPIO27 迁移提示**：HX711 SCK 从 GPIO6 → GPIO27（SPEC.md v0.8+）

⚠️ **AD7746 引线 <5cm**：超过 5cm 电缆效应导致 ±4pF 测量误差

⚠️ **透明通道窗口**：磨砂面朝上（避免粉尘落在检测面）

⚠️ **涡轮鼓风机供电**：12V 3A 独立电源，不要与 Pi 共用

---

## 5. 软件安装与配置（Day 1）

### 5.1 Pi 系统配置

```bash
# SSH 登录
ssh pi@sorter-001.local

# 配置 I2C/SPI/摄像头
sudo raspi-config
# Interface Options → I2C → Enable
# Interface Options → SPI → Enable  
# Interface Options → Camera → Enable
# Advanced → Memory Split → 256MB (GPU)

# 重启
sudo reboot
```

### 5.2 项目初始化

```bash
cd ~/sorter-project
git pull origin main

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
PYTHONPATH=. python3 -c "
from sorter.db.database import init_database
init_database()
print('Database initialized')
"

# 配置 MQTT
cp sorter/config_example.json sorter/config.json
# 编辑 config.json，填写 MQTT broker 地址、WiFi 配置等
```

### 5.3 ESP32 固件烧录

```bash
cd ~/sorter-project/firmware/sorter_esp32/
pio run --target upload --environment esp32dev

# 验证固件版本
python3 sorter/control/firmware_update_tool.py --check-version
# 预期输出：Firmware: v1.0.0 build-2026-05-03
```

### 5.4 Dashboard 启动测试

```bash
# 启动 Dashboard（模拟模式，无需硬件）
PYTHONPATH=. python3 sorter/control/dashboard.py --simulate

# 验证：应显示 GUI 窗口，状态=IDLE，传感器读数为模拟值
# 按 Ctrl+C 关闭
```

---

## 6. 传感器标定（Day 2）

> 参考：`sorter/simulation/field_calibration_toolkit.py`

### 6.1 标定顺序

| 序号 | 传感器 | 工具 | 预计时间 | 验收标准 |
|------|--------|------|---------|---------|
| 1 | Top Camera 白平衡 | 白板 | 15min | ΔR<5%, ΔG<3% |
| 2 | Bottom Camera 白平衡 | 白板 | 15min | ΔR<5%, ΔG<3% |
| 3 | 颜色 L*a*b* 阈值 | SCA 标样 | 30min | ΔE<1.5 |
| 4 | HX711 称重零点 | 空称重杯 | 10min | 读数 <0.01g |
| 5 | HX711 称重量程 | 100g砝码 | 20min | 误差 <0.05g |
| 6 | AD7746 含水率零点 | 空气基准 | 15min | C <0.5pF |
| 7 | AD7746 含水率两点标定 | 5%/15% 参考 | 30min | 误差 <0.5% |
| 8 | 密度风速标定 | 风速计 | 30min | v=4.0±0.2m/s |

### 6.2 颜色相机标定详细步骤

```
目标：建立 Ethiopian Natural 批次的颜色阈值基准
参考：sorter/camera/ANNOTATION_GUIDE.md
```

1. **预热**：LED 光源预热 30 分钟（点亮稳定）
2. **采集白板图像**：
   ```bash
   PYTHONPATH=. python3 sorter/camera/dark_box_test_protocol.py \
     --calibrate-white-balance \
     --output calibration_data/wb_$(date +%Y%m%d).json
   ```
3. **验证白平衡**：检查 R/G/B 比例，R≈G≈B（±5%）
4. **采集 SCA 标样图像**：
   ```bash
   PYTHONPATH=. python3 sorter/camera/dark_box_test_protocol.py \
     --test-color-accuracy \
     --reference-sample sorter/data/sca_reference.png \
     --threshold-output calibration_data/color_thresholds.json
   ```
5. **验证 ΔE**：ΔE < 1.5（PASS）/ ΔE 1.5-3.0（WARNING）/ ΔE > 3.0（FAIL）

### 6.3 HX711 称重标定详细步骤

```bash
# Step 1：零点标定（空称重杯）
PYTHONPATH=. python3 sorter/simulation/field_calibration_toolkit.py \
  --calibrate-loadcell \
  --mode zero \
  --output calibration_data/loadcell_zero.json

# Step 2：量程标定（100g 砝码）
PYTHONPATH=. python3 sorter/simulation/field_calibration_toolkit.py \
  --calibrate-loadcell \
  --mode span \
  --reference-weight 100.0 \
  --output calibration_data/loadcell_span.json

# Step 3：验证（10次连续读数）
# 期望：标准差 <0.01g，线性误差 <0.05g
```

### 6.4 标定记录

每次标定后保存记录：
```
calibration_data/CERT-YYYYMMDD-HHMMSS.json
```

包含字段：
- calibration_id
- timestamp
- sensor_type
- calibration_type（zero/span/two-point）
- reference_value（如适用）
- measured_value
- error
- ambient_temperature
- operator
- notes

---

## 7. 空机联调测试（Day 2）

> 参考：`sorter/simulation/physical_test_protocol.py`

### 7.1 系统上电自检（POST）

```bash
# 运行完整 POST
PYTHONPATH=. python3 sorter/control/health_monitor.py --test post

# 预期输出：
# [PASS] System基础检查      0.2ms
# [PASS] GPIO初始化          1.1ms
# [PASS] I2C设备发现          8.5ms
# [PASS] 传感器基础读数       12.3ms
# [PASS] 执行器基础响应       25.0ms
# [PASS] 通信模块（MQTT）     45.2ms
# [PASS] 存储读写              3.1ms
# [PASS] 安全回路状态         8.0ms
# [SKIP] ESP32连接            (硬件未连接)
# OVERALL: PASS ✅
```

### 7.2 执行器单独测试

```bash
# 电磁阀测试（每个阀门逐一测试）
PYTHONPATH=. python3 sorter/control/main.py test-valve --valve 1
PYTHONPATH=. python3 sorter/control/main.py test-valve --valve 2
PYTHONPATH=. python3 sorter/control/main.py test-valve --valve 3
PYTHONPATH=. python3 sorter/control/main.py test-valve --valve 4
# 预期：听到"咔嗒"声，气流通道切换

# 步进电机测试
PYTHONPATH=. python3 sorter/control/main.py test-motor --motor feeder --steps 200
PYTHONPATH=. python3 sorter/control/main.py test-motor --motor distributor --steps 36
# 预期：电机平稳转动，无异响

# 涡轮鼓风机测试
PYTHONPATH=. python3 sorter/control/main.py test-fan --speed 50
# 预期：风速 4.0±0.2m/s
```

### 7.3 空机运行测试（无豆）

```bash
# 启动系统（空跑模式）
PYTHONPATH=. python3 sorter/control/main.py start --mode empty

# 观察指标：
# - 状态机状态转换：IDLE → INITIALIZING → READY → RUNNING
# - Dashboard 传感器读数：无异常波动
# - MQTT 消息频率：心跳 1Hz
# - 运行 10 分钟，检查温升（<5°C）
```

### 7.4 端到端集成测试

```bash
# 运行完整集成测试
PYTHONPATH=. python3 sorter/simulation/end_to_end_integration_test.py

# 预期：10/13 PASS，3 WARN（MQTT/Flask/TFLite 预期警告）
```

---

## 8. 首-batch 测试运行（Day 3）

### 8.1 测试批次准备

```
测试批次规格：
- 咖啡豆：Ethiopian Yirgacheffe Natural（优质产区）
- 数量：300 粒（约 100g）
- 预期缺陷率：约 5%（含 15 粒缺陷豆）
- 预期 Grade A 率：≥85%
```

**缺陷样本注入**（可选，用于验证剔除功能）：
- 发霉豆 3 粒（表面可见蓝绿色霉斑）
- 发酵豆 3 粒（醋酸气味）
- 黑豆 3 粒（深棕色至黑色）
- 碎豆 3 粒（破碎 >50%）
- 虫蛀豆 3 粒（虫眼可见）

### 8.2 测试运行步骤

```bash
# Step 1：启动 Dashboard 监控
PYTHONPATH=. python3 sorter/control/dashboard.py --simulate

# Step 2：新终端，启动系统
PYTHONPATH=. python3 sorter/control/main.py start --batch-id TEST-001

# Step 3：加载批次配方
PYTHONPATH=. python3 sorter/production/batch_recipe_manager.py \
  --load Ethiopian_Washed

# Step 4：倒入测试咖啡豆
# 注意：分批倒入，避免堵塞（每次 ≤50g）

# Step 5：观察分选过程
# - 每粒豆经过 T1 → Top Camera → T2 → Bottom Camera → 称重 → 密度 → 水分
# - 缺陷豆在气喷区被剔除
# - 合格豆进入 Grade A/B 出口

# Step 6：记录实时指标
# Dashboard 应显示：
#   - 分选速度：≥40 bpm
#   - 实时缺陷检测：数量计数
#   - 称重读数：0.10-0.20g 范围
```

### 8.3 测试结果记录

```
测试批次：TEST-001
日期：YYYY-MM-DD HH:MM
操作员：___
豆源：Ethiopian Yirgacheffe Natural
批次量：300 粒 / 102.3g

分选结果：
- 合格出口：268 粒 / 89.3g
- 缺陷剔除：32 粒 / 6.7g
- 未分类：0 粒

Grade A：251 粒（83.7%）✅（目标 ≥85%）
Grade B：17 粒（5.7%）
缺陷：32 粒（10.7%）

分选速度：43 bpm
吞吐量：1.52 g/min = 0.09 kg/h（单通道测试模式）

异常记录：
- 无
```

### 8.4 测试结果判定

| 指标 | 目标 | 实测 | 判定 |
|------|------|------|------|
| Grade A 率 | ≥85% | 待填 | 待定 |
| 缺陷召回率 | ≥85% | 待填 | 待定 |
| 分选速度 | ≥40 bpm | 待填 | 待定 |
| 称重准确性 | ±0.05g | 待填 | 待定 |
| 含水率读数 | ±0.5% | 待填 | 待定 |
| 气喷剔除精度 | ≥90% | 待填 | 待定 |

**任一关键指标不达标** → 暂停，排查问题，重新标定

---

## 9. 首-batch 生产运行（Day 3）

### 9.1 准备正式生产批次

```
正式批次规格：
- 咖啡豆：Kenyan Kirinyaga Washed AA（高品质）
- 数量：2kg（约 6667 粒 @0.30g/粒）
- 预期缺陷率：约 2%（约 133 粒缺陷）
- 目标 Grade A 率：≥90%
```

### 9.2 生产运行步骤

```bash
# Step 1：系统完全初始化
PYTHONPATH=. python3 sorter/control/main.py reset
PYTHONPATH=. python3 sorter/control/health_monitor.py --test post
# 确认全部 PASS

# Step 2：加载 Kenya_Washed 配方
PYTHONPATH=. python3 sorter/production/batch_recipe_manager.py \
  --load Kenyan_Washed_AA

# Step 3：启动批次第 tracking
PYTHONPATH=. python3 sorter/production/batch_quality_tracker.py \
  --batch-id BATCH-001 \
  --start

# Step 4：启动生产系统
PYTHONPATH=. python3 sorter/control/main.py start \
  --batch-id BATCH-001 \
  --mode production

# Step 5：倒入咖啡豆（约 2kg，分 4 次，每次 500g）

# Step 6：实时监控
# Dashboard 监控关键指标（见下表）

# Step 7：批次完成，停止系统
PYTHONPATH=. python3 sorter/control/main.py stop

# Step 8：生成批次报告
PYTHONPATH=. python3 sorter/db/cli.py report --batch-id BATCH-001
```

### 9.3 实时监控指标（Dashboard）

| 指标 | 正常范围 | 告警阈值 |
|------|---------|---------|
| 分选速度 | 45-55 bpm | <35 bpm 或 >60 bpm |
| 实时缺陷率 | 1-5% | >8% |
| 称重均值 | 0.12-0.18g | 超出范围持续 >30s |
| 含水率均值 | 10-13% | <9% 或 >14% |
| 颜色评分 | 75-95 | <70 |
| 批次进度 | 0-100% | - |
| MQTT 连接 | Connected | Disconnected >5s |
| 温度告警 | <60°C | >60°C |

### 9.4 批次完成报告

```bash
# 导出批次报告
PYTHONPATH=. python3 sorter/db/cli.py report \
  --batch-id BATCH-001 \
  --format json \
  --output reports/BATCH-001-report.json

# 导出 CSV 明细
PYTHONPATH=. python3 sorter/db/cli.py export \
  --batch-id BATCH-001 \
  --format csv \
  --output reports/BATCH-001-beans.csv

# 查看统计
PYTHONPATH=. python3 sorter/db/cli.py stats --batch-id BATCH-001
```

---

## 10. Go-Live 判定标准

> 只有满足以下所有条件，才可判定 **Go-Live 成功**

### 10.1 硬性指标（必须全部满足）

| # | 指标 | 目标 | 测试方法 |
|---|------|------|---------|
| H1 | Grade A 率 | ≥85% | 首-batch 批次报告 |
| H2 | 缺陷召回率（Critical） | ≥90% | 人工复核剔除物 |
| H3 | 系统可用性 | ≥95% | 2h 连续运行无故障 |
| H4 | 称重精度 | ±0.05g（100g砝码） | 标定验证 |
| H5 | 含水率精度 | ±0.5%（vs 参考值） | 标定验证 |
| H6 | 颜色检测 ΔE | <1.5 | SCA 标样测试 |
| H7 | 气喷剔除精度 | ≥90% | 人工计数验证 |
| H8 | 安全回路 | 正常 | E-STOP 测试 |

### 10.2 软件指标

| # | 指标 | 目标 | 测试方法 |
|---|------|------|---------|
| S1 | Dashboard 响应 | <1s | 操作观察 |
| S2 | MQTT 消息延迟 | <100ms | 日志分析 |
| S3 | 数据库写入 | 0 丢失 | 批次完整性检查 |
| S4 | 报告生成 | <5s | CLI 计时 |
| S5 | CI 管道 | 10/10 PASS | `ci_pipeline.py` |

### 10.3 Go-Live 签署

```
╔══════════════════════════════════════════════════════╗
║           HUSKY-SORTER-001 GO-LIVE 签署                ║
╠══════════════════════════════════════════════════════╣
║ 批次编号：BATCH-001                                    ║
║ Go-Live 日期：___________                             ║
║                                                        ║
║ 技术负责人签署：____________________  日期：________  ║
║ 质量负责人签署：____________________  日期：________  ║
║ 运营负责人签署：____________________  日期：________  ║
║                                                        ║
║ 硬性指标通过：H1□ H2□ H3□ H4□ H5□ H6□ H7□ H8□       ║
║ 软件指标通过：S1□ S2□ S3□ S4□ S5□                    ║
║                                                        ║
║ 最终判定：□ GO   □ NO-GO（需整改后重新评估）          ║
╚══════════════════════════════════════════════════════╝
```

---

## 11. Go-Live 后检查清单

> Go-Live 完成后 24h 内执行

- [ ] **数据备份**
  ```bash
  # 备份数据库
  cp ~/sorter-project/sorter.db ~/sorter-project/backups/sorter-$(date +%Y%m%d).db
  
  # 备份配置
  tar czf ~/sorter-project/backups/config-$(date +%Y%m%d).tar.gz ~/sorter-project/sorter/config.json
  ```

- [ ] **系统快照**：拍摄 Dashboard 最终状态截图

- [ ] **缺陷样本保存**：Go-Live 批次剔除的缺陷样本保留 ≥7天（用于问题追溯）

- [ ] **标定证书归档**：所有标定 JSON 文件存入 `calibration_data/` 并 commit

- [ ] **更新维护日志**：记录 Go-Live 日期、首-batch 结果、发现的任何问题

- [ ] **通知干系人**：向项目组发送 Go-Live 成功通知（含关键指标截图）

- [ ] **安排 7 日复查**：预约 Go-Live 后 7 日进行一次全面复盘

---

## 12. 常见问题与应急处理

### 12.1 传感器类问题

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| 称重读数跳变 | HX711 I2C 干扰 | 检查 GPIO 27 SCK 接线；添加 100nF 去耦电容 |
| 含水率始终偏高 | AD7746 探头引线 >5cm | 更换为 <5cm 引线；使用 PIM 直连探头 |
| 相机图像偏暗 | LED 光源未预热 | 预热 30 分钟后再采集；检查 LED 供电 5V |
| 颜色 ΔE 过大 | 白平衡未校准 | 重新执行白平衡标定；检查暗箱遮光 |
| 光电传感器误触发 | 环境光干扰 | 用遮光棉包裹传感器；检查反射式 vs 遮断式 |

### 12.2 执行器类问题

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| 电磁阀不动作 | 驱动电流不足 | 测量 GPIO 输出（应 >3.3V）；检查继电器驱动 |
| 步进电机失步 | 电源电压不足 | 测量电源电压（应 ≥12V）；检查 Nema17 供电 12V |
| 涡轮鼓风机不启动 | 气路压力不足 | 确认空压机输出 ≥0.5MPa；检查电磁阀接线 |
| 气喷力度不足 | 气压 <0.5MPa | 调节空压机压力；检查气管是否弯折 |

### 12.3 软件类问题

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| Dashboard 无法启动 | 缺少依赖 | `pip install -r requirements.txt`；检查 Python 版本 ≥3.9 |
| MQTT 连接失败 | Broker 未启动 | `sudo systemctl start mosquitto`；检查端口 1883 |
| ESP32 无响应 | USB 连接松动 | 检查 Micro-USB 线；尝试重新烧录固件 |
| 批次数据丢失 | 数据库写入失败 | 检查 SD 卡空间（df -h）；更换为 SSD |
| 报告生成错误 | JSON 格式错误 | 检查 sensor_snapshot 字段；运行 `ci_pipeline.py` |

### 12.4 应急停机流程

> 任何异常情况均可触发应急停机

1. **按 E-STOP 按钮**（红色按钮，位于机台右侧）
2. **切断气源**（主气阀，位于空压机出口）
3. **关闭主电源**（机台总开关）
4. **记录故障现象**（时间、传感器读数、操作日志截图）
5. **联系技术支持**（参考 COMMISSIONING_GUIDE.md）

---

## 13. Go-Live 里程碑记录

> 本节在 Go-Live 执行过程中填写

| 里程碑 | 计划日期 | 实际日期 | 完成 | 负责人 | 备注 |
|--------|---------|---------|------|--------|------|
| 硬件开箱验货 | Day 0 | ___ | ☐ | ___ | |
| 硬件组装完成 | Day 1 | ___ | ☐ | ___ | |
| 软件安装完成 | Day 1 | ___ | ☐ | ___ | |
| ESP32 固件烧录 | Day 1 | ___ | ☐ | ___ | |
| 传感器标定完成 | Day 2 | ___ | ☐ | ___ | |
| 空机联调通过 | Day 2 | ___ | ☐ | ___ | |
| 首-batch 测试运行 | Day 3 | ___ | ☐ | ___ | |
| 首-batch 生产运行 | Day 3 | ___ | ☐ | ___ | |
| Go-Live 判定 | Day 3 | ___ | ☐ | ___ | |

---

## 附录 A：快速命令参考

```bash
# 系统启动
PYTHONPATH=. python3 sorter/control/main.py start --batch-id BATCH-001

# 系统停止
PYTHONPATH=. python3 sorter/control/main.py stop

# 紧急停机
PYTHONPATH=. python3 sorter/control/main.py estop

# 健康检查
PYTHONPATH=. python3 sorter/control/health_monitor.py --test post

# Dashboard
PYTHONPATH=. python3 sorter/control/dashboard.py --simulate

# 批次报告
PYTHONPATH=. python3 sorter/db/cli.py report --batch-id BATCH-001

# 配方加载
PYTHONPATH=. python3 sorter/production/batch_recipe_manager.py --load Ethiopian_Washed

# CI 验证
PYTHONPATH=. python3 sorter/tests/ci_pipeline.py
```

---

## 附录 B：关键文件路径

```
sorter-project/
├── sorter/
│   ├── control/
│   │   ├── main.py              # 主控制系统
│   │   ├── dashboard.py        # 监控界面
│   │   ├── health_monitor.py   # 健康监控
│   │   └── firmware_update_tool.py
│   ├── camera/
│   │   ├── dark_box_test_protocol.py  # 相机标定协议
│   │   └── ml_pipeline.py      # ML 推理管道
│   ├── sensors/
│   │   ├── load_cell.py         # 称重传感器
│   │   └── moisture.py          # 含水率传感器
│   ├── production/
│   │   ├── batch_quality_tracker.py   # 批次质量追踪
││   ├── db/
│   │   ├── database.py          # 数据库
│   │   └── cli.py               # 数据库 CLI
│   ├── simulation/
│   │   ├── field_calibration_toolkit.py  # 标定工具
│   │   ├── end_to_end_integration_test.py # 集成测试
│   │   └── production_scheduler.py        # 生产调度
├── sorter/
│   └── config.json              # 系统配置（勿提交）
├── calibration_data/            # 标定证书目录
├── reports/                     # 批次报告目录
└── docs/
    ├── COMMISSIONING_GUIDE.md   # 调试指南
    ├── OPERATOR_MANUAL.md       # 操作员手册
    ├── WIRING_GUIDE.md          # 接线指南
    ├── SITE_PREP.md             # 场地准备
    └── MAINTENANCE_GUIDE.md     # 维护保养
```

---

## 附录 C：关键联系人

| 角色 | 职责 | 联系方式 |
|------|------|---------|
| 项目经理 | 整体协调 | ___ |
| 电气工程师 | GPIO/传感器问题 | ___ |
| 机械工程师 | 3D 打印件/组装问题 | ___ |
| 软件工程师 | Pi/ESP32/ML 问题 | ___ |
| 咖啡质量顾问 | 缺陷判定/SCA 标准 | ___ |

---

## 附录 D：修订历史

| 版本 | 日期 | 修订内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-05-15 | 初始版本 | Little Husky (AI) |

---

*本文档为 HUSKY-SORTER-001 项目的一部分。*
*项目代码：https://github.com/QuantumCheuk/sorter-project*
