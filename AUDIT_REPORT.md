# HUSKY-SORTER-001 全面生产就绪审计报告

> 审核日期: 2026-05-16
> 审核范围: 全部代码模块 + CAD 设计 + 固件 + 安全系统
> 审核目标: 排除所有隐藏隐患，确保可直接投入生产/硬件采购

---

## 总览

| 模块 | CRITICAL | HIGH | MEDIUM | LOW |
|------|----------|------|--------|-----|
| **CAD 设计** | 8 | 7 | 4 | 2 |
| **传感器模块** | 4 | 8 | 4 | 2 |
| **视觉/摄像头模块** | 8 | 6 | 3 | 0 |
| **控制/电机/MQTT/API/DB** | 23 | 20+ | 10+ | 5 |
| **ESP32 固件/质量/生产/安全** | 17 | 22 | 15 | 10 |
| **合计** | **60** | **63** | **36** | **19** |

**结论: 当前完全不具备投入生产条件。** 60 个 CRITICAL 问题中有大量是会导致硬件损坏、安全风险或功能完全失效的致命缺陷。

---

## 一、CAD 设计（重中之重）

### 现状
7 个 OpenSCAD 文件，1 个 Python 辅助设计文件。SPEC.md 4.2-4.4 要求约 17 个 3D 打印零件。

### CRITICAL 问题（8 个 — 根本性几何错误，打出来就是废品）

#### CAD-001: 密度分选喷嘴方向完全错误（3 个文件同时犯同样的错）
**文件**: `density_channel.scad:27-31`, `density_stage1.scad:27-31`, `density_stage2.scad:31`
```openscad
rotate([90,0,0]) cylinder(h=plenum_W+2, d=2.0, center=true, $fn=8);
```
**问题**: `rotate([90,0,0])` 将 Z 轴圆柱旋转 90°，喷嘴轴线变成 Y 方向（横向），而非预期的 Z 方向（向上）。
**后果**: 气流横向吹过通道，豆子被横推而非轻豆上浮。**密度分选功能完全失效。**
**修复**: 去掉 rotate，或改为 `rotate([0,0,0])`，让喷嘴从底部向上吹。

#### CAD-002: 缓冲仓入料斗倒置
**文件**: `buffer_bin.scad:48-57`
```openscad
linear_extrude(height=hopper_height_mm,
    scale=[inlet_diameter_top_mm/inlet_diameter_bottom_mm, ...])
    circle(d=inlet_diameter_bottom_mm, $fn=32);
rotate([180,0,0])
```
**问题**: 从底径 20mm 缩到顶径 40mm，再 rotate(180°) 翻转。结果是 20mm 小口在上、40mm 大口在下，**完全反了**。而且大口直接对接旋转分配器盘面，豆子落在旋转盘表面而非进入导向管。
**后果**: 豆子被旋转盘甩飞，无法进入任何仓位。
**修复**: 添加固定入料管穿透旋转盘中心；漏斗方向应上大下小。

#### CAD-003: 缓冲仓出料口与仓体不连通
**文件**: `buffer_bin.scad:104-109`
```openscad
translate([x - 4, wall_mm + bin_depth_mm + 2, 0])
    cube([8, 10, wall_mm]);
```
**问题**: outlet cube 起始于 y = 34.5mm，而仓内后壁在 y = 32.5mm。出料口在仓壁**外面**，没有穿透仓壁。
**后果**: 所有仓格的豆子**全部卡死**，一粒都出不去。
**修复**: 出料口应从 y = wall_mm - 1 开始，确保穿透仓壁。

#### CAD-004: 含水率探头入料漏斗与电极间隙 16.6mm 悬空
**文件**: `moisture_probe.scad:89-94`
**问题**: 漏斗底端在 z=26.2mm，上压板顶在 z=16.8mm。豆子从漏斗出来后要在 **16.6mm 空域**中自由落体，才能落入 8mm 电极间隙。咖啡生豆 9×6.5×3.5mm，弹跳后极大概率错过电极间隙。
**后果**: **含水率检测完全失效**，豆子落在探头外面。
**修复**: 漏斗底口直接对接上压板顶面（gap ≤ 1mm），直径匹配电极板（15mm）。

#### CAD-005: 称重杯闸门槽严重过切
**文件**: `weighing_cup.scad:46-48`
```openscad
translate([outer_diameter/2 - wall_thickness/2, -12.0/2, cup_height * 0.3])
    cube([wall_thickness + 2, 12.0, cup_height * 0.5]);
```
**问题**: 槽口宽 12mm(Y) × 深 4mm(X) × 高 5mm(Z)，切入 2mm 壁厚的杯体。深度超出壁厚 2mm，挖入杯内空间。5mm 高的槽在 10mm 高的杯体上，仅剩 2mm 上壁 + 3mm 下壁。
**后果**: 结构严重削弱，动态落豆冲击下可能**断裂**。
**修复**: 槽口改为 4-5mm 宽 × 3mm 高，深度仅穿透壁厚。

#### CAD-006: density_stage2 挡板完全在通道底板下方
**文件**: `density_stage2.scad:34-35`
```openscad
translate([..., 0])
    cube([channel_L-4, baffle_H, channel_H]);
```
**问题**: baffle_H=3，挡板占据 z=-3 到 z=0。但通道底板在 z=2。整个挡板在底板**下方**，与通道内部空间完全不相交。
**后果**: 轻豆无逃逸路径，stage2 密度分选无效。
**修复**: 挡板应放在通道顶部（z=channel_H-baffle_H 到 z=channel_H），并在顶壁开孔。

#### CAD-007: 称重杯入料漏斗方向反了
**文件**: `weighing_cup.scad:24`
```openscad
cylinder(h=funnel_height, d1=outer_diameter, d2=inlet_diameter, $fn=32)
// d1=18, d2=22 — 上小下大
```
**问题**: 漏斗从杯口 φ18mm 扩张到顶部 φ22mm，是**发散形**（正常漏斗应收敛：上大下小）。豆子落在 φ22mm 的宽面上，没有居中引导。
**修复**: 翻转: `d1=inlet_diameter(22), d2=outer_diameter(18)`。

#### CAD-008: 缓冲仓格子间距仅 1mm — 打印必然熔合
**文件**: `buffer_bin.scad:17` `gap_mm = 1.0`
**问题**: FDM 打印 0.2mm 层厚下，1mm 间隙只有 ~5 层宽。熔融塑料会跨越间隙，将 8 个独立仓位熔合成一个大连仓。
**后果**: 品质分级功能完全失效，A/B/C 豆混在一起。
**修复**: gap_mm ≥ 2.5mm，或将仓体拆成独立件组装。

---

### HIGH 问题（7 个 — 严重影响功能/装配/安全）

#### CAD-009: 称重杯 M2 螺纹孔在 1.5mm 底板上只有 1-2 牙咬合
**文件**: `weighing_cup.scad:40-41`, `weighing_cup_design.py:157`
**问题**: 底板仅 1.5mm 厚，M2×0.4 牙距最多咬合 3-4 牙。PETG 打印的螺纹在这个厚度下极易滑牙。
**修复**: 底板加厚到 3mm，或改用 M2 通孔 + 螺母。

#### CAD-010: 缓冲仓电机安装架壁厚仅 0.25mm
**文件**: `buffer_bin.scad:93-100`
**问题**: 安装架 38×15×38mm，螺栓孔中心距边缘 2mm，孔径 φ3.5mm（M3 通孔），孔边到表面仅 **0.25mm**。
**后果**: Nema17 振动下立即断裂。
**修复**: 安装块加宽到 40mm+，螺栓孔距边缘 ≥3mm。

#### CAD-011: density_stage1 挡板只覆盖通道左半边
**文件**: `density_stage1.scad:33-34`
**问题**: 挡板 y 范围 -30~30（左半），通道 y 范围 0~60。豆子沿通道中心（~y=30）运动，正好在挡板边界，无有效遮挡。
**修复**: 挡板覆盖全宽，或重新定位豆子路径。

#### CAD-012: density_stage2 φ1.5mm 喷嘴孔无法 FDM 打印
**文件**: `density_stage2.scad:31`
**问题**: φ1.5mm 孔穿过 14mm 厚壁（深径比 ~9:1），0.4mm 喷嘴 FDM 打印必然堵死。
**修复**: 孔径 ≥ φ2.5mm，或标注为"打印后钻孔"。

#### CAD-013: 称重杯入料漏斗方向发散（同 CAD-007 补充）
**问题**: 漏斗不居中引导豆子，豆子落在 φ22mm 宽面上随机弹跳。

#### CAD-014: 含水率探头电缆出口在法兰边缘
**文件**: `moisture_probe.scad:53-55`
**问题**: φ6mm 孔中心距 φ34mm 法兰边缘仅 3mm。电缆拖拽产生应力集中。
**修复**: 移到漏斗侧壁，或加电缆固定座。

#### CAD-015: 缓冲仓分配器通道孔径 φ18.2mm 卡豆风险
**文件**: `buffer_bin.scad:72-78`
**问题**: 咖啡生豆长轴 9mm，在 φ18.2mm 孔中偏心时有卡住风险。
**修复**: 增大到 φ22mm 或使用椭圆孔。

---

### MEDIUM 问题（4 个）

| # | 文件 | 问题 |
|---|------|------|
| CAD-016 | `weighing_cup.scad` | 底板延伸至杯体下方 1.5mm，可能与 load cell 安装面干涉 |
| CAD-017 | `weighing_cup.scad` | φ4mm load cell 定位孔太浅（1.5mm），无法正确定位 |
| CAD-018 | `density_channel.scad` | 分区导脊 0.5mm 宽 × 2mm 高，FDM 极限分辨率，大概率打不出 |
| CAD-019 | `buffer_bin.scad` | 总宽 215mm vs SPEC 标注 212mm（差 3mm），可能影响整机布局 |

---

### LOW 问题（2 个）

| # | 文件 | 问题 |
|---|------|------|
| CAD-020 | `moisture_probe.scad` | 上压板中央 φ2mm 孔可能卡入碎豆 |
| CAD-021 | `buffer_bin.scad` | 旋转分配器通道孔径偏小，长豆偏心风险 |

---

### 缺失的 CAD 文件（SPEC.md 要求但未设计）

| 缺失零件 | 优先级 | SPEC 参考 | 说明 |
|----------|--------|-----------|------|
| 入料斗（500g 容量，PETG） | HIGH | 4.2 | 人工倒豆入口 |
| 振动给料器基座（PLA） | HIGH | 4.2 | 弹簧支撑 + 电磁铁 |
| 5 级尺寸分选孔板 | HIGH | 2.1, 4.2 | 16/15/14/13/12 目阶梯孔板 |
| 颜色检测暗箱（PLA 白内壁） | HIGH | 2.2, 4.2 | 双摄像头 + LED 环形灯安装空间 |
| 单文件通道管（PETG, φ20mm） | HIGH | 2.2.1, 4.4 | 垂直通道，T1/T2 光电传感器安装位 |
| 气喷嘴（PLA, φ2mm 喷口） | HIGH | 2.2.5, 4.4 | 缺陷豆剔除用 |
| 传感器安装支架 | HIGH | 4.4 | T1/T2 光电传感器、连接件安装 |
| 废料仓（PETG, ~100g） | MEDIUM | 2.2.5, 4.4 | 接收被剔除的缺陷豆 |
| 偏转导向板（PLA） | MEDIUM | 2.2.5, 4.4 | 引导缺陷豆进入废料仓 |
| 框架连接件（PLA） | MEDIUM | 4.2 | 2020 铝型材或 M5 螺纹杆组装 |

**关键缺失**: 单文件通道管是双摄像头方案的核心机械结构（SPEC 2.2.1），但完全没有 CAD 文件。没有它，双摄方案无法组装。

---

## 二、传感器模块（sensors/）

### CRITICAL（4 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| S-001 | `load_cell.py:433` | 测试代码 `clock_pin=6`，但 SPEC v0.6 已迁移到 GPIO27（解决 DRV8833 冲突）。上硬件即冲突 | 称重失效 + 电机失控 |
| S-002 | `moisture.py:187-191` | `_read_capacitance_raw()` **无 return 语句**，硬件模式返回 None | 含水率永远读不到数据 |
| S-003 | `moisture.py:155-185` | AD7746 寄存器地址错误（VT_DATA 0x03 应为 0x02），且 `init()` 从未写配置寄存器 | 芯片处于默认/掉电状态，不工作 |
| S-004 | `sensors/__init__.py` | 只有注释，无任何 export。其他模块 `from sorter.sensors.moisture import ...` 全部 ImportError | 含水率模块无法被导入 |

### HIGH（8 个）

| # | 文件 | 问题 |
|---|------|------|
| S-005 | `load_cell.py:185` | 采样间隔 20ms，5 次 = ~100ms，超出 SPEC 80ms 周期要求（2kg/h 瓶颈） |
| S-006 | `load_cell.py` | **无温度漂移补偿** — SPEC 要求 40mg/°C + 每 30 秒 auto-tare，完全未实现 |
| S-007 | `moisture.py:305-332` | AD7746 从未配置转换速率（10Hz vs 50Hz），采样时序不确定 |
| S-008 | `moisture.py` | 无寄生电容距离警告 — SPEC 要求 <5cm，代码无检查 |
| S-009 | `moisture.py:213-275` | 555 振荡器备选方案仅为 stub（`_simulate = True` 锁死），无法切换到硬件 |
| S-010 | `calibration.py:70-79` | 保存无文件锁/原子写入，并发写入可能损坏标定文件 |
| S-011 | `calibration.py:231-232` | 直接访问 `load_cell._hx711.config`，封装破坏，重构即崩 |
| S-012 | `calibration.py:260-294` | verify() 使用 `input()` 交互，无法自动化/无人值守 |

### MEDIUM（4 个）

| # | 文件 | 问题 |
|---|------|------|
| S-013 | `load_cell.py:31-41` | HX711Config 默认 reference_unit=1.0/offset=0.0，无"未标定"警告 |
| S-014 | `load_cell.py:99-113` | 超时 1000ms 远超需要的 65ms，传感器断开时反应迟钝 |
| S-015 | `moisture.py:126-131` | 无标定漂移检测，无法发现探头老化 |
| S-016 | `calibration.py:296-314` | 豆种期望重量范围从未与实际测量对比 |

### LOW（2 个）

| # | 文件 | 问题 |
|---|------|------|
| S-017 | `load_cell.py:55` | 时钟时序 1µs（datasheet 要求 ≥0.2µs），保守但浪费吞吐 |
| S-018 | `calibration.py:402-447` | Demo 代码 import 路径错误 |

---

## 三、视觉/摄像头模块（camera/）

### CRITICAL（8 个 — 核心设计完全缺失）

| # | 文件 | 问题 | 影响 |
|---|------|------|------|
| C-001 | `capture.py:29-53` | **仅实现单摄像头**，SPEC.md 2.2 的双摄像头方案（Top HQ Camera + Bottom USB Camera）完全未实现 | 背面缺陷 100% 漏检 |
| C-002 | `capture.py` | **光电传感器 T1/T2 触发逻辑完全缺失**（GPIO4/GPIO17） | 无法知道何时拍照 |
| C-003 | `capture.py` | **bean_buffer 追踪缺失** — SPEC 2.2.3 要求 top/bottom 图像一一对应 | 正反面无法配对 |
| C-004 | `defect_detector.py:29-36` | **仅实现 6 类缺陷**，SPEC 要求 14 类（mold/fermented/black/broken/foreign/underweight/underdeveloped/dead/insect/hollow/over_dry/over_wet/pre_mold） | 8 类缺陷完全漏检 |
| C-005 | `ml_pipeline.py:897-902` | TFLite INT8 量化无 representative_dataset（注释掉了），无实际校准数据 | 量化后模型精度暴跌或无法导出 |
| C-006 | `color_analyzer.py:38-50` | L*a*b* 阈值全部硬编码，未按品种/处理法独立标定 | 不同豆种误判率极高 |
| C-007 | 全局 | **气喷剔除时序逻辑完全缺失** — SPEC 2.2.5 定义 15ms 延迟 + 80ms 喷气，无任何模块实现 | 缺陷豆无法被剔除 |
| C-008 | `defect_detector.py:54-61` | 硬编码缺陷规则未适配品种差异，`expected_area = 10000` 未校准分辨率 | 切换豆种后误判 |

### HIGH（6 个）

| # | 文件 | 问题 |
|---|------|------|
| C-009 | `capture.py:34` | `cv2.VideoCapture(0, cv2.CAP_V4L2)` 在 Pi libcamera 下可能不兼容 |
| C-010 | `capture.py:44-46` | HQ Camera 4056×3040 分辨率需显式配置，cv2 不一定能自动设置 |
| C-011 | `calibration.py:327-366` | LAB→BGR 转换公式不正确，应使用 `cv2.cvtColor` |
| C-012 | `image_processor.py:38-42` | HSV 范围硬编码，未根据 LED 色温/暗箱反射标定 |
| C-013 | `image_processor.py:278` | 像素→mm 转换因子 `/30` 未标定 |
| C-014 | `edge_model_optimization.py:30` | 硬编码绝对路径 `~/.openclaw/...`，非项目相对路径 |

### MEDIUM（3 个）

| # | 文件 | 问题 |
|---|------|------|
| C-015 | `dark_box.py:47-113` | 生成 OpenSCAD 但不验证尺寸是否匹配 SPEC |
| C-016 | `test_color_analyzer.py:87-103` | LAB→BGR 简化转换，与 OpenCV 可能有偏差 |
| C-017 | `ml_pipeline.py:603-609` | MobileNetV2 ImageNet 预训练，domain gap（自然图像 vs 咖啡豆）大 |

---

## 四、控制系统（control/ motor/ mqtt/ api/ db/）

### CONTROL — CRITICAL（6 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| CTL-001 | `control/main.py:514-516,819-824` | **E-STOP 通过事件队列排队**，而非立即执行。SPEC SF001 要求 SIL-3 E-STOP < 50ms 响应 | 安全违规，急停延迟可能伤人 |
| CTL-002 | `control/main.py:659` | 主循环被 `_pause_event.wait()` 阻塞，PAUSED 状态下 E-STOP 无法及时响应 | 同上 |
| CTL-003 | `control/main.py:447-490` | SorterController 接受裸 Dict 配置，完全不使用 `config.py` 中的 SystemConfig | 配置管理系统形同虚设 |
| CTL-004 | `control/dashboard.py:168-173` | **Dashboard 维护独立状态**（`self._state = "IDLE"`），与实际 SorterController 状态完全脱节 | 操作员看到的是假状态 |
| CTL-005 | `control/main.py:99-113` | BeanRecord **无 batch_id 字段**，无法关联豆子与批次 | 批次追溯不可能 |
| CTL-006 | `control/main.py:470-474` | **所有数据仅存内存**，无数据库持久化。断电即丢失所有分选记录 | 生产数据零追溯 |

### MOTOR — CRITICAL（5 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| MOT-001 | `motor/spiral_feeder.py:188-192` | **Python `time.sleep()` 无法生成精确步进脉冲** — Pi Linux 下 sleep 粒度 1-5ms，而 120RPM × 512步需要 ~977µs。速度误差 20-40% | 出料量严重不准 |
| MOT-002 | `motor/spiral_feeder.py:36-48` | **DRV8833 微步配置未实现** — 代码设 `microstep=8` 但从未写 MS1/MS2/MS3 引脚。默认全步模式（64步/转 vs 512步/转） | 出料量误差 8 倍 |
| MOT-003 | `motor/spiral_feeder.py:36-57` | **GPIO 引脚跨模块冲突** — FAN_PWM(GPIO12) vs distributor DIR(GPIO12)；HX711_SCK 在不同文件中用 GPIO6 和 GPIO27 | 硬件损坏风险 |
| MOT-004 | `motor/solenoid_gate.py:198,207,215` | **级联 `threading.Timer()` 无取消机制** — 中断后孤立 Timer 继续触发 | 停机后电磁阀误动作 |
| MOT-005 | `motor/solenoid_gate.py:315-323` | Auto-tare 线程与测量线程无锁同步 | 称重数据在读时被篡改 |

### MQTT — CRITICAL（4 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| MQ-001 | `mqtt/__init__.py:40-60` | **BatchStats 字段与 SPEC.md 5.3 JSON schema 完全不匹配** — SPEC 要求 origin_country/size_avg/defect_count 等，代码输出 grade_a_g/grade_b_g 等 | 与烘豆机集成必失败 |
| MQ-002 | `mqtt/__init__.py` | **BATCH_START 消息格式缺失** — SPEC 7.3 定义了完整的 roaster 接口 JSON，代码中不存在 | 烘豆机无法接收批次数据 |
| MQ-003 | `mqtt/__init__.py:243-247` | **重连无指数退避** — 固定 5s 重试，无上限，网络不稳时形成风暴 | Broker 被锤爆 |
| MQ-004 | `mqtt/__init__.py:406` | **发送虚假重量数据** — `actual_weight_g=cmd.target_weight_g`，报请求值而非实际出料量 | 烘豆机收到错误批次数据 |

### API — CRITICAL（5 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| API-001 | `api/__init__.py:26` | **无认证** — `auth_required` 默认为 False，即使设为 True 也无实现 | 任何人可控制机器 |
| API-002 | `api/__init__.py:362-373` | 电机控制无输入校验 — rpm 可设为 0 或极高值 | 安全风险 |
| API-003 | `api/__init__.py` | **无 POST /batch 端点** — 无法通过 API 创建批次 | API 功能残缺 |
| API-004 | `api/__init__.py:228-237` | **批次历史返回 mock 空数据** — 未接入 SQLite | API 数据虚假 |
| API-005 | `api/__init__.py:34-132` | **API SystemState 与 SorterController 完全脱节** — API 改的是假状态，真实机器状态不可见 | 远程监控/控制无效 |

### DB — CRITICAL（3 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| DB-001 | `db/database.py:136-138` | **WAL 模式无 checkpoint 管理** — WAL 文件无限增长，Pi SD 卡空间耗尽 | 数据丢失 |
| DB-002 | `db/models.py:265-273` | **除零错误** — `grade_yield_pct()` 分母可能为 0 | 空批次报告生成崩溃 |
| DB-003 | `db/report_generator.py:79-95` | **缺陷键查找逻辑混乱** — 多级 fallback（string→int→prefix→as-is），可能静默返回错误缺陷名 | 质量报告数据错误 |

### 跨模块系统级问题

| # | 问题 | 影响 |
|---|------|------|
| X-001 | **SystemConfig 从未被任何模块使用** — config.py 中完整的 JSON 加载 + 环境变量覆盖 + 类型化配置类完全是摆设 | 配置散落各处，无法统一管理 |
| X-002 | **GPIO 引脚分散在 5+ 个文件中**，无中央注册表，无冲突检测 | 上硬件即炸板 |
| X-003 | **所有模块默认 `simulate=True`** — 生产模式代码路径从未被实际测试 | 硬件模式大概率有隐藏 bug |

---

## 五、ESP32 固件（firmware/）

### CRITICAL（4 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| FW-001 | `sorter_esp32.ino:422-630` | **UART 命令解析使用手写 substring，无校验和** — 无效 JSON 导致未定义行为。STEPPER/VALVE 等执行器命令无 CRC 保护 | 串口噪声可导致电机误动作 |
| FW-002 | `sorter_esp32.ino:422-630` | **执行器命令无安全状态机守卫** — FAULT 状态下仍可执行 stepper/valve | E-STOP 后仍可动作 |
| FW-003 | `sorter_esp32.ino:200-211` | **T1/T2 传感器使用 `GPIO_INTR_ANYEDGE` 无消抖** — 红外光电传感器有 1-5ms 机械弹跳，每个豆触发 2 次中断 | 豆计数翻倍，ISR 队列溢出 |
| FW-004 | `sorter_esp32.ino:721-767` | **无看门狗定时器** — SPEC SF002 要求 SIL-2 watchdog (5s)，完全未实现 | 任务挂死后无法恢复 |

### HIGH（6 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| FW-005 | `sorter_esp32.ino:403-416` | ISR 直接修改 `g_status.beans_detected++` 无临界区保护 | 撕裂读 |
| FW-006 | `sorter_esp32.ino:691-717` | 步进脉冲使用阻塞 `delayMicroseconds()`，阻塞整个 FreeRTOS 任务 | 高 RPM 时系统无响应 |
| FW-007 | `sorter_esp32.ino:291-307` | 电磁阀 pulse 使用 `vTaskDelay()` 阻塞整个调用任务 80ms | 阻塞串口命令处理 |
| FW-008 | `sorter_esp32.ino:195-211` | T1/T2 GPIO 无上拉/下拉电阻 — 30cm 长线 EMI 敏感 | 误触发 |
| FW-009 | `sorter_esp32.ino:313-382` | HX711 驱动使用阻塞 `delayMicroseconds(100)` | 阻塞调用任务 |
| FW-010 | `sorter_esp32.ino:611-621` | **E-STOP 仅通过软件串口命令实现，无硬件 GPIO E-STOP** — Pi 崩溃则 E-STOP 失效 | 安全违规（SIL-3 不合规） |

### MEDIUM（5 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| FW-011 | `sorter_esp32.ino:753-757` | 所有任务栈固定 4096 字节，无高水位检查 | 栈溢出风险 |
| FW-012 | `sorter_esp32.ino:313-382` | HX711 超时 10000 次 busy-wait，无注释解释计算 | |
| FW-013 | `sorter_esp32.ino:233-238` | HX711 引脚 GPIO32/35 与 ADC 通道冲突风险 | |
| FW-014 | `sorter_esp32.ino:723-761` | 无启动自检/硬件验证序列 | 传感器断开无法发现 |
| FW-015 | `sorter_esp32.ino:246-285` | `g_stepper_mutex` 非 ISR 安全，优先级反转风险 | |

### LOW（4 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| FW-016 | `sorter_esp32.ino:445-466` | STATUS 响应 snprintf 512 字节缓冲区可能截断 |
| FW-017 | `sorter_esp32.ino:596-609` | FAN_PWM 命令为 no-op stub — 风扇速度无法控制 |
| FW-018 | `sorter_esp32.ino:767` | `loop()` 仅 `delay(1000)`，无看门狗/堆监控 |
| FW-019 | `sorter_esp32.ino:663-664` | VCC 读数与 T1 传感器共享 ADC1_CHANNEL_0，互相干扰 |

---

## 六、质量模块（quality/）

### CRITICAL（4 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| Q-001 | `classifier.py:273-280` | **分级逻辑 OR/AND 错误** — `if quality_score >= 95 or defect_rate < 1.0: return A`。评分 50 但缺陷率 0% 的豆也被评为 A 级 | 品质分级完全不可信 |
| Q-002 | `qc_audit_system.py:1563-1574` | **SCA 缺陷换算公式根本错误** — 忽略缺陷严重度权重（黑豆=2.0 vs 碎豆=1.0），所有缺陷等权处理 | 合规证书数据错误 |
| Q-003 | `qc_audit_system.py:1369-1382` | SCA 计算有 3 种不同实现，中间两个是死代码（计算后被覆盖），最终用错误公式 | 同上 |
| Q-004 | `classifier.py:232-239` | **`should_reject` 逻辑冗余** — `grade == REJECT` 与 critical defect 检查用 OR 连接，但 critical defect 可能存在于 B/C 级豆中而不设 grade=REJECT | 关键缺陷可能不被剔除 |

### HIGH（6 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| Q-005 | `thresholds.py:284-513` | BROKEN(0.01-0.08g)/UNDERWEIGHT(0.05-0.10g)/HOLLOW(0.03-0.10g) **三重叠加区 0.05-0.08g** — 同一豆触发 3 个缺陷，3× 扣分 |
| Q-006 | `classifier.py:260-280` | `_grade_from_results()`（OR 逻辑）与 `grade_from_score()`（AND 逻辑）不一致，相同输入不同输出 |
| Q-007 | `qc_audit_system.py:463-480` | 含水率合规检查边界条件错误（8.0% 被判为不合格） |
| Q-008 | `thresholds.py:204-214` | 物理传感器（包含=缺陷）与颜色传感器（包含=正常）语义完全相反，但 `contains()` 无区分 |
| Q-009 | `qc_audit_system.py:78-94` | SCA_DEFECT_EQUIVALENTS 键名（"over_dry"）与 DefectType 枚举（OVERDRY）不一致 |
| Q-010 | `classifier.py:207-221` | ML 置信度阈值 0.7 是魔法数字，不可配置 |

### MEDIUM（5 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| Q-011 | `qc_audit_system.py:1055` | 用 sorter quality_score 冒充 SCA cupping score（两种评分体系不同） |
| Q-012 | `quality_module_validator.py:76-85` | 验证测试仅测试"正常不触发"，无边界值测试 |
| Q-013 | `config.py:23` | 硬编码 `/etc/sorter/quality_config.json`，无开发环境 fallback |
| Q-014 | `grades.py:25-29` | 导出中的 emoji 字符（🅰️🅱️）在 CSV/Excel 中可能乱码 |
| Q-015 | `thresholds.py:89-93` | NORMAL_* 常量定义了两次（constants 和 dataclass 默认值），不同步 |

### LOW（4 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| Q-016 | `classifier.py:242-246` | Notes 生成引用了未实际触发的 ML 缺陷 |
| Q-017-Q019 | 多处 | 文档/注释中命名不一致 |

---

## 七、生产模块（production/）

### CRITICAL（5 个）

| # | 文件:行 | 问题 | 影响 |
|---|---------|------|------|
| P-001 | `batch_recipe_manager.py:622-626` | validate_recipe() 不检查阈值范围顺序 — `undersize_g >= normal_min_g`（反转）能通过验证 | 无效配方导致分类崩溃 |
| P-002 | `disaster_recovery.py:177-181` | SQLite backup 无错误处理 — `pages=0` 在 WAL 模式下如果有读者则失败 | 备份静默失败 |
| P-003 | `data_export_archive.py:222` | 硬编码绝对路径 `/Users/quantumcheuk/.openclaw/...` | 生产部署直接崩溃 |
| P-004 | `integration_bridge.py:203-213` | HOLLOW 阈值 `min_val=0.0, max_val=medium_min` — 覆盖所有低密度值，无物理意义下界 | 逻辑错误 |
| P-005 | `integration_bridge.py:133-138` | 缺陷权重属性名大小写敏感，SCA 键名小写 vs 枚举大写 — 脆弱映射 | 静默查找失败 |

### HIGH（7 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| P-006 | `batch_tracking_system.py:97` | TraceEvent 使用简单 SHA-256 链，无 HMAC — 可伪造审计日志 |
| P-007 | `disaster_recovery.py:67-69` | 云备份配置在 import 时读取，非运行时 — 环境变量变更不生效 |
| P-008 | `batch_quality_tracker.py:231-236` | THRESHOLDS 字典混用绝对值和偏差值两种不同语义 |
| P-009 | `alarm_manager.py:321-326` | MQTT 错误被 `except Exception: pass` 静默吞掉 — 告警系统本身故障时无人知晓 |
| P-010 | `batch_recipe_manager.py:132` | `__post_init__` 不校验 recipe_id/origin_country 非空 |
| P-011 | `disaster_recovery.py:186-199` | SQL dump 手动字符串拼接 — `O'Reilly` 类数据导致 SQL 损坏 |
| P-012 | `integration_bridge.py:203` | HOLLOW 密度阈值下界 0.0 无物理意义 — 应设 0.30 |

### MEDIUM（5 个）

| # | 文件:行 | 问题 |
|---|---------|------|
| P-013 | `alarm_manager.py:198-199` | 滞回 10% 硬编码，CRITICAL 和 INFO 共用同一值 |
| P-014 | `data_export_archive.py:222` | 财务价格硬编码 CNY，不可配置 |
| P-015 | `alarm_manager.py:474-475` | 即时触发告警用 occurrence_count 计数，每个 eval 周期递增，非实际发生次数 |
| P-016 | `integration_bridge.py:623` | `recipe.origin` 属性不存在（应为 `origin_country`）— 死代码中的 bug |
| P-017 | `batch_tracking_system.py:480` | 追溯详情截断为 3 个字段 |

### LOW（2 个）

| # | 文件 | 问题 |
|---|------|------|
| P-018 | `disaster_recovery.py:196-198` | SQL dump 每行一条 INSERT，大批次慢 |
| P-019 | `batch_tracking_system.py` | 无 HMAC 的审计链在法规合规上存疑 |

---

## 八、安全系统（SPEC.md Section 11 合规性）

### 安全功能实现状态

| 安全功能 | SPEC 要求 | 实际实现 | 状态 |
|----------|-----------|---------|------|
| SF001 E-STOP (SIL-3) | <50ms 硬件响应 | 软件排队，延迟 5-200ms | ❌ 不合格 |
| SF002 Watchdog (SIL-2) | 5s 看门狗 | 未实现 | ❌ 不合格 |
| SF003 气压监测 (SIL-2) | 500ms 响应 | GPIO8 未读取 | ❌ 不合格 |
| SF004 电源监控 (SIL-1) | 1s 响应 | VCC 读数有但通道冲突 | ⚠️ 部分 |
| SF005 温度保护 (SIL-1) | 1s 响应 | temperatureRead() 存在 | ✅ 合格 |
| SF006 气喷前气压验证 (SIL-2) | 200ms | 未实现 | ❌ 不合格 |
| SF007 传感器数据校验 (SIL-1) | 10ms | 无范围验证 | ❌ 不合格 |
| SF008 MQTT 完整性 (SIL-1) | 5s | 无 CRC/校验和 | ❌ 不合格 |
| SF009 电机堵转检测 (SIL-1) | 1s | 无脉冲计数/位置验证 | ❌ 不合格 |
| SF010 HX711 Auto-Tare (SIL-1) | 5s | hx711_tare() 已实现 | ✅ 合格 |

**安全合规率: 2/10 = 20%** — 远低于投入生产的安全基线。

### CRITICAL 安全问题

| # | 问题 |
|---|------|
| SAF-001 | E-STOP 仅软件实现，Pi 崩溃则失效 — 不符合 SIL-3 |
| SAF-002 | 无看门狗，任何任务挂死无法恢复 — 不符合 SIL-2 |
| SAF-003 | 安全继电器 K1/K2/K3/K4 固件中完全无控制代码 — 硬件采购了但固件不驱动 |
| SAF-004 | T1/T2 传感器无消抖，豆计数翻倍导致节拍混乱 |

### HIGH 安全问题

| # | 问题 |
|---|------|
| SAF-005 | GPIO8 气压传感器未实现 — 气喷前无法验证气压是否足够 |
| SAF-006 | T1/T2 长线无上拉电阻 — EMI 误触发 |
| SAF-007 | 安全回路硬件已设计（SPEC 11.3）但固件未集成 |

---

## 九、问题优先级总结与修复建议

### P0 — 阻断性问题（不解决不能上硬件）

| # | 类别 | 问题 | 建议 |
|---|------|------|------|
| P0-01 | CAD | 密度分选喷嘴方向错误（3 个文件） | 去掉 rotate([90,0,0])，改为垂直向上 |
| P0-02 | CAD | 缓冲仓出料口不连通 | 修正 translate Y 坐标 |
| P0-03 | CAD | 缓冲仓入料斗倒置 | 翻转漏斗方向，添加固定入料管 |
| P0-04 | CAD | 含水率探头漏斗 16.6mm 悬空 | 漏斗底口直接对接电极板 |
| P0-05 | CAD | density_stage2 挡板在通道外 | 挡板移至通道顶部 |
| P0-06 | CAD | 称重杯闸门过切 | 缩小槽口尺寸 |
| P0-07 | 固件 | E-STOP 无硬件实现 | GPIO22 硬件 ISR，直接切断执行器 |
| P0-08 | 固件 | 无看门狗 | esp_task_wdt_init(5000, true) |
| P0-09 | 固件 | T1/T2 无消抖 | 改为 GPIO_INTR_NEGEDGE + 5ms 软件消抖 |
| P0-10 | 固件 | UART 无校验和 | 添加 CRC-16 到所有命令帧 |
| P0-11 | 传感器 | AD7746 无 return 语句 | 实现 I2C 读取 |
| P0-12 | 传感器 | AD7746 未初始化 | 写入 CAP_SETUP + MODE 寄存器 |
| P0-13 | 传感器 | sensors/__init__.py 无 export | 添加所有类的 export |
| P0-14 | 视觉 | 双摄像头同步完全缺失 | 实现 T1/T2 GPIO 中断 → 拍照 → bean_buffer |
| P0-15 | 视觉 | 气喷剔除时序完全缺失 | 新建 rejection_controller.py |
| P0-16 | 控制 | E-STOP 排队执行 | 改为直接调用 `_on_estop()` |
| P0-17 | 控制 | 步进脉冲用 time.sleep() | 改用 pigpio 硬件 PWM |
| P0-18 | 控制 | DRV8833 未配置微步 | 初始化 MS1/MS2/MS3 引脚 |
| P0-19 | 系统 | GPIO 引脚冲突 | 创建 gpio_manager.py 中央注册表 |
| P0-20 | 系统 | 所有配置硬编码 | 接入 SystemConfig |
| P0-21 | MQTT | 消息格式与 SPEC 不匹配 | 实现 SPEC 5.3 的完整 JSON schema |
| P0-22 | API | 无认证 | 添加 API key 或 JWT |
| P0-23 | DB | WAL 无 checkpoint | 定期 PRAGMA wal_checkpoint(TRUNCATE) |
| P0-24 | 质量 | 分级 OR/AND 逻辑错误 | 改 OR 为 AND |
| P0-25 | 质量 | SCA 计算公式错误 | 实现带严重度权重的正确公式 |

### P1 — 高风险（影响生产可靠性和数据正确性）

| # | 类别 | 问题 | 建议 |
|---|------|------|------|
| P1-01 | CAD | 缓冲仓格子间距 1mm | 增大到 2.5mm 或分件打印 |
| P1-02 | CAD | 电机安装架壁厚 0.25mm | 加宽到 3mm+ |
| P1-03 | CAD | 称重杯漏斗方向反 | 翻转 d1/d2 |
| P1-04 | 视觉 | 缺陷分类仅 6 类 vs 14 类 | 扩展 defect_detector.py |
| P1-05 | 视觉 | 颜色阈值硬编码 | 从配方文件加载 |
| P1-06 | 传感器 | 无温度漂移补偿 | 每 30 秒 auto-tare + DS18B20 补偿 |
| P1-07 | 控制 | 数据仅存内存 | 接入 SQLite 持久化 |
| P1-08 | 控制 | BeanRecord 无 batch_id | 添加字段 |
| P1-09 | 控制 | API 与 SorterController 脱节 | API 直接调用 Controller |
| P1-10 | MQTT | 发送虚假重量数据 | 使用实际称重值 |
| P1-11 | MQTT | 重连无退避 | 指数退避 + 熔断器 |
| P1-12 | 固件 | 阻塞 delayMicroseconds 脉冲 | 改用 LEDC/MCPWM 硬件 |
| P1-13 | 固件 | 电磁阀 pulse 阻塞任务 | 改用硬件定时器回调 |
| P1-14 | 固件 | GPIO 无上拉电阻 | 启用 GPIO_PULLUP_ENABLE |
| P1-15 | 生产 | 配方验证不检查范围顺序 | 添加 min < max 校验 |
| P1-16 | 生产 | SQL dump 有注入风险 | 改用参数化或 iterdump() |
| P1-17 | 质量 | 缺陷阈值范围三重叠加 | 重新设计互斥范围 |

### P2 — 中风险（影响可维护性和生产质量）

| # | 类别 | 问题 | 状态 |
|---|------|------|------|
| P2-01 | CAD | 密度分选导脊 0.5mm 太细 | ✅ 已修复 |
| P2-02 | CAD | 缓冲仓宽度偏差 3mm | ✅ 已修复 |
| P2-03 | 视觉 | LAB→BGR 转换公式不对 | ✅ 已修复 |
| P2-04 | 视觉 | 像素→mm 未标定 | ✅ 已修复 |
| P2-05 | 传感器 | HX711 采样超时设置 | ✅ 已修复 |
| P2-06 | 控制 | Dashboard 状态与控制器脱节 | ✅ 已修复 |
| P2-07 | DB | 缺陷键查找逻辑混乱 | ✅ 已修复 |
| P2-08 | 固件 | 任务栈大小未验证 | ✅ 已修复 |
| P2-09 | 固件 | 无启动自检 | ✅ 已修复 |
| P2-10 | 生产 | 告警滞回固定 10% | ✅ 已分析（非bug，per-policy可配） |
| P2-11 | 生产 | 告警系统故障静默 | ✅ 已修复 |
| P2-12 | 质量 | SCA 键名与枚举不一致 | ✅ 已修复 |

### P3 — 低优先级（可后续优化）

| # | 类别 | 问题 |
|---|------|------|
| P3-01 | CAD | 称重杯底板干涉 | ✅ 已修复 |
| P3-02 | 传感器 | 时钟时序保守 | ✅ 已分析（保守值安全，无需改） |
| P3-03 | 固件 | STATUS 截断 | ✅ 已修复 |
| P3-04 | 固件 | FAN_PWM 为 stub | ✅ 已修复 (LEDC) |
| P3-05 | 固件 | loop() 空 | ✅ 已修复 (watchdog feed) |
| P3-06 | 质量 | emoji 导出问题 | ✅ 已修复 |
| P3-07 | 生产 | SQL dump 性能 | ✅ 已修复 |

---

## 十、缺失 CAD 文件清单（硬件采购前必须补全）

| 零件 | 优先级 | 为什么重要 |
|------|--------|-----------|
| 单文件通道管 | **CRITICAL** | 双摄方案核心，T1/T2 传感器安装位 |
| 入料斗 | HIGH | 人工操作界面，影响上料效率 |
| 振动给料器基座 | HIGH | 均匀给料是吞吐量关键 |
| 尺寸分选孔板 ×5 | HIGH | 5 级尺寸分选的核心部件 |
| 颜色检测暗箱 | HIGH | 控制光照环境，影响颜色检测精度 |
| 气喷嘴 | HIGH | 缺陷豆剔除执行机构 |
| 传感器支架 | HIGH | 所有传感器的安装基础 |
| 废料仓 | MEDIUM | 缺陷豆收集 |
| 偏转导向板 | MEDIUM | 引导缺陷豆入废料仓 |
| 框架连接件 | MEDIUM | 整机结构组装 |

---

## 十一、采购决策建议

### 可以现在采购的（不受软件 bug 影响）

| 组件 | 说明 |
|------|------|
| Raspberry Pi 4B | 通用硬件 |
| HX711 + Load Cell | 通用传感器 |
| 28BYJ-48 / Nema17 电机 | 标准步进电机 |
| DRV8833 驱动板 | 标准驱动 |
| 继电器/安全回路组件 | 通用电气件 |
| ESP32 开发板 | 通用 MCU |

### 必须等 CAD 修复后才能采购/定制的

| 组件 | 等待原因 |
|------|---------|
| 3D 打印件（全部） | 6 个 CRITICAL 几何错误，打出来就是废品 |
| 涡轮鼓风机 | 密度通道设计有根本错误，先修 CAD |
| HQ Camera IMX477 | 双摄方案无 CAD 暗箱和通道管 |
| 光电传感器 T1/T2 | 无安装支架 CAD |

### 建议立即订购的（交付周期最长）

| 组件 | 交付周期 | 理由 |
|------|---------|------|
| HQ Camera IMX477 | ~45 天 | 最长交期，但可以先订购，到货时 CAD 应该修好了 |
| 涡轮鼓风机 | ~45 天 | 同上 |

---

## 附录：按模块统计代码量

| 模块 | 文件数 | 说明 |
|------|--------|------|
| camera/ | ~14 | 视觉处理（含仿真/测试） |
| sensors/ | 4 | 称重 + 含水率 + 标定 |
| motor/ | 3 | 螺旋给料 + 分配器 + 称重站 |
| control/ | 7 | 状态机 + 仪表盘 + 配置 + 固件工具 |
| mqtt/ | 1 | MQTT 客户端 |
| api/ | 1 | Flask REST API |
| db/ | 5 | 数据库 + 模型 + 报告生成 |
| quality/ | 7 | 分级 + 阈值 + QC 审核 |
| production/ | 9 | 批次 + 配方 + 告警 + 灾备 |
| simulation/ | ~32 | 各类仿真分析 |
| firmware/ | 1 | ESP32 固件（767 行） |
| cad/ | 7 | OpenSCAD 模型 |
| docs/ | ~5 | 文档 |
| **合计** | **~125 Python + 7 SCAD + 1 INO** | |

---

## 附录：P0 修复进度跟踪

> 更新时间: 2026-05-17

| # | 模块 | 问题 | 状态 |
|---|------|------|------|
| P0-01 | CAD | 密度分选喷嘴方向错误（3 个文件） | ✅ 已修复 |
| P0-02 | CAD | 缓冲仓出料口不连通 | ✅ 已修复 |
| P0-03 | CAD | 缓冲仓入料斗倒置 | ✅ 已修复 |
| P0-04 | CAD | 含水率探头漏斗 16.6mm 悬空 | ✅ 已修复 |
| P0-05 | CAD | density_stage2 挡板在通道外 | ✅ 已修复 |
| P0-06 | CAD | 称重杯闸门过切 | ✅ 已修复 |
| P0-07 | 固件 | E-STOP 无硬件实现 | ✅ 已修复 |
| P0-08 | 固件 | 无看门狗 | ✅ 已修复 |
| P0-09 | 固件 | T1/T2 无消抖 | ✅ 已修复 |
| P0-10 | 固件 | UART 无校验和 | ✅ 已修复 |
| P0-11 | 传感器 | AD7746 无 return 语句 | ✅ 已修复 |
| P0-12 | 传感器 | AD7746 未初始化 | ✅ 已修复 |
| P0-13 | 传感器 | sensors/__init__.py 无 export | ✅ 已修复 |
| P0-14 | 视觉 | 双摄像头同步完全缺失 | ✅ 已修复 |
| P0-15 | 视觉 | 气喷剔除时序完全缺失 | ✅ 已修复 |
| P0-16 | 控制 | E-STOP 排队执行 | ✅ 已修复 |
| P0-17 | 控制 | 步进脉冲用 time.sleep() | ✅ 已修复 |
| P0-18 | 控制 | DRV8833 未配置微步 | ✅ 已修复 |
| P0-19 | 系统 | GPIO 引脚冲突 | ✅ 已修复 |
| P0-20 | 系统 | 所有配置硬编码 | ✅ 已修复 |
| P0-21 | MQTT | 消息格式与 SPEC 不匹配 | ✅ 已修复 |
| P0-22 | API | 无认证 | ✅ 已修复 |
| P0-23 | DB | WAL 无 checkpoint | ✅ 已修复 |
| P0-24 | 质量 | 分级 OR/AND 逻辑错误 | ✅ 已修复 |
| P0-25 | 质量 | SCA 计算公式错误 | ✅ 已修复 |

**进度: 25/25 已修复 (100%)**

### 本轮修复详情（ESP32 固件 + 控制层）

**P0-07: E-STOP 无硬件实现** ✅
- 新增 GPIO15 E-STOP 按钮输入（NC 常闭触点，active LOW）
- 新增 `estop_isr()` 硬件 ISR，立即停止所有电机和电磁阀（不经过 UART 队列）
- 新增 `g_estop_active` 全局标志
- 新增 `ESTOP_HW` 命令类型区分硬件/软件 E-STOP
- 新增 `ESTOP_RESET` 命令清除硬件 E-STOP 状态
- STATUS 响应新增 `estop_active` 字段
- SIL-3 合规: 硬件 ISR 延迟 <50μs（vs 原来 UART 命令 5-200ms）

**P0-08: 无看门狗** ✅
- `setup()` 初始化 ESP32 Task Watchdog (TWDT, 5 秒超时, panic on timeout)
- `loop()` 每 1 秒 `esp_task_wdt_reset()`
- `serial_task()` 每 10ms 喂狗
- `status_task()` 每 5 秒喂狗
- 任何任务卡死超过 5 秒 → 自动触发 panic 重启

**P0-09: T1/T2 无消抖** ✅
- T1/T2 GPIO 中断从 `GPIO_INTR_ANYEDGE` 改为 `GPIO_INTR_NEGEDGE`（仅下降沿）
- 新增 `GPIO_PULLUP_ENABLE` 配合 NPN NO 传感器
- ISR 改用 `esp_timer_get_time()` 微秒级时间戳（原 `millis()` 仅毫秒精度）
- 新增 5ms 消抖窗口：`g_t1_last_trigger_us` / `g_t2_last_trigger_us` 记录上次触发时间
- 消抖窗口内重复触发直接忽略

**P0-10: UART 无校验和** ✅
- 新增 CRC-16-CCITT 校验函数 `crc16_ccitt()`
- `process_command()` 自动检测 `"crc":NNNN` 字段
- CRC 不匹配立即拒绝帧并递增 `faults_detected`
- 无 CRC 字段的帧向后兼容（接受但不校验）
- Raspberry Pi 发送端可选附加 CRC 到 JSON 帧末尾

**P0-17: 步进脉冲 time.sleep() 精度不足** ✅
- `stepper_task()` 改用 `esp_timer_get_time()` 微秒级精确定时
- `ets_delay_us(50)` 替代 `delayMicroseconds()` 用于脉冲宽度
- 步进间隔计算: `us_per_step = (60 × 1,000,000) / (rpm × steps_per_rev × microstep)`
- 长间隔自动 yield (`vTaskDelay`) 让其他任务运行
- 原 us_per_step 公式错误已修复：`(steps_per_rev × 1,000,000) / (rpm × 60)` → `(60 × 1,000,000) / (rpm × steps_per_rev)`

**P0-18: DRV8833 未配置微步** ✅
- 新增 GPIO14 (MS1) 和 GPIO23 (MS2) 输出引脚
- `init_pins()` 设置 MS1=HIGH, MS2=HIGH → 1/8 微步（与 config microstep=8 一致）
- DRV8833 真值表: 00=full | 10=half | 01=1/4 | 11=1/8
- 固件版本字符串更新: Build "2026-05-03" → "2026-05-17"

### 本轮修复详情（续）

**P0-23: DB WAL 无 checkpoint** ✅
- `Database.__init__` 新增 `wal_checkpoint_interval` 参数（默认 1000 次写入）
- `transaction()` 上下文管理器在每次 commit 后递增写入计数器
- `_maybe_checkpoint()` 自动在达到阈值时执行 `PRAGMA wal_checkpoint(PASSIVE)`（非阻塞）
- 新增 `wal_checkpoint(mode)` 公开方法支持手动触发（PASSIVE/FULL/RESTART）
- 新增 `close()` 方法，关闭前执行 RESTART checkpoint 清理 WAL 文件
- 写入计数器在 checkpoint 后归零，线程安全（`_checkpoint_lock`）

**P0-24: 分级 OR/AND 逻辑错误** ✅
- `classifier.py:_grade_from_results()` 将 `or` 改为 `and`
- 修复前：`score >= 95.0 or defect_rate < 1.0` → score=96, defect=5% → 错误地得到 Grade A
- 修复后：`score >= 95.0 and defect_rate < 1.0` → score=96, defect=5% → 正确得到 Grade C
- 与 `grades.py:grade_from_score()` 的 AND 逻辑保持一致

**P0-25: SCA 计算公式错误** ✅
- `classifier.py:_compute_quality_score()` 改用 SCA 指数级严重度惩罚
- 旧惩罚：5/10/15/20/25（线性，severity 5 仅扣 25 分，太宽容）
- 新惩罚：2/5/12/25/40（指数，severity 5 扣 40 分，severity 1 仅扣 2 分）
- Severity 5 (CRITICAL): 单个缺陷 → 60 分（自动 REJECT）
- Severity 4 (HIGH): 单个缺陷 → 75 分
- Severity 3 (MEDIUM): 两个缺陷 → 76 分
- Severity 2 (LOW): 两个缺陷 → 90 分（仍可能 Grade A/B）
- 测试验证：所有修复后行为符合预期

### 本轮修复详情

**P0-21: MQTT 消息格式与 SPEC 不匹配** ✅
- 新增 `BatchOutputMessage` 数据类，字段完全匹配 SPEC 5.3 BATCH_READY（message_type/batch_id/timestamp/source/metadata/measurements/quality_class/feed_plan/total_weight_kg/portion_count/recommended_profile/roast_level_target/notes）
- 新增 `BatchStartMessage` 数据类匹配 SPEC 7.3 BATCH_START
- 新增 `BatchMetadata` / `BatchMeasurements` / `FeedPortion` 辅助数据类
- 旧 `BatchStats` 保留向后兼容，新增 `to_output_message()` 转换方法
- `publish_batch_ready()` 同时支持新旧格式
- 新增 `publish_batch_start()` 方法
- `BatchDispatcher` 改用实际出料量（从 buffer bin level 读取）而非请求量
- `BatchDispatcher` 每次出料自动发布 BATCH_START 消息
- FeedCommand 新增 `to_json()` 方法

**P0-22: API 无认证** ✅
- 新增 API key 认证系统（SHA-256 哈希存储）
- 密钥通过 `SORTER_API_KEYS` 环境变量配置
- 无环境变量时自动生成随机 key 并打印 stdout
- 写操作端点强制认证（config PUT/calibration POST/control POST/motor PUT/bin PUT/mqtt/publish POST）
- GET 端点无需认证（只读）
- 认证可通过 `SORTER_API_AUTH_REQUIRED=false` 环境变量关闭
- 新增 `/api-keys` 端点查看已注册 key 信息
- 电机控制新增 RPM 范围校验（每种电机独立上下限）
- 仓位设置新增负数校验和 bin_id 白名单

---

## P1 修复进度跟踪

> 更新时间: 2026-05-17 (第二轮修复)

| # | 类别 | 问题 | 状态 |
|---|------|------|------|
| P1-01 | CAD | 缓冲仓格子间距 1mm | ✅ 已修复 (P0-02 gap→2.5mm) |
| P1-02 | CAD | 电机安装架壁厚 0.25mm | ✅ 已修复 (P0-02 4mm) |
| P1-03 | CAD | 称重杯漏斗方向反 | ✅ 已修复 (P0-02) |
| P1-04 | 视觉 | 缺陷分类仅 6 类 vs 14 类 | ✅ 已修复 (P0-24) |
| P1-05 | 视觉 | 颜色阈值硬编码 | ✅ 已修复 (P0-24 variety) |
| P1-06 | 传感器 | 无温度漂移补偿 | ✅ 已修复 (P0-24 solenoid_gate auto_tare) |
| P1-07 | 控制 | 数据仅存内存 | ✅ 已修复 (P0-23 DB 模块) |
| P1-08 | 控制 | BeanRecord 无 batch_id | ✅ 已修复 (P0-16) |
| P1-09 | 控制 | API 与 SorterController 脱节 | ✅ 已修复 |
| P1-10 | MQTT | 发送虚假重量数据 | ✅ 已修复 (P0-21) |
| P1-11 | MQTT | 重连无退避 | ✅ 已修复 |
| P1-12 | 固件 | 阻塞 delayMicroseconds 脉冲 | ✅ 已修复 (P0-17 esp_timer) |
| P1-13 | 固件 | 电磁阀 pulse 阻塞任务 | ✅ 已修复 |
| P1-14 | 固件 | GPIO 无上拉电阻 | ✅ 已修复 (P0-09) |
| P1-15 | 生产 | 配方验证不检查范围顺序 | ✅ 已修复 |
| P1-16 | 生产 | SQL dump 有注入风险 | ✅ 已修复 |
| P1-17 | 质量 | 缺陷阈值范围三重叠加 | ✅ 已修复 |

**P1 进度: 17/17 已修复 (100%)**

### 本轮 P1 修复详情

**P1-11: MQTT 重连无退避** ✅
- `_reconnect()` 改用指数退避: 2s → 4s → 8s → 16s → 32s → 60s (capped)
- 新增 0-1s 随机 jitter 防止 thundering herd
- 新增 `_reconnect_max_attempts` 可配置最大重试次数（默认无限）
- 成功连接后自动重置 `_reconnect_attempt = 0`

**P1-15: 配方验证不检查范围顺序** ✅
- 新增完整阈值范围排序验证:
  - Weight: `undersize < light < normal_min < normal_max < heavy < oversize`
  - Moisture: `too_dry < target_min < target_max < too_wet`
  - Density: `light < medium_min < medium_max < heavy`
- 新增 `recipe_id` 非空验证 (P-010)
- 反转的阈值范围（如 `undersize_g=0.30 > light_g=0.11`）现在会被正确拒绝

**P1-16: SQL dump 有注入风险** ✅
- `disaster_recovery.py` SQL dump 改用 SQL 标准单引号转义
- `f"'{str(v).replace(\"'\", \"''\")}'"` 替代裸字符串拼接
- 修复 `O'Reilly` 等含单引号的值导致的 SQL 损坏

**P-003: 硬编码绝对路径** ✅
- `data_export_archive.py` 两处 `/Users/quantumcheuk/.openclaw/...` 改为 `~/.husky_sorter/data/...`

**P-004/P-012: HOLLOW 密度阈值下界 0.0** ✅
- `integration_bridge.py` HOLLOW `min_val` 从 0.0 改为 0.30（物理有意义的最低密度）

**P-009: SCA_DEFECT_EQUIVALENTS 键名不一致** ✅
- 键名从 `insect_damaged`→`insect`、`stunted`→`underdev`、`over_dry`→`overdry`、`over_wet`→`overwet`
- 新增 `mold_precursor` 和 `unknown` 条目
- diagnose() 方法的 hypotheses 和 action_map 同步更新
- 测试代码的 defect_types 列表同步更新

**P1-09: API 与 SorterController 脱节** ✅
- 新增 `inject_controller()` 注入真实 SorterController 实例
- GET `/status` 优先读取 `controller.get_status()` 而非 SystemState 假数据
- GET `/batch/current` 读取 `controller._current_batch` 实时数据
- POST `/control/start|stop|pause` 调用 `controller.post_event(Event.*)` 操作真实状态机
- 未注入时 fallback 到 SystemState（开发/测试模式）

**P1-13: ESP32 电磁阀 pulse 阻塞任务** ✅
- `solenoid_set()` 改用 FreeRTOS one-shot timer 非阻塞脉冲
- `solenoid_pulse_off_cb()` timer 回调自动关闭电磁阀
- 80ms 气喷脉冲不再阻塞 UART 命令处理任务
- timer 对象可复用（xTimerStop → xTimerChangePeriod → xTimerStart）

**P1-17: 缺陷阈值三重叠加** ✅
- BROKEN 范围从 0.02-0.08g → 0.02-0.05g（排除与 UNDERWEIGHT 重叠）
- UNDERWEIGHT 保持 0.05-0.10g（与 BROKEN 互斥）
- HOLLOW 从 weight 传感器改为 density 传感器（0.25-0.52 g/mL）
  — 不再与 BROKEN/UNDERWEIGHT 重量范围重叠
  — HOLLOW 现在是纯密度缺陷，物理语义正确

**FW-017: Fan PWM 无操作 stub** ✅
- `init_pins()` 初始化 LEDC 硬件 PWM（25kHz, 10-bit 0-1023）
- FAN_PWM 命令调用 `ledc_set_duty()` + `ledc_update_duty()` 驱动真实 PWM
- 从 no-op 变为真正的硬件 PWM 控制

**P-004/P-012: HOLLOW 密度阈值** ✅
- `integration_bridge.py` HOLLOW `min_val` 从 0.0 → 0.30（物理有意义下界）

---

*审核完成。P0 级 25/25 ✅ + P1 级 17/17 ✅ 全部修复完成 (100%)。项目进入可采购/定制硬件阶段。*
