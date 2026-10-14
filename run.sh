#!/bin/bash
set -e
cd "$(dirname "$0")"

export MHDDOS_DIR="${MHDDOS_DIR:-$(pwd)}"
export API_KEY="${API_KEY:-kuy}"
export BOT_TOKEN="${BOT_TOKEN:-}"

echo "[RUN] MHDDOS_DIR = $MHDDOS_DIR"
echo "[RUN] API_KEY    = $API_KEY"

if [ ! -f "$MHDDOS_DIR/start.py" ]; then
    echo "[!] start.py not found"
    exit 1
fi

python3 api_server.py &
API_PID=$!
echo "[RUN] API PID = $API_PID"

for i in $(seq 1 15); do
    if curl -s "http://127.0.0.1:8000/" >/dev/null 2>&1; then
        echo "[RUN] API ready"
        break
    fi
    sleep 1
done

python3 bot.py &
BOT_PID=$!
echo "[RUN] BOT PID = $BOT_PID"

trap "echo '[RUN] stopping...'; kill $API_PID $BOT_PID 2>/dev/null; wait" EXIT
wait