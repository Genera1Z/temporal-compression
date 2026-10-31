<!--
导出日期：2026-10-31
来源：Claude Docs https://claude.ai/artifact/RDf4cN41e2FEbbd1w8ybgX
Tab：执行规范（Claude Code）
文档 rev：111
本文件为只读快照；以 Claude Docs 原文为准，原文更新后需重新导出。
-->

# 执行规范（Claude Code）

本页让一个没看过对话的 Claude Code 会话能直接接手：规则、配置、模型定义、数据、阶段与验收。科学论证见主页面，二者冲突时以主页面为准。

## 0. 工作规则

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

## 1. 待用户填写的配置

下表填完之前，S0 不能开始。写入仓库的 `configs/site.yaml`，不要硬编码在代码里。

| 配置项 | 值 |
| --- | --- |
| GitHub 仓库（建议名 `temporal-compression`） | `temporal-compression` |
| Slurm partition / account / QoS | 参考我的已有的slurm脚本\`sbr-roihu.sh\` |
| 集群数据根目录 | /scratch/project\_2020002 |
| 每个作业的 GPU 型号和卡数 | Finland CSC Roihu集群的GH200 / 按需确定，节省着用 |
| WandB entity / project | 同仓库名 |
| 三个全局随机种子（沿用 object-centric-bench 的约定） | 42/43/44 |
| 结果回传方式：作业把 `results/` 提交到 `results` 分支，或用户粘贴日志 | 前者 |
| Hugging Face 访问（V-JEPA 2、Wan、Qwen 权重） | 集群可联网，但希望下载到数据根目录，而非用户主目录 |

## 2. 模型的形式定义

三种策略只在“每个事件存多少单元”上不同，各有恰好 2 个自由参数；读出模块和干扰项（共 5 个参数）完全共享。这是理论裁决公平的前提，修改任何一项都要先问用户。

**符号。** 视频 v 由 N 个事件组成，事件 j 时长 Tⱼ（秒），事件边界取自刺激设计。e(t) 是第 4 节定义的预测误差，用训练集合并的均值和标准差做 z 标准化。禁止逐视频标准化，否则惊奇门控会失去视频间的差异。

**编码：事件 j 存下的单元数 nⱼ。**

```latex
\begin{aligned}
\text{U（均匀采样）:}\quad & n_j = r\,T_j^{\alpha} && (r,\alpha)\\
\text{SG（惊奇门控）:}\quad & n_j = 1+\sum_{p\in\mathcal{P}_j(\delta)}\sigma\!\left(\frac{e(t_p)-\theta}{0.1}\right) && (\theta,\delta)\\
\text{PC（可预测性压缩）:}\quad & n_j = 1+\frac{1}{\kappa}\int_{t\in j}\operatorname{softplus}\big(e(t)\big)^{\gamma}\,dt && (\kappa,\gamma)
\end{aligned}
```

其中 𝒫ⱼ(δ) 是事件 j 内间隔至少 δ 秒的局部极大值。δ 在 {0.5, 1, 2} s 上网格搜索，其余参数连续优化。

**读出（三种策略共享）。** 工作记忆容量有限，序列中的事件分享容量；保留下来的单元按原速回放，丢弃的单元被跳过。

```latex
\begin{aligned}
K_N &= \frac{K}{1+\beta(N-1)}, \qquad m_j = K_N\left(1-e^{-n_j/K_N}\right)\\
R_j &= s\,T_j\,\frac{m_j}{n_j}, \qquad D = t_0+\sum_{j=1}^{N}R_j\\
D_{\text{obs}} &= (1-\lambda)\,D+\lambda\,\bar D_{\text{block}}, \qquad \log D^{\text{trial}}\sim\mathcal N\!\left(\log D_{\text{obs}}+u_{\text{subj}},\ \sigma^2\right)\\
\text{口头回忆单元数} &= \textstyle\sum_j m_j
\end{aligned}
```

共享参数：t₀（启动耗时）、s（回放速度）、K（容量）、β（序列分享）、λ（中心趋势）。D̄\_block 是该被试所在区组的实际平均时长。逐事件按键的数据（Open Mind 2025 实验 2）只对第一个事件加 t₀。

**哪些单元被保留。** U 随机保留；SG 和 PC 优先保留平均预测误差最高的单元。在有口头回忆内容的数据上，这一差异可以直接检验。

**因果实验的 2×2 预测。** 两个因子是 A = ∑softplus(e)^γ（总预测误差）和 B = 超过 θ 的误差峰个数；时长固定在压缩区（默认 12 s）。θ 和 γ 取 S4 拟合的后验，设计必须在其 95% 区间内稳健。

| 策略 | A 主效应 | B 主效应 |
| --- | --- | --- |
| U（均匀采样） | 无 | 无 |
| SG（惊奇门控） | 无 | 峰多 → 单元多、压缩少 |
| PC（可预测性压缩） | 误差高 → 单元多、压缩少 | 无 |

## 3. 数据与划分

参数只在开发集上拟合，然后冻结，在留出集上做零样本测试。OSF 项目页面由 JavaScript 渲染，文件清单只能在集群上用 osfclient 取得，尚未核实。

| 数据 | OSF / 来源 | 角色 | 状态 |
| --- | --- | --- | --- |
| Leroy, Majerus & D'Argembeau 2024（Cognition）：单事件 3–15 s，90 人 | zkwf2 | 开发集 | 已公开 |
| Leroy & D'Argembeau 2025（Memory）：启动耗时、四种时长范围 | 2xt93 | 开发集，约束 t₀ 和 λ | 已公开 |
| Leroy & D'Argembeau 2025（Open Mind）：1–3 个事件序列 | 6aecj | 零样本测试 | 已公开 |
| Leroy, Majerus & D'Argembeau 2025（Memory & Cognition）：边界密度 ± 双任务，含口头描述 | 待确认 | 第二测试集（含回忆内容） | 向作者索取 |
| Jeunehomme et al. 2020：佩戴摄像头的真实事件 | uny8r | 可选 | 视频很可能未公开 |
| Fountas 2022 / Roseboom 2019：回溯时长估计 | 待确认 | 与 Fountas 模型正面对比 | 待确认 |
| Memento10k | 需申请 | 可记忆度的大规模检验 | 待确认 |

下载方式（在集群上）：`pip install osfclient`，然后 `osf -p zkwf2 clone data/raw/zkwf2`，其余编号同理。还要为每个文件生成校验和，写入 `data/manifest.json`。

若某份数据缺视频，只用它的行为数据约束读出参数，不用于策略裁决，并写进 `OPEN_QUESTIONS.md`。

## 4. 特征提取

主信号是 V-JEPA 2 的时间预测误差 e(t)；主结论还要求在 VideoMAEv2 上方向一致。

- **V-JEPA 2**：`facebook/vjepa2-vitl-fpc64-256`，通过 transformers 的 `VJEPA2Model` 调用自带预测器，用 `context_mask` / `target_mask` 屏蔽未来的时间块。e(t) = 预测器输出与编码器在目标时间块上的输出之间的平均 L1 距离。具体定义以 Garrido 2025 的代码仓库 jepa-intuitive-physics 为准，先读它再实现。
- **滑动窗口**：模型按 64 帧训练，输入帧率以模型卡为准。稳健性网格为窗口 {16, 32, 64} 帧 × 两种帧率。验收标准：各设置下逐视频 ∑e 的秩相关 ≥ 0.8。
- **复核模型**：VideoMAEv2 对屏蔽未来帧的像素重建误差，jepa-intuitive-physics 已支持。
- **低层协变量**：光流运动能量（torchvision 的 RAFT）、亮度、相邻帧 CLIP 嵌入的变化量。它们既用于因果实验的匹配，也用作基线。
- **基线模型**：只用时长（即 U）；只用运动能量；按 Fountas 2022 复现的“显著变化计数”（逐帧 CNN 特征变化超阈次数，标注为本文的复现版本）。

必须有的单元测试：输出形状和时间对齐；固定种子时结果可复现；静止视频的 ∑e 低于噪声视频；倒放视频的低层协变量均值与原视频相同；缓存命中时不重算。

## 5. 行为预处理、拟合与模型比较

模型先要证明“能分辨三种策略”，然后才允许在真实数据上裁决。

**预处理**

- 逐试次计算时间比 = 回放时长 / 实际时长，沿用原论文的剔除标准。
- 单元测试：复现原论文报告的均值。例如 zkwf2 五种时长的比值为 1.23、1.09、0.98、0.89、0.83，允许误差 ≤ 0.02。
- 噪声上限：逐视频均值的分半信度（1000 次随机切分，Spearman–Brown 校正）。所有解释方差都相对它报告。
- 口头回忆 → 经验单元：用开源 LLM（Qwen 系列）切分，并对齐到 VLM 生成的视频单元描述。先在人工编码上校验，ICC ≥ 0.8 才可使用。

**拟合**

1. 先对逐视频均值做非线性最小二乘（scipy），用于快速调试。
2. 再做层级贝叶斯拟合（NumPyro NUTS）：log t₀ 和 log s 带被试随机效应，弱信息先验，并做先验预测检查。
3. 恢复实验必须先于真实数据完成。在真实刺激上，用每种策略按真实的试次数和噪声水平模拟数据，再用三种策略分别拟合，得到模型混淆矩阵和参数恢复图。

**模型比较（胜出标准在 S4 之前写定）**

- 开发集：PSIS-LOO 的 ELPD（ArviZ）。
- 测试集：冻结后验下的对数预测密度，以及逐视频均值的 r 和 R²（相对噪声上限）。
- 一种策略算胜出，需要同时满足两条：对另两种的 ΔELPD > 2 SE；测试集 r 高于对手，且视频层面 bootstrap 的 95% 区间不含 0。

## 6. 阶段与验收标准

S0–S5 可以全部自动化；S6 只准备草稿；S7 在数据采集后只运行冻结的脚本。

| 阶段 | 产出 | 验收标准 |
| --- | --- | --- |
| S0 环境与数据审计 | `data/manifest.json`、`reports/S0.md` | zkwf2、2xt93、6aecj 的视频和逐试次数据齐全；各自复现原文报告的均值 |
| S1 特征提取 | `features/{vjepa2,videomae,lowlevel}/` | 单元测试全部通过；窗口/帧率稳健性 ≥ 0.8；报告两个模型之间的相关 |
| S2 行为预处理 | 逐试次表、逐视频表、噪声上限 | 原文主要统计检验的方向和显著性都能复现 |
| S3 模型与参数恢复 | 混淆矩阵、参数恢复图 | 对角线 ≥ 0.8；共享参数恢复 r ≥ 0.7。不达标就如实记录，并作为 S5 必要性的证据 |
| S4 拟合与零样本测试 | 打 tag `freeze-v1` 后才跑测试集；产出核心图 | 按第 5 节的胜出标准判定，结果无论正负都写报告。这张图就是联系合作方用的核心图 |
| S5 刺激设计与功效分析 | 2×2 刺激集、匹配报告、功效模拟 | 四格低层协变量的差异 \|d\| < 0.2；A 与 B 的相关 \|r\| < 0.2；给出功效 0.95（Registered Report）和 0.90（常规 Article）对应的样本量 |
| S6 人工环节（只准备草稿） | 致 Leroy/D'Argembeau 和 Bainbridge 的邮件、NHB 投稿前咨询、Aalto 伦理申请、OSF 预注册、Gorilla 实验规格 | 用户审阅并亲自发出 |
| S7 采集后分析 | 运行冻结脚本得到的结果 | 只有预注册的分析进入主结论，探索性分析单独标注 |

S5 刺激的来源：首选用 Wan 系列图生视频模型，从同一起始帧生成多个续写，再按 A、B 筛选。备选是从大型自然视频库中筛选。另加倒放和子段打乱两种对照，它们与原视频的帧和运动能量完全相同。

## 7. 仓库结构

一个阶段对应一个入口脚本，`run.sh` 用 `STAGE` 环境变量选择要跑哪个阶段。

```text
temporal-compression/
  configs/        site.yaml（第 1 节）、features.yaml、models.yaml、design.yaml
  data/           raw/（只读）、interim/、manifest.json
  tcomp/
    data/         OSF 读取、剔除标准、逐试次与逐视频表
    features/     vjepa2.py、videomae.py、lowlevel.py、fountas_baseline.py
    models/       encoding.py（U/SG/PC）、readout.py、likelihood.py
    fit/          lsq.py、numpyro_hier.py、recovery.py、compare.py
    recall/       llm_segment.py、align.py
    design/       generate_wan.py、select_2x2.py、match.py、power.py
  scripts/        s0_audit.py … s7_confirmatory.py
  tests/          每个模块一个测试文件，含“复现原文均值”的测试
  reports/        S0.md … S7.md
  results/        各阶段的 JSON/CSV/PNG
  run.sh          Slurm 入口
  OPEN_QUESTIONS.md
```

## 8. 开工前要读的文献

前三项是要复现的范式和数据，必须先读；其余用于实现细节和定位。

1. [Leroy, Majerus & D'Argembeau 2024（Cognition）](https://orbi.uliege.be/bitstream/2268/316194/1/WMCE1_AcceptedVersion_01April2024.pdf)
2. [Leroy & D'Argembeau 2025（Open Mind）](https://orbi.uliege.be/bitstream/2268/338910/1/opmi.a.276.pdf)
3. [Leroy 2026 报告：三项研究的汇总与开放问题](https://orbi.uliege.be/bitstream/2268/348688/1/TC_Talk_100926_NL.pdf)
4. [Memory 2025：启动耗时与中心趋势](https://www.tandfonline.com/doi/full/10.1080/09658211.2025.2551232)
5. [Fountas et al. 2022](https://www.biorxiv.org/content/10.1101/2020.02.17.953133.full.pdf)
6. [V-JEPA 直觉物理（Garrido et al. 2025）](https://arxiv.org/html/2502.11831v1)；[VJEPA2Model 文档](https://huggingface.co/docs/transformers/model_doc/vjepa2)
7. [CRUISE](https://www.biorxiv.org/content/10.1101/2025.07.31.667952v1.full)；[随机树模型](https://arxiv.org/pdf/2412.01806)
8. [Spens & Burgess 2024（NHB）](https://www.nature.com/articles/s41562-023-01799-z)；[Spens & Burgess 2026](https://www.nature.com/articles/s41467-026-74357-6)
9. [Bainbridge 实验室发表列表](https://brainbridgelab.uchicago.edu/publications)（可记忆度与加工效率、可压缩性）
10. [NHB Registered Report 指南](https://media.nature.com/original/nature-cms/uploads/ckeditor/attachments/4127/RegisteredReportsGuidelines_NatureHumanBehaviour.pdf)
