"""S8 reranker prerequisite：三路冻结 top-20 上的 real retrieval-window measurement（人工裁决 P1_MEASURE_ALL_FROZEN_ROUTES）。

只消费已提交的冻结 artifact：BM25 沿用已正式记录的 packing measurement（s8_bm25_packing.json，不重算）；
vector / hybrid 把各自保存的 top-20 按原顺序交给已提交的 eval/run_retrieval_eval.compute_packing（当前可执行打包契约）。
不检索、不 embedding、不融合、不调用 Ollama；不改任何排序、协议或 token 契约。输出 measurement only，不是新的 baseline。

用法: python3 experiments/m1c_s8_reranker/measure_reranker_prerequisite.py   # 写 reranker_prerequisite.json（拒绝覆盖）
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import ContractViolation  # noqa: E402
from eval import run_retrieval_eval as base  # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reranker_prerequisite.json")
# 冻结 evidence（sha 抄自 DECISIONS 各 component closure 条目）。
RESULTS = {
    "bm25": ("experiments/m1c_s8_bm25/s8_bm25_results.jsonl", "9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8"),
    "vector": ("experiments/m1c_s8_vector/s8_vector_results.jsonl", "0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073"),
    "hybrid": ("experiments/m1c_s8_hybrid/s8_hybrid_results.jsonl", "5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8"),
}
METRICS = {
    "bm25": ("experiments/m1c_s8_bm25/s8_bm25_metrics.json", "019f6ee850bcb4788aa48d32807ccc1d61c2a570343104674004c5b37529b339"),
    "vector": ("experiments/m1c_s8_vector/s8_vector_metrics.json", "aa404fa9e1a33c3d1d3c87c5dde2624c70fc68471c6d79b16a56e37c0b286599"),
    "hybrid": ("experiments/m1c_s8_hybrid/s8_hybrid_metrics.json", "97021b12a03d5e5e6535ea794af64f4e1e022667297d725538f34e9932152f81"),
}
BM25_PACKING = ("experiments/m1c_s8_bm25/s8_bm25_packing.json", "81fedf9fd7ad2a0ba46a128a8c6fbe449a2131216bb9a8e5c482164eebb65313")
BM25_RUN_LOG = ("experiments/m1c_s8_bm25/s8_bm25_run.log", "91412c65bb5988e44651a7b7f2bbac6e89df47bb1302eb99667322872264ce3a")
ROUTES = ("bm25", "vector", "hybrid")
MEASURED_ROUTES = ("vector", "hybrid")
K_CONTEXT_CANDIDATES = (2, 3)
CD01 = "CD01"
WINDOW_FIELDS = ("question_id", "expected", "realized_k", "packed_ids", "stopped_by", "est_context_tokens", "est_overbudget",
                 "proxy_actual_context_tokens", "proxy_overbudget")


def checked(spec: tuple[str, str]) -> str:
    path = os.path.join(REPO_ROOT, spec[0])
    if base.file_sha256(path) != spec[1]:
        raise ContractViolation(f"{spec[0]} sha 与冻结值不符")
    return path


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def k_stats(windows: list[dict]) -> dict:
    ks = [w["realized_k"] for w in windows]
    counts = Counter(ks)
    top = max(counts.values())
    return {"n_windows": len(ks), "min": min(ks), "median": statistics.median(ks), "max": max(ks),
            "mode": sorted(k for k, c in counts.items() if c == top),
            "count_by_k": {str(k): counts.get(k, 0) for k in range(1, contracts.TOP_K_CONTEXT + 1)}}


def main() -> int:
    if os.path.exists(OUT_PATH):
        raise ContractViolation(f"拒绝覆盖已有 artifact: {OUT_PATH}")
    corpus = base.load_corpus()
    items = base.load_testset()
    gold_map = base.load_gold_map(items, corpus)
    for path, expected in base.EXPECTED_SHA256.items():
        if base.file_sha256(path) != expected:
            raise ContractViolation(f"{path} sha 与冻结值不符")
    contracts_sha = base.file_sha256(os.path.join(REPO_ROOT, "core", "contracts.py"))
    bm25_audit = json.loads(read(checked(BM25_RUN_LOG)).splitlines()[0])["audit"]
    for path, key in ((base.CHUNK_TOKENS_PATH, "chunk_token_proxy_csv_sha256"), (base.SEQUENTIAL_WINDOWS_PATH, "sequential_windows_csv_sha256")):
        if base.file_sha256(path) != bm25_audit[key]:
            raise ContractViolation(f"{path} 与 BM25 正式运行时的字节不同")

    rows, identity = {}, {}
    for name in ROUTES:
        run_identity, rows[name] = base.parse_artifact(read(checked(RESULTS[name])))
        if run_identity["contracts_sha256"] != contracts_sha or [r["question_id"] for r in rows[name]] != [i.id for i in items]:
            raise ContractViolation(f"{name} artifact 的 contracts 或题目序列与当前不一致")
        identity[name] = {"results_sha256": RESULTS[name][1], "code_commit": run_identity["code_commit"],
                          "retrieval_config_digest": run_identity["retrieval_config_digest"]}
    packing = {"bm25": json.loads(read(checked(BM25_PACKING)))}
    for name in MEASURED_ROUTES:
        packing[name] = base.compute_packing(rows[name], corpus, gold_map)

    metrics = {name: json.loads(read(checked(METRICS[name])))["overall_answer_31"]["ANY_GOLD"] for name in ROUTES}
    answer_ids = [i.id for i in items if i.expected == "answer"]
    routes_out = {}
    for name in ROUTES:
        windows = packing[name]["per_window"]
        by_q = {w["question_id"]: w for w in windows}
        hits = {r["question_id"]: [h["chunk_id"] for h in r["hits"]] for r in rows[name]}
        first_gold = {q: next((i for i, c in enumerate(hits[q], 1) if c in set(gold_map.mapping[q])), None) for q in answer_ids}
        opportunity = sorted(q for q in answer_ids
                             if first_gold[q] is not None and q in by_q and first_gold[q] > by_q[q]["realized_k"])
        gold01 = gold_map.mapping[CD01]
        w01 = by_q.get(CD01)
        packed01 = [c for c in (w01["packed_ids"] if w01 else []) if c in set(gold01)]
        routes_out[name] = {
            "source": "s8_bm25_packing.json (recorded, not recomputed)" if name == "bm25"
                      else "eval/run_retrieval_eval.compute_packing on frozen top-20 (this script)",
            "realized_k_all_windows": k_stats(windows),
            "realized_k_answer_windows": k_stats([w for w in windows if w["expected"] == "answer"]),
            "realized_k_refuse_windows": k_stats([w for w in windows if w["expected"] == "refuse"]),
            "questions_without_window": [r["question_id"] for r in rows[name] if not r["hits"]],
            "packed_answer_31": {k: packing[name]["packed_gold_current_contract_answer_31"][k]
                                 for k in ("ANY_GOLD", "GOLD_COVERAGE", "ALL_MAPPED_GOLD", "mean_realized_k", "n")},
            "est_overbudget_count": packing[name]["est_overbudget_count"],
            "proxy_overbudget_count": packing[name]["proxy_overbudget_count"],
            "fixed_k_headroom": {f"k_context_{k}": {f"ANY@{k}": metrics[name][f"@{k}"]["macro"],
                                                    "ANY@20": metrics[name]["@20"]["macro"],
                                                    "headroom": metrics[name]["@20"]["macro"] - metrics[name][f"@{k}"]["macro"]}
                                 for k in K_CONTEXT_CANDIDATES},
            "realized_window_rerank_opportunity": {"definition": "gold in top-20 but first_gold_rank > this question's realized_k",
                                                   "count": len(opportunity), "question_ids": opportunity},
            "cd01": {"gold_ids": gold01, "gold_ranks": [i for i, c in enumerate(hits[CD01], 1) if c in set(gold01)],
                     "realized_k": w01["realized_k"] if w01 else None, "packed_ids": w01["packed_ids"] if w01 else [],
                     "packed_gold_ids": packed01, "packed_gold_coverage": f"{len(packed01)}/{len(gold01)}",
                     "retrieval_attribution": "NO_RETRIEVAL_FAILURE"},
            "per_window": [{k: w[k] for k in WINDOW_FIELDS} for w in windows],
        }
    distributions = {name: routes_out[name]["realized_k_all_windows"]["count_by_k"] for name in ROUTES}
    payload = {
        "status": "S8 reranker prerequisite real retrieval-window measurement; MEASUREMENT_ONLY (not a retrieval baseline)",
        "route_gap_decision": "P1_MEASURE_ALL_FROZEN_ROUTES",
        "measurement_kind": "PACKED_CONTEXT_REALIZED_K under CURRENT_EXECUTABLE_CONTRACT_ONLY (prereg §11)",
        "inputs": {"routes": identity, "metrics_sha256": {n: METRICS[n][1] for n in ROUTES},
                   "bm25_packing_sha256": BM25_PACKING[1],
                   "corpus_sha256": base.EXPECTED_SHA256[base.CORPUS_PATH], "testset_sha256": base.EXPECTED_SHA256[base.TESTSET_PATH],
                   "gold_chunk_map_sha256": base.EXPECTED_SHA256[base.MAP_PATH],
                   "chunk_token_proxy_csv_sha256": bm25_audit["chunk_token_proxy_csv_sha256"],
                   "contracts_version": contracts.CONTRACTS_VERSION, "contracts_sha256": contracts_sha},
        "executable_packing_contract": {
            "MAX_PROMPT_TOKENS": contracts.MAX_PROMPT_TOKENS, "PROMPT_OVERHEAD_RESERVE_TOKENS": contracts.PROMPT_OVERHEAD_RESERVE_TOKENS,
            "CONTEXT_PACK_MARGIN": contracts.CONTEXT_PACK_MARGIN, "CONTEXT_PACK_BUDGET_TOKENS": contracts.CONTEXT_PACK_BUDGET_TOKENS,
            "TOP_K_CONTEXT": contracts.TOP_K_CONTEXT, "CHARS_PER_TOKEN_EST": contracts.CHARS_PER_TOKEN_EST,
            "CITATION_HEADER_EST_TOKENS": contracts.CITATION_HEADER_EST_TOKENS,
            "function": "core.contracts.pack_context (relevance prefix, saved order)"},
        "actual_tokens": "proxy = sum of S4a.9c per-chunk actual_rendered_tokens (no tokenizer run), as in BM25 closure E",
        "realized_k_route_invariant": len({json.dumps(d, sort_keys=True) for d in distributions.values()}) == 1,
        "routes": routes_out,
        "budget_boundary": {"TTFT_BUDGET_10S_STATUS": "BUSINESS_ASSUMPTION_NOT_YET_CONFIRMED",
                            "TTFT_180S_STATUS": "EXPLORATORY_UPPER_BOUND_ONLY",
                            "falsified_if": "numeric token contract changes such that the realized-k distribution or the reranker decision criterion changes"},
    }
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n").hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
