#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/home/ecs-user/learning_english"
VENV_ACTIVATE="${PROJECT_ROOT}/venv/bin/activate"
LOG_DIR="${PROJECT_ROOT}/logs"
PID_FILE="${LOG_DIR}/uvicorn.pid"
LOG_FILE="${LOG_DIR}/uvicorn.log"
APP="api.main:app"
HOST="0.0.0.0"
PORT="8000"
WORKERS="1"

cd "${PROJECT_ROOT}"

load_env() {
  set -a
  if [ -f ".env" ]; then
    # shellcheck disable=SC1091
    source ".env"
  fi
  set +a
}

activate_venv() {
  # shellcheck disable=SC1091
  source "${VENV_ACTIVATE}"
}

is_running() {
  if [ -f "${PID_FILE}" ]; then
    local pid
    pid="$(cat "${PID_FILE}")"
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_bg() {
  mkdir -p "${LOG_DIR}"
  activate_venv
  load_env

  if is_running; then
    echo "服务已在运行 (PID=$(cat "${PID_FILE}"))"
    return 0
  fi

  nohup python -m uvicorn "${APP}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level info \
    >> "${LOG_FILE}" 2>&1 &

  echo $! > "${PID_FILE}"
  sleep 1

  if ! is_running; then
    echo "服务启动失败，最近日志如下："
    tail -n 80 "${LOG_FILE}" || true
    return 1
  fi

  echo "服务已启动 (PID=$(cat "${PID_FILE}"))"
}

run_fg() {
  activate_venv
  load_env
  exec python -m uvicorn "${APP}" --host "${HOST}" --port "${PORT}" --log-level info
}

stop_service() {
  if is_running; then
    local pid
    pid="$(cat "${PID_FILE}")"
    echo "停止服务 (PID=${pid})..."
    kill "${pid}" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "${pid}" 2>/dev/null; then
      echo "优雅停止失败，强制结束 (PID=${pid})"
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${PID_FILE}"
  else
    echo "未检测到 PID，尝试清理遗留进程..."
    pkill -f "uvicorn ${APP}" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
}

status_service() {
  if is_running; then
    echo "运行中 (PID=$(cat "${PID_FILE}"))"
  else
    echo "未运行"
  fi
  ss -ltnp | grep ":${PORT}" || true
}

health_check() {
  curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:${PORT}/monitoring/dashboard"
}

tail_logs() {
  tail -n 200 -f "${LOG_FILE}"
}

case "${1:-}" in
  start)
    start_bg
    ;;
  run)
    run_fg
    ;;
  stop)
    stop_service
    ;;
  restart)
    stop_service
    start_bg
    ;;
  status)
    status_service
    ;;
  health)
    health_check
    ;;
  logs)
    tail_logs
    ;;
  *)
    echo "用法: $0 {start|run|stop|restart|status|health|logs}"
    exit 1
    ;;
esac
