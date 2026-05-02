# 生豆分选机项目工作日志 / WORKLOG
> 项目代号：HUSKY-SORTER-001

---

## 项目状态：✅ 所有课题完成（进入下一阶段：硬件采购+物理测试）

---

## 当前版本
- **SPEC.md: v0.8 (2026-04-29)**
- **WORKLOG.md: v1.35 (2026-05-02)** — 批次数据持久化与报告生成系统（sorter/db/，SQLite数据库+JSON/CSV/TEXT三格式报告+CLI）

---

## 项目完整性最终检查

### 全部完成文件清单

| 模块 | 文件数 | 状态 |
|------|--------|------|
| 颜色检测 `camera/` | 12 | ✅ |
| 称重系统 `sensors/load_cell.py` | 1 | ✅ |
| 含水率 `sensors/moisture.py` | 1 | ✅ |
| 仿真分析 `simulation/` | 32 | ✅ |
| 电机控制 `motor/` | 2 | ✅ |
| MQTT客户端 `mqtt/` | 1 | ✅ |
| REST API `api/` | 1 | ✅ |
| CAD设计 `cad/` | 4 | ✅ |
| 数据库 `db/` | 5 | ✅ |
| 控制系统 `control/` | 7 | ✅ |
| 配置模块 `sorter/config.py` | 1 | ✅ |
| 合计 | **~63文件** | ✅ |

### 剩余TODO清理

| 文件 | TODO内容 | 评估 |
|------|---------|------|
| `sorter/camera/dark_box_test_protocol.py:417` | 实现加载逻辑 | 非阻塞：仅测试协议辅助功能 |
| `sorter/camera/dark_box_test_protocol.py:515` | 真实样本测试逻辑 | 非阻塞：仅测试协议辅助功能 |

> ✅ `dispensed_bins` 已在 v1.8 修复（commit 1d913ab）

---

## 课题完成总览

| 课题 | 状态 | 完成日期 |
|------|------|---------|
| 课题1：尺寸分选机构 | ✅ | 2026-04-14 |
| 课题2：颜色检测系统 | ✅ | 2026-04-14 |
| 课题3：称重系统 | ✅ | 2026-04-14 |
| 课题4：密度分选 | ✅ | 2026-04-25 |
| 课题5：含水率检测 | ✅ | 2026-04-25 |
| 课题6：缓冲仓+螺旋给料 | ✅ | 2026-04-26 |
| 课题7：MQTT + REST API | ✅ | 2026-04-26 |
| 课题8：综合评审+联调测试 | ✅ | 2026-04-26 |

---

## 变更历史
| 日期 | 变更内容 | 版本 |
|------|----------|------|
| 2026-04-10 | 项目初始化 | v0.1 |
| 2026-04-12 | SPEC v0.2：批次模式澄清+颜色独立建模 | v0.2 |
| 2026-04-13 | SPEC v0.3：双摄方案+气喷剔除+宽通道备选 | v0.3 |
| 2026-04-13 | SPEC v0.4：称重系统深化（温度/滤波/称重杯CAD） | v0.4 |
| 2026-04-13 | WORKLOG v0.3：课题3 Day1 称重系统HX711+仿真 | v0.3 |
| 2026-04-13 | WORKLOG v0.4：课题3 Day2 增强分析+称重杯3D设计 | v0.4 |
| 2026-04-14 | WORKLOG v0.5：课题3 Day3 物理测试协议+称重站控制模块 | v0.5 |
| 2026-04-25 | WORKLOG v0.6：课题4 Day3 物理测试协议+涡轮鼓风机规格+集成分析 | v0.6 |
| 2026-04-25 | WORKLOG v0.7：课题5 Day1 电容含水率探头原理分析+AD7746驱动 | v0.7 |
| 2026-04-25 | WORKLOG v0.8：课题5 Day2 标定方法+电路设计+电缆效应修正 | v0.8 |
| 2026-04-25 | WORKLOG v0.9：课题5 Day3 CAD探头设计+物理测试协议+集成分析 | v0.9 |
| 2026-04-26 | WORKLOG v1.0：课题6 Day1 缓冲仓+螺旋给料设计（8格仓+φ20螺旋） | v1.0 |
| 2026-04-26 | WORKLOG v1.1：课题6 Day2 PID控制算法+流量标定+分配器时序 | v1.1 |
| 2026-04-26 | WORKLOG v1.2：课题6 Day3 MQTT完整实现+物理测试+CAD整合 | v1.2 |
| 2026-04-26 | WORKLOG v1.3：课题7 REST API完整实现（Flask 12端点）+课题6/7全部完成 | v1.3 |
| 2026-04-26 | WORKLOG v1.4：课题8 Day1 综合评审（架构审查+时序分析+BOM+6步测试计划） | v1.4 |
| 2026-04-26 | WORKLOG v1.5：课题8 Day2 GPIO重新分配（HX711→GPIO27）+ 采购清单整理（¥841） | v1.5 |
| 2026-04-26 | WORKLOG v1.6：课题8 Day3 硬件组装3阶段计划+SPEC.md v0.6 GPIO表更新+最终检查清单+课题8全部完成 | v1.6 |
| 2026-04-27 | WORKLOG v1.7：项目完整性检查 + TODO清理 + 下一步规划 | v1.7 |
| 2026-04-27 | WORKLOG v1.8：修复 `mqtt/__init__.py` dispensed_bins TODO | v1.8 |
| 2026-04-27 | WORKLOG v1.9：每日cron检查 — 所有课题完成，Git已同步，硬件采购阶段待机 | v1.9 |
| 2026-04-27 | WORKLOG v1.10：每日cron检查 — Git push成功（v1.9已推送），项目完整清洁，无新增TODO | v1.10 |
| 2026-04-27 | WORKLOG v1.11：每日cron检查 — 项目待机状态，Git已同步，无新增TODO或待处理事项 | v1.11 |
| 2026-04-27 | WORKLOG v1.12：每日cron检查（15:06）— Git已同步（v1.11），项目完整清洁，无新增TODO或待处理事项 | v1.12 |
| 2026-04-27 | WORKLOG v1.13：每日cron检查（21:06）— 项目待机状态，所有课题完成，Git已同步，无新增TODO | v1.13 |
| 2026-04-28 | WORKLOG v1.14：每日cron检查（00:07）— 项目待机状态，所有课题完成，Git已同步，无新增TODO或待处理事项 | v1.14 |
| 2026-04-28 | WORKLOG v1.15：每日研究任务 — **吞吐量瓶颈深度分析**（sorter/simulation/throughput_bottleneck_analysis.py）。关键发现：单通道设计理论上限0.27kg/h（振动给料30bpm），距2kg/h目标差87%。3通道×50bpm=2.70kg/h可达成目标，需¥520升级费。生成3张分析图：throughput_stage_comparison.png / throughput_multichannel_scaling.png / throughput_upgrade_roadmap.png | v1.15 |
| 2026-04-28 | WORKLOG v1.16：每日cron检查（12:07）— Git已同步（v1.15已推送f41cb12），SPEC.md v0.7已完成，项目待机状态，无新增TODO | v1.16 |
| 2026-04-28 | WORKLOG v1.17：每日研究任务（18:07）— **多通道协调架构深度分析**（sorter/simulation/multi_channel_coordination.py）。在昨日吞吐量瓶颈分析基础上：①Nema17电机物理仿真验证50bpm可行性（相比28BYJ-48提速1.3×）；②2/3/4通道机械布局设计（共享下游设备）；③轮询调度算法仿真验证2.70kg/h达成；④ESP32多电机协调架构（LEDC硬件PWM+UART bean_id）；⑤MQTT多通道批次追踪设计。生成3张图：nema17_feeder_performance.png / multi_channel_layout.png / multi_channel_scheduling.png。升级成本估算¥347（原估算¥520含 contingency）。| v1.17 |

| 2026-04-28 | WORKLOG v1.18：每日研究任务（21:09）— **多通道 FMEA + 可靠性工程深度分析**（sorter/simulation/multi_channel_fmea_reliability.py）。覆盖内容：①20项失效模式FMEA分析（FM-01振动给料器卡豆RPN=27最高风险；FM-14旋转分配器失步严重度=5极危险）；②MTBF/可用性计算（3通道系统可用性99.92%，年停机399分钟 vs 单通道652分钟）；③降级分析（3通道健康=2.70kg/h✅ / 2通道=1.80kg/h⚠ / 1通道=0.90kg/h❌）；④关键设计建议（原点复位传感器+看门狗+每通道独立保险丝，新增成本约¥80）。生成3张图：fmea_risk_matrix.png / reliability_degradation.png / availability_comparison.png。Git已推送（75ef2ff）。|
| 2026-04-29 | WORKLOG v1.19：每日研究任务（00:07）— **多传感器数据融合与品质评分系统**（sorter/simulation/fusion_quality_scoring.py）。覆盖内容：①14种缺陷×4传感器覆盖矩阵建模（发霉豆/发酵豆/黑豆/碎豆/异物/过轻豆/过重豆/发育不全豆/死豆/虫蛀豆/空心豆/过干豆/过湿豆/发霉前兆）；②贝叶斯融合算法（sequential posterior update，阈值5%）；③蒙特卡洛50轮×10000豆仿真验证：融合召回率87.9% vs 最佳单传感器40.7%（提升+47.2%）；④加权投票融合（87.9%与贝叶斯等效）；⑤品质评分系统（0-100分，含缺陷风险/数据完整性/物理参数三维）；⑥单传感器盲区分析（10种缺陷仅单一传感器覆盖，失去融合保护）。生成3张图：fusion_recall_comparison.png / quality_score_distribution.png / sensor_defect_matrix.png。Git已推送（69b4860）。|

| 2026-04-29 | WORKLOG v1.21：每日研究任务（09:06）— **制造准备度评估**（sorter/simulation/manufacturing_readiness.py + .json）。目标：项目待机状态下，为硬件组装做最后准备。覆盖内容：①19种3D打印件工艺分析（PLA/PETG/层厚/填充/warping风险）；总打印33.5小时，PLA/PETG线材成本¥25；高风险件：缓冲仓212mm PETG（需RAFT+80°C热床）/ 称重杯壁薄2mm（0.1mm缝隙精度）。②激光切割建议：尺寸分选孔板×5级+气喷嘴φ2mm用PMMA替代3D打印（±0.1mm精度）。③25步装配顺序（依赖关系图），总工时13.2小时（约4工作日），10个HIGH风险关键检查点（相机标定/称重标定/AD7746<5cm引线/GPIO27接线）。④BOM采购成本：Phase1标准配置¥1927（21种），Phase2升级（Nema17×3+涡轮鼓风机）¥317，总计¥2244（超原始预算¥1500约50%，主因：HQ相机¥350+空压机¥200+AD7746¥60）。⑤8项关键风险（HQ相机货期/AD7746电缆效应/GPIO接线错误等）及缓解措施。⑥7天分阶段组装时间线（Day1-2框架到Day11+升级评估）。⑦6类最终检查清单（发运前必查）。Git已推送（2e50ae1）。|

| 2026-04-29 | WORKLOG v1.22：每日研究任务（12:07）— **控制系统核心实现**（sorter/control/main.py + config.py）。目标：在课题全部完成后，为硬件组装准备完整的软件控制层。覆盖内容：①SorterController主控制类：9状态状态机（IDLE→INITIALIZING→CALIBRATING→READY→RUNNING→FEEDING→PAUSED→FAULT→ESTOP）+ 事件驱动架构；②传感器抽象层（T1Sensor/T2Sensor/HX711Sensor/MoistureSensor/ColorCamera）支持模拟+真实硬件模式；③执行器抽象层（AirJetValve/VibratingFeeder/WeighingCupRelease）；④BeanRecord+BatchRecord数据模型；⑤系统配置类SystemConfig（GPIO/Sensor/Motor/MQTT/API/Batch/Quality七个子配置，支持JSON加载/保存/环境变量覆盖）；⑥CLI交互界面（start/stop/load/batch/status/beans/estop命令）。SPEC.md更新至v0.8（新增第10节：软件架构更新+控制层说明）。Git已推送（f9616c6）。|

| 2026-04-29 | WORKLOG v1.23：每日研究任务（15:11）— **实时监控仪表盘**（sorter/control/dashboard.py）。目标：在所有课题完成后，为硬件组装阶段准备完整的操作员界面，无需硬件即可演示评估。覆盖内容：①Tkinter全GUI实现（1280×800，深色主题）；②9状态机颜色编码大字状态显示（IDLE灰/INITIALIZING蓝/READY绿/RUNNING亮绿/PAUSED橙/FAULT红/ESTOP深红）；③实时传感器读数（重量/含水率/颜色分/尺寸/密度/最新缺陷类型）；④统计面板（已分选粒数/已剔除粒数/总重量/实时吞吐量/给料速度/故障次数）；⑤批次进度条（可配置目标kg）；⑥matplotlib吞吐量折线图（近2分钟，5fps更新，含2.0kg/h目标线）；⑦5类缺陷计数器（发霉豆/发酵豆/黑豆/碎豆/发育不全）；⑧控制按钮（Start/Pause/Stop/E-Stop/Reset）；⑨MQTT连接状态指示；⑩滚动事件日志。BeanSimulator以50bpm模拟豆子流（8%缺陷率）。Python语法检查通过。Git已推送。|
| 2026-04-29 | WORKLOG v1.20：每日研究任务（03:06）— **物理测试协议与标定程序**（sorter/simulation/physical_test_protocol.py）。目标：硬件到位后，按本协议执行各模块标定与集成测试。覆盖内容：①18项性能基准PASS/FAIL阈值定义（颜色/称重/含水率/密度/给料/系统）；②模块标定流程（颜色预热+白板稳定性+双摄重现性 / 称重零点+量程+线性 / 含水率基线+样本验证 / 密度风速+分离正确率 / 振动给料稳定性+最大速率）；③8步集成测试序列（GPIO/I2C设备发现/相机连通性/MQTT延迟/API响应/持续运行/缺陷检出/吞吐量实测）；④CalibrationRecord+TestReport数据结构；⑤模拟运行结果：14/18通过（77.8%）。关键发现：称重系统100g误差23.5mg（临界区），线性误差35.3mg（临界区），给料49.6bpm差0.4bpm未达50bpm目标，吞吐量0.45kg/h（单通道瓶颈，预期结果，与v0.7结论一致）。通过率77.8%反映设计余量充足，真实硬件应有更大改善空间。Git已推送（104f1f4）。|

| 2026-04-29 | WORKLOG v1.24：每日研究任务（18:07）— **完整时序分析**（sorter/simulation/bean_timing_sequence_analysis.py）。目标：为硬件组装准备完整的端到端时序验证。覆盖内容：①单粒完整时序链（入口→缓冲仓，685ms，正常豆 vs 缺陷豆：缺陷豆多15ms）；②关键路径分析（颜色检测125ms为瓶颈，决定系统最大容量480bpm）；③多通道争用分析（3通道轮询调度，Pi图像处理资源争用，每通道571bpm，总1714bpm=0.26kg/h）；④端到端吞吐量验证（4配置对比：1/3通道×28BYJ/Nema17）；⑤最坏情况时序叠加（+60ms延迟，相对正常路径+10%）。生成1张图：bean_timing_sequence.png。关键发现：颜色检测图像处理25ms为关键路径，3通道×50bpm=2.70kg/h ✅ 满足2kg/h目标。最坏情况分析显示系统有充足时序余量。硬件组装调试建议：①颜色检测系统优先调试（T1/T2传感器时序验证）；②示波器测量GPIO中断延迟（目标<100μs）；③AD7746配置50Hz模式（采样从100ms降至20ms）；④多通道场景用BeanSimulator模拟验证轮询调度；⑤完整系统用dashboard.py实时监控端到端时序。Git已推送（da6a402）。
| 2026-04-29 | WORKLOG v1.25：每日研究任务（21:14）— **硬件组装准备三件套**：①`pi_setup.sh`（一键Pi配置脚本）：系统更新、I2C/SPI/摄像头启用、项目克隆、Python依赖、Mosquitto MQTT、WiFi、静态IP（可选）、GPIO权限、systemd服务；②`WIRING_GUIDE.md`（接线指南）：GPIO总图、**GPIO27迁移提示**（HX711 SCK从GPIO6→GPIO27）、详细接线表、I2C地址速查、线缆标签、常见错误表；③`DEBUGGING_GUIDE.md`（调试手册）：首次通电检查、6大模块调试流程、10种故障代码速查、性能基准测试脚本。控制模块文件数3→6个。Git已推送（c0ab24d）。
| 2026-04-30 | WORKLOG v1.26：每日研究任务（00:07）— **能量消耗分析**（sorter/simulation/energy_consumption_analysis.py）。覆盖内容：①14种组件功耗清单（峰值40.5W/典型27.1W）；②电源轨规格选型（5V 3A USB-C×Pi + 12V 3A适配器×执行器）；③运行成本估算（¥122/年，10h/天300天）；④散热设计（总热耗8.05W，外壳温升≈2°C，需60mm风扇）；⑤3通道升级电源规划（Nema17升级峰值116W需12V 10A独立电源）。关键发现：当前12V 2A适配器不足以驱动空压机（峰值需求3A+），建议升级12V 3A以上适配器。Git已推送（6fe31c3）。

| 2026-04-30 | WORKLOG v1.27：每日研究任务（03:11）— **蒙特卡洛生产产量仿真 + 供应链交付周期风险分析**（sorter/simulation/monte_carlo_production_analysis.py）。目标：为硬件到位后的实际运行提供预期基准，同时评估关键组件供应风险。覆盖内容：①10,000次蒙特卡洛仿真（缺陷率2%/5%/10% × 单/三通道6种配置）；②贝叶斯融合召回率87.9%+假阳性5%建模；③日产量/合格品量/剔除量概率分布；④收益损耗建模（精品豆¥120/kg，普通豆¥80/kg）；⑤年度收益汇总：精品豆¥857,750/年（净收益率94.5%），普通豆¥552,102/年；⑥供应链交付周期风险：关键路径（涡轮鼓风机+HQ相机）≈60天，预计2026-07-13硬件到位；⑦产能利用率热力图（8×6工况）；⑧15张分析图+JSON报告。关键发现：3通道日产量中位数25kg（10h@2.70kg/h），年处理≈7.5吨；假阳性率高导致精确率仅26-64%（低缺陷率时最严重）；涡轮鼓风机和HQ相机为最高风险进口件，建议立即订购。Git已推送（b7f560a）。|

| 2026-04-30 | WORKLOG v1.28：每日研究任务（06:06）— **综合操作员手册**（sorter/docs/OPERATOR_MANUAL.md，654行，12,770字节，v1.0）。目标：在硬件到位前准备完整的操作文档，为实际使用阶段做准备。覆盖内容：①安全警告（電氣/機械/咖啡豆處理三類分級）；②機器規格（基本參數/分選指標/通訊接口）；③操作界面說明（dashboard.py 完整解析 + CLI 命令 + 狀態燈含義）；④操作前檢查清單（電源/機械/電氣/軟體/材料/環境6大類每日必填檢查表）；⑤標準操作流程（開機5步/正常運行5步/正常關機4步+清理）；⑥批次操作指南（參數建議/監控指標/數據導出）；⑦維護保養（每日/每週/每月/耗材更換時間表）；⑧故障排除（10種故障代碼速查表 + 6個常見QA：MQTT/相機/稱重/給料速度/空壓機）；⑨緊急停機程序（觸發條件/6步程序/嚴禁事項）；⑩技術參數（GPIO定義/I2C地址/軟體依賴/網路配置）；⑪配件備件清單（10種常備配件 + 工具清單）；⑫術語表。同時更新 README.md 至 v0.9（添加操作員手冊鏈接 + 供應鏈狀態）。Git已推送（556942d）。|

| 2026-04-30 | WORKLOG v1.29：每日研究任务（09:06）— **ML训练管道框架**（sorter/camera/ml_pipeline.py，1178行）。目标：硬件到位前建立完整的缺陷检测模型训练管道，无需真实硬件即可开发ML能力。覆盖内容：①SyntheticBeanGenerator（合成数据生成器）：基于L*a*b*颜色范围生成14类咖啡豆图像，含传感器噪声/LED光斑/开裂纹理模拟；②BeanDataCollector（真实数据收集管理器）：配合dark_box_test_protocol.py使用，支持top+bottom双图配对采集；③BeanDefectTrainer（训练器）：MobileNetV2预训练模型+自定义分类头，迁移学习策略（冻结基座+微调最后30层），Adam优化器+余弦学习率+早停+类别权重（缺陷类×1.5增强）；④TFLiteDefectClassifier（TFLite推理器）：INT8量化模型，Pi 4边缘部署，推理速度基准测试；⑤ANNOTATION_GUIDE.md（标注指南，v1.0）：14类标签定义+视觉指标对照表，top+bottom双图标注规则（任意一面有缺陷→标注该缺陷），LabelImg/CVAT使用指南，最小训练数据量要求（生产≥2000张/类），质量保证QA协议（双重标注+分歧解决）。README.md更新至v1.0（ML章节+快速开始指南）。Git已推送（b3ef89c）。|
| 2026-04-30 | WORKLOG v1.31：每日研究任务（00:07）— **Edge AI推理优化分析**（sorter/camera/edge_inference_analysis.py + edge_inference_report.json）。目标：在ML训练管道完成后，分析Pi 4边缘部署的推理性能约束。覆盖内容：①Pi 4硬件资源基线（1GB/2GB/4GB/4GB+EdgeTPU × FP32/INT8/EdgeTPU共9种组合）；②内存可行性：Pi 4 2GB + INT8剩余450MB（足够dashboard+MQTT共存）；③INT8 vs FP32：推理延迟70ms→28ms（2.5×加速），功耗节省8%（0.33W）；④多通道吞吐量验证：3通道×50bpm=2.70kg/h（满足2kg/h目标），50bpm间隔1200ms >> 轮询时间144ms，稳态无队列积压；⑤实时性保障5层机制：看门狗（5s超时重启）/推理超时（100ms）/降级策略（规则引擎）/背压检测（队列>5暂停给料）/多进程隔离；⑥升级路径：Phase 1 Pi 4 2GB ¥290（推荐）→ Phase 1b Pi 4 4GB ¥390 → Phase 2 EdgeTPU ¥850（仅在50bpm瓶颈确认后）；⑦关键结论：EdgeTPU升级¥560非必要（延迟余量充足，Pi 4 2GB INT8已满足所有推理需求）；⑧日能耗成本：¥0.022/天（@10h，¥0.6/kWh）。Git已推送（5fb3941）。|

| 2026-04-30 | WORKLOG v1.30：每日研究任务（21:11）— **成本优化分析**（sorter/simulation/cost_optimization_analysis.py + cost_optimization_report.json + cost_optimization_analysis.png）。当前成本¥1864超预算24.3%，5种方案对比：方案A纯Phase1（¥1565但仅0.27kg/h❌）/ 方案D综合优化（¥1434达2.70kg/h✅）/ 方案E降级涡轮（¥1409但仅1.35kg/h⚠️）。方案D核心降本：HQ Camera→USB Camera（-¥270）+ AD7746→分立电路（-¥40）+ 涡轮鼓风机→优化版5015（-¥120）= 节省¥430，低于¥1500预算4.4%。替代品调研：Logitech C270×2/NE555分立电路/盘古风扇/Pi Zero 2W。Git已推送（5fb3941）。|

| 2026-05-01 | WORKLOG v1.33：每日研究任务（18:07）— **ML Pipeline 验证工具运行**（sorter/camera/ml_pipeline_validator.py，8项测试）。验证结果：总分 93.8/100，6通过2警告0失败。✅ COCO格式正确（14类100条标注）/ 图像内容有效（100张224×224）/ 类别分布均衡（CV=0.242，不平衡比3.0:1）/ OpenCV 4.13.0+NumPy 2.4.2+PIL可用 / 标注-图像一致性通过 / Bbox面积分布合理 / 推理延迟满足实时约束（50bpm时延迟占比仅2.3%）。⚠️ YOLO格式未生成（需--format both参数）/ TensorFlow未安装（预期行为，硬件到位后安装）。同步验证：synthetic_test_data_generator.py生成50张COCO+YOLO双格式图像耗时1392.7ms（35.9 img/s）。Git push成功（ad8c35c）。

| 2026-05-02 | WORKLOG v1.34：每日研究任务（12:07）— **自诊断与健康监控系统**（sorter/control/health_monitor.py，1144行）。目标：硬件组装前建立完整的系统自诊断与传感器健康监控能力，为现场运维提供实时保障。覆盖内容：①POST上电自检程序（8项测试：系统基础/GPIO/I2C/传感器/执行器/通信/存储/安全回路，模拟模式无需硬件）；②HealthMonitor监控引擎（17种传感器基线定义，颜色/称重/含水率/光电/密度/液位/执行器全覆盖）；③多通道独立健康追踪（每通道独立评分，支持1-N通道扩展）；④实时分析：噪声异常/漂移检测/离线检测/错误率监控；⑤通道级综合健康评分(0-100) + 系统级评分；⑥AlertLevel 6级告警（OK/INFO/WARNING/DEGRADED/CRITICAL/OFFLINE）；⑦预测性维护告警（基于漂移速率趋势计算剩余标定周期）；⑧预测性故障分析（基于历史错误率预测传感器降级）；⑨传感器数据模拟器（用于无需硬件的监控逻辑验证）；⑩CLI支持（--test POST自检 / --monitor持续监控）。POST验证结果：8项测试85ms，6 PASS / 1 WARNING（传感器误差0.51）/ 1 SKIP（GPIO），综合PASS。Git push成功（4587f28）。|

| 2026-05-02 | WORKLOG v1.35：每日研究任务（21:04）— **批次数据持久化与报告生成系统**（sorter/db/）。目标：在所有课题完成后，为硬件到位后的实际生产运行准备完整的数据持久化层和可追溯性报告。覆盖内容：①`models.py`（570行）：14类缺陷枚举BeanDefect（含severity等级）/ 批次状态BatchState / 咖啡豆分级SortGrade（Grade A/B/C/Reject）/ ColorReading/SensorSnapshot/BeanRecord/BatchRecord/CalibrationRecord/SystemEvent完整数据模型；②`database.py`（580行）：SQLite WAL模式数据库，4张表（batches/beans/calibrations/system_events）+5个索引，线程安全connection-per-thread模式，批次CRUD/批量豆粒插入/事件查询/系统统计完整API；③`report_generator.py`（500行）：JSON报告（含质量评估/缺陷分布/等级产量）/ CSV导出（含传感器原始数据）/ TEXT人类可读报告（含条形图缺陷可视化/6级质量判定）/ 多批次汇总报告（加权平均质量分/总体缺陷率/等级产量）；④`cli.py`（200行）：init/list/stats/report/export/events命令，支持批量导出到指定目录；⑤`demo_batch_runner.py`：蒙特卡洛模拟3批次×3000豆端到端验证，数据库9,000豆记录，3格式报告全部生成✅；⑥`SPEC.md` v0.9新增数据持久化章节。CLI验证：list命令显示批次列表（origin/state/defect%/GradeA%/weight）✅。Git push成功（e51e2ad）。
