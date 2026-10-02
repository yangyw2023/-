# Phase B Design Freeze —— native extraction → selective OCR → citation-safe ingestion

状态：**DESIGN_FREEZE_STATUS = READY**

本文件冻结设计，不实现、不改 parser / contracts / corpus / testset。
详细论证在本文件内；最终回答只做摘要。

---

## 0. 冻结基线与证据入口

| 项 | 值 |
|---|---|
| HEAD | `1b0cfda`（docs: record S5 and OCR investigation decisions） |
| corpus | `corpus/chunks.jsonl` sha256 `8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa`，3383 chunks，1335 pages / 9 PDF |
| parser + builder provenance | `545947a`（DECISIONS：`545947a → corpus sha 8c6bee0a…` 是 S5 baseline 的正式生成 provenance） |
| 调查脚本 | `9611e9d` ocr_survey、`124403c` audit_citation_sections、`727a20b` ocr_visual_survey、`2e8e92c` A.2、`0df2ede` A.2b |
| 产物 | `experiments/ocr_survey/_page_signals.csv` `78e87446…`、`_visual_page_signals.csv` `dcb056e9…`、`_visual_threshold_validation.csv` `31c10291…`、`_content_completeness_census.csv` `3a6fbc10…`、`experiments/parser_audit/_citation_section_audit.csv` `4f76ab2a…` |
| measurement line | CLOSED（DECISIONS 2026-09-21 · OCR / parser 调查线关闭） |

引用的经验事实全部已在 DECISIONS 中留痕，本轮只做引用与转换，不新增测量。

---

## 1. 术语冻结：六个互不替代的被测量对象

**原则：一个字段只回答一个问题。以下六个名字在 Phase B 代码、审计与文档中互不混用。**

| 轴 | 回答什么 | 明确不回答什么 |
|---|---|---|
| `native_body_status` | native extraction 已取得的正文本身是否适合 retrieval / generation | 页面是否还有没被抽到的视觉知识；section 是否正确 |
| `page_content_completeness_status` | 页面业务内容是否已被当前 text representation 足够覆盖 | 已有文本是不是乱码；缺失内容是否值得索引 |
| `citation_metadata_status` | `(doc_id, section, pdf_page)` 是否能可靠支撑 Citation First | 正文是否正确、是否完整 |
| `ocr_body_status` | OCR 新取得的文本是否可用（仅在执行 OCR 后存在） | OCR 内容是否值得进 corpus；OCR 的 section 是否正确 |
| `content_policy_status` | 已抽到的内容是否值得进入 RAG corpus | 内容抽取质量 |
| `remediation_action` | 系统最终做什么（动作，不是观察） | 任何质量判断本身 |

三层分离（§4 层次）：

```
Layer 1 observations   alpha_token_ratio / control chars / parser_body_chars /
                       active_row_ratio / section source / 渲染像素统计 / OCR 引擎输出
        ↓ （detector，只产生 state，不产生动作）
Layer 2 page states    native_body / completeness / citation_metadata / ocr_body / content_policy
        ↓ （policy，只读 state，不读 raw signal）
Layer 3 actions        KEEP_NATIVE / OCR_ATTEMPT → OCR_REPLACE|OCR_PRIMARY /
                       SKIP_NONCONTENT / QUARANTINE / FAIL_INGEST / REQUIRE_REVIEW
```

**禁止 Layer 1 → Layer 3 直连。** policy 层不得读取任何原始信号；detector 层不得产生动作。
这条规则的作用是：让"一个信号承担业务价值判断"在代码结构上不可能发生
（A.2b 已证明 ink / active-row 不能回答 OCR worthiness）。

---

## 2. 状态枚举（最小充分集）

### 2.1 `native_body_status`

| 状态 | 精确定义（确定性判据） | 支持它的 observation | 不足以支持它的 observation |
|---|---|---|---|
| `usable` | body 通过 §2.1.1 的三条检查全部 | 有 ASCII 词 token、无 C0/C1 控制字符、body ≥ `CHUNK_MIN_CHARS` | "页面看起来正常" |
| `unusable` | body 长度 ≥ 1 token 且 `alpha_token_ratio == 0`，**且**文档语言在 Latin-script 作用域内 | Phase A：TACM 65/66，unreviewed trigger 0（`_criterion_calibration.log`） | `uni=no` / Type 3（DECISIONS：结构信号 ≠ 文本可用性） |
| `insufficient` | `parser_body_chars < CHUNK_MIN_CHARS`（即当前 parser 已有的丢页条件，不新增阈值） | Phase A：88 页 | 墨迹高低 |
| `uncertain` | 文档语言不在作用域内；或信号互相矛盾（如控制字符 > 0 但 `alpha_token_ratio > 0`） | —— | —— |

判定顺序（确定性、互斥）：`insufficient` → `unusable` → `uncertain` → `usable`。
`insufficient` 优先于 `unusable`：短 body 上的比值统计不稳定（TACM p.39–50 的 `"010213433"` 即是例子）。

**2.1.1 usable 的三条检查**（全部复用已有常量，不引入新阈值）：
`parser_body_chars ≥ CHUNK_MIN_CHARS`；`control_char_count_excluding_form_feed == 0`；`alpha_token_ratio > 0`。

### 2.2 `page_content_completeness_status`

**被评估的 population 仅限 body 非 `usable` 的页**（即 `insufficient` / `unusable`）；body `usable` 的页在 Phase B 内不评估（C3 决定，DF-06）。

| 状态 | 定义（确定性） | 说明 |
|---|---|---|
| `visual_content_suspected` | 页在被评估 population 内，且 active-row 审计信号落在 A.2 冻结规则的触发侧 | 仅审计用途，**不决定是否 OCR**（见 §4 / DF-05） |
| `presumed_complete` | 页在被评估 population 内，且未落在触发侧 | **不是"已证明完整"**，只表示本轮未发现缺失证据 |
| `not_assessed` | 页不在被评估 population 内（body `usable`） | 第三类 failure 的记录位置：状态存在、评估未做 |

不设 `complete` 状态：没有任何确定性测试能把"完整"与"未发现缺失"区分开（A.2b：完整性只能被内容级人工比对**否证**，不能被信号**证成**）。

### 2.3 `citation_metadata_status`

冻结枚举：**`explicit_supported` / `uncertain` / `failed`**。

> **术语更正（old/rejected terminology）**：本设计的早期草稿曾使用 `verified_structural`。
> 该名字过强——现有证据不能证明"显式标签 + 字符完整 + body usable"等价于"语义位置正确"。
> `verified_structural` 已作废，**不得**作为 production metadata state 出现在实现中。

| 状态 | 定义（确定性判据） | 依据 |
|---|---|---|
| `explicit_supported` | 五条同时成立：(1) page identity 硬门已通过；(2) 页面存在明确的 SECTION label；(3) 从该 explicit label 成功读到非空值；(4) 该值未命中已定义的机械损坏判据（无 C0/C1 控制字符、无 U+00FF 类乱码字符、含至少一个字母数字、长度 ≤ 上限）；(5) provenance 可指出 extraction channel、source line / region、raw extracted value | `_citation_section_audit`：`explicit_header_label` 覆盖 993 页 / 2789 chunks |
| `uncertain` | 至少一条成立：`title_line_fallback` 来源；继承来源；native 与 OCR metadata candidate 冲突；explicit label 存在但值无法可靠读取；metadata provenance 不完整；只有弱结构证据；多个候选值无法区分 | `title_line_fallback` 覆盖 254 页 / 594 chunks，其中 96 页 / 278 chunks 是异常候选 |
| `failed` | 存在明确失败证据：page identity mismatch；artifact page mismatch；metadata extraction 过程失败；值明确损坏且不存在可接受 candidate；必需 metadata 完全无法形成 | TACM p.38–103 的 37/50 有明显乱码证据 |

**`explicit_supported` is evidence-supported extraction, not semantic verification.**
它**不表示**：人工验证过语义正确性；已与目录 / 章节 ground truth 核对；
"属于 known section vocabulary" 因此正确；body usable 因此 metadata correct；citation 整体已被 verified。
TACM p.100 的 `"9"` 正是"看起来合法、且与真实章节集合碰撞、但来源与语义位置均未被验证"的反例形状。

**三条禁令**：显式标签不自动通过（还需其余四条）；`title_line_fallback` **不自动 `failed`**（fallback 本身不是错误的直接证据，只进 `uncertain`）；
"看起来奇怪"不构成 `failed`（`failed` 只接受明确失败证据）。

**representation vs semantic 分离**：`Chapter 15` vs `15` 属 representation difference（DECISIONS 已判，38/38 semantic location 一致），
**不进入本 gate**；本 gate 只处理来源、provenance 完整性与机械损坏判据。section canonicalization 属 scorer / renderer 设计，Phase B 不动。

### 2.3.1 metadata candidate 冲突语义

当同时存在 `native_metadata_candidate` 与 `ocr_metadata_candidate` 且两者不相等时，**禁止**：
自动优先 native；自动优先 OCR；用 known section vocabulary 自动择一；用相邻页 section 自动覆盖；静默继承；majority vote。

冻结：`citation_metadata_status = uncertain`，并记录
`native_metadata_candidate`、`ocr_metadata_candidate`、`metadata_conflict = true`、`metadata_reason_code`。

### 2.4 `ocr_body_status`

| 状态 | 定义（确定性，复用已有常量） |
|---|---|
| `not_attempted` | 未触发 OCR，或 artifact 不存在（后者另有 failure 语义，见 §8） |
| `usable` | OCR artifact 存在且 digest 校验通过；OCR 文本经同一去页眉页脚流程后 ≥ `CHUNK_MIN_CHARS`；且对该文本施加 §2.1 的 `unusable` 判据不成立 |
| `degraded` | artifact 存在且校验通过，但上述两条之一不满足（文本过短，或文本自身被判 `unusable`） |
| `failed` | OCR 进程非零退出 / 超时 / 输出为空 / artifact digest 不匹配 |

不设独立 `uncertain`：`degraded` 已覆盖"有输出但不达标"，再拆分没有确定性测试支撑。
**引擎置信度（如 tesseract word confidence）只写入审计字段，不参与状态判定**——引擎置信度不是 ground truth。

### 2.5 `content_policy_status`

| 状态 | 定义 |
|---|---|
| `admit` | 抽取结果通过 body gate 与 citation gate；默认值 |
| `reject_noncontent` | 去页眉页脚后 < `CHUNK_MIN_CHARS`（即 parser 既有规则），无独立"价值判断" |
| `hold_for_review` | 抽取成功但任一 gate 为 `uncertain`，或属于未来 augmentation 候选 |

**Phase B 不引入自动化的"业务价值"判定。** A.2b 已证明同为 Microsoft Forms，价值从实质规则到空输入框都有；
production 没有可确定性测试的 form/scaffold 判据（人工 review 标签不可用于 runtime）。

---

## 3. V1 的冻结角色（DF-04）

- **角色：scoped hard detector**，只产生 `native_body_status = unusable`，不产生动作、不回答完整性、不回答 citation。
- **作用域硬编码在代码里**：仅当文档语言属于 Latin-script 集合（当前 corpus `CORPUS_LANG_DEFAULT = "en"`，9/9 手册为英文）时生效。
- 作用域外：返回 `uncertain`，走 REQUIRE_REVIEW / OCR_ATTEMPT，**绝不自动判 unusable**。
- 禁止写法：`alpha_token_ratio <= 0` 永久等于 garbled。本设计把它定义为
  "在 Latin-script 文档上，正文完全没有字母词 token"这一**观察**，并把作用域写进实现。
- 证据强度：TACM 65/66（漏 p.55，该页无文本、渲染全白），unreviewed trigger 0；仅来自单一文档的单一区间，记为 residual risk。

## 4. V2 / active-row 的冻结角色（DF-05）

**active-row / active-column / ink / bbox 等全部视觉统计在 Phase B 中一律是 diagnostic / audit signals only，正式退出 production OCR gating。**

production rule 冻结为：

```
native_body_status == insufficient  →  OCR_ATTEMPT
```

**而不是**：`insufficient + active-row 阈值 → OCR_ATTEMPT`。
**不得因为 active-row 不触发而静默跳过任何 insufficient page。**

理由（五条，全部来自已有证据）：
- 当前 insufficient population 只有 88 页；
- OCR 在岸端执行，不影响船端；
- OCR 是一次性 / 缓存化成本（artifact 冻结后不再重跑）；
- false negative 的代价是业务内容继续静默缺失（A.2 已证 66/88 页含业务视觉内容）；
- 用一个 NEG=7 的 classifier 省下几十页 OCR，不值得承担该 correctness risk。

`STRUCTURE_CASE_1` 的正确解释：在 A.2 的 66 POS / 7 NEG 标签上，active-row 成功解释并解决了
cover-vs-business-content 的 middle-ink 冲突，说明 **visual structure distribution 比 raw ink amount 在该冲突上更有诊断信息**。
它**不证明**：active-row 是 production detector；阈值已 generalize；NEG=7 足以刻画 false-positive 行为；
未来文档集可直接复用该阈值。

其余保留：

1. **active-row 只写审计**：产生 `page_content_completeness_status = visual_content_suspected`，
   用于人工复核排序与未来评估，不影响 corpus 内容，也不影响是否 OCR。
2. **阈值不在本轮重定。** 实现时若要在审计里给出触发侧标记，由冻结规则重算：
   feature = `d40_active_row_ratio_245_f0p01`，阈值 = A.2 预注册的 midpoint 规则在 A.2 冻结标签
   （66 POS / 7 NEG，`_visual_threshold_validation.csv`）上的取值，由代码计算而非手抄。
   **禁止重新搜索特征或阈值。** 该阈值只影响审计标记，不影响任何动作。
3. **作用域**：只在 `insufficient` population 上计算，不扫描全部页面。全页扫描既无标签支撑，也会诱发把它当完整性 detector 使用。

**明确记录：`STRUCTURE_CASE_1 ≠ production-proven detector`。**

## 5. 第三类 failure 的 Phase B 范围（DF-06）

比较：

| | C1 只修 class 1+2 | C2 同时做 class 3 augmentation | **C3 建 state + 接口，不自动 OCR**（选定） |
|---|---|---|---|
| corpus 影响 | 无额外 | 16+ 页文本翻倍风险 | 无额外 |
| chunking 影响 | 无 | augment 改变 chunk 数与 ordinal，风险最大 | 无 |
| retrieval 影响 | 无 | 重复正文抬高 BM25 词频、扭曲向量 | 无 |
| citation 影响 | 无 | 同页两个 extraction channel 的出处归属需新语义 | 无 |
| determinism | 同 C3 | 额外的 merge 非确定性面 | 同 C1 |
| 复杂度 | 最低 | 最高 | 低（多一个 state + 审计字段） |
| 需要新 detector | 否 | 是（需要能判"缺什么"） | 否（沿用 A.2b 口径，仅审计） |
| 阻塞 S6 | 否 | 是 | 否 |

**冻结：Scope C3。**
依据：16 个 confirmed examples 跨 6 本手册确有其事，但 (a) prevalence 未估计；
(b) 当前 4 条相关 gold citation 的 10/10 quote fragments 仍在 corpus 中（窄义 R2）；
(c) augmentation 的 merge / chunking 风险显著高于其收益证据。
**残余风险**：船员提问若正好落在图内知识（如 ERM p.14 的上报关系、QMM p.110 的 MOC 步骤），
当前 corpus 无法回答；M5 复核。

**同时冻结未来接口**（避免未来只能字符串拼接）：页文本模型为
`page_text = [TextBlock(source_channel, order, text, bbox_hint?)]`，
parser 内部以 block 列表组装正文；Phase B 只会出现单 channel 列表，
但 augmentation 未来可追加 block 而不需要重写 merge 语义。

## 6. OCR 架构（DF-08）

**冻结：方案 C（hybrid）—— 岸端独立的 page-level OCR 步骤，产出 digest 寻址的冻结 page-text artifact；parser 只消费 artifact。**

```
raw/*.pdf （immutable）
   └─ ingest 第 1 步：native 扫描 + detector → page states（只读，不 OCR）
   └─ ingest 第 2 步（独立可重跑）：对被 policy 选中的页
        pdftoppm 光栅化（内存/临时目录）→ OCR 引擎 → 写
        ocr_cache/<source_sha256>/p<pdf_page>.json  （text + 引擎 provenance + 自身 sha256）
   └─ ingest 第 3 步：parser 读源 PDF 的 native 文本 + 对应页的 frozen artifact
        → 按 merge 语义组装 → chunks.jsonl + ingest/page_quality.jsonl
```

对比结论：

| 维度 | A 派生 PDF | B ingest 内联 OCR | **C（选定）** |
|---|---|---|---|
| 源 PDF 不变 | 是 | 是 | 是 |
| page identity | 依赖派生 PDF 页数与顺序，存在插页/删页风险 | 天然 | 天然（artifact 以 `(source_sha256, pdf_page)` 寻址） |
| 只 OCR 选中页 | 需要 `--pages` 且行为未验证 | 是 | 是 |
| 矢量文字被栅格化 | force-ocr 会把整页变图 | 否 | 否（只对选中页做像素输入，不改源） |
| parser 输入确定性 | 派生 PDF 字节可能含时间戳等非确定内容 | 取决于 OCR 是否确定（unverified） | artifact 一次冻结后逐字节固定 |
| 可在改 corpus 前审阅 OCR | 需先生成整份 PDF | 难 | 是（artifact 是纯文本 JSON） |
| 可独立重试 OCR | 重做整份 | 与 ingest 耦合 | 是（单页重试） |
| 船端依赖 | 无（若只下发 corpus） | 若船端 ingest 则需 OCR runtime | 无 |
| parser 复杂度 | 最低 | 最高 | 中（多一个 artifact reader） |
| 可测试性 | 差（要造 PDF） | 中 | 好（artifact 可手写 fixture） |

A 的关键否决点：`pdftotext -layout` 对 OCR 隐藏文本层能否保持页眉列对齐（parser 的 `_LABEL_VALUE_GAP_RE` 依赖 ≥2 空格）**未验证**，
而 citation metadata 正依赖这条；C 把这个风险变成显式的 OCR 页眉解析路径，失败时可判 `uncertain` 而不是悄悄改变 section。

## 7. 岸端 / 船端边界（DF-09）

依据项目既有文档（实施方案 v0.12 §"岸端（Mac Studio，有网，算力充足） / 船端（离线，CPU，无人维护）"，
以及性能预算"岸端全量建语料 ≤ 8 h"）：

- **corpus ingest 与 OCR 只在岸端运行**；船端只消费冻结 corpus / index pack / 模型。
- **船端不安装任何 OCR runtime**，船端依赖保持 poppler 之外零增。
- `ocr_cache/` 与 `ingest/page_quality.jsonl` 属岸端产物，可随索引包分发副本供审计，但不参与船端启动校验。

这不是本轮新造的假设，而是引用既有设计约束。

## 8. determinism 与 cache（DF-10）

**必须先区分两个独立问题**：

| | 问题 | 归属 |
|---|---|---|
| **A. corpus-build determinism** | 同一 frozen input → parser/build → 同一 corpus？ | **Hybrid C 的 architecture invariant**。成立条件是"parser 在 build 时不运行 OCR，只消费 frozen / immutable / digest-addressed artifact"，与 OCR 引擎本身是否 byte-deterministic **无关** |
| **B. OCR artifact regeneration reproducibility** | 同 source page + 同 raster + 同 engine/version + 同 params/langpack，重复执行 OCR 是否产出逐字节相同 artifact？ | **implementation precheck**，不是 Hybrid C 成立的硬前提，也不是新的 Phase A measurement round |

**不得写成**：Hybrid C 需要 OCR 是 byte-deterministic 才成立。

### 8.1 身份定义

**命名约定（canonical）**：持久化字段名唯一为 **`source_hash`**，语义 = immutable 源 PDF 的 SHA256
（与 `core/contracts.py` 的 `Chunk.source_hash` 同义，本轮不改 contracts）。
下面公式中的 `source_pdf_sha256` 只是该值在公式里的可读别名：

```
source_pdf_sha256 := page_quality.source_hash
```

`page_quality` schema 中**不得**同时存在 `source_hash` 与 `source_pdf_sha256` 两个独立字段。
OCR 派生 artifact 的 digest 名唯一为 **`ocr_artifact_sha256`**，与 `source_hash` 绝不混用。

| 身份 | 定义 |
|---|---|
| source identity | `source_hash` = 源 PDF SHA256（immutable） |
| cache identity（key） | `(source_pdf_sha256, pdf_page, rasterizer, rasterizer_version, raster_dpi, ocr_engine, ocr_engine_version, langpack_identity_digest, ocr_params_digest)`，其中第一项按上式等于 `source_hash` |
| accepted artifact identity | artifact 文件自身 `ocr_artifact_sha256` |
| parser input identity | native 文本（由源 PDF 决定）+ 被引用 accepted artifact 的 `ocr_artifact_sha256` 列表 |

### 8.2 determinism invariant（七条硬规则）

1. artifact 不存在：OCR execution step 可以创建 **candidate artifact**。
2. candidate artifact 未经过 acceptance：**parser 不得消费**。
3. **accepted artifact 是 immutable 的。**
4. 同 cache key 已存在 accepted artifact：**不得静默覆盖**。
5. 同 cache key 再次运行 OCR 得到不同字节：**不得自动替换**；记录一条 reproducibility event；
   新 artifact 必须有新 digest，并显式重新走 acceptance。
6. **parser / build 永远不得隐式运行 OCR。**
7. parser 输入 artifact digest mismatch → **FAIL_INGEST**。

这七条就是 OCR nondeterminism 与 corpus determinism 解耦的实际机制。

补充规则：
- cache miss 且 OCR runtime 不可用 → 显式失败（见 §9 case 1/7），不静默退回 native。
- detector / policy version 变化**不使 artifact 失效**（不影响 artifact 字节），但会记入 `page_quality.jsonl`，
  并可能改变哪些页被引用；这属于 corpus 变化，走 §16 invalidation。
- 工具 / 语言包 / dpi / 参数变化 → 新 cache key → 新 artifact；旧 artifact 保留，corpus 变化显式可见。
- 源 PDF 改 1 byte → 全部 key 变化，旧 artifact 不再被引用（保留供审计），需要重跑 OCR。
- artifact digest 记录在两处：artifact 文件内自述 + `page_quality.jsonl` 的 `ocr_artifact_sha256`（同名同义）。

### 8.3 IMPLEMENTATION PRECHECK 0（OCR repeatability characterization）

对固定的少量代表页，在固定 `source sha` / `pdf_page` / `raster DPI` / `OCR engine+version` / `language pack` / `params` 下
**至少执行 OCR 两次**，比较：raw OCR text、structured OCR artifact、`ocr_artifact_sha256`。

- 结果 byte-identical → 记录 `observed deterministic under tested configuration`（**不外推**到其他配置或版本）。
- 结果不一致 → **不阻塞 Hybrid C**；artifact 必须 first-write freeze，后续 build 只能消费已冻结 digest，
  **不得在 rebuild 时自动 regenerate**（即 §8.2 规则 4/5 生效）。

无论哪种结果，**corpus build determinism 必须用 frozen-artifact 双跑单独验证**（与 S5 双跑同一口径）。

结论：**OCR execution may be nondeterministic; accepted parser input is immutable and digest-addressed.**

## 9. failure semantics（DF-18）

| # | 情况 | 冻结动作 |
|---|---|---|
| 1 | detector 判 unusable 但 OCR runtime 不可用 | **FAIL_INGEST**（整批失败并报告），不得退回使用乱码 native |
| 2 | OCR 进程非零退出 | `ocr_body_status=failed` → 该页 **QUARANTINE**，审计记录，ingest 继续，批次结束时汇总非零退出码 |
| 3 | OCR 输出为空 | 同 2 |
| 4 | OCR 输出 degraded | **QUARANTINE + REQUIRE_REVIEW**，不进 corpus |
| 5 | OCR body usable 但 citation metadata `uncertain` | **QUARANTINE + REQUIRE_REVIEW**（Citation First：OCR 替换页若出处不可信，不入库） |
| 6 | artifact digest 不匹配 | **FAIL_INGEST**（provenance 被破坏，不可继续） |
| 7 | cache artifact 缺失且不允许现场 OCR | **FAIL_INGEST**，提示先跑 OCR 步骤 |
| 8 | 源 PDF hash 改变 | 旧 artifact 全部失效 → 按 7 处理；corpus 必须重建 |
| 9 | page count 不一致（pdfinfo vs 分页符 vs artifact 覆盖） | **FAIL_INGEST**（现有 parser 已有此检查，语义不变） |
| 10 | detector 无法分类（`uncertain`） | `KEEP_NATIVE` + `hold_for_review`（若 body usable）；`QUARANTINE + REQUIRE_REVIEW`（若 body 非 usable） |
| 11 | content policy uncertain | 审计标记 `hold_for_review`，内容仍按 gate 结果处理，不额外丢弃 |
| 12 | native body 短且页面视觉上也无内容 | `SKIP_NONCONTENT`，**但必须写审计记录**（当前 parser 的静默 `continue` 被此规则取代） |
| 13 | augmentation 候选但 Phase B 不支持 | `KEEP_NATIVE` + `completeness=not_assessed` + 审计标记，记 residual risk |

**硬性：任何不进入 corpus 的页面都必须在 `page_quality.jsonl` 留下一条状态记录。禁止 `except: continue`，禁止静默丢页。**

## 10. merge semantics（DF-13）

**禁止 `merged_text = native + "\n" + ocr`。** 三个 case 分别冻结：

**贯穿三个 case 的解耦原则：body channel 与 metadata channel 完全独立判定。**
既有 citation audit 已证明 `native body clean/usable ≠ native citation metadata correct`
（`title_line_fallback` 254 页、异常候选 96 页），因此**不得**把"这些页的 native header 通常干净"升级成 architecture invariant。

```
body 路径：      native body ─┐
                              ├─► OCR body quality gate ─► primary body candidate（单一 channel）
                 OCR body ────┘

metadata 路径：  native metadata candidate ─┐
                                             ├─► citation metadata gate ─► citation_metadata_status
                 OCR metadata candidate ────┘                              + metadata_source_channel
                                                                             (native / ocr / none)
```

### CASE R —— native body `unusable`（class 1）
1. `OCR_ATTEMPT` → OCR body gate。
2. 若 OCR body `usable`：OCR body 是**唯一** body candidate；native 乱码正文只留 audit，不进 corpus。
3. 不需要去重（只有一个 body channel）。
4. metadata：**native 与 OCR candidate 均可进入独立 citation gate，不预设来源。**
   实际上这些页的 native 页眉通常同样损坏，多半会由机械损坏判据自行淘汰——但这是**判定结果**，不是预设规则。
5. citation gate 非 `explicit_supported` → 该页 QUARANTINE（见 §11）。
6. chunking 在 body 选定之后进行，与现有分块规则一致。
7. provenance：`body_source_channel = ocr`；`metadata_source_channel` 由 gate 结果决定；记 `ocr_artifact_sha256`。

### CASE S —— native body `insufficient`（class 2）
1. `OCR_ATTEMPT` → OCR body gate。
2. 若 OCR body `usable`：OCR body 是 **primary body candidate**；
   native 的残余正文（< `CHUNK_MIN_CHARS`，多为页眉页脚残留）**不与 OCR 文本拼接**，丢弃并记审计。
3. metadata：**native 与 OCR candidate 均进入独立 citation gate，不预设来源。**
4. **允许 `body_source_channel != metadata_source_channel`**（例如 body=ocr、metadata=native），
   前提是 page-level provenance 完整记录两个 candidate 与最终 channel。
5. 两个 candidate 冲突 → `uncertain`（§2.3.1），OCR 路径页因此进 quarantine / review。
6. provenance：`body_source_channel = ocr`，`metadata_source_channel ∈ {native, ocr, none}`。

### CASE A —— native body usable 但缺视觉知识（class 3）
**Phase B 不执行。** 冻结接口：未来 augmentation 以追加 `TextBlock(source_channel="ocr_augment", …)` 实现，
并且必须在那一轮单独设计去重（例如 block 级归一化文本比对）与 chunk 边界影响，
**不得以字符串拼接落地**。当前 corpus 行为不变。

**跨 case 不变量**：同一页最终 body 只能来自一个 channel（Phase B 内），
因此"同一句出现两次"在结构上不可能；未来引入第二 channel 时，去重是那一轮的必答项。

## 11. citation metadata gate 的动作（DF-12）

| 状态 | 动作 |
|---|---|
| `explicit_supported` | 正常入库 |
| `uncertain` | **既有 native 页**（body usable、未走 OCR 路径）→ 维持当前 baseline 行为**入库 + 审计标记**（本轮不借 OCR 项目顺手重写整个 legacy corpus，corpus 已有 254 页 fallback 页不动）；**OCR-derived / OCR-recovered 页**（CASE R/S）→ **QUARANTINE + REQUIRE_REVIEW** |
| `failed` | **QUARANTINE**（不入 corpus），审计记录 |

理由：新增的 OCR 内容不能以"正文恢复成功"为由绕过 citation safety gate；
而既有 native 页采用"不扩大破坏"策略（这些页当前已在 corpus 中，且 gold audit 38/38 semantic location 一致）。
这一不对称是有意的，并在 `page_quality.jsonl` 中逐页写明。

**后果（已知且接受）**：TACM p.38–103 中 body `unusable` 的页，其现有 50 个乱码 chunk（37 个有明显乱码 section）
将在 Phase B 重建后不再以现有形态存在——它们要么被 OCR 替换并通过双门，要么进入 quarantine。
这是 corpus 变化的主要来源之一。

运行时显示策略（M2 renderer 是否隐藏 `uncertain` 的 §section）**不在 Phase B 范围**，
接口已留：`page_quality.jsonl` 可按 `(doc_id, pdf_page)` join，M2 设计时可消费。

## 12. page audit artifact 与 Chunk contract（DF-14 / DF-15 / DF-16）

**冻结：方案 2 —— Chunk schema 不变；新增 `ingest/page_quality.jsonl`（每页一条）。**

**最小设计必须保存 candidate-level provenance**（不只是最终结论），按四组组织：

| 组 | 字段 | 谁消费 | 理由 |
|---|---|---|---|
| identity | `doc_id`、`source_filename`、`source_hash`（= 源 PDF sha256）、`pdf_page` | 全部 | join key + provenance |
| native | `native_body_status`、`native_detector_reason`、`native_metadata_candidate`、`native_metadata_source_kind`（explicit_label / title_line_fallback / inherited / none） | audit / 回归 | 不可由其他字段重建；candidate 必须独立于最终结论保存 |
| visual diagnostics | `visual_signal_summary`、`active_row_diagnostic`（若已计算） | audit / M5 | **diagnostic only**，不参与任何动作（§4） |
| OCR | `ocr_attempted`、`ocr_artifact_sha256`、`ocr_cache_key`（或等价身份串）、`ocr_engine`、`ocr_engine_version`、`ocr_params_digest`、`langpack_identity_digest`、`rasterizer`+`rasterizer_version`+`raster_dpi`、`ocr_body_status`、`ocr_metadata_candidate`、`ocr_metadata_source_kind`、`ocr_engine_confidence_stats`（仅统计量，不参与判定） | 重建 / 审计 | 构成 cache identity，必须可追；两个 metadata candidate 必须都留痕 |
| resolved | `body_source_channel`（native / ocr / none）、`metadata_source_channel`（native / ocr / none）、`citation_metadata_status`、`metadata_conflict`、`metadata_reason_code`、`page_content_completeness_status`、`content_policy_status`、`remediation_action`、`chunk_ids` | audit / 未来 M2 renderer | 结论与动作留痕；`chunk_ids = []` 表示未入库 |

**这些字段一律不自动升级进 Chunk；Chunk schema 继续保持不变。**

**不进 Chunk 的判断依据**：M1 retrieval 不需要（检索只用 text + 向量）；
M2 renderer 当前按 `Citation.display()` 渲染，不读质量字段；M2 scorer 按 gold 判分，不读；
UI 若未来要提示"本页经 OCR"，届时再按"跨组件语义确有需要"升级——DECISIONS 已有同向决定
（[L3] OCR 审计信息优先留在 page-level audit，不自动升级 Chunk contract）。

**`source_hash` 语义（DF-16）：保持现状 = 源 PDF 的 sha256（选项 A）。**
派生 artifact 的 digest 叫 `ocr_artifact_sha256`，**只存在于审计**。
一个字段不承担两个 digest；Chunk 不新增字段。

## 13. page identity 不变量（DF-17）

1. **不产生派生 PDF**，因此不存在插页 / 删页 / 重排风险。
2. artifact 命名与寻址 = `ocr_cache/<source_hash>/p<pdf_page>.json`，`pdf_page` 1-based（约定第 4 条）。
3. artifact 内自述 `(source_hash, pdf_page)`，parser 读入时**双向校验**，不一致 → FAIL_INGEST。
4. 光栅化仅作为 OCR 输入，**禁止 rotation / crop 改变页面语义**；若引擎需要旋转，必须把旋转记入 `ocr_params_digest` 并保持页号不变。
5. parser 继续保留现有的"pdfinfo 页数 == 分页符数"检查，并新增"被引用 artifact 的页号 ⊆ 源 PDF 页号集合"检查。
6. **OCR 成功 + page identity 错 = 严重静默失败**，因此以上全部为硬门（FAIL_INGEST），不降级。

## 14. TACM 相关的三个冻结（DF-19 / DF-20 / DF-21）

- **p.55（DF-19）：Option A。** 历史 `confirmed_bad` 标签与历史结果一律不改；
  production 侧按确定性规则（`font_count == 0` 且 `extracted_chars == 0` 且 40/100/150 dpi nonwhite = 0）判为 blank/noncontent → `SKIP_NONCONTENT` + 审计。
  benchmark denominator 保持历史形态，附注说明该页为空白页。**禁止为改善 recall 数字而移动历史标签。**
- **form/template（DF-20）：不设 form 专用规则。** production 无可确定性测试的 form 判据；
  OCR 照常执行，admission 由 body gate + citation gate 决定。
  残余风险：脚手架文本可能进入索引；缓解手段是审计可回溯 + 未来可基于人工 review 形成排除清单（M5）。
- **p.38–103（DF-21）：T1 的 policy consequence。** 不写任何 TACM 专用 if/else；
  它们因 `native_body_status = unusable` 而被通用 policy 选中 OCR_ATTEMPT，
  之后与所有页面同样经双门；通不过的页进 quarantine。预期结果：部分页恢复、部分页被隔离，二者都有审计记录。

## 15. S6 顺序（DF-22）：**IMPLEMENTATION BEFORE S6**

会改变 corpus 的已冻结设计（逐条）：

1. CASE R：class-1 页的 body 被 OCR 文本替换 → text 变、chunk 数变。
2. CASE S：88 页中通过双门者从"无 chunk"变为"有 chunk" → chunk 数增、`Chunk.id` ordinal 集合变。
3. citation gate `failed` → quarantine：现有 TACM 乱码页的 50 个 chunk 不再以现形态存在 → chunk 数减。
4. §9 case 12：`SKIP_NONCONTENT` 取代静默 `continue`，corpus 内容本身不变，但审计产物新增。

因此**现在构建 GoldChunkMap 必然作废**（`GoldChunkMap` 以 `corpus_sha256` 为 identity，见 contracts）。
R2 是窄义的（只说"仅因第三类 failure 不必改 corpus"），本轮的 class 1/2 + citation gate 决定超出了 R2 的范围——
按 DECISIONS 的既定边界，这属于"Phase B 基于 citation safety 决定先改 parser"的情形，应在实现轮追加新的决策条目，不回改 R2 原条。

**冻结执行顺序**：Phase B implementation → 重建 corpus（新 sha + determinism 双跑验证） → S6 GoldChunkMap → M1/M2。

## 16. invalidation graph（DF-23）

```
raw/*.pdf ──► ocr_cache/<sha>/p<N>.json ──► parser ──► corpus/chunks.jsonl ──► corpus sha256
                                                              │
        ┌─────────────────────────────────────────────────────┼───────────────┐
        ▼                         ▼                           ▼               ▼
  GoldChunkMap            IndexManifest              retrieval index      M1 / M2 artifacts
```

**必须重做**：`corpus/chunks.jsonl`、corpus sha、chunk count / 长度分布、受影响页的 `Chunk.id` ordinal、
`GoldChunkMap`（尚未生成，因此只是"不要提前生成"）、未来 `IndexManifest`、任何以 corpus sha 为键的产物。

**必须复核（因真实 chunk 分布变化）**：`experiments/gate2_raw/_s4a9c_final_real_chunks.log`、
`_s4a9c_overbudget_attribution.log`、`_s4a9c_none_observed_deepdive.log`（三者都记录了 `corpus sha=8c6bee0a… chunks=3383`），
以及由其校准的预算参数结论与 `core/contracts.py` 中旧的 chunk-distribution 注释（注释更新属实现轮的文档动作，不是 contract 语义变更）。

**不受影响**：GATE-1 / GATE-2 模型评测、license evidence、CPU/GPU control、language smoke、TTFT / prompt-overhead 系列
（`_s4a9a_*`、`_s4a9b_*`、`_s4a9c_chars_per_token`：grep 证实不引用 corpus），以及 `eval/testset_v5_3.jsonl` 本身（题目与 gold 不变）。

## 17. contract 变更判定（DF-24）

**CONTRACT_CHANGE_REQUIRED_BEFORE_IMPLEMENTATION = NO。**

- A. Phase B 全部审计需求由 `ingest/page_quality.jsonl` 承载，不需要 Chunk 新字段。
- B. 无 runtime 组件（retriever / packer / generator / scorer）需要读取质量状态：M1/M2 当前设计不消费。
- C. `source_hash` 现有语义（源 PDF sha）足够；派生 digest 留审计。
- D. `Citation.section` 的 canonicalization（`Chapter 15` vs `15`）属 scorer/renderer 设计，
  DECISIONS 已判为 representation-only，不在 Phase B 触发 contract 变更。
- E. page-quality status 不进 contract。

审计性如何在不改 contract 下保持：`page_quality.jsonl` 以 `(doc_id, pdf_page)` 与 corpus join，
`chunk_ids` 字段提供反向关联；corpus sha + artifact sha + 脚本 commit 构成完整生成链。

**contract-change trigger（硬规则）**：若 implementation 过程中发现某个 runtime component
**必须**依据 `body_source_channel` / `metadata_source_channel` / `citation_metadata_status` 等 page-level 字段改变行为，
那是一个新的 contract-change trigger：**STOP → 单独的 contract decision → 不得顺手改 Chunk**。

### 17.1 状态可测试性（设计级要求）

对每个冻结状态只回答一个问题：**是否存在确定性的 observable / test 能把它与相邻状态区分？**

| 轴 | 区分手段（确定性） | 结论 |
|---|---|---|
| `native_body_status` | `parser_body_chars` 与 `CHUNK_MIN_CHARS` 比较；`alpha_token_ratio`；控制字符计数；文档语言作用域 | 四状态均可区分 |
| `page_content_completeness_status` | 由 population 与冻结 active-row 规则确定（`not_assessed` 由 body usable 直接确定） | 三状态均可区分；无法区分的"真完整"已被删除（不设 `complete`） |
| `ocr_body_status` | artifact 存在性 + digest 校验 + 进程退出码 + 复用 `CHUNK_MIN_CHARS` 与 V1 判据 | 四状态均可区分；不再细分 `uncertain` |
| `citation_metadata_status` | 五条 `explicit_supported` 条件逐条可判；冲突可判；失败证据可判 | 三状态均可区分；其余一律落入 `uncertain` |
| `content_policy_status` | `admit` / `reject_noncontent` 由既有 `CHUNK_MIN_CHARS` 规则确定；`hold_for_review` 由 gate 结果确定 | 三状态均可区分；不引入不可测的"业务价值"判定 |

完整测试矩阵留给下一轮 implementation prompt，本文件不展开。

## 18. 最终状态机

```
[source page]
   │ native extraction（pdftotext -layout，源 PDF 只读）
   ▼
native_body_status
   ├── usable ──────────────► completeness = not_assessed
   │                              │
   │                              ▼  citation gate（candidate: native）
   │                          explicit_supported → KEEP_NATIVE → chunking → 入库
   │                          uncertain          → KEEP_NATIVE + hold_for_review → 入库 + 审计
   │                          failed             → QUARANTINE
   │
   ├── unusable ────────────► remediation = OCR_ATTEMPT (CASE R)
   │        │ artifact 缺失/runtime 不可用 → FAIL_INGEST
   │        │ digest 不匹配 → FAIL_INGEST
   │        ▼ ocr_body_status
   │      failed / degraded → QUARANTINE (+REQUIRE_REVIEW if degraded)
   │      usable ──► body = OCR（唯一 channel）
   │                citation gate（candidates: native ∪ ocr，不预设来源；冲突 → uncertain）
   │                   explicit_supported → OCR_REPLACE → chunking → 入库
   │                                        （记 metadata_source_channel）
   │                   uncertain / failed  → QUARANTINE + REQUIRE_REVIEW
   │
   ├── insufficient ───────► completeness：active-row 仅写审计（不门控）
   │        │                remediation = OCR_ATTEMPT (CASE S)（无条件，不由视觉信号决定）
   │        ▼ ocr_body_status
   │      failed/degraded ─► 去页眉页脚后 < CHUNK_MIN_CHARS ? SKIP_NONCONTENT : QUARANTINE
   │      usable ──► body = OCR（primary channel）
   │                citation gate（candidates: native ∪ ocr，不预设来源；冲突 → uncertain）
   │                   explicit_supported → OCR_PRIMARY → chunking → 入库
   │                                        （body_source_channel 可 != metadata_source_channel）
   │                   uncertain / failed  → QUARANTINE + REQUIRE_REVIEW
   │
   └── uncertain ──────────► body usable? KEEP_NATIVE + hold_for_review
                             : QUARANTINE + REQUIRE_REVIEW

所有分支终点（入库 / QUARANTINE / SKIP_NONCONTENT / FAIL_INGEST）
必须写 ingest/page_quality.jsonl 一条记录。
```

每个 transition 的 input state / decision / output action 均在 §2、§9、§10、§11 中有确定性定义。

## 19. DESIGN_FREEZE 表

| ID | Design question | Frozen decision | Evidence | Residual risk | Implementation consequence |
|---|---|---|---|---|---|
| DF-01 | native_body states | `usable / unusable / insufficient / uncertain`，判定序 insufficient→unusable→uncertain→usable | `_criterion_calibration.log`；parser `CHUNK_MIN_CHARS` 既有规则 | unusable 判据仅来自单文档区间 | detector 模块 + 4 状态枚举 |
| DF-02 | completeness states | `presumed_complete / visual_content_suspected / not_assessed`；无 `complete` | A.2b 175 页人工比对 | prevalence 未估计 | 仅写审计字段 |
| DF-03 | citation metadata states | **`explicit_supported / uncertain / failed`**（`verified_structural` 已作废）；`explicit_supported` 需五条同时成立，且只断言 evidence-supported extraction，不断言语义验证 | `_citation_section_audit`（explicit 993 页 / fallback 254 页 / 异常 96 页）；TACM p.100 `"9"` | 语义正确性仍未被证明 | 独立 gate 模块 + candidate 级 provenance |
| DF-04 | V1 role | scoped hard detector，仅 Latin-script 作用域，只产 `unusable` | TACM 65/66，unreviewed trigger 0 | 跨语言未验证 | 代码内显式 lang 作用域守卫 |
| DF-05 | V2 / active-row role | **视觉统计正式退出 production OCR gating**，一律 diagnostic/audit only；production rule = `insufficient → OCR_ATTEMPT`；阈值只影响审计标记 | `STRUCTURE_CASE_1`；NEG N=7；88 页规模 + 岸端一次性成本 | detector 未经 production 验证；OCR 页数略多 | 审计字段 + 复算函数，policy 层不读视觉信号 |
| DF-06 | class-3 scope | **Scope C3**：建 state + 接口，不自动 OCR | 16 confirmed examples；gold 10/10 quote 仍在 corpus | 图内知识当前不可检索 | `TextBlock` 列表接口 |
| DF-07 | OCR worthiness separation | `OCR_ATTEMPT` 与 `OCR_CONTENT_ADMIT` 是两个动作；无自动业务价值判定 | TACM form 抽样价值分布 | 脚手架文本可能入库 | policy 两段式 |
| DF-08 | OCR architecture | **方案 C**：岸端独立 OCR 步骤 + digest 寻址 page artifact；parser 只读 artifact | A 的 `-layout` 行为未验证；B 依赖未验证的 OCR 确定性 | 引擎选型仍待实现轮 | 新增 OCR adapter + artifact reader |
| DF-09 | shore/vessel boundary | OCR 与 ingest 仅岸端；船端零新增依赖 | 实施方案 v0.12 岸/船分工与 ≤8h 预算 | 无 | 船端不受影响 |
| DF-10 | determinism / cache | 区分 corpus-build determinism（architecture invariant）与 OCR regeneration reproducibility（implementation precheck 0）；cache key 九元组；candidate→accepted 两阶段；accepted immutable、不得静默覆盖/自动替换；parser 绝不隐式跑 OCR | OCR regeneration reproducibility unverified；Hybrid C 不以其为前提 | 引擎升级使 key 全变 | cache 目录 + acceptance 流程 + digest 校验 |
| DF-11 | OCR body gate | `not_attempted / usable / degraded / failed`；复用 `CHUNK_MIN_CHARS` 与 V1 判据，不新增阈值；引擎置信度只入审计 | 无 OCR 数据 → 不得凭空定阈值 | 首轮 OCR 后可能需校准（须预注册） | gate 模块 |
| DF-12 | citation gate action | 既有 native 页 uncertain → 维持 baseline 入库 + 审计；OCR-derived/recovered 页 uncertain/failed → quarantine；candidate 冲突 → uncertain（禁止自动择一/继承/投票） | gold 38/38 semantic 一致；Citation First | 既有 fallback 页风险保留 | 不对称策略 + 冲突语义写入代码与审计 |
| DF-13 | merge semantics | 禁止拼接；body channel 与 metadata channel **完全解耦**，均不预设来源；CASE R/S 的 body 单一 channel，metadata 由独立 gate 决定；CASE A 不实现但留接口 | 既有 audit 证明 native body clean ≠ native metadata correct | 未来 augment 需单独设计去重 | merge 函数 + candidate 级 provenance |
| DF-14 | page audit artifact | `ingest/page_quality.jsonl`，四组字段（identity / native / visual diagnostics / OCR / resolved），保存 **candidate-level provenance**；任何不入库页必须有记录 | DECISIONS [L3] 审计优先留在 page level | 文件随语料增长 | 新增 writer |
| DF-15 | Chunk contract strategy | **方案 2**：Chunk 不变 | M1/M2/UI 当前不消费质量字段 | 未来 UI 若需提示需另行升级 | 无 contract 改动 |
| DF-16 | source_hash semantics | canonical persisted field = `source_hash` = immutable 源 PDF SHA256；派生 digest 唯一名 `ocr_artifact_sha256`，只入审计；二者绝不混用 | contracts 现有语义 | 无 | 无 contract 改动 |
| DF-17 | page identity | 不产生派生 PDF；artifact 以 `(source_sha, pdf_page)` 寻址并双向校验；旋转/裁剪不得改页语义 | Citation First | 无 | 硬门检查 |
| DF-18 | failure semantics | §9 的 13 条；禁止静默丢页 | 当前 parser 静默 `continue` 已被证明会丢图像页 | quarantine 页需人工复核产能 | 显式状态 + 汇总退出码 |
| DF-19 | TACM p.55 | Option A：历史标签不动，production 判 blank/noncontent | 40/100/150 dpi 全白 | 无 | 通用空白页规则 |
| DF-20 | form/template policy | 无 form 专用规则，按通用双门处理 | A.2b form 价值分布 | 脚手架文本入库 | 无额外代码 |
| DF-21 | TACM p.38–103 | 通用 policy 的后果（unusable → OCR → 双门），无文档专用规则 | CLAUDE.md 铁律 + Phase A 证据 | 部分页可能全部进 quarantine | 无专用分支 |
| DF-22 | S6 ordering | **IMPLEMENTATION BEFORE S6** | 四条会改 corpus 的设计（§15） | 实现延后 S6 | 先重建 corpus 再 S6 |
| DF-23 | invalidation policy | §16 的依赖图；按依赖判定，不写"全部重跑" | grep 证实哪些 log 引用 corpus | 无 | 实现轮附 invalidation 清单 |
| DF-24 | contract change | **NO** | §17 A–E | 未来 UI 需求可能推翻 | 实现轮禁止改 contracts |

无 blocker TBD。

## 20. IMPLEMENTATION_HANDOFF

**允许修改 / 新建**
- `components/parsers/kaiva_pdf.py`（引入 artifact reader、状态与 merge 语义、审计输出）
- `ingest/build_corpus.py`
- 新增：OCR 执行步骤（独立脚本）、OCR adapter、page audit writer、detector / gate / policy 模块
- 新增测试
- 重建 `corpus/chunks.jsonl`（实现轮的一部分，必须产生新 corpus sha 并做双跑确定性验证）
- 新增 DECISIONS 条目（记录 R2 边界被 Phase B 设计超越）

**未经单独 contract 变更不得修改**
- `core/contracts.py`
- `eval/testset_v5_3.jsonl`
- packing / prompt budget / retrieval / renderer / scorer
- 既有 Phase A/A.1/A.2/A.2b 产物与 review 标签
- `raw/` 下任何文件

**输入 artifacts**：源 PDF 9 份；本 Design Freeze；A.2 / A.2b 冻结标签与预注册；`_page_signals.csv`；`_citation_section_audit.csv`。

**必须产出的 artifacts**：`ocr_cache/`（digest 寻址的 accepted artifacts）；**PRECHECK 0 的 OCR repeatability characterization 记录**
（含 `observed deterministic under tested configuration` 或 reproducibility event）；`ingest/page_quality.jsonl`；
新 `corpus/chunks.jsonl` + 新 sha；双跑确定性证据；quarantine 清单；invalidation 清单。

**执行顺序**：PRECHECK 0 → OCR 执行步骤（产出 candidate → acceptance → frozen artifacts）→ parser/build 重建 corpus → 双跑验证。

**acceptance invariants**
1. 同输入（含 frozen artifacts）两次 build，`chunks.jsonl` 逐字节一致。
2. 1335 页中每页在 `page_quality.jsonl` 恰有一条记录。
3. 无静默丢页：未入库页必有状态与 reason code。
4. 任何 OCR 页的 `pdf_page` 与源 PDF 页号一一对应（硬门）。
5. Chunk schema 未变；`source_hash` 仍为源 PDF sha。
6. 代码中不存在文档名 / 页码硬编码。
7. OCR-derived / OCR-recovered 页若 citation gate 非 `explicit_supported`，则不在 corpus 中。
8. parser/build 路径中不存在任何隐式 OCR 调用（§8.2 规则 6）。
9. 每个 OCR 页的 `native_metadata_candidate` 与 `ocr_metadata_candidate` 均已留痕，冲突页 `metadata_conflict = true`。

**corpus rebuild 属于 implementation 的一部分；S6 在其之后。**

---

## 21. 残余风险登记（不阻塞实现）

1. V2 / active-row 未经 production 验证（NEG N=7，标注者为 Claude visual review）——已降级为审计信号。
2. 第三类 failure prevalence 未估计；图内知识当前不可检索（C3 决定）。
3. OCR artifact regeneration reproducibility 未验证——由 candidate→accepted 冻结机制隔离；implementation precheck 0 做 characterization，不阻塞架构。
4. OCR 后的页眉解析能否产出 `explicit_supported` 未知——失败路径为 quarantine，不会静默污染出处。
5. 既有 `title_line_fallback` 页（254 页）的 section 语义正确性未逐页证明——本轮不扩大破坏，记录在审计中。
6. quarantine 页的人工复核产能未评估。
7. 结论作用域仅限当前 9 份 PDF。
