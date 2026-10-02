"""S8 / M1c 固定-k 检索基线 runner（vector）。严格执行 experiments/M1c_preregistration.md §15（及共享的 §2–§9）。

复用 eval/run_retrieval_eval.py（BM25 runner，已提交）的冻结输入加载、query / metric / total-order payload、有效性检查与
指标纯函数；本文件只加 vector 专属的身份门、检索循环与 Run B。用 EvalItem.question 原文调用 search_records(k=20)。

用法: python3 eval/run_vector_eval.py --out-dir experiments/m1c_s8_vector
      （--emit-normative 只供 Run B 子进程使用: 把 normative 字节写到 stdout，不写任何文件）
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import unicodedata
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import ContractViolation, canonical_sha256, retrieval_record_json_object  # noqa: E402
from components.retrievers import vector  # noqa: E402
from eval import run_retrieval_eval as base  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m1c_corpus_embeddings", os.path.join(REPO_ROOT, "experiments", "m1c_s8_vector", "corpus_embeddings.py"))
corpus_embeddings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus_embeddings)

EXPECTED_VECTOR_DIGESTS = {
    "retrieval_config_digest": "c9c3868cf19a77d2b88a705580367ba933930af28c265887d2da6aad7a0e7343",
    "embedding_protocol_digest": "38acb0b4260a516dffc32680067d5cb55c6c56d09a4d4045ebcda2d289b54af0",
}
EXPECTED_RUNTIME = {"ollama_server": "0.34.0", "ollama_client": "0.23.1"}
EXPECTED_MANIFEST_SHA256 = "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
EXPECTED_MODEL_BLOB = "sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c"
MANIFEST_PATH = os.path.expanduser("~/.ollama/models/manifests/registry.ollama.ai/library/bge-m3/latest")
EXECUTION_PATH = "MAC_DEFAULT_METAL"
VECTOR_KEYS = ("embedder_model_tag", "embedder_model_blob_digest", "embedder_manifest_sha256", "embedding_dimension",
               "embedding_protocol_digest", "corpus_embeddings_sha256", "ollama_server_version", "ollama_client_version",
               "embedding_execution_path")
RUN_IDENTITY_KEYS = base.RUN_IDENTITY_KEYS + VECTOR_KEYS
RUN_B_HASH_SEED = "4242"
OUT_FILES = {"results": "s8_vector_results.jsonl", "metrics": "s8_vector_metrics.json", "log": "s8_vector_run.log"}

# prereg §15.5 冻结的 vector retrieval_config payload。
RETRIEVAL_CONFIG_PAYLOAD = {
    "digest_name": "retrieval_config", "payload_version": 1,
    "retrieval_variant": vector.HIT_ORIGIN,
    "indexed_text": "Chunk.text",
    "indexed_documents": "all_chunks_in_canonical_corpus",
    "embedding_protocol_digest": canonical_sha256(corpus_embeddings.EMBEDDING_PROTOCOL_PAYLOAD),
    "index": "exact_brute_force_over_all_corpus_vectors",
    "empty_or_whitespace_query": "return_empty_without_endpoint_call",
    "raw_score": "numerator / (norm_a * norm_b); numerator = math.fsum(a_i * b_i); norm = sqrt(math.fsum(x_i * x_i))",
    "raw_score_kind": vector.RAW_SCORE_KIND,
    "relevance": "(raw_score + 1.0) / 2.0", "relevance_kind": vector.AFFINE_KIND,
    "match_score": "(raw_score + 1.0) / 2.0", "match_score_kind": vector.AFFINE_KIND,
    "return_filter": "none_by_sign_return_min_k_corpus_size",
    "k": contracts.TOP_K_RETRIEVE,
    "total_order": "core.contracts.retrieval_order_key(raw_score, corpus_ordinal)",
}


def http_json(path: str) -> dict:
    with urllib.request.urlopen(vector.OLLAMA_BASE_URL + path, timeout=30) as response:
        return json.loads(response.read())


def identity_gate(chunks, embeddings_meta) -> dict:
    """冻结身份全部 EXPECTED == ACTUAL，否则 ContractViolation。返回 run identity（键序冻结）与审计身份。"""
    shared = base.identity_gate()                       # corpus / testset / map / report / builder / contracts / clean tree / 3 共享 digest
    digests = {"retrieval_config_digest": canonical_sha256(RETRIEVAL_CONFIG_PAYLOAD),
               "embedding_protocol_digest": canonical_sha256(corpus_embeddings.EMBEDDING_PROTOCOL_PAYLOAD)}
    for name, value in digests.items():
        if value != EXPECTED_VECTOR_DIGESTS[name]:
            raise ContractViolation(f"{name} {value} != prereg {EXPECTED_VECTOR_DIGESTS[name]}")
    observed = corpus_embeddings.ollama_identity()
    runtime = {"ollama_server": observed["ollama_server"], "ollama_client": observed["ollama_client"]}
    if runtime != EXPECTED_RUNTIME:
        raise ContractViolation(f"runtime {runtime} != frozen {EXPECTED_RUNTIME}")
    with open(MANIFEST_PATH, "rb") as handle:
        manifest_bytes = handle.read()
    if hashlib.sha256(manifest_bytes).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise ContractViolation("bge-m3 manifest sha 与冻结值不符")
    blob = next(layer["digest"] for layer in json.loads(manifest_bytes)["layers"] if layer["mediaType"].endswith(".model"))
    if blob != EXPECTED_MODEL_BLOB:
        raise ContractViolation(f"model blob {blob} != frozen {EXPECTED_MODEL_BLOB}")
    if embeddings_meta["vector_py_sha256"] != base.file_sha256(vector.__file__):
        raise ContractViolation("corpus embeddings 由不同的 vector.py 生成")
    values = {**shared["run_identity"], "retrieval_variant": vector.HIT_ORIGIN, "retrieval_config_digest": digests["retrieval_config_digest"],
              "embedder_model_tag": vector.EMBED_MODEL, "embedder_model_blob_digest": blob,
              "embedder_manifest_sha256": EXPECTED_MANIFEST_SHA256, "embedding_dimension": vector.EMBED_DIMENSION,
              "embedding_protocol_digest": digests["embedding_protocol_digest"],
              "corpus_embeddings_sha256": embeddings_meta["npy_sha256"], "ollama_server_version": runtime["ollama_server"],
              "ollama_client_version": runtime["ollama_client"], "embedding_execution_path": EXECUTION_PATH}
    audit = {**shared["audit"], "vector_implementation_sha256": base.file_sha256(vector.__file__),
             "vector_runner_sha256": base.file_sha256(os.path.abspath(__file__)),
             "corpus_embeddings_helper_sha256": base.file_sha256(corpus_embeddings.__file__),
             "corpus_embeddings_meta_sha256": base.file_sha256(corpus_embeddings.META_PATH)}
    return {"run_identity": {key: values[key] for key in RUN_IDENTITY_KEYS}, "audit": audit}


def assert_metal_path() -> list:
    loaded = [m for m in http_json("/api/ps").get("models", []) if m["name"] == vector.EMBED_MODEL]
    if not loaded or loaded[0].get("size_vram") != loaded[0].get("size"):
        raise ContractViolation(f"执行路径不是 {EXECUTION_PATH}（size_vram != size）: {loaded}")
    return [{"size": m["size"], "size_vram": m["size_vram"]} for m in loaded]


def run_retrieval(identity, chunks, corpus_vectors, items, gold_map):
    corpus_embeddings.unload_model()                    # 以默认 options（Metal）重新加载
    retriever = vector.VectorRetriever(chunks, corpus_vectors)
    lines = [base.jline(identity["run_identity"])]
    latencies, path = [], None
    for item in items:
        started = time.perf_counter()
        records = retriever.search_records(item.question, k=contracts.TOP_K_RETRIEVE)
        latencies.append(time.perf_counter() - started)
        if path is None:
            path = assert_metal_path()
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
        lines.append(base.jline({key: row[key] for key in base.QUESTION_KEYS}))
    assert_metal_path()
    return "".join(lines), latencies, path


def prepare():
    chunks = corpus_embeddings.load_chunks()
    corpus_vectors, meta = corpus_embeddings.load(chunks)
    identity = identity_gate(chunks, meta)
    return chunks, corpus_vectors, identity


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir")
    parser.add_argument("--emit-normative", action="store_true")
    args = parser.parse_args(argv)
    chunks, corpus_vectors, identity = prepare()
    if args.emit_normative:
        items = base.load_testset()
        text, _, _ = run_retrieval(identity, chunks, corpus_vectors, items, base.load_gold_map(items, chunks))
        sys.stdout.buffer.write(text.encode("utf-8"))
        return 0
    if not args.out_dir:
        raise SystemExit("--out-dir 必填")
    out = {name: os.path.join(args.out_dir, fname) for name, fname in OUT_FILES.items()}
    existing = [p for p in out.values() if os.path.exists(p)]
    if existing:
        raise ContractViolation(f"拒绝覆盖已有 artifact（不重跑挑结果）: {existing}")
    log = open(out["log"], "w", encoding="utf-8")
    log.write(base.jline({"event": "identity_header_before_results",
                          "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **identity}))
    log.flush()
    items = base.load_testset()
    gold_map = base.load_gold_map(items, chunks)
    text, latencies, path = run_retrieval(identity, chunks, corpus_vectors, items, gold_map)
    with open(out["results"], "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    log.write(base.jline({"event": "run_a_written", "results_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                          "execution_path_observed": path,
                          "latency_s": {"total": round(sum(latencies), 4), "max": round(max(latencies), 4),
                                        "median": round(sorted(latencies)[len(latencies) // 2], 4)}}))
    run_b = subprocess.run([sys.executable, os.path.abspath(__file__), "--emit-normative"], capture_output=True,
                           env=dict(os.environ, PYTHONHASHSEED=RUN_B_HASH_SEED), cwd=REPO_ROOT)
    run_b_ok = run_b.returncode == 0 and run_b.stdout == text.encode("utf-8")
    log.write(base.jline({"event": "run_b_determinism", "pythonhashseed": RUN_B_HASH_SEED, "returncode": run_b.returncode,
                          "run_b_sha256": hashlib.sha256(run_b.stdout).hexdigest(), "byte_identical": run_b_ok,
                          "run_b_stderr_tail": run_b.stderr.decode("utf-8", "replace")[-500:] if run_b.returncode else ""}))
    log.flush()
    if not run_b_ok:
        log.write(base.jline({"event": "BASELINE_VALIDITY", "value": "INVALID", "reason": "Run A != Run B"}))
        log.close()
        raise ContractViolation("Run A 与 Run B normative artifact 不逐字节相同 → 结果不得使用")
    with open(out["results"], encoding="utf-8") as handle:
        run_identity, rows = base.parse_artifact(handle.read())
    checks = base.validity_checks(run_identity, rows, items, chunks, gold_map)
    checks["run_identity_keys_frozen"] = list(run_identity) == list(RUN_IDENTITY_KEYS)
    checks["returned_min_k_N_for_nonempty_queries"] = all(len(r["hits"]) == contracts.TOP_K_RETRIEVE for r in rows)
    metrics = base.compute_metrics(rows, items, gold_map)
    metrics["status"] = "S8 fixed-k vector baseline metrics; recomputed from the saved normative top-20 artifact"
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
