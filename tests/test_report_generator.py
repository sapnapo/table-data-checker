from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from analyzer import Summary, compute_stats
from data_cleaner import ColumnConfig, run_checks
from report_generator import MAX_DETAIL_ISSUES, generate_report, save_report


@pytest.fixture
def report_input(dirty_df, column_config):
    errors, valid = run_checks(dirty_df, column_config)
    summary = compute_stats(dirty_df, valid, errors, group_col="班级")
    return summary, errors


def test_overview_sentence(report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors, now=datetime(2025, 1, 1, 12, 0))
    assert "本次共收到 11 份报名" in text
    assert "有效记录 5 份" in text
    assert "剔除重复 1 份" in text
    assert "缺失/格式错误 5 份" in text


def test_timestamp(report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors, now=datetime(2025, 1, 1, 12, 0))
    assert "生成时间：2025-01-01 12:00" in text


def test_group_section(report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors)
    assert "| 组别 | 人数 | 占比 |" in text
    assert "| A班 | 2 | 40.0% |" in text
    assert "其中 A班 2 人，占比 40.0%" in text


def test_quality_summary_and_details(report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors)
    assert "共发现 6 处问题" in text
    assert "缺失 3 处" in text
    assert "格式错误 2 处" in text
    assert "重复 1 处" in text
    assert "第 5 行" in text
    assert "与第 2 行重复" in text


def test_detail_limit_20():
    rows = [{"姓名": f"学生{i:03d}", "学号": f"S{i:03d}", "手机号": "1234567890"} for i in range(30)]
    df = pd.DataFrame(rows)
    errors, valid = run_checks(df, ColumnConfig(name="姓名", student_id="学号", phone="手机号"))
    summary = compute_stats(df, valid, errors, group_col=None)
    text = generate_report("批量.xlsx", summary, errors)
    assert text.count("- 第 ") <= MAX_DETAIL_ISSUES


def test_no_issues_report():
    df = pd.DataFrame(
        {
            "姓名": ["张三", "李四"],
            "学号": ["S1", "S2"],
            "手机号": ["13800138001", "13800138002"],
            "班级": ["A班", "B班"],
        }
    )
    errors, valid = run_checks(
        df, ColumnConfig(name="姓名", student_id="学号", phone="手机号", group="班级")
    )
    summary = compute_stats(df, valid, errors, group_col="班级")
    text = generate_report("干净表.xlsx", summary, errors)
    assert "未发现数据质量问题" in text
    assert "本次共收到 2 份报名" in text


def test_zero_valid_does_not_crash():
    df = pd.DataFrame({"姓名": [None, None], "学号": ["S1", "S1"]})
    errors, valid = run_checks(df, ColumnConfig(name="姓名", student_id="学号", required_columns=("姓名",)))
    summary = compute_stats(df, valid, errors, group_col="学号")
    text = generate_report("全错表.xlsx", summary, errors)
    assert "有效记录 0 份" in text
    assert "跳过分组统计" in text


def test_save_report(tmp_path, report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors)
    output = tmp_path / "简报.md"
    result = save_report(text, output)
    assert result == str(output)
    assert output.read_text(encoding="utf-8") == text


def test_save_report_creates_dirs(tmp_path, report_input):
    summary, errors = report_input
    text = generate_report("报名表.xlsx", summary, errors)
    output = tmp_path / "out" / "简报.md"
    save_report(text, output)
    assert output.exists()
