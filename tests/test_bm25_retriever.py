"""BM25 检索器（components/retrievers/bm25.py）的实现正确性测试。S8 / M1c implementation round。

只用合成语料与合成 query 证明"实现忠实于冻结预注册"（experiments/M1c_preregistration.md §2–§6、§9.2）；
不读评测集、不读 GoldChunkMap、不产生任何检索实验结果。

结构:
  - 合成语料 FIXTURE_DOCS（8 个 chunk）: 重复词、常见 / 罕见词、长短文档、文本完全相同的两块（精确 tie，
    且 chunk_id 字典序与行序相反）、零分文档、Unicode（NFD、casefold ß）、多语种（天城文、汉字 + 假名、他加禄语）。
  - 独立参考实现 ref_*: 另写的切词算法（替换为空格后 split）、自算统计、逐次求贡献后直接 math.fsum，
    不调用 bm25 模块的任何函数，也不经 contracts.bm25_accumulate。
  - 冻结期望（EXPECTED_*）: 排序与 raw score 的 float.hex 字面量，由参考实现在实现前算出后写死；
    文档长度、tf、IDF、k1 / b 的若干值由手算公式给出。
  - T1–T30 与 TRACEABILITY 矩阵（T30 机械核对 prereg 片段 → 代码符号 → 测试名）。

运行: python3 -m unittest tests.test_bm25_retriever -v
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import math
import os
import subprocess
import sys
import unicodedata
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import (
    Chunk,
    ContractViolation,
    RetrievalResultRecord,
    canonical_sha256,
    serialize_retrieval_record,
    validate_retrieval_records,
)
from components.retrievers import bm25
from components.retrievers.bm25 import BM25Retriever, analyze, indexed_text

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BM25_SOURCE_PATH = os.path.join(REPO_ROOT, "components", "retrievers", "bm25.py")
PREREG_PATH = os.path.join(REPO_ROOT, "experiments", "M1c_preregistration.md")

# 冻结值（prereg §10.2 EXPECTED 字面量；不由被测代码自算）。
EXPECTED_RETRIEVAL_CONFIG_DIGEST = "3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e"
# 手算参考值所用的冻结参数（prereg §6.1），与被测模块常量分开写，防止共同漂移。
PREREG_K1 = 1.2
PREREG_B = 0.75
PREREG_SATURATION = 10.0
# 重复检索 / 独立进程的次数与 hash 种子（只用于证明确定性）。
SAME_PROCESS_REPEATS = 10
INDEPENDENT_PROCESS_HASH_SEEDS = ("0", "1", "4242")
LARGE_K = 100

# ---- 合成语料（下标 = corpus_ordinal）-------------------------------------------
FIXTURE_DOCS = (
    ("D:p1:0", "Fire pump test. Fire pump pressure must be checked weekly."),
    ("D:p1:1", "Emergency generator test procedure: start the generator and record the load."),
    ("D:p2:0", "Alcohol and drug testing: alcohol testing is random."),
    ("D:p2:1", "The master shall inspect the lifeboat and the davit."),
    ("C:p9:0", "Alcohol and drug testing: alcohol testing is random."),     # 与 2 文本相同；id 字典序更小、行序更大
    ("D:p3:0", "Ångström naïve café — CAFÉ 東京港の検査 नमस्ते kumusta po 2024 Straße"),   # cafe+U+0301 = NFD
    ("D:p3:1", "Lorem ipsum dolor sit amet."),
    ("D:p4:0", "Pump maintenance log. Pump maintenance log. Pump maintenance log. Pump maintenance log. "
               "The pump was overhauled after the test."),
)
# 手数的 token 数（analyzer 定义下）: 10 / 11 / 8 / 9 / 8 / 10 / 5 / 19，合计 80 → avgdl = 10.0。
EXPECTED_LENGTHS = (10, 11, 8, 9, 8, 10, 5, 19)
EXPECTED_AVGDL = 80 / 8

# 冻结期望排序（corpus_ordinal）与 raw score（float.hex），由独立参考实现在写实现前算出。
EXPECTED_RANKINGS = {
    "alcohol alcohol testing": ([2, 4], ["0x1.665278d946f2fp+2", "0x1.665278d946f2fp+2"]),
    "alcohol testing": ([2, 4], ["0x1.ddc34bcc5e994p+1", "0x1.ddc34bcc5e994p+1"]),
    "fire pump": ([0, 7], ["0x1.0e65a28eec683p+2", "0x1.01487c43e068ep+1"]),
    "pump": ([7, 0], ["0x1.01487c43e068ep+1", "0x1.c2e382bc12e0ap+0"]),
    "pump test": ([0, 7, 1], ["0x1.5a55df932fb60p+1", "0x1.59a45f505ba37p+1", "0x1.d08f440305192p-1"]),
    "the": ([3, 1, 7], ["0x1.84436a5c37a5dp+0", "0x1.435b291d56076p+0", "0x1.094c11c5b6f10p+0"]),
    "café": ([5], ["0x1.3b5983bfcf601p+1"]),
    "CAFÉ": ([5], ["0x1.3b5983bfcf601p+1"]),
    "STRASSE": ([5], ["0x1.cab0bfa2a2002p+0"]),
    "नमस्ते": ([5], ["0x1.cab0bfa2a2002p+0"]),
    "東京港": ([], []),
    "東京港の検査": ([5], ["0x1.cab0bfa2a2002p+0"]),
    "kumusta po": ([5], ["0x1.cab0bfa2a2002p+1"]),
    "2024": ([5], ["0x1.cab0bfa2a2002p+0"]),
    "zzzzabsent": ([], []),
    "pump zzzzabsent": ([7, 0], ["0x1.01487c43e068ep+1", "0x1.c2e382bc12e0ap+0"]),
    "": ([], []),
    "   ": ([], []),
    "!!! ---": ([], []),
}
# 朴素左到右累加与 math.fsum 在这一组上给出不同的 raw（doc 2）；由参考实现搜索得到。
FSUM_DISCRIMINATING_QUERY = "alcohol dolor pump load inspect overhauled log generator start random drug naïve"
FSUM_DISCRIMINATING_ORDINAL = 2
FSUM_DISCRIMINATING_RAW = 4.656414162508481
NAIVE_SUM_RAW = 4.65641416250848


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def identifier_parts(name: str) -> list[str]:
    """标识符拆成小写组成部分（下划线与驼峰边界），用于整词比对而不是子串比对。"""
    parts = []
    for piece in name.split("_"):
        current = ""
        for ch in piece:
            if ch.isupper() and current and not current[-1].isupper():
                parts.append(current.lower())
                current = ch
            else:
                current += ch
        if current:
            parts.append(current.lower())
    return parts


def fixture_chunks() -> list[Chunk]:
    return [Chunk(id=cid, text=text, doc_id=cid.split(":")[0], doc_name="Synthetic", section="1",
                  pdf_page=int(cid.split(":p")[1].split(":")[0])) for cid, text in FIXTURE_DOCS]


def fixture_ids() -> list[str]:
    return [cid for cid, _ in FIXTURE_DOCS]


# ---- 独立参考实现（不调用被测模块）-------------------------------------------------

def ref_tokens(text):
    """另写的 analyzer: NFC → casefold → 非 L/N/M 码点替换为空格 → split()。"""
    normalized = unicodedata.normalize("NFC", text).casefold()
    return "".join(ch if unicodedata.category(ch)[0] in "LNM" else " " for ch in normalized).split()


def ref_contributions(texts, query):
    """每个文档: 对 query 的每一次 token 出现求一次贡献（逐次求值，无缓存）。"""
    docs = [ref_tokens(t) for t in texts]
    n_docs = len(docs)
    avgdl = sum(len(d) for d in docs) / n_docs
    out = []
    for d in docs:
        contribs = []
        for t in ref_tokens(query):
            tf = d.count(t)
            if tf == 0:
                contribs.append(0.0)
                continue
            n = sum(1 for x in docs if t in x)
            idf = math.log(1.0 + (n_docs - n + 0.5) / (n + 0.5))
            contribs.append(idf * tf * (PREREG_K1 + 1) / (tf + PREREG_K1 * (1 - PREREG_B + PREREG_B * len(d) / avgdl)))
        out.append(contribs)
    return out


def ref_raw_scores(texts, query):
    return [math.fsum(c) for c in ref_contributions(texts, query)]


def ref_ranking(texts, query, k):
    scored = [(s, i) for i, s in enumerate(ref_raw_scores(texts, query)) if s > 0]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:k]


def serialized_fixture_results() -> str:
    """独立进程确定性用: 新建索引，按固定顺序跑全部固定 query，输出规范序列化的记录。"""
    retriever = BM25Retriever(fixture_chunks())
    lines = []
    for query in EXPECTED_RANKINGS:
        lines.append(json.dumps(query, ensure_ascii=False))
        lines.extend(serialize_retrieval_record(r) for r in retriever.search_records(query, k=contracts.TOP_K_RETRIEVE))
    return "\n".join(lines) + "\n"


class _Fixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.chunks = fixture_chunks()
        cls.texts = [t for _, t in FIXTURE_DOCS]
        cls.r = BM25Retriever(cls.chunks)

    def raws(self, query, k=contracts.TOP_K_RETRIEVE):
        return [(rec.corpus_ordinal, rec.raw_score) for rec in self.r.search_records(query, k)]


# ==============================================================================
# T1–T2 indexed text / analyzer
# ==============================================================================

class TestIndexedTextAndAnalyzer(_Fixture):

    def test_t01_indexed_text_is_exactly_chunk_text(self):
        chunk = Chunk(id="X:p1:0", text="Body only.", doc_id="X", doc_name="Lifeboat Manual", section="9.9",
                      section_title="Lifeboat Davit", pdf_page=7, printed_page="Page 1 of 3", issued_by="Master")
        self.assertEqual(indexed_text(chunk), "Body only.")
        r = BM25Retriever([chunk, Chunk(id="X:p1:1", text="other words", doc_id="X", doc_name="n", section="1")])
        for metadata_word in ("lifeboat", "davit", "manual", "master", "page", "7", "9"):
            self.assertEqual(r.search_records(metadata_word), [], metadata_word)

    def test_t02_analyzer_exact_tokens(self):
        cases = {
            "Fire pump test. Fire": ["fire", "pump", "test", "fire"],
            "pump pump": ["pump", "pump"],
            "a-b_c, d/e": ["a", "b", "c", "d", "e"],          # "_" 是 Pc，不属于 L/N/M
            "No.2024-10 x²": ["no", "2024", "10", "x²"],      # 数字保留；² 是 No
            "  \t\n ": [],
            "": [],
            "!!! --- …": [],
            "a😀b": ["a", "b"],                                # So 分隔
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(analyze(text), expected)

    def test_t02_analyzer_rejects_non_str(self):
        for bad in (None, b"bytes", 3):
            with self.subTest(bad=bad), self.assertRaises(ContractViolation):
                analyze(bad)

    def test_analyzer_matches_independent_reference_on_fixture(self):
        for text in self.texts + list(EXPECTED_RANKINGS):
            self.assertEqual(analyze(text), ref_tokens(text), text)


# ==============================================================================
# T3–T8 统计量与参数
# ==============================================================================

class TestStatistics(_Fixture):

    def test_t03_idf_formula(self):
        r = BM25Retriever([Chunk(id=f"I:p1:{i}", text=f"alpha w{i}", doc_id="I", doc_name="n", section="1")
                           for i in range(4)])
        # N = 4: n = 4 → ln(1 + 0.5/4.5) = ln(10/9)；n = 1 → ln(1 + 3.5/1.5) = ln(10/3)。
        self.assertTrue(math.isclose(r.idf("alpha"), math.log(10 / 9), rel_tol=1e-15))
        self.assertTrue(math.isclose(r.idf("w0"), math.log(10 / 3), rel_tol=1e-15))
        self.assertGreater(r.idf("alpha"), 0.0)                         # n = N 时仍为正（非负 IDF）
        with self.assertRaises(ContractViolation):
            r.idf("absent")                                            # n = 0: prereg 未定义

    def test_t04_term_frequency(self):
        self.assertEqual(self.r.term_frequency("pump", 7), 5)
        self.assertEqual(self.r.term_frequency("alcohol", 2), 2)
        self.assertEqual(self.r.term_frequency("café", 5), 2)           # NFD 与 NFC/大写合并
        self.assertEqual(self.r.term_frequency("pump", 6), 0)
        self.assertEqual(self.r.document_frequency("pump"), 2)
        self.assertEqual(self.r.document_frequency("the"), 3)
        self.assertEqual(self.r.document_frequency("absent"), 0)

    def test_t05_document_length(self):
        self.assertEqual(tuple(self.r.document_length(i) for i in range(len(FIXTURE_DOCS))), EXPECTED_LENGTHS)

    def test_t06_avgdl(self):
        self.assertEqual(self.r.corpus_size, 8)
        self.assertEqual(self.r.average_document_length, EXPECTED_AVGDL)

    def test_t06_avgdl_counts_tokenless_chunks(self):
        """avgdl = 全部 N 个 chunk 的 |d| 均值，没有 token 的 chunk 也计入（|d| = 0）: (2 + 0 + 4) / 3 = 2。"""
        r = BM25Retriever([Chunk(id="A:p1:0", text="x y", doc_id="A", doc_name="n", section="1"),
                           Chunk(id="A:p1:1", text="!!! ---", doc_id="A", doc_name="n", section="1"),
                           Chunk(id="A:p1:2", text="x z z z", doc_id="A", doc_name="n", section="1")])
        self.assertEqual((r.corpus_size, r.average_document_length, r.document_length(1)), (3, 2.0, 0))
        (y,) = r.search_records("y")
        # n(y) = 1，N = 3 → IDF = ln(1 + 2.5/1.5)；|d| = 2 = avgdl → 长度因子 1。
        self.assertTrue(math.isclose(y.raw_score, math.log(1 + 2.5 / 1.5) * 2.2 / (1 + PREREG_K1), rel_tol=1e-14))

    def test_t07_k1(self):
        """两篇等长文档（|d| / avgdl = 1，b 不起作用）: s = ln2 · 2 · 2.2 / (2 + 1.2)。"""
        r = BM25Retriever([Chunk(id="K:p1:0", text="p p q", doc_id="K", doc_name="n", section="1"),
                           Chunk(id="K:p1:1", text="q r s", doc_id="K", doc_name="n", section="1")])
        (record,) = r.search_records("p")
        self.assertTrue(math.isclose(record.raw_score, math.log(2) * 2 * (PREREG_K1 + 1) / (2 + PREREG_K1), rel_tol=1e-14))
        self.assertTrue(math.isclose(record.raw_score, math.log(2) * 4.4 / 3.2, rel_tol=1e-14))

    def test_t08_b(self):
        """|d| = 2 与 6，avgdl = 4: "y" → ln2 · 2.2 / 1.75；"z"（tf = 5）→ ln2 · 11 / 6.65。"""
        r = BM25Retriever([Chunk(id="B:p1:0", text="x y", doc_id="B", doc_name="n", section="1"),
                           Chunk(id="B:p1:1", text="x z z z z z", doc_id="B", doc_name="n", section="1")])
        (y,) = r.search_records("y")
        (z,) = r.search_records("z")
        self.assertTrue(math.isclose(y.raw_score, math.log(2) * 2.2 / 1.75, rel_tol=1e-14))
        self.assertTrue(math.isclose(z.raw_score, math.log(2) * 11 / 6.65, rel_tol=1e-14))


# ==============================================================================
# T9–T12 MULTISET / 累加 / 与独立参考一致
# ==============================================================================

class TestScoring(_Fixture):

    def test_t09_multiset_repeated_query_terms(self):
        (_, once), _ = self.raws("alcohol testing")
        (_, twice), _ = self.raws("alcohol alcohol testing")
        contribs = ref_contributions(self.texts, "alcohol alcohol testing")[2]
        self.assertEqual(len(contribs), 3)
        self.assertEqual(contribs[0], contribs[1])
        self.assertEqual(twice, math.fsum(contribs))
        self.assertNotEqual(twice, once)
        self.assertTrue(math.isclose(twice - once, contribs[0], rel_tol=1e-12))

    def test_t10_cached_and_per_occurrence_recomputation_agree(self):
        """生产路径经 bm25_accumulate（按不同 token 缓存）；参考逐次求值。契约可见 raw 逐比特相同。"""
        for query in ("alcohol alcohol testing", "pump pump pump test", "the the the master"):
            with self.subTest(query=query):
                ref = ref_raw_scores(self.texts, query)
                for ordinal, raw in self.raws(query, k=LARGE_K):
                    self.assertEqual(raw.hex(), ref[ordinal].hex())

    def test_t11_accumulation_is_math_fsum(self):
        contribs = ref_contributions(self.texts, FSUM_DISCRIMINATING_QUERY)[FSUM_DISCRIMINATING_ORDINAL]
        naive = 0.0
        for c in contribs:
            naive += c
        self.assertEqual(math.fsum(contribs), FSUM_DISCRIMINATING_RAW)
        self.assertEqual(naive, NAIVE_SUM_RAW)
        self.assertNotEqual(naive, FSUM_DISCRIMINATING_RAW)             # 判别向量确实存在
        got = dict(self.raws(FSUM_DISCRIMINATING_QUERY, k=LARGE_K))
        self.assertEqual(got[FSUM_DISCRIMINATING_ORDINAL], FSUM_DISCRIMINATING_RAW)

    def test_t11_production_routes_through_frozen_helper_only(self):
        """生产代码没有第二套累加器: 只经 contracts.bm25_accumulate；模块内无 sum / fsum / += 。"""
        tree = ast.parse(read_text(BM25_SOURCE_PATH))
        call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        calls = {(n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)) for n in call_nodes}
        self.assertIn("bm25_accumulate", calls)
        self.assertNotIn("fsum", calls)
        # 唯一允许的 sum 是 avgdl 的整数长度合计 sum(lengths)（整数求和精确），不是分数累加。
        sums = [ast.unparse(n) for n in call_nodes if getattr(n.func, "id", None) == "sum"]
        self.assertEqual(sums, ["sum(lengths)"])
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.AugAssign)])
        real = bm25.bm25_accumulate
        with mock.patch.object(bm25, "bm25_accumulate", side_effect=real) as spy:
            self.r.search_records("pump")
        self.assertGreater(spy.call_count, 0)

    def test_t12_production_equals_independent_reference(self):
        for query in EXPECTED_RANKINGS:
            with self.subTest(query=query):
                got = self.raws(query, k=LARGE_K)
                ref = ref_ranking(self.texts, query, LARGE_K)
                self.assertEqual([o for o, _ in got], [i for _, i in ref])
                self.assertEqual([s.hex() for _, s in got], [s.hex() for s, _ in ref])

    def test_frozen_expected_rankings_and_raw_scores(self):
        for query, (ordinals, hexes) in EXPECTED_RANKINGS.items():
            with self.subTest(query=query):
                got = self.raws(query)
                self.assertEqual([o for o, _ in got], ordinals)
                self.assertEqual([s.hex() for _, s in got], [float.fromhex(h).hex() for h in hexes])


# ==============================================================================
# T13–T17 分数映射 / kinds / 全序 / zero-score
# ==============================================================================

class TestScoreFieldsAndOrder(_Fixture):

    def test_t13_saturation_mapping(self):
        for rec in self.r.search_records("pump test"):
            self.assertEqual(rec.relevance, rec.raw_score / (rec.raw_score + PREREG_SATURATION))
            self.assertEqual(rec.match_score, rec.raw_score / (rec.raw_score + PREREG_SATURATION))

    def test_t14_relevance_equals_match_score_two_fields(self):
        for rec in self.r.search_records("the"):
            self.assertEqual(rec.relevance, rec.match_score)
        names = [f for f in contracts.RETRIEVAL_RECORD_JSON_FIELDS]
        self.assertIn("relevance", names)
        self.assertIn("match_score", names)

    def test_t15_score_kind_values(self):
        for rec in self.r.search_records("fire pump"):
            self.assertEqual((rec.raw_score_kind, rec.relevance_kind, rec.match_score_kind),
                             ("bm25_raw", "bm25_saturation", "bm25_saturation"))

    def test_t16_exact_tie_broken_by_corpus_ordinal(self):
        recs = self.r.search_records("alcohol testing")
        self.assertEqual([r.corpus_ordinal for r in recs], [2, 4])
        self.assertEqual(recs[0].raw_score, recs[1].raw_score)
        self.assertLess(recs[1].chunk_id, recs[0].chunk_id)              # 若按 chunk_id 打破 tie，顺序会反过来

    def test_t17_zero_score_policy_only_positive_raw(self):
        for query in EXPECTED_RANKINGS:
            recs = self.r.search_records(query, k=LARGE_K)
            self.assertTrue(all(r.raw_score > 0 for r in recs), query)
        self.assertEqual([r.corpus_ordinal for r in self.r.search_records("pump", k=LARGE_K)], [7, 0])
        self.assertNotIn(6, [r.corpus_ordinal for q in EXPECTED_RANKINGS for r in self.r.search_records(q, k=LARGE_K)])

    def test_ranking_uses_raw_score_not_relevance(self):
        """relevance 失去全部排序信息（恒为常数）时，返回顺序仍按 raw score —— 排序不读 relevance。"""
        with mock.patch.object(bm25, "_relevance", lambda raw: 0.5):
            self.assertEqual([r.corpus_ordinal for r in self.r.search_records("pump test")], [0, 7, 1])

    def test_relevance_and_match_score_are_independently_sourced(self):
        with mock.patch.object(bm25, "_relevance", lambda raw: raw / (raw + 1.0)):
            for rec in self.r.search_records("the"):
                self.assertEqual(rec.match_score, rec.raw_score / (rec.raw_score + PREREG_SATURATION))
                self.assertNotEqual(rec.relevance, rec.match_score)
        with mock.patch.object(bm25, "_match_score", lambda raw: raw / (raw + 1.0)):
            for rec in self.r.search_records("the"):
                self.assertEqual(rec.relevance, rec.raw_score / (rec.raw_score + PREREG_SATURATION))
                self.assertNotEqual(rec.relevance, rec.match_score)


# ==============================================================================
# T18–T23 k / 空 query / 缺失词 / Unicode / 多语种
# ==============================================================================

class TestQueryEdges(_Fixture):

    def test_t18_k_equals_one(self):
        self.assertEqual([r.corpus_ordinal for r in self.r.search_records("pump test", k=1)], [0])

    def test_t19_k_larger_than_corpus(self):
        recs = self.r.search_records("must pump and naïve davit and random", k=LARGE_K)
        self.assertLessEqual(len(recs), len(FIXTURE_DOCS))
        self.assertEqual([r.corpus_ordinal for r in recs], [i for _, i in ref_ranking(self.texts, "must pump and naïve davit and random", LARGE_K)])

    def test_invalid_k_and_query_rejected(self):
        for bad_k in (0, -1, True, 2.0, None):
            with self.subTest(k=bad_k), self.assertRaises(ContractViolation):
                self.r.search_records("pump", k=bad_k)
        for bad_q in (None, b"pump", ["pump"]):
            with self.subTest(q=bad_q), self.assertRaises(ContractViolation):
                self.r.search_records(bad_q)

    def test_t20_empty_query(self):
        for query in ("", "   ", "\n\t", "!!! ---"):
            self.assertEqual(self.r.search_records(query), [])
            self.assertEqual(self.r.search(query), [])

    def test_t21_absent_term(self):
        self.assertEqual(self.r.search_records("zzzzabsent"), [])
        self.assertEqual(self.raws("pump zzzzabsent"), self.raws("pump"))   # 缺失词贡献 0.0

    def test_t22_unicode(self):
        self.assertEqual(self.raws("café"), self.raws("café"))        # NFC
        self.assertEqual(self.raws("café"), self.raws("CAFÉ"))              # casefold
        self.assertEqual([o for o, _ in self.raws("STRASSE")], [5])         # ß → ss
        self.assertEqual([o for o, _ in self.raws("ångström")], [5])

    def test_t23_multilingual(self):
        self.assertEqual([o for o, _ in self.raws("नमस्ते")], [5])          # 天城文元音符号（M）留在 token 内
        self.assertEqual([o for o, _ in self.raws("kumusta po")], [5])
        self.assertEqual(self.raws("東京港"), [])                           # 不分词: 汉字 + 假名连续串是一个 token
        self.assertEqual([o for o, _ in self.raws("東京港の検査")], [5])


# ==============================================================================
# T24–T29 record / 无泄漏 / 不改状态 / 封闭打分路径
# ==============================================================================

class TestRecordsAndBoundaries(_Fixture):

    def test_t24_records_validate_and_search_projects_them(self):
        for query in EXPECTED_RANKINGS:
            recs = self.r.search_records(query)
            validate_retrieval_records(recs, k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=fixture_ids())
            for rank, rec in enumerate(recs, start=1):                     # rank 1-based；corpus_ordinal 0-based
                self.assertIsInstance(rec, RetrievalResultRecord)
                self.assertIs(type(rec.raw_score), float)
                self.assertEqual(fixture_ids()[rec.corpus_ordinal], rec.chunk_id)
                self.assertEqual(rec, recs[rank - 1])
            hits = self.r.search(query)
            self.assertEqual([(h.chunk, h.relevance, h.match_score, h.origin) for h in hits],
                             [(r.chunk, r.relevance, r.match_score, "bm25") for r in recs])
        self.assertEqual(self.r.search_records("fire pump")[0].corpus_ordinal, 0)   # 第一行 = 0

    def test_t25_no_gold_or_eval_metadata_in_records(self):
        rec = self.r.search_records("pump")[0]
        self.assertEqual(list(json.loads(serialize_retrieval_record(rec))), list(contracts.RETRIEVAL_RECORD_JSON_FIELDS))
        forbidden = {"question_id", "qid", "expected", "gold", "is_gold", "citations", "verdict", "rank"}
        self.assertFalse(forbidden & {f for f in contracts.RETRIEVAL_RECORD_JSON_FIELDS})

    def test_t26_no_eval_or_gold_dependency(self):
        tree = ast.parse(read_text(BM25_SOURCE_PATH))
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                imported.add(n.module)
        self.assertEqual(imported, {"__future__", "math", "unicodedata", "collections", "typing", "core.contracts"})
        identifiers = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name):
                identifiers.add(n.id)
            elif isinstance(n, ast.Attribute):
                identifiers.add(n.attr)
            elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                identifiers.add(n.name)
            elif isinstance(n, ast.arg):
                identifiers.add(n.arg)
        parts = {part for name in identifiers for part in identifier_parts(name)}
        forbidden = {"gold", "testset", "citation", "citations", "expected", "qid", "question", "recall", "verdict",
                     "eval", "evaluation", "metric", "metrics"}
        self.assertFalse(forbidden & parts, forbidden & parts)
        self.assertNotIn("open", identifiers)                                # 不读任何文件

    def test_t27_query_does_not_mutate_index(self):
        r = BM25Retriever(fixture_chunks())
        before = copy.deepcopy(r.__dict__)
        r.search_records("alcohol alcohol testing zzzzabsent café")
        self.assertEqual(r.__dict__, before)

    def test_t28_repeated_search_no_mutation_and_same_process_determinism(self):
        r = BM25Retriever(fixture_chunks())
        before = copy.deepcopy(r.__dict__)
        first = None
        for _ in range(SAME_PROCESS_REPEATS):
            out = "\n".join(serialize_retrieval_record(x) for q in EXPECTED_RANKINGS for x in r.search_records(q))
            if first is None:
                first = out
            self.assertEqual(out, first)
        self.assertEqual(r.__dict__, before)

    def test_t29_production_contribution_path_closed(self):
        self.assertEqual(list(inspect.signature(BM25Retriever.__init__).parameters), ["self", "chunks"])
        self.assertEqual(list(inspect.signature(BM25Retriever.search_records).parameters), ["self", "query", "k"])
        self.assertEqual(list(inspect.signature(BM25Retriever.search).parameters), ["self", "query", "k"])
        public = {n for n in vars(BM25Retriever) if not n.startswith("_")}
        self.assertEqual(public, {"corpus_size", "average_document_length", "document_length", "term_frequency",
                                  "document_frequency", "idf", "search_records", "search"})
        for name in ("document_length", "term_frequency", "document_frequency", "idf"):
            params = inspect.signature(getattr(BM25Retriever, name)).parameters.values()
            self.assertFalse([p for p in params if "Callable" in str(p.annotation)], name)
        # bm25_accumulate 的 contribution 参数只来自类内部（lambda → self._term_contribution）。
        tree = ast.parse(read_text(BM25_SOURCE_PATH))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "bm25_accumulate"]
        self.assertEqual(len(calls), 1)
        contribution_arg = calls[0].args[1]
        self.assertIsInstance(contribution_arg, ast.Lambda)
        self.assertIn("self._term_contribution", ast.unparse(contribution_arg))


# ==============================================================================
# 构造约束 / 确定性
# ==============================================================================

class TestConstructionAndDeterminism(unittest.TestCase):

    def test_construction_preconditions(self):
        good = fixture_chunks()
        for bad in ([], (), iter(good), good + [good[0]], good[:2] + ["not a chunk"]):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ContractViolation):
                BM25Retriever(bad)
        tokenless = [Chunk(id=f"E:p1:{i}", text="!!! ---", doc_id="E", doc_name="n", section="1") for i in range(2)]
        with self.assertRaises(ContractViolation):
            BM25Retriever(tokenless)                                         # avgdl = 0：公式无定义

    def test_independent_process_determinism(self):
        """不同 PYTHONHASHSEED 的全新进程各自从合成语料建索引，规范序列化结果逐字节相同，且与本进程相同。"""
        script = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "import tests.test_bm25_retriever as T; sys.stdout.buffer.write(T.serialized_fixture_results().encode('utf-8'))")
        outputs = []
        for seed in INDEPENDENT_PROCESS_HASH_SEEDS:
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run([sys.executable, "-c", script, REPO_ROOT], capture_output=True, env=env, cwd=REPO_ROOT)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            outputs.append(proc.stdout)
        self.assertEqual(len(set(outputs)), 1)
        self.assertEqual(outputs[0], serialized_fixture_results().encode("utf-8"))
        self.assertGreater(len(outputs[0]), 0)


# ==============================================================================
# T30 prereg → code → test 可追溯
# ==============================================================================

# (prereg 条目, 预注册原文片段（必须出现在 committed prereg 中）, 代码符号, 测试名)
TRACEABILITY = (
    ("indexed text", "| indexed text | `Chunk.text` only |", ["bm25.indexed_text"], ["test_t01_indexed_text_is_exactly_chunk_text"]),
    ("query construction boundary", "query = `EvalItem.question` 原始字符串", ["bm25.BM25Retriever.search_records"],
     ["test_t29_production_contribution_path_closed", "test_invalid_k_and_query_rejected"]),
    ("analyzer", "→ `str.casefold()` → 取 Unicode General_Category 为 L", ["bm25.analyze", "bm25.TOKEN_CATEGORY_CLASSES",
     "bm25.UNICODE_NORMAL_FORM"], ["test_t02_analyzer_exact_tokens", "test_analyzer_matches_independent_reference_on_fixture",
     "test_t22_unicode", "test_t23_multilingual"]),
    ("IDF", "`ln(1 + (N − n + 0.5) / (n + 0.5))`", ["bm25.BM25Retriever.idf", "bm25.IDF_SMOOTHING"], ["test_t03_idf_formula"]),
    ("tf / |d| / avgdl", "tf = token 在该 chunk token 序列中的出现次数", ["bm25.BM25Retriever.term_frequency",
     "bm25.BM25Retriever.document_length", "bm25.BM25Retriever.average_document_length"],
     ["test_t04_term_frequency", "test_t05_document_length", "test_t06_avgdl", "test_t06_avgdl_counts_tokenless_chunks"]),
    ("k1", "| k1 / b | 1.2 / 0.75 ", ["bm25.BM25_K1"], ["test_t07_k1"]),
    ("b", "| k1 / b | 1.2 / 0.75 ", ["bm25.BM25_B"], ["test_t08_b"]),
    ("term contribution formula", "IDF(t) · tf(t,d) · (k1 + 1) / ( tf(t,d) + k1 · (1 − b + b · |d| / avgdl) )",
     ["bm25.BM25Retriever._term_contribution"], ["test_t12_production_equals_independent_reference"]),
    ("MULTISET", "`BM25_QUERY_TERM_SEMANTICS = MULTISET`", ["bm25.BM25Retriever._raw_score"], ["test_t09_multiset_repeated_query_terms"]),
    ("occurrence multiplicity", "`BM25_MULTIPLICITY_SEMANTICS = MATHEMATICAL_OCCURRENCE_MULTIPLICITY`",
     ["bm25.BM25Retriever._raw_score"], ["test_t09_multiset_repeated_query_terms"]),
    ("math.fsum", "`BM25_ACCUMULATION = MATH_FSUM`", ["contracts.bm25_accumulate"],
     ["test_t11_accumulation_is_math_fsum", "test_t11_production_routes_through_frozen_helper_only"]),
    ("callback trace not contract", "`BM25_CALLBACK_INVOCATION_COUNT_IS_CONTRACT = NO`", ["contracts.bm25_accumulate"],
     ["test_t10_cached_and_per_occurrence_recomputation_agree"]),
    ("zero-score policy", "只返回 raw BM25 score > 0", ["bm25.RAW_SCORE_EXCLUSIVE_FLOOR"],
     ["test_t17_zero_score_policy_only_positive_raw", "test_t20_empty_query", "test_t21_absent_term"]),
    ("raw-score ranking", "ranking 一律使用 raw_score，不使用 relevance / match_score 排序", ["contracts.retrieval_order_key"],
     ["test_ranking_uses_raw_score_not_relevance", "test_t12_production_equals_independent_reference"]),
    ("corpus-ordinal tie break", "全序 = (−raw_score, corpus_ordinal)", ["contracts.retrieval_order_key"],
     ["test_t16_exact_tie_broken_by_corpus_ordinal"]),
    ("saturation mapping", "`relevance = bm25_match_score(s)`", ["bm25._relevance", "bm25._match_score"],
     ["test_t13_saturation_mapping", "test_t14_relevance_equals_match_score_two_fields",
      "test_relevance_and_match_score_are_independently_sourced"]),
    ("score kinds", '`relevance_kind = "bm25_saturation"`', ["bm25.RAW_SCORE_KIND", "bm25.SATURATION_KIND"],
     ["test_t15_score_kind_values"]),
    ("RetrievalResultRecord", "逐 hit 载体 = `core.contracts.RetrievalResultRecord`", ["bm25.BM25Retriever.search_records"],
     ["test_t24_records_validate_and_search_projects_them", "test_t25_no_gold_or_eval_metadata_in_records"]),
    ("search_records signature", "`search_records(query: str, k: int = TOP_K_RETRIEVE) -> Sequence[RetrievalResultRecord]`",
     ["bm25.BM25Retriever.search_records"], ["test_t29_production_contribution_path_closed"]),
    ("rank semantics", "| retrieval rank | **1-based** |", ["bm25.BM25Retriever.search_records"],
     ["test_t24_records_validate_and_search_projects_them", "test_t18_k_equals_one"]),
    ("corpus_ordinal semantics", "| corpus_ordinal | **0-based** |", ["bm25.BM25Retriever.__init__"],
     ["test_t24_records_validate_and_search_projects_them"]),
    ("deterministic ordering", "Run A == Run B 逐字节相同", ["bm25.BM25Retriever.search_records"],
     ["test_t28_repeated_search_no_mutation_and_same_process_determinism", "test_independent_process_determinism"]),
    ("no-gold leakage", "下列字段不得用于 query / filter / boost / routing / tie-break / dynamic k", ["bm25"],
     ["test_t26_no_eval_or_gold_dependency", "test_t25_no_gold_or_eval_metadata_in_records"]),
    ("k / top-k", "`RETRIEVAL_K_MAX = TOP_K_RETRIEVE = 20`", ["contracts.TOP_K_RETRIEVE"],
     ["test_t18_k_equals_one", "test_t19_k_larger_than_corpus"]),
    ("retrieval_config digest", "3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e",
     ["bm25.BM25_RETRIEVAL_CONFIG_PAYLOAD"], ["test_t30_retrieval_config_digest_matches_prereg"]),
)


def _resolve(symbol: str):
    root, _, rest = symbol.partition(".")
    obj = {"bm25": bm25, "contracts": contracts}[root]
    for part in filter(None, rest.split(".")):
        obj = getattr(obj, part)
    return obj


class TestT30Traceability(unittest.TestCase):

    def test_t30_traceability_matrix_complete(self):
        prereg = read_text(PREREG_PATH)
        test_names = {name for cls in (TestIndexedTextAndAnalyzer, TestStatistics, TestScoring, TestScoreFieldsAndOrder,
                                       TestQueryEdges, TestRecordsAndBoundaries, TestConstructionAndDeterminism,
                                       TestT30Traceability) for name in vars(cls) if name.startswith("test_")}
        for item, snippet, symbols, tests in TRACEABILITY:
            with self.subTest(item=item):
                self.assertIn(snippet, prereg)
                for symbol in symbols:
                    _resolve(symbol)
                self.assertTrue(tests)
                self.assertFalse(set(tests) - test_names, set(tests) - test_names)

    def test_t30_retrieval_config_digest_matches_prereg(self):
        self.assertIn(EXPECTED_RETRIEVAL_CONFIG_DIGEST, read_text(PREREG_PATH))
        self.assertEqual(canonical_sha256(bm25.BM25_RETRIEVAL_CONFIG_PAYLOAD), EXPECTED_RETRIEVAL_CONFIG_DIGEST)
        self.assertEqual((bm25.BM25_K1, bm25.BM25_B), (PREREG_K1, PREREG_B))


if __name__ == "__main__":
    unittest.main()
