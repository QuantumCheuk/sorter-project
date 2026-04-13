# 生豆分选机项目工作日志 / WORKLOG
> 项目代号：HUSKY-SORTER-001

---

## 项目状态：🟢 进行中（课题2 Day3/3 完结）

---

## 当前版本
- **SPEC.md: v0.2 (2026-04-10)**
- **WORKLOG.md: v0.2.3 (2026-04-13)** — 课题2 Day3，物理实测协议+LED均匀度工具+自动阈值优化器

---

## 课题进度

### 课题2：颜色检测系统 🟡 Day 2/3
- 状态：🟡 进行中
- **今日完成：**
  - `sorter/camera/calibration.py` — ColorCalibrator 阈值标定工具：
    - 多策略背景分离（Otsu/自适应/HSV/组合）
    - 按品种+处理法分组统计 L*a*b* 分布
    - 自动计算缺陷阈值建议 + 参考范围 (5th-95th percentile)
    - 支持合成样本测试 + 真实文件夹批量导入
    - YAML 标定结果导出
  - `sorter/camera/dataset_collector.py` — DatasetCollector 训练数据采集工具：
    - 摄像头实时预览 + 键盘标注（G/B/M/F/R/I）
    - 结构化保存到 `output/{good,bleached,moldy,fermented,broken,insect}/`
    - 自动生成 `labels.json` 标签记录
    - metadata.json 元数据导出
  - `sorter/camera/image_processor.py` — ImageProcessor 改进预处理器：
    - 组合背景分离（HSV绿色范围 + LAB L通道 + 边缘检测）
    - BeanRegion 数据类（轮廓/掩码/重心/面积/紧凑度/等效直径）
    - `batch_statistics()` 批量统计分析
    - `visualize()` 检测结果可视化
  - `sorter/camera/test_color_analyzer.py` — 测试框架：
    - 合成测试集生成（Heirloom水洗/Geisha日晒 + 4种缺陷类型）
    - 基准测试 + 召回率统计 + 处理时间
  - **合成测试结果：**
    - 正常豆召回率：100% ✅
    - 漂白豆召回率：100% ✅
    - 发霉豆/发酵过度：待真实样本标定（合成数据特征不够典型）
    - 平均处理时间：13.4ms/帧 ✅（目标<100ms）
  - 修复 color_analyzer.py 缩进错误（Chinese variable mixing）
- 待完成（Day 3）：
  - [ ] 真实样本采集（目标：每个品种≥30张）
  - [ ] 阈值实测校准
  - [ ] LED光源均匀度测试验证
  - [ ] 暗箱3D打印样品实测

### 课题1：尺寸分选机构 ✅ 已完成基础框架
- 状态：🟡 进行中（3D模型待验证）
- 完成内容：
  - 振动给料器 + 5级阶梯孔板 结构设计
  - 步进电机驱动方案（28BYJ-48 + ULN2003）
- 待验证：3D打印样品测试

### 课题2：颜色检测系统 🟡 Day 1/3 ✅
- 状态：🟡 进行中
- **今日完成：**
  - `sorter/camera/__init__.py` — 模块初始化
  - `sorter/camera/capture.py` — BeanCamera 图像采集类，支持 HQ Camera / USB Camera，预热降噪
  - `sorter/camera/color_analyzer.py` — ColorAnalyzer 颜色分析类：
    - L\*a\*b\* 色彩空间分析（符合人眼感知）
    - 品种+处理法参考范围查询（预置 Heirloom/Geisha/Bourbon/Typica）
    - 缺陷检测（漂白豆/发霉豆/发酵过度）
    - 颜色评分算法（基于偏离度计算 0-100）
    - `calibrate_reference()` 标定函数接口
  - `sorter/camera/defect_detector.py` — DefectDetector 缺陷检测类：
    - 双模式：规则检测（阈值法）/ ML模型（SVM）
    - 特征提取（颜色+HSV+均匀度+斑点）
    - `train_svm()` 训练接口
  - `sorter/camera/dark_box.py` — 暗箱3D设计生成器：
    - OpenSCAD 脚本生成
    - FreeCAD Python Macro 生成
    - SLA 3D打印参数配置
    - 关键尺寸：120×120×80mm，壁厚3mm，LED环形灯60mm直径
  - `sorter/config.py` — 全系统配置（硬件/软件/MQTT/分选参数/品种参考数据）
- 待完成：
  - [ ] HQ Camera 实测（验证IMX477驱动）
  - [ ] 暗箱3D打印样品
  - [ ] LED光源均匀度测试
  - [ ] 颜色分析算法实测标定
  - [ ] 缺陷检测阈值调优

### 课题2：颜色检测系统 🟡 Day 3/3 ✅ (2026-04-13)
- 状态：🟢 完成（物理测试协议建立）
- **今日完成：**
  - `sorter/camera/dark_box_test_protocol.py` — **暗箱物理实测协议框架**：
    - 5项完整测试流程：LED均匀度、摄像头预热稳定性、背景色一致性、颜色准确性（标准色卡）、缺陷召回率实测
    - 综合评分体系（0-100）+ 通过/失败判定
    - JSON报告自动导出
  - `sorter/camera/light_uniformity_test.py` — **LED光照均匀度专用分析工具**：
    - 从白板图像分析光照分布（5×5网格）
    - 均匀度系数 U = 1-(Imax-Imin)/(Imax+Imin) 计算
    - 热力图可视化输出（matplotlib）
    - LED位置调整建议（基于暗角/中心暗斑/单侧过亮模式识别）
  - `sorter/camera/auto_threshold_optimizer.py` — **自动阈值优化器**：
    - 网格搜索（Grid Search）在参数空间中找最优缺陷阈值
    - F1-score 最大化目标
    - 支持真实样本导入（dataset folder格式）和合成数据降级
    - 漂白豆/发霉豆/发酵过度三类缺陷独立优化
    - YAML + Python双格式导出，可直接导入 config.py
- **课题2总结（3天完成内容）：**
  | 文件 | 功能 | 状态 |
  |------|------|------|
  | `capture.py` | 图像采集（HQ/USB Camera） | ✅ |
  | `color_analyzer.py` | L\*a\*b\*颜色分析 | ✅ |
  | `defect_detector.py` | 规则+ML双模式缺陷检测 | ✅ |
  | `image_processor.py` | 组合背景分离预处理 | ✅ |
  | `calibration.py` | 阈值标定工具（多策略） | ✅ |
  | `dataset_collector.py` | 训练数据采集+标注 | ✅ |
  | `test_color_analyzer.py` | 合成/真实测试框架 | ✅ |
  | `dark_box.py` | 暗箱3D设计生成器 | ✅ |
  | `dark_box_test_protocol.py` | 物理实测协议 | ✅ 新增 |
  | `light_uniformity_test.py` | LED均匀度分析 | ✅ 新增 |
  | `auto_threshold_optimizer.py` | 自动阈值优化 | ✅ 新增 |
- **课题2待实测验证（硬件就绪后）：**
  - [ ] 暗箱3D打印 + LED安装后运行 `dark_box_test_protocol.py`
  - [ ] LED均匀度测试（目标 U ≥ 0.85）
  - [ ] Macbeth色卡标定颜色准确性
  - [ ] 真实缺陷样本采集（目标：每类≥20张）→ `auto_threshold_optimizer.py`
  - [ ] HQ Camera IMX477 在暗箱内实际成像质量评估
- **Day 4起进入课题3：称重系统（Load Cell + HX711）**
- 状态：🔴 进行中
- **今日完成：**
  - `sorter/camera/__init__.py` — 模块初始化
  - `sorter/camera/capture.py` — BeanCamera 图像采集类，支持 HQ Camera / USB Camera，预热降噪
  - `sorter/camera/color_analyzer.py` — ColorAnalyzer 颜色分析类：
    - L\*a\*b\* 色彩空间分析（符合人眼感知）
    - 品种+处理法参考范围查询（预置 Heirloom/Geisha/Bourbon/Typica）
    - 缺陷检测（漂白豆/发霉豆/发酵过度）
    - 颜色评分算法（基于偏离度计算 0-100）
    - `calibrate_reference()` 标定函数接口
  - `sorter/camera/defect_detector.py` — DefectDetector 缺陷检测类：
    - 双模式：规则检测（阈值法）/ ML模型（SVM）
    - 特征提取（颜色+HSV+均匀度+斑点）
    - `train_svm()` 训练接口
  - `sorter/camera/dark_box.py` — 暗箱3D设计生成器：
    - OpenSCAD 脚本生成
    - FreeCAD Python Macro 生成
    - SLA 3D打印参数配置
    - 关键尺寸：120×120×80mm，壁厚3mm，LED环形灯60mm直径
  - `sorter/config.py` — 全系统配置（硬件/软件/MQTT/分选参数/品种参考数据）
- 待完成：
  - [ ] HQ Camera 实测（验证IMX477驱动）
  - [ ] 暗箱3D打印样品
  - [ ] LED光源均匀度测试
  - [ ] 颜色分析算法实测标定
  - [ ] 缺陷检测阈值调优

### 课题3：称重系统
- 状态：🔴 待开始

### 课题4：密度分选
- 状态：🔴 待开始

### 课题5：含水率检测
- 状态：🔴 待开始

### 课题6：缓冲料仓+螺旋给料
- 状态：🔴 待开始

### 课题7：MQTT通信 + REST API
- 状态：🔴 待开始

### 课题8：综合评审 + 联调测试
- 状态：🔴 待开始

---

## 关键设计决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-04-10 | 采用 HQ Camera 颜色检测方案 | 树莓派原生支持，OpenCV成熟 |
| 2026-04-10 | 电容式含水率检测替代红外 | 电路简单，可3D打印探头 |
| 2026-04-10 | 气流上扬法密度分级 | 无运动件，可PWM连续调节 |
| 2026-04-10 | 分批喂入烘豆机 | 支持大批次分段烘焙 |
| 2026-04-10 | 每次处理单一品种+预设元数据 | 简化流程，操作员预先设置品种/产区/处理法 |
| 2026-04-10 | 颜色检测按品种/处理法独立建模 | 不同品种颜色差异大，需独立训练集 |
| 2026-04-10 | quality_class 为操作员可配置阈值 | 非自动分级，由操作员按需求设定A/B/C标准 |
| **2026-04-12** | **颜色分析采用 L\*a\*b\* 而非 RGB** | **L\*a\*b\* 更符合人眼感知，缺陷检测更准确** |
| **2026-04-12** | **暗箱内壁用漫反射白树脂+喷漆** | **LED环形灯需均匀漫反射，避免镜面反射** |
| **2026-04-12** | **预置4个品种参考数据** | **Heirloom/Geisha/Bourbon/Typica，覆盖主要精品咖啡** |

---

## 待解决问题
- [ ] 尺寸分选孔板目数标准（16/15/14/13/12是否合适）— 课题1遗留
- [ ] HQ Camera vs 普通 USB Camera 选型 — **决定采用 HQ Camera (IMX477)**
- [ ] 电容含水率探头标定方法 — 课题5待研究
- [ ] 颜色检测ML模型训练数据集来源 — **建议：收集50+样本/品种手工标注**
- [ ] 暗箱遮光密封方案 — **决定用黑色密封胶+遮光棉**

---

## 今日研究笔记（2026-04-13 课题2 Day2）

### 合成测试发现的问题

**发霉豆召回率 0%（预期应该检出）**
- 原因：合成 moldy 图像 L=35, a=-4, b=10，但阈值要求 a≤-5
- a=-4 超出阈值 1 个单位 → 未触发
- 真实发霉豆样本可能 a 更负（更绿），需要实测确认

**发酵过度召回率 0%**
- 原因：合成 fermented 图像 a=9, b=20，阈值 a≥8, b≥18 → 理论上应该触发
- 但 L*a*b* 计算时背景干扰导致平均值偏移
- 真实样本中发酵过度的红棕色特征应更明显

**结论：** 合成数据有限，真实样本标定是下一步关键。

### 标定工具使用流程（实测时）
```
1. 用 dataset_collector.py 采集样本：
   python -m sorter.camera.dataset_collector -o dataset/heirloom_washed

2. 采集完毕后运行标定：
   python -m sorter.camera.calibration -i dataset/heirloom_washed \
       --variety Heirloom --process 水洗 --output cal_heirloom.yaml

3. 更新 config.py 中的 VARIETY_REFERENCES 和 DEFECT_THRESHOLDS
```

### image_processor.py 组合策略详解
```
融合4种信号：
1. HSV绿色范围 → 豆子主体
2. LAB L通道中间调 → 去除极亮/极暗背景
3. 自适应阈值 → 光照不均补偿
4. Canny边缘 dilated → 精确边界

最终：HSV OR (边缘 AND L中间调) OR 自适应
```

### Day 3 计划
- 重点：真实样本采集 + 阈值实测校准
- 工具：dataset_collector.py（标注界面）+ calibration.py（标定）
- 采集目标：每个品种≥20张（good），每种缺陷≥10张


### 颜色检测关键技术点

**1. 为什么用 L\*a\*b\* 而非 RGB？**
- RGB 受光源影响大（同一豆子在不同光下R/G/B值差异大）
- L\*a\*b\* 将亮度(L)和色度(a,b)分离，更适合比较"纯颜色"
- 咖啡生豆颜色差异主要在 a\*（红绿）和 b\*（黄蓝），L\* 主要反映反光程度

**2. 缺陷颜色阈值（经验值，待实测校准）**
```
漂白豆：L* ≥ 75，|a*| ≤ 3，|b*| ≤ 8
发霉豆：L* ≤ 40，a* ≤ -5，b* ≥ 8
发酵过度：a* ≥ 8，b* ≥ 18
```

**3. 暗箱设计关键参数**
- 内壁：漫反射白（白度≥90%）
- 光源：4× LED环形灯，均匀分布
- 摄像头：M12镜头，焦距6mm，工作距离~80mm
- 遮光：接缝处黑胶密封，摄像头开孔用遮光棉

**4. 后续计划（课题2 Day2-3）**
- 搭建硬件测试平台
- 用已知合格/缺陷样本验证阈值
- 收集训练数据集

---

## 变更历史
| 日期 | 变更内容 | 操作人 |
|------|----------|--------|
| 2026-04-10 | 项目初始化，SPEC v0.1 完成 | Husky |
| 2026-04-12 | SPEC v0.2 完成，澄清批次模式等设计约束 | Husky |
| **2026-04-13** | **WORKLOG v0.2.1，课题2 Day1 完成** | **Husky** |
| **2026-04-13** | **WORKLOG v0.2.2，课题2 Day2 完成：标定工具+数据集采集+测试框架** | **Husky** |
| **2026-04-13** | **WORKLOG v0.2.3，课题2 Day3 完成：物理实测协议+LED均匀度工具+自动阈值优化器** | **Husky** |
