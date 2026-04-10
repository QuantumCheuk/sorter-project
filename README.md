# 生豆分选机 / Green Coffee Bean Sorter

> 项目代号：HUSKY-SORTER-001  
> 版本：v0.1 | 2026-04-10

---

## 项目概述

HUSKY-SORTER-001 是一款面向小型精品咖啡作坊的**全指标生豆分选机**，支持：

- ✅ **尺寸分选**：5级目数（16/15/14/13/12目）
- ✅ **颜色检测**：Raspberry Pi HQ Camera + OpenCV + ML
- ✅ **单粒称重**：200g Load Cell，精度 0.01g
- ✅ **密度分级**：气流上扬法（轻/中/重 3级）
- ✅ **含水率检测**：电容式探头
- ✅ **分类标注**：产区/豆种/处理法/批次
- ✅ **数据输出**：MQTT → HUSKY-ROASTER-001
- ✅ **分批喂入**：按设定重量分段输出

## 📁 项目结构

```
sorter-project/
├── SPEC.md              # 设计规范
├── WORKLOG.md           # 项目进度追踪
├── README.md            # 本文件
├── sorter/              # 树莓派端主程序 (Python)
│   ├── camera/          # 图像采集和分析
│   ├── sensors/          # 传感器驱动
│   ├── motor/           # 电机控制
│   ├── mqtt/            # MQTT通信
│   ├── api/             # REST API
│   └── db/              # SQLite数据库
├── firmware/            # ESP32固件
├── docs/                # 技术分析文档
├── components/          # 物料清单
├── cad/                 # 3D模型/工程图
├── memory/              # 每日记忆
└── tasks/               # Cron任务脚本
```

## 🎯 设计指标

| 指标 | 目标值 |
|------|--------|
| 处理量 | ≥ 2kg/h |
| 尺寸分级 | 16/15/14/13/12目 |
| 称重精度 | ±0.01g |
| 含水率精度 | ±0.5% |
| 缺陷检出率 | ≥ 95% |
| 总成本 | < ¥1,500 |

## 🔗 流水线集成

```
[HUSKY-SORTER-001]  ──MQTT──►  [HUSKY-ROASTER-001]
  生豆分选机                          热风烘豆机
  ├── 尺寸/颜色/重量/密度/含水率      ├── 接收批次参数
  ├── 分类标注                         ├── 自动适配曲线
  └── 分批输出（250g×N）             └── 冷却后出豆
                                                  │
                                                  ▼
                                         [计量包装机]
```

## 📡 MQTT 消息流

- `sorter/{id}/batch/output` → 向上游发送批次数据
- `sorter/{id}/status` → 设备状态心跳
- `roaster/{id}/batch/input` → 触发烘豆机进豆

## 🚀 运行要求

- Raspberry Pi 4B (2GB+)
- Python 3.9+
- Raspberry Pi OS (64-bit)
- 3D打印机（打印面积 ≥ 220×220mm）

## 📖 文档

- [SPEC.md](./SPEC.md) — 完整设计规范
- [WORKLOG.md](./WORKLOG.md) — 项目进度

---

*此项目与 [HUSKY-ROASTER-001](https://github.com/QuantumCheuk/roaster-project) 共同构成 DDC 数字化干燥链。*
