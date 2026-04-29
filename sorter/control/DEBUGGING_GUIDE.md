# HUSKY-SORTER-001 调试指南 / Debugging Guide

> 版本：v1.0 | 2026-04-29  
> 适用阶段：硬件组装 → 首次通电 → 正常运行

---

## 🚦 首次通电检查序列

### Day 0：视觉检查（上电前）

```
□ 全部接线与 WIRING_GUIDE.md 逐一核对
□ 没有电线裸露/破皮
□ 没有金属物品掉在Pi上
□ 12V/5V/3.3V 没有混接
□ 继电器板指示灯状态确认
□ 3D打印件安装牢固，无松动
□ 压缩空气管路连接正确（无泄漏）
```

### 通电后 30 秒观察

```
□ 绿灯：Pi 电源指示灯亮
□ 红灯：Pi ACT 闪烁 → Linux 启动中
□ 绿灯：USB 摄像头指示灯亮
□ 风扇：12V风扇转动（转速正常）
□ 无火花/无焦味/无异常发热
□ 闻到烧焦味 → 立即断电！
```

---

## 🔬 模块级调试

### 1. 称重系统（HX711）

**症状：无读数 / 读数跳变**

```bash
# 基础测试
cd sorter-project
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN)  # DT
GPIO.setup(27, GPIO.OUT) # SCK

# 手动发SCK脉冲
for i in range(25):
    GPIO.output(27, 1)
    time.sleep(0.0001)
    GPIO.output(27, 0)
    time.sleep(0.0001)

print('DT after 25 pulses:', GPIO.input(17))
GPIO.cleanup()
"

# 使用 hx711py 库
python3 -c "
from sensors.hx711 import HX711
hx = HX711(dout=17, pd_sck=27)
hx.set_scale(1)
hx.tare(10)
print('Weight:', hx.get_weight(5), 'g')
"

# 常见问题：
# 1. 读数跳变 → 检查GPIO接线（DT/S CK是否正确）
# 2. 一直0 → 检查HX711是否上电（万用表测VCC应为5V）
# 3. 漂移 → 预热10分钟再tare
```

**标定流程：**
```bash
python3 sorter/sensors/hx711.py --calibrate
# 1. 放空杯，读稳定值 → ENTER（零点）
# 2. 放100g砝码，读稳定值 → ENTER（量程）
# 3. 标定因子写入 config.json
```

### 2. 颜色检测（双摄像头）

**症状：Top Camera 无图像**

```bash
# 检查摄像头已启用
vcgencmd get_camera

# 测试 raspistill（单张拍摄）
raspistill -o test_top.jpg -t 1000

# 测试 picamera2（Python）
python3 -c "
from picamera2 import Picamera2
picam2 = Picamera2()
picam2.configure(picam2.create_preview_config())
picam2.start()
import time; time.sleep(2)
picam2.capture_file('test_top.jpg')
picam2.close()
print('OK')
"

# 焦距调整
# 如果图像模糊：
# 1. 拧松镜头固定环
# 2. 对准白色参考卡（ISO 400 白板）
# 3. 旋转镜头直到清晰
# 4. 拧紧固定环
```

**症状：Bottom Camera USB 无响应**

```bash
# 检查USB设备
ls /dev/video*
# 期望：/dev/video0, /dev/video1

# 测试OpenCV读取
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print('OK' if ret else 'FAIL')
cap.release()
"

# 如FAIL：检查USB摄像头是否被其他进程占用
# ps aux | grep video
```

**颜色阈值验证：**
```bash
# 使用暗箱测试协议
python3 sorter/camera/dark_box_test_protocol.py --mode top
# 期望 L* ∈ [40, 60]（正常豆），L* < 30（发黑豆）

python3 sorter/camera/dark_box_test_protocol.py --mode bottom
# 期望 底部亮度比顶部低5-10%（透射效果正常）
```

### 3. 含水率检测（AD7746）

**症状：I2C找不到设备**

```bash
# I2C设备扫描
sudo i2cdetect -y 1
# 期望看到 48（0x48 = AD7746）
# 如果显示 "--" → 设备未识别

# 常见原因：
# 1. SDA/SCL接反 → 交换接线
# 2. 未启用I2C → 运行 sudo raspi-config → Interface → I2C → Enable
# 3. AD7746模块损坏 → 换一个新模块测试

# I2C地址确认（AD7746 = 0x48）
i2cdetect -y 1 | grep "48"
# 应显示 "48"

# 测试寄存器读
python3 -c "
import smbus2
bus = smbus2.SMBus(1)
# 读AD7746 ID寄存器（0x0F）
id_reg = bus.read_word_data(0x48, 0x0F)
print('AD7746 ID:', hex(id_reg))
# 期望：0x4D 或类似值
bus.close()
"

# 引线过长测试（诊断电缆效应）
# 用数字万用表测量探头电容（目标：4-20pF）
# AD7746内部基准电容：10pF ±10%
# 如果引线 > 10cm，误差将超过 ±5%
```

**症状：读数一直不变 / 完全错误**

```python
# 可能原因：探头未连接 / 线缆断裂
# 诊断：
python3 -c "
from sensors.moisture import MoistureSensor
sensor = MoistureSensor()
print('Raw capacitance:', sensor.read_raw())
print('Moisture %:', sensor.read_moisture())
# 如果读数固定不变（如一直是2048）→ 探头未连接
# 如果读数 > 30000 → SDA/SCL短路或I2C错误
"
```

### 4. 电机控制

**症状：振动给料器不转 / 乱转**

```bash
# 28BYJ-48 单步测试
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)

PUL = 5
DIR = 12
GPIO.setup(PUL, GPIO.OUT)
GPIO.setup(DIR, GPIO.OUT)

# DIR方向测试
GPIO.output(DIR, 0)  # 方向A
print('DIR=0: 顺时针')

# 发送10个脉冲，观察电机
for i in range(10):
    GPIO.output(PUL, 1)
    time.sleep(0.001)
    GPIO.output(PUL, 0)
    time.sleep(0.001)

time.sleep(0.5)
GPIO.output(DIR, 1)  # 方向B
print('DIR=1: 逆时针')
for i in range(10):
    GPIO.output(PUL, 1)
    time.sleep(0.001)
    GPIO.output(PUL, 0)
    time.sleep(0.001)

GPIO.cleanup()
"

# 如果电机乱转（抖动）：
# → DIR/PUL接线反了，交换
# → 脉冲宽度太短，增加到 1ms
# → 电源功率不足，5V 2A以上

# 如果电机嗡嗡响但不转：
# → 线圈顺序错误，检查 IN1/IN2/IN3/IN4 接线
# → 28BYJ-48 固有半步模式，正常（不是故障）
```

**速度验证（与设计目标对比）：**

| 配置 | 目标频率 | 实际频率 | 转速 |
|------|---------|---------|------|
| 28BYJ-4步模式 | 500Hz | ? Hz | 28bpm |
| 28BYJ-8步模式 | 500Hz | ? Hz | 14bpm |
| **Nema17 + A4988** | **2kHz** | ? Hz | **50bpm** |

```bash
# 验证频率
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(5, GPIO.OUT)
freq = 2000  # 2kHz for 50bpm target

# 测量实际频率
start = time.time()
for i in range(1000):
    GPIO.output(5, 1)
    GPIO.output(5, 0)
elapsed = time.time() - start
actual_freq = 1000 / elapsed
print(f'Actual frequency: {actual_freq:.0f}Hz (target: {freq}Hz)')
print(f'Speed ratio: {actual_freq/freq*100:.1f}%')
GPIO.cleanup()
"
```

### 5. 气喷剔除系统

**症状：电磁阀不动作**

```bash
# 中间继电器测试（用LED代替电磁阀先测试）
python3 -c "
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT)  # 电磁阀1控制

# 测试脉冲（50ms喷射）
GPIO.output(26, 1)
import time; time.sleep(0.05)
GPIO.output(26, 0)
print('Pulse sent - check relay click')
GPIO.cleanup()
"

# 如果继电器不响：
# 1. 测继电器VCC=5V是否到位
# 2. 测GPIO26输出电压（有负载时约3.3V）

# 如果继电器响但电磁阀不动：
# → 电磁阀坏或12V电源未连接
# → 用万用表测电磁阀线圈电阻（正常约30-60Ω）
```

**气压校准：**
```bash
# 气压表读数应在 100-150kPa
# 如果气压不够（喷射无力）：
# → 检查空压机压力（目标 > 150kPa）
# → 检查气管直径（PK-4 = 4mm内径，最小要求）
# → 检查气管长度（越长压力损失越大，< 2m）
```

### 6. MQTT 通信

```bash
# 测试MQTT broker
mosquitto -d  # 启动守护进程
ps aux | grep mosquitto  # 确认运行

# 测试本地发布/订阅
mosquitto_pub -t sorter/test -m "hello" &
mosquitto_sub -t sorter/test -C 1
# 期望看到 "hello"

# Python MQTT测试
python3 -c "
import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc):
    print('Connected:', rc)
    client.subscribe('sorter/#')

def on_message(client, userdata, msg):
    print(msg.topic, msg.payload)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect('localhost', 1883, 60)
client.loop_start()
import time; time.sleep(2)
client.publish('sorter/test', 'ping')
time.sleep(1)
client.loop_stop()
"
```

### 7. REST API

```bash
# 启动Flask服务
python3 sorter/api/app.py &
# 或用 dashboard.py 内置API

# 测试端点
curl http://localhost:5000/api/status
curl http://localhost:5000/api/config
curl -X POST http://localhost:5000/api/batch/start \
  -H "Content-Type: application/json" \
  -d '{"target_weight_g": 250}'

# 验证JSON格式
curl http://localhost:5000/api/status | python3 -m json.tool
```

---

## 📊 性能基准测试

### 颜色检测延迟（目标 < 25ms）

```python
import time
import cv2
from picamera2 import Picamera2

picam2 = Picamera2()
picam2.configure(picam2.create_preview_config())
picam2.start()

times = []
for _ in range(100):
    start = time.time()
    frame = picam2.capture_array()
    # OpenCV处理（参考实现）
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    elapsed = time.time() - start
    times.append(elapsed * 1000)

avg_ms = sum(times) / len(times)
p95_ms = sorted(times)[94]
print(f"Avg: {avg_ms:.1f}ms, P95: {p95_ms:.1f}ms")
print("PASS" if avg_ms < 25 else "FAIL - 需优化或降分辨率")
```

### 端到端时序（目标 < 200ms/粒）

```python
# 参考: sorter/simulation/bean_timing_sequence_analysis.py
# 使用 BeanSimulator 测试
python3 -c "
from sorter.control.main import BeanSimulator
sim = BeanSimulator(mode='simulation', rate=50)  # 50bpm
sim.start()
import time; time.sleep(5)
stats = sim.get_stats()
print(f'Processed: {stats[\"total\"]}')
print(f'Avg latency: {stats.get(\"avg_latency_ms\", \"N/A\")}ms')
sim.stop()
"
```

---

## 🆘 故障代码速查

| 错误代码 | 含义 | 解决方法 |
|---------|------|---------|
| E001 | HX711 无信号 | 查GPIO17/27接线，测5V供电 |
| E002 | AD7746 I2C失败 | i2cdetect确认0x48存在 |
| E003 | 相机初始化失败 | vcgencmd get_camera，reboot |
| E004 | MQTT连接失败 | 检查mosquitto是否运行 |
| E005 | 称重超量程 | 豆重>200g或传感器损坏 |
| E006 | 通道堵塞 | 检查3D打印件，清除卡豆 |
| E007 | 电机失步 | 检查给料器机械阻力，减小负荷 |
| E008 | 气压不足 | 检查空压机，清理气管 |
| E009 | 温度过高 | 停机5分钟，检查散热 |
| E010 | ESP32 UART超时 | 查GPIO0/1接线，波特率115200 |

---

## 🛠️ 调试工具推荐

| 工具 | 用途 | 成本 |
|------|------|------|
| 万用表 | 电压/通断测试 | ¥100 |
| 逻辑分析仪（24MHz） | GPIO时序分析 | ¥80 |
| 示波器（50MHz） | 信号完整性 | ¥500 |
| 热成像仪（手机配件） | 热点检测 | ¥300 |
| 体重秤（0.01g精度） | 豆重标定 | ¥150 |

---

*调试完成后，运行 `python3 sorter/simulation/physical_test_protocol.py` 执行完整物理测试。*
