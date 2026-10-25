from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from analyzer import (
    GROUP_COLUMNS,
    PROFILE_COLUMNS,
    Summary,
    bar_chart,
    build_figure,
    column_profile,
    compute_stats,
    interactive_bar,
    interactive_pie,
)
from data_cleaner import ColumnConfig, run_checks


@pytest.fixture
def pipeline(dirty_df, column_config):
    errors, valid = run_checks(dirty_df, column_config)
    summary = compute_stats(dirty_df, valid, errors, group_col="班级")
    return errors, valid, summary


def test_conservation(dirty_df, column_config):
    errors, valid = run_checks(dirty_df, column_config)
    summary = compute_stats(dirty_df, valid, errors, group_col="班级")
    assert summary.total_submitted == 11
    assert summary.total_valid == 5
    assert summary.duplicate_removed == 1
    assert summary.error_removed == 5
    assert (
        summary.total_submitted
        == summary.total_valid + summary.duplicate_removed + summary.error_removed
    )


def test_group_table_structure(pipeline):
    _, _, summary = pipeline
    table = summary.group_table
    assert list(table.columns) == GROUP_COLUMNS
    assert table["人数"].tolist() == sorted(table["人数"].tolist(), reverse=True)
    assert table["组别"].tolist() == ["A班", "B班", "C班", "未填写"]


def test_group_unfilled_bucket(pipeline):
    _, _, summary = pipeline
    table = summary.group_table
    assert "未填写" in table["组别"].tolist()
    assert int(table.loc[table["组别"] == "未填写", "人数"].iloc[0]) == 1


def test_percent_rounding(pipeline):
    _, _, summary = pipeline
    table = summary.group_table
    assert table["占比(%)"].tolist() == [40.0, 20.0, 20.0, 20.0]


def test_no_group_column(dirty_df, column_config):
    errors, valid = run_checks(dirty_df, column_config)
    summary = compute_stats(dirty_df, valid, errors, group_col=None)
    assert summary.group_table is None
    assert summary.total_valid == 5


def test_zero_valid_records():
    df = pd.DataFrame({"姓名": [None, None], "学号": ["S1", "S1"]})
    config = ColumnConfig(name="姓名", student_id="学号", required_columns=("姓名",))
    errors, valid = run_checks(df, config)
    assert valid.empty
    summary = compute_stats(df, valid, errors, group_col="学号")
    assert summary.total_valid == 0
    assert summary.total_submitted == 2
    assert summary.duplicate_removed == 1
    assert summary.group_table is None


def test_bar_chart_writes_png(pipeline, tmp_path):
    _, _, summary = pipeline
    output = tmp_path / "chart.png"
    result = bar_chart(summary.group_table, output_path=output)
    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0


def test_bar_chart_creates_parent_dirs(pipeline, tmp_path):
    _, _, summary = pipeline
    output = tmp_path / "nested" / "dir" / "chart.png"
    bar_chart(summary.group_table, output_path=output)
    assert output.exists()


def test_bar_chart_empty_table_raises():
    with pytest.raises(ValueError):
        bar_chart(None)
    with pytest.raises(ValueError):
        bar_chart(pd.DataFrame(columns=["组别", "人数", "占比(%)"]))


def test_bar_chart_many_groups_horizontal(pipeline, tmp_path):
    _, _, summary = pipeline
    big = pd.concat([summary.group_table] * 6, ignore_index=True)
    big["组别"] = [f"组{i}" for i in range(len(big))]
    output = tmp_path / "big.png"
    bar_chart(big, output_path=output)
    assert output.exists()


def test_build_figure_returns_fig_and_flag(pipeline):
    _, _, summary = pipeline
    fig, found_cjk = build_figure(summary.group_table)
    assert fig is not None
    assert isinstance(found_cjk, bool)
    plt.close(fig)


def test_build_figure_empty_raises():
    with pytest.raises(ValueError):
        build_figure(None)
    with pytest.raises(ValueError):
        build_figure(pd.DataFrame(columns=["组别", "人数", "占比(%)"]))


def test_column_profile_structure(dirty_df):
    profile = column_profile(dirty_df)
    assert list(profile.columns) == PROFILE_COLUMNS
    assert len(profile) == len(dirty_df.columns)
    name_row = profile[profile["列名"] == "姓名"].iloc[0]
    assert int(name_row["缺失"]) == 2
    assert float(name_row["缺失率(%)"]) == round(2 / 12 * 100, 1)
    assert name_row["示例值"].startswith("张三")


def test_column_profile_all_blank_column():
    df = pd.DataFrame({"姓名": ["甲"], "备注": [None]})
    profile = column_profile(df)
    remark_row = profile[profile["列名"] == "备注"].iloc[0]
    assert int(remark_row["缺失"]) == 1
    assert remark_row["示例值"] == "（全空）"


def test_column_profile_unique_counts(dirty_df):
    profile = column_profile(dirty_df)
    class_row = profile[profile["列名"] == "班级"].iloc[0]
    assert int(class_row["唯一值数"]) == 3


def test_interactive_bar(pipeline):
    _, _, summary = pipeline
    fig = interactive_bar(summary.group_table)
    assert fig is not None
    assert len(fig.data) == 1
    assert list(fig.data[0].x) == summary.group_table["组别"].astype(str).tolist()


def test_interactive_pie(pipeline):
    _, _, summary = pipeline
    fig = interactive_pie(summary.group_table)
    assert fig is not None
    assert len(fig.data[0].values) == len(summary.group_table)


def test_interactive_empty_raises():
    with pytest.raises(ValueError):
        interactive_bar(None)
    with pytest.raises(ValueError):
        interactive_pie(pd.DataFrame(columns=["组别", "人数"]))


def test_interactive_bar_computes_percent_when_missing(pipeline):
    _, _, summary = pipeline
    table = summary.group_table.drop(columns=["占比(%)"])
    fig = interactive_bar(table)
    assert len(fig.data[0].customdata) == len(table)
