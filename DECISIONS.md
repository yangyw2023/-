# DECISIONS

> 日志类产物：**只追加，永不修改。** 写错了追加更正条目，不回去改历史。
> 条目格式与决策分级 L1/L2/L3 见实施方案 v0.7 §20.2 / §20.5。

## 2026-09-07 · 迁移说明：历史日志未随本仓库迁移

### 起始声明
- 事实：v0.7 §20.5 记载"日志已 185 行"，而本仓库的 `DECISIONS.md` 起始为空。
- 依据（本会话实测，非声明）：
  - `git log --all --oneline` → 全历史仅 4 个 commit：`054e5c4` / `316e9f7` / `39404ba` / `d3a023b`
  - `git log --all --diff-filter=A --name-only` → 全历史新增过的文件只有
    `scripts/resolve_gold_chunks.py`（39404ba）与 `kNN.py`（d3a023b），无 `DECISIONS.md`
  - `git rev-list --all --objects | grep -i decision` → 无命中
  - `find / -xdev -iname 'DECISIONS*'` → 仅命中本仓库刚建的空文件
- **决策：本文件的记录起点为 2026-09-07，历史 185 行未随仓库迁移。**
  原因：该日志此前只存在于岸端本机（Mac Studio）工作目录，从未进入本仓库的 git 历史；
  本轮工作在远程容器中进行，取不到岸端本机文件系统。
- **决策：禁止凭 v0.7 §20.5 的摘要反推重建那 185 行。** 重建出来的条目不是历史记录，
  是伪造的历史记录，会让"只追加"这条纪律失去意义。
- 待办：Arya 在岸端本机找到原文件后，按"整份迁入、不做任何格式整理、不补标级别"处置，
  并在该次 commit message 中注明来源路径与迁移日期。
- 待办：v0.7 §20.5 "已有条目不必回头补标，从本版起的新条目一律带级别"这句话的前提
  （历史延续）在本仓库暂时不成立；历史迁入后需复核该句是否仍适用。

---

## 2026-09-07 补充 9 · 仓库脚手架建立与基线冲突处置

### [L3] 仓库结构按 v0.7 §19 建立，25 个文件，边界内无遗漏无越界
- 事实：`git status -uall` 25 个 untracked + `kNN.py` 已跟踪未修改；`find` 无多余文件
- 依据（真实数据验证，非声明）：
  - `git check-ignore` 实测：`eval/testset_v5_2.jsonl` NOT ignored（§19.2 唯一例外成立）；
    `raw/*.pdf`、`corpus/chunks.jsonl`、`index/bm25.pkl`、`models/*.safetensors`、
    `.venv/`、`__pycache__/` 均 IGNORED
  - 15 个包全部可导入；stub 抛 NotImplementedError 且消息可区分
  - `eval/results.csv` 1 行 19 列，列名唯一
- **决策：结构验收通过。**
- 待办：`DOCUMENT_MAP.md`、`ingest/build_corpus.py`、`eval/run_eval.py`、
  `eval/question_anchors.csv`、`experiments/models.yaml`、`components/` 下的具体实现
  均在 v0.7 §19 目录中但本轮边界外，未建

### [L3] 三项实现判断保留
- **决策 1：`.gitignore` 顶部保留两行判断标准注释。** 理由：§6.2 纪律二
  "流程要写死在文档里，不能靠自觉"。裸 ignore 文件挡不住有人以后加 `eval/*`，
  那会直接违反 §19.2 的唯一例外
- **决策 2：`core/contracts.py` 保持为"只有注释的占位"，不做成空文件。** 理由：
  贴入实现之前任何取名字都当场 `ImportError`，不会静默拿到 `None`。同时命中
  §22 必查五条第 1 条（静默吞异常）与第 4 条（魔法数字硬编码）
  - 依据：`from core.contracts import MAX_CONTEXT_TOKENS` →
    `ImportError: cannot import name 'MAX_CONTEXT_TOKENS'`
- **决策 3：各 `__init__.py` 保留一行 docstring；`components/__init__.py` 写明
  "只能 import core.contracts，各子包互不 import"。** 理由：§19.1 说
  "Code review 第一个查这条"，铁律应放在 reviewer 必然打开的位置

### [L3] 基线冲突处置：执行 A（从 origin/master 重开 ship-rag）
- 事实：PR #1（`ship-rag`→`master`，431 行，加 `scripts/resolve_gold_chunks.py`）
  已于 2026-09-07 01:58:58Z 合并；本地 `ship-rag` 落后 `origin/ship-rag` 1 个 commit
- 事实：`master` 的 `054e5c4 Delete kNN.py` 使 A 方案会从工作区移除 `kNN.py`，
  与"kNN.py 保持不动"的边界冲突
- 依据：`39404ba` 是 `054e5c4` 的祖先 → 后续 push 为 fast-forward，不需要 `--force`
- **决策：执行 A。** 理由：designated branch 的 PR 已合并，不在已合并历史上叠新
  commit；`kNN.py` 与本项目无关（删除 commit 是 Arya 自己的）
- **决策：`kNN.py` 不取回。** blob `081c007`，必要时
  `git show origin/ship-rag:kNN.py > kNN.py`
- 待办：`git checkout -B` 会把 upstream 指向 `origin/master`，已改回 `origin/ship-rag`；
  后续任何 `-B` 操作都要复查 upstream

### [L1] 记录轴不得断档：DECISIONS.md 历史必须随仓库迁移
- falsified_if: 无（方法论前提，同 Evidence First）
- 事实：新建仓库的 `DECISIONS.md` 为空，而 v0.7 §20.5 记载"日志已 185 行"
- 推论：§20.5"已有条目不必回头补标，从本版起的新条目一律带级别"这句话的前提
  是历史延续。空文件让它失去意义
- 推论：一旦提交空文件并开始追加，再迁历史只有重写（违反 §20.2 铁律 1）或留
  指针（记录轴仍断）两条路。**提交前是唯一便宜的时刻**
- 事实：风险登记 #10「决定未入库」已标"已发生两次"；此为第三次且丢失范围最大
- **决策：第一个 commit 之前必须处置。** 找得到 → 原样迁入，不做格式整理；
  找不到 → 顶部追加说明条目，注明起始日期与原因。**禁止凭 v0.7 反推重建历史条目**

### [L2] M2 预注册模板标注待修正项，sha256 栏留空
- owner_experiment: M2（判定规则修正完成后解除标注）
- 事实：Claude Code 核对"模板数字 vs v0.7"三项一致（31 道可答题 / 排除 TR02 /
  6-31=19.4pp）。核对方法正确，但验的是内部一致性
- 推论：v0.7 的净差判据本身有技术错误（见 补充 2），模板忠实复现了一个错误规范。
  预注册"提交后不改"，模板缺陷会原样变成实例缺陷
- **决策：模板 H1/H2/H3 段加 ⚠️ 待修正标注，指向 补充 2；判定阈值取值不动
  （§22 四不交）**
- **决策：`评测集版本 + sha256` 栏留空。** 依据：当前 sha256 =
  `d9a61862b9942a0c041cef269f09c3897d7356b8d939c90e2e957945759c127d`，但
  `gold_chunk_ids` 回填会改文件内容；sha 必须是冻结后的值（见 补充 8 冻结顺序）
- **决策：模板新增「判分协议」占位节，五项待填**（见 补充 3）

### [L3] README 暂不写 resolver 输出路径约定
- 事实：`scripts/resolve_gold_chunks.py`（PR #1）的 `--out-testset` 将
  `gold_chunk_ids` 回写进 testset 本身，落在 `eval/testset_*.jsonl` 会命中
  `.gitignore` 唯一例外并进 Git
- 推论：该形状与 补充 5「`gold_chunk_ids` 移出评测集、改为派生产物」的待拍板
  决策直接冲突。PR #1 合并早于该建议
- **决策：契约变更仪式走完前，不在 README 写入该约定。** 仪式结论决定 resolver
  是继续回写还是改为输出独立派生文件
- 待办：仪式后同步修改 `resolve_gold_chunks.py` 的参数语义或输出路径

### [L3] eval/testset_v5_2.jsonl 入库
- 事实：该文件在本轮结束时仍只存在于上传目录，未进仓库
- 依据：§19.2「唯一例外：`eval/testset.jsonl`，它是人的判断，不可再生，必须版本控制」；
  §18.5 备份表列为"每次修改进 Git"
- 推论：经 5 轮人工核对、单位成本最高的产物，目前存在于一个未版本化的单点上
- **决策：随第一个 commit 入库。**

## 2026-09-07 补充 3 · <一句话标题>

### [L?] <决策标题>
- falsified_if / owner_experiment:
- 事实:
- 依据:
- **决策:**
- 待办:


## 2026-09-07 补充 4 · S1 仓库初始化验收完成

### [L3] S1 仓库初始化
- 事实：
  - 当前工作分支 `ship-rag` 已与 `origin/ship-rag` 对齐，并在完成本轮记录后正常提交、推送。
  - `eval/testset_v5_2.jsonl` 已纳入 Git，且实测不受 `.gitignore` 影响。
  - `corpus/*` 与 `raw/*` 已实测被 `.gitignore` 正确忽略。
  - KAIVA 原始语料共 9 份 PDF / 49 MB。
  - `raw/` 已备份至 `/Users/developer/Documents/ship-rag-raw-backup-2026-09-07`，复核为 9 份 PDF / 49 MB。
  - `shiprag` 已在 login shell 实测：进入仓库、激活 `.venv`、设置 `PYTHONPATH`。
  - Python 3.12.14；MLX 实测 `Device(gpu, 0)`。
  - 岸端环境 baseline 已写入 `ENVIRONMENT.md`。
- 依据：
  - `git check-ignore -v`
  - `git ls-files eval/`
  - `ls "raw/KAIVA - Manuals/"*.pdf | wc -l`
  - `du -sh`
  - `zsh -lic 'shiprag; ...'`
  - `python -c "import mlx.core as mx; print(mx.default_device())"`
- **决策：S1 仓库初始化验收通过。现仓库不再重复执行 `git init` / `git branch -M`；后续开工先以 `git status`、`git log` 和远端实际历史确认 checkpoint。**
- 记录更正：上一条 `2026-09-07 补充 3 · <一句话标题>` 是 `dlog` 工具在编辑器调用失败前已追加的未填写模板，不代表任何项目决策；按 DECISIONS 只追加原则保留原文，不回删。
- 待办：进入下一实际 checkpoint 前再次核对 Git 状态。
## 2026-09-07 补充 N · S2 Claude Code 工作规范就位

### [L3] Claude Code 项目常驻指令
- 事实：
  - 仓库根目录已增加 `CLAUDE.md`。
  - 文件固化九条全链路语义约定与依赖树约束。
  - 明确任何 component 只能依赖 `core.contracts`，组件之间互不 import。
  - `CLAUDE.md` 已单独提交，commit `9c036b2`。
- 依据：
  - `CLAUDE.md`
  - Git commit `9c036b2`
- **决策：S2 验收通过。后续 Claude Code 实现组件时，以 `core/contracts.py` 为契约权威，并受 `CLAUDE.md` 常驻规则约束。**
- 待办：组件实现仍须按项目 code review 纪律逐项验收。

## 2026-09-07 补充 N · S3 契约冻结

### [L1] 引用与评测派生产物契约冻结
- falsified_if: 发现当前三元组不能唯一定位来源，或发现更简单且同样唯一、可审计的定位形式。
- 事实：
  - 引用定位采用 `(doc_id, section, pdf_page)`；`printed_page` 仅展示。
  - `gold_chunk_ids` 属于 citation 在具体 corpus/chunking 配置上的派生映射，不再属于人工评测集。
  - v5.3 中拒答题 citations 全为空；TR01 的 QMM 引文仅保留在 `known_distractor.source`。
  - v5.3 机械校验：39 题 / 无 `gold_chunk_ids` / 拒答题无 citation / citation 总数 38。
- **决策：上述语义进入 contracts v0.1.0。**

### [L2] M1c 上下文与检索实验契约
- owner_experiment: M1c
- **决策：** 按 S3 实际拍板后的 contracts 当前值执行；参数由 M1c 数据重新校准，不把当前值视为最终产品参数。

### [L3] 评测集升级至 v5.3
- 事实：v5.2 实际文件中 38/39 记录仍含空 `gold_chunk_ids`，ML03 已无该字段。
- **决策：** v5.3 统一移除该字段；TR01 citation 清空。
- 验收：39 / [] / [] / 38。
- sha256: `05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b`

## 2026-09-07 · S4 模型下载与资产台账建立

### [L3] S4 模型下载
- 事实：
  - 船端候选 `qwen3:4b`、`gemma3:4b`、`phi4-mini:latest`、`llama3.2:3b` 下载成功。
  - 历史候选 `qwen3.5:4b` 已存在本机，本轮纳入台账但不继承旧 GATE 状态。
  - `granite4:tiny` 下载失败：Ollama 返回 `model manifest file does not exist`，记为 SKIP。
  - `smollm3` 下载失败：Ollama 返回 `model manifest file does not exist`，记为 SKIP。
  - 两个失败 tag 均未自行替换。
  - Teacher `qwen3:32b` 下载成功，blob 约 19G。
  - Embedder `bge-m3:latest` 下载成功，blob 约 1.1G。
  - 本机另有 `qwen2.5:14b`、`deepseek-r1:32b`、`llama3:latest`，只作为已安装资产记录，不自动进入当前船端候选池。
- 依据：
  - `ollama pull <tag>` 实测输出。
  - `ollama list`。
  - `ollama show <tag> --modelfile`。
  - 本机 Ollama blob 路径与 digest。
  - `experiments/models.yaml`。
- **决策：`experiments/models.yaml` 同时承担本机模型资产台账，但用 `role` 明确区分 `candidate` / `teacher` / `embedder` / `other`；只有 candidate 使用船端 GATE-1～4 状态。**
- **决策：S4 不根据模型名称、历史结果或方案表提前填写 GATE 状态。GATE-2/3/4 必须由对应步骤重新实测。**
- 待办：
  - S7 正式执行候选生成模型 GATE-2。
  - GATE-3 执行时重新核官方许可证。
  - Embedder 的最终船端 runtime/兼容性在后续对应实验单独验证，不把 Ollama 可用等同于船端可用。

# 2026-09-07 补充 N · teacher 的输出用途许可

### [L1] 许可约束按“产出是否上船”传递，不按“自身是否部署”

* falsified_if: 出现证据表明合成训练数据不构成许可意义上的“模型输出使用”，或 LoRA adapter 不被认定为受 teacher 输出条款约束的派生物
* 事实: §12.4 原标题「不上船，不受 5B 限制」顺带免除了 GATE-3，teacher 表全是裸的 🟢/🟡 且无 `gate3_license` 列
* 事实: teacher 的产出 → 合成训练数据 → LoRA adapter → **上船**。链条中间没有任何一处切断许可传递
* 事实: 多个开放权重许可专门规定“用本模型输出训练/改进其他模型”的场景。Llama Community License 已知包含派生模型命名要求与 “Built with Llama” 标注义务
* 推论（具体后果）: 若用 Llama 3.3 70B 当 teacher，学生是 Apache 2.0 的 Qwen，但上船的 adapter 可能需以 “Llama” 开头命名 —— **一个需要向法务解释的状态**
* **决策: 判据改为“它的产出会不会上船”，不是“它上不上船”。** 新增 GATE-T1（输出用途许可，硬门）与 GATE-T2（本机可行性）
* **决策: “不适用”必须显式写 `N/A(理由)`，不能留空。** 留空像“还没查”，N/A 是一个已做出的判断
* 待办: LLM judge 在 M3/M5 引入时重新过这个判据 —— 产出是分数则风险低，**但若用于拒绝采样筛训练数据，产出就间接上船了**

### [L2] M2 首轮用单 teacher `qwen3:32b`

* owner_experiment: M3（届时若第二 teacher 过了 T1/T2，可启用双 teacher 交叉验证）
* 事实: `qwen3:32b` 已下载、已实测 26.09 tok/s、Apache 2.0（无输出条款）
* 依据: **干净方案零成本。** 不是权衡取舍，是免费规避一个未量化的风险
* **决策: M2 首轮单 teacher。** 代价是失去交叉验证过滤（§12.4 理由①），那是质量增益不是正确性前提，可接受
* **决策: Llama 3.3 70B 与 GLM-4.5-Air 降级为备选，M2 首轮不用，须先核输出条款**
* **决策: `gpt-oss:120b` 的 `license_claim` 记 TODO，不标 🟢。** 依据: 这正是 §12.3 刚修掉的“裸绿勾”错误，不能在 teacher 表里重犯。另需实测本机吞吐 —— 63/96 GB 是边界情况，装得下 ≠ 跑得完
* 待办: 合成数据文件记录 teacher 的 model_id / digest / license_claim / 生成日期。没有它，某个 teacher 出问题时“哪些数据受影响”只能答“全部”

## 2026-09-08 · contracts v0.2.0 冻结

### [L3] contracts v0.2.0 冻结
- 事实: v0.2.0 契约会已完成；prompt 总预算与 context packing 预算已分离，`MAX_CONTEXT_TOKENS` 更名为 `MAX_PROMPT_TOKENS`，`EvalItemResult` / `results.csv` 同步使用 `max_prompt_tokens`。
- 事实: 当前基线为 `MAX_PROMPT_TOKENS=1050`、`TTFT_BUDGET_S=10.0`、`PROMPT_OVERHEAD_RESERVE_TOKENS=200`（待 S4a.9 用主模型 tokenizer 实测替换）、`CONTEXT_PACK_BUDGET_TOKENS=765`。
- 依据: `core/contracts.py` v0.2.0；契约 smoke test；`eval/results.csv` schema exact-match 检查。
- **决策: contracts v0.2.0 正式冻结。后续任何契约修改继续走独立 `contract:` commit；S4a.9 对 prompt overhead 的实测替换属于已预注册 owner 的后续 L2 契约更新。**
- 待办: S4a 选定主模型后执行 S4a.9；必须在 S8 前完成。