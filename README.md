# ship-rag

**一句话定位：离线的、带出处的文档导航器**——生成的自然语言只是所依据片段的摘要。
没有出处就不输出答案；检索不到就拒答；生成层挂掉降级为纯检索。

部署环境：远洋船舶，完全离线、CPU 推理、船上无 IT 支持。

> README 只做导航（orientation only），**不是 normative source**。与下列文件冲突时以它们为准。

## Source of truth

| 文件 | 角色 |
|---|---|
| `DECISIONS.md` | append-only 的决策 / 证据历史 |
| `core/contracts.py` | 可执行的语义 / 数据契约（当前 `CONTRACTS_VERSION = "0.2.0"`） |
| `船载离线文档问答系统_实施方案_v0.13.md` | 设计 / rationale |
| `执行手册_v4.md` | 操作顺序（operational sequence） |
| `README.md` | 仅导航 |

`experiments/` 下的原始 log / `_runtime.txt` 是 point-in-time evidence，保持原样不回改；
之后的解读与收窄记录在 `DECISIONS.md`。

## 当前状态

- S5c：**CLOSED**；canonical corpus 已冻结（见下）
- S4a.9c-final measurement：已完成
- S6（GoldChunkMap）：**未完成**，当前阻塞于 resolver 与契约对齐 / semantic closure
- S8：未开始

canonical corpus（`corpus/chunks.jsonl`，不进 Git，按下文重建后用这两个值核验）:

    sha256 = c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb
    chunks = 3409   (wc -l)

## 目录

| 路径 | 说明 | 进 Git |
|---|---|---|
| `core/contracts.py` | 唯一可信来源：数据结构 + 阈值 + 接口 + 语义约定 | ✅ |
| `core/pipeline.py` | 组装层：读配置 → 实例化组件 → 串成流程 | ✅ |
| `core/registry.py` | 名字 → 实现类的注册表，让"换组件"变成改配置 | ✅ |
| `components/` | 可替换组件；各子包之间互不 import，只能 import `core.contracts` | ✅ |
| `ingest/` | 岸端：把原始文档变成索引包 | ✅ |
| `serve/` | 船端：查询服务 + 前端 | ✅ |
| `eval/testset_*.jsonl` | 评测集。人工产物、不可再生 | ✅ |
| `eval/results.csv` | 实验结果，**只追加，永不删行** | ✅ |
| `experiments/` | 预注册模板、实验配置、模型台账 | ✅ |
| `scripts/` | 一次性工具脚本 | ✅ |
| `raw/` | 原始 PDF。只读，必须另行备份 | ❌ |
| `corpus/` | 解析产物（chunks 等），可重新生成 | ❌ |
| `index/` | 向量库 + BM25 索引，可重新生成 | ❌ |
| `models/` | LoRA adapter、GGUF 转换产物 | ❌ |

进 Git 的判断标准：**能一条命令重新生成的 → 不进 Git，但生成脚本必须进。**
唯一例外是 `eval/testset_*.jsonl`——它是人的判断，不可再生。

## 语料重建

```bash
python3 ingest/build_corpus.py "raw/KAIVA - Manuals" corpus --cache-dir ocr_cache
```

`ingest/build_corpus.py` 已在仓库中（完整参数见其 docstring）。它不执行 OCR，只消费
`ocr_cache/accepted/` 下已冻结的 OCR artifact；产出 `chunks.jsonl`、`page_quality.jsonl`、
`ingest_report.csv`。重建后用上面的 sha256 / 行数核验是否得到 canonical corpus。

## GoldChunkMap（当前契约架构）

以 `core/contracts.py`（`EvalItem` / `GoldChunkMap`）为准，要点：

- `EvalItem` **不含** `gold_chunk_ids`；评测集里的 citations 是人工事实，不可再生。
- citations 在某套语料 + 分块配置上的投影是独立的 `GoldChunkMap`：派生产物，可再生，不进评测集。
- `mapping` 只包含 `expected=="answer"` 的题。
- 逐 citation 的 match level 的权威记录是 `.report.csv`；`GoldChunkMap` 不含 match levels。

**S6 未完成，GoldChunkMap 尚未生成。**
`scripts/resolve_gold_chunks.py` currently requires alignment with contracts v0.2.0
before formal S6 GoldChunkMap generation —— 现有脚本仍按旧方式把 `gold_chunk_ids`
回填进评测集（`--out-testset`），不是上述架构。

## 纪律

**契约变更要走仪式，见 DECISIONS.md。**
