#!/bin/sh
ip=$(cat .env | grep -E "^host" | awk -F '=' '{print $2}' | awk -F '\r' '{print $1}' | tr -d '[:space:]')
port=$(cat .env | grep -E "^port" | awk -F '=' '{print $2}' | awk -F '\r' '{print $1}' | tr -d '[:space:]')
gcmd=$(cat .env | grep -E "^gunicornCmd" | awk -F '=' '{print $2}' | awk -F '\r' '{print $1}' | tr -d '[:space:]')
$gcmd main:app -b $ip:$port -k uvicorn.workers.UvicornWorker --timeout 30 --daemon
echo "start server success ~"

pythoncmd=$(cat .env | grep -E "^pythonCmd" | awk -F '=' '{print $2}' | awk -F '\r' '{print $1}' | tr -d '[:space:]')
nohup $pythoncmd getStock.py 2>&1 &
echo "start run $pythoncmd getStock.py success ~"