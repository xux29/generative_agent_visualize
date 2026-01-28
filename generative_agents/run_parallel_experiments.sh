#!/bin/bash
# 健康模拟实验并行运行脚本（补位机制：始终保持2个并行）
# 用法: bash run_parallel_experiments.sh
# 实时查看: tail -f results/health/exp_*.log

cd "$(dirname "$0")"

SCENARIO="diabetes"
DAYS=90
MAX_PARALLEL=9  # 有23个API key，可以全部并行
LOG_DIR="results/health"
mkdir -p "$LOG_DIR"

# 9种实验组合: (初始分, 自律程度)
EXPERIMENTS=(
    "90 high"
    "90 medium"
    "90 low"
    "75 high"
    "75 medium"
    "75 low"
    "60 high"
    "60 medium"
    "60 low"
)

TOTAL=${#EXPERIMENTS[@]}
NEXT_IDX=0
RUNNING_PIDS=()
RUNNING_NAMES=()
COMPLETED=0
FAILED=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

start_experiment() {
    local idx=$1
    local params=(${EXPERIMENTS[$idx]})
    local init_health=${params[0]}
    local discipline=${params[1]}
    local exp_num=$((idx + 1))
    local log_file="${LOG_DIR}/exp_${exp_num}_init${init_health}_${discipline}.log"

    log "启动实验 ${exp_num}/${TOTAL}: init=${init_health}, discipline=${discipline}"

    python start_health_simulation.py \
        --scenario "$SCENARIO" \
        --initial-health "$init_health" \
        --discipline "$discipline" \
        --days "$DAYS" \
        --batch \
        > "$log_file" 2>&1 &

    local pid=$!
    RUNNING_PIDS+=($pid)
    RUNNING_NAMES+=("exp${exp_num}(init${init_health}_${discipline})")
    log "  PID=$pid, 日志: $log_file"
}

# 启动前两个实验
for ((i=0; i<MAX_PARALLEL && i<TOTAL; i++)); do
    start_experiment $NEXT_IDX
    NEXT_IDX=$((NEXT_IDX + 1))
done

log "初始启动完成，当前并行: ${#RUNNING_PIDS[@]}个"
log "实时查看日志: tail -f ${LOG_DIR}/exp_*.log"
echo ""

# 补位循环：等待任意一个完成，然后补位
while [ ${#RUNNING_PIDS[@]} -gt 0 ]; do
    # 检查哪个进程结束了
    for i in "${!RUNNING_PIDS[@]}"; do
        pid=${RUNNING_PIDS[$i]}
        if ! kill -0 "$pid" 2>/dev/null; then
            # 进程结束
            wait "$pid"
            exit_code=$?
            name=${RUNNING_NAMES[$i]}

            if [ $exit_code -eq 0 ]; then
                COMPLETED=$((COMPLETED + 1))
                log "✓ ${name} 完成 (${COMPLETED}+${FAILED}/${TOTAL})"
            else
                FAILED=$((FAILED + 1))
                log "✗ ${name} 失败(exit=$exit_code) (${COMPLETED}+${FAILED}/${TOTAL})"
            fi

            # 移除已完成的
            unset 'RUNNING_PIDS[i]'
            unset 'RUNNING_NAMES[i]'
            RUNNING_PIDS=("${RUNNING_PIDS[@]}")
            RUNNING_NAMES=("${RUNNING_NAMES[@]}")

            # 补位：启动下一个
            if [ $NEXT_IDX -lt $TOTAL ]; then
                start_experiment $NEXT_IDX
                NEXT_IDX=$((NEXT_IDX + 1))
            fi

            break
        fi
    done

    sleep 5
done

echo ""
log "=========================================="
log "全部完成！成功: ${COMPLETED}, 失败: ${FAILED}, 总计: ${TOTAL}"
log "=========================================="
log "结果目录: ${LOG_DIR}/"
ls -la "${LOG_DIR}"/exp_*.log 2>/dev/null
