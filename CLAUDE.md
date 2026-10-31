# temporal-compression

目标：建立第一个直接从原始视频出发、定量预测人类回忆中视觉经历时间压缩的模型，并裁决均匀采样 / 惊奇门控 / 可预测性压缩三种编码策略（目标期刊 NHB）。

## 方案文档（只读快照，源头是 Claude Docs）
- `docs/plan.md`：主页面，科学论证。与执行规范冲突时以它为准。
- `docs/execution_spec.md`：执行规范——模型定义（§2）、数据（§3）、特征（§4）、拟合（§5）、阶段验收（§6）、仓库结构（§7）。
- 两份文件开头注明了导出日期和 rev；原文更新后需重新导出。

## 0. 工作规则（照抄执行规范第 0 节）

每个阶段都按“计划 → 用户确认 → 代码和测试 → 集群运行 → 报告 → 验收”推进，验收不通过就不进入下一阶段。

1. 开始一个阶段前，先给出计划和伪代码，用户确认后再写代码。
2. 代码和单元测试一起推送到 GitHub 仓库；用户在 Slurm 集群上运行 `git pull && sbatch run.sh`。
3. Claude 的云端环境连不上 OSF 和集群。下载、GPU 计算都在集群上做，`run.sh` 必须自带下载步骤。
4. 每次运行记录 git commit、配置和种子；每个含随机性的实验跑三个全局种子。代码、模型权重和日志最终全部公开。
5. 每个阶段结束时写 `reports/<阶段>.md`：做了什么、验收是否通过、关键图表、下一步。不确定的事记入 `OPEN_QUESTIONS.md`。

禁止事项：

- 修改 `data/raw/` 下的任何原始文件。
- 在模型定义冻结（git tag `freeze-v1`）之前查看测试集上的拟合结果。
- 用新采集的人类数据调参。预注册分析脚本必须在采集前冻结。
- 编造、估算或从记忆里填写任何数字。所有数字都必须来自代码输出或有链接的文献。
- 代替用户对外联系、提交伦理审批或预注册。这些事 Claude 只准备草稿。

## 1. 配置值（执行规范第 1 节；机器可读版本在 `configs/site.yaml`，代码只从那里读）

| 配置项 | 值 |
| --- | --- |
| GitHub 仓库 | `temporal-compression` |
| Slurm partition / account / QoS | 参考用户已有的 slurm 脚本 `sbr-roihu.sh` |
| 集群数据根目录 | /scratch/project_2020002 |
| 每个作业的 GPU 型号和卡数 | Finland CSC Roihu 集群的 GH200 / 按需确定，节省着用 |
| WandB entity / project | 同仓库名 |
| 三个全局随机种子 | 42/43/44 |
| 结果回传方式 | 作业把 `results/` 提交到 `results` 分支 |
| Hugging Face 访问（V-JEPA 2、Wan、Qwen 权重） | 集群可联网，但下载到数据根目录，而非用户主目录 |

用户补充确认（2026-10-31）：Slurm account `project_2020002`；CPU 分区 `small`/`medium`；WandB entity `rongzhen-team`；集群可推送 `results` 分支。

## 运行
- `STAGE=S0 sbatch --partition=small --gres=none --mem=32G run.sh`（GPU 阶段直接 `STAGE=S1 sbatch run.sh`）。每个阶段一个入口 `scripts/sN_*.py`；run.sh 先跑 `pytest`，失败则不跑阶段。
- 本地测试：`python -m pytest -q tests`。
- 新开会话时先读 `OPEN_QUESTIONS.md` 和最近的 `reports/S*.md`。
