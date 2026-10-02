# M1c / S8 预注册 —— 固定-k 检索基线（提交后不许改）

- 实验编号：M1c / S8（milestone 级，与 `experiments/M2_preregistration.md` 同级）
- 写于：2026-10-01，**任何 S8 检索结果产生之前**
- `PREREG_BEFORE_RESULTS = YES`：写作时仓库中不存在任何 retriever 实现，没有运行过任何 BM25 / vector / hybrid 检索；
  本文件不含任何检索结果。下文所有数字只来自冻结输入（corpus / testset / GoldChunkMap）的机械统计。
- 依据：DECISIONS 2026-10-01「S8 / M1c retrieval protocol：人工裁决落地」（D1–D15）、同日「protocol apply blocker closure」
  与同日「final protocol closure」。本文件只冻结已由人裁决的内容；未裁决项一律标 `NOT_FROZEN`，不得在实现中自行填补。
- `PREREG_STATUS = FROZEN_FOR_BM25_BASELINE`（待人工审核后随 protocol commit 入库）。本文件不再含 `PROPOSED` 项。
- 修改规则：commit 之后若需改动，只能追加带日期的 amendment 节，并在 DECISIONS 记录理由；不得改写已冻结的节。
  已产生结果之后的 amendment 必须声明"写于结果之后"。

---

## 0. 状态总览

| 项 | 状态 |
|---|---|
| BM25 baseline protocol | FROZEN：MULTISET（数学出现多重性）+ `math.fsum`；回调调用次数不是契约（§6.3 / §6.3.1）→ `BM25_BASELINE_PROTOCOL_READY = YES` |
| retrieval result record / search_records | FROZEN（`core.contracts.RetrievalResultRecord`、`Retriever.search_records`，§5、§9.2） |
| query / total-order / metric digest | FROZEN（§10） |
| retrieval_config_digest（bm25） | FROZEN（§6.4 / §10） |
| result schema 完整性 | `RESULT_SCHEMA_COMPLETE = YES`（§9.4） |
| vector baseline | `VECTOR_BASELINE_READY = NO`（§13） |
| hybrid baseline | `HYBRID_BASELINE_READY = NO`（§13） |
| IndexManifest | `INDEX_MANIFEST_CONTRACT_GAP = YES`（§13） |
| CONTRACTS_VERSION 语义 | SPLIT：`CONTRACTS_VERSION = 0.4.0`（整模块）/ `GOLD_CHUNK_MAP_SEMANTICS_VERSION = 0.3.1`；run identity 仍另记 contracts 字节身份（§9.1） |

---

## 1. 冻结输入身份（EXPECTED，抄自 DECISIONS 冻结条目，不得由被测文件自算）

| 输入 | sha256 | 规模 | 来源 |
|---|---|---|---|
| `corpus/chunks.jsonl` | `c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb` | 3409 行 | DECISIONS 2026-09-28 Formal S6 |
| `eval/testset_v5_3.jsonl` | `05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b` | 39 行 | 同上 |
| canonical GoldChunkMap `map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json` | `8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc` | 31 answer qids | 同上 |
| 同名 `.report.csv` | `f48018cbe88de3d379fb65c17e75e6b8a87eebdc8dd19bdd539356bfff5a2572` | 38 citation 行 | 同上 |
| builder identity | `kaiva_phase_b_builder_v1` / `e89e6f94ec80abdc458622a52587644dc72baaadeb6564606ddc273c2951c5a1` / `chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350` | — | 同上 |

runner 必须在检索前对上述每项做 EXPECTED == ACTUAL 断言（EXPECTED 取本表字面量），任一不等即抛异常、不产出 artifact。

canonical GoldChunkMap 是拆分前 schema（`contracts_version = "0.3.1"`，无 `gold_chunk_map_semantics_version`）。
在 contracts 0.4.0 下它按 documented legacy 规则被读作 GoldChunkMap 语义版本 0.3.1，`validate_gold_chunk_map` 通过；字节与 sha 不变、不再生。

---

## 2. Query protocol 与 leakage policy

- query = `EvalItem.question` 原始字符串，原样传给 retriever；orchestration 层不翻译、不 LLM rewrite、不做 metadata augmentation、
  不把整个 EvalItem 作为检索输入。
- Unicode / case / token normalization 属各 retriever 的 analyzer / embedder protocol，对 query 与 document 对称应用。
- 下列字段不得用于 query / filter / boost / routing / tie-break / dynamic k：
  `expected`、`type`、`language`、`citations`、`GoldChunkMap` 及其 report.csv、gold chunk ids、`required_elements`、
  `acceptable_elements`、`gold_answer`、`answer_key`、`known_distractor`、`trap_subtype`、`exclude_from_primary_score`、
  `pair_id`、`safety_critical`、`at_risk`、`rationale`、`source_boundary_ambiguity`。
- `question_id` 只能在排序完成之后作为 join key。
- 39 题全部执行检索（含 8 道 refuse），按评测集文件顺序。
- 机器可读形式与 digest：§10 `query_protocol_digest`。

## 3. Indexed text

- BM25 = `Chunk.text` only；Vector = `Chunk.text` only。section / doc / page / citation header 不进入 baseline retrieval representation。
- metadata augmentation 只作 future M5 ablation（6/31 道可答题在问题里点名手册或章节：FL06 / FL10 / FL15 / PR02 / PR04 / CD02）。

## 4. 确定性全序与 corpus_ordinal

- 全序 = (−raw_score, corpus_ordinal)；tie-break 只在 raw_score **精确相等**时生效。可执行形式 `core.contracts.retrieval_order_key`；
  返回序列的可执行校验 `core.contracts.validate_retrieval_records`。
- `corpus_ordinal` = 该 chunk 在 canonical `corpus/chunks.jsonl` 中的 **zero-based physical line ordinal**（第一行 = 0）。
  它不是 pdf_page、不是页内 chunk 序号、不是 chunk_id 字典序位置；只用于确定性 tie-break 与 provenance / audit。
- 禁止 chunk_id 字典序、doc / page 排序、任何评测 / gold 信息打破 tie。
- ranking 一律使用 raw_score，不使用 relevance / match_score 排序。
- 背景（`MEASURED`，D6）：canonical corpus 有 52 组文本完全相同的 chunk（共 112 个），只看文本的打分器必然在此产生精确 tie。
- 机器可读形式与 digest：§10 `total_order_protocol_digest`。

## 5. 分数语义与 retrieval result record

- 三个分数分开：
  - `raw_score`：检索器内部未归一化的精确排序量；决定全序。
  - `relevance`：ranking-oriented normalized score（0..1），是 raw_score 的单调不减函数。
  - `match_score`：query-independent absolute-match score（0..1），MIN_RELEVANCE 面向的唯一字段。
- **BM25 baseline**：`raw_score = s`（raw BM25 score）；`relevance = bm25_match_score(s)`；`match_score = bm25_match_score(s)`。
  因此 BM25 baseline 上 `relevance == match_score` 数值恒等；字段与 kind 仍分开保存，消费方不得互换。
  架构不依赖二者恒等：`tests/test_contracts_retrieval.py` 的合成非 BM25（RRF）向量证明 relevance ≠ match_score 时记录、
  序列化、全序与阈值语义均成立。
- 逐 hit 载体 = `core.contracts.RetrievalResultRecord`（独立于 Hit；Hit 未改），由 `Retriever.search_records` 产出：
  `chunk`、`chunk_id`（= chunk.id 的投影）、`corpus_ordinal`、`raw_score`、`raw_score_kind`、`relevance`、`relevance_kind`、
  `match_score`、`match_score_kind`。不含任何 gold / eval 信息、latency、墙钟时间。
- BM25 baseline 的 kind 取值（FROZEN，人工裁决）：
  `raw_score_kind = "bm25_raw"`、`relevance_kind = "bm25_saturation"`、`match_score_kind = "bm25_saturation"`。
  kind 描述"这个数是怎么算出来的"，不是字段名：relevance 与 match_score 都由饱和映射 `bm25_match_score(s)` 算出，
  故 BM25 baseline 上 `relevance == match_score` 且 `relevance_kind == match_score_kind`，允许且正确；字段语义仍不同。
  vector / hybrid 的 kind 与 relevance 定义：`NOT_FROZEN`。
- `S9_CALIBRATION_SEMANTICS = DEFERRED`（MIN_RELEVANCE 的校准 population 本实验不裁）。

## 6. BM25 baseline protocol

### 6.1 已冻结（人工裁决 D11）

| 项 | 值 |
|---|---|
| indexed text | `Chunk.text` only |
| indexed documents | canonical corpus 全部 3409 个 chunk，N = 3409 |
| analyzer（query 与 document 对称） | `unicodedata.normalize("NFC", ·)` → `str.casefold()` → 取 Unicode General_Category 为 L\*（Letter）/ N\*（Number）/ M\*（Mark，即 Combining_Mark）的码点的最长连续串为 token |
| stopwords / stemming | 不用 / 不做 |
| 数字 | 保留（N\* 类码点属于 token） |
| CJK segmentation | baseline 不做（canonical corpus 无 CJK chunk）；multilingual limitation 必须在报告中显式记录（§8.3） |
| IDF | `ln(1 + (N − n + 0.5) / (n + 0.5))`，n = 含该 token 的 chunk 数；对全部 1 ≤ n ≤ N 恒 > 0 |
| k1 / b | 1.2 / 0.75 —— preregistered baseline default，**不得在 v5.3 上调参** |
| tf / 文档长度 / avgdl | tf = token 在该 chunk token 序列中的出现次数；\|d\| = 该 chunk 的 token 数；avgdl = 全部 N 个 chunk 的 \|d\| 均值 |
| 返回过滤 | 只返回 raw BM25 score > 0；按 §4 全序取前 k = 20 |
| BM25_SCORE_SATURATION | 不参与 BM25 单路 ranking，只用于 relevance / match_score 映射 |
| persistent index artifact | 不需要 |

说明：analyzer 一行中"L\* / N\* / M\*"是对 D11"Unicode 字母 / 数字 / combining marks"的机械翻译（Unicode 中 Combining_Mark 即 General_Category M）。
analyzer 依赖 Python `unicodedata` 的 Unicode 数据库版本，必须进入 run identity（§9.1）。写作时本机为 Python 3.12.14 / unidata 15.0.0。

### 6.2 单题打分式（除 §6.3 外已冻结）

    s(q, d) = Σ_{t ∈ Q(q)}  IDF(t) · tf(t,d) · (k1 + 1) / ( tf(t,d) + k1 · (1 − b + b · |d| / avgdl) )

其中 Q(q) = query 的 analyzer token 序列本身（物理顺序、保留重复，MULTISET）—— 见 §6.3。query 无 token（或无 token 命中任何 chunk）→ 全部 s = 0 → 返回 []（"确实没检索到"，不是异常）。

### 6.3 query term semantics 与累加（FROZEN，人工裁决）

冻结的是**数学语义**，不是实现的回调执行轨迹。

- `BM25_QUERY_TERM_SEMANTICS = MULTISET`：analyzer 产生的 query token 序列保留重复 token，**每一次出现**都对 raw score 贡献一次
  对应 term 的 BM25 contribution。例：`["alcohol", "alcohol", "testing"]` →
  `score(q, d) = contribution(alcohol, d) + contribution(alcohol, d) + contribution(testing, d)`。不得先转成 set / unique terms / 去重。
- `BM25_MULTIPLICITY_SEMANTICS = MATHEMATICAL_OCCURRENCE_MULTIPLICITY`：贡献多重集 C 由 analyzer 输出序列给出，每次出现恰为 C 中一个元素。
- `BM25_ACCUMULATION = MATH_FSUM`：raw score = `math.fsum(C)`。不得用 set / 无序容器构造 C（会丢失多重性）；不得用其他累加器
  （朴素循环、内建 `sum()`）代替。fsum 对有限输入给出精确和的正确舍入，结果只取决于多重集 C，与元素顺序无关 ——
  因此元素顺序**不是**契约可见属性，测试也不以顺序为 oracle。
- `BM25_CALLBACK_INVOCATION_COUNT_IS_CONTRACT = NO`：contribution 函数被调用的次数与顺序不属于契约。逐次求值（Implementation A）与
  按不同 token 缓存后复用（Implementation B）只要 C 相同即都合法；合法缓存不得改变 raw score。前提：contribution 对固定文档是 token 的纯函数。
- 可执行形式：`core.contracts.bm25_accumulate(query_tokens, term_contribution)` —— 只接受 list / tuple（拒绝 set / frozenset / dict /
  Counter / 生成器 / str，防止已去重或无序表示静默改变多重性），按上述多重集返回 `math.fsum`。BM25 实现必须用它累加。
- **SET-vs-MULTISET selection on v5.3 is prohibited test-set tuning.** 不得在 v5.3 上比较 SET 与 MULTISET（或任何其他 query term
  语义）后择优；本裁决是 preregistered baseline semantics。
- 理由（人工）：SET 是额外的信息删除；MULTISET 保留 query term frequency；document 侧 BM25 使用 tf，没有证据支持在 query 侧删除 frequency。
- protocol-impact evidence（`MEASURED`，只读 probe：按 §6.1 analyzer 切分 39 道 question，未计算任何 BM25 分数；**不是检索结果**）：
  21 / 39 题含重复 analyzer token（共 58 次额外出现），例：FL06 `alcohol`×4、`testing`×3；CD02 `internal`×3；PR04 `permit` / `work` 各 ×2。
- `math.fsum` runtime gate（`MEASURED`，本机 CPython 3.12.14 / arm64 / Darwin）：存在；`float_repr_style = short`、mant_dig 53；
  20000 个 BM25 形状的非负随机向量上 fsum == 精确和的正确舍入 20000 / 20000，打乱顺序后结果改变 0 / 20000
  （朴素左到右循环在 1196 / 2000 例中正反序不等）；CPython 3.12 起内建 `sum()` 对 float 改用补偿求和（`sum([1e16, 1.0, -1e16])` = 1.0，
  朴素循环 = 0.0），故不得以 `sum()` 代替。fsum 对 inf / nan 不报错 → `bm25_accumulate` 先拒绝非有限、负数与 bool 贡献。
  平台注记：CPython 文档注明 fsum 在使用 x87 扩展精度的构建上可能偶发末位双重舍入；本仓库只有上述 arm64 实测，船端 x86 硬件未测（M6）。

### 6.3.1 数学语义与实现的边界；可复现性作用域

- D11 已冻结 analyzer、非负 IDF、k1 = 1.2、b = 0.75、term contribution 公式（§6.1 / §6.2）；本节只追加 query multiplicity 与累加方式。
- **不冻结**：特定 libm 实现、特定 CPU 浮点微架构、跨平台逐比特相同的 `math.log`，以及单个 contribution 的浮点求值式（由实现固定）。
- 可复现性作用域：**同一 committed implementation（code_commit）+ 同一声明的 runtime / protocol identity（§9.1）→ 期望确定性 artifact**
  （Run A == Run B 逐字节相同，§9.2）。**不**宣称任意 Python / libm / 平台之间 BM25 raw score 逐比特相同 —— 仓库没有支持该主张的证据。

### 6.4 retrieval_config payload（bm25，FROZEN）

payload 与 digest 见 §10.2 `retrieval_config_digest`。相对最初列出的字段清单，增加了 `term_contribution`（§6.2 的公式；
不入 digest 则 digest 不绑定 tf 归一化式）；`query_term_multiplicity` 与 `numeric_evaluation` 按 §6.3 / §6.3.1 写明数学多重性、
回调调用次数不是契约、可复现性作用域与不宣称跨平台逐比特相同。

---

## 7. 指标与分母

### 7.1 固定-k

- `EVAL_RECALL_K_SET = (1, 2, 3, 5, 20)`；`RETRIEVAL_K_MAX = TOP_K_RETRIEVE = 20`；保存完整 top-20 ranking。
- topk(q) = 已保存 ranking 的前 min(k, len(ranking)) 条；gold(q) = `GoldChunkMap.mapping[question_id]`。
- `ANY_GOLD@k` = 1 iff |topk ∩ gold| ≥ 1 —— navigation：是否至少触达一份 formal gold evidence。
- `GOLD_COVERAGE@k` = |topk ∩ gold| / |gold| —— 主 aggregate = 31 道可答题的 macro 平均；micro（47 个题目–chunk 对）只作诊断。
- `ALL_MAPPED_GOLD@k` = 1 iff gold ⊆ topk —— **strict map-union diagnostic**，见 §8.1；不得命名或宣称为
  EVIDENCE_COMPLETE / ANSWER_COMPLETE / COMPLETE_EVIDENCE。
- `PACKING_REALIZED_K` 是 pack_context 的逐题输出，不是 evaluation cutoff。HISTORICAL "306 tokens/chunk" 不得用于推导 k。

### 7.2 结构上限（`DERIVED`，只由 canonical map 的 |gold| 算出，不是检索结果）

|gold| 分布 1:21 / 2:7 / 3:1 / 4:1 / 5:1（Σ = 47）。任何 retriever 都不可能超过：

| k | ALL_MAPPED_GOLD 上限 | 结构不可达（\|gold\| > k） | GOLD_COVERAGE macro 上限 |
|---|---|---|---|
| 1 | 21/31 | CD01 CD02 CD03 CN03 FL06 FL07 ML02 PR01 PR03 PR06 | 0.8156 |
| 2 | 28/31 | CD01 FL06 FL07 | 0.9538 |
| 3 | 29/31 | CD01 FL06 | 0.9790 |
| 5 | 31/31 | — | 1.0000 |
| 20 | 31/31 | — | 1.0000 |

审计 CSV 逐题逐 k 标 structural-unreachable flag；报告 ALL_MAPPED_GOLD 时必须同时给出上限。

### 7.3 answer / refuse 分母

- `ANSWER_RECALL_DENOMINATOR = 31`（全部 answer 题，含 multilingual）。
- 8 道 refuse / trap 全部执行检索；TR02 executed = YES、exclude_from_primary_score = YES；`PRIMARY_TRAP_DENOMINATOR = 7`。
- 陷阱题逐题展示，不报百分比式强结论。至少保存：top-20 ranking、raw_score、relevance、match_score、max_match_score、
  top-1 document、empty-result flag。
- `known_distractor` rank：`NOT_DEFINED`（known_distractor.source 是自由文本、页码口径混用）。

### 7.4 multilingual

- overall answer metrics 用 31 题；English breakout 用 28 题；zh / tl / hi（ML01 / ML02 / ML03）逐题报告，不对 n = 3 做百分比式推断。
- pair_id 只做描述性比较。pair gold：P-master-handover（FL01↔ML01）相同；P-dpa-notify（FL12↔ML03）相同；
  **P-drug-freq（FL06 4 chunks ⊋ ML02 2 chunks）不同，必须显式标注，不得直接等价比较。**

### 7.5 reranker 观察

- `RERANKER_OBSERVATION_K = (2, 3)`；`RERANKER_DECISION_THRESHOLD = NOT_FROZEN`。
  不得把 @2 固化为最终 reranker gate；在 §11 的 real retrieval-window measurement 之后再裁。

---

## 8. Known limitations（写于结果之前）

### 8.1 ALL_MAPPED_GOLD 对含"非必需 citation"的题系统性偏严

`ALL_MAPPED_GOLD_STATUS = STRICT_MAP_UNION_DIAGNOSTIC_WITH_KNOWN_SUPPORTING_CITATION_BIAS`。

GoldChunkMap 的 mapping 是该题全部 citation formal cover 的并集，不表达 citation 之间的逻辑关系（AND / OR / 仅佐证）。
D1-A probe（`DERIVED`，依据人工撰写的 testset 文本，未写回 testset）显示至少以下 3 题含支撑 acceptable element 或仅作佐证的 citation：

| qid | formal map | citation 角色（probe） | 必需 citation 的 cover（机械取自 report.csv） | 非必需 citation 的 cover | probe 强度 |
|---|---|---|---|---|---|
| CD01 | 5 chunks / 3 citations | #0 SMM p73 ∧ #1 ERM p105 必需；#2 SMM p74 只支撑 acceptable | **4 chunks**：SMM:p73:0、SMM:p73:1（#0 L2）+ ERM:p105:0、ERM:p105:1（#1 L2） | 1：SMM:p74:0 | 强 |
| FL07 | 3 chunks / 2 citations | #0 p32 必需；#1 p34 只支撑 acceptable | 2：QMM:p32:4、QMM:p32:5 | 1：QMM:p34:2 | 强 |
| FL06 | 4 chunks / 2 citations | #0 p33 必需；#1 p34 佐证 | 3：QMM:p33:0、QMM:p33:1、QMM:p33:2 | 1：QMM:p34:0 | 中 |

"必需 citation 的 cover"一列的 chunk 数是在 probe 角色**成立的前提下**从 report.csv `formal_chunk_ids` 机械并出的；角色本身是 `DERIVED`，未经人工确认。

因此：
- 对这些题，ALL_MAPPED_GOLD 比 required-element 层面的完整证据更严；
- **低 ALL_MAPPED_GOLD 不得自动解释为 retrieval failure，也不得解释为 insufficient answer evidence**；
- 在人工逐 citation 标注角色之前，不得把任何 ALL 型指标宣称为 answer-level complete-evidence primary metric。

### 8.2 CN03

`CN03_CITATION_LOGIC = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW`。

CN03 的两项 required_elements 只出现在 ERM p14（`MEASURED`：`ERM:p14:0` 含 "overall management" / "main contact"，`QMM:p46:1` 不含），
指向 #0 必需；rationale 的宽松描述（"无论检索到哪一处…都不被判 0"）表达 OR 意图。required_elements / canonical evidence 与 rationale
不能同时推出唯一 citation logic。本实验不修改 testset、不替人裁 CN03；CN03 的 ALL_MAPPED_GOLD 与 GOLD_COVERAGE 按 formal map 计算，
报告中逐题附此冲突标注。

### 8.3 multilingual / CJK

baseline analyzer 不做 CJK segmentation；canonical corpus 无 CJK / 天城文 chunk。`DERIVED`（analyzer 定义 + corpus 性质，非检索结果）：
ML01（zh）的 query 被切成 2 个汉字长串 token，不可能与任何 chunk token 相同 —— 任何满足 §6 的 BM25 实现对 ML01 都必然返回 []。
ML01 的 BM25 结果只能说明本 analyzer 的结构限制，不能解释为"中文问题检索不到证据"。

### 8.4 其他

- `REQUIRED_ELEMENTS_SUFFICIENT_TO_INFER_CITATION_LOGIC = PARTIAL`；`MULTI_CITATION_LOGIC_GAP = PARTIAL`（D1-A）。
- S8 只给出 evidence coverage；不评估答案质量（§12）。

---

## 9. 结果 artifact

### 9.1 run identity

至少（D10）：`schema_version`、`contracts_version`、`corpus_chunks_sha256`、`gold_chunk_map_sha256`、`testset_sha256`、
`retrieval_variant`、`retrieval_config_digest`、`query_protocol_digest`、`metric_protocol_digest`、`total_order_protocol_digest`、runtime identity。
vector / hybrid 另加 embedder model / tag、model blob digest、embedding dimension、embedding protocol digest、embeddings artifact sha。

另加：`contracts_sha256`（运行时 `core/contracts.py` 文件字节的 SHA-256）、`code_commit`（完整 40 位）、`python_version`、
`unicodedata_unidata_version`、`platform`。版本拆分后 `contracts_version` 记整模块版本（0.4.0 起）；
contracts_sha256 仍保留，使契约内容由字节而不只由版本号识别。

BM25 run identity 对象（FROZEN，键序即下列顺序；vector / hybrid 专属键不出现）：

    schema_version, contracts_version, contracts_sha256, code_commit, corpus_chunks_sha256, gold_chunk_map_sha256,
    testset_sha256, retrieval_variant, retrieval_config_digest, query_protocol_digest, metric_protocol_digest,
    total_order_protocol_digest, python_version, unicodedata_unidata_version, platform

- `schema_version = "M1c_S8_retrieval_result_v1"`；`retrieval_variant = "bm25"`；各 digest 必须等于 §10.2 的 EXPECTED 字面量。
- `python_version = platform.python_version()`；`platform = platform.platform()`；`unicodedata_unidata_version = unicodedata.unidata_version`。
- `code_commit` 只有在运行时 tracked 树干净时才代表运行代码；tracked 树不干净 → 不得产出 normative artifact。
- 不含墙钟时间、latency、绝对路径。

### 9.2 normative artifact（deterministic JSONL）

- UTF-8；每行 = `json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"`；字段顺序固定（不 sort_keys）。
- **不含** wall-clock timestamp、latency、绝对路径。latency 只进 audit sidecar。
- 逐 hit 对象 = `core.contracts.retrieval_record_json_object(record)`，字段顺序 = `RETRIEVAL_RECORD_JSON_FIELDS`：
  `chunk_id, corpus_ordinal, raw_score, raw_score_kind, relevance, relevance_kind, match_score, match_score_kind`。
  raw_score：float → JSON 数；Fraction → 字符串 "p/q"。
- 逐题对象字段顺序（FROZEN）：`question_id, expected, type, language, gold_count, empty_result, max_match_score,
  top1_doc_id, first_gold_rank, gold_ranks, hits`。
  - eval 元数据（expected / type / language / gold_count）只在排序完成后按 question_id join 进本行，不进入 record；
  - `gold_count` = |GoldChunkMap.mapping[qid]|，refuse 题为 0；
  - `empty_result` = (hits == [])；为空时 `max_match_score` / `top1_doc_id` / `first_gold_rank` 为 null（不是 0.0）；
  - `max_match_score` = max(hit.match_score)；`top1_doc_id` = hits[0] 对应 Chunk 的 doc_id；
  - `first_gold_rank` = top-20 内第一个 gold chunk 的 rank，无则 null；`gold_ranks` = top-20 内全部 gold chunk 的 rank 升序列表，无则 []。
- 两种序号**不同基，不得统一**（FROZEN）：

  | 量 | 基数 | 含义 |
  |---|---|---|
  | retrieval rank | **1-based** | 记录在本题 hits 序列中的位置：rank 1 = first retrieval result |
  | corpus_ordinal | **0-based** | corpus_ordinal 0 = canonical `corpus/chunks.jsonl` 的 first physical line；不是 pdf_page、不是页内 chunk 序号、不是 chunk_id 字典序位置 |

- 文件布局（FROZEN）：第 1 行 = run identity 对象（§9.1），第 2–40 行 = 39 道题、每行一题、按冻结评测集文件顺序。
- Retriever 接口（FROZEN）：`search_records(query: str, k: int = TOP_K_RETRIEVE) -> Sequence[RetrievalResultRecord]`。
- 确定性验收：同一冻结输入、同一 code_commit 跑两次（Run A / Run B），normative artifact 逐字节相同，否则结果不得使用。
- metric 值必须能由纯函数、**不重跑 retrieval** 地重算；输入只允许：normative artifact + 经 run identity sha 绑定的冻结输入
  （GoldChunkMap、testset、corpus）+ 本预注册的冻结字面量。aggregate 不作唯一事实来源。
  （上一稿写作"normative artifact + GoldChunkMap"，与 §11 packed measurement 需要 corpus 的 est_prompt_tokens 自相矛盾，本稿更正。）
- 每道题的 hits 必须通过 `validate_retrieval_records(hits, k=20, corpus_chunk_ids=<canonical 行序>)`。

### 9.3 audit / report（非 normative）

per-k ANY_GOLD、GOLD_COVERAGE、ALL_MAPPED_GOLD、structural-unreachable flag、latency、diagnostics；不复用 EvalItemResult / `eval/results.csv`。

### 9.4 result schema 完整性（只读核对，写于结果之前）

`RESULT_SCHEMA_COMPLETE = YES`：下列每一项都能在不重跑 retrieval 的前提下重算。

| 冻结量 | 所需信息 | normative artifact 内 | 另需（sha 绑定的冻结输入 / 字面量） |
|---|---|---|---|
| ANY_GOLD / GOLD_COVERAGE / ALL_MAPPED_GOLD @1/2/3/5/20 | 每题 top-20 的 chunk_id 顺序；gold(q) | hits[].chunk_id（按序） | GoldChunkMap（gold_chunk_map_sha256） |
| first_gold_rank / gold_ranks | 同上 | 已存，且可由 hits 重算 | GoldChunkMap |
| structural-unreachable flag / §7.2 上限 | \|gold\|、k | gold_count | — |
| 分母 31 / 28 / 8 / 7 | expected、language；TR02 排除 | expected、language、question_id | metric payload 字面量 `excluded_from_primary_trap = ["TR02"]` |
| zh / tl / hi 逐题 | language、question_id | 是 | — |
| pair 描述性比较 | pair_id ↔ question_id | **否** | testset（testset_sha256）按 question_id join |
| refuse / trap 诊断 | hits、max_match_score、top1_doc_id、empty_result、type | 是 | — |
| reranker 观察 k = 2 / 3 | 同 ANY / COVERAGE | 是 | GoldChunkMap |
| packed-context measurement | top-20 顺序与 relevance；chunk 的 est_prompt_tokens / 正文（tokenizer） | hits（顺序、relevance、corpus_ordinal、chunk_id） | corpus（corpus_chunks_sha256），按 corpus_ordinal 取 Chunk |
| S9 再分析 | 每个 hit 的 match_score / raw_score 及 kind | 是 | — |

唯一不在 artifact 行内的 eval 元数据是 pair_id；它属于 eval 元数据而非检索输出，按 D10 的逐题最小字段清单不进行内，由 sha 绑定的 testset join。

机械验证（`MEASURED`，写于结果之前）：用**合成** ranking（种子随机抽取 corpus 行与 gold，非检索输出、未计算任何 BM25 分数）按本节冻结 schema
生成 39 行、经 JSON 往返后，仅凭行内容 + sha 绑定的 corpus / GoldChunkMap / testset 重算：rank / first_gold_rank / gold_ranks / corpus_ordinal→chunk /
top1_doc_id 一致；五个 k 的 ANY / COVERAGE / ALL 均可算（31 题）；分母 31 / 28 / 8 / 7 与 zh / tl / hi 逐题可得；pair 经 testset join 得到；
packed-context 由 corpus_ordinal 重建 Hit 后调用可执行 `pack_context` 得到。

---

## 10. Digest protocol

### 10.1 算法（冻结）

`digest = core.contracts.canonical_sha256(payload)`，即对
`json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` 的 UTF-8 字节（**无**末尾换行、
不做 Unicode 规范化）取 SHA-256，64 位小写十六进制。payload 只允许 dict（str 键）/ list / str / int / bool / null / 有限 float；
dict 键序不影响结果，数组顺序影响结果。不得 digest Python repr、墙钟时间、本机绝对路径；payload 内的字符串即被冻结的字节。

仓库既有 digest 口径（`ingest/builder_identity.construction_rules_identity`：ensure_ascii=False、无 sort_keys；
`components/parsers/ocr_artifact.ocr_params_digest`：sort_keys=True、ensure_ascii=True）都是组件内私有、各自已冻结，不迁移；
contracts 此前没有统一 helper，本协议是第一个跨实验的 canonicalization（对纯 ASCII payload 与 ocr_artifact 口径逐字节一致）。

### 10.2 冻结 payload 与期望值

下列每个代码块的内容就是被哈希的完整字节（单行，无末尾换行）。runner 必须在代码中构造等价 payload，算出的 digest 与此处的
EXPECTED 字面量比较，不等即抛异常（EXPECTED 不得从 runner 自己的 payload 反推）。

`total_order_protocol_digest` = `99c87596d8c964a585f0c38c8a312066afa7e3517d9e963c4d6f182ed4e04221`（631 bytes）

```json
{"corpus_ordinal":"zero_based_physical_line_index_in_canonical_corpus_chunks_jsonl","digest_name":"total_order_protocol","exact_raw_score_representation_for_rrf":"fractions.Fraction","executable":"core.contracts.retrieval_order_key","forbidden_tie_breakers":["chunk_id_lexicographic","doc_or_page_order","any_eval_or_gold_information"],"payload_version":1,"primary_direction":"descending","primary_key":"raw_score","sequence_validator":"core.contracts.validate_retrieval_records","tie_break_direction":"ascending","tie_break_key":"corpus_ordinal","tie_condition":"exact_equality_of_raw_score","truncation":"first_k_of_total_order"}
```

`query_protocol_digest` = `e26afbf39257f8674d98a51541c75ebe2c66a4684ceb83ed3f6a918b290b85a9`（1000 bytes）

```json
{"digest_name":"query_protocol","forbidden_eval_fields":["EvalItem.acceptable_elements","EvalItem.answer_key","EvalItem.at_risk","EvalItem.citations","EvalItem.exclude_from_primary_score","EvalItem.expected","EvalItem.gold_answer","EvalItem.known_distractor","EvalItem.language","EvalItem.pair_id","EvalItem.rationale","EvalItem.required_elements","EvalItem.safety_critical","EvalItem.source_boundary_ambiguity","EvalItem.trap_subtype","EvalItem.type","GoldChunkMap","GoldChunkMap.report_csv","gold_chunk_ids"],"forbidden_uses":["boost","dynamic_k","filter","query","routing","tie_break"],"items_executed":"all_items_in_testset_file_order_including_refuse","llm_rewrite":false,"metadata_augmentation":false,"payload_version":1,"query_source":"EvalItem.question","query_string_transform":"identity","question_id_use":"join_key_after_ranking_only","text_normalization_owner":"retriever_analyzer_applied_symmetrically_to_query_and_document","translation":false,"whole_evalitem_as_retrieval_input":false}
```

`metric_protocol_digest` = `e78d361fed8c3a945d3333b879df909f2e6a565502f0f0c3c6b3a3b0cf38ef6b`（1100 bytes）

```json
{"aggregation":{"micro_over_question_chunk_pairs":"diagnostic_only","primary":"macro_mean_over_answer_items"},"denominators":{"answer_english":28,"answer_overall":31,"excluded_from_primary_trap":["TR02"],"primary_trap":7,"refuse_executed":8},"digest_name":"metric_protocol","gold_set":"GoldChunkMap.mapping[question_id]","k_max":20,"k_set":[1,2,3,5,20],"known_distractor_rank":"NOT_DEFINED","metric_status":{"ALL_MAPPED_GOLD":"strict_map_union_diagnostic_not_answer_completeness"},"metrics":{"ALL_MAPPED_GOLD":"1 if gold <= topk else 0","ANY_GOLD":"1 if len(topk & gold) >= 1 else 0","GOLD_COVERAGE":"len(topk & gold) / len(gold)"},"multilingual":{"non_english_languages":["hi","tl","zh"],"non_english_reporting":"per_item","pair_comparison":"descriptive_only","pair_gold_mismatch_must_be_flagged":["P-drug-freq"]},"payload_version":1,"refuse_item_reporting":"per_item_no_percentage_claims","reranker_decision_threshold":"NOT_FROZEN","reranker_observation_k":[2,3],"s9_calibration_population":"DEFERRED","saved_ranking_depth":20,"topk_definition":"first_min(k,len(ranking))_records_of_saved_ranking"}
```

`retrieval_config_digest`（bm25）= `3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e`（1495 bytes）

```json
{"analyzer":{"applied_to":"query_and_document","cjk_segmentation":false,"digits_kept":true,"stemming":false,"steps":["unicodedata.normalize:NFC","str.casefold","maximal_runs_of_unicode_general_category_L_N_M"],"stopwords":false},"avgdl":"mean_document_length_over_all_indexed_documents","b":0.75,"digest_name":"retrieval_config","document_length":"token_count","idf":"ln(1 + (N - n + 0.5) / (n + 0.5))","indexed_documents":"all_chunks_in_canonical_corpus","indexed_text":"Chunk.text","k":20,"k1":1.2,"match_score":"core.contracts.bm25_match_score(raw_score)","match_score_kind":"bm25_saturation","numeric_evaluation":{"accumulation":"math.fsum","accumulation_input":"contribution_multiset_one_element_per_analyzer_query_token_occurrence","callback_invocation_count_is_contract":false,"cross_platform_bit_identity_claimed":false,"executable":"core.contracts.bm25_accumulate","float":"IEEE-754_binary64","reproducibility_scope":"same_code_commit_and_same_declared_runtime_identity","term_contribution_float_evaluation":"implementation_defined"},"payload_version":1,"persistent_index_artifact":false,"query_term_multiplicity":"MULTISET_mathematical_occurrence_multiplicity","raw_score_kind":"bm25_raw","relevance":"core.contracts.bm25_match_score(raw_score)","relevance_kind":"bm25_saturation","retrieval_variant":"bm25","return_filter":"raw_score > 0","term_contribution":"idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))","term_frequency":"count_of_token_in_document_token_sequence"}
```

---

## 11. fixed-k 与 packed context 分离；real retrieval-window measurement

- `FIXED_K_RETRIEVAL_BASELINE` 不读取 MAX_PROMPT_TOKENS / PROMPT_OVERHEAD_RESERVE_TOKENS / CONTEXT_PACK_MARGIN /
  CONTEXT_PACK_BUDGET_TOKENS / TOP_K_CONTEXT / pack_context，不被 numeric token-contract decision 阻塞。
- 条件失效：`CHARS_PER_TOKEN_EST` 同时参与 canonical chunk construction；若将来修改它并改变 canonical chunking，
  corpus、GoldChunkMap 与本实验 fixed-k 结果全部失效。
- **real retrieval-window measurement**（`PACKED_CONTEXT_MEASUREMENT`）：在冻结的 S8 normative artifact 上、对每题已保存的 top-20 ranking，
  用当前可执行打包契约（`pack_context`，预算 765）及后续候选预算重新模拟 —— realized k 分布、packed ANY / coverage / ALL_MAPPED_GOLD、
  overbudget、actual token cost —— **无需重跑 retrieval**。它取代按语料顺序连续窗口（`_s4a9c_final_canonical_windows.csv`）作为 reranker k 的证据，
  为 numeric token-contract decision 提供 evidence，不得反向阻塞 fixed-k baseline。
- final packed-context conclusions 在 numeric contract freeze 之后确认。未来 TTFT / token budget 调整不构成重跑 fixed-k retrieval 的理由，
  除非 corpus identity、retrieval protocol 或 model / index identity 本身变化。

## 12. TTFT 与 evidence coverage 的边界

- `TTFT_BUDGET_10S_STATUS = BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED`。
- `MAX_ACCEPTABLE_TTFT_EXPLORATION_CEILING = 180_SECONDS_NOT_AN_EXECUTABLE_CONTRACT`：180 秒是 exploration ceiling，
  不是 target、SLA、executable contract，也不是 MAX_PROMPT_TOKENS；不得把任何开发机 tokens/s × 180 换算成 production MAX_PROMPT_TOKENS。
- S8 提供 budget → packed evidence coverage；M2 才提供 budget → answer quality。
- `S8_EVIDENCE_COVERAGE_IS_ANSWER_QUALITY = NO`：不得用 S8 evidence coverage 冒充 answer quality。
- 最终 latency / quality operating point 必须等 M2 evidence；目标是 trade-off / Pareto frontier 上的合理点，不是最大化 prompt，也不是逼近 180 秒。

## 13. 未就绪项

- `VECTOR_BASELINE_READY = NO`：bge-m3 model file identity 已测量；`MODEL_SELECTION_STATUS = NOT_FROZEN`；
  `EMBEDDING_PROTOCOL_IDENTITY = NOT_FROZEN`；需单独一轮 `EMBEDDING_PROTOCOL_PROBE`。
- `HYBRID_BASELINE_READY = NO`：方向 = unweighted RRF；RRF constant、per-route fusion depth、embedding dependency 未冻结；
  任何 weight sweep 只作 exploratory，不得在 v5.3 上选 M2 production configuration。
- `INDEX_MANIFEST_CONTRACT_GAP = YES`：本实验不创建 IndexManifest；run artifact 自己记录完整 identity（§9.1）。

## 14. 本实验不回答的问题

- 答案质量（M2）；检索参数调优、metadata augmentation、融合权重（M5）；MIN_RELEVANCE 取值（S9）；船端 runtime 与 TTFT（M6）。


---

## 15. Amendment 2026-10-02 · VECTOR BASELINE（写于任何 vector 检索结果之前）

- `PREREG_BEFORE_RESULTS = YES`：写作时没有任何 vector 检索结果、vector Recall 或语料 embedding 评测；仓库中没有 vector retriever 实现。
- 依据：DECISIONS 2026-10-02「S8 embedding protocol probe evidence」（测量）与「S8 vector embedding protocol human decision」（人工裁决 D-V1–D-V10）。
- 本节冻结 vector baseline；§1–§14 的 BM25 内容不变。共享不变的冻结项：query protocol（§2，`query_protocol_digest = e26afbf3…`）、
  indexed text（§3：`Chunk.text` only）、全序（§4，`total_order_protocol_digest = 99c87596…`）、指标与分母（§7，`metric_protocol_digest = e78d361f…`）、
  known limitations（§8）、结果 schema（§9.2 逐题字段顺序、rank 1-based、corpus_ordinal 0-based、首行 run identity、Run A == Run B）。

### 15.1 embedding protocol（FROZEN）

| 项 | 值 |
|---|---|
| model | `bge-m3:latest`；blob `sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`；manifest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab` |
| dimension | 1024 |
| runtime | Ollama server 0.34.0 / client 0.23.1（models.yaml 的 0.33.3 为历史记录） |
| endpoint | `POST /api/embed`，request `{"model": "bge-m3:latest", "input": <str 或 list>, "truncate": false}`，只读响应 `embeddings`；不用 legacy `/api/embeddings` |
| execution path | `MAC_DEFAULT_METAL`；不设 `num_gpu` 或任何 options；语料与 query 同一路径 |
| prefix | query `""`；document `""` |
| document text | `Chunk.text`（与 BM25 相同） |
| 存储值 | 按 /api/embed JSON 解析得到的 float64 原值，不做任何变换 |
| 空 / 全空白 query | 返回 []，不调用 endpoint |

`SHIP_X86_EQUIVALENCE = NOT_MEASURED`；`M6_SHIP_CPU_VALIDATION = REQUIRED_LATER`。不得在 v5.3 上比较不同 model / prefix / 执行路径后择优。

### 15.2 打分、全序与返回（FROZEN）

- `raw_score = numerator / (norm_a · norm_b)`，`numerator = math.fsum(a_i · b_i)`，`norm = sqrt(math.fsum(x_i · x_i))`；`raw_score_kind = "cosine"`。不以点积代替 cosine。
- `match_score = (raw_score + 1.0) / 2.0`，`match_score_kind = "cosine_affine_01"`；`relevance = match_score`，`relevance_kind = "cosine_affine_01"`。
  若浮点舍入使 match_score 越出 [0, 1]，RetrievalResultRecord 校验报错（fail-closed），不做截断。
- 全序：`retrieval_order_key(raw_score, corpus_ordinal)`，raw_score 降序，精确相等时 corpus_ordinal 升序。
- 不按 cosine 正负过滤；非空 query 返回 min(k, 3409) 条；k = 20，保存完整 top-20。
- 索引：对全部语料向量精确暴力计算（无 ANN / 向量库）。

### 15.3 语料 embedding artifact

- `experiments/m1c_s8_vector/corpus_embeddings.npy`：float64，shape (3409, 1024)，第 i 行 = canonical `corpus/chunks.jsonl` 第 i 行（0-based）；
  `corpus_embeddings.meta.json` 记录 corpus sha、行数、维度、dtype、chunk id 顺序摘要、model / manifest / runtime / endpoint / truncate / 执行路径 / prefix、
  embedding_protocol_digest 与 .npy sha256。生成后对固定子集用两个全新进程重新 embedding，必须与已存行逐位相同。

### 15.4 指标与结果

- 与 BM25 同口径（§7）：ANY_GOLD / GOLD_COVERAGE / ALL_MAPPED_GOLD @1/2/3/5/20（31 题 macro）、English 28、first_gold_rank、gold_ranks、
  multilingual 逐题（ML01 / ML02 / ML03）与 pair 描述、refuse / trap 逐题诊断。ALL_MAPPED_GOLD 仍只是 strict map-union diagnostic。
- 结果文件：`experiments/m1c_s8_vector/s8_vector_results.jsonl`（normative，首行 run identity）、`s8_vector_metrics.json`、`s8_vector_run.log`。
- vector run identity 键序（FROZEN）：§9.1 的 15 个键（`retrieval_variant = "vector"`）之后依次追加
  `embedder_model_tag, embedder_model_blob_digest, embedder_manifest_sha256, embedding_dimension, embedding_protocol_digest,
  corpus_embeddings_sha256, ollama_server_version, ollama_client_version, embedding_execution_path`。
- Run A / Run B：两个全新进程，normative artifact 逐字节相同，否则结果不得使用。`TEST_SET_TUNING_PERFORMED` 必须为 NO。
- 本节不包含 packing 测量；如需，可从保存的 top-20 另行重算。

### 15.5 冻结 payload 与期望 digest（算法同 §10.1）

`embedding_protocol_digest` = `38acb0b4260a516dffc32680067d5cb55c6c56d09a4d4045ebcda2d289b54af0`（689 bytes）

```json
{"digest_name":"embedding_protocol","dimension":1024,"document_prefix":"","document_text":"Chunk.text","endpoint":"POST /api/embed","execution_path":"MAC_DEFAULT_METAL","manifest_sha256":"7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab","model_blob_digest":"sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c","model_tag":"bge-m3:latest","options":"none_no_num_gpu_override","payload_version":1,"query_prefix":"","request":{"input":"str_or_list","model":"bge-m3:latest","truncate":false},"response_field":"embeddings","runtime":{"ollama_client":"0.23.1","ollama_server":"0.34.0"},"stored_vector_values":"float64_exactly_as_parsed_from_api_embed_json"}
```

`retrieval_config_digest`（vector）= `c9c3868cf19a77d2b88a705580367ba933930af28c265887d2da6aad7a0e7343`（808 bytes）

```json
{"digest_name":"retrieval_config","embedding_protocol_digest":"38acb0b4260a516dffc32680067d5cb55c6c56d09a4d4045ebcda2d289b54af0","empty_or_whitespace_query":"return_empty_without_endpoint_call","index":"exact_brute_force_over_all_corpus_vectors","indexed_documents":"all_chunks_in_canonical_corpus","indexed_text":"Chunk.text","k":20,"match_score":"(raw_score + 1.0) / 2.0","match_score_kind":"cosine_affine_01","payload_version":1,"raw_score":"numerator / (norm_a * norm_b); numerator = math.fsum(a_i * b_i); norm = sqrt(math.fsum(x_i * x_i))","raw_score_kind":"cosine","relevance":"(raw_score + 1.0) / 2.0","relevance_kind":"cosine_affine_01","retrieval_variant":"vector","return_filter":"none_by_sign_return_min_k_corpus_size","total_order":"core.contracts.retrieval_order_key(raw_score, corpus_ordinal)"}
```
