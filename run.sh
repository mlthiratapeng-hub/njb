#!/bin/bash
cd "$(dirname "$0")"

export MHDDOS_DIR="${MHDDOS_DIR:-$HOME/MHDDoS}"
export API_KEY="${API_KEY:-CHANGE_ME_SECRET}"
export BOT_TOKEN="${BOT_TOKEN:-}"

# start API
python3 api_server.py &
API_PID=$!
sleep 3

# start bot
python3 bot.py &
BOT_PID=$!

trap "kill $API_PID $BOT_PID 2>/dev/null" EXIT
wait