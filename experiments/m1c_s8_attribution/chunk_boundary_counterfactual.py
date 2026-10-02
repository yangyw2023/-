"""S8 失败归因：切块边界反事实诊断（只读）。

问题：PR03 / PR04 的 BM25 top-20 漏召回，是否由"清单 / 表格与其引导语被切到不同 chunk"造成？
做法：在冻结 corpus 上用冻结 BM25 实现建索引；只把引导语（从 LEAD_MARKER 起到引导块末尾）从引导块移到答案块开头，
其余 chunk 原样不动；分别报告基线与反事实下每个 gold chunk 在完整 BM25 排序中的名次。
判据：反事实下该题至少一个 gold 名次 ≤ TOP_K_RETRIEVE → 切块边界足以解释该路漏召回（R4）。

契约：
  - 输入文件 sha256 与冻结字面量不符 → InputIdentityError，不输出任何结果。
  - LEAD_MARKER 不在引导块中、或 chunk id 不存在 → InputIdentityError（文本前提不成立，不做猜测性修补）。
  - 不写任何文件、不调用网络 / LLM / embedder；结果打印为 JSON（stdout）。
  - 退出码：0 = 所有反事实都让 gold 进入 top-K；1 = 至少一题没有（调用方应停止录入）。
本诊断不是 S8 baseline 的一部分，不产生 artifact；数值只用于支撑人工归因。

用法: python3 experiments/m1c_s8_attribution/chunk_boundary_counterfactual.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from components.retrievers.bm25 import BM25Retriever  # noqa: E402
from core.contracts import TOP_K_RETRIEVE, Chunk  # noqa: E402

CORPUS = ("corpus/chunks.jsonl", "c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb")
TESTSET = ("eval/testset_v5_3.jsonl", "05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b")
GOLD_MAP = ("eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json",
            "8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc")

# (question_id, 引导块, 答案块, 引导语起始标记)。引导语 = 引导块中从标记起到块末尾的文本。
CASES: tuple[tuple[str, str, str, str], ...] = (
    ("PR04", "SMM:p35:0", "SMM:p35:1", "All permits to be correctly numbered"),
    ("PR03", "CMM:p74:0", "CMM:p74:1", "The onboard complaint procedure"),
)
LEAD_JOINER = "\n"
HASH_BLOCK_BYTES = 1 << 20


class InputIdentityError(RuntimeError):
    """冻结输入身份或文本前提不成立。"""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _checked(spec: tuple[str, str]) -> str:
    path, expected = spec
    actual = _sha256(path)
    if actual != expected:
        raise InputIdentityError(f"{path} sha256 {actual} != 冻结值 {expected}")
    return path


def _load_corpus(path: str) -> list[Chunk]:
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    if lines[-1] != "" or any(not line for line in lines[:-1]):
        raise InputIdentityError("corpus 含空行或缺末尾换行，corpus_ordinal 与行序不一致")
    return [Chunk(**json.loads(line)) for line in lines[:-1]]


def _gold_ranks(chunks: list[Chunk], question: str, gold: list[str]) -> dict[str, int | None]:
    """gold chunk 在完整 BM25 排序（全部正分 chunk）中的 1-based 名次；未得正分为 None。"""
    order = [record.chunk_id for record in BM25Retriever(chunks).search_records(question, k=len(chunks))]
    position = {chunk_id: index + 1 for index, chunk_id in enumerate(order)}
    return {chunk_id: position.get(chunk_id) for chunk_id in gold}


def _move_lead(chunks: list[Chunk], lead_id: str, answer_id: str, marker: str) -> list[Chunk]:
    by_id = {chunk.id: chunk for chunk in chunks}
    if lead_id not in by_id or answer_id not in by_id:
        raise InputIdentityError(f"chunk 不存在: {lead_id} / {answer_id}")
    lead_text = by_id[lead_id].text
    start = lead_text.find(marker)
    if start < 0:
        raise InputIdentityError(f"引导语标记 {marker!r} 不在 {lead_id} 中")
    lead_sentence = lead_text[start:].strip()
    replaced = {
        lead_id: lead_text[:start].rstrip(),
        answer_id: lead_sentence + LEAD_JOINER + by_id[answer_id].text,
    }
    return [dataclasses.replace(chunk, text=replaced[chunk.id]) if chunk.id in replaced else chunk for chunk in chunks]


def main() -> int:
    chunks = _load_corpus(_checked(CORPUS))
    with open(_checked(TESTSET), encoding="utf-8") as handle:
        questions = {item["id"]: item["question"] for item in map(json.loads, handle)}
    with open(_checked(GOLD_MAP), encoding="utf-8") as handle:
        gold_map = json.load(handle)["mapping"]
    report, all_recovered = [], True
    for qid, lead_id, answer_id, marker in CASES:
        baseline = _gold_ranks(chunks, questions[qid], gold_map[qid])
        moved = _gold_ranks(_move_lead(chunks, lead_id, answer_id, marker), questions[qid], gold_map[qid])
        recovered = any(rank is not None and rank <= TOP_K_RETRIEVE for rank in moved.values())
        all_recovered &= recovered
        report.append({"question_id": qid, "lead_chunk": lead_id, "answer_chunk": answer_id,
                       "baseline_gold_ranks": baseline, "counterfactual_gold_ranks": moved,
                       "top_k": TOP_K_RETRIEVE, "recovered_into_top_k": recovered})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all_recovered else 1


if __name__ == "__main__":
    sys.exit(main())
