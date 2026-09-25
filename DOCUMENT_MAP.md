# DOCUMENT_MAP —— 文档与产物体系

**版本**:2.0 · **日期**:2026-09-07
**本文件的职责**:定义**每个文件干什么、归哪一类、改动走什么流程**。

**本文件里没有的东西**(去对应文件找):

| 你想找 | 去哪 |
|---|---|
| 为什么这么设计、约束是什么、实验怎么设计 | `实施方案_v0.11.md` |
| 按什么顺序做、每步敲什么命令 | `执行手册_v2.md` |
| 数据结构、阈值、接口的**代码** | `core/contracts.py` |
| 给实现工具的 prompt | `ClaudeCode_任务序列_v4.md` |
| 历次决定的原始记录 | `DECISIONS.md` |

---

## 1. 五类产物,五种纪律

**不同文件的性质完全不同,混在一起管是所有混乱的根源。**

| 类别 | 性质 | 纪律 | 典型文件 |
|---|---|---|---|
| **规划类** | 会被推翻重写 | 每版留存;新版必须**自包含**(不需查历史版本) | `实施方案_vX.md` |
| **操作类** | 随现实推进而过期 | 顶部必须有 **checkpoint 声明**;权威是现实不是文档 | `执行手册_v2.md`、`ClaudeCode_任务序列_v4.md` |
| **日志类** | **只追加,永不修改** | 写错了追加更正,不改历史 | `DECISIONS.md`、`eval/results.csv` |
| **契约类** | 改动代价极高 | 改动走 §4 变更仪式 | `core/contracts.py` |
| **台账类** | 持续更新状态 | 状态字段**必须来自实测** | `experiments/models.yaml` |
| **数据类** | 体积大、多数可再生 | 可再生的不进 Git,**生成脚本必须进** | `corpus/`、`index/` |

> **为什么这个分类是必要的**:
> `DECISIONS.md` 如果被当成规划类去"整理更新",项目就失去了唯一的历史记录;
> `contracts.py` 如果被当成普通代码顺手改,组件之间的语义就开始漂移;
> 执行手册如果被当成状态记录,就多了一个会过期的真相来源。
> **类别决定纪律。**

---

## 2. 完整文件清单

### 2.1 规划类

| 文件 | 回答什么 | 更新时机 |
|---|---|---|
| `实施方案_v0.11.md` | 情景 / 任务 / 约束 / 架构决定 / 实验设计 / 里程碑判据 / 风险 | 需求变化、里程碑结束、外部审核后 |
| `DOCUMENT_MAP.md`(本文件) | 每个文件干什么、改动走什么流程 | 新增文件类型、Git 规则变更 |
| `BACKLOG.md` | 这一版不做但记下来的想法 | 随时,想到就记 |

**版本纪律**:实施方案**每版单独存档**,不覆盖。新版第 0 节必须写"相对上一版改了什么"。

> **"自包含"的准确含义:不需要查历史版本,不是不需要查别的文件。**
> 跨文档引用是对的,跨版本引用才是错的。
> 把执行步骤写进方案的后果是两处都要维护、两处都会过期。

### 2.2 操作类

| 文件 | 回答什么 | 更新时机 |
|---|---|---|
| `执行手册_v2.md` | S0–S12 的顺序、每步命令、验收动作 | 每完成一个 S 就更新顶部 checkpoint |
| `ClaudeCode_任务序列_v4.md` | 机械任务的 prompt、审查要点、不交给 AI 的边界 | 每次任务完成后回填经验 |

**⚠️ 操作类文件必须在顶部写 checkpoint 声明**,格式:

```markdown
> **Current checkpoint（每次推进后更新）**
> 已完成到 S?；S1 保留作为"从零重建"说明，不应在现仓库重复执行。
> ⚠️ 本行可能落后于现实 —— 权威是 `git status` 与 `DECISIONS.md`，不是本手册。
```

**最后那句是关键。** 执行手册是**顺序说明**,不是状态记录。
一旦它开始声称仓库处于什么状态,就多了一个会过期的真相来源。
**开工前先 `git status` + `git log --oneline -5`,以实际状态为准。**

### 2.3 日志类(只追加)

| 文件 | 记什么 | 更新时机 |
|---|---|---|
| `DECISIONS.md` | 每一个决定 + 依据数据 + 待办 | **做出决定的当天** |
| `eval/results.csv` | 每次实验的**单题 × 单臂**结果 | 每次跑评测(脚本自动追加) |
| `corpus/ingest_failures.csv` | 解析失败的文档与原因 | 每次建语料(脚本自动) |

#### `DECISIONS.md` 的三条铁律

1. **只追加。** 结论变了就写新条目说明"推翻 X 月 X 日的某决定,原因是…",**不回去改旧的**。
2. **决策必须带依据。** "决定用 X" 不够,要有"因为实测 Y = Z"。
3. **待办要写进去。** 未完成项列在条目末尾,下次翻日志能接上。

#### 条目格式

```markdown
## YYYY-MM-DD 补充 N · 一句话标题

### [级别] 决策标题
- falsified_if / owner_experiment / why_not_falsifiable:   ← 按级别填对应字段
- 事实:（带数字）
- 依据:（实测命令或输出）
- **决策:**
- 待办:
```

#### `eval/results.csv` 的粒度

**一行 = 一次实验 × 一道题 × 一个臂。** 一次 M2 实验产生 39 × 4 = **156 行,不是 4 行**。

*为什么*:McNemar 检验需要逐题逐臂的对错矩阵,只有汇总正确率算不出来。
**这一条如果漏了,实验跑完也算不出检验,只能重跑。**

汇总指标由这张表**算出来**,不预先存——存汇总值会让原始数据与汇总值有漂移的可能。
列的定义在 `core/contracts.py` 的 `RESULTS_COLUMNS`,由 `EvalItemResult` 的字段自动生成
——**表头与字段是同一个定义处**,不会漂移。

### 2.4 契约类

| 文件 | 内容 |
|---|---|
| `core/contracts.py` | 九条语义约定 · 阈值常量 · 数据结构 · 异常 · 组件接口 · 工具函数 |

**⚠️ 本文件绝对不交给 AI 生成或修改。** AI 可以按它实现组件,不能改它。

### 2.5 台账类

| 文件 | 内容 | 更新时机 |
|---|---|---|
| `experiments/models.yaml` | 候选模型 + 四道门的通过状态 | 每完成一次门测试 |
| `experiments/exp_XXX.yaml` | 单次实验的完整配置 | 每次新实验(复制上一个改) |
| `experiments/M2_preregistration.md` | M2 预注册,**提交后不改** | 一次性 |
| `ENVIRONMENT.md` | 环境快照(软件版本、模型 digest) | 环境变更时 |

**台账纪律**:状态字段(`gate_2: pass/fail/pending`)**只能来自实测**。

> 2026-08-17 的教训:Ollama 能跑 ≠ llama.cpp 能跑。
> **看文档填状态会直接把错误结论带到 M6。** 每个 `pass` 必须附实测命令或数据来源。

### 2.6 数据类

| 路径 | 内容 | 可再生? | 进 Git? |
|---|---|---|---|
| `raw/` | 原始 PDF(9 份 / 49 MB) | ❌ **不可,必须备份** | ❌ |
| `corpus/chunks.jsonl` | 解析后的 chunk(3309 条) | ✅ 一条命令 41 秒 | ❌ |
| `corpus/ingest_report.csv` | 解析统计 | ✅ | ❌ |
| `index/` | 向量文件 + BM25 索引 | ✅ | ❌ |
| `models/` | 模型权重、LoRA adapter | ✅(重新 pull) | ❌ |
| **`eval/testset_v5_*.jsonl`** | **评测集** | ❌ **人工产物,不可再生** | ✅ **唯一例外** |

---

## 3. Git 规则

### 3.1 判断标准

> **能一条命令重新生成的 → 不进 Git,但生成脚本必须进。**
> **唯一例外**:`eval/testset_*.jsonl`。它是人的判断,不可再生,**必须版本控制**。

### 3.2 `.gitignore`

```gitignore
# 判断标准（写在文件里，不靠自觉）：
#   能一条命令重新生成的 → 不进 Git，但生成脚本必须进
#   唯一例外：eval/testset_*.jsonl 是人的判断，不可再生，必须进 Git

.venv/
__pycache__/
*.pyc
.DS_Store

raw/*
!raw/.gitkeep
corpus/*
!corpus/.gitkeep
index/*
!index/.gitkeep
models/*
!models/.gitkeep

# gold_chunk_map：见 §3.3 裁定
eval/gold_chunk_map/map__*.json
eval/gold_chunk_map/map__*.report.csv
```

> **顶部两行注释是刻意保留的。** 裸 ignore 文件挡不住有人以后加 `eval/*`,
> 那会直接违反唯一例外。纪律要写死在文件里,不能靠自觉。

### 3.3 ⚠️ `gold_chunk_map/` 的裁定(规则曾自相矛盾)

`gold_chunk_ids` 是 `citations` 在**某套语料 + 分块配置**上的投影,属派生产物。
但产物内部还要再分一层:

| 文件 | 进 Git? | 理由 |
|---|---|---|
| `map__*.json` | ❌ | 机械派生;语料一变即失效;脚本可一键再生 |
| `map__*.report.csv` | ❌ | **它同样是可再生的**。放进 Git 会破坏 §3.1 规则的一致性 |
| **`map__*.adjudication.csv`** | ✅ | **你对 L4/FAIL 行的人工裁定。这是判断,不可再生** |

> **关键区分**:原始报告是机器产出的;**你对报告里可疑行的裁定才是人的判断**。
> 前者随时可再生,后者丢了就没了。**进 Git 的是后者。**

裁定文件的最小结构:

```
question_id, citation_idx, match_level, 判定, 一行理由
```

`判定` 取值:`接受` / `引文有误` / `页码有误` / `语料缺失`。

---

## 4. 契约变更仪式(缺一不可)

改 `core/contracts.py` 必须:

1. **单独开一次工作会话**,不与实现组件混在一起
2. **单独一个 commit**,message 以 `contract:` 开头
3. **同步在 `DECISIONS.md` 追加一条**,按 §5 标注级别
4. 若改动影响已生成的语料或索引 → **必须重建**,并在 DECISIONS 注明重建时间

**永远不在实现组件时顺手改契约。** 要改契约就停下来单独改。

---

## 5. 决策分级:L1 / L2 / L3 / `[M]`

**不分级的话 `DECISIONS.md` 很快就无法检索——没人知道哪些能推翻、哪些不能。**
但只打标签解决不了问题,**每一级必须带一个强制字段**:

| 级别 | 是什么 | 强制字段 | 为什么是这个字段 |
|---|---|---|---|
| **L1** 架构决策 | 关于本系统的硬主张,几乎不改 | `falsified_if:` 什么情况下会被推翻 | **没有证伪条件的原则就是教条,不是工程决策** |
| **L2** 实验参数 | 允许被实验推翻,替换是正常的 | `owner_experiment:` 哪个实验负责重新校准 | 否则半年后没人知道这个数该不该改、谁负责 |
| **L3** 实现细节 | 重构不影响结论 | 无 | 保持自由度,不必留痕 |
| **`[M]`** 方法约束 | 统计学 / 实验设计的**正确性要求**,不是关于本系统的经验主张 | `why_not_falsifiable:` 为什么它不是经验假设 | 见 §5.1 |

### 5.1 为什么加 `[M]` 而不是放宽 L1

日志里出现过这样的条目:

```
[L1] 判定改为两道闸        falsified_if: 无
[L1] 预注册必须锁死判分函数  falsified_if: 无
```

**写"无"说明它根本不属于 L1/L2/L3 这条轴。**
"McNemar 只看不一致对""预注册要在看数据之前完成"——这些不是关于本系统的主张,
是统计学与实验设计的正确性要求,**不可能被本项目的实验推翻**。

> **不直接放宽 L1 的理由**:"L1 必须可证伪"这条规则的全部价值,
> 正在于**它阻止 L1 变成教条**。一旦允许 L1 写 `falsified_if: 无`,这道闸就废了。
> **加一类比拆一道闸便宜。**

### 5.2 现有决策的归级

**L1(架构)** —— 每条都带 `falsified_if`:

| 决策 | falsified_if |
|---|---|
| Offline First(完全离线) | 船方确认可提供稳定卫星带宽 |
| Citation First(没有出处就不输出答案) | 船务方书面同意接受无出处答案 |
| 岸-船分离 | 船端硬件规格确认可承载解析与建索引 |
| RAG 为默认架构 | **M2 中 C 臂正确率 ≥ D 臂,且文档更新响应测试中微调耗时 ≤ 索引重建耗时** |
| 混合检索(BM25 + 向量) | M5 消融显示纯向量与混合无显著差异 |
| 引用三元组 `(doc_id, section, pdf_page)` | 找到能唯一定位的更简形式 |
| `gold_chunk_ids` 外置为派生产物 | 语料与分块配置在项目全周期内都不再变化 |
| 失败降级(生成层挂掉 → 纯检索模式) | 船务方确认宁可白屏也不要降级结果 |
| thinking 模式全链路禁用 | 证据表明 thinking 显著提升带出处问答的正确率且延迟可接受 |
| `temperature = 0`,四臂一致 | 证据表明贪心解码系统性劣于采样,且差异大于采样引入的噪声 |

**L2(实验参数)** —— 每条都带 `owner_experiment`:

| 决策 | 当前值 | owner_experiment |
|---|---|---|
| `MAX_CONTEXT_TOKENS` | 1050(待拍板) | M6(船端硬件实测后重定) |
| `CONTEXT_PACK_MARGIN` | 0.90 | M1c(真 tokenizer 核对估算系数) |
| `TOP_K_CONTEXT` | 5(上限保护,非固定值) | M1c |
| `TOP_K_RETRIEVE` | 20 | M1c(Recall@k 曲线) |
| `MIN_RELEVANCE` | 0.35 **未校准** | M1c(检索分数分布) |
| `CHARS_PER_TOKEN_EST` | 4 | M1c |
| chunk 大小 / overlap | 350 / 60 | M5 消融 |
| 主模型 | 待 GATE-2 | M3 横评 |
| Teacher | `qwen3:32b`(+ 第二个) | M2 合成数据质量抽检 |
| 是否引入 reranker | **未引入** | M1c(Recall@k_context vs Recall@20) |

**`[M]`(方法约束)** —— 每条都带 `why_not_falsifiable`:

| 决策 | why_not_falsifiable |
|---|---|
| 判定 = 实用效应闸 + McNemar 两道闸 | 净差 ≠ 显著性,是配对检验的定义问题,不是本系统的经验主张 |
| 预注册在看数据之前完成并锁死判分函数 | 防 HARKing 是实验设计的正确性要求 |
| 盲评(判分者不得知道答案来自哪个臂) | 判分者有先验立场时的标准做法 |
| Partial 一律映射 Incorrect,主指标保持二分类 | 引入部分分会让 McNemar 失效,是方法学约束 |

**L3(实现)**:parser 具体实现 · 目录结构 · JSON schema · 日志格式 · 缓存策略 · CLI 参数。

**历史条目不回头补标**(日志只追加原则)。从 2026-09-07 起的新条目一律带级别。

---

## 6. 代码结构

```
ship-rag/
├── core/
│   ├── contracts.py           ⚠️ 唯一可信来源。改它走 §4 仪式，不交给 AI
│   ├── pipeline.py            组装层：读配置 → 实例化组件 → 串成流程
│   └── registry.py            名字 → 实现类的注册表，让"换组件"变成改配置
│
├── components/                可替换组件。⚠️ 各子目录之间【互不 import】
│   ├── parsers/kaiva_pdf.py   KAIVA 手册解析器（页眉元数据 + 结构感知分块）
│   │                          命名带 "kaiva" 是刻意的 ——
│   │                          新版式来了写新文件，不改这个
│   ├── chunkers/              分块策略
│   ├── embedders/             文本向量化
│   ├── retrievers/            bm25.py / vector.py / hybrid.py
│   ├── rerankers/             noop.py（当前默认）/ 其他（待 M1c 决定是否引入）
│   └── generators/            ollama.py / mlx.py / llamacpp.py
│
├── ingest/build_corpus.py     岸端：解析 → chunks.jsonl + 统计 + 失败清单
├── serve/                     船端：查询服务 + 前端（M6 才写）
│
├── eval/
│   ├── testset_v5_2.jsonl     ⚠️ 人工产物，不可再生，必须进 Git
│   ├── gold_chunk_map/        派生映射 + 报告 + 人工裁定（Git 规则见 §3.3）
│   ├── question_anchors.csv   从语料抽的候选锚点（中间产物）
│   ├── run_eval.py            跑评测，结果追加进 results.csv
│   ├── results.csv            ⚠️ 只追加，永不删行。单题粒度
│   ├── M2_blind_sheet.csv     盲评工作表（隐去臂标签），进 Git
│   └── M2_blind_key.csv       臂标签还原表，判分前不看，进 Git
│
├── experiments/               models.yaml + exp_XXX.yaml + M2_preregistration.md
├── scripts/                   一次性工具脚本（resolve_gold_chunks.py 等）
│
├── raw/ corpus/ index/ models/    数据类，不进 Git
│
├── DECISIONS.md  BACKLOG.md  ENVIRONMENT.md  DOCUMENT_MAP.md
├── 实施方案_v0.11.md  执行手册_v2.md  ClaudeCode_任务序列_v4.md
└── README.md
```

### 6.1 依赖是树,不是图

```
core/contracts.py             ← 谁都依赖它，它谁都不依赖
     ↑
  components/*                ← 各组件之间【互不 import】
     ↑
  core/pipeline.py            ← 唯一负责组装的地方
     ↑
  ingest/  serve/  eval/  scripts/
```

**铁律:任何 component 只能 `import core.contracts`。**
一旦出现 `retrievers/hybrid.py` import `generators/ollama.py`,
树就变成了图,可替换性当场消失。**Code review 第一个查这条。**

> 这条铁律同时写在 `components/__init__.py` 的 docstring 里——
> 放在 reviewer 必然打开的位置,而不只是文档里。

---

## 7. 三条工作流

### 7.1 我做了一个技术决定

1. **当天**写进 `DECISIONS.md`(带依据数据 + 级别 + 强制字段)
2. 若影响契约 → 走 §4 变更仪式
3. 若影响计划 → 记着,下次更新实施方案时纳入(不必立刻改)

> 风险登记里「决定未入库」已标**已发生三次**。这条流程是针对它的。
> 建议在 shell 里做一个 `dlog` 函数把追加变成一条命令——
> **把纪律变成机制,而不是靠自觉。**

### 7.2 我要新增 / 修改一个组件

1. 确认 `contracts.py` 里已有对应 Protocol,没有则**先走契约变更仪式**
2. 开新会话,**贴 `contracts.py` 全文**,明说"不许改它,只准按它实现"
3. **一次只做一个文件**——一次动多处,出了问题无法归因
4. **陌生人测试**:盖住实现,只看签名 + docstring,另一个人能否正确使用且不踩隐藏假设
5. **生成后必查五条**(AI 在本项目最爱犯的错):

   | # | 错误 | 怎么查 |
   |---|---|---|
   | 1 | 静默 `except` 吞异常返回 `[]` | 搜 `except`,每处要么重抛、要么是显式失败面写明的降级 |
   | 2 | 分数语义偷偷翻转(返回距离而非相似度) | 搜所有 `relevance` 赋值处,确认已归一化到 0..1 |
   | 3 | `pdf_page` 变成 0-based | 拿真实 PDF 人工核对一次出处页码 |
   | 4 | 魔法数字硬编码 | 搜数字字面量,必须来自 `contracts.py` 或配置 |
   | 5 | docstring 复述代码而非陈述契约 | 看有没有写清:边界输入、失败抛什么、返回值语义 |

6. **跑一遍 `run_eval.py`,`results.csv` 出现新行才算完成**

**prompt 模板与任务边界见 `ClaudeCode_任务序列_v4.md`。**

### 7.3 我要跑一次实验

1. 复制上一个 `exp_XXX.yaml`,改需要改的字段
2. 跑,结果自动追加进 `results.csv`(单题粒度)
3. 有价值的结论 → 写进 `DECISIONS.md`

**可复现性四条机制**:

| # | 机制 | 做法 |
|---|---|---|
| 1 | **记 digest 不记 tag** | tag 会被上游悄悄更新,实验就不可比了 |
| 2 | **固定随机种子** + `temperature=0` | 否则同配置两次结果不同 |
| 3 | **artifact digest 全记** | `testset_sha256` / `corpus_chunks_sha256` / `model_digest` / `teacher_digest` / `lora_adapter_sha256` / `prompt_config_sha256` / `gold_chunk_map_sha256` / `code_commit` |
| 4 | **环境快照** | `pip freeze`,依赖变更时更新 `ENVIRONMENT.md` |

> 机制 3 的理由很实在:三周后出现"为什么第二次跑和第一次差 3 题",
> **你必须能回答到底什么变了。**

---

## 8. 绝对不交给 AI 的四样

| 事项 | 为什么 |
|---|---|
| `core/contracts.py` 本身 | 唯一可信来源。改它走仪式,只能由 Arya 定 |
| **评测集的题目与标准答案** | 这是判断不是生成。机械回填 `gold_chunk_ids` 可以,改内容不行 |
| 拒答阈值等的**取值** | 必须来自实测分数分布 |
| "这一版不做什么"清单 | 防第二系统效应的刹车,只能由人踩 |

**这四样是判断,不是生成任务。** AI 可以帮忙讨论,不能替你决定。

---

## 9. 当前文件状态

> ⚠️ **本表可能落后于现实。权威是 `git status` 与 `git log`,不是本表。**
> 开工前先跑一次。

| 文件 | 状态 | 备注 |
|---|---|---|
| `实施方案_v0.11.md` | ✅ 最新 | 已按职责重切,不再含执行步骤 |
| `DOCUMENT_MAP.md` | ✅ 本文件 | v2.0 |
| `执行手册_v2.md` | 🔶 需加 checkpoint | S1 已被真实执行越过,**不可重跑 `git init`** |
| `ClaudeCode_任务序列_v4.md` | 🔶 需同步 | 任务 4 的向量库部分需按"穷举 cosine"改写 |
| `DECISIONS.md` | ⚠️ **历史断档** | 早期 185 行未随仓库迁移。**禁止凭摘要反推重建** |
| `BACKLOG.md` | ⏳ | 待记入:prompt cache、skip-and-fill packing、扩充陷阱题至 ≥15 |
| `ENVIRONMENT.md` | ✅ | 岸端 baseline 已写入 |
| `core/contracts.py` | 🔶 **v0.2.0-draft 待拍板** | 10 处改动 + 5 项待拍板,见文件末尾 |
| `eval/testset_v5_2.jsonl` | ✅ 已入 Git | 待升 v5.3(移除 `gold_chunk_ids`、TR01 citation 置空) |
| `eval/results.csv` | 🔶 表头需重生成 | v0.2.0-draft 加了 4 列,须按 `RESULTS_COLUMNS` 重出 |
| `scripts/resolve_gold_chunks.py` | 🔶 **与新契约冲突** | 它把 `gold_chunk_ids` 回写进 testset;新设计是外置派生产物。**契约冻结后必须改参数语义** |
| `components/` 各实现 | ⏳ 未建 | 等契约冻结 |
| `ingest/build_corpus.py` | ⏳ 未建 | 等契约冻结 |

**🔶 = 能用但依赖未拍板的决定,不要在此基础上继续写代码。**

---

*DOCUMENT_MAP v2.0。本文件只讲"每个文件干什么、改动走什么流程"。*
*"为什么这么设计"见 `实施方案_v0.11.md`;"按什么顺序做"见 `执行手册_v2.md`。*
