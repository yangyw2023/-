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