"""EMBEDDING_PROTOCOL_PROBE 补充: CPU 强制路径（options.num_gpu = 0）的 Run A / Run B 可重复性。

动机（写于运行前）: 主 probe 显示默认路径（Metal GPU）与 CPU 强制路径的向量不逐位相同，执行路径因此是一个协议选择；
主 probe 只测了默认路径的 Run A/B。本补充对同一组探针（复用主 probe 的 PROBES 与语料抽样规则）在两个全新子进程中、
每次重新加载模型，用 CPU 强制路径各算一遍，比较向量摘要。结果作为事件追加到 embedding_protocol_probe.log。
不做检索、不读评测集或 GoldChunkMap。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("probe", os.path.join(HERE, "embedding_protocol_probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def one_pass() -> dict:
    samples, _ = probe.corpus_samples()
    texts = {**probe.PROBES, **samples}
    probe.unload()
    batch = probe.embed([texts[n] for n in texts], options=probe.CPU_FORCED_OPTIONS)["embeddings"]
    singles = {n: probe.embed(texts[n], options=probe.CPU_FORCED_OPTIONS)["embeddings"][0] for n in texts}
    out = {"batch": {n: probe.digest(v) for n, v in zip(texts, batch)},
           "single": {n: probe.digest(v) for n, v in singles.items()},
           "single_vs_batch_exact": {n: singles[n] == v for n, v in zip(texts, batch)},
           "processor": probe.loaded_processor()}
    probe.unload()
    return out


if __name__ == "__main__":
    if "--pass" in sys.argv:
        sys.stdout.write(json.dumps(one_pass()))
        sys.exit(0)
    runs = []
    for seed in ("0", "4242"):
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--pass"], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONHASHSEED=seed))
        if proc.returncode != 0:
            raise SystemExit(proc.stderr[-2000:])
        runs.append(json.loads(proc.stdout))
    a, b = runs
    event = {"event": "supplement_cpu_forced_run_ab",
             "script_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
             "batch_digests_equal": a["batch"] == b["batch"], "single_digests_equal": a["single"] == b["single"],
             "single_vs_batch_exact_run_a": a["single_vs_batch_exact"], "processor_run_a": a["processor"],
             "processor_run_b": b["processor"],
             "differing": sorted({n for n in a["batch"] if a["batch"][n] != b["batch"][n]} |
                                 {n for n in a["single"] if a["single"][n] != b["single"][n]})}
    with open(probe.LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(event, ensure_ascii=False))
