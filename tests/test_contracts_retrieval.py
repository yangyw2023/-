"""检索侧契约测试（contracts 0.3.1 版本内追加，S8 protocol apply，DECISIONS 2026-10-01）。

只测 core.contracts 自己负责的东西:
  1. 确定性全序 retrieval_order_key(): (−RAW_SCORE, corpus_ordinal)，tie 只由行序打破。
  2. BM25 前提不变量 bm25_match_score(): 原始分 s ≥ 0（IDF 恒非负），饱和映射查询无关、单调。
  3. RAW_SCORE / RELEVANCE / MATCH_SCORE 三者区分在 Hit 上的落点。
  4. （blocker closure）RetrievalResultRecord / validate_retrieval_records / 记录序列化（T1–T5、T9、T10），
     含一个非 BM25 的合成 RRF 向量证明 relevance ≠ match_score 时架构仍成立；
     canonical_json_bytes / canonical_sha256（T6–T8）。
  5. （final protocol closure）bm25_accumulate(): query token MULTISET + math.fsum（T-B1–T-B6），
     只用合成贡献向量，不实现 BM25；只断言契约可见得分，不断言回调调用次数 / 顺序。

不实现任何检索器: 测试里的分数都是手写数值，不来自 BM25 / 向量计算。
合成 RRF 向量只是手算的 Fraction，不是 hybrid 实现。

运行: python3 -m unittest tests.test_contracts_retrieval -v
"""

from __future__ import annotations

import dataclasses
import inspect
import itertools
import json
import math
import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import (
    Chunk,
    ContractViolation,
    Hit,
    RetrievalResultRecord,
    bm25_accumulate,
    bm25_match_score,
    canonical_json_bytes,
    canonical_sha256,
    retrieval_order_key,
    retrieval_record_json_object,
    serialize_retrieval_record,
    validate_retrieval_records,
)

# 打乱输入顺序的次数与种子；只用于证明输出与输入顺序无关。
SHUFFLE_ROUNDS = 50
SHUFFLE_SEED = 20261001

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# canonical 语料被 gitignore；不在场时只跳过 T1 的真实语料子项（合成子项恒执行）。
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")

# 合成语料: 下标即 0-based 物理行序。
SYNTH_CORPUS_IDS = ["DOC:p1:0", "DOC:p1:1", "DOC:p2:0", "DOC:p2:1", "DOC:p3:0", "DOC:p3:1"]

# BM25 baseline 的 kind（人工裁决；S8 预注册 experiments/M1c_preregistration.md 冻结）。kind 描述"数怎么算出来"，
# 不是字段名: relevance 与 match_score 都由 bm25_match_score(s) 的饱和映射算出，故同为 bm25_saturation。
BM25_KINDS = {"raw_score_kind": "bm25_raw", "relevance_kind": "bm25_saturation",
              "match_score_kind": "bm25_saturation"}
# 合成非 BM25 向量的 kind（只用于测试，不是任何已冻结 retriever 的词表）。
RRF_KINDS = {"raw_score_kind": "rrf_exact", "relevance_kind": "rrf_normalized",
             "match_score_kind": "route_absolute_match"}
# 合成 RRF: 常数与路数只用于手算测试向量。
SYNTH_RRF_K = 60
SYNTH_RRF_ROUTES = 2
SYNTH_RRF_MAX = Fraction(SYNTH_RRF_ROUTES, SYNTH_RRF_K + 1)   # 两路都排第 1 时的 RRF 和


def make_chunk(chunk_id):
    return Chunk(id=chunk_id, text="synthetic chunk text", doc_id="DOC", doc_name="Synthetic", section="1",
                 pdf_page=1)


def bm25_record(ordinal, raw, corpus_ids=SYNTH_CORPUS_IDS, chunk=None):
    """BM25 baseline 口径: relevance = match_score = bm25_match_score(raw)。"""
    score = bm25_match_score(raw)
    return RetrievalResultRecord(chunk=chunk or make_chunk(corpus_ids[ordinal]), corpus_ordinal=ordinal,
                                 raw_score=raw, relevance=score, match_score=score, **BM25_KINDS)


def rrf_raw(*ranks):
    return sum((Fraction(1, SYNTH_RRF_K + r) for r in ranks), Fraction(0))


def rrf_record(ordinal, ranks, match_score):
    raw = rrf_raw(*ranks)
    return RetrievalResultRecord(chunk=make_chunk(SYNTH_CORPUS_IDS[ordinal]), corpus_ordinal=ordinal,
                                 raw_score=raw, relevance=float(raw / SYNTH_RRF_MAX),
                                 match_score=match_score, **RRF_KINDS)


def synthetic_rrf_result():
    """按 RRF 和降序排好的合成结果。match_score = 手写的"各路归一化原始分的 max"，
    刻意与 RRF 排名不单调: 融合第 1 的证据绝对质量低于融合第 2。"""
    return [
        rrf_record(3, (2, 2), 0.41),    # 1/31       ≈ 0.03226
        rrf_record(0, (1, 5), 0.83),    # 126/3965   ≈ 0.03178
        rrf_record(5, (3, 9), 0.12),    # 1/63+1/69  ≈ 0.03037
    ]


def ranked(candidates):
    """candidates: [(ranking_score, corpus_ordinal), ...] → 按契约全序排好的 corpus_ordinal 列表。"""
    return [o for _, o in sorted(candidates, key=lambda c: retrieval_order_key(c[0], c[1]))]


class TestRetrievalTotalOrder(unittest.TestCase):

    def test_non_tie_order_is_score_descending(self):
        cands = [(0.2, 0), (0.9, 5), (0.5, 1), (0.7, 3)]
        self.assertEqual(ranked(cands), [5, 3, 1, 0])

    def test_tie_broken_by_corpus_ordinal_ascending_only(self):
        cands = [(0.5, 9), (0.8, 7), (0.5, 2), (0.5, 4), (0.1, 0)]
        self.assertEqual(ranked(cands), [7, 2, 4, 9, 0])

    def test_tie_break_never_overrides_a_higher_score(self):
        """行序再小也不能越过更高的分数。"""
        self.assertEqual(ranked([(0.4, 0), (0.41, 3000)]), [3000, 0])

    def test_output_independent_of_input_order(self):
        cands = [(Fraction(1, 61) + Fraction(1, 63), i) for i in range(4)] + \
                [(Fraction(2, 61), 10), (Fraction(1, 62), 11), (0.0, 12)]
        expected = ranked(cands)
        rng = random.Random(SHUFFLE_SEED)
        for _ in range(SHUFFLE_ROUNDS):
            shuffled = cands[:]
            rng.shuffle(shuffled)
            self.assertEqual(ranked(shuffled), expected)

    def test_exact_rrf_representation_makes_ties_deterministic(self):
        """浮点累加顺序会抹掉 tie；Fraction 精确表示下对称排名恒相等，交由行序打破。"""
        a, b, c = 0.1, 0.2, 0.3
        self.assertNotEqual(a + b + c, c + b + a)          # 浮点: 同一组数，不同累加顺序 → 不同值
        fa, fb, fc = Fraction(1, 10), Fraction(2, 10), Fraction(3, 10)
        self.assertEqual(fa + fb + fc, fc + fb + fa)
        rrf_x = Fraction(1, 60 + 1) + Fraction(1, 60 + 3)   # 一路第 1、另一路第 3
        rrf_y = Fraction(1, 60 + 3) + Fraction(1, 60 + 1)   # 对称情形
        self.assertEqual(rrf_x, rrf_y)
        self.assertEqual(ranked([(rrf_y, 8), (rrf_x, 5)]), [5, 8])

    def test_mixed_exact_and_float_scores_compare(self):
        self.assertEqual(ranked([(Fraction(1, 2), 1), (0.75, 2), (0, 3)]), [2, 1, 3])

    def test_rejects_non_finite_scores(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ContractViolation):
                retrieval_order_key(bad, 0)

    def test_rejects_non_real_or_bool_scores(self):
        for bad in (True, "0.5", None, complex(1, 0)):
            with self.assertRaises(ContractViolation):
                retrieval_order_key(bad, 0)

    def test_rejects_invalid_ordinals(self):
        for bad in (-1, 1.0, True, "3", None):
            with self.assertRaises(ContractViolation):
                retrieval_order_key(0.5, bad)

    def test_key_reads_only_score_and_ordinal(self):
        """排序键的输入只有分数与行序 —— 结构上不可能读取 gold / 评测信息。"""
        self.assertEqual(list(inspect.signature(retrieval_order_key).parameters),
                         ["ranking_score", "corpus_ordinal"])


class TestBm25NonNegativeInvariant(unittest.TestCase):

    def test_anchor_values(self):
        self.assertEqual(bm25_match_score(0), 0.0)
        self.assertEqual(bm25_match_score(contracts.BM25_SCORE_SATURATION), 0.5)

    def test_range_and_monotone(self):
        raws = [0, 0.001, 0.5, 1, 3, 10, 25, 100, 1e6]
        scores = [bm25_match_score(s) for s in raws]
        for s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)
        self.assertEqual(scores, sorted(scores))

    def test_negative_raw_score_rejected(self):
        """Okapi 原式 IDF 在 n > N/2 时为负 → 可产生 s < 0；契约必须拒绝，而不是输出 0..1 之外的值。"""
        n_docs, doc_freq = 10, 8
        okapi_idf = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        self.assertLess(okapi_idf, 0)
        with self.assertRaises(ContractViolation):
            bm25_match_score(okapi_idf)
        with self.assertRaises(ContractViolation):
            bm25_match_score(-contracts.BM25_SCORE_SATURATION)   # 映射的奇异点

    def test_non_finite_and_bool_rejected(self):
        for bad in (math.nan, math.inf, True, "1.0", None):
            with self.assertRaises(ContractViolation):
                bm25_match_score(bad)

    def test_query_independent(self):
        """同一原始分在不同"查询结果列表"里给出同一个 match_score —— 不是 per-query 归一化。"""
        self.assertEqual(list(inspect.signature(bm25_match_score).parameters), ["raw_score"])
        low_query = [3.0, 2.0, 1.0]
        self.assertLess(max(bm25_match_score(s) for s in low_query), 1.0)   # top-1 不被抬成 1.0
        self.assertEqual(bm25_match_score(3.0), bm25_match_score(3.0))


class TestScoreSemanticDistinction(unittest.TestCase):

    def test_hit_carries_relevance_and_match_score_not_an_ambiguous_score(self):
        names = [f.name for f in dataclasses.fields(Hit)]
        self.assertEqual(names, ["chunk", "relevance", "match_score", "origin"])
        self.assertNotIn("score", names)

    def test_saturated_relevance_preserves_raw_order(self):
        """若 relevance 取 RAW_SCORE 的单调映射，按 RAW_SCORE 全序返回时 relevance 非增。"""
        raws = [(7.5, 4), (2.0, 1), (7.5, 2), (0.3, 9), (12.0, 6)]
        order = ranked(raws)
        by_ordinal = {o: s for s, o in raws}
        relevances = [bm25_match_score(by_ordinal[o]) for o in order]
        self.assertEqual(relevances, sorted(relevances, reverse=True))

    def test_numeric_contract_unchanged(self):
        """除 S9 校准的 MIN_RELEVANCE（0.35 → 0.78，contracts 0.4.1）外，本测试保护的数值契约未变。"""
        self.assertEqual(
            (contracts.MAX_PROMPT_TOKENS, contracts.PROMPT_OVERHEAD_RESERVE_TOKENS,
             contracts.CONTEXT_PACK_MARGIN, contracts.CONTEXT_PACK_BUDGET_TOKENS,
             contracts.CHARS_PER_TOKEN_EST, contracts.TOP_K_CONTEXT, contracts.TOP_K_RETRIEVE,
             contracts.BM25_SCORE_SATURATION, contracts.MIN_RELEVANCE, contracts.TTFT_BUDGET_S),
            (1050, 200, 0.90, 765, 4, 5, 20, 10.0, 0.78, 10.0),
        )

    def test_min_relevance_strict_boundary(self):
        """runtime 判定: score < MIN_RELEVANCE → 拒答；score == MIN_RELEVANCE → 不拒答（S9 校准边界值）。"""
        trap_max, answer_min = 0.7792718520928508, 0.8012534982161421
        self.assertEqual(contracts.MIN_RELEVANCE, 0.78)
        self.assertTrue(trap_max < contracts.MIN_RELEVANCE)
        self.assertFalse(0.78 < contracts.MIN_RELEVANCE)
        self.assertFalse(answer_min < contracts.MIN_RELEVANCE)


class TestT1CorpusOrdinalZeroBased(unittest.TestCase):

    def test_synthetic_first_line_is_zero(self):
        validate_retrieval_records([bm25_record(0, 3.0)], k=1, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_one_based_drift_rejected(self):
        """第一行的 chunk 标成 corpus_ordinal=1（1-based 漂移）→ 与语料行序对不上。"""
        drifted = bm25_record(1, 3.0, chunk=make_chunk(SYNTH_CORPUS_IDS[0]))
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([drifted], k=1, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_out_of_range_and_negative_rejected(self):
        past_end = bm25_record(len(SYNTH_CORPUS_IDS), 3.0, chunk=make_chunk(SYNTH_CORPUS_IDS[-1]))
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([past_end], k=1, corpus_chunk_ids=SYNTH_CORPUS_IDS)
        with self.assertRaises(ContractViolation):
            bm25_record(-1, 3.0, chunk=make_chunk(SYNTH_CORPUS_IDS[0]))

    def test_ordinal_is_not_pdf_page(self):
        """pdf_page 从 1 开始（约定 4），corpus_ordinal 从 0 开始: 二者独立。"""
        record = bm25_record(0, 3.0)
        self.assertEqual(record.chunk.pdf_page, 1)
        self.assertEqual(record.corpus_ordinal, 0)

    @unittest.skipUnless(os.path.isfile(CORPUS_PATH), "canonical corpus 不在场（gitignored）")
    def test_real_canonical_corpus_first_and_last_line(self):
        with open(CORPUS_PATH, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        ids = [row["id"] for row in rows]
        first, last = Chunk(**rows[0]), Chunk(**rows[-1])
        validate_retrieval_records([bm25_record(0, 1.0, ids, chunk=first)], k=1, corpus_chunk_ids=ids)
        validate_retrieval_records([bm25_record(len(ids) - 1, 1.0, ids, chunk=last)], k=1, corpus_chunk_ids=ids)
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([bm25_record(1, 1.0, ids, chunk=first)], k=1, corpus_chunk_ids=ids)


class TestT2RecordSequenceTotalOrder(unittest.TestCase):

    def test_raw_descending_then_ordinal_ascending_accepted(self):
        records = [bm25_record(3, 9.0), bm25_record(1, 7.5), bm25_record(4, 7.5), bm25_record(0, 2.0)]
        validate_retrieval_records(records, k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_tie_in_ordinal_descending_rejected(self):
        records = [bm25_record(4, 7.5), bm25_record(1, 7.5)]
        with self.assertRaises(ContractViolation):
            validate_retrieval_records(records, k=2, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_raw_ascending_rejected(self):
        records = [bm25_record(0, 2.0), bm25_record(1, 7.5)]
        with self.assertRaises(ContractViolation):
            validate_retrieval_records(records, k=2, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_duplicate_ordinal_rejected(self):
        records = [bm25_record(2, 7.5), bm25_record(2, 7.5)]
        with self.assertRaises(ContractViolation):
            validate_retrieval_records(records, k=2, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_more_than_k_rejected_and_empty_accepted(self):
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([bm25_record(0, 3.0), bm25_record(1, 2.0)], k=1,
                                       corpus_chunk_ids=SYNTH_CORPUS_IDS)
        validate_retrieval_records([], k=1, corpus_chunk_ids=SYNTH_CORPUS_IDS)   # [] = 确实没检索到
        for bad_k in (0, True, 2.0):
            with self.assertRaises(ContractViolation):
                validate_retrieval_records([], k=bad_k, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_mixed_kinds_in_one_result_rejected(self):
        other = dataclasses.replace(bm25_record(1, 2.0), relevance_kind="other_kind")
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([bm25_record(0, 3.0), other], k=2, corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_equal_raw_with_unequal_relevance_rejected(self):
        """relevance 必须是 RAW_SCORE 的函数。"""
        a = bm25_record(1, 7.5)
        b = dataclasses.replace(bm25_record(4, 7.5), relevance=0.1)
        with self.assertRaises(ContractViolation):
            validate_retrieval_records([a, b], k=2, corpus_chunk_ids=SYNTH_CORPUS_IDS)


class TestT3Bm25RelevanceEqualsMatchScore(unittest.TestCase):

    def test_values_equal_kinds_are_separate_fields(self):
        record = bm25_record(0, 7.5)
        self.assertEqual(record.relevance, record.match_score)
        # kind 描述计算方式: 两者同由饱和映射算出 → 同为 bm25_saturation（人工裁决），字段仍分开。
        self.assertEqual((record.raw_score_kind, record.relevance_kind, record.match_score_kind),
                         ("bm25_raw", "bm25_saturation", "bm25_saturation"))
        self.assertEqual(record.relevance, bm25_match_score(7.5))
        names = [f.name for f in dataclasses.fields(RetrievalResultRecord)]
        self.assertIn("relevance_kind", names)
        self.assertIn("match_score_kind", names)
        changed = dataclasses.replace(record, relevance_kind="changed_kind")
        self.assertEqual(changed.match_score_kind, record.match_score_kind)
        self.assertEqual(changed.relevance, changed.match_score)

    def test_raw_score_is_not_the_normalized_score(self):
        record = bm25_record(0, 7.5)
        self.assertEqual(record.raw_score, 7.5)
        self.assertNotEqual(record.raw_score, record.relevance)


class TestT4SyntheticNonBm25ScoreSeparation(unittest.TestCase):
    """非 BM25 的合成 RRF 向量: relevance ≠ match_score 时，记录、全序、阈值语义都不依赖二者恒等。"""

    def test_record_represents_different_values(self):
        records = synthetic_rrf_result()
        for record in records:
            self.assertNotEqual(record.relevance, record.match_score)
            self.assertIsInstance(record.raw_score, Fraction)
            self.assertEqual(record.raw_score_kind, "rrf_exact")
            self.assertEqual(record.relevance_kind, "rrf_normalized")
            self.assertEqual(record.match_score_kind, "route_absolute_match")

    def test_order_uses_raw_score_not_match_score(self):
        records = synthetic_rrf_result()
        validate_retrieval_records(records, k=len(records), corpus_chunk_ids=SYNTH_CORPUS_IDS)
        by_raw = sorted(records, key=lambda r: retrieval_order_key(r.raw_score, r.corpus_ordinal))
        by_match = sorted(records, key=lambda r: -r.match_score)
        self.assertEqual(by_raw, records)
        self.assertNotEqual(by_match, records)

    def test_match_score_need_not_be_monotone_along_ranking(self):
        match_scores = [r.match_score for r in synthetic_rrf_result()]
        self.assertNotEqual(match_scores, sorted(match_scores, reverse=True))

    def test_swapping_relevance_and_match_score_is_detected(self):
        """消费方若把 match_score 填进 relevance（互换），全序上的 relevance 不再非增 → 拦下。"""
        swapped = [dataclasses.replace(r, relevance=r.match_score, match_score=r.relevance)
                   for r in synthetic_rrf_result()]
        with self.assertRaises(ContractViolation):
            validate_retrieval_records(swapped, k=len(swapped), corpus_chunk_ids=SYNTH_CORPUS_IDS)

    def test_threshold_facing_field_is_match_score(self):
        """RRF 的 relevance 把融合第 1 抬到接近 1.0；只看 match_score 才能得到"证据都不够好"。"""
        weak = [dataclasses.replace(r, match_score=m)
                for r, m in zip(synthetic_rrf_result(), (0.20, 0.31, 0.12))]
        validate_retrieval_records(weak, k=len(weak), corpus_chunk_ids=SYNTH_CORPUS_IDS)
        self.assertLess(max(r.match_score for r in weak), contracts.MIN_RELEVANCE)
        self.assertGreater(max(r.relevance for r in weak), contracts.MIN_RELEVANCE)

    def test_serialization_keeps_the_different_values(self):
        for record in synthetic_rrf_result():
            obj = json.loads(serialize_retrieval_record(record))
            self.assertEqual(obj["relevance"], record.relevance)
            self.assertEqual(obj["match_score"], record.match_score)
            self.assertNotEqual(obj["relevance"], obj["match_score"])
            self.assertEqual(Fraction(obj["raw_score"]), record.raw_score)
            for name in ("raw_score_kind", "relevance_kind", "match_score_kind"):
                self.assertEqual(obj[name], getattr(record, name))


class TestRecordConstructionContract(unittest.TestCase):

    def test_raw_score_type(self):
        for bad in (3, True, "3.0", None, math.nan, math.inf):
            with self.assertRaises(ContractViolation):
                RetrievalResultRecord(chunk=make_chunk("DOC:p1:0"), corpus_ordinal=0, raw_score=bad,
                                      relevance=0.5, match_score=0.5, **BM25_KINDS)

    def test_normalized_scores_must_be_float_in_unit_interval(self):
        for bad in (1, -0.1, 1.5, math.nan, True, Fraction(1, 2)):
            for name in ("relevance", "match_score"):
                with self.subTest(name=name, value=bad), self.assertRaises(ContractViolation):
                    dataclasses.replace(bm25_record(0, 3.0), **{name: bad})

    def test_kind_format(self):
        for bad in ("", "Bm25", "bm25\n", "1bm25", "bm-25", None):
            for name in ("raw_score_kind", "relevance_kind", "match_score_kind"):
                with self.subTest(name=name, value=bad), self.assertRaises(ContractViolation):
                    dataclasses.replace(bm25_record(0, 3.0), **{name: bad})

    def test_chunk_must_be_chunk_and_chunk_id_is_its_projection(self):
        with self.assertRaises(ContractViolation):
            RetrievalResultRecord(chunk="DOC:p1:0", corpus_ordinal=0, raw_score=3.0,
                                  relevance=0.5, match_score=0.5, **BM25_KINDS)
        self.assertEqual(bm25_record(2, 3.0).chunk_id, SYNTH_CORPUS_IDS[2])


class TestT5T9RecordSerialization(unittest.TestCase):

    def test_t5_all_scores_and_kinds_preserved(self):
        record = bm25_record(3, 7.5)
        obj = json.loads(serialize_retrieval_record(record))
        self.assertEqual(list(obj), list(contracts.RETRIEVAL_RECORD_JSON_FIELDS))
        self.assertEqual(obj, {
            "chunk_id": "DOC:p2:1", "corpus_ordinal": 3,
            "raw_score": 7.5, "raw_score_kind": "bm25_raw",
            "relevance": record.relevance, "relevance_kind": "bm25_saturation",
            "match_score": record.match_score, "match_score_kind": "bm25_saturation",
        })

    def test_t9_exact_bytes_pinned(self):
        """手写期望字节，独立于被测函数。7.5 / (7.5 + 10.0) 的 float repr 为 0.42857142857142855。"""
        self.assertEqual(
            serialize_retrieval_record(bm25_record(0, 7.5)),
            '{"chunk_id":"DOC:p1:0","corpus_ordinal":0,"raw_score":7.5,"raw_score_kind":"bm25_raw",'
            '"relevance":0.42857142857142855,"relevance_kind":"bm25_saturation",'
            '"match_score":0.42857142857142855,"match_score_kind":"bm25_saturation"}',
        )
        self.assertEqual(
            serialize_retrieval_record(rrf_record(3, (2, 2), 0.41)),
            '{"chunk_id":"DOC:p2:1","corpus_ordinal":3,"raw_score":"1/31","raw_score_kind":"rrf_exact",'
            '"relevance":0.9838709677419355,"relevance_kind":"rrf_normalized",'
            '"match_score":0.41,"match_score_kind":"route_absolute_match"}',
        )

    def test_t9_deterministic_and_construction_order_independent(self):
        a = bm25_record(1, 2.25)
        score = bm25_match_score(2.25)
        b = RetrievalResultRecord(match_score_kind="bm25_saturation", match_score=score,
                                  relevance_kind="bm25_saturation", relevance=score,
                                  raw_score_kind="bm25_raw", raw_score=2.25, corpus_ordinal=1,
                                  chunk=make_chunk(SYNTH_CORPUS_IDS[1]))
        self.assertEqual(serialize_retrieval_record(a), serialize_retrieval_record(a))
        self.assertEqual(serialize_retrieval_record(a), serialize_retrieval_record(b))

    def test_t9_embedding_in_a_line_yields_the_same_substring(self):
        records = [bm25_record(0, 7.5), bm25_record(2, 1.25)]
        line = json.dumps({"hits": [retrieval_record_json_object(r) for r in records]},
                          ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        for record in records:
            self.assertIn(serialize_retrieval_record(record), line)

    def test_chunk_text_does_not_enter_serialization(self):
        self.assertNotIn("synthetic chunk text", serialize_retrieval_record(bm25_record(0, 7.5)))


class TestT10NoEvalMetadataInRecord(unittest.TestCase):

    FORBIDDEN = {
        "question_id", "qid", "expected", "type", "language", "citations", "gold", "gold_chunk_ids",
        "is_gold", "gold_rank", "required_elements", "acceptable_elements", "gold_answer", "answer_key",
        "known_distractor", "trap_subtype", "exclude_from_primary_score", "pair_id", "safety_critical",
        "rationale", "latency_s", "ttft_s", "timestamp", "run_at", "built_at", "query",
    }

    def test_record_fields_are_exactly_the_retrieval_fields(self):
        names = [f.name for f in dataclasses.fields(RetrievalResultRecord)]
        self.assertEqual(names, ["chunk", "corpus_ordinal", "raw_score", "raw_score_kind",
                                 "relevance", "relevance_kind", "match_score", "match_score_kind"])
        self.assertFalse(self.FORBIDDEN & set(names))
        self.assertFalse(self.FORBIDDEN & set(contracts.RETRIEVAL_RECORD_JSON_FIELDS))

    def test_eval_fields_cannot_be_attached(self):
        with self.assertRaises(TypeError):
            RetrievalResultRecord(chunk=make_chunk("DOC:p1:0"), corpus_ordinal=0, raw_score=3.0,
                                  relevance=0.5, match_score=0.5, question_id="FL01", **BM25_KINDS)

    def test_producer_and_validator_take_no_eval_input(self):
        self.assertEqual(list(inspect.signature(contracts.Retriever.search_records).parameters),
                         ["self", "query", "k"])
        self.assertEqual(list(inspect.signature(validate_retrieval_records).parameters),
                         ["records", "k", "corpus_chunk_ids"])


class TestT6T8CanonicalDigest(unittest.TestCase):

    PAYLOAD = {"protocol": "example", "k_set": [1, 2, 3, 5, 20], "bm25": {"k1": 1.2, "b": 0.75},
               "note": "多语种", "flag": True, "absent": None}

    def test_exact_bytes_pinned(self):
        """手写期望字节: 键按码点序、无空白、非 ASCII 原样 UTF-8、无末尾换行。"""
        self.assertEqual(
            canonical_json_bytes(self.PAYLOAD),
            '{"absent":null,"bm25":{"b":0.75,"k1":1.2},"flag":true,"k_set":[1,2,3,5,20],'
            '"note":"多语种","protocol":"example"}'.encode("utf-8"),
        )

    def test_t6_same_semantic_payload_same_digest(self):
        rebuilt = json.loads(json.dumps(self.PAYLOAD))
        self.assertEqual(canonical_sha256(self.PAYLOAD), canonical_sha256(rebuilt))
        as_tuple = dict(self.PAYLOAD, k_set=(1, 2, 3, 5, 20))
        self.assertEqual(canonical_sha256(self.PAYLOAD), canonical_sha256(as_tuple))
        self.assertRegex(canonical_sha256(self.PAYLOAD), r"^[0-9a-f]{64}$")

    def test_t7_any_field_change_changes_digest(self):
        base = canonical_sha256(self.PAYLOAD)
        variants = [
            dict(self.PAYLOAD, k_set=[1, 2, 3, 5]),
            dict(self.PAYLOAD, k_set=[2, 1, 3, 5, 20]),          # 数组顺序有语义
            dict(self.PAYLOAD, bm25={"k1": 1.2, "b": 0.7500001}),
            dict(self.PAYLOAD, flag=False),
            dict(self.PAYLOAD, extra=0),
            {k: v for k, v in self.PAYLOAD.items() if k != "absent"},
        ]
        digests = [canonical_sha256(v) for v in variants]
        self.assertNotIn(base, digests)
        self.assertEqual(len(set(digests)), len(digests))

    def test_t8_dict_insertion_order_irrelevant_at_every_depth(self):
        reordered = {key: self.PAYLOAD[key] for key in reversed(list(self.PAYLOAD))}
        reordered["bm25"] = {"b": 0.75, "k1": 1.2}
        self.assertNotEqual(list(reordered), list(self.PAYLOAD))
        self.assertEqual(canonical_json_bytes(reordered), canonical_json_bytes(self.PAYLOAD))

    def test_unsupported_values_rejected(self):
        for bad in ({"x": math.nan}, {"x": math.inf}, {"x": {1, 2}}, {"x": Fraction(1, 3)},
                    {1: "non-str key"}, {"x": b"bytes"}, {"x": object()}):
            with self.subTest(bad=repr(bad)), self.assertRaises(ContractViolation):
                canonical_json_bytes(bad)


# 合成贡献值（不是任何真实 IDF / tf 的结果）。取 2 的幂，使得分可唯一反解出每个 token 的出现次数。
SYNTH_CONTRIBUTIONS = {"alcohol": 1.0, "testing": 0.125}
FL06_LIKE_TOKENS = ["alcohol", "alcohol", "testing"]
# fsum 与"朴素左到右循环"以及 CPython 3.12 内建 sum()（补偿求和）给出不同结果的非负向量:
# 精确和 = 2**53 + 1.0000000000000001 → 正确舍入为 2**53 + 2；另两种都得到 2**53。
FSUM_DISCRIMINATING = {"a": 2.0 ** 53, "b": 0.5, "c": 0.5000000000000001}
FSUM_DISCRIMINATING_EXACT = 2.0 ** 53 + 2


def per_occurrence_reference(tokens, contribution):
    """用户示例 Implementation A: 每次出现各求一次贡献，再 fsum。"""
    return math.fsum([contribution(t) for t in tokens])


def cached_reference(tokens, contribution):
    """用户示例 Implementation B: 每个不同 token 求一次，按出现次数复用，再 fsum。"""
    cache = {}
    for t in tokens:
        if t not in cache:
            cache[t] = contribution(t)
    return math.fsum([cache[t] for t in tokens])


class TestBm25MultisetAccumulation(unittest.TestCase):
    """冻结的是贡献多重集与 fsum（数学语义），不是 term_contribution 的调用次数或顺序。
    本类没有任何断言观察回调轨迹 —— 正确性 oracle 只有契约可见的得分。"""

    def test_tb1_multiplicity_three_visible_in_score(self):
        score = bm25_accumulate(FL06_LIKE_TOKENS, SYNTH_CONTRIBUTIONS.__getitem__)
        self.assertEqual(score, 2 * SYNTH_CONTRIBUTIONS["alcohol"] + 1 * SYNTH_CONTRIBUTIONS["testing"])
        # 2 的幂贡献 → 得分唯一反解出多重性: alcohol ×2、testing ×1，共 3 次出现。
        self.assertEqual((int(score), int((score - int(score)) / SYNTH_CONTRIBUTIONS["testing"])), (2, 1))
        multiset = [SYNTH_CONTRIBUTIONS[t] for t in FL06_LIKE_TOKENS]
        self.assertEqual(len(multiset), 3)
        self.assertEqual(score, math.fsum(multiset))

    def test_tb2_set_semantics_gives_a_different_score(self):
        multiset_score = bm25_accumulate(FL06_LIKE_TOKENS, SYNTH_CONTRIBUTIONS.__getitem__)
        set_score = math.fsum(SYNTH_CONTRIBUTIONS[t] for t in set(FL06_LIKE_TOKENS))
        self.assertEqual((multiset_score, set_score), (2.125, 1.125))
        self.assertNotEqual(multiset_score, set_score)

    def test_tb3_caching_and_per_occurrence_recomputation_agree(self):
        """合法缓存与逐次重算给出相同的契约可见得分（逐比特）。"""
        def recomputing(token):
            return SYNTH_CONTRIBUTIONS[token]

        memo = {}

        def memoized(token):
            if token not in memo:
                memo[token] = SYNTH_CONTRIBUTIONS[token]
            return memo[token]

        for tokens in (FL06_LIKE_TOKENS, ["testing", "alcohol", "testing", "alcohol", "alcohol"], ["alcohol"]):
            with self.subTest(tokens=tokens):
                expected = per_occurrence_reference(tokens, SYNTH_CONTRIBUTIONS.__getitem__)
                self.assertEqual(cached_reference(tokens, SYNTH_CONTRIBUTIONS.__getitem__).hex(), expected.hex())
                self.assertEqual(bm25_accumulate(tokens, recomputing).hex(), expected.hex())
                self.assertEqual(bm25_accumulate(tokens, memoized).hex(), expected.hex())
                self.assertEqual(bm25_accumulate(list(tokens), dict(SYNTH_CONTRIBUTIONS).get).hex(), expected.hex())

    def test_tb4_same_contribution_multiset_same_score(self):
        """得分只取决于贡献多重集: 同一多重集的任意排列、任意贡献表插入顺序 → 逐比特相同。"""
        tokens = ["testing", "alcohol", "testing", "alcohol", "alcohol"]
        expected = bm25_accumulate(tokens, SYNTH_CONTRIBUTIONS.__getitem__).hex()
        backward = {k: SYNTH_CONTRIBUTIONS[k] for k in reversed(list(SYNTH_CONTRIBUTIONS))}
        self.assertNotEqual(list(backward), list(SYNTH_CONTRIBUTIONS))
        for perm in set(itertools.permutations(tokens)):
            self.assertEqual(bm25_accumulate(list(perm), backward.__getitem__).hex(), expected)
        for _ in range(SHUFFLE_ROUNDS):
            self.assertEqual(bm25_accumulate(tokens, SYNTH_CONTRIBUTIONS.__getitem__).hex(), expected)

    def test_tb5_fsum_distinguishable_from_wrong_accumulators(self):
        tokens = ["a", "b", "c"]
        self.assertEqual(bm25_accumulate(tokens, FSUM_DISCRIMINATING.__getitem__), FSUM_DISCRIMINATING_EXACT)
        naive = 0.0
        for t in tokens:
            naive += FSUM_DISCRIMINATING[t]
        builtin = sum(FSUM_DISCRIMINATING[t] for t in tokens)
        self.assertNotEqual(naive, FSUM_DISCRIMINATING_EXACT)
        self.assertNotEqual(builtin, FSUM_DISCRIMINATING_EXACT)

    def test_tb6_deduplicated_or_unordered_representations_rejected(self):
        """不接受会丢失或隐藏多重性的表示 —— 报错，而不是静默按 1 次计。"""
        from collections import Counter
        counts = Counter(FL06_LIKE_TOKENS)
        for bad in (set(FL06_LIKE_TOKENS), frozenset(FL06_LIKE_TOKENS), dict(counts), counts, counts.keys(),
                    (t for t in FL06_LIKE_TOKENS), iter(FL06_LIKE_TOKENS), "alcohol alcohol testing"):
            with self.subTest(type(bad).__name__), self.assertRaises(ContractViolation):
                bm25_accumulate(bad, SYNTH_CONTRIBUTIONS.__getitem__)
        self.assertEqual(bm25_accumulate(tuple(FL06_LIKE_TOKENS), SYNTH_CONTRIBUTIONS.__getitem__), 2.125)

    def test_empty_query_scores_zero(self):
        self.assertEqual(bm25_accumulate([], SYNTH_CONTRIBUTIONS.__getitem__), 0.0)

    def test_invalid_tokens_and_contributions_rejected(self):
        for tokens in ([""], [None], [1]):
            with self.subTest(tokens=tokens), self.assertRaises(ContractViolation):
                bm25_accumulate(tokens, lambda t: 1.0)
        for value in (-0.1, math.nan, math.inf, True, "1.0", None):
            with self.subTest(value=value), self.assertRaises(ContractViolation):
                bm25_accumulate(["alcohol"], lambda t, v=value: v)


if __name__ == "__main__":
    unittest.main()
