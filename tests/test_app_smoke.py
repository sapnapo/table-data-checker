from __future__ import annotations

from pathlib import Path

import io

import pandas as pd
import pytest

from streamlit.testing.v1 import AppTest

from app import (
    DATE_HINTS,
    ID_HINTS,
    PHONE_HINTS,
    build_cleaned_xlsx,
    render_chart_png,
    sniff_column,
)
from analyzer import compute_stats
from data_cleaner import ColumnConfig, run_checks

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(scope="module")
def app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    return at


def test_app_renders_without_exception(app):
    assert not app.exception


def test_app_title(app):
    titles = [str(item.value) for item in app.title]
    assert any("表格数据检查与简报生成助手" in title for title in titles)


def test_app_shows_upload_hint(app):
    infos = [str(item.value) for item in app.info]
    assert any("上传" in text for text in infos)


def test_app_sidebar_renders(app):
    assert len(app.sidebar) >= 1


def test_app_demo_full_flow():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    demo_btn = next(b for b in at.sidebar.button if b.label and "示例数据" in b.label)
    demo_btn.click()
    at.run()
    assert "demo" in at.session_state
    start_btn = next(b for b in at.sidebar.button if b.label and "开始检查" in b.label)
    start_btn.click()
    at.run()
    assert not at.exception
    assert at.session_state["result"] is not None
    md_texts = [str(m.value) for m in at.markdown]
    assert any("报名数据简报" in text for text in md_texts)
    assert any("共收到" in text for text in md_texts)
    download_count = len(at.sidebar.button) + len(at.main.button)
    assert download_count >= 1


def test_sniff_column():
    assert sniff_column(["姓名", "学号", "班级"], ID_HINTS) == "学号"
    assert sniff_column(["姓名", "手机号"], PHONE_HINTS) == "手机号"
    assert sniff_column(["Name", "Phone"], ID_HINTS) is None
    assert sniff_column(["报名时间"], DATE_HINTS) == "报名时间"


def test_build_cleaned_xlsx(tmp_path, dirty_df):
    config = ColumnConfig(
        student_id="学号",
        phone="手机号",
        date="报名日期",
        group="班级",
        required_columns=("姓名", "学号", "手机号"),
    )
    errors, valid = run_checks(dirty_df, config)
    payload = build_cleaned_xlsx(dirty_df, valid, errors)
    book = pd.read_excel(io.BytesIO(payload), sheet_name=None)
    assert set(book.keys()) == {"有效数据", "被剔除明细"}
    assert len(book["有效数据"]) == len(valid)
    dropped = book["被剔除明细"]
    assert "剔除原因" in dropped.columns
    assert len(dropped) == 6
    assert dropped["剔除原因"].notna().all()


def test_render_chart_png(dirty_df):
    config = ColumnConfig(
        student_id="学号",
        phone="手机号",
        date="报名日期",
        group="班级",
        required_columns=("姓名", "学号", "手机号"),
    )
    errors, valid = run_checks(dirty_df, config)
    summary = compute_stats(dirty_df, valid, errors, group_col="班级")
    png_bytes, found_font = render_chart_png(summary)
    assert png_bytes
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert isinstance(found_font, bool)


def test_render_chart_png_without_group(dirty_df):
    config = ColumnConfig(student_id="学号", required_columns=("姓名", "学号"))
    errors, valid = run_checks(dirty_df, config)
    summary = compute_stats(dirty_df, valid, errors, group_col=None)
    png_bytes, _ = render_chart_png(summary)
    assert png_bytes == b""
