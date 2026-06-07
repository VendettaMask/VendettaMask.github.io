#!/bin/bash

set -u

cd "$(dirname "$0")" || exit 1

echo "== 地球屋博客编辑器 =="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3。"
  echo
  read -r -p "按回车键关闭窗口..." _
  exit 1
fi

python3 editor/server.py
