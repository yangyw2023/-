# ship-rag

**一句话定位：离线的、带出处的文档导航器**——生成的自然语言只是所依据片段的摘要。
没有出处就不输出答案；检索不到就拒答；生成层挂掉降级为纯检索。

部署环境：远洋船舶，完全离线、CPU 推理、船上无 IT 支持。

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
python3 ingest/build_corpus.py "raw/KAIVA - Manuals" corpus
```

> ⚠️ `ingest/build_corpus.py` **尚未进入本仓库**（当前仅有脚手架）。
> 上面是既定的调用形式，写在这里是为了让重建方式有唯一说法，不是说它现在能跑。

## gold_chunk_ids 回填

**用途**：`scripts/resolve_gold_chunks.py` 把评测集里每条 citation 解析到具体的
corpus chunk id 上，让检索层的 Recall@k 变得可测量——没有 `gold_chunk_ids`，
就无法区分"检索没找到"和"模型没用好"。一次性数据回填工具，仅用标准库。

**输入 / 输出**：

```bash
python3 scripts/resolve_gold_chunks.py \
  --chunks      <corpus 的 chunks.jsonl> \
  --testset     eval/testset_v5_2.jsonl \
  --out-testset <解析后的评测集：独立文件名，见下> \
  --out-report  <逐 citation 的 CSV 审计报告>
```

两个输入文件都只读，工具不回写输入。匹配按 L1 → L2 → L3 → L4 顺序进行，
首个命中即止并记下 `match_level`；L4 是兜底不是匹配，标 `needs_review`。

**FAIL 不得静默接受。** FAIL 的含义是该 `(doc_id, pdf_page)` 下根本没有 chunk，
即引文写错了、页码写错了，或解析器丢了那一页。它是信号不是噪声：必须逐条查到底，
不允许因为"只有几条"就放过。

**第一轮不要覆盖 `eval/testset_v5_2.jsonl`**：`--out-testset` 用独立文件名，
核验通过之后再决定哪个文件是 canonical。`gold_chunk_ids` 究竟回写进评测集本身、
还是外置为派生产物，是一个待拍板的契约变更（见 `DECISIONS.md` 2026-09-07 补充 5）；
仪式走完之前，本文件不写死输出路径约定。

## 纪律

**契约变更要走仪式，见 DECISIONS.md。**
