from __future__ import annotations

import pandas as pd
import pytest

import data_cleaner
from data_cleaner import (
    ERROR_COLUMNS,
    ISSUE_DATE_FORMAT,
    ISSUE_DUPLICATE,
    ISSUE_INTERNAL,
    ISSUE_MISSING,
    ISSUE_PHONE_FORMAT,
    ColumnConfig,
    LoadError,
    get_valid,
    list_sheets,
    load_bytes,
    load_table,
    run_checks,
    validate,
)


def _errors_of(df, config):
    return validate(df, config)


def test_row_number_equals_index_plus_two(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    assert (errors["行号"] >= 2).all()
    name_missing = errors[(errors["错误类型"] == ISSUE_MISSING) & (errors["列名"] == "姓名")]
    assert name_missing["行号"].tolist() == [4]


def test_missing_detection(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    missing = errors[errors["错误类型"] == ISSUE_MISSING]
    assert len(missing) == 3
    assert set(missing["列名"]) == {"姓名", "手机号", "学号"}


def test_duplicate_keeps_first_row(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    dup = errors[errors["错误类型"] == ISSUE_DUPLICATE]
    assert len(dup) == 1
    assert dup["行号"].iloc[0] == 5
    assert "与第 2 行重复" in dup["问题描述"].iloc[0]


def test_duplicate_nan_student_id_not_flagged():
    df = pd.DataFrame(
        {"姓名": ["甲", "乙"], "学号": [None, None], "手机号": ["13800138001", "13800138002"]}
    )
    errors = validate(df, ColumnConfig(name="姓名", student_id="学号", phone="手机号", required_columns=("学号",)))
    assert (errors["错误类型"] == ISSUE_DUPLICATE).sum() == 0
    assert (errors["错误类型"] == ISSUE_MISSING).sum() == 2


def test_phone_formats(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    phone_issues = errors[errors["错误类型"] == ISSUE_PHONE_FORMAT]
    assert phone_issues["行号"].tolist() == [6]

    cases = pd.DataFrame(
        {
            "姓名": ["a", "b", "c", "d", "e", "f"],
            "手机号": ["13800138000", "1234567890", "138001380001", "23800138000", "138-0013-8000", 13800138000],
        }
    )
    errors = validate(cases, ColumnConfig(name="姓名", phone="手机号"))
    bad = errors[errors["错误类型"] == ISSUE_PHONE_FORMAT]
    assert bad["行号"].tolist() == [3, 4, 5, 6]


def test_phone_optional_not_required():
    cases = pd.DataFrame({"姓名": ["a", "b"], "手机号": ["13800138000", None]})
    errors = validate(cases, ColumnConfig(name="姓名", phone="手机号", phone_required=False))
    assert errors.empty


def test_date_formats(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    date_issues = errors[errors["错误类型"] == ISSUE_DATE_FORMAT]
    assert date_issues["行号"].tolist() == [8]

    cases = pd.DataFrame(
        {
            "姓名": ["a", "b", "c", "d"],
            "日期": ["2025-01-01", "2025-02-30", "2025/01/01", pd.Timestamp("2025-01-05")],
        }
    )
    errors = validate(cases, ColumnConfig(name="姓名", date="日期"))
    bad = errors[errors["错误类型"] == ISSUE_DATE_FORMAT]
    assert bad["行号"].tolist() == [3, 4]


def test_date_required_flag():
    cases = pd.DataFrame({"姓名": ["a"], "日期": [None]})
    errors = validate(cases, ColumnConfig(name="姓名", date="日期", date_required=False))
    assert errors.empty
    errors = validate(cases, ColumnConfig(name="姓名", date="日期", date_required=True))
    assert len(errors) == 1
    assert errors["错误类型"].iloc[0] == ISSUE_MISSING


def test_blank_row_ignored(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    assert not (errors["行号"] == 12).any()
    valid = get_valid(dirty_df, column_config)
    assert len(valid) == 5
    assert set(valid["学号"]) == {"S01", "S02", "S07", "S08", "S09"}


def test_valid_rows_content(dirty_df, column_config):
    valid = get_valid(dirty_df, column_config)
    assert len(valid) == 5
    assert set(valid["学号"]) == {"S01", "S02", "S07", "S08", "S09"}


def test_multi_error_row_reports_all_issues():
    df = pd.DataFrame(
        {"姓名": [None], "学号": ["S01"], "手机号": ["1234567890"], "日期": ["2025-02-30"]}
    )
    errors = validate(
        df,
        ColumnConfig(
            name="姓名", student_id="学号", phone="手机号", date="日期", required_columns=("姓名",)
        ),
    )
    assert set(errors["错误类型"]) == {ISSUE_MISSING, ISSUE_PHONE_FORMAT, ISSUE_DATE_FORMAT}
    assert (errors["行号"] == 2).all()


def test_bad_cell_does_not_crash():
    class Evil:
        def __str__(self):
            raise RuntimeError("boom")

    df = pd.DataFrame({"姓名": ["a"], "手机号": [Evil()]})
    errors = validate(df, ColumnConfig(name="姓名", phone="手机号"))
    internal = errors[errors["错误类型"] == ISSUE_INTERNAL]
    assert len(internal) == 1
    assert internal["行号"].iloc[0] == 2


def test_error_df_schema(dirty_df, column_config):
    errors = _errors_of(dirty_df, column_config)
    assert list(errors.columns) == ERROR_COLUMNS


def test_load_csv_utf8(tmp_path):
    path = tmp_path / "报名.csv"
    df = pd.DataFrame({"姓名": ["张三"], "学号": ["S01"]})
    df.to_csv(path, index=False, encoding="utf-8-sig")
    loaded = load_table(path)
    assert loaded.shape == (1, 2)
    assert loaded["姓名"].iloc[0] == "张三"


def test_load_csv_gbk(tmp_path):
    path = tmp_path / "报名.csv"
    df = pd.DataFrame({"姓名": ["张三"], "学号": ["S01"]})
    df.to_csv(path, index=False, encoding="gbk")
    loaded = load_table(path)
    assert loaded["姓名"].iloc[0] == "张三"


def test_load_xlsx(tmp_path, dirty_df):
    path = tmp_path / "报名.xlsx"
    dirty_df.to_excel(path, index=False)
    loaded = load_table(path)
    assert len(loaded) == len(dirty_df)


def test_load_preserves_blank_rows(tmp_path):
    path = tmp_path / "表.csv"
    pd.DataFrame({"姓名": ["a", None], "学号": ["S1", None]}).to_csv(path, index=False)
    loaded = load_table(path)
    assert len(loaded) == 2


def test_load_strips_column_names(tmp_path):
    path = tmp_path / "表.csv"
    pd.DataFrame({" 姓名 ": ["a"], "学号": ["S1"]}).to_csv(path, index=False)
    loaded = load_table(path)
    assert "姓名" in loaded.columns


def test_load_missing_file():
    with pytest.raises(LoadError):
        load_table("/workspace/不存在的文件.csv")


def test_load_bad_extension(tmp_path):
    path = tmp_path / "表.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(LoadError):
        load_table(path)


def test_load_unknown_encoding(tmp_path, monkeypatch):
    path = tmp_path / "表.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")

    def fake_read_csv(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\x81", 0, 1, "invalid start byte")

    monkeypatch.setattr(data_cleaner.pd, "read_csv", fake_read_csv)
    with pytest.raises(LoadError):
        load_table(path)


def test_run_checks_consistency(dirty_df, column_config):
    errors, valid = run_checks(dirty_df, column_config)
    assert len(errors) == 6
    assert len(valid) == 5


def test_load_bytes_csv_utf8():
    data = pd.DataFrame({"姓名": ["张三"], "学号": ["S01"]}).to_csv(index=False).encode("utf-8")
    loaded = load_bytes("报名.csv", data)
    assert loaded["姓名"].iloc[0] == "张三"


def test_load_bytes_csv_gbk():
    data = pd.DataFrame({"姓名": ["李四"]}).to_csv(index=False).encode("gbk")
    loaded = load_bytes("报名.csv", data)
    assert loaded["姓名"].iloc[0] == "李四"


def test_load_bytes_xlsx(tmp_path, dirty_df):
    path = tmp_path / "表.xlsx"
    dirty_df.to_excel(path, index=False)
    loaded = load_bytes("表.xlsx", path.read_bytes())
    assert len(loaded) == len(dirty_df)


def test_load_bytes_bad_suffix():
    with pytest.raises(LoadError):
        load_bytes("表.txt", b"a,b\n1,2")


def test_load_bytes_empty_file():
    with pytest.raises(LoadError):
        load_bytes("空.csv", b"")


def test_load_bytes_undecodable():
    with pytest.raises(LoadError):
        load_bytes("坏.csv", b"\xc3\x28\xff")


def test_required_columns_generic():
    df = pd.DataFrame({"姓名": ["甲", None], "班级": ["A班", "B班"]})
    errors = validate(df, ColumnConfig(required_columns=("班级",)))
    assert len(errors) == 0
    errors = validate(df, ColumnConfig(required_columns=("姓名", "班级")))
    missing = errors[errors["错误类型"] == ISSUE_MISSING]
    assert missing["行号"].tolist() == [3]
    assert set(missing["列名"]) == {"姓名"}


def test_implicit_required_removed_for_roles():
    df = pd.DataFrame({"姓名": [None], "学号": [None]})
    errors = validate(df, ColumnConfig(name="姓名", student_id="学号"))
    assert errors.empty


def test_list_sheets_xlsx(tmp_path):
    path = tmp_path / "多表.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"姓名": ["张三"]}).to_excel(writer, sheet_name="报名", index=False)
        pd.DataFrame({"姓名": ["李四"]}).to_excel(writer, sheet_name="签到", index=False)
    names = list_sheets("多表.xlsx", path.read_bytes())
    assert names == ["报名", "签到"]


def test_list_sheets_csv_returns_empty():
    assert list_sheets("表.csv", b"a,b\n1,2") == []


def test_list_sheets_corrupted_xlsx_returns_empty():
    assert list_sheets("坏.xlsx", b"not a real xlsx") == []


def test_load_bytes_select_sheet_by_name(tmp_path):
    path = tmp_path / "多表.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"姓名": ["张三"]}).to_excel(writer, sheet_name="报名", index=False)
        pd.DataFrame({"姓名": ["李四"]}).to_excel(writer, sheet_name="签到", index=False)
    loaded = load_bytes("多表.xlsx", path.read_bytes(), sheet="签到")
    assert loaded["姓名"].iloc[0] == "李四"


def test_load_bytes_select_sheet_by_index(tmp_path):
    path = tmp_path / "多表.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"姓名": ["张三"]}).to_excel(writer, sheet_name="报名", index=False)
        pd.DataFrame({"姓名": ["李四"]}).to_excel(writer, sheet_name="签到", index=False)
    loaded = load_bytes("多表.xlsx", path.read_bytes(), sheet=1)
    assert loaded["姓名"].iloc[0] == "李四"


def test_load_bytes_missing_sheet_raises_friendly(tmp_path):
    path = tmp_path / "多表.xlsx"
    pd.DataFrame({"姓名": ["张三"]}).to_excel(path, sheet_name="报名", index=False)
    with pytest.raises(LoadError):
        load_bytes("多表.xlsx", path.read_bytes(), sheet="不存在的表")
