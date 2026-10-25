#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "[1/2] 安装依赖…"
pip install -r requirements.txt
echo "[2/2] 启动表格数据检查与简报生成助手…"
streamlit run app.py
