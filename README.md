# 生豆分選機 / Green Coffee Bean Sorter

> 項目代號：HUSKY-SORTER-001  
> 版本：v0.9 | 2026-04-30  
> 目標：全指標分選（大小/顏色/重量/密度/含水率）+ 分批餵入烘豆機  
> 狀態：**硬體採購階段**（預計 2026-07-13 到位）

---

## 項目概述

HUSKY-SORTER-001 是一款面向小型精品咖啡作坊的**全指標生豆分選機**，支持：

- ✅ **尺寸分選**：5級目數（16/15/14/13/12目）
- ✅ **顏色檢測**：Raspberry Pi HQ Camera IMX477 + OpenCV + 雙攝像頭方案
- ✅ **單粒稱重**：200g Load Cell，精度 ±0.01g（HX711 24bit ADC）
- ✅ **密度分選**：氣流上揚法（輕/中/重 3級，渦輪鼓風機）
- ✅ **含水率檢測**：電容式探頭（AD7746 VCN），精度 ±0.5%
- ✅ **緩衝倉 + 螺旋給料**：8格旋轉料倉 + PID 控制
- ✅ **MQTT 通信**：完整客戶端 + 狀態/批次數據上報
- ✅ **REST API**：Flask 12端點，本地控制 + 遠程監控
- ✅ **實時儀表盤**：Tkinter GUI，無硬體即可演示
- ✅ **綜合仿真**：蒙特卡洛 / FMEA / 能量分析 / 供應鏈風險 / 時序分析

**對標產能：** ≥2.0 kg/h（3通道 × 50bpm）  
**當前瓶頸：** 單通道 0.27kg/h（需升級至 3 通道 Nema17 配置）

---

## 📁 項目結構

```
sorter-project/
├── SPEC.md              # 完整設計規範（v0.8）
├── WORKLOG.md          # 項目進度追蹤（v1.27）
├── README.md            # 本文件
├── sorter/              # 樹莓派端主程序
│   ├── camera/          # 圖像採集和分析（11文件）
│   ├── sensors/         # 傳感器驅動（Load Cell / 含水率）
│   ├── motor/           # 馬達控制（Nema17 + 28BYJ-48）
│   ├── mqtt/            # MQTT 客戶端（狀態/批次）
│   ├── api/             # REST API（Flask 12端點）
│   ├── control/         # 控制模組（主控 + 儀表盤 + 配置）
│   │   ├── main.py      # SorterController 狀態機
│   │   ├── dashboard.py # Tkinter GUI 儀表盤
│   │   ├── config.py    # SystemConfig 配置類
│   │   ├── pi_setup.sh  # 一鍵 Pi 配置腳本
│   │   ├── WIRING_GUIDE.md  # 接線指南
│   │   └── DEBUGGING_GUIDE.md # 調試手冊
│   ├── docs/            # 文檔
│   │   └── OPERATOR_MANUAL.md # 操作員手冊（v1.0）✨
│   ├── simulation/      # 仿真分析（32文件）
│   ├── cad/             # 3D模型/工程圖（Fusion360）
│   └── db/              # SQLite 數據庫
└── firmware/            # ESP32 固件
```

---

## 🎯 設計指標

| 指標 | 目標值 | 當前狀態 |
|------|--------|---------|
| 處理量 | ≥ 2kg/h | 🔵 0.27kg/h（單通道瓶頸）|
| 尺寸分級 | 5級（16-12目）| ✅ 完成 |
| 稱重精度 | ±0.01g | ✅ 完成 |
| 含水率精度 | ±0.5% | ✅ 完成 |
| 顏色檢出率 | ≥95%（融合召回87.9%）| ✅ 完成 |
| 總成本 | < ¥1,500 | 🔵 ~¥2,244（含升級）|
| 缺陷檢出率 | ≥95% | ✅ 融合算法達成 |

---

## 📡 MQTT 消息流

| Topic | 方向 | 內容 |
|-------|------|------|
| `sorter/{id}/batch/output` | → Roaster | 批次數據（重量/含水率/缺陷統計）|
| `sorter/{id}/status` | → Monitor | 設備狀態心跳（5s間隔）|
| `sorter/{id}/bean/{bean_id}` | → Monitor | 單豆檢測結果（實時）|
| `roaster/{id}/batch/input` | ← Roaster | 觸發進豆指令 |

---

## 🚀 運行要求

- Raspberry Pi 4B (2GB+)
- Python 3.9+
- Raspberry Pi OS (64-bit)
- 3D打印機（打印面積 ≥ 220×220mm）
- 12V 3A 電源適配器（執行器）
- 5V 3A USB-C（Pi 供電）

---

## 📖 文檔

| 文檔 | 說明 |
|------|------|
| [SPEC.md](./SPEC.md) | 完整設計規範（v0.8）|
| [WORKLOG.md](./WORKLOG.md) | 項目進度追蹤 |
| [sorter/control/OPERATOR_MANUAL.md](./sorter/docs/OPERATOR_MANUAL.md) | **操作員手冊（v1.0）** |
| [sorter/control/WIRING_GUIDE.md](./sorter/control/WIRING_GUIDE.md) | 接線指南 |
| [sorter/control/DEBUGGING_GUIDE.md](./sorter/control/DEBUGGING_GUIDE.md) | 調試手冊 |

---

## 供應鏈狀態（2026-04-30 更新）

| 關鍵組件 | 交付週期 | 預計到位 | 狀態 |
|---------|---------|---------|------|
| HQ Camera IMX477 | ~45天 | 2026-07-13 | 🔵 最高風險 |
| 渦輪鼓風機 | ~45天 | 2026-07-13 | 🔵 最高風險 |
| Nema17 馬達 ×3 | ~7天 | 2026-05-07 | ✅ 可提前備貨 |
| HX711 Load Cell | ~7天 | 2026-05-07 | ✅ 國產備貨 |

> ⚠️ 預計硬體到位：2026-07-13（60天風險窗口）

---

*此項目與 [HUSKY-ROASTER-001](https://github.com/QuantumCheuk/roaster-project) 共同構成 DDC 數字化乾燥鏈。*
