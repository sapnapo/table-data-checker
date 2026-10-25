# 表格数据检查与简报生成助手 — 开发方案（spec.md）

> 版本：v1.0（待确认）
> 场景：报名表 / 签到表的整理与简报生成，**单一场景工具，不做通用 BI 平台**

---

## 1. 项目概述

### 1.1 背景与用户

班委 / 行政助理需要整理报名表、签到表（CSV 或 XLSX），手工查找重复报名、漏填、手机号写错等问题费时且易漏。本工具一次性完成：**上传 → 选列 → 质量检查 → 统计 → 图表 → 简报 → 导出**。

### 1.2 目标

| 目标 | 说明 |
|---|---|
| 数据质量检查 | 缺失 / 重复 / 格式错误三类问题，精确定位到"表格行号 + 列"，逐条给出原因 |
| 统计简报 | 自动计算总人数、分组人数与占比，生成模板化文字简报 |
| 安全 | 原始文件永远只读；所有产出均为新文件（清洗副本 / 简报 / 图表） |
| 鲁棒 | 任何单个脏单元格、坏行、坏文件都不会导致程序崩溃，只降级为"问题项"或友好提示 |

---

## 2. 范围与边界

### 2.1 v1 范围内

- CSV / XLSX（默认读取**第一个 sheet**，假设**第 1 行为表头**）
- 固定 5 种列角色：姓名 / 学号 / 手机号 / 日期 / 分组（班级或部门），用户在 UI 中映射
- 必填缺失、按学号查重、手机号格式、日期格式四类规则
- 总数、单分组列的人数与占比统计、柱状图、Markdown 简报
- 导出：清洗副本 XLSX（双 sheet：有效数据 + 被剔除明细）、简报 .md、图表 .png

### 2.2 v1 范围外（明确不做）

- 多 sheet 合并、表头不在首行的智能识别
- 多分组列交叉统计 / 透视表 / 通用 BI 能力
- 可自定义正则的"规则引擎"（规则硬编码于 `config.py`）
- 数据库存储、用户系统、部署运维（本地单机工具）
- 自动修复脏数据（只报告 + 剔除，不猜测改写用户数据）

---

## 3. 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 交互形态 | **Streamlit Web 应用**（已与需求方确认） | 纯 Python 全栈；上传 / 表格预览 / 下拉选列 / 图表 / 下载全为内置组件；本地 `streamlit run app.py` 即用，开发量最小 |
| 数据处理 | pandas 2.x | 向量化校验，1000 行毫秒级 |
| Excel 读写 | openpyxl | pandas 引擎，读写 XLSX |
| 图表 | matplotlib | 柱状图够用，可同时渲染到页面与 PNG |
| 测试 | pytest | 核心层全单测；UI 层手工验收 |
| Python | ≥ 3.9 | 适配 pandas 2.x |

依赖清单（`requirements.txt`）：

```
streamlit>=1.30
pandas>=2.0
openpyxl>=3.1
matplotlib>=3.7
# dev
pytest>=7.4
```

---

## 4. 总体架构与数据流

三层架构：**UI 层（app.py）→ 编排即 UI 流程 → 核心领域层（纯函数，无 Streamlit 依赖）**。核心层每个模块可独立单测。

```
用户上传文件 ──▶ loader ──▶ DataFrame + 列名列表
                                  │
用户映射列角色 ──▶ models.ColumnRoles
                                  │
              ──▶ validator ──▶ QualityReport（问题清单 + 有效行索引 + 剔除行索引及原因）
                                  │
              ──▶ analyzer ──▶ StatsResult（总数 / 去重数 / 分组统计）
                                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
    charting    reporter   exporter
    （柱状图）  （简报文案） （清洗副本 XLSX / 简报 md / 图表 png → 下载）
```

**UI 状态管理**：解析结果与列角色存入 `st.session_state`，避免任一控件交互导致重新上传 / 重新选择；"开始检查"按钮触发一次全流程并把结果写回 session_state。

---

## 5. 文件结构

```
/workspace
├── spec.md                      # 本方案
├── requirements.txt
├── app.py                       # Streamlit 入口：UI 编排（唯一依赖 streamlit 的文件）
├── src/
│   ├── __init__.py
│   ├── config.py                # 列角色枚举、校验正则、文案模板、字体候选表
│   ├── models.py                # 数据结构：ColumnRoles / Issue / QualityReport / StatsResult
│   ├── loader.py                # 文件加载：格式分流、编码探测、异常包装
│   ├── validator.py             # 四类质量检查（向量化 + 逐单元格容错）
│   ├── analyzer.py              # 统计：口径计算、分组计数与占比
│   ├── charting.py              # 柱状图绘制（中文字体运行时探测）
│   ├── reporter.py              # 简报 Markdown 生成
│   └── exporter.py              # 清洗副本 XLSX / 简报 / PNG 导出（内存中生成，供下载）
├── tests/
│   ├── conftest.py              # 公共 fixture：内存构造脏数据 DataFrame / BytesIO 文件
│   ├── test_loader.py
│   ├── test_validator.py
│   ├── test_analyzer.py
│   ├── test_reporter.py
│   └── test_exporter.py
└── sample_data/
    └── make_sample.py           # 生成含各类错误的示例报名表（手工验收用）
```

---

## 6. 核心数据结构（`src/models.py` 契约）

```python
@dataclass
class ColumnRoles:
    """用户在 UI 中完成的列角色映射；None 表示未选用该角色"""
    name: str | None        # 姓名列（若选用则必填校验）
    student_id: str | None  # 学号列（必填 + 唯一性查重依据）
    phone: str | None       # 手机号列（必填性由 phone_required 控制）
    phone_required: bool
    date: str | None        # 日期列（必填性由 date_required 控制）
    date_required: bool
    group: str | None       # 分组列（班级/部门，仅统计用，空值归入"未填写"）

@dataclass
class Issue:
    row_excel: int          # 表格行号（表头=第1行，首条数据=第2行），文件级问题为 -1
    column: str             # 列名
    issue_type: str         # MISSING / DUPLICATE / PHONE_FORMAT / DATE_FORMAT / INTERNAL
    value: str              # 原始值（截断至 50 字符，防止超长内容）
    message: str            # 人话原因，如"手机号不足 11 位"

@dataclass
class QualityReport:
    issues: list[Issue]     # 全部问题，按 row_excel 升序
    valid_indices: list[int]     # 通过全部校验的 DataFrame 行索引
    removed_count: int      # 被剔除行数（缺失/格式错误/重复组的后续行）

@dataclass
class StatsResult:
    total_submitted: int    # 提交总行数（原始数据行，含问题行，不含全空行）
    total_valid: int        # 有效记录数（QualityReport.valid_indices 去重后）
    duplicate_removed: int  # 因重复被剔除的行数
    error_removed: int      # 因缺失/格式错误被剔除的行数
    group_table: pd.DataFrame  # 列：组别 / 人数 / 占比(%)，按人数降序
```

---

## 7. 模块设计

### 7.1 `loader.py` — 文件加载

- 入口：`load_table(file_name: str, file_bytes: bytes) -> tuple[pd.DataFrame, str]`（返回 DataFrame 与实际编码/格式说明）
- 分流：后缀 `.xlsx` → `pd.read_excel`；`.csv` → 编码探测
- **CSV 编码探测**：依次尝试 `utf-8-sig → gb18030`，均抛 `UnicodeDecodeError` 则返回友好错误（提示"请用 Excel 另存为 xlsx 后重试"），不崩溃
- **列名清洗**：`df.columns = df.columns.str.strip()`，去重列名（重名列自动加后缀 `.1`，pandas 默认行为，UI 选择器中会显示后缀）
- **行保持原则**：不删除任何数据行（保证行号对齐 Excel）；仅将 `df.replace(r'^\s+$', np.nan)` 把纯空白单元格归一为缺失
- 全空行**不删除**，由 validator 标记 `INTERNAL: 整行为空`并跳过其余检查，analyzer 排除出统计
- 异常包装：空文件、损坏文件、非二维表 → 抛 `LoadError`（自定义异常，app.py 捕获后 `st.error` 展示）

### 7.2 `validator.py` — 质量检查（核心）

入口：`validate(df: pd.DataFrame, roles: ColumnRoles) -> QualityReport`

**行号换算规则（全工具唯一口径）**：

```
Excel/表格行号 = DataFrame 行索引 + 2      （第 1 行为表头，首条数据在第 2 行）
```

四类检查（顺序执行，前一类的剔除结果参与后续统计）：

| # | 检查 | 规则 | 输出 issue_type |
|---|---|---|---|
| 1 | 必填缺失 | 角色列选用了姓名/学号（必选必填）+ 按开关的 phone/date；值为 NaN 或空串 | `MISSING` |
| 2 | 重复 | 按 student_id 列分组（strip 后比较，空值不参与查重）；同值 ≥2 行为一组，每组保留行号最小的一条，其余行标记 | `DUPLICATE`（message 含"与第 X 行重复"） |
| 3 | 手机号格式 | `str(value).strip()` 匹配 `^1\d{10}$`（11 位、1 开头、纯数字；中间含空格/横线即报错） | `PHONE_FORMAT` |
| 4 | 日期格式 | 正则 `^\d{4}-\d{2}-\d{2}$` + `datetime.strptime` 双重校验（拦截 `2025-02-30` 这类假日期）；Excel 自动转成 datetime 的单元格视为合法，输出时统一为 `YYYY-MM-DD` | `DATE_FORMAT` |

**有效行定义**：未被任何 Issue 标记，且非全空行 → 进入 `valid_indices`。

**容错策略（硬性要求）**：
- 所有检查先做 pandas 向量化批量计算（满足性能），对每条可疑单元格的"取值与字符串化"再逐条 `try/except`
- 单条单元格转换异常 → 记 `INTERNAL` Issue（message 记异常摘要），**绝不向上抛**
- validator 顶层再套一层 try/except 兜底，任何未预见异常转成文件级 Issue 而非崩溃

### 7.3 `analyzer.py` — 统计

入口：`analyze(df, roles, report: QualityReport) -> StatsResult`

**统计口径（歧义消解，简报文案直接引用）**：

| 指标 | 口径 |
|---|---|
| 提交总数 `total_submitted` | 原始数据行数（含问题行，排除全空行）— 对应简报"共收到 N 份报名" |
| 有效记录数 `total_valid` | `valid_indices` 对应行数（已通过校验且去重）— 分组统计的数据基础 |
| 分组人数 | 对有效记录按 group 列计数；空值归入"未填写"组 |
| 占比 | 组人数 ÷ `total_valid` × 100，四舍五入保留 **1 位小数**；各组占比之和可能因舍入≠100%，属预期，不做强行配平 |

### 7.4 `charting.py` — 柱状图

- 入口：`bar_chart(group_table: pd.DataFrame, title: str) -> matplotlib.figure.Figure`
- **中文字体运行时探测**：按候选表 `SimHei / Microsoft YaHei / Noto Sans CJK SC / WenQuanYi Zen Hei / PingFang SC` 查询系统可用字体，命中则设 `rcParams['font.sans-serif']` 并关闭负号转义；**全部未命中 → 图表标签回退为英文**（组名替换为 `G1..Gn`，标题附英文），并在页面 `st.warning` 提示"系统缺少中文字体"
- 分组数 > 15 时自动横向条形图，避免 x 轴标签挤压

### 7.5 `reporter.py` — 简报生成

入口：`build_report(file_name: str, stats: StatsResult, report: QualityReport) -> str`（Markdown 文本）

模板结构（文案模板集中放 `config.py`）：

```
# 报名数据简报 — {文件名}
生成时间：{YYYY-MM-DD HH:MM}

## 一、总览
本次共收到 {total_submitted} 份报名，其中有效记录 {total_valid} 份
（剔除重复 {duplicate_removed} 份、缺失/格式错误 {error_removed} 份）。

## 二、分组统计
| 组别 | 人数 | 占比 |
|---|---|---|
| A班 | 40 | 42.1% |
（按人数降序；示例句式：其中 A 班 40 人，占比 42.1%）

## 三、数据质量摘要
共发现 {len(issues)} 处问题：缺失 X 处、重复 Y 处、格式错误 Z 处。
问题明细（前 20 条，完整清单见清洗副本"被剔除明细"页）：
- 第 14 行 [手机号] "12345678"：手机号不足 11 位
```

### 7.6 `exporter.py` — 导出

- 入口：
  - `export_cleaned(df, report, roles, original_name) -> bytes`（XLSX 字节流）
  - `export_report_md(md_text, original_name) -> bytes`
  - `export_chart_png(fig, original_name) -> bytes`
- **清洗副本 XLSX = 双 sheet**：
  - Sheet1 `有效数据`：`valid_indices` 的原始行，**不修改任何单元格值**（日期列只统一显示格式不改底层值）
  - Sheet2 `被剔除明细`：被剔除行 + 追加"剔除原因"列
- 文件命名：`{去后缀原名}_cleaned.xlsx` / `{原名}_简报.md` / `{原名}_柱状图.png`
- 全部在内存（BytesIO）生成，经 `st.download_button` 提供下载；**磁盘上不落任何文件，更不触碰原始文件**
- 有效数据为空时：不提供清洗副本下载按钮，改为提示"无有效记录可供导出"

### 7.7 `app.py` — UI 流程（单页五步）

```
Step1 上传    st.file_uploader(type=["csv","xlsx"]) → loader → st.error/st.success
Step2 预览    st.dataframe(df.head(5))；显示"共 N 行 × M 列、实际编码"
Step3 选列    5 个 st.selectbox（选项=列名+“不使用此角色”）；手机号/日期各配"允许为空"开关；
              姓名/学号列未选时给出提醒（允许继续分析，仅警告）；点【开始检查与分析】触发 Step4
Step4 结果    st.metric 指标卡×4（提交总数/有效/重复剔除/错误剔除）
              → 问题明细 st.dataframe（行号/列/类型/原因/原值，可排序）
              → 分组统计表 → st.pyplot(柱状图)
Step5 导出    简报 Markdown 预览（st.markdown）+ 三个 st.download_button
```

- 结果对象存 `st.session_state`，切换控件不丢失已上传文件与已映射角色
- 每个阶段错误就地 `st.error` 展示并允许重新上传，**任何路径不退出程序**

### 7.8 `config.py` — 常量集中

列角色显示名、手机号/日期正则、字体候选表、简报文案模板、Issue 类型 → 中文名映射（缺失/重复/格式错误/内部异常）。规则修改只动此文件。

---

## 8. 非功能实现方案

### 8.1 性能（1000 行 ≤ 5 秒）

| 阶段 | 预算 |
|---|---|
| 文件解析（pandas 读入） | < 1s |
| 校验（向量化：isna / duplicated / str.match） | < 200ms |
| 统计 + 图表 + 简报 + 导出 | < 1s |
| Streamlit 渲染 | < 1s |

瓶颈在 IO 与渲染，核心计算全部向量化；验收用 1000 行 × 8 列样例实测。

### 8.2 鲁棒性矩阵

| 异常场景 | 行为 |
|---|---|
| 非 csv/xlsx 后缀 | 上传组件直接过滤 + 提示 |
| CSV 编码不可识别 | st.error 提示转存 xlsx，可重新上传 |
| 空 / 损坏 / 非二维表 | LoadError → st.error，不崩溃 |
| 单元格类型怪异（数字学号、日期列为文本等） | 字符串化失败 → INTERNAL Issue，继续处理 |
| 超长 / 含换行 / 特殊字符单元格 | Issue.value 截断 50 字符；表格渲染转义由 Streamlit 处理 |
| 全空行 | 跳过检查与统计，不报错 |
| 有效记录为 0 | 提示，隐藏导出按钮 |
| 任何未预见异常 | app.py 顶层 try/except → st.error 展示摘要 + 可重新开始 |

### 8.3 数据安全

- 原始上传文件全程只读（内存字节流），不写回、不覆盖、不落盘
- 所有导出物均为新生成的独立字节流，命名带 `_cleaned` / `_简报` / `_柱状图` 后缀
- 不引入任何网络上传：纯本地运行

---

## 9. 测试方案

**原则：核心层（src/*）100% 纯函数，全部用内存数据单测，不依赖磁盘样例文件。**

| 测试文件 | 关键用例 |
|---|---|
| test_loader | xlsx 正常读 / utf-8 CSV / gbk CSV / 编码失败返回友好错误 / 空文件 / 列名去空格 / 行数保持 |
| test_validator | 各类缺失 / 学号重复组（保留首行）/ 手机号 10 位、12 位、含横线、非 1 开头 / 日期 `2025-02-30`、`2025/01/01`、Excel datetime 合法 / **行号=索引+2 断言** / 单个怪异单元格不抛异常 / 全空行跳过 |
| test_analyzer | 口径互斥完备（总数=有效+重复剔除+错误剔除；全空行不计入四数任何一项）/ 占比 1 位小数 / 空分组归"未填写" / 无分组列时只出总数 |
| test_reporter | 模板句式含"共收到 N 份报名"与"占比 X%" / 空数据不出分组表 / 问题明细上限 20 条 |
| test_exporter | 双 sheet 结构与内容 / 有效为空时的行为 / 原始 DataFrame 未被修改（防副作用断言） |

**验收样例**：`sample_data/make_sample.py` 生成 1000 行 × 8 列、含 5% 各类错误的 `报名示例.xlsx`，用于手工跑通全流程 + 性能实测。

**UI 层**：不做自动化测试，提供手工验收清单（见 §10）。

---

## 10. 验收标准

1. `pytest` 全部通过
2. 用 1000 行样例实测：上传 → 简报导出全流程 ≤ 5 秒
3. 用 Excel 打开样例文件人工核对：问题清单中的"表格行号"与 Excel 中肉眼所见行号**逐条一致**
4. 样例中植入的每一处错误（缺失/重复/手机号/日期）全部被检出，无误报
5. 记录上传前后原始文件哈希一致（只读验证）
6. 逐项尝试鲁棒性矩阵场景，全程无堆栈、无崩溃

---

## 11. 实施顺序（确认后执行）

1. `models.py` + `config.py`（契约先行）
2. `loader.py` + `test_loader.py`
3. `validator.py` + `test_validator.py`（核心，最长）
4. `analyzer.py` + `reporter.py` + 对应测试
5. `charting.py` + `exporter.py` + 对应测试
6. `app.py` UI 串联
7. `make_sample.py` 生成样例 → §10 验收清单逐项过

---

## 12. 后续扩展（v2 候选，本期不做）

多 sheet 与非首行表头识别 / 多分组列交叉统计 / 自定义校验规则 / 结果一键复制到剪贴板 / 简报导出 Word
