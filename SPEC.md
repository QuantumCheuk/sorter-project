# 生豆分选机 / Green Coffee Bean Sorter
> 项目代号：HUSKY-SORTER-001  
> 版本：v0.1 | 2026-04-10  
> 目标：全指标分选（大小/颜色/重量/密度/含水率）+ 分类标签 + 数据输出 + 分批喂入烘豆机

---

## 1. 设计背景

HUSKY-SORTER-001 是数字化干燥链（DDC）的最上游节点，负责：

1. **全维度分选**：大小、颜色、重量、密度、含水率
2. **分类标注**：产区、豆种、处理法、批次等元数据
3. **数据输出**：每批次完整测量数据 → 烘豆机 `/batch/start` 接口
4. **分批喂入**：按设定重量分批输出，对接烘豆机进豆阀

**对标产能：** ≥ HUSKY-ROASTER-001 的处理量（250g/批次，实际运行~8-10批次/小时）  
→ 目标处理量：**≥ 2kg/小时**

---

## 2. 分选指标与技术方案

### 2.1 尺寸分选（Size Sorting）

| 项目 | 说明 |
|------|------|
| 原理 | 振动给料 + 阶梯形孔板（3D打印PLA/PETG） |
| 规格 | 5级目数：16目/15目/14目/13目/12目（对应约1.18-1.70mm） |
| 实现 | 步进电机驱动振动 bowl feeder，旋转到对应孔位 |
| 材质 | 3D打印（PLA+最高精度，层厚0.12mm）或激光切割PMMA |
| 备注 | 尺寸直接反映豆子成熟度，过大/过小影响烘焙曲线 |

### 2.2 颜色分选（Color Sorting）

| 项目 | 说明 |
|------|------|
| 原理 | Raspberry Pi HQ Camera + 图像处理 + ML分类模型 |
| 规格 | 分辨率 4056×3040（1200万像素），镜头 M12 6mm |
| 算法 | 颜色直方图 + SVM/MLP分类（按烘焙度/品种/缺陷） |
| 光源 | 4× LED 环形灯，漫反射箱（3D打印白PLA） |
| 检测指标 | L*a*b* 色彩空间、亮度均匀度、斑点检测 |
| 分类 | 正常豆 / 漂白豆 / 发霉豆 / 发酵过度 / 破碎豆 |
| 用途 | 剔除缺陷豆，辅助判断品种和处理法 |

### 2.3 重量分选（Weight Sorting）

| 项目 | 说明 |
|------|------|
| 原理 | 静态称重（单点 Load Cell）+ 积分计算 |
| 规格 | Load Cell 50g~200g，精度 0.01g，HX711 AD模块 |
| 实现 | 豆子落杯 → 称重 → 记录单粒重量 → 统计分布 |
| 输出 | 平均重、单粒重分布直方图、异常值标记 |
| 用途 | 密度计算辅助、烘焙曲线参考 |

### 2.4 密度分选（Density Sorting）

| 项目 | 说明 |
|------|------|
| 原理 | 气流上扬法（Air Lift）— 轻豆被气流吹起，重豆下落 |
| 实现 | 可调风扇（ PWM 调速）+ 3D打印气流通道 |
| 分级 | 3级密度：轻（<0.60）、中（0.60-0.72）、重（>0.72）g/mL |
| 用途 | 低密度豆水分低/成熟度差，单独处理或标记 |

### 2.5 含水率检测（Moisture Sensing）

| 项目 | 说明 |
|------|------|
| 原理 | 电容式含水率传感器（自制分离式平板电容探头） |
| 规格 | 测量范围 5%-30%，精度 ±0.5% |
| 实现 | 豆子落入测量槽 → 两极板间电容变化 → AD转换 |
| 标定 | 用已知含水率样本（烘干法）标定曲线 |
| 输出 | 含水率%、干燥度评级（A/B/C） |

---

## 3. 分类标注系统

### 3.1 元数据标签（手动输入 / 扫码）

| 字段 | 类型 | 说明 |
|------|------|------|
| `origin_country` | string | 产国 |
| `origin_region` | string | 产区/农场 |
| `variety` | string | 豆种（Arabica/Robusta/Heirloom/...） |
| `process` | string | 处理法（水洗/日晒/蜜处理/...） |
| `harvest_year` | int | 收获年份 |
| `grade` | string | 等级（G1/G2/...） |
| `batch_code` | string | 批次码（人工输入或扫码） |
| `supplier` | string | 供应商 |

### 3.2 自动检测输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `size_avg` | float | 平均粒径（目数） |
| `weight_avg_g` | float | 平均单粒重（g） |
| `density_class` | string | 密度等级（light/medium/heavy） |
| `moisture_pct` | float | 含水率% |
| `color_score` | float | 颜色评分（0-100） |
| `defect_count` | int | 缺陷豆检测数 |
| `defect_rate_pct` | float | 缺陷率%（已剔除） |
| `quality_class` | string | 综合品质分级（A/B/C） |

---

## 4. 机械结构

### 4.1 整体布局（垂直叠放，节省面积）

```
  [入料斗 Hoppers]           ← 人工倒豆，容量约500g
       ↓
  [振动给料器]                 ← 步进电机驱动，均匀下料
       ↓
  [尺寸分选台]                ← 5级阶梯孔板，3D打印
       ↓
  [颜色检测室]                ← 密闭暗箱 + HQ摄像头
       ↓
  [称重杯]                    ← Load Cell 称重
       ↓
  [密度分选区]                ← 气流上扬分离
       ↓
  [含水率测量槽]              ← 电容探头
       ↓
  [缓冲料仓（按等级分格）]    ← 8格，每格约50g容量
       ↓
  [出豆口 → 烘豆机进豆阀]     ← 气动阀 + 螺旋给料
```

**占地面积：** 250×200mm（相当于一张A4纸）  
**总高度：** ~400mm（3D打印框架逐层叠加）

### 4.2 3D打印件清单

| 零件 | 数量 | 材料 | 说明 |
|------|------|------|------|
| 入料斗 | 1 | PETG | 漏斗形，500g容量 |
| 振动给料器基座 | 1 | PLA | 弹簧支撑 + 电磁铁 |
| 尺寸分选孔板 | 5 | PETG/PMMA | 激光切割优先，精度更高 |
| 颜色检测暗箱 | 1 | PLA（白内壁） | 漫反射，LED环形灯 |
| 称重杯托 | 1 | PLA | Load Cell安装基座 |
| 气流分选通道 | 1 | PETG | 气流上扬分离室 |
| 含水率测量槽 | 1 | PLA | 平行板电容夹具 |
| 缓冲料仓 | 1 | PETG | 8格分配器 |
| 出豆螺旋给料 | 1 | PLA | 步进电机驱动 |
| 框架立柱×4 | 4 | PLA | 2020铝型材或M5螺纹杆 |
| 框架连接件 | 若干 | PLA | 框架组装用 |

### 4.3 非3D打印件（外购）

| 零件 | 规格 | 数量 | 用途 |
|------|------|------|------|
| Raspberry Pi 4B | 2GB+ | 1 | 主控 + 图像处理 |
| ESP32 | DevKit | 1 | 传感器控制 + 通信 |
| HQ Camera | IMX477 | 1 | 颜色/缺陷检测 |
| M12 镜头 | 6mm | 1 | 配合HQ Camera |
| LED 环形灯 | 5V USB | 4 | 颜色检测光源 |
| Load Cell | 200g | 1 | 称重 |
| HX711 模块 | - | 1 | AD转换 |
| 42步进电机 | 28BYJ-48 | 3 | 振动给料/螺旋给料/旋转分选 |
| 风扇 | 5015 5V | 1 | 气流上扬密度分选 |
| 薄膜电容 | 100pF级 | 2 | 含水率传感器 |
| 气管/快插接头 | PK-4/M5 | 若干 | 气动系统 |
| 电磁阀 | 12V 2WAY | 1 | 出豆口控制 |

---

## 5. 电气与控制

### 5.1 系统架构

```
[感知层]
  ├── HQ Camera (I2C/SPI)
  ├── Load Cell + HX711 (GPIO)
  ├── 电容式水分探头 (GPIO/ADC)
  ├── 步进电机×3 (GPIO via ULN2003)
  ├── 气流风扇 PWM (GPIO)
  └── 电磁阀 (GPIO)

[主控层]
  ├── Raspberry Pi 4B (Python + OpenCV + ML)
  │     ├── 图像处理 (颜色/缺陷检测)
  │     ├── 数据整合 (重量/尺寸/密度/水分)
  │     ├── MQTT Client (to Roaster)
  │     └── REST API (参数配置/状态查询)
  └── ESP32 (Arduino C)
        ├── 传感器驱动
        ├── 步进电机脉冲生成
        └── 设备级Modbus/串口 → Pi

[通信层]
  ├── 内部：UART (Pi ↔ ESP32)
  ├── 上行：MQTT → HUSKY-ROASTER-001
  └── 人机：触控屏 (可选) 或 Web UI
```

### 5.2 MQTT 消息格式（输出到烘豆机）

**主题：** `sorter/{device_id}/batch/output`

```json
{
  "message_type": "BATCH_READY",
  "batch_id": "LOT-2026-0410-A",
  "timestamp": "2026-04-10T14:50:00+08:00",
  "source": "sorter-01",

  "metadata": {
    "origin_country": "埃塞俄比亚",
    "origin_region": "耶加雪菲·Aricha",
    "variety": "Heirloom",
    "process": "水洗",
    "harvest_year": 2025,
    "grade": "G1",
    "batch_code": "ARI-2025-W-001"
  },

  "measurements": {
    "size_avg": 17.2,
    "weight_avg_g": 0.152,
    "density_class": "medium",
    "moisture_pct": 11.4,
    "color_score": 92,
    "defect_count": 1,
    "defect_rate_pct": 0.4
  },

  "quality_class": "A",

  "feed_plan": [
    {"portion_kg": 0.250, "feed_sequence": 1},
    {"portion_kg": 0.250, "feed_sequence": 2},
    {"portion_kg": 0.250, "feed_sequence": 3}
  ],

  "total_weight_kg": 0.750,
  "portion_count": 3,
  "recommended_profile": "light-ethiopia-01",
  "roast_level_target": "Light",
  "notes": "果香突出，酸质明亮"
}
```

**出豆控制消息（to Roaster）：**

**主题：** `roaster/{device_id}/batch/input`

```json
{
  "message_type": "BATCH_START",
  "batch_id": "LOT-2026-0410-A-1",
  "timestamp": "2026-04-10T14:55:00+08:00",
  "source": "sorter-01",

  "green_beans": {
    "origin": {
      "country": "埃塞俄比亚",
      "region": "耶加雪菲·Aricha"
    },
    "variety": "Heirloom",
    "process": "水洗",
    "harvest_year": 2025,
    "grade": "G1"
  },

  "quality_class": "A",
  "moisture_pct": 11.4,
  "bulk_density": 0.65,
  "avg_size": 17.2,
  "weight_kg": 0.250,

  "recommended_profile": "light-ethiopia-01",
  "roast_level_target": "Light"
}
```

---

## 6. 软件架构

### 6.1 树莓派端（Python）

```
sorter/
├── main.py                 # 主程序入口
├── config.py               # 参数配置
├── camera/
│   ├── capture.py          # 图像采集
│   ├── color_analyzer.py   # 颜色分析 (L*a*b*)
│   └── defect_detector.py  # 缺陷检测 (ML)
├── sensors/
│   ├── load_cell.py        # 称重模块
│   ├── moisture.py         # 含水率模块
│   └── density.py          # 气流密度模块
├── motor/
│   ├── vibrating_feeder.py # 振动给料
│   ├── size_sorter.py      # 尺寸分选
│   └── spiral_feeder.py    # 螺旋出豆
├── mqtt/
│   └── client.py           # MQTT客户端（发送至烘豆机）
├── api/
│   └── server.py           # REST API（参数设置/状态查询）
├── db/
│   └── batch_db.py         # SQLite批次数据库
└── tests/
    └── calibration.py      # 传感器标定
```

### 6.2 ESP32端（Arduino）

```
firmware/
├── sorter_esp32/
│   ├── sorter_esp32.ino
│   ├── stepper_ctrl.h      # 步进电机驱动
│   ├── sensor_ctrl.h       # 传感器读取
│   └── comm.h              # 与Pi通信
```

### 6.3 数据库

- **SQLite**：`/var/sorter/batches.db`
- 每条记录包含：metadata + measurements + feed_history + 完整曲线数据

---

## 7. 与烘豆机的集成

### 7.1 机械接口

| 项目 | 说明 |
|------|------|
| 连接方式 | 软管 + 快拆法兰 DN40 |
| 出豆控制 | 螺旋给料器（步进电机）+ 电磁阀 |
| 释放条件 | 烘豆机 `UPSTREAM_READY=1` 时才开启 |

### 7.2 数据接口

| 项目 | 说明 |
|------|------|
| 协议 | MQTT |
| 出豆触发 | 接收烘豆机 `UPSTREAM_READY` 信号后，按 feed_plan 顺序出豆 |
| 每批数据 | 随第一份豆子一起发送 `/batch/start` JSON |
| 出豆完毕 | 发布 `BATCH_FEED_COMPLETE` 消息 |

### 7.3 分批逻辑

```
feed_plan = [
  {portion: 250g, sequence: 1},
  {portion: 250g, sequence: 2},
  {portion: 250g, sequence: 3}
]

→ 第一份：发送 BATCH_START + 打开出豆阀
→ 第二份：收到 ROASTER_RECEIVING 后（冷却完成），再发第二份
→ 第三份：同上
→ 全部完成后：发布 BATCH_FEED_COMPLETE
```

---

## 8. 设计目标（量化指标）

| 指标 | 目标值 | 备注 |
|------|--------|------|
| 处理量 | ≥ 2kg/h | 满足烘豆机产能 |
| 分选精度 | ±0.5% | 重量/含水率 |
| 缺陷检出率 | ≥ 95% | 颜色+形状识别 |
| 分类准确率 | ≥ 90% | ML模型 |
| 尺寸分级误差 | ±0.5目 | 相邻级别不混料 |
| 总成本 | < ¥1,500 | 3D打印+传感器+Pi |
| 框架重量 | < 3kg | PLA打印件 |

---

## 9. 课题规划

| 课题 | 主题 | 工具 |
|------|------|------|
| 课题1 | 尺寸分选机构（振动给料+阶梯孔板） | 3D打印 + 步进电机 |
| 课题2 | 颜色检测系统（Camera+光源+暗箱） | OpenCV + ML |
| 课题3 | 称重系统（Load Cell + HX711） | Python + 标定 |
| 课题4 | 密度分选（气流上扬通道） | CFD理论 + 实验 |
| 课题5 | 含水率检测（电容探头） | 电子学 + 标定 |
| 课题6 | 缓冲料仓+螺旋给料（分批控制） | 步进电机 + PID |
| 课题7 | MQTT通信 + REST API | Python paho-mqtt + Flask |
| 课题8 | 综合评审 + 联调测试 | - |

---

*版本记录：*
- v0.1 (2026-04-10): 初始版本，定义全部分选指标和技术路线
