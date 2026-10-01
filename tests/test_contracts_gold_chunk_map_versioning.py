"""CONTRACTS_VERSION / GOLD_CHUNK_MAP_SEMANTICS_VERSION 拆分（contracts 0.4.0）的测试。

人工裁决 CONTRACT_VERSION_DECISION = SPLIT（DECISIONS 2026-10-01 final protocol closure）:
失效由实际依赖决定。GoldChunkMap 的兼容判定只看 GoldChunkMap 语义版本；拆分前 schema 的映射
（有 contracts_version、无 gold_chunk_map_semantics_version）按 documented legacy 规则解释。

两层保护（编号对应 DECISIONS 2026-10-01 final protocol closure 的 T-V1–T-V10）:
  Layer 1  冻结 artifact 回归锚（T-V1–T-V3）: canonical 映射的字节与 sha 不变，并在 0.4.0 下仍被接受。
           EXPECTED sha 取自 DECISIONS 2026-09-28 Formal S6 条目的字面量，不由被测文件自算。
  Layer 2  语义兼容（T-V4–T-V10）: 合成映射，不依赖任何具体 artifact sha。

运行: python3 -m unittest tests.test_contracts_gold_chunk_map_versioning -v
"""

from __future__ import annotations

import ast
import csv
import hashlib
import inspect
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import Chunk, Citation, ContractViolation, EvalItem, GoldChunkMap
from ingest import builder_identity
import scripts.resolve_gold_chunks as rgc
from tests.test_contracts_gold_chunk_map import make_map, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL_MAP_RELPATH = "eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json"
CANONICAL_MAP_PATH = os.path.join(REPO_ROOT, CANONICAL_MAP_RELPATH)
CANONICAL_REPORT_PATH = CANONICAL_MAP_PATH[: -len(".json")] + ".report.csv"
TESTSET_PATH = os.path.join(REPO_ROOT, "eval", "testset_v5_3.jsonl")
# canonical 语料被 gitignore；不在场时只跳过需要它的 T-V3 / T-V8 真实映射子项。
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")

# 冻结值（DECISIONS 2026-09-28「[L1] Canonical GoldChunkMap identity」）。
EXPECTED_CANONICAL_MAP_SHA256 = "8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc"
EXPECTED_CANONICAL_MAP_BYTES = 2026
EXPECTED_CORPUS_SHA256 = "c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb"

# 合成"未来整模块版本"：只用于证明兼容判定不看 CONTRACTS_VERSION。
SIMULATED_FUTURE_CONTRACTS_VERSION = "0.5.0"


def read_canonical_bytes() -> bytes:
    with open(CANONICAL_MAP_PATH, "rb") as handle:
        return handle.read()


def parse_map(raw: bytes) -> GoldChunkMap:
    return GoldChunkMap(**json.loads(raw.decode("utf-8")))


def validate_canonical(gold_map: GoldChunkMap) -> None:
    """用真实评测集、真实 report.csv 与 canonical 语料校验映射；语料哈希用 EXPECTED 字面量。"""
    items = []
    with open(TESTSET_PATH, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            record["citations"] = tuple(Citation(**c) for c in record["citations"])
            items.append(EvalItem(**record))
    with open(CORPUS_PATH, "rb") as handle:
        corpus_bytes = handle.read()
    if hashlib.sha256(corpus_bytes).hexdigest() != EXPECTED_CORPUS_SHA256:
        raise AssertionError("canonical 语料字节与冻结 sha 不符")
    corpus_ids = [Chunk(**json.loads(line)).id for line in corpus_bytes.decode("utf-8").splitlines()]
    resolutions = {}
    with open(CANONICAL_REPORT_PATH, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            resolutions[(row["question_id"], int(row["citation_index"]))] = (
                row["match_level"], [c for c in row["formal_chunk_ids"].split(";") if c])
    contracts.validate_gold_chunk_map(gold_map, items, corpus_ids, resolutions,
                                      current_corpus_chunks_sha256=EXPECTED_CORPUS_SHA256,
                                      builder=builder_identity)


def pre_split_versions_from_git_history():
    """从 core/contracts.py 的每个历史版本机械恢复: GoldChunkMap 有 contracts_version、无语义版本字段的
    CONTRACTS_VERSION 集合。没有 .git 时返回 None。"""
    log = subprocess.run(["git", "-C", REPO_ROOT, "log", "--format=%H", "--", "core/contracts.py"],
                         capture_output=True, text=True)
    if log.returncode != 0:
        return None
    found = set()
    for commit in log.stdout.split():
        shown = subprocess.run(["git", "-C", REPO_ROOT, "show", f"{commit}:core/contracts.py"],
                               capture_output=True, text=True, check=True).stdout
        tree = ast.parse(shown)
        version = next((n.value.value for n in tree.body if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], "id", "") == "CONTRACTS_VERSION"), None)
        gold = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldChunkMap"), None)
        names = {n.target.id for n in gold.body if isinstance(n, ast.AnnAssign)} if gold else set()
        if "contracts_version" in names and "gold_chunk_map_semantics_version" not in names:
            found.add(version)
    return found


def legacy_map(contracts_version: str) -> GoldChunkMap:
    """拆分前 schema 的合成映射: 有 contracts_version，无 gold_chunk_map_semantics_version。"""
    return make_map(contracts_version=contracts_version, gold_chunk_map_semantics_version=None)


def future_map(semantics_version: str, contracts_version: str = contracts.CONTRACTS_VERSION) -> GoldChunkMap:
    return make_map(contracts_version=contracts_version, gold_chunk_map_semantics_version=semantics_version)


# ==============================================================================
# Layer 1 —— 冻结 artifact 回归锚
# ==============================================================================

class TestLayer1CanonicalFrozenMap(unittest.TestCase):

    def test_tv1_canonical_bytes_unchanged(self):
        raw = read_canonical_bytes()
        self.assertEqual(len(raw), EXPECTED_CANONICAL_MAP_BYTES)
        gold_map = parse_map(raw)
        self.assertIsNone(gold_map.gold_chunk_map_semantics_version)
        self.assertNotIn(b"gold_chunk_map_semantics_version", raw)
        # 0.4.0 的序列化对拆分前 schema 逐字节复现原文件（新字段为 None 时省略）。
        self.assertEqual(contracts.serialize_gold_chunk_map(gold_map).encode("utf-8"), raw)
        head = subprocess.run(["git", "-C", REPO_ROOT, "show", f"HEAD:{CANONICAL_MAP_RELPATH}"], capture_output=True)
        if head.returncode == 0:   # git archive 导出的树没有 .git
            self.assertEqual(head.stdout, raw)

    def test_tv2_canonical_sha_unchanged(self):
        self.assertEqual(hashlib.sha256(read_canonical_bytes()).hexdigest(), EXPECTED_CANONICAL_MAP_SHA256)

    @unittest.skipUnless(os.path.isfile(CORPUS_PATH), "canonical corpus 不在场（gitignored）")
    def test_tv3_canonical_legacy_map_accepted_under_0_4_0(self):
        self.assertEqual(contracts.CONTRACTS_VERSION, "0.4.0")
        gold_map = parse_map(read_canonical_bytes())
        self.assertEqual(gold_map.contracts_version, "0.3.1")
        self.assertNotEqual(gold_map.contracts_version, contracts.CONTRACTS_VERSION)
        validate_canonical(gold_map)


# ==============================================================================
# Layer 2 —— 语义兼容（合成映射）
# ==============================================================================

class TestLayer2LegacyFallback(unittest.TestCase):

    def test_pre_split_set_is_the_frozen_history(self):
        self.assertEqual(contracts.GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS, frozenset({"0.2.0", "0.3.0", "0.3.1"}))
        self.assertNotIn(contracts.CONTRACTS_VERSION, contracts.GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS)
        recovered = pre_split_versions_from_git_history()
        if recovered is not None:   # git archive 导出的树没有 .git
            self.assertEqual(recovered, set(contracts.GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS))

    def test_tv4_legacy_without_field_contracts_0_3_1_accepted(self):
        validate(legacy_map("0.3.1"))

    def test_legacy_incompatible_semantic_version_rejected(self):
        for version in ("0.3.0", "0.2.0"):
            with self.subTest(version), self.assertRaises(ContractViolation):
                validate(legacy_map(version))

    def test_tv5_post_split_missing_field_rejected(self):
        """拆分后生成却缺字段：legacy 规则不适用（contracts_version 不在拆分前闭集）。"""
        for version in (contracts.CONTRACTS_VERSION, SIMULATED_FUTURE_CONTRACTS_VERSION, "0.2.0-draft"):
            with self.subTest(version), self.assertRaises(ContractViolation):
                validate(legacy_map(version))

    def test_tv10_version_collision_cannot_use_legacy_fallback(self):
        """闭集的作用: 若将来语义版本恰好取了某个拆分后的整模块版本号，缺字段的拆分后映射
        也不得借 legacy 规则蒙混通过（否则只靠"两个数相等"就被接受）。"""
        with mock.patch.object(contracts, "GOLD_CHUNK_MAP_SEMANTICS_VERSION", SIMULATED_FUTURE_CONTRACTS_VERSION):
            with self.assertRaises(ContractViolation):
                validate(legacy_map(SIMULATED_FUTURE_CONTRACTS_VERSION))
            validate(future_map(SIMULATED_FUTURE_CONTRACTS_VERSION, SIMULATED_FUTURE_CONTRACTS_VERSION))

    def test_legacy_serialization_omits_field(self):
        text = contracts.serialize_gold_chunk_map(legacy_map("0.3.1"))
        self.assertNotIn("gold_chunk_map_semantics_version", text)


class TestLayer2ExplicitSemanticsVersion(unittest.TestCase):

    def test_tv6_explicit_matching_version_accepted(self):
        validate(future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION))
        validate(future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, SIMULATED_FUTURE_CONTRACTS_VERSION))

    def test_tv7_explicit_mismatch_rejected(self):
        for version in ("0.3.0", "0.3.2", "0.4.0"):
            with self.subTest(version), self.assertRaises(ContractViolation):
                validate(future_map(version))

    def test_explicit_field_with_pre_split_contracts_version_rejected(self):
        """拆分前不可能写出该字段；这种组合只能是手工拼接，拒绝。"""
        for version in sorted(contracts.GOLD_CHUNK_MAP_PRE_SPLIT_CONTRACTS_VERSIONS):
            with self.subTest(version), self.assertRaises(ContractViolation):
                validate(future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, version))

    def test_malformed_versions_rejected(self):
        for bad in ("", "0.3", "v0.3.1", "0.3.1 ", "00.3.1", 31):
            with self.subTest(semantics=bad), self.assertRaises(ContractViolation):
                validate(future_map(bad))
            with self.subTest(contracts=bad), self.assertRaises(ContractViolation):
                validate(future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, bad))

    def test_future_serialization_round_trips(self):
        gold_map = future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION)
        text = contracts.serialize_gold_chunk_map(gold_map)
        payload = json.loads(text)
        self.assertEqual(list(payload)[-1], "gold_chunk_map_semantics_version")
        self.assertEqual(contracts.serialize_gold_chunk_map(GoldChunkMap(**payload)), text)


class TestLayer2RetrievalOnlyChange(unittest.TestCase):

    def test_tv8_whole_module_bump_does_not_change_compatibility(self):
        with mock.patch.object(contracts, "CONTRACTS_VERSION", SIMULATED_FUTURE_CONTRACTS_VERSION):
            validate(legacy_map("0.3.1"))
            validate(future_map(contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION, "0.4.0"))
            if os.path.isfile(CORPUS_PATH):
                validate_canonical(parse_map(read_canonical_bytes()))

    def test_tv8_semantics_bump_does_change_compatibility(self):
        with mock.patch.object(contracts, "GOLD_CHUNK_MAP_SEMANTICS_VERSION", "0.3.2"):
            with self.assertRaises(ContractViolation):
                validate(legacy_map("0.3.1"))
            with self.assertRaises(ContractViolation):
                validate(future_map("0.3.1"))

    def test_tv8_validator_never_reads_whole_module_version(self):
        for func in (contracts.validate_gold_chunk_map, contracts._gold_chunk_map_semantics_version_of):
            names = {n.id for n in ast.walk(ast.parse(inspect.getsource(func))) if isinstance(n, ast.Name)}
            self.assertNotIn("CONTRACTS_VERSION", names, func.__name__)


class TestTV9ResolverWritesAuthoritativeSemanticsVersion(unittest.TestCase):

    def build(self):
        return rgc.identity_map(TESTSET_PATH, "a" * 64, "b" * 64, {})

    def test_identity_map_writes_both_versions(self):
        gold_map = self.build()
        self.assertEqual(gold_map.gold_chunk_map_semantics_version, contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION)
        self.assertEqual(gold_map.contracts_version, contracts.CONTRACTS_VERSION)
        self.assertNotEqual(gold_map.gold_chunk_map_semantics_version, gold_map.contracts_version)

    def test_identity_map_reads_the_authoritative_constant_at_call_time(self):
        """resolver 不钉住字面量，也不把整模块版本冒充语义版本。"""
        with mock.patch.object(contracts, "GOLD_CHUNK_MAP_SEMANTICS_VERSION", "9.9.9"):
            self.assertEqual(self.build().gold_chunk_map_semantics_version, "9.9.9")
        with mock.patch.object(contracts, "CONTRACTS_VERSION", "8.8.8"):
            gold_map = self.build()
            self.assertEqual(gold_map.contracts_version, "8.8.8")
            self.assertEqual(gold_map.gold_chunk_map_semantics_version, contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION)


if __name__ == "__main__":
    unittest.main()
