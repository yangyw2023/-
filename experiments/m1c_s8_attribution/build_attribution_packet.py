"""S8 retrieval failure attribution 的人工审核包（DECISIONS 2026-10-02 "S8 failure attribution protocol closure"）。

完全机械：只读冻结输入（testset、GoldChunkMap、corpus、三份已提交的 S8 top-20 artifact），各自 sha 与冻结字面量比较；
lexical overlap 只用已冻结的 BM25 analyzer（components.retrievers.bm25.analyze）。不检索、不调用 LLM / Ollama / 网络。
不给任何题写最终 FailureTag：human_failure_tag 一律为 PENDING_HUMAN，human_failure_note 为空。

用法: python3 experiments/m1c_s8_attribution/build_attribution_packet.py   # 生成 packet.csv + packet.md（拒绝覆盖）
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import typing

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import ContractViolation  # noqa: E402
from components.retrievers import bm25  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(OUT_DIR, "failure_attribution_packet.csv")
MD_PATH = os.path.join(OUT_DIR, "failure_attribution_packet.md")

# 冻结输入（sha 抄自 DECISIONS 各 closure 条目，不由被检文件自算）。
FROZEN = {
    "testset": ("eval/testset_v5_3.jsonl", "05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b"),
    "gold_chunk_map": ("eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json",
                       "8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc"),
    "corpus": ("corpus/chunks.jsonl", "c89787778448d773f4fe5e00dbea328795821860412da01edda0da110425f4eb"),
    "bm25_analyzer": ("components/retrievers/bm25.py", "11ee5029899c3c55070de9a6fbd5622eb75f3d1c3a25c05856dd9489591c61ef"),
    "bm25": ("experiments/m1c_s8_bm25/s8_bm25_results.jsonl", "9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8"),
    "vector": ("experiments/m1c_s8_vector/s8_vector_results.jsonl", "0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073"),
    "hybrid": ("experiments/m1c_s8_hybrid/s8_hybrid_results.jsonl", "5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8"),
}
ROUTES = ("bm25", "vector", "hybrid")

# 人工裁决的选择规则（protocol closure）。
TIER2_FIRST_GOLD_RANK_ABOVE = 5          # 某路 first_gold_rank > 5 且该路 top-20 有 gold → Tier 2
TIER1_DESIGNATED = {                     # 执行手册 / prereg 明确点名、并附带观察 / 审核 / 归因要求的题
    "CD01": "执行手册 S8.4：CD01 的单独观察结果打出来了",
    "ML01": "执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出",
    "ML02": "执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出",
    "ML03": "执行手册 S8.4：多语种题检索 Recall 单独报；embedder 与生成模型的归因区分必须在 M2 之前做出",
    "CN03": "prereg §8.2：CN03_CITATION_LOGIC = ANNOTATION_CONFLICT_REQUIRES_HUMAN_REVIEW（标注冲突，不是检索失败指定）",
}
# FailureTag 适用性矩阵中 S8_RETRIEVAL_APPLICABLE 的取值（DECISIONS protocol closure）；人工只从这里选。
S8_APPLICABLE_TAGS = ("parse_failure", "chunk_boundary", "bm25_miss", "vector_miss", "fusion_miss")
PENDING_HUMAN = "PENDING_HUMAN"
TOP_HITS_SHOWN = 5
EXCERPT_CHARS = 240
CSV_COLUMNS = (
    "question_id", "expected", "type", "language", "review_tier", "tier1_reasons", "tier2_routes", "gold_count",
    "gold_chunk_ids",
    *(f"{r}_{f}" for r in ROUTES for f in ("first_gold_rank", "gold_ranks", "top20_candidate_miss", "top5")),
    "query_tokens", "lexical_overlap_with_gold", "multilingual", "human_failure_tag", "human_failure_note",
)


def file_bytes(rel_path: str) -> bytes:
    with open(os.path.join(REPO_ROOT, rel_path), "rb") as handle:
        return handle.read()


def load_frozen() -> dict:
    data = {}
    for name, (rel_path, expected) in FROZEN.items():
        raw = file_bytes(rel_path)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ContractViolation(f"{rel_path} sha 与冻结值不符")
        data[name] = raw.decode("utf-8")
    if not set(S8_APPLICABLE_TAGS) <= set(typing.get_args(contracts.FailureTag)):
        raise ContractViolation("S8_APPLICABLE_TAGS 含非 FailureTag 值")
    return data


def route_rows(text: str) -> dict[str, dict]:
    lines = text.splitlines()
    return {row["question_id"]: row for row in map(json.loads, lines[1:])}


def flat(text: str) -> str:
    return " ".join(text.split())


def hit_compact(rank: int, hit: dict, diag: dict | None) -> str:
    routes = "" if diag is None else " [bm25={} vector={}]".format(
        diag["bm25"]["rank"] if diag["bm25"]["present"] else "-", diag["vector"]["rank"] if diag["vector"]["present"] else "-")
    return (f"{rank}:{hit['chunk_id']}(raw={hit['raw_score']},rel={hit['relevance']},match={hit['match_score']})"
            f"{routes}")


def build() -> int:
    for path in (CSV_PATH, MD_PATH):
        if os.path.exists(path):
            raise ContractViolation(f"拒绝覆盖已有 packet: {path}")
    data = load_frozen()
    items = [json.loads(line) for line in data["testset"].splitlines()]
    gold_map = json.loads(data["gold_chunk_map"])["mapping"]
    chunks = {c["id"]: c for c in map(json.loads, data["corpus"].splitlines())}
    rows = {name: route_rows(data[name]) for name in ROUTES}
    for name in ROUTES:
        if list(rows[name]) != [i["id"] for i in items]:
            raise ContractViolation(f"{name} artifact 题目序列与 testset 不同")

    answer = [i for i in items if i["expected"] == "answer"]
    diag = {}                                 # (qid, route) → first_gold_rank / gold_ranks / miss
    for item in answer:
        gold = set(gold_map[item["id"]])
        for name in ROUTES:
            ranks = [r for r, h in enumerate(rows[name][item["id"]]["hits"], start=1) if h["chunk_id"] in gold]
            diag[item["id"], name] = {"first_gold_rank": ranks[0] if ranks else None, "gold_ranks": ranks, "miss": not ranks}

    tier1 = {}
    for item in answer:
        reasons = [f"top20_candidate_miss:{name}" for name in ROUTES if diag[item["id"], name]["miss"]]
        if item["id"] in TIER1_DESIGNATED:
            reasons.append("designated:" + TIER1_DESIGNATED[item["id"]])
        if reasons:
            tier1[item["id"]] = reasons
    tier2 = {item["id"]: [name for name in ROUTES if (diag[item["id"], name]["first_gold_rank"] or 0) > TIER2_FIRST_GOLD_RANK_ABOVE]
             for item in answer}
    tier2 = {qid: routes for qid, routes in tier2.items() if routes}
    population = [i for i in answer if i["id"] in tier1 or i["id"] in tier2]

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    md = [header_md(items, answer, diag, tier1, tier2, population)]
    for item in population:
        qid = item["id"]
        query_tokens = bm25.analyze(item["question"])
        overlap = {cid: sorted(set(query_tokens) & set(bm25.analyze(chunks[cid]["text"]))) for cid in gold_map[qid]}
        record = {
            "question_id": qid, "expected": item["expected"], "type": item["type"], "language": item["language"],
            "review_tier": "TIER1" if qid in tier1 else "TIER2", "tier1_reasons": " | ".join(tier1.get(qid, [])),
            "tier2_routes": ";".join(tier2.get(qid, [])), "gold_count": len(gold_map[qid]),
            "gold_chunk_ids": ";".join(gold_map[qid]),
            "query_tokens": " ".join(query_tokens),
            "lexical_overlap_with_gold": " | ".join(f"{cid}: {' '.join(tokens) or '∅'}" for cid, tokens in overlap.items()),
            "multilingual": item["language"] != "en",
            "human_failure_tag": PENDING_HUMAN, "human_failure_note": "",
        }
        for name in ROUTES:
            hits = rows[name][qid]["hits"]
            diags = rows[name][qid].get("route_diagnostics")
            d = diag[qid, name]
            record.update({
                f"{name}_first_gold_rank": d["first_gold_rank"] if d["first_gold_rank"] is not None else "",
                f"{name}_gold_ranks": ";".join(map(str, d["gold_ranks"])),
                f"{name}_top20_candidate_miss": d["miss"],
                f"{name}_top5": " ; ".join(hit_compact(r, h, diags[r - 1] if diags else None)
                                           for r, h in enumerate(hits[:TOP_HITS_SHOWN], start=1)),
            })
        writer.writerow(record)
        md.append(question_md(item, gold_map[qid], chunks, rows, diag, tier1, tier2, query_tokens, overlap))
    md.append(appendix_md(items, answer, diag, rows, gold_map))
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(csv_buffer.getvalue())
    with open(MD_PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(md))
    print(json.dumps({"tier1": list(tier1), "tier2": tier2, "population": [i["id"] for i in population]}, ensure_ascii=False))
    return 0


def cell(text: object) -> str:
    return flat(str(text)).replace("|", "\\|")


def loc(chunk: dict) -> str:
    return f"{chunk['doc_id']} p.{chunk['pdf_page']} §{chunk['section']}"


def header_md(items, answer, diag, tier1, tier2, population) -> str:
    lines = [
        "# S8 retrieval failure attribution packet（人工审核）", "",
        "协议：DECISIONS 2026-10-02 \"S8 failure attribution protocol closure\"。本文件由 `build_attribution_packet.py` 从冻结输入机械生成，"
        "**没有任何 AI 最终归因**。", "",
        "**你只需要在 `failure_attribution_packet.csv` 里填两列**：`human_failure_tag`（初始 `PENDING_HUMAN`）与 `human_failure_note`。"
        "rank / sha / top hits 都是机械值，不需要复核。", "",
        "S8 可用的 FailureTag（矩阵 A 类）：" + "、".join(f"`{t}`" for t in S8_APPLICABLE_TAGS) +
        "。`ranking_miss` / `context_truncation` 属 packing 阶段，`generation_miss` / `refusal_miss` / `distractor_capture` 属生成阶段，本轮不用。", "",
        "冻结输入：", "",
        *[f"- {name}: `{rel}` `{sha}`" for name, (rel, sha) in FROZEN.items()], "",
        "## 审核人口（机械规则）", "",
        "- Tier 1：任一路 top-20 candidate miss（gold ∩ top20 = ∅），或执行手册 / prereg 明确点名的题。",
        f"- Tier 2：某一路 first_gold_rank > {TIER2_FIRST_GOLD_RANK_ABOVE} 且该路 top-20 仍有 gold（ranking diagnostic，不是自动 failure label）。", "",
        "| question_id | review_tier | Tier 1 理由 | Tier 2 routes |", "|---|---|---|---|",
        *[f"| {i['id']} | {'TIER1' if i['id'] in tier1 else 'TIER2'} | {cell(' / '.join(tier1.get(i['id'], [])) or '—')} | "
          f"{';'.join(tier2.get(i['id'], [])) or '—'} |" for i in population], "",
    ]
    return "\n".join(lines)


def question_md(item, gold_ids, chunks, rows, diag, tier1, tier2, query_tokens, overlap) -> str:
    qid = item["id"]
    out = [f"---", "", f"## {qid}（{'TIER1' if qid in tier1 else 'TIER2'}）", "",
           f"- expected / type / language：{item['expected']} / {item['type']} / {item['language']}",
           f"- question：{item['question']}",
           f"- required_elements：{json.dumps(item['required_elements'], ensure_ascii=False)}",
           f"- acceptable_elements：{json.dumps(item['acceptable_elements'], ensure_ascii=False)}",
           f"- citations：{json.dumps(item['citations'], ensure_ascii=False)}",
           f"- query tokens（BM25 analyzer）：`{' '.join(query_tokens)}`", "",
           "### gold（GoldChunkMap）", ""]
    for cid in gold_ids:
        out += [f"**{cid}** — {loc(chunks[cid])}；与 query 共享 token：`{' '.join(overlap[cid]) or '∅'}`", "",
                "> " + flat(chunks[cid]["text"]), ""]
    out += ["### 三路诊断", "", "| route | first_gold_rank | gold_ranks | top20_candidate_miss |", "|---|---|---|---|"]
    for name in ROUTES:
        d = diag[qid, name]
        out.append(f"| {name} | {d['first_gold_rank'] if d['first_gold_rank'] is not None else '—'} | "
                   f"{d['gold_ranks'] or '[]'} | {d['miss']} |")
    gold = set(gold_ids)
    for name in ROUTES:
        hits = rows[name][qid]["hits"][:TOP_HITS_SHOWN]
        diags = rows[name][qid].get("route_diagnostics")
        extra = " | bm25 rank | vector rank" if diags else ""
        out += ["", f"### {name} top {TOP_HITS_SHOWN}", "",
                f"| rank | gold | chunk_id | doc/page/section | raw | relevance | match{extra} | excerpt |",
                "|---|---|---|---|---|---|---|" + ("---|---|" if diags else "") + "---|"]
        if not hits:
            n_columns = 8 + (2 if diags else 0)
            out.append("| — | " + " | ".join(["", "（该路返回 0 条）"] + [""] * (n_columns - 3)) + " |")
        for rank, hit in enumerate(hits, start=1):
            ch = chunks[hit["chunk_id"]]
            routes = ""
            if diags:
                dg = diags[rank - 1]
                routes = " | " + " | ".join(str(dg[r]["rank"]) if dg[r]["present"] else "—" for r in ("bm25", "vector"))
            out.append(f"| {rank} | {'✓' if hit['chunk_id'] in gold else ''} | {hit['chunk_id']} | {loc(ch)} | {hit['raw_score']} | "
                       f"{hit['relevance']} | {hit['match_score']}{routes} | {cell(ch['text'][:EXCERPT_CHARS])}… |")
    out += ["", "**human_failure_tag**：`PENDING_HUMAN`　**human_failure_note**：（在 CSV 填写）", ""]
    return "\n".join(out)


def appendix_md(items, answer, diag, rows, gold_map) -> str:
    out = ["---", "", "## 附录 A · 全部 31 道可答题的 ranking diagnostic（机械值，不是 failure label）", "",
           "| question_id | language | gold_count | " + " | ".join(f"{r} first / gold_ranks" for r in ROUTES) + " |",
           "|---|---|---|" + "---|" * len(ROUTES)]
    for item in answer:
        cells = []
        for name in ROUTES:
            d = diag[item["id"], name]
            cells.append(f"{d['first_gold_rank'] if d['first_gold_rank'] is not None else '—'} / {d['gold_ranks'] or '[]'}")
        out.append(f"| {item['id']} | {item['language']} | {len(gold_map[item['id']])} | " + " | ".join(cells) + " |")
    out += ["", "## 附录 B · TOP_K_RETRIEVE = 20 的 evidence（只准备证据，不做 L1 决策）", ""]
    for name in ROUTES:
        misses = [i["id"] for i in answer if diag[i["id"], name]["miss"]]
        out.append(f"- {name}：top-20 无 gold 的可答题 {len(misses)} / {len(answer)}：{misses or '[]'}")
    out += ["", "只是当前 39 题评测集上的 evidence，不自动证明 20 普遍足够。", "",
            "## 附录 C · refuse / trap 题（不进入 candidate_retrieval_miss 分母；本轮不赋 refusal_miss）", "",
            "| question_id | type | " + " | ".join(f"{r} max_match / top1" for r in ROUTES) + " |", "|---|---|" + "---|" * len(ROUTES)]
    for item in items:
        if item["expected"] != "refuse":
            continue
        cells = []
        for name in ROUTES:
            row = rows[name][item["id"]]
            top1 = row["hits"][0]["chunk_id"] if row["hits"] else "—"
            cells.append(f"{row['max_match_score']} / {top1}")
        out.append(f"| {item['id']} | {item['type']} | " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(build())
