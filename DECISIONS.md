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

## 2026-09-08 · S4a GATE-1 / GATE-2 首轮结果

### [L3] GATE-2 首轮实测结果
- Runtime 作用域：`llama.cpp 0.4.0`（build 10809, commit 5266f24da）/ 实际加载 ggml 0.23.0
  （本机 Cellar 内另有 0.20.0）/ Ollama 0.33.3 / macOS 15.6 (24G84) / arm64
- 测试参数统一 `-ngl 0 -t 8`。启动日志显示 Metal backend 被初始化，
  benchmark backend banner 为 `BLAS,MTL`。
  **因此本轮记录不宣称这批数字"已验证纯 CPU"**；设备作用域标为
  `cpu_only_verified: false`，待 `--device none` control run 后定性
- GATE-1 / GATE-2：
  | tag | params | GATE-1 | artifact sha(前8) | exit | GATE-2 |
  |---|---|---|---|---|---|
  | llama3.2:3b | 3.21B | PASS | dde5aa3f | 0 | PASS  pp 117.05/107.17/101.87, tg32 57.12 |
  | phi4-mini:latest | 3.84B | PASS | 3c168af1 | 0 | PASS  pp 107.47/98.15/92.91, tg32 49.65 |
  | qwen3:4b | 4.02B | PASS | 3e4cb141 | 0 | PASS  pp 87.95/78.81/75.40, tg32 44.58 |
  | gemma3:4b | — | ⏳ | aeda25e6 | 1 | **根因未取得，本轮不判 FAIL / INCONCLUSIVE** |
  | qwen3.5:4b | 4.7B | PASS | 81fb60c7 | 1 | **FAIL**（限定本次 artifact + runtime） |
- 依据（qwen3.5 根因，完整错误）：
  `key qwen35.rope.dimension_sections has wrong array length; expected 4, got 3`
  与 2026-08-17 补充 5 的记录一致，但当时环境为 ggml 0.20.0，**本轮实际为 0.23.0**
- 依据（健全性检查通过）：llama3.2:3b 今日 pp512/pp1024 = 117.05/107.17，
  M0（2026-08-17）为 117.5/107.4 —— 环境与基线可复现，新旧数据可比
- **决策：GATE-2 的 PASS / FAIL 只绑定本次 artifact + runtime，
  不外推为该模型家族永久兼容或永久不兼容**
- **决策：qwen3.5:4b 本次为正式候选的 GATE-2 FAIL，不是信息性复测** ——
  实测总参数 4.7B 已通过 GATE-1，手册原本"若 >5B 则降级为信息性记录"的预判被实测推翻
- 待办：gemma3:4b 补完整诊断；补 `--device none` control run；
  主模型选定后同步 `models.yaml`

### [L3] 更正：设备作用域的推断此前缺证据
- 事实：2026-08-17 补充 4 记载"backend 显示 BLAS,MTL —— Metal 未能完全禁用，
  此为乐观上界，非纯 CPU"
- 推论：**该结论缺少证据。** 日志证明的是 Metal backend 库被加载、Metal 设备被初始化、
  benchmark banner 列出了已注册后端 —— **这三件事都不等于矩阵运算实际 offload 到 GPU**。
  llama.cpp 启动时会加载所有可用 backend 库，不论是否使用
- 推论：§10.2 的上下文预算推导建立在那批被标为"乐观上界"的数字上，
  因此该定性成立与否直接影响预算的解释
- **决策：不回改补充 4（只追加原则），本条为更正。**
  自本条起，设备作用域一律记 `cpu_only_verified: true/false`，
  未做 control run 时记 false，不使用"乐观上界"这类未经验证的定性
- 待办：`--device none` control run（`-p 512,1024,1200`，与主实验逐点对比）。
  两种结果都有信息量 —— 数字基本不变说明现有数据本就是 CPU 口径；
  明显下降说明补充 4 的定性成立，且此时才有证据

### [L2] 主模型的选择会改变 prompt / context 预算
- owner_experiment: S4a.9
- 事实：契约 `MAX_PROMPT_TOKENS = 1050` 的依据来自历史 llama3.2:3b 8 线程 benchmark，
  **不是与模型无关的物理常数**
- 事实：本轮实测的 prefill 差异足以改变 TTFT=10s 下可容纳的 prompt 长度，
  进而改变 context packing budget 与可装 chunk 数
- 推论：在多个合法候选之间，prefill 性能可能改变 B/D 臂可装入的 chunk 数，
  因此**不能永远只作为无结构影响的末位 tie-breaker**
- **决策：S4a.9 扩为两项校准** ——
  9a 用最终主模型的 tokenizer 实测 `PROMPT_OVERHEAD_RESERVE_TOKENS`；
  9b 用最终主模型的 prefill/TTFT 实测重新校准 `MAX_PROMPT_TOKENS`。
  两者共同决定 S8 之前的 context packing budget
- **决策：由离散 pp512/1024/1200 反推得到的 prompt 上限（~1061 / ~991 / ~824）
  只作候选筛选估算，不直接写入冻结契约。**
  S4a.9b 须对最终主模型在目标长度附近做直接实测

### [L3] 语言 smoke test 的定位
- 事实：S4a 的关闭判据（GATE-1 + GATE-2 + license pre-check）在本轮开跑前已定
- 推论：看到结果后把 GATE-4 提为 S4a 的必经门，属于**改变已定的关闭判据**；
  且门是淘汰筛、tie-break 是另一回事，把门提前来服务 tie-break 反而混淆了两者
- **决策：语言测试定位为「已合格候选之间的 tie-break 证据 / 排除性 smoke test」，
  不是新增的 S4a hard gate。正式 GATE-4 仍按实施方案原定位置执行**
- **决策：判据为「实质性回答是否使用了提问所用的语言（而非回退成英文）」YES/NO，
  规则在判读前先定：混合输出只看实质性回答的语言。本轮不评事实正确性**
- 待检验的假设（**不是事实**）：「模型卡的语言列表通常偏保守」——
  本项目无证据支持，由本次 smoke test 检验
- 待办：判读时注意信息量不对称 —— **失败是较强的负面信号**
  B/D 臂还会加入英文 context，因此裸模型已经回退英文构成较强负面信号；其在带英文 context 条件下是否进一步恶化，留待 M2 实测。
  **通过是较弱的正面信号**（裸问能用该语言答，不保证塞进英文 context 后仍如此）

## 2026-09-08 · S4a 收口：补充实验、主模型选定与关闭

### [L3] gemma3:4b 的 GATE-1 参数核查
- 事实：`ollama show gemma3:4b` → parameters **4.3B**
  （architecture `gemma3`，quantization Q4_K_M，context length 131072，
  embedding length 2560；Capabilities 含 completion 与 **vision**）
- 依据：`experiments/gate2_raw/gemma3__gate1_params.log`
- **决策：`gate1_params_le_5b` = PASS（4.3B ≤ 5B）**
- **决策：不得根据 tag 里的 "4b" 推断参数量。** §12.1 已写死"tag 里的数字不是参数量证据"；
  本次是取到实测值后才判定的
- 事实：该 artifact 为**多模态打包**（Capabilities 含 vision）。
  实施方案 §18.1 明确不做图片
- **决策：仅记录该事实，不对它与 GATE-2 加载失败之间是否存在关系作任何判断。**
  能做该区分的实验是 S4b 的独立来源复测
- 事实：`ollama show` 显示该 artifact 的 Capabilities 含 vision（多模态打包）
- **决策：当前【无证据】表明 vision capability 与本次加载失败有关** ——
  失败发生在 hyperparameter 加载阶段，且本轮未向 llama-cli 提供任何 mmproj
- 待办（S4b）：复测优先使用来源与 provenance 可验证的**文本生成** GGUF artifact；
  若所选分发物包含独立 multimodal projector，本项目不加载 mmproj，
  **理由是 §18.1 不评估图片能力（范围问题，不是兼容性嫌疑）**

### [L3] gemma3:4b 的 GATE-2 判定
- 事实：artifact sha256 `aeda25e6…`，GGUF 魔数正常（47475546），`llama-bench` exit code 1
- 事实（完整诊断，`experiments/gate2_raw/gemma3__diagnostic.log`）：
  `key not found in model: gemma3.attention.layer_norm_rms_epsilon`
  → 不是 OOM、不是文件损坏、不是魔数错误，是一个**缺失的元数据字段**
- **决策：GATE-2 = FAIL，作用域限定为「当前 Ollama artifact + rt-2026-09-08」**
- **决策：不外推为 Gemma 3 架构永久不兼容。** 失败表现与 artifact 元数据 / 转换链问题一致，
  但**当前证据不足以将根因归因到 Ollama 转换环节本身**
- 待办（S4b）：用独立来源 GGUF（Google 官方或 ggml-org）复测 ——
  **该实验区分「artifact provenance 问题」与「runtime/schema 兼容问题」**，
  是目前唯一能做出这个区分的实验。不阻塞 S4a

### [L1] GATE-2 的 failure 与 artifact provenance 解耦
- falsified_if: 取得当前 Ollama blob 的可验证 provenance
  （能证明其 GGUF 的生成链、转换工具与来源 artifact）
- 事实：本轮 `gemma3:4b` 与 `qwen3.5:4b` 的当前本地 artifact，
  在固定的 rt-2026-09-08 下**稳定复现**加载失败：
  - gemma3:4b：`gemma3.attention.layer_norm_rms_epsilon` 缺失
  - qwen3.5:4b：`qwen35.rope.dimension_sections` 数组长度不匹配
- 事实：文件位于 Ollama blob store，**只能证明本轮通过 Ollama 取得该 artifact**；
  **不能仅凭这一点确定 GGUF 是由 Ollama 转换、由模型所有者发布、
  还是从其他 GGUF 来源导入 Ollama** —— Ollama 支持直接导入外部 GGUF
- **更正：此前"Ollama 执行自己的 GGUF 转换，不是模型所有者的官方发布"
  这一论断【证据不足】。** 它是「第 14 类错误」（观察 + 一个说得通的机制 = 结论）
  的又一次实例，且发生在提出该规则的同一份文档中。
  按只追加原则不回改，本条为更正
- **决策：`acquisition.channel = ollama`，`artifact_provenance = unverified`**
- **决策：GATE-2 的 PASS / FAIL 与 provenance 判断解耦。**
  当前 artifact 在当前 runtime 下可复现加载失败 → GATE-2 判 FAIL；
  但**不得由此推断具体转换环节，也不得推断模型架构永久不兼容**
- **决策：需要区分「artifact provenance 问题」与「runtime/schema 兼容问题」时，
  使用 provenance 已知的独立 artifact 做二次取源复测**
- **决策：`source_trust` 分级（official / upstream / community）
  仅在 `artifact_provenance: verified` 时才可赋值。**
  provenance 未核实时不赋分级 —— 分级本身就是一个 provenance 判断
- 待办（S4b，可验证 provenance 的便宜实验）：
  将 Ollama blob 的 sha256 与模型所有者官方发布的 GGUF digest 比对。
  相同 → provenance 验证为 official；不同 → 排除"官方原件"但 provenance 仍未知。
  **这是能区分两个解释的实验**，几分钟可做
- 待办（S4b 复测记录要求）：对 gemma3 与 qwen3.5 的二次 artifact，
  记录来源 URL、发布者、digest、量化等级与获取日期
- 待办（方案同步）：**实施方案 §12.5 目前定义了 `source_trust` 三档
  并把 FAIL 强度绑在上面，与本决策不一致。**
  须同步改为「以 provenance 已验证为前提 + FAIL 与 provenance 解耦」。
  不阻塞 S4a 关闭，但不改就是"改了台账没改规范"

### [L3] 设备作用域：正对照完成，cpu_only_verified = true
- 事实（同 artifact llama3.2:3b `dde5aa3f…`、同 runtime、8 线程，pp512/1024/1200）：
  - `-ngl 0`：117.05 / 107.17 / 101.87
  - `--device none`：116.65 / 106.87 / 101.59
  - `-ngl 99`（正对照）：2554.33 / 2499.06 / 2440.03
  - tg32：57.12 ± 2.99 → 55.70 ± 0.30（差 −2.49%，落在原测 σ 内）
- 依据：`-ngl 99` 的 pp1024 为 `-ngl 0` 的 **23.3 倍** →
  该旋钮在本 runtime 下**确实能区分** GPU 路径，
  因此 `-ngl 0` 与 `--device none` 的一致性**构成**"未 offload"的证据
- 事实：三种运行方式启动时**均**加载并初始化 Metal backend，banner 均为 `BLAS,MTL`
  → **backend 被加载/初始化本身不能证明发生了 GPU offload**
- **决策：在「当前 artifact + rt-2026-09-08 + 本 workload」作用域内，
  `cpu_only_verified = true`**
- **更正：2026-08-17 补充 4 把 `BLAS,MTL` 直接解释为"Metal 未能完全禁用、乐观上界、
  非纯 CPU"，该推断缺少证据。按只追加原则不回改旧记录，以本条作为更正**
- **⚠️ 边界（必读）：本条证明的是「无 GPU offload」，不是「这些数字适用于船端」。**
  `-ngl 0` 路径仍包含 **BLAS（Apple Accelerate）**；船端 x86 无 Accelerate、
  也无 Apple 统一内存带宽。M0（2026-08-17）估算 x86 CPU 为 35–85 t/s，对比本机 117 t/s。
  **船端外推仍然乐观，原因是 Accelerate 与内存带宽，不是 Metal**
- 边界：不外推为所有模型、所有 workload、所有 llama.cpp 版本的永久行为

### [L3] thinking 对照：先前的假设被证伪
- 事实：`qwen3:4b` 在 `think=True` 时 API 返回独立 `thinking` 字段；
  `think=False` 时该字段消失 → **Ollama 0.33.3 对该模型的 thinking 开关实际生效**
- **更正：此前"`\"think\": false` 可能未生效、是 M2 阻断项"的假设【被证伪】。
  不构成 M2 阻断项**
- 事实：`qwen3:4b` 在 `think=False` 后，普通 `response` 仍产出长篇英文
  reasoning-style prose；400-token 对照在所观察部分仍未形成 Hindi 实质回答
- 推论：**「独立 thinking channel」与「response 中的推理式文本」是两件事。**
  关掉前者不等于消除后者
- 事实：`phi4-mini:latest` 对 `think=True` 返回 **HTTP 400: model does not support thinking**；
  `think=False` 正常生成、`thinking` 字段不存在；最小 smoke 返回 `OK`
- **决策：项目约束 `THINKING_ENABLED=False` 在选定的 phi4-mini 路径上可落实，
  不构成 M2 blocker**
- **边界：这说明的是【不存在独立 thinking 模式】，因此不存在该模式被误开启、
  或其独立 channel 泄露的风险；【不是】"普通 response 不会产生推理式文本"**
- 辅助的行为证据：phi4-mini 在语言 smoke 的 5 条输出中均直奔答案、无推理前缀（n=5）。
  比结构论证弱，但是实测。结构与行为两者同向，**均不构成保证**

### [L3] 语言 smoke test 结果
- 事实：判据在查看输出前已冻结 ——
  「实质性回答是否使用提问所用的语言」YES/NO；不评事实正确性；
  混合输出只看实质性回答主体
- 实测（2026-09-08，`experiments/gate2_raw/_language_smoke.log`）：
  | 模型 | ML01(zh) | ML02(tl) | ML03(hi) | EXTRA-tl | EXTRA-hi | 计 |
  |---|---|---|---|---|---|---|
  | phi4-mini:latest | YES | YES | YES | YES | YES | 5/5 |
  | qwen3:4b | YES | NO | NO | NO | NO | 1/5 |
  | llama3.2:3b | YES | YES | YES | YES | YES | 5/5 |
- **决策：`qwen3:4b` 的 1/5 记为 `NOT_CLEAN`，不作为干净的多语种能力测量引用。**
  理由**不是**"开关被忽略"（已证伪），而是原 protocol 仅 120 output token
  且未在全部五条上复跑。**结论方向未变**
- **决策：phi4-mini 与 llama3.2:3b 的 5/5 成立**（输出无推理前缀，不受该混杂影响）
- 事实：Microsoft 官方模型卡声明 phi4-mini 支持语言 23 种，含 zh、
  **不含 tl、不含 hi**。本轮 5/5 是本项目当前 artifact + protocol 下的实测行为，
  **不得改写为"官方支持 tl / hi"**
- 事实：phi4-mini 的 5/5 输出**内容为流利的错误信息**
  （hi 那条讲耆那教圣日，tl 那条讲菲律宾海军军官轮换）。
  判据冻结时已声明只看语言不看正确性，故 5/5 成立
- **决策：该批输出留档作为 A 臂幻觉的多语种样本，供 M2 汇报使用**
- 待检验的假设**仍只是假设**：「模型卡的语言列表通常偏保守」—— n=1 不足以成立
- 待办：判读时注意信息量不对称 —— **失败是较强的负面信号**
  （B/D 臂的 prompt 还会加入英文 context，只会更把输出拉向英文）；
  **通过是较弱的正面信号**（裸问能用该语言答，不保证塞进英文 context 后仍如此）。
  后者留待 M2 实测

### [L1] 许可 pre-check 足以解锁 M2
- falsified_if: M3 横评显示 RAG vs 微调的相对优劣在不同基座家族之间实质反转，
  使单一基座上的 M2 架构结论不能外推
- 事实：S4a 的目标是为 M2 找到一个合法、可运行、足以承载 RAG × 微调架构对照的**实验载体**，
  **不是完成最终船端模型选型**
- 事实：`phi4-mini:latest` 对应 Microsoft 官方 `Phi-4-mini-instruct`；
  2026-09-08 查证官方仓库 LICENSE 为 **MIT**
  （https://huggingface.co/microsoft/Phi-4-mini-instruct/blob/main/LICENSE）；
  本机 `ollama show` 的 License 段同时显示 Microsoft 版权声明（输出截断，未含完整 MIT 文本）
  → **官方 LICENSE 为主证据，本机 artifact 为辅助 provenance**
- **决策：M2 依据模型所有者官方来源的 `license_claim` pre-check 解锁；
  该动作不冒充正式 GATE-3，`gate3_license` 继续记 TODO**
- **边界声明：M2 主模型的选定基于 `license_claim`，正式 GATE-3 未执行。
  即便该模型后来在 GATE-3 被否，M2 的架构对照结论仍然成立** ——
  M2 是 RAG × 微调的架构对照，不是最终选型实验；
  需要更换的是船端的那个模型，不是"RAG vs 微调"这个实验问题。
  **正式 GATE-3 必须在 M3 / M6 之前完成**

### [L2] M2 主模型选定：phi4-mini:latest
- owner_experiment: M3（横评会重新打开基座家族选择）
- 事实：总参数 3.84B，GATE-1 PASS
- 事实：artifact sha256 `3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db`；
  在 rt-2026-09-08 下 GATE-2 PASS
- 事实：`-ngl 0 -t 8` bench：pp512/1024/1200 = 107.47 / 98.15 / 92.91 t/s，tg32 = 49.65 t/s
- 事实：官方 LICENSE pre-check = MIT；正式 GATE-3 未执行
- **三条互相独立的选定理由，没有一条依赖被标为 NOT_CLEAN 的语言证据**：
  1. **上下文预算**：与另一 GREEN 候选 qwen3:4b 相比 prefill 更快
     （pp1200 92.91 vs 75.40）。基于离散 pp 点的筛选估算，
     TTFT=10s 下 phi4-mini 约可容纳 2 个中位 chunk 而 qwen3:4b 约 1 个。
     **该差异直接决定 B/D 臂能装几个 chunk** ——
     选 qwen3 会使 CD01（gold 3 chunk 跨 2 手册）结构性不可答、procedure 类基本废掉。
     ⚠️ 具体预算值不在此冻结，由 S4a.9 直接实测
  2. **MIT license claim**（官方 LICENSE + 本机 artifact 二次证据）
  3. **无独立 thinking 模式**（`think=True` 返回 HTTP 400），
     降低"该模式被误开启 / 其独立 channel 泄露"这一特定风险，
     与 §11.5 的安全方向一致。
     ⚠️ **不据此声称普通 response 不会产生 reasoning-style prose** ——
     同批 qwen3 实验已表明二者是两件事
- 辅助证据（不单独承重）：语言 smoke 5/5 vs qwen3 的 NOT_CLEAN
- **决策：M2 首轮主模型 = `phi4-mini:latest`。这不是"最快的赢"** ——
  llama3.2:3b 更快（pp1200 101.87）且语言同为 5/5，
  但其 license_claim 为 Llama Community（AMBER），**GATE-3 未过即不进 tie-break**。
  **门在前，性能在后**
- **决策：本轮结果不解释为 M3 的模型冠军**
- 待办：执行 S4a.9，用 phi4-mini 的实际 tokenizer 与 prefill/TTFT
  重新校准 prompt / context budget

### [L1] S4a.9 结果的处置方式（⚠️ 预先声明，必须先于实验入库）
- falsified_if: 无（这是对实验结果的预先承诺，不是关于系统的经验主张）
- 事实：chunk 预算 = (`MAX_PROMPT_TOKENS` − `PROMPT_OVERHEAD_RESERVE_TOKENS`)
  × `CONTEXT_PACK_MARGIN`；中位单 chunk ≈ 306 tok
- 事实（敏感性）：以 X≈990 估算，prompt 开销 O=250 时可装 2 个 chunk，
  O=300 时只装 1 个 —— **50 token 的差别就能把 k 从 2 打到 1**
- 推论：k=1 意味着 CD01 结构性不可答，procedure 类基本废掉
- **决策（先于实验）：若实测算出中位可装 1 个 chunk，我们接受它并记为代价。
  不通过放宽 `CONTEXT_PACK_MARGIN`、抬高 `MAX_PROMPT_TOKENS`、
  或压低 `PROMPT_OVERHEAD_RESERVE_TOKENS` 来凑到 2**
- **决策：该代价由 M1c 的 Recall@1 / Recall@2 量化，
  并写进 M2 预注册的「预期最可能结果」**
- 依据：**事先声明了是证据，事后调参是找补。** 与 §15「只找大效应、不扩题」同一取向

### [L2] CONTEXT_PACK_MARGIN 的安全不等式（S4a.9 执行时应用）
- owner_experiment: S4a.9d
- 事实：契约当前为 `CONTEXT_PACK_MARGIN = 0.90`，配 `CHARS_PER_TOKEN_EST` 的 ±15% 误差假设
- 推论：**0.90 × 1.15 = 1.035 > 1 —— 该余量在数学上就吸收不掉 15% 的低估**
- 依据：这正是此前算出「765 × 1.15 + 200 = 1080 > 1050，TTFT 10.13 s 超预算」的根因。
  **不是"余量已归零"，是余量从一开始就是负的**
- **决策：margin 必须满足 `(X − O) × m × err_factor + O ≤ X`，即 `m ≤ 1 / err_factor`。**
  在 `err_factor = 1.15` 下，`m ≤ 0.8696` → 取 **0.87**
- 待办：S5 建完语料后在**真实 chunk** 上实测 chars/token，
  届时 `err_factor` 可下调、margin 随之可放宽。
  **顺序是先量后放宽，不是先放宽后找理由**

### [L3] 方法论：把"一个说得通的机制"当成结论（新增第 14 类错误）
- 事实（本轮三次同形状实例，均由审核脑提出后被自身实验或旁证推翻/收窄）：
  ① 由 `BLAS,MTL` banner 断言"`-ngl 0` 未生效"
  ② 由 `think=True` 返回 HTTP 400 断言"不可能把推理泄进答案"
     —— **反证就在同一批 qwen3 实验里**
  ③ 由缺失元数据字段断言"极可能是 Ollama 转换环节未写入"
  ④ 由"artifact 位于 Ollama blob store"断言"Ollama 执行了 GGUF 转换"
     —— **发生在提出本规则的同一份文档中**，说明这条检查必须是可执行的动作，
     而不是一个提醒
- 推论：共同形状是 **一个观察 + 一个说得通的机制 = 被当成了结论**
- **决策：加入 §6.2 第 14 类错误。检查方式 ——
  每写一句因果性陈述，问一句「有哪个实验能区分这个解释和它的替代解释？」
  没有 → 降级为假设，并把那个能区分的实验记成待办**
- 依据（这条检查有效的证据）：三次里有两次事后补了那个能区分的实验
  （`-ngl 99` 正对照、thinking 开关对照），**结论都变了** —— 只是事前没做
- 依据（这条检查有效但需要被机械执行）：四次实例中有三次事后补了那个能区分的实验
  （`-ngl 99` 正对照、thinking 开关对照、provenance digest 比对已列为待办），
  **结论都变了或被收窄**。第四次实例发生在提出规则的同一份文档里 ——
  说明"记住这条"不够，必须写进审查清单成为一个动作
- **决策：同时作为「每完成一步回来的审查五问」的第 6 问**

### [L3] 观察留档：§12.3「预期的差异来源」首次命中
- 事实：实施方案 §12.3 给 llama 家族写的预测是
  「指令跟随保守 → **预期拒答率偏高**」
- 事实：语言 smoke 的 ML01（zh）上，`llama3.2:3b` 的回答是
  「我无法提供有关船长晋升的具体时间要求的信息。」——
  **三个受测模型里唯一选择拒答而非编造的**
- 推论：预测写在测试之前，结果对上
- **决策：记为「预期 vs 实测」机制的第一次命中，n=1，不作推广。
  M3 出数时按同一方式逐条对照**

### [L3] S4a 关闭
- 事实：已存在 `phi4-mini:latest` 同时满足 GATE-1（3.84B ≤ 5B）、
  rt-2026-09-08 下 GATE-2 PASS、模型所有者官方 MIT license pre-check
- 事实：artifact digest / runtime / 测试日期 / GATE 状态 / 主模型身份已写入
  `experiments/models.yaml`；原始 GATE-2、失败诊断、GATE-1 补测、语言 smoke、
  thinking 对照、CPU/GPU control、许可证据均保存在 `experiments/gate2_raw/`
- **决策：完成台账与原始证据的 commit/push 后，S4a.1–S4a.8 正式 CLOSED，S5 解锁**
- **边界：S4a.9 不属于 S4a.7 的 hard gate，但必须在 S8 之前完成；
  其契约修改使用独立的 `contract:` commit**
- 项目状态：
  ```
  S4a readiness gate ......... CLOSED
  M2 primary ................. phi4-mini:latest
  S5 ......................... UNLOCKED
  S4a.9 prompt-budget 校准 .... OPEN，S8 之前完成
  S4b candidate-space survey .. OPEN，不阻塞
  ```

  ## 2026-09-11 · 工具职责与 S4a.9 冻结边界

### [L3] LM Studio 纳入 S4b，职责限定为「候选发现 + GGUF 获取 + provenance 调查」
- 事实：当前 `gemma3:4b` 与 `qwen3.5:4b` 的 llama.cpp 加载失败只能绑定到
  已测试的具体 artifact + runtime；现有 Ollama blob 的取得渠道已知，
  但**不能仅凭其位于 Ollama blob store 推断 GGUF 的转换者或发布者**
- 事实：LM Studio 支持从 Hugging Face 搜索并下载 GGUF（`lms get <repo>`、
  `lms get <repo>@Q4_K_M`、`lms import`），本地按 `publisher/model/file.gguf`
  组织；其自身带独立的 llama.cpp / MLX runtime
- **决策：纳入 S4b，职责严格限定为「候选发现、GGUF 获取、artifact provenance 调查」**
- **决策：`source_repo_verified` 与 `artifact_provenance` 分开记录。**
  从某个 `publisher/repo` 下载**不自动**证明该 GGUF 的转换链已验证 ——
  LM Studio Hub 的 `model.yaml` 可以引用别的 base/source
  （官方示例：一个 `qwen/...` 的定义指向 `lmstudio-community/...-gguf`）。
  **命令里的命名空间 ≠ 文件的来源**
- **决策：provenance 的验证动作是 digest 比对**：
  `shasum -a 256 <本地.gguf>` 对照模型所有者 HF 仓库文件页显示的 SHA256
  （LFS 文件的 OID 即 sha256）。
  一致 → 该文件与该 publisher 发布的字节完全相同 → `artifact_provenance: verified`；
  不一致 → 是另一个 build，provenance 仍未知，但**排除了"官方原件"**。
  ⚠️ 精确地说，它验的是「这个文件就是仓库 X 发布的那一份」，
  不是「仓库 X 亲手转换的」
- **决策：只有 `artifact_provenance: verified` 之后，才允许赋
  `source_trust: official / upstream / community`**
- **决策：LM Studio 内运行成功【不得】作为 GATE-2 PASS。**
  它自带独立的 llama.cpp 构建，且 Apple Silicon 上可能走 MLX 路径 ——
  与 §6.2 错误 #4「Ollama 能跑 ≠ llama.cpp 能跑」同形。
  正式 GATE-2 仍用项目 pin 住的 runtime，并记 artifact sha256 与 runtime scope
- **决策：不采用其内置 RAG**（自己分块，不接收外部 chunk ID、不保留
  `(doc_id, section, pdf_page)` → 三元组产生不出来）；
  **不以它替换当前推理栈**（会使 `rt-2026-09-08` 下全部 GATE-2 结论作用域失效）
- **更正：审核脑此前在工具评估中写「`lmstudio-community/*` 加载失败只能记
  INCONCLUSIVE」，这引用的是已被推翻的旧 §12.5 规则。**
  按现行解耦规则：**加载失败就是该 artifact + runtime 的 FAIL；
  provenance 只限制这个 FAIL 能外推多远**
- 待办（S4b，非阻塞）：`lms get smollm3 --gguf` / `lms get granite --gguf`，
  补上两个 tag 缺失候选的 acquisition route
- 待办（S4b，非阻塞）：gemma3 / qwen3.5 的独立 GGUF 二次取源复测；
  优先选 provenance 可核实的模型所有者 artifact。
  **可先只比 digest**，就能回答「Ollama 那份是不是官方原件」

### [L3] Unsloth Studio 暂不进入 M2 训练关键路径
- 事实：M2 的训练与评测要求显式保留 `lora_adapter_sha256` / `teacher_digest` /
  `prompt_config_sha256` / `seed` / `code_commit` 等可复现性指纹
- 推论：在 MLX-LM 命令行训练路径已可用的前提下，引入 GUI 训练工具
  只有在提供额外、可验证的能力时才有收益；
  **否则会增加配置状态捕获与复现的成本** ——
  命令行训练脚本本身就是配置记录，进 Git、可 diff、可复现；
  无代码 GUI 把配置藏进自己的状态里
- 事实：Unsloth **核心**依赖 Triton，而 Mac 没有 Triton ——
  这正是方案 §15 选 MLX-LM 的由来。**Unsloth Studio 是另一个产品**，不要混为一谈
- 事实：官方文档自相矛盾（Requirements 页称 Mac 训练全支持；
  快速开始 / GitHub 把训练列为 NVIDIA/Intel、CPU 仅推理）。**须自行打开确认**
- 事实：社区项目 `mlx-tune`（原名 `unsloth-mlx`）**不是官方项目**
- **决策：当前不进入 M2 训练关键路径，不阻塞 S4a.9 / S5 / S6 / S8**
- **决策：S11 前重新评估其在【合成训练数据人工质检】上的窄职责，
  而不是默认把它当训练 runtime。** §14.5 要求合成数据含 ≥20%「应拒答」负样本，
  那批数据需要人工抽检 —— **那是数据质检的需求，不是训练的需求**
- 待办：届时判据为「是否显著改善合成数据的浏览、筛选、标注与审计，
  同时不破坏可复现性」

### [M] 未测量的变量不得用猜测上界伪装成已关闭的门
- why_not_falsifiable：这是证据解释与实验设计的纪律，
  不是关于某个模型或参数的经验主张，不可能被本项目的实验推翻
- 事实：S4a.9 中，真实 rendered chunk 的块间 separator token 成本
  **尚未在其真实左右文中测量**；孤立换行符的 token 增量
  **不能等价为**真实块间 separator 成本（tokenizer 会合并连续换行；
  真实 separator 两边有 citation header 与 chunk 文本，分词不同）
- 事实：审核脑曾为该未测量项猜一个上界（"约 1–3 tok，再留一倍"= 5），
  并把 `slack ≥ 5` 写成硬门。该门**不产生新信息**
  （它"失败"的原因已知）**也不导出新动作**（处置已写好）
- **决策：对尚未测量但会影响结论的变量，结论必须写成关于该变量的条件式，
  不为其猜一个上界再把该上界当硬门**
- 具体到当前预算：设 `X` 为 prompt 总预算、`O` 为已实测固定开销、
  `B` 为 context packing budget、`ERR` 为现行估算误差因子，则
  `slack = X − (B × ERR + O)`。
  **`k_est = 2` 成立仍要求真实块间 separator 成本 ≤ slack**；
  该成本由 S5 的真实 rendered chunk 实测。**在实测前不猜其上界**
- ⚠️ 读法是**单向**的：`sep > slack` → k=2 一定死（这个方向是硬的）；
  `sep ≤ slack` → k=2 还活着但**未确定**，`CHARS_PER_TOKEN_EST` 的校准仍可能翻掉它
- 待办：S5 后以真实 chunk 执行 9c-final 与 separator 测量，再冻结 S8 的主 k 值

### [L3] 方法论：第 14 类错误的第五次实例，及其共同发生位置
- 事实（第五次实例）：审核脑由「LM Studio 的本地路径含 publisher」
  推出「`artifact_provenance: verified`」。
  但路径里的 publisher **只证明获取命名空间**，不证明转换者、量化者或权重血缘 ——
  LM Studio Hub 的 `model.yaml` 可引用别的 base/source
- 事实（五次实例的清单）：
  ① `BLAS,MTL` banner → "`-ngl 0` 没生效"
  ② `think=True` 返回 HTTP 400 → "不可能把推理泄进答案"
  ③ 缺失元数据字段 → "极可能是 Ollama 转换环节未写入"
  ④ 孤立换行的 token 增量 SEP → "应并入 `CITATION_HEADER_EST_TOKENS`"
  ⑤ 本地路径含 publisher → "`artifact_provenance: verified`"
- **推论（这次的新发现）：五次的共同点不是"疏忽"，而是【位置】——
  全部发生在「把观察写成一个字段值或一条规则」的那一刻。**
  测量本身没错，分析也没错，错的永远是落笔那一下
- **决策：把检查放在落笔处，而不是"以后注意"** ——
  **每当要写 `field: value` 或"所以应该改 X"时，问一句：
  「我观察到的那个量，和我要填的这个字段，是同一个东西吗？」**
  五次实例里，五次的答案都是"不是"
- **决策：该问句加入 §6.2 第 14 类错误的改进措施栏，
  并作为「审查五问」的第 6 问**

### [L2] S4a.9 的预算冻结尚未完成
- owner_experiment: S4a.9（9a-bis）与 S5 后的 9c-final
- 事实：phi4-mini 的 fine sweep 已提供 `MAX_PROMPT_TOKENS` 的校准证据；
  系统提示词 + 问题的初测（9a）已完成，
  但 **B/D 实际 rendering framework 开销 F 尚需 9a-bis 单独计入** ——
  9a 量的是 A/C 形状（`SYSTEM + "\n\n" + question`），不含 context 块框架
- 事实：`CHARS_PER_TOKEN_EST` 直接进入 `Chunk.est_tokens()` →
  `pack_context()` → 最终可装 chunk 数，
  **因此不是仅影响解释强度的旁支参数，而是承重变量**
- 事实：审核脑此前把 9c 定位为「provisional、只影响解释强度」，**该定位低估了它**
- **决策：在 9a-bis 与 S5 后的 9c-final 完成前，
  不宣布最终 `CONTEXT_PACK_BUDGET_TOKENS`，不宣布 S8 的主 `k` 已冻结**
- **决策（重申预先声明）：若最终实测只支持 `k=1`，接受该结果，
  交给 M1c 的 Recall@1 / Recall@2 量化代价；
  不得通过事后放宽 margin、抬高 prompt budget 或压低实测 overhead 把结果凑成 `k=2`**
- **决策：S5 Parser 现在并行启动。** 它不依赖预算冻结，
  且其产出正是 9c-final 所需（真实 chunk 长度分布 / 真实 rendered chunk /
  真实 separator 上下文 / phi4-mini tokenizer 下的真实 chars/token）
- 待办：9a-bis → 9c-provisional，与 S5 并行；S5 后 9c-final → 9d →
  独立的 `contract:` commit → 解锁 S8
- 待办：`_s4a9b_ttft_fine.log` 需确认已进 Git（磁盘上存在 ≠ 已跟踪）。
  基准日志是**不可再生的测量记录**，按 §19.2 必须版本控制

### [L3] BACKLOG：实施方案 §12.5 需与 provenance 解耦规则同步
- 事实：§12.5 现行文本把 `source_trust` 三档与 GATE-2 的 FAIL 强度绑定
- 事实：2026-09-08 已决定把两者解耦 ——
  GATE-2 的 PASS/FAIL 永远只关于 artifact + runtime 的实测事实；
  provenance 是独立维度，只决定该失败能外推多远；
  且 provenance 未核实时不赋 `source_trust`
- 推论：**台账与规范已不一致**（改了实现没改规范）
- **决策：记入 BACKLOG，不阻塞 9a-bis / S5。**
  §12.5 改写为：
  ```
  GATE-2 FAIL        = 永远只关于 artifact + runtime 的实测事实
  artifact provenance = 独立维度
  provenance verified   → 才允许赋 source_trust
  provenance unverified → 不赋 source_trust
  要把 artifact 级失败提升为「model × runtime」的更强负面证据
                      → 换 provenance 已知的独立 artifact 复测
  ```

  ### [L3] S4a.9a-bis：B/D context framing 开销实测
- 事实（phi4-mini:latest tokenizer；问题固定为 FL06，9a 实测其为本评测集 token 最长问题）：
  - A/C 形状（SYSTEM + 问题）= 201 tok
  - B/D 形状（增加 Passages / Question 框架）= 206 tok
  - framing overhead F = 5 tok
  - SEP（无 chunk 上下文中增加一个换行的 token 增量）= 0 tok
- **决策：当前 provisional `PROMPT_OVERHEAD_RESERVE_TOKENS = 206`。**
  该值尚未冻结进 contracts；最终预算仍受真实 chunk tokenization 与真实块间 separator 约束。
- **决策：SEP=0 仅是诊断观察，不得解释为“真实块间 separator 成本为 0”。**
  两者测量对象不同；真实 separator 必须在 S5 的 rendered chunk 上测量。
- 派生核算（provisional，不写入 contracts）：
  - `B = int((950 - 206) × 0.86) = 639`
  - `worst = 639 × 1.15 + 206 = 940.85`
  - `slack = 950 - 940.85 = 9.15 tok`
  - 按当前 `306 tok/chunk` 估算，中位 `k_est = 2`
- **决策：`CONTEXT_PACK_MARGIN=0.86` 的候选依据改为显式数学约束。**
  在两位小数粒度下，为满足 `m <= 1/1.15 = 0.8696`，最大允许值为 `0.86`。
  `0.87` 在实测 `O=206` 输入下核算为 `950.05 > 950`，不满足预算自洽条件。
  此前在 `O=201` 下得到 `949.65 <= 950` 是整数截断造成的边界现象，不应据此采用 `0.87`。
- **决策：`k_est=2` 不冻结。**
  当前中位 chunk 条件要求真实 chars/token 约大于 3.82，而 `CHARS_PER_TOKEN_EST=4`
  尚未由真实 chunk 校准；真实 separator 成本亦未测。两项均由 S5 后的 9c-final 关闭。
- **决策：realized k 是逐题运行结果，不是全局常数。**
  `TOP_K_CONTEXT` 仍只是个数上限；实际进入上下文的数量由预算与 chunk 长度共同决定，
  并通过 `EvalItemResult.n_chunks_in_context` 落盘。
- 待办：S5 后对真实 chunk 与真实 rendered context 执行 9c-final，再执行 9d；
  在此之前不修改预算相关 contracts 常量，不宣布 S4a.9 CLOSED。

  ## 2026-09-17 · S4a.9 最终预算诊断：真实 chunk 暴露 chars/token 尾部风险

### [L2] S4a.9c-final：真实语料上的 token estimator 不能只用总体中位数验收

- owner_experiment: S4a.9c-final / S4a.9d

- 冻结输入：
  - corpus = `corpus/chunks.jsonl`
  - chunk count = 3383
  - corpus sha256 =
    `8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa`
  - model = `phi4-mini:latest`
  - `MAX_PROMPT_TOKENS X = 950`
  - `PROMPT_OVERHEAD_RESERVE_TOKENS O = 206`
  - `CONTEXT_PACK_MARGIN m = 0.86`
  - provisional `CONTEXT_PACK_BUDGET_TOKENS B = 639`
  - `CHARS_PER_TOKEN_EST = 4`
  - `CITATION_HEADER_EST_TOKENS = 14`
  - `TOP_K_CONTEXT = 5`

- 事实：
  - 3379 个模拟窗口中，有 70 个在 `D=0` 时满足
    `O + actual_context > 950`。
  - 70 个窗口中 51 个至少包含一个当时已定义的异常标签。
  - 剩余 19 个窗口为 `none_observed`。
  - 排除异常标签 chunk 的诊断性 counterfactual 后，
    仍有 `19 / 3218 = 0.59%` 的窗口超预算。
  - `none_observed` chunk 的 chars/token：
    min / p5 / p50 / mean / p95 / max =
    `2.331 / 3.787 / 5.134 / 5.602 / 9.047 / 24.600`。
  - `none_observed` rendered actual / est_prompt_tokens：
    p50 = `0.7770`，p95 = `1.0327`，max = `1.6640`。
  - 有 102 个 `none_observed` chunk 的
    `actual_rendered / estimate > 1.15`。
  - 真实相邻 rendered chunk 的 separator 增量实测 max = `1 token`。

- 推论：
  - `CHARS_PER_TOKEN_EST=4` 对总体中位 chunk 是保守估计，
    但总体保守不能推出尾部安全。
  - prompt-budget correctness 不能只由总体 chars/token 中位数、
    p95 或单一 ±15% 假设证明。
  - “总体平均高估”与“局部尾部低估导致 prompt overflow”
    可以同时成立。

- **决策：S4a.9 的安全判断必须以真实 rendered context 的 tokenization
  为依据；不能再用总体 chars/token 中位数替代尾部安全性。**

- **决策：本轮不得因为观察到 overflow 就事后修改
  `CHARS_PER_TOKEN_EST`、margin、MAX_PROMPT_TOKENS 或 packing 规则。**
  先做 failure decomposition。

- 待办：
  - 对 19 个 `none_observed` 窗口逐窗口 deep dive。
  - 单独检验 actual-token-aware prefix packing。
  - framing boundary `D` 保持显式未知，除非能从版本控制证据重建。


### [L3] S4a.9c 方法论更正：tokenization 不可加性不得被“估算误差归零”掩盖

- 事实：
  - rendered chunk 的 token 数预计算后，
    chunk 内部 estimator 误差可以消除。
  - 但 tokenizer 在字符串边界上并不一般满足严格可加。
  - 已实测真实相邻 rendered chunk separator 增量 max = 1 token。
  - 当时 9a-bis 的完整 framing template 是通过 stdin/heredoc 临时运行，
    未进入版本控制，因此 framing 与首/末 chunk 的 boundary delta `D`
    无法从已版本控制证据精确补算。

- **更正：此前“预计算 token 后估算误差直接归零”的表述过强。**
  能消除的是逐 chunk 的 chars/token proxy 误差；
  完整 prompt 是否安全仍取决于实际拼接 tokenization。

- **决策：未知的 `D` 不猜上界，不伪装成已关闭变量。**
  结论必须写成条件式。

- **决策：任何测量若其输出将进入契约常量或承重派生量，
  测量脚本与输入模板必须进入版本控制。**
  只保存输出数字或脚本 sha256 不足以支持未来补算派生量。

- 待办：
  - 后续完整 prompt admission control 应直接 tokenize 完整 prompt，
    而不是继续维护 `O + chunk + SEP + D` 的误差项链。


## 2026-09-17 · S4a.9c none_observed deep dive 完成

### [L2] 19 个 clean-labeled overflow 的主因是正文 token estimator 尾部，不是 citation header

- owner_experiment: S4a.9c deep dive

- 事实：19 个 `none_observed` 超预算窗口的 failure shape：
  - `A_single_chunk_tail = 16 / 19`
  - `B_multi_chunk_accumulation = 3 / 19`
  - `C_header_boundary = 0 / 19`
  - `D_mixed = 0 / 19`

- 事实：
  - 这些窗口的真实 citation header increment 恒为 11 token。
  - 当前 `CITATION_HEADER_EST_TOKENS = 14`。
  - 因而 header 在这些窗口中是高估而非低估；
    越界来自正文侧的 token estimator tail。
  - 这些 chunk 的 `actual_text / est_tokens = 1.01–1.58`，
    对应 chars/token `2.33–3.94`。

- **决策：不得把这 19 个 overflow 归因于 citation header。**
  当前证据指向正文 chars/token 尾部。

- **决策：`CITATION_HEADER_EST_TOKENS=14` 的局部高估也不得反过来
  被解释为“因此应该调低 header 常量”。**
  本轮是诊断，不是调参。


### [L2] actual-token-aware prefix packing 在当前 clean-window 样本上消除了已观察 overflow

- 事实：保持 relevance/order、prefix semantics、`TOP_K_CONTEXT=5`
  与 X/O 不变，仅使用实测 rendered token count 与实测 separator：

  对原 19 个窗口：
  - cap = 744 (`X-O`)：
    19/19 在加入导致越界的 chunk 之前被挡住；
    0/19 最终实际越界。
  - cap = 639：
    19/19 被提前挡住；
    0/19 最终实际越界。

- 对全部 3218 个 `none_observed` 窗口、cap=744：
  - overbudget = `0 / 3218`
  - actual context p50 / p95 / max =
    `635 / 734 / 744`
  - realized k：
    - k=1: 0.78%
    - k=2: 13.67%
    - k=3: 43.66%
    - k=4: 29.18%
    - k=5: 12.71%

- 事实：对这 3218 个实际 pack，
  `Σ(rendered chunk) + Σ(separator increment)` 与完整 context 串实测 token 数的残差：
  min / p50 / max = `0 / 0 / 0`。

- **决策：上述“残差为 0”只是在当前 3218 个 pack 上的实测事实，
  不是 tokenizer 可加性的一般性证明。**

- **决策：actual-token-aware packing 是后续设计候选，
  但本轮不据此修改 contracts 或 packing。**

- 事实：在 actual-token-aware cap=744 下，
  `TOP_K_CONTEXT=5` 有 12.71% 窗口真正触顶；
  因而“TOP_K=5 几乎不会触及”的旧解释不再成立于该 counterfactual。

- 待办：
  - production 预算设计时重新定义 TOP_K 的语义；
  - 优先考虑 full-prompt token admission，而不是继续叠加 estimator 修补项。


### [L3] FMM estimator-tail enrichment 存在，但与 +66 chunks 是否同源仍 unresolved

- 事实：
  - FMM 当前 `878 / 3383 = 25.95%` chunks。
  - FMM 占 19 个 `none_observed` overbudget windows：
    `10 / 19 = 52.6%`。
  - FMM 占这些窗口涉及的 37 个去重 packed chunks：
    `22 / 37 = 59.5%`。
  - descriptive window enrichment =
    `(10/19) / (878/3383) = 2.03`。
  - descriptive chunk enrichment =
    `(22/37) / (878/3383) = 2.29`。
  - 版本控制中的旧基线记录 FMM = 812 chunks，
    当前为 878，即 `+66 / +8.1%`。

- 事实：这些 FMM tail chunk 共同形态主要是维护编码/编号密集，
  不是 table-layout dense。

- 限制：旧版本只保存了 per-document chunk count，
  没有旧的 per-chunk corpus，因此无法识别“新增的 66 个 chunk”
  并与 estimator tail 做重合分析。

- **决策：“FMM +66 chunk 与 estimator tail 同源”状态 = `unresolved`。**
  enrichment 是 observation，不是同源性证据。

- **决策：不得由 enrichment 推导 parser 修改。**


## 2026-09-17 · TACM native extraction failure 边界确认

### [L3] TACM PDF p.38–103 可作为已实测 native-text failure 区间

- 事实：
  - PDF p.93：Type 3 / Custom / `uni=no`；`pdftotext -layout` 乱码。
  - p.94：Type 3 / Custom / `uni=no`；乱码。
  - p.103：Type 3 / Custom / `uni=no`；乱码。
  - p.104：Calibri/Verdana TrueType / WinAnsi / `uni=yes`；
    `pdftotext -layout` 恢复正常，PCL E-Learning Matrix 可读。
  - 起始侧 p.38 的坏页证据此前已取得。

- **决策：TACM PDF p.38–103 可写为“已验证 native text extraction
  不可用区间”。**

- **边界：不得把“Type 3 / Custom / uni=no”直接升级为因果根因。**
  它是与 failure 同时出现的结构证据。

- **更正：此前“任何 parser 改动都救不了它”的说法过强。**
  当前证据只证明基于现有 PDF text layer / `pdftotext` 的路径无法恢复；
  OCR / visual extraction 未被排除。

- 观察：截图显示该区间至少部分页面为 Microsoft Forms 风格的 competency
  assessment 页面；这解释了可能的生成机制，但不是已证明根因。

- 待办：OCR 是否值得用于该区间，必须与“是否建立通用 OCR fallback”
  分开决策。


### [L2] 更正：2026-08-31「全部有文本层，无需 OCR」的结论不成立

- 事实：2026-08-31 勘察记录「发现 1 ✅ 全部有文本层，无需 OCR」，
  依据为 `pdffonts` 显示 9 份 PDF 的字体表均非空。

- 事实：TACM PDF p.38–103 的字体表非空，但相关字体为
  Type 3 / Custom encoding，`pdffonts` 的 `uni` 列为 `no`；
  `pdftotext -layout` 输出不可用。

- **更正：该结论对 TACM p.38–103 不成立。**
  「字体表非空」与「字形可映射到 Unicode / native extraction 可用」
  不是同一个量。

- 依据（为何当时看起来成立）：
  `uni` 列当时已经存在于 `pdffonts` 输出中，
  不是数据缺失，而是判断时使用了错误的观测量：
  字体表非空 → 推断存在可用文本层 → 推断无需 OCR。

- 推论：该错误属于 §6.2 第 14 类错误的早期实例：
  观察到的量与最终填写的判断不是同一个被测量对象。

- **决策：按只追加原则不回改 2026-08-31 的历史记录，
  以本条作为明确更正。**

- **决策：今后任何“native 文本层可用性”判断必须直接引用
  Unicode mapping / extraction output usability 或等价证据，
  不得以字体表是否非空作为充分依据。**

- 边界：本条只推翻“全部有文本层，因此无需 OCR”这一结论，
  不改变 2026-08-31 其余独立勘察发现。


## 2026-09-17 · S5 parser / corpus baseline 建成，但验收仍有开放 failure surfaces

### [L3] S5 corpus baseline 的可再生结果

- 事实：
  - 9/9 PDF 解析成功。
  - 总页数 = 1335。
  - chunk count = 3383。
  - `corpus/chunks.jsonl` sha256 =
    `8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa`。
  - 每手册 chunk：
    - CRM 240
    - CMM 363
    - EMM 344
    - ERM 364
    - FMM 878
    - NPM 286
    - QMM 416
    - SMM 300
    - TACM 192
  - build time ≈ 2.7–2.8 s。
  - 同一输入连续 build 的 `chunks.jsonl` sha256 完全一致。

- **决策：该 3383-chunk corpus 作为当前 S5 baseline 与后续诊断的冻结输入。**

- **边界：baseline 可再生 ≠ S5 已完全验收。**
  TACM 乱码、视觉内容丢失、section metadata fallback 等 failure surface 仍开放。

- **决策：不得因为数量、长度、确定性等 shape checks 通过，
  就把 S5 解释为内容正确性 PASS。**
  TACM 乱码 chunk 已证明“形状正常”可以与“内容不可用”同时成立。


### [L1] Parser 与 corpus builder 必须进入版本控制，corpus sha 才有可追溯生成链

- falsified_if: 无；这是 provenance / reproducibility 纪律。

- 事实：在 2026-09-17 之前，
  `components/parsers/kaiva_pdf.py` 与 `ingest/build_corpus.py`
  仍是 untracked，但 corpus sha 已被 S4a.9c 等测量引用。

- 推论：一个 corpus digest 若由未版本控制的生成代码产生，
  digest 只能标识结果，不能复现生成过程。

- **决策：parser 与 corpus builder 必须进入 Git。**

- 实施：
  - commit `545947a`
    `feat: add KAIVA PDF parser and corpus builder S5 baseline`
  - 随后从该 commit 的代码重建 corpus：
    `3383 chunks`
    sha256 仍为
    `8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa`

- **决策：自此可把 `545947a → 8c6bee0a…` 作为 S5 baseline 的
  provenance 链。**

- **边界：commit message 中的 S5 baseline 不等于宣布 S5 PASS。**


## 2026-09-17 · Citation section metadata 独立审计

### [L3] 38 条人工 citation 的 3 个 exact mismatch 是 representation difference，不是已证 parser bug

- 事实：38 条人工 citation 与 corpus page-level section 对比：
  - exact match = 35
  - exact mismatch = 3
  - citation page missing chunk = 0

- mismatch：
  - FL13 EMM p.131：gold `Chapter 15` vs parser `15`
  - PR05 EMM p.131：gold `Chapter 15` vs parser `15`
  - CD02 EMM p.96：gold `Chapter 10` vs parser `10`

- 后续 PDF / parser 审计：
  - EMM 页眉并无独立 SECTION 字段；
    页面使用 `Chapter 15 – ...` / `Chapter 10 – ...` 标题。
  - parser 对 EMM chapter title 有意规范为裸章节号。
  - EMM 157 个 chapter pages 的 section 均使用裸数字，无混杂表示。
  - 38/38 citation 的 semantic location 均一致。

- **决策：这 3 条 mismatch 不作为 parser bug，也不修改 v5.3 testset。**
  当前证据支持“representation-only mismatch”。

- **决策：exact string equality 与 semantic location identity 必须分开。**
  后续 scorer 是否 canonicalize section 属于独立设计问题，
  本轮不提前决定。

- 边界：38 条 gold 的一致性只覆盖这些 citation 页，
  不证明全 corpus section metadata 正确。


### [L2] `title_line_fallback` 是独立于 OCR 的 citation metadata failure surface

- owner_experiment: parser metadata audit / Phase B metadata gate

- 事实：
  - corpus page-level section source：
    - `explicit_header_label`: 993 页 / 2789 chunks
    - `title_line_fallback`: 254 页 / 594 chunks
    - inherited / unresolved：当前有 chunk 页中 0
  - 96 页 / 278 chunks 被描述性规则标为 section anomaly candidate，
    横跨 6 份手册：
    TACM 66、EMM 13、CMM 7、ERM 5、CRM 4、SMM 1。
  - 已确认异常集中于 `title_line_fallback`。
  - fallback 的核心行为允许页眉扫描窗口中第一条非 doc_id 文本
    被直接作为 section。
  - TACM p.38–103 的 50 个乱码 chunks：
    50/50 section 来自 current-page extraction，
    0 inheritance，0 unresolved。
  - 其中 37 个 section 有明显乱码证据；
    另有 13 个值形似合法字符串，例如 p.100 的 `"9"`，
    恰好可与真实章节号碰撞。
  - TACM p.104–115 出现 `section = "PCL E"`。
  - TACM p.116–120 出现完整问句被当作 section。

- **更正：此前“乱码页会静默继承 p.37 section”的机制猜测被实测证伪。**
  实际上 permissive fallback 在本页取得了错误字符串，因此 inheritance 没发生。

- **决策：body text usability 与 citation metadata correctness 是两个独立质量轴。**
  `body usable` 不推出 `citation metadata valid`。

- **决策：未来 OCR quality gate 必须有独立 citation-metadata gate。**
  OCR 正文成功不得自动让 citation metadata 通过。

- **边界：本轮不据此删除 fallback、不修改 parser。**


### [L3] section 取值行与正文剥离语义存在独立风险

- 事实：section 来源行在部分 fallback 路径中没有从正文剥除：
  - numbered_regex：12 页
  - raw_line：78 页
  - 合计 90 页

- 推论：
  - 若未来检索/BM25 与 renderer 按现有规划实现，
    同一字符串可能同时出现在正文与 citation header。
  - 这可能抬高 BM25 词频并重复占用 prompt token。

- **决策：该问题独立记录，不与 OCR detector 合并。**

- 边界：当时 retriever / renderer / scorer 尚未实现，
  因此这是 future risk，不得写成“当前 M2 已被扣分”。


## 2026-09-17 · OCR Phase A：native extraction usability 全语料调查

### [L2] `uni=no` 不是 production OCR trigger；结构信号与文本可用性不是同一个量

- owner_experiment: OCR Phase A

- 事实：
  - 扫描 9 PDF / 1335 页，采集失败 0。
  - 全量逐页采集 structural + native extraction signals。
  - 1198 个 unreviewed 页面含至少一个 `uni=no` 字体，
    占 unreviewed 约 94.4%。
  - mixed `uni=yes + uni=no` 页面 = 941。
  - 人工抽样 mixed / all-uni-no 页面正文均可读。
  - TACM confirmed_bad 区间的 Type3 / Custom signal 有区分度，
    但不能由此证明 Type3 是乱码的因果根因。

- **决策：`uni=no → OCR required` 禁止作为 production rule。**
  structural signal 适合作为诊断证据，不等于 page usability。

- **决策：production detector 的被测量对象是“该页 native extraction
  是否支持本项目的 retrieval/citation”，不是字体属性本身。**

- 运行成本：
  - 逐页 `pdffonts` ≈ 55.8 s
  - 整份 `pdftotext` 后计算 output signals ≈ +0.9 s
  - 当前 build corpus ≈ 2.8 s

- **决策：是否把 structural channel 放进 hot path 必须有增量收益证据，
  不能因为它诊断价值高就自动进入 production ingest。**


### [L2] 当前 parser 存在“图像业务内容被静默丢页”的第二类正文 failure surface

- 事实：
  - `extracted_chars == 0`: 13 页
  - `0 < extracted_chars < 120`: 17 页
  - `extracted_chars < 120`: 30 页
  - parser 在 strip 后因 body `< CHUNK_MIN_CHARS=120`
    实际丢弃 88 页。
  - Phase A 抽样的 8/8 丢弃页均发现页面视觉层存在业务内容，
    包括流程图、扫描政策页、图片化表格等。
  - 示例：
    - QMM p.139 / p.148：整页扫描政策文字
    - CRM p.31：BCDR 流程图
    - ERM p.17：应急报告流程图
    - TACM p.12：能力评估流程图
    - EMM p.103：Open Reporting policy poster
    - SMM p.71：Hot Work schematic
    - CMM p.113：绩效评估表

- **决策：native text garbling 与“视觉内容存在但 native body 不足”
  是两个正交 failure surface。**

- **决策：`body_chars < 120` 不能直接等价为 `OCR required`。**
  同一观察也可由封面、空白页、分隔页产生。

- **决策：当前 parser 对这些丢页缺少逐页 audit record，
  属于显式 failure-surface 欠账。**
  本轮只记录，不修改实现。


### [L3] OCR 审计信息优先留在 page-level audit，不自动升级 Chunk contract

- 事实：OCR provenance、detector signals、tool version、
  artifact hash 等主要服务 ingest/debug。
  检索与生成并不天然需要全部字段。

- **决策：不要因为 ingest 层需要审计信息，
  就自动把 extraction metadata 提升成全链路 Chunk contract。**

- 设计候选：
  `page_quality` 类 artifact 以
  `(doc_id, source_filename, source_hash, pdf_page)` 定位，
  记录 native/OCR/citation quality。

- **边界：是否最终需要把 extraction_method /
  citation_metadata_status 提升进 Chunk，
  留到 Phase B Design Freeze 决定。**


### [L1] OCR fallback 不得硬编码 TACM 或页码

- falsified_if: 无；这是系统泛化边界。

- 事实：未来文档集可能完全不同。
  TACM p.38–103 只是 confirmed_bad calibration sample。

- **决策：production OCR fallback 禁止出现任何
  `doc_id == TACM` / `38 <= page <= 103` 或语义等价逻辑。**

- **决策：机制必须是
  `native extraction → page quality decision → fallback / explicit state`，
  由可用性证据触发，而不是由已知文档身份触发。**


## 2026-09-17 · OCR Phase A.1：视觉通道调查

### [L2] 视觉通道证明第二类 failure 无法由 V1 文本 detector 覆盖

- owner_experiment: OCR Phase A.1

- 事实：
  - 全 1335 页以 40 / 100 dpi 采集视觉信号，失败 0。
  - 使用 PGM + numpy；Pillow 未安装且未新增依赖。
  - 40 dpi 全量约 14.7 s；
    100 dpi 全量约 25.8 s；
    pdfimages ≈ 3.1 s。
  - A.1 已复核的 29 张 image-based business-content dropped pages：
    V1 命中 `0 / 29`。
  - 页面中部 rendered ink signal 可命中 `29 / 29`。
  - `pdfimages` object presence 区分度低：
    1197 个正常有 chunk 页中 1176 页本来就有 image object，
    主要受页眉 logo 等影响。

- **决策：只建立“乱码 detector”不足以覆盖当前 corpus 的 native extraction failures。**
  第二类 failure 需要视觉证据或等价机制。

- **决策：image-object existence 不作为当前 production detector 的充分依据。**

- **决策：visual detector 只判断“页面是否存在 native extraction 未覆盖的视觉内容迹象”，
  不承担“这些内容是否值得索引”的业务价值判断。**


### [L3] TACM p.55 的历史 confirmed_bad 标签需要语义复核

- 事实：
  - TACM p.55 在 40 / 100 / 150 dpi 下所有像素均为 255；
    nonwhite absolute count = 0。
  - 人工视觉观察为空白页。
  - V1 不触发该页。

- **决策：保留历史标签不回改，但记录
  `current_content_observation = blank_or_separator`。**

- **决策：不得为了把 detector recall 从 65/66 改成 65/65
  而事后修改 benchmark denominator。**
  是否重定义 confirmed_bad 属于标签语义决定。


### [L3] TACM p.38–103 的内容价值与 OCR 机制是两个独立问题

- 事实：15 页视觉抽样：
  - business_knowledge_present = 1
  - repeated_form_scaffolding = 6
  - mixed = 7
  - blank = 1
  - uncertain = 0

- **决策：建立通用 OCR fallback ≠ 决定 TACM p.38–103 全部值得 OCR。**

- **决策：detector 负责 extraction failure；
  content policy 负责 OCR 后内容是否值得进入 RAG。
  两者不得合并成一个阈值。**


## 2026-09-21 · OCR Phase A.2：88 个 parser-dropped 页全量复核

### [L2] 88 个 dropped pages 的内容分布被完整复核

- owner_experiment: OCR Phase A.2

- 事实：88/88 完成 100 dpi visual review：
  - `visual_business_content = 66`
  - `form_or_template = 15`
  - `mostly_header_footer = 4`
  - `cover_or_frontmatter = 2`
  - `blank_or_separator = 1`
  - `uncertain = 0`

- 事实：NEGATIVE 仅 7 页，因此预注册规则选择 leave-one-out，
  而不是 2/3–1/3 holdout。

- **决策：不得把这 88 页笼统称为“短页噪声”。**
  其中绝大多数含视觉业务内容或表单内容。

- reviewer limitation：
  全部标签来自 `claude_visual_review`，
  不是 independent human ground truth。

- **决策：后续引用这些结果时必须写
  “validated against Claude visual-review labels on current 9-PDF corpus”，
  不得写 human-validated / ground-truth-validated / production-proven。**


### [L2] 中部墨迹量 F1/F2 无法稳定区分封面与业务视觉页；V2 保持 underdetermined

- 事实：
  - EMM p.1（cover / NEGATIVE）middle ink ≈ 0.048。
  - CRM p.77（VBC / POSITIVE）≈ 0.046。
  - CRM p.74（VBC / POSITIVE）≈ 0.037。
  - 即封面的 ink 高于两个真实业务视觉页。
  - bbox-density F2 同样不能拉开：
    CRM p.74 相对 max-negative 的余量仍 `< 1`。

- LOO：
  - C1 F1@40/245：POS 66/66，NEG trigger 1/7（EMM p.1）
  - C2 F1@100/245：66/66，1/7
  - C3 F2@40/245：65/66，2/7

- LODO：
  - C1 CRM fold 漏 p.74 / p.77
  - C2 EMM fold 触发 p.1
  - C3 多折失败

- **决策：V2 threshold status = `still_underdetermined`。**
  不通过继续降低 ink threshold 来掩盖 feature overlap。

- **决策：这里的问题是 feature discrimination，
  不是简单“negative 样本数量不足”。**

- 待办：仅允许检验 A.1 已预先采集的结构信号，
  不事后无限扩 feature search。


## 2026-09-21 · OCR Phase A.2b：active-row 机制检验与 content-completeness census

### [L2] active-row 解决了 A.2 的 cover-vs-business-content 单点冲突

- owner_experiment: Phase A.2b

- 预注册：
  - 在读取 EMM p.1 / CRM p.74 / CRM p.77 active signals 前冻结。
  - prereg block sha256 =
    `f48349e609ae2d5cbbe5bf0698962a88f24b9b5a0495e0b2d1daa01af1c60b50`
  - 预注册方向：
    cover = 少数大字块 → active-row 较低；
    distributed diagram/table = 行覆盖更广 → active-row 较高。

- 三页关键实测：
  - EMM p.1：
    d40 active_row = `0.1624`
  - CRM p.74：
    `0.6389`
  - CRM p.77：
    `0.7267`

- 同时 column 方向反向重叠：
  - EMM p.1 col ≈ `0.6556`
  - CRM p.74 col ≈ `0.2680`
  - CRM p.77 col ≈ `0.4551`

- 验证：
  - A1/A3/A4/A6 row 类特征：
    LOO POS miss = 0/66；
    NEG trigger = 0/7；
    LODO 8/8 documents pass；
    fold instability = 0。
  - column 类 A2/A5 不满足。

- **决策：Part A classification = `STRUCTURE_CASE_1`。**
  在当前 66 POS / 7 NEG / 9-PDF corpus 上，
  active-row 的分离方向与预注册机制假设一致，
  并解决了 F1/F2 的 cover-vs-content 冲突。

- **边界：该结果不等于 production V2 已冻结。**
  NEG 仍只有 7 页；`V2 status` 继续保持 `still_underdetermined`
  直到 Phase B 明确 production policy。


### [L1] `native_text_usable` 与 `page_content_complete` 必须拆成两个概念

- falsified_if: 发现所有已有 chunk / native-text-usable 页面
  均能完整表示页面上的业务知识。

- 事实：QMM p.110 是首个确证反例：
  - native body = 1147 chars
  - 有 chunk
  - V1 不触发
  - 页面流程图中的
    `Concur with parameters for change`、
    `Identify risk assessment team`、
    `Close out and Sign Off`
    在 native/corpus text 中均不存在。

- Phase A.2b 进一步确认：
  - Part B population = 1197 个“有 chunk、body≥120、V1 不触发”的页面。
  - review 175 unique pages。
  - confirmed `VISUAL_KNOWLEDGE_MISSING` = 16 页，
    横跨 CMM / CRM / EMM / ERM / QMM / SMM 六本手册。
  - missing 形态包括：
    图片化评分表、e-learning matrix、流程图、设备图、
    截图中的时限规则、图形中的热线号码等。

- **决策：**
  `native_text_usable ≠ page_content_complete`。

- **决策：Phase B 不得再用一个 `page usable` 状态同时表示
  “已抽到的文本质量正常”和“页面业务内容已完整覆盖”。**

- 方法论记录：
  这是项目第四次出现“一个字段承担两个不同问题”的同形错误：
  1. relevance vs match_score
  2. est_tokens vs est_prompt_tokens
  3. body usability vs citation metadata correctness
  4. native_text_usable vs page_content_complete

- **决策：Phase B 至少必须把正文质量、内容完整性、
  citation metadata correctness 视为独立被测量对象。**


### [L2] 第三类 extraction-completeness failure 已确认重复存在，但 prevalence 尚未估计

- 事实：
  - prioritized sample：14 / 100 `VISUAL_KNOWLEDGE_MISSING`
  - random control：0 / 50
  - gold-page census：2 / 28 unique gold pages
  - 总 confirmed unique missing pages = 16

- **决策：不得把三组比例合并成 corpus prevalence。**
  prioritized 不是概率样本；random n=50 太小；
  gold 是 citation-page census，抽样目标不同。

- **决策：第三类 failure 的“存在性与跨文档重复性”已被确认；
  “全 corpus prevalence”保留为 residual uncertainty，
  不再作为 Phase B Design Freeze 的 blocker。**


### [L2] Gold-page extraction completeness：2/28 页存在视觉知识缺失，但当前 gold 引文证据仍在 corpus 中

- owner_experiment: Phase A.2b / S6 readiness

- 事实：
  - 38 条 citation → 28 unique gold pages。
  - 其中：
    - COMPLETE_NATIVE = 26
    - VISUAL_KNOWLEDGE_MISSING = 2
    - VISUAL_NON_TEXTUAL = 0
    - UNCERTAIN = 0
  - 两页：
    - ERM p.14：影响 FL12 / CN03 / ML03
    - SMM p.38：影响 CN04

- 视觉层缺失示例：
  - ERM p.14：
    `In charge of vessel` 等 Line of Communication 图内标签。
  - SMM p.38：
    `Check what PPE is required as per the PPE Matrix` 等 toolbox diagram 内容。

- 事实（gold-quote 判据版本）：
  执行前曾提出「quote fragment MISS → G3」；
  在实际运行前收紧为：
  `MISS → G3 candidate，必须与源 PDF 直接比对后方可升格`。
  理由是 MISS 亦可能来自 normalization、chunking 或 quote 转录差异。
  本轮所有 fragment 均 HIT，因此该 MISS 分支未被触发。

- 随后对 4 条受影响 gold citation 的 quote fragments
  在当前 page corpus 中逐条复核：

  - FL12 / ERM p.14：`2/2 HIT`
  - CN03 / ERM p.14：`1/1 HIT`
  - ML03 / ERM p.14：`1/1 HIT`
  - CN04 / SMM p.38：`6/6 HIT`

  合计：`10 / 10 quote fragments HIT`。

- **决策：当前没有观察到 gold citation 的引用证据只能存在于视觉层的 G3 情况。**
  这 4 条 citation 的 gold quote evidence 均存在于当前 corpus text。

- **边界：这不证明缺失视觉内容与答案完全无关。**
  它证明的是当前人工 gold citation 所引用的证据可由现有 corpus 支撑。

- **决策：不因第三类 extraction-completeness failure 在 S6 前修改 parser/corpus。**
  当前 corpus 可继续作为 S6 baseline；
  第三类 failure 记录为 residual risk，并在后续设计/评测中显式保留。

- **决策：不得把“gold quote HIT”解释为“页面 extraction complete”。**
  2/28 gold pages 已经证明两者可以同时成立：
  gold evidence present + page content incomplete。

- **边界（证据强度限制）：10/10 HIT 可能部分受到评测集构造方式影响，
  因而不是关于整体 extraction completeness 的独立随机证据。**
  gold citation 的 quote 由人工从 PDF 抄录；
  `question_anchors` 是否由 parser 可抽取文本生成，
  此前调查尚未取得足够 provenance 证据，
  因此继续记为
  `selection-bias hypothesis remains unresolved`。

- 若该假设成立，则 gold questions / citations 天然更可能落在
  native extraction 已能暴露的内容上，
  `"quote 命中 corpus"` 的先验概率会偏高。

- **决策：R2 仍成立。**
  这里的 R2 只回答：
  “是否已有证据要求因为第三类 failure 而在 S6 前修改当前 corpus？”
  当前答案为否，因为已识别的 4 条受影响 citation 的全部 10 个 quote fragments
  均存在于当前 corpus。

- **决策：不得把 R2 扩大解释为
  “第三类 failure 对评测无影响”或
  “当前评测集能够测量 extraction completeness”。**

- 待办：
  若后续 Phase B / M5 取得 `question_anchors` 生成 provenance，
  并证实 selection-bias hypothesis，
  应追加记录并相应收窄本条证据的外推范围。


### [L3] 方法论：第 14 类错误在 parser / OCR 调查线新增四个实例

- 事实（承接 2026-09-11 记录的第五次实例，编号续）：

  ⑥ 由「TACM 字体为 Type 3 / uni=no」
     推出「任何 parser 改动都救不了它」
     —— 已更正；该实验从未排除 OCR / visual extraction。

  ⑦ 由「TACM p.38–103 无法正常抽取 section」
     预测「会静默继承 p.37 的 section」
     —— 实测 50/50 chunk 的 section 来自本页 extraction，
     0 个 inheritance；
     机制猜错，且实际 permissive fallback
     可以把任意字符串变成看似合法的 section。

  ⑧ 由「section 字段计划被 renderer 放入 prompt」
     推出「模型正在因为 parser section 缺陷被 M2 扣分」
     —— 实测当时 renderer / citations_correct scorer 均 not implemented；
     正确表述为
     `future risk if implemented as specified`，
     不是 observed current impact。

  ⑨ 由「gold citation 页的 rendered ink signal」
     试图判断「第三类 page-content-incompleteness 是否影响 M2」
     —— rendered ink 测的是视觉内容量，
     page-content completeness 测的是业务知识是否已进入 native/corpus text；
     两者不是同一个被测量对象。
     该错误在执行该判据前被指出并收紧，
     未污染正式测量。

- 推论：承接此前记录，这些实例再次集中发生在
  “把一个观察写成字段值、判据或因果结论”的落笔位置，
  而不是原始测量本身。

- **决策：§6.2 第 14 类错误的已记录实例计数更新为 9。**

- **决策：继续执行落笔检查：**
  “我观察到的那个量，和我要填写/决定的这个字段，是同一个东西吗？”

- **决策：该问题继续作为项目审查流程中的第 6 问。**

- 事实（该检查有效的证据）：
  - ⑨ 在实验执行前被拦下，因此没有产生错误的正式测量结论。
  - ⑥⑦⑧ 经后续实验或代码核查后均被更正或收窄。


## 2026-09-21 · OCR / parser 调查线关闭

### [L2] Phase A / A.1 / A.2 / A.2b measurement line CLOSED

- owner_experiment: Phase B Design Freeze

- 已关闭的经验问题：

  1. native text 存在但不可用：
     TACM p.38–103 已确认。

  2. native body 不足但视觉层有业务内容：
     88 页全量 review 已确认。

  3. native text 可用但页面业务内容不完整：
     16 个 confirmed examples，跨 6 本手册。

  4. cover vs visual-business-content 的简单 ink overlap：
     active-row 机制实验得到 `STRUCTURE_CASE_1`。

  5. citation metadata correctness：
     已证明与 body usability 独立；
     `title_line_fallback` 是单独 failure surface。

  6. 当前 gold citation 是否因第三类 failure 而缺失引用证据：
     4 条相关 citation、10/10 quote fragments 均存在于 corpus。

- **决策：不再增加 Phase A.3 / A.4 或继续扩大调查样本。**
  当前剩余问题主要是 design choices，
  不是继续测量就会自动得到唯一答案的问题。

- residual uncertainties：
  - V2 production threshold 仍未冻结。
  - NEG 样本只有 7。
  - random completeness control 只有 50。
  - Claude visual review 不是 independent human ground truth。
  - 当前结果只作用于这 9 份 PDF，不外推到未来不同文档集。
  - full-corpus visual-content-missing prevalence 未估计。
  - question-anchor selection-bias hypothesis 尚未由 provenance 证实或证伪。

- **决策：上述不确定性记录为 residual risk，
  不再阻塞 Phase B Design Freeze。**

- **决策：下一步不是继续调 detector，而是冻结设计。**

- Phase B 必须明确区分至少三个轴：
  1. native body quality / usability
  2. page content completeness
  3. citation metadata correctness

- OCR 是 failure remediation mechanism，
  不是这三个状态的同义词。


## 2026-09-21 · 测量与生成链 provenance 闭环

### [L1] 承重测量脚本与不可再生 review labels 必须进入 Git

- falsified_if: 无；这是 reproducibility 纪律。

- 事实：
  - 此前 9a-bis framing template 未入库，
    导致后续无法精确补测 `D`。
  - 旧 FMM 只有 per-doc chunk count，没有 per-chunk baseline，
    导致 +66 chunks 的同源性无法检验。
  - parser / builder 曾在 corpus 已被大量实验引用时仍处于 untracked 状态。

- 推论：只保存结果 log 或 sha256 不足以保证未来可解释性。
  特别是人工/reviewer judgment 不可由源 PDF 自动重建。

- **决策：承重测量脚本必须版本控制；
  不可再生的人工/reviewer judgment 必须随脚本或独立标注 artifact
  进入版本控制。**

- 已完成：
  - `9611e9d`
    `experiment: add reproducible OCR fallback survey`
    → `scripts/ocr_survey.py`

  - `124403c`
    `experiment: add reproducible citation section audit`
    → `scripts/audit_citation_sections.py`

  - `545947a`
    `feat: add KAIVA PDF parser and corpus builder S5 baseline`
    → parser + corpus builder

  - `727a20b`
    `experiment: add reproducible OCR visual survey`
    → `scripts/ocr_visual_survey.py`

  - `2e8e92c`
    `experiment: add A.2 visual detector threshold validation`
    → 88-page review labels + frozen prereg

  - `0df2ede`
    `experiment: add A.2b content completeness census`
    → 175-page review labels + frozen prereg

- **决策：可由版本控制脚本与冻结输入一条命令重新生成的 CSV/log
  可以不进入 Git；
  生成它们的承重脚本与不可再生 judgment 必须进入。**

- **决策：`545947a → corpus sha 8c6bee0a…`
  是当前 S5 baseline 的正式生成 provenance。**


### [L3] 预注册从“文字纪律”升级为可验证 artifact

- 事实：
  - A.2 / A.2b 对容易发生 threshold / feature fishing 的分析
    在查看关键结果之前冻结判据。
  - A.2b preregistration block 具有独立 sha256，
    后续结果没有回改该 block。

- **决策：对容易产生 feature fishing / threshold fishing 的实验，
  优先使用“预注册内容 + sha256 + 写入时间”形成可验证冻结，
  而不是仅在最终报告中声明“判据事先写好”。**

- **边界：预注册约束的是不得事后修改判据追结果，
  不是要求忽略反证。**
  若后续数据推翻预注册中的经验预期，
  正确动作是保留预注册并报告反证。


## 2026-09-21 · 进入 Phase B Design Freeze 前的边界

### [L1] OCR fallback 的设计问题与测量问题正式分离

- falsified_if:
  Phase B 发现仍存在一个尚未测量、
  且不能作为 residual risk 记录、
  会直接改变安全 / 契约设计的 blocker。

- 事实：
  Phase A measurement line 已关闭。

- 当前尚未拍板的问题包括：
  - V1 vs V1 + visual 的 production policy
  - active-row 是否进入 production V2
  - TACM p.55 benchmark label semantics
  - form/template content policy
  - TACM p.38–103 是否值得实际 OCR
  - OCR preprocessing artifact vs parser-level fallback
  - OCR determinism / cache / artifact provenance
  - OCR body quality gate
  - citation metadata gate
  - native + OCR merge semantics
  - page-level audit artifact vs Chunk contract
  - third-class page-content-incompleteness 的长期处置范围

- **决策：上述问题进入 Phase B Design Freeze，
  不再通过无边界追加调查来替代架构决策。**

- **决策：Design Freeze 前不实现 OCR、不改 parser、不改 Chunk contract、
  不改 corpus。**

- **决策：当前采用窄义 R2：**
  当前没有证据要求仅因第三类 extraction-completeness failure
  在 S6 之前修改当前 parser / corpus；
  `8c6bee0a…` corpus 可以继续作为 S6 baseline。

- **边界：R2 不是永久架构决定。**
  Phase B 若基于 citation safety、merge semantics、
  provenance 或其他设计约束决定先改 parser，
  应追加新的决策条目，不回改本条。

- **决策：完整 prompt admission control、OCR fallback、
  content-completeness policy 与 citation metadata gate
  都必须遵守同一原则：**
  被测量对象、状态字段和最终动作不得偷换语义。

- 待办：
  - Phase B Design Freeze。
  - Design Freeze 只冻结架构、状态语义、failure semantics、
    provenance 与 contract boundary。
  - 对每个提出的状态，只回答：
    “它能否被一个确定性测试区分出来？”
    不能 → 该状态需要合并、降级为 `uncertain`，或重新定义。
  - 完整 test plan 留给 implementation prompt。
  - Design Freeze 后单独写 implementation prompt。
  - 若 implementation 修改 parser / extraction text / chunking，
    必须重建 corpus 并产生新的 corpus sha；
    所有 corpus-hash-keyed artifact 与相关 S4a.9 measurements
    必须按真实依赖关系重新生成或重新验证。


## 2026-09-22 · Phase B Design Freeze：citation-safe selective OCR ingestion

### [L1] 三个独立问题不得重新压成一个 good/bad 状态：Phase B 冻结五个状态轴

- owner_experiment: S5c / Phase B implementation

- falsified_if:
  出现一个页面级判断，无法归入下列任一轴，且必须由某一轴兼职回答。

- 事实：Phase A → A.2b 已分别确认三个互不等价的问题：
  1. native body usability（TACM p.38–103 的乱码正文）
  2. page content completeness（16 个 confirmed 视觉知识缺失页，跨 6 本手册）
  3. citation metadata support（`title_line_fallback` 254 页 / 异常候选 96 页）
  OCR 之后还会多出两个：
  4. OCR body usability
  5. content / admission policy

- **决策：Phase B 冻结五个独立状态轴，任何一轴不得兼职回答另一轴的问题。**

  ```
  native_body_status              : usable / unusable / insufficient / uncertain
  page_content_completeness_status: presumed_complete / visual_content_suspected / not_assessed
  ocr_body_status                 : not_attempted / usable / degraded / failed
  citation_metadata_status        : explicit_supported / uncertain / failed
  content_policy_status           : admit / hold_for_review / reject_noncontent
  ```

- **决策：架构上强制 signals → states → actions 三层分离。**
  detector 层只产生 state，不产生动作；policy 层只读 state，
  **不得直接读 raw detector signal 决定 corpus action**。
  该分层的目的是让"一个信号承担业务价值判断"在代码结构上不可能发生，
  而不是依赖实现者记住一条提醒。

- **决策：`native_text_usable != page_content_complete`；
  `body usable != citation metadata correct`。** 两条不等式写进状态定义本身。

- **决策：不设 page content `complete` 状态。**
  没有确定性 signal 能证明"页面内容完整"；完整性只能被内容级人工比对**否证**，
  不能被信号**证成**。因此只保留 `presumed_complete`（本轮未发现缺失证据）。

- 边界：`remediation_action` 是动作枚举，不是观察，不得与上述五轴混用。


### [L1] `citation_metadata_status` 的窄语义：`explicit_supported` 不是 semantic verification

- owner_experiment: S5c / Phase B citation gate

- falsified_if:
  出现一条把 `explicit_supported` 当作"语义位置已验证"来消费的下游逻辑。

- **决策：冻结 `citation_metadata_status = explicit_supported / uncertain / failed`。**

- **决策：`verified_structural` 是 rejected terminology，不得作为 production state。**
  该名字过强：现有证据不能证明"显式标签 + 字符完整 + body usable"等价于"语义位置正确"。

- **决策：`explicit_supported` 只表示"存在直接、可追溯的 explicit metadata extraction evidence"。**
  它明确**不**表示：semantic verification；人工 ground-truth verification；
  directory / 目录核对；known-section-vocabulary 命中即正确；
  body usable 即 metadata correct；citation 整体已 verified。

- 反例形状（已实测）：TACM p.100 的 section 值 `"9"` 看起来合法，
  甚至碰巧属于该文档真实章节集合，但"值合法"不能证明"语义位置正确"。

- **决策：`title_line_fallback` 不自动判 `failed`**（fallback 本身不是错误的直接证据，
  只进 `uncertain`）；**"看起来奇怪"也不构成 `failed`**（`failed` 只接受明确失败证据，
  如 page identity mismatch、artifact page mismatch、extraction 过程失败、
  值明确损坏且无可接受 candidate）。

- **决策：metadata candidate 冲突（native candidate != OCR candidate）一律判 `uncertain`。**
  禁止：自动优先 native；自动优先 OCR；用 known vocabulary 自动择一；majority vote；silent inherit。
  两个 candidate 必须同时进入 page-level provenance。

- 边界：`Chapter 15` vs `15` 属 representation difference（既有 audit 38/38 semantic location 一致），
  不进入本 gate；section canonicalization 属 scorer / renderer 的独立设计问题。


### [L2] Phase B OCR architecture 冻结为 Hybrid C

- owner_experiment: S5c / Phase B implementation

- falsified_if:
  出现一条 parser/build 路径在 build 期间隐式触发 OCR，
  或 accepted artifact 被静默覆盖。

- **决策：Phase B architecture = Hybrid C。**

  ```
  源 PDF（immutable）
    → 岸端独立 OCR execution step
    → candidate artifact
    → acceptance
    → immutable / digest-addressed accepted artifact
    → parser/build 只消费 frozen artifact
  ```

- **决策：parser/build 不得隐式运行 OCR。**

- **决策：OCR 不增加船端 runtime dependency。**
  OCR 与 ingest 只在岸端执行，船端继续只消费冻结产物
  （依据实施方案既有的岸端/船端分工）。

- **决策：OCR execution 本身允许 nondeterministic；
  corpus-build determinism 通过"accepted artifact immutable + digest-addressed"
  与 OCR execution nondeterminism 解耦。**

- 冻结 cache identity：
  `source_hash`、`pdf_page`、`rasterizer`、`rasterizer_version`、`raster_dpi`、
  `ocr_engine`、`ocr_engine_version`、`langpack_identity_digest`、`ocr_params_digest`。

- 冻结 accepted artifact identity = `ocr_artifact_sha256`。

- **决策：`source_hash` 继续表示 immutable source PDF 的 SHA256**，
  与 `ocr_artifact_sha256` 绝不混用；同一个量不得保存为两个 persisted field。


### [L2] OCR repeatability 是 IMPLEMENTATION PRECHECK 0，不是新的 measurement round

- owner_experiment: S5c / Phase B implementation

- **决策：OCR repeatability characterization 既不是新的 Phase A measurement round，
  也不是 Hybrid C 的 architecture blocker。它是 IMPLEMENTATION PRECHECK 0。**

- 执行方式：实现开始后，先对少量固定代表页，在
  same source / same page / same raster / same OCR engine + version /
  same langpack / same params 下至少运行两次 OCR，
  比较 raw OCR text、structured artifact、`ocr_artifact_sha256`。

- **决策：若结果一致，只记录
  `observed deterministic under tested configuration`，不得外推**
  到其他配置、其他版本或其他文档集。

- **决策：若结果不一致，不推翻 Hybrid C；
  不得自动覆盖已 accepted artifact；
  新输出必须成为新 candidate / 新 digest，并重新走 acceptance。**

- **决策：无论 precheck 结果如何，corpus build determinism
  仍必须在 frozen artifact 上独立双跑验证。**


### [L1] primary body 单 channel invariant：禁止 native + OCR 字符串拼接

- owner_experiment: S5c / Phase B implementation

- falsified_if:
  出现一个 admitted page 的 primary body 由两个 channel 拼接而成。

- **决策：在 Phase B，同一 admitted page 的 primary body 只能来自一个 channel。**

- **决策：禁止 `native_text + "\n" + ocr_text` 作为 production merge。**

- 理由：直接拼接会造成重复页眉、重复正文、BM25 词频污染、
  embedding 内容重复、token budget 膨胀，
  以及 chunk boundary / chunk id 变化难以解释。

- 边界：该问题必须通过结构不变量消除，
  而不是靠实现者记住一条"不要拼接"的提醒。


### [L2] CASE R：`native_body_status == unusable` 的冻结语义

- **决策：**
  - remediation = `OCR_ATTEMPT`；
  - OCR body `usable` 后，OCR 是**唯一** primary body channel；
  - native unusable body 只留 audit，不进入 corpus；
  - metadata：native candidate 与 OCR candidate **都**进入独立 citation gate；
  - **不预设 metadata 来源**；
  - `citation_metadata_status != explicit_supported` → quarantine / review。

- provenance 至少记录：
  `body_source_channel`、`metadata_source_channel`、
  `native_metadata_candidate`、`ocr_metadata_candidate`、
  `metadata_conflict`、`ocr_artifact_sha256`。


### [L2] CASE S：`native_body_status == insufficient` 的冻结语义

- **决策：**
  - production action = **无条件** `OCR_ATTEMPT`；active-row / V2 不门控该动作；
  - OCR body `usable` 后，OCR 是 primary body channel；
  - native residual body **不与** OCR body 拼接；
  - metadata：native candidate 与 OCR candidate **都**进入独立 citation gate；
  - **不预设 native metadata 更可信**；
  - 允许 `body_source_channel != metadata_source_channel`；
  - candidate conflict → `uncertain`；
  - OCR recovered page 非 `explicit_supported` → quarantine / review。

- **边界：**"这些 insufficient 页的 native header 通常干净"
  **只是调查观察，不是 architecture invariant**，
  不得据此在实现中预设 metadata 取自 native。


### [L2] CASE A / class-3 scope：Phase B 只建状态与接口，不自动 augment

- owner_experiment: S5c / 后续 M5 或独立设计项

- 事实：A.2b confirmed 16 页 `VISUAL_KNOWLEDGE_MISSING`，跨 6 本手册；
  其中 2/28 unique gold citation pages 命中（ERM p.14、SMM p.38）；
  对应 4 条 gold citation 的 quote fragments 10/10 仍存在于当前 corpus。

- **决策：Phase B 不自动实现 class-3 OCR augmentation。**
  本轮只做三件事：建状态（`page_content_completeness_status`）、
  写 page-level audit、预留未来 `TextBlock(source_channel=...)` 接口。

- **决策：Phase B 不自动 OCR augment usable-native pages，
  不设计 native + OCR production merge，不为第三类重写 chunking。**

- **边界：本条不得被解读为"第三类 failure 不重要"或"对 M2 没影响"。**
  它作为 residual risk 保留：
  当前 corpus 无法回答只存在于视觉层的业务知识，
  full-corpus prevalence 仍未估计。


### [L2] V1 / V2 / active-row 的 production role

- **决策：V1 是 scoped native-body `unusable` detector**，
  作用域受语言条件限制（当前语料为 Latin-script 英文手册）；
  **不得外推为跨语言 universal detector**；作用域外返回 `uncertain`。

- **决策：V2 / active-row / active-column / ink / bbox 正式退出 production OCR gating，
  全部只作 diagnostic / audit signals。**

- 冻结 production rule：

  ```
  native_body_status == insufficient  →  OCR_ATTEMPT
  ```

  **不得写成** `insufficient + active-row trigger → OCR_ATTEMPT`。

- 理由：当前 insufficient population 只有 88 页；OCR 在岸端一次性执行并缓存；
  false negative 的代价是业务内容继续静默缺失；
  而 `STRUCTURE_CASE_1` 只在 66 POS / 7 NEG 的 Claude visual-review labels 上成立。

- **边界：`STRUCTURE_CASE_1 != production-proven detector`。**
  它证明的是 active-row 能解释当前 cover-vs-business-content 的 ink conflict，
  不证明阈值已 generalize，也不证明 false-positive 行为已被刻画。


### [L2] 审计信息进 `ingest/page_quality.jsonl`，不升级 Chunk contract

- owner_experiment: S5c / Phase B implementation

- **决策：Chunk schema 本轮不变；新增 `ingest/page_quality.jsonl`，每个 source page 恰一条。**

- canonical identity：`doc_id`、`source_filename`、`source_hash`、`pdf_page`。
  `source_hash` = immutable source PDF SHA256；OCR digest = `ocr_artifact_sha256`。
  **不得把同一个量同时保存为 `source_hash` 与 `source_pdf_sha256` 两个 persisted field。**

- page_quality 至少保存：
  `native_body_status`、`native_detector_reason`、
  `native_metadata_candidate`、`native_metadata_source_kind`、
  visual diagnostics（若计算；diagnostic only）、
  `ocr_attempted`、`ocr_artifact_sha256`、ocr cache identity（或等价身份串）、
  `ocr_engine`、`ocr_engine_version`、`ocr_params_digest`、`langpack_identity_digest`、
  `rasterizer`、`rasterizer_version`、`raster_dpi`、
  `ocr_body_status`、`ocr_metadata_candidate`、`ocr_metadata_source_kind`、
  `body_source_channel`、`metadata_source_channel`、
  `citation_metadata_status`、`metadata_conflict`、`metadata_reason_code`、
  `page_content_completeness_status`、`content_policy_status`、
  `remediation_action`、`chunk_ids`。

- `chunk_ids = []` 表示该页最终未进入 corpus。

- **决策（contract-change trigger）：若 implementation 中发现某个 runtime component
  必须依据这些 page-level quality fields 改变 runtime behavior：
  STOP → 单独的 contract decision → 不得顺手修改 Chunk。**


### [L1] page accounting invariant：每个 source page 必须有终态记录

- falsified_if:
  存在一个 source page 既不在 corpus 中，也没有 page_quality 终态记录。

- 事实：旧 parser 的 `continue` 使 88 页在无任何记录的情况下消失，
  其中 66 页经复核含业务视觉内容。

- **决策：1335 个 source page 必须每页在 `page_quality.jsonl` 恰有一条终态记录。**

- **决策：未进入 corpus 的页必须显式落入已定义的 remediation action
  （quarantine / skip_noncontent / OCR failure 或 degraded 处理等），并带 reason code。**

- 边界：本条是对"silent continue → 88 页无 chunk"这一失败模式的直接修复，
  不是新增的质量判断。


### [L1] 执行顺序冻结：S5c implementation → rebuild corpus → new corpus sha → S6

- owner_experiment: S5c → S6

- falsified_if:
  Phase B implementation 最终被证明不改变 chunk 集合、chunk text 与 corpus sha。

- 事实：Phase B 已冻结的设计至少会改变：
  chunk 数、chunk text、chunk length distribution、per-page ordinal、
  受影响页的 chunk identity、corpus sha。

- 事实：`GoldChunkMap` 的 identity 依赖 corpus / chunk identity。

- **决策：冻结顺序为 S5c / Phase B implementation → rebuild corpus → new corpus sha → S6 GoldChunkMap。
  S6 当前等待新 corpus。**

- 理由：现在在 `8c6bee0a…` / 3383 上生成 S6 artifact，
  会得到一个已知马上失效的 artifact。

- **边界：此前 DECISIONS 中的 R2 是"class-3 failure 是否使当前 gold 不可答"的窄义判断。
  R2 不等于"任何 corpus-changing parser remediation 都应推迟到 S6 之后"。**
  本条是 Design Freeze 之后新增的 ordering decision，
  按 append-only 原则追加，**不回改 R2 原条**。


### [L2] S5c rebuild 的 invalidation 边界

- **决策：S5c rebuild 后必须失效 / 重做：**
  `corpus/chunks.jsonl`、corpus sha、chunk count、chunk length distribution、
  受影响页的 ordinal 与 chunk ID、future `GoldChunkMap`、future `IndexManifest`、
  以及任何以旧 corpus sha 为 identity / key 的派生产物。

- **决策：必须在新 corpus 上复核：**
  `experiments/gate2_raw/_s4a9c_final_real_chunks.log`、
  `experiments/gate2_raw/_s4a9c_overbudget_attribution.log`、
  `experiments/gate2_raw/_s4a9c_none_observed_deepdive.log`，
  及它们基于 `8c6bee0a…` / 3383 得到的 budget / estimator-tail 结论。

- **边界：不得写成"所有 S4a.9 结果都作废"。**
  不受本次 corpus rebuild 直接影响的模型级证据包括：
  GATE-1、GATE-2、license evidence、CPU/GPU control、language smoke、model artifact digest。
  只有 corpus-dependent 部分必须在新 corpus 上复核。


### [L2] 更正：当前 executable budget contract 与 S4a.9 候选值必须分离

- 事实（本轮直接读取 `core/contracts.py` 求值）：
  - `MAX_PROMPT_TOKENS = 1050`
  - `PROMPT_OVERHEAD_RESERVE_TOKENS = 200`
  - `CONTEXT_PACK_MARGIN = 0.90`
  - `CONTEXT_PACK_BUDGET_TOKENS = 765`
  这四个值是**当前代码真实执行值**，即当前 executable contract。

- 事实：S4a.9 / 9c 讨论中的 `950 / 206 / 0.86 → 639` 属于
  实验测量结果、安全不等式候选与诊断预算状态。
  9a-bis 条目已写明 `206` "尚未冻结进 contracts"、`639` 为"provisional，不写入 contracts"；
  9c-final 条目中的 `MAX_PROMPT_TOKENS X = 950` 等是**该实验的冻结输入**，不是 contracts 取值。

- **更正：任何把 `950 / 206 / 0.86 / 639` 叙述或理解为"当前 contracts 已冻结值"的措辞，
  以本条为准更正为 experimental / candidate 值。**
  按 append-only，不修改上述历史条目。

- **决策：后续顺序为 S5c rebuild → 在新 corpus 上重跑 corpus-dependent 的 9c-final
  → 9d safety inequality / budget decision → 若证据支持，再独立 `contract:` commit。**

- **边界：本条不得被解读为"budget contract update 是 S6 的 blocker"。**
  S6 是否依赖 budget contract，必须在读取实际 `scripts/resolve_gold_chunks.py`
  与 S6 implementation 之后再判断。
  当前唯一已冻结的硬顺序是：S5c rebuild → new corpus → S6。


### [L3] 关于"950 的证据类型"的检查结果：未发现需要更正的历史措辞

- 事实：本轮检索 DECISIONS 全文，`950` 共 6 处命中，
  全部出现在派生算式（`B = int((950 - 206) × 0.86) = 639`、slack 核算）
  或 9c-final 的实验冻结输入清单中。

- 事实：未发现"benchmark / timing log 直接证明 950 PASS"一类措辞，
  也未发现把 `950` 当作原始测量字段的表述；
  历史条目已明确把由 pp512/1024/1200 反推的 prompt 上限定位为"候选筛选估算，不直接写入冻结契约"。

- **结论：无需追加"measurement != derived budget decision"的更正条目。**
  该区分本身仍然成立，并已由上一条（executable contract vs candidate）覆盖。


### Design Freeze provenance

- Design Freeze commit：`eed31a3`（design: freeze Phase B citation-safe OCR ingestion）
- Design Freeze file：`experiments/ocr_survey/_phase_b_design_freeze.md`
- Design Freeze sha256：
  `b840ae4590023dbc1ab796eb3ecdea6fc8d1e8292e13b29b5764d4947df896d1`
- baseline corpus at freeze：
  `8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa`，3383 chunks
- Design Freeze commit 已 push。
  **本日期块记录的是该已冻结设计，不是重新定义设计**；
  详细论证与 DF-01…DF-24 冻结表在该文件内，本条目不复制其全文。
