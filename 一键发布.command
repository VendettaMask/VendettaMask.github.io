#!/bin/bash

set -u

cd "$(dirname "$0")" || exit 1

pause() {
  echo
  read -r -p "按回车键关闭窗口..." _
}

fail() {
  local status=$?
  echo
  echo "发布失败，错误码：$status"
  echo "请看上面的提示；修好后可以再次双击这个脚本。"
  pause
  exit "$status"
}

trap fail ERR

echo "== 地球屋：一键发布 =="
echo

if ! command -v git >/dev/null 2>&1; then
  echo "找不到 git，请先安装 Git。"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3。"
  exit 1
fi

branch="$(git branch --show-current)"
if [ -z "$branch" ]; then
  echo "当前不在普通 Git 分支上，无法自动发布。"
  exit 1
fi

echo "1/4 生成博客页面..."
python3 scripts/build-posts.py

echo
echo "2/4 检查本地改动..."
if git diff --quiet && git diff --cached --quiet; then
  if [ "$(git rev-list --count "origin/$branch..HEAD" 2>/dev/null || echo 0)" -gt 0 ]; then
    echo "没有新的文件改动，但有本地提交尚未推送。"
    echo
    echo "4/4 推送到 GitHub Pages..."
    git push origin "$branch"
    echo
    echo "发布完成！"
  else
    echo "没有检测到需要发布的新内容。"
  fi
  pause
  exit 0
fi

echo
echo "即将发布这些文件："
git status --short

echo
echo "3/4 提交到本地 Git..."
git add -A
commit_message="Publish blog $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$commit_message"

echo
echo "4/4 推送到 GitHub Pages..."
git pull --rebase origin "$branch"
git push origin "$branch"

echo
echo "发布完成！"
echo "提交信息：$commit_message"
pause
