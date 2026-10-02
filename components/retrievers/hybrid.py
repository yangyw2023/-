"""Unweighted RRF hybrid（S8 / M1c hybrid baseline）：在两路已排好序的检索结果之上做纯确定性融合。

严格执行 experiments/M1c_preregistration.md §16（人工裁决 H1–H10，protocol commit a0a9241）。
只依赖 core.contracts 与标准库；不读语料、不读评测集 / GoldChunkMap、不调用 BM25 / vector 检索器或 Ollama。
两路输入由调用方给出（formal baseline = 已冻结的 component top-20 artifact；生产组装属于 core/pipeline.py）。

协议落点:
  融合族 / 常数        unweighted RRF，RRF_K = 60，route rank 1-based；两路权重 1 : 1（实现中不存在权重参数）
  逐路深度             BM25_FUSION_DEPTH = VECTOR_FUSION_DEPTH = 20；不足则用实际返回的全部，不 padding
  candidate            两路 top-depth 记录的并集
  raw score            Σ Fraction(1, RRF_K + rank)，kind "rrf_k60_2route"（精确有理数，不用 float 累加）
  relevance            float(raw / RRF_MAX_RAW)，RRF_MAX_RAW = 2/61，kind "rrf_normalized_2route_k60"
  match_score          出现的各路已保存 match_score 的 max，不补算缺失路，kind "max_present_route_match_score"
  全序                 contracts.retrieval_order_key(raw, corpus_ordinal)，取前 k
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from core.contracts import TOP_K_RETRIEVE, ContractViolation, RetrievalResultRecord, retrieval_order_key

# ==============================================================================
# 冻结协议（prereg §16.2）
# ==============================================================================

RRF_K: int = 60
BM25_FUSION_DEPTH: int = 20
VECTOR_FUSION_DEPTH: int = 20
ROUTES: tuple[str, ...] = ("bm25", "vector")
# 每一路都排第 1 时的 raw RRF（理论最大值）= len(ROUTES) / (RRF_K + 1) = 2/61；relevance = raw / RRF_MAX_RAW ∈ (0, 1]。
RRF_MAX_RAW: Fraction = Fraction(len(ROUTES), RRF_K + 1)
# 两路冻结记录的 (raw_score_kind, relevance_kind, match_score_kind)（prereg §5 / §15.2）；用于拒绝放错位置或口径不符的输入。
BM25_ROUTE_KINDS: tuple[str, str, str] = ("bm25_raw", "bm25_saturation", "bm25_saturation")
VECTOR_ROUTE_KINDS: tuple[str, str, str] = ("cosine", "cosine_affine_01", "cosine_affine_01")
RAW_SCORE_KIND: str = "rrf_k60_2route"
RELEVANCE_KIND: str = "rrf_normalized_2route_k60"
MATCH_SCORE_KIND: str = "max_present_route_match_score"
HIT_ORIGIN = "hybrid"


@dataclass(frozen=True)
class RouteEvidence:
    """某一路对一个融合候选的 provenance：该路中的 1-based rank，以及该路记录里保存的 raw_score / match_score 原值（不重算）。"""
    rank: int
    raw_score: float
    match_score: float


@dataclass(frozen=True)
class HybridResult:
    """一条融合结果：contracts 的 RetrievalResultRecord + 两路 provenance（该路未出现 → None）。

    实验审计载体（prereg §16.3 route_diagnostics 的来源）；不扩张、不替代 Hit。
    """
    record: RetrievalResultRecord
    bm25: RouteEvidence | None
    vector: RouteEvidence | None


def rrf_contribution(route_rank: int) -> Fraction:
    """一路对一个 chunk 的 RRF 贡献 = Fraction(1, RRF_K + route_rank)。route_rank 是 1-based 的 int（≥ 1），否则 ContractViolation。"""
    if isinstance(route_rank, bool) or not isinstance(route_rank, int) or route_rank < 1:
        raise ContractViolation(f"route_rank 必须是 ≥ 1 的 int（1-based），得到 {route_rank!r}")
    return Fraction(1, RRF_K + route_rank)


def _route_evidence(name: str, records: Sequence[RetrievalResultRecord], kinds: tuple[str, str, str],
                    depth: int) -> dict[int, tuple[RetrievalResultRecord, RouteEvidence]]:
    """校验一路输入并取前 depth 条，返回 {corpus_ordinal: (记录, provenance)}。"""
    if type(records) not in (list, tuple):
        raise ContractViolation(f"{name} 输入必须是 list 或 tuple")
    for position, record in enumerate(records):
        if not isinstance(record, RetrievalResultRecord):
            raise ContractViolation(f"{name}[{position}] 不是 RetrievalResultRecord")
        if (record.raw_score_kind, record.relevance_kind, record.match_score_kind) != kinds:
            raise ContractViolation(f"{name}[{position}] 的 kind 不是冻结的 {kinds}")
    if len({r.chunk_id for r in records}) != len(records) or len({r.corpus_ordinal for r in records}) != len(records):
        raise ContractViolation(f"{name} 输入含重复 chunk_id 或 corpus_ordinal")
    for prev, cur in zip(records, records[1:]):
        if not (retrieval_order_key(prev.raw_score, prev.corpus_ordinal)
                < retrieval_order_key(cur.raw_score, cur.corpus_ordinal)):
            raise ContractViolation(f"{name} 输入不是该路的全序（{prev.chunk_id} → {cur.chunk_id}）")
    return {record.corpus_ordinal: (record, RouteEvidence(rank=rank, raw_score=record.raw_score,
                                                          match_score=record.match_score))
            for rank, record in enumerate(records[:depth], start=1)}


def rank_candidates(candidates: Sequence[HybridResult], k: int) -> list[HybridResult]:
    """按 contracts 全序（raw RRF 降序，精确相等时 corpus_ordinal 升序）取前 k 个。与 candidates 的给出顺序无关。

    调用方保证 candidates 的 corpus_ordinal 互不相同（fuse 由 dict 键保证）。
    """
    return sorted(candidates, key=lambda c: retrieval_order_key(c.record.raw_score, c.record.corpus_ordinal))[:k]


def fuse(bm25_records: Sequence[RetrievalResultRecord], vector_records: Sequence[RetrievalResultRecord],
         k: int = TOP_K_RETRIEVE) -> list[HybridResult]:
    """两路 unweighted RRF 融合，返回按全序排列的前 min(k, |candidate 并集|) 条。

    输入假设（违反抛 ContractViolation）:
      - bm25_records / vector_records: 该路一次检索的完整返回（list / tuple，可为空），按该路自己的全序排列
        （retrieval_order_key 严格递增），chunk_id 与 corpus_ordinal 各自不重复；kind 分别等于 BM25_ROUTE_KINDS / VECTOR_ROUTE_KINDS。
        rank = 记录在该路序列中的 1-based 位置；只取前 BM25_FUSION_DEPTH / VECTOR_FUSION_DEPTH 条，少于深度时用全部（不 padding）。
      - 同一 chunk 出现在两路时，两路的 corpus_ordinal 与 Chunk 必须相同；不同 chunk 不得共用 corpus_ordinal。
      - k: int（不含 bool），≥ 1。
    返回: HybridResult 列表；record 的 raw_score 是 Fraction，relevance / match_score 见模块说明。两路都为空 → []。
    不做的事: 不读语料（corpus_ordinal 与语料的对应由调用方用 validate_retrieval_records 校验）、不补算缺失路的分数、
    不读任何评测 / gold 信息、不做拒答判断。
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ContractViolation(f"k 必须是 ≥ 1 的 int，得到 {k!r}")
    bm25 = _route_evidence("bm25", bm25_records, BM25_ROUTE_KINDS, BM25_FUSION_DEPTH)
    vector = _route_evidence("vector", vector_records, VECTOR_ROUTE_KINDS, VECTOR_FUSION_DEPTH)
    ordinal_of: dict[str, int] = {}
    for route in (bm25, vector):
        for ordinal, (record, _) in route.items():
            if ordinal_of.setdefault(record.chunk_id, ordinal) != ordinal:
                raise ContractViolation(f"{record.chunk_id} 在两路的 corpus_ordinal 不同")
    for ordinal in bm25.keys() & vector.keys():
        if bm25[ordinal][0].chunk != vector[ordinal][0].chunk:
            raise ContractViolation(f"corpus_ordinal {ordinal} 在两路对应不同的 Chunk")
    candidates = []
    for ordinal in bm25.keys() | vector.keys():
        present = [route[ordinal] for route in (bm25, vector) if ordinal in route]
        raw = sum((rrf_contribution(evidence.rank) for _, evidence in present), Fraction(0))
        record = RetrievalResultRecord(
            chunk=present[0][0].chunk, corpus_ordinal=ordinal,
            raw_score=raw, raw_score_kind=RAW_SCORE_KIND,
            relevance=float(raw / RRF_MAX_RAW), relevance_kind=RELEVANCE_KIND,
            match_score=max(evidence.match_score for _, evidence in present), match_score_kind=MATCH_SCORE_KIND,
        )
        candidates.append(HybridResult(record=record,
                                       bm25=bm25[ordinal][1] if ordinal in bm25 else None,
                                       vector=vector[ordinal][1] if ordinal in vector else None))
    return rank_candidates(candidates, k)
