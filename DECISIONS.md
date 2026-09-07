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
