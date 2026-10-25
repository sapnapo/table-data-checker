"""生成 1000 行含各类错误的报名表示例文件（手工验收与性能测试用）。

用法：python sample_data/make_sample.py [输出路径]
默认输出：sample_data/报名示例.xlsx
"""

import sys
from pathlib import Path

import pandas as pd

DEFAULT_OUTPUT = Path(__file__).parent / "报名示例.xlsx"
N_ROWS = 1000
CLASSES = ["一班", "二班", "三班", "四班"]


def make_sample(n: int = N_ROWS) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = {
            "姓名": f"学生{i:04d}",
            "学号": f"S{i:04d}" if i % 97 else "S0000",
            "手机号": f"138{i:08d}" if i % 53 else "1234567890",
            "报名日期": "2025-03-01" if i % 41 else "2025/02/30",
            "班级": CLASSES[i % len(CLASSES)],
        }
        if i % 211 == 0:
            row["姓名"] = None
        if i % 317 == 0:
            row["手机号"] = None
        if i % 500 == 0:
            row = {}
        rows.append(row)
    return pd.DataFrame(rows, columns=["姓名", "学号", "手机号", "报名日期", "班级"])


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    df = make_sample()
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output, index=False)
    print(f"已生成示例文件：{output}（{len(df)} 行 × {len(df.columns)} 列）")


if __name__ == "__main__":
    main()
