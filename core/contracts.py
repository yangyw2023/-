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

import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Literal, Mapping, Protocol, Sequence

# ==============================================================================
# 版本
# ==============================================================================

# 索引包与运行时的一致性校验依据（见 IndexManifest）。
# 任何影响 Chunk 结构或引用语义的改动都必须递增此版本号。
CONTRACTS_VERSION = "0.3.0"


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
# ⚠️ CD01 的 gold 是 3 个 chunk 跨 2 份手册 —— 在 765 chunk 预算下几乎必然装不全，
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


# ==============================================================================
# 阈值（二）⚠️ 未校准 —— 当前值是猜的，尚无实测依据
#
# 本节与上一节【物理分开】是刻意的。
# 纪律一: 任何进入契约的数字，必须有一次实测或一次真实数据勘察作为依据。
# 本节的值还不满足这一条，因此单列，让误用在视觉上就显眼。
# ==============================================================================

# [L2] owner_experiment: M1c（用检索分数分布校准）
# ⚠️ 0.35 是【猜的】。M1c 之前不得用它下任何结论。
# 目标: 陷阱题的最高检索分落在阈值之下，可答题的 gold chunk 分数落在阈值之上。
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
MIN_RELEVANCE: float = 0.35

# 非 chunk 部分的 prompt 开销预留。[L2] owner_experiment: M1c
#
# ⚠️⚠️ 这个数【不应该长期是估算值】。系统提示词是固定的，可以用真 tokenizer
#    精确量一次。M1c 开跑前【必须】实测替换，并把实测值记进 DECISIONS.md。
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
#      ⚠️ 必须在 S8 之前完成 —— S8 要选 Recall 的 k 值(2 还是 3),
#      k 由 chunk 预算决定,chunk 预算由本值决定。不先量,S8 的 k 值建立在猜测上。
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

      - match_score = 【绝对匹配质量】。恒 0.0..1.0，且必须【查询无关】。
        它是 MIN_RELEVANCE 拒答判定的【唯一】依据。
          · bm25   : s / (s + BM25_SCORE_SATURATION)
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

      - origin 仅用于调试归因，不参与打分
    """
    chunk: Chunk
    relevance: float
    match_score: float
    origin: HitOrigin = "hybrid"


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
         它不进 Git，可再生是前提；EvalItemResult.gold_chunk_map_sha256 记录的是
         serialize_gold_chunk_map() 输出的字节哈希。墙钟时间会让同输入两次生成的
         哈希不同，已记录的结果就再也对不上再生的映射。运行时间只许打到 stdout / log。
      ⚠️ Recall 在一题多 gold chunk 时按 ANY / ALL / coverage 哪种判命中，
         【不由本类决定】—— 那是 metric 契约（owner: M1c / S8，尚未冻结）。

    ── identity 字段 ─────────────────────────────────────────────────────────
      testset_version      由 testset_version_from_path() 从评测集文件名导出，禁止手写。
      testset_sha256       评测集文件字节的 SHA-256（64 位小写十六进制）。
      corpus_chunks_sha256 resolver 【自行计算】的 chunks.jsonl 字节 SHA-256（完整 64 位）。
                           CLI 的 --corpus-sha 只是期望值断言（8 位前缀或 64 位全长），
                           不匹配即硬失败；映射里只写计算值，从不写断言值。
      corpus_builder_name  生成该冻结语料的【语料构建语义实现族】的名字。
                           不是某个 class 的名字（当前 canonical 语料由
                           ingest/build_corpus.py 经 Phase B 路径生成，不是 KaivaPdfParser.parse()）。
                           权威来源 = 语料构建实现导出的 CORPUS_BUILDER_NAME（或等价的单一接口），
                           resolver 只能 import，不得手写。
                           ⚠️ 截至 v0.3.0 该权威导出【尚不存在】，是正式生成 GoldChunkMap 的前置。
      chunker_config       语料构建【实际消费】的全部 chunk 构建参数的确定性序列化。
                           权威来源 = 语料构建实现导出的 effective_chunker_config_identity()
                           （或等价的单一接口）：由构建实现列出它自己消费的参数，
                           而不是由契约列出"它应该消费"的参数。resolver 只能 import，
                           不得手写字符串、复制参数列表或从无关常量推断。
                           ⚠️ 当前的 chunker_config_identity() 只是【临时】的契约侧推导，
                           见其 docstring；正式生成 GoldChunkMap 前必须由构建实现的权威导出取代或桥接。
      contracts_version    = CONTRACTS_VERSION。解析语义一变，旧映射即不能作为当前 canonical 映射
                           （不表示它在自己的 identity 下历史无效），必须可追溯。

    ── 确定性 ────────────────────────────────────────────────────────────────
      同一输入两次生成，serialize_gold_chunk_map() 的输出必须逐字节相同。
      candidate / formal chunk 的顺序一律用 corpus 顺序（chunks.jsonl 行序）；
      该顺序只用于枚举与序列化，【不得】用于消歧（见 MatchLevel）。

    再生方式（这是它可以不进 Git 的前提）:
        python3 scripts/resolve_gold_chunks.py --chunks corpus/chunks.jsonl \\
            --testset eval/testset_v5_3.jsonl --corpus-sha <8 位或 64 位> \\
            --out-dir eval/gold_chunk_map/
    """
    testset_version: str          # 如 "v5.3"，见 testset_version_from_path()
    testset_sha256: str
    corpus_chunks_sha256: str     # 完整 64 位，resolver 自算
    corpus_builder_name: str      # 见上方 identity 字段说明
    chunker_config: str           # 见上方 identity 字段说明（当前临时推导: chunker_config_identity()）
    contracts_version: str        # = CONTRACTS_VERSION；解析语义一变，旧映射即不能作为当前
                                  # canonical 映射，必须可追溯是用哪版契约生成的
    mapping: dict[str, list[str]]           # question_id -> [chunk_id, ...]，见上方键约束

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


def chunker_config_identity() -> str:
    """GoldChunkMap.chunker_config 的【临时】契约侧推导。

    ⚠️ 状态: TEMPORARY_CONTRACT_DERIVATION_PENDING_BUILDER_EXPORT（v0.3.0）。
       它能证明下列三个值来自契约常量，配合源码审计能证明它们当前确实被 chunker 消费；
       但它【不能结构性证明】未来 chunker 没有新增第四个实际参与 chunk 构建的参数
       （silent omission risk）。因此:
         - 它【不是】让 resolver 复制参数列表的许可；
         - 正式生成 GoldChunkMap 之前，必须由语料构建实现导出的
           effective_chunker_config_identity()（或等价的单一权威接口）取代或桥接。

    契约:
      - 只包含【实际参与】canonical chunk 构建的契约常量:
          CHARS_PER_TOKEN_EST / CHUNK_MIN_CHARS / CHUNK_TARGET_TOKENS
        （v0.3.0 审计: components/parsers 与 ingest 读取这三者；
          CHUNK_OVERLAP_TOKENS 未被任何分块代码读取，故【不】进入 identity，
          直到某个 chunker 真正开始消费它 —— 那时须走契约仪式补进来。）
      - 键为常量名小写，按字典序排列，形如 `key=value`，以 ";" 连接:
          "chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350"
      - 值直接取本文件常量，任何调用方都不得手抄这个字符串。
    """
    params = {
        "chars_per_token_est": CHARS_PER_TOKEN_EST,
        "chunk_min_chars": CHUNK_MIN_CHARS,
        "chunk_target_tokens": CHUNK_TARGET_TOKENS,
    }
    return ";".join(f"{key}={params[key]}" for key in sorted(params))


def validate_gold_chunk_map(
    gold_map: GoldChunkMap,
    items: Sequence[EvalItem],
    corpus_chunk_ids: Sequence[str],
    citation_resolutions: Mapping[tuple[str, int], tuple[str, Sequence[str]]],
) -> None:
    """校验一份 GoldChunkMap 能否被接受为【当前】canonical GoldChunkMap。不满足抛 ContractViolation。

    作用域: CURRENT_CANONICAL_ONLY。
      本函数判断的是"能否在当前 canonical 语料与当前可执行契约下被接受"，
      【不是】通用的历史 artifact 校验器。一份记录旧 corpus sha、旧 builder/config identity
      或旧 contracts_version 的历史映射，可能在它自己的 identity 下是有效的历史产物；
      它在这里被拒绝只表示"不能作为当前 canonical 映射使用"，【不表示】它当年无效。

    输入:
      - items: 生成该映射所用的评测集，【按文件顺序】。本函数会对每条调用 validate_eval_item。
      - corpus_chunk_ids: 语料全部 chunk id，【按 chunks.jsonl 行序】。
      - citation_resolutions: (question_id, citation_index) → (match_level, formal_chunk_ids)，
        覆盖每一道 answer 题的每一条 citation；citation_index 为 0-based。

    本函数负责的是【契约边界】，不负责解析算法本身（片段匹配与最小 cover 的计算属于 resolver）:
      - identity 字段格式: testset_version、两个 SHA-256（完整 64 位小写十六进制）、
        corpus_builder_name（非空、文件名安全）、chunker_config == chunker_config_identity()、
        contracts_version == CONTRACTS_VERSION
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
    for name in ("testset_sha256", "corpus_chunks_sha256"):
        if not _SHA256_HEX_RE.match(getattr(gold_map, name)):
            raise ContractViolation(f"{name} 必须是完整 64 位小写十六进制 SHA-256")
    if not _BUILDER_NAME_RE.match(gold_map.corpus_builder_name):
        raise ContractViolation(
            f"corpus_builder_name 为空或含文件名不安全字符: {gold_map.corpus_builder_name!r}"
        )
    if gold_map.chunker_config != chunker_config_identity():
        raise ContractViolation(
            f"chunker_config {gold_map.chunker_config!r} != chunker_config_identity() "
            f"{chunker_config_identity()!r}"
        )
    if gold_map.contracts_version != CONTRACTS_VERSION:
        raise ContractViolation(
            f"contracts_version {gold_map.contracts_version!r} != {CONTRACTS_VERSION!r}"
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
      - ensure_ascii=False，indent=2，末尾恰一个换行
      - 同一 GoldChunkMap 两次调用逐字节相同；EvalItemResult.gold_chunk_map_sha256
        即对本函数输出（UTF-8 编码）取的 SHA-256
      - 本函数【不做】接受性校验。调用方必须先通过 validate_gold_chunk_map()，
        未被接受的映射不得序列化落盘。
    """
    return json.dumps(asdict(gold_map), ensure_ascii=False, indent=2) + "\n"


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
          - 【必须同时填 relevance 与 match_score】，两者恒 0..1。
            match_score 的归一化必须【查询无关】（见约定 1 与 Hit 的契约）——
            禁止 per-query min-max / softmax，那会让拒答机制静默失效
          - query 为空或全空白 → 返回 []（有意义的"确实没有"，不是异常）
          - 索引损坏、后端不可达 → 抛 RetrievalError，禁止静默返回 []
          - 【禁止】在本层做拒答判断。拒答由 pipeline 依据 MIN_RELEVANCE 决定
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
#    → 属实验实现。3309×1024×4B ≈ 13 MB，穷举扫描不是瓶颈；
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
