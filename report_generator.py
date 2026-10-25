"""简报生成模块：将统计结果填入文字模板，生成 Markdown 简报并保存。

用法示例:
    from report_generator import generate_report, save_report
    md_text = generate_report("报名表.xlsx", summary, errors_df)
    save_report(md_text, "output/简报.md")
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from analyzer import Summary
from data_cleaner import (
    ISSUE_DATE_FORMAT,
    ISSUE_DUPLICATE,
    ISSUE_INTERNAL,
    ISSUE_MISSING,
    ISSUE_PHONE_FORMAT,
)

OVERVIEW_TEMPLATE = (
    "本次共收到 {total_submitted} 份报名，其中有效记录 {total_valid} 份"
    "（剔除重复 {duplicate_removed} 份、缺失/格式错误 {error_removed} 份）。"
)

GROUP_SENTENCE_TEMPLATE = "其中 {group} {count} 人，占比 {percent}%；"
MAX_DETAIL_ISSUES = 20

ISSUE_TYPE_NAMES = {
    ISSUE_MISSING: "缺失",
    ISSUE_DUPLICATE: "重复",
    ISSUE_PHONE_FORMAT: "格式错误",
    ISSUE_DATE_FORMAT: "格式错误",
    ISSUE_INTERNAL: "内部异常",
}


def generate_report(
    source_name: str,
    summary: Summary,
    errors_df: pd.DataFrame,
    now: Optional[datetime] = None,
) -> str:
    if now is None:
        now = datetime.now()
    lines: list[str] = []
    lines.append(f"# 报名数据简报 — {Path(source_name).name}")
    lines.append("")
    lines.append(f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    lines.append("## 一、总览")
    lines.append("")
    lines.append(
        OVERVIEW_TEMPLATE.format(
            total_submitted=summary.total_submitted,
            total_valid=summary.total_valid,
            duplicate_removed=summary.duplicate_removed,
            error_removed=summary.error_removed,
        )
    )
    lines.append("")

    lines.append("## 二、分组统计")
    lines.append("")
    if summary.group_table is None or summary.group_table.empty:
        lines.append("未指定分组列或无有效记录，跳过分组统计。")
    else:
        lines.append("| 组别 | 人数 | 占比 |")
        lines.append("|---|---|---|")
        for _, row in summary.group_table.iterrows():
            lines.append(f"| {row['组别']} | {int(row['人数'])} | {row['占比(%)']:.1f}% |")
        lines.append("")
        sentences = "".join(
            GROUP_SENTENCE_TEMPLATE.format(
                group=item["组别"], count=int(item["人数"]), percent=f"{item['占比(%)']:.1f}"
            )
            for _, item in summary.group_table.iterrows()
        )
        lines.append(sentences.rstrip("；") + "。")
    lines.append("")

    lines.append("## 三、数据质量摘要")
    lines.append("")
    if errors_df is None or errors_df.empty:
        lines.append("未发现数据质量问题。")
    else:
        counts = errors_df["错误类型"].map(lambda t: ISSUE_TYPE_NAMES.get(t, "其他")).value_counts()
        parts = "、".join(f"{name} {int(count)} 处" for name, count in counts.items())
        lines.append(f"共发现 {len(errors_df)} 处问题：{parts}。")
        lines.append("")
        lines.append(f"问题明细（最多 {MAX_DETAIL_ISSUES} 条，完整清单见错误清单）：")
        for _, issue in errors_df.head(MAX_DETAIL_ISSUES).iterrows():
            row_label = "文件级" if issue["行号"] < 2 else f"第 {int(issue['行号'])} 行"
            value_part = f"“{issue['原始值']}”" if str(issue["原始值"]) else "（空值）"
            lines.append(f"- {row_label} [{issue['列名']}] {value_part}：{issue['问题描述']}")
    lines.append("")
    return "\n".join(lines)


def save_report(text: str, path: Union[str, Path] = "output/简报.md") -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return str(output)


if __name__ == "__main__":
    import sys

    from analyzer import bar_chart, compute_stats
    from data_cleaner import ColumnConfig, load_table, make_demo_dataframe, run_checks

    if len(sys.argv) > 1:
        source = sys.argv[1]
        table = load_table(source)
    else:
        source = "内存示例数据.csv"
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

    md_text = generate_report(source, summary, error_list)
    report_path = save_report(md_text, "output/简报.md")
    print(md_text)
    print(f"\n简报已保存：{report_path}")

    if summary.group_table is not None and not summary.group_table.empty:
        png_path = bar_chart(summary.group_table, output_path="output/柱状图.png")
        print(f"图表已保存：{png_path}")
