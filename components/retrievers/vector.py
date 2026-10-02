"""Exact vector 单路检索器（S8 / M1c vector baseline）。

严格执行 experiments/M1c_preregistration.md §15（人工裁决 D-V1–D-V10，protocol commit 5443495）。
只依赖 core.contracts 与标准库；不读评测集、不读 GoldChunkMap、不计算评测量。语料向量由调用方传入
（实验 artifact 的加载与校验在 experiments/m1c_s8_vector/，不在本组件）。

协议落点:
  模型 / endpoint / 请求体   EMBED_MODEL / EMBED_ENDPOINT_PATH / build_embed_request()（truncate = false，无 options → 默认 Metal）
  prefix                     QUERY_PREFIX = DOCUMENT_PREFIX = ""
  raw score                  exact_cosine(): fsum 点积 / (‖a‖‖b‖)，不以点积代替 cosine
  relevance / match_score    _relevance() / _match_score() = (cos + 1) / 2，kind = cosine / cosine_affine_01
  返回                       不按正负过滤，返回 min(k, N) 条；全序 = contracts.retrieval_order_key
  空 query                   返回 []，不调用 endpoint
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Sequence

from core.contracts import (
    TOP_K_RETRIEVE,
    Chunk,
    ContractViolation,
    Hit,
    RetrievalError,
    RetrievalResultRecord,
    retrieval_order_key,
    validate_retrieval_records,
)

# ==============================================================================
# 冻结协议（prereg §15.1 / §15.2）
# ==============================================================================

EMBED_MODEL: str = "bge-m3:latest"
EMBED_DIMENSION: int = 1024
OLLAMA_BASE_URL: str = "http://localhost:11434"
EMBED_ENDPOINT_PATH: str = "/api/embed"
EMBED_TIMEOUT_S: float = 300.0
QUERY_PREFIX: str = ""
DOCUMENT_PREFIX: str = ""
# match_score / relevance = (cos + COSINE_AFFINE_OFFSET) / COSINE_AFFINE_SCALE，把 [−1, 1] 仿射到 [0, 1]。
COSINE_AFFINE_OFFSET: float = 1.0
COSINE_AFFINE_SCALE: float = 2.0
RAW_SCORE_KIND: str = "cosine"
AFFINE_KIND: str = "cosine_affine_01"
HIT_ORIGIN = "vector"


def build_embed_request(inputs: list[str]) -> dict:
    """/api/embed 的冻结请求体: model、input、truncate = false。不带 options —— 执行路径取 Ollama 默认（开发 Mac = Metal）。"""
    return {"model": EMBED_MODEL, "input": inputs, "truncate": False}


def _validated_embeddings(payload: object, n_texts: int) -> list[list[float]]:
    """响应必须含 n_texts 个 EMBED_DIMENSION 维、全部有限的 float 向量，否则 RetrievalError（不静默降级）。"""
    vectors = payload.get("embeddings") if isinstance(payload, dict) else None
    if not isinstance(vectors, list) or len(vectors) != n_texts:
        raise RetrievalError(f"/api/embed 返回 {type(vectors).__name__} 而非 {n_texts} 个向量")
    for index, vector in enumerate(vectors):
        if not isinstance(vector, list) or len(vector) != EMBED_DIMENSION:
            raise RetrievalError(f"第 {index} 个向量维度不是 {EMBED_DIMENSION}")
        if not all(isinstance(x, float) and math.isfinite(x) for x in vector):
            raise RetrievalError(f"第 {index} 个向量含非 float 或非有限值")
    return vectors


def embed_texts(texts: list[str]) -> list[list[float]]:
    """按冻结协议调用 POST /api/embed，返回与输入同序的向量（float64，即 JSON 解析原值）。

    调用方负责 prefix（本协议为 ""）。连接失败、HTTP 错误（含 truncate = false 时超长输入）、响应格式不符 → RetrievalError。
    """
    if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
        raise ContractViolation("embed_texts 需要非空的 str 列表")
    body = json.dumps(build_embed_request(texts)).encode("utf-8")
    request = urllib.request.Request(OLLAMA_BASE_URL + EMBED_ENDPOINT_PATH, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=EMBED_TIMEOUT_S) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RetrievalError(f"/api/embed 调用失败: {exc}") from exc
    return _validated_embeddings(payload, len(texts))


def vector_norm(vector: Sequence[float]) -> float:
    """sqrt(math.fsum(x · x))。"""
    return math.sqrt(math.fsum(x * x for x in vector))


def exact_cosine(a: Sequence[float], b: Sequence[float], norm_a: float, norm_b: float) -> float:
    """raw_score = math.fsum(a_i · b_i) / (norm_a · norm_b)（prereg §15.2）。norm 由 vector_norm 给出。"""
    return math.fsum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


def _affine_01(raw_score: float) -> float:
    return (raw_score + COSINE_AFFINE_OFFSET) / COSINE_AFFINE_SCALE


# relevance 与 match_score 在单路 vector 中数值相同（prereg §15.2），但是两个字段：各自独立求值。
def _relevance(raw_score: float) -> float:
    """ranking-oriented normalized score = (cos + 1) / 2。"""
    return _affine_01(raw_score)


def _match_score(raw_score: float) -> float:
    """query-independent absolute-match score = (cos + 1) / 2（与 contracts Hit 中 vector 的 match_score 定义一致）。"""
    return _affine_01(raw_score)


class VectorRetriever:
    """在固定语料与其冻结 embedding 上做精确暴力 cosine 检索（实现 core.contracts.Retriever）。

    构造输入:
      - chunks: canonical corpus/chunks.jsonl 的全部 Chunk，按物理行序（chunks[i] = 第 i 行，0-based）。
      - corpus_vectors: 与 chunks 一一对应的 EMBED_DIMENSION 维 float 向量（按冻结协议对 DOCUMENT_PREFIX + Chunk.text 生成）。
    构造时（违反抛 ContractViolation）: list / tuple；chunks 非空、元素为 Chunk、id 不重复；向量数 = chunk 数；
    每个向量维度正确、全部有限 float、范数非零（零向量的 cosine 无定义）。
    索引构造后不变；检索不改状态。query 向量由 embed_texts 按冻结协议生成，本类不接受任何 embedder / scorer 注入。
    """

    def __init__(self, chunks: Sequence[Chunk], corpus_vectors: Sequence[Sequence[float]]) -> None:
        if type(chunks) not in (list, tuple) or type(corpus_vectors) not in (list, tuple):
            raise ContractViolation("chunks 与 corpus_vectors 必须是 list 或 tuple")
        if not chunks:
            raise ContractViolation("语料为空")
        if len(chunks) != len(corpus_vectors):
            raise ContractViolation(f"chunk 数 {len(chunks)} != 向量数 {len(corpus_vectors)}")
        seen: set[str] = set()
        norms: list[float] = []
        for position, (chunk, vector) in enumerate(zip(chunks, corpus_vectors)):
            if not isinstance(chunk, Chunk):
                raise ContractViolation(f"chunks[{position}] 不是 Chunk")
            if chunk.id in seen:
                raise ContractViolation(f"chunk id 重复: {chunk.id!r}")
            seen.add(chunk.id)
            if len(vector) != EMBED_DIMENSION or not all(type(x) is float and math.isfinite(x) for x in vector):
                raise ContractViolation(f"corpus_vectors[{position}] 维度不是 {EMBED_DIMENSION} 或含非有限 float")
            norm = vector_norm(vector)
            if norm == 0.0:
                raise ContractViolation(f"corpus_vectors[{position}] 是零向量，cosine 无定义")
            norms.append(norm)
        self._chunks: tuple[Chunk, ...] = tuple(chunks)
        self._chunk_ids: tuple[str, ...] = tuple(c.id for c in self._chunks)
        self._vectors: tuple[tuple[float, ...], ...] = tuple(tuple(v) for v in corpus_vectors)
        self._norms: tuple[float, ...] = tuple(norms)

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    def search_records(self, query: str, k: int = TOP_K_RETRIEVE) -> list[RetrievalResultRecord]:
        """检索并返回评测 / 审计记录（core.contracts.Retriever.search_records）。

        - query: 原样字符串；非 str → ContractViolation；空或全空白 → []，不调用 endpoint。
        - k: int（不含 bool），≥ 1，否则 ContractViolation。返回 min(k, N) 条，不按 cosine 正负过滤。
        - query 向量 = embed_texts([QUERY_PREFIX + query])[0]；零范数 → RetrievalError。
        - 记录: raw_score = 精确 cosine（kind "cosine"），relevance = match_score = (cos + 1) / 2（kind "cosine_affine_01"）；
          全序 (−raw, corpus_ordinal)；返回前 validate_retrieval_records 自检。浮点舍入若使 match_score 越出 [0, 1]，记录校验报错。
        """
        if not isinstance(query, str):
            raise ContractViolation(f"query 必须是 str，得到 {type(query).__name__}")
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ContractViolation(f"k 必须是 ≥ 1 的 int，得到 {k!r}")
        if not query.strip():
            return []
        (query_vector,) = embed_texts([QUERY_PREFIX + query])
        query_norm = vector_norm(query_vector)
        if query_norm == 0.0:
            raise RetrievalError("query 向量为零向量，cosine 无定义")
        scored = [(exact_cosine(query_vector, vector, query_norm, norm), ordinal)
                  for ordinal, (vector, norm) in enumerate(zip(self._vectors, self._norms))]
        scored.sort(key=lambda item: retrieval_order_key(item[0], item[1]))
        records = [
            RetrievalResultRecord(
                chunk=self._chunks[ordinal], corpus_ordinal=ordinal,
                raw_score=raw, raw_score_kind=RAW_SCORE_KIND,
                relevance=_relevance(raw), relevance_kind=AFFINE_KIND,
                match_score=_match_score(raw), match_score_kind=AFFINE_KIND,
            )
            for raw, ordinal in scored[:k]
        ]
        validate_retrieval_records(records, k=k, corpus_chunk_ids=self._chunk_ids)
        return records

    def search(self, query: str, k: int = TOP_K_RETRIEVE) -> list[Hit]:
        """core.contracts.Retriever.search: search_records 的 Hit 投影。"""
        return [Hit(chunk=r.chunk, relevance=r.relevance, match_score=r.match_score, origin=HIT_ORIGIN)
                for r in self.search_records(query, k)]
