"""BM25 单路检索器（S8 / M1c baseline）。

严格执行冻结预注册 experiments/M1c_preregistration.md §2–§6、§9.2（protocol commits b88d534 / 693f959）。
本模块只实现检索；不读评测集、不读 GoldChunkMap、不计算任何评测量。依赖只有 core.contracts 与标准库。

协议落点（prereg → 本文件）:
  indexed text            §3 / §6.1   indexed_text()
  analyzer                §6.1        analyze()
  IDF / tf / |d| / avgdl  §6.1        BM25Retriever（构造时统计；idf()）
  k1 / b                  §6.1        BM25_K1 / BM25_B
  term contribution 公式  §6.2        BM25Retriever._term_contribution()
  MULTISET + math.fsum    §6.3        analyze() 的 token 列表原样交给 contracts.bm25_accumulate()
  只返回 raw > 0          §6.1        search_records() 的过滤
  全序                    §4          contracts.retrieval_order_key()
  score kinds / 饱和映射  §5          RAW_SCORE_KIND / SATURATION_KIND / _relevance() / _match_score()
  record / 接口           §5 / §9.2   search_records()；search() 是同一次排序的 Hit 投影

production contribution 路径是封闭的: term contribution 只由本类内部按冻结公式计算，构造函数与检索方法都不接受
任何 scorer / contribution 回调，因此 bm25_accumulate 的"纯函数"前置条件由实现结构保证，而不是运行时检查。
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from typing import Sequence

from core.contracts import (
    TOP_K_RETRIEVE,
    Chunk,
    ContractViolation,
    Hit,
    RetrievalError,
    RetrievalResultRecord,
    bm25_accumulate,
    bm25_match_score,
    retrieval_order_key,
    validate_retrieval_records,
)

# ==============================================================================
# 预注册冻结参数（prereg §6.1；preregistered baseline default，不得在 v5.3 上调参）
# ==============================================================================

BM25_K1: float = 1.2
BM25_B: float = 0.75
# IDF = ln(1 + (N − n + IDF_SMOOTHING) / (n + IDF_SMOOTHING))；公式常数，不是可调参数。
IDF_SMOOTHING: float = 0.5
# analyzer: Unicode 规范化形式与保留的 General_Category 大类（L = Letter，N = Number，M = Mark / Combining_Mark）。
UNICODE_NORMAL_FORM: str = "NFC"
TOKEN_CATEGORY_CLASSES: frozenset[str] = frozenset({"L", "N", "M"})
# zero-score policy: 只返回 raw BM25 score 严格大于此值的 chunk（prereg §6.1"只返回 raw BM25 score > 0"）。
RAW_SCORE_EXCLUSIVE_FLOOR: float = 0.0
# score kinds（prereg §5，人工裁决）。kind 描述数值怎么算出来，不是字段名。
RAW_SCORE_KIND: str = "bm25_raw"
SATURATION_KIND: str = "bm25_saturation"
HIT_ORIGIN = "bm25"

# 本检索器的 retrieval_config payload（prereg §10.2）。canonical_sha256(本值) 必须等于预注册 EXPECTED 字面量
# 3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e —— 由测试核对；runner 写入 run identity 时也必须核对。
BM25_RETRIEVAL_CONFIG_PAYLOAD: dict = {
    "digest_name": "retrieval_config", "payload_version": 1,
    "retrieval_variant": HIT_ORIGIN,
    "indexed_text": "Chunk.text",
    "indexed_documents": "all_chunks_in_canonical_corpus",
    "analyzer": {
        "steps": ["unicodedata.normalize:NFC", "str.casefold", "maximal_runs_of_unicode_general_category_L_N_M"],
        "stopwords": False, "stemming": False, "digits_kept": True, "cjk_segmentation": False,
        "applied_to": "query_and_document",
    },
    "term_frequency": "count_of_token_in_document_token_sequence",
    "document_length": "token_count",
    "avgdl": "mean_document_length_over_all_indexed_documents",
    "idf": "ln(1 + (N - n + 0.5) / (n + 0.5))",
    "term_contribution": "idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))",
    "k1": BM25_K1, "b": BM25_B,
    "query_term_multiplicity": "MULTISET_mathematical_occurrence_multiplicity",
    "numeric_evaluation": {
        "accumulation": "math.fsum",
        "accumulation_input": "contribution_multiset_one_element_per_analyzer_query_token_occurrence",
        "executable": "core.contracts.bm25_accumulate",
        "callback_invocation_count_is_contract": False,
        "float": "IEEE-754_binary64",
        "term_contribution_float_evaluation": "implementation_defined",
        "reproducibility_scope": "same_code_commit_and_same_declared_runtime_identity",
        "cross_platform_bit_identity_claimed": False,
    },
    "return_filter": "raw_score > 0",
    "k": TOP_K_RETRIEVE,
    "raw_score_kind": RAW_SCORE_KIND,
    "relevance": "core.contracts.bm25_match_score(raw_score)", "relevance_kind": SATURATION_KIND,
    "match_score": "core.contracts.bm25_match_score(raw_score)", "match_score_kind": SATURATION_KIND,
    "persistent_index_artifact": False,
}


# ==============================================================================
# indexed text 与 analyzer（query 与 document 共用，prereg §6.1）
# ==============================================================================

def indexed_text(chunk: Chunk) -> str:
    """BM25 索引的文本 = Chunk.text，原样（prereg §3）。section / doc / page / citation header 与任何元数据都不进入。"""
    return chunk.text


def analyze(text: str) -> list[str]:
    """prereg §6.1 analyzer: NFC → casefold → General_Category 属于 L / N / M 的码点的最长连续串为 token。

    返回 token 序列（物理顺序、保留重复）。不去停用词、不做词干、不做语言相关处理；CJK 不分词（连续汉字 / 假名为一个 token）。
    query 与 document 必须都经过本函数。text 不是 str → ContractViolation；无 token → []。
    结果依赖运行时 unicodedata.unidata_version（属 run identity）。
    """
    if not isinstance(text, str):
        raise ContractViolation(f"analyzer 输入必须是 str，得到 {type(text).__name__}")
    normalized = unicodedata.normalize(UNICODE_NORMAL_FORM, text).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for ch in normalized:
        if unicodedata.category(ch)[0] in TOKEN_CATEGORY_CLASSES:
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


# relevance 与 match_score 在 BM25 baseline 上数值相同（prereg §5），但是两个字段、两种语义:
# 各自独立求值，任何一方的定义将来改变都不会牵动另一方。
def _relevance(raw_score: float) -> float:
    """ranking-oriented normalized score。BM25 baseline: bm25_match_score(s)（prereg §5）。"""
    return bm25_match_score(raw_score)


def _match_score(raw_score: float) -> float:
    """query-independent absolute-match score（MIN_RELEVANCE 面向的字段）。BM25 baseline: bm25_match_score(s)（prereg §5）。"""
    return bm25_match_score(raw_score)


# ==============================================================================
# 检索器
# ==============================================================================

class BM25Retriever:
    """在一份固定语料上执行冻结 BM25 协议的检索器（实现 core.contracts.Retriever）。

    构造输入:
      - chunks: canonical corpus/chunks.jsonl 的全部 Chunk，【按物理行序】—— chunks[i] 必须是第 i 行（0-based）。
        corpus_ordinal 直接取这个位置；调用方负责行序与语料字节身份（runner 以 corpus sha 核对）。
    构造时（违反抛 ContractViolation）:
      - chunks 必须是 list / tuple 且元素都是 Chunk；chunk id 不得重复。
      - 语料为空或全部 chunk 都没有 token → avgdl 为 0 或无定义，BM25 公式无法求值 → 拒绝构造。
        这是公式定义域的前置条件，不是对协议的扩展（冻结语料 N = 3409，不会触发）。
    索引在构造后不再改变；检索不修改任何状态，同一输入恒得同一输出。不持久化（prereg §6.1）。
    """

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        if type(chunks) not in (list, tuple):
            raise ContractViolation(f"chunks 必须是 list 或 tuple（按 corpus 物理行序），得到 {type(chunks).__name__}")
        seen: set[str] = set()
        for position, chunk in enumerate(chunks):
            if not isinstance(chunk, Chunk):
                raise ContractViolation(f"chunks[{position}] 不是 Chunk，得到 {type(chunk).__name__}")
            if chunk.id in seen:
                raise ContractViolation(f"chunk id 重复: {chunk.id!r}")
            seen.add(chunk.id)
        self._chunks: tuple[Chunk, ...] = tuple(chunks)
        self._chunk_ids: tuple[str, ...] = tuple(chunk.id for chunk in self._chunks)
        term_frequencies: list[dict[str, int]] = []
        document_frequency: Counter[str] = Counter()
        lengths: list[int] = []
        for chunk in self._chunks:
            tokens = analyze(indexed_text(chunk))
            tf = dict(Counter(tokens))
            term_frequencies.append(tf)
            document_frequency.update(tf.keys())
            lengths.append(len(tokens))
        total_length = sum(lengths)
        if total_length == 0:      # 含 N = 0（空语料）: 先于除法拦下
            raise ContractViolation(f"语料为空或没有任何 token（N = {len(lengths)}）: avgdl 为 0 或无定义，BM25 长度归一化无法求值")
        self._tf: tuple[dict[str, int], ...] = tuple(term_frequencies)
        self._df: dict[str, int] = dict(document_frequency)
        self._lengths: tuple[int, ...] = tuple(lengths)
        self._n: int = len(self._chunks)
        self._avgdl: float = total_length / self._n

    # ---- 只读统计（审计 / 测试用）--------------------------------------------

    @property
    def corpus_size(self) -> int:
        """N = 已索引 chunk 数。"""
        return self._n

    @property
    def average_document_length(self) -> float:
        """avgdl = 全部 N 个 chunk 的 token 数均值。"""
        return self._avgdl

    def document_length(self, corpus_ordinal: int) -> int:
        """|d| = 该 chunk 的 analyzer token 数。ordinal 越界抛 IndexError。"""
        return self._lengths[corpus_ordinal]

    def term_frequency(self, token: str, corpus_ordinal: int) -> int:
        """tf = token 在该 chunk token 序列中的出现次数（不出现为 0）。"""
        return self._tf[corpus_ordinal].get(token, 0)

    def document_frequency(self, token: str) -> int:
        """n = 含该 token 的 chunk 数（不在词表中为 0）。"""
        return self._df.get(token, 0)

    def idf(self, token: str) -> float:
        """IDF = ln(1 + (N − n + 0.5) / (n + 0.5))，prereg 只对 1 ≤ n ≤ N 定义；n = 0 → ContractViolation。"""
        n = self.document_frequency(token)
        if n < 1:
            raise ContractViolation(f"token {token!r} 不在语料中（n = 0），IDF 无定义")
        return math.log(1.0 + (self._n - n + IDF_SMOOTHING) / (n + IDF_SMOOTHING))

    # ---- 打分 ----------------------------------------------------------------

    def _term_contribution(self, token: str, corpus_ordinal: int) -> float:
        """单个 query token 对 chunk 的贡献（prereg §6.2）。tf = 0 → 0.0（式中因子 tf 为 0）。纯函数。"""
        tf = self._tf[corpus_ordinal].get(token, 0)
        if tf == 0:
            return 0.0
        if self._df.get(token, 0) < 1:
            raise RetrievalError(f"索引不一致: {token!r} 在 chunk {corpus_ordinal} 中 tf = {tf} 但 df = 0")
        length_norm = 1 - BM25_B + BM25_B * self._lengths[corpus_ordinal] / self._avgdl
        return self.idf(token) * tf * (BM25_K1 + 1) / (tf + BM25_K1 * length_norm)

    def _raw_score(self, query_tokens: list[str], corpus_ordinal: int) -> float:
        """s(q, d) = math.fsum(贡献多重集)，经冻结 helper bm25_accumulate（MULTISET，prereg §6.3）。"""
        return bm25_accumulate(query_tokens, lambda token: self._term_contribution(token, corpus_ordinal))

    # ---- Retriever 接口 ------------------------------------------------------

    def search_records(self, query: str, k: int = TOP_K_RETRIEVE) -> list[RetrievalResultRecord]:
        """检索并返回评测 / 审计记录（core.contracts.Retriever.search_records）。

        - query: 原样字符串（prereg §2 只允许 EvalItem.question 原文；本方法不接收任何其他评测字段）。
          非 str → ContractViolation。经 analyze() 得到 token 序列，重复 token 保留（MULTISET）。
        - k: int（不含 bool），≥ 1，否则 ContractViolation。k 大于正分 chunk 数时返回全部正分 chunk。
        - 对全部 N 个 chunk 求 raw score，只保留 raw > 0（zero-score policy）；按 (−raw, corpus_ordinal) 全序取前 k。
          query 无 token 或无 token 命中 → []（确实没检索到，不是异常）。
        - 每条记录 raw_score = s，relevance = match_score = bm25_match_score(s)，kind = bm25_raw / bm25_saturation ×2；
          rank = 在返回序列中的位置（1-based）；corpus_ordinal = 构造输入中的位置（0-based）。
        - 返回前用 validate_retrieval_records 自检；不通过抛 ContractViolation。
        """
        if not isinstance(query, str):
            raise ContractViolation(f"query 必须是 str，得到 {type(query).__name__}")
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ContractViolation(f"k 必须是 ≥ 1 的 int，得到 {k!r}")
        query_tokens = analyze(query)
        scored: list[tuple[float, int]] = []
        for corpus_ordinal in range(self._n):
            raw = self._raw_score(query_tokens, corpus_ordinal)
            if raw > RAW_SCORE_EXCLUSIVE_FLOOR:
                scored.append((raw, corpus_ordinal))
        scored.sort(key=lambda item: retrieval_order_key(item[0], item[1]))
        records = [
            RetrievalResultRecord(
                chunk=self._chunks[corpus_ordinal], corpus_ordinal=corpus_ordinal,
                raw_score=raw, raw_score_kind=RAW_SCORE_KIND,
                relevance=_relevance(raw), relevance_kind=SATURATION_KIND,
                match_score=_match_score(raw), match_score_kind=SATURATION_KIND,
            )
            for raw, corpus_ordinal in scored[:k]
        ]
        validate_retrieval_records(records, k=k, corpus_chunk_ids=self._chunk_ids)
        return records

    def search(self, query: str, k: int = TOP_K_RETRIEVE) -> list[Hit]:
        """core.contracts.Retriever.search: search_records 的 Hit 投影（同一次排序，逐项同 chunk / relevance / match_score）。"""
        return [Hit(chunk=record.chunk, relevance=record.relevance, match_score=record.match_score, origin=HIT_ORIGIN)
                for record in self.search_records(query, k)]
