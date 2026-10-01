"""GoldChunkMap / MatchLevel 契约测试（contracts v0.4.0 / GoldChunkMap 语义 v0.3.1；v0.3.0 S6 clarification + v0.3.1 follow-up；
0.4.0 版本拆分见 tests/test_contracts_gold_chunk_map_versioning.py）。

两部分:
  1. 契约边界: core.contracts 自己负责的东西 —— 版本、字段、文件名、identity helper、
     validate_gold_chunk_map 的 fail-closed 与键/序约束、序列化确定性，以及 v0.3.1 的
     权威 builder 身份桥接（构建身份一律取自 ingest.builder_identity，测试不钉住当前值）。
  2. 规范性测试向量 GOLD_RESOLUTION_VECTORS（T1–T8 及补充）: 单条 citation 的解析语义。
     解析算法属于 resolver，不在 contracts 里。这里的 reference_resolve() 是 MatchLevel
     定义的【逐字转写】（暴力枚举子集），只用来证明向量与契约文字一致；
     下一轮 resolver 必须对同一组向量给出相同的 (level, formal)。

当前真实语料没有覆盖 AMBIGUOUS / L3 / L4 / FAIL，所以这些状态只能靠合成向量验收。

运行: python3 -m unittest tests.test_contracts_gold_chunk_map -v
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import (
    Citation,
    ContractViolation,
    EvalItem,
    GoldChunkMap,
    is_sole_match_eligible,
    normalize_text,
    split_quote_fragments,
)
from components.parsers import kaiva_pdf
from ingest import builder_identity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 合成片段 -------------------------------------------------------------
# eligible / short 的判定一律走 is_sole_match_eligible，不在测试里复制阈值；
# TestVectorSanity 会断言这些片段确实落在预期一侧。
FRAG_A = "the first action must be to raise the alarm"
FRAG_B = "period of validity shall not exceed eight hours"
FRAG_C = "switch off wifi and crew internet access"      # 在向量里从不出现于任何 chunk
FRAG_SHORT = "Not Required"
FRAG_SHORT_2 = "For Tankers"
FILLER = "this paragraph intentionally contains no quoted evidence at all"

ELLIPSIS = " ... "


def quote_of(*fragments: str) -> str:
    return ELLIPSIS.join(fragments)


def text_with(*fragments: str) -> str:
    return " ".join([FILLER, *fragments, FILLER])


# ---- 规范性测试向量 ---------------------------------------------------------
# page_chunks: citation 所在页的全部 chunk，按 corpus 顺序；空元组 = C(P) 为空。
# expected_formal: 按 corpus 顺序；非 L1/L2 为空元组。
GOLD_RESOLUTION_VECTORS: tuple[dict, ...] = (
    dict(name="T1_unique_single_chunk_cover",
         quote=quote_of(FRAG_A, FRAG_B),
         page_chunks=(("X", text_with(FRAG_A, FRAG_B)), ("Y", FILLER)),
         expected_level="L1", expected_formal=("X",)),
    dict(name="T2_unique_multi_chunk_cover",
         quote=quote_of(FRAG_A, FRAG_B),
         page_chunks=(("X", text_with(FRAG_A)), ("Y", text_with(FRAG_B))),
         expected_level="L2", expected_formal=("X", "Y")),
    dict(name="T3_unique_minimum_cover_without_single_candidate_fragment",
         quote=quote_of(FRAG_A, FRAG_B),
         page_chunks=(("X", text_with(FRAG_A)), ("Y", text_with(FRAG_A, FRAG_B)), ("Z", text_with(FRAG_B))),
         expected_level="L1", expected_formal=("Y",)),
    dict(name="T4_minimum_cover_tie",
         quote=quote_of(FRAG_A, FRAG_B),
         page_chunks=(("X", text_with(FRAG_A, FRAG_B)), ("Y", text_with(FRAG_B, FRAG_A))),
         expected_level="AMBIGUOUS", expected_formal=()),
    dict(name="T4b_multi_chunk_minimum_cover_tie",
         quote=quote_of(FRAG_A, FRAG_B),
         page_chunks=(("X", text_with(FRAG_A)), ("Y", text_with(FRAG_A)), ("Z", text_with(FRAG_B))),
         expected_level="AMBIGUOUS", expected_formal=()),
    dict(name="T5_partial_eligible_match",
         quote=quote_of(FRAG_A, FRAG_C),
         page_chunks=(("X", text_with(FRAG_A)), ("Y", FILLER)),
         expected_level="L3", expected_formal=()),
    dict(name="T6_only_short_fragment_match",
         quote=quote_of(FRAG_C, FRAG_SHORT),
         page_chunks=(("X", text_with(FRAG_SHORT)), ("Y", FILLER)),
         expected_level="L4", expected_formal=()),
    dict(name="T6b_page_exists_zero_matches",
         quote=quote_of(FRAG_C),
         page_chunks=(("X", FILLER),),
         expected_level="L4", expected_formal=()),
    dict(name="T7_page_absent",
         quote=quote_of(FRAG_A),
         page_chunks=(),
         expected_level="FAIL", expected_formal=()),
    dict(name="T8_short_fragment_required_for_full_cover",
         quote=quote_of(FRAG_A, FRAG_SHORT),
         page_chunks=(("X", text_with(FRAG_A)), ("Y", text_with(FRAG_SHORT))),
         expected_level="L2", expected_formal=("X", "Y")),
    dict(name="T8b_two_short_fragments_single_chunk",
         quote=quote_of(FRAG_SHORT_2, FRAG_SHORT),
         page_chunks=(("X", text_with(FRAG_SHORT_2, FRAG_SHORT)),),
         expected_level="L1", expected_formal=("X",)),
    dict(name="T9_whitespace_normalised_on_both_sides",
         quote="the first action   must be\nto raise the alarm",
         page_chunks=(("X", FILLER + "\nthe first action must\n    be to raise   the alarm\n"),),
         expected_level="L1", expected_formal=("X",)),
)


def reference_resolve(quote: str, page_chunks: tuple[tuple[str, str], ...]) -> tuple[str, tuple[str, ...]]:
    """MatchLevel 定义的逐字转写。暴力枚举，不做任何优化 —— 它是规格，不是实现。"""
    if not page_chunks:
        return "FAIL", ()
    fragments = split_quote_fragments(quote)
    order = [chunk_id for chunk_id, _ in page_chunks]
    texts = {chunk_id: normalize_text(text) for chunk_id, text in page_chunks}
    cand = [{cid for cid in order if f in texts[cid]} for f in fragments]
    if all(cand):
        for size in range(1, len(order) + 1):
            covers = [set(s) for s in itertools.combinations(order, size)
                      if all(c & set(s) for c in cand)]
            if covers:
                break
        if len(covers) > 1:
            return "AMBIGUOUS", ()
        formal = tuple(cid for cid in order if cid in covers[0])
        return ("L1" if len(formal) == 1 else "L2"), formal
    if any(c and is_sole_match_eligible(f) for f, c in zip(fragments, cand)):
        return "L3", ()
    return "L4", ()


class TestVectorSanity(unittest.TestCase):
    """向量本身的前提成立（否则后面的断言测的不是它们声称的东西）。"""

    def test_fragment_eligibility_sides(self):
        for frag in (FRAG_A, FRAG_B, FRAG_C):
            self.assertTrue(is_sole_match_eligible(frag), frag)
        for frag in (FRAG_SHORT, FRAG_SHORT_2):
            self.assertFalse(is_sole_match_eligible(frag), frag)

    def test_filler_contains_no_fragment(self):
        for frag in (FRAG_A, FRAG_B, FRAG_C, FRAG_SHORT, FRAG_SHORT_2):
            self.assertNotIn(frag, FILLER)

    def test_vectors_have_unique_names_and_known_levels(self):
        names = [v["name"] for v in GOLD_RESOLUTION_VECTORS]
        self.assertEqual(len(names), len(set(names)))
        for v in GOLD_RESOLUTION_VECTORS:
            self.assertIn(v["expected_level"], contracts.MATCH_LEVEL_REASON)
            self.assertEqual(bool(v["expected_formal"]),
                             v["expected_level"] in contracts.FORMAL_MATCH_LEVELS)

    def test_every_match_level_is_covered(self):
        covered = {v["expected_level"] for v in GOLD_RESOLUTION_VECTORS}
        self.assertEqual(covered, set(contracts.MATCH_LEVEL_REASON))


class TestResolutionVectors(unittest.TestCase):
    """T1–T8：向量与 MatchLevel 定义一致。"""

    def test_each_vector(self):
        for v in GOLD_RESOLUTION_VECTORS:
            with self.subTest(v["name"]):
                self.assertEqual(reference_resolve(v["quote"], v["page_chunks"]),
                                 (v["expected_level"], v["expected_formal"]))

    def test_t3_is_not_ambiguous(self):
        """防止退回旧 FORCED_COVER：T3 中没有单候选片段，但 {Y} 是唯一最小 cover。"""
        v = next(v for v in GOLD_RESOLUTION_VECTORS if v["name"].startswith("T3_"))
        fragments = split_quote_fragments(v["quote"])
        texts = {cid: normalize_text(t) for cid, t in v["page_chunks"]}
        cand_sizes = [sum(f in t for t in texts.values()) for f in fragments]
        self.assertTrue(all(size >= 2 for size in cand_sizes), cand_sizes)
        self.assertEqual(reference_resolve(v["quote"], v["page_chunks"]), ("L1", ("Y",)))

    def test_t8_short_fragment_is_not_dropped(self):
        """去掉短片段会把 T8 误判成 L1 {X}；契约要求它仍参与 full cover。"""
        v = next(v for v in GOLD_RESOLUTION_VECTORS if v["name"].startswith("T8_"))
        self.assertIn(FRAG_SHORT, split_quote_fragments(v["quote"]))
        self.assertEqual(reference_resolve(v["quote"], v["page_chunks"]), ("L2", ("X", "Y")))
        self.assertEqual(reference_resolve(quote_of(FRAG_A), v["page_chunks"]), ("L1", ("X",)))


class TestOrderInvariance(unittest.TestCase):
    """排序只用于枚举与序列化，不参与消歧：任意 chunk 顺序 × 任意片段顺序，级别与 formal 集合不变。"""

    def test_all_vectors_under_all_permutations(self):
        for v in GOLD_RESOLUTION_VECTORS:
            fragments = split_quote_fragments(v["quote"])
            for chunk_perm in itertools.permutations(v["page_chunks"]):
                for frag_perm in itertools.permutations(fragments):
                    with self.subTest(v["name"], chunks=[c for c, _ in chunk_perm], frags=frag_perm):
                        level, formal = reference_resolve(quote_of(*frag_perm), chunk_perm)
                        self.assertEqual(level, v["expected_level"])
                        self.assertEqual(set(formal), set(v["expected_formal"]))
                        order = [c for c, _ in chunk_perm]
                        self.assertEqual(list(formal), [c for c in order if c in formal])

    def test_t4_tie_stays_ambiguous_in_every_order(self):
        for name in ("T4_minimum_cover_tie", "T4b_multi_chunk_minimum_cover_tie"):
            v = next(v for v in GOLD_RESOLUTION_VECTORS if v["name"] == name)
            results = {reference_resolve(v["quote"], perm)
                       for perm in itertools.permutations(v["page_chunks"])}
            self.assertEqual(results, {("AMBIGUOUS", ())}, name)


class TestContractConstants(unittest.TestCase):

    def test_version(self):
        self.assertEqual(contracts.CONTRACTS_VERSION, "0.4.0")
        self.assertEqual(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, "0.3.1")

    def test_match_level_enum(self):
        self.assertEqual(contracts.MatchLevel.__args__, ("L1", "L2", "AMBIGUOUS", "L3", "L4", "FAIL"))
        self.assertEqual(contracts.FORMAL_MATCH_LEVELS, frozenset({"L1", "L2"}))
        self.assertEqual(set(contracts.MATCH_LEVEL_REASON), set(contracts.MatchLevel.__args__))
        self.assertEqual(set(contracts.MATCH_LEVEL_REASON.values()),
                         set(contracts.GoldResolutionReason.__args__))

    def test_report_columns_frozen(self):
        self.assertEqual(contracts.GOLD_CHUNK_MAP_REPORT_COLUMNS, (
            "question_id", "citation_index", "doc_id", "section", "pdf_page",
            "section_exact_match", "fragment_count", "match_level", "reason",
            "formal_chunk_ids", "candidate_chunk_ids", "needs_review", "fragment_matches_json",
        ))


class TestContractsOwnsNoBuilderIdentity(unittest.TestCase):
    """v0.3.1: 契约不持有、不复制、不 import builder 身份（DUPLICATE_IDENTITY_LOGIC = REMOVED）。"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO_ROOT, "core", "contracts.py"), encoding="utf-8") as handle:
            cls.tree = ast.parse(handle.read())

    def test_temporary_chunker_helper_removed(self):
        self.assertFalse(hasattr(contracts, "chunker_config_identity"))
        module_functions = {n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.assertFalse({n for n in module_functions if "chunker_config" in n or "construction_rules" in n})

    def test_builder_identity_protocol_is_shape_only(self):
        """CorpusBuilderIdentity 只声明形状: 方法体只能是 `...`，不得有任何取值逻辑。"""
        cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "CorpusBuilderIdentity")
        for member in cls.body:
            if isinstance(member, ast.FunctionDef):
                body = [s for s in member.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                                       and s.value.value is not Ellipsis)]
                self.assertEqual(len(body), 1, member.name)
                self.assertIsInstance(body[0], ast.Expr)
                self.assertIs(body[0].value.value, Ellipsis)
            else:
                self.assertIsInstance(member, (ast.AnnAssign, ast.Expr), ast.dump(member)[:80])
                if isinstance(member, ast.AnnAssign):
                    self.assertIsNone(member.value)

    def test_no_identity_key_literals_in_executable_code(self):
        """参数键只允许出现在注释/docstring 中，不允许出现在可执行字符串字面量里。"""
        docstrings = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(node) is not None:
                docstrings.add(id(node.body[0].value))
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                for key in ("chars_per_token_est", "chunk_min_chars", "chunk_target_tokens"):
                    self.assertNotIn(key, node.value)

    def test_contracts_is_a_dependency_leaf(self):
        """contracts 谁都不依赖（CLAUDE.md 依赖树）: 不 import 任何第一方模块，含函数内延迟 import。"""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                self.assertNotIn(root, ("core", "components", "ingest", "eval", "scripts", "serve"))


class TestGoldChunkMapFields(unittest.TestCase):

    def test_fields(self):
        names = [f.name for f in dataclasses.fields(GoldChunkMap)]
        self.assertEqual(names, ["testset_version", "testset_sha256", "corpus_chunks_sha256",
                                 "corpus_builder_name", "construction_rules_sha256", "chunker_config",
                                 "contracts_version", "mapping", "gold_chunk_map_semantics_version"])
        self.assertNotIn("built_at", names)
        self.assertNotIn("parser_name", names)

    def test_t14_runtime_provenance_not_in_schema(self):
        """H2: GoldChunkMap 不要求运行时语料构建 provenance。"""
        joined = " ".join(f.name for f in dataclasses.fields(GoldChunkMap))
        for token in ("doc_lang", "lang", "ocr", "manifest", "poppler", "pdftotext", "visual", "pdf", "tool"):
            self.assertNotIn(token, joined)


class TestIdentityHelpers(unittest.TestCase):

    def test_testset_version_from_path(self):
        self.assertEqual(contracts.testset_version_from_path("eval/testset_v5_3.jsonl"), "v5.3")
        self.assertEqual(contracts.testset_version_from_path("testset_v10_0.jsonl"), "v10.0")

    def test_invalid_testset_filenames(self):
        for bad in ("eval/testset_v5.3.jsonl", "eval/testset_5_3.jsonl", "eval/testset_v05_3.jsonl",
                    "eval/testset_v5_3.json", "eval/testset_v5_3.jsonl.bak", "eval/testset.jsonl"):
            with self.subTest(bad):
                with self.assertRaises(ContractViolation):
                    contracts.testset_version_from_path(bad)


# ---- validate_gold_chunk_map / 序列化 ---------------------------------------
# 构建身份一律在调用时取自权威 builder（ingest.builder_identity），测试不钉住任何当前值。
SHA_TESTSET = "a" * 64
SHA_CORPUS = "c8978777" + "b" * 56
OTHER_SHA = "d" * 64
CORPUS_IDS = ("D:p1:0", "D:p1:1", "D:p2:0", "D:p2:1", "E:p5:0")


def citation(page: int) -> Citation:
    return Citation(doc_id="D", section="1", pdf_page=page, quote=FRAG_A)


ITEMS = (
    EvalItem(id="Q1", type="fact_lookup", language="en", question="q1", expected="answer",
             gold_answer="a1", citations=(citation(1), citation(2))),
    EvalItem(id="R1", type="trap", language="en", question="r1", expected="refuse",
             gold_answer="refuse"),
    EvalItem(id="Q2", type="concept", language="en", question="q2", expected="answer",
             gold_answer="a2", citations=(citation(2),)),
)
RESOLUTIONS = {
    ("Q1", 0): ("L2", ("D:p1:0", "D:p1:1")),
    ("Q1", 1): ("L1", ("D:p2:1",)),
    ("Q2", 0): ("L1", ("D:p2:0",)),
}


def make_map(**overrides) -> GoldChunkMap:
    base = dict(
        testset_version="v5.3", testset_sha256=SHA_TESTSET, corpus_chunks_sha256=SHA_CORPUS,
        corpus_builder_name=builder_identity.CORPUS_BUILDER_NAME,
        construction_rules_sha256=builder_identity.construction_rules_identity(),
        chunker_config=builder_identity.effective_chunker_config_identity(),
        contracts_version=contracts.CONTRACTS_VERSION,
        mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"], "Q2": ["D:p2:0"]},
        gold_chunk_map_semantics_version=contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION,
    )
    base.update(overrides)
    return GoldChunkMap(**base)


def validate(gold_map, items=ITEMS, corpus=CORPUS_IDS, resolutions=None, corpus_sha=SHA_CORPUS):
    contracts.validate_gold_chunk_map(gold_map, items, corpus, RESOLUTIONS if resolutions is None else resolutions,
                                      current_corpus_chunks_sha256=corpus_sha, builder=builder_identity)


def one_char_changed(value: str) -> str:
    last = value[-1]
    return value[:-1] + ("0" if last != "0" else "1")


class TestValidateGoldChunkMap(unittest.TestCase):

    def assertRejected(self, gold_map=None, **kwargs):
        with self.assertRaises(ContractViolation):
            validate(gold_map or make_map(), **kwargs)

    def test_t2_authoritative_current_identity_map_accepted(self):
        validate(make_map())

    def test_refuse_qid_rejected(self):
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"],
                                              "R1": ["D:p2:0"], "Q2": ["D:p2:0"]}))

    def test_unresolved_citation_is_fail_closed(self):
        for level in ("AMBIGUOUS", "L3", "L4", "FAIL"):
            with self.subTest(level):
                bad = dict(RESOLUTIONS)
                bad[("Q1", 1)] = (level, ())
                self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1"], "Q2": ["D:p2:0"]}),
                                    resolutions=bad)

    def test_unresolved_answer_cannot_be_omitted_or_empty(self):
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"]}))
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"], "Q2": []}))

    def test_missing_citation_resolution_rejected(self):
        bad = dict(RESOLUTIONS)
        del bad[("Q1", 1)]
        self.assertRejected(resolutions=bad)

    def test_level_cardinality(self):
        bad = dict(RESOLUTIONS)
        bad[("Q2", 0)] = ("L1", ("D:p2:0", "D:p2:1"))
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"],
                                              "Q2": ["D:p2:0", "D:p2:1"]}), resolutions=bad)
        bad = dict(RESOLUTIONS)
        bad[("Q1", 0)] = ("L2", ("D:p1:0",))
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p2:1"], "Q2": ["D:p2:0"]}),
                            resolutions=bad)

    def test_duplicate_chunk_ids_rejected(self):
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:0", "D:p1:1", "D:p2:1"],
                                              "Q2": ["D:p2:0"]}))
        self.assertRejected(corpus=CORPUS_IDS + ("D:p1:0",))

    def test_unknown_chunk_rejected(self):
        bad = dict(RESOLUTIONS)
        bad[("Q2", 0)] = ("L1", ("NOPE:p9:0",))
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1"],
                                              "Q2": ["NOPE:p9:0"]}), resolutions=bad)

    def test_ordering_is_enforced(self):
        # 值必须按 corpus 顺序
        self.assertRejected(make_map(mapping={"Q1": ["D:p2:1", "D:p1:0", "D:p1:1"], "Q2": ["D:p2:0"]}))
        # 键必须按评测集顺序
        self.assertRejected(make_map(mapping={"Q2": ["D:p2:0"], "Q1": ["D:p1:0", "D:p1:1", "D:p2:1"]}))

    def test_mapping_must_equal_union_of_formal_covers(self):
        self.assertRejected(make_map(mapping={"Q1": ["D:p1:0", "D:p1:1", "D:p2:1", "E:p5:0"],
                                              "Q2": ["D:p2:0"]}))

    def test_identity_field_formats(self):
        self.assertRejected(make_map(corpus_chunks_sha256=SHA_CORPUS[:8]), corpus_sha=SHA_CORPUS[:8])
        self.assertRejected(make_map(corpus_chunks_sha256=SHA_CORPUS.upper()), corpus_sha=SHA_CORPUS.upper())
        self.assertRejected(make_map(testset_sha256="x" * 64))
        self.assertRejected(make_map(testset_version="5.3"))
        self.assertRejected(make_map(corpus_builder_name=""))
        self.assertRejected(make_map(corpus_builder_name="a/b"))
        self.assertRejected(make_map(chunker_config="target350_overlap60_min120"))
        self.assertRejected(make_map(contracts_version="0.2.0"))

    def test_t1_construction_rules_sha256_is_64_lowercase_hex(self):
        self.assertRegex(builder_identity.construction_rules_identity(), r"^[0-9a-f]{64}$")
        current = builder_identity.construction_rules_identity()
        self.assertRejected(make_map(construction_rules_sha256=current.upper()))
        self.assertRejected(make_map(construction_rules_sha256=current[:-1]))

    def test_t3_builder_name_one_char_changed(self):
        self.assertRejected(make_map(corpus_builder_name=one_char_changed(builder_identity.CORPUS_BUILDER_NAME)))

    def test_t4_chunker_config_one_char_changed(self):
        self.assertRejected(make_map(
            chunker_config=one_char_changed(builder_identity.effective_chunker_config_identity())))

    def test_t5_construction_rules_one_hex_changed(self):
        self.assertRejected(make_map(
            construction_rules_sha256=one_char_changed(builder_identity.construction_rules_identity())))

    def test_t6_previous_semantics_version_rejected(self):
        """0.4.0 起兼容判定看 GoldChunkMap 语义版本，不看整模块 contracts_version（拆分见 versioning 测试）。"""
        self.assertEqual(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, "0.3.1")
        self.assertRejected(make_map(gold_chunk_map_semantics_version="0.3.0"))
        self.assertRejected(make_map(contracts_version="0.3.0", gold_chunk_map_semantics_version=None))

    def test_t7_corpus_sha_mismatch_rejected(self):
        self.assertRejected(make_map(), corpus_sha=OTHER_SHA)
        self.assertRejected(make_map(), corpus_sha="not-a-sha")

    def test_t9_validator_follows_authoritative_chunker_config(self):
        old = make_map()
        with mock.patch.object(contracts, "CHARS_PER_TOKEN_EST", contracts.CHARS_PER_TOKEN_EST + 1):
            self.assertNotEqual(builder_identity.effective_chunker_config_identity(), old.chunker_config)
            self.assertRejected(old)
            validate(make_map())

    def test_t10_validator_rejects_old_map_when_construction_rules_change(self):
        old = make_map()
        with mock.patch.object(kaiva_pdf, "_PARA_SPLIT_RE", re.compile(r"\n")):
            self.assertNotEqual(builder_identity.construction_rules_identity(), old.construction_rules_sha256)
            self.assertRejected(old)
            validate(make_map())


class TestFilenameAndSerialization(unittest.TestCase):

    def test_filename(self):
        gold_map = make_map()
        stem = f"map__ts-v5.3__corpus-c8978777__builder-{builder_identity.CORPUS_BUILDER_NAME}"
        self.assertEqual(gold_map.filename(), stem + ".json")
        self.assertEqual(gold_map.report_filename(), stem + ".report.csv")

    def test_full_corpus_sha_is_serialized(self):
        self.assertIn(f'"corpus_chunks_sha256": "{SHA_CORPUS}"',
                      contracts.serialize_gold_chunk_map(make_map()))

    def test_serialization_is_byte_identical(self):
        first = contracts.serialize_gold_chunk_map(make_map()).encode("utf-8")
        second = contracts.serialize_gold_chunk_map(make_map()).encode("utf-8")
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"}\n"))
        self.assertNotIn(b"built_at", first)
        self.assertIn(b'"construction_rules_sha256"', first)

    def test_non_ascii_kept(self):
        text = contracts.serialize_gold_chunk_map(make_map(mapping={"Q1": ["中:p1:0"]}))
        self.assertIn("中:p1:0", text)


if __name__ == "__main__":
    unittest.main()
