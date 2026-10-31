#!/bin/bash
#SBATCH --job-name=oclz
#SBATCH --account=project_2019964
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:gh200:1          # 申请 3 块 GPU
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24          # 总共 24 个核，分给 6 个任务
#SBATCH --time=10:00:00
#SBATCH --mem=240G
# #SBATCH --mail-type=BEGIN,FAIL,END

module load python-pytorch
nvidia-smi

# 接收外部传入的随机种子
SEED=${1:-42}
echo "🚀 开始运行随机种子 Seed: ${SEED}"

# 1. 同步数据集
echo "正在复制数据集到${TMPDIR}"
cp -r /scratch/project_2008396/Datasets/clevrtex $TMPDIR/
cp -r /scratch/project_2008396/Datasets/coco $TMPDIR/
cp -r /scratch/project_2008396/Datasets/voc $TMPDIR/
cp -r /scratch/project_2008396/Datasets/movi_c $TMPDIR/
cp -r /scratch/project_2008396/Datasets/movi_e $TMPDIR/
cp -r /scratch/project_2008396/Datasets/ytvis_2022 $TMPDIR/
ls -la $TMPDIR

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# --------------------------------------------------------------------
# 🚀 终极放飞性能：去掉 srun！用 sleep 错开 3 秒，完美躲过容器启动死锁！
# --------------------------------------------------------------------

CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsa_r-clevrtex.py --seed $SEED > logs_s${SEED}_m1_d1.txt 2>&1 &
sleep 3
CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsa_r-coco.py --seed $SEED > logs_s${SEED}_m1_d2.txt 2>&1 &
sleep 3
CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsa_r-voc.py --seed $SEED > logs_s${SEED}_m1_d3.txt 2>&1 &

sleep 3
CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsav_c-movi_c.py --seed $SEED > logs_s${SEED}_m2_d1.txt 2>&1 &
sleep 3
CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsav_c-movi_e.py --seed $SEED > logs_s${SEED}_m2_d2.txt 2>&1 &
sleep 3
CUDA_VISIBLE_DEVICES=0 python train.py --project samodulat --data_dir $TMPDIR --cfg_file config-smoothsa/smoothsav_r-ytvis.py --seed $SEED > logs_s${SEED}_m2_d3.txt 2>&1 &

# ❗ 必须加 wait
wait
echo "🎉 Seed ${SEED} 的所有任务已全部跑完！"
