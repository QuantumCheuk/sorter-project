# 生豆分选机每日研究任务 / Daily Research Task

## 任务说明
每天每3小时（0 */3 * * * GMT+8）自动执行研究循环，直至设计达到"合格"等级。

**注意：** isolated session push 前需确保 git 已配置 user.name/user.email。

## ⚙️ 路径自检 + 自修复（每次任务启动时自动执行）

任务启动时自动运行以下逻辑，修复路径问题：

```
1. 定义工作区根目录
   WORKSPACE = ~/.openclaw/workspace

2. 搜索 sorter-project 目录（向上搜索防止目录迁移）
   搜索顺序：
   a) WORKSPACE/../sorter-project/
   b) WORKSPACE/../Projects/sorter-project/
   c) 向上最多2层

3. 验证关键文件，找到真实路径后：
   - WORKLOG.md  ← 在 sorter-project/ 下
   - SPEC.md     ← 在 sorter-project/ 下
   - sorter/     ← 在 sorter-project/ 下

4. 若发现路径与任务脚本不符，自动修正：
   - 重写 DAILY_TASK.md 中的路径引用
   - 记录到 memory/YYYY-MM-DD.md

5. 验证失败时的处理：
   - SPEC.md 不存在 → 警告并跳过读取步骤
   - WORKLOG.md 不存在 → 创建空白文件
   - 多次失败 → 通知 Master Puppy
```

## 执行模式
1. 读取 `sorter-project/WORKLOG.md` 了解当前进度
2. 读取 `sorter-project/SPEC.md` 当前版本和对标差距
3. 确定当日重点课题（轮换制）
4. 执行研究/仿真/改进
5. 更新 `sorter-project/WORKLOG.md`
6. 记录到 `memory/YYYY-MM-DD.md`

## 课题轮换表（每课题 ≥ 3天验证）

### 第1轮：尺寸分选机构（Day 1-3）
- 目标：设计振动给料器 + 5级阶梯孔板
- 工具：FreeCAD + 3D打印
- 输出：STEP文件 + 3D打印参数

### 第2轮：颜色检测系统（Day 4-6）
- 目标：暗箱设计 + Camera + 颜色分析算法
- 工具：Python OpenCV + Raspberry Pi HQ Camera
- 输出：颜色检测算法 + 暗箱3D模型

### 第3轮：称重系统（Day 7-9）
- 目标：Load Cell + HX711 + Python 标定
- 工具：Python + HX711库 + 标定脚本
- 输出：称重精度报告

### 第4轮：密度分选（Day 10-12）
- 目标：气流上扬通道设计 + PWM调速
- 工具：CFD理论计算 + 实验
- 输出：密度分级参数

### 第5轮：含水率检测（Day 13-15）
- 目标：电容探头设计 + 标定曲线
- 工具：电子学 + Python标定
- 输出：含水率标定曲线

### 第6轮：缓冲料仓+螺旋给料（Day 16-18）
- 目标：8格缓冲仓 + 螺旋给料分批控制
- 工具：步进电机 + PID控制
- 输出：分批控制逻辑

### 第7轮：MQTT通信 + REST API（Day 19-21）
- 目标：MQTT client → 烘豆机接口 + Flask REST API
- 工具：paho-mqtt + Flask
- 输出：MQTT消息格式 + API端点

### 第8轮：综合评审 + 联调测试（Day 22-24）
- 目标：汇总所有验证结果，对标SPEC评分
- 工具：综合计算 + 联调
- 输出：完整设计评审报告

## 质量门控
每次迭代必须：
- [ ] 有具体数据支撑（计算/仿真/实验）
- [ ] 引用SPEC中的量化指标
- [ ] 记录到 sorter-project/WORKLOG.md
- [ ] 若发现更好的方案，更新 sorter-project/SPEC.md 并标注变更原因

## 停止条件
当总分达标时：
1. 生成完整3D模型包
2. 生成采购清单（含型号、数量、参考价）
3. 通知 Master Puppy
