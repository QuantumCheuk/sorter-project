# HUSKY-SORTER-001 接线指南 / Wiring Guide

> 版本：v1.0 | 2026-04-29  
> 对应SPEC：v0.8 第9节GPIO定义  
> 适用：Raspberry Pi 4B + ESP32 DevKit

---

## 🗺️ GPIO总图

```
        ┌─────────────────────────────────────────────────────┐
        │              Raspberry Pi 4B GPIO                  │
        │                                                     │
        │  3.3V ●───● 5V        ●─── 5V                     │
        │  GPIO 2 ●─── 5V        ●─── GND                   │
        │  GPIO 3 ●─── 5V        ●─── GPIO 17 ←─── HX711 SCK│
        │      GND ●─── GPIO 27 ←─── HX711 SCK              │
        │  GPIO 4 ●─── (NC)      ●─── GND                   │
        │  GPIO 14│              │─── GPIO 15               │
        │      GND│              │─── (NC)                  │
        │  GPIO18│              │─── GPIO 21 (I2C SDA) ──┐ │
        │  GPIO23│              │─── GND                  │ │
        │      3.3V│            │─── GPIO 22              │ │
        │ GPIO24│  UART TX      │─── (NC)                 │ │
        │      GND│              │─── (NC)                │ │
        │  GPIO10│              │─── (NC)                 │ │
        │      GND│              │─── (NC)                 │ │
        │  GPIO9 │─── SPI MOSI  │─── (NC)                   │
        │  GPIO11 │─── SPI SCLK  │─── (NC)                   │
        │  ───────┼──────────────┼─────────────────────────│
        │  GPIO 0 │─── I2C SDA ──┼─────────────────────── ESP32 TX
        │  GPIO 1 │─── I2C SCL ──┴─────────────────────── ESP32 RX
        │  GPIO 5 │─── 振动给料 PUL  │─── GPIO 6  │
        │  GPIO 12│─── 振动给料 DIR  │─── GND     │
        │  GPIO 13│─── 分配器 PUL    │─── GPIO 19 │
        │  GPIO 16│─── 分配器 DIR    │─── GPIO 20 │
        │  GPIO 26│─── 电磁阀 AIRJET1│─── GPIO 21 │
        │  GPIO 27│─── HX711 SCK ←───────────── (已迁移！) │
        │  GPIO 25│─── 称重释放电磁阀 │─── GPIO 24│
        │      GND│─── 公共地        │─── GPIO 23│
        │  ID_SD  │─── (NC用于GPIO) │─── GPIO 22 │
        │  ID_SC  │─── (NC用于GPIO) │─── (NC)   │
        │  GPIO 6 │─── SPI CE0     │─── GPIO 12 │
        │  GPIO 13│─── SPI CE1     │─── GPIO 16 │
        │      GND│                 │─── GPIO 20 │
        │  GPIO 19│─── SPI MISO   │─── GPIO 21 │
        │  GPIO 18│─── 预留       │─── GPIO 19 │
        └─────────────────────────────────────────────────────┘
```

---

## ⚠️ 关键设计决策（v0.8）

### GPIO27 迁移（HX711 SCK）
> ⚠️ **2026-04-26变更：** HX711 SCK 从 GPIO6 迁移至 **GPIO27**  
> 原因：GPIO6 被 SPI CE0 占用，与 HC-SR501 PIR传感器冲突  
> **确认你的SPEC.md版本 ≥ v0.6**

---

## 🔌 详细接线表

### 电源系统

| 用途 | 规格 | Pi引脚 | 备注 |
|------|------|--------|------|
| 主电源 | 5V 3A | Pin 2 (5V) | USB-C输入 |
| 逻辑电 | 3.3V | Pin 1 (3.3V) | 传感器供电 |
| 公共地 | GND | Pin 6, 9, 14, 20, 25, 30, 34, 39 | 共地连接 |
| 12V电源 | DC 12V | 外部适配器 | 电磁阀/电机 |

### 称重系统（HX711）

| HX711模块 | Pi GPIO | 引脚号 | 线色（典型） |
|-----------|---------|--------|-------------|
| VCC | 5V | Pin 2 | 红 |
| GND | GND | Pin 9 | 黑 |
| DT (DATA) | GPIO 17 | Pin 11 | 白 |
| SCK | **GPIO 27** | Pin 13 | 绿 |
| ADJ | 空 | — | — |

> ⚠️ HX711 DATA接GPIO17，**SCK必须接GPIO27**（不是GPIO6！）

### 颜色检测（双摄像头）

**Top Camera — HQ Camera IMX477**
| 功能 | 连接方式 |
|------|---------|
| 图像数据 | MIPI CSI-2 排线（15pin） |
| 控制 | I2C总线自动识别 |
| 镜头 | M12 6mm，所有参数通过raspi-config启用 |
| 安装方向 | 镜头朝下，对准通道管 |

**Bottom Camera — USB Camera C270**
| 功能 | Pi连接 |
|------|--------|
| 图像数据 | USB 2.0端口 |
| 控制 | USB HID自动识别 |
| 安装方向 | 镜头朝上，透过磨砂亚克力拍摄 |

**光电传感器 T1/T2（遮挡式红外）**
| 传感器 | Pi连接 | 引脚 |
|--------|--------|------|
| T1 VCC | 3.3V | Pin 1 |
| T1 GND | GND | Pin 9 |
| T1 OUT (信号) | GPIO 4 | Pin 7 |

| 传感器 | Pi连接 | 引脚 |
|--------|--------|------|
| T2 VCC | 3.3V | Pin 1 |
| T2 GND | GND | Pin 14 |
| T2 OUT (信号) | GPIO 22 | Pin 15 |

> ⚠️ 使用3.3V（NPN型），**不要**接5V（会损坏GPIO）

### 电机驱动

**振动给料器 — 28BYJ-48 + ULN2003/DRV8833**

| 驱动板 | Pi GPIO | 引脚 |
|--------|---------|------|
| IN1 (蓝) | GPIO 5 (PUL) | Pin 29 |
| IN2 (粉) | GPIO 6 (DIR) | Pin 31 |
| IN3 (黄) | GPIO 12 | Pin 32 |
| IN4 (橙) | GPIO 13 | Pin 33 |
| VCC | 5V | Pin 2 |
| GND | GND | Pin 6 |

**旋转分配器 — 28BYJ-48 + ULN2003/DRV8833**

| 驱动板 | Pi GPIO | 引脚 |
|--------|---------|------|
| IN1 | GPIO 19 | Pin 35 |
| IN2 | GPIO GPIO 16 | Pin 36 |
| IN3 | GPIO 20 | Pin 38 |
| IN4 | GPIO 21 | Pin 40 |
| VCC | 5V | Pin 4 |
| GND | GND | Pin 14 |

**称重释放电磁阀（12V NC）**
| 用途 | Pi GPIO | 引脚 |
|------|---------|------|
| 电磁阀+ | 12V外部电源 | — |
| 电磁阀- | 中间继电器COM | — |
| 继电器信号 | GPIO 25 | Pin 22 |
| 继电器VCC | 5V | Pin 4 |

### 气喷剔除系统

**12V 2-way NC电磁阀（×3）**

| 用途 | GPIO | 引脚 | 说明 |
|------|------|------|------|
| 电磁阀1（合格剔除） | GPIO 26 | Pin 37 | 气喷嘴1 |
| 电磁阀2（缺陷剔除） | GPIO 24 | Pin 18 | 气喷嘴2 |
| 电磁阀3（预留） | GPIO 23 | Pin 16 | 备用 |
| VCC（所有电磁阀） | 12V | 外部 | 共电源正 |

> ⚠️ 电磁阀需要**中间继电器**（5V触发12V），不要直连GPIO！

### 含水率检测（AD7746 I2C）

| AD7746模块 | Pi连接 | 说明 |
|-----------|--------|------|
| VDD | 3.3V | Pin 1 |
| GND | GND | Pin 9 |
| SDA | GPIO 0 (I2C SDA) | Pin 27 |
| SCL | GPIO 1 (I2C SCL) | Pin 28 |
| NC/浮空 | — | 保持悬空 |

> ⚠️ **关键：** AD7746至探头引线必须 **<5cm**（超过会产生寄生电容误差）

### ESP32 通信（UART）

| ESP32 | Pi连接 | 说明 |
|-------|--------|------|
| TX | GPIO 0 (I2C SDA) | Pi接收ESP32数据 |
| RX | GPIO 1 (I2C SCL) | Pi发送ESP32命令 |
| GND | GND | Pin 6 |
| EN | 3.3V（保持使能） | — |

> ⚠️ **GPIO 0/1 是I2C总线，同时也是UART与ESP32通信！不可用于其他I2C设备同时共存**

### I2C设备地址速查

| 设备 | I2C地址 | 总线 | 备注 |
|------|---------|------|------|
| AD7746 | 0x48 | /dev/i2c-1 | 含水率 |
| HX711 | GPIO (非I2C) | — | 专用GPIO |
| 备用I2C接口 | 0x? | /dev/i2c-1 | 扩展用 |

---

## 🔧 接线质量检查清单

### 通电前必查（每次重新接线后）

- [ ] **GPIO27 = HX711 SCK**（已从GPIO6迁移！验证：grep GPIO27 /boot/config.txt）
- [ ] 所有5V传感器确认使用3.3V（NPN型不要接5V）
- [ ] 电磁阀不直连GPIO，通过继电器
- [ ] 共地用粗线（AWG22或更粗）
- [ ] AD7746引线 <5cm（量一下！）
- [ ] 12V电源单独，5V/3.3V走Pi供电
- [ ] CSI排线扣紧（HQ Camera）

### 通电后验证命令

```bash
# I2C设备发现
sudo i2cdetect -y 1
# 期望：48（AD7746）出现

# GPIO测试（以HX711为例）
python3 -c "
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(27, GPIO.OUT)
GPIO.output(27, GPIO.HIGH)
print('GPIO27 HIGH')
GPIO.output(27, GPIO.LOW)
print('GPIO27 LOW')
GPIO.cleanup()
"

# 检查HC-SR04超声波（如有）
# 示波器或逻辑分析仪测GPIO响应时间 < 100μs
```

---

## 🎨 线缆标签建议

每根GPIO线缆两端贴标签：

```
格式：[功能]-[方向]
示例：
  HX711-DT-IN   (GPIO 17)
  HX711-SCK-OUT (GPIO 27)
  T1-SIG-IN     (GPIO 4)
  VALVE-AIRJET1 (GPIO 26)
  MOTOR-FEEDER-DIR (GPIO 12)
```

推荐标签机型号：Brother P-Touch PT-D210（约¥150）

---

## 🆘 常见接线错误

| 症状 | 可能原因 | 解决方法 |
|------|---------|---------|
| I2C设备全不见 | SDA/SCL接反了 | 交换SDA/SCL |
| HX711读数跳变 | SCK接在GPIO6而非27 | 迁移到GPIO27 |
| 电磁阀不动作 | 没接继电器，直连GPIO | GPIO无法驱动12V电磁阀 |
| 摄像头无图像 | CSI排线扣松了 | 重新扣紧两端 |
| AD7746含水率读数飘 | 引线太长（>5cm） | 缩短到<5cm |
| 电机乱转 | DIR/PUL反了 | 交换DIR接线 |
| GPIO损坏 | 5V直连GPIO | 永远不要！ |

---

*接线图基于 Raspberry Pi 4B GPIO Header (40-pin)。如有疑问，以实物万用表测量为准。*
