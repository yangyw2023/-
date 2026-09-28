"""scripts/resolve_gold_chunks.py（contracts v0.3.1）的测试。

解析语义: 复用 tests.test_contracts_gold_chunk_map.GOLD_RESOLUTION_VECTORS（契约轮冻结的规范性向量），
resolver 必须对同一组向量给出相同的 (level, formal)。其余测试用合成语料/评测集夹具端到端跑 run()。

运行: python3 -m unittest tests.test_resolve_gold_chunks -v
"""

from __future__ import annotations

import ast
import csv
import dataclasses
import hashlib
import inspect
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import Chunk, ContractViolation, GoldChunkMap  # noqa: E402
import ingest.builder_identity as bi  # noqa: E402
from scripts import resolve_gold_chunks as rgc  # noqa: E402
from tests.test_contracts_gold_chunk_map import (  # noqa: E402
    FILLER, FRAG_A, FRAG_B, FRAG_C, FRAG_SHORT, GOLD_RESOLUTION_VECTORS, quote_of, text_with,
)

RESOLVER_SOURCE_PATH = os.path.join(REPO_ROOT, "scripts", "resolve_gold_chunks.py")
TESTSET_NAME = "testset_v9_1.jsonl"   # 合成评测集，版本应解析为 v9.1


def vector(prefix: str) -> dict:
    return next(v for v in GOLD_RESOLUTION_VECTORS if v["name"].startswith(prefix))


# ==============================================================================
# 合成夹具
# ==============================================================================

def chunk(cid: str, page: int, text: str, section: str = "1") -> dict:
    return dataclasses.asdict(Chunk(id=cid, text=text, doc_id="D", doc_name="d.pdf", section=section, pdf_page=page))


# 语料顺序刻意让 p9 在 p10 之前（字典序相反），用于验证 mapping 值按 corpus 顺序。
RESOLVED_CORPUS = [
    chunk("D:p1:0", 1, text_with(FRAG_A, FRAG_B)),
    chunk("D:p2:0", 2, text_with(FRAG_A)),
    chunk("D:p2:1", 2, text_with(FRAG_B)),
    chunk("D:p3:0", 3, text_with(FRAG_C)),
    chunk("D:p4:0", 4, text_with(FRAG_C)),            # 邻页重复文本：不得进入 gold
    chunk("D:p9:0", 9, text_with(FRAG_A)),
    chunk("D:p10:0", 10, text_with(FRAG_B)),
]


def item(qid: str, expected: str, citations: list[dict]) -> dict:
    return {"id": qid, "type": "fact_lookup" if expected == "answer" else "trap", "language": "en",
            "question": qid, "expected": expected, "gold_answer": qid, "citations": citations}


def cite(page: int, quote: str, section: str = "1") -> dict:
    return {"doc_id": "D", "section": section, "pdf_page": page, "quote": quote}


# 评测集顺序刻意不是字典序（QZ 在 QA 之前），用于验证 mapping 键按评测集顺序。
RESOLVED_TESTSET = [
    item("QZ", "answer", [cite(1, quote_of(FRAG_A, FRAG_B))]),
    item("R1", "refuse", []),
    item("QA", "answer", [cite(2, quote_of(FRAG_A, FRAG_B)), cite(3, quote_of(FRAG_C), section="Chapter 1")]),
    item("QM", "answer", [cite(10, quote_of(FRAG_B)), cite(9, quote_of(FRAG_A))]),
]

UNRESOLVED_TESTSET = RESOLVED_TESTSET + [item("QF", "answer", [cite(77, quote_of(FRAG_A))])]


class Fixture:
    """在临时目录写出语料与评测集；run() 调用真实 resolver。"""

    def __init__(self, testset=RESOLVED_TESTSET, corpus=RESOLVED_CORPUS):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.chunks = os.path.join(self.root, "chunks.jsonl")
        self.testset = os.path.join(self.root, TESTSET_NAME)
        for path, rows in ((self.chunks, corpus), (self.testset, testset)):
            with open(path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.corpus_sha = rgc.file_sha256(self.chunks)

    def run(self, out_name="out", corpus_sha=None) -> tuple[int, str]:
        out_dir = os.path.join(self.root, out_name)
        code = rgc.run(self.chunks, self.testset, corpus_sha or self.corpus_sha[:8], out_dir)
        return code, out_dir

    def names(self) -> GoldChunkMap:
        return GoldChunkMap(
            testset_version="v9.1", testset_sha256=rgc.file_sha256(self.testset),
            corpus_chunks_sha256=self.corpus_sha, corpus_builder_name=bi.CORPUS_BUILDER_NAME,
            construction_rules_sha256=bi.construction_rules_identity(),
            chunker_config=bi.effective_chunker_config_identity(),
            contracts_version=contracts.CONTRACTS_VERSION, mapping={})

    def close(self):
        self._tmp.cleanup()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def read_report(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FixtureCase(unittest.TestCase):
    testset = RESOLVED_TESTSET

    def setUp(self):
        self.fx = Fixture(self.testset)
        self.addCleanup(self.fx.close)
        self._quiet = mock.patch("sys.stdout", new_callable=io.StringIO)
        self._quiet.start()
        self.addCleanup(self._quiet.stop)


# ==============================================================================
# 解析语义（规范性向量 + 命名分支）
# ==============================================================================

class TestResolveQuoteVectors(unittest.TestCase):

    def test_all_normative_vectors(self):
        for v in GOLD_RESOLUTION_VECTORS:
            with self.subTest(v["name"]):
                r = rgc.resolve_quote(v["quote"], v["page_chunks"])
                self.assertEqual((r.level, r.formal_chunk_ids), (v["expected_level"], v["expected_formal"]))

    def test_t5_unique_one_chunk_cover_is_l1(self):
        v = vector("T1_")
        self.assertEqual(rgc.resolve_quote(v["quote"], v["page_chunks"]).level, "L1")

    def test_t6_unique_multi_chunk_cover_is_l2(self):
        r = rgc.resolve_quote(**{k: vector("T2_")[k] for k in ("quote", "page_chunks")})
        self.assertEqual((r.level, r.formal_chunk_ids), ("L2", ("X", "Y")))

    def test_t7_unique_minimum_cover_without_single_candidate_fragment(self):
        """A→{X,Y}, B→{Y,Z} → 唯一最小 cover {Y} → L1（不是 FORCED_COVER 的 AMBIGUOUS）。"""
        v = vector("T3_")
        r = rgc.resolve_quote(v["quote"], v["page_chunks"])
        self.assertEqual([m.candidate_chunk_ids for m in r.fragments], [("X", "Y"), ("Y", "Z")])
        self.assertEqual((r.level, r.formal_chunk_ids), ("L1", ("Y",)))

    def test_t8_tie_is_ambiguous_in_every_chunk_order(self):
        import itertools
        for name in ("T4_", "T4b_"):
            v = vector(name)
            for perm in itertools.permutations(v["page_chunks"]):
                r = rgc.resolve_quote(v["quote"], perm)
                self.assertEqual((r.level, r.formal_chunk_ids), ("AMBIGUOUS", ()), (name, [c for c, _ in perm]))

    def test_order_invariance_for_all_vectors(self):
        import itertools
        for v in GOLD_RESOLUTION_VECTORS:
            fragments = contracts.split_quote_fragments(v["quote"])
            for chunks in itertools.permutations(v["page_chunks"]):
                for frags in itertools.permutations(fragments):
                    r = rgc.resolve_quote(quote_of(*frags), chunks)
                    self.assertEqual(r.level, v["expected_level"], v["name"])
                    self.assertEqual(set(r.formal_chunk_ids), set(v["expected_formal"]), v["name"])
                    order = [c for c, _ in chunks]
                    self.assertEqual(list(r.formal_chunk_ids), [c for c in order if c in r.formal_chunk_ids])

    def test_t9_l3(self):
        v = vector("T5_")
        self.assertEqual(rgc.resolve_quote(v["quote"], v["page_chunks"]).level, "L3")

    def test_t10_l4_only_short_fragment_hit(self):
        v = vector("T6_")
        r = rgc.resolve_quote(v["quote"], v["page_chunks"])
        self.assertEqual((r.level, r.formal_chunk_ids), ("L4", ()))
        self.assertEqual(r.candidate_chunk_ids, ("X",))   # 命中留作审计证据，但绝不当 gold

    def test_t11_fail_page_absent(self):
        v = vector("T7_")
        self.assertEqual(rgc.resolve_quote(v["quote"], v["page_chunks"]).level, "FAIL")

    def test_t12_short_fragment_participates_in_full_cover(self):
        v = vector("T8_")
        r = rgc.resolve_quote(v["quote"], v["page_chunks"])
        self.assertFalse(contracts.is_sole_match_eligible(FRAG_SHORT))
        self.assertEqual((r.level, r.formal_chunk_ids), ("L2", ("X", "Y")))

    def test_t13_unresolved_levels_have_no_formal_chunks(self):
        for prefix in ("T4_", "T4b_", "T5_", "T6_", "T6b_", "T7_"):
            v = vector(prefix)
            r = rgc.resolve_quote(v["quote"], v["page_chunks"])
            self.assertNotIn(r.level, contracts.FORMAL_MATCH_LEVELS)
            self.assertEqual(r.formal_chunk_ids, ())

    def test_t3_whole_ellipsis_quote_is_never_literal_matched(self):
        quote = quote_of(FRAG_A, FRAG_B)
        page = [("X", text_with(FRAG_A, FRAG_B))]
        self.assertNotIn(contracts.normalize_text(quote), contracts.normalize_text(page[0][1]))
        self.assertEqual(rgc.resolve_quote(quote, page).level, "L1")


# ==============================================================================
# 端到端: 输入、映射、report、确定性
# ==============================================================================

class TestInputs(FixtureCase):

    def test_t1_v53_loads_without_gold_chunk_ids(self):
        items = rgc.load_testset(os.path.join(REPO_ROOT, "eval", "testset_v5_3.jsonl"))
        self.assertEqual(len(items), 39)
        self.assertFalse(any(hasattr(i, "gold_chunk_ids") for i in items))

    def test_legacy_gold_chunk_ids_field_is_rejected(self):
        with open(self.fx.testset, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(item("QL", "answer", [cite(1, FRAG_A)]) | {"gold_chunk_ids": []}) + "\n")
        with self.assertRaises(rgc.ResolverInputError):
            rgc.load_testset(self.fx.testset)

    def test_blank_lines_skipped_but_malformed_lines_fail(self):
        """空行是无意义格式（仓库 JSONL 读取惯例）；坏 JSON 与非对象行仍然硬失败，且报物理行号。"""
        items_before = rgc.load_testset(self.fx.testset)
        with open(self.fx.testset, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        with open(self.fx.testset, "w", encoding="utf-8") as handle:
            handle.write("\n" + lines[0] + "\n   \n" + "\n".join(lines[1:]) + "\n\n")
        self.assertEqual(rgc.load_testset(self.fx.testset), items_before)
        for bad in ("{not json", "[1, 2]"):
            with open(self.fx.testset, "a", encoding="utf-8") as handle:
                handle.write(bad + "\n")
            with self.subTest(bad), self.assertRaisesRegex(rgc.ResolverInputError, r":\d+: "):
                rgc.load_testset(self.fx.testset)
            with open(self.fx.testset, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")

    def test_t2_validate_eval_item_called_per_item(self):
        with mock.patch.object(rgc, "validate_eval_item", wraps=contracts.validate_eval_item) as spy:
            self.assertEqual(self.fx.run()[0], 0)
        self.assertEqual(spy.call_count, len(RESOLVED_TESTSET))

    def test_t3_split_quote_fragments_used_for_every_citation(self):
        with mock.patch.object(rgc, "split_quote_fragments", wraps=contracts.split_quote_fragments) as spy:
            self.fx.run()
        quotes = [c["quote"] for q in RESOLVED_TESTSET for c in q["citations"]]
        self.assertEqual([call.args[0] for call in spy.call_args_list], quotes)

    def test_t20_testset_bytes_unchanged(self):
        before = read_bytes(self.fx.testset)
        self.fx.run()
        self.assertEqual(read_bytes(self.fx.testset), before)

    def test_t21_corpus_sha_assertion(self):
        for bad in (self.fx.corpus_sha[:7], self.fx.corpus_sha[:8].upper(), "0" * 8, "0" * 64, self.fx.corpus_sha[:9]):
            with self.subTest(bad), self.assertRaises(rgc.ResolverInputError):
                self.fx.run(out_name="bad", corpus_sha=bad)
        self.assertEqual(self.fx.run(out_name="full", corpus_sha=self.fx.corpus_sha)[0], 0)


class TestResolvedRun(FixtureCase):

    def setUp(self):
        super().setUp()
        self.code, self.out = self.fx.run()
        names = self.fx.names()
        self.map_path = os.path.join(self.out, names.filename())
        self.report_path = os.path.join(self.out, names.report_filename())
        with open(self.map_path, encoding="utf-8") as handle:
            self.map = json.load(handle)

    def test_exit_code_and_identity(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.map["testset_version"], "v9.1")
        self.assertEqual(self.map["corpus_chunks_sha256"], self.fx.corpus_sha)   # 完整 64 位，不是断言的前缀
        self.assertEqual(self.map["corpus_builder_name"], bi.CORPUS_BUILDER_NAME)
        self.assertEqual(self.map["construction_rules_sha256"], bi.construction_rules_identity())
        self.assertEqual(self.map["chunker_config"], bi.effective_chunker_config_identity())
        self.assertEqual(self.map["contracts_version"], contracts.CONTRACTS_VERSION)
        self.assertNotIn("built_at", self.map)

    def test_t4_exact_citation_page_only(self):
        self.assertEqual(self.map["mapping"]["QA"], ["D:p2:0", "D:p2:1", "D:p3:0"])
        self.assertNotIn("D:p4:0", json.dumps(self.map))
        self.assertNotIn(b"D:p4:0", read_bytes(self.report_path))

    def test_t15_refuse_absent(self):
        self.assertNotIn("R1", self.map["mapping"])

    def test_t16_keys_in_testset_order(self):
        self.assertEqual(list(self.map["mapping"]), ["QZ", "QA", "QM"])

    def test_t17_values_in_corpus_order(self):
        self.assertEqual(self.map["mapping"]["QM"], ["D:p9:0", "D:p10:0"])   # 字典序会反过来

    def test_t22_t23_formal_chunks_exist_and_are_on_citation_page(self):
        corpus = {c["id"]: c for c in RESOLVED_CORPUS}
        testset = {q["id"]: q for q in RESOLVED_TESTSET}
        for row in read_report(self.report_path):
            page = testset[row["question_id"]]["citations"][int(row["citation_index"])]["pdf_page"]
            for cid in filter(None, row["formal_chunk_ids"].split(";")):
                self.assertIn(cid, corpus)
                self.assertEqual(corpus[cid]["pdf_page"], page)

    def test_t18_report_rows_order_and_columns(self):
        rows = read_report(self.report_path)
        self.assertEqual(tuple(rows[0]), contracts.GOLD_CHUNK_MAP_REPORT_COLUMNS)
        self.assertEqual([(r["question_id"], r["citation_index"]) for r in rows],
                         [("QZ", "0"), ("QA", "0"), ("QA", "1"), ("QM", "0"), ("QM", "1")])
        qa1 = rows[2]
        self.assertEqual((qa1["pdf_page"], qa1["match_level"], qa1["reason"], qa1["needs_review"]),
                         ("3", "L1", "RESOLVED_SINGLE_CHUNK", "false"))
        self.assertEqual(qa1["section_exact_match"], "false")      # "Chapter 1" vs "1"：只审计，不挡匹配
        frag = json.loads(rows[1]["fragment_matches_json"])
        self.assertEqual(frag, [
            {"index": 0, "text": FRAG_A, "length": len(FRAG_A), "sole_match_eligible": True, "candidate_chunk_ids": ["D:p2:0"]},
            {"index": 1, "text": FRAG_B, "length": len(FRAG_B), "sole_match_eligible": True, "candidate_chunk_ids": ["D:p2:1"]},
        ])

    def test_t19_filenames_come_from_contract(self):
        names = self.fx.names()
        self.assertEqual(sorted(os.listdir(self.out)), sorted([names.filename(), names.report_filename()]))

    def test_t24_run_a_run_b_byte_identical(self):
        _, second = self.fx.run(out_name="run_b")
        for name in os.listdir(self.out):
            with open(os.path.join(self.out, name), "rb") as a, open(os.path.join(second, name), "rb") as b:
                self.assertEqual(hashlib.sha256(a.read()).digest(), hashlib.sha256(b.read()).digest(), name)

    def test_existing_outputs_are_not_overwritten(self):
        with self.assertRaises(rgc.ResolverInputError):
            self.fx.run()


class TestFailClosed(FixtureCase):
    testset = UNRESOLVED_TESTSET

    def test_t14_unresolved_answer_citation_writes_report_only(self):
        code, out = self.fx.run()
        names = self.fx.names()
        self.assertEqual(code, rgc.EXIT_MAP_NOT_ACCEPTED)
        self.assertNotEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(out, names.report_filename())))
        self.assertFalse(os.path.exists(os.path.join(out, names.filename())))
        rows = read_report(os.path.join(out, names.report_filename()))
        qf = [r for r in rows if r["question_id"] == "QF"]
        self.assertEqual([(r["match_level"], r["reason"], r["formal_chunk_ids"], r["needs_review"]) for r in qf],
                         [("FAIL", "PAGE_ABSENT", "", "true")])

    def test_t13_validator_not_reached_when_unresolved(self):
        with mock.patch.object(rgc, "validate_gold_chunk_map") as spy:
            self.fx.run()
        spy.assert_not_called()


# ==============================================================================
# 权威 builder provider 身份（T25 / T26）
# ==============================================================================

class TestBuilderProvider(FixtureCase):

    def test_t25_production_resolver_passes_the_authoritative_module_object(self):
        with mock.patch.object(rgc, "validate_gold_chunk_map", wraps=contracts.validate_gold_chunk_map) as spy:
            self.assertEqual(self.fx.run()[0], 0)
        self.assertEqual(spy.call_count, 1)
        captured = spy.call_args.kwargs["builder"]
        self.assertIs(captured, bi)
        self.assertIs(captured, sys.modules["ingest.builder_identity"])

    def test_t26_equal_valued_fake_provider_is_never_the_production_provider(self):
        fake = types.SimpleNamespace(
            CORPUS_BUILDER_NAME=bi.CORPUS_BUILDER_NAME,
            effective_chunker_config_identity=bi.effective_chunker_config_identity,
            construction_rules_identity=bi.construction_rules_identity,
        )
        # 值相等的伪 provider 能骗过 validator 的值比较 —— 这正是必须用对象同一性断言的原因。
        with mock.patch.object(rgc, "validate_gold_chunk_map", wraps=contracts.validate_gold_chunk_map) as spy:
            self.fx.run()
        _, kwargs = spy.call_args
        contracts.validate_gold_chunk_map(*spy.call_args.args, current_corpus_chunks_sha256=kwargs[
            "current_corpus_chunks_sha256"], builder=fake)          # 值比较放行 fake
        self.assertIsNot(kwargs["builder"], fake)
        self.assertIs(kwargs["builder"], bi)
        # resolver 没有任何注入 provider 的入口
        self.assertEqual(list(inspect.signature(rgc.run).parameters),
                         ["chunks_path", "testset_path", "asserted_corpus_sha", "out_dir"])
        self.assertIs(rgc.builder_identity, bi)


# ==============================================================================
# CLI 与遗留代码移除
# ==============================================================================

class TestCli(unittest.TestCase):

    ARGS = ["--chunks", "c", "--testset", "t", "--corpus-sha", "abcdef01", "--out-dir", "o"]

    def test_t29_accepts_the_four_arguments(self):
        ns = rgc.parse_args(self.ARGS)
        self.assertEqual((ns.chunks, ns.testset, ns.corpus_sha, ns.out_dir), ("c", "t", "abcdef01", "o"))

    def test_t28_rejects_legacy_out_testset_and_abbreviations(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            for extra in (["--out-testset", "x"], ["--out-report", "x"]):
                with self.subTest(extra), self.assertRaises(SystemExit):
                    rgc.parse_args(self.ARGS + extra)
            with self.assertRaises(SystemExit):
                rgc.parse_args(["--chunks", "c", "--testset", "t", "--corpus-sha", "abcdef01", "--out", "o"])
            for missing in ("--corpus-sha", "--out-dir"):
                args = list(self.ARGS)
                i = args.index(missing)
                del args[i:i + 2]
                with self.subTest(missing), self.assertRaises(SystemExit):
                    rgc.parse_args(args)


class TestLegacyRemoved(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(RESOLVER_SOURCE_PATH, encoding="utf-8") as handle:
            cls.source = handle.read()
        cls.tree = ast.parse(cls.source)
        cls.names = {n.id for n in ast.walk(cls.tree) if isinstance(n, ast.Name)} | \
                    {n.name for n in ast.walk(cls.tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        cls.strings = [n.value for n in ast.walk(cls.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]

    def test_t27_no_testset_mutation_path(self):
        for name in ("write_resolved_testset", "fill_gold_chunk_ids", "REQUIRED_QUESTION_FIELDS",
                     "PAGE_WINDOW", "FUZZY_PREFIX_CHARS", "normalize_whitespace", "_chunks_on_pages"):
            self.assertNotIn(name, self.names)
        options = [a.value for n in ast.walk(self.tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
                   for a in n.args if isinstance(a, ast.Constant)]
        self.assertEqual(sorted(options), ["--chunks", "--corpus-sha", "--out-dir", "--testset"])
        self.assertEqual([s for s in self.strings if s == "gold_chunk_ids"], [])
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                self.assertNotEqual(node.slice.value, "gold_chunk_ids")

    def test_no_hand_written_builder_identity(self):
        self.assertNotIn(bi.CORPUS_BUILDER_NAME, self.source)
        self.assertNotIn(bi.construction_rules_identity(), self.source)
        self.assertNotIn(bi.effective_chunker_config_identity(), self.source)
        for key in ("chars_per_token_est", "chunk_min_chars", "chunk_target_tokens", "parser-", "__builder-"):
            self.assertNotIn(key, self.source)

    def test_imports_authoritative_builder_module(self):
        imports = [n for n in ast.walk(self.tree) if isinstance(n, ast.Import)]
        self.assertTrue(any(a.name == "ingest.builder_identity" and a.asname == "builder_identity"
                            for n in imports for a in n.names))


if __name__ == "__main__":
    unittest.main()
