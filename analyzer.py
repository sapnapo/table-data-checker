"""统计分析模块：分组统计、列健康度概览与图表（matplotlib PNG / plotly 交互图）。

用法示例:
    from analyzer import compute_stats, bar_chart, column_profile
    summary = compute_stats(raw_df, valid_df, errors_df, group_col="班级")
    png_path = bar_chart(summary.group_table, output_path="output/柱状图.png")
    profile = column_profile(raw_df)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

from data_cleaner import ISSUE_DUPLICATE, normalize_blank

GROUP_COLUMNS = ["组别", "人数", "占比(%)"]
PROFILE_COLUMNS = ["列名", "非空", "缺失", "缺失率(%)", "唯一值数", "示例值"]
UNSPECIFIED_GROUP = "未填写"
MAX_VERTICAL_GROUPS = 15
SAMPLE_VALUE_LENGTH = 24

CHART_PRIMARY = "#2563EB"
CHART_PALETTE = ["#2563EB", "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE", "#F59E0B", "#10B981", "#EF4444"]
CHART_MUTED = "#9CA3AF"

CJK_FONT_CANDIDATES = [
    "SimHei",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "PingFang SC",
    "AR PL UMing CN",
]


@dataclass
class Summary:
    total_submitted: int
    total_valid: int
    duplicate_removed: int
    error_removed: int
    group_table: Optional[pd.DataFrame]


def compute_stats(
    raw_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    errors_df: pd.DataFrame,
    group_col: Optional[str] = None,
) -> Summary:
    raw = normalize_blank(raw_df.reset_index(drop=True))
    total_submitted = int((~raw.isna().all(axis=1)).sum())
    total_valid = int(len(valid_df))

    if errors_df is None or errors_df.empty:
        duplicate_removed = 0
    else:
        dup = errors_df[errors_df["错误类型"] == ISSUE_DUPLICATE]
        duplicate_removed = int(dup[dup["行号"] >= 2]["行号"].nunique())

    error_removed = max(0, total_submitted - total_valid - duplicate_removed)

    group_table = None
    if group_col and total_valid > 0 and group_col in valid_df.columns:
        counts = (
            valid_df[group_col].fillna(UNSPECIFIED_GROUP).replace(r"^\s*$", UNSPECIFIED_GROUP, regex=True).value_counts()
        )
        group_table = pd.DataFrame(
            {
                "组别": counts.index.tolist(),
                "人数": counts.values.tolist(),
            }
        )
        group_table["占比(%)"] = (group_table["人数"] / total_valid * 100).round(1)

    return Summary(
        total_submitted=total_submitted,
        total_valid=total_valid,
        duplicate_removed=duplicate_removed,
        error_removed=error_removed,
        group_table=group_table,
    )


def build_figure(
    group_table: pd.DataFrame, title: str = "各组人数统计"
) -> tuple[plt.Figure, bool]:
    if group_table is None or group_table.empty:
        raise ValueError("分组统计表为空，无法绘制柱状图")

    font_name = _find_cjk_font()
    found_cjk = font_name is not None
    if font_name:
        plt.rcParams["font.sans-serif"] = [font_name]
        plt.rcParams["axes.unicode_minus"] = False
        labels = [str(v) for v in group_table["组别"]]
        chart_title = title
    else:
        labels = [f"G{i + 1}" for i in range(len(group_table))]
        chart_title = "Group Counts"

    values = group_table["人数"].tolist()
    horizontal = len(group_table) > MAX_VERTICAL_GROUPS

    if horizontal:
        fig, ax = plt.subplots(figsize=(8, max(4.0, 0.4 * len(group_table))))
        y_positions = range(len(group_table) - 1, -1, -1)
        bars = ax.barh(y_positions, values, color=CHART_PRIMARY)
        ax.set_yticks(list(y_positions))
        ax.set_yticklabels(labels)
        ax.set_xlabel("人数")
    else:
        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(range(len(group_table)), values, color=CHART_PRIMARY)
        ax.set_xticks(range(len(group_table)))
        ax.set_xticklabels(labels, rotation=45 if len(group_table) > 8 else 0, ha="right" if len(group_table) > 8 else "center")
        ax.set_ylabel("人数")
    ax.set_title(chart_title)
    ax.bar_label(bars)
    fig.tight_layout()
    return fig, found_cjk


def bar_chart(
    group_table: pd.DataFrame,
    output_path: Union[str, Path] = "output/柱状图.png",
    title: str = "各组人数统计",
) -> str:
    fig, found_cjk = build_figure(group_table, title)
    if not found_cjk:
        print("警告：系统未找到中文字体，图表标签已回退为英文（G1、G2…）")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)
    return str(output)


def _find_cjk_font() -> Optional[str]:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in CJK_FONT_CANDIDATES:
        if candidate in available:
            return candidate
    return None


def column_profile(df: pd.DataFrame) -> pd.DataFrame:
    """逐列健康度概览：非空/缺失数、缺失率、唯一值数与示例值。"""
    frame = normalize_blank(df)
    n_rows = max(len(frame), 1)
    rows: list[dict] = []
    for column in frame.columns:
        series = frame[column]
        non_null = int(series.notna().sum())
        sample = ""
        for value in series.dropna().head(3):
            text = str(value).replace("\n", " ")[:SAMPLE_VALUE_LENGTH]
            sample = f"{sample} / {text}" if sample else text
            if len(sample) >= SAMPLE_VALUE_LENGTH * 2:
                break
        rows.append(
            {
                "列名": column,
                "非空": non_null,
                "缺失": int(len(frame) - non_null),
                "缺失率(%)": round((len(frame) - non_null) / n_rows * 100, 1),
                "唯一值数": int(series.nunique(dropna=True)),
                "示例值": sample or "（全空）",
            }
        )
    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)


def interactive_bar(group_table: pd.DataFrame, title: str = "各组人数统计"):
    """plotly 交互柱状图：悬停显示人数与占比。"""
    import plotly.graph_objects as go

    table = _normalize_group_table(group_table)
    percentages = table["占比(%)"].round(1)
    fig = go.Figure(
        data=[
            go.Bar(
                x=table["组别"].astype(str),
                y=table["人数"],
                text=table["人数"],
                textposition="outside",
                hovertemplate="%{x}<br>人数 %{y}<br>占比 %{customdata:.1f}%<extra></extra>",
                customdata=percentages,
                marker_color=CHART_PRIMARY,
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title="组别",
        yaxis_title="人数",
        template="plotly_white",
        height=420,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def interactive_pie(group_table: pd.DataFrame, title: str = "各组占比"):
    """plotly 交互饼图：各组人数占比。"""
    import plotly.graph_objects as go

    table = _normalize_group_table(group_table)
    colors = [
        CHART_MUTED if str(label) == UNSPECIFIED_GROUP else CHART_PALETTE[i % len(CHART_PALETTE)]
        for i, label in enumerate(table["组别"])
    ]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=table["组别"].astype(str),
                values=table["人数"],
                hole=0.45,
                hovertemplate="%{label}<br>人数 %{value}<br>占比 %{percent}<extra></extra>",
                textinfo="label+percent",
                marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            )
        ]
    )
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=420,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def _normalize_group_table(group_table: pd.DataFrame) -> pd.DataFrame:
    if group_table is None or group_table.empty:
        raise ValueError("分组统计表为空，无法绘制图表")
    table = group_table.copy()
    if "占比(%)" not in table.columns:
        total = table["人数"].sum()
        table["占比(%)"] = table["人数"] / max(total, 1) * 100
    return table


if __name__ == "__main__":
    from data_cleaner import ColumnConfig, make_demo_dataframe, run_checks

    table = make_demo_dataframe()
    config = ColumnConfig(
        name="姓名",
        student_id="学号",
        phone="手机号",
        date="报名日期",
        group="班级",
        required_columns=("姓名", "学号", "手机号"),
    )
    error_list, valid_rows = run_checks(table, config)
    summary = compute_stats(table, valid_rows, error_list, group_col="班级")
    print(
        f"提交总数 {summary.total_submitted}，有效 {summary.total_valid}，"
        f"重复剔除 {summary.duplicate_removed}，错误剔除 {summary.error_removed}"
    )
    if summary.group_table is not None:
        print(summary.group_table.to_string(index=False))
        png_path = bar_chart(summary.group_table, output_path="output/柱状图.png")
        print(f"图表已保存：{png_path}")
    else:
        print("无分组统计结果")
