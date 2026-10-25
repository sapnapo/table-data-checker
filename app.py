"""表格数据检查与简报生成助手 — Streamlit Web 界面（面向普通用户）。

核心逻辑位于 data_cleaner / analyzer / report_generator 三个模块，
本文件仅负责界面编排：上传 → 选列 → 检查 → 统计图表 → 简报 → 导出。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from analyzer import (
    build_figure,
    column_profile,
    compute_stats,
    interactive_bar,
    interactive_pie,
)
from data_cleaner import (
    ISSUE_DATE_FORMAT,
    ISSUE_DUPLICATE,
    ISSUE_INTERNAL,
    ISSUE_MISSING,
    ISSUE_PHONE_FORMAT,
    ColumnConfig,
    LoadError,
    list_sheets,
    load_bytes,
    make_demo_dataframe,
    run_checks,
)
from report_generator import generate_report

st.set_page_config(
    page_title="表格数据检查与简报生成助手",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

NO_SELECTION = "（不使用）"
NAME_HINTS = ("姓名", "名字")
ID_HINTS = ("学号", "工号", "编号", "学籍号")
PHONE_HINTS = ("手机", "电话", "联系方式")
DATE_HINTS = ("日期", "时间", "date")
GROUP_HINTS = ("班级", "部门", "组别", "院系", "单位", "专业", "年级")
MAX_GROUP_METRICS = 6
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEMO_SOURCE_NAME = "示例报名表.csv"

ISSUE_TYPE_LABELS = {
    ISSUE_MISSING: "缺失",
    ISSUE_DUPLICATE: "重复",
    ISSUE_PHONE_FORMAT: "格式错误",
    ISSUE_DATE_FORMAT: "格式错误",
    ISSUE_INTERNAL: "内部异常",
}

ISSUE_DISPLAY_LABELS = {
    ISSUE_MISSING: "缺失",
    ISSUE_DUPLICATE: "重复",
    ISSUE_PHONE_FORMAT: "手机号格式",
    ISSUE_DATE_FORMAT: "日期格式",
    ISSUE_INTERNAL: "内部异常",
}

PRIMARY = "#2563EB"
GREEN = "#10B981"
AMBER = "#F59E0B"
RED = "#EF4444"

CUSTOM_CSS = """
<style>
/* ===== 隐藏开发者元素（Deploy / 工具栏 / 状态角标 / 菜单 / 页脚） ===== */
div[data-testid="stToolbar"] { display: none !important; }
div[data-testid="stStatusWidget"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

/* ===== 全局字体与背景 ===== */
html, body, button, input, select, textarea {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC",
               "Helvetica Neue", Arial, sans-serif;
}
.stApp { background: #F5F7FB; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1180px; }

/* ===== 侧边栏 ===== */
section[data-testid="stSidebar"] {
  background: #FFFFFF;
  border-right: 1px solid #E6EAF2;
}
.side-step {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 700; color: #1F2937;
  margin: 4px 0 2px;
}
.step-chip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%;
  background: #2563EB; color: #fff; font-size: 13px; font-weight: 700;
  flex: none;
}

/* ===== 页面主标题 ===== */
h1 { padding-top: 0 !important; }

/* ===== 首页步骤条 ===== */
.flow-bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 14px;
  padding: 16px 20px; margin: 6px 0 16px;
  box-shadow: 0 1px 3px rgba(31,41,55,0.04);
}
.flow-item { display: flex; align-items: center; gap: 8px; font-size: 14.5px; color: #374151; font-weight: 600; }
.flow-arrow { color: #C3CBD9; font-size: 18px; }

/* ===== 功能卡片 ===== */
.feature-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}
.feature-card {
  background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 1px 3px rgba(31,41,55,0.04);
  transition: box-shadow .2s ease, transform .2s ease;
}
.feature-card:hover { box-shadow: 0 6px 16px rgba(31,41,55,0.09); transform: translateY(-2px); }
.feature-icon {
  display: flex; align-items: center; justify-content: center;
  width: 46px; height: 46px; border-radius: 12px; font-size: 23px;
}
.feature-title { font-size: 16px; font-weight: 700; color: #1F2937; margin: 10px 0 5px; }
.feature-desc { font-size: 13.5px; color: #6B7280; line-height: 1.7; }

/* ===== KPI 指标卡 ===== */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 4px 0 10px; }
.kpi-card {
  display: flex; align-items: center; gap: 13px;
  background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 14px;
  padding: 16px 18px;
  box-shadow: 0 1px 3px rgba(31,41,55,0.04);
}
.kpi-icon {
  display: flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; border-radius: 12px; font-size: 21px; flex: none;
}
.kpi-label { font-size: 13px; color: #6B7280; }
.kpi-value { font-size: 27px; font-weight: 700; color: #1F2937; line-height: 1.2; }
.kpi-unit { font-size: 14px; font-weight: 500; color: #6B7280; margin-left: 3px; }

/* ===== 组别人数卡 ===== */
.group-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 4px 0 10px; }
.group-card {
  background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 12px;
  padding: 13px 16px;
}
.group-card.muted { background: #F9FAFB; border-color: #EDEFF3; }
.group-name { font-size: 13px; color: #6B7280; }
.group-card.muted .group-name { color: #9CA3AF; }
.group-count { font-size: 23px; font-weight: 700; color: #1F2937; margin-top: 2px; }
.group-card.muted .group-count { color: #6B7280; }
.group-pct { font-size: 12.5px; color: #2563EB; font-weight: 600; margin-top: 2px; }
.group-card.muted .group-pct { color: #9CA3AF; }

/* ===== 标签页（胶囊风格，Streamlit 1.66 DOM: div[role=tab]） ===== */
div[data-testid="stTabs"] div[role="tablist"] {
  gap: 8px !important; border-bottom: 0 !important; background: transparent !important;
}
div[data-testid="stTabs"] div[role="tab"] {
  border-radius: 999px !important; padding: 8px 22px !important; margin-bottom: 4px !important;
  font-weight: 600 !important; font-size: 14.5px !important; color: #4B5563 !important;
  background-color: #FFFFFF !important;
  border: 1px solid #E6EAF2 !important;
  box-shadow: 0 1px 2px rgba(31,41,55,0.04) !important;
}
div[data-testid="stTabs"] div[role="tab"]:hover:not([aria-selected="true"]) {
  color: #2563EB !important; border-color: #BFDBFE !important; background-color: #F8FAFF !important;
}
div[data-testid="stTabs"] div[role="tab"][aria-selected="true"] {
  color: #FFFFFF !important; background-color: #2563EB !important;
  border-color: #2563EB !important; box-shadow: 0 2px 6px rgba(37,99,235,0.28) !important;
}

/* ===== 表格容器 ===== */
div[data-testid="stDataFrame"] {
  border: 1px solid #E6EAF2; border-radius: 12px; overflow: hidden;
}

/* ===== 简报文档卡（带边框容器） ===== */
div[data-testid="stVerticalBlockBorderContainer"] {
  background: #FFFFFF;
  border: 1px solid #E6EAF2 !important;
  border-radius: 14px !important;
  padding: 6px 20px 12px;
}

/* ===== 段落间距 ===== */
hr { border-color: #EEF1F6 !important; }
</style>
"""


def sniff_column(columns: list[str], hints: tuple[str, ...]) -> Optional[str]:
    lowered = [column.lower() for column in columns]
    for hint in hints:
        for column, low in zip(columns, lowered):
            if hint in low:
                return column
    return None


def select_column(label: str, columns: list[str], default: Optional[str], help_text: str) -> Optional[str]:
    options = [NO_SELECTION] + columns
    index = 0 if default is None else options.index(default)
    chosen = st.selectbox(label, options, index=index, help=help_text)
    return None if chosen == NO_SELECTION else chosen


def load_uploaded(uploaded) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """读取上传件；返回 (DataFrame, sheet 名)。失败时就地展示友好错误。"""
    try:
        sheets = list_sheets(uploaded.name, uploaded.getvalue())
    except Exception:
        sheets = []
    sheet_label = None
    sheet_choice = 0
    if len(sheets) > 1:
        options = [f"{name}" for name in sheets]
        sheet_label = st.sidebar.selectbox("这个 Excel 有多个工作表，要检查哪一个？", options, index=0)
        sheet_choice = sheets[options.index(sheet_label)]
    elif len(sheets) == 1:
        sheet_label = sheets[0]
    try:
        df = load_bytes(uploaded.name, uploaded.getvalue(), sheet=sheet_choice)
        return df, sheet_label
    except LoadError as exc:
        st.sidebar.error(f"文件读取失败：{exc}")
    except Exception as exc:
        st.sidebar.error(f"读取文件时出现未预期的问题，请重试或更换文件：{exc}")
    return None, None


def _kpi_card(icon: str, label: str, value, unit: str, bg: str) -> str:
    return (
        f'<div class="kpi-card"><div class="kpi-icon" style="background:{bg};">{icon}</div>'
        f"<div><div class=\"kpi-label\">{label}</div>"
        f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div></div></div>'
    )


def _kpi_row(summary) -> str:
    cards = [
        _kpi_card("👥", "共收到报名", summary.total_submitted, "人", "#EFF6FF"),
        _kpi_card("✅", "信息完整有效", summary.total_valid, "人", "#ECFDF5"),
        _kpi_card("🔁", "重复报名剔除", summary.duplicate_removed, "份", "#FFF7ED"),
        _kpi_card("⚠️", "缺填 / 填错剔除", summary.error_removed, "份", "#FEF2F2"),
    ]
    return '<div class="kpi-row">' + "".join(cards) + "</div>"


def _group_card(name: str, count: int, pct: float) -> str:
    muted = name == "未填写"
    cls = "group-card muted" if muted else "group-card"
    return (
        f'<div class="{cls}"><div class="group-name">{name}</div>'
        f'<div class="group-count">{count} 人</div>'
        f'<div class="group-pct">占比 {pct:.1f}%</div></div>'
    )


def render_empty_state() -> None:
    steps = (
        ("1", "上传报名表（Excel 或 CSV）"),
        ("2", "点一下「开始检查」"),
        ("3", "看结果、下载报表"),
    )
    flow = ""
    for i, (num, text) in enumerate(steps):
        flow += f'<div class="flow-item"><span class="step-chip">{num}</span>{text}</div>'
        if i < len(steps) - 1:
            flow += '<span class="flow-arrow">→</span>'
    st.markdown(f'<div class="flow-bar">{flow}</div>', unsafe_allow_html=True)

    features = [
        ("🧹", "#EFF6FF", "自动找出问题", "谁漏填了、谁重复报名、手机号和日期填错的，一次全部找出来，并告诉你出错在第几行。"),
        ("📊", "#ECFDF5", "统计一目了然", "总共多少人、每个班各多少人、占多少比例，自动算好并画成图表。"),
        ("📝", "#FFF7ED", "简报自动生成", "一句“本次共收到 95 份报名，A 班 40 人占比 42%”这样的汇报文案，直接生成给你。"),
        ("🔒", "#FEF2F2", "文件安全", "所有处理都在你自己的电脑上完成，原始文件不会被修改，结果另存为新文件。"),
    ]
    grid = ""
    for icon, bg, title, desc in features:
        grid += (
            f'<div class="feature-card"><div class="feature-icon" style="background:{bg};">{icon}</div>'
            f'<div class="feature-title">{title}</div><div class="feature-desc">{desc}</div></div>'
        )
    st.markdown(f'<div class="feature-grid">{grid}</div>', unsafe_allow_html=True)

    st.info("请在左侧点击「浏览文件」上传你的报名表；想先看看效果，就点「先用示例数据体验一下」。")


def render_sidebar_config(df: pd.DataFrame, source_name: str) -> None:
    columns = [str(column) for column in df.columns]
    with st.sidebar:
        st.markdown(
            '<div class="side-step"><span class="step-chip">2</span>确认一下列设置</div>',
            unsafe_allow_html=True,
        )
        st.caption("系统已按列名自动识别，一般不用改，直接点下面的按钮就行。")
        default_name = sniff_column(columns, NAME_HINTS)
        default_id = sniff_column(columns, ID_HINTS)
        default_phone = sniff_column(columns, PHONE_HINTS)
        default_date = sniff_column(columns, DATE_HINTS)
        default_group = sniff_column(columns, GROUP_HINTS)

        unique_col = select_column(
            "学号 / 编号列（用来查重复）",
            columns,
            default_id,
            "此列相同的两条记录会被认作重复报名，保留最先提交的那条。",
        )
        default_required = [c for c in (default_name, default_id) if c]
        required_cols = st.multiselect(
            "哪些列不能为空？",
            columns,
            default=default_required,
            help="选中的列一旦有空值，就会在检查结果里逐行标出（比如姓名、学号漏填）。",
        )
        phone_col = select_column(
            "手机号列（检查是否为 11 位手机号）",
            columns,
            default_phone,
            "只做格式检查；如果加进了上面的“不能为空”列，则漏填也会被标出。",
        )
        date_col = select_column(
            "日期列（检查日期格式）",
            columns,
            default_date,
            "按 2025-03-01 这样的格式检查；写成 2025/3/1 或 2025-02-30 都会标为格式错误。",
        )
        group_col = select_column(
            "按哪一列统计人数？（班级 / 部门）",
            columns,
            default_group,
            "选中的列用来分组统计和画图，比如班级、部门。没填的自动归到“未填写”。",
        )

        if not unique_col and not required_cols:
            st.info("建议至少选一个“学号列”或一个“不能为空”的列，检查结果才更有意义。")

        inputs = {
            "unique_col": unique_col,
            "required_cols": required_cols,
            "phone_col": phone_col,
            "date_col": date_col,
            "group_col": group_col,
        }
        if st.button("🚀 开始检查", type="primary", use_container_width=True):
            run_analysis(df, inputs, source_name)


def run_analysis(df: pd.DataFrame, inputs: dict, source_name: str) -> None:
    required_cols = [column for column in inputs["required_cols"] if column in df.columns]
    config = ColumnConfig(
        student_id=inputs["unique_col"],
        phone=inputs["phone_col"],
        date=inputs["date_col"],
        group=inputs["group_col"],
        phone_required=inputs["phone_col"] in required_cols,
        date_required=inputs["date_col"] in required_cols,
        required_columns=tuple(required_cols),
    )
    try:
        with st.spinner("正在检查数据，请稍等…"):
            errors, valid = run_checks(df, config)
            summary = compute_stats(df, valid, errors, group_col=inputs["group_col"])
            report = generate_report(source_name, summary, errors)
            png_bytes, found_font = render_chart_png(summary)
            xlsx_bytes = build_cleaned_xlsx(df, valid, errors) if summary.total_valid > 0 else b""
        st.session_state["result"] = {
            "source_name": source_name,
            "errors": errors,
            "summary": summary,
            "report": report,
            "png_bytes": png_bytes,
            "found_font": found_font,
            "xlsx_bytes": xlsx_bytes,
        }
        st.toast("检查完成！结果在下方各标签页中查看。", icon="✅")
    except Exception as exc:
        st.error(f"分析过程中出现问题，请检查数据或调整左侧列设置后重试：{exc}")


def render_chart_png(summary) -> tuple[bytes, bool]:
    if summary.group_table is None or summary.group_table.empty:
        return b"", True
    fig, found_font = build_figure(summary.group_table)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    return buffer.getvalue(), found_font


def build_cleaned_xlsx(df: pd.DataFrame, valid: pd.DataFrame, errors: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        valid.to_excel(writer, sheet_name="有效数据", index=False)
        dropped = pd.DataFrame()
        if errors is not None and not errors.empty:
            row_errors = errors[errors["行号"] >= 2]
            if not row_errors.empty:
                positions = sorted({int(p) for p in row_errors["行号"] - 2})
                positions = [p for p in positions if 0 <= p < len(df)]
                dropped = df.iloc[positions].copy()
                reason_map = row_errors.groupby("行号")["问题描述"].apply("；".join).to_dict()
                dropped.insert(
                    len(dropped.columns),
                    "剔除原因",
                    [reason_map.get(p + 2, "") for p in positions],
                )
        dropped.to_excel(writer, sheet_name="被剔除明细", index=False)
    return buffer.getvalue()


def render_preview_tab(df: pd.DataFrame, source_name: str, sheet_label: Optional[str]) -> None:
    st.subheader("数据预览（前 5 行）")
    meta = f"文件：{source_name}｜共 {len(df)} 行 × {len(df.columns)} 列"
    if sheet_label:
        meta += f"｜工作表：{sheet_label}"
    st.caption(meta)
    st.dataframe(df.head(5), use_container_width=True)

    st.subheader("每列数据概况")
    st.caption("哪些列有缺失、缺失多不多，这里一眼就能看出来。")
    st.dataframe(column_profile(df), use_container_width=True)


def render_pending_hint() -> None:
    st.info("左边设置好以后，点「🚀 开始检查」，这里就会显示检查结果、统计图表和简报。")


def render_errors_tab(result: dict) -> None:
    summary = result["summary"]
    errors = result["errors"]

    st.markdown(_kpi_row(summary), unsafe_allow_html=True)

    st.subheader(f"发现的问题（共 {len(errors)} 处）")
    if errors.empty:
        st.success("这份表格很干净，没有发现漏填、重复或格式问题。🎉")
        return

    labeled = errors.copy()
    labeled["类别"] = labeled["错误类型"].map(lambda t: ISSUE_TYPE_LABELS.get(t, "其他"))
    counts = labeled["类别"].value_counts()

    category_order = [c for c in ("缺失", "重复", "格式错误", "内部异常") if counts.get(c, 0) > 0]
    tab_labels = [f"全部（{len(labeled)}）"] + [
        f"{name}（{int(counts.get(name, 0))}）" for name in category_order
    ]
    tabs = st.tabs(tab_labels)
    views = [labeled] + [labeled[labeled["类别"] == name] for name in category_order]
    for tab, view in zip(tabs, views):
        with tab:
            if view.empty:
                st.caption("这一类没有问题。")
            else:
                display = view.drop(columns=["类别", "错误类型"]).copy()
                display.insert(
                    2,
                    "问题类型",
                    view["错误类型"].map(lambda t: ISSUE_DISPLAY_LABELS.get(t, t)).values,
                )
                st.dataframe(display, use_container_width=True, hide_index=True)

    st.caption("“行号”就是打开 Excel 时看到的行号（第 1 行是表头），照着行号就能直接找到出错的地方。")
    st.download_button(
        "下载问题清单（Excel 可打开）",
        errors.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{Path(result['source_name']).stem}_问题清单.csv",
        mime="text/csv",
        key="dl_errors_csv",
    )


def render_chart_tab(result: dict) -> None:
    summary = result["summary"]
    if summary.group_table is None or summary.group_table.empty:
        st.warning("还没有选“按哪一列统计人数”，或没有有效记录，所以暂时没有分组统计。")
        return

    st.subheader("各组人数")
    table = summary.group_table
    if len(table) <= MAX_GROUP_METRICS:
        cards = "".join(
            _group_card(str(row["组别"]), int(row["人数"]), float(row["占比(%)"]))
            for _, row in table.iterrows()
        )
        st.markdown(f'<div class="group-row">{cards}</div>', unsafe_allow_html=True)
    st.dataframe(table, use_container_width=True, hide_index=True)

    chart_tabs = st.tabs(["📊 柱状图（可悬停看占比）", "🥧 占比饼图"])
    with chart_tabs[0]:
        st.plotly_chart(interactive_bar(table), use_container_width=True)
    with chart_tabs[1]:
        st.plotly_chart(interactive_pie(table), use_container_width=True)

    if result["png_bytes"]:
        with st.expander("查看 / 下载静态图表图片（PNG）"):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.image(result["png_bytes"])
            with col2:
                st.write("")
                st.download_button(
                    "下载图片",
                    result["png_bytes"],
                    file_name=f"{Path(result['source_name']).stem}_柱状图.png",
                    mime="image/png",
                    key="dl_chart_tab_png",
                )
        if not result["found_font"]:
            st.warning("电脑上缺少中文字体，静态图片里的文字自动改成了英文；上面的交互图表不受影响。")


def render_report_tab(result: dict) -> None:
    summary = result["summary"]
    stem = Path(result["source_name"]).stem

    st.subheader("汇报简报（可直接复制使用）")
    with st.container(border=True):
        st.markdown(result["report"])
    with st.expander("复制简报原文（Markdown 格式）"):
        st.code(result["report"], language="markdown")

    st.subheader("下载")
    col1, col2, col3 = st.columns(3)
    if result["xlsx_bytes"]:
        col1.download_button(
            "📥 清洗后的数据（Excel）",
            result["xlsx_bytes"],
            file_name=f"{stem}_清洗后.xlsx",
            mime=XLSX_MIME,
            key="dl_cleaned_xlsx",
            help="含两个工作表：信息完整的有效数据 + 被剔除的记录（附原因）。",
        )
    else:
        col1.caption("没有有效记录，未生成清洗数据。")
    col2.download_button(
        "📥 汇报简报（Markdown）",
        result["report"].encode("utf-8"),
        file_name=f"{stem}_简报.md",
        mime="text/markdown",
        key="dl_report_md",
    )
    if result["png_bytes"]:
        col3.download_button(
            "📥 统计图表（PNG 图片）",
            result["png_bytes"],
            file_name=f"{stem}_柱状图.png",
            mime="image/png",
            key="dl_report_png",
        )

    st.caption("放心：整个过程只在你自己的电脑上完成，上传的原始文件不会被修改，下载的都是新生成的文件。")


def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("表格数据检查与简报生成助手")
    st.caption("上传报名表或签到表，自动找出漏填、重复和格式问题，并生成统计图表和汇报简报。")

    uploaded = st.sidebar.file_uploader("📤 上传报名表 / 签到表", type=["csv", "xlsx"])
    if uploaded is None and st.sidebar.button(
        "📋 先用示例数据体验一下", use_container_width=True
    ):
        st.session_state["demo"] = make_demo_dataframe()
        st.session_state.pop("result", None)
        st.session_state.pop("source_key", None)
        st.rerun()

    df = None
    source_name = None
    sheet_label = None
    if uploaded is not None:
        st.session_state.pop("demo", None)
        source_key = (uploaded.name, uploaded.size)
        if st.session_state.get("source_key") != source_key:
            st.session_state.pop("result", None)
            st.session_state["source_key"] = source_key
        df, sheet_label = load_uploaded(uploaded)
        if df is not None:
            source_name = uploaded.name
            st.sidebar.success("文件读取成功！确认左侧列设置后开始检查。")
            render_sidebar_config(df, source_name)
    elif "demo" in st.session_state:
        df = st.session_state["demo"]
        source_name = DEMO_SOURCE_NAME
        render_sidebar_config(df, source_name)

    if df is None:
        if uploaded is not None:
            st.warning("文件没能读取成功，请看看左侧的提示，调整后重新上传。")
        else:
            render_empty_state()
        return

    result = st.session_state.get("result")
    tab_labels = ["📤 数据预览", "🔍 检查结果", "📊 统计图表", "📝 简报与下载"]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_preview_tab(df, source_name, sheet_label)
    with tabs[1]:
        if result:
            render_errors_tab(result)
        else:
            render_pending_hint()
    with tabs[2]:
        if result:
            render_chart_tab(result)
        else:
            render_pending_hint()
    with tabs[3]:
        if result:
            render_report_tab(result)
        else:
            render_pending_hint()


if __name__ == "__main__":
    main()
