# OPEN_QUESTIONS

不确定的事记在这里（执行规范 §0 第 5 条）。解决后注明结论和日期，不要删除。

| # | 问题 | 来源 | 状态 |
| --- | --- | --- | --- |
| OQ-1 | Slurm account：`sbr-roihu.sh` 用 `project_2019964`，数据根目录是 `/scratch/project_2020002`。本项目计费用哪个 account？ | site.yaml | 已解决（2026-10-31）：`project_2020002` |
| OQ-2 | S0（下载与审计）不需要 GPU。Roihu 上的 CPU 分区名是什么？还是直接用 `gpumedium` 并只申请 1 卡？ | run.sh | 已解决（2026-10-31）：`small` 或 `medium` |
| OQ-3 | 原始数据放在 `/scratch/project_2020002/temporal-compression/data/raw`（代码从 site.yaml 读取，仓库内 `data/raw` 只是占位；执行规范 §3 写的是 `osf clone data/raw/zkwf2`）。是否接受？（scratch 有自动清理策略时需要备份方案） | site.yaml | 已解决（2026-10-31）：接受 |
| OQ-4 | WandB entity 填“同仓库名”。entity 一般是用户名或团队名，确认是 `temporal-compression` 还是你的 WandB 用户名？ | site.yaml | 已解决（2026-10-31）：`rongzhen-team` |
| OQ-5 | 结果回传走 `results` 分支，需要集群上能 `git push`（SSH key 或 token）。集群上的仓库克隆是否已有推送权限？ | run.sh | 已解决（2026-10-31）：能推送 |
| OQ-6 | 各 OSF 项目（zkwf2、2xt93、6aecj、uny8r）的文件清单尚未核实；视频是否在 OSF 上，S0 才能确认。 | 执行规范 §3 | S0 解决 |
| OQ-7 | Memory & Cognition 2025（边界密度 ± 双任务）、Fountas 2022 / Roseboom 2019、Memento10k 的获取方式待确认。 | 执行规范 §3 | 待确认 |
