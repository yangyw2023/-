"""Unweighted RRF hybrid（components/retrievers/hybrid.py）的承重语义测试（prereg §16，H1–H10）。

只用合成的两路 RetrievalResultRecord；不读语料 / 评测集 / GoldChunkMap，不调用 BM25 / vector / Ollama。

运行: python3 -m unittest tests.test_hybrid_retriever -v
"""

from __future__ import annotations

import ast
import inspect
import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import (Chunk, ContractViolation, RetrievalResultRecord, bm25_match_score,
                            serialize_retrieval_record, validate_retrieval_records)
from components.retrievers import hybrid
from components.retrievers.hybrid import fuse

HYBRID_SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "components", "retrievers", "hybrid.py")
CORPUS_SIZE = 60
SHUFFLES = 20
SHUFFLE_SEED = 7

CORPUS_IDS = [f"D:p{i // 3 + 1}:{i % 3}" for i in range(CORPUS_SIZE)]
CHUNKS = [Chunk(id=cid, text=f"text {cid}", doc_id="D", doc_name="Synthetic", section="1", pdf_page=i // 3 + 1)
          for i, cid in enumerate(CORPUS_IDS)]


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def bm25_route(ordinals, raws=None):
    """BM25 记录（kind 冻结），raw 默认严格递减。"""
    raws = raws or [float(100 - i) for i in range(len(ordinals))]
    return [RetrievalResultRecord(chunk=CHUNKS[o], corpus_ordinal=o, raw_score=r, raw_score_kind="bm25_raw",
                                  relevance=bm25_match_score(r), relevance_kind="bm25_saturation",
                                  match_score=bm25_match_score(r), match_score_kind="bm25_saturation")
            for o, r in zip(ordinals, raws)]


def vector_route(ordinals, raws=None):
    """vector 记录（kind 冻结），cosine 默认严格递减。"""
    raws = raws or [0.9 - 0.01 * i for i in range(len(ordinals))]
    return [RetrievalResultRecord(chunk=CHUNKS[o], corpus_ordinal=o, raw_score=r, raw_score_kind="cosine",
                                  relevance=(r + 1.0) / 2.0, relevance_kind="cosine_affine_01",
                                  match_score=(r + 1.0) / 2.0, match_score_kind="cosine_affine_01")
            for o, r in zip(ordinals, raws)]


def by_ordinal(results):
    return {r.record.corpus_ordinal: r for r in results}


def dump(results):
    return "\n".join(serialize_retrieval_record(r.record) + repr((r.bm25, r.vector)) for r in results)


class TestHybridFusion(unittest.TestCase):

    def test_t01_single_route_contribution(self):
        out = by_ordinal(fuse(bm25_route([5, 6]), vector_route([7])))
        self.assertEqual(out[6].record.raw_score, Fraction(1, 62))       # 只在 BM25 rank 2
        self.assertEqual(out[7].record.raw_score, Fraction(1, 61))       # 只在 vector rank 1

    def test_t02_two_route_contributions_add(self):
        out = by_ordinal(fuse(bm25_route([5, 6, 7]), vector_route([7, 5])))
        self.assertEqual(out[5].record.raw_score, Fraction(1, 61) + Fraction(1, 62))
        self.assertEqual(out[7].record.raw_score, Fraction(1, 63) + Fraction(1, 61))

    def test_t03_t04_rank_one_based_and_k60(self):
        self.assertEqual((hybrid.RRF_K, hybrid.rrf_contribution(1), hybrid.rrf_contribution(20)),
                         (60, Fraction(1, 61), Fraction(1, 80)))
        for bad in (0, -1, True, 1.0):
            with self.subTest(rank=bad), self.assertRaises(ContractViolation):
                hybrid.rrf_contribution(bad)
        out = fuse(bm25_route([9]), [])
        self.assertEqual((out[0].bm25.rank, out[0].record.raw_score), (1, Fraction(1, 61)))

    def test_t05_exact_fraction_arithmetic(self):
        # 6 个两路贡献和: 浮点累加可能制造或抹掉 tie，Fraction 必须精确
        out = fuse(bm25_route(list(range(20))), vector_route(list(range(19, -1, -1))))
        for r in out:
            self.assertIs(type(r.record.raw_score), Fraction)
            self.assertEqual(r.record.raw_score, Fraction(1, 60 + r.bm25.rank) + Fraction(1, 60 + r.vector.rank))
        self.assertEqual(len({r.record.raw_score for r in out}), 10)    # rank i 与 21 − i 两两精确相等

    def test_t06_raw_serialization_p_over_q(self):
        out = fuse(bm25_route([5]), vector_route([5]))
        obj = contracts.retrieval_record_json_object(out[0].record)
        self.assertEqual(obj["raw_score"], "2/61")
        self.assertEqual((obj["raw_score_kind"], obj["relevance_kind"], obj["match_score_kind"]),
                         ("rrf_k60_2route", "rrf_normalized_2route_k60", "max_present_route_match_score"))

    def test_t07_theoretical_max_relevance_one(self):
        self.assertEqual(hybrid.RRF_MAX_RAW, Fraction(2, 61))
        out = fuse(bm25_route([5]), vector_route([5]))
        self.assertEqual(out[0].record.relevance, 1.0)

    def test_t08_single_route_relevance_below_one(self):
        out = by_ordinal(fuse(bm25_route([5]), vector_route([6])))
        self.assertEqual(out[5].record.relevance, 0.5)
        self.assertEqual(out[6].record.relevance, 0.5)
        self.assertLess(out[5].record.relevance, 1.0)
        out20 = fuse(bm25_route(list(range(20))), [])
        self.assertEqual(out20[-1].record.relevance, float(Fraction(61, 160)))

    def test_t09_match_score_max_of_present_routes(self):
        b = bm25_route([5, 6], raws=[50.0, 2.0])
        v = vector_route([6, 5], raws=[0.9, 0.1])
        out = by_ordinal(fuse(b, v))
        self.assertEqual(out[5].record.match_score, max(b[0].match_score, v[1].match_score))
        self.assertEqual(out[6].record.match_score, max(b[1].match_score, v[0].match_score))
        self.assertNotEqual(out[5].record.match_score, out[5].record.relevance)

    def test_t10_missing_route_not_rescored(self):
        b = bm25_route([5], raws=[0.5])                                   # BM25 match 很低
        out = by_ordinal(fuse(b, vector_route([6])))
        self.assertIsNone(out[5].vector)
        self.assertEqual(out[5].record.match_score, b[0].match_score)    # 不因缺失 vector 而补算
        self.assertEqual(list(inspect.signature(fuse).parameters), ["bm25_records", "vector_records", "k"])

    def test_t11_short_route_no_padding(self):
        out = fuse([], vector_route(list(range(20))))                     # 如 ML01: BM25 0 条
        self.assertEqual([r.record.corpus_ordinal for r in out], list(range(20)))
        self.assertTrue(all(r.bm25 is None for r in out))
        out3 = fuse(bm25_route([30, 31, 32]), vector_route([1, 2]))
        self.assertEqual(len(out3), 5)
        self.assertEqual(sum(r.bm25 is not None for r in out3), 3)
        self.assertEqual(fuse([], []), [])

    def test_t12_candidate_union(self):
        b, v = [3, 4, 5, 6], [5, 6, 7, 8, 9]
        out = fuse(bm25_route(b), vector_route(v), k=50)
        self.assertEqual({r.record.corpus_ordinal for r in out}, set(b) | set(v))
        deep = fuse(bm25_route(list(range(25))), [], k=50)                  # 深度 20：第 21 条起不参与
        self.assertEqual(len(deep), hybrid.BM25_FUSION_DEPTH)

    def test_t13_t14_order_rrf_desc_then_ordinal_asc(self):
        # 9 只在 BM25 rank 1，2 只在 vector rank 1 → 精确 tie；先出现的是 9，但 2 的 corpus_ordinal 更小
        out = fuse(bm25_route([9, 40]), vector_route([2, 40]))
        self.assertEqual([r.record.corpus_ordinal for r in out], [40, 2, 9])
        raws = [r.record.raw_score for r in out]
        self.assertEqual(raws, sorted(raws, reverse=True))
        self.assertEqual(out[1].record.raw_score, out[2].record.raw_score)
        validate_retrieval_records([r.record for r in out], k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=CORPUS_IDS)

    def test_t15_final_top_20(self):
        out = fuse(bm25_route(list(range(20))), vector_route(list(range(20, 40))))
        self.assertEqual(len(out), contracts.TOP_K_RETRIEVE)
        validate_retrieval_records([r.record for r in out], k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=CORPUS_IDS)
        for bad in (0, -3, True, 2.0):
            with self.subTest(k=bad), self.assertRaises(ContractViolation):
                fuse([], [], k=bad)

    def test_t16_route_diagnostics_preserved(self):
        b = bm25_route([5, 6, 7])
        v = vector_route([7, 8])
        out = by_ordinal(fuse(b, v))
        self.assertEqual(out[7].bm25, hybrid.RouteEvidence(rank=3, raw_score=b[2].raw_score, match_score=b[2].match_score))
        self.assertEqual(out[7].vector, hybrid.RouteEvidence(rank=1, raw_score=v[0].raw_score, match_score=v[0].match_score))
        self.assertIsNone(out[8].bm25)
        self.assertIsNone(out[5].vector)

    def test_t17_candidate_order_does_not_change_output(self):
        results = fuse(bm25_route(list(range(0, 40, 2))), vector_route(list(range(39, -1, -2))), k=50)
        expected = dump(hybrid.rank_candidates(results, contracts.TOP_K_RETRIEVE))
        rng = random.Random(SHUFFLE_SEED)
        for _ in range(SHUFFLES):
            shuffled = list(results)
            rng.shuffle(shuffled)
            self.assertEqual(dump(hybrid.rank_candidates(shuffled, contracts.TOP_K_RETRIEVE)), expected)
        self.assertEqual(dump(fuse(tuple(bm25_route([1, 2])), tuple(vector_route([2, 3])))),
                         dump(fuse(bm25_route([1, 2]), vector_route([2, 3]))))

    def test_input_validation(self):
        with self.assertRaises(ContractViolation):
            fuse(vector_route([1]), bm25_route([2]))                        # 两路放反
        with self.assertRaises(ContractViolation):
            fuse(list(reversed(bm25_route([1, 2]))), [])                   # 不是该路全序
        conflict = vector_route([1])[0]
        moved = RetrievalResultRecord(chunk=CHUNKS[1], corpus_ordinal=2, raw_score=conflict.raw_score,
                                      raw_score_kind="cosine", relevance=conflict.relevance, relevance_kind="cosine_affine_01",
                                      match_score=conflict.match_score, match_score_kind="cosine_affine_01")
        with self.assertRaises(ContractViolation):
            fuse(bm25_route([1]), [moved])                                  # 同一 chunk 两路 ordinal 不同

    def test_t18_t19_no_eval_gold_or_retriever_dependency(self):
        tree = ast.parse(read_text(HYBRID_SOURCE))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                   {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"__future__", "dataclasses", "fractions", "typing", "core.contracts"})
        names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for word in ("gold", "testset", "question", "expected", "citation", "recall", "open",
                     "search", "search_records", "embed", "embed_texts", "ollama", "urlopen", "bm25retriever", "vectorretriever"):
            self.assertFalse([x for x in names if word == x or x.startswith(word + "_")], word)
        # D3 / D15: fixed-k baseline 不读取 packing 相关常量
        packing = {"max_prompt_tokens", "prompt_overhead_reserve_tokens", "context_pack_margin",
                   "context_pack_budget_tokens", "chars_per_token_est", "top_k_context", "pack_context"}
        imported_names = {a.name.lower() for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertEqual(packing & (names | imported_names), set())


if __name__ == "__main__":
    unittest.main()
