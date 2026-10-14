#!/bin/bash
# run.sh — start API + bot
set -e

cd "$(dirname "$0")"

# fix C2: MHDDOS_DIR = repo root (ที่เดียวกับ start.py)
export MHDDOS_DIR="${MHDDOS_DIR:-$(pwd)}"
export BOT_TOKEN="${BOT_TOKEN:-}"

echo "[RUN] MHDDOS_DIR = $MHDDOS_DIR"

if [ ! -f "$MHDDOS_DIR/start.py" ]; then
    echo "[!] start.py not found in $MHDDOS_DIR"
    echo "    แก้ MHDDOS_DIR ให้ชี้ไปที่ repo ที่มี start.py"
    exit 1
fi

# start API
python3 api_server.py &
API_PID=$!
echo "[RUN] API PID = $API_PID"

# รอ API พร้อม (fix L1)
for i in $(seq 1 15); do
    if curl -s "http://127.0.0.1:8000/" >/dev/null 2>&1; then
        echo "[RUN] API ready"
        break
    fi
    sleep 1
done

# start bot
python3 bot.py &
BOT_PID=$!
echo "[RUN] BOT PID = $BOT_PID"

# fix M1: graceful shutdown
trap "echo '[RUN] stopping...'; kill $API_PID $BOT_PID 2>/dev/null; wait" EXIT

wait