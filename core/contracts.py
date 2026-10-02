"""船载离线文档问答系统 —— 唯一可信来源 (Single Source of Truth)。

================================================================================
本文件的地位
================================================================================
所有组件只 import 本文件；组件之间【互不 import】。
改动本文件 = 契约变更，必须走完整仪式（实施方案 §20.3）：
  1. 单独一次工作会话，不与实现组件混在一起
  2. 单独一个 commit，message 以 `contract:` 开头
  3. 同步在 DECISIONS.md 追加一条，按四类标注级别:
       L1  架构决策    强制字段 falsified_if
       L2  实验参数    强制字段 owner_experiment
       L3  实现细节    无强制字段
       [M] 方法约束    强制字段 why_not_falsifiable
           —— 统计学/实验设计的正确性要求，不是关于本系统的经验主张，
              不可能被本项目的实验推翻（如"McNemar 只看不一致对"）。
              单列是为了不让 L1 出现 "falsified_if: 无" —— 那会让
              "L1 必须可证伪"这道闸失效，L1 就开始变成教条。
  4. 若改动影响已生成的语料或索引 → 必须重建，并在 DECISIONS 注明重建时间

  # [L2] 一次性实测,非实验参数 —— 系统提示词是固定文本,token 数是量出来的不是跑出来的。

本文件的【契约语义只能由人裁决】（Arya）。AI 不得自行决定是否改契约、改什么语义、
选哪个契约选项，也不得根据实验结果顺手修改可执行契约。
在专门的契约轮次中，若人已逐项明确给出 语义裁决 / 允许的 diff 范围 / 必须的不变量 /
验收测试 / commit 边界，AI 可以【机械落地】这些已裁决内容；发现新的语义缺口必须停下，交回人工裁决。
此类修改一律走上面的仪式：独立的 `contract:` commit（必须真实包含本文件），commit 前由人审核完整 diff。
AI 可以按本文件实现组件。

================================================================================
九条全链路语义约定 —— 每次让 AI 生成代码时必须整段贴入
================================================================================
 1. 分数一律 0.0..1.0，越大越相关。BM25 原始分与向量距离必须在组件内部
    归一化后再出口。禁止某处用距离（越小越好）。
    ⚠️ 归一化必须是【查询无关】的：一个固定的单调映射，只依赖该条 hit 的原始分，
    不依赖本次返回的其他结果。禁止 per-query min-max / softmax ——
    那会让 top-1 恒为 1.0（或最低项恒为 0.0），使 MIN_RELEVANCE 永远不触发
    （或永远触发），而这个失败【不报错，只是拒答率变成 0% 或 100%】。
 2. 空列表 [] 的唯一含义是"确实没检索到"。出错一律抛异常，
    禁止 `except: return []` —— 否则"没找到"和"崩了"变成同一个状态，无法归因。
 3. 拒答不是异常。Answer(refused=True) 是合法的正常返回。
 4. pdf_page 从 1 开始（与 PDF 阅读器一致）。AI 极易生成成 0-based，
    会导致所有出处差一页。
 5. 所有 ID 一律 str，不用 int，避免序列化时类型漂移。
 6. 时间一律 float 秒，不混 ms。
 7. 语言代码一律 ISO 639-1 小写（en / zh / tl / hi）。
 8. 阈值只有本文件这一个定义处。组件内禁止出现魔法数字。
 9. 岸端与船端共用同一份本文件，这是一致性的物理保证。

================================================================================
引用契约 —— 由真实语料结构决定，不可简化
================================================================================
KAIVA 手册的页脚按【章节】独立编号（"Page 1 of 7" / "Page 1 of 3"），
同一份手册里 "Page 1" 会出现很多次。因此：

    单独的印刷页码不能唯一定位一段文字。

引用必须是三元组 (doc_id, section, pdf_page)。
printed_page 仅供船员核对，绝不用于定位。

此结论来自 2026-08-31 语料勘察，非推测。
[L1] falsified_if: 找到能唯一定位的更简形式

================================================================================
人工产物 vs 派生产物 —— 决定什么进评测集
================================================================================
    citations       人的判断，逐条回原始 PDF 核对过，不可再生   → 进评测集，进 Git
    gold_chunk_ids  citations 在【某一套语料 + 分块配置】上的投影，
                    一条命令可再生                            → 【不进评测集】

后果如果混在一起：M5 一做 chunk 大小消融，全部 gold_chunk_ids 作废且没有
再生路径（再生要靠脚本，而脚本读的是同一个文件）；完整 SMM 到货重建语料同理。

→ 见 GoldChunkMap。映射文件按 (评测集版本, 语料哈希, 语料构建器名) 命名，
  语料一变旧映射自动失效【且能看出来是哪一份失效了】。
[L1] falsified_if: 语料与分块配置在项目全周期内都不再变化
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import os
import re
from dataclasses import asdict, dataclass, field, fields
from fractions import Fraction
from typing import Callable, Literal, Mapping, Protocol, Sequence

# ==============================================================================
# 版本
# ==============================================================================

# 【整个可执行契约模块（本文件）的版本】（人工裁决 CONTRACT_VERSION_DECISION = SPLIT，DECISIONS 2026-10-01
# final protocol closure）。每个 `contract:` commit 都递增它（历史: 0.2.0 / 0.3.0 / 0.3.1 / 0.4.0 / 0.4.1 各对应一个
# contract commit）；任何影响 Chunk 结构或引用语义的改动当然也在其中。
# 用途: 索引包与运行时的一致性校验依据（见 IndexManifest；约定 9 岸船共用同一份本文件），以及 artifact 的 provenance。
# ⚠️ 它【不】决定派生 artifact 是否失效 —— 失效由 artifact 实际依赖的语义版本决定。
#    GoldChunkMap 的兼容判定用 GOLD_CHUNK_MAP_SEMANTICS_VERSION，不用本值；
#    只改检索语义的版本递增不得使 GoldChunkMap 失效。
CONTRACTS_VERSION = "0.4.1"

# 【GoldChunkMap 语义版本】citation → chunk 投影的兼容判定依据（validate_gold_chunk_map）。
# 拆分自 CONTRACTS_VERSION（0.4.0 起）；取值沿用拆分前最后一个契约版本，因此 0.3.1 生成的映射语义上即本版本。
# 必须递增的条件（GoldChunkMap 的实际依赖，任一改变即递增）:
#   - Chunk / Citation / EvalItem 中被解析器与校验器读取的字段语义；validate_eval_item；testset_version_from_path
#   - normalize_text / split_quote_fragments / is_sole_match_eligible / QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH
#   - MatchLevel 定义、FORMAL_MATCH_LEVELS、MATCH_LEVEL_REASON、GOLD_CHUNK_MAP_REPORT_COLUMNS
#   - GoldChunkMap 字段 / serialize_gold_chunk_map / filename() / report_filename()（含 CORPUS_SHA_PREFIX_CHARS）
#   - validate_gold_chunk_map 的接受条件
# （清单 = resolver 与校验器实际触达的本文件符号，2026-10-01 AST 扫描；其中不含任何检索 / 打包 / 生成侧符号。）
# 不随以下改动递增: 检索 / 打包 / 生成侧的契约（Hit、RetrievalResultRecord、retrieval_order_key、
#   bm25_* 、pack_context、数值预算常量）。构建身份由 builder 三项另行绑定，不归本版本。
# ⚠️ 递增依赖人按上述清单执行（没有 AST 守卫）。
GOLD_CHUNK_MAP_SEMANTICS_VERSION = "0.3.1"

# 拆分前（< 0.4.0）GoldChunkMap 带 contracts_version 字段、但没有 gold_chunk_map_semantics_version 字段的
# 契约版本【闭集】（取自 git 历史: a1973ef = 0.2.0、b866134 = 0.3.0、d30ed34 = 0.3.1；ae33bc4 = 0.2.0-draft
# 的 GoldChunkMap 无 contracts_version 字段）。拆分是一次性事件，本集合永不增长。
# legacy 规则见 GoldChunkMap docstring 与 validate_gold_chunk_map。
GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS: frozenset[str] = frozenset({"0.2.0", "0.3.0", "0.3.1"})


# ==============================================================================
# 阈值（一）已校准 —— 每个值都有实测来源
#
# 每个常量必须标注：
#   [级别]  L1=架构决策（几乎不改） / L2=实验参数（允许被实验推翻）
#   来源    实测数据或勘察结论，不接受"经验值""默认值"
#   owner   L2 参数必须写明哪个实验负责重新校准它
# ==============================================================================

# ---- 上下文预算 ----
# [L2] owner_experiment: M6（拿到船端硬件后按实测 prefill 重定）
# 来源: 2026-08-17 llama-bench 实测 (llama3.2:3b Q4_K_M, 8 线程)
#   512 tok  -> 117.5 t/s ->  4.4s TTFT
#   1024 tok -> 107.4 t/s ->  9.5s
#   2048 tok ->  92.3 t/s -> 22.2s
#   4096 tok ->  71.8 t/s -> 57.1s  ← 船端不可接受
# 注: 该实测 backend 显示 BLAS,MTL（Metal 未完全禁用），是【乐观上界】。
#
# 【当前基线】采用方案 C：MAX_PROMPT_TOKENS=1050 / TTFT_BUDGET_S=10.0。
# 两者均为 L2，后续由 owner experiment 根据实测重定；M1c 同时报约 1050 与
# 约 1500 两档 Recall，用于量化收紧 prompt 预算的代价。
#
# 双向核算（纪律五：能互相推导的两个数字必须显式核对一次）:
#   用上表在 1024→2048 之间线性插值:
#     rate(1500) = 107.4 + (476/1024)×(92.3-107.4) = 100.4 t/s
#     TTFT(1500) = 1500 / 100.4 = 14.9 s
#   而 TTFT_BUDGET_S = 10.0 s
#   反推: 要守住 10 s，上下文只能到 ≈1050 tok（1050/107.0 = 9.8 s ✅）
#
# 两个数只能留一个自洽的组合。三个选项:
#   A. 收紧上下文 → 1050 / 10s        代价: 中位 chunk 只能装 3 个，recall 可能受损
#   B. 放宽延迟   → 1500 / 15s        代价: 船员等 15s；M6 真硬件只会更慢
#   C. 先按 A，让 M1c 测出代价 ✅推荐   两个数都是 L2/owner=M6，现在谁也不是终值；
#                                     现在要做的不是挑一个，而是让它们自洽并把取舍量化
#
# 当前基线采用 C（1050 / 10s）。若后续 owner experiment 的实测支持放宽延迟预算，
# 须通过新的契约变更同步修改 MAX_PROMPT_TOKENS 与 TTFT_BUDGET_S。
# 无论选哪个，M1c 必须在 ~1050 与 ~1500 两档预算下各报一次 Recall。
#
# ⚠️⚠️ 这是【整个 prompt】的预算，不是 context 块的预算。
#    llama-bench -p N 测的是 N 个【总 prompt token】的 prefill，
#    所以 TTFT(1050)=9.8s 对应的是【整个 prompt】1050 token。
#    旧名 MAX_CONTEXT_TOKENS 掩盖了这一点，曾导致 pack_context 把全部预算给了 chunk，
#    系统提示词/问题/引用头/chat template 全部白送 —— 实际 TTFT 12.4s，超预算 24%。
#    这是"数字有来源但口径没核对"的第三次，见纪律五。
#
# ⚠️ TOP_K_CONTEXT 只是个数上限保护，不是本值的替代品。
MAX_PROMPT_TOKENS: int = 1050

# [L2] owner_experiment: M1c（Recall@3 与 Recall@5 的差距出来后重定）
#
# 来源与推导（v0.7 与旧版 contracts 的推导有算术错误，本版修正）:
#   实测 chunk 字符数 中位 1169 / p95 1491 / max 1893
#   按英文技术文档 4 字符/token 估算 →  中位 ≈292 tok，p95 ≈373 tok，max ≈473 tok
#   最坏情况: 1500 ÷ 473 ≈ 3.2  → 3 个
#   中位情况: 1500 ÷ 292 ≈ 5.1  → 5 个
# 旧注释写"1500 ÷ 中位 292 tok ≈ 3 个"，算术不成立（那样得 5）。
# 真正得出 3 的是【最坏情况】，即用 max chunk 定预算。
#
# 因此本契约的语义是【预算内的 relevance 连续前缀，以本值为个数上限】:
#   - 组件按 relevance 降序逐个累加 token 估算
#   - 遇到第一个装不下的即【停止，不跳过】（prefix 语义，见 pack_context）
#   - 同时不得超过本值个数
# 按 CONTEXT_PACK_BUDGET_TOKENS=765 重算（含每块的引用头 +14 tok）:
#   最坏情况 765 ÷ (473+14) ≈ 1.6 → 1 个
#   中位情况 765 ÷ (292+14) ≈ 2.5 → 2 个
#   → 实际装 1-2 个居多；本值 5 只是上限保护，几乎不会触及
# ⚠️ 这个数比 v0.7 设想的"3 个"少得多。它是 prompt 口径修正 + 引用头计入的
#    共同结果，【不是缺陷】—— 是之前的预算把开销白送了。
#    真实代价由 M1c 的 Recall@1/@2/@5 量化，不靠猜。
# 好处: chunk 偏小时不白白浪费预算。
# ⚠️ CD01 的 formal gold 是 5 个 chunk（3 条 citation）跨 2 份手册（canonical GoldChunkMap
#    8cf9f3be…；旧写"3 个 chunk"从未由 canonical 映射实测支持，更正见 DECISIONS 2026-10-01）
#    —— 在 765 chunk 预算下几乎必然装不全，
#    这会成为 M1c 的一个真实观察（failure_tag="context_truncation"），
#    【不要】为了让它装下而调大预算，那是为一道题优化。
TOP_K_CONTEXT: int = 5

# [L2] owner_experiment: M1c（Recall@k 曲线出来后重定）
TOP_K_RETRIEVE: int = 20

# ---- 分块 ----
# [L2] owner_experiment: M5（消融实验）
# 来源: 实测该配置下 chunk 字符数 中位 1169 / p95 1491 / max 1893，分布可控
CHUNK_TARGET_TOKENS: int = 350
CHUNK_OVERLAP_TOKENS: int = 60
# 小于此长度的块直接丢弃（页眉残渣、空白页、纯目录页）
CHUNK_MIN_CHARS: int = 120

# token 估算系数。英文技术文档约 4 字符/token。刻意不引入 tokenizer 依赖。
#
# ⚠️ [L2] owner_experiment: M1c（用真 tokenizer 抽样核对一次）
# 【v0.2.0 从 L3 升级】。旧注释写"误差 ±15% 不影响结论"，在改用按预算填充之后
# 这句话失效了: 本值现在【直接决定装多少内容进 context】，而超预算是【静默】的
# —— 不报错，只是 TTFT 变长。装多个 chunk 时误差还会累加。
# 算一下: 预算 1050，若估算低估 15%，实际 1208 tok → TTFT 11.4s，已破 10s 预算。
CHARS_PER_TOKEN_EST: int = 4

# 预算安全余量。[L2] owner_experiment: M1c
# 对【扣除 prompt 开销后的剩余预算】乘本值，为 CHARS_PER_TOKEN_EST 的估算误差留空间。
# 最坏情况 945 × 1.15 = 1087 tok → TTFT 10.2s，仍在预算附近。
CONTEXT_PACK_MARGIN: float = 0.90

# 每个 chunk 渲染进 prompt 时的引用头开销，形如 "[SMM §2.1 PDF p.73]"。
# [L3] 实测替换后可降级；当前为估算。
# ⚠️ 引用头【不是可选装饰】: 没有它模型无法给出处，Citation First 落不了地。
#    所以它的 token 必须计入预算，见 Chunk.est_prompt_tokens()。
CITATION_HEADER_EST_TOKENS: int = 14

# ---- 生成 ----
# [L2] owner_experiment: M6（按船端实测生成速率重定）
GEN_TIMEOUT_S: float = 30.0

# [L2] owner_experiment: M6
# 来源: 5s 在 CPU 推理上不现实，见上方 prefill 实测
TTFT_BUDGET_S: float = 10.0

# [L1] 全链路禁用 thinking 模式。
# 来源: 2026-08-17 实测。"What is SOLAS?" 开启 thinking 时输出 2014 token / 36.7s，
#       关闭后 380 token。三个理由:
#         (a) 超出延迟预算，船端 CPU 会放大数倍
#         (b) 与心智模型冲突 —— 模型应"摘要依据"而非自由推理
#         (c) thinking 正是模型脱离依据自由发挥的地方，幻觉最易从此进入
# 实测有效: Ollama API `"think": false`；MLX `--prefill-response "<think>\n\n</think>\n\n"`
# 实测【无效】: Ollama prompt 里写 `/no_think`（被当作普通文本，仍输出 751 token）
# falsified_if: 出现证据表明 thinking 显著提升带出处问答的正确率且延迟可接受
THINKING_ENABLED: bool = False

# [M] 生成采样一律关闭。
#
# why_not_falsifiable:
#   约束的【本体】是"四臂的采样设置必须一致且可复现"，这是实验设计层面的
#   混杂控制要求，不是关于本系统的经验主张，不可能被本项目的实验推翻。
#   n=31 的规模下，几道题因采样翻面就能移动 6 个百分点 ——
#   正好是实用效应闸（Δ≥19pp）的三分之一量级；四臂若用不同随机性，
#   臂间差异里就混进了采样噪声，McNemar 检验的前提不成立。
#
#   0.0 是满足该约束【最省事的一种实现】: 输出确定，单次跑即可，不需重复采样。
#   （用固定 seed 的 temperature=0.7 也能控住混杂，只是更贵。）
#   所以级别标 [M] 而不是 L1 —— 标 L1 就要写 falsified_if，而它没有真正的证伪条件，
#   那正是新增 [M] 类别想避免的情形。
#
# ⚠️ 【可证伪的是另一条，独立成立】: 某些 MoE 后端在 temperature=0 下仍不确定。
#    开工前必须实测: 同一 prompt 跑两遍，输出逐字节相同才算通过；
#    不通过则该模型跑 3 次取多数，并在报告中注明。
GENERATION_TEMPERATURE: float = 0.0

# ---- 判分（实施方案 §14.3）----
# [L2] owner_experiment: M2 预注册（冻结后不得更改）
# 来源: §14.3 三级判分。命中 ≥ 本比例的 required_elements 且无冲突内容 → Partial。
# ⚠️ Partial 在主指标里【一律映射为 Incorrect】(见 Verdict / scored_as 的契约)，
#    只作为诊断维度单独报告。理由: 引入部分分会让主指标变成连续量，
#    McNemar 就用不了了；n=31 规模上少一个自由参数比多一点分辨率更值钱。
PARTIAL_MIN_ELEMENT_HIT_RATIO: float = 0.60

# ---- 语料 ----
CORPUS_LANG_DEFAULT: str = "en"

# ---- 拒答阈值 ----
# [L2] owner_experiment: M1c（用检索分数分布校准）
# 来源: S9 MIN_RELEVANCE calibration（2026-10-02；DECISIONS "S9 MIN_RELEVANCE calibration result"）。
#   状态 PROVISIONAL_SAME_SET_CALIBRATED。hybrid gate_score = max(match_score over top-20)：
#   7 道计分陷阱 ≤ 0.7792718520928508，31 道可答题 ≥ 0.8012534982161421；人工取值 0.78。
#   同集 7/7 计分陷阱拒答、0/31 可答题误拒；规则留一 6/7（失败 = TR01）。
# ⚠️ 经验操作阈值（empirical operating threshold），不是概率 / calibrated confidence / gold 置信度，
#   不可跨 retriever 移植。falsified_if: hybrid 打分语义、生产检索路径、reranker 进入 score / gating、
#   match_score 构造任一改变；或代表性校准数据显示不可接受的可答题误拒 / 陷阱误放 → 须重校。
# 目标: 陷阱题的最高检索分落在阈值之下，可答题的判定量（max match_score）落在阈值之上；
#   gold chunk 分数只作诊断（S9 协议 S9-D2）。
#
# ⚠️ 已知效度隐患（M2 汇报时必须标注）:
#   计划用同一批 39 题的检索分数分布来校准本值，而 M2 又用同一批题测拒答表现
#   —— 这是在测试集上调参，会让 B/D 臂的拒答成绩系统性偏乐观。
#   缓解: 加留一交叉验证（7 道计分陷阱轮流留出）把乐观幅度【量化】成一个数字，
#   而不只是写"偏乐观"。报告写法:
#     "同集校准的拒答正确率 X%，留一估计 Y%，乐观幅度约 Z pp"
#
# ⚠️⚠️ 【优化方向】校准时【不要】去找"漂亮切点"，要取【保守偏低】的值。
#   理由 —— 两边代价不对称:
#     可答题检索分低于阈值 → 系统拒答 → 记 Incorrect → 【直接扣主指标】
#     陷阱题检索分低于阈值 → 系统拒答 → 正确，但陷阱只做个案呈现【不进主指标】
#   计分陷阱仅 7 道，任何"拒答正确率"都是噪声，不作为定量结论。
#   为一个不计分的指标去抬高阈值，是拿会计分的东西换不计分的东西。
#   判据: 【尽量不误拒 31 道可答题】，而非最大化陷阱拒答率。
#   拒答的正式校准（独立校准集）排到 M5 安全验收，那时它才是主角。
#
# ⚠️⚠️ 【判定位置必须唯一】拒答条件是:
#
#        max(hit.match_score for hit in retrieved_hits) < MIN_RELEVANCE
#
#    三处不许含糊，任一处放松都会让三个组件实现出三种语义，
#    而分数分布图会看起来【都很合理】:
#
#    (a) 用 match_score，【不是】relevance。
#        relevance 可以是 RRF 之类的纯排名分，绝对阈值对它在数学上不成立。
#    (b) 用 max，【不是】均值、也不是进 context 的那几个的均值。
#        问的是"语料里到底有没有够格的证据"，那是最好那条说了算。
#    (c) 作用在 retriever 返回的【全部 hits（top-k_retrieve）】上，
#        【在 pack_context 之前】。
#        若作用在打包后的集合上，预算把好证据挤掉会被误读成"语料里没有证据"——
#        两种完全不同的失败会记成同一种。
#        被预算挤掉的情况有 failure_tag="context_truncation" 专门接着。
MIN_RELEVANCE: float = 0.78


# ==============================================================================
# 阈值（二）⚠️ 未校准 —— 当前值是猜的，尚无实测依据
#
# 本节与上一节【物理分开】是刻意的。
# 纪律一: 任何进入契约的数字，必须有一次实测或一次真实数据勘察作为依据。
# 本节的值还不满足这一条，因此单列，让误用在视觉上就显眼。
# ==============================================================================

# 非 chunk 部分的 prompt 开销预留。[L2] owner_experiment: M1c
#
# ⚠️⚠️ 这个数【不应该长期是估算值】。系统提示词是固定的，可以用真 tokenizer
#    精确量一次。packed-context 的最终结论（及据此写入 M2 预注册的数字）之前【必须】实测替换，
#    并把实测值记进 DECISIONS.md。S8 固定-k 检索基线不读取本值（DECISIONS 2026-10-01 收窄）。
#    ⚠️ 当前预算余量已归零（见 CONTEXT_PACK_BUDGET_TOKENS 的核算：TTFT 10.13s）。
#      这意味着【任何低估都会直接破预算】。若实测是 250 而非 200，整条链要重算。
#
# 组成（当前为估算，待实测）:
#   系统提示词（B/D 臂，含引用与拒答指令）   80–150
#   问题                                     15–40
#   chat template 脚手架（role 标记、BOS）    10–20
# ⚠️ 取【四臂中最长的那套】（B/D）。A/C 臂无 context 块、提示词更短，
#    但预算必须按最坏情况定 —— 见"四臂 prompt 天然不同"这条已知混杂。
# 这个取值没有校准！！
#      实测时点: S4a 选定主模型后,用【该模型的 tokenizer】量四臂提示词初稿,
#      立即替换本值;S10 预注册时用终稿再量一次锁死。
#      【2026-10-01 收窄，见 DECISIONS 同日条目】旧写法"必须在 S8 之前完成 —— S8 的 k 由 chunk
#      预算决定"已被依赖审计取代: S8 固定-k 检索基线的评测截断点是预注册的固定集合，不由 chunk
#      预算导出，也不读取本值；本值只进入 packed-context measurement 与最终打包结论。
#      realized k 是 pack_context 的逐题输出，不是评测截断点。
PROMPT_OVERHEAD_RESERVE_TOKENS: int = 200

# 派生常量【唯一定义处】—— 组件一律用它，不要各自去算。
# 三段式: 先扣掉 prompt 开销（可精确量，不需余量），再对剩余部分乘估算余量。
CONTEXT_PACK_BUDGET_TOKENS: int = int(
    (MAX_PROMPT_TOKENS - PROMPT_OVERHEAD_RESERVE_TOKENS) * CONTEXT_PACK_MARGIN
)
# 当前取值: (1050 - 200) × 0.90 = 765
# 核算（纪律五：能互相推导的两个数字必须显式核算一次）:
#   765 × 1.15（CHARS_PER_TOKEN_EST 的最坏低估）+ 200 = 1080 实际 token
#   rate(1080) = 107.4 + (1080-1024)/1024 × (92.3-107.4) = 106.6 t/s
#   TTFT = 1080 / 106.6 = 10.13 s
# ⚠️ 10.13 > TTFT_BUDGET_S = 10.0。技术上仍破线，余量已归零。
#    【不要】为了凑过线去把 CONTEXT_PACK_MARGIN 调成 0.88 —— 那是为了让数字好看而动参数。
#    正确的反应是把 PROMPT_OVERHEAD_RESERVE_TOKENS 列为 M1c 开跑前的必测项。
#    （该项属于 packed-context 线；S8 固定-k 检索基线不读取本常量，见 DECISIONS 2026-10-01。）

# [L2] owner_experiment: 回填脚本首跑报告（按 L1+L2 命中率与误命中情况重定）
#
# 语义【不是】"丢弃短于此长度的片段"。见 split_quote_fragments 的契约。
# 短片段仍参与 full evidence cover 判定（L1/L2/AMBIGUOUS），只是【不能单独构成 L3 部分命中】。
# 本值【只】影响 L3 与 L4 的分界，不影响任何 formal gold 集合（见 MatchLevel）。
#
# 来源（2026-09-07 对 testset_v5_2 的 39 条 citation 实测）:
#   95 个片段，长度 min 11 / p5 14 / 中位 38 / max 236
#   最短的几个恰恰是答案本身:
#     'For Tankers'(11)  '54mg% urine'(11)  'Not Required'(12)  'should be Zero'(14)
#     分别是 FL06 / FL07 / ML02 的核心事实
#   → 若按"丢弃短片段"实现且阈值 ≥15，这些会被丢掉，
#     结果是【片段变少 → L1 的"全片段命中"更容易满足 → 命中率虚高】。
#     那是一个内建在常量里的"为了让数字好看"。
QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH: int = 20

# [L2] owner_experiment: M1c（按实际 BM25 分数分布重定）
#
# BM25 原始分无上界，必须用【查询无关】的单调映射压进 0..1。
# 约定用饱和函数:  match_score = s / (s + BM25_SCORE_SATURATION)
#     s=0 → 0.0      s=k → 0.5      s→∞ → 1.0
# 选饱和函数而非 min-max 的理由见约定 1（min-max 是查询相关的，会让 top-1 恒为 1.0）。
# ⚠️ k 的量级依赖语料与查询长度，当前 10.0 是【猜的】，M1c 出分布后重定。
#
# ⚠️ 已知局限（M1c 必须诊断）: 饱和函数是【查询无关】的，但【不是查询长度无关】的。
#    BM25 原始分随查询词数增长 —— 15 词的程序题与 3 词的事实题，
#    同样好的匹配会给出量级不同的 s，导致固定阈值对短查询系统性更严。
#    评测集里问题长度差异很大（多语种题 vs 10 个 required_element 的程序题）。
#    诊断: 把 39 道题的 top-1 match_score 对【问题 token 数】做散点。
#    若明显正相关 → 阈值在按问题长度而非证据质量分流，需改归一化（如按查询词数缩放）。
#    现在不预先加复杂归一化 —— 那属于未测就写进架构（纪律四）。
#
# ⚠️【前提不变量，2026-10-01 S8 protocol apply】本映射要求 BM25 原始分 s ≥ 0。
#    Okapi 原式 IDF = ln((N−n+0.5)/(n+0.5)) 在 n > N/2 时为负，可使 s < 0 →
#    映射落到 0..1 之外（且在 s = −BM25_SCORE_SATURATION 处奇异），违反约定 1。
#    因此任何 BM25 实现的 IDF 必须对全部 1 ≤ n ≤ N 恒非负；具体 IDF 公式、k1、b、analyzer
#    属实验预注册，不在本文件。可执行形式见 bm25_match_score()。
# ⚠️ 本映射严格单调，只用于分数归一化与 match_score 语义；【不参与】BM25 单路排序 ——
#    排序用原始分 s 本身（见 retrieval_order_key）。
BM25_SCORE_SATURATION: float = 10.0

# 余弦相似度不需要新常量: (cos + 1) / 2 本身就是查询无关的固定映射。
# 该公式写进 vector.py 的 docstring，不在此处再定义一个常量。


# ==============================================================================
# 枚举与字面量
# ==============================================================================

# M2 的四个实验臂。写进 EvalItemResult 与 results.csv，用于归因。
#   A = 裸模型（无检索无微调）    B = 仅 RAG
#   C = 仅微调                    D = RAG + 微调
ExperimentArm = Literal["A", "B", "C", "D"]

# 评测题型。与 testset 的 type 字段一一对应。
QuestionType = Literal[
    "fact_lookup",   # 事实查找，单值数字，答案唯一
    "concept",       # 概念定义
    "procedure",     # 程序步骤
    "cross_doc",     # 跨文档，答案需综合两份手册
    "trap",          # 陷阱，语料中确实没有答案，应拒答
    "multilingual",  # 非英语提问
]

# 陷阱题的子类型。
TrapSubtype = Literal[
    "absent_no_hit",           # 语料里完全没有相关内容
    "absent_with_distractor",  # 有格式相似但指向错误对象的干扰项
]

# 检索来源标记，仅用于调试归因，不参与打分。
HitOrigin = Literal["bm25", "vector", "hybrid", "rerank"]

# 判分结果（实施方案 §14.3 三级判分）。
Verdict = Literal["Correct", "Partial", "Incorrect"]

# gold chunk 回填的匹配级别（实施方案 §24 第 4 步）。
# 【v0.3.0 重新冻结】单条 citation 的解析语义。记号:
#   P          = (citation.doc_id, citation.pdf_page)
#   C(P)       = 语料中 doc_id、pdf_page 都等于 P 的全部 chunk
#   fragments  = split_quote_fragments(citation.quote)      —— 全部片段，含短片段
#   cand(f)    = { x ∈ C(P) | f 是 normalize_text(x.text) 的子串 }
#   full evidence cover = 满足 ∀f: cand(f) ∩ S ≠ ∅ 的任意 S ⊆ C(P)
#
#   L1         最小基数 full cover【唯一】且 |cover| = 1   → 该 chunk 进 mapping
#   L2         最小基数 full cover【唯一】且 |cover| ≥ 2   → cover 全部 chunk 进 mapping
#   AMBIGUOUS  存在 full cover，但最小基数 full cover 不唯一 → 不进 mapping，needs_review
#   L3         不存在 full cover，且至少一个满足 is_sole_match_eligible 的片段有 candidate
#              → 只是【部分证据】，不是已解析的 citation；不进 mapping，needs_review
#   L4         C(P) 非空，不存在 full cover，且没有可进 L3 的 eligible 命中
#              （含: 零命中 / 只命中不具 sole-match eligibility 的短片段）
#              → 【引文抄写有出入】的强信号；不进 mapping，needs_review
#   FAIL       C(P) 为空 → 【页缺失】；不进 mapping，needs_review
#
# ⚠️ 页范围只有 citation 所在页（EXACT_CITATION_PAGE_ONLY），【不】搜 pdf_page±1，
#    不做任何邻页 fallback。依据: chunk 按页构建、不跨页。
#    若 chunker 开始产出跨页 chunk，本条必须重新走契约仪式。
# ⚠️ 最小基数 full cover 不唯一时【必须】是 AMBIGUOUS。禁止按 chunk id、corpus 顺序、
#    片段顺序任取一个，也禁止取并列 cover 的并集 —— 这些都加入了 citation 本身没有提供的偏好。
#    实现可以用 corpus 顺序做确定性的枚举与序列化，但顺序【不得】参与消歧。
# ⚠️ L4 与 FAIL 必须分开。合并会让"引文抄错"伪装成"页缺失"。
# ⚠️ section 【不是】匹配前置条件（表示差异如 "Chapter 15" vs "15" 不得制造 false negative），
#    只用于审计与 mismatch 报告。
MatchLevel = Literal["L1", "L2", "AMBIGUOUS", "L3", "L4", "FAIL"]

# 能进入 GoldChunkMap.mapping 的级别。【唯一定义处】。其余级别一律 needs_review。
FORMAL_MATCH_LEVELS: frozenset[str] = frozenset({"L1", "L2"})

# report.csv 的 reason 列取值，与 MatchLevel 一一对应（见 MATCH_LEVEL_REASON）。
GoldResolutionReason = Literal[
    "RESOLVED_SINGLE_CHUNK",   # L1
    "RESOLVED_MULTI_CHUNK",    # L2
    "CARRIER_AMBIGUOUS",       # AMBIGUOUS
    "FRAGMENTS_UNMATCHED",     # L3
    "NO_ELIGIBLE_MATCH",       # L4
    "PAGE_ABSENT",             # FAIL
]
MATCH_LEVEL_REASON: dict[str, str] = {
    "L1": "RESOLVED_SINGLE_CHUNK",
    "L2": "RESOLVED_MULTI_CHUNK",
    "AMBIGUOUS": "CARRIER_AMBIGUOUS",
    "L3": "FRAGMENTS_UNMATCHED",
    "L4": "NO_ELIGIBLE_MATCH",
    "FAIL": "PAGE_ABSENT",
}

# 失败归因标签（实施方案 §24.3）。
# 每一个标签对应一种完全不同的修法 —— 有了它，M5 该调什么是数据说的不是猜的。
FailureTag = Literal[
    "parse_failure",        # 解析阶段就丢了内容
    "chunk_boundary",       # 内容被切到了两个 chunk 中间
    "bm25_miss",            # 关键词检索没召回
    "vector_miss",          # 向量检索没召回
    "fusion_miss",          # 两路都召回了但融合排序把它挤掉
    "ranking_miss",         # 进了 top-k_retrieve 但没进 context
    "context_truncation",   # 进了 context 但被 token 预算截断
    "generation_miss",      # 证据在 context 里，但模型没用
    "refusal_miss",         # 该答却拒答
    "distractor_capture",   # 被干扰项俘获（拒答题的主要失败模式）
]


# ==============================================================================
# 数据契约
# ==============================================================================

@dataclass(frozen=True)
class Citation:
    """一条出处。

    契约:
      - (doc_id, section, pdf_page) 三元组必须足以让人在原始 PDF 中唯一定位
      - pdf_page 从 1 开始
      - printed_page 是页脚原文（如 "1 of 7"），可能为 None，且【不唯一】，
        只用于展示给船员核对，绝不用于定位
      - quote 是原文引语。可能包含省略号 "..." 表示非连续片段 ——
        任何消费 quote 的代码【必须】调用 split_quote_fragments()，
        不许自己写切片逻辑（约定第 8 条的同类要求：单点定义）。
        字面包含匹配对含省略号的引文永远不成立。
        （2026-09-07 实测: 移除 TR01 那条后共 38 条 citation，
          其中 20 条含省略号、18 条连续；95 个片段最短 11 字符）
    """
    doc_id: str            # SMM / ERM / NPM / CRM / FMM / QMM / TACM / CMM / EMM
    section: str           # "2.1" / "GP 1.1" / "PART I"
    pdf_page: int          # 1-based
    printed_page: str | None = None
    quote: str = ""

    def display(self) -> str:
        """船员看到的出处字符串，形如 `SMM §2.1 p.1 of 7 [PDF p.12]`。"""
        parts = [self.doc_id, f"§{self.section}"]
        if self.printed_page:
            parts.append(f"p.{self.printed_page}")
        parts.append(f"[PDF p.{self.pdf_page}]")
        return " ".join(parts)


@dataclass(frozen=True)
class Chunk:
    """文档的一个可检索单元。

    契约:
      - text 非空，且已剥离页眉页脚（页眉中的元数据搬到本对象的字段里）
      - (doc_id, section, pdf_page) 必须足以让船员在原始 PDF 中定位到这一段
      - pdf_page 从 1 开始；None 仅当来源确实无页码概念
      - image_ids 在当前范围内恒为空列表（不是 None）。
        字段保留是为后续图片支持留口子，当前不填、也不引入任何视觉依赖。
      - source_hash 是源文件哈希，供增量更新使用；当前阶段可为空字符串
      - id 必须是确定性的：同一输入两次解析产生相同的 id。
        禁止混入随机数、时间戳、内存地址。
    """
    id: str
    text: str
    doc_id: str
    doc_name: str
    section: str
    section_title: str | None = None
    pdf_page: int | None = None
    printed_page: str | None = None
    issued_by: str | None = None
    revision: str | None = None
    lang: str = CORPUS_LANG_DEFAULT
    image_ids: list[str] = field(default_factory=list)
    source_hash: str = ""

    def est_tokens(self) -> int:
        """本块【文本本身】的 token 估算。【不含引用头】。

        用途: 分块逻辑（与 CHUNK_TARGET_TOKENS 比较）。
        契约: 恒 ≥1。当前 CHUNK_MIN_CHARS=120 保证不会出现 0，
        但类型本身没有 runtime 校验，返回 0 会让 pack_context 无限装块。
        """
        return max(1, len(self.text) // CHARS_PER_TOKEN_EST)

    def est_prompt_tokens(self) -> int:
        """本块【渲染进 prompt 后】的 token 估算。【含引用头】。

        用途: pack_context 的预算填充。
        契约: 必须计入引用头 —— 没有引用头模型就无法给出处，
        Citation First 落不了地；而只数 text 会让每个 chunk 静默少算约
        CITATION_HEADER_EST_TOKENS 个 token。

        ⚠️ 为什么拆成两个方法而不是让 est_tokens 直接加上引用头:
           两个消费方的需求【相反】——
             分块逻辑问"这块文本本身多大"     → 不该含引用头
             pack_context 问"这块进 prompt 花多少" → 该含
           合并会让分块阈值被静默抬高 CITATION_HEADER_EST_TOKENS。
           这与"一个数据结构不要同时干两件事"是同一条原则。
        """
        return self.est_tokens() + CITATION_HEADER_EST_TOKENS


@dataclass(frozen=True)
class Hit:
    """一条检索结果。【两个分数，各司其职】。

    契约:
      - relevance = 【排序分】。恒 0.0..1.0，越大越相关。pack_context 依赖它降序。
        融合检索可以用 RRF 之类的纯排名方法产生它。
          · bm25 baseline : bm25_match_score(s)，与 match_score【数值相同、字段语义不同】
                            （人工裁决，DECISIONS 2026-10-01 blocker closure）
          · vector / hybrid : 尚未冻结（随各自 protocol closure 裁决）

      - match_score = 【绝对匹配质量】。恒 0.0..1.0，且必须【查询无关】。
        它是 MIN_RELEVANCE 拒答判定的【唯一】依据。
          · bm25   : s / (s + BM25_SCORE_SATURATION)，要求 s ≥ 0（IDF 恒非负），
                     可执行形式 bm25_match_score()
          · vector : (cos + 1) / 2
          · rrf hybrid : 【必然与 relevance 不同】。
            RRF 分数只由排名决定（Σ 1/(60+rank)），双路都排第一恒为 2/61 = 0.0328，
            【无论内容是完美匹配还是垃圾匹配】。
            → 此时 match_score 必须取【各路归一化原始分的 max】。
              ⚠️ 锁死 max，不许用加权和。两个理由:
                (a) 语义干净: max 的含义是"任何一路找到的最好证据有多好"，
                    正是拒答判定要问的问题。
                (b) 加权和会引入耦合: 融合权重是 L2 参数（M1c 要扫），
                    让 match_score 依赖它 = 调融合权重会同时移动拒答阈值的语义，
                    两个本该独立的旋钮被绑在一起。

      ⚠️ 为什么分成两个字段: "怎么排"和"够不够好"是两个问题。
         用一个字段同时承担，要么排序失去信息，要么阈值失去意义 ——
         后者是【静默】的: 拒答率会直接变成 0%，不报任何错。

      - 【三种分数必须区分（2026-10-01 S8 protocol apply）】RAW_SCORE ≠ RELEVANCE ≠ MATCH_SCORE:
          RAW_SCORE   = 检索器内部未归一化的精确排序量（bm25 = 原始分 s；vector = 原始 cosine；
                        rrf hybrid = 精确表示的 RRF 和）。检索器的全序由它决定
                        （见 Retriever.search / retrieval_order_key）。本类【不】携带它 ——
                        需要 RAW_SCORE / corpus_ordinal / kind 的消费方（评测、审计）用
                        RetrievalResultRecord（Retriever.search_records），本类保持面向生产。
          RELEVANCE   = 上面定义的排序分（0..1）。"按 relevance 降序"与"按 RAW_SCORE 全序"
                        同时成立，要求 relevance 是 RAW_SCORE 的单调不减函数。
          MATCH_SCORE = 上面定义的查询无关绝对匹配质量（0..1）。
        任何持久化检索结果的 artifact 若记录分数，必须三者分开存，并各带 kind 标注
        （raw_score_kind / relevance_kind / match_score_kind）；禁止只输出一个含义不明的 `score`。
        逐 hit 的载体与序列化见 RetrievalResultRecord；kind 的取值词表与 artifact 其余 schema
        属实验预注册，不在本文件。

      - origin 仅用于调试归因，不参与打分
    """
    chunk: Chunk
    relevance: float
    match_score: float
    origin: HitOrigin = "hybrid"


# RetrievalResultRecord 三个 kind 字段的取值格式。取值词表本身属实验预注册，不在本文件。
_SCORE_KIND_RE = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class RetrievalResultRecord:
    """一条检索结果的【评测 / 审计载体】。与 Hit 并列，不替代 Hit。

    为什么不扩展 Hit（人工裁决，DECISIONS 2026-10-01 blocker closure）: Hit 面向生产
    （pipeline / pack_context / 拒答）；本类服务 retriever → 评测 runner → 确定性 artifact。
    bm25 / vector / hybrid 共用本类，不得各自发明记录格式。产出方式见 Retriever.search_records。

    契约（构造时校验，违反抛 ContractViolation）:
      - chunk: 被检索到的 Chunk。chunk_id 是 chunk.id 的只读投影，不是独立字段，二者不可能不一致。
      - corpus_ordinal: 该 chunk 在 canonical corpus/chunks.jsonl 中的【0-based 物理行序】（第一行 = 0）。
        int（不含 bool），≥ 0。它【不是】pdf_page、不是页内 chunk 序号、不是 chunk_id 的字典序位置；
        只用于确定性 tie-break 与 provenance / 审计。与语料的对应由 validate_retrieval_records 校验。
      - raw_score: 检索器的精确排序量 RAW_SCORE（见 Hit）。类型只能是 float 或 fractions.Fraction
        （精确 RRF 和）；有限；不接受 bool / int / float 子类（如 numpy 标量 —— 调用方先转 float）。
        未归一化，不要求在 0..1。全序只由它与 corpus_ordinal 决定（retrieval_order_key）。
      - relevance: 排序导向的归一化分（见 Hit）。float，0.0..1.0。
      - match_score: 查询无关的绝对匹配质量（见 Hit），面向 MIN_RELEVANCE 的【唯一】字段。float，0.0..1.0。
      - raw_score_kind / relevance_kind / match_score_kind: 各自分数的计算口径标注；
        非空，只含 [a-z0-9_]，以小写字母开头。三者是【独立字段】—— 数值相同（如 bm25 baseline 的
        relevance 与 match_score）也各自保存；消费方不得互换 relevance 与 match_score。
      - 不含任何评测 / gold 信息（question_id、gold 标记、命中判定都不在本类）；不含 latency 与墙钟时间 ——
        本类的序列化进入哈希的 normative artifact。rank 不存：它就是记录在返回序列中的位置。

    序列化见 retrieval_record_json_object / serialize_retrieval_record。
    """
    chunk: Chunk
    corpus_ordinal: int
    raw_score: float | Fraction
    raw_score_kind: str
    relevance: float
    relevance_kind: str
    match_score: float
    match_score_kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, Chunk):
            raise ContractViolation(f"chunk 必须是 Chunk，得到 {type(self.chunk).__name__}")
        if not (type(self.raw_score) is float or isinstance(self.raw_score, Fraction)):
            raise ContractViolation(
                f"raw_score 必须是 float 或 Fraction，得到 {type(self.raw_score).__name__}"
            )
        # 有限性与 corpus_ordinal 的类型 / 非负校验只有一个实现处。
        retrieval_order_key(self.raw_score, self.corpus_ordinal)
        for name in ("relevance", "match_score"):
            value = getattr(self, name)
            # NaN 与任何值比较都为假，因此被区间检查拒绝。
            if type(value) is not float or not (0.0 <= value <= 1.0):
                raise ContractViolation(f"{name} 必须是 0.0..1.0 的 float，得到 {value!r}")
        for name in ("raw_score_kind", "relevance_kind", "match_score_kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SCORE_KIND_RE.fullmatch(value):
                raise ContractViolation(f"{name} 格式非法（需 [a-z][a-z0-9_]*）: {value!r}")

    @property
    def chunk_id(self) -> str:
        return self.chunk.id


@dataclass(frozen=True)
class Answer:
    """一次问答的最终输出。

    契约:
      - refused=True  时 text 必须为 None 且 reason 非空。
        这是【正常状态】，不是错误。
      - refused=False 时 citations 必须非空 ——
        没有出处就不允许有答案（心智模型的直接推论）。
      - degraded=True 表示运行在纯检索模式（生成层不可用），
        此时 text 为 None 而 citations 非空，是合法组合。
      - arm 标识本次由哪个实验臂产生，用于 M2 归因。
        ⚠️ A/C 臂没有检索层，citations 天然为空。这不是契约违反，
           是该臂的固有属性 —— 见 validate_answer 的例外分支。
    """
    text: str | None
    citations: Sequence[Citation]
    refused: bool
    reason: str | None = None
    latency_s: float = 0.0
    ttft_s: float = 0.0
    degraded: bool = False
    arm: ExperimentArm = "B"


@dataclass(frozen=True)
class EvalItem:
    """评测集的一道题。对应 testset jsonl 的一行。

    契约:
      - expected 是【唯一权威】的"该不该答"字段。
        type=="trap" 与 expected=="refuse" 在当前数据中恒等价，
        但评测脚本只许分支于 expected。
      - expected=="answer" 时 citations 必须非空
      - expected=="refuse" 时 citations 必须【为空】。
        拒答题按定义没有"答案所在的出处"；那类引文属于干扰项来源，
        应放进 known_distractor.source。
        （TR01 曾违反此条，v5.3 已修正。回填脚本必须硬断言这一条。）
      - trap_subtype 标为 absent_with_distractor 时 known_distractor 必须非空，
        否则该标签无法核验
      - exclude_from_primary_score=True 的题不计入主分母（当前仅 TR02，SMM 缺页）

      ⚠️ 本类【不含 gold_chunk_ids】。
         它是 citations 在某套语料+分块配置上的投影，属派生产物，见 GoldChunkMap。
         把它放进评测集会让 M5 的分块消融失去再生路径。
    """
    id: str
    type: QuestionType
    language: str                       # ISO 639-1 小写
    question: str
    expected: Literal["answer", "refuse"]
    gold_answer: str
    citations: Sequence[Citation] = ()
    answer_key: dict | None = None      # {value, unit, operator}
    required_elements: Sequence[str] = ()
    acceptable_elements: Sequence[str] = ()
    known_distractor: dict | None = None
    trap_subtype: TrapSubtype | None = None
    safety_critical: bool = False
    at_risk: bool = False
    exclude_from_primary_score: bool = False
    source_boundary_ambiguity: str | None = None
    pair_id: str | None = None
    rationale: str = ""


# GoldChunkMap 文件名里语料哈希的前缀长度；也是 --corpus-sha 断言允许的短形式长度。
CORPUS_SHA_PREFIX_CHARS: int = 8


@dataclass(frozen=True)
class GoldChunkMap:
    """citations → chunk id 的映射。【派生、可再生、确定性，不进评测集】。

    ── 语义单元（v0.3.0 冻结）──────────────────────────────────────────────
      - 单条 citation 的 formal gold = 该 citation 的【唯一】最小基数 full evidence cover
        （定义见 MatchLevel）。一条 citation 是一组人工给定的证据片段；formal gold 是
        覆盖其【全部】片段所需的 chunk，不是"某一个 chunk 独自包含整条 quote"。
      - 片段一律来自 split_quote_fragments()，【包括】短于
        QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH 的片段。该常量只决定 L3/L4 的分界，
        不得用于从完整证据中删除片段。
      - 页范围只有 citation 所在页 (doc_id, pdf_page)，不搜邻页。
      - 只有 FORMAL_MATCH_LEVELS（L1/L2）贡献 chunk。AMBIGUOUS / L3 / L4 / FAIL
        【不贡献任何 chunk】—— "该页有 chunk 但不知道哪个承载证据"推不出
        "这些 chunk 都是 gold"；部分证据也不是完整 gold。
      - mapping[qid] = 该题全部 citation 的 formal cover 的并集，按 corpus 顺序排列、无重复。

    ── mapping 的键 ──────────────────────────────────────────────────────────
      - 键集合【恰好】等于评测集中 expected=="answer" 的题，按评测集顺序排列。
      - expected=="refuse" 的题【不出现】。这是正常语义：拒答题没有 gold 出处
        （validate_eval_item 已保证其 citations 为空），混进 Recall 分母会让 Recall 失去意义。
      - 【fail-closed】可答题的每一条 citation 都必须解析为 L1 或 L2，映射才可被接受。
        任何一条不是 → 不产出被接受的 GoldChunkMap（resolver 以非零码退出，
        只写 report.csv 供人工复核）。以下三种写法【全部禁止】:
          · mapping[qid] = []            —— 读起来是"这题没有 gold"
          · 省略未解析的 answer qid      —— 与拒答题不可区分，且静默缩小 Recall 分母
          · 把部分 citation 的并集当成完整 gold —— mapping 不带级别，下游无法察觉
        可执行形式见 validate_gold_chunk_map()。

    ── 不含什么 ──────────────────────────────────────────────────────────────
      ⚠️ 本类【不含 match_levels】。
         一道题的多条 citation 各自有级别，压成一个 question-level 级别会丢掉
         【到底是哪一条需要人工复核】。匹配级别与逐片段证据的权威记录是 report.csv
         （每条 citation 一行，列见 GOLD_CHUNK_MAP_REPORT_COLUMNS）。
         一个数据结构不要同时干"提供映射"和"承载审计"两件事。
      ⚠️ 本类【不含时间戳】（v0.3.0 删除 built_at）。
         它是派生产物，逐字节可再生是前提；canonical 映射及其 report.csv 另按 DECISIONS
         2026-09-28（TRACK_CANONICAL_MAP_AND_REPORT_IN_GIT）冻结入 Git
         （旧写"它不进 Git"已被该决定取代，叙述更正见 DECISIONS 2026-10-01）。
         EvalItemResult.gold_chunk_map_sha256 记录的是
         serialize_gold_chunk_map() 输出的字节哈希。墙钟时间会让同输入两次生成的
         哈希不同，已记录的结果就再也对不上再生的映射。运行时间只许打到 stdout / log。
      ⚠️ Recall 在一题多 gold chunk 时按 ANY / ALL / coverage 哪种判命中，
         【不由本类决定】—— S8 固定-k 指标协议（ANY_GOLD / GOLD_COVERAGE / ALL_MAPPED_GOLD）
         由 S8 预注册定义（DECISIONS 2026-10-01）。
      ⚠️ 本类【不表达】同一道题多条 citation 之间的逻辑关系（AND / OR / 仅佐证）。
         mapping 是各 citation formal cover 的并集，因此 gold ⊆ top-k（ALL_MAPPED_GOLD）
         只是严格诊断量，【不得】称为 answer-level complete evidence。

    ── identity 字段 ─────────────────────────────────────────────────────────
      testset_version      由 testset_version_from_path() 从评测集文件名导出，禁止手写。
      testset_sha256       评测集文件字节的 SHA-256（64 位小写十六进制）。
      corpus_chunks_sha256 resolver 【自行计算】的 chunks.jsonl 字节 SHA-256（完整 64 位）。
                           CLI 的 --corpus-sha 只是期望值断言（8 位前缀或 64 位全长），
                           不匹配即硬失败；映射里只写计算值，从不写断言值。
      ── construction identity 四层（v0.3.1 冻结；四者含义不同，不得互相替代）──
      corpus_chunks_sha256       = 最终冻结语料的【字节】身份（见上）。语料相等性只由它决定。
      corpus_builder_name        = canonical 构建的【语义实现族/版本】。
                                 不是某个 class 的名字（当前 canonical 语料由
                                 ingest/build_corpus.py 经 Phase B 路径生成，不是 KaivaPdfParser.parse()）。
      construction_rules_sha256  = 权威 builder 导出的【静态构建语义指纹】（64 位小写十六进制）。
                                 它【不是】语料哈希、Git commit、源 PDF 身份、OCR artifact 身份，
                                 也不是运行时/工具链清单。
      chunker_config             = 核心【数值型】分块构建参数的人类可读确定性身份
                                 （键 = 常量名小写，字典序，`key=value`，";" 连接）。

      权威来源（H3）: 三项构建身份只由 ingest/builder_identity.py 导出 ——
        CORPUS_BUILDER_NAME / construction_rules_identity() / effective_chunker_config_identity()。
      本文件【不】列举 builder 依赖、不持有这些值、也【不 import】builder
      （本文件谁都不依赖；直接 import 会形成 core.contracts → ingest.builder_identity →
      core.contracts 的循环）。validate_gold_chunk_map() 通过参数接收实现
      CorpusBuilderIdentity 的权威提供者；resolver 必须传入 ingest.builder_identity 本身，
      不得手写、复制或钉住任何当前值。

      ── 不进入本类的运行时 provenance（H2）──
      源 PDF 身份、accepted OCR manifest、--doc-lang 实参、Poppler/pdftotext 版本、
      视觉诊断 CSV 身份 —— 都【不】写进 GoldChunkMap。
      理由: 本类是"人工 citations → 冻结语料 chunks"的派生投影，不是第二份语料构建清单。
        这些输入变化而语料字节不变 → 本映射不应仅因此失效；
        导致语料字节改变 → corpus_chunks_sha256 已使旧映射失效。
      前提: corpus_chunks_sha256 始终是可核验的字节锚 —— canonical 语料在场时可直接重算；
        丢失时能由冻结代码 + 冻结的必要输入重建并核验。
      ⚠️ REOPEN CONDITION: 若出现"语料字节可能已变、但 corpus_chunks_sha256 无法重算、
        也无法由冻结输入重建核验"的情形，本边界必须重新打开；
        届时不得再声称语料哈希足以承担唯一字节锚。

      ── 版本（0.4.0 起拆分，DECISIONS 2026-10-01 final protocol closure）──
      contracts_version    = 生成时的 CONTRACTS_VERSION（整模块版本）。只作 provenance，【不参与】兼容判定 ——
                           只改检索 / 打包等无关语义的契约递增不得使映射失效。
      gold_chunk_map_semantics_version
                           = 生成时的 GOLD_CHUNK_MAP_SEMANTICS_VERSION。【兼容判定的唯一依据】:
                           与当前 GOLD_CHUNK_MAP_SEMANTICS_VERSION 不等 → 不能作为当前 canonical 映射
                           （不表示它在自己的 identity 下历史无效）。拆分后生成的映射必须写入本字段。
      legacy 规则（只服务拆分前生成的历史映射，不看文件名 / 路径 / mtime / 日期）:
                           本字段缺失（None）的映射是拆分前 schema。当且仅当其 contracts_version 属于
                           GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS（拆分前带该字段的契约版本闭集）时，
                           把 contracts_version 读作它的 GoldChunkMap 语义版本（拆分前二者是同一个数）；
                           contracts_version 不在该闭集 → 拆分后生成却缺字段 → 拒绝。
                           本字段存在但 contracts_version 属于该闭集 → 拆分前不可能写出本字段 → 拒绝。
                           例: canonical 映射 8cf9f3be…（contracts_version="0.3.1"，无本字段）→ 语义版本 0.3.1。

    ── 确定性 ────────────────────────────────────────────────────────────────
      同一输入两次生成，serialize_gold_chunk_map() 的输出必须逐字节相同。
      candidate / formal chunk 的顺序一律用 corpus 顺序（chunks.jsonl 行序）；
      该顺序只用于枚举与序列化，【不得】用于消歧（见 MatchLevel）。

    逐字节再生的作用域 = 【原生成身份】（生成时的 resolver 代码 + 契约语义 + 输入）。实测（DECISIONS 2026-10-01）:
      canonical 映射 8cf9f3be… 由其原生成代码（contracts d30ed34 + resolver 8719761）逐字节再生；
      0.4.0 resolver 再生的 mapping 与 report.csv 相同，但版本字段不同（contracts_version 0.4.0、新增语义版本字段），
      不要求、也不声称与历史文件逐字节相同 —— 这不是历史可复现性失败。历史 artifact 保持冻结，按 legacy 规则仍被接受。
    再生方式（canonical 映射另已冻结入 Git）:
        python3 scripts/resolve_gold_chunks.py --chunks corpus/chunks.jsonl \\
            --testset eval/testset_v5_3.jsonl --corpus-sha <8 位或 64 位> \\
            --out-dir eval/gold_chunk_map/
    """
    testset_version: str          # 如 "v5.3"，见 testset_version_from_path()
    testset_sha256: str
    corpus_chunks_sha256: str     # 完整 64 位，resolver 自算
    corpus_builder_name: str      # 见上方 construction identity 四层
    construction_rules_sha256: str  # 见上方 construction identity 四层
    chunker_config: str           # 见上方 construction identity 四层
    contracts_version: str        # = 生成时的 CONTRACTS_VERSION；只作 provenance，见上方"版本"
    mapping: dict[str, list[str]]           # question_id -> [chunk_id, ...]，见上方键约束
    # 放在最后且默认 None: 拆分前 schema 的映射（无此键）仍能按原样构造，序列化时省略 → 原字节不变。
    gold_chunk_map_semantics_version: str | None = None   # 见上方"版本"与 legacy 规则

    def filename(self) -> str:
        """映射文件的标准文件名（不含目录）。

        形如: map__ts-v5.3__corpus-c8978777__builder-<corpus_builder_name>.json
        只由 identity 字段决定，与生成时间无关。
        """
        return (
            f"map__ts-{self.testset_version}"
            f"__corpus-{self.corpus_chunks_sha256[:CORPUS_SHA_PREFIX_CHARS]}"
            f"__builder-{self.corpus_builder_name}.json"
        )

    def report_filename(self) -> str:
        """配套 report.csv 的标准文件名：filename() 把 `.json` 换成 `.report.csv`。

        映射未被接受（fail-closed）时 report 仍按此名写出 —— 它只依赖 identity 字段。
        """
        return self.filename()[: -len(".json")] + ".report.csv"


# GoldChunkMap 的 report.csv 表头。【唯一定义处】，理由同 RESULTS_COLUMNS。
# 每条 answer citation 一行；行序 = 评测集顺序，再按 citation_index。
#   citation_index        该 citation 在 EvalItem.citations 中的位置，【0-based】
#   pdf_page              【1-based】（约定第 4 条）
#   section_exact_match   citation.section 是否等于该页某 chunk 的 section。只用于审计，不是匹配前置
#   match_level           MatchLevel
#   reason                = MATCH_LEVEL_REASON[match_level]
#   formal_chunk_ids      只含 L1/L2 的 formal cover；其余级别为空
#   candidate_chunk_ids   有片段命中、但不在 formal cover 中的 chunk
#   needs_review          当且仅当 match_level 不在 FORMAL_MATCH_LEVELS
#   fragment_matches_json 每个片段一项: {"index", "text", "length", "sole_match_eligible",
#                         "candidate_chunk_ids"}，按片段序；
#                         json.dumps(ensure_ascii=False, separators=(",", ":"))
# 多个 chunk id 用 ";" 连接，一律按 corpus 顺序，禁止按 set / hash 迭代顺序输出。
GOLD_CHUNK_MAP_REPORT_COLUMNS: tuple[str, ...] = (
    "question_id",
    "citation_index",
    "doc_id",
    "section",
    "pdf_page",
    "section_exact_match",
    "fragment_count",
    "match_level",
    "reason",
    "formal_chunk_ids",
    "candidate_chunk_ids",
    "needs_review",
    "fragment_matches_json",
)


@dataclass(frozen=True)
class EvalItemResult:
    """单题 × 单臂的评测结果。【McNemar 检验的输入单元】。

    契约（实施方案 §14.2 / §18.3）:
      - 一次 M2 实验产生 len(testset) × 4 = 39 × 4 = 156 条，【不是 4 条】
      - 汇总指标由本表【算出来】，不预先存 —— 存汇总值会让原始数据与
        汇总值有漂移的可能
      - scored_as 是 verdict 按 §14.3 映射后的主指标取值:
          Correct  -> 1
          Partial  -> 0   （一律映射为 Incorrect，只作诊断维度）
          Incorrect-> 0
      - refused 与 correct 独立: 拒答题上 refused=True 才可能 Correct
      - citations_correct 与 gold_chunk_hit 对 A/C 臂【均为 None】（没有检索层）。
        ⚠️ 【必须用 None 而不是 False】—— 用 False 会让 A/C 臂被算成
           "引用准确率 0%" / "gold 命中率 0%" 并混进平均，
           那是用一个天然为 0 的指标去否定微调，违反公平性纪律。
           聚合时必须先滤掉 None，不能当 0 参与平均。
      - elements_total 恒 ≥1（实测: 31 道可答题的 required_elements 数量 1..10，
        无一为空）。若将来出现为 0 的题，命中率无定义，判分必须落到 answer_key，
        不得用 0/0。
      - is_blind_scored 记录该条是否走了 §14.3 的盲评协议。
        非盲评的结果不得进入主指标。
      - failure_tag 只在 scored_as==0 时填（§24.3 十标签），用于逐题归因

    落盘: eval/results.csv，只追加，永不删行。列顺序见 RESULTS_COLUMNS。
    """
    # ---- 标识 ----
    exp_id: str
    run_at: str                 # ISO 8601
    arm: ExperimentArm
    question_id: str
    # ---- 判分 ----
    verdict: Verdict
    scored_as: int              # 0 / 1
    is_blind_scored: bool
    elements_hit: int
    elements_total: int
    refused: bool
    expected: Literal["answer", "refuse"]
    citations_correct: bool | None
    failure_tag: FailureTag | None
    # ---- 检索与上下文 ----
    retrieved_chunk_ids: Sequence[str]
    retrieval_scores: Sequence[float]
    gold_chunk_hit: bool | None          # A/C 臂为 None，理由同 citations_correct
    n_chunks_in_context: int             # pack_context 后实际进了几个（k 已是变量）
    actual_context_tokens: int           # 真 tokenizer 数出的实际 token 数
                                         # —— 唯一能事后发现 CHARS_PER_TOKEN_EST
                                         #    偏了多少的手段。A/C 臂填 0
    # ---- 性能 ----
    ttft_s: float
    latency_s: float
    peak_mem_gb: float
    # ---- 可复现性指纹（§18.3 机制 3b）----
    model_id: str
    model_digest: str
    teacher_digest: str
    lora_adapter_sha256: str
    retriever: str
    reranker: str               # 未引入时填 "none"，见 Reranker 的说明
    top_k_retrieve: int
    top_k_context: int
    max_prompt_tokens: int               # 原名 max_ctx_tokens，见 MAX_PROMPT_TOKENS 的口径说明
    pack_budget_tokens: int              # = CONTEXT_PACK_BUDGET_TOKENS（三段式派生）
    temperature: float                   # 四臂必须一致，见 GENERATION_TEMPERATURE
    prompt_config_sha256: str
    testset_sha256: str
    corpus_chunks_sha256: str
    gold_chunk_map_sha256: str
    code_commit: str
    seed: int


# results.csv 的表头。【唯一定义处】——
# 表头写在 csv 文件里、字段写在 dataclass 里，是两个定义处，必然漂移。
RESULTS_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(EvalItemResult))


@dataclass(frozen=True)
class IndexManifest:
    """索引包的自描述清单。

    契约（见实施方案 §11 显式失败面）:
      - 船端【启动时】必须校验本清单。任一项不匹配 → 抛 IndexIntegrityError
        并【拒绝启动】。绝不静默降级使用不匹配的索引。
      - embedder_name + embedder_dim 不匹配是最难 debug 的故障类型
        （向量空间对不上，检索全废但不报错），必须在启动就挡住。
      - chunker_config 必须记录: M5 的分块消融会产生多个索引包，
        没有这个字段就分不清哪个包用的哪套分块，
        也无法判断某份 GoldChunkMap 是否与本索引匹配。

      ⚠️ 向量与 chunk 的【行序对应】是本清单最关键的一条:
         embeddings 文件的第 i 行必须对应 chunks.jsonl 的第 i 行。
         加载时先比对 chunk_count 与 embeddings 行数，不一致直接抛
         IndexIntegrityError。向量错位是【最难 debug 的一类错】——
         检索结果看起来完全正常，但全是乱的，且不报任何错。
    """
    contracts_version: str
    embedder_name: str
    embedder_dim: int
    corpus_sha256: str
    chunk_count: int          # 必须等于 embeddings 的行数
    embeddings_sha256: str    # 向量文件哈希；空字符串表示该索引包不含向量
    built_at: str             # ISO 8601
    parser_name: str
    chunker_config: str       # "target350_overlap60_min120"


# ==============================================================================
# 异常 —— 禁止静默吞掉
# ==============================================================================

class ShipRagError(Exception):
    """本项目所有异常的基类。"""


class ParseError(ShipRagError):
    """文档解析失败。

    契约: 单份文档失败应记入 ingest_failures.csv 并跳过，【不中断整批】。
    """


class RetrievalError(ShipRagError):
    """检索层故障（索引损坏、加载失败、后端不可达）。

    契约: 绝不能降级成返回 [] —— 那会把"崩了"伪装成"没检索到"。
    """


class GenerationTimeout(ShipRagError):
    """生成超时。

    契约: 由 pipeline 捕获并降级为纯检索模式（Answer.degraded=True）。
    """


class IndexIntegrityError(ShipRagError):
    """索引包校验失败（checksum 或 embedder/chunker 指纹不匹配）。

    契约: 启动时抛出，拒绝启动。
    """


class ContractViolation(ShipRagError):
    """数据不满足本文件声明的契约。

    用于断言检查，例如 refused=False 却没有 citations、
    或 expected=="refuse" 的题带了 citations。
    """


# ==============================================================================
# 工具函数 —— 放在本文件是因为它们承载语义，不是便利封装
#
# 判据: 如果两个组件各自实现一遍会导致语义漂移，就该放这里。
# ==============================================================================

_ELLIPSIS_RE = re.compile(r"\.\.\.|…")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """折叠连续空白为单个空格并去首尾空白。

    契约: 所有做文本比对的地方【必须】先过这个函数。
    PDF 抽出的文本里空白是不可靠的（-layout 模式会插入大量对齐空格），
    不归一化的字面比对对本项目的语料基本不成立。
    """
    return _WHITESPACE_RE.sub(" ", s).strip()


def split_quote_fragments(quote: str) -> list[str]:
    """把含省略号的引文切成片段，归一化后返回。

    契约:
      - 按 "..." 或 "…" 切分，去掉空片段，每段过 normalize_text
      - 【不丢弃任何片段】，包括很短的。
        丢弃短片段的后果是反直觉的: 片段变少 → "全片段命中"更容易满足
        → 匹配级别虚高。见 QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH 的实测依据。
      - 短片段的限制由 is_sole_match_eligible() 表达，不由本函数表达
      - quote 为空或归一化后为空 → 抛 ContractViolation。
        空 quote 会匹配整页每个 chunk，是必须被挡住的输入。

    任何消费 Citation.quote 的代码都必须走本函数，不许自己写切片逻辑。
    """
    if not quote or not quote.strip():
        raise ContractViolation("quote 为空：空 quote 会匹配整页每个 chunk")
    parts = [normalize_text(p) for p in _ELLIPSIS_RE.split(quote)]
    frags = [p for p in parts if p]
    if not frags:
        raise ContractViolation(f"quote 切片后无有效片段: {quote!r}")
    return frags


def is_sole_match_eligible(fragment: str) -> bool:
    """该片段能否【单独】构成一次部分命中（L3）。

    契约:
      - 短于 QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH 的片段返回 False。
        理由: 'Not Required' / 'For Tankers' 这类通用短语在一页里可能出现多次，
        单凭它命中会产生假阳性。
      - 返回 False 【不代表】该片段被忽略。它仍参与 full evidence cover 判定
        （L1/L2/AMBIGUOUS，见 MatchLevel），且可以是 formal cover 的必要组成部分。
      - 本函数只决定"不存在 full cover 时，算 L3 还是 L4"。
    """
    return len(fragment) >= QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH


def validate_eval_item(item: EvalItem) -> None:
    """校验一道评测题是否满足契约。不满足抛 ContractViolation。

    契约: 评测脚本与回填脚本在读入 testset 后【必须】对每一条调用本函数。
    这些条件在 EvalItem 的 docstring 里是声明，在这里是可执行的断言 ——
    只有声明的话，违反了也不会有人发现（TR01 就是这么混过去的）。
    """
    if item.expected == "answer" and not item.citations:
        raise ContractViolation(f"{item.id}: expected=answer 但 citations 为空")
    if item.expected == "refuse" and item.citations:
        raise ContractViolation(
            f"{item.id}: expected=refuse 但 citations 非空。"
            f"拒答题没有 gold 出处；干扰项来源应放进 known_distractor.source"
        )
    if item.trap_subtype == "absent_with_distractor" and not item.known_distractor:
        raise ContractViolation(
            f"{item.id}: 标为 absent_with_distractor 但无 known_distractor，标签无法核验"
        )
    if item.language != item.language.lower():
        raise ContractViolation(f"{item.id}: language 必须是 ISO 639-1 小写")


_TESTSET_FILENAME_RE = re.compile(r"^testset_v(0|[1-9][0-9]*)_(0|[1-9][0-9]*)\.jsonl$")
_TESTSET_VERSION_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
# contracts_version / gold_chunk_map_semantics_version 的格式（X.Y.Z）。
_SEMVER_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
# corpus_builder_name 会进文件名，只允许文件名安全字符。
_BUILDER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def testset_version_from_path(path: str) -> str:
    """从评测集文件名导出 GoldChunkMap.testset_version。

    契约:
      - 只看 basename，格式必须是 `testset_v<MAJOR>_<MINOR>.jsonl`，
        MAJOR / MINOR 为不带前导零的十进制整数；返回 `v<MAJOR>.<MINOR>`。
        例: "eval/testset_v5_3.jsonl" → "v5.3"
      - 不符合格式 → 抛 ContractViolation。评测集版本是 identity 的一部分，
        不允许猜、不允许手写。
      - 不读文件内容；版本与内容的一致性由 testset_sha256 负责。
    """
    m = _TESTSET_FILENAME_RE.match(os.path.basename(path))
    if not m:
        raise ContractViolation(
            f"评测集文件名不符合 testset_v<MAJOR>_<MINOR>.jsonl: {path!r}"
        )
    return f"v{m.group(1)}.{m.group(2)}"


class CorpusBuilderIdentity(Protocol):
    """GoldChunkMap 三项构建身份的【权威提供者】的形状。本文件只定义形状，不持有任何值。

    契约:
      - 唯一的合法提供者是 ingest/builder_identity.py 模块本身（模块对象即满足本形状）。
        resolver 必须把该模块传给 validate_gold_chunk_map()，不得手写、复制或钉住当前值。
      - 本文件【不 import】builder：本文件谁都不依赖，且直接 import 会形成
        core.contracts → ingest.builder_identity → core.contracts 的循环
        （实测: 部分初始化的 core.contracts 在 kaiva_pdf 导入期缺 CHUNK_TARGET_TOKENS）。
      - 三项取值都在调用时读取，不缓存。
    """
    CORPUS_BUILDER_NAME: str

    def effective_chunker_config_identity(self) -> str: ...

    def construction_rules_identity(self) -> str: ...


def _gold_chunk_map_semantics_version_of(gold_map: GoldChunkMap) -> str:
    """一份映射的 GoldChunkMap 语义版本（显式字段，或拆分前 schema 的 legacy 规则）。违反抛 ContractViolation。

    只读映射自身的两个版本字段，不看文件名 / 路径 / mtime / 日期，不做版本区间推断。规则见 GoldChunkMap docstring。
    """
    contracts_version = gold_map.contracts_version
    explicit = gold_map.gold_chunk_map_semantics_version
    if not isinstance(contracts_version, str) or not _SEMVER_RE.fullmatch(contracts_version):
        raise ContractViolation(f"contracts_version 格式非法（需 X.Y.Z）: {contracts_version!r}")
    if explicit is None:
        if contracts_version not in GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS:
            raise ContractViolation(
                f"缺少 gold_chunk_map_semantics_version，且 contracts_version {contracts_version!r} 不属于拆分前闭集 "
                f"{sorted(GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS)}：拆分后生成的映射必须显式写出语义版本"
            )
        return contracts_version
    if not isinstance(explicit, str) or not _SEMVER_RE.fullmatch(explicit):
        raise ContractViolation(f"gold_chunk_map_semantics_version 格式非法（需 X.Y.Z）: {explicit!r}")
    if contracts_version in GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS:
        raise ContractViolation(
            f"contracts_version {contracts_version!r} 属于拆分前版本，不可能写出 gold_chunk_map_semantics_version"
        )
    return explicit


def validate_gold_chunk_map(
    gold_map: GoldChunkMap,
    items: Sequence[EvalItem],
    corpus_chunk_ids: Sequence[str],
    citation_resolutions: Mapping[tuple[str, int], tuple[str, Sequence[str]]],
    *,
    current_corpus_chunks_sha256: str,
    builder: CorpusBuilderIdentity,
) -> None:
    """校验一份 GoldChunkMap 能否被接受为【当前】canonical GoldChunkMap。不满足抛 ContractViolation。

    作用域: CURRENT_CANONICAL_ONLY。
      本函数判断的是"能否在当前 canonical 语料与当前 GoldChunkMap 语义下被接受"，
      【不是】通用的历史 artifact 校验器。一份记录旧 corpus sha、旧 builder/config identity
      或旧 GoldChunkMap 语义版本的历史映射，可能在它自己的 identity 下是有效的历史产物；
      它在这里被拒绝只表示"不能作为当前 canonical 映射使用"，【不表示】它当年无效。
      contracts_version（整模块版本）只作 provenance，不参与接受判定（0.4.0 拆分）。

    输入:
      - items: 生成该映射所用的评测集，【按文件顺序】。本函数会对每条调用 validate_eval_item。
      - corpus_chunk_ids: 语料全部 chunk id，【按 chunks.jsonl 行序】。
      - citation_resolutions: (question_id, citation_index) → (match_level, formal_chunk_ids)，
        覆盖每一道 answer 题的每一条 citation；citation_index 为 0-based。
      - current_corpus_chunks_sha256: 调用方对当前 corpus_chunk_ids 所在 chunks.jsonl
        字节自行计算的完整 SHA-256。
      - builder: 权威构建身份提供者，必须是 ingest.builder_identity 模块本身（见 CorpusBuilderIdentity）。

    本函数负责的是【契约边界】，不负责解析算法本身（片段匹配与最小 cover 的计算属于 resolver）:
      - identity: testset_version 格式；testset_sha256 为完整 64 位小写十六进制；
        corpus_chunks_sha256 == current_corpus_chunks_sha256；
        corpus_builder_name == builder.CORPUS_BUILDER_NAME（且文件名安全）；
        construction_rules_sha256 == builder.construction_rules_identity()（且为 64 位小写十六进制）；
        chunker_config == builder.effective_chunker_config_identity()；
        contracts_version 为 X.Y.Z 格式（只作 provenance）；
        GoldChunkMap 语义版本 == GOLD_CHUNK_MAP_SEMANTICS_VERSION —— 语义版本取
        gold_chunk_map_semantics_version；该字段缺失时按 legacy 规则（见 GoldChunkMap docstring）:
        contracts_version ∈ GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS 则以它为语义版本，否则拒绝；
        字段存在而 contracts_version 属于拆分前闭集 → 拒绝
      - fail-closed: 每条 answer citation 的级别都必须在 FORMAL_MATCH_LEVELS；
        L1 恰 1 个 chunk，L2 至少 2 个，且无重复
      - mapping 键【恰好】是 answer 题、按评测集顺序；拒答题不得出现
      - mapping[qid] 非空、无重复、全部存在于语料、按 corpus 顺序，
        且等于该题各 citation formal cover 的并集

    返回 None 表示通过。不通过即抛异常，绝不返回布尔值让调用方去忽略。
    """
    for item in items:
        validate_eval_item(item)
    item_ids = [item.id for item in items]
    if len(set(item_ids)) != len(item_ids):
        raise ContractViolation("评测集中存在重复的 question id")

    if not _TESTSET_VERSION_RE.match(gold_map.testset_version):
        raise ContractViolation(f"testset_version 格式非法: {gold_map.testset_version!r}")
    for name in ("testset_sha256", "corpus_chunks_sha256", "construction_rules_sha256"):
        if not _SHA256_HEX_RE.match(getattr(gold_map, name)):
            raise ContractViolation(f"{name} 必须是完整 64 位小写十六进制 SHA-256")
    if not _SHA256_HEX_RE.match(current_corpus_chunks_sha256):
        raise ContractViolation("current_corpus_chunks_sha256 必须是完整 64 位小写十六进制 SHA-256")
    if gold_map.corpus_chunks_sha256 != current_corpus_chunks_sha256:
        raise ContractViolation(
            f"corpus_chunks_sha256 {gold_map.corpus_chunks_sha256!r} != 当前语料 {current_corpus_chunks_sha256!r}"
        )
    if not _BUILDER_NAME_RE.match(gold_map.corpus_builder_name):
        raise ContractViolation(
            f"corpus_builder_name 为空或含文件名不安全字符: {gold_map.corpus_builder_name!r}"
        )
    expected_identity = (
        ("corpus_builder_name", builder.CORPUS_BUILDER_NAME),
        ("construction_rules_sha256", builder.construction_rules_identity()),
        ("chunker_config", builder.effective_chunker_config_identity()),
    )
    for name, expected in expected_identity:
        if getattr(gold_map, name) != expected:
            raise ContractViolation(f"{name} {getattr(gold_map, name)!r} != 权威 builder 导出 {expected!r}")
    semantics_version = _gold_chunk_map_semantics_version_of(gold_map)
    if semantics_version != GOLD_CHUNK_MAP_SEMANTICS_VERSION:
        raise ContractViolation(
            f"GoldChunkMap 语义版本 {semantics_version!r} != 当前 {GOLD_CHUNK_MAP_SEMANTICS_VERSION!r}"
        )

    position: dict[str, int] = {}
    for index, chunk_id in enumerate(corpus_chunk_ids):
        if chunk_id in position:
            raise ContractViolation(f"语料中 chunk id 重复: {chunk_id!r}")
        position[chunk_id] = index

    answer_items = [item for item in items if item.expected == "answer"]
    expected_keys = {(item.id, i) for item in answer_items for i in range(len(item.citations))}
    if set(citation_resolutions) != expected_keys:
        raise ContractViolation(
            "citation_resolutions 必须恰好覆盖每道 answer 题的每一条 citation"
        )

    expected_mapping: dict[str, list[str]] = {}
    for item in answer_items:
        union: set[str] = set()
        for i in range(len(item.citations)):
            level, formal = citation_resolutions[(item.id, i)]
            if level not in MATCH_LEVEL_REASON:
                raise ContractViolation(f"{item.id}#{i}: 未知 match_level {level!r}")
            if level not in FORMAL_MATCH_LEVELS:
                raise ContractViolation(
                    f"{item.id}#{i}: match_level={level}，未解析的 answer citation "
                    f"不得产出被接受的 GoldChunkMap（fail-closed）"
                )
            if len(set(formal)) != len(formal):
                raise ContractViolation(f"{item.id}#{i}: formal chunk id 重复")
            if level == "L1" and len(formal) != 1:
                raise ContractViolation(f"{item.id}#{i}: L1 必须恰好 1 个 formal chunk")
            if level == "L2" and len(formal) < 2:
                raise ContractViolation(f"{item.id}#{i}: L2 必须至少 2 个 formal chunk")
            union.update(formal)
        unknown = sorted(cid for cid in union if cid not in position)
        if unknown:
            raise ContractViolation(f"{item.id}: formal chunk 不在语料中: {unknown}")
        expected_mapping[item.id] = sorted(union, key=position.__getitem__)

    if list(gold_map.mapping) != list(expected_mapping):
        raise ContractViolation(
            "mapping 的键必须恰好是 answer 题、按评测集顺序；拒答题不得出现，未解析题不得省略"
        )
    for qid, chunk_ids in gold_map.mapping.items():
        if list(chunk_ids) != expected_mapping[qid]:
            raise ContractViolation(
                f"{qid}: mapping 值必须是各 citation formal cover 的并集、无重复、按 corpus 顺序"
            )


def serialize_gold_chunk_map(gold_map: GoldChunkMap) -> str:
    """GoldChunkMap 落盘文本的【唯一】生成方式。

    契约:
      - 字段顺序 = dataclass 字段顺序；mapping 保持插入顺序（不 sort_keys，
        键序已由 validate_gold_chunk_map 约束为评测集顺序）
      - gold_chunk_map_semantics_version 为 None（拆分前 schema）时【省略该键】，
        因此拆分前映射经 解析 → 本函数 后逐字节不变；不为 None 时作为最后一个键写出
      - ensure_ascii=False，indent=2，末尾恰一个换行
      - 同一 GoldChunkMap 两次调用逐字节相同；EvalItemResult.gold_chunk_map_sha256
        即对本函数输出（UTF-8 编码）取的 SHA-256
      - 本函数【不做】接受性校验。调用方必须先通过 validate_gold_chunk_map()，
        未被接受的映射不得序列化落盘。
    """
    payload = asdict(gold_map)
    if payload["gold_chunk_map_semantics_version"] is None:
        del payload["gold_chunk_map_semantics_version"]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def validate_answer(answer: Answer) -> None:
    """校验一次输出是否满足契约。不满足抛 ContractViolation。

    契约:
      - refused=True  → text 必须 None 且 reason 非空
      - refused=False → citations 必须非空，【但 A/C 臂例外】:
        这两臂没有检索层，无出处是其固有属性而非缺陷（见 §14.5 公平性纪律）
    """
    if answer.refused:
        if answer.text is not None:
            raise ContractViolation("refused=True 时 text 必须为 None")
        if not answer.reason:
            raise ContractViolation("refused=True 时 reason 必须非空")
        return
    # 到这里 refused=False，无论哪个臂都必须有答案内容
    if answer.text is None:
        raise ContractViolation(
            "refused=False 时 text 不得为 None：既没拒答也没答案是非法状态"
        )
    if answer.arm in ("A", "C"):
        return  # 无检索层，天然无 citations
    if not answer.citations:
        raise ContractViolation(
            "refused=False 时 citations 必须非空：没有出处就不允许有答案"
        )


def pack_context(hits: Sequence[Hit],
                 max_tokens: int = CONTEXT_PACK_BUDGET_TOKENS,
                 max_chunks: int = TOP_K_CONTEXT) -> list[Hit]:
    """按预算填充上下文，采用【relevance 连续前缀】语义。

    契约:
      - hits 必须已按 relevance 降序
      - 按顺序逐个累加 token 估算，【遇到第一个装不下的即停止，不跳过】
      - 同时不超过 max_chunks 个
      - 真正的约束是 max_tokens；max_chunks 只是上限保护
      - 【hits 非空时】至少返回一个（若首个 hit 本身就超预算，仍返回它并由上游截断，
        因为返回空会被误读为"没检索到"，违反约定第 2 条）
      - hits 为空时返回 []，那是约定第 2 条意义上的"确实没检索到"，是正常状态
      - 被预算挡在外面的 hit 数量应由调用方记入 failure_tag="context_truncation"
      - 默认预算是 CONTEXT_PACK_BUDGET_TOKENS（已扣掉 prompt 开销并含安全余量），
        【不是】 MAX_PROMPT_TOKENS。传参时也不要自己去减开销或乘余量。
      - 用 chunk.est_prompt_tokens()（含引用头），不是 est_tokens()。
      ⚠️ 本函数【不做】拒答判定。拒答由 pipeline 在【打包之前】、
        对 retriever 返回的全部 hits 用 max(match_score) 判，见 MIN_RELEVANCE。

    为什么是 prefix 而不是 skip-and-fill（跳过装不下的、继续试后面的短块）——
    两个理由，第二个更硬:

      1. 审计清晰。M1c 测的是检索排序。rank #3 因为太长被预算挡在外面，
         这【本身就是一个真实观察】，应记 failure_tag="context_truncation"，
         而不是靠 packing 技巧绕过去 —— 绕过去就看不见这个问题了。

      2. 消除一个不可见的混杂。skip-and-fill 会【系统性偏好短 chunk】——
         所有题都倾向装进更多短块，而 chunk 长度与内容类型相关
         （清单、表格、页眉附近的短段 vs 连续散文）。
         这等于给整个实验加了一个贯穿全部四臂、且从结果里看不出来的偏倚。
         prefix 严格按 relevance 取连续前缀，不对内容形态做隐性选择。
         在要下架构结论的阶段，一个没有隐性偏倚的基线比多用几百 token 值钱。

    skip-and-fill / knapsack packing 记入 BACKLOG，M5 消融时作为对照臂再比。
    """
    packed: list[Hit] = []
    used = 0
    for hit in hits[:max_chunks]:
        t = hit.chunk.est_prompt_tokens()
        if packed and used + t > max_tokens:
            break          # prefix 语义：停止，不 continue
        packed.append(hit)
        used += t
    return packed


def retrieval_order_key(ranking_score: numbers.Real, corpus_ordinal: numbers.Integral) -> tuple:
    """检索结果确定性全序的排序键。bm25 / vector / hybrid 共用这【一个】定义。

    用法: sorted(candidates, key=lambda c: retrieval_order_key(c.raw, c.ordinal))，
    排序结果的前 k 个即 Retriever.search 的返回顺序。返回值只用于比较，不得解析其内部结构。

    契约:
      - 主键 = ranking_score 降序。ranking_score 是该检索器的【精确】排序量（RAW_SCORE，见 Hit）:
        bm25 = 原始 BM25 分 s；vector = 原始 cosine；rrf hybrid = 精确表示的 RRF 和
        （用 fractions.Fraction 等精确有理数；浮点累加顺序会制造或抹掉 tie，禁止）。
      - 次键 = corpus_ordinal 升序，【仅在】ranking_score 完全相等时生效；非 tie 的相对顺序不变。
        corpus_ordinal = 该 chunk 在 canonical chunks.jsonl 中的行序位置。调用方必须保证同一次
        排序中 corpus_ordinal 互不相同，否则不构成全序（本函数只看单个候选，查不出重复）。
      - 不读取任何评测 / gold 信息；禁止改用 chunk_id 字典序或 doc/page 排序打破 tie。
      - ranking_score 必须是有限实数（numbers.Real，不含 bool）；NaN / ±inf → ContractViolation。
        NaN 与任何值比较都为假，会让排序结果依赖输入顺序，即静默失去确定性。
      - corpus_ordinal 必须是 ≥ 0 的整数（numbers.Integral，不含 bool），否则 ContractViolation。
    """
    if isinstance(ranking_score, bool) or not isinstance(ranking_score, numbers.Real):
        raise ContractViolation(f"ranking_score 必须是实数（不含 bool），得到 {type(ranking_score).__name__}")
    if not isinstance(ranking_score, numbers.Rational) and not math.isfinite(ranking_score):
        raise ContractViolation(f"ranking_score 必须有限，得到 {ranking_score!r}")
    if isinstance(corpus_ordinal, bool) or not isinstance(corpus_ordinal, numbers.Integral):
        raise ContractViolation(f"corpus_ordinal 必须是整数（不含 bool），得到 {type(corpus_ordinal).__name__}")
    if corpus_ordinal < 0:
        raise ContractViolation(f"corpus_ordinal 必须 ≥ 0，得到 {corpus_ordinal!r}")
    return (-ranking_score, int(corpus_ordinal))


def bm25_match_score(raw_score: numbers.Real) -> float:
    """BM25 原始分 s → match_score 的【唯一】映射: s / (s + BM25_SCORE_SATURATION)。

    契约:
      - 查询无关（约定 1）: 输出只依赖这一个 hit 自己的原始分，不看本次返回的其他结果。
      - s 必须是有限、≥ 0 的实数（不含 bool）。s < 0 / NaN / ±inf → ContractViolation。
        s < 0 说明所用 IDF 变体可以为负（如 Okapi 原式在 n > N/2 时），
        违反 BM25_SCORE_SATURATION 处的前提不变量。
      - 返回 0.0..1.0；s = 0 → 0.0，s = BM25_SCORE_SATURATION → 0.5；对 s 单调不减
        （浮点精度下，极大的 s 可能映射到同一个值）。
      - 只给出 match_score 的数值。BM25 单路排序用原始分 s（见 retrieval_order_key），不用本值。
    """
    if isinstance(raw_score, bool) or not isinstance(raw_score, numbers.Real):
        raise ContractViolation(f"BM25 原始分必须是实数（不含 bool），得到 {type(raw_score).__name__}")
    if not isinstance(raw_score, numbers.Rational) and not math.isfinite(raw_score):
        raise ContractViolation(f"BM25 原始分必须有限，得到 {raw_score!r}")
    if raw_score < 0:
        raise ContractViolation(
            f"BM25 原始分 {raw_score!r} < 0：IDF 必须恒非负（见 BM25_SCORE_SATURATION 的前提不变量）"
        )
    s = float(raw_score)
    return s / (s + BM25_SCORE_SATURATION)


def bm25_accumulate(query_tokens: Sequence[str], term_contribution: Callable[[str], numbers.Real]) -> float:
    """BM25 原始分 s(q, d) 的【唯一】累加方式（人工裁决 BM25_QUERY_TERM_SEMANTICS = MULTISET、
    BM25_ACCUMULATION = math.fsum，DECISIONS 2026-10-01 final protocol closure 及其 mathematical-semantics 补充）。

    输入:
      - query_tokens: analyzer 对 query 的输出序列（保留重复）。类型必须是 list 或 tuple；
        set / frozenset / dict 及其视图 / Counter / 生成器 / str 一律 ContractViolation。
        这是防止调用方传入已去重或无序表示的 API 闸门，【不】表示元素顺序影响结果。元素必须是非空 str。
      - term_contribution: 对【同一个文档 d】给出单个 token 的 BM25 贡献
        IDF(t) · tf · (k1+1) / (tf + k1 · (1 − b + b · |d| / avgdl))（公式与参数属实验预注册）。
        必须是 token 的【纯函数】（同一 token 恒给同一值），返回有限、≥ 0 的实数（不含 bool），否则 ContractViolation。
    契约（冻结的是数学语义，不是回调执行轨迹）:
      - 贡献多重集 C = [term_contribution(t) for t in query_tokens]：【每一次出现】恰好对应 C 中一个元素（MULTISET）。
        ["alcohol", "alcohol", "testing"] → C = [c(alcohol), c(alcohol), c(testing)]。不得先去重。
      - 返回 math.fsum(C)，float，≥ 0。fsum 对有限输入给出精确和的正确舍入，结果只取决于 C 这个多重集，
        与元素顺序无关；也不受 CPython 3.12 起内建 sum() 改用补偿求和的影响。
      - term_contribution 被调用的次数与顺序【不是契约】：本实现对每个不同 token 求值一次、按出现次数展开；
        其他实现（逐次求值、预先查表）只要 C 相同即合法。合法缓存不得改变结果。
      - query_tokens 为空 → 0.0（"确实没检索到"由调用方据 s > 0 过滤，见预注册）。
    """
    if type(query_tokens) not in (list, tuple):
        raise ContractViolation(
            f"query_tokens 必须是 list 或 tuple（analyzer 输出序列），得到 {type(query_tokens).__name__}"
        )
    contribution_of: dict[str, numbers.Real] = {}
    for token in query_tokens:
        if not isinstance(token, str) or not token:
            raise ContractViolation(f"query token 必须是非空 str，得到 {token!r}")
        if token in contribution_of:
            continue
        value = term_contribution(token)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ContractViolation(f"{token!r} 的贡献必须是实数（不含 bool），得到 {type(value).__name__}")
        if not math.isfinite(value) or value < 0:
            raise ContractViolation(f"{token!r} 的贡献必须有限且 ≥ 0，得到 {value!r}")
        contribution_of[token] = value
    return math.fsum([contribution_of[token] for token in query_tokens])


def validate_retrieval_records(records: Sequence[RetrievalResultRecord], *, k: int,
                               corpus_chunk_ids: Sequence[str]) -> None:
    """校验一次 Retriever.search_records 的返回序列。不满足抛 ContractViolation。

    输入:
      - records: search_records(query, k) 的返回值，原样、按返回顺序。空序列合法（约定 2）。
      - k: 该次调用传入的 k。int（不含 bool），≥ 1。
      - corpus_chunk_ids: canonical corpus/chunks.jsonl 的全部 chunk id，【按物理行序】
        （下标即 0-based 行序）。调用方负责它与所评测语料是同一份字节。
    检查:
      - len(records) ≤ k；每项是 RetrievalResultRecord
      - corpus_chunk_ids[corpus_ordinal] == chunk_id（越界或 1-based 漂移即抛）；corpus_ordinal 互不相同
      - 相邻两项 retrieval_order_key 严格递增（RAW_SCORE 降序，精确相等时 corpus_ordinal 升序）
      - 同一序列内 raw_score_kind / relevance_kind / match_score_kind 各自恒定
      - relevance 是 RAW_SCORE 的单调不减函数: RAW_SCORE 精确相等 → relevance 相等；沿序列 relevance 非增
      - match_score【不】要求随序列单调（hybrid 取各路 max，与融合排名无单调关系）
    不检查（本函数看不到）: 这些记录确实是全部候选在全序下的前 k 项；分数确实按所声明的 kind 算出；
    检索器专属的过滤规则（如 bm25 只返回 RAW_SCORE > 0，属实验预注册）。
    返回 None 表示通过。
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ContractViolation(f"k 必须是 ≥ 1 的 int，得到 {k!r}")
    if len(records) > k:
        raise ContractViolation(f"返回 {len(records)} 条 > k={k}")
    for record in records:
        if not isinstance(record, RetrievalResultRecord):
            raise ContractViolation(f"期望 RetrievalResultRecord，得到 {type(record).__name__}")
    seen: set[int] = set()
    for record in records:
        if record.corpus_ordinal >= len(corpus_chunk_ids):
            raise ContractViolation(
                f"corpus_ordinal {record.corpus_ordinal} 越界（语料 {len(corpus_chunk_ids)} 行）"
            )
        if corpus_chunk_ids[record.corpus_ordinal] != record.chunk_id:
            raise ContractViolation(
                f"corpus_ordinal {record.corpus_ordinal} 处是 {corpus_chunk_ids[record.corpus_ordinal]!r}，"
                f"不是 {record.chunk_id!r}（corpus_ordinal 必须是 0-based 物理行序）"
            )
        if record.corpus_ordinal in seen:
            raise ContractViolation(f"corpus_ordinal {record.corpus_ordinal} 重复")
        seen.add(record.corpus_ordinal)
    for name in ("raw_score_kind", "relevance_kind", "match_score_kind"):
        kinds = {getattr(record, name) for record in records}
        if len(kinds) > 1:
            raise ContractViolation(f"同一次检索混用了多个 {name}: {sorted(kinds)}")
    for prev, cur in zip(records, records[1:]):
        if not (retrieval_order_key(prev.raw_score, prev.corpus_ordinal)
                < retrieval_order_key(cur.raw_score, cur.corpus_ordinal)):
            raise ContractViolation(
                f"{prev.chunk_id} → {cur.chunk_id} 违反全序（RAW_SCORE 降序，精确相等时 corpus_ordinal 升序）"
            )
        if prev.raw_score == cur.raw_score and prev.relevance != cur.relevance:
            raise ContractViolation(f"{prev.chunk_id} / {cur.chunk_id}: RAW_SCORE 相等但 relevance 不等")
        if cur.relevance > prev.relevance:
            raise ContractViolation(f"{prev.chunk_id} → {cur.chunk_id}: relevance 沿全序上升")


# RetrievalResultRecord 序列化的字段与顺序【唯一定义处】。
RETRIEVAL_RECORD_JSON_FIELDS: tuple[str, ...] = (
    "chunk_id", "corpus_ordinal",
    "raw_score", "raw_score_kind",
    "relevance", "relevance_kind",
    "match_score", "match_score_kind",
)


def retrieval_record_json_object(record: RetrievalResultRecord) -> dict:
    """RetrievalResultRecord → JSON 对象（dict，键按 RETRIEVAL_RECORD_JSON_FIELDS 顺序插入）。

    契约:
      - 只含 RETRIEVAL_RECORD_JSON_FIELDS。chunk 正文与其余 Chunk 字段不进入，
        由 chunk_id + corpus 身份追溯。
      - raw_score: float → JSON 数；Fraction → JSON 字符串 "<分子>/<分母>"（最简、分母 > 0，
        分母为 1 也写 "/1"），无损。消费方按 raw_score_kind 解释类型，不得把两种表示混算。
      - relevance / match_score: JSON 数。任何字段都不舍入。
    """
    if not isinstance(record, RetrievalResultRecord):
        raise ContractViolation(f"期望 RetrievalResultRecord，得到 {type(record).__name__}")
    raw = record.raw_score
    raw_json = f"{raw.numerator}/{raw.denominator}" if isinstance(raw, Fraction) else raw
    values = {
        "chunk_id": record.chunk_id,
        "corpus_ordinal": record.corpus_ordinal,
        "raw_score": raw_json,
        "raw_score_kind": record.raw_score_kind,
        "relevance": record.relevance,
        "relevance_kind": record.relevance_kind,
        "match_score": record.match_score,
        "match_score_kind": record.match_score_kind,
    }
    return {name: values[name] for name in RETRIEVAL_RECORD_JSON_FIELDS}


def serialize_retrieval_record(record: RetrievalResultRecord) -> str:
    """单条记录的确定性 JSON 文本（UTF-8 落盘；不含换行）。

    = json.dumps(retrieval_record_json_object(record), ensure_ascii=False, separators=(",", ":"),
    allow_nan=False)。不 sort_keys —— 字段顺序由 RETRIEVAL_RECORD_JSON_FIELDS 固定。
    同一记录两次调用逐字节相同。嵌入更大的 JSONL 行时，用 retrieval_record_json_object 并以同样参数
    dumps，所得子串与本函数输出相同。
    """
    return json.dumps(retrieval_record_json_object(record), ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _check_canonical_json_value(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractViolation(f"{path}: 非有限 float {value!r} 不可进入 digest")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_canonical_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractViolation(f"{path}: dict 键必须是 str，得到 {type(key).__name__}")
            _check_canonical_json_value(item, f"{path}.{key}")
        return
    raise ContractViolation(f"{path}: 类型 {type(value).__name__} 不可进入 digest（不猜转换）")


def canonical_json_bytes(payload: object) -> bytes:
    """digest 输入的【唯一】规范字节形式。跨实验共用（S8 起的各 *_digest；未来 IndexManifest 的协议身份）。

    规则:
      - json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        再 UTF-8 编码；末尾【不】加换行；不做 Unicode 规范化（字符串按原样编码）。
      - 允许的值（递归）: dict（键必须是 str）、list / tuple（同为 JSON 数组）、str、int、bool、
        None、有限 float。其余类型（set、Fraction、bytes、numpy 标量、float 子类、自定义对象）
        → ContractViolation，不猜转换。
      - dict 插入顺序不影响输出（sort_keys，按码点序）；数组顺序【影响】输出（顺序有语义）。
    调用方义务（本函数无法识别）: payload 不得含 Python repr、未冻结字节的散文、墙钟时间、本机绝对路径。
    已有组件内的 digest（construction_rules_identity、ocr_params_digest）各有冻结口径，不迁移到本函数。
    """
    _check_canonical_json_value(payload, "$")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    """canonical_json_bytes(payload) 的 SHA-256，64 位小写十六进制。payload 约束同 canonical_json_bytes。"""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


# ==============================================================================
# 组件接口
#
# 判据（"陌生人测试"）: 盖住实现，只看签名 + docstring，
# 另一个人能否正确使用它且不踩隐藏假设？不能 → docstring 没写清契约。
# ==============================================================================

class Parser(Protocol):
    name: str    # 写入 IndexManifest，用于可复现性

    def parse(self, path: str) -> Sequence[Chunk]:
        """解析一份文档为 Chunk 序列。

        契约:
          - 必须剥离页眉页脚，并把其中的元数据填入 Chunk 字段
          - 空白页 / 少于 CHUNK_MIN_CHARS 的内容 → 直接丢弃，不产出 Chunk
          - 无法解析 → 抛 ParseError（不返回空列表）
          - 必须是确定性的：同一输入两次调用产生相同的 Chunk.id
        """
        ...


class Embedder(Protocol):
    name: str    # 写入 IndexManifest，岸船一致性校验依据
    dim: int

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """文本向量化。

        契约:
          - 返回长度与输入一致，顺序对应
          - 每个向量长度恒为 self.dim
          - 岸端建索引与船端查询【必须使用相同的 name 与 dim】，
            否则向量空间对不上，检索全废且难以察觉
        """
        ...


class Retriever(Protocol):
    def search(self, query: str, k: int = TOP_K_RETRIEVE) -> Sequence[Hit]:
        """检索。

        契约:
          - 返回 0..k 个 Hit，按 relevance 降序
          - 【确定性全序（2026-10-01 S8 protocol apply）】返回顺序 = 按
            retrieval_order_key(ranking_score, corpus_ordinal) 升序取前 k 个:
            先按本检索器的精确排序量 RAW_SCORE 降序（见 Hit），仅当 RAW_SCORE【完全相等】时
            按 corpus_ordinal（chunk 在 canonical chunks.jsonl 中的行序位置）升序。
            bm25 / vector / hybrid 共用这一条规则；禁止用 chunk_id 字典序、doc/page 排序
            或任何评测 / gold 信息打破 tie。同一输入两次调用必须返回相同的序列。
            relevance 是 RAW_SCORE 的单调不减函数（见 Hit），故上一条"按 relevance 降序"仍成立。
          - 【必须同时填 relevance 与 match_score】，两者恒 0..1。
            match_score 的归一化必须【查询无关】（见约定 1 与 Hit 的契约）——
            禁止 per-query min-max / softmax，那会让拒答机制静默失效
          - query 为空或全空白 → 返回 []（有意义的"确实没有"，不是异常）
          - 索引损坏、后端不可达 → 抛 RetrievalError，禁止静默返回 []
          - 【禁止】在本层做拒答判断。拒答由 pipeline 依据 MIN_RELEVANCE 决定
        """
        ...

    def search_records(self, query: str, k: int = TOP_K_RETRIEVE) -> Sequence[RetrievalResultRecord]:
        """同一次检索的评测 / 审计投影: 额外给出 RAW_SCORE、corpus_ordinal 与三个 kind。

        契约:
          - 与 search(query, k) 一一对应: 长度相同、顺序相同，第 i 项的 chunk / relevance / match_score
            与 search 的第 i 个 Hit 相同。两者是同一次排序的两种投影，不得各自实现排序。
          - 返回序列必须通过 validate_retrieval_records(records, k=k, corpus_chunk_ids=<canonical 行序>)。
          - 空 query → []；异常 → RetrievalError；不做拒答判断 —— 同 search。
          - 不接收、不读取任何评测 / gold 信息；question_id 只能在返回之后由调用方作为 join key 使用。
        """
        ...


class Reranker(Protocol):
    """⚠️ 【本组件是否引入尚未决定】—— 实施方案 §13.1。

    v0.7 曾写"只能塞 3 个 chunk → rerank 从可选升为必需"，
    v0.8 撤回了该推断: 从 TOP_K_CONTEXT 小只能推出"排序质量的杠杆变大"，
    推不出"必须引入独立 reranker 模型"。一个额外的 reranker 会带来延迟、内存、
    模型文件与新的故障面，【直接顶撞约束 A4（船上无 IT 支持）】。

    [L2] owner_experiment: M1c。判据:
      Recall@k_context ≈ Recall@20   → 融合排序已够用，【不引入】
      Recall@20 高但 Recall@k_context 明显低 → 值得试，但须过延迟预算
      Recall@20 本身就低             → 问题在召回不在排序，加了也没用

    接口保留在此，是为了让"引入"这件事将来不必再走一次契约仪式；
    【接口存在不等于组件被采纳】。M1c 出数之前，
    EvalItemResult.reranker 一律填 "none"，架构图里不画这一层。
    """
    name: str

    def rerank(self, query: str, hits: Sequence[Hit],
               k: int = TOP_K_CONTEXT) -> Sequence[Hit]:
        """重排。

        契约:
          - 返回至多 k 个 Hit，按新的 relevance 降序
          - 输出的 relevance 仍恒为 0..1，origin 应改为 "rerank"
          - NoOpReranker（直接返回前 k 个）是合法实现，且是当前默认
        """
        ...


class Generator(Protocol):
    name: str      # 写入 results.csv，用于实验归因
    digest: str    # 模型 blob 摘要。记 digest 不记 tag —— tag 会被上游悄悄更新

    def generate(self, prompt: str, *,
                 timeout_s: float = GEN_TIMEOUT_S) -> str:
        """生成。

        契约:
          - 必须已禁用 thinking 模式（见 THINKING_ENABLED 的实测依据）
          - 超时 → 抛 GenerationTimeout，由上游降级为纯检索模式
          - 【禁止】在本层做拒答判断 —— 拒答由 pipeline 依据 MIN_RELEVANCE 决定。
            职责混在一起会让"模型不肯答"和"系统判定证据不足"无法区分。
        """
        ...


# ==============================================================================
# 本文件【不】包含什么（边界声明，防止后来者往里塞东西）
# ==============================================================================
# 1. M2 的判定规则（两道闸: Δ≥19pp 且 McNemar 双侧 p<0.05）
#    → 属【预注册】，不属契约。放进来会让它变成可被代码引用的参数，
#      而它必须是"提交后不改"的一次性承诺。
#
# 2. Partial 的题型映射表（safety_critical / procedure / cross_doc 一律 Incorrect）
#    → 同上，属预注册。本文件只提供 PARTIAL_MIN_ELEMENT_HIT_RATIO 这个阈值。
#
# 3. 四臂的系统提示词全文
#    → 属预注册附录。本文件只保留 prompt_config_sha256 这个指纹字段。
#
# 4. 模型候选池与四道门的状态
#    → 属台账（experiments/models.yaml），状态必须来自实测。
#
# 5. 具体的检索融合权重、rerank 模型、embedding 模型名
#    → 属实验配置（experiments/exp_XXX.yaml），是 M1c/M5 要扫的对象。
#
# 6. M1c 的向量存储方案（穷举 cosine / .npy 落点 / numpy 是否放行）
#    → 属实验实现。3409×1024×4B ≈ 14 MB（canonical corpus c8978777… / 3409 chunks），穷举扫描不是瓶颈；
#      M1c 要答的是"向量检索有没有价值"，不是"哪个向量库好"。
#      船端向量 runtime 由 M6 决定，【实验后端不等于架构事实】——
#      "Ollama 能跑 ≠ llama.cpp 能跑"这个错已经犯过一次。
#
# 7. 单人自审协议、盲评流程、逐题归因的操作步骤
#    → 属执行手册。本文件只提供 FailureTag 这套标签本身。
#
# 边界的判据: 一个值如果【会被实验重新校准】，它属配置或预注册；
#             一个值如果【组件之间必须对齐才能互操作】，它属本文件。


# ==============================================================================
# 0.4.0 相对 0.3.1 的改动记录（S8 protocol apply / blocker closure / final protocol closure，DECISIONS 2026-10-01 三个条目）
# ==============================================================================
# 【R1】Retriever.search 增加确定性全序: (−RAW_SCORE, corpus_ordinal)，tie 只由 corpus 行序打破；
#    可执行形式 retrieval_order_key()。
# 【R2】Hit 写明 RAW_SCORE / RELEVANCE / MATCH_SCORE 三者区分；持久化分数必须各带 kind。
# 【R3】BM25 原始分 s ≥ 0（IDF 恒非负）作为 BM25_SCORE_SATURATION 的前提不变量；
#    可执行形式 bm25_match_score()。饱和映射不参与 BM25 单路排序。
# 【R4】叙述更正: CD01 = 5 chunks / 3 citations；GoldChunkMap 已冻结入 Git；3309 → 3409；
#    PROMPT_OVERHEAD_RESERVE_TOKENS 的 S8 顺序叙述按依赖审计收窄；GoldChunkMap 不表达多 citation 逻辑。
# 【R5】RetrievalResultRecord + Retriever.search_records + validate_retrieval_records
#    + retrieval_record_json_object / serialize_retrieval_record: 独立于 Hit 的逐 hit 评测载体，
#    corpus_ordinal = 0-based 物理行序，三个分数与三个 kind 分开保存。Hit 未改。
# 【R6】Hit.relevance 写明 bm25 baseline = bm25_match_score(s)（与 match_score 数值相同、
#    字段语义不同）；vector / hybrid 的 relevance 未冻结。
# 【R7】canonical_json_bytes / canonical_sha256: 跨实验共用的 digest 规范字节。
# 【V1】版本拆分（人工裁决 SPLIT）: CONTRACTS_VERSION = 整模块版本，0.3.1 → 0.4.0；
#    新增 GOLD_CHUNK_MAP_SEMANTICS_VERSION = "0.3.1" 作为 GoldChunkMap 兼容判定依据；
#    GoldChunkMap 新增末位可选字段 gold_chunk_map_semantics_version（None 时序列化省略）；
#    拆分前 schema 的映射按 legacy 规则（GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS 闭集）解释。
#    canonical GoldChunkMap 8cf9f3be… 字节不变、仍被接受。
# 【B1】bm25_accumulate(): BM25 query token MULTISET（每次出现在贡献多重集中占一个元素）+ math.fsum 累加；
#    只接受 list / tuple 形式的 analyzer 输出序列（人工裁决）。冻结的是数学多重性，
#    不是 term_contribution 的调用次数 / 顺序（合法缓存允许，不得改变结果）。
# 未改动: 全部数值常量 / Chunk / Citation / EvalItem / Hit 字段 / EvalItemResult / IndexManifest /
#    pack_context / MatchLevel / 解析语义（GoldChunkMap 语义版本因此保持 0.3.1）。

# ==============================================================================
# 0.3.1 相对 0.3.0 的冻结改动记录（S6 contract follow-up，DECISIONS 2026-09-28 同名条目）
# ==============================================================================
# 【F1】GoldChunkMap 新增 construction_rules_sha256；construction identity 定为四层:
#    corpus_chunks_sha256 / corpus_builder_name / construction_rules_sha256 / chunker_config。
# 【F2】删除 v0.3.0 的临时推导 chunker_config_identity()（它自带参数列表）。三项构建身份的
#    唯一权威 = ingest/builder_identity.py；本文件只定义 CorpusBuilderIdentity 形状。
# 【F3】validate_gold_chunk_map 新增必填关键字参数 current_corpus_chunks_sha256 与 builder，
#    按权威 builder 导出与当前语料哈希做相等校验（依赖注入，避免 contracts ↔ builder 循环）。
# 【F4】运行时 provenance（源 PDF / OCR manifest / doc_lang / Poppler / 视觉 CSV）不进 GoldChunkMap，
#    附 REOPEN CONDITION（见 GoldChunkMap docstring）。
# 未改动: EvalItem / 引文片段语义 / 最小 cover 语义 / MatchLevel / 全部数值常量。

# ==============================================================================
# 0.3.0 相对 0.2.0 的冻结改动记录（S6 contract clarification，DECISIONS 2026-09-25 同名条目）
# ==============================================================================
# 【G1】单条 citation 的 formal gold = 唯一最小基数 full evidence cover，只看 citation 所在页。
#    MatchLevel 新增 AMBIGUOUS（最小 cover 不唯一）；L1/L2/L3/L4/FAIL 重新定义。
#    旧定义"L2 全片段邻页"作废：chunk 不跨页，邻页命中不是 gold 证据。
# 【G2】只有 L1/L2 贡献 mapping；AMBIGUOUS/L3/L4/FAIL 不贡献，且使映射 fail-closed。
# 【G3】GoldChunkMap 删除 built_at（确定性、可再生）；parser_name → corpus_builder_name；
#    filename() 中 "__parser-" → "__builder-"；新增 report_filename()。
# 【G4】新增 FORMAL_MATCH_LEVELS / GoldResolutionReason / MATCH_LEVEL_REASON /
#    GOLD_CHUNK_MAP_REPORT_COLUMNS / CORPUS_SHA_PREFIX_CHARS，以及
#    testset_version_from_path / chunker_config_identity / validate_gold_chunk_map /
#    serialize_gold_chunk_map。
# 【G5】Recall 一题多 gold 的命中规则【未】在本版冻结（owner: M1c / S8）。
# 未改动: Chunk / Citation / EvalItem / EvalItemResult / IndexManifest / 全部数值常量。

# ==============================================================================
# 本版（0.2.0）相对 0.1.0 的冻结改动记录
# ==============================================================================
# 【P1 阻断】relevance 与 match_score 分离
#    问题: 约定 1 只说"归一化到 0..1"，没说【怎么】归一化。两条静默失败路径:
#      ① per-query min-max → top-1 恒为 1.0 → MIN_RELEVANCE 永远不触发 → 拒答率 0%
#      ② RRF 融合的分数只由排名决定（双路都第一恒为 2/61=0.0328），
#         完美匹配与垃圾匹配完全一样 → 绝对阈值对 hybrid 臂数学上不可能生效
#    而 hybrid 恰恰最可能被选为 M2 主配置。这会让 Citation First 这条 L1
#    在最关键的那一臂上名存实亡，且不报任何错。
#    改: 约定 1 加"查询无关"要求；Hit 加 match_score；hybrid 锁死用 max（不许加权和）；
#        MIN_RELEVANCE 写死判定的三个要素（用 match_score / 用 max / 作用在检索集上）；
#        新增 BM25_SCORE_SATURATION。
#
# 【P2 阻断】1050 是 prompt 预算，不是 context 块预算
#    问题: llama-bench -p N 测的是 N 个【总 prompt token】。旧实现把 945 全给了 chunk，
#    系统提示词/问题/引用头/chat template 白送。核算 945×1.15+200=1287 → TTFT 12.4s，
#    超预算 24%。这是"数字有来源但口径没核对"的第三次。
#    改: MAX_CONTEXT_TOKENS → MAX_PROMPT_TOKENS；新增 PROMPT_OVERHEAD_RESERVE_TOKENS=200；
#        CONTEXT_PACK_BUDGET_TOKENS 改三段式 =(1050-200)×0.90=765；
#        新增 CITATION_HEADER_EST_TOKENS=14；est_tokens 拆成两个方法；
#        EvalItemResult.max_ctx_tokens → max_prompt_tokens。
#
# 【P3】GENERATION_TEMPERATURE 从 [L1] 改为 [M]
#    它没有真正的证伪条件，标 L1 就要写 falsified_if —— 那正是新增 [M] 想避免的情形。
#    措辞同时厘清: 不可证伪的是"四臂采样设置必须一致且可复现"，
#    0.0 只是满足它最省事的一种实现。
#
# 【P4】三处 docstring 与字段修正
#    · validate_answer 补 text is None 检查
#      （原实现下 arm="A" + text=None + citations=[] + refused=False 会通过校验，
#        那是"既没拒答也没答案"的非法状态）
#    · pack_context 的"至少返回一个"限定为"hits 非空时"
#    · GoldChunkMap 补 contracts_version（切片语义一变旧映射即作废，需可追溯）
#
# 【P5】冻结时 CONTRACTS_VERSION 去掉 "-draft"
#    它会写进 IndexManifest → 索引包 → EvalItemResult → M2 预注册。
#    带 -draft 的版本号出现在冻结后的实验记录里，本身就是个错误信号。
#
# ==============================================================================
# 契约会建议顺序（P1/P2 会连带改 Hit/Chunk/常量名，P2 的改名会动 RESULTS_COLUMNS）
# ==============================================================================
#   1. 先定 A: MAX_PROMPT_TOKENS = 1050 还是 1500   → 决定 P2 的所有数字
#   2. 走 P2: 改名 + 三段式分解 + est_tokens 拆两个方法
#            → 动 RESULTS_COLUMNS。趁 results.csv 只有表头，【零成本】；
#              M2 开跑后再改就要动已落盘的数据
#   3. 走 P1: Hit 加 match_score + hybrid 锁死 max + 判定作用域写死
#            → 动 components 的接口
#   4. P3 / P4 独立小修
#   5. CONTRACTS_VERSION → "0.2.0"
#   6. contract: 前缀单独 commit + DECISIONS 逐条入库
#
# ==============================================================================
# 待拍板（本文件已预填推荐值，不同意就改）
# ==============================================================================
#  A. MAX_PROMPT_TOKENS / TTFT_BUDGET_S 取 1050/10（推荐）还是 1500/15
#     ⚠️ 按 P2 分解后，1050 是 prompt 预算，chunk 只剩 765 —— 代价比原估的更大。
#        【这正是要量化的东西，不是改回 1500 的理由。】
#        M1c 的两档 Recall 要按 chunk 预算 765 / 1170 扫，不是 1050 / 1500。
#  B. CONTEXT_PACK_MARGIN = 0.90
#     核算后 TTFT = 10.13s，仍破 10.0 线，余量已归零。
#     【不要】为凑过线把它调成 0.88 —— 正确做法是把
#     PROMPT_OVERHEAD_RESERVE_TOKENS 列为 M1c 开跑前的必测项。
#  C. GENERATION_TEMPERATURE 进契约（判据: 组件之间必须对齐才能互操作）
#  D. EvalItem 纳入本文件（代价: 评测集格式变更也要走契约仪式）
#  E. QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH = 20 作起始值
#  F. BM25_SCORE_SATURATION = 10.0 作起始值
#
# ==============================================================================
# 配套的 M1c 诊断（写进执行手册，不进契约）—— 两条都不过则 M1c 的拒答数据是废的
# ==============================================================================
#  诊断 1「归一化是不是 per-query」:
#    跑两个语义完全不同的 query（一个必然命中、一个必然不命中），比 top-1 match_score。
#      两者都 ≈ 1.0 → 归一化是 per-query 的，拒答机制已死，回去改
#      两者明显不同 → 通过
#    对 hybrid 额外查: relevance 与 match_score 是否为同一个数组。
#      是 → RRF 被直接当成了 match_score，阈值不可能生效。
#
#  诊断 2「match_score 是否被问题长度带偏」:
#    把 39 道题的 top-1 match_score 对【问题 token 数】做散点。
#      明显正相关 → 阈值在按问题长度而非证据质量分流，需改归一化。
#    理由: 饱和函数是查询无关的，但【不是查询长度无关】的 ——
#    BM25 原始分随查询词数增长，而评测集里问题长度差异很大。
