#!/usr/bin/env bash
# =============================================================================
# 能源 AI 平台 · 前后端服务管理脚本（Linux / macOS）
#
# 用法：
#   ./scripts/manage.sh <动作> [目标]
#   动作：start | stop | restart | status | logs
#   目标：backend | frontend | all   （默认 all）
#
# 示例：
#   ./scripts/manage.sh start            # 启动前后端
#   ./scripts/manage.sh stop backend     # 停止后端
#   ./scripts/manage.sh restart frontend # 重启前端
#   ./scripts/manage.sh status           # 查看状态
#   ./scripts/manage.sh logs backend     # 跟踪后端日志(Ctrl+C 退出)
#
# 说明：
#   - 服务以"后台进程组"方式运行，PID 与日志写入 logs/ 目录。
#   - 后端默认开启 --reload（开发热重载），停止时按进程组清理子进程。
#   - 可用环境变量覆盖：BACKEND_PORT(8000) FRONTEND_PORT(5173) HOST(0.0.0.0)
#     RELOAD(1=热重载,0=关闭)  AUTO_INSTALL(1=缺依赖自动安装)
# =============================================================================
set -uo pipefail

# ---- 路径与配置 -------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUN_DIR="$ROOT_DIR/logs"
mkdir -p "$RUN_DIR"

HOST="${HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
RELOAD="${RELOAD:-1}"
AUTO_INSTALL="${AUTO_INSTALL:-1}"

BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"
BACKEND_LOG="$RUN_DIR/backend.run.log"
FRONTEND_LOG="$RUN_DIR/frontend.run.log"

# ---- 终端颜色 ---------------------------------------------------------------
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[31m%s\033[0m\n" "$*"; }
c_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
info()    { printf "\033[36m[manage]\033[0m %s\n" "$*"; }

# ---- 进程探测 ---------------------------------------------------------------
# 读取 pid 文件并判断进程是否存活；存活则输出 pid
running_pid() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 1
  local pid
  pid="$(cat "$pidfile" 2>/dev/null)"
  [[ -n "${pid:-}" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "$pid"; return 0
  fi
  return 1
}

# 按端口查找监听进程（pid 文件丢失时的兜底）
pid_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$port" -s tcp:LISTEN 2>/dev/null | head -n1
  elif command -v fuser >/dev/null 2>&1; then
    fuser "${port}/tcp" 2>/dev/null | awk '{print $1}' | head -n1
  fi
}

# ---- 启动后台进程：setsid 使其成为独立进程组，便于整组停止 -----------------
spawn() {
  local pidfile="$1"; local logfile="$2"; shift 2
  : > "$logfile"
  setsid "$@" >>"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" > "$pidfile"
  echo "$pid"
}

# ---- 后端 -------------------------------------------------------------------
start_backend() {
  local pid
  if pid="$(running_pid "$BACKEND_PID")"; then
    c_yellow "后端已在运行 (pid=$pid, :$BACKEND_PORT)"; return 0
  fi
  if [[ -z "$(pid_on_port "$BACKEND_PORT")" ]]; then :; else
    c_yellow "端口 $BACKEND_PORT 已被占用，跳过启动后端（如需重启请先 stop backend）"; return 1
  fi

  cd "$BACKEND_DIR" || { c_red "找不到 backend 目录"; return 1; }
  if [[ ! -d .venv ]]; then
    if [[ "$AUTO_INSTALL" == "1" ]]; then
      info "创建虚拟环境并安装依赖（首次较慢）..."
      python3 -m venv .venv
      ./.venv/bin/pip install -r requirements.txt -q
    else
      c_red "缺少 .venv，请先创建或设 AUTO_INSTALL=1"; return 1
    fi
  fi

  local reload_flag=""
  [[ "$RELOAD" == "1" ]] && reload_flag="--reload"

  info "启动后端 uvicorn ($HOST:$BACKEND_PORT, reload=$RELOAD) ..."
  local pid
  pid="$(spawn "$BACKEND_PID" "$BACKEND_LOG" \
    "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app \
    --host "$HOST" --port "$BACKEND_PORT" $reload_flag)"

  sleep 2
  if kill -0 "$pid" 2>/dev/null; then
    c_green "后端已启动 (pid=$pid) → http://$HOST:$BACKEND_PORT  (docs: /docs)"
    info "日志: $BACKEND_LOG"
  else
    c_red "后端启动失败，请查看日志: $BACKEND_LOG"; tail -n 20 "$BACKEND_LOG" 2>/dev/null; return 1
  fi
}

# ---- 前端 -------------------------------------------------------------------
start_frontend() {
  local pid
  if pid="$(running_pid "$FRONTEND_PID")"; then
    c_yellow "前端已在运行 (pid=$pid, :$FRONTEND_PORT)"; return 0
  fi
  if [[ -z "$(pid_on_port "$FRONTEND_PORT")" ]]; then :; else
    c_yellow "端口 $FRONTEND_PORT 已被占用，跳过启动前端（如需重启请先 stop frontend）"; return 1
  fi

  cd "$FRONTEND_DIR" || { c_red "找不到 frontend 目录"; return 1; }
  if [[ ! -d node_modules ]]; then
    if [[ "$AUTO_INSTALL" == "1" ]]; then
      info "安装前端依赖（首次较慢）..."
      npm install
    else
      c_red "缺少 node_modules，请先 npm install 或设 AUTO_INSTALL=1"; return 1
    fi
  fi

  info "启动前端 vite ($HOST:$FRONTEND_PORT) ..."
  local pid
  pid="$(spawn "$FRONTEND_PID" "$FRONTEND_LOG" \
    npm run dev -- --host "$HOST" --port "$FRONTEND_PORT")"

  sleep 2
  if kill -0 "$pid" 2>/dev/null; then
    c_green "前端已启动 (pid=$pid) → http://$HOST:$FRONTEND_PORT"
    info "日志: $FRONTEND_LOG"
  else
    c_red "前端启动失败，请查看日志: $FRONTEND_LOG"; tail -n 20 "$FRONTEND_LOG" 2>/dev/null; return 1
  fi
}

# ---- 停止（按进程组优雅终止，超时强杀，端口兜底）---------------------------
stop_service() {
  local name="$1"; local pidfile="$2"; local port="$3"
  local pid; pid="$(cat "$pidfile" 2>/dev/null || true)"

  if [[ -z "${pid:-}" ]]; then
    # pid 文件丢失：按端口兜底
    pid="$(pid_on_port "$port")"
  fi

  if [[ -z "${pid:-}" ]]; then
    c_yellow "$name 未在运行"; rm -f "$pidfile"; return 0
  fi

  info "停止 $name (pid=$pid) ..."
  # 优先终止整个进程组（uvicorn --reload / npm 会派生子进程）
  if kill -TERM -- "-$pid" 2>/dev/null; then :; else kill -TERM "$pid" 2>/dev/null || true; fi

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done

  if kill -0 "$pid" 2>/dev/null; then
    c_yellow "$name 未退出，强制结束 ..."
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi

  # 端口仍被占用则再清理一次
  local leftover; leftover="$(pid_on_port "$port")"
  if [[ -n "${leftover:-}" ]]; then
    kill -KILL "$leftover" 2>/dev/null || true
  fi

  rm -f "$pidfile"
  c_green "$name 已停止"
}

# ---- 状态 -------------------------------------------------------------------
status_one() {
  local name="$1"; local pidfile="$2"; local port="$3"
  local pid
  if pid="$(running_pid "$pidfile")"; then
    c_green "$name: 运行中 (pid=$pid, 端口 $port)"
  elif pid="$(pid_on_port "$port")"; [[ -n "${pid:-}" ]]; then
    c_yellow "$name: 端口 $port 被进程 $pid 占用（无 pid 文件，可能是手动启动）"
  else
    c_red "$name: 已停止"
  fi
}

# ---- 动作分发 ---------------------------------------------------------------
do_start()   { case "$1" in backend) start_backend;; frontend) start_frontend;; all) start_backend; start_frontend;; esac; }
do_stop()    { case "$1" in backend) stop_service 后端 "$BACKEND_PID" "$BACKEND_PORT";; frontend) stop_service 前端 "$FRONTEND_PID" "$FRONTEND_PORT";; all) stop_service 前端 "$FRONTEND_PID" "$FRONTEND_PORT"; stop_service 后端 "$BACKEND_PID" "$BACKEND_PORT";; esac; }
do_status()  { status_one 后端 "$BACKEND_PID" "$BACKEND_PORT"; status_one 前端 "$FRONTEND_PID" "$FRONTEND_PORT"; }
do_logs()    {
  case "$1" in
    backend)  tail -n 60 -f "$BACKEND_LOG";;
    frontend) tail -n 60 -f "$FRONTEND_LOG";;
    all)      tail -n 30 -f "$BACKEND_LOG" "$FRONTEND_LOG";;
  esac
}

usage() {
  cat <<EOF
用法: $0 <start|stop|restart|status|logs> [backend|frontend|all]
  start    启动服务（默认 all）
  stop     停止服务
  restart  重启服务
  status   查看运行状态
  logs     跟踪日志输出 (Ctrl+C 退出)
EOF
}

main() {
  local action="${1:-}"; local target="${2:-all}"
  case "$target" in backend|frontend|all) ;; *) c_red "未知目标: $target"; usage; exit 1;; esac
  case "$action" in
    start)   do_start "$target";;
    stop)    do_stop "$target";;
    restart) do_stop "$target"; sleep 1; do_start "$target";;
    status)  do_status;;
    logs)    do_logs "$target";;
    -h|--help|help|"") usage;;
    *) c_red "未知动作: $action"; usage; exit 1;;
  esac
}

main "$@"
