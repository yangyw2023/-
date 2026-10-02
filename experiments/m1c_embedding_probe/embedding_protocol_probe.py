"""S8 / M1c EMBEDDING_PROTOCOL_PROBE（DECISIONS D12）。只测协议，不做检索、不算 Recall、不读评测集或 GoldChunkMap。

在任何 embedding 调用之前，把探针字符串、语料抽样规则、prefix 候选与计划写入 log 头（prereg）。
用法: python3 experiments/m1c_embedding_probe/embedding_protocol_probe.py          # 主流程，写 .log / .json
      python3 ... --repeat-pass                                                    # Run B 子进程，只把向量摘要写到 stdout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(OUT_DIR, "embedding_protocol_probe.log")
JSON_PATH = os.path.join(OUT_DIR, "embedding_protocol_probe.json")
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")

OLLAMA = "http://localhost:11434"
MODEL = "bge-m3:latest"
HTTP_TIMEOUT_S = 300
UNIT_NORM_TOLERANCE = 1e-6
# 固定探针（结果产生前写死；与评测集无关）。
PROBES = {
    "P1_en_short": "The pump was checked.",
    "P2_en_technical": "Check the emergency fire pump discharge pressure at 7 bar before the weekly drill.",
    "P3_zh": "船员应每周检查应急消防泵。",
    "P4_tl": "Dapat suriin ng mga tripulante ang bomba linggu-linggo.",
    "P5_punct_numeric_unit": "O2 ≥ 20.8 %; CO < 25 ppm; H2S 10 ppm (TWA) — 3 × 15 min.",
}
EDGE_PROBES = {"P6a_empty": "", "P6b_whitespace": "   "}
# 语料侧只为观察 document 侧 API 行为: 固定行序 0 / 中位 / 末行，外加按 len(text) 最长的 chunk（并列取最小行序）。
CORPUS_SAMPLE_RULE = "ordinals [0, N//2, N-1] + argmax len(text) (ties -> smallest ordinal)"
# prefix 只做协议行为探针（接受？确定？向量变？），不是提案。
QUERY_PREFIX_CANDIDATE = "Represent this sentence for searching relevant passages: "   # BGE v1.5 惯例；仓库无 authority
DOCUMENT_PREFIX_CANDIDATE = "passage: "                                                  # 任意探针前缀；非 BGE 惯例
CPU_FORCED_OPTIONS = {"num_gpu": 0}


def http(path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(OLLAMA + path, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read())


def try_http(path: str, payload: dict) -> tuple[dict | None, str | None]:
    try:
        return http(path, payload), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"


def embed(inputs, **extra) -> dict:
    return http("/api/embed", {"model": MODEL, "input": inputs, **extra})


def digest(vector: list[float]) -> str:
    return hashlib.sha256(json.dumps(vector, separators=(",", ":")).encode("utf-8")).hexdigest()


def l2(vector: list[float]) -> float:
    return math.sqrt(math.fsum(x * x for x in vector))


def cosine(a: list[float], b: list[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b)) / (l2(a) * l2(b))


def max_abs_diff(a, b) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def max_rel_diff(a, b) -> float:
    return max((abs(x - y) / abs(y) if y else (0.0 if x == y else math.inf)) for x, y in zip(a, b))


def compare(a, b) -> dict:
    return {"exact_equal": a == b, "max_abs_diff": max_abs_diff(a, b), "max_rel_diff": max_rel_diff(a, b),
            "cosine": cosine(a, b)}


def corpus_samples() -> tuple[dict[str, str], str]:
    """返回 (样本 {name: text}, 最长 chunk 的 name)。"""
    with open(CORPUS_PATH, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    n = len(rows)
    longest = max(range(n), key=lambda i: (len(rows[i]["text"]), -i))
    picks = [0, n // 2, n - 1, longest]
    samples = {f"C{i}_{rows[i]['id']}": rows[i]["text"] for i in picks}
    return samples, f"C{longest}_{rows[longest]['id']}"


def unload() -> None:
    subprocess.run(["ollama", "stop", MODEL], capture_output=True)


def loaded_processor() -> list[dict]:
    return [{"name": m["name"], "size": m.get("size"), "size_vram": m.get("size_vram"),
             "gpu_fraction": (m.get("size_vram", 0) / m["size"]) if m.get("size") else None}
            for m in http("/api/ps").get("models", [])]


def measurement_pass(texts: dict[str, str]) -> dict:
    """一次完整测量（Run A / Run B 共用）: batch 与逐条 /api/embed，返回每条向量摘要与原向量。"""
    names = list(texts)
    batch = embed([texts[n] for n in names])
    singles = {n: embed(texts[n])["embeddings"][0] for n in names}
    return {"order": names, "batch": dict(zip(names, batch["embeddings"])), "single": singles,
            "batch_prompt_eval_count": batch.get("prompt_eval_count")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat-pass", action="store_true")
    args = parser.parse_args()
    samples, longest = corpus_samples()
    texts = {**PROBES, **samples}
    if args.repeat_pass:
        unload()
        result = measurement_pass(texts)
        sys.stdout.write(json.dumps({"batch": {n: digest(v) for n, v in result["batch"].items()},
                                     "single": {n: digest(v) for n, v in result["single"].items()},
                                     "processor": loaded_processor()}))
        unload()
        return 0

    for path in (LOG_PATH, JSON_PATH):
        if os.path.exists(path):
            raise SystemExit(f"拒绝覆盖已有 probe artifact: {path}")
    log = open(LOG_PATH, "w", encoding="utf-8")

    def emit(event: str, **fields):
        log.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
        log.flush()

    emit("prereg_before_any_embedding", model=MODEL, endpoint_candidates=["/api/embed", "/api/embeddings"],
         probes=PROBES, edge_probes=EDGE_PROBES, corpus_sample_rule=CORPUS_SAMPLE_RULE,
         corpus_samples={k: {"chars": len(v), "sha256": hashlib.sha256(v.encode("utf-8")).hexdigest()}
                         for k, v in texts.items() if k.startswith("C")},
         query_prefix_candidate=QUERY_PREFIX_CANDIDATE, document_prefix_candidate=DOCUMENT_PREFIX_CANDIDATE,
         cpu_forced_options=CPU_FORCED_OPTIONS, no_testset=True, no_gold_map=True, no_retrieval_metric=True,
         script_sha256=hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest())

    report: dict = {}
    show = http("/api/show", {"model": MODEL})
    info = show.get("model_info", {})
    report["identity"] = {
        "server_version": http("/api/version")["version"],
        "details": show.get("details"),
        "embedding_length": info.get("bert.embedding_length"),
        "context_length": info.get("bert.context_length"),
        "pooling_type": info.get("bert.pooling_type"),
        "manifest_sha256": hashlib.sha256(open(os.path.expanduser(
            "~/.ollama/models/manifests/registry.ollama.ai/library/bge-m3/latest"), "rb").read()).hexdigest(),
    }
    emit("identity", **report["identity"])

    # ---- Run A（默认执行路径）----
    unload()
    run_a = measurement_pass(texts)
    report["execution_path_default"] = loaded_processor()
    dims = {n: len(v) for n, v in run_a["batch"].items()} | {f"single:{n}": len(v) for n, v in run_a["single"].items()}
    finite = all(math.isfinite(x) for v in list(run_a["batch"].values()) + list(run_a["single"].values()) for x in v)
    report["dimension"] = {"distinct": sorted(set(dims.values())), "per_input": dims}
    report["finite_all"] = finite
    report["norms_api_embed_batch"] = {n: l2(v) for n, v in run_a["batch"].items()}
    report["zero_vectors"] = [n for n, v in run_a["batch"].items() if not any(v)]
    report["single_vs_batch"] = {n: compare(run_a["single"][n], run_a["batch"][n]) for n in run_a["order"]}
    emit("run_a", dims=report["dimension"]["distinct"], finite=finite, processor=report["execution_path_default"])

    # ---- 空 / 空白输入行为 ----
    report["edge_inputs"] = {}
    for name, text in EDGE_PROBES.items():
        out, err = try_http("/api/embed", {"model": MODEL, "input": text})
        report["edge_inputs"][name] = ({"error": err} if err else
                                       {"n_vectors": len(out["embeddings"]),
                                        "dims": [len(v) for v in out["embeddings"]],
                                        "norms": [l2(v) for v in out["embeddings"]] if out["embeddings"] else []})

    # ---- legacy /api/embeddings 的最小等价检查 ----
    report["legacy_endpoint"] = {}
    for name in ("P1_en_short", "P2_en_technical", "P3_zh"):
        out, err = try_http("/api/embeddings", {"model": MODEL, "prompt": texts[name]})
        if err:
            report["legacy_endpoint"][name] = {"error": err}
            continue
        vec = out["embedding"]
        report["legacy_endpoint"][name] = {"dim": len(vec), "norm": l2(vec),
                                           "vs_api_embed": compare(vec, run_a["batch"][name])}

    # ---- prefix 行为探针 ----
    report["prefix_probe"] = {}
    for name in ("P2_en_technical", next(k for k in texts if k.startswith("C0_"))):
        raw = run_a["batch"][name]
        q = embed(QUERY_PREFIX_CANDIDATE + texts[name])["embeddings"][0]
        q2 = embed(QUERY_PREFIX_CANDIDATE + texts[name])["embeddings"][0]
        d = embed(DOCUMENT_PREFIX_CANDIDATE + texts[name])["embeddings"][0]
        report["prefix_probe"][name] = {"query_prefix_accepted_dim": len(q), "query_prefix_deterministic": q == q2,
                                        "cos_raw_vs_query_prefixed": cosine(raw, q),
                                        "cos_raw_vs_document_prefixed": cosine(raw, d),
                                        "norms": {"query_prefixed": l2(q), "document_prefixed": l2(d)}}

    # ---- 截断风险: 最长 chunk 的 truncate=true / false ----
    t_true, err_true = try_http("/api/embed", {"model": MODEL, "input": texts[longest], "truncate": True})
    t_false, err_false = try_http("/api/embed", {"model": MODEL, "input": texts[longest], "truncate": False})
    report["truncation_probe"] = {
        "input": longest, "chars": len(texts[longest]),
        "truncate_true": {"prompt_eval_count": t_true.get("prompt_eval_count") if t_true else None, "error": err_true},
        "truncate_false": {"prompt_eval_count": t_false.get("prompt_eval_count") if t_false else None, "error": err_false,
                           "equal_to_truncate_true": (t_false["embeddings"] == t_true["embeddings"]) if (t_true and t_false) else None},
    }

    # ---- CPU 强制路径 vs 默认路径 ----
    unload()
    cpu = {n: embed(texts[n], options=CPU_FORCED_OPTIONS)["embeddings"][0] for n in run_a["order"]}
    report["execution_path_cpu_forced"] = loaded_processor()
    report["cpu_forced_vs_default"] = {n: compare(cpu[n], run_a["single"][n]) for n in run_a["order"]}
    unload()

    # ---- Run B: 全新进程、模型重新加载 ----
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--repeat-pass"], capture_output=True, text=True,
                          cwd=REPO_ROOT, env=dict(os.environ, PYTHONHASHSEED="4242"))
    if proc.returncode != 0:
        raise SystemExit(f"Run B 失败: {proc.stderr[-2000:]}")
    run_b = json.loads(proc.stdout)
    a_batch = {n: digest(v) for n, v in run_a["batch"].items()}
    a_single = {n: digest(v) for n, v in run_a["single"].items()}
    report["run_ab"] = {"batch_digests_equal": a_batch == run_b["batch"], "single_digests_equal": a_single == run_b["single"],
                        "run_b_processor": run_b["processor"],
                        "differing_batch": [n for n in a_batch if a_batch[n] != run_b["batch"][n]],
                        "differing_single": [n for n in a_single if a_single[n] != run_b["single"][n]]}
    report["vector_digests_run_a"] = {"batch": a_batch, "single": a_single}
    report["vector_head4_run_a"] = {n: v[:4] for n, v in run_a["batch"].items()}
    emit("run_ab", **{k: v for k, v in report["run_ab"].items() if k != "run_b_processor"})

    with open(JSON_PATH, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    emit("done", json_sha256=hashlib.sha256(open(JSON_PATH, "rb").read()).hexdigest(),
         finished_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
