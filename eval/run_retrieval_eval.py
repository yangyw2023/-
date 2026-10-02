"""S8 / M1c 固定-k 检索基线 runner（BM25）。严格执行 experiments/M1c_preregistration.md。

职责只有: 核对冻结输入与协议身份 → 写 run log 身份头 → 用 EvalItem.question 原文调用 search_records(k=20) →
保存完整 top-20 normative JSONL（首行 run identity）→ 独立进程 Run B 逐字节核对 → 从【已保存的】artifact 纯函数重算
冻结指标与 real retrieval packing 测量。不调 BM25 参数、不改 analyzer / query / 指标 / gold 语义。

用法: python3 eval/run_retrieval_eval.py --out-dir experiments/m1c_s8_bm25
      （--emit-normative 只供 Run B 子进程使用: 把 normative 字节写到 stdout，不写任何文件）
输出目录中任一目标文件已存在 → 拒绝运行（不覆盖、不重跑挑结果）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from fractions import Fraction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import (  # noqa: E402
    Chunk, Citation, ContractViolation, EvalItem, GoldChunkMap, Hit, canonical_sha256, pack_context,
    retrieval_record_json_object, validate_eval_item, validate_gold_chunk_map,
)
from components.retrievers import bm25  # noqa: E402
import ingest.builder_identity as builder_identity  # noqa: E402

# ==============================================================================
# 冻结身份（EXPECTED 字面量取自 prereg §1 / §10.2 / §9.1；不由被检文件自算）
# ==============================================================================
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")
TESTSET_PATH = os.path.join(REPO_ROOT, "eval", "testset_v5_3.jsonl")
MAP_PATH = os.path.join(REPO_ROOT, "eval", "gold_chunk_map",
                        "map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json")
REPORT_PATH = MAP_PATH[: -len(".json")] + ".report.csv"
PREREG_PATH = os.path.join(REPO_ROOT, "experiments", "M1c_preregistration.md")
# S4a.9c 已提交的逐 chunk 实测 rendered token（phi4-mini），只用于 packing 的 additive proxy（非冻结测量）。
CHUNK_TOKENS_PATH = os.path.join(REPO_ROOT, "experiments", "gate2_raw", "_s4a9c_final_canonical_chunks.csv")
SEQUENTIAL_WINDOWS_PATH = os.path.join(REPO_ROOT, "experiments", "gate2_raw", "_s4a9c_final_canonical_windows.csv")

EXPECTED_SHA256 = {
    CORPUS_PATH: "c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb",
    TESTSET_PATH: "05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b",
    MAP_PATH: "8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc",
    REPORT_PATH: "f48018cbe88de3d379fb65c17e75e6b8a87eebdc8dd19bdd539356bfff5a2572",
}
EXPECTED_CORPUS_LINES = 3409
EXPECTED_TESTSET_ROWS = 39
EXPECTED_BUILDER = ("kaiva_phase_b_builder_v1", "e89e6f94ec80abdc458622a52587644dc72baaadeb6564606ddc273c2951c5a1",
                    "chars_per_token_est=4;chunk_min_chars=120;chunk_target_tokens=350")
EXPECTED_CONTRACTS_VERSION = "0.4.0"
EXPECTED_GOLD_CHUNK_MAP_SEMANTICS_VERSION = "0.3.1"
EXPECTED_DIGESTS = {
    "retrieval_config_digest": "3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e",
    "query_protocol_digest": "e26afbf39257f8674d98a51541c75ebe2c66a4684ceb83ed3f6a918b290b85a9",
    "metric_protocol_digest": "e78d361fed8c3a945d3333b879df909f2e6a565502f0f0c3c6b3a3b0cf38ef6b",
    "total_order_protocol_digest": "99c87596d8c964a585f0c38c8a312066afa7e3517d9e963c4d6f182ed4e04221",
}
SCHEMA_VERSION = "M1c_S8_retrieval_result_v1"
RUN_IDENTITY_KEYS = ("schema_version", "contracts_version", "contracts_sha256", "code_commit", "corpus_chunks_sha256",
                     "gold_chunk_map_sha256", "testset_sha256", "retrieval_variant", "retrieval_config_digest",
                     "query_protocol_digest", "metric_protocol_digest", "total_order_protocol_digest", "python_version",
                     "unicodedata_unidata_version", "platform")
QUESTION_KEYS = ("question_id", "expected", "type", "language", "gold_count", "empty_result", "max_match_score",
                 "top1_doc_id", "first_gold_rank", "gold_ranks", "hits")
# 冻结指标参数（prereg §7 / metric payload）。
K_SET = (1, 2, 3, 5, 20)
EXCLUDED_FROM_PRIMARY_TRAP = ("TR02",)
PAIR_GOLD_MISMATCH = ("P-drug-freq",)
# Run B 子进程使用的 hash 种子（与 Run A 不同，证明不依赖哈希迭代顺序）。
RUN_B_HASH_SEED = "4242"
# 仅作描述性预算探索（prereg §11 / 本轮 §11）；不是契约，不选择任何 TTFT 目标。
DESCRIPTIVE_BUDGET_GRID = (400, 765, 1170, 1500, 2000, 3000, 4000, 6000)
SEQUENTIAL_SCENARIO = ("CURRENT_EXECUTABLE", "\\n")
TAIL_EXAMPLES = 3

OUT_FILES = {"results": "s8_bm25_results.jsonl", "metrics": "s8_bm25_metrics.json",
             "packing": "s8_bm25_packing.json", "log": "s8_bm25_run.log"}

# 冻结 digest payload（prereg §10.2 的完整内容；runner 构造等价 payload 再与 EXPECTED 比较）。
TOTAL_ORDER_PAYLOAD = {
    "digest_name": "total_order_protocol", "payload_version": 1,
    "executable": "core.contracts.retrieval_order_key",
    "primary_key": "raw_score", "primary_direction": "descending",
    "tie_condition": "exact_equality_of_raw_score",
    "tie_break_key": "corpus_ordinal", "tie_break_direction": "ascending",
    "corpus_ordinal": "zero_based_physical_line_index_in_canonical_corpus_chunks_jsonl",
    "exact_raw_score_representation_for_rrf": "fractions.Fraction",
    "forbidden_tie_breakers": ["chunk_id_lexicographic", "doc_or_page_order", "any_eval_or_gold_information"],
    "truncation": "first_k_of_total_order",
    "sequence_validator": "core.contracts.validate_retrieval_records",
}
QUERY_PAYLOAD = {
    "digest_name": "query_protocol", "payload_version": 1,
    "query_source": "EvalItem.question", "query_string_transform": "identity",
    "translation": False, "llm_rewrite": False, "metadata_augmentation": False,
    "whole_evalitem_as_retrieval_input": False,
    "text_normalization_owner": "retriever_analyzer_applied_symmetrically_to_query_and_document",
    "forbidden_eval_fields": [
        "EvalItem.acceptable_elements", "EvalItem.answer_key", "EvalItem.at_risk", "EvalItem.citations",
        "EvalItem.exclude_from_primary_score", "EvalItem.expected", "EvalItem.gold_answer",
        "EvalItem.known_distractor", "EvalItem.language", "EvalItem.pair_id", "EvalItem.rationale",
        "EvalItem.required_elements", "EvalItem.safety_critical", "EvalItem.source_boundary_ambiguity",
        "EvalItem.trap_subtype", "EvalItem.type", "GoldChunkMap", "GoldChunkMap.report_csv", "gold_chunk_ids",
    ],
    "forbidden_uses": ["boost", "dynamic_k", "filter", "query", "routing", "tie_break"],
    "question_id_use": "join_key_after_ranking_only",
    "items_executed": "all_items_in_testset_file_order_including_refuse",
}
METRIC_PAYLOAD = {
    "digest_name": "metric_protocol", "payload_version": 1,
    "k_set": list(K_SET), "k_max": 20, "saved_ranking_depth": 20,
    "topk_definition": "first_min(k,len(ranking))_records_of_saved_ranking",
    "gold_set": "GoldChunkMap.mapping[question_id]",
    "metrics": {"ANY_GOLD": "1 if len(topk & gold) >= 1 else 0", "GOLD_COVERAGE": "len(topk & gold) / len(gold)",
                "ALL_MAPPED_GOLD": "1 if gold <= topk else 0"},
    "metric_status": {"ALL_MAPPED_GOLD": "strict_map_union_diagnostic_not_answer_completeness"},
    "aggregation": {"primary": "macro_mean_over_answer_items", "micro_over_question_chunk_pairs": "diagnostic_only"},
    "denominators": {"answer_overall": 31, "answer_english": 28, "refuse_executed": 8, "primary_trap": 7,
                     "excluded_from_primary_trap": list(EXCLUDED_FROM_PRIMARY_TRAP)},
    "refuse_item_reporting": "per_item_no_percentage_claims",
    "multilingual": {"non_english_reporting": "per_item", "non_english_languages": ["hi", "tl", "zh"],
                     "pair_comparison": "descriptive_only", "pair_gold_mismatch_must_be_flagged": list(PAIR_GOLD_MISMATCH)},
    "reranker_observation_k": [2, 3], "reranker_decision_threshold": "NOT_FROZEN",
    "known_distractor_rank": "NOT_DEFINED", "s9_calibration_population": "DEFERRED",
}


def file_sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def jline(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


# ==============================================================================
# 身份门
# ==============================================================================

def identity_gate() -> dict:
    """全部冻结身份 EXPECTED == ACTUAL，否则 ContractViolation。返回 run identity（键序冻结）与额外审计身份。"""
    for path, expected in EXPECTED_SHA256.items():
        actual = file_sha256(path)
        if actual != expected:
            raise ContractViolation(f"{path}: sha256 {actual} != frozen {expected}")
    builder = (builder_identity.CORPUS_BUILDER_NAME, builder_identity.construction_rules_identity(),
               builder_identity.effective_chunker_config_identity())
    if builder != EXPECTED_BUILDER:
        raise ContractViolation(f"builder identity {builder} != frozen {EXPECTED_BUILDER}")
    if contracts.CONTRACTS_VERSION != EXPECTED_CONTRACTS_VERSION:
        raise ContractViolation(f"CONTRACTS_VERSION {contracts.CONTRACTS_VERSION} != {EXPECTED_CONTRACTS_VERSION}")
    if contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION != EXPECTED_GOLD_CHUNK_MAP_SEMANTICS_VERSION:
        raise ContractViolation("GOLD_CHUNK_MAP_SEMANTICS_VERSION drift")
    digests = {
        "retrieval_config_digest": canonical_sha256(bm25.BM25_RETRIEVAL_CONFIG_PAYLOAD),
        "query_protocol_digest": canonical_sha256(QUERY_PAYLOAD),
        "metric_protocol_digest": canonical_sha256(METRIC_PAYLOAD),
        "total_order_protocol_digest": canonical_sha256(TOTAL_ORDER_PAYLOAD),
    }
    for name, value in digests.items():
        if value != EXPECTED_DIGESTS[name]:
            raise ContractViolation(f"{name} {value} != prereg {EXPECTED_DIGESTS[name]}")
    dirty = subprocess.run(["git", "-C", REPO_ROOT, "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise ContractViolation(f"tracked 树不干净，code_commit 不能代表运行代码:\n{dirty}")
    code_commit = subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True,
                                 check=True).stdout.strip()
    values = {
        "schema_version": SCHEMA_VERSION, "contracts_version": contracts.CONTRACTS_VERSION,
        "contracts_sha256": file_sha256(os.path.join(REPO_ROOT, "core", "contracts.py")), "code_commit": code_commit,
        "corpus_chunks_sha256": EXPECTED_SHA256[CORPUS_PATH], "gold_chunk_map_sha256": EXPECTED_SHA256[MAP_PATH],
        "testset_sha256": EXPECTED_SHA256[TESTSET_PATH], "retrieval_variant": bm25.HIT_ORIGIN, **digests,
        "python_version": platform.python_version(), "unicodedata_unidata_version": unicodedata.unidata_version,
        "platform": platform.platform(),
    }
    run_identity = {key: values[key] for key in RUN_IDENTITY_KEYS}
    audit = {
        "bm25_implementation_sha256": file_sha256(bm25.__file__),
        "runner_sha256": file_sha256(os.path.abspath(__file__)),
        "prereg_sha256": file_sha256(PREREG_PATH),
        "report_csv_sha256": EXPECTED_SHA256[REPORT_PATH],
        "gold_chunk_map_semantics_version": contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION,
        "builder_identity": list(builder),
        "chunk_token_proxy_csv_sha256": file_sha256(CHUNK_TOKENS_PATH),
        "sequential_windows_csv_sha256": file_sha256(SEQUENTIAL_WINDOWS_PATH),
    }
    return {"run_identity": run_identity, "audit": audit}


# ==============================================================================
# 冻结输入
# ==============================================================================

def load_corpus() -> list[Chunk]:
    """corpus_ordinal = 0-based 物理行序；空行会破坏这一等式 → 拒绝。"""
    with open(CORPUS_PATH, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.split("\n")
    if lines[-1] != "" or any(not line for line in lines[:-1]):
        raise ContractViolation("corpus 含空行或缺末尾换行：corpus_ordinal 与物理行序将不一致")
    chunks = [Chunk(**json.loads(line)) for line in lines[:-1]]
    if len(chunks) != EXPECTED_CORPUS_LINES:
        raise ContractViolation(f"corpus {len(chunks)} 行 != {EXPECTED_CORPUS_LINES}")
    return chunks


def load_testset() -> list[EvalItem]:
    items = []
    with open(TESTSET_PATH, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            record["citations"] = tuple(Citation(**c) for c in record["citations"])
            item = EvalItem(**record)
            validate_eval_item(item)
            items.append(item)
    if len(items) != EXPECTED_TESTSET_ROWS or len({i.id for i in items}) != len(items):
        raise ContractViolation("testset 行数或 id 唯一性不符")
    return items


def load_gold_map(items: list[EvalItem], corpus: list[Chunk]) -> GoldChunkMap:
    with open(MAP_PATH, encoding="utf-8") as handle:
        gold_map = GoldChunkMap(**json.load(handle))
    resolutions = {}
    with open(REPORT_PATH, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            resolutions[(row["question_id"], int(row["citation_index"]))] = (
                row["match_level"], [c for c in row["formal_chunk_ids"].split(";") if c])
    validate_gold_chunk_map(gold_map, items, [c.id for c in corpus], resolutions,
                            current_corpus_chunks_sha256=EXPECTED_SHA256[CORPUS_PATH], builder=builder_identity)
    return gold_map


# ==============================================================================
# 检索（Run A / Run B 共用；只把 question 原文交给检索器）
# ==============================================================================

def run_retrieval(identity: dict, corpus: list[Chunk], items: list[EvalItem], gold_map: GoldChunkMap):
    """返回 (normative 文本, 每题检索耗时秒)。eval 元数据只在排序完成后按 question_id join。"""
    retriever = bm25.BM25Retriever(corpus)
    lines = [jline(identity["run_identity"])]
    latencies = []
    for item in items:
        started = time.perf_counter()
        records = retriever.search_records(item.question, k=contracts.TOP_K_RETRIEVE)
        latencies.append(time.perf_counter() - started)
        gold = gold_map.mapping.get(item.id, [])
        gold_set = set(gold)
        ranks = [rank for rank, record in enumerate(records, start=1) if record.chunk_id in gold_set]
        row = {
            "question_id": item.id, "expected": item.expected, "type": item.type, "language": item.language,
            "gold_count": len(gold), "empty_result": not records,
            "max_match_score": max((r.match_score for r in records), default=None),
            "top1_doc_id": records[0].chunk.doc_id if records else None,
            "first_gold_rank": ranks[0] if ranks else None, "gold_ranks": ranks,
            "hits": [retrieval_record_json_object(r) for r in records],
        }
        lines.append(jline({key: row[key] for key in QUESTION_KEYS}))
    return "".join(lines), latencies


# ==============================================================================
# 有效性检查与指标 / packing（只从已保存 artifact 纯函数重算）
# ==============================================================================

def parse_artifact(text: str) -> tuple[dict, list[dict]]:
    rows = [json.loads(line) for line in text.splitlines()]
    return rows[0], rows[1:]


def validity_checks(identity: dict, rows: list[dict], items: list[EvalItem], corpus: list[Chunk],
                    gold_map: GoldChunkMap) -> dict:
    ids = [c.id for c in corpus]
    numbers = []
    schema_ok = ranks_ok = ordinal_ok = True
    for row in rows:
        schema_ok &= list(row) == list(QUESTION_KEYS)
        hits = row["hits"]
        schema_ok &= all(list(h) == list(contracts.RETRIEVAL_RECORD_JSON_FIELDS) for h in hits)
        ranks_ok &= len(hits) <= contracts.TOP_K_RETRIEVE and len({h["corpus_ordinal"] for h in hits}) == len(hits)
        ranks_ok &= all((-a["raw_score"], a["corpus_ordinal"]) < (-b["raw_score"], b["corpus_ordinal"])
                        for a, b in zip(hits, hits[1:]))
        ordinal_ok &= all(0 <= h["corpus_ordinal"] < len(ids) and ids[h["corpus_ordinal"]] == h["chunk_id"] for h in hits)
        numbers += [h[k] for h in hits for k in ("raw_score", "relevance", "match_score")]
        if row["max_match_score"] is not None:
            numbers.append(row["max_match_score"])
        gold = set(gold_map.mapping.get(row["question_id"], []))
        ranks_ok &= row["gold_ranks"] == [i + 1 for i, h in enumerate(hits) if h["chunk_id"] in gold]
    return {
        "questions_processed": f"{len(rows)}/{len(items)}",
        "question_order_equals_testset": [r["question_id"] for r in rows] == [i.id for i in items],
        "expected_equals_testset": [r["expected"] for r in rows] == [i.expected for i in items],
        "answer_refuse_population": dict(Counter(r["expected"] for r in rows)),
        "run_identity_keys_frozen": list(identity) == list(RUN_IDENTITY_KEYS),
        "schema_valid": schema_ok,
        "ranks_contiguous_no_duplicates_total_order": ranks_ok,
        "corpus_ordinal_and_chunk_id_valid": ordinal_ok,
        "all_numbers_finite": all(isinstance(x, float) and math.isfinite(x) for x in numbers),
        "kinds": sorted({(h["raw_score_kind"], h["relevance_kind"], h["match_score_kind"]) for r in rows for h in r["hits"]}),
    }


def item_metrics(hits: list[dict], gold: list[str]) -> dict:
    out = {}
    for k in K_SET:
        top = {h["chunk_id"] for h in hits[:k]}
        overlap = len(top & set(gold))
        out[k] = {"ANY_GOLD": int(overlap >= 1), "GOLD_COVERAGE": Fraction(overlap, len(gold)),
                  "ALL_MAPPED_GOLD": int(set(gold) <= top), "overlap": overlap}
    return out


def as_float(x) -> float:
    return float(x) if isinstance(x, Fraction) else x


def compute_metrics(rows: list[dict], items: list[EvalItem], gold_map: GoldChunkMap) -> dict:
    by_id = {i.id: i for i in items}
    answer = [r for r in rows if r["expected"] == "answer"]
    per_item = {r["question_id"]: item_metrics(r["hits"], gold_map.mapping[r["question_id"]]) for r in answer}

    def aggregate(subset):
        table = {}
        for metric in ("ANY_GOLD", "GOLD_COVERAGE", "ALL_MAPPED_GOLD"):
            table[metric] = {}
            for k in K_SET:
                total = sum((per_item[r["question_id"]][k][metric] for r in subset), Fraction(0))
                table[metric][f"@{k}"] = {"macro": as_float(total / len(subset)), "numerator": str(total), "n": len(subset)}
        return table

    english = [r for r in answer if r["language"] == "en"]
    total_pairs = sum(r["gold_count"] for r in answer)
    micro = {f"@{k}": {"overlap": sum(per_item[r["question_id"]][k]["overlap"] for r in answer), "pairs": total_pairs,
                       "micro": sum(per_item[r["question_id"]][k]["overlap"] for r in answer) / total_pairs} for k in K_SET}
    ceiling = {f"@{k}": {"ALL_MAPPED_GOLD_structural_ceiling": f"{sum(1 for r in answer if r['gold_count'] <= k)}/{len(answer)}",
                         "unreachable": [r["question_id"] for r in answer if r["gold_count"] > k]} for k in K_SET}
    first = Counter()
    for r in answer:
        rank = r["first_gold_rank"]
        first["none_in_top20" if rank is None else "1" if rank == 1 else "2" if rank == 2 else "3" if rank == 3
              else "4-5" if rank <= 5 else "6-20"] += 1
    per_item_table = [{
        "question_id": r["question_id"], "language": r["language"], "gold_count": r["gold_count"],
        "first_gold_rank": r["first_gold_rank"], "gold_ranks": r["gold_ranks"], "n_hits": len(r["hits"]),
        **{f"COVERAGE@{k}": str(per_item[r["question_id"]][k]["GOLD_COVERAGE"]) for k in K_SET},
        **{f"ALL@{k}": per_item[r["question_id"]][k]["ALL_MAPPED_GOLD"] for k in K_SET},
        "structural_unreachable_ALL": [k for k in K_SET if r["gold_count"] > k],
    } for r in answer]
    non_english = [row for row in per_item_table if row["language"] != "en"]
    pairs = {}
    for item in items:
        if item.pair_id:
            pairs.setdefault(item.pair_id, []).append(item.id)
    pair_rows = [{"pair_id": pid, "members": [{"question_id": q, "language": by_id[q].language,
                  "gold_count": len(gold_map.mapping[q]), "first_gold_rank": next(r for r in rows if r["question_id"] == q)["first_gold_rank"],
                  **{f"COVERAGE@{k}": str(per_item[q][k]["GOLD_COVERAGE"]) for k in K_SET}} for q in members],
                  "pair_gold_mismatch_flag": pid in PAIR_GOLD_MISMATCH,
                  "comparison": "descriptive_only"} for pid, members in sorted(pairs.items())]
    refuse = [{"question_id": r["question_id"], "type": r["type"], "trap_subtype": by_id[r["question_id"]].trap_subtype,
               "excluded_from_primary_trap": r["question_id"] in EXCLUDED_FROM_PRIMARY_TRAP,
               "empty_result": r["empty_result"], "n_hits": len(r["hits"]), "max_match_score": r["max_match_score"],
               "top1_doc_id": r["top1_doc_id"]} for r in rows if r["expected"] == "refuse"]
    return {
        "status": "S8 fixed-k BM25 baseline metrics; recomputed from the saved normative top-20 artifact",
        "ALL_MAPPED_GOLD_status": "STRICT_MAP_UNION_DIAGNOSTIC_WITH_KNOWN_SUPPORTING_CITATION_BIAS (not answer completeness)",
        "CN03_CITATION_LOGIC": "ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW",
        "overall_answer_31": aggregate(answer),
        "english_answer_28": aggregate(english),
        "micro_over_question_chunk_pairs_diagnostic": micro,
        "structural_ceilings": ceiling,
        "first_gold_rank_distribution_answer_31": dict(sorted(first.items())),
        "non_english_per_item": non_english,
        "pairs_descriptive": pair_rows,
        "refuse_trap_per_item": refuse,
        "primary_trap_denominator": len([r for r in refuse if not r["excluded_from_primary_trap"]]),
        "empty_result_question_ids": [r["question_id"] for r in rows if r["empty_result"]],
        "per_item_answer": per_item_table,
        "known_distractor_rank": "NOT_DEFINED",
    }


def compute_packing(rows: list[dict], corpus: list[Chunk], gold_map: GoldChunkMap) -> dict:
    with open(CHUNK_TOKENS_PATH, encoding="utf-8") as handle:
        rendered = {r["chunk_id"]: int(r["actual_rendered_tokens"]) for r in csv.DictReader(handle)}
    budget, max_k = contracts.CONTEXT_PACK_BUDGET_TOKENS, contracts.TOP_K_CONTEXT
    reserve, prompt_max = contracts.PROMPT_OVERHEAD_RESERVE_TOKENS, contracts.MAX_PROMPT_TOKENS

    def pack(row, max_tokens, max_chunks):
        hits = [Hit(chunk=corpus[h["corpus_ordinal"]], relevance=h["relevance"], match_score=h["match_score"],
                    origin=bm25.HIT_ORIGIN) for h in row["hits"]]
        return pack_context(hits, max_tokens=max_tokens, max_chunks=max_chunks)

    windows = []
    for row in rows:
        if not row["hits"]:
            continue
        packed = pack(row, budget, max_k)
        est = sum(h.chunk.est_prompt_tokens() for h in packed)
        proxy = sum(rendered[h.chunk.id] for h in packed)
        windows.append({
            "question_id": row["question_id"], "expected": row["expected"], "n_hits": len(row["hits"]),
            "realized_k": len(packed), "stopped_by": "max_chunks" if len(packed) == max_k else
            ("ranking_exhausted" if len(packed) == len(row["hits"]) else "budget"),
            "first_hit_alone_over_budget": est > budget and len(packed) == 1,
            "est_context_tokens": est, "proxy_actual_context_tokens": proxy,
            "est_overbudget": est + reserve > prompt_max, "proxy_overbudget": proxy + reserve > prompt_max,
            "estimator_safe_but_proxy_over": est <= budget and proxy + reserve > prompt_max,
            "packed_ids": [h.chunk.id for h in packed],
        })
    answer = [w for w in windows if w["expected"] == "answer"]
    answer_all = [r for r in rows if r["expected"] == "answer"]

    def packed_gold(max_tokens, max_chunks):
        any_, cov, all_, ks = Fraction(0), Fraction(0), Fraction(0), []
        for r in answer_all:
            gold = set(gold_map.mapping[r["question_id"]])
            ids = {h.chunk.id for h in pack(r, max_tokens, max_chunks)} if r["hits"] else set()
            ks.append(len(ids))
            any_ += int(bool(ids & gold)); cov += Fraction(len(ids & gold), len(gold)); all_ += int(gold <= ids)
        n = len(answer_all)
        return {"ANY_GOLD": float(any_ / n), "GOLD_COVERAGE": float(cov / n), "ALL_MAPPED_GOLD": float(all_ / n),
                "mean_realized_k": sum(ks) / n, "n": n}

    with open(SEQUENTIAL_WINDOWS_PATH, encoding="utf-8") as handle:
        seq = [r for r in csv.DictReader(handle) if (r["scenario"], r["sep"]) == SEQUENTIAL_SCENARIO]
    seq_k = Counter(int(r["window_k"]) for r in seq)
    tail = sorted(windows, key=lambda w: (-w["proxy_actual_context_tokens"], w["question_id"]))[:TAIL_EXAMPLES]
    return {
        "status": "real retrieval-window measurement on saved top-20 (current executable packing contract); descriptive",
        "packing_contract": {"max_tokens": budget, "max_chunks": max_k, "reserve": reserve, "MAX_PROMPT_TOKENS": prompt_max,
                             "function": "core.contracts.pack_context (relevance prefix)"},
        "actual_tokens": "NOT_MEASURED_WITH_TOKENIZER (M1c prereg freezes no tokenizer protocol); proxy = sum of S4a.9c "
                         "measured per-chunk actual_rendered_tokens, excludes separators (S4a.9c sep increment 0-1 token "
                         "per join, so proxy undercounts joint tokenization by <= realized_k - 1)",
        "windows_with_hits": len(windows),
        "realized_k_distribution_all": dict(sorted(Counter(w["realized_k"] for w in windows).items())),
        "realized_k_distribution_answer": dict(sorted(Counter(w["realized_k"] for w in answer).items())),
        "stopped_by": dict(sorted(Counter(w["stopped_by"] for w in windows).items())),
        "first_hit_alone_over_budget": [w["question_id"] for w in windows if w["first_hit_alone_over_budget"]],
        "est_context_tokens": {"min": min(w["est_context_tokens"] for w in windows),
                               "median": sorted(w["est_context_tokens"] for w in windows)[len(windows) // 2],
                               "max": max(w["est_context_tokens"] for w in windows)},
        "proxy_actual_context_tokens": {"min": min(w["proxy_actual_context_tokens"] for w in windows),
                                        "median": sorted(w["proxy_actual_context_tokens"] for w in windows)[len(windows) // 2],
                                        "max": max(w["proxy_actual_context_tokens"] for w in windows)},
        "est_overbudget_count": sum(w["est_overbudget"] for w in windows),
        "proxy_overbudget_count": sum(w["proxy_overbudget"] for w in windows),
        "estimator_safe_but_proxy_over": [w["question_id"] for w in windows if w["estimator_safe_but_proxy_over"]],
        "packed_gold_current_contract_answer_31": packed_gold(budget, max_k),
        "tail_examples_by_proxy_tokens": [{k: w[k] for k in ("question_id", "realized_k", "est_context_tokens",
                                           "proxy_actual_context_tokens", "proxy_overbudget")} for w in tail],
        "sequential_window_comparison": {
            "source": "experiments/gate2_raw/_s4a9c_final_canonical_windows.csv CURRENT_EXECUTABLE sep=\\n (corpus-order windows)",
            "n_windows": len(seq), "realized_k_distribution": dict(sorted(seq_k.items())),
            "overbudget_rate_actual": sum(int(r["overbudget"]) for r in seq) / len(seq),
            "real_retrieval_n_windows": len(windows),
            "real_retrieval_proxy_overbudget_rate": sum(w["proxy_overbudget"] for w in windows) / len(windows),
        },
        "descriptive_budget_table_not_a_contract": [
            {"budget_tokens": b, "max_chunks": mc, **packed_gold(b, mc)}
            for mc in (contracts.TOP_K_CONTEXT, contracts.TOP_K_RETRIEVE) for b in DESCRIPTIVE_BUDGET_GRID],
        "per_window": windows,
    }


# ==============================================================================
# 主流程
# ==============================================================================

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir")
    parser.add_argument("--emit-normative", action="store_true")
    args = parser.parse_args(argv)
    identity = identity_gate()
    if args.emit_normative:
        corpus, items = load_corpus(), load_testset()
        text, _ = run_retrieval(identity, corpus, items, load_gold_map(items, corpus))
        sys.stdout.buffer.write(text.encode("utf-8"))
        return 0
    if not args.out_dir:
        raise SystemExit("--out-dir 必填")
    out = {name: os.path.join(args.out_dir, fname) for name, fname in OUT_FILES.items()}
    os.makedirs(args.out_dir, exist_ok=True)
    existing = [p for p in out.values() if os.path.exists(p)]
    if existing:
        raise ContractViolation(f"拒绝覆盖已有 artifact（不重跑挑结果）: {existing}")
    log = open(out["log"], "w", encoding="utf-8")
    log.write(jline({"event": "identity_header_before_results", "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     **identity}))
    log.flush()
    corpus, items = load_corpus(), load_testset()
    gold_map = load_gold_map(items, corpus)
    text, latencies = run_retrieval(identity, corpus, items, gold_map)
    with open(out["results"], "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    log.write(jline({"event": "run_a_written", "results_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     "latency_s": {"total": round(sum(latencies), 4), "max": round(max(latencies), 4),
                                   "median": round(sorted(latencies)[len(latencies) // 2], 4)}}))
    env = dict(os.environ, PYTHONHASHSEED=RUN_B_HASH_SEED)
    run_b = subprocess.run([sys.executable, os.path.abspath(__file__), "--emit-normative"], capture_output=True,
                           env=env, cwd=REPO_ROOT)
    run_b_ok = run_b.returncode == 0 and run_b.stdout == text.encode("utf-8")
    log.write(jline({"event": "run_b_determinism", "pythonhashseed": RUN_B_HASH_SEED, "returncode": run_b.returncode,
                     "run_b_sha256": hashlib.sha256(run_b.stdout).hexdigest(), "byte_identical": run_b_ok}))
    log.flush()
    if not run_b_ok:
        log.write(jline({"event": "BASELINE_VALIDITY", "value": "INVALID", "reason": "Run A != Run B"}))
        log.close()
        raise ContractViolation("Run A 与 Run B normative artifact 不逐字节相同（prereg §9.2）→ 结果不得使用")
    with open(out["results"], encoding="utf-8") as handle:
        run_identity, rows = parse_artifact(handle.read())
    checks = validity_checks(run_identity, rows, items, corpus, gold_map)
    metrics = compute_metrics(rows, items, gold_map)
    packing = compute_packing(rows, corpus, gold_map)
    for name, payload in (("metrics", {"validity_checks": checks, **metrics}), ("packing", packing)):
        with open(out[name], "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    valid = all(v for k, v in checks.items() if isinstance(v, bool))
    log.write(jline({"event": "artifacts", **{name: {"sha256": file_sha256(out[name])} for name in ("results", "metrics", "packing")}}))
    log.write(jline({"event": "BASELINE_VALIDITY", "value": "VALID" if valid else "INVALID", "checks": checks}))
    log.close()
    print(json.dumps({"validity": "VALID" if valid else "INVALID", "checks": checks}, ensure_ascii=False))
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
