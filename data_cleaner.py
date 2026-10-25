"""表格数据检查核心模块：读取 CSV/XLSX，执行缺失/重复/格式校验。

错误清单中的"行号"与 Excel 打开文件所见一致（表头为第 1 行，首条数据在第 2 行，
即 行号 = DataFrame 位置索引 + 2）。

用法示例:
    from data_cleaner import load_table, validate, get_valid, ColumnConfig
    df = load_table("报名表.xlsx")
    config = ColumnConfig(name="姓名", student_id="学号", phone="手机号",
                          date="报名日期", group="班级")
    errors = validate(df, config)
    valid = get_valid(df, config)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

import numpy as np
import openpyxl
import pandas as pd

PHONE_PATTERN = r"1\d{10}"
DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"

ISSUE_MISSING = "MISSING"
ISSUE_DUPLICATE = "DUPLICATE"
ISSUE_PHONE_FORMAT = "PHONE_FORMAT"
ISSUE_DATE_FORMAT = "DATE_FORMAT"
ISSUE_INTERNAL = "INTERNAL"

ERROR_COLUMNS = ["行号", "列名", "错误类型", "原始值", "问题描述"]

CSV_ENCODINGS = ("utf-8-sig", "gb18030")

MAX_VALUE_LENGTH = 50


class LoadError(ValueError):
    pass


@dataclass
class ColumnConfig:
    name: Optional[str] = None
    student_id: Optional[str] = None
    phone: Optional[str] = None
    date: Optional[str] = None
    group: Optional[str] = None
    phone_required: bool = True
    date_required: bool = False
    required_columns: tuple[str, ...] = ()


def normalize_blank(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace(r"^\s*$", np.nan, regex=True)


def load_table(path: Union[str, Path]) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise LoadError(f"文件不存在：{file_path}")
    return _load_source(file_path.name, file_path)


def load_bytes(file_name: str, data: bytes, sheet: Union[int, str] = 0) -> pd.DataFrame:
    return _load_source(file_name, io.BytesIO(data), sheet)


def list_sheets(file_name: str, data: bytes) -> list[str]:
    if Path(file_name).suffix.lower() != ".xlsx":
        return []
    try:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        names = list(book.sheetnames)
        book.close()
        return names
    except Exception:
        return []


def _load_source(file_name: str, source, sheet: Union[int, str] = 0) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    try:
        if suffix == ".csv":
            df = _read_csv_with_encoding(source)
        elif suffix == ".xlsx":
            df = pd.read_excel(source, sheet_name=sheet, engine="openpyxl")
        else:
            raise LoadError(f"不支持的文件类型：{suffix}，仅支持 .csv 与 .xlsx")
    except LoadError:
        raise
    except UnicodeDecodeError as exc:
        raise LoadError("无法识别 CSV 文件编码，请用 Excel 打开后另存为 .xlsx 再试") from exc
    except pd.errors.EmptyDataError as exc:
        raise LoadError("文件内容为空，没有可分析的数据") from exc
    except Exception as exc:
        raise LoadError(f"文件读取失败，可能已损坏或格式不正确：{exc}") from exc
    if df is None or df.columns.empty:
        raise LoadError("文件为空或没有数据表")
    df.columns = [str(col).strip() for col in df.columns]
    df = normalize_blank(df)
    return df.reset_index(drop=True)


def _read_csv_with_encoding(source) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in CSV_ENCODINGS:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise LoadError(
        "无法识别 CSV 文件编码（已尝试 utf-8 / gb18030），"
        "请用 Excel 打开后另存为 .xlsx 再试"
    ) from last_error


def validate(df: pd.DataFrame, config: ColumnConfig) -> pd.DataFrame:
    errors, _ = _run_checks_safe(df, config)
    return errors


def get_valid(df: pd.DataFrame, config: ColumnConfig) -> pd.DataFrame:
    _, valid = _run_checks_safe(df, config)
    return valid


def run_checks(df: pd.DataFrame, config: ColumnConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _run_checks_safe(df, config)


def _run_checks_safe(
    df: pd.DataFrame, config: ColumnConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        return _run_checks(df, config)
    except Exception as exc:
        message = f"发生未预见的内部错误：{type(exc).__name__}: {exc}"
        message = message[: MAX_VALUE_LENGTH + 60]
        errors = pd.DataFrame(
            [{"行号": -1, "列名": "", "错误类型": ISSUE_INTERNAL, "原始值": "", "问题描述": message}],
            columns=ERROR_COLUMNS,
        )
        return errors, pd.DataFrame(columns=list(df.columns))


def _run_checks(df: pd.DataFrame, config: ColumnConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = normalize_blank(df.reset_index(drop=True))
    issues: list[dict] = []
    n_rows = len(frame)
    active = ~frame.isna().all(axis=1)

    _check_missing(frame, config, issues, active)
    _check_duplicate(frame, config, issues, active)
    _check_phone(frame, config, issues, active)
    _check_date(frame, config, issues, active)

    bad_positions = {item["行号"] - 2 for item in issues if item["行号"] >= 2}
    valid_positions = [
        pos for pos in range(n_rows) if bool(active.iat[pos]) and pos not in bad_positions
    ]

    errors = pd.DataFrame(issues, columns=ERROR_COLUMNS)
    if not errors.empty:
        errors = errors.sort_values(by=["行号", "列名"], kind="stable").reset_index(drop=True)
    valid = frame.iloc[valid_positions]
    return errors, valid


def _check_missing(
    frame: pd.DataFrame, config: ColumnConfig, issues: list[dict], active: pd.Series
) -> None:
    required: list[str] = []
    for column in config.required_columns:
        if column not in required:
            required.append(column)
    if config.phone and config.phone_required and config.phone not in required:
        required.append(config.phone)
    if config.date and config.date_required and config.date not in required:
        required.append(config.date)
    for column in required:
        if column not in frame.columns:
            continue
        missing_mask = frame[column].isna() & active
        for pos in np.flatnonzero(missing_mask.to_numpy()):
            issues.append(
                {
                    "行号": int(pos) + 2,
                    "列名": column,
                    "错误类型": ISSUE_MISSING,
                    "原始值": "",
                    "问题描述": f"【{column}】为必填项，不能为空",
                }
            )


def _check_duplicate(
    frame: pd.DataFrame, config: ColumnConfig, issues: list[dict], active: pd.Series
) -> None:
    if not config.student_id or config.student_id not in frame.columns:
        return
    sid = frame[config.student_id]
    notna = sid.notna() & active
    ids = pd.Series(pd.NA, index=frame.index, dtype="object")
    ids.loc[notna] = sid.loc[notna].astype(str).str.strip()
    dup_mask = ids.duplicated(keep="first") & ids.notna()
    first_position: dict[object, int] = {}
    for pos in np.flatnonzero((~dup_mask.to_numpy()) & notna.to_numpy()):
        value = ids.iat[int(pos)]
        first_position.setdefault(value, int(pos))
    for pos in np.flatnonzero(dup_mask.to_numpy()):
        value = ids.iat[int(pos)]
        first = first_position.get(value)
        issues.append(
            {
                "行号": int(pos) + 2,
                "列名": config.student_id,
                "错误类型": ISSUE_DUPLICATE,
                "原始值": str(value)[:MAX_VALUE_LENGTH],
                "问题描述": f"【{config.student_id}】与第 {first + 2} 行重复",
            }
        )


def _check_phone(
    frame: pd.DataFrame, config: ColumnConfig, issues: list[dict], active: pd.Series
) -> None:
    if not config.phone or config.phone not in frame.columns:
        return
    series = frame[config.phone]
    for pos in np.flatnonzero((series.notna() & active).to_numpy()):
        try:
            text = _cell_str(series.iat[int(pos)])
        except Exception as exc:
            _append_internal(issues, int(pos) + 2, config.phone, series.iat[int(pos)], exc)
            continue
        if re.fullmatch(PHONE_PATTERN, text) is None:
            hint = f"当前值 {len(text)} 位" if text.isdigit() else "当前值含非数字字符"
            issues.append(
                {
                    "行号": int(pos) + 2,
                    "列名": config.phone,
                    "错误类型": ISSUE_PHONE_FORMAT,
                    "原始值": text[:MAX_VALUE_LENGTH],
                    "问题描述": f"【{config.phone}】格式不正确，应为 1 开头的 11 位手机号（{hint}）",
                }
            )


def _check_date(
    frame: pd.DataFrame, config: ColumnConfig, issues: list[dict], active: pd.Series
) -> None:
    if not config.date or config.date not in frame.columns:
        return
    series = frame[config.date]
    for pos in np.flatnonzero((series.notna() & active).to_numpy()):
        value = series.iat[int(pos)]
        if isinstance(value, (datetime, date)):
            continue
        try:
            text = _cell_str(value)
        except Exception as exc:
            _append_internal(issues, int(pos) + 2, config.date, value, exc)
            continue
        if not _is_valid_date_text(text):
            issues.append(
                {
                    "行号": int(pos) + 2,
                    "列名": config.date,
                    "错误类型": ISSUE_DATE_FORMAT,
                    "原始值": text[:MAX_VALUE_LENGTH],
                    "问题描述": f"【{config.date}】格式不正确，应为 YYYY-MM-DD（当前值 {text[:20]}）",
                }
            )


def _is_valid_date_text(text: str) -> bool:
    if re.fullmatch(DATE_PATTERN, text) is None:
        return False
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _append_internal(issues: list[dict], row: int, column: str, value, exc: Exception) -> None:
    issues.append(
        {
            "行号": row,
            "列名": column,
            "错误类型": ISSUE_INTERNAL,
            "原始值": type(value).__name__,
            "问题描述": f"【{column}】单元格无法解析：{type(exc).__name__}",
        }
    )


def _cell_str(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def make_demo_dataframe() -> pd.DataFrame:
    """构造内置示例报名表：含缺失、重复、手机号/日期格式错误与全空行，供演示与验收使用。"""
    rows = [
        {"姓名": "张三", "学号": "S001", "手机号": "13800000001", "报名日期": "2025-01-01", "班级": "一班"},
        {"姓名": "李四", "学号": "S002", "手机号": "13800000002", "报名日期": "2025-01-01", "班级": "一班"},
        {"姓名": "王五", "学号": "S003", "手机号": "13800000003", "报名日期": "2025-01-02", "班级": "二班"},
        {"姓名": None, "学号": "S004", "手机号": "13800000004", "报名日期": "2025-01-02", "班级": "二班"},
        {"姓名": "赵六", "学号": "S001", "手机号": "13800000005", "报名日期": "2025-01-03", "班级": "一班"},
        {"姓名": "钱七", "学号": "S005", "手机号": "1234567890", "报名日期": "2025-01-03", "班级": "三班"},
        {"姓名": "孙八", "学号": "S006", "手机号": "13800000006", "报名日期": "2025/01/04", "班级": "三班"},
        {"姓名": "周九", "学号": "S007", "手机号": "13800000007", "报名日期": "2025-01-04", "班级": "三班"},
        {"姓名": "吴十", "学号": "S008", "手机号": 13800000008, "报名日期": "2025-01-05", "班级": "一班"},
        {"姓名": "郑一", "学号": "S009", "手机号": "13800000009", "报名日期": "2025-01-05", "班级": "二班"},
        {},
        {"姓名": "王二", "学号": "S010", "手机号": "13800000010", "报名日期": "2025-01-06", "班级": None},
        {"姓名": "冯三", "学号": "S011", "手机号": "23800000011", "报名日期": "2025-01-06", "班级": "一班"},
        {"姓名": "褚四", "学号": "S012", "手机号": "13800000012", "报名日期": "2025-02-30", "班级": "二班"},
        {"姓名": "卫五", "学号": "S013", "手机号": None, "报名日期": "2025-01-07", "班级": "一班"},
        {"姓名": "蒋六", "学号": "S014", "手机号": "13800000014", "报名日期": "2025-01-07", "班级": "三班"},
        {"姓名": "沈七", "学号": "S015", "手机号": "13800000015", "报名日期": "2025-01-08", "班级": "二班"},
        {"姓名": "韩八", "学号": "S016", "手机号": "13800000016", "报名日期": "2025-01-08", "班级": "三班"},
        {"姓名": "杨九", "学号": "S002", "手机号": "13800000017", "报名日期": "2025-01-09", "班级": "一班"},
        {"姓名": "朱十", "学号": "S017", "手机号": "13800000018", "报名日期": "2025-01-09", "班级": "二班"},
        {"姓名": "秦一", "学号": "S018", "手机号": "13800000019", "报名日期": "2025-01-10", "班级": "三班"},
        {"姓名": "尤二", "学号": "S019", "手机号": "13800000020", "报名日期": "2025-01-10", "班级": "一班"},
    ]
    columns = ["姓名", "学号", "手机号", "报名日期", "班级"]
    return pd.DataFrame(rows, columns=columns)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        source = sys.argv[1]
        table = load_table(source)
    else:
        source = "内存示例数据.csv"
        table = make_demo_dataframe()
    demo_config = ColumnConfig(
        name="姓名",
        student_id="学号",
        phone="手机号",
        date="报名日期",
        group="班级",
        required_columns=("姓名", "学号", "手机号"),
    )
    error_list, valid_rows = run_checks(table, demo_config)
    print(f"数据源：{source}（共 {len(table)} 行）")
    print(f"\n[错误清单] 共 {len(error_list)} 处问题：")
    if error_list.empty:
        print("  无")
    else:
        print(error_list.to_string(index=False))
    print(f"\n[有效数据] 共 {len(valid_rows)} 行")
