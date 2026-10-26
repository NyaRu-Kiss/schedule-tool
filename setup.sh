#!/usr/bin/env bash
# ========================================
# 日程效率工具 - 配置引导脚本
# ========================================
# 用法: bash setup.sh
# 完成后用 python3 cli.py server 启动服务

set -e

cd "$(dirname "$0")"

echo "================================"
echo "  日程效率工具 - 配置引导"
echo "================================"
echo ""

# 1. 检查 .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ 已从模板创建 .env"
else
    echo "ℹ️  .env 已存在"
fi
echo ""

# 2. 检查 Python 依赖
echo "--- 检查依赖 ---"
if python3 -c "import flask, requests" 2>/dev/null; then
    echo "✅ flask + requests 已安装"
else
    echo "⚙️  安装依赖..."
    pip3 install --user --break-system-packages -q -r requirements.txt
    echo "✅ 依赖安装完成"
fi
echo ""

# 3. 收集 webhook 配置
echo "--- Webhook 配置 ---"
echo "请输入推送目标 URL（直接回车跳过则只打印控制台）:"
read -r webhook_url
if [ -n "$webhook_url" ]; then
    sed -i.bak "s|^SCHEDULE_WEBHOOK_URL=.*|SCHEDULE_WEBHOOK_URL=$webhook_url|" .env
    echo "✅ URL 已写入 .env"
else
    echo "ℹ️  跳过，提醒消息将只打印到控制台"
fi
echo ""

echo "选择消息格式:"
echo "  1) generic  — 通用 JSON（适合自建平台，推荐）"
echo "  2) wecom    — 企业微信群机器人"
echo "  3) feishu   — 飞书自定义机器人"
echo "  4) custom  — 自定义模板"
read -r -p "选择 [1-4]，默认 1: " fmt_choice
case $fmt_choice in
    2) fmt="wecom" ;;
    3) fmt="feishu" ;;
    4) fmt="custom" ;;
    *) fmt="generic" ;;
esac
sed -i.bak "s|^SCHEDULE_WEBHOOK_FORMAT=.*|SCHEDULE_WEBHOOK_FORMAT=$fmt|" .env
echo "✅ 格式设为 $fmt"
echo ""

# 4. 初始化数据库
echo "--- 初始化数据库 ---"
python3 -c "import db; db.init_db(); print('✅ 数据库已初始化')"
echo ""

# 5. 测试推送
if [ -n "$webhook_url" ]; then
    read -r -p "现在发送一条测试消息验证推送? [y/N] " test_choice
    if [[ "$test_choice" =~ ^[yY] ]]; then
        echo "发送测试消息..."
        python3 -c "
from remind import push
result = push('🧪 测试消息：日程效率工具配置成功', [], event_type='test')
if result['success']:
    print(f'✅ 推送成功 (HTTP {result[\"status_code\"]}, {result[\"duration_ms\"]}ms)')
else:
    print(f'❌ 推送失败: {result[\"error\"]}')
"
    fi
    echo ""
fi

echo "================================"
echo "  配置完成!"
echo "================================"
echo ""
echo "启动服务:  python3 cli.py server"
echo "添加待办:  python3 cli.py add \"写周报\" -p 2 -d \"2026-10-08T18:00\" -e 60"
echo "查看档期:  python3 cli.py today"
echo ""
echo "也可通过 HTTP API 调用: http://localhost:7800/api/health"