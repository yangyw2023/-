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


## 2026-09-24 · S5c Phase B ingestion 正式关闭与 canonical corpus 冻结

### [L1] frozen OCR input 的真正 identity

- 事实：`FROZEN_OCR_INPUT_SNAPSHOT` 的组成为
  external manifest = 1、accepted store index = 1、accepted artifact JSON = 140。
  当前派生 file count = 142。

- **决策：冻结的是 composition，不是总数。142 不是独立规范、不是魔法数字，
  它只是当前 snapshot composition 的派生值。**

- 事实（本轮更正）：上一轮的 hard gate 写成 `1 manifest + 140 artifacts = 141`，
  漏掉了 `ocr_cache/accepted/index.jsonl`。
  实测证明该 index 是当前 production recovery path 的 runtime lookup 入口：
  `OcrArtifactStore.__init__` → `accepted/index.jsonl` → `self._index`
  → `accepted_entry()` → `load_accepted()`。
  临时 store 对照：index + artifacts → load PASS；仅 artifacts、删除 index → `OcrArtifactError`。

- **决策：hard gate 应冻结它所守护的 composition / invariant，
  而不是脱离语义冻结一个总文件数。**

- **边界：若未来 accepted-store schema 增加必要文件，
  必须重新判断该文件是否属于 recoverable frozen input，
  不得只修改 expected total 去迁就 staged count。**


### [L2] `ocr_cache/accepted/index.jsonl` 的性质

- 事实：`ACCEPTED_INDEX_RUNTIME_REQUIRED = YES`。

- 事实：`INDEX_REGENERABILITY = BYTE_REGENERABLE`。
  仅从 140 个 accepted artifact JSON，按 production schema / sorting / serialization
  可逐字节重建 `index.jsonl`；reconstructed index 与真实 index 的 sha 同为 `8881893c859ee1fb…`。

- **决策：index 是 derived runtime index。它入 Git 的理由不是"包含不可再生信息"，
  而是 fresh clone 后 production `OcrArtifactStore` 无需额外 reconstruction step
  即可直接恢复 accepted store。**

- **边界："可再生"与"runtime 不需要"是两个判断，不得混为一谈。**


### [L1] OCR artifact durability 已关闭

- 事实：implementation commit = `4683f3264993b19f4d5a730d7674c76552645795`；
  OCR data commit = `25250146fddf54a9661082595ac877ee2fd1a7f8`。

- 事实：accepted artifact manifest =
  `experiments/ocr_survey/_phase_b_accepted_artifacts_manifest.jsonl`，
  sha256 = `c0e5b0371dc315b97d43e1d01d7049e5ee05493bdec3756c07765326efe07337`，
  accepted artifacts = 140。

- 事实（Git tree static validation）：`M_git == I_git == A_git`，rows = 140，
  140/140 artifact digest 重算匹配。

- 事实（Git-only dynamic recovery，store 由 Git tree 导出而非 working tree 复制）：
  target TACM p.60 → PASS；A\T CMM p.32 → PASS；A\T CMM p.112 → PASS；
  negative control（Git-only store 删除 index.jsonl）→ `OcrArtifactError`。

- **决策：`OCR_ARTIFACT_DURABILITY = DURABLE_IN_GIT`。
  fresh clone 可恢复构建 `c8978777…` corpus 所需的全部 frozen OCR input。**

- **边界：manifest 解决 identity / verification，Git-tracked artifact + index 解决 recovery。
  "能发现丢失"与"能够恢复"是两个不同能力，不得用前者代替后者。**


### [L1] artifact availability != policy selection != artifact consumption

- 事实（天然反例）：CMM p.32 与 CMM p.112 的 accepted artifact 存在、在 manifest 中、在 Git 中，
  但 `native_body_status = usable`、`ocr_attempted = false`、`ocr_body_status = not_attempted`、
  `body_source_channel = native`、terminal action = `ADMITTED_NATIVE`。

- 事实：T = 138、A = 140、C = 138；`T - C = {}`、`C - T = {}`、
  `A - C = {(CMM,32), (CMM,112)}`。

- **决策：artifact existence / availability 不得作为 OCR policy selection 的输入。
  accepted artifact 的存在本身不得推动页面进入 OCR path。**


### [L1] 三代 corpus identity 与 supersession

- `8c6bee0a…` / 3383 chunks —— role = S5 baseline，status = **SUPERSEDED**。

- `c154a67b264ce38c6c5a65d6e910a5dec2c090af2d3845e21c9db422418ded7b` / 3413 chunks
  —— role = S5c pre-QA intermediate，status = **SUPERSEDED**。

- `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb` / 3409 chunks
  —— role = S5c final，status = **CURRENT_CANONICAL**。

- canonical page_quality =
  `698428966639264203996f393ea4bc5a1fb03cf19ae1d050450eb6d6b41f7001` / 1335 rows。

- **决策：`corpus/chunks.jsonl` 当前 canonical path 已 promotion 到 `c8978777…` / 3409。
  任何后续 corpus-dependent measurement 必须使用该 identity，
  除非后续有新的正式 supersession 记录。**


### [L2] S5c final provenance chain

- 冻结生成链：source PDFs + implementation commit `4683f326…`
  + frozen OCR input data commit `25250146…` + manifest `c0e5b037…`
  + Design Freeze `b840ae45…` → canonical corpus `c8978777…` / 3409。

- 事实：committed-code independent rebuild A / B 的 chunks 与 page_quality 均逐字节一致。

- 事实：canonical-path verifier = PASS，failures = 0。

- 事实（page accounting）：`ADMITTED_NATIVE 1197` + `ADMITTED_OCR 53` + `QUARANTINED 81`
  + `SKIPPED_NONCONTENT 4` + `FAILED_INGEST 0` = 1335；
  chunk-bearing pages = admitted pages = 1250；UNKNOWN-section chunks = 0。

- **决策：S5c corpus identity 不再只绑定 parser code，
  它绑定 parser implementation + frozen OCR input identity。**


### [L3] 独立证据交叉验证：CRM p.3 / p.23 / p.67

- 事实：Phase A.2 的人工视觉 review 把 CRM p.3 / p.23 / p.67 标为 `mostly_header_footer`。

- 事实：S5c post-QA 的通用 OCR structural stripping rule 使同三页 raw OCR 非空、
  strip 后 body 为空 → `SKIPPED_NONCONTENT`。

- 事实：两条路径时间不同、方法不同、且没有使用页码 special case，却落到同一组三页。

- **决策：记为独立交叉验证证据。**

- **边界：不得反向把 Phase A 的人工标签写进 production rule。**


### [L2] OCR body failure reason 与 terminal action 分离

- 事实：CRM p.3 / p.23 / p.67 —— `ocr_body_status = failed`，
  `ocr_body_reason = ocr_body_empty_after_structural_strip`。

- 事实：TACM p.55 —— `ocr_body_status = failed`，`ocr_body_reason = ocr_text_empty_raw`。

- 事实：engine-failure 路径另有 `ocr_engine_failed_no_artifact`。

- **决策：status / reason / terminal action 是三个不同量。
  多个不同 reason 可以共享同一个 status，也可以导向同一个 terminal action。
  reason 不得编码进 terminal-action identity。**

- 事实：该约束由自动化回归测试保护，用于防止此前
  `ADMITTED_* + REQUIRE_REVIEW` 字符串拼接导致 admission predicate 静默失效的同类故障。


### [L2] SECTION_MAX_CHARS 的精确状态

- 事实：`SECTION_MAX_CHARS = 80`，production path 确实执行该 rule，
  当前触发 6 页：CRM p.75、CRM p.76、CRM p.77、TACM p.117、TACM p.118、TACM p.120。

- 事实（反事实实验）：去掉该 length rule 后，6/6 citation state 不变、6/6 terminal action 不变。
  原因是这些 candidate 同时为 `title_line_fallback` / `inherited`，
  `source_kind != explicit_label` 已独立足以把它们判为 `uncertain`。

- **决策：`SECTION_MAX_CHARS_RULE_STATUS =
  PRODUCTION_ACTIVE_BUT_OUTCOME_REDUNDANT_ON_CURRENT_CORPUS`。**

- **决策：`SECTION_MAX_CHARS_VALUE_SENSITIVITY =
  INSENSITIVE_WITHIN_CURRENT_CORPUS_INTERVAL_[56,85]`。**

- **边界：不得写"80 不承重"，也不得写"80 决定 CRM p.77 被隔离"。
  当前证据只支持：rule 在 production path 中 active，但对当前 corpus 的最终 outcome 是 redundant。
  [56,85] 仅为 current-corpus sensitivity interval，不外推未来文档；
  不宣称 80 optimal，不宣称 80 uniquely validated。**


### [L2] OCR broken-label residual

- 事实：18 / 53 OCR-admitted pages、756 residual chars、0 chunk-boundary changes。

- **决策：`OCR_BROKEN_LABEL_RESIDUAL = DEFERRED_RESIDUAL_RISK`。**

- 不修的理由（两层）：
  1. 当前量级低；
  2. 更重要的是，下一步需要 fuzzy matching damaged OCR labels，
     而当前不存在一个同时满足 deterministic、corpus-independent、doc/page-independent、
     且在 control 上证明不误删正文的机械规则。

- `falsified_if`：出现满足上述全部条件的确定性规则时，本 residual risk 重新打开。


### [L3] native isolated SECTION residual backlog

- 事实：CMM p.2–p.8，7 pages，49 chars。

- 根因：`pdftotext -layout` 在这些页把 SECTION label 与 value 拆成两行，
  现有结构判据没有将其作为完整 header row 剥离。

- **决策：`NATIVE_ISOLATED_SECTION_RESIDUAL = BACKLOG`。**

- **边界：existing native behavior；not S5c regression；new/old corpus behavior unchanged；
  outside OCR stripping prereg scope。不在 S5c 顺手修改。**


### [L1] 方法论：hard gate 本身也必须可被证伪

- 事实：本轮预设 hard gate 为 `1 manifest + 140 artifacts = 141`，实际 staged 为 142。

- 事实：处理方式既不是改 expected count 去迁就现实，也不是删除"多出来"的文件去迁就 hard gate，
  而是回到 hard gate 的目标——"fresh clone 是否能恢复 frozen OCR input？"——
  由代码追踪与负例实验发现 `accepted/index.jsonl` 是当前 runtime recovery path 的必要入口，
  正确 snapshot 为 manifest 1 + runtime index 1 + artifact payload 140。

- **决策：hard gate 是保护 invariant 的工具，不是事实本身。
  observation 与 hard gate 冲突时，不能自动假设 observation 错，
  必须先回到"这个 gate 在守什么"。**

- **决策：以后设计数量型 hard gate 时，优先冻结组成关系 / invariant，
  总数作为组成关系的派生值报告。组成关系发生合法变化时重新评估 gate，
  不把旧数字当不可质疑的真理。**


### [L1] S5c 正式关闭

- 事实：implementation commit `4683f326…` 已 push；OCR data commit `25250146…` 已 push；
  frozen OCR input 可由 fresh Git tree 恢复；
  canonical corpus 已 promotion 到 `c8978777…` / 3409；
  canonical page_quality = `69842896…` / 1335；canonical verifier = PASS；
  page accounting = CLOSED；deterministic rebuild = PASS。

- **决策：`S5C_STATUS = CLOSED`。**

- **决策：`NEW_CORPUS_READY_FOR_9C_FINAL = YES`。**

- **决策：`S6_UNLOCK_RECOMMENDATION = NO`** ——
  新 canonical corpus 上的 S4a.9c-final 尚未运行，之后的 contract decision 亦未完成。

- **决策（执行顺序冻结）：DECISIONS closure → 9c-final on `c8978777…` → contract decision
  → committed contract verification → S6。**


### [L2] 本轮不产生任何 budget contract 结论

- 事实：本轮未修改 `core/contracts.py`，
  未重新解释 `MAX_PROMPT_TOKENS` / `PROMPT_OVERHEAD_RESERVE_TOKENS` /
  `CONTEXT_PACK_MARGIN` / `CONTEXT_PACK_BUDGET_TOKENS` / `CHARS_PER_TOKEN_EST`。

- 事实：9c-final 尚未运行，因此当前 executable contracts 保持原值。

- **边界：历史 experimental / candidate values 不得称为 executable contract。**


## 2026-09-25 · S4a.9c-final measurement 冻结、contract architecture review 与 S6 并行化

### [L1] evidence taxonomy 纪律

- **决策：本日期块起，任何作为 decision evidence 的数字必须标注
  `MEASURED` / `ESTIMATOR_OUTPUT` / `DERIVED` / `NOT_VERIFIED` 四类之一，不得新增第五类。**
  每个关键数字必须能指向 source artifact + locator（必要时附计算式）。

- **决策：任何在对话 / DECISIONS / 文档中反复出现并承担推导作用的数字，
  必须能机械指回原始 evidence artifact。找不到即 `NOT_VERIFIED`，
  并立即停止作为事实参与任何推导。**

### [L1] 更正：`306 tokens/chunk` 从未被测量

- 事实（机械搜索）："306" 作为 per-chunk token 数只定位到
  `experiments/gate2_raw/_s4a9a_bis_context_framing.log:20`
  （`provisional k_est = 639 // 306 = 2`）与 `:27`
  （`k_est 按 306 tok/chunk 估算，而 CHARS_PER_TOKEN_EST=4 尚未校准`）。
  该 artifact 自述为估算；**不存在任何 measurement artifact 证明
  actual median chunk token count = 306**。

- **决策：`306_EVIDENCE_STATUS = NOT_VERIFIED`。
  不得继续用于 actual chunk-size statement、realized-k inference、
  F/c sensitivity、packing budget 或 contract numeric decision。**

- 正式区分四个 median：
  - old actual chunk-token median = **188** · `MEASURED` ·
    `_s4a9c_final_real_chunks.log:21` · superseded corpus `8c6bee0a…` / 3383
  - new actual chunk-token median = **189** · `MEASURED` ·
    `_s4a9c_final_canonical_chunks.csv` · canonical corpus `c8978777…` / 3409
  - new est_tokens median = **274** · `ESTIMATOR_OUTPUT` · 同 CSV
  - new actual rendered-token median = **199** · `MEASURED` · 同 CSV

- **边界：本条不否定旧 measurement 本身，只撤销所有以
  "306 是 measured chunk token statistic" 为前提的推导。**

### [L1] canonical 9c-final measurement 已冻结并单独入库

- 事实：measurement commit = `657387461e64abda3c393182092877deaed338a8`
  （`experiment: measure canonical corpus token packing`，9 文件，已 push，在 HEAD ancestry）。

- 事实：canonical corpus = `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb` / 3409；
  canonical page_quality = `698428966639264203996f393ea4bc5a1fb03cf19ae1d050450eb6d6b41f7001` / 1335；
  accepted artifact manifest = `c0e5b0371dc315b97d43e1d01d7049e5ee05493bdec3756c07765326efe07337`。

- 事实：Run 1 / Run 2 的 input identity 逐项一致，六个 deterministic output 逐字节一致
  → `RUN_REPEATABILITY_STATUS = DETERMINISTIC_MEASUREMENT_PASS`。

- **决策：measurement 是 evidence，contract update 是 decision，
  二者必须处于不同 commit / 不同轮次。本轮 measurement 已单独 commit，未夹带任何 contract 变更。**

### [L2] 更正：`est_over_but_actual_safe = 0` 是结构必然，不是经验证据

- 事实（`core/contracts.py` `pack_context()` prefix 语义）：
  `for hit in hits[:max_chunks]: t = hit.chunk.est_prompt_tokens();
  if packed and used + t > max_tokens: break; packed.append(hit); used += t`。
  注意 `packed and` 守卫 —— 首块无条件入选，故 `sum(est) <= max_tokens` 并非无条件成立。

- 事实（`MEASURED`，canonical chunks CSV）：current corpus `max est_prompt_tokens = 392`；
  `est_prompt_tokens > 765` 与 `> 639` 的 chunk 数均为 **0** → 首块例外不可能触发。
  `DERIVED`：CURRENT `200 + 765 = 965 <= 1050`；HISTORICAL CANDIDATE `206 + 639 = 845 <= 950`。

- **决策：`EST_OVER_BUT_ACTUAL_SAFE_STATUS =
  STRUCTURALLY_ZERO_ON_CURRENT_CORPUS_AND_PROTOCOL`。
  `est_over_but_actual_safe = 0` 不得作为 estimator quality 的 empirical evidence。**

- **决策：`est_safe_but_actual_over` 仍有 empirical information。
  CURRENT executable scenario = 35 / 3405 windows（`MEASURED`），
  含义是「packer 依据 estimator 判为安全并已 admit 的 context 中，
  有 35 个实际 rendered token cost 超出真实 prompt budget」。
  两个方向的计数不得对称解释。**

### [L2] estimator failure shape（canonical，`MEASURED`）

- text actual/estimated：p50 = 0.7784 · p95 = 1.087 · p99 = 1.455 · max = 2.0000
- rendered actual/estimated：p50 = 0.7755 · p95 = 1.049 · p99 = 1.372 · max = 1.664
- dangerous tail：text > 1.15 = **129 / 3409**；rendered > 1.15 = **110 / 3409**
- 方向约定：`ratio = actual / estimated`；> 1 = estimator 低估 = 危险侧；< 1 = 保守。

- **边界：中位行为保守不得推出 tail behavior 安全。**

### [L3] dangerous tail 的文档富集：只是 observation

- 固定 population：text actual/estimated > 1.15，T = 129；N = 3409。
  enrichment = (tail_share) / (corpus_share)，全部文档如下（`MEASURED` + `DERIVED` 比值）：

  | doc_id | corpus_chunks | corpus_share | tail_chunks | tail_share | enrichment |
  |---|---|---|---|---|---|
  | CMM | 391 | 0.1147 | 14 | 0.1085 | 0.946 |
  | CRM | 256 | 0.0751 | 4 | 0.0310 | 0.413 |
  | EMM | 344 | 0.1009 | 2 | 0.0155 | 0.154 |
  | ERM | 377 | 0.1106 | 7 | 0.0543 | 0.491 |
  | FMM | 883 | 0.2590 | 59 | 0.4574 | 1.766 |
  | NPM | 286 | 0.0839 | 2 | 0.0155 | 0.185 |
  | QMM | 423 | 0.1241 | 6 | 0.0465 | 0.375 |
  | SMM | 304 | 0.0892 | 1 | 0.0078 | 0.087 |
  | TACM | 145 | 0.0425 | 34 | 0.2636 | **6.197** |

- 只允许陈述：**TACM 与 FMM 在观察到的 dangerous tail 中富集（TACM 6.20×，FMM 1.77×）。**
  不得写"因为表格多 / layout 特殊 / 是 estimator failure 的原因 / 应按 document 建 estimator"。

- **决策：`DANGEROUS_TAIL_DOC_ENRICHMENT = OBSERVATION_ONLY`。**

- **边界：该结果意味着 "native vs OCR" 未必是唯一或正确的 conditioning variable ——
  富集最强的 TACM 只有 3 个 OCR chunk，文档维度的解释力独立于 channel 维度。**

### [L2] native vs OCR：candidate 支持，architecture 未证明

- `MEASURED`：native n=3333 · ratio p50 = 0.7748 · p95 = 1.0546 · max = 1.7333 · >1.15 = 117
- `MEASURED`：OCR n=76 · ratio p50 = 0.9258 · p95 = 1.2193 · max = 2.0000 · >1.15 = 12
- `PER_CHANNEL_ESTIMATOR_CANDIDATE_SUPPORTED = YES`
- **`PER_CHANNEL_ESTIMATOR_ARCHITECTURE_PROVEN = NO`**

- 未排除的 alternative explanations（至少）：whitespace density（OCR p50 = 0.1696 vs
  native 0.2766，`MEASURED`）、document composition（见上表）、chunk length、chunk ordinal、
  punctuation density、table-like text、OCR spacing artifacts。

- **决策：不得冻结 conditioned estimator。**

### [L2] OPTION_C = tokenizer-specific exact-cost artifact：C1 与 C2 必须分开

- **C1（exact token count 写入 Chunk schema）**：corpus schema 与 tokenizer 耦合；
  corpus identity 与 tokenizer/model identity 绑定；换 tokenizer/model 可能要求 corpus rebuild；
  GoldChunkMap 等 corpus-keyed identity 的 invalidation 需重新评估。

- **C2（独立 sidecar artifact）**：identity =
  `(corpus_sha256, tokenizer_identity_digest, counting_protocol_digest)`。
  corpus 保持 tokenizer/model independent；换 tokenizer → 只重建 sidecar，不重建 corpus；
  换 corpus → sidecar 必然 invalid；船端只消费 frozen integer cost，不安装 tokenizer runtime。

- 事实：canonical measurement chunks CSV 已构成 3409 行的 C2 原型 ——
  deterministic、双跑逐字节一致、tokenizer identity 已知、corpus identity 已知、counting protocol 已知。
  → **`OPTION_C2_PROTOTYPE_EVIDENCE = AVAILABLE`**

- **决策：`OPTION_C_SELECTED = NO`。本轮不修改 Chunk schema / IndexManifest / packing implementation。**

### [L2] citation header 的双向误差

- `ESTIMATOR_OUTPUT`：`CITATION_HEADER_EST_TOKENS = 14`
- `MEASURED`（canonical chunks CSV）：actual header increment p50 = 10 · p95 = 13 ·
  p99 = 16 · max = 28；> 14 的 chunk = **106 / 3409**

- **边界：14 同时是绝大多数 chunk 上的 conservative overestimate 与少数 chunk 上的 underestimate。
  本轮不选择新的 header constant。若未来采用 exact rendered-cost sidecar，
  该双向误差可由 per-chunk exact rendered cost 取代。**

### [L3] separator 不确定性关闭（scope 受限）

- `MEASURED`：SEP `"\n"` 与 `"\n\n"` 的真实相邻 rendered chunk 增量成本
  **max = 1 token**（n = 3408，两候选一致）。
- **决策：`SEPARATOR_UNCERTAINTY_STATUS = CLOSED`，scope =
  current tokenizer identity + current renderer + 已测 SEP 候选。不外推到未来 tokenizer / renderer。**

### [L1] token budget 的校准目标设备

- 事实（机械恢复自既有规范记录）：`DECISIONS.md:391–392` —— 船端 x86 无 Accelerate、
  无 Apple 统一内存带宽，M0（2026-08-17）估算 x86 CPU 为 35–85 t/s；
  `core/contracts.py:207` —— 船端 CPU 会放大数倍；
  `core/contracts.py` `TTFT_BUDGET_S = 10.0`（owner_experiment: M6）。

- **决策：`TOKEN_BUDGET_CALIBRATION_TARGET_DEVICE = VESSEL_X86_CPU_NO_GPU`。**

- **决策：`PRODUCTION_GPU_PREFILL_MEASUREMENT_REQUIRED = NO`。**
  **更正：上一轮 architecture review 曾把「phi4-mini GPU prefill 实测」列为待补测量，
  该建议基于开发机的运行形态而非项目的目标设备约束，按本条收回。**

- **边界：development Mac CPU-only benchmark != vessel x86 CPU benchmark；
  development GPU benchmark != vessel production benchmark。**

### [L2] overbudget 的后果必须分三层记录

- `MEASURED`：CURRENT executable scenario overbudget = 35 / 3405 = 1.03%，max overage = **+338 tokens**。
- `MEASURED`：HISTORICAL candidate（NOT EXECUTABLE CONTRACT）overbudget = 19 / 3405 = 0.56%，
  max overage = **+203 tokens**。
- `MEASURED` / `DEVELOPMENT_MACHINE_CPU_ONLY`：phi4-mini prefill ≈ 94.60–97.33 t/s
  （`_s4a9b_ttft_fine.log:42–46`、`_s4a9b_ttft_sweep.log:42–46`；`_runtime.txt` 记录 `bench_args=-ngl 0 -t 8`）。
- `DERIVED`（公式 `Δt = Δtokens / rate`，仅开发机 CPU-only 口径）：
  338 / 94.60 ≈ 3.57 s；338 / 96.70 ≈ 3.50 s；203 / 94.60 ≈ 2.15 s；203 / 96.70 ≈ 2.10 s。

- **决策：`VESSEL_TTFT_CONSEQUENCE = NOT_VERIFIED`。**
  只能写"在开发机 CPU-only evidence 下，+338-token max overage 对应约 +3.5 s；
  该换算不外推到船端 x86 CPU"，**不得写"生产请求会多等约 3.5 秒"**。

### [L2] 历史船端性能估计的边界

- 事实：`DECISIONS.md:392` 的 x86 CPU 35–85 t/s 自述为 **M0 估算**
  → `evidence_type = DERIVED / ESTIMATE`，**不得升级为 MEASURED**。
- `DERIVED`：`1050 / 85 ≈ 12.35 s`；`1050 / 35 = 30.0 s`，对照 `TTFT_BUDGET_S = 10.0`。
- **只允许记录：历史船端性能估计与当前 10 s prompt budget 之间存在待真实硬件验证的 tension。
  不得写"船端实际 TTFT 是 12–30 秒"。**
- **决策：`VESSEL_X86_PREFILL_MEASUREMENT_REQUIRED = YES`，owner = M6 / real target hardware calibration。
  若目标船端硬件在 M6 前不可用，`NUMERIC_LATENCY_CONTRACT_FINALIZATION` 必须保持 provisional。**

### [L1] S6 依赖与 invalidation 审计闭合

- 事实（`scripts/resolve_gold_chunks.py` AST 审计，imports 仅
  `argparse, csv, json, re, sys, typing`）：
  - `DIRECT_DEPENDENCY`：`corpus/chunks.jsonl`、corpus identity、`chunk.id`、`doc_id`、
    `pdf_page`、`section`、`text`、quote matching、testset citations
  - `NOT_DEPENDENCY`：`CHARS_PER_TOKEN_EST`、`CONTEXT_PACK_MARGIN`、
    `CONTEXT_PACK_BUDGET_TOKENS`、`MAX_PROMPT_TOKENS`、`CITATION_HEADER_EST_TOKENS`、
    `TOP_K_CONTEXT`、`pack_context`、tokenizer、retriever、renderer、scorer、`core.contracts`

- **决策：`TOKEN_BUDGET_CHANGE_INVALIDATES_GOLD_CHUNK_MAP = NO`**，
  条件为 corpus / chunk identity / text / doc / page 保持不变。

- **决策：`S6_BLOCKED_BY_CONTRACT_DECISION = NO`；
  `S6_CAN_PROCEED_IN_PARALLEL_WITH_CONTRACT_DECISION = YES`。**
  并行成立需同时满足两条，本轮均已机械证明：
  (1) S6 不依赖 token-budget contract；(2) token-budget-only 变更不 invalidate GoldChunkMap。

- **边界：若未来 Contract Decision 改动 chunking / corpus text / chunk IDs / doc-page identity，
  必须重新评估 GoldChunkMap invalidation。**

### [L1] ordering narrowing：token-contract line 与 S6 line 在 canonical freeze 后分叉

- 旧 ordering（不回改）：S5c → rebuild → canonical corpus → token-budget decision → S6。

- 当前机械 evidence：S5c = CLOSED；canonical corpus = `c8978777…` / 3409；
  S6 dependency audit 显示 token-budget contract 非依赖；
  invalidation audit 显示 token-budget-only change 不 invalidate GoldChunkMap。

- **决策：自 canonical freeze 起正式分叉 ——**

      canonical S5c corpus ──┬─ S6 / GoldChunkMap
                             └─ token-contract line

  token-contract line = architecture review → real retrieval evidence →
  vessel hardware calibration（可用时）→ Contract Decision → optional implementation →
  numeric contract freeze。
  **S6 不再等待 token numeric decision。**

### [L1] 方法论：结论不得因为"更保守"就超过证据支持的范围

- 事实：本项目已多次出现 append-only narrowing ——
  implementation-before-S6 的前置关系后被细化；
  "native body usable/clean" 不能推出 "metadata correct"；
  本轮 "S6 被 token-budget Contract Decision 阻塞" 的 ordering
  经 code dependency + invalidation audit 后被收窄。

- 共同形状：当时为了"安全"，把结论 / dependency / blocker 写得比 evidence 更宽。

- 后果：不一定造成 correctness failure，但会制造不必要串行、延迟后续阶段、
  重复 measurement / review，并把本来独立的问题错误地绑在一起。

- **决策："保守"不是扩大结论范围的许可证。一个 blocker / dependency 必须能回答：
  (1) 下游实际读取了什么？(2) 上游变化是否真的 invalidate 下游 artifact？
  两者都不能机械证明时，不得把"为了安全"升级为 hard dependency。**

- **边界：该纪律与"证据不足却下太强的因果/字段结论"互补 ——
  前者防止结论过强，本条防止 blocker 过宽。两者共同要求：
  conclusion strength == evidence strength，不多也不少。**

### [L2] contract line 的 readiness

- **决策：`CONTRACT_ARCHITECTURE_DECISION_READY = YES`；
  `NUMERIC_CONTRACT_DECISION_READY = NO`。**

- 仍需：
  - **A. `REAL_RETRIEVAL_WINDOW_MEASUREMENT_REQUIRED = YES`** ——
    判断 sequential-window simulation 的 realized k、overbudget rate、tail shape
    是否代表 production retrieval。
  - **B. `VESSEL_X86_PREFILL_MEASUREMENT_REQUIRED = YES`** ——
    owner = M6 / target hardware calibration；用于校准真正的 vessel TTFT / prompt budget。
    **不是 GPU measurement。**
  - **C. `PER_CHANNEL_MEASUREMENT_REQUIRED = CONDITIONAL`** ——
    仅当下一轮仍认真考虑 Option B conditioned estimator 时才需要；**不得因此阻塞 S6。**

## 2026-09-25 · S6 contract clarification：GoldChunkMap evidence-cover semantics and deterministic identity

证据标记沿用本日期块起的纪律：`CONTRACT_FACT` / `CODE_FACT` / `MEASURED` / `DERIVED` / `NOT_VERIFIED`。
作用域：corpus `c8978777…` / 3409 chunks；testset `eval/testset_v5_3.jsonl` `05614407…` / 39 题；
`core/contracts.py` 修改前 sha256 = `7ed2399b3d34aaba0bd672655f5f104ff3b77756ebabc9ff534efa5ca7cecd9b`。

### [L1] legacy backfill architecture 已被契约否决；resolver 顶层重写

- 事实（`CODE_FACT`）：`scripts/resolve_gold_chunks.py:86/:228` 要求 `gold_chunk_ids`，`:326` 回写 question，
  `:330-341` 输出 resolved testset，`:272/:276` 按整条 quote 字面匹配（不调用 `split_quote_fragments`）。
  `MEASURED`：旧 `load_questions(eval/testset_v5_3.jsonl)` 抛 `missing required field(s): gold_chunk_ids`。
- 契约（`CONTRACT_FACT`）：`gold_chunk_ids` 是派生产物、不进评测集（S3，见本文件 `:93-101`、`:160-165`）。
- **决策：`LEGACY_BACKFILL_ARCHITECTURE = REJECTED_BY_CURRENT_CONTRACT`；
  `LEGACY_RESOLVER_TOP_LEVEL_STATUS = TOP_LEVEL_REWRITE_REQUIRED`。
  不在旧 backfill 架构上打补丁；`write_resolved_testset` / `fill_gold_chunk_ids` 删除；
  `TESTSET_MUTATION_ALLOWED = NO`。** 本条是既有契约冲突的记录，不是新架构决策。

### [L1] formal gold = 唯一最小基数 citation evidence cover，只看 citation 所在页

- falsified_if: 出现人工核验过的 citation，其证据确实位于 citation 页上某组 chunk，
  而"唯一最小基数 full cover"给出了错误集合或错误地判为 AMBIGUOUS；或 chunker 开始产出跨页 chunk。
- 定义（已写入 `core/contracts.py` 的 `MatchLevel` / `GoldChunkMap`）：
  `C(P)` = citation (doc_id, pdf_page) 页上的全部 chunk；片段 = `split_quote_fragments(quote)`（含短片段）；
  `cand(f)` = C(P) 中 `normalize_text(text)` 含 f 的 chunk；full cover = 与每个 cand(f) 都相交的 S ⊆ C(P)。
  - **L1** 最小基数 full cover 唯一且 |cover|=1 → 进 mapping
  - **L2** 最小基数 full cover 唯一且 |cover|≥2 → 进 mapping
  - **AMBIGUOUS** 有 full cover 但最小基数 cover 不唯一 → 不进 mapping，needs_review
  - **L3** 无 full cover，且至少一个 `is_sole_match_eligible` 片段有 candidate → 部分证据，不进 mapping
  - **L4** C(P) 非空、无 full cover、无可进 L3 的 eligible 命中（含只命中短片段）→ 不进 mapping
  - **FAIL** C(P) 为空 → 不进 mapping
- **决策：`GOLD_PAGE_SCOPE = EXACT_CITATION_PAGE_ONLY`，无邻页 fallback。**
  依据：chunk 按页构建（`CODE_FACT` phase_b_ingest.py:259-272）；本页 94/94 片段命中，
  而 ±1 会额外引入 PR01#0 fragment 4 → `ERM:p104:2`（`MEASURED`），那不是 gold 证据。
- **决策：最小 cover 不唯一一律 AMBIGUOUS。禁止按 chunk id / corpus 顺序 / 片段顺序任取，
  禁止取并列 cover 的并集。** corpus 顺序只用于确定性枚举与序列化，不参与消歧。
- **更正（相对上一轮提案）：不采用 FORCED_COVER（单候选片段载体之并）作为一般契约。**
  反例 A→{X,Y}、B→{Y,Z}：FORCED_COVER 给 AMBIGUOUS，但 {Y} 是唯一最小基数 full cover。
  FORCED_COVER 与最小 cover 在当前 38 条上结果一致（`MEASURED`），那只是数据上的巧合，不是定义。
- **决策：短片段仍参与 full evidence cover；`QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH`
  只影响 L3/L4 分界，不得用于从完整证据中删除片段。**
  依据：删短片段（MF-B）会删掉 FL07 的 `QMM:p32:4`（`(For TANKERS only)` / `should be Zero` 的唯一载体）
  与 ML02 的 `QMM:p33:0`（`For Dry Vessels` 的唯一载体）（`MEASURED`）。
- **决策：section 不是匹配前置条件，只用于审计**（`MEASURED`：3/38 条为表示差异，如 `Chapter 15` vs `15`）。

### [L1] L3 / L4 / AMBIGUOUS / FAIL 不贡献 mapping；GoldChunkMap fail-closed（K3-C）

- falsified_if: mapping 获得能显式标注"不完整 gold"的结构，或引入经契约定义的人工裁决通道。
- 依据（`CONTRACT_FACT`）：mapping 不带级别（`GoldChunkMap` docstring），又是 Recall 的唯一依据。
  "该页有 chunk 但不知道哪个承载证据"推不出"这些 chunk 都是 gold"；部分证据也不是完整 gold。
- **决策：可答题的每一条 citation 都必须解析为 L1/L2，映射才被接受；否则只写 report.csv、
  不产出被接受的 map JSON、非零退出。禁止 `mapping[qid] = []`、禁止省略未解析的 answer qid、
  禁止把部分 citation 的并集当完整 gold。** 可执行形式：`validate_gold_chunk_map()`。
- 拒答题 qid 不进 mapping 是正常语义，与"answer 题未解析"是两种状态；后者只能表现为映射不被接受。

### [M] GoldChunkMap 确定性：删除 `built_at`

- why_not_falsifiable: GoldChunkMap 不进 Git，逐字节可再生是它存在方式的前提；
  `EvalItemResult.gold_chunk_map_sha256` 记录其字节哈希。这是方法要求，不是关于系统的经验主张。
- **决策：删除 `GoldChunkMap.built_at`；运行时间只打到 stdout / log；落盘文本唯一由
  `serialize_gold_chunk_map()` 生成。**

### [L3] GoldChunkMap identity 字段

- **`parser_name` → `corpus_builder_name`**，`filename()` 中 `__parser-` → `__builder-`，新增 `report_filename()`。
  依据（`CODE_FACT`）：canonical 语料由 `ingest/build_corpus.py` → `phase_b_ingest._build_chunks`
  → `kaiva_pdf.split_body_to_texts` + OCR 路径生成，不是 `KaivaPdfParser.parse()`。
  语义：生成该冻结语料的语料构建语义实现族，不是某个 class 名。
  **待办（resolver rewrite 前置）：权威 builder identity 常量当前不存在，须由语料构建实现提供；
  本轮不创建，resolver 不得手写。**
- **testset_version**：`testset_version_from_path()`，`testset_v<MAJOR>_<MINOR>.jsonl` → `v<MAJOR>.<MINOR>`，
  不符合即 `ContractViolation`。
- **chunker_config** = `chunker_config_identity()` =
  `chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350`。
  `CODE_FACT`：分块代码读取 `CHUNK_TARGET_TOKENS` / `CHARS_PER_TOKEN_EST` / `CHUNK_MIN_CHARS`；
  `CHUNK_OVERLAP_TOKENS` 在 components/ 与 ingest/ 中零引用；
  `MEASURED`：2159 对同页相邻 chunk 中仅 29 对共享 60 字符尾部，无系统性 overlap。
  **不得再写 `target350_overlap60_min120`。**
- **corpus sha**：resolver 自算完整 SHA-256；`--corpus-sha` 为必填断言（8 位前缀或 64 位全长），
  不匹配硬失败；map 只写计算值。
- **report.csv 列冻结**为 `GOLD_CHUNK_MAP_REPORT_COLUMNS`（13 列，含 `fragment_matches_json`）；
  citation_index 0-based，pdf_page 1-based；chunk id 一律按 corpus 顺序。

### [L2] Recall 一题多 gold 的命中规则：下游契约缺口

- owner_experiment: M1c / S8
- **决策：`RECALL_MULTI_GOLD_SEMANTICS = DOWNSTREAM_CONTRACT_GAP`，本轮不冻结 ANY / ALL / coverage。**
  GoldChunkMap 只回答"哪些 chunk 构成 formal gold 证据"。不阻塞映射生成。

### [L3] 当前语料测量（current-corpus measurement，不是契约定义）

- `MEASURED`（corpus `c8978777…`、testset `05614407…`，按上述定义）：
  38 条 citation / 94 片段，94/94 在 citation 页命中；MF-1 = 12 / MF-2 = 8 / MF-3 = 0；
  **L1 = 30 / L2 = 8 / AMBIGUOUS = 0 / L3 = 0 / L4 = 0 / FAIL = 0；formal associations = 47**；
  最小 cover 并列 = 0；多个完整覆盖 = 0。
- 这些数字随语料变化，不参与定义。**契约不因当前 AMBIGUOUS/L3/L4/FAIL 为 0 而省略这些状态。**
- **决策：真实数据未覆盖 AMBIGUOUS / L3 / L4 / FAIL，合成向量 `GOLD_RESOLUTION_VECTORS`
  （`tests/test_contracts_gold_chunk_map.py`，T1–T9）是验收要求；下一轮 resolver 必须对同一组向量
  给出相同的 (level, formal)。** 变异检查：把参考解析改成 FORCED_COVER 时 T3 失败，
  改成丢弃短片段时 T8 失败（`MEASURED`）。

### [L1] CONTRACTS_VERSION 0.2.0 → 0.3.0 与 invalidation 审计

- 改动：MatchLevel 语义、GoldChunkMap schema（删除 built_at、parser_name → corpus_builder_name）、
  gold 解析语义、确定性 identity。GoldChunkMap / IndexManifest / EvalItemResult 均尚未生成，迁移成本近零。
- 未改动：Chunk / Citation / EvalItem / EvalItemResult / IndexManifest / 全部数值常量。
- invalidation 判据：artifact 是否消费本次改变的 GoldChunkMap / MatchLevel / identity 语义，
  **不是**"是否出现 0.2.0"。

  | artifact | 记录 contracts 版本? | 消费改变的语义? | 被 0.3.0 invalidate? |
  |---|---|---|---|
  | corpus/chunks.jsonl | NO（13 个 Chunk 字段） | NO（Chunk 与分块常量未变） | NO |
  | ingest/page_quality.jsonl | NO | NO | NO |
  | ocr_cache/accepted（140 个 artifact + index.jsonl） | NO（`schema_version` 是 OCR artifact schema） | NO | NO |
  | S4a.9c-final 产物 | NO（日志无版本、无 contracts.py sha） | NO（只读 Chunk 与数值常量） | **NOT_INVALIDATED_BY_0.3.0** |
  | eval/testset_v5_3.jsonl | NO | NO（EvalItem 未变） | NO |
  | eval/results.csv（仅表头） | NO | NO（表头仍等于 RESULTS_COLUMNS） | NO |
  | Phase B Design Freeze | NO | NO（只把 GoldChunkMap 当未来产物） | NO |
  | parser_audit `_citation_section_audit.log` | 记录 contracts.py 文件 sha `7ed2399b…` | NO | NO（只是 provenance 旧值） |

- 待办：按 `core/contracts.py` 仪式，本改动单独一个以 `contract:` 开头的 commit（由人工执行）。
  本改动由 Arya 裁决，Claude Code 按裁决落地；`core/contracts.py` 头部"不交给 AI 修改"与本轮授权之间的冲突已在会话中报告。

## 2026-09-28 · S6 contract diff review closeout：契约治理收窄、invalidation 收窄、权威语料构建身份

### [L1] HUMAN_CONTRACT_AUTHORITY_DECISION = SEMANTIC_AUTHORITY_HUMAN / MECHANICAL_APPLICATION_ALLOWED

- falsified_if: 出现 AI 机械落地时混入了未经人工裁决的语义选择、且现有审核流程未能拦下的实例。
- **决策（Arya 裁决）：原"`core/contracts.py` 绝对不交给 AI 生成或修改"收窄为：
  契约语义只能由人裁决。AI 不得自行决定是否改契约、改什么语义、选哪个选项，
  也不得根据实验结果顺手修改可执行契约。在专门的契约轮次中，若人已逐项给出
  语义裁决 / 允许的 diff 范围 / 必须的不变量 / 验收测试 / commit 边界，AI 可以机械落地。**
- 约束：独立 `contract:` commit，且必须真实包含 `core/contracts.py`；commit 前由人审核完整 diff；
  不得混入未裁决的语义选择；发现新的语义缺口必须停下，交回人工裁决。
- 这条纪律保护的是 **human semantic authority**，不是 human keystrokes。
- 性质认定：上一条目（2026-09-25 S6 contract clarification）对应的 `core/contracts.py` diff 为
  **AI_MECHANICAL_APPLICATION_OF_EXPLICIT_HUMAN_CONTRACT_DECISIONS**，不是自主的契约决策。
- 同步修改的治理措辞（仅这两处）：`core/contracts.py` 文件头
  "本文件【绝对不交给 AI 生成或修改】…"一行；`CLAUDE.md`"绝对不要碰的东西"表中 `core/contracts.py` 一行。

### [L1] S6 invalidation 收窄：packing-only 与 chunk-construction 分开

- 事实（`CODE_FACT`，canonical 构建路径 `ingest/build_corpus.py:145` → `phase_b_ingest.process_page`
  → `_build_chunks`（`phase_b_ingest.py:259-264`）→ `kaiva_pdf.split_body_to_texts`（`:660-662`）→ `_split_page_body`）：

  | 常量 | 定义处 | canonical chunker 消费? | 代码位置 | 可改变 chunk 边界? |
  |---|---|---|---|---|
  | `CHARS_PER_TOKEN_EST` | contracts.py | YES | `kaiva_pdf.py:469`（`_est_tokens` = len // 本值）→ `:494/:499/:516` 与目标比较 | YES |
  | `CHUNK_TARGET_TOKENS` | contracts.py | YES | `kaiva_pdf.py:494/:499/:516` | YES |
  | `CHUNK_MIN_CHARS` | contracts.py | YES | `kaiva_pdf.py:539/:543`（合并短块）；`phase_b_ingest.py:226/:234/:243`、`page_states.py:109/:149/:178`（页准入） | YES |
  | `CHUNK_OVERLAP_TOKENS` | contracts.py | **NO** | components/ 与 ingest/ 零引用 | NO |

- `MEASURED`（进程内 monkeypatch 契约常量，在 canonical 页文本上重跑 `split_body_to_texts`；未改任何文件）：
  `CHARS_PER_TOKEN_EST` 取 3 / 5 → 1053 / 792 页（共 1250 页）的切分改变，chunk 数 4677 / 2722；
  `CHUNK_TARGET_TOKENS` 取 300 / 400 → 925 / 623 页；`CHUNK_MIN_CHARS` 取 100 / 200 → 13 / 85 页；
  `CHUNK_OVERLAP_TOKENS` 取 0 / 200 → 0 页。
  效度边界：页正文由 canonical chunk 以 `"\n\n"` 重新拼接近似，当前常量下复现 1068/1250 页
  （3277 vs 3409 chunk）。它证明"能改变边界"，不给出精确幅度。

- **决策：**
  - **PACKING_ONLY_CONTRACT_CHANGE**：只影响 prompt/context packing、运行时预算、渲染余量，
    且经 `CODE_FACT` 确认不参与 canonical corpus 构建的参数（如 `MAX_PROMPT_TOKENS`、`CONTEXT_PACK_MARGIN`、
    `PROMPT_OVERHEAD_RESERVE_TOKENS`、`CITATION_HEADER_EST_TOKENS`、`TOP_K_CONTEXT`）。
    这类变化**不改变 corpus identity**，**不会仅因此 invalidate GoldChunkMap**。
  - **CHUNK_CONSTRUCTION_CONTRACT_CHANGE**：任何经 `CODE_FACT` 确认真实参与 canonical chunk 构建的参数
    （当前：`CHARS_PER_TOKEN_EST`、`CHUNK_TARGET_TOKENS`、`CHUNK_MIN_CHARS`）。任一值改变 →
    重建 corpus → 新 corpus sha / 可能的新 chunk id → 旧 GoldChunkMap 过时 → 重新生成 GoldChunkMap。
  - **`S6_CAN_PROCEED_BEFORE_NUMERIC_TOKEN_CONTRACT_CLOSURE = YES`，
    ONLY because no chunk-construction parameter is being changed now。**
- **收窄（append-only，不回改历史）**：本文件"S6 依赖与 invalidation 审计闭合"条目中的
  `TOKEN_BUDGET_CHANGE_INVALIDATES_GOLD_CHUNK_MAP = NO` 只对 packing-only 参数成立。
  它原附条件"corpus / chunk identity / text / doc / page 保持不变"，
  而 `CHARS_PER_TOKEN_EST` 的改变本身就会违反这一条件。

### [L1] CHARS_PER_TOKEN_EST 的双重角色与"依赖不看名字"纪律

- **`CHARS_PER_TOKEN_EST_ROLE = TOKEN_ESTIMATOR_PARAMETER + CANONICAL_CHUNK_CONSTRUCTION_INPUT`**（依据见上表）。
- **决策：invalidation 由实际依赖决定，不由参数名称、所在文件，或它此前被放在哪条讨论线上决定。**
- 同类反例（只作为纪律示例，不扩展契约）：
  `parser_name` 这个名字 ≠ 实际语料构建器身份；`CHUNK_OVERLAP_TOKENS` 存在于 contracts ≠ canonical chunker 实际消费；
  `CHARS_PER_TOKEN_EST` 被放在 token-budget 讨论里 ≠ 它只是 packing 依赖。

### [L1] CHUNKER_CONFIG_IDENTITY_STATUS = TEMPORARY_CONTRACT_DERIVATION_PENDING_BUILDER_EXPORT

- 事实：当前 `chunker_config_identity()` 能证明所列三个值来自契约常量；配合源码审计能证明它们当前被 chunker 消费；
  但**不能结构性证明**未来 chunker 没有新增第四个实际参与 chunk 构建的参数 → silent omission risk。
- `CODE_FACT`（作为该风险的现存实例，不扩展契约）：canonical 构建路径上还消费着不在
  `chunker_config_identity()` 里的构建参数，例如：`kaiva_pdf._PARA_SPLIT_RE`（`:108/:484`，段落切分规则）、
  `kaiva_pdf.PDFTOTEXT_ARGS`（`:37/:247`，`-layout`）、`citation_gate.SECTION_MAX_CHARS`（`:55/:114`）、
  `contracts.CORPUS_LANG_DEFAULT`（`build_corpus.py:234` → `phase_b_ingest.py:98` 页准入）。
  这些参数哪些属于"effective chunker config"、哪些归 `corpus_builder_name` 覆盖，
  由下一轮构建实现导出时逐项列出，交人工确认。
- **职责冻结：**
  - **Contract layer**：定义 `corpus_builder_name` 的语义；要求 effective chunker config 进入 provenance；
    规定 `chunker_config` 的确定性序列化要求；要求 GoldChunkMap 绑定这些 identity。
  - **Corpus-building implementation = authoritative provider**：导出 `CORPUS_BUILDER_NAME` 与
    `effective_chunker_config_identity()`（或等价的单一权威接口），内容是**它实际消费的全部** corpus 构建参数，
    而不是契约列出的"它应该消费"的参数。
  - **Resolver**：只能 import / 消费上述权威导出；禁止手写 builder name、手写 chunker_config、
    复制参数列表、从无关常量推断。
- **`IMPLEMENTATION_PREREQUISITE_FOR_FORMAL_S6 = YES`**：权威 builder/config 导出留给下一轮
  resolver rewrite implementation；本轮不改 components/parsers/*、ingest/*、scripts/resolve_gold_chunks.py。
  当前 `chunker_config_identity()` 保留为 v0.3.0 契约侧临时推导（docstring 已标注 TEMPORARY、
  不是 resolver 复制的许可、正式生成 GoldChunkMap 前必须被取代或桥接）。

### [L1] CURRENT_VALIDATOR_SCOPE = CURRENT_CANONICAL_ONLY；HISTORICAL_IDENTITY_BLOCKER = NO

- **决策：`validate_gold_chunk_map()` 只判断某份映射能否被接受为当前 canonical 语料、
  当前可执行契约下的 GoldChunkMap；它不是通用的历史 artifact 校验器**（docstring 已写明）。
  其中 `chunker_config == chunker_config_identity()` 与 `contracts_version == CONTRACTS_VERSION` 两项检查保留。
- 历史映射（旧 corpus sha / 旧 builder/config identity / 旧 contracts_version）可能在它自己的 identity 下
  historically valid，只是 not acceptable as CURRENT canonical GoldChunkMap。
  **不得写成"历史 artifact 当年无效"。**
- **`HISTORICAL_IDENTITY_BLOCKER = NO`。**

### [L3] 本轮未重新打开的语义与复核

- 未改变：formal gold = 唯一最小基数 full evidence cover；L1 / L2 / AMBIGUOUS / L3 / L4 / FAIL 定义；
  `EXACT_CITATION_PAGE_ONLY`；短片段参与 full cover；K3-C fail-closed；删除 built_at；testset_version 规则；
  report schema；Recall 多 gold 下游缺口。
- `MEASURED`（current-corpus measurement，不是契约不变量）：L1 = 30 / L2 = 8 / AMBIGUOUS = 0 / L3 = 0 / L4 = 0 /
  FAIL = 0；formal associations = 47。
- `MEASURED`：`python3 -m unittest tests.test_contracts_gold_chunk_map tests.test_phase_b` → 91 OK；
  T3 拦 FORCED_COVER 回退，T4/T4b 覆盖最小 cover 并列，T8 拦丢弃短片段（变异检查见上一条目）。
- 0.2.0 → 0.3.0 失效复核：corpus `c8978777…`、page_quality、accepted OCR artifacts（140）与 index.jsonl、
  testset v5.3、9c-final 产物都不记录 contracts_version，也不消费被改变的 GoldChunkMap / MatchLevel /
  identity 语义 → **均无 semantic invalidation**。区分"artifact 没记录版本号"与
  "artifact 语义依赖被改变的契约"：只有后者构成失效，本次为零。

## 2026-09-28 · S6 contract follow-up：GoldChunkMap 绑定 authoritative builder identity

作用域：contracts 0.3.0 → 0.3.1；canonical corpus `c8978777…` / 3409；page_quality `69842896…` / 1335；
testset `05614407…` / 39；accepted OCR manifest `c0e5b037…`。

### [L1] invalidation 由 executable dependency 决定，不由参数名称 / 所属讨论主题决定

- evidence_type: `MEASURED`（真实 `ingest/build_corpus.build()` 在 scratch 中逐字节复现 canonical
  chunks `c8978777…` 与 page_quality `69842896…` 后，逐项 monkeypatch 做精确反事实）+ `CODE_FACT`（AST 可达性普查）。
- owner: 语料构建实现（`ingest/builder_identity.py`）。
- 例：`CHARS_PER_TOKEN_EST` 是 token 估算参数，同时参与 chunk 构建（改为 3 → 4384 chunks；改为 5 → 2770）；
  `CHUNK_OVERLAP_TOKENS` 存在于 contracts，但 canonical builder 不读取（改为 0 / 200 → corpus 与 page_quality 逐字节不变）；
  `MAX_PROMPT_TOKENS` / `TOP_K_CONTEXT` / `CONTEXT_PACK_MARGIN` / `CITATION_HEADER_EST_TOKENS` /
  `PROMPT_OVERHEAD_RESERVE_TOKENS` 改变 → 逐字节不变；
  `_PARA_SPLIT_RE` / `PDFTOTEXT_ARGS` / `SECTION_MAX_CHARS` / `HEADER_SCAN_LINES` / `OCR_LABEL_LINE_MAX_CHARS` /
  `LATIN_SCRIPT_LANGS` / `--doc-lang` 改变 → corpus 改变。
- falsified_if: 出现某参数的 executable dependency 与反事实结论不一致（按名称/主题分类反而正确）的实例。

### [L1] GoldChunkMap construction identity 四层

- **决策（Arya H1）：GoldChunkMap 对构建身份的正式绑定为
  `corpus_chunks_sha256`（最终语料字节）/ `corpus_builder_name`（构建语义实现族与版本）/
  `construction_rules_sha256`（权威 builder 导出的静态构建语义指纹）/ `chunker_config`（数值型分块参数的人类可读身份）。
  四者不得互相替代。** 本次新增字段 `construction_rules_sha256`，CONTRACTS_VERSION 0.3.0 → 0.3.1。
- evidence_type: `MEASURED`（上一条反事实：26 条静态构建规则会改变 corpus，却不在 v0.3.0 任何 identity 字段中 → B2）。
- owner: 契约层（字段语义）/ 语料构建实现（取值）。
- falsified_if: 出现四层中某一层与另一层始终同变、无独立信息的证据，或出现静态构建依赖改变而四层都不变的实例。

### [L1] authoritative ownership：`ingest/builder_identity.py`；contracts / resolver 只消费

- **决策（Arya H3）：`CORPUS_BUILDER_NAME` / `effective_chunker_config_identity()` / `construction_rules_identity()`
  只由 `ingest/builder_identity.py` 导出；contracts / resolver / 下游不得复制登记表、重列参数、手写或钉住当前值。**
- **v0.3.0 的临时推导 `core.contracts.chunker_config_identity()` 删除（不保留 facade）。**
- **桥接方式 = 依赖注入**：`core/contracts.py` 只定义 `CorpusBuilderIdentity` 形状；
  `validate_gold_chunk_map(..., current_corpus_chunks_sha256=..., builder=...)` 以参数接收权威提供者，
  resolver 必须传入 `ingest.builder_identity` 模块本身。
  理由（`MEASURED`）：contracts 顶层 import builder 形成循环
  `core.contracts → ingest.builder_identity → core.contracts`（部分初始化的 contracts 在
  `components/parsers/kaiva_pdf.py:48` 导入期缺 `CHUNK_TARGET_TOKENS` → AttributeError）；
  函数内延迟 import 虽不崩溃，但让 contracts 依赖 ingest 与 components，违反"contracts 谁都不依赖"。
  两条都有测试守护（contracts 不 import 任何第一方模块；Protocol 只有形状）。
- evidence_type: `MEASURED` + `CODE_FACT`。
- owner: 语料构建实现（值）；契约层（形状与校验规则）。
- falsified_if: 出现不经权威模块也能正确产生三项身份的场景；或依赖注入被用来传入非权威提供者而未被 resolver 测试拦下。
- 已知残余风险：contracts 在运行时无法验证传入的 `builder` 确为 `ingest.builder_identity`；由 resolver 侧测试负责。

### [L2] runtime corpus provenance 不复制进 GoldChunkMap（H2）

- owner_experiment: S6（GoldChunkMap 生成）/ 语料构建链。
- **决策（Arya H2）：源 PDF 身份、accepted OCR manifest、`--doc-lang` 实参、Poppler/pdftotext 版本、
  视觉诊断 CSV 身份不写进 GoldChunkMap。** GoldChunkMap 是"人工 citations → 冻结语料 chunks"的派生投影，
  不是第二份语料构建清单。输入变化而语料字节不变 → 不应仅因此失效；语料字节改变 → `corpus_chunks_sha256` 已使其失效。
- 前提：`corpus_chunks_sha256` 始终是可核验的字节锚（canonical 在场可重算；丢失可由冻结代码 + 冻结必要输入重建核验）。
- **REOPEN CONDITION：若出现"语料字节可能已变、但 `corpus_chunks_sha256` 无法重算、也无法由冻结输入重建核验"，
  本边界必须重新打开，届时不得再声称语料哈希足以承担唯一字节锚。**
- 登记表边界：`CORPUS_LANG_DEFAULT` 保持 `RUNTIME_INPUT_DEFAULT`，不进入静态身份（不得以默认值冒充本次构建的实际值）。
- evidence_type: `DERIVED`（输入：`corpus_chunks_sha256` 的字节锚定义 + 本节反事实）。

### [L2] SILENT_OMISSION_DEFENSE = PARTIAL

- owner_experiment: 语料构建实现的每次改动（由 `tests/test_builder_identity.py` 执行）。
- 结构性防御：builder 自有登记表；AST 从 `build_corpus.main/build` 出发的可达常量普查；登记表与可达集合双向相等；
  构建代码 AST 指纹 tripwire；合成漏登 / 变异测试（`MEASURED`：删除登记项、合成包新增依赖、改合并连接符均被拦下；
  改 docstring / 注释不触发 tripwire）。
- 已知盲区（不宣称覆盖）：函数体内字面量与逻辑；任意运行时输入；外部可执行文件/工具版本；
  逻辑改动是否应递增 builder 版本的最终人工判断。
- falsified_if: 出现构建可达常量改变 corpus 而上述测试全部通过的实例。

### [L2] validator scope = CURRENT_CANONICAL_ONLY

- owner_experiment: S6。
- **决策（Arya H8）：`validate_gold_chunk_map` 只回答"能否作为当前 canonical 语料 / 当前构建语义下的 GoldChunkMap 被接受"。**
  v0.3.1 起它对 `corpus_chunks_sha256`（与调用方自算的当前语料哈希）、`corpus_builder_name`、
  `construction_rules_sha256`、`chunker_config`（与权威 builder 导出）做相等校验。
  历史映射在自身 identity 下可能历史有效，在此被拒绝不表示它当年无效。
- evidence_type: `CODE_FACT`（validator 实现）+ `MEASURED`（T3/T4/T5/T7/T9/T10；变异检查：去掉身份相等校验后 6 个测试失败）。
- falsified_if: 出现需要在当前 builder 下接受历史语料映射的正式用例。

### [L3] page_quality Git durability = FOLLOWUP；不阻塞 S6

- 事实（`MEASURED`）：`ingest/page_quality.jsonl` 未被 Git 跟踪（也未被 ignore）；committed-tree 自测有 1 个 Phase B
  集成测试因缺该文件而 skip。视觉诊断 CSV 同样未跟踪，因此 fresh clone 无法复现 page_quality 的 sha（chunks 不受影响）。
- **决策（Arya H9）：单独 FOLLOWUP，不阻塞 formal S6** —— resolver 不读 page_quality，GoldChunkMap identity 不依赖它，
  chunks 字节可独立核验。
- owner: artifact durability（独立决定）。
- reopen condition: resolver 或 GoldChunkMap identity 开始读取 page_quality。

### [L3] 0.3.0 → 0.3.1 失效复核

- `MEASURED`：canonical corpus、page_quality、accepted OCR artifacts（140）与 index、accepted manifest、9c-final 产物
  均不记录 contracts_version，也不消费被改变的 GoldChunkMap identity / validator 语义 → **均不失效**；
  GoldChunkMap / IndexManifest / EvalItemResult 均尚不存在。改动后真实 build() 仍逐字节复现 `c8978777…` / `69842896…`。

## 2026-09-28 · S6 manual alignment：formal S6 就绪、builder provider 同一性、旧 80% 门撤销

作用域：contracts `d30ed34`（v0.3.1）；resolver `8719761`；canonical corpus `c8978777…` / 3409；testset `05614407…` / 39。
本条只记录文档对齐与既有实现证据，不改契约、不改代码。

### [L2] BUILDER_PROVIDER_IDENTITY_ASSERTION = PASS

- owner_experiment: S6 resolver（`tests/test_resolve_gold_chunks.py` T25 / T26 守护）。
- 事实（`CODE_FACT`）：v0.3.1 用依赖注入让调用方把 `CorpusBuilderIdentity` 提供者传给 `validate_gold_chunk_map`；
  validator 只做**值比较**。
- 事实（`MEASURED`，T26）：一个与 `ingest.builder_identity` 值完全相同的伪 provider **能通过** validator。
- 因此 resolver 生产路径必须 `import ingest.builder_identity as builder_identity`，并把**同一个模块对象**传给 validator；
  `run()` 没有任何注入 provider 的参数。
- 事实（`MEASURED`，T25）：测试捕获生产路径实际传入的 builder，断言 `builder is ingest.builder_identity`
  （对象同一性 `is`，不是 `==`、不是字段值相等）。变异检查：把生产路径改为传值相等的伪 provider → T25 / T26 失败。
- 这是实现验收证据，不新增 GoldChunkMap 契约字段。
- falsified_if: resolver 生产路径出现传入非 `ingest.builder_identity` 对象、而 T25 / T26 仍通过的实例。

### [L1] 旧"L1+L2 ≥ 80%"验收门撤销：L1_L2_80_PERCENT_STATUS = REDUNDANT

- 事实（`CONTRACT_FACT`）：v0.3.1 的接受条件是 fail-closed —— 每道 answer 题的**每一条** citation 都必须是 L1/L2，
  否则 `validate_gold_chunk_map` 抛异常、resolver 只写 report、退出码 3。
- 推导（`DERIVED`，输入仅为上一条契约事实）：任何被接受的映射，其 L1+L2 占比必为 100%，"≥ 80%" 恒成立，
  作为接受门不提供额外约束 → **REDUNDANT**。旧门配套的"低于 80% 才处理"的写法还暗示 80–99% 可接受，
  与 fail-closed 矛盾。另外，旧门的 L2 是"邻页全片段命中"，v0.3.0 起已重定义为"同页唯一多块最小 cover"，
  80% 这个数本身也是按旧语义设的。
- 本结论不依赖当前 38/38 全部解析的测量结果。
- **决策：执行手册 S6 删除该门，由"全部 answer citation 为 L1/L2"取代；不改成 100%（那只是把契约条件抄一遍）。**
  保留旧门背后仍然有效的纪律：未解析时不修数据、不放宽匹配、逐条对照原文人工复核。
- falsified_if: 契约的接受条件从 fail-closed 放宽为比例门。

### [L1] S6 ordering 收窄：formal S6 当前可以执行

- 追加收窄（不回改历史）：本文件及旧版手册中"S6 等待 S5c / 现在生成的 GoldChunkMap 是 known-to-be-invalidated artifact"
  的前提已不成立 —— S5c 已 CLOSED（2026-09-24 条目），canonical corpus 已冻结，contracts v0.3.1 与权威 builder 身份已提交，
  resolver 已按 v0.3.1 实现并提交。**formal S6 当前可以执行。**
- GoldChunkMap 依赖的是 canonical corpus 字节与构建身份（`corpus_chunks_sha256` / `corpus_builder_name` /
  `construction_rules_sha256` / `chunker_config`）。
- **保留：若未来改动任何会改变 chunk 构建的依赖（包括但不限于 `CHARS_PER_TOKEN_EST`、`CHUNK_TARGET_TOKENS`、
  `CHUNK_MIN_CHARS`、construction rules）而导致 corpus sha 改变，GoldChunkMap 必须针对新 corpus 重新生成。
  invalidation 按实际依赖，不按参数所属的讨论主题。**
- evidence_type: `CONTRACT_FACT` + 本文件既有 `MEASURED` 条目（S5c 关闭；构建依赖精确反事实）。
- falsified_if: 出现 formal S6 的前置条件未满足、但本条仍被当作可执行依据的情形。

### [L3] 执行手册 S6 对齐记录

- 手册 S6 状态改为 **READY FOR FORMAL RUN（formal S6 尚未执行）**；正式流程写为 Phase A（identity gate）→ B（只读 preflight）→
  C（Run A / Run B 全新目录、逐字节比较）→ D（fail-closed 验收 + 独立校验）→ E（只提升通过 D 的字节）。
  文档中的 Phase A–D 命令已逐字执行验证（C / D 的产物只写入临时目录，事后删除）；Phase E 只做语法检查。
- 文件名一律来自 `GoldChunkMap.filename()`；删除手写的 `parser-kaiva_pdf_v1`（S6 验收项与 S8 命令两处）。
- resolver 输出覆盖策略（已存在同名 map/report 即拒绝运行）记为 **implementation / operational policy**，不是 GoldChunkMap 契约语义。
- README 只做最小事实修正（resolver 已对齐；formal S6 未运行）。

### [L3] 登记的 followup（本轮不处理）

- **`RESOLVER_CORPUS_TOCTOU = FOLLOWUP`**，owner：post-S6 hardening。事实（`CODE_FACT`）：resolver 只在开始时计算一次
  corpus sha；testset 有运行前后比对，corpus 没有加载后的复核。
- **`GOLD_CHUNK_MAP_GIT_TRACKING = PENDING_DECISION`**，owner：formal S6 Phase E。事实（`MEASURED`）：
  `eval/gold_chunk_map/` 不在 `.gitignore` 中，提升后会显示为 untracked；契约允许 GoldChunkMap 不进 Git（可再生）。

## 2026-09-28 · Formal S6 closure / canonical GoldChunkMap freeze

作用域：contracts `d30ed34`（v0.3.1）；resolver `8719761`；manual alignment `7c8ef4a`（formal run 时的 HEAD）；
canonical corpus `c8978777…` / 3409；testset `05614407…` / 39；page_quality `69842896…` / 1335。
证据标记沿用本文件纪律（`MEASURED` / `DERIVED` / `CODE_FACT` / `CONTRACT_FACT`）。
Run A / Run B 与独立审计的原始日志位于执行会话的 scratch 目录，**未入库**；
下文 level 计数与 mapping 计数可由已提交的 map 与 report.csv 直接复核（locator 见各条）。

### [L1] Formal S6 acceptance

- 事实（`MEASURED`）：Run A / Run B 为两个独立进程、两个全新目录，执行同一条 committed CLI 命令；
  `RC_A = 0`，`RC_B = 0`（`$?` 直接取值，未经管道）。
- 事实（`MEASURED`）：map A == map B 逐字节一致；report A == report B 逐字节一致（`cmp` 均为 0）。
- 事实（`MEASURED` · locator：已提交 report.csv 的 `match_level` / `needs_review` 列）：
  **L1 = 30 / L2 = 8 / L3 = 0 / L4 = 0 / AMBIGUOUS = 0 / FAIL = 0**；needs_review = true 0 条 / false 38 条。
- 事实（`MEASURED` · locator：已提交 map + `eval/testset_v5_3.jsonl`）：
  **answer qids in mapping = 31/31；refuse qids in mapping = 0/8**；mapping 无空值，键按评测集顺序、值按 corpus 顺序。
- 事实（`MEASURED` · 独立审计，不 import resolver，按契约定义重新计算片段、同页候选与**全部**最小基数 cover）：
  **EXACT_PAGE_PROVENANCE_VIOLATIONS = 0；minimum-cover ties = 0**；每页候选 universe ≤ 3；
  multi-fragment citations = 20（L1 12 / L2 8）；formal associations = 47；unique formal chunks = 39。
- 事实（`MEASURED`）：`validate_gold_chunk_map(..., builder=ingest.builder_identity)` 对 Run A 产物与提升后的
  canonical 路径各执行一次，均 PASS。与执行手册 S6.2 参考值（39 / 31 / 8 / 38 / 94 / L1 30 / L2 8 / 47 / section 不一致 3）无差异。
- **决策：`FORMAL_S6_ACCEPTANCE = PASS`；`GOLD_CHUNK_MAP_PROMOTION = PASS`；`S6_STATUS = CLOSED`。**
- falsified_if: 从已提交的 map / report.csv 复核出任一 answer citation 不是 L1/L2，
  或同一冻结输入下 resolver 不能逐字节再生这份 map / report。

### [L1] Canonical GoldChunkMap identity

- map path：`eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json`
- map sha256：`8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc`（2026 bytes / 120 lines）
- report path：`eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.report.csv`
- report sha256：`f48018cbe88de3d379fb65c17e75e6b8a87eebdc8dd19bdd539356bfff5a2572`（17897 bytes / 39 lines）
- map identity 字段（读自 map 本身）：
  - `testset_version` = `v5.3`
  - `testset_sha256` = `05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b`
  - `corpus_chunks_sha256` = `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb`
  - `contracts_version` = `0.3.1`
  - `corpus_builder_name` = `kaiva_phase_b_builder_v1`
  - `construction_rules_sha256` = `e89e6f94ec80abdc458622a52587644dc72baaadeb6564606ddc273c2951c5a1`
  - `chunker_config` = `chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350`
- 事实（`MEASURED`）：map 文件字节 == `serialize_gold_chunk_map()` 对其解析结果的输出；
  文件名 == `GoldChunkMap.filename()` / `report_filename()`。
  文件名只编码 testset_version、corpus sha 前 8 位、builder 名；其余 identity 只在 map 字段里。

### [L1] GoldChunkMap durability

- **决策（人工）：`GOLD_CHUNK_MAP_DURABILITY_POLICY = TRACK_CANONICAL_MAP_AND_REPORT_IN_GIT`。**
- 理由：
  - GoldChunkMap 是 derived / reproducible artifact；
  - Formal S6 已证明相同冻结输入下可逐字节重建（Run A == Run B）；
  - 它不是 EvalItem，也不回写 testset；
  - S8 及后续结果将依赖这份 map 作为 gold provenance；
  - EvalItemResult / downstream evidence 会引用 GoldChunkMap identity；
  - 因而 canonical gold artifact 必须可由 fresh clone 直接恢复；
  - Git tracking 避免要求每个新环境先重跑 S6；
  - 不允许长期处于 untracked + not ignored 状态。
  - 成本说明（不是 provenance 理由）：map 2026 bytes + report 17897 bytes。
- 事实：data commit = `717650526879fac689328b7e80747edab5bd670c`（`data: freeze canonical S6 GoldChunkMap`），
  staged 恰为上述 2 个文件（均为 `A`），`git diff --cached --check` clean，已 push，fetch 后 `origin/ship-rag == HEAD`。
- 事实（`MEASURED`，Git-tree recovery）：`git archive 7176505 | tar -x` 导出到全新临时目录；
  导出的 map / report 的 sha256 / bytes / lines 与上方 identity 逐项相等；
  在导出树中 import 导出树自身的 `core.contracts` 与 `ingest.builder_identity`，解析 GoldChunkMap，
  `validate_gold_chunk_map(..., builder=ingest.builder_identity)` PASS（validation scope 见下一条）。
- **决策：`GOLD_CHUNK_MAP_DURABILITY = DURABLE_IN_GIT`。**
- 性质：map / report 是 derived、reproducible、Git-frozen canonical artifact；不属于 EvalItem；不修改 testset
  （`eval/testset_v5_3.jsonl` 在 formal run 前后与本轮前后 sha256 均为 `05614407…`）。
- 关闭已登记 followup：2026-09-28 manual alignment 条目中的 `GOLD_CHUNK_MAP_GIT_TRACKING = PENDING_DECISION`
  由本条决定关闭。

### [L2] committed-tree validation scope

- **GIT_TREE_ARTIFACT_VALIDATION**（输入只来自导出的 Git tree）：map / report 字节可恢复；schema（字段集合与顺序）正确；
  serialization（字节 == `serialize_gold_chunk_map()`）正确；filename 正确；`contracts_version` 与导出树 `CONTRACTS_VERSION` 一致；
  builder identity 三项与导出树 `ingest.builder_identity` 导出一致；`testset_version` / `testset_sha256` 与导出树中的评测集一致；
  mapping 键 == 导出评测集 answer qids（31）、无 refuse qid；report 表头、行序、级别（全部 L1/L2）与 mapping 自洽。
- **EXTERNAL_CANONICAL_CORPUS_VALIDATION**：`corpus/chunks.jsonl` 被 gitignore，不在 git archive 中。
  因此仅靠 committed tree **不能**重新证明"mapping 里的每个 chunk id 确实存在于 canonical corpus"
  及 `corpus_chunks_sha256` 与语料字节相符。本轮这一层以当前磁盘上的 canonical corpus 作为明确标注的
  read-only external input（重算 sha256 = `c8978777…` 后）完成，PASS。
- **边界：不得把 Git-tree recovery 描述成"完整 S6 acceptance 纯 Git 可重放"。**
  这一层依赖 canonical corpus external input；而 corpus 重建本身还依赖不进 Git 的 `raw/` 源 PDF。
  这不是 failure，是 validation scope boundary。

### [L2] Resolver corpus TOCTOU

- **`RESOLVER_CORPUS_TOCTOU = FOLLOWUP`（保持不变）。**
- 事实（`MEASURED`）：`corpus/chunks.jsonl` 的 sha256 / bytes / lines 在 Run A 前、Run A 后、Run B 后均为
  `c8978777…` / 4678209 / 3409 → `CORPUS_IDENTITY_DRIFT_DURING_RUN = NO`。
- 边界：这只证明本次运行没有发生 drift，不代表 resolver 本身已解决 TOCTOU
  （`CODE_FACT`：resolver 仍只在开始时计算一次 corpus sha，加载后无复核）。

### [L2] Builder-provider identity

- 事实：production resolver 传给 `validate_gold_chunk_map` 的 builder `is ingest.builder_identity`（对象同一性）。
  该约束由 resolver tests 的对象同一性测试（T25 / T26）保护。
- 事实（`MEASURED`，formal run 前）：`tests.test_resolve_gold_chunks` / `tests.test_contracts_gold_chunk_map` /
  `tests.test_builder_identity` 共 99 个测试 OK；另在真实 canonical 数据上把 committed 脚本作为 `__main__` 运行并截获
  validator 参数：捕获的 builder `is ingest.builder_identity`；值相等的伪 provider 能通过 validator 的值比较；
  CLI 拒绝 `--builder`，`run()` 无 provider 参数。

### [L3] Formal-run CLI note

- 事实：Formal Run A / Run B 都使用完整 64-char corpus sha assertion（`--corpus-sha c89787778448…25f4eb`），
  与旧手册 Phase C 的 A = 8-char prefix / B = 64-char 写法不同。
- 参数只做 assertion，不进入 map / report 的 self-computed identity（`CODE_FACT`：map 写 resolver 自算的 sha，
  文件名亦由自算 sha 生成）；Run A / B 输出逐字节一致。

### [L1] Evidence rule：identity assertion 不得 self-derive

- 事实（本轮发现）：旧手册 Phase C 写法为
  `CORPUS_SHA=$(shasum -a 256 corpus/chunks.jsonl …)` → `resolver --corpus-sha "$CORPUS_SHA"`。
  assertion 的 expected 与被检查对象来自同一来源，无论文件是什么都会通过 ——
  这是 **structurally non-falsifiable gate**。
- **决策：identity assertion 的 expected value 必须来自独立的已冻结来源，
  不能在同一步从被检查对象重新计算后再传回。**
- 落地：执行手册 S6.3 Phase C 已改为区分 `EXPECTED_CORPUS_SHA256`（冻结 canonical identity，
  来源：2026-09-24 S5c 关闭条目 `CURRENT_CANONICAL`）与 `ACTUAL_CORPUS_SHA256`（现场计算，只用于与 EXPECTED 比较）；
  `--corpus-sha` 传 EXPECTED。本条只修一个无约束力的操作门，不扩展为新的 contract。

### [L3] 登记的 followup（本轮不处理）

- `core/contracts.py` 的 `GoldChunkMap` docstring 写有"它不进 Git，可再生是前提"与
  "再生方式（这是它可以不进 Git 的前提）"；2026-09-25 [M] 条目的 why_not_falsifiable 亦写"GoldChunkMap 不进 Git"。
  本条 durability 决定之后，这些描述性措辞与现状不一致。本轮不修改 contracts；
  是否及如何更新措辞，由人工在契约轮次裁决。
- `.gitignore` 顶部注释"唯一例外：eval/testset_*.jsonl …"未随本决定更新（不在本轮修改范围内）。


## 2026-10-01 · S8 / M1c retrieval protocol：人工裁决落地（apply for review）

证据标记沿用：`CONTRACT_FACT` / `CODE_FACT` / `MEASURED` / `DERIVED` / `DOCUMENTED_ONLY` / `HISTORICAL` / `NOT_VERIFIED`。
作用域：HEAD `d28d130de33ec4abf79b67cff12dfd9e33b885be`；corpus `c8978777…` / 3409；testset `05614407…` / 39；
canonical GoldChunkMap `8cf9f3be…`、report `f48018cb…`；`CONTRACTS_VERSION = 0.3.1`。
依据：同日只读 S8 protocol closure（会话内）+ 人工逐项裁决 D1–D15。裁决归 Arya；本条目由 AI 按裁决机械落地，待人工审核 diff。

### [L2] D1 · 固定-k 多 gold 指标

- owner_experiment: S8 / M1c
- 事实（`MEASURED`，canonical map + report.csv）：answer 31 / refuse 8；|gold| 分布 1:21 / 2:7 / 3:1 / 4:1 / 5:1（多 gold 10 题）；
  Σ|gold| = 47；citation 38 条，L1 30 / L2 8。
- **决策：GoldChunkMap mapping 不变。固定-k 至少报告三个不同的量：**
  - `ANY_GOLD@k` = 1 iff top_k ∩ gold(q) ≠ ∅ —— navigation / candidate retrieval 是否至少触达一份 formal gold evidence。
  - `GOLD_COVERAGE@k` = |top_k ∩ gold(q)| / |gold(q)| —— 主 aggregate 为 31 道可答题的 macro 平均；micro（47 个 题目–chunk 对）只作诊断。
  - `ALL_MAPPED_GOLD@k` = 1 iff gold(q) ⊆ top_k —— **严格诊断量**。
- **决策：`ALL_MAPPED_GOLD` 当前不得命名或宣称为 EVIDENCE_COMPLETE / ANSWER_COMPLETE / COMPLETE_EVIDENCE。**
  依据（`CONTRACT_FACT`）：GoldChunkMap 冻结的是 citation → chunk 投影；EvalItem schema 没有字段表达同一道题多条 citation 之间的逻辑关系。
  single-citation L2 的 cover 内 chunk 共同构成该 citation 的完整 formal cover —— 这**不**推出同题多条 citation 之间为 AND。
- 关闭范围：本条部分关闭 2026-09-25 `RECALL_MULTI_GOLD_SEMANTICS = DOWNSTREAM_CONTRACT_GAP`（固定-k 报告口径已定）；
  answer-level complete-evidence 语义仍开放，见下一条。

### [L2] D1-A · multi-citation logic 只读 probe

- owner_experiment: S8 / M1c（关闭需人工标注）
- 输入（只读）：`eval/testset_v5_3.jsonl` 各题 question / required_elements / acceptable_elements / gold_answer / rationale；
  report.csv `fragment_matches_json`；canonical chunk 正文。testset 未修改。
- 下列 heuristic 只作待验证假设，**未直接采用**："不同 citation 支撑不同 required_element → AND"、"相同 required_element → OR"。
- 结果（evidence 类型 = `DERIVED(人工撰写的 testset 文本)`；不是 schema 字段，不写回 testset）：

  | qid | citation 数 | 推断的 citation 角色 | 依据（locator：testset 该题对应字段） | 强度 |
  |---|---|---|---|---|
  | CD01 | 3 | #0 SMM p73 ∧ #1 ERM p105 为必需；#2 SMM p74 只支撑 acceptable | required_elements 逐项带 "(SMM)" / "(ERM)"；rationale "两半各属一册、缺一不可"；acceptable "EEBD … (SMM p74)" | 强 |
  | CD02 | 2 | #0 ∧ #1 均必需 | required_elements "QMM: …" / "EMM (EMS): …"；rationale "两数不同、各属一册" | 强 |
  | CD03 | 2 | #0 ∧ #1 均必需 | rationale "'Master 是 PTW 批准权人'全库只在 SMM"；另两项 required 与 FMM p38 片段逐字对应 | 强 |
  | FL07 | 2 | #0 p32 必需；#1 p34 只支撑 acceptable | rationale "评分只保留 BAC 0 / 40mg% 两项为必需"；acceptable "17.5 µg/L (p32) OR 19 µg/100ml (p34) — SOURCE CONFLICT" | 强 |
  | FL06 | 2 | #0 p33 表格必需；#1 p34 为佐证 | question "Per QMM's Drug & Alcohol Testing Requirements table"；rationale "以 QMM p34 的'6-monthly'交叉核实"；`MEASURED`：required 元素 "(c) … at random" 中的 random 字样在 `QMM:p33:2` 正文内，但不在 #0 的 quote 片段里，只出现在 #1 的 quote 中 | 中 |
  | CN03 | 2 | **未解出** | 两项 required 只出现在 ERM p14（`MEASURED`：`ERM:p14:0` 含 "overall management" / "main contact"，`QMM:p46:1` 不含）；但 rationale "使模型无论检索到哪一处…都不被判 0" 表达 OR 意图 —— 两处人工文本冲突 | — |

- **决策：`REQUIRED_ELEMENTS_SUFFICIENT_TO_INFER_CITATION_LOGIC = PARTIAL`；`MULTI_CITATION_LOGIC_GAP = PARTIAL`。**
  可推出 5/6（CD01 / CD02 / CD03 / FL07 / FL06），但多数还需 rationale / question / acceptable_elements，只靠 required_elements 不够；
  CN03 = `NEEDS_HUMAN_ANNOTATION`。上述推断在人工确认前不得作为 metric 定义的输入。
- 推论（`DERIVED`）：citation 之间的关系不只有 AND / OR，还有"仅佐证 / 只支撑 acceptable"。FL06 / FL07 / CD01 的 mapping 含这类非必需 citation 的
  chunk（`QMM:p34:0` / `QMM:p34:2` / `SMM:p74:0`）→ 对这三题，`ALL_MAPPED_GOLD` 比 required-element 层面的完整证据更严。这进一步支持 D1 的命名限制。
- 边界：本 gap 不阻塞 BM25 fixed-k baseline；在把任何 ALL 型指标宣称为 answer-level complete-evidence primary metric 之前必须关闭
  （需人工逐 citation 标注角色；是否把角色写进 EvalItem schema 另行裁决）。
- falsified_if: 人工复核给出与上表任一推断不同的 citation 角色。
- 另记（不改 testset）：CN03 的 rationale "无论检索到哪一处都不被判 0" 与 §14.3 判分规则（Partial 需命中 ≥ 60% required_elements）
  在只检索到 QMM p46 时不一致。

### [L2] D2 · evaluation k

- owner_experiment: S8 / M1c
- **决策：`RETRIEVAL_K_MAX = TOP_K_RETRIEVE = 20`；`EVAL_RECALL_K_SET = (1, 2, 3, 5, 20)`；保存完整 top-20 ranking。**
- **决策：`PACKING_REALIZED_K` 是 pack_context 的逐题输出，不是 evaluation cutoff。**
- **决策：HISTORICAL "306 tokens/chunk"（2026-09-25 已标 `NOT_VERIFIED`）不得再用于推导 evaluation k。**
- 依据：2 / 3 是 `_s4a9c_final_canonical_windows.csv` 两种打包场景下 realized k 的众数区间（`MEASURED`；按语料顺序的连续窗口，不是检索窗口）；
  1 / 2 兑现 2026-09-08 [L1] 预先声明；5 = `TOP_K_CONTEXT`；20 = `TOP_K_RETRIEVE`。
- **决策：`RERANKER_OBSERVATION_K = (2, 3)`；`RERANKER_DECISION_THRESHOLD = NOT_YET_FROZEN`。**
  不得现在把 @2 固化为最终 reranker gate；真实 retrieval-window measurement 完成后再裁。

### [L1] D3 / D15 · fixed-k retrieval 与 packed context 的依赖收窄

- falsified_if: S8 fixed-k 的实现被证明读取了 MAX_PROMPT_TOKENS / PROMPT_OVERHEAD_RESERVE_TOKENS / CONTEXT_PACK_MARGIN /
  CONTEXT_PACK_BUDGET_TOKENS / TOP_K_CONTEXT / pack_context 中任一项；或数值契约决定改变了 canonical chunking，而 S8 结果未随之失效。
- 冲突（不按日期裁）：旧记录 2026-09-08（"S4a.9 必须在 S8 前完成"、"9d → `contract:` commit → 解锁 S8"、"再冻结 S8 的主 k 值"）
  及 contracts.py `PROMPT_OVERHEAD_RESERVE_TOKENS` 注释；新记录 2026-09-25（token-contract line 需要 real retrieval evidence）。两者合读成环。
- 依赖证据（`CONTRACT_FACT` + `DERIVED`；retriever / eval 代码尚不存在，`CODE_FACT`）：fixed-k 指标只读 corpus、question、retriever protocol、
  TOP_K_RETRIEVE、GoldChunkMap；pack_context 读 CONTEXT_PACK_BUDGET_TOKENS（← 1050 / 200 / 0.90）、TOP_K_CONTEXT、
  est_prompt_tokens（← CHARS_PER_TOKEN_EST、CITATION_HEADER_EST_TOKENS）。
- **决策：`FIXED_K_RETRIEVAL_BASELINE` 不读取 MAX_PROMPT_TOKENS / PROMPT_OVERHEAD_RESERVE_TOKENS / CONTEXT_PACK_MARGIN /
  CONTEXT_PACK_BUDGET_TOKENS / TOP_K_CONTEXT / pack_context → 不被 numeric token-contract decision 阻塞。**
- **条件失效：`CHARS_PER_TOKEN_EST` 同时参与 canonical chunk construction（2026-09-28 [L1]）。** 若未来修改它并改变 canonical chunking
  → corpus、GoldChunkMap、fixed-k S8 结果全部失效。
- **决策：`PACKED_CONTEXT_MEASUREMENT` 读取当前 executable packing contract，是 numeric token-contract decision 的 evidence，
  不得反向阻塞 fixed-k baseline。**
- **决策：`S8_BLOCKED_BY_NUMERIC_TOKEN_CONTRACT = PARTIAL`** —— fixed-k baseline = NO；current-contract packed measurement = NO；
  final-budget packed conclusion = YES。
- **顺序：S8 fixed-k BM25 baseline 可先于 numeric token-contract final decision；real retrieval-window measurement 在 frozen S8 result 上运行，
  为 numeric decision 提供 evidence；final packed-context conclusions 在 numeric contract freeze 后确认。不得恢复旧的循环依赖。**
- 收窄（append-only，不回改）：2026-09-08 上述三处表述按本条收窄为只约束 packed 结论。contracts.py 对应叙述已同步修改（只改注释，数值常量未动）。

### [L2] D3-A · TTFT 10 s 的业务需求状态

- owner_experiment: numeric token-contract decision / M6（目标硬件实测）
- 事实：现有材料描述"船员使用、离线、CPU-only、无 IT 支持"，但**没有冻结**具体使用场景、紧急程度、可接受等待时间、TTFT SLA、
  end-to-end latency SLA。`TTFT_BUDGET_S = 10.0` 在 contracts 中是 [L2]（owner M6）。
- **决策：`TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`。** 10 s 不得描述为已确认的业务硬需求、船员硬 SLA，
  或经用户研究确认的 production requirement。
- **决策（人工方向）：`PERFORMANCE_QUALITY_PRIORITY = QUALITY_SPEED_TRADEOFF`。** 若更长上下文显著改善质量，可以接受明显高于 10 s 的响应时间。
- **决策：`MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180 seconds`。** 它只是后续 trade-off analysis 的最大探索上限；
  不是 target TTFT、recommended TTFT、executable contract、production SLA，也不是 MAX_PROMPT_TOKENS 的直接换算依据。
- **禁止：用开发机 measured prefill rate（tokens/sec）× 180 推出船端 MAX_PROMPT_TOKENS。** 开发机测量作用域 ≠ 船端 x86 production hardware
  （2026-09-25 [L1] token budget 校准目标设备）。任何此类换算必须标 `DERIVED(<source evidence scope>)`，不得升级为 production fact；
  在同时获得 production hardware measurement 与 concrete use-case requirement 之前，不得换算成 MAX_PROMPT_TOKENS。
- 未来 numeric token-contract decision 的目标：在 TTFT ≤ 180 s 的探索范围内，比较 retrieval evidence coverage、packed gold coverage、
  answer quality、TTFT、end-to-end latency 的 trade-off / Pareto frontier，选择合理的 operating point —— **不是最大化 prompt size，
  也不是尽量接近 180 s**。若较低延迟已获得绝大多数质量收益，不得因 ceiling 是 180 s 而继续扩大 prompt。
- 本条不修改任何数值常量。

### [L2] D3-B · S8 结果对未来预算的可复用性

- owner_experiment: S8 / numeric token-contract decision
- **决策：S8 normative result 必须保存完整 top-20 ranking、score semantics、corpus / map / testset identity**，使不同 packing budget 下的
  realized k、packed ANY / coverage / ALL_MAPPED_GOLD、overbudget、actual token cost 都能在 frozen S8 result 上重新模拟，**无需重跑 retrieval**。
- **决策：未来 TTFT / token budget 调整不构成重跑 fixed-k retrieval 的理由**，除非 corpus identity、retrieval protocol 或 model / index identity 本身变化。

### [L2] D4 · query construction

- owner_experiment: S8
- **决策：query = `EvalItem.question` 原始字符串。** retrieval orchestration 层不翻译、不 LLM rewrite、不做 metadata augmentation、
  不把整个 EvalItem 作为 query 输入。
- **决策：Unicode / case / token normalization 属于各 retriever 的 analyzer / embedder protocol，对 query 与 document 对称应用。**
- 事实（`MEASURED`）：39/39 题 NFC 稳定、空白规整；NFKC 只会改变 ML01 的全角标点；ML01 没有 ASCII 词元；canonical corpus 无 CJK / 天城文 chunk。

### [M] D4 · gold leakage policy

- why_not_falsifiable: 评测信息不得进入检索，是实验有效性的方法要求，不是关于本系统的经验主张。
- **决策：下列字段不得用于 query / filter / boost / routing / tie-break / dynamic k：** expected、type、language、citations/*、GoldChunkMap、
  report.csv、gold ids、required_elements、acceptable_elements、gold_answer / answer_key、known_distractor、trap_subtype、
  exclude_from_primary_score、pair_id、safety_critical / at_risk、rationale、source_boundary_ambiguity。
- question_id 只能在排序完成后作为 join key。

### [L2] D5 · indexed content

- owner_experiment: M5（metadata augmentation 消融）
- **决策：BM25 = `chunk.text` only；Vector = `chunk.text` only。section / doc / page / citation header 不进入 baseline retrieval representation；
  metadata augmentation 只作 future M5 ablation。**
- 依据（`MEASURED`）：6/31 道可答题在问题里点名手册或章节（FL06 / FL10 / FL15 / PR02 / PR04 / CD02），metadata 进索引会给这 6 题可预先识别的人为优势。

### [M] D6 · retrieval total order

- why_not_falsifiable: 同输入同输出与"tie-break 不读评测信息"是可复现性与实验有效性的方法要求。
- **决策：全序 = (−ranking_score, corpus_ordinal)；tie-break 只在 primary score 完全相同时生效；禁止 chunk_id 字典序与 doc/page 排序。**
  BM25 ranking score = raw BM25 score；vector = raw cosine；RRF 用确定性精确表示，不得因浮点累加顺序产生不确定 tie。
- 事实（`MEASURED`）：canonical corpus 有 52 组文本完全相同的 chunk（共 112 个），只看文本的打分器必然在这里产生精确 tie；39 个 gold chunk 不在其中。
- 落地：`core/contracts.py` 的 `Retriever.search` 契约 + `retrieval_order_key()`（见本日 contracts 条目）。

### [M] D7 · score semantics

- why_not_falsifiable: 持久化分数必须可区分、可归因，是审计方法要求。
- **决策：RAW_SCORE / RELEVANCE / MATCH_SCORE 三个字段分开，各带 raw_score_kind / relevance_kind / match_score_kind；不得只输出含义不明的 `score`。
  S8 normative artifact 必须保存足够信息，使 S9 不重跑 retrieval 即可重新分析。**
- **决策：`S9_CALIBRATION_SEMANTICS = DEFERRED`。** 本轮不裁"gold chunk 分数分布"与"all-hit max(match_score) 分布"哪一个是
  MIN_RELEVANCE 的最终校准 population（张力：contracts.py MIN_RELEVANCE 注释的目标句写 gold chunk 分数，判定式写 max over hits）。

### [L2] D8 · answer / trap

- owner_experiment: S8 / S9
- 事实（`MEASURED`，v5.3）：answer 31 / refuse 8（全部 type=trap）；absent_with_distractor 5（TR01 / 03 / 04 / 07 / 08）、
  absent_no_hit 3（TR02 / 05 / 06）；exclude_from_primary_score 只有 TR02 → "7 道计分陷阱 + 1 道排除"已确认。
- **决策：`ANSWER_RECALL_DENOMINATOR = 31`；8 道 refuse / trap 全部运行 retrieval；TR02 executed = YES、exclude_from_primary_score = YES；
  `PRIMARY_TRAP_DENOMINATOR = 7`；陷阱题逐题展示，不报百分比式强结论。**
- 至少保存：top-20 ranking、raw_score、relevance、match_score、max_match_score、top-1 document、BM25 empty-result flag。
- **决策：known_distractor rank 暂不定义**（`MEASURED`：known_distractor.source 是自由文本，页码口径混用）。

### [L2] D9 · multilingual

- owner_experiment: S8 / GATE-E3（证据）
- 事实（`MEASURED`）：en 36（answer 28 + refuse 8）、zh / tl / hi 各 1；pair gold：FL01↔ML01 相同、FL12↔ML03 相同、FL06（4）⊋ ML02（2）。
- **决策：overall answer metrics 用 31 题（含 multilingual）；English breakout 用 28 题；zh / tl / hi 逐题报告，不对 n=3 做百分比式强推断；
  pair_id 只做描述性比较；pair gold 不同（P-drug-freq）必须显式标注，不得直接等价比较。**

### [L2] D10 · S8 result artifact

- owner_experiment: S8
- **决策：不复用 EvalItemResult / `eval/results.csv`**（`CODE_FACT`：多个必填字段对纯检索无意义；`retrieval_scores` 是一列没有 kind 的数字；
  results.csv 是 M2 McNemar 的只追加输入）。
- **决策：建立独立的 S8 retrieval-result schema；normative artifact = deterministic JSONL**（UTF-8、ensure_ascii=False、固定字段顺序、
  separators=(",",":")）；**哈希的 normative artifact 内不放 wall-clock timestamp、不放 latency**；latency 只进 audit sidecar。
- Run identity 至少：schema_version、contracts_version、corpus_chunks_sha256、gold_chunk_map_sha256、testset_sha256、retrieval_variant、
  retrieval_config_digest、query_protocol_digest、metric_protocol_digest、total_order_protocol_digest、runtime identity；
  vector / hybrid 另加 embedder model/tag、model blob digest、embedding dimension、embedding protocol digest、embeddings artifact sha。
- per-question 至少：question_id、expected、type、language、gold_count、ranked hits ≤ 20（每个 hit：chunk_id、corpus_ordinal、raw_score、
  raw_score_kind、relevance、relevance_kind、match_score、match_score_kind），另存 max_match_score、first_gold_rank、gold_ranks、BM25 empty-result flag。
- metric 值尽量由纯函数从 normative artifact 重算；可派生的 aggregate 不作唯一事实来源。
  Audit / report CSV：per-k ANY_GOLD、GOLD_COVERAGE、ALL_MAPPED_GOLD、structural-unreachable flag、latency、diagnostics。
- 本轮 schema 不进 contracts.py：各 *_digest 的计算方式尚未裁决（见本日"留待人工确认的空白"）。

### [L2] D11 · BM25 baseline protocol

- owner_experiment: S8（baseline）/ M5（任何调参）
- **决策（人工接受）：** indexed text = `chunk.text` only；analyzer = NFC → casefold → Unicode 字母 / 数字 / combining marks 的最长连续串，
  query 与 document 对称；不用 stopwords、不做 stemming；数字保留；CJK 在 baseline 不做专门 segmentation（canonical corpus 无 CJK chunk；
  multilingual limitation 必须在报告中显式记录）；IDF = ln(1 + (N − n + 0.5) / (n + 0.5))，必须 ≥ 0；
  k1 = 1.2、b = 0.75 为 preregistered baseline default，不得在 v5.3 上调参；只返回 raw BM25 score > 0；不需要 persistent index artifact；
  BM25_SCORE_SATURATION 不参与 BM25 单路 ranking，只用于 score normalization 与 match_score semantics。
- **决策：`BM25_BASELINE_PROTOCOL_READY = YES`。**
- 落地：IDF 非负（s ≥ 0）作为长期不变量进入 contracts（`bm25_match_score()`）；analyzer regex、IDF 公式、k1 / b 属预注册，不进 contracts。

### [L2] D12 · vector

- owner_experiment: EMBEDDING_PROTOCOL_PROBE（单独一轮）
- 事实（`MEASURED`，只读文件）：bge-m3 manifest sha256 `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`；
  model blob 重算 sha256 = `daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`（= 文件名 = models.yaml digest）；
  GGUF v3、bert、embedding_length 1024、context_length 8192、pooling_type 2、F16。
  runtime：`ollama --version` 显示 server 0.34.0 / client 0.23.1，与 models.yaml `rt-2026-09-08` 的 0.33.3 不同。
- **决策：`MODEL_FILE_IDENTITY` 已测量存在；`MODEL_SELECTION_STATUS = NOT_FROZEN`；`EMBEDDING_PROTOCOL_IDENTITY = NOT_FROZEN`；
  `VECTOR_BASELINE_READY = NO`。**
- 下一步（单独一轮）：`EMBEDDING_PROTOCOL_PROBE` 至少测 endpoint、normalization、prefix、single vs batch equality、Run A/B determinism、
  runtime identity、CPU path、output dimension，并人工记录 model-selection decision。本轮不生成 formal embeddings artifact。

### [L2] D13 · hybrid

- owner_experiment: S8（baseline）/ M5（融合权重）
- **决策：baseline 不扫融合权重；方向 = unweighted RRF。RRF constant、per-route fusion depth、embedding dependency 尚未完全冻结
  → `HYBRID_BASELINE_READY = NO`；vector protocol closure 后再最终冻结。**
- **决策：任何 weight sweep 只作 exploratory，不得用于在同一 v5.3 上选择 M2 production configuration。**
- 已知叙述冲突（本轮未改，`CONTRACT_NARRATIVE_FOLLOWUP`）：contracts.py Hit docstring "融合权重是 L2 参数（M1c 要扫）"
  与边界声明 §5 "是 M1c/M5 要扫的对象" 与本条不一致。

### [L2] D14 · IndexManifest

- owner_experiment: 后续单独 contract round
- **决策：`INDEX_MANIFEST_CONTRACT_GAP = YES`；本轮不修 IndexManifest；S8 run artifact 自己记录完整 identity。**
- 缺口（`CONTRACT_FACT`）：没有 corpus_builder_name（仍是 parser_name）、construction_rules_sha256、embedder digest、
  embedding protocol identity、BM25 protocol / artifact identity；`built_at` 是墙钟时间。
- `INDEXMANIFEST_CONTRACT_FOLLOWUP`：IndexManifest.chunker_config 示例 `"target350_overlap60_min120"` 与 2026-09-25 [L3]"不得再写"
  及权威 builder identity 的格式不一致；本轮只登记，不改。

### [L3] 更正：CD01 "3 chunks"

- 事实（`MEASURED`，canonical GoldChunkMap `8cf9f3be…`）：CD01 = **5 chunks / 3 citations**（SMM p73 {0,1} L2；ERM p105 {0,1} L2；
  SMM p74 {0} L1），跨 2 份手册。
- 事实："3 chunks" 出现于本文件 2026-09-08 "M2 主模型选定"条目、contracts.py `TOP_K_CONTEXT` 注释、执行手册 S3 表与 S8.4、实施方案 §10.2。
  写下时评测集 gold_chunk_ids 为 39/39 空（实施方案 §14.3），因此 "3 chunks" **从未由 canonical GoldChunkMap 实测支持**（起源 `NOT_VERIFIED`）。
- 推论（`DERIVED`；输入：contracts.pack_context 代码 + canonical chunk 的 est_prompt_tokens + canonical map）：即使 gold 以最优顺序排在最前，
  CD01 的 5 个 gold chunk 合计 est_prompt_tokens 1386 > 765，在当前可执行预算下不可能全部打包。
- **更正：以 5 chunks / 3 citations 为准。** 2026-09-08 M2 主模型选定的理由 ① 部分以 "3 chunk" 为前提；另外两条独立理由不受影响；本更正不重开模型选型。
- 落地：contracts.py 注释与执行手册 S8.4（当前 S8 指令）已改；执行手册 S3 表、实施方案 §10.2 只登记，未改。

### [L3] LOG_INTEGRITY_DEFECT：commit 18f556e

- 事实（`CODE_FACT`）：commit `18f556eb798282ac620881785943df23f777e09e` 的 message 为
  "contract: 用 phi4-mini 实测校准 MAX_PROMPT_TOKENS 与 PROMPT_OVERHEAD_RESERVE_TOKENS；修正 CONTEXT_PACK_MARGIN 使安全不等式成立"，
  但 diff 只有 5 个文件（`experiments/gate2_raw/_s4a9a_prompt_overhead.log`、`_s4a9b_ttft_sweep.log`、`_s4a9c_chars_per_token.log`、
  `prompts/system_ac_draft.txt`、`prompts/system_bd_draft.txt`）；`core/contracts.py` 未改（`git log -- core/contracts.py` 不含该 commit）。
- **决策：`LOG_INTEGRITY_DEFECT = CONFIRMED`。不改 git history。**
- 明确：`950 / 206 / 0.86 / 639` 是 experimental / historical candidate，不是 executable contract；
  executable contract 仍是 `1050 / 200 / 0.90 / 765`（与 2026-09-22 "executable budget contract 与 S4a.9 候选值必须分离" 一致）。

### [L3] 更正：GoldChunkMap 的 Git 状态叙述

- 事实：2026-09-28 决定 `GOLD_CHUNK_MAP_DURABILITY_POLICY = TRACK_CANONICAL_MAP_AND_REPORT_IN_GIT`；canonical map / report 已入 Git（`7176505`）。
- 更正：2026-09-25 [M]"GoldChunkMap 确定性：删除 built_at" 的 why_not_falsifiable 写 "GoldChunkMap 不进 Git" —— 该前提已被 2026-09-28 决定取代；
  该条目的决策（删除 built_at、逐字节可再生）不变。
- 落地：contracts.py GoldChunkMap docstring 两处 "不进 Git" 叙述已改为 "派生、可再生，canonical 映射已冻结入 Git"；schema 与校验未改。
  关闭 2026-09-28 登记的 contracts 措辞 followup；`.gitignore` 顶部注释仍未改。

### [L3] 更正：3309 chunks

- 事实（`MEASURED`）：canonical corpus = 3409；3309 不属于已记录的三代语料（3383 / 3413 / 3409）。
- 落地：contracts.py 边界声明 §6 的当前性陈述改为 3409（≈ 14 MB，结论不变）。实施方案 / DOCUMENT_MAP / 执行手册中的 3309 只登记，未改。

### [L3] contracts.py 本轮改动（待人工审核 diff）

- 改动（全部是 0.3.1 版本内追加，`CONTRACTS_VERSION` 未递增）：
  - R1 `Retriever.search` 确定性全序 + `retrieval_order_key()`；
  - R2 `Hit` 写明 RAW_SCORE / RELEVANCE / MATCH_SCORE 的区分与持久化 kind 要求；
  - R3 BM25 原始分 s ≥ 0（IDF 非负）前提不变量 + `bm25_match_score()`；
  - R4 叙述更正：CD01、GoldChunkMap 的 Git 状态与多 citation 逻辑、3309、PROMPT_OVERHEAD_RESERVE_TOKENS 的 S8 顺序。
- 未改：全部数值常量、Chunk / Citation / EvalItem / GoldChunkMap schema 与校验 / EvalItemResult / IndexManifest / pack_context / MatchLevel。
- 测试（`MEASURED`）：新增 `tests/test_contracts_retrieval.py`（18 个）；5 个测试模块共 176 个 OK；变异检查 —— 去掉行序 tie-break、
  行序降序、接受负 s、常数 1.0 映射 —— 4 个变体都被拦下。canonical GoldChunkMap 在改后的 contracts 下仍通过 `validate_gold_chunk_map`，序列化逐字节一致。
- **待人工裁决：`CONTRACTS_VERSION` 是否递增。** 现行规则只要求 Chunk 结构或引用语义改变时递增；若递增，contracts_version="0.3.1"
  的 canonical GoldChunkMap 将无法通过 `validate_gold_chunk_map`（需要新的 data commit 再生）。本轮未递增。
- 本轮未进入 contracts：S8 result schema（*_digest 定义未裁决）、EVAL_RECALL_K_SET、BM25 k1 / b / analyzer / IDF 公式、RRF constant / depth、
  packed scenarios、reranker observation k、180 s ceiling、multilingual 报告布局。
- 已知未处理的 contracts 叙述（只登记）："M1c 要扫融合权重"（Hit docstring、边界 §5）；Reranker docstring 判据 "Recall@k_context ≈ Recall@20"
  （k_context 是逐题变量）；TOP_K_CONTEXT 注释中的 Recall@3 / @5 与 Recall@1 / @2 / @5 口径；MIN_RELEVANCE 目标句与判定式的 population 张力
  （S9 deferred）；IndexManifest.chunker_config 示例。

### [L3] 留待人工确认的空白（不阻塞本条目审核；阻塞 BM25 实现开工）

- S8 prereg artifact 的路径：仓库有两种既有惯例 —— DOCUMENT_MAP 记载的 `experiments/M2_preregistration.md`（里程碑级，位于 experiments/ 根）
  与实际使用的 `experiments/<line>/_<step>_prereg.txt`（测量线子目录）；两者都没有 M1c / S8 先例 → 本轮未创建，路径待人工指定。
- 单路 relevance 的定义：D6 定了 ranking score，D11 定了 match_score；BM25 / vector 单路的 relevance（及 relevance_kind）尚未定义。
- RAW_SCORE 与 corpus_ordinal 从 retriever 到 S8 artifact 的载体：Hit 当前不携带二者；需决定是扩展 Hit，还是另定接口。
- corpus_ordinal 的基数（0-based / 1-based）。
- 各 *_protocol_digest / retrieval_config_digest 的计算方式。

### [L3] docs followup（本轮只登记）

- 执行手册 S8.2：仍引用不在 HEAD 的 `ClaudeCode_任务序列_v4.md`「任务 4」。
- 执行手册 S8.3：`CORPUS_SHA=$(shasum …)` 从被使用的文件自算（违反 2026-09-28 [L1] identity assertion 不得 self-derive）；`--k 1 2 3 20` 与 D2 不一致；
  `--retrievers bm25 vector hybrid` 与 D12 / D13（vector / hybrid NOT_READY）不一致；306 推导块。
- 执行手册 S8.4 / S8.5：Recall@1/2/3/20 清单、"cross_doc 按每份手册算"判据、"融合方式是模块顶部常量"、reranker 用 Recall@2 判 —— 与 D1 / D2 / D13 不一致。
- 执行手册 S1.4：仍安装 lancedb "给 S8 用"；S3 表 CD01 "3 chunk"；S4a.9 状态块 "must rerun after Phase B"；S5c 标题 "阻塞 S6"。
- 实施方案 §10.2（CD01 3 chunk、306）、§10.3（把 950 / 206 / 0.86 / 639 列为"当前值"）、§15.2 / §9（3309）；DOCUMENT_MAP（3309、任务序列 v4）。


## 2026-10-01 · S8 / M1c protocol apply blocker closure（apply for review）

证据标记沿用上一条目。作用域：HEAD `d28d130de33ec4abf79b67cff12dfd9e33b885be`（== origin/ship-rag，0 / 0）；
上一条目留下的候选 diff（DECISIONS.md / core/contracts.py / 执行手册_v4.md + 未跟踪 tests/test_contracts_retrieval.py）为本轮基线。
依据：人工裁决 A（prereg 路径）/ B（corpus_ordinal）/ C（BM25 relevance）/ D（Hit 不改、独立 record）/ E（TTFT，本轮不改）。
本条目由 AI 按裁决机械落地并记录审计，待人工审核 diff。上一条目的文字未改动；其"留待人工确认的空白"由本条目逐项关闭或改记。

### [L3] 输入身份复核

- `MEASURED`（EXPECTED 取 2026-09-28 Formal S6 条目字面量，ACTUAL 只用于比较）：corpus `c8978777…` / 3409 行；testset `05614407…` / 39 行；
  map `8cf9f3be…`；report `f48018cb…`；page_quality `69842896…` / 1335；builder `kaiva_phase_b_builder_v1` / `e89e6f94…` /
  `chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350` —— 全部相等；`validate_gold_chunk_map` PASS，重序列化逐字节相等。
  `INPUT_IDENTITY_DRIFT = NO`。token 数值常量只读：1050 / 200 / 0.90 / 765 / 4 / 14 / 5 / 20 / 350 / 120 / 10.0 / 0.35 / 10.0（未改）。

### [L3] CONTRACTS_VERSION 语义审计（只读；决策待人工）

- 源与消费方（`CONTRACT_FACT` / `CODE_FACT`）：

  | locator | 角色 | 比较语义 | 失效后果 |
  |---|---|---|---|
  | contracts.py `CONTRACTS_VERSION` 注释 | 自述"索引包与运行时的一致性校验依据（见 IndexManifest）"；递增条件"任何影响 Chunk 结构或引用语义的改动**都必须**递增"（必要条件，未说"只有"） | — | — |
  | contracts.py 0.2.0 改动记录 P5 | "它会写进 IndexManifest → 索引包 → EvalItemResult → M2 预注册" | — | — |
  | `IndexManifest.contracts_version` | 船端启动校验，"任一项不匹配 → IndexIntegrityError 拒绝启动"；约定 9 岸船共用同一份 contracts | 相等 | 整个索引包被拒（尚无实例） |
  | `GoldChunkMap.contracts_version` 注释 / 0.2.0 P4 | "解析语义一变，旧映射即不能作为当前 canonical 映射" / "切片语义一变旧映射即作废" | — | — |
  | `validate_gold_chunk_map` | `gold_map.contracts_version != CONTRACTS_VERSION` → ContractViolation | 严格相等 | canonical map 不可再作为当前映射 |
  | `scripts/resolve_gold_chunks.py:327` | 写入 `contracts.CONTRACTS_VERSION` | 生产方 | — |
  | `EvalItemResult` | **无** contracts_version 字段（P5 所说的 EvalItemResult 承载未实现；有 code_commit） | — | — |
  | 其他 artifact（corpus、page_quality、OCR accepted、9c-final、experiments/*） | 不记录（0.3.0 / 0.3.1 失效复核已确认） | — | — |
  | tests | `test_contracts_gold_chunk_map` 断言 =="0.3.1" 且拒绝 0.2.0 / 0.3.0 | 相等 | — |

- 历史（`CODE_FACT`，`git show <commit>:core/contracts.py`）：ae33bc4 = 0.2.0-draft；a1973ef = 0.2.0；b866134 = 0.3.0；d30ed34 = 0.3.1。
  **每个 contract commit 都递增且内容与版本一一对应**；0.2.0 的 P1（relevance / match_score 分离）本身就是检索语义改动，随该版递增。
- 逐问：
  1. 注释称追踪"索引包与运行时一致性"，递增条件写 Chunk 结构 / 引用语义 —— 二者口径不同。
  2. GoldChunkMap 保存它，是为记录"由哪版解析语义生成"。
  3. 是：严格相等，无兼容表。
  4. 只改检索语义时，canonical map 的字节、corpus、testset、builder identity、解析语义都未变；按本项目既有失效判据
     （2026-09-25：artifact 是否消费被改变的语义，而非是否出现旧版本号），map **不应**失效；但若递增，严格相等会使其机械失效 —— 判据与校验器冲突。
  5. 是：IndexManifest 按"整模块 / 岸船一致"解释；GoldChunkMap 按"解析 / 切片语义"解释；EvalItemResult 不承载。
  6. Git 历史内：**NO**。工作区：**YES** —— 当前候选 `core/contracts.py`（未提交，本轮前 `c14a791f…`）与 d30ed34（`b8560e7e…`）内容不同，
     版本号同为 0.3.1；若原样提交，Git 内即出现 YES。
- **结论：`CONTRACTS_VERSION_SEMANTIC_CLASS = C_MIXED_AMBIGUOUS`。**
- 最小修复 proposal 与兼容性（均未实施）：
  - **Option A（整模块版本）**：本轮递增（如 0.4.0）。兼容性：canonical map 的 `contracts_version="0.3.1"` 无法通过 `validate_gold_chunk_map`；
    要么再生 map（字节仅 contracts_version 一处不同 → 新 sha，S6 canonical identity 改变，需新 data commit + DECISIONS），
    要么同时采用 Option C。单独 A = 对一个未消费检索语义的 artifact 做虚假失效。
  - **Option B（只追踪 chunk / citation 语义）**：保持 0.3.1，把注释改为该语义并为整模块另立 identity。兼容性：map 不受影响；
    但与 IndexManifest 的岸船一致用途、约定 9、P5、以及 0.2.0 把检索语义改动计入版本的历史相悖；IndexManifest 需新增整模块字段（D14 缺口内）。
  - **Option C（validator 绑定更窄的语义版本）**：CONTRACTS_VERSION 保持整模块含义并照常递增；GoldChunkMap 的接受判据改为绑定
    "gold 解析语义版本"（新常量），或在 validator 中显式列出与当前解析语义兼容的 contracts 版本集合。兼容性：若保留字段名 `contracts_version`
    并用兼容集合，map 字节与 sha 不变；若改字段名，map 需再生。代价：多一个须人工维护的语义版本 / 兼容表，以及 validator 语义变更。
  - AI 倾向（仅供裁决参考）：A + C 的"兼容集合"变体 —— 整模块含义与历史、IndexManifest 一致，且不使冻结 map 失效。
- **决策：`CONTRACT_VERSION_DECISION = BLOCKED`（待人工）。本轮未改版本号。**
  对 S8 的影响：record 的 schema 不依赖版本号取值，可在当前版本下冻结；为防止"同版本号不同内容"污染 S8 证据，
  prereg run identity 追加 `contracts_sha256` 与完整 `code_commit`。但本裁决必须在 protocol commit 之前给出，否则提交即造成问 6 的 Git 内 YES。

### [M] corpus_ordinal（人工裁决 B 落地）

- why_not_falsifiable: 行序基数是表示约定，不是关于系统的经验主张。
- **决策：`corpus_ordinal` = canonical `corpus/chunks.jsonl` 中的 zero-based physical line ordinal（第一行 = 0）；不是 pdf_page、不是页内序号、
  不是 chunk_id 字典序位置；只用于 deterministic tie-break 与 provenance / audit。**
- 落地：`RetrievalResultRecord` docstring + `validate_retrieval_records` 校验 `corpus_chunk_ids[corpus_ordinal] == chunk_id`；
  测试含真实 canonical corpus 首 / 末行（0 / 3408）与 1-based 漂移拒绝。

### [L2] BM25 relevance（人工裁决 C 落地）

- owner_experiment: S8（baseline）/ S9（校准）
- **决策：BM25 baseline 的 raw_score = s；relevance = match_score = `bm25_match_score(s)`；ranking 只用 raw_score。数值相同、字段与 kind 分开。**
- 落地：Hit.relevance docstring 增加 bm25 baseline 一行（vector / hybrid relevance 未冻结）。
- 非 BM25 证明（`MEASURED`）：合成 RRF 向量（raw = 精确 Fraction，relevance = raw / (2/61)，match_score 为手写的各路 max 且与排名不单调）下，
  记录、序列化、全序、"阈值面向 match_score"均成立；把 match_score 写进 relevance（互换）被 `validate_retrieval_records` 拦下。
  变异检查：序列化把 relevance 写进 match_score、或把 match_score_kind 写进 relevance_kind —— 两个变体**只**被合成非 BM25 向量拦下，BM25 用例全部照常通过。

### [L2] RetrievalResultRecord（人工裁决 D 落地）

- owner_experiment: S8（及后续一切检索评测）
- **决策：Hit 不改。新增独立逐 hit 载体 `RetrievalResultRecord`，放在 `core/contracts.py`。**
  依据（ownership / reuse / dependency direction）：生产方是 `components/retrievers/*`，消费方是评测 runner（eval / experiments）；
  依赖树规定 component 只能 import `core.contracts` —— 放在 eval/ 或实验 schema 则 retriever 无法 import，放在 components/retrievers/ 下
  则 bm25 / vector / hybrid 无法共享同一定义（且 component 之间互不 import）。它是 executable cross-retriever interface。
- 字段：chunk、chunk_id（chunk.id 的只读投影）、corpus_ordinal、raw_score（float 或 Fraction）、raw_score_kind、relevance、relevance_kind、
  match_score、match_score_kind。不含 gold / eval 信息、latency、墙钟时间；rank = 序列位置，不存。
- 产出接口：`Retriever.search_records(query, k)`，与 `search` 一一对应（同一次排序的两种投影）；序列校验 `validate_retrieval_records`；
  序列化 `retrieval_record_json_object` / `serialize_retrieval_record`（字段顺序 `RETRIEVAL_RECORD_JSON_FIELDS`，Fraction → "p/q"）。
- 边界：逐 hit record 进 contracts；S8 逐题行 schema、run identity、kind 取值词表留在 `experiments/M1c_preregistration.md`
  （上一条目 D10 "schema 不进 contracts" 对后者仍成立）。
- 待审核的形状选择（AI 提案）：方法名 / 签名 `search_records`；chunk_id 作为属性而非独立字段；relevance / match_score 只接受 float、raw_score 只接受 float / Fraction。

### [M] Digest protocol

- why_not_falsifiable: 规范字节与哈希算法是可复现性的方法要求。
- 既有口径（`CODE_FACT`）：`ingest/builder_identity.construction_rules_identity`（ensure_ascii=False、无 sort_keys、payload 为有序 list）；
  `components/parsers/ocr_artifact`（sort_keys=True、ensure_ascii=True）。均为组件内私有，contracts 无统一 helper。二者不迁移（会改变已冻结身份）。
- **决策：新增 `core.contracts.canonical_json_bytes` / `canonical_sha256`：canonical JSON（UTF-8、ensure_ascii=False、sort_keys=True、
  separators=(",",":")、allow_nan=False、无末尾换行、不做 Unicode 规范化）→ SHA-256。** 只接受 dict（str 键）/ list / tuple / str / int / bool /
  None / 有限 float；其余抛 ContractViolation。放 contracts 的理由：S8 起各实验的 *_digest、未来 IndexManifest 的协议身份，以及可能由 retriever
  组件导出的配置 payload 都需同一定义，而组件只能 import contracts。
- 冻结值（prereg §10，`shasum` 对代码块字节独立复核一致）：`total_order_protocol_digest = 99c87596…`、`query_protocol_digest = e26afbf3…`、
  `metric_protocol_digest = e78d361f…`；`retrieval_config_digest`（bm25）未计算，见下一条。

### [L2] 新缺口：BM25 query term multiplicity（`BM25_BASELINE_PROTOCOL_READY` 改记为 NO）

- owner_experiment: S8
- 事实（`MEASURED`，只读 probe：按 D11 analyzer 切分 39 道 question，未计算任何 BM25 分数）：21 / 39 题含重复 token（58 次额外出现），
  含实词（FL06 alcohol×4 / testing×3；CD02 internal×3；PR04 permit×2、work×2；PR02、FL07、FL15、ML02 等）。
- D11 冻结了 analyzer、IDF、k1、b、过滤与 indexed text，但**没有规定 query 中重复 token 计一次（SET）还是每次出现都计（MULTISET）**；
  两者都是常见"标准 BM25"实现，对上述 21 题给出不同排序。同一裁决还需给出数值求值约定（求和顺序、IDF 求值式），因其决定 raw_score 末位比特与 artifact 字节。
- **决策：`BM25_BASELINE_PROTOCOL_READY` 由上一条目 D11 的 YES 改记为 NO，直到人工裁决本项；AI 不选择。**
  AI 倾向（仅供参考）：MULTISET（rank_bm25 / Lucene 多子句的行为），求和按 token 在 query 中的出现顺序。
- 本项裁决后：按 prereg §6.4 字段清单计算 `retrieval_config_digest`，以"写于结果之前"的 amendment 写入 prereg。

### [L2] ALL_MAPPED_GOLD known bias 与 CN03

- owner_experiment: S8
- **决策：`ALL_MAPPED_GOLD_STATUS = STRICT_MAP_UNION_DIAGNOSTIC_WITH_KNOWN_SUPPORTING_CITATION_BIAS`。** 它是 strict map-union diagnostic，不是 answer-completeness metric。
- CD01 / FL07 / FL06 含支撑 acceptable 或仅佐证的 citation（D1-A probe，`DERIVED`）。在 probe 角色成立的前提下，从 report.csv 机械并出必需 citation 的 cover：
  CD01 = 4 chunks（SMM:p73:0/1 + ERM:p105:0/1；非必需 SMM:p74:0）；FL07 = 2（QMM:p32:4/5；非必需 QMM:p34:2）；FL06 = 3（QMM:p33:0/1/2；佐证 QMM:p34:0，probe 强度"中"）。
- 低 ALL_MAPPED_GOLD 不得自动解释为 retrieval failure 或 insufficient answer evidence；报告须同时给出结构上限（prereg §7.2，由 map 的 |gold| 推出）。
- **`CN03_CITATION_LOGIC = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW`**：required_elements / canonical evidence 指向 ERM p14 必需，rationale 表达 OR 意图，二者不能同时推出唯一 citation logic。
  testset 未改；不替人裁。

### [L3] 预注册文件

- 人工裁决 A：路径 `experiments/M1c_preregistration.md`（milestone 级，与 M2 同级）。已创建。`PREREG_BEFORE_RESULTS = YES`（仓库中无任何 retriever 实现，未运行任何检索）。
- 冻结内容：query protocol、leakage policy、indexed text、k = (1, 2, 3, 5, 20)、ANY_GOLD / GOLD_COVERAGE / ALL_MAPPED_GOLD 与其 known bias、CN03 冲突、
  answer / refuse 分母、multilingual 报告、确定性全序、corpus_ordinal zero-based、BM25 analyzer / 非负 IDF / k1 = 1.2 / b = 0.75、relevance / match_score 语义、
  retrieval result record、JSONL 确定性、digest protocol、fixed-k / packed 分离、real retrieval-window measurement、reranker k = 2 / 3 与阈值 NOT_FROZEN、
  TTFT 两个状态、evidence coverage ≠ answer quality、operating point 等 M2、vector / hybrid NOT_READY、IndexManifest gap。
- `PROPOSED`（随审核确认）：BM25 kind 取值（bm25_raw / bm25_match_score / bm25_match_score）；逐题行字段顺序；rank 从 1 开始（与 0-based corpus_ordinal 不同基）；
  文件布局（首行 run identity）；analyzer "L\* / N\* / M\*" 是对 D11 文字的机械翻译。
- `NOT_FROZEN`：query term multiplicity 与数值求值约定（阻塞）；`retrieval_config_digest`。

### [L3] TTFT（人工裁决 E，未改）

- `TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；`MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`；
  `S8_EVIDENCE_COVERAGE_IS_ANSWER_QUALITY = NO`。已写入 prereg §12；数值常量未动。

### [L3] contracts.py 本轮改动（叠加在上一条目候选之上，待人工审核 diff）

- 新增：`RetrievalResultRecord`、`Retriever.search_records`、`validate_retrieval_records`、`RETRIEVAL_RECORD_JSON_FIELDS`、`retrieval_record_json_object`、
  `serialize_retrieval_record`、`canonical_json_bytes`、`canonical_sha256`；Hit docstring 增加 bm25 relevance 一行与指向 record 的说明（Hit 字段未改）。
- 修改上一轮候选的一处叙述（文件末"0.3.1 版本内追加"块）：原写"版本规则只针对 Chunk 结构或引用语义"——审计显示这只是互相冲突的几种读法之一，
  原样保留会把未裁决的读法当作事实；改为记录审计结论与"提交前须裁决"。R1–R4 文字未改。
- 未改：全部数值常量、CONTRACTS_VERSION、Chunk / Citation / EvalItem / Hit 字段 / GoldChunkMap schema 与校验 / EvalItemResult / IndexManifest / pack_context / MatchLevel。
- 测试（`MEASURED`）：`tests/test_contracts_retrieval.py` 18 → 55；5 个模块共 213 OK。变异检查 11 个真实变体全部被拦（见 blocker closure 会话报告）；
  canonical GoldChunkMap 在改后 contracts 下仍 PASS、重序列化逐字节相等；`construction_rules_identity` 未变。

### [L3] 上一条目"留待人工确认的空白"的去向

- prereg 路径 → 已关闭（裁决 A）。单路 relevance → BM25 已关闭（裁决 C）；vector / hybrid 仍 NOT_FROZEN（随各自 protocol）。
- RAW_SCORE 与 corpus_ordinal 的载体 → 已关闭（裁决 D：RetrievalResultRecord）。corpus_ordinal 基数 → 已关闭（裁决 B：0-based）。
- *_digest 计算方式 → 算法已冻结，3 / 4 个 payload 已冻结；`retrieval_config_digest` 等 query term multiplicity 裁决。
- 新增开放项：CONTRACTS_VERSION 语义（BLOCKED）；BM25 query term multiplicity（阻塞 BM25 实现）。


## 2026-10-01 · S8 / M1c final protocol closure：版本拆分 + BM25 MULTISET（apply for review）

作用域：HEAD `d28d130de33ec4abf79b67cff12dfd9e33b885be`（== origin/ship-rag，0 / 0，staged 空）；候选 diff 只来自前两轮 protocol apply
（开场 sha：DECISIONS `b7691765…`、contracts `3138c16e…`、执行手册 `74a1fe4d…`、tests/test_contracts_retrieval `c7c2dd70…`、prereg `81b6f46f…`）。
依据：人工裁决 A（BM25 MULTISET）/ B（fsum 累加）/ C（版本 SPLIT）/ D（legacy 兼容）/ E（两层测试）/ F（kind 名）/ G（rank / ordinal / 布局 / 接口）。
本条目由 AI 按裁决机械落地，待人工审核 diff。前两个同日条目的文字未改动。

### [L3] 输入身份复核

- `MEASURED`（EXPECTED 取 2026-09-28 Formal S6 字面量）：corpus `c8978777…` / 3409；testset `05614407…` / 39；map `8cf9f3be…`；report `f48018cb…`；
  page_quality `69842896…` / 1335；builder `kaiva_phase_b_builder_v1` / `e89e6f94…` / `chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350`。
  `INPUT_IDENTITY_DRIFT = NO`。token 数值常量只读、未改。

### [L1] CONTRACT_VERSION_SEMANTICS_SPLIT（人工裁决 C / D 落地）

- falsified_if: 出现一个只改检索 / 打包 / 生成侧契约（不在 GOLD_CHUNK_MAP_SEMANTICS_VERSION 递增清单内）的改动，却确实改变了某份 GoldChunkMap 的正确性或解析结果。
- 原则：invalidation 由实际 dependency 决定，不由"都位于 core/contracts.py"决定。审计前状态 `C_MIXED_AMBIGUOUS`（同日 blocker closure 条目）。
- **决策：`CONTRACTS_VERSION` = 整个可执行契约模块的版本，0.3.1 → `0.4.0`（每个 `contract:` commit 递增，与历史一致）；
  新增 `GOLD_CHUNK_MAP_SEMANTICS_VERSION = "0.3.1"`，是 GoldChunkMap 兼容判定的唯一依据；其递增清单（实际依赖）写在常量注释中：
  Chunk / Citation / EvalItem 被读字段、normalize_text / split_quote_fragments / is_sole_match_eligible / QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH、
  MatchLevel / FORMAL_MATCH_LEVELS / MATCH_LEVEL_REASON / GOLD_CHUNK_MAP_REPORT_COLUMNS、GoldChunkMap 字段 / 序列化 / 文件名、validate_gold_chunk_map 接受条件。**
- migration design 比较（前提：canonical map 字节不变）：

  | | D1 新增显式字段 + legacy 规则 | D2 保留字段名 contracts_version、收窄语义 | D3 schema 不变、validator 维护兼容表 |
  |---|---|---|---|
  | canonical map 字节 | 不变（新字段默认 None，序列化省略） | 不变 | 不变 |
  | schema 清晰度 | 高：contracts_version 在 GoldChunkMap / IndexManifest 中同义（整模块），兼容判定字段名即语义 | 低：同名字段在 GoldChunkMap 指语义版本、在 IndexManifest 指整模块 | 中：字段名仍是 contracts_version，语义靠表外知识 |
  | 未来歧义 | legacy 规则只服务拆分前闭集，未来映射显式自述 | 高：未来读者无法从字段名区分两种含义 | 中：每次整模块递增都必须同步维护表，漏维护 = 静默失效或静默放行 |
  | validator 复杂度 | 一个 helper（约 20 行）+ 一个闭集常量 | 最小 | 一张随版本增长的表 |
  | 向后兼容 | legacy 映射按规则接受；拆分后缺字段的映射拒绝 | 接受 | 接受（若表已维护） |
  | 未来生成 | resolver 写显式字段（一行） | resolver 须写语义版本进 contracts_version，与整模块版本冲突 | resolver 不变，但写入的是整模块版本，兼容只能查表 |
  | IndexManifest | 不受影响；contracts_version 在两处同义 | 两处不同义 | 不受影响 |

  **选择 D1。**
- legacy 规则（写入 GoldChunkMap docstring 与 `_gold_chunk_map_semantics_version_of`）：`gold_chunk_map_semantics_version` 缺失 → 当且仅当
  `contracts_version ∈ GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS = {"0.2.0", "0.3.0", "0.3.1"}` 时把 contracts_version 读作语义版本；否则拒绝。
  字段存在而 contracts_version 属于该闭集 → 拒绝。闭集取自 git 历史（`CODE_FACT`：a1973ef 0.2.0 / b866134 0.3.0 / d30ed34 0.3.1 的 GoldChunkMap
  有 contracts_version 字段；ae33bc4 0.2.0-draft 没有），拆分是一次性事件，闭集不增长。不看文件名 / 路径 / mtime / 日期，不做版本区间推断。
  闭集的作用：防止将来语义版本与某个拆分后整模块版本号碰撞时，缺字段的映射靠"两数相等"蒙混通过（有专门测试）。
- **canonical map 仍有效（`MEASURED`）：字节 2026 / sha `8cf9f3be…` 不变、未再生；0.4.0 下 `serialize_gold_chunk_map(parse(file))` 逐字节等于文件；
  `validate_gold_chunk_map` PASS（legacy 规则 → 语义版本 0.3.1）。**
- resolver（compatibility-only）：`identity_map()` 增加一个关键字 `gold_chunk_map_semantics_version=contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION`；
  `contracts_version` 仍写 CONTRACTS_VERSION（provenance）。AST 证明：45 个顶层语句中只有 identity_map 不同，且只多这一个关键字；
  resolve_quote / _minimum_covers / resolve_all / build_mapping / load_corpus / load_testset / write_report / run 的 AST 不变。
- 真实数据（`MEASURED`，输出写入会话 scratch，未触碰 canonical）：用 0.4.0 resolver 对 canonical 输入再生 → mapping 完全相同；report.csv 逐字节相同
  （`f48018cb…`）；map 只有两处不同：contracts_version 0.3.1 → 0.4.0、新增 gold_chunk_map_semantics_version = 0.3.1。
- 对 2026-09-28 Formal S6 `falsified_if`（"同一冻结输入下 resolver 不能逐字节再生这份 map / report"）的影响，记录供人工判断：
  report 在新代码下仍逐字节再生；map 的 mapping 逐项再生，但 map 文件字节因版本 identity 字段而不同 —— 任何 CONTRACTS_VERSION 递增都会如此。
  逐字节再生 canonical map 仍可在其生成代码（contracts d30ed34 + resolver 8719761）上完成。AI 判断这不是 mapping 可复现性的失败，未据此改任何东西。
- IndexManifest：未改；其 contracts_version 继续表示整模块版本（与约定 9 岸船共用同一份 contracts 一致）。`INDEX_MANIFEST_CONTRACT_GAP = YES` 不变。

### [L2] BM25 query term semantics（人工裁决 A）

- owner_experiment: S8
- **决策：`BM25_QUERY_TERM_SEMANTICS = MULTISET`。** analyzer 产生的 query token 序列保留重复，每次出现贡献一次 term contribution；不得先转成 set / unique terms。
- 理由（人工）：SET 是额外的信息删除；MULTISET 保留 query term frequency；document 侧已保留 tf，不应无证据地在 query 侧删除 frequency。
- protocol-impact evidence（`MEASURED`，不是检索结果）：21 / 39 题含重复 analyzer token（58 次额外出现）；FL06 alcohol×4 / testing×3、CD02 internal×3、PR04 permit / work 各×2。

### [M] BM25 deterministic accumulation（人工裁决 B）

- why_not_falsifiable: raw_score 是全序主键，累加方式必须固定以保证同输入同字节，这是可复现性方法要求。
- runtime gate（`MEASURED`，CPython 3.12.14 / arm64 / Darwin）：`math.fsum` 存在；20000 个非负随机向量上 == 精确和的正确舍入 20000 / 20000，
  打乱顺序后结果改变 0 / 20000；朴素循环正反序不等 1196 / 2000；3.12 内建 `sum()` 已改用补偿求和（`sum([1e16, 1.0, -1e16])` = 1.0、朴素 = 0.0）。
  **无 compatibility blocker。** fsum 对 inf / nan 不报错 → 由 helper 先拒绝。平台注记：x87 扩展精度构建可能偶发末位双重舍入（CPython 文档），
  x86-64 / arm64 不受影响，船端实测属 M6。
- **决策：`BM25_ACCUMULATION = MATH_FSUM_QUERY_TOKEN_ORDER`**：贡献按 analyzer 输出的 query token 物理顺序（含重复）枚举，`math.fsum` 求和。
  可执行形式 `core.contracts.bm25_accumulate(query_tokens, term_contribution)`：只接受 list / tuple（set / frozenset / dict / 视图 / Counter /
  生成器 / str → ContractViolation），每次出现按序恰调用一次 term_contribution，贡献须有限、≥ 0、非 bool。放在 contracts 的理由：
  未来 BM25 组件只能 import core.contracts；与 bm25_match_score 同处。IDF、tf 归一化式、k1 / b、analyzer 仍属预注册，不进 contracts。
- 注（`DERIVED`）：fsum 的结果与顺序无关，"按 query token 顺序"约束的是枚举 / 调用顺序（测试以调用记录验证），不是数值；
  单个 term contribution 的浮点求值式由实现固定、以 code_commit + runtime identity 绑定；确定性验收是同 code_commit / 同 runtime 的 Run A == Run B。

### [M] SET-vs-MULTISET tuning prohibition

- why_not_falsifiable: 禁止在评测集上择优选择协议是实验有效性的方法要求。
- **决策：SET-vs-MULTISET selection on v5.3 is prohibited test-set tuning.** 不得在 v5.3 上比较 SET 与 MULTISET（或其他 query term 语义）后择优。已写入 prereg §6.3。

### [L2] BM25 score kind 名（人工裁决 F）

- owner_experiment: S8
- **决策：`raw_score_kind = "bm25_raw"`、`relevance_kind = "bm25_saturation"`、`match_score_kind = "bm25_saturation"`**（取代上一条目的提案 bm25_match_score）。
  kind 描述数怎么算出来，不是字段名；BM25 baseline 上 relevance == match_score 且两 kind 相等，允许且正确；字段语义仍不同。
- 合成非 BM25 测试继续证明 relevance ≠ match_score 可表达；collapse / swap 变异（序列化中 relevance_kind ← match_score_kind、relevance ← match_score、
  match_score ← relevance）全部被拦，且**只**被合成非 BM25 向量拦下。

### [L3] rank / ordinal / 布局 / 接口（人工裁决 G）

- **决策（FROZEN）：retrieval rank 1-based；corpus_ordinal 0-based physical line ordinal；prereg 并排写出、不统一。**
- **决策：S8 normative JSONL 首行 = run identity；之后每行一题，按冻结评测集顺序。**
- **决策：`search_records(query: str, k: int = TOP_K_RETRIEVE)` 名称与签名 FROZEN。**
- 逐题字段顺序按上一稿提案机械冻结：`question_id, expected, type, language, gold_count, empty_result, max_match_score, top1_doc_id,
  first_gold_rank, gold_ranks, hits`。
- 为使首行可确定性序列化而做的机械细化（AI，随本 diff 审核）：run identity 键序；`schema_version = "M1c_S8_retrieval_result_v1"`；
  python_version / platform / unicodedata_unidata_version 的取值来源；tracked 树不干净不得产出 normative artifact。

### [L3] RESULT_SCHEMA_COMPLETE = YES

- 只读核对（prereg §9.4 逐项表）：ANY_GOLD / GOLD_COVERAGE / ALL_MAPPED_GOLD @1/2/3/5/20、first_gold_rank、gold_ranks、分母、多语种逐题、
  refuse / trap 诊断、reranker k = 2 / 3、packed-context measurement、S9 再分析 —— 都能在不重跑 retrieval 的前提下由 normative artifact +
  sha 绑定的冻结输入（GoldChunkMap / testset / corpus）+ 预注册字面量重算。
- 唯一不在行内的是 pair_id（eval 元数据）：由 testset 按 question_id join；按 D10 逐题最小字段清单不加入。
- 更正（AI 自己上一稿的措辞）：prereg 曾写"metric 由 normative artifact + GoldChunkMap 重算"，与 §11 packed measurement 需要 corpus 自相矛盾，已改为上述输入集合。

### [L3] canonical JSON implementations coexist

- 事实（`CODE_FACT`，AST 扫描全部 tracked + untracked 非测试 .py 的 `json.dumps` 与 hashlib 调用点）：把结构化 payload 规范化后再取哈希的实现
  **`CANONICALIZATION_IMPLEMENTATIONS = 3`**，规则互不相同：

  | owner | 函数 / 路径 | 规则 | 依赖它的冻结 artifact |
  |---|---|---|---|
  | contracts（新） | `core/contracts.py` canonical_json_bytes / canonical_sha256 | UTF-8、ensure_ascii=False、sort_keys=True、(",",":")、allow_nan=False、无末尾换行、类型白名单 | S8 prereg 四个 digest（未提交） |
  | builder | `ingest/builder_identity.py` _canonical + construction_rules_identity | 自定义规范化（Pattern→{re,flags}、dict→排序键值对列表、set→按 JSON 排序）后 json.dumps(ensure_ascii=False, (",",":"))，无 sort_keys | construction_rules_sha256 `e89e6f94…`（canonical GoldChunkMap 的 identity 字段） |
  | OCR | `components/parsers/ocr_artifact.py` `_JSON_KW` → ocr_params_canonical / CacheIdentity.canonical / serialize_artifact | sort_keys=True、ensure_ascii=True、(",",":")；artifact 字节另加 "\n" | ocr_params_digest、cache identity、accepted OCR artifacts 与 index.jsonl（2026-09-28 记录 accepted manifest `c0e5b037…`） |

  另有确定性 artifact 序列化器（不是"规范化后取哈希"，但其输出字节的 sha 是冻结身份）：serialize_gold_chunk_map（indent=2）→ `8cf9f3be…`；
  build_corpus 的 chunks.jsonl / page_quality 写出 → `c8978777…` / `69842896…`；resolver write_report 的 fragment_matches_json → `f48018cb…`；
  serialize_retrieval_record（新）。scripts/ 下的 prereg 文本块哈希是对冻结字符串取哈希，不是 JSON 规范化。
- **决策：本轮不迁移 legacy implementations。** 理由：它们服务已冻结 artifact，迁移可能改变冻结 sha。
- **新代码纪律：从 S8 起，新的 cross-experiment canonical digest 必须使用 `canonical_json_bytes` / `canonical_sha256`；不得新增第四套。**
- followup：若未来统一 legacy implementations，必须先证明所有受影响冻结 artifact 的 sha 不变，或走明确 migration。

### [L3] prereg 定稿

- `experiments/M1c_preregistration.md`：`PREREG_STATUS = FROZEN_FOR_BM25_BASELINE`，`PREREG_BEFORE_RESULTS = YES`（仍无任何 retriever 实现、未运行任何检索）。
  不再含 PROPOSED。新增 / 改动：§6.3 MULTISET + fsum + 禁止择优 + gate 证据；§6.4 / §10.2 `retrieval_config_digest = 49f4dd23…`（1330 bytes，
  payload 比上一稿字段清单多 term_contribution）；§5 kind 名；§9.1 run identity 键序；§9.2 rank / ordinal 并排表、布局、接口；§9.4 完整性表；§0 / §1 版本拆分。
  其余三个 digest 未变（`99c87596…` / `e26afbf3…` / `e78d361f…`）；四个代码块均经 `shasum` 对字节独立复核。
- 保持：VECTOR / HYBRID NOT_READY；RERANKER_DECISION_THRESHOLD NOT_FROZEN；ALL_MAPPED_GOLD = strict map-union diagnostic；
  CN03 = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW。
- analyzer 一行"L\* / N\* / M\*"未在本轮单独裁决，按 Unicode 定义（General_Category M 的别名即 Combining_Mark）作机械翻译冻结；若人工不同意，retrieval_config_digest 随之改变。

### [L3] TTFT（未改）

- `TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；`MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`；
  `S8_EVIDENCE_COVERAGE_IS_ANSWER_QUALITY = NO`。数值常量未动。

### [L3] 本轮代码 / 测试改动与验证

- contracts：CONTRACTS_VERSION 0.4.0；GOLD_CHUNK_MAP_SEMANTICS_VERSION；GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS；GoldChunkMap 末位可选字段；
  `_gold_chunk_map_semantics_version_of`；validate / serialize 相应改动；`bm25_accumulate`；文件末改动记录块由"0.3.1 版本内追加（未递增）"
  改写为"0.4.0 相对 0.3.1"（R1–R7 原文保留，新增 V1 / B1；原块中"是否递增待裁决"一段因本裁决失效而删除）。
- resolver：见上，一个关键字。
- tests：tests/test_contracts_retrieval.py 55 → 65（T-B1–T-B6 等，kind 改名）；新增 tests/test_contracts_gold_chunk_map_versioning.py 19（T-V1–T-V9 及补充）；
  tests/test_contracts_gold_chunk_map.py 版本断言更新（test_version、test_fields、make_map 写显式字段、t6 改为语义版本）；
  tests/test_resolve_gold_chunks.py 增一条端到端断言。全套 6 模块 242 discovered / 242 executed / 242 passed / 0 skipped / 0 failed / 0 errors，RC = 0。
- 变异检查（`MEASURED`，在 scratch 镜像中逐个注入）：19 个变体全部被杀 —— query 去重（set / dict.fromkeys）、sorted 重排、API 接受无序容器、朴素循环、
  内建 sum、relevance / match collapse ×2、swap、legacy fallback 删除、legacy 接受任意版本、闭集检查删除、语义版本不匹配放行、改回比较 CONTRACTS_VERSION、
  显式字段 + 拆分前版本检查删除、序列化写出 null 字段、resolver 写 CONTRACTS_VERSION / 省略字段 / 钉死字面量。`TEST_DEFENSE_INCOMPLETE = NO`。

### [L3] docs followup（本轮只登记）

- README.md "当前 `CONTRACTS_VERSION = \"0.3.1\"`" 在提交后过时（不在本轮允许修改的文件内）。
- 执行手册 S6.0 identity 字段列表未提新字段；S6.1 记录值 "CONTRACTS_VERSION 0.3.1" 已标注为 2026-09-28 测量记录（历史，未改）。
- GOLD_CHUNK_MAP_SEMANTICS_VERSION 的递增依赖人按清单执行，没有类似 builder 登记表的 AST 守卫。


## 2026-10-01 · S8 / M1c final protocol closure：mathematical-semantics boundary（apply for review）

作用域：HEAD `d28d130de33ec4abf79b67cff12dfd9e33b885be`（== origin/ship-rag，0 / 0，staged 空）；开场时候选 diff 与上一条目结束时逐文件 sha 相同
（DECISIONS `81a715f5…`、contracts `04bc0823…`、resolver `271f2f18…`、两个 tracked 测试、两个 untracked 测试、prereg `ef346c73…`；执行手册未变）。
依据：人工裁决（本轮）—— BM25 冻结数学语义而非回调执行轨迹；可复现性作用域；版本 SPLIT 与 legacy 规则的两层测试；历史逐字节再生的作用域。
本条目由 AI 机械落地，待人工审核 diff。前三个同日条目未改动；其中与本条冲突的表述由本条更正（append-only）。

### [L3] 输入身份与审计复核

- `MEASURED`：corpus `c8978777…` / 3409；testset `05614407…` / 39；map `8cf9f3be…` / 2026 bytes；report `f48018cb…`；page_quality `69842896…` / 1335；
  builder 三项不变；token 数值常量 1050 / 200 / 0.90 / 765 / 4 / 5 只读未改。`INPUT_IDENTITY_DRIFT = NO`。
- canonical map 在**改动前的 HEAD 代码**下校验（`git archive HEAD` 导出树内 import 其自身 contracts，CONTRACTS_VERSION 0.3.1）：PASS，重序列化逐字节相等；
  在 0.4.0 候选下同样 PASS。
- CONTRACTS_VERSION 审计对 HEAD 重做（`CODE_FACT`）：常量注释"索引包与运行时一致性"/递增条件"Chunk 结构或引用语义"；consumer = IndexManifest（字段）、
  GoldChunkMap（字段）、resolver（写入）、validate_gold_chunk_map（`contracts.py:1161` 严格相等，canonical acceptance 条件）；EvalItemResult 无该字段（有 code_commit）；
  文件名不含该字段。**`CONTRACTS_VERSION_SEMANTIC_CLASS_BEFORE = C_MIXED_AMBIGUOUS`（复核确认）。**
- 依赖回答（`CODE_FACT`，AST）：GoldChunkMap 的生产方（resolver）与接受方（validate / serialize / filename / validate_eval_item / 片段切分）触达的 contracts 符号中，
  检索 / 打包 / 生成侧符号（Hit、RetrievalResultRecord、retrieval_order_key、bm25_*、pack_context、MIN_RELEVANCE、TOP_K_*、预算常量、canonical_*）**为 0**；
  CONTRACTS_VERSION 只经 HEAD 的严格相等检查到达接受方。→ 只改检索语义时，按依赖 GoldChunkMap **不应**失效；HEAD 下却会被机械判失效。SPLIT 消除这一冲突。
- GOLD_CHUNK_MAP_SEMANTICS_VERSION 递增清单按该 AST 扫描补全（加入 validate_eval_item、testset_version_from_path、CORPUS_SHA_PREFIX_CHARS）。

### [L2] BM25：冻结数学多重性，不冻结回调执行轨迹（更正上一条目）

- owner_experiment: S8
- **决策（人工）：`BM25_MULTIPLICITY_SEMANTICS = MATHEMATICAL_OCCURRENCE_MULTIPLICITY`；`BM25_CALLBACK_INVOCATION_COUNT_IS_CONTRACT = NO`；
  `BM25_ACCUMULATION = MATH_FSUM`。** 贡献多重集 C 中每次 query token 出现恰对应一个元素，raw score = `math.fsum(C)`。contribution 函数被调用几次、
  以什么顺序被调用不属于契约；逐次求值与按 token 缓存只要 C 相同都合法，合法缓存不得改变结果。前提：contribution 对固定文档是 token 的纯函数。
- 更正上一条目（"final protocol closure：版本拆分 + BM25 MULTISET"）中的三处表述，以本条为准：
  "每次出现按序恰调用一次 term_contribution"（[M] BM25 deterministic accumulation 与 [L3] 本轮代码改动）→ 作废；
  `BM25_ACCUMULATION = MATH_FSUM_QUERY_TOKEN_ORDER` → `MATH_FSUM`（fsum 结果只取决于多重集，顺序不是契约可见属性）；
  "x87 … x86-64 / arm64 不受影响" → 作废，仓库只有本机 arm64 实测，船端 x86 未测（M6）。
- 落地：`bm25_accumulate()` docstring 改为多重集契约；实现改为每个不同 token 求值一次、按出现次数展开后 fsum（体现缓存合法）；仍只接受 list / tuple。
  测试删除全部回调轨迹断言（调用次数 / 调用顺序 / spy），改为只看契约可见得分：T-B1 多重性 3（2 的幂贡献使得分唯一反解出现次数）、T-B2 SET ≠ MULTISET、
  T-B3 缓存实现与逐次重算逐比特相同（含用户示例 Implementation A / B）、T-B4 同一多重集的全部排列逐比特相同、T-B5 fsum 与朴素循环 / 内建 sum 可区分、
  T-B6 去重或无序表示被拒。`MEASURED`：tests 中对调用次数 / 顺序 / spy 的断言数 = 0。
- 合法变体对照（`MEASURED`）：把实现改为逐次求值（无缓存）、或按 sorted 顺序枚举贡献 —— 两者测试均通过（证明测试未把轨迹或顺序当 oracle）。

### [M] BM25 可复现性作用域

- why_not_falsifiable: 声明可复现性的作用域是证据纪律，不是关于系统的经验主张。
- **决策：同一 committed implementation（code_commit）+ 同一声明的 runtime / protocol identity → 期望确定性 artifact。不宣称任意 Python / libm / 平台之间
  BM25 raw score 逐比特相同；不冻结特定 libm、CPU 浮点微架构、跨平台 `math.log`、单个 contribution 的浮点求值式。** 写入 prereg §6.3.1。
- 因 payload 改动，`retrieval_config_digest`（bm25）由上一条目的 `49f4dd23…` 变为 **`3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e`**（1495 bytes）；
  numeric_evaluation 现含 accumulation = math.fsum、accumulation_input = 每次出现一个元素的贡献多重集、callback_invocation_count_is_contract = false、
  reproducibility_scope、cross_platform_bit_identity_claimed = false。其余三个 digest 不变。四个代码块均经 `shasum` 独立复核。

### [L1] 历史逐字节再生的作用域

- falsified_if: 在 canonical map 的原生成身份（contracts d30ed34 内容 + resolver 8719761 + 冻结输入）下，resolver 不能逐字节再生 `8cf9f3be…`。
- 事实（`MEASURED`，本轮，输出只写 scratch）：HEAD 导出树（contracts = d30ed34 内容、resolver = 8719761）在 canonical 输入上再生 → map **逐字节相同**
  （`8cf9f3be…` / 2026 bytes）、report 逐字节相同；0.4.0 resolver 再生 → mapping 相同、report 逐字节相同（`f48018cb…`）、级别分布 L1 30 / L2 8 相同，
  map 字节不同（`5ded46a0…` / 2073 bytes），差异只在 contracts_version（0.3.1 → 0.4.0）与新增 gold_chunk_map_semantics_version = 0.3.1。
- **决策：`HISTORICAL_MAP_BYTE_REPRODUCIBILITY_SCOPE = ORIGINAL_GENERATION_IDENTITY`。** 历史 map 的逐字节重建身份绑定其当年的实现、契约语义与输入；
  0.4.0 resolver 生成的新 map 不要求与历史 map 逐字节相同，这不是 historical reproducibility failure。不声称"0.4.0 resolver 能逐字节再生 0.3.1 canonical map"。
  canonical 历史 artifact 保持冻结、sha 不变，按 documented legacy 规则有效。GoldChunkMap docstring 已写明该作用域。

### [L3] 版本拆分复核与测试编号

- pre-split 闭集对 core/contracts.py **全部 5 个历史提交**机械恢复（d30ed34 0.3.1 / b866134 0.3.0 / a1973ef 0.2.0 有 contracts_version、无语义字段；ae33bc4 0.2.0-draft 无该字段；
  d9fdb35 无 GoldChunkMap）= {"0.2.0", "0.3.0", "0.3.1"}，与常量相等；对应测试在有 .git 时从历史重新推导并比较。
- 测试编号与本轮 T-V1–T-V10 对齐：T-V5 = 拆分后缺字段的映射 FAIL；T-V10 = 版本号碰撞不能借 legacy 规则通过（原名 test_legacy_rule_cannot_be_hit_by_version_collision）。
- `LEGACY_GOLD_CHUNK_MAP_COMPATIBILITY = PASS`；`CANONICAL_GOLD_CHUNK_MAP_STILL_VALID = YES`；canonical 字节 / sha 未变。

### [L3] retrieval result record 与接口复核

- RetrievalResultRecord 字段（chunk_id、corpus_ordinal、raw_score + kind、relevance + kind、match_score + kind）对 BM25（raw float）、future vector（raw cosine float）、
  future hybrid（raw 精确 Fraction，序列化 "p/q"）与 S8 确定性 artifact 均可表达；不含 gold 标记、expected、判分。hybrid 的逐路诊断（各路名次 / 分数）不在 record 中 ——
  不是 S8 冻结量所需，是否需要随 hybrid protocol closure 裁决（`HYBRID_BASELINE_READY = NO`）。
- `search_records(query: str, k: int = TOP_K_RETRIEVE)`：定义在 core/contracts（component 只能 import contracts；依赖方向 components → contracts、eval → components）；
  返回 `Sequence[RetrievalResultRecord]`；顺序由 retrieval_order_key 全序决定、由 validate_retrieval_records 校验。

### [L3] canonicalization census（本轮重做，两类分开计数）

- A 类：结构化 payload 规范化后取哈希的实现 **`CANONICALIZATION_IMPLEMENTATIONS = 3`** = 1 个跨实验 helper（`core.contracts.canonical_json_bytes / canonical_sha256`）
  + 2 个规则不同的 legacy 私有实现（`ingest/builder_identity._canonical + construction_rules_identity`；`components/parsers/ocr_artifact` 的
  `ocr_params_canonical` 与 `CacheIdentity.canonical`，二者同一规则集）。与上一条目一致。
- B 类（不计入上数）：输出字节本身是冻结身份的 artifact 序列化器 —— serialize_gold_chunk_map → `8cf9f3be…`；build_corpus.build → chunks.jsonl `c8978777…` 与
  page_quality.jsonl `69842896…`；resolver write_report → `f48018cb…`；ocr_artifact serialize_artifact / _rewrite_index → accepted OCR artifacts 与 manifest `c0e5b037…`；
  另有新增 serialize_retrieval_record（尚无冻结 artifact）。scripts/ 下其余 json.dumps 是日志 / 报告输出。
- 纪律不变（见上一条目）：不迁移 legacy；S8 起新的 cross-experiment digest 只用 canonical_json_bytes / canonical_sha256；不得新增第四套。

### [L3] RESULT_SCHEMA_COMPLETE = YES（机械验证）

- `MEASURED`：以**合成** ranking（种子随机抽取 corpus 行与 gold；非检索输出，未计算 BM25）按冻结 schema 生成 39 行、JSON 往返后，只用行内容 + sha 绑定的
  corpus / GoldChunkMap / testset 重算：rank / first_gold_rank / gold_ranks / corpus_ordinal→chunk / top1_doc_id 一致；五个 k 的 ANY / COVERAGE / ALL（31 题）；
  分母 31 / 28 / 8 / 7；zh / tl / hi 逐题；pair 经 testset join；packed-context 由 corpus_ordinal 重建 Hit 后调用可执行 pack_context。均无需重跑 retrieval。

### [L3] prereg 定稿（本轮）

- §6.3 改写为数学多重性 + MATH_FSUM + 回调调用次数非契约；新增 §6.3.1 边界与可复现性作用域；§6.4 / §10.2 新 digest；§9.2 rank / ordinal 并排表补全措辞
  （rank 1 = first retrieval result；corpus_ordinal 0 = first physical line；不是 pdf_page / 页内序号 / chunk_id 字典序）；§9.4 记录机械验证。
  `PREREG_BEFORE_RESULTS = YES`；`PREREG_STATUS = FROZEN_FOR_BM25_BASELINE`；SET-vs-MULTISET 择优禁令保留。
- 保持：ALL_MAPPED_GOLD = strict frozen-map-union diagnostic（CD01 map 5 / 必需 citation cover 4；FL07 3 / 2；FL06 4 / 3 —— 角色为 probe `DERIVED`，强度强 / 强 / 中）；
  CN03 = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW；testset 未改。
- TTFT 不变：`TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；`MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`；
  `S8_EVIDENCE_COVERAGE_IS_ANSWER_QUALITY = NO`。

### [L3] 测试与变异

- 全套 6 模块：240 discovered / 240 executed / 240 passed / 0 skipped / 0 failed / 0 errors，RC = 0（retrieval 63、GoldChunkMap 43、versioning 19、resolver 38、
  builder identity 18、Phase B 59；retrieval 由 65 → 63 是因为删去回调轨迹测试）。
- 变异（scratch 镜像，逐个注入）：20 个，killed 20，survived 0 —— query 去重 ×2、API 接受无序容器、朴素循环、内建 sum、缓存存陈旧值、缓存重复项计 0、
  relevance / match collapse ×2、swap、legacy fallback 删除、legacy 接受任意版本、语义版本不匹配放行、改回比较 CONTRACTS_VERSION、闭集检查删除（拆分后缺字段被接受）、
  显式字段 + 拆分前版本被接受、序列化写出 null 字段、resolver 写 CONTRACTS_VERSION / 省略字段 / 钉死字面量。`TEST_DEFENSE_INCOMPLETE = NO`。
  合法变体对照 2 / 2 通过（见上）。collapse / swap 三个变体只被合成非 BM25 向量拦下。

### [L3] contracts 叙述复核

- 已无"GoldChunkMap 兼容 == 当前 CONTRACTS_VERSION"的现行表述。残留的 0.3.1 / "切片语义一变旧映射即作废"出现在文件末 0.2.0 / 0.3.1 历史改动记录块（P4 等），
  是当时的记录，按历史保留未改。

### [L3] docs followup（`DOC_FOLLOWUP_REQUIRED = YES`，本轮不改）

- README.md:15 "当前 `CONTRACTS_VERSION = \"0.3.1\"`"。
- 执行手册_v4.md S6.0（"摘自契约"）identity 字段列表缺 `gold_chunk_map_semantics_version` 与版本拆分说明；S6.1 记录值 "CONTRACTS_VERSION 0.3.1" 与 1642 行
  "contracts v0.3.1（d30ed34）" 是 2026-09-28 的历史记录（标注为测量记录）。
- GOLD_CHUNK_MAP_SEMANTICS_VERSION 的递增仍靠人按清单执行（无类似 builder 登记表的 AST 守卫）。


## 2026-10-02 · S8 / M1c BM25 component closure

**`S8_BM25_COMPONENT_STATUS = CLOSED`；`S8_OVERALL_STATUS = OPEN`。** 执行手册 S8.4 / S8.5 要求的 vector baseline、hybrid baseline、
失败归因与 reranker L1 决策尚未完成（见本条 I），因此 S8 整体不关闭。本条只记录 BM25 component 的正式证据。

### [L2] M1c BM25 检索基线（component）

- owner_experiment: S8 / M1c
- **A. 实现身份**：implementation commit `3511aa072be3b6a1e3551017418ebda8e5d5ed8d`；`components/retrievers/bm25.py`
  sha256 `11ee5029899c3c55070de9a6fbd5622eb75f3d1c3a25c05856dd9489591c61ef`；runner `eval/run_retrieval_eval.py`
  sha256 `2c0e9a4459950170a7a475c7fdcc1388fcf63c702fd239c32acabb673f04bc0f`。
- **B. 冻结输入**：corpus `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb` / 3409；testset
  `05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b` / 39；GoldChunkMap
  `8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc`（语义版本 0.3.1）；prereg `experiments/M1c_preregistration.md`
  `ee0e028bdf8779ff2fe8c15e4c687635b2cf6f41104cb0bb643828a455b807ce`；`CONTRACTS_VERSION = 0.4.0`；四个 protocol digest 与 prereg §10.2 字面量一致。
- **C. 有效性（`MEASURED`）**：39 / 39 题；answer / refuse = 31 / 8；Run A / Run B（独立进程，PYTHONHASHSEED 不同）normative artifact
  逐字节相同（`9ce4df23…`）；`TEST_SET_TUNING_PERFORMED = NO`；`PROTOCOL_DRIFT = NO`。指标与 packing 已在 2026-10-02 由不 import runner 的
  独立代码从保存的 top-20 重算，逐项一致。
- **D. BM25 headline（31 道可答题，macro）**：

  | 指标 | @1 | @2 | @3 | @5 | @20 |
  |---|---|---|---|---|---|
  | ANY_GOLD | 0.452 (14/31) | 0.548 (17/31) | 0.645 (20/31) | 0.742 (23/31) | 0.871 (27/31) |
  | GOLD_COVERAGE | 0.364 | 0.469 | 0.576 | 0.676 | 0.823 |
  | ALL_MAPPED_GOLD | 0.323 (10/31) | 0.419 (13/31) | 0.516 (16/31) | 0.613 (19/31) | 0.774 (24/31) |

- **E. real retrieval packing（当前可执行打包契约，765 / TOP_K_CONTEXT 5）**：realized k 分布 {2: 30, 3: 7, 5: 1}（38 个非空窗口）；
  packed ANY 0.581（18/31）、COVERAGE 0.512、ALL 0.452（14/31）；按估算器 overbudget 0。实际 token 成本**未用 tokenizer 测量**：
  所报 actual-cost 是 `PROXY` —— S4a.9c 已实测的逐 chunk rendered token 之和，不含分隔符（每次拼接 0–1 token），代理 overbudget 0。
  旧 corpus 顺序连续窗口的 realized k（2 / 3 / 4 / 5 = 52% / 41% / 6% / 0.8%）与真实检索窗口不同（真实窗口更集中于 k = 2）。
- **F. 观察**：top-20 内无 gold 的可答题 = PR03、PR04、ML01、ML02。ML01（zh）结果为空，符合 prereg §8.3 的结构预测（不分词、语料无 CJK）；
  ML02（tl）query 与 gold chunk 只共享 at / drug / test，且他加禄语小品词 `sa` 撞上英文 "SA Surveyor" —— 词面层面的多语种局限。
- **G. 解释边界**：ALL_MAPPED_GOLD 只是 strict frozen-map-union diagnostic，不是答案证据完整性；retrieval / evidence coverage ≠ answer quality；
  本结果**不**决定 vector / hybrid / reranker，**不**修改 numeric token contract、TOP_K_CONTEXT 或 TTFT contract。
- **H. 延迟状态不变**：`TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；
  `MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`。
- **I. S8 剩余工作**：`VECTOR_BASELINE = PENDING`（D12：先单独一轮 EMBEDDING_PROTOCOL_PROBE + 人工 model-selection 记录）；
  `HYBRID_BASELINE = PENDING`（D13：vector protocol closure 后冻结 RRF 常数与逐路深度）；`S8_FAILURE_ATTRIBUTION = PENDING`（S8.5 十个归因标签）；
  `RERANKER_L1_DECISION = PENDING`（D2：RERANKER_DECISION_THRESHOLD 未冻结）。→ **`S8_OVERALL_STATUS = OPEN`**。
- 证据文件：`experiments/m1c_s8_bm25/s8_bm25_results.jsonl`（normative，首行 run identity，`9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8`）、
  `s8_bm25_metrics.json`（`019f6ee850bcb4788aa48d32807ccc1d61c2a570343104674004c5b37529b339`）、
  `s8_bm25_packing.json`（`81fedf9fd7ad2a0ba46a128a8c6fbe449a2131216bb9a8e5c482164eebb65313`）、
  `s8_bm25_run.log`（`91412c65bb5988e44651a7b7f2bbac6e89df47bb1302eb99667322872264ce3a`）。


## 2026-10-02 · S8 embedding protocol probe evidence（apply for review）

本条只记录 `S8_EMBEDDING_PROTOCOL_PROBE`（D12 指定的单独一轮）的测量与提案；不做任何人工裁决，不实现 vector，不生成语料 embedding，不跑检索。
`S8_OVERALL_STATUS = OPEN`；`VECTOR_BASELINE_READY = NO`。证据：`experiments/m1c_embedding_probe/`（probe 脚本、CPU 补充脚本、log、json）。
探针字符串与语料抽样规则在任何 embedding 调用前写入 log 头；未读评测集、未读 GoldChunkMap、未算任何检索指标。

### [L3] MEASURED

- 模型：`bge-m3:latest`；manifest sha256 `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`；model blob
  `sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`（1,157,671,200 B）；bert / F16 / 566.70M；embedding_length 1024；
  context_length 8192；pooling_type 2。与 D12 一致。
- runtime：Ollama server 0.34.0（client 0.23.1）；models.yaml `rt-2026-09-08` 记 0.33.3 → `RUNTIME_IDENTITY_DRIFT = YES`（未降级、未改 yaml）。
- endpoint：`POST /api/embed`（`input` 可为 str 或 list，响应字段 `embeddings`）可用；legacy `POST /api/embeddings`（`prompt`，响应 `embedding`）也可用，
  方向相同（cosine 1.0）但不归一化（norm ≈ 25）。
- 维度：全部非空输入 1024，= embedding_length → `DIMENSION_GATE = PASS`；全部有限，无零向量。
- 归一化：`/api/embed` 返回单位向量（|‖v‖ − 1| ≤ 6.4e-7，float32 舍入量级）→ `RAW_EMBEDDING_NORMALIZATION = UNIT`（该 endpoint）。
- 单条 vs 批量：逐位相同（8 / 8）→ `SINGLE_BATCH_EQUIVALENCE = EXACT`。
- Run A / Run B（全新进程、模型重新加载）：默认路径与 CPU 强制路径各自逐位相同 → `EMBEDDING_RUN_REPEATABILITY = BYTE_IDENTICAL`。
- 执行路径：默认 = 100% GPU（Metal，size_vram = size）；`options.num_gpu = 0` = 100% CPU（size_vram = 0）。**两条路径的向量不逐位相同**
  （max_abs_diff ≤ 4.0e-4，cosine ≥ 0.999993）。`SHIP_X86_EQUIVALENCE = NOT_MEASURED`（开发机 Mac ≠ 船端 x86）。
- 空输入：`""` → 返回 0 个向量（非错误）；`"   "` → 正常单位向量。
- 截断：最长 canonical chunk（`FMM:p130:2`，1515 字符）= 210 prompt tokens，`truncate=false` 与 `true` 结果相同 → 语料无截断风险。
- prefix 行为：仓库无 query / document prefix 的 authority。候选 query 前缀（BGE v1.5 惯例句）与原文向量 cosine 0.830 / 0.907，
  任意 document 前缀 0.953 / 0.951 —— prefix 会实质改变向量。
- 多语种输入（zh / tl）可被接受并产出有效单位向量；这**不是**跨语言检索质量证据（gate_e3 未测）。

### [L2] PROPOSED（待人工裁决，未生效）

- owner_experiment: S8（vector baseline）
- endpoint：`POST /api/embed`，body `{"model": "bge-m3:latest", "input": …, "truncate": false}`（截断即报错，fail-closed），只读 `embeddings`。
- 相似度：raw_score = 精确 cosine = fsum(a·b) / (‖a‖‖b‖)（float64，显式除以范数）；理由是契约已规定 vector RAW_SCORE = 原始 cosine，
  而端点范数只在 float32 舍入内为 1，不能把点积直接当 cosine。不按检索表现选择。
- 执行路径：语料与 query 必须用同一路径；倾向 CPU 强制（`num_gpu = 0`），理由：船端目标是 CPU（但仍不等于 x86 等价）。
- 空 / 全空白 query：按 Retriever 契约在调用 embedder 之前返回 []。

### HUMAN_PENDING（AI 不裁决）

- `MODEL_SELECTION_STATUS = NOT_FROZEN` → `HUMAN_MODEL_SELECTION_REQUIRED = YES`（手册 S8.1 只是倾向 bge-m3，不等于人工裁决）。
- `QUERY_PREFIX_STATUS = NEEDS_HUMAN_DECISION`；`DOCUMENT_PREFIX_STATUS = NEEDS_HUMAN_DECISION`（实测会改变向量，authority 未裁决）。
- 执行路径（默认 Metal vs CPU 强制）。
- `VECTOR_SCORE_PROTOCOL = GAP`（契约已定: match_score = (cos + 1) / 2、RAW_SCORE = 原始 cosine、全序 / tie-break 共用）。最小缺口：
  vector relevance 定义；vector 的三个 kind 取值；返回过滤（cosine 可为负，BM25 的 raw > 0 规则不适用）；embedding_protocol_digest 的 payload；
  语料 embeddings artifact 的身份与存放（prereg §9.1 已要求记入 run identity）。


## 2026-10-02 · S8 vector embedding protocol human decision

人工裁决（Arya），在任何 vector Recall 产生之前作出；本条由 AI 按裁决落地。上一条 "S8 embedding protocol probe evidence" 的 MEASURED / PROPOSED /
HUMAN_PENDING 文字不回改，其中的 HUMAN_PENDING 项由本条关闭。作用域：`M1c = development-Mac retrieval comparison`；`M6 = ship-target hardware validation`。

### [L2] D-V1 · embedding model

- owner_experiment: S8 / M1c（vector baseline）
- **决策：`S8_VECTOR_EMBEDDING_MODEL = bge-m3:latest`**；冻结 artifact：model blob `sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`，
  manifest sha256 `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`，dimension 1024。`MODEL_SELECTION_STATUS = FROZEN_FOR_M1C`。
- 理由：执行手册 S8.1 已将 bge-m3 列为倾向 baseline；probe 证明当前 artifact 可用、英 / 中 / 他加禄语均可编码、维度稳定、single = batch 逐位相同、独立运行确定。
- 含义只是"bge-m3 = M1c vector baseline model"，**不**表示 bge-m3 是最佳 embedding model。不得在 v5.3 上比较多个 embedding model 后挑 Recall 更高者。

### [L2] D-V2 · endpoint

- owner_experiment: S8 / M1c
- **决策：`EMBEDDING_ENDPOINT = POST /api/embed`**；request `{"model": "bge-m3:latest", "input": <str 或 list>, "truncate": false}`；只读响应 `embeddings`。
  legacy `POST /api/embeddings` 不用于 formal vector baseline。

### [L2] D-V3 · prefix

- owner_experiment: S8 / M1c（baseline）/ M5（任何 prefix 消融）
- **决策：`QUERY_PREFIX = ""`；`DOCUMENT_PREFIX = ""`。** 理由：仓库 authority 未冻结 prefix；probe 证明 prefix 会实质改变 embedding；baseline 不引入未经 authority 冻结的变换。
  不允许通过 v5.3 Recall 选择 prefix。

### [L2] D-V4 · execution path

- owner_experiment: S8 / M1c（开发机比较）/ M6（船端硬件验证）
- **决策：`S8_VECTOR_EXECUTION_PATH = MAC_DEFAULT_METAL`；`EMBEDDING_OPTIONS = NO_NUM_GPU_OVERRIDE`。** 语料与 query embedding 都走开发 Mac 上 Ollama 的默认 Metal。
- 理由（人工）：
  1. S8 / M1c 的目的是在开发 Mac 上快速、稳定地比较 BM25 / vector / hybrid 的检索质量；
  2. 老板要求在 Mac 上运行，是为了加速实验与方案比较，不是让 Mac 模拟最终船端硬件；
  3. probe 实测：默认路径 = Metal GPU，`num_gpu = 0` = CPU；两条路径向量极接近（max_abs_diff ≤ 4.0e-4，cosine ≥ 0.999993）但不逐位相同；两条路径各自确定；
  4. 执行路径会改变 embedding 字节，所以 formal baseline 必须冻结一个路径；
  5. 本裁决在看到任何 vector Recall 之前、依据实验目的作出，不是依据检索表现。
- **`SHIP_X86_EQUIVALENCE = NOT_MEASURED`；`M6_SHIP_CPU_VALIDATION = REQUIRED_LATER`。** 不得声称 Mac Metal == ship CPU，也不得声称 Mac CPU == ship x86。
- 描述性计时（`MEASURED`，计划先写后跑，**不是**选择依据）：probe 的 8 条输入一次 batch，各 3 次 fresh run —— Metal 冷启动中位 0.98 s / 热 0.13 s；
  CPU（`num_gpu = 0`）冷 1.95 s / 热 1.20 s。不外推到船端 x86，不形成性能契约。

### [L3] D-V5 · runtime

- **决策：formal vector baseline 使用 Ollama server 0.34.0 / client 0.23.1。** models.yaml 的 0.33.3（`rt-2026-09-08`）视为历史 runtime 记录；不降级、不回改历史证据；
  formal run identity 记录真实当前 runtime。

### [L2] D-V6 – D-V10 · vector 打分与返回

- owner_experiment: S8 / M1c
- **D-V6 raw score**：`raw_score = numerator / (norm_a · norm_b)`，`numerator = math.fsum(a_i · b_i)`，`norm = sqrt(math.fsum(x_i · x_i))`；不得以 dot(a, b) 代替 cosine
  （/api/embed 只在浮点精度内是单位向量，契约定义的是 cosine）。`raw_score_kind = "cosine"`。
- **D-V7**：`match_score = (raw_score + 1.0) / 2.0`，`match_score_kind = "cosine_affine_01"`；`relevance = match_score`，`relevance_kind = "cosine_affine_01"`
  （单路 vector 中二者数值相同，字段语义仍分开）。
- **D-V8 全序**：raw_score 降序；精确相等时 corpus_ordinal 升序；不得用无序集合迭代、chunk_id 字典序或近似 tie。
- **D-V9 过滤**：不按 cosine 正负过滤；非空 query + 非空语料返回 min(k, corpus_size) 条。理由：cosine 合法域为 [−1, 1]，负 cosine 不是 BM25 式"无匹配"标记；
  不照搬 BM25 的 raw_score > 0。
- **D-V10 空 query**：空或全空白 query 返回 []，且不调用 embedding endpoint。

### 状态

- `MODEL_SELECTION_STATUS = FROZEN_FOR_M1C`；`VECTOR_PROTOCOL_STATUS = FROZEN_FOR_M1C_BASELINE`；`SHIP_X86_EQUIVALENCE = NOT_MEASURED`；`S8_OVERALL_STATUS = OPEN`。


## 2026-10-02 · S8 / M1c vector component closure

**`S8_VECTOR_COMPONENT_STATUS = CLOSED`；`S8_OVERALL_STATUS = OPEN`。** 本条只记录 vector component 的正式证据；hybrid、失败归因与 reranker L1 决策仍未完成（见 K）。

### [L2] M1c vector 检索基线（component）

- owner_experiment: S8 / M1c
- **A. protocol**：`VECTOR_PROTOCOL_COMMIT_SHA = 544349518a73106d506319035baeb8590fb85975`（prereg §15；人工裁决 D-V1–D-V10；
  embedding_protocol_digest `38acb0b4260a516dffc32680067d5cb55c6c56d09a4d4045ebcda2d289b54af0`，vector retrieval_config_digest
  `c9c3868cf19a77d2b88a705580367ba933930af28c265887d2da6aad7a0e7343`）。
- **B. implementation**：`VECTOR_IMPLEMENTATION_COMMIT_SHA = 1a7c6749ba844e33f3237625c4e21f18c3d77c1e`（`components/retrievers/vector.py`
  `0e6da0b29e36f8e9854680ec1be2d5778f67ff3ca3c512ccbd3053ec7b09335b`）；runner `eval/run_vector_eval.py`
  `c436e37ee27da50a8e3ab40245bf09c8f37b441b293f8327952eba26084f7cb4`。模型 `bge-m3:latest`（blob `sha256:daec91ff…c3e062c`，manifest `79076464…`），
  Ollama 0.34.0 / 0.23.1，`MAC_DEFAULT_METAL`，prefix ""，`truncate = false`，`CONTRACTS_VERSION = 0.4.0`。
- **C. embedding artifact**：`experiments/m1c_s8_vector/corpus_embeddings.npy` sha256
  `70c34277a2be8ce54b78474a81eeb0ced9276e0c5c3312b43446a4126cf54459`；rows 3409；dimension 1024；dtype float64；
  meta `corpus_embeddings.meta.json` `0089f6d1942e177e596e15a8714c879d8a000fbccfd913fbea3933ffd8b946d1`。生成后两个全新进程对固定 9 行逐条重算，与已存行逐位相同。
- **决策（人工）：`GIT_TRACK_CORPUS_EMBEDDINGS = YES`。** 理由：① 该 artifact 是 formal vector run identity 的输入；② 正式结果已绑定
  `corpus_embeddings_sha256`；③ 约 28 MB，当前规模直接 Git tracking 足够；④ 入库使 fresh clone 能直接取得正式 vector baseline 输入；
  ⑤ 当前语料是实验语料，不因此建立 artifact registry、cache manager、LFS 或 production vector-store 基础设施；⑥ artifact 仍可再生，
  入库目的是 durability / provenance，不是因为它不可再生。
- **D. 有效性（`MEASURED`）**：39 / 39 题；answer / refuse = 31 / 8；Run A / Run B（全新进程、不同 PYTHONHASHSEED）normative artifact
  逐字节相同（`0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073`）；不 import runner 的独立复算 PASS；每题返回 20 条；
  `TEST_SET_TUNING_PERFORMED = NO`；`PROTOCOL_DRIFT = NO`。
- **E. headline（31 道可答题，macro）**：

  | 指标 | @1 | @2 | @3 | @5 | @20 |
  |---|---|---|---|---|---|
  | ANY_GOLD | 0.645 (20/31) | 0.871 (27/31) | 0.871 (27/31) | 0.935 (29/31) | 0.968 (30/31) |
  | GOLD_COVERAGE | 0.509 | 0.754 | 0.768 | 0.858 | 0.935 |
  | ALL_MAPPED_GOLD | 0.419 (13/31) | 0.645 (20/31) | 0.645 (20/31) | 0.774 (24/31) | 0.903 (28/31) |

- **F. 与 BM25 的描述性比较（`DESCRIPTIVE_ONLY`）**：ANY@5 BM25 0.742 / vector 0.935；ANY@20 BM25 0.871 / vector 0.968。
  不得据此直接决定 hybrid、reranker 或 M2 检索配置。
- **G. 多语种**：first_gold_rank ML01（zh）= 2，ML02（tl）= 1，ML03（hi）= 2。
- **H. top-20 无 gold 的可答题**：FL14（唯一）。
- **I. 计时作用域**：probe 8 条 batch 热启动中位数 Metal ≈ 0.13 s、CPU（`num_gpu = 0`）≈ 1.20 s；formal vector 检索 39 题合计 ≈ 8.3 s（Metal）。
  `DEV_MAC_TIMING_ONLY = YES`；`SHIP_X86_EQUIVALENCE = NOT_MEASURED`。不构成船端延迟或任何 SLA。
- **J. 解释边界**：retrieval / evidence coverage ≠ answer quality；ALL_MAPPED_GOLD 仍为 strict map-union diagnostic；本结果不修改 numeric token contract、
  TOP_K_CONTEXT 或 TTFT 状态（`TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；
  `MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`）。
- **K. S8 剩余**：`HYBRID_BASELINE = PENDING`；`FAILURE_ATTRIBUTION = PENDING`；`RERANKER_L1_DECISION = PENDING` → **`S8_OVERALL_STATUS = OPEN`**。
- 证据文件：`s8_vector_results.jsonl`（normative，首行 run identity）、`s8_vector_metrics.json`
  （`aa404fa9e1a33c3d1d3c87c5dde2624c70fc68471c6d79b16a56e37c0b286599`）、`s8_vector_run.log`
  （`49866a59a73d4e95f21e9ce96cbfc92ddeeae6757bc2c74d9d546df968ad7543`）。


## 2026-10-02 · S8 hybrid protocol human decision

人工裁决（Arya），在任何 hybrid 融合结果产生之前作出；本条由 AI 按裁决落地。D13 原文不回改；D13 中"RRF constant、per-route fusion depth、
embedding dependency 尚未完全冻结 → `HYBRID_BASELINE_READY = NO`"由本条收窄并关闭（见 H2 / H3 / H10）。
**`HYBRID_PROTOCOL_STATUS = FROZEN_FOR_M1C_BASELINE`；`S8_OVERALL_STATUS = OPEN`。** 预注册见 `experiments/M1c_preregistration.md` §16。

### [L2] H1 · fusion family

- owner_experiment: S8 / M1c（baseline）/ M5（任何融合消融）
- **决策：`HYBRID_FUSION = UNWEIGHTED_RRF`**；只融合 frozen BM25 route 与 frozen vector route，两路权重 1 : 1。
- 不得 sweep route weights、根据 v5.3 调权重、learning-to-rank 或 reranker。理由：D13 已冻结 unweighted RRF 方向且 baseline 不扫融合权重。

### [L2] H2 · RRF constant

- **决策：`RRF_K = 60`**；route rank r（1-based）的贡献 = `1 / (60 + r)`。
- 理由：现有 contract 文本已用 Σ 1/(60+rank) 表达 RRF；D13 已冻结 unweighted RRF 方向；沿用 60 是 baseline 中新增自由度最少的选择。
  不允许通过 v5.3 sweep RRF_K。

### [L2] H3 · per-route fusion depth

- **决策：`BM25_FUSION_DEPTH = 20`；`VECTOR_FUSION_DEPTH = 20`。** 某一路返回少于 20 条 → 使用该路实际返回的全部 hits。
- 理由：两条 formal component baseline 都已冻结完整 top-20，正式 metrics 也评价到 @20。
- 不得 padding fake hits、扩大到 > 20、为 hybrid 重跑 component retrieval。

### [L2] H4 · candidate set

- **决策：hybrid candidate set = union(BM25 frozen top-20, vector frozen top-20)**；每个 candidate 必须来自至少一路正式 component result；不得重新检索 corpus。

### [L2] H5 · raw RRF score

- **决策：`raw_rrf(d) = [d 在 BM25 top-20 ? 1/(60 + bm25_rank(d)) : 0] + [d 在 vector top-20 ? 1/(60 + vector_rank(d)) : 0]`**；
  内部表示 exact `fractions.Fraction`，不得用 float 累加决定排序；序列化 `"p/q"`；`raw_score_kind = "rrf_k60_2route"`。
- 理由：contracts `retrieval_order_key` 与 total-order digest 已规定 RRF 用精确有理数，浮点累加顺序会制造或抹掉 tie。

### [L2] H6 · total order

- **决策：primary = exact RRF Fraction 降序；exact tie → corpus_ordinal 升序；最终返回 top 20。**
- 不得使用 route-specific tie preference、chunk_id 字典序、insertion order、dict / set order。理由：与 bm25 / vector 共用 contracts 的同一条全序规则。

### [L2] H7 · relevance

- **决策：`relevance = float(raw_rrf / Fraction(2, 61))`（= `float(raw_rrf * Fraction(61, 2))`）；`relevance_kind = "rrf_normalized_2route_k60"`。**
  2/61 是两路、RRF_K = 60 时 raw RRF 的理论最大值（两路都排第 1），故 0 ≤ relevance ≤ 1。
- relevance 不参与排序；排序只看 exact raw_rrf。

### [L2] H8 · match_score

- **决策：hybrid 不做 cross-route rescoring；`match_score(d) = max(d 实际出现的各路已冻结 match_score)`；`match_score_kind = "max_present_route_match_score"`。**
  只在一路出现 → 取该路 match_score；两路都出现 → 取两者 max。不得为了补齐缺失 route 重新运行另一 scorer。match_score 不参与 RRF 排序。
- 与 contracts 的关系：contracts Hit 契约锁死"各路归一化原始分的 max、不许加权和"，未规定某路未检索到该 chunk 时如何取值；本裁决取 present routes。
  contracts.py 未改。

### [L2] H9 · route diagnostics

- **决策：正式 hybrid experimental artifact 必须保留 per-route provenance**：chunk_id、corpus_ordinal、hybrid rank、exact RRF raw score、relevance、
  match_score；BM25 与 vector 各自的 present / rank / raw_score / match_score。
- 属于 experimental result record；不因此扩张 production Hit schema。

### [L2] H10 · input authority

- **决策：formal hybrid baseline 直接消费已 durable-frozen 的 BM25 formal top-20 artifact 与 vector formal top-20 artifact；不得重新运行 BM25、vector 或 embedding。**
  hybrid baseline 因此是 frozen component outputs 之上的纯 deterministic fusion。
  - BM25：`experiments/m1c_s8_bm25/s8_bm25_results.jsonl` `9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8`（evidence commit 56c5990）
  - vector：`experiments/m1c_s8_vector/s8_vector_results.jsonl` `0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073`（evidence commit 5b5a7ef）
- D13 的 embedding dependency 由此冻结：hybrid 的 vector 输入就是上述 artifact，其 embedding 身份已由该 artifact 的 run identity 绑定（D-V1–D-V10）。

### 状态

- `HYBRID_PROTOCOL_STATUS = FROZEN_FOR_M1C_BASELINE`；`HYBRID_BASELINE_READY = YES`（仅 M1c baseline）。
- D13 其余决策不变：baseline 不扫融合权重；任何 weight sweep 只作 exploratory，不得在 v5.3 上选择 M2 production configuration。
- D13 登记的 `CONTRACT_NARRATIVE_FOLLOWUP`（contracts Hit docstring "融合权重是 L2 参数（M1c 要扫）"）仍未处理，本轮不改 contracts。
- hybrid baseline 是 fixed-k retrieval baseline，不读取 packing 相关常量（D3 / D15）。
- `S8_OVERALL_STATUS = OPEN`（`HYBRID_BASELINE`、`FAILURE_ATTRIBUTION`、`RERANKER_L1_DECISION` 仍 PENDING）。


## 2026-10-02 · S8 / M1c hybrid component closure

**`S8_HYBRID_COMPONENT_STATUS = CLOSED`；`S8_OVERALL_STATUS = OPEN`。** 本条只记录 hybrid component 的正式证据；失败归因与 reranker L1 决策仍未完成（见 P）。

### [L2] M1c hybrid 检索基线（component）

- owner_experiment: S8 / M1c
- **A. protocol**：`HYBRID_PROTOCOL_COMMIT_SHA = a0a92414e543b868f66bc016ec954c70b5420766`（人工裁决 H1–H10；prereg §16；
  hybrid retrieval_config_digest `97ddd20aa9f4e837f188c7c6eb29c5eaa400544b5b2eff367c8e0eed4425e621`；RRF_K = 60；route depth BM25 20 / vector 20；权重 1 / 1）。
- **B. implementation**：`HYBRID_IMPLEMENTATION_COMMIT_SHA = 1e07e1b08d58d9980b7c6cee3fd7b5d389e0b26d`；`components/retrievers/hybrid.py`
  sha256 `1456b850b3ee2f0777d1937af6a130866948c751e9a513375f010073a2f9fbb5`；runner `eval/run_hybrid_eval.py`
  sha256 `944306e34cbf3715c198e67e66d3012033b02bb757d7f94c525e54648e697f07`。
- **C. 冻结输入（未重跑任何 retrieval / embedding）**：BM25 `experiments/m1c_s8_bm25/s8_bm25_results.jsonl`
  `9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8`；vector `experiments/m1c_s8_vector/s8_vector_results.jsonl`
  `0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073`。两路记录由 artifact 无损重建，并各自通过 `validate_retrieval_records(k=20)`。
- **D. 正式证据**：`experiments/m1c_s8_hybrid/s8_hybrid_results.jsonl`（normative，首行 run identity）
  `5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8`；`s8_hybrid_metrics.json`
  `97021b12a03d5e5e6535ea794af64f4e1e022667297d725538f34e9932152f81`；`s8_hybrid_run.log`
  `3624a2783ec503a35b1bbbc75aebd21729a2cf41964dd8e82865d58db70d8e6d`。
- **E. 39 / 39 题**；answer / refuse = 31 / 8；每题 route_diagnostics 与 hits 逐条对齐，per-route provenance 与两份 component artifact 一致。
- **F. Run A / Run B**（全新进程、不同 PYTHONHASHSEED）normative artifact 逐字节相同。
- **G. 独立复算 PASS**：不 import runner / 组件的 scratch 代码 ① 直接从两份 component artifact 重新融合，top-20 与 raw / relevance / match_score 逐条一致；
  ② 从保存的 hybrid top-20 重算 31 题与 English 28 题 headline 及逐题 first_gold_rank，一致。
- **H. headline（31 道可答题，macro）**：

  | 指标 | @1 | @2 | @3 | @5 | @20 |
  |---|---|---|---|---|---|
  | ANY_GOLD | 0.581 (18/31) | 0.710 (22/31) | 0.774 (24/31) | 0.903 (28/31) | 1.000 (31/31) |
  | GOLD_COVERAGE | 0.461 | 0.609 | 0.689 | 0.803 | 0.952 |
  | ALL_MAPPED_GOLD | 0.387 (12/31) | 0.516 (16/31) | 0.613 (19/31) | 0.710 (22/31) | 0.903 (28/31) |

- **I. 多语种**：first_gold_rank ML01（zh）= 2，ML02（tl）= 4，ML03（hi）= 1。
- **J. 解释边界（`DESCRIPTIVE_ONLY = YES`）**：
  - hybrid ANY@20 = 31 / 31 = 1.000：component 各自 top-20 遗漏的 gold（vector：FL14；BM25：PR03、PR04、ML01、ML02）都由另一路补回。
  - hybrid ANY@1 / @2 / @5 = 0.581 / 0.710 / 0.903，低于 vector 的 0.645 / 0.871 / 0.935（BM25 为 0.452 / 0.548 / 0.742）。
  - 结果产生后没有调融合权重、RRF_K、route depth 或任何协议项（执行手册 S8.4：hybrid 比单一 retriever 差时不调融合权重）。
  - 不据此得出 hybrid 优于或劣于 vector、hybrid 应成为 production route、reranker 需要或不需要、answer quality 提高等结论 ——
    S8.5 失败归因与 reranker L1 决策尚未执行。retrieval / evidence coverage ≠ answer quality；ALL_MAPPED_GOLD 仍为 strict map-union diagnostic。
- **K. match_score 刻度 caveat（`HYBRID_MATCH_SCORE_IS_UNIFIED_CONFIDENCE = NO`）**：hybrid `match_score = max(present BM25 bm25_saturation,
  present vector cosine_affine_01)`，两路 match_score 不是同一原始分布。观察（`MEASURED`）：8 道 refuse / trap 题的 max_match_score 为 0.749–0.779，
  8 题的最大值全部来自 vector route（这些题 hits 中 BM25 match_score 最高 0.530–0.698）—— vector 刻度主导。只作 S9 calibration input；
  本轮不改 match_score、不改 MIN_RELEVANCE、不校准阈值。
- **L. T17 澄清（不是 protocol change）**：route list 的顺序有语义（位置 = route rank），随机打乱 route list 不是合法的"输入顺序扰动"，
  实现对不符合该路全序的输入 fail-fast 是正确行为。要求 permutation invariant 的是 candidate 插入顺序、内部 dict 构造顺序、set 迭代顺序等非语义顺序。
- **hybrid operator scope**：`components/retrievers/hybrid.py` 当前是 deterministic fusion operator，不是 Retriever 实现类；这不阻塞 M1c hybrid baseline。
  production pipeline assembly 留给执行手册对应阶段。
- **M. `S4A_9D_BLOCKS_HYBRID = NO`**：hybrid.py、runner 及其调用到的 base 函数均不读取 MAX_PROMPT_TOKENS / PROMPT_OVERHEAD_RESERVE_TOKENS /
  CONTEXT_PACK_MARGIN / CONTEXT_PACK_BUDGET_TOKENS / CHARS_PER_TOKEN_EST / TOP_K_CONTEXT / pack_context（grep + AST），D3 / D15 falsified_if 未命中。
- **N. `TEST_SET_TUNING_PERFORMED = NO`。**
- **O. `PROTOCOL_DRIFT = NO`。**
- **P. S8 剩余**：`FAILURE_ATTRIBUTION = PENDING`；`RERANKER_L1_DECISION = PENDING` → **`S8_OVERALL_STATUS = OPEN`**。


## 2026-10-02 · S8 failure attribution protocol closure

人工裁决（Arya）：S8 retrieval failure attribution 的口径、FailureTag 适用范围与 AI / human 分工。本条由 AI 按裁决落地并机械生成人工审核包；
**没有任何题被 AI 赋予最终 FailureTag。** `FAILURE_ATTRIBUTION_PROTOCOL_STATUS = FROZEN`；`FAILURE_ATTRIBUTION_STATUS = PENDING_HUMAN`；
`RERANKER_L1_DECISION = PENDING`；`S8_OVERALL_STATUS = OPEN`。

### authority 摘录（只读，未改任何 authority 文件）

- 执行手册 S8.5 要回答的三个问题：① `TOP_K_RETRIEVE=20` 够不够（Recall@20 曲线）；② 要不要引入 reranker（Recall@2 vs Recall@20）；
  ③ 失败的题为什么失败（逐题明细 + 十个归因标签 → M5 该调什么）。本步应入库：`[L2] M1c 检索基线` + `[L1] 是否引入 reranker`（带 falsified_if）。
- 失败归因 owner：实施方案 v0.13 §18 分工原则 —— Arya 负责"缺陷归因"。
- FailureTag：`core/contracts.py` L496–507，10 个值：parse_failure、chunk_boundary、bm25_miss、vector_miss、fusion_miss、ranking_miss、
  context_truncation、generation_miss、refusal_miss、distractor_capture。contracts 注释引用的"实施方案 §24.3"在 v0.13 中不存在（`LOCATOR_NOT_FOUND`，
  本轮只登记，不改 contracts）。contracts `EvalItemResult.failure_tag` 是 M2 答案级字段（只在 scored_as == 0 时填）；本条的 `human_failure_tag`
  是 S8 审核包字段，不写入 EvalItemResult / `eval/results.csv`。

### [L2] 失败单元（FROZEN）

- **A. `CANDIDATE_RETRIEVAL_MISS(q, r)` ⇔ `gold(q) ∩ top20(q, r) = ∅`**，q ∈ 31 道可答题，r ∈ {BM25, VECTOR, HYBRID}；gold = GoldChunkMap.mapping[q]，
  top20 = 已提交 S8 artifact 中该题保存的排序。由 committed artifact 重算（`MEASURED`）：BM25 = PR03、PR04、ML01、ML02；VECTOR = FL14；HYBRID = 无。
- **B. `RANKING_DIAGNOSTIC`**：31 道可答题 × 三路的 first_gold_rank 与 gold_ranks。只是诊断，**不是**自动 failure label；rank > 1 不得自动记为
  ranking_miss；是否触发 reranker 由后续 S8.5 decision rule 判断。
- **refuse / trap（8 题）**：不进入 CANDIDATE_RETRIEVAL_MISS 的可答题分母；top hits、match_score、relevance、route diagnostics 保留在三份已提交
  artifact 中，供 S9 阈值校准与后续拒答分析。本轮不赋 refusal_miss（生成 / 拒答行为尚未运行）。

### [L2] FailureTag 适用性矩阵（FROZEN；定义 = contracts L497–506 注释）

| FailureTag | 分类 | 理由 |
|---|---|---|
| `parse_failure` | S8_RETRIEVAL_APPLICABLE | 候选未召回的根因可能在解析阶段；冻结 corpus 中 gold chunk 正文已在审核包内，可判断内容是否丢失 / 受损 |
| `chunk_boundary` | S8_RETRIEVAL_APPLICABLE | chunk 边界由冻结 corpus 固定；审核包给出全部 gold chunk 与 gold_count，切分可在 S8 观察 |
| `bm25_miss` | S8_RETRIEVAL_APPLICABLE | 直接对应 CANDIDATE_RETRIEVAL_MISS(q, BM25)，可从冻结 BM25 top-20 判断 |
| `vector_miss` | S8_RETRIEVAL_APPLICABLE | 直接对应 CANDIDATE_RETRIEVAL_MISS(q, VECTOR) |
| `fusion_miss` | S8_RETRIEVAL_APPLICABLE | 融合是 S8 组件；hybrid artifact 的 route_diagnostics 给出两路 rank 与融合 rank |
| `ranking_miss` | DEFER_TO_PACKING | 定义是"进了 top-k_retrieve 但没进 context"，依赖 context packing；fixed-k baseline 不含 packing（D3 / D15） |
| `context_truncation` | DEFER_TO_PACKING | 定义是"进了 context 但被 token 预算截断"（另见 contracts pack_context 文档）；final-budget packed 结论要等 numeric contract freeze（D3 / D15、prereg §11），authority 未允许 provisional 标签 |
| `generation_miss` | DEFER_TO_GENERATION | "证据在 context 里，但模型没用"，需要生成运行 |
| `refusal_miss` | DEFER_TO_GENERATION | "该答却拒答"，取决于 MIN_RELEVANCE 拒答判定（S9）与答案行为（M2），S8 均未运行 |
| `distractor_capture` | DEFER_TO_GENERATION | "被干扰项俘获"是拒答题的答案级结果，需要生成运行 |

- **context_truncation 边界**：本轮不得以最终意义的 context_truncation 给任何题下结论。BM25 已有的 current-contract packing 结果（BM25 closure E）
  只作 descriptive evidence，不是 final failure tag。

### [L2] 分工（FROZEN）

- **`AI_ROLE = PREPARE_EVIDENCE_ONLY`**：机械计算 ranks、lexical overlap（仅用冻结 BM25 analyzer）、摘出冻结 chunk / 题目字段 / route diagnostics、
  列出矩阵中 S8 可用的 FailureTag。不替人选最终 tag，不把解释写成 MEASURED，不因归因改 retrieval protocol。
- **`HUMAN_ROLE = FINAL_FAILURE_ATTRIBUTION`**：人工字段 `human_failure_tag`（初始 `PENDING_HUMAN`）、`human_failure_note`（初始空）。
  取值只从矩阵 S8_RETRIEVAL_APPLICABLE 类中选；"无检索失败"的哨兵值与是否允许多标签本协议未规定，由人工填写时裁决。

### [L2] 审核人口（机械规则，FROZEN）

- **Tier 1（必须审核）**：任一路 CANDIDATE_RETRIEVAL_MISS，或执行手册 / prereg 明确点名并附观察 / 审核 / 归因要求的题：
  CD01（执行手册 S8.4"CD01 的单独观察结果"）；ML01 / ML02 / ML03（执行手册 S8.4：多语种检索 Recall 单独报，embedder 与生成模型的归因区分须在 M2 前做出）；
  CN03（prereg §8.2 `ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW`，是标注冲突而非检索失败指定）。
  → `TIER1 = FL14, CN03, PR03, PR04, CD01, ML01, ML02, ML03`（8）。
- **Tier 2（ranking diagnostic）**：某一路 first_gold_rank > 5 且该路 top-20 仍有 gold；不人工挑题。
  → `TIER2 = FL08(vector), FL14(hybrid), CN02(bm25), CN04(bm25), PR01(bm25), PR03(hybrid), PR04(hybrid), CD03(bm25)`（8）。
- 并集 13 题：FL08、FL14、CN02、CN03、CN04、PR01、PR03、PR04、CD01、CD03、ML01、ML02、ML03；同属两层的题标 TIER1。

### 审核包 artifact

- 生成器 `experiments/m1c_s8_attribution/build_attribution_packet.py`（`bd32b8852a010bfb8913cc743cc6d6d54fa4bf436df8327d48ded259267d0fb1`）：
  只读冻结输入，各自 sha 与冻结字面量比较；不检索、不调用 LLM / Ollama / 网络；拒绝覆盖；重复生成逐字节相同。
- `failure_attribution_packet.csv`（`c1a033978447b787f9e6c9140371a98c6acbdf4b3a8a0c68670a7be1b5e9fc34`，13 行，人工填写处）；
  `failure_attribution_packet.md`（`7768390c029eef29a7af35cd6b3e99cb0947174011eba3af55242cdae18859d4`，逐题证据 + 附录 A 全部 31 题 ranking diagnostic +
  附录 B TOP_K evidence + 附录 C refuse / trap 描述）。
- 独立 QA PASS：Tier 1 / Tier 2 人口、gold ids、三路 ranks、top-5 hits 与冻结 artifact 一致；human_failure_tag 全为 PENDING_HUMAN，note 全空。

### reranker 前提审计（只读）

- `RERANKER_REAL_WINDOW_MEASUREMENT_REQUIRED = YES`（D2：真实 retrieval-window measurement 完成后再裁；prereg §7.5 同）。
- `RERANKER_REAL_WINDOW_MEASUREMENT_ROUTE = NOT_SPECIFIED`：prereg §11 只写"在冻结的 S8 normative artifact 上、对每题已保存的 top-20 ranking"，
  未指定 BM25 / vector / hybrid；不得由"BM25 已做过"推出三路都必须做。
- 定义（prereg §11）：在已保存的 top-20 ranking 上，用当前可执行打包契约（pack_context，预算 765）及后续候选预算重新模拟 realized k 分布、
  packed ANY / coverage / ALL_MAPPED_GOLD、overbudget、actual token cost；不重跑 retrieval；取代按语料顺序的连续窗口作为 reranker k 的证据。
- `RERANKER_DECISION_THRESHOLD_STATUS = NOT_FROZEN`（D2）。本轮不裁阈值，不跑额外 packing measurement。

### TOP_K_RETRIEVE = 20 evidence（决策 PENDING）

- top-20 无 gold 的可答题：BM25 4 / 31（PR03、PR04、ML01、ML02）；vector 1 / 31（FL14）；hybrid 0 / 31（ANY_GOLD@20 = 31 / 31）。
- 只是当前 39 题评测集上的 evidence，不自动证明 20 普遍足够；S8 L1 决策留到失败归因与 reranker 决策之后。

### 状态

- `FAILURE_ATTRIBUTION_PROTOCOL_STATUS = FROZEN`；`FAILURE_ATTRIBUTION_STATUS = PENDING_HUMAN`；`RERANKER_L1_DECISION = PENDING`；
  **`S8_OVERALL_STATUS = OPEN`**。


## 2026-10-02 · S8 failure attribution result（human）

**`FAILURE_ATTRIBUTION = CLOSED`；`RERANKER_L1_DECISION = PENDING`；`TOP_K_RETRIEVE_L1_DECISION = PENDING`；`S8_OVERALL_STATUS = OPEN`。**
落实上一条 "S8 failure attribution protocol closure"。

### A. 人工权威

- `HUMAN_ROLE = FINAL_FAILURE_ATTRIBUTION`；`AI_ROLE = EVIDENCE_PREPARATION_AND_DIAGNOSTICS_ONLY`。
- 13 题最终标签由 Arya 人工审核后采纳；AI 未重新判断、未改任何标签。

### B. 填写规则（人工裁决，补全上一条留给人工的两项）

- **R1 取值**：parse_failure、chunk_boundary、bm25_miss、vector_miss、fusion_miss、NO_RETRIEVAL_FAILURE。
  `NO_RETRIEVAL_FAILURE` 只是 attribution packet 的哨兵值，**不是** `core.contracts.FailureTag` 成员（contracts 未改）。
- **R2**：每题恰好一个 primary tag；secondary factor 只写 note。
- **R3**：任一路 top-20 candidate miss → 必须用一个 S8 retrieval FailureTag；三路都无 candidate miss → `NO_RETRIEVAL_FAILURE`。
- **R4**：primary cause = 最上游、且已被证据证明足以解释本次 candidate miss 的环节。
  `parse_failure`：原 PDF 有、解析后丢失或损坏。`chunk_boundary`：内容存在，但所属逻辑单元被分到不同 chunk，且反事实地移动被分离部分后，
  冻结 retriever 可恢复 top-20 gold。否则用 route 级 miss（bm25_miss / vector_miss / fusion_miss）。

### C. 最终计数（13 题）

| primary tag | 数量 | 题 |
|---|---|---|
| chunk_boundary | 2 | PR03、PR04 |
| bm25_miss | 2 | ML01、ML02 |
| vector_miss | 1 | FL14 |
| NO_RETRIEVAL_FAILURE | 8 | FL08、CN02、CN03、CN04、PR01、CD01、CD03、ML03 |
| fusion_miss | 0 | — |
| parse_failure | 0 | — |

hybrid top-20 candidate miss = 0 / 31。

### D. 反事实证据（`MEASURED`；`chunk_boundary_counterfactual.py`，exit 0）

- 方法：在冻结 corpus 上用冻结 BM25 实现，只把引导语从引导块移到答案块开头，其余 chunk 不动；报告 gold 在完整 BM25 排序中的名次。
- PR03（引导块 CMM:p74:0 → 答案块 CMM:p74:1）：baseline `{CMM:p74:1: 29, CMM:p74:2: 33}` → counterfactual `{CMM:p74:1: 1, CMM:p74:2: 32}`；recovered_into_top_k = true。
- PR04（引导块 SMM:p35:0 → 答案块 SMM:p35:1）：baseline `{SMM:p35:1: 35}` → counterfactual `{SMM:p35:1: 1}`；recovered_into_top_k = true。
- 这是 attribution diagnostic，不是 baseline artifact：没有修改 canonical corpus，没有修改任何 formal baseline，脚本不写文件。

### E. 失败归因

- **PR03 / PR04 = chunk_boundary**：清单 / 表格与其引导语被切到不同 chunk；反事实把引导语移回答案块后 BM25 恢复 top-20（均到 rank 1）。
- **ML01 = bm25_miss**：CJK analyzer 的结构性限制（prereg §8.3）：中文 query 切成汉字长串 token，BM25 返回 0 条。
- **ML02 = bm25_miss**：不是完全的词面不可能 —— 与 gold 有部分词面共享；analyzer 无词干、形态差异，以及他加禄语虚词 "sa" 与语料缩写 "SA" 撞词，造成词面检索失败。
- **FL14 = vector_miss**：vector top-20 无 frozen gold。可能机制（embedding dilution / term placement / same-topic competition）= `NOT_VERIFIED`，不是确定根因。

### F. NO_RETRIEVAL_FAILURE 边界

- **CN03**：当前两项 required_elements 均由 ERM:p14:0 支撑，三路都在 top-20 召回（BM25@2、vector@1、hybrid@1）→ 按当前 S8 retrieval attribution 作用域不构成
  retrieval failure。QMM:p46:1 对应 acceptable evidence，三路 top-20 都没有它；citation AND / OR 的标注语义冲突（prereg §8.2）只作为 observation 保留，不改变 primary tag。
- **CD01**：检索本身不是 failure（5 个 gold 三路 top-20 都在）；packing 风险留给 packing / numeric-contract 线。

### G. FROZEN_GOLD_ALTERNATIVE_EVIDENCE_CANDIDATES（观察，不是 map 错误的证明）

- 候选：FL08 `QMM:p83:2`；ML01 `CMM:p123:1`；ML03 `ERM:p21:0`。
- 定义：冻结 gold 之外发现的候选替代证据 —— 这些 chunk 看起来能独立支持答案；但 frozen GoldChunkMap 的语义是 citation-to-corpus projection，
  不是 all answer-supporting evidence registry，因此本观察不证明 map 错误。不修改 GoldChunkMap、不修改 testset、不重跑 S6。
- 条件性影响：**只有**当后续协议明确把这些 non-gold chunk 接受为 equivalent retrieval evidence 时，才可以说当前基于 frozen GoldChunkMap 的
  Recall@1 / Recall@2 可能低估语义层面的 evidence retrieval。在此之前：正式 BM25 / vector / hybrid Recall 保持有效，不重算，不修改 frozen artifact，
  不回溯调整 retrieval protocol。

### H. 多语种观察

- vector first gold rank：ML01 = 2，ML02 = 1，ML03 = 2 —— 三题 vector 全部在 top-2；在这三题上未观察到 bge-m3 的跨语言 candidate retrieval failure。
- 不外推为 bge-m3 多语种能力已被普遍验证（n = 3）。

### I. 排序观察（`DESCRIPTIVE_ONLY = YES`；由冻结 artifact 重算）

- 可答题 first gold 在 top-2 内：BM25 17 / 31；vector 27 / 31；hybrid 22 / 31。
- 相对 vector，RRF 使 6 题跌出 top-2：CD03、CN02、CN04、FL04、ML02、PR04；使 1 题进入 top-2：FL08。
- 本条不据此做 reranker 决策。

### J. Artifact 身份

- `experiments/m1c_s8_attribution/failure_attribution_packet.csv`（人工标签写入后）= `c2ed3f7bec5910aa0e1cb28a0056a691dd4b4103eb5bfa45cf206e4ed3cd5a04`
  （写入前 `c1a03397…`；只有 human_failure_tag / human_failure_note 两列变化，round-trip 校验 PASS）。
- `apply_human_labels.py` = `7311b2a75233d740e1d2da618bd7d9ef953ed49f67af8d42c274d20de23eebe0`（审核版 `b6b71de8…`（commit 723594b）之上，
  经人工批准的三处措辞收窄：候选替代证据表述 ×3、CN03 note；qid → tag 映射未变）。
- `chunk_boundary_counterfactual.py` = `c31f81d1997d4dc8543805851ba35e0455eefee64271148dca3b881c8b5cb588`（commit 723594b，本轮未改）。

### K. 状态

- `FAILURE_ATTRIBUTION = CLOSED`；`RERANKER_L1_DECISION = PENDING`；`TOP_K_RETRIEVE_L1_DECISION = PENDING`；**`S8_OVERALL_STATUS = OPEN`**。
- `NEXT_STEP = RERANKER_PREREQUISITE`。


## 2026-10-02 · S8 reranker prerequisite real-window measurement

**`RERANKER_PREREQUISITE_STATUS = SATISFIED`；`RERANKER_L1_DECISION = PENDING`；`TOP_K_RETRIEVE_L1_DECISION = PENDING`；`S8_OVERALL_STATUS = OPEN`。**

### A. authority gap 的裁决

- D2（L3215–3216）与 prereg §7.5 要求 reranker 决策在 real retrieval-window measurement 之后；prereg §11 未指定 route（上一轮审计）。
- **人工裁决：`RERANKER_REAL_WINDOW_ROUTE_GAP_DECISION = P1_MEASURE_ALL_FROZEN_ROUTES`。** 理由：realized k 取决于排序前部 chunk 的长度，BM25 的结果
  不能自动代表 vector / hybrid；最终 production ranking 尚未裁定，不预设只测 hybrid；BM25 已有正式 measurement，vector / hybrid 可直接消费各自冻结
  top-20、用同一个已提交的 compute_packing 补测；不重跑 retrieval / embedding，不改排序、retrieval protocol 或 numeric token contract。不选 P2（只测 hybrid）、P3（只用 BM25）。

### B. 测量定义

- prereg §11 `PACKED_CONTEXT_MEASUREMENT`，`CURRENT_EXECUTABLE_CONTRACT_ONLY`：每题保存的 top-20 按原顺序交给 `core.contracts.pack_context`（relevance 前缀，不重排），
  经已提交的 `eval/run_retrieval_eval.compute_packing`。契约值（取自 contracts 0.4.0，sha 与三份 artifact 的 run identity 一致）：MAX_PROMPT_TOKENS 1050、
  PROMPT_OVERHEAD_RESERVE_TOKENS 200、CONTEXT_PACK_MARGIN 0.90、CONTEXT_PACK_BUDGET_TOKENS 765、TOP_K_CONTEXT 5。actual token cost 为 PROXY（S4a.9c 逐 chunk 实测
  rendered token 之和，未跑 tokenizer），同 BM25 closure E。
- BM25 沿用已记录的 `s8_bm25_packing.json`（未重算；QA 中用同一函数复算逐窗口一致）；vector / hybrid 为本条新测。全部是 `MEASUREMENT_ONLY`，不是新的检索 baseline。

### C. realized k（全部有 packing window 的题；`MEASURED`）

| route | windows | k=2 | k=3 | k=4 | k=5 | min / median / max | mode | 可答题 windows（k=2 / 3 / 5） |
|---|---|---|---|---|---|---|---|---|
| BM25 | 38（ML01 无结果） | 30 | 7 | 0 | 1 | 2 / 2 / 5 | 2 | 30（24 / 5 / 1） |
| vector | 39 | 26 | 13 | 0 | 0 | 2 / 2 / 3 | 2 | 31（21 / 10 / 0） |
| hybrid | 39 | 28 | 10 | 1 | 0 | 2 / 2 / 4 | 2 | 31（23 / 8 / 0） |

- 三路都没有 k = 1。`REALIZED_K_ROUTE_INVARIANT = NO`（分布不同；三路 mode 与 median 均为 2）。hybrid 的 k = 4 窗口是 refuse 题。

### D. packed 指标（31 道可答题，`MEASUREMENT_ONLY`）

| route | packed ANY | packed COVERAGE | packed ALL | mean realized k | est overbudget | proxy overbudget |
|---|---|---|---|---|---|---|
| BM25 | 0.581 | 0.512 | 0.452 | 2.194 | 0 | 0 |
| vector | 0.871 | 0.754 | 0.645 | 2.323 | 0 | 0 |
| hybrid | 0.742 | 0.641 | 0.548 | 2.258 | 0 | 1 |

- proxy overbudget 1：hybrid TR03（refuse，k = 3，估算 755 ≤ 765，proxy 890 + 200 > 1050）—— 估算器判安全但 proxy 超限；只作观察，不改预算。
- fixed-k 参照（正式 metrics）：k_context = 2 时 ANY@2 → ANY@20 差距 BM25 0.548 → 0.871（0.323）、vector 0.871 → 0.968（0.097）、hybrid 0.710 → 1.000（0.290）；
  k_context = 3 时 BM25 0.645 → 0.871（0.226）、vector 0.871 → 0.968（0.097）、hybrid 0.774 → 1.000（0.226）。不据此选择 k_context。

### E. realized-window rerank opportunity（`DESCRIPTIVE_MEASUREMENT`）

- 定义：gold 在 top-20 内，但该题第一个 gold 的 rank > 该题自己的 realized k（逐题值，不是全局 k）。不表示 reranker 一定能修复。
- vector：3 / 31 —— FL08、PR01、PR03。
- hybrid：8 / 31 —— CD03、CN02、CN04、FL14、ML02、PR01、PR03、PR04。
- （BM25 同口径：9 / 31 —— CD03、CN02、CN04、FL13、FL14、ML03、PR01、PR05、PR06；另有 4 题 top-20 无 gold。）

### F. CD01（检索归因仍为 NO_RETRIEVAL_FAILURE；以下只是 packing 观察）

| route | gold ranks | realized k | packed ids | packed gold coverage |
|---|---|---|---|---|
| BM25 | 1, 8, 10, 11, 12 | 2 | SMM:p73:1、SMM:p85:2 | 1 / 5（SMM:p73:1） |
| vector | 1, 3, 5, 8, 10 | 2 | SMM:p73:1、SMM:p84:0 | 1 / 5（SMM:p73:1） |
| hybrid | 1, 4, 6, 7, 8 | 2 | SMM:p73:1、SMM:p84:0 | 1 / 5（SMM:p73:1） |

三路在当前契约下都只装入 2 块、只含 1 / 5 个 gold，ERM 侧 gold 都未进入 context —— 与执行手册"可能结构性不可答"的预测一致（描述性）。

### G. 预算边界

- 本测量 = `CURRENT_EXECUTABLE_CONTRACT_ONLY`；本轮不改任何预算。`TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；180 s = `EXPLORATORY_UPPER_BOUND_ONLY`。
- falsified_if：numeric token contract 改变，导致 realized-k 分布或 reranker 决策判据改变 → 依赖它的 reranker L1 决策必须重新检查。不因此阻塞当前决策。

### H. artifact 与状态

- `experiments/m1c_s8_reranker/reranker_prerequisite.json` = `4e035f85d9f3e376d3a420ca27aca0a3a52f6aba57cb2de1c881b8815f603d59`（deterministic，sort_keys；重跑逐字节相同）；
  生成脚本 `measure_reranker_prerequisite.py`。输入：三份 results（9ce4df23… / 0e80682c… / 5d859a90…）、三份 metrics、BM25 packing（81fedf9f…）、corpus / testset / GoldChunkMap。
- QA PASS：每路 31 / 8 / 39；window 数 = 有结果的题数；每个 packed 序列都是该题冻结 top-20 的有序前缀；opportunity 独立重算一致；冻结 retrieval artifact 字节未变。
- `RERANKER_PREREQUISITE_STATUS = SATISFIED`；`RERANKER_L1_DECISION = PENDING`；`TOP_K_RETRIEVE_L1_DECISION = PENDING`；**`S8_OVERALL_STATUS = OPEN`**；
  `NEXT_STEP = RERANKER_L1_DECISION`。


## 2026-10-02 · S8 reranker / candidate-depth L1 decisions

人工裁决（Arya）D-R1–D-R5，在 real-window measurement（b409b41）之后作出；本条由 AI 按裁决落地。逐项核对执行手册 S8.5、实施方案 §11.3 / §13.1、
M1c prereg §7.5 / §11、DECISIONS D2 与 prerequisite 条目、contracts Reranker docstring：**无直接冲突**。prereg 与 contracts 未改。

### [L2] A. K_CONTEXT（D-R1）

- **决策：`K_CONTEXT_SELECTION_RULE = COMMON_REAL_WINDOW_MEDIAN_AND_MODE`；`K_CONTEXT = 2`。**
- 依据：real-window measurement 已完成；BM25 / vector / hybrid 的 realized-k 中位数都是 2、众数都是 2，三路都没有 k = 1；因此 2 是不依赖最终 route 选择的共同
  current-executable-contract operating point。与实施方案 §13.1 对 1050 预算的 k_context = 2 描述一致，但本裁决依据的是新的 real-window measurement，不是旧推算。
- falsified_if：numeric token contract 改变并使三路 realized-k operating point 不再支持 2；production retrieval / window semantics 改变。

### [L2] B. 主指标（D-R2）

- **决策：`RERANKER_RECALL_METRIC = ANY_GOLD`。** reranker L1 问的是融合排序是否把至少一个 frozen gold chunk 推进实际可见的 context window。
  GOLD_COVERAGE、ALL_MAPPED_GOLD 只作 diagnostics，不得替换为 primary gate。

### [L2] C. 判据方法（D-R3）

- **决策：`RERANKER_NUMERIC_THRESHOLD = NONE`；`RERANKER_DECISION_METHOD = AUTHORITY_QUALITATIVE_CASE_CLASSIFICATION`。**
  按 authority 原文（实施方案 §11.3 / §13.1、执行手册 S8.5、contracts Reranker docstring）分类：
  CASE A：Recall@k_context ≈ Recall@20 → `NO_MATERIAL_RERANK_HEADROOM`；
  CASE B：Recall@20 高但 Recall@k_context 明显低 → `RERANKER_EVALUATION_WARRANTED_SUBJECT_TO_LATENCY`；
  CASE C：Recall@20 本身低 → `RECALL_LIMITED_RERANKER_NOT_USEFUL`。
- 不借用 M2 的 ≥ 6/31（实施方案 §13.2 / §14.4，属 answer-correctness / McNemar 语境）作为 retrieval threshold；不把"≈""明显低"泛化成永久数值阈值。
  D2 的 `RERANKER_DECISION_THRESHOLD = NOT_YET_FROZEN` 由本条以"无数值阈值、按原文定性分类"关闭。

### [L1] D. Hybrid 分类（`MEASURED` 输入，人工分类）

- 决策 route = HYBRID（authority 判据针对融合排序）；BM25 / vector 为 diagnostic。
- Hybrid ANY_GOLD@2 = 22/31（0.710）；ANY_GOLD@20 = 31/31（1.000）；差距 9/31（≈ 0.290）。人工裁决：不属于"≈"；ANY@20 = 31/31 不属于"Recall@20 本身低"
  → **`RERANKER_CASE = CASE_B`**。
- real-window opportunity（gold 在 top-20 但第一个 gold 排在该题 realized k 之后）：hybrid 8/31（CD03、CN02、CN04、FL14、ML02、PR01、PR03、PR04）；
  vector 3/31。opportunity 不等于 reranker 的保证收益。
- diagnostics（`DIAGNOSTIC_ONLY = YES`）：hybrid GOLD_COVERAGE 0.609 → 0.952、ALL_MAPPED_GOLD 16/31 → 28/31；vector ANY 27/31 → 30/31；BM25 ANY 17/31 → 27/31。
- 失败归因背景（只作解释，不重新归因）：hybrid rank 3–20 的 9 题中 PR03 / PR04 = chunk_boundary，FL14 = vector_miss，ML02 = bm25_miss，
  CN02 / CN04 / PR01 / CD03 = NO_RETRIEVAL_FAILURE，FL04 不在审核包；fusion_miss = 0。

### [L1] E. reranker L1 决策（D-R4）

- **决策：`RERANKER_L1_DECISION = EVALUATE_RERANKER_SUBJECT_TO_LATENCY`。** 当前 M1c evidence 显示存在 material ranking headroom，reranker 值得进入后续候选评估；
  authority 的"值得试，但须过延迟预算"原样保留。
- 不等于：已决定 production 必须使用 reranker；已证明 reranker 能恢复全部 9 题；已决定 M2 一定包含 reranker；已通过 latency budget；已测 reranker latency。
  不写 INTRODUCE，也不写 DO_NOT_INTRODUCE；reranker 仍不进入架构图，`EvalItemResult.reranker` 仍为 "none"（contracts Reranker docstring）。
- falsified_if：实际 reranker 无法改善 frozen opportunity population；reranker latency / memory 成本超出后续冻结的业务约束；numeric token contract 改变后
  reranking headroom 不再 material；未来代表性语料不复现该 ranking gap。

### [L1] F. TOP_K_RETRIEVE（D-R5）

- **决策：`TOP_K_RETRIEVE_L1_DECISION = KEEP_20_FOR_CURRENT_M1C`。** 依据：hybrid top-20 中 31/31 道可答题至少有一个 frozen gold；hybrid candidate miss 0/31；
  人工失败归因 fusion_miss = 0。对当前冻结 39 题评测集、当前 hybrid candidate generation、当前 M1c，没有 evidence 要求把 TOP_K_RETRIEVE 从 20 调大。
  不表示 20 普遍足够；常量未改。
- falsified_if：未来评测出现 hybrid top-20 candidate miss；production 语料分布实质变化；reranker 需要不同的 candidate depth；latency / memory 约束要求更小的 k。

### G. 其他边界

- 候选替代证据敏感性：`RERANKER_DECISION_SENSITIVE_TO_ALTERNATIVE_EVIDENCE = NO`（hybrid top-2 = 22 与 @20 = 31 在三个候选下不变）。GoldChunkMap 未改。
- `TOKEN_ESTIMATOR_FALSE_SAFE_OBSERVED = YES`（hybrid TR03，见 prerequisite 条目 D）：属 numeric token-contract / S4a.9d evidence，不是 reranker blocker；预算未改。
  `TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；180 s = `EXPLORATORY_UPPER_BOUND_ONLY`。

### H. CD01 → M2 预注册 handoff

- 执行手册 S8.4 要求 CD01 观察写进 M2 预注册「预期最可能结果」；正式 M2 预注册尚未创建（只有 TEMPLATE），本轮不创建。
- 已建 handoff：`experiments/m1c_s8_handoff/m2_prereg_handoff.md`（`b350c4bdcdd9d7bdf3dc02f6632b992fe547505493c05c106e26ed79f5740fef`）—— 检索归因 NO_RETRIEVAL_FAILURE；三路 realized k 2 / 2 / 2；packed gold coverage
  1/5 / 1/5 / 1/5；ERM 侧 gold 未进入当前 packed context；风险在 packing / context availability；numeric contract 未冻结，不作 production claim。
  `CD01_M2_HANDOFF = CREATED`；正式写入待 M2 预注册创建时完成。

### I. models.yaml GATE-E3 bookkeeping

- 执行手册 S8.4 要求把多语种检索数字填进 `experiments/models.yaml` 的 `gate_e3_evidence`；当前 bge-m3 条目 `gate_e3_evidence: null`、`gate_e3_multilingual: TODO`。
- GATE-E3 是硬门（实施方案 §12.7："该语言的查询能否召回正确的英文 chunk"），PASS / FAIL 是人工判断 → `GATE_E3_HUMAN_DECISION_REQUIRED = YES`。
  本轮未修改 models.yaml。拟填 evidence（来源 `s8_vector_metrics.json` aa404fa9…，vector evidence commit 5b5a7ef）：
  vector first_gold_rank ML01（zh）= 2、ML02（tl）= 1、ML03（hi）= 2；三题 ANY_GOLD@2 = 3/3、@1 = 1/3；English 28 题 ANY_GOLD@1 / @2 / @20 = 19/28 / 24/28 / 27/28；n = 3，不外推。

### 状态

- `FAILURE_ATTRIBUTION = CLOSED`；`RERANKER_PREREQUISITE_STATUS = SATISFIED`；`RERANKER_L1_DECISION = EVALUATE_RERANKER_SUBJECT_TO_LATENCY`；
  `TOP_K_RETRIEVE_L1_DECISION = KEEP_20_FOR_CURRENT_M1C`；**`S8_OVERALL_STATUS = OPEN`**（剩余：GATE-E3 人工判断与 models.yaml 记账；S8 收尾）。


## 2026-10-02 · S8 / M1c retrieval baseline closure

**`S8_OVERALL_STATUS = CLOSED`。** 执行手册 S8.4 / S8.5 要求的输出已全部完成（见 G）。本条汇总已落盘的正式结论，不引入新的测量或协议。

### A. 三路正式 baseline 身份

| route | protocol | implementation | evidence commit | results sha256 |
|---|---|---|---|---|
| BM25 | b88d534 / 693f959（contracts 0.4.0 + prereg） | 3511aa0 | 56c5990 | `9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8` |
| vector | 5443495（D-V1–D-V10，prereg §15） | 1a7c674 | 5b5a7ef | `0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073` |
| hybrid | a0a9241（H1–H10，prereg §16） | 1e07e1b | b0a88d5 | `5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8` |

- 冻结输入：corpus `c8978777…` / 3409；testset v5.3 `05614407…` / 39；GoldChunkMap `8cf9f3be…`；`CONTRACTS_VERSION = 0.4.0`。三路均 39 / 39、Run A / B 逐字节相同、独立复算 PASS、
  `TEST_SET_TUNING_PERFORMED = NO`、`PROTOCOL_DRIFT = NO`。
- 后续 S8 commits：失败归因 3fb6e6a / 723594b / ea1544a；real-window measurement b409b41；L1 决策 17d4d17。

### B. headline（31 道可答题，ANY_GOLD macro；`DESCRIPTIVE_ONLY`）

| route | @1 | @2 | @5 | @20 |
|---|---|---|---|---|
| BM25 | 0.452 | 0.548 | 0.742 | 0.871 |
| vector | 0.645 | 0.871 | 0.935 | 0.968 |
| hybrid | 0.581 | 0.710 | 0.903 | 1.000 |

GOLD_COVERAGE / ALL_MAPPED_GOLD 见各 component closure；ALL_MAPPED_GOLD 仍为 strict map-union diagnostic。retrieval / evidence coverage ≠ answer quality。

### C. 主要结论（均已在各自条目落盘）

- **候选召回**：hybrid top-20 含 gold = 31 / 31，当前 M1c 没有 hybrid top-20 candidate miss。
- **前排质量**：vector top-2 = 27 / 31，hybrid top-2 = 22 / 31；简单 unweighted RRF 没有改善当前 top-2 排序（`DESCRIPTIVE_ONLY`，不据此改 RRF）。
- **真实 context window**：当前可执行打包契约（MAX_PROMPT_TOKENS 1050、PROMPT_OVERHEAD_RESERVE_TOKENS 200、CONTEXT_PACK_MARGIN 0.90、
  CONTEXT_PACK_BUDGET_TOKENS 765）下，三路 realized k 中位数 = 2、众数 = 2 —— 当前 evidence window 通常只容纳约 2 个 chunk。
- **reranker**：K_CONTEXT = 2；主指标 ANY_GOLD；hybrid ANY@2 = 22 / 31、ANY@20 = 31 / 31 → `RERANKER_CASE = CASE_B` →
  **`RERANKER_L1_DECISION = EVALUATE_RERANKER_SUBJECT_TO_LATENCY`**（不是"reranker required"）。
- **candidate depth**：**`TOP_K_RETRIEVE_L1_DECISION = KEEP_20_FOR_CURRENT_M1C`**，不外推为普遍足够。
- **失败归因（人工）**：chunk_boundary = PR03、PR04；bm25_miss = ML01、ML02；vector_miss = FL14；NO_RETRIEVAL_FAILURE = 8；fusion_miss = 0；parse_failure = 0。
- **CD01**：检索归因 NO_RETRIEVAL_FAILURE；三路 realized k = 2 / 2 / 2，packed gold coverage = 1/5 / 1/5 / 1/5；当前主要风险是 packing / context availability，
  不是 candidate retrieval miss。正式写入 M2 预注册「预期最可能结果」延后到 M2 预注册创建时；handoff `experiments/m1c_s8_handoff/m2_prereg_handoff.md`
  已就位（人工裁决：不阻塞 S8 closure）。
- **token estimator**：`TOKEN_ESTIMATOR_FALSE_SAFE_OBSERVED = YES`（hybrid TR03：估算判安全，proxy actual + reserve 超过 MAX_PROMPT_TOKENS）—— 属 numeric
  token-contract / S4a.9d evidence，不阻塞 S8 closure。

### [L2] D. GATE-E3（bge-m3 多语种，人工裁决）

- **决策：`GATE_E3_MULTILINGUAL = PASS_FOR_M1C`**（Arya，2026-10-02）。依据（formal vector baseline，evidence commit 5b5a7ef，
  `s8_vector_metrics.json` `aa404fa9e1a33c3d1d3c87c5dde2624c70fc68471c6d79b16a56e37c0b286599`）：ML01（zh）first_gold_rank = 2，ML02（tl）= 1，ML03（hi）= 2；
  multilingual ANY_GOLD@2 = 3 / 3 —— 对实施方案 §12.7 的判据"该语言的查询能否召回正确的英文 chunk"，在当前 M1c 冻结评测的三道多语种题上为 YES。
- 边界：n = 3，zh / tl / hi 各一题；不证明 production multilingual coverage、所有语言、所有 query 类型、generation quality 或船端 x86 等价。
  不得写"bge-m3 multilingual universally validated"。
- 台账：`experiments/models.yaml` bge-m3 条目 `gate_e3_multilingual: PASS`（台账状态词表只有 PASS / FAIL / TODO，M1c 作用域写在 evidence 中）、
  `gate_e3_evidence` 记录上述来源、数值、scope、sample_size 与 limitation；其他字段与条目未改。

### E. TTFT 边界

- `TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`；180 s = `EXPLORATORY_UPPER_BOUND_ONLY`。MAX_PROMPT_TOKENS 与 context budget 未改。
- real-window evidence 显示当前契约通常只容纳约 2 个 chunk —— 这是后续 numeric token-contract / TTFT–quality operating-point 决策的重要输入。

### F. S8 closure 不意味着

reranker 已实现；reranker 已通过 latency gate；numeric token contract 已冻结；S4a.9d 已完成；M2 预注册已创建；generator 已实现；LoRA 已运行；M2 已运行；
船端 x86 已验证（`SHIP_X86_EQUIVALENCE = NOT_MEASURED`）。

### G. 执行手册 S8.4 / S8.5 输出核对

三路正式 baseline、逐题明细、多语种单独报告、GATE-E3 evidence 与人工判断、CD01 单独观察、CD01 → M2 预注册 handoff（正式写入在 M2 预注册创建时）、
失败归因（CLOSED）、reranker 前提（SATISFIED）、`[L2] M1c 检索基线`、`[L1] 是否引入 reranker`（带 falsified_if）、TOP_K_RETRIEVE 决策 —— 全部完成。
`S8_REQUIRED_OUTPUTS_REMAINING = []`。执行手册 S8.4 中"Recall@1/2/3/20 清单""cross_doc 按每份手册算"已被 D1 / D2 取代（2026-10-01 docs followup 已登记）。

### 状态与下一步

- **`S8_OVERALL_STATUS = CLOSED`**。
- 执行手册附录 C 顺序 S8 → S9；S9（MIN_RELEVANCE 校准）的前置是"S8 的逐题明细（含 retrieval scores）"，已由三份冻结 artifact 满足 → `NEXT_STEP = S9`（本条不执行）。
  S9 开始时须处理：prereg `S9_CALIBRATION_SEMANTICS = DEFERRED`；`HYBRID_MATCH_SCORE_IS_UNIFIED_CONFIDENCE = NO`；手册 S9.1 引用的
  `eval/calibrate_threshold.py` 与 `eval/m1c_items__*.csv` 在仓库中不存在。S4a.9d 与 S9 的关系：authority 未规定（`NOT_SPECIFIED`）。


## 2026-10-02 · S9 MIN_RELEVANCE calibration protocol

人工裁决（Arya）S9-D1–D3，写于任何 S9 校准数字产生之前；本条由 AI 按裁决落地。与执行手册 S9、contracts MIN_RELEVANCE、实施方案 §14.4 / §18、
DECISIONS D7 / D8 逐项核对：**无直接冲突**。`S9_PROTOCOL_STATUS = FROZEN`；`S9_CALIBRATION_STATUS = NOT_RUN`。

### [L2] S9 MIN_RELEVANCE 校准协议

- owner_experiment: S9 / M1c threshold calibration。`OWNER_LABEL_CONFLICT = FOLLOWUP`：contracts MIN_RELEVANCE 注释写 owner_experiment M1c、
  执行手册 S9.3 要求入库条目写 M5；不阻塞本轮。
- **runtime 判定式（契约，不变）**：拒答 ⇔ `max(match_score over 全部 top-k_retrieve hits) < MIN_RELEVANCE`，在 pack_context 之前；严格 `<`。
- **S9-D1 route**：`CALIBRATION_ROUTE = HYBRID`；BM25 / vector 只作 diagnostic。MIN_RELEVANCE = 当前 hybrid score construction 下的
  `EMPIRICAL_OPERATING_THRESHOLD` —— 不是 probability、不是 calibrated confidence、不是可跨 retriever 移植的阈值
  （`HYBRID_MATCH_SCORE_IS_UNIFIED_CONFIDENCE = NO`）。
- **population**：31 道可答题 + 7 道计分陷阱（D8 `PRIMARY_TRAP_DENOMINATOR = 7`）；`TR02 = EXCLUDED_FROM_CALIBRATION_DENOMINATOR`（可描述性展示）。
- **S9-D2 分数**：`THRESHOLD_SCORE_FIELD = match_score`；每题 `gate_score = max(match_score over 冻结 hybrid top-20)`，可答题与陷阱同一口径
  （`ANSWER_SIDE_SCORE = MAX_MATCH_SCORE_OVER_TOP20`）。gold chunk 分数 `GOLD_SCORE_DIAGNOSTIC_ONLY = YES`（只用于画图和解释，不替代 gate statistic）。
  D7 的 `S9_CALIBRATION_SEMANTICS = DEFERRED` 由本条关闭。
- **S9-D3 选值规则**：`THRESHOLD_SELECTION_RULE = CONSERVATIVE_LOW_NEXTAFTER`：
  `trap_max = max(7 道计分陷阱 gate_score)`；`candidate_threshold = math.nextafter(trap_max, math.inf)`（IEEE-754 binary64 中严格大于 trap_max 的最小 float；
  不用 +ε、round 或 midpoint —— 显示精度不得决定判定语义）。`answer_min = min(31 道可答题 gate_score)`。
  - `candidate_threshold <= answer_min` → `PERFECT_SAME_SET_SEPARATION = YES`，`PROPOSED_MIN_RELEVANCE = candidate_threshold`；
  - 否则 `PERFECT_SAME_SET_SEPARATION = NO`：`ZERO_ANSWER_FALSE_REJECTION` 优先于 `ALL_TRAPS_REJECTED`，脚本不得自动选最终阈值，只输出 trade-off 表，停等人工。
  - 存储：artifact 保存完整精度 Python float repr；报告 / 图显示 6 位小数。
- **LOO**：7 折留一（每折留出 1 道计分陷阱）；`fold_threshold = math.nextafter(max(其余 6 道 gate_score), math.inf)`；机械评估 31 道可答题误拒数与留出陷阱是否被拒；
  每折不重新优化其他规则。LOO 不是独立测试集。
- **同集边界**：`SAME_SET_THRESHOLD_CALIBRATION = YES`；`S9_CALIBRATION_DATA_STATUS = SAME_SET_PROVISIONAL`；`DISCLOSED = YES`（执行手册 S9.2"接受并披露"）；
  `RETRIEVAL_RANKING_TUNING = NO`。S9 不得以 `TEST_SET_TUNING_PERFORMED = NO` 概括。独立校准集留 BACKLOG / M5。
- **最终取值**：脚本只产出 PROPOSED_MIN_RELEVANCE；最终值由 Arya 定（执行手册 S9.3；实施方案 §18），之后另走 `contract:` 变更仪式；脚本不改 contracts。
- `S4A_9D_BLOCKS_S9 = NO`：判定量只读 match_score、作用在 pack_context 之前（contracts 判定式 (c)），不读 MAX_PROMPT_TOKENS / CONTEXT_PACK_BUDGET_TOKENS / TTFT。
- falsified_if：hybrid scoring semantics 改变；production retrieval route 改变；reranker 进入 score / gating path；match_score construction 改变。


## 2026-10-02 · S9 MIN_RELEVANCE calibration result

**`S9_PROTOCOL_STATUS = FROZEN`；`S9_CALIBRATION_STATUS = CLOSED`；`S9_OVERALL_STATUS = CLOSED`。** 落实上一条 "S9 MIN_RELEVANCE calibration protocol"。

### [L2] MIN_RELEVANCE 校准

- owner_experiment: S9 / M1c threshold calibration（正式校准与独立校准集见 M5；`OWNER_LABEL_CONFLICT = FOLLOWUP`）
- **A. 人工最终取值**：**`MIN_RELEVANCE = 0.78`**；`MIN_RELEVANCE_STATUS = PROVISIONAL_SAME_SET_CALIBRATED`（Arya，2026-10-02）。
- **B. 契约**：contract commit `e14a2b0e37b9f768b9cd5059f1959d0226656fbc`；`CONTRACTS_VERSION` 0.4.0 → **0.4.1**（patch；无新 schema / 接口，GoldChunkMap 语义与检索记录语义不变）；
  `GOLD_CHUNK_MAP_SEMANTICS_VERSION = 0.3.1` 未变。MIN_RELEVANCE 块按执行手册 S9.3 从"阈值（二）未校准"移到"阈值（一）已校准"，
  "0.35 是猜的"删除，目标句按 S9-D2 改为判定量口径（gold chunk 分数只作诊断）；AST 核对：代码层只变 CONTRACTS_VERSION 与 MIN_RELEVANCE。
  同 commit 测试：`test_numeric_contract_unchanged`（0.35 → 0.78）、新增 `test_min_relevance_strict_boundary`、两处直接版本钉
  （`test_contracts_gold_chunk_map.test_version`、`test_tv3_…_accepted_under_current_contracts`，"0.4.0" → "0.4.1"）。targeted 126 / 126、全量 313 / 313 通过，0 skip。
- **C. 校准身份**：route = HYBRID；population = 31 道可答题 + 7 道计分陷阱；TR02 排除于主分母；gate statistic = max(match_score over 冻结 hybrid top-20)。
- **D. 分离（`MEASURED`）**：trap_max = 0.7792718520928508；answer_min = 0.8012534982161421；observed gap = 0.021981646123291343。
  计分陷阱 gate 0.7487373263590936 – 0.7792718520928508；可答题 gate 0.8012534982161421 – 0.9158319960994566。
- **E. 取值选择**：机械提议 A = 0.7792718520928509（`CONSERVATIVE_LOW_NEXTAFTER`）；人工最终 B = 0.78；候选 C = 0.79。
  选 B：A 只比 TR01 高一个 binary64 ULP，会把长期契约值绑定到单个极端样本的尾数；B 在当前数据上仍 7 / 7 陷阱拒答、0 / 31 误拒，只消耗约 3.3% 观测间隙；
  C 没有增加当前分类收益却消耗约 48.8% 间隙。**没有证据证明 B 的泛化优于 A。**
- **F. 同集结果（threshold 0.78，严格 `<`）**：计分陷阱拒答 7 / 7；可答题误拒 0 / 31。TR02：描述性预测拒答 = YES，不进主分母。不得写作泛化准确率。
- **G. LOO（规则留一，`CONSERVATIVE_LOW_NEXTAFTER`）**：留出陷阱被拒 6 / 7，失败 = TR01；可答题误拒 7 折皆 0。`EXTREME_SAMPLE_DEPENDENCE = YES`。LOO 不是独立测试集。
- **H. 解释**：`MIN_RELEVANCE = EMPIRICAL_OPERATING_THRESHOLD`；`HYBRID_MATCH_SCORE_IS_UNIFIED_CONFIDENCE = NO`。FL05 / FL14 的 gold 分低于阈值（0.7789 / 0.6891），
  但 gate 分高于阈值（0.8013 / 0.8204）—— MIN_RELEVANCE 不是 gold-confidence threshold。
- **I. 披露**：`SAME_SET_THRESHOLD_CALIBRATION = YES`；`S9_CALIBRATION_DATA_STATUS = SAME_SET_PROVISIONAL`；`DISCLOSED = YES`；`RETRIEVAL_RANKING_TUNING = NO`。
- **J. 稳健性（`s9_threshold_robustness.json`）**：A 陷阱侧余量 1.1102230246251565e-16 / 可答题侧 0.021981646123291232；
  B 0.0007281479071492569 / 0.021253498216142086；C 0.010728147907149266 / 0.011253498216142077。三者同集与固定值留一均 7 / 7、0 / 31。
- **K. falsified_if**：hybrid scoring semantics 改变；production retrieval route 改变；reranker 进入 score / gating path；match_score construction 改变；
  代表性校准数据显示 0.78 造成不可接受的可答题误拒或陷阱误放。同集校准不能作为无偏的泛化估计。
- **artifact（sha256）**：`eval/calibrate_threshold.py` `850d88bb1e04ff8d4fd19d755b34fc5a76732edd18504880b7902d023d1a7ba7`；
  `experiments/m1c_s9_threshold/s9_threshold_scores.csv` `a58ab19233b4066d42c2ae2d7c9baa92ad31ce02f95e1e7764abe85a1fcad73d`；
  `s9_threshold_calibration.json` `7e289c23b00051bd4268aaaa20589d8436dda0b7f2cc32a356fc91caa9ed6d30`；
  `s9_threshold_distribution.svg` `9904f7d80bead6a4575f5f12bafe3af414a0a1247189535565a32d11a78c883a`；
  `s9_threshold_run.log` `48cf92286cb7b5ee89f3af5b07f605d1c69e99a1c1774a01baace4ddbadf1552`；
  `s9_threshold_robustness.json` `b5f6f2cd53528f8ab9be07ff920d115972e1f6c81ab152aa98afd235a90a1cb6`。
  calibration.json 中的 `proposed_min_relevance = 0.7792718520928509` 是机械规则的提议、`current_contract_min_relevance = 0.35` 是运行时的契约值，二者均为历史测量，
  不改写；人工最终 0.78 记录于本条与 contracts —— 层级不同，不冲突。
- **L. 状态**：`S9_PROTOCOL_STATUS = FROZEN`；`S9_CALIBRATION_STATUS = CLOSED`；**`S9_OVERALL_STATUS = CLOSED`**。执行手册顺序下一步 = S10（冻结评测集 + 写 M2 预注册，本条不执行）；
  S4a.9d 与 S10 的关系：authority 未规定（`NOT_SPECIFIED`）。
