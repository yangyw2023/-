"""S8 / M1c 固定-k 检索基线 runner（hybrid）。严格执行 experiments/M1c_preregistration.md §16（及共享的 §2–§9）。

不调用任何检索器、不访问 Ollama：直接读取已提交的 BM25 / vector formal top-20 artifact，按 §16.1 校验并无损重建为
RetrievalResultRecord，再用 components.retrievers.hybrid.fuse 融合。question_id 只用于对齐两路已保存的排序（join key），不进入融合计算。
复用 eval/run_retrieval_eval.py（已提交）的冻结输入加载、共享身份门、有效性检查与指标纯函数。

用法: python3 eval/run_hybrid_eval.py --out-dir experiments/m1c_s8_hybrid
      （--emit-normative 只供 Run B 子进程使用: 把 normative 字节写到 stdout，不写任何文件）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from fractions import Fraction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import (  # noqa: E402
    ContractViolation, RetrievalResultRecord, canonical_sha256, retrieval_record_json_object, validate_retrieval_records,
)
from components.retrievers import hybrid  # noqa: E402
from eval import run_retrieval_eval as base  # noqa: E402

# ==============================================================================
# 冻结身份（EXPECTED 取自 prereg §16 / DECISIONS component closure；commit 内文件 sha 取自该 commit 的 blob）
# ==============================================================================
EXPECTED_HYBRID_RETRIEVAL_CONFIG_DIGEST = "97ddd20aa9f4e837f188c7c6eb29c5eaa400544b5b2eff367c8e0eed4425e621"
HYBRID_PROTOCOL_COMMIT = "a0a92414e543b868f66bc016ec954c70b5420766"
HYBRID_IMPLEMENTATION_COMMIT = "1e07e1b08d58d9980b7c6cee3fd7b5d389e0b26d"
PREREG_REL_PATH = "experiments/M1c_preregistration.md"
HYBRID_REL_PATH = "components/retrievers/hybrid.py"
ROUTE_INPUTS = {
    "bm25": {"path": "experiments/m1c_s8_bm25/s8_bm25_results.jsonl",
             "sha256": "9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8",
             "code_commit": "3511aa072be3b6a1e3551017418ebda8e5d5ed8d",
             "retrieval_config_digest": "3069070aad6aec04259313c0242a251c191808f53cde574cf6534529034b8a2e"},
    "vector": {"path": "experiments/m1c_s8_vector/s8_vector_results.jsonl",
               "sha256": "0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073",
               "code_commit": "1a7c6749ba844e33f3237625c4e21f18c3d77c1e",
               "retrieval_config_digest": "c9c3868cf19a77d2b88a705580367ba933930af28c265887d2da6aad7a0e7343"},
}
# 两路 run identity 中必须彼此相同、且等于本次运行冻结值的键（§16.1）。
SHARED_ROUTE_IDENTITY_KEYS = ("schema_version", "contracts_version", "contracts_sha256", "corpus_chunks_sha256",
                              "gold_chunk_map_sha256", "testset_sha256", "query_protocol_digest", "metric_protocol_digest",
                              "total_order_protocol_digest")
# unweighted RRF：实现中不存在权重参数；此值只作 run identity / digest 记录（H1）。
ROUTE_WEIGHTS = {"bm25": 1, "vector": 1}
HYBRID_KEYS = ("hybrid_protocol_commit", "hybrid_implementation_commit", "hybrid_implementation_sha256", "prereg_sha256",
               "bm25_input_results_sha256", "bm25_input_code_commit", "bm25_retrieval_config_digest",
               "vector_input_results_sha256", "vector_input_code_commit", "vector_retrieval_config_digest",
               "rrf_k", "route_fusion_depth", "route_weights")
RUN_IDENTITY_KEYS = base.RUN_IDENTITY_KEYS + HYBRID_KEYS
QUESTION_KEYS = base.QUESTION_KEYS + ("route_diagnostics",)
RAW_SCORE_RE = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")
OUT_FILES = {"results": "s8_hybrid_results.jsonl", "metrics": "s8_hybrid_metrics.json", "log": "s8_hybrid_run.log"}

# prereg §16.5 冻结的 hybrid retrieval_config payload。
RETRIEVAL_CONFIG_PAYLOAD = {
    "digest_name": "retrieval_config", "payload_version": 1,
    "retrieval_variant": hybrid.HIT_ORIGIN,
    "fusion": "unweighted_reciprocal_rank_fusion",
    "routes": list(hybrid.ROUTES),
    "route_inputs": "frozen_component_top20_artifacts_no_re_retrieval",
    "route_retrieval_config_digests": {name: spec["retrieval_config_digest"] for name, spec in ROUTE_INPUTS.items()},
    "route_weights": ROUTE_WEIGHTS,
    "rrf_k": hybrid.RRF_K,
    "route_rank": "1_based_position_in_route_saved_ranking",
    "route_fusion_depth": {"bm25": hybrid.BM25_FUSION_DEPTH, "vector": hybrid.VECTOR_FUSION_DEPTH},
    "short_route": "use_all_returned_records_no_padding",
    "candidate_set": "union_of_route_top_depth_records",
    "raw_score": "sum_over_present_routes_of_Fraction(1, rrf_k + route_rank)",
    "raw_score_representation": "fractions.Fraction",
    "raw_score_serialization": "p/q",
    "raw_score_kind": hybrid.RAW_SCORE_KIND,
    "relevance": "float(raw_score / Fraction(2, 61))",
    "relevance_kind": hybrid.RELEVANCE_KIND,
    "match_score": "max(saved_match_score_of_present_routes)",
    "match_score_kind": hybrid.MATCH_SCORE_KIND,
    "missing_route_rescoring": False,
    "total_order": "core.contracts.retrieval_order_key(raw_score, corpus_ordinal)",
    "k": contracts.TOP_K_RETRIEVE,
    "route_diagnostics": "per_hit_present_rank_raw_score_match_score_for_each_route",
}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", REPO_ROOT, *args], capture_output=True)


def committed_blob_sha256(commit: str, rel_path: str) -> str:
    proc = git("show", f"{commit}:{rel_path}")
    if proc.returncode != 0:
        raise ContractViolation(f"{commit}:{rel_path} 不存在: {proc.stderr.decode('utf-8', 'replace')}")
    return hashlib.sha256(proc.stdout).hexdigest()


def identity_gate() -> dict:
    """冻结身份全部 EXPECTED == ACTUAL，否则 ContractViolation。返回 run identity（键序冻结）与审计身份。"""
    shared = base.identity_gate()                       # corpus / testset / map / builder / contracts / clean tree / 3 共享 digest
    digest = canonical_sha256(RETRIEVAL_CONFIG_PAYLOAD)
    if digest != EXPECTED_HYBRID_RETRIEVAL_CONFIG_DIGEST:
        raise ContractViolation(f"hybrid retrieval_config_digest {digest} != prereg {EXPECTED_HYBRID_RETRIEVAL_CONFIG_DIGEST}")
    for commit in (HYBRID_PROTOCOL_COMMIT, HYBRID_IMPLEMENTATION_COMMIT):
        if git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
            raise ContractViolation(f"{commit} 不是 HEAD 的祖先")
    hybrid_sha = base.file_sha256(hybrid.__file__)
    if hybrid_sha != committed_blob_sha256(HYBRID_IMPLEMENTATION_COMMIT, HYBRID_REL_PATH):
        raise ContractViolation("hybrid.py 与 implementation commit 中的字节不同")
    prereg_sha = base.file_sha256(base.PREREG_PATH)
    if prereg_sha != committed_blob_sha256(HYBRID_PROTOCOL_COMMIT, PREREG_REL_PATH):
        raise ContractViolation("prereg 与 hybrid protocol commit 中的字节不同")
    for name, spec in ROUTE_INPUTS.items():
        actual = base.file_sha256(os.path.join(REPO_ROOT, spec["path"]))
        if actual != spec["sha256"]:
            raise ContractViolation(f"{name} 输入 artifact sha {actual} != frozen {spec['sha256']}")
    values = {**shared["run_identity"], "retrieval_variant": hybrid.HIT_ORIGIN, "retrieval_config_digest": digest,
              "hybrid_protocol_commit": HYBRID_PROTOCOL_COMMIT, "hybrid_implementation_commit": HYBRID_IMPLEMENTATION_COMMIT,
              "hybrid_implementation_sha256": hybrid_sha, "prereg_sha256": prereg_sha,
              "rrf_k": hybrid.RRF_K, "route_fusion_depth": RETRIEVAL_CONFIG_PAYLOAD["route_fusion_depth"],
              "route_weights": ROUTE_WEIGHTS}
    for name, spec in ROUTE_INPUTS.items():
        values.update({f"{name}_input_results_sha256": spec["sha256"], f"{name}_input_code_commit": spec["code_commit"],
                       f"{name}_retrieval_config_digest": spec["retrieval_config_digest"]})
    audit = {**shared["audit"], "hybrid_runner_sha256": base.file_sha256(os.path.abspath(__file__))}
    return {"run_identity": {key: values[key] for key in RUN_IDENTITY_KEYS}, "audit": audit}


# ==============================================================================
# 两路冻结输入（§16.1）
# ==============================================================================

def load_route(name: str, chunks, items, run_identity: dict) -> dict[str, list[RetrievalResultRecord]]:
    """读取一路 component artifact 并无损重建记录；任何不兼容 → ContractViolation。返回 {question_id: 该路记录序列}。"""
    spec = ROUTE_INPUTS[name]
    with open(os.path.join(REPO_ROOT, spec["path"]), encoding="utf-8") as handle:
        route_identity, rows = base.parse_artifact(handle.read())
    expected = {"retrieval_variant": name, "code_commit": spec["code_commit"],
                "retrieval_config_digest": spec["retrieval_config_digest"],
                **{key: run_identity[key] for key in SHARED_ROUTE_IDENTITY_KEYS}}
    mismatched = [key for key, value in expected.items() if route_identity.get(key) != value]
    if mismatched:
        raise ContractViolation(f"{name} artifact 身份不兼容: {mismatched}")
    if [row["question_id"] for row in rows] != [item.id for item in items]:
        raise ContractViolation(f"{name} artifact 的题目序列与冻结评测集不同")
    ids = [c.id for c in chunks]
    out = {}
    for row in rows:
        records = []
        for hit in row["hits"]:
            ordinal = hit["corpus_ordinal"]
            if not (isinstance(ordinal, int) and 0 <= ordinal < len(chunks)) or chunks[ordinal].id != hit["chunk_id"]:
                raise ContractViolation(f"{name} {row['question_id']}: corpus_ordinal / chunk_id 不对应")
            record = RetrievalResultRecord(
                chunk=chunks[ordinal], corpus_ordinal=ordinal,
                raw_score=hit["raw_score"], raw_score_kind=hit["raw_score_kind"],
                relevance=hit["relevance"], relevance_kind=hit["relevance_kind"],
                match_score=hit["match_score"], match_score_kind=hit["match_score_kind"])
            rebuilt = retrieval_record_json_object(record)
            if list(hit) != list(rebuilt) or hit != rebuilt:
                raise ContractViolation(f"{name} {row['question_id']}: 记录重建不是无损的")
            records.append(record)
        validate_retrieval_records(records, k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=ids)
        out[row["question_id"]] = records
    return out


def prepare():
    chunks = base.load_corpus()
    items = base.load_testset()
    identity = identity_gate()
    gold_map = base.load_gold_map(items, chunks)
    routes = {name: load_route(name, chunks, items, identity["run_identity"]) for name in hybrid.ROUTES}
    return chunks, items, identity, gold_map, routes


# ==============================================================================
# 融合（Run A / Run B 共用）
# ==============================================================================

def route_json(evidence) -> dict:
    if evidence is None:
        return {"present": False, "rank": None, "raw_score": None, "match_score": None}
    return {"present": True, "rank": evidence.rank, "raw_score": evidence.raw_score, "match_score": evidence.match_score}


def diagnostics_json(result, hybrid_rank: int) -> dict:
    record = retrieval_record_json_object(result.record)
    return {"hybrid_rank": hybrid_rank, "chunk_id": record["chunk_id"], "corpus_ordinal": record["corpus_ordinal"],
            "raw_score": record["raw_score"], "relevance": record["relevance"], "match_score": record["match_score"],
            "bm25": route_json(result.bm25), "vector": route_json(result.vector)}


def run_fusion(identity, chunks, items, gold_map, routes) -> str:
    ids = [c.id for c in chunks]
    lines = [base.jline(identity["run_identity"])]
    for item in items:
        results = hybrid.fuse(routes["bm25"][item.id], routes["vector"][item.id], k=contracts.TOP_K_RETRIEVE)
        records = [r.record for r in results]
        validate_retrieval_records(records, k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=ids)
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
            "route_diagnostics": [diagnostics_json(r, rank) for rank, r in enumerate(results, start=1)],
        }
        lines.append(base.jline({key: row[key] for key in QUESTION_KEYS}))
    return "".join(lines)


# ==============================================================================
# 有效性检查（只从已保存 artifact + 两路冻结输入重算）
# ==============================================================================

def parse_raw(text: object) -> Fraction:
    """"p/q" → Fraction；必须是最简、正的规范写法，否则 ContractViolation。"""
    match = RAW_SCORE_RE.fullmatch(text) if isinstance(text, str) else None
    value = Fraction(int(match.group(1)), int(match.group(2))) if match else None
    if value is None or f"{value.numerator}/{value.denominator}" != text:
        raise ContractViolation(f"raw_score 不是规范的 p/q: {text!r}")
    return value


def validity_checks(run_identity, rows, items, chunks, gold_map, routes) -> dict:
    projected = [{**{key: row[key] for key in base.QUESTION_KEYS},
                  "hits": [{**h, "raw_score": parse_raw(h["raw_score"])} for h in row["hits"]]} for row in rows]
    checks = base.validity_checks(run_identity, projected, items, chunks, gold_map)
    checks["run_identity_keys_frozen"] = list(run_identity) == list(RUN_IDENTITY_KEYS)
    checks["schema_valid"] = checks["schema_valid"] and all(list(row) == list(QUESTION_KEYS) for row in rows)
    floats = [h[k] for row in rows for h in row["hits"] for k in ("relevance", "match_score")] + \
             [row["max_match_score"] for row in rows if row["max_match_score"] is not None]
    checks["all_numbers_finite"] = all(type(x) is float and math.isfinite(x) for x in floats)
    checks["raw_score_canonical_p_over_q"] = all(isinstance(h["raw_score"], str) for row in rows for h in row["hits"])
    aligned = rrf_ok = provenance_ok = union_ok = True
    for row in rows:
        qid, hits, diags = row["question_id"], row["hits"], row["route_diagnostics"]
        route_by_ordinal = {name: {r.corpus_ordinal: (rank, r) for rank, r in enumerate(routes[name][qid], start=1)}
                            for name in hybrid.ROUTES}
        union = set(route_by_ordinal["bm25"]) | set(route_by_ordinal["vector"])
        union_ok &= len(hits) == min(contracts.TOP_K_RETRIEVE, len(union)) and all(h["corpus_ordinal"] in union for h in hits)
        aligned &= len(diags) == len(hits)
        for position, (hit, diag) in enumerate(zip(hits, diags), start=1):
            aligned &= diag["hybrid_rank"] == position and all(
                diag[key] == hit[key] for key in ("chunk_id", "corpus_ordinal", "raw_score", "relevance", "match_score"))
            present = {name: diag[name] for name in hybrid.ROUTES if diag[name]["present"]}
            rrf_ok &= bool(present) and parse_raw(hit["raw_score"]) == sum(
                (Fraction(1, hybrid.RRF_K + d["rank"]) for d in present.values()), Fraction(0))
            rrf_ok &= hit["match_score"] == max(d["match_score"] for d in present.values())
            for name in hybrid.ROUTES:
                saved = route_by_ordinal[name].get(hit["corpus_ordinal"])
                if diag[name]["present"]:
                    provenance_ok &= saved is not None and diag[name] == {
                        "present": True, "rank": saved[0], "raw_score": saved[1].raw_score, "match_score": saved[1].match_score}
                else:
                    provenance_ok &= saved is None and diag[name] == route_json(None)
    checks["route_diagnostics_aligned_with_hits"] = aligned
    checks["raw_score_equals_rrf_of_route_ranks_and_match_is_max_present"] = rrf_ok
    checks["route_provenance_equals_component_artifacts"] = provenance_ok
    checks["returned_min_k_union_from_candidate_union"] = union_ok
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir")
    parser.add_argument("--emit-normative", action="store_true")
    args = parser.parse_args(argv)
    chunks, items, identity, gold_map, routes = prepare()
    if args.emit_normative:
        sys.stdout.buffer.write(run_fusion(identity, chunks, items, gold_map, routes).encode("utf-8"))
        return 0
    if not args.out_dir:
        raise SystemExit("--out-dir 必填")
    os.makedirs(args.out_dir, exist_ok=True)
    out = {name: os.path.join(args.out_dir, fname) for name, fname in OUT_FILES.items()}
    existing = [p for p in out.values() if os.path.exists(p)]
    if existing:
        raise ContractViolation(f"拒绝覆盖已有 artifact（不重跑挑结果）: {existing}")
    log = open(out["log"], "w", encoding="utf-8")
    log.write(base.jline({"event": "identity_header_before_results",
                          "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **identity}))
    log.flush()
    text = run_fusion(identity, chunks, items, gold_map, routes)
    with open(out["results"], "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    log.write(base.jline({"event": "run_a_written", "results_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}))
    run_b = subprocess.run([sys.executable, os.path.abspath(__file__), "--emit-normative"], capture_output=True,
                           env=dict(os.environ, PYTHONHASHSEED=base.RUN_B_HASH_SEED), cwd=REPO_ROOT)
    run_b_ok = run_b.returncode == 0 and run_b.stdout == text.encode("utf-8")
    log.write(base.jline({"event": "run_b_determinism", "pythonhashseed": base.RUN_B_HASH_SEED, "returncode": run_b.returncode,
                          "run_b_sha256": hashlib.sha256(run_b.stdout).hexdigest(), "byte_identical": run_b_ok,
                          "run_b_stderr_tail": run_b.stderr.decode("utf-8", "replace")[-500:] if run_b.returncode else ""}))
    log.flush()
    if not run_b_ok:
        log.write(base.jline({"event": "BASELINE_VALIDITY", "value": "INVALID", "reason": "Run A != Run B"}))
        log.close()
        raise ContractViolation("Run A 与 Run B normative artifact 不逐字节相同 → 结果不得使用")
    with open(out["results"], encoding="utf-8") as handle:
        run_identity, rows = base.parse_artifact(handle.read())
    checks = validity_checks(run_identity, rows, items, chunks, gold_map, routes)
    metrics = base.compute_metrics(rows, items, gold_map)
    metrics["status"] = "S8 fixed-k hybrid (unweighted RRF) baseline metrics; recomputed from the saved normative top-20 artifact"
    with open(out["metrics"], "w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps({"validity_checks": checks, **metrics}, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    valid = all(v for v in checks.values() if isinstance(v, bool))
    log.write(base.jline({"event": "artifacts", **{n: {"sha256": base.file_sha256(out[n])} for n in ("results", "metrics")}}))
    log.write(base.jline({"event": "BASELINE_VALIDITY", "value": "VALID" if valid else "INVALID", "checks": checks}))
    log.close()
    print(json.dumps({"validity": "VALID" if valid else "INVALID", "checks": checks}, ensure_ascii=False))
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
