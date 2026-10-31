#!/bin/bash
# Slurm 入口（执行规范 §7）。用 STAGE 选择阶段：
#   STAGE=S0 sbatch run.sh            # 或 sbatch run.sh S0
# 资源按阶段在命令行覆盖，例如：
#   STAGE=S1 sbatch --time=08:00:00 --mem=120G run.sh
# 下列默认值参照 sbr-roihu.sh，按“节省着用”调小；account/partition 同 configs/site.yaml。
#SBATCH --job-name=tcomp
#SBATCH --account=project_2019964
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:gh200:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --mem=64G
#SBATCH --output=logs/slurm-%x-%j.out

set -euo pipefail

STAGE=${STAGE:-${1:-}}
if [[ -z "${STAGE}" ]]; then
  echo "❌ 未指定阶段：STAGE=S0 sbatch run.sh" >&2; exit 2
fi

cd "${SLURM_SUBMIT_DIR:-$(dirname "$(readlink -f "$0")")}"
REPO_DIR=$(pwd)
mkdir -p logs

module load python-pytorch
nvidia-smi || echo "（无 GPU 或 nvidia-smi 不可用）"

# ---------------------------------------------------------------------
# 1. 读取 configs/site.yaml（唯一配置来源，不在脚本里硬编码路径）
# ---------------------------------------------------------------------
eval "$(python3 - <<'PY'
import yaml, shlex
c = yaml.safe_load(open("configs/site.yaml"))
p = c["paths"]
out = {
    "DATA_ROOT": p["data_root"], "PROJECT_ROOT": p["project_root"],
    "RAW_DIR": p["raw"], "INTERIM_DIR": p["interim"],
    "HF_HOME": p["hf_home"], "VENV_DIR": p["venv"],
    "WANDB_ENTITY": c["wandb"]["entity"] or "", "WANDB_PROJECT": c["wandb"]["project"],
    "SEEDS": " ".join(str(s) for s in c["seeds"]),
    "RESULTS_BRANCH": c["results"]["branch"],
}
for k, v in out.items():
    print(f"export {k}={shlex.quote(str(v))}")
PY
)"
export HF_HUB_CACHE="${HF_HOME}/hub"
export TORCH_HOME="${DATA_ROOT}/torch_cache"
export PIP_CACHE_DIR="${DATA_ROOT}/pip_cache"
mkdir -p "${PROJECT_ROOT}" "${RAW_DIR}" "${INTERIM_DIR}" "${HF_HOME}" "${TORCH_HOME}"

# ---------------------------------------------------------------------
# 2. Python 环境：在数据根目录建 venv（继承模块里的 torch），不占主目录
# ---------------------------------------------------------------------
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv --system-site-packages "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
if [[ -f requirements.txt ]]; then
  pip install --quiet -r requirements.txt
fi

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# ---------------------------------------------------------------------
# 3. 运行记录：git commit、配置、种子（执行规范 §0 第 4 条）
# ---------------------------------------------------------------------
GIT_COMMIT=$(git rev-parse HEAD)
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "⚠️  工作区有未提交改动，结果将无法精确溯源" >&2
  GIT_COMMIT="${GIT_COMMIT}-dirty"
fi
export GIT_COMMIT
RUN_ID="${STAGE}_$(date +%Y%m%d-%H%M%S)_${SLURM_JOB_ID:-local}"
LOG_DIR="logs/${RUN_ID}"
mkdir -p "${LOG_DIR}"
cp configs/*.yaml "${LOG_DIR}/"
echo "🚀 STAGE=${STAGE} commit=${GIT_COMMIT} seeds=(${SEEDS}) run=${RUN_ID}"

# ---------------------------------------------------------------------
# 4. 阶段分派：一个阶段一个入口脚本；STOCHASTIC=1 的阶段跑三个全局种子
# ---------------------------------------------------------------------
case "${STAGE}" in
  S0) ENTRY=scripts/s0_audit.py;        STOCHASTIC=0 ;;
  S1) ENTRY=scripts/s1_features.py;     STOCHASTIC=0 ;;
  S2) ENTRY=scripts/s2_behavior.py;     STOCHASTIC=0 ;;
  S3) ENTRY=scripts/s3_recovery.py;     STOCHASTIC=1 ;;
  S4) ENTRY=scripts/s4_fit_test.py;     STOCHASTIC=1 ;;
  S5) ENTRY=scripts/s5_design.py;       STOCHASTIC=1 ;;
  S6) echo "S6 只准备草稿，不在集群上运行"; exit 0 ;;
  S7) ENTRY=scripts/s7_confirmatory.py; STOCHASTIC=1 ;;
  *)  echo "❌ 未知阶段 ${STAGE}" >&2; exit 2 ;;
esac
if [[ ! -f "${ENTRY}" ]]; then
  echo "❌ ${ENTRY} 尚未实现（该阶段计划需先经用户确认）" >&2; exit 3
fi

COMMON_ARGS=(--config configs/site.yaml --run-id "${RUN_ID}")
if [[ "${STOCHASTIC}" == 1 ]]; then
  PIDS=()
  for SEED in ${SEEDS}; do
    python "${ENTRY}" "${COMMON_ARGS[@]}" --seed "${SEED}" > "${LOG_DIR}/s${SEED}.txt" 2>&1 &
    PIDS+=($!)
    sleep 3   # 同 sbr-roihu.sh：错开启动，避免容器启动死锁
  done
  FAIL=0
  for PID in "${PIDS[@]}"; do wait "${PID}" || FAIL=1; done
  [[ "${FAIL}" == 0 ]] || { echo "❌ 至少一个种子失败，见 ${LOG_DIR}/" >&2; exit 1; }
else
  python "${ENTRY}" "${COMMON_ARGS[@]}" --seed "${SEEDS%% *}" 2>&1 | tee "${LOG_DIR}/main.txt"
fi

# ---------------------------------------------------------------------
# 5. 结果回传：把 results/ 和本次日志提交到 results 分支（site.yaml: results.branch）
# ---------------------------------------------------------------------
WT="${TMPDIR:-/tmp}/tcomp_results_${SLURM_JOB_ID:-$$}"
git fetch origin "${RESULTS_BRANCH}" 2>/dev/null || true
if git show-ref --verify --quiet "refs/remotes/origin/${RESULTS_BRANCH}"; then
  git worktree add -B "${RESULTS_BRANCH}" "${WT}" "origin/${RESULTS_BRANCH}"
else
  git worktree add --detach "${WT}"
  git -C "${WT}" checkout --orphan "${RESULTS_BRANCH}"
  git -C "${WT}" rm -rq --cached .
  git -C "${WT}" clean -fdq
fi
mkdir -p "${WT}/results" "${WT}/logs"
cp -r results/. "${WT}/results/"
cp -r "${LOG_DIR}" "${WT}/logs/"
git -C "${WT}" add results logs
git -C "${WT}" commit -q -m "results: ${STAGE} @ ${GIT_COMMIT} (run ${RUN_ID}, seeds ${SEEDS})" || echo "（无新结果）"
git -C "${WT}" push -u origin "${RESULTS_BRANCH}"
git worktree remove --force "${WT}"

echo "🎉 ${STAGE} 完成：${RUN_ID}"
