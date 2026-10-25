from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from data_cleaner import ColumnConfig


@pytest.fixture
def dirty_df() -> pd.DataFrame:
    rows = [
        {"姓名": "张三", "学号": "S01", "手机号": "13800138001", "报名日期": "2025-01-01", "班级": "A班"},
        {"姓名": "李四", "学号": "S02", "手机号": "13800138002", "报名日期": "2025-01-02", "班级": "B班"},
        {"姓名": None, "学号": "S03", "手机号": "13800138003", "报名日期": "2025-01-03", "班级": "A班"},
        {"姓名": "王五", "学号": "S01", "手机号": "13800138004", "报名日期": "2025-01-04", "班级": "C班"},
        {"姓名": "赵六", "学号": "S04", "手机号": "1234567890", "报名日期": "2025-01-05", "班级": "B班"},
        {"姓名": "钱七", "学号": "S05", "手机号": None, "报名日期": "2025-01-06", "班级": "A班"},
        {"姓名": "孙八", "学号": "S06", "手机号": "13800138006", "报名日期": "2025-02-30", "班级": "B班"},
        {"姓名": "周九", "学号": "S07", "手机号": "13800138007", "报名日期": pd.Timestamp("2025-01-08"), "班级": "C班"},
        {"姓名": "吴十", "学号": "S08", "手机号": 13800138008, "报名日期": "2025-01-09", "班级": "A班"},
        {"姓名": "郑一", "学号": None, "手机号": "13800138009", "报名日期": "2025-01-10", "班级": "B班"},
        {},
        {"姓名": "王二", "学号": "S09", "手机号": "13800138010", "报名日期": "2025-01-11", "班级": None},
    ]
    return pd.DataFrame(
        rows, columns=["姓名", "学号", "手机号", "报名日期", "班级"]
    )


@pytest.fixture
def column_config() -> ColumnConfig:
    return ColumnConfig(
        name="姓名",
        student_id="学号",
        phone="手机号",
        date="报名日期",
        group="班级",
        phone_required=True,
        date_required=False,
        required_columns=("姓名", "学号", "手机号"),
    )
