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

本文件【绝对不交给 AI 生成或修改】。AI 可以按它实现组件，不能改它。

================================================================================
九条全链路语义约定 —— 每次让 AI 生成代码时必须整段贴入
================================================================================
 1. 分数一律 0.0..1.0，越大越相关。BM25 原始分与向量距离必须在组件内部
    归一化后再出口。禁止某处用距离（越小越好）。
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

→ 见 GoldChunkMap。映射文件按 (评测集版本, 语料哈希, 解析器名) 命名，
  语料一变旧映射自动失效【且能看出来是哪一份失效了】。
[L1] falsified_if: 语料与分块配置在项目全周期内都不再变化
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Literal, Protocol, Sequence

# ==============================================================================
# 版本
# ==============================================================================

# 索引包与运行时的一致性校验依据（见 IndexManifest）。
# 任何影响 Chunk 结构或引用语义的改动都必须递增此版本号。
CONTRACTS_VERSION = "0.2.0-draft"


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
# ⚠️⚠️ 【待拍板】本值与 TTFT_BUDGET_S 互相矛盾，必须在契约会上一起定。
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
# 本文件按 C 预填 1050。若拍板选 B，改为 1500 并同步把 TTFT_BUDGET_S 改为 15.0。
# 无论选哪个，M1c 必须在 ~1050 与 ~1500 两档预算下各报一次 Recall。
#
# ⚠️ 这是【真正的约束】。TOP_K_CONTEXT 只是它的上限保护，不是它的替代品。
MAX_CONTEXT_TOKENS: int = 1050

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
# 按 MAX_CONTEXT_TOKENS=1050 与 CONTEXT_PACK_BUDGET_TOKENS=945 重算:
#   最坏情况 945 ÷ 473 ≈ 2.0 个   中位情况 945 ÷ 292 ≈ 3.2 个
#   → 实际装 2-3 个居多；本值 5 只是上限保护，几乎不会触及
# 好处: chunk 偏小时不白白浪费预算。
# ⚠️ CD01 的 gold 是 3 个 chunk 跨 2 份手册 —— 在 1050 预算下大概率装不全，
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
# 按 MAX_CONTEXT_TOKENS × 本值填充，为 CHARS_PER_TOKEN_EST 的估算误差留空间。
# 最坏情况 945 × 1.15 = 1087 tok → TTFT 10.2s，仍在预算附近。
CONTEXT_PACK_MARGIN: float = 0.90

# 派生常量【唯一定义处】—— 组件一律用它，不要各自去乘那个 0.90。
CONTEXT_PACK_BUDGET_TOKENS: int = int(MAX_CONTEXT_TOKENS * CONTEXT_PACK_MARGIN)

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

# [L1] 生成采样一律关闭。
# 来源: n=31 的规模下，几道题因为采样而翻面就能移动 6 个百分点 ——
#       正好是实用效应闸（Δ≥19pp）的量级。四个实验臂必须完全一致，
#       否则臂间差异里混进了采样噪声，McNemar 检验的前提不成立。
# 与 THINKING_ENABLED 同类: 它是跨组件必须对齐的行为要求，不是某次实验的判断。
# falsified_if: 出现证据表明贪心解码系统性劣于采样，且差异大于采样引入的噪声
# ⚠️ 某些 MoE 后端在 temperature=0 下仍不确定。开工前必须实测:
#    同一 prompt 跑两遍，输出逐字节相同才算通过；不通过则该模型跑 3 次取多数并注明。
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
MIN_RELEVANCE: float = 0.35

# [L2] owner_experiment: 回填脚本首跑报告（按 L1+L2 命中率与误命中情况重定）
#
# 语义【不是】"丢弃短于此长度的片段"。见 split_quote_fragments 的契约。
# 短片段仍参与 L1/L2 的"全片段命中"检验，只是【不能单独构成 L3 部分命中】。
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
#   L1   全片段同块      L2   全片段邻页      L3   部分片段命中
#   L4   页存在但无片段命中 → 【引文抄写有出入】的强信号
#   FAIL (doc_id, pdf_page) 在语料中根本没有 chunk → 【页缺失】
# ⚠️ L4 与 FAIL 必须分开。合并会让"引文抄错"伪装成"页缺失"。
MatchLevel = Literal["L1", "L2", "L3", "L4", "FAIL"]

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
        """token 估算。用于上下文预算填充，不是精确计数。

        契约: 恒 ≥1。当前 CHUNK_MIN_CHARS=120 保证不会出现 0，
        但类型本身没有 runtime 校验，返回 0 会让 pack_context 无限装块。
        """
        return max(1, len(self.text) // CHARS_PER_TOKEN_EST)


@dataclass(frozen=True)
class Hit:
    """一条检索结果。

    契约:
      - relevance 恒为 0.0..1.0，越大越相关，且【已在组件内部归一化】。
        BM25 原始分与向量距离都不满足此约定，出口前必须转换。
      - origin 仅用于调试归因，不参与打分
    """
    chunk: Chunk
    relevance: float
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


@dataclass(frozen=True)
class GoldChunkMap:
    """citations → chunk id 的映射。【派生产物，可再生，不进评测集】。

    契约:
      - 由 scripts/resolve_gold_chunks.py 从 EvalItem.citations 机械生成
      - 是测量检索层 Recall 的唯一依据
      - mapping 只包含 expected=="answer" 的题。
        拒答题不出现在 mapping 里 —— 它们没有 gold chunk，
        混进 Recall 分母会让 Recall 失去意义。
      - 文件名由 filename() 生成，含 (评测集版本, 语料哈希, 解析器名)。
        语料或分块一变，旧映射自动失效【且能看出来是哪一份失效了】。

      ⚠️ 本类【不含 match_levels】。
         实测: 39 题中有 6 道带多条 citation（CD01 3 条，FL06/FL07/CN03/CD02/CD03 各 2 条）。
         一道题的多条 citation 完全可能是 L1/L2/L4 混合，压成一个 question-level
         "最低级别"会丢掉【到底是哪一条需要人工复核】—— 而那正是唯一需要人看的信息。
         匹配级别的权威记录是 `.report.csv`（每条 citation 一行）。
         一个数据结构不要同时干"提供映射"和"承载审计"两件事。

    再生方式（这是它可以不进 Git 的前提）:
        python3 scripts/resolve_gold_chunks.py --chunks ... --testset ...
    """
    testset_version: str          # "v5.3"
    testset_sha256: str
    corpus_chunks_sha256: str
    parser_name: str              # "kaiva_pdf_v1"
    chunker_config: str           # "target350_overlap60_min120"
    built_at: str                 # ISO 8601
    mapping: dict[str, list[str]]           # question_id -> [chunk_id, ...]

    def filename(self) -> str:
        """映射文件的标准文件名（不含目录）。

        形如: map__ts-v5.3__corpus-a1b2c3d4__parser-kaiva_pdf_v1.json
        """
        return (
            f"map__ts-{self.testset_version}"
            f"__corpus-{self.corpus_chunks_sha256[:8]}"
            f"__parser-{self.parser_name}.json"
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
    max_ctx_tokens: int
    pack_budget_tokens: int              # = MAX_CONTEXT_TOKENS × CONTEXT_PACK_MARGIN
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
      - 返回 False 【不代表】该片段被忽略。它仍参与 L1/L2 的"全片段命中"检验。
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
      - 至少返回一个 hit（若首个 hit 本身就超预算，仍返回它并由上游截断，
        因为返回空会被误读为"没检索到"，违反约定第 2 条）
      - 被预算挡在外面的 hit 数量应由调用方记入 failure_tag="context_truncation"
      - 默认预算是 CONTEXT_PACK_BUDGET_TOKENS（已含安全余量），不是
        MAX_CONTEXT_TOKENS。传参时也不要自己去乘 CONTEXT_PACK_MARGIN。

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
        t = hit.chunk.est_tokens()
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
          - 返回 0..k 个 Hit，按 relevance 降序；relevance 恒 0..1 已归一化
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
# 本版（0.2.0-draft）相对 0.1.0 的改动 —— 契约会上逐条确认
# ==============================================================================
# 【硬错误，必须改】
#  1. MAX_CONTEXT_TOKENS 1500 → 1050。原值与 TTFT_BUDGET_S=10 互相矛盾
#     （1500 tok 实测插值 TTFT=14.9s）。本文件按方案 C 预填，待拍板。
#  2. GoldChunkMap.match_levels 删除。实测 6 道题带多条 citation，
#     question-level 压缩会丢掉"哪一条要复核"。审计权威改为 report.csv。
#  3. pack_context docstring 自相矛盾（标题说"按预算填充"、细则说"立即停止"、
#     代码是 break）。锁定为 prefix 语义并重写。
#
# 【失效的注释，必须改】
#  4. CHARS_PER_TOKEN_EST 从 L3 升 L2。"误差不影响结论"在它开始驱动
#     pack_context 之后失效。新增 CONTEXT_PACK_MARGIN=0.90 与派生的
#     CONTEXT_PACK_BUDGET_TOKENS。
#  5. MIN_RELEVANCE 的优化方向反转: 取保守偏低值，判据是"尽量不误拒 31 道
#     可答题"，而非"最大化陷阱拒答率"。两边代价不对称（前者进主指标，后者不进）。
#
# 【补漏】
#  6. 新增 GENERATION_TEMPERATURE = 0.0 [L1]。原文件从未规定采样，
#     n=31 下采样噪声足以移动 6pp。
#  7. EvalItemResult 新增 n_chunks_in_context / actual_context_tokens /
#     pack_budget_tokens / temperature；gold_chunk_hit 改 bool|None
#     （A/C 臂无检索层，理由同 citations_correct）。
#  8. IndexManifest 新增 embeddings_sha256，并写明【向量与 chunk 的行序对应】
#     是最关键契约 —— 向量错位时检索看起来正常但全是乱的，且不报错。
#  9. Chunk.est_tokens 加 max(1, ...) 下界，防 pack_context 无限装块。
# 10. 头部级别说明新增 [M] 方法约束类别。
#
# 【待你拍板（本文件已预填推荐值，不同意就改）】--全部暂时同意
#  A. MAX_CONTEXT_TOKENS / TTFT_BUDGET_S 取 1050/10（推荐）还是 1500/15
#  B. CONTEXT_PACK_MARGIN 取 0.90 是否够
#  C. GENERATION_TEMPERATURE 进契约（而非留在预注册）是否合适
#  D. EvalItem 是否确认纳入本文件（纳入 = 评测集格式变更也要走契约仪式）
#  E. QUOTE_FRAGMENT_MIN_CHARS_FOR_SOLE_MATCH = 20 是否接受