"""M1c vector baseline 的语料 embedding artifact（prereg §15.3）: 生成、加载校验、固定子集复核。实验辅助，不是产品组件。

用法:
  python3 experiments/m1c_s8_vector/corpus_embeddings.py build           # 生成 .npy + .meta.json（拒绝覆盖）
  python3 experiments/m1c_s8_vector/corpus_embeddings.py verify-subset   # 两个全新进程对固定子集逐条 re-embed，与已存行逐位比较
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

import numpy as np  # noqa: E402  (实验 artifact 存储；不进入组件)

from core.contracts import Chunk, ContractViolation, canonical_sha256  # noqa: E402
from components.retrievers import vector  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
NPY_PATH = os.path.join(OUT_DIR, "corpus_embeddings.npy")
META_PATH = os.path.join(OUT_DIR, "corpus_embeddings.meta.json")
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")
EXPECTED_CORPUS_SHA256 = "c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb"
EXPECTED_CORPUS_LINES = 3409
EXPECTED_EMBEDDING_PROTOCOL_DIGEST = "38acb0b4260a516dffc32680067d5cb55c6c56d09a4d4045ebcda2d289b54af0"
EMBED_BATCH_SIZE = 32
DTYPE = "float64"
# 固定复核子集（写死；与评测集无关）: 首 / 末行、每 500 行一个、中位。
SUBSET_ORDINALS = (0, 500, 1000, 1500, 1704, 2000, 2500, 3000, 3408)
SUBSET_HASH_SEEDS = ("0", "4242")

# prereg §15.5 冻结的 embedding_protocol payload（digest 必须等于 EXPECTED）。
EMBEDDING_PROTOCOL_PAYLOAD = {
    "digest_name": "embedding_protocol", "payload_version": 1,
    "model_tag": vector.EMBED_MODEL,
    "model_blob_digest": "sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c",
    "manifest_sha256": "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab",
    "dimension": vector.EMBED_DIMENSION,
    "runtime": {"ollama_server": "0.34.0", "ollama_client": "0.23.1"},
    "endpoint": "POST " + vector.EMBED_ENDPOINT_PATH,
    "request": {"model": vector.EMBED_MODEL, "input": "str_or_list", "truncate": False},
    "response_field": "embeddings",
    "options": "none_no_num_gpu_override",
    "execution_path": "MAC_DEFAULT_METAL",
    "query_prefix": vector.QUERY_PREFIX, "document_prefix": vector.DOCUMENT_PREFIX,
    "document_text": "Chunk.text",
    "stored_vector_values": "float64_exactly_as_parsed_from_api_embed_json",
}


def file_sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_chunks() -> list[Chunk]:
    """canonical 语料，按物理行序；sha 与行数核对冻结值；空行会破坏 ordinal = 行序 → 拒绝。"""
    if file_sha256(CORPUS_PATH) != EXPECTED_CORPUS_SHA256:
        raise ContractViolation("corpus sha 与冻结值不符")
    with open(CORPUS_PATH, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    if lines[-1] != "" or any(not line for line in lines[:-1]) or len(lines) - 1 != EXPECTED_CORPUS_LINES:
        raise ContractViolation("corpus 行结构不符")
    return [Chunk(**json.loads(line)) for line in lines[:-1]]


def ids_sha256(chunks: list[Chunk]) -> str:
    return hashlib.sha256("\n".join(c.id for c in chunks).encode("utf-8")).hexdigest()


def ollama_identity() -> dict:
    import urllib.request
    with urllib.request.urlopen(vector.OLLAMA_BASE_URL + "/api/version", timeout=30) as response:
        server = json.loads(response.read())["version"]
    client_out = subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout + \
        subprocess.run(["ollama", "--version"], capture_output=True, text=True).stderr
    client = next((line.rsplit(" ", 1)[-1] for line in client_out.splitlines() if "client version" in line), None)
    with urllib.request.urlopen(vector.OLLAMA_BASE_URL + "/api/ps", timeout=30) as response:
        loaded = json.loads(response.read()).get("models", [])
    path = [{"name": m["name"], "size": m.get("size"), "size_vram": m.get("size_vram")} for m in loaded]
    return {"ollama_server": server, "ollama_client": client, "loaded_models": path}


def unload_model() -> None:
    subprocess.run(["ollama", "stop", vector.EMBED_MODEL], capture_output=True)


def build() -> int:
    for path in (NPY_PATH, META_PATH):
        if os.path.exists(path):
            raise ContractViolation(f"拒绝覆盖已有 artifact: {path}")
    if canonical_sha256(EMBEDDING_PROTOCOL_PAYLOAD) != EXPECTED_EMBEDDING_PROTOCOL_DIGEST:
        raise ContractViolation("embedding_protocol_digest 与 prereg 不符")
    chunks = load_chunks()
    unload_model()                                   # 确保以默认 options（Metal）重新加载
    started = time.perf_counter()
    rows: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        rows.extend(vector.embed_texts([vector.DOCUMENT_PREFIX + c.text for c in batch]))
    elapsed = time.perf_counter() - started
    identity = ollama_identity()
    array = np.asarray(rows, dtype=DTYPE)
    if array.shape != (len(chunks), vector.EMBED_DIMENSION) or not np.isfinite(array).all():
        raise ContractViolation(f"embedding 形状或有限性不符: {array.shape}")
    if [list(map(float, r)) for r in array[:3]] != rows[:3]:
        raise ContractViolation("float64 存储改变了 JSON 解析值")
    np.save(NPY_PATH, array, allow_pickle=False)
    meta = {
        "corpus_sha256": EXPECTED_CORPUS_SHA256, "rows": len(chunks), "dimension": vector.EMBED_DIMENSION,
        "dtype": DTYPE, "row_order": "row i = canonical corpus/chunks.jsonl physical line i (0-based)",
        "chunk_ids_sha256": ids_sha256(chunks), "model_tag": vector.EMBED_MODEL,
        "model_blob_digest": EMBEDDING_PROTOCOL_PAYLOAD["model_blob_digest"],
        "manifest_sha256": EMBEDDING_PROTOCOL_PAYLOAD["manifest_sha256"],
        "endpoint": EMBEDDING_PROTOCOL_PAYLOAD["endpoint"], "truncate": False,
        "execution_path": "MAC_DEFAULT_METAL", "options": "none_no_num_gpu_override",
        "query_prefix": vector.QUERY_PREFIX, "document_prefix": vector.DOCUMENT_PREFIX,
        "embed_batch_size": EMBED_BATCH_SIZE, "runtime_observed": identity,
        "embedding_protocol_digest": EXPECTED_EMBEDDING_PROTOCOL_DIGEST,
        "vector_py_sha256": file_sha256(vector.__file__),
        "npy_sha256": file_sha256(NPY_PATH), "build_seconds": round(elapsed, 2),
    }
    with open(META_PATH, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("rows", "dimension", "npy_sha256", "build_seconds", "runtime_observed")}))
    return 0


def load(chunks: list[Chunk]) -> tuple[list[list[float]], dict]:
    """读取并校验 artifact（meta 与 chunks、npy sha、形状、dtype、有限性），返回 (按行序的 float 向量, meta)。"""
    with open(META_PATH, encoding="utf-8") as handle:
        meta = json.load(handle)
    checks = {
        "npy_sha256": file_sha256(NPY_PATH) == meta["npy_sha256"],
        "corpus_sha256": meta["corpus_sha256"] == EXPECTED_CORPUS_SHA256,
        "rows": meta["rows"] == len(chunks), "chunk_ids_sha256": meta["chunk_ids_sha256"] == ids_sha256(chunks),
        "protocol_digest": meta["embedding_protocol_digest"] == EXPECTED_EMBEDDING_PROTOCOL_DIGEST,
    }
    if not all(checks.values()):
        raise ContractViolation(f"corpus embedding artifact 校验失败: {checks}")
    array = np.load(NPY_PATH, allow_pickle=False)
    if array.dtype != np.dtype(DTYPE) or array.shape != (len(chunks), vector.EMBED_DIMENSION) or not np.isfinite(array).all():
        raise ContractViolation(f"artifact dtype / 形状 / 有限性不符: {array.dtype} {array.shape}")
    return array.tolist(), meta


def subset_pass() -> dict:
    """一个全新进程: 逐条 re-embed 固定子集，返回 {ordinal: 是否与已存行逐位相同}。"""
    chunks = load_chunks()
    stored, _ = load(chunks)
    unload_model()
    out = {}
    for ordinal in SUBSET_ORDINALS:
        (fresh,) = vector.embed_texts([vector.DOCUMENT_PREFIX + chunks[ordinal].text])
        out[str(ordinal)] = fresh == stored[ordinal]
    out["loaded_models"] = ollama_identity()["loaded_models"]
    unload_model()
    return out


def verify_subset() -> int:
    results = []
    for seed in SUBSET_HASH_SEEDS:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "_subset_pass"], capture_output=True,
                              text=True, env=dict(os.environ, PYTHONHASHSEED=seed))
        if proc.returncode != 0:
            raise ContractViolation(proc.stderr[-2000:])
        results.append(json.loads(proc.stdout))
    summary = {"subset_ordinals": list(SUBSET_ORDINALS),
               "process_a_all_equal": all(results[0][str(o)] for o in SUBSET_ORDINALS),
               "process_b_all_equal": all(results[1][str(o)] for o in SUBSET_ORDINALS),
               "loaded_models": [r["loaded_models"] for r in results]}
    print(json.dumps(summary))
    return 0 if summary["process_a_all_equal"] and summary["process_b_all_equal"] else 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "build":
        sys.exit(build())
    if command == "verify-subset":
        sys.exit(verify_subset())
    if command == "_subset_pass":
        sys.stdout.write(json.dumps(subset_pass()))
        sys.exit(0)
    raise SystemExit("usage: corpus_embeddings.py build | verify-subset")
