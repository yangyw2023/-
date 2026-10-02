"""S9 MIN_RELEVANCE 同集校准（DECISIONS 2026-10-02 "S9 MIN_RELEVANCE calibration protocol"，人工裁决 S9-D1–D3）。

只读冻结输入：S8 hybrid top-20 artifact（gate 分数）、评测集、GoldChunkMap（gold 诊断）；BM25 / vector artifact 只作诊断。
不检索、不融合、不调用 Ollama；不修改 core/contracts.py —— 只产出 PROPOSED_MIN_RELEVANCE，最终值由人工决定。

契约:
  - gate_score(q) = max(match_score over 该题冻结 hybrid top-20)，与 runtime 判定式（refuse ⇔ score < MIN_RELEVANCE，严格 <）同一判定量。
  - 校准人口 = 31 道可答题 + 7 道计分陷阱（exclude_from_primary_score 为真的陷阱只做描述性展示）。
  - candidate = math.nextafter(trap_max, math.inf)；candidate <= answer_min → PERFECT_SAME_SET_SEPARATION 并给出 PROPOSED_MIN_RELEVANCE；
    否则不给出最终阈值，只输出 trade-off 表。LOO = 7 折，每折 nextafter(其余 6 道陷阱 max)。
  - 冻结输入 sha 不符、DECISIONS 中找不到协议条目、或人口计数不符 → ContractViolation，不写任何文件；已有输出 → 拒绝覆盖。
  - CSV / JSON / SVG 为 normative（确定性字节）；run.log 含墙钟时间，不参与字节比较。

用法: python3 eval/calibrate_threshold.py --out-dir experiments/m1c_s9_threshold
      （--emit-normative 只供 Run B 子进程使用：把三个 normative 文件的内容以 JSON 写到 stdout，不写文件）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from core.contracts import ContractViolation  # noqa: E402

# 冻结输入（sha 抄自 DECISIONS 各 closure 条目）。
FROZEN = {
    "hybrid": ("experiments/m1c_s8_hybrid/s8_hybrid_results.jsonl", "5d859a901f49155aa8be6f4e84f3b79bf8e564261d026f0397ef54a1cff5e9a8"),
    "bm25": ("experiments/m1c_s8_bm25/s8_bm25_results.jsonl", "9ce4df232af8c395e0749dcb2fd9c84e5376a7939ae20af7005b12d54dac3ba8"),
    "vector": ("experiments/m1c_s8_vector/s8_vector_results.jsonl", "0e80682cfded9fb73db0b9204120582984f33604ab5bfbc88694d47f9d371073"),
    "testset": ("eval/testset_v5_3.jsonl", "05614407a0e43a7f912ae17864892b0f069a22d1ad9d1ec2bfb7362150883e8b"),
    "gold_chunk_map": ("eval/gold_chunk_map/map__ts-v5.3__corpus-c8978777__builder-kaiva_phase_b_builder_v1.json",
                       "8cf9f3be1b1bc296c196d1b5598c1351d456f83b1a05a6043c7b643f0fedeacc"),
}
DIAGNOSTIC_ROUTES = ("bm25", "vector")
PROTOCOL_HEADING = "## 2026-10-02 · S9 MIN_RELEVANCE calibration protocol"
EXPECTED_ANSWERS = 31
EXPECTED_SCORED_TRAPS = 7
DISPLAY_DECIMALS = 6
RUN_B_HASH_SEED = "4242"
OUT_FILES = {"csv": "s9_threshold_scores.csv", "json": "s9_threshold_calibration.json",
             "svg": "s9_threshold_distribution.svg", "log": "s9_threshold_run.log"}
CSV_COLUMNS = ("question_id", "expected", "population", "included_in_calibration", "gate_score", "gold_score_diagnostic",
               "selected_threshold", "predicted_refuse")

# SVG 版式（像素）。
SVG_WIDTH, SVG_HEIGHT = 960, 420
PLOT_LEFT, PLOT_RIGHT = 200, 920
ROW_Y = {"answer_gate": 130, "trap_gate": 210, "answer_gold": 290}
AXIS_Y = 350
POINT_RADIUS = 5
AXIS_STEP = 0.05
TITLE_Y, SUBTITLE_Y = 32, 56
COLORS = {"answer": "#2563eb", "trap": "#dc2626", "excluded": "#6b7280", "gold": "#0d9488", "threshold": "#111827", "axis": "#9ca3af"}


def fmt(x: float) -> str:
    return f"{x:.{DISPLAY_DECIMALS}f}"


def file_sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_inputs() -> dict:
    data = {}
    for name, (rel, expected) in FROZEN.items():
        path = os.path.join(REPO_ROOT, rel)
        if file_sha256(path) != expected:
            raise ContractViolation(f"{rel} sha 与冻结值不符")
        with open(path, encoding="utf-8") as handle:
            data[name] = handle.read()
    with open(os.path.join(REPO_ROOT, "DECISIONS.md"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    if PROTOCOL_HEADING not in lines:
        raise ContractViolation("DECISIONS 中没有 S9 协议条目：协议必须先于校准冻结")
    data["protocol_line"] = lines.index(PROTOCOL_HEADING) + 1
    return data


def route_rows(text: str) -> dict[str, dict]:
    return {row["question_id"]: row for row in map(json.loads, text.splitlines()[1:])}


def gate(row: dict) -> float | None:
    """该题 top-20 的 max(match_score)；检索为空 → None（runtime 上即"确实没检索到"）。"""
    return max((h["match_score"] for h in row["hits"]), default=None)


def calibrate(data: dict) -> tuple[dict, list[dict]]:
    items = [json.loads(line) for line in data["testset"].splitlines()]
    gold = json.loads(data["gold_chunk_map"])["mapping"]
    hybrid = route_rows(data["hybrid"])
    if list(hybrid) != [i["id"] for i in items]:
        raise ContractViolation("hybrid artifact 题目序列与评测集不同")
    rows = []
    for item in items:
        population = ("answer" if item["expected"] == "answer"
                      else "excluded_trap" if item["exclude_from_primary_score"] else "scored_trap")
        hits = hybrid[item["id"]]["hits"]
        gold_scores = [h["match_score"] for h in hits if h["chunk_id"] in set(gold.get(item["id"], []))]
        rows.append({"question_id": item["id"], "expected": item["expected"], "population": population,
                     "included_in_calibration": population != "excluded_trap", "gate_score": gate(hybrid[item["id"]]),
                     "gold_score_diagnostic": max(gold_scores) if gold_scores else None})
    answers = [r["gate_score"] for r in rows if r["population"] == "answer"]
    traps = {r["question_id"]: r["gate_score"] for r in rows if r["population"] == "scored_trap"}
    if len(answers) != EXPECTED_ANSWERS or len(traps) != EXPECTED_SCORED_TRAPS or None in answers or None in traps.values():
        raise ContractViolation(f"校准人口不符: answers={len(answers)} scored_traps={len(traps)}")

    trap_max, answer_min = max(traps.values()), min(answers)
    candidate = math.nextafter(trap_max, math.inf)
    perfect = candidate <= answer_min
    proposed = candidate if perfect else None
    folds = []
    for held_out, score in traps.items():
        fold_threshold = math.nextafter(max(s for q, s in traps.items() if q != held_out), math.inf)
        folds.append({"held_out_qid": held_out, "training_trap_max": max(s for q, s in traps.items() if q != held_out),
                      "fold_threshold": fold_threshold, "held_out_score": score, "held_out_rejected": score < fold_threshold,
                      "answer_false_reject_count": sum(a < fold_threshold for a in answers)})
    tradeoff = None
    if not perfect:
        cuts = sorted({math.nextafter(s, math.inf) for s in traps.values()} | set(answers))
        tradeoff = [{"threshold": t, "answer_false_rejects": sum(a < t for a in answers),
                     "scored_traps_rejected": sum(s < t for s in traps.values())} for t in cuts]
    for r in rows:
        r["selected_threshold"] = proposed
        r["predicted_refuse"] = None if proposed is None or r["gate_score"] is None else r["gate_score"] < proposed
    golds = [r["gold_score_diagnostic"] for r in rows if r["population"] == "answer"]
    result = {
        "status": "S9 same-set provisional MIN_RELEVANCE calibration; PROPOSED value only (human decides; contracts unchanged)",
        "protocol": {"decisions_heading": PROTOCOL_HEADING, "route": "hybrid", "population": "31 answer + 7 scored traps",
                     "excluded_from_calibration": [r["question_id"] for r in rows if r["population"] == "excluded_trap"],
                     "gate_statistic": "max(match_score over frozen hybrid top-20)", "runtime_rule": "refuse iff gate_score < MIN_RELEVANCE",
                     "selection_rule": "CONSERVATIVE_LOW_NEXTAFTER", "data_status": "SAME_SET_PROVISIONAL",
                     "interpretation": "EMPIRICAL_OPERATING_THRESHOLD (not a probability / calibrated confidence)"},
        "inputs": {name: {"path": rel, "sha256": sha} for name, (rel, sha) in FROZEN.items()},
        "contracts_version": contracts.CONTRACTS_VERSION, "current_contract_min_relevance": contracts.MIN_RELEVANCE,
        "trap_max": trap_max, "answer_min": answer_min, "candidate_threshold": candidate,
        "perfect_same_set_separation": perfect, "proposed_min_relevance": proposed,
        "proposed_min_relevance_display": fmt(proposed) if proposed is not None else None,
        "same_set": None if proposed is None else {
            "scored_traps_rejected": sum(s < proposed for s in traps.values()), "scored_traps_n": len(traps),
            "answer_false_rejected": sum(a < proposed for a in answers), "answers_n": len(answers)},
        "loo": {"folds": folds, "held_out_traps_rejected": sum(f["held_out_rejected"] for f in folds), "folds_n": len(folds),
                "answer_false_rejects_total_over_folds": sum(f["answer_false_reject_count"] for f in folds),
                "answer_false_rejects_denominator": f"{len(folds)} folds x {len(answers)} answers"},
        "tradeoff_table_if_not_separable": tradeoff,
        "ranges": {"scored_trap_gate": [min(traps.values()), trap_max], "answer_gate": [answer_min, max(answers)],
                   "answer_gold_diagnostic": [min(g for g in golds if g is not None), max(g for g in golds if g is not None)],
                   "answer_gold_missing_in_top20": sum(g is None for g in golds),
                   "answers_with_gold_score_below_candidate": sum(g is not None and g < candidate for g in golds)},
        "diagnostic_routes": diagnostics(data, items),
    }
    return result, rows


def diagnostics(data: dict, items: list[dict]) -> dict:
    """BM25 / vector 的 gate 分数范围，只作诊断（DIAGNOSTIC_ONLY），不选阈值。"""
    out = {}
    for name in DIAGNOSTIC_ROUTES:
        rows = route_rows(data[name])
        answers = [gate(rows[i["id"]]) for i in items if i["expected"] == "answer"]
        traps = [gate(rows[i["id"]]) for i in items if i["expected"] == "refuse" and not i["exclude_from_primary_score"]]
        present = [a for a in answers if a is not None]
        out[name] = {"scored_trap_gate": [min(traps), max(traps)], "answer_gate": [min(present), max(present)],
                     "answers_with_empty_retrieval": sum(a is None for a in answers),
                     "answers_at_or_below_trap_max": sum(a <= max(traps) for a in present), "status": "DIAGNOSTIC_ONLY"}
    return out


def render_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: ("" if r[k] is None else repr(r[k]) if isinstance(r[k], float) else str(r[k]).lower()
                             if isinstance(r[k], bool) else r[k]) for k in CSV_COLUMNS})
    return buffer.getvalue()


def render_svg(result: dict, rows: list[dict]) -> str:
    values = [r["gate_score"] for r in rows if r["gate_score"] is not None] + \
             [r["gold_score_diagnostic"] for r in rows if r["gold_score_diagnostic"] is not None]
    lo = math.floor(min(values) / AXIS_STEP) * AXIS_STEP
    hi = math.ceil(max(values) / AXIS_STEP) * AXIS_STEP

    def x(v: float) -> float:
        return PLOT_LEFT + (v - lo) / (hi - lo) * (PLOT_RIGHT - PLOT_LEFT)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="13">',
           f'<rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" fill="#ffffff"/>',
           f'<text x="{PLOT_LEFT}" y="{TITLE_Y}" font-size="17" font-weight="bold">S9 MIN_RELEVANCE — Same-set provisional calibration</text>',
           f'<text x="{PLOT_LEFT}" y="{SUBTITLE_Y}" fill="#4b5563">gate score = max(match_score) over frozen hybrid top-20 · '
           f'refuse iff score &lt; threshold · not a probability</text>']
    labels = {"answer_gate": "31 answers · gate score", "trap_gate": "7 scored traps · gate score", "answer_gold": "31 answers · gold score (diagnostic)"}
    for key, y in ROW_Y.items():
        out.append(f'<line x1="{PLOT_LEFT}" y1="{y}" x2="{PLOT_RIGHT}" y2="{y}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{PLOT_LEFT - 12}" y="{y + 4}" text-anchor="end">{labels[key]}</text>')
    for r in rows:
        if r["population"] == "answer":
            out.append(f'<circle cx="{x(r["gate_score"]):.2f}" cy="{ROW_Y["answer_gate"]}" r="{POINT_RADIUS}" fill="{COLORS["answer"]}" '
                       f'fill-opacity="0.45"><title>{r["question_id"]} {fmt(r["gate_score"])}</title></circle>')
            if r["gold_score_diagnostic"] is not None:
                out.append(f'<circle cx="{x(r["gold_score_diagnostic"]):.2f}" cy="{ROW_Y["answer_gold"]}" r="{POINT_RADIUS}" '
                           f'fill="{COLORS["gold"]}" fill-opacity="0.45"><title>{r["question_id"]} gold {fmt(r["gold_score_diagnostic"])}</title></circle>')
        elif r["population"] == "scored_trap":
            out.append(f'<circle cx="{x(r["gate_score"]):.2f}" cy="{ROW_Y["trap_gate"]}" r="{POINT_RADIUS}" fill="{COLORS["trap"]}" '
                       f'fill-opacity="0.55"><title>{r["question_id"]} {fmt(r["gate_score"])}</title></circle>')
        else:
            out.append(f'<circle cx="{x(r["gate_score"]):.2f}" cy="{ROW_Y["trap_gate"]}" r="{POINT_RADIUS}" fill="none" '
                       f'stroke="{COLORS["excluded"]}" stroke-width="1.5"><title>{r["question_id"]} {fmt(r["gate_score"])} '
                       f'(excluded from calibration)</title></circle>')
    steps = round((hi - lo) / AXIS_STEP)
    out.append(f'<line x1="{PLOT_LEFT}" y1="{AXIS_Y}" x2="{PLOT_RIGHT}" y2="{AXIS_Y}" stroke="{COLORS["axis"]}"/>')
    for i in range(steps + 1):
        v = lo + i * AXIS_STEP
        out.append(f'<line x1="{x(v):.2f}" y1="{AXIS_Y}" x2="{x(v):.2f}" y2="{AXIS_Y + 6}" stroke="{COLORS["axis"]}"/>')
        out.append(f'<text x="{x(v):.2f}" y="{AXIS_Y + 22}" text-anchor="middle" fill="#4b5563">{v:.2f}</text>')
    threshold = result["proposed_min_relevance"]
    if threshold is not None:
        top, bottom = ROW_Y["answer_gate"] - 30, ROW_Y["answer_gold"] + 20
        out.append(f'<line x1="{x(threshold):.2f}" y1="{top}" x2="{x(threshold):.2f}" y2="{bottom}" stroke="{COLORS["threshold"]}" '
                   f'stroke-width="1.5" stroke-dasharray="5,4"/>')
        out.append(f'<text x="{x(threshold) + 6:.2f}" y="{top + 12}" fill="{COLORS["threshold"]}">PROPOSED_MIN_RELEVANCE = '
                   f'{fmt(threshold)} (nextafter of scored-trap max)</text>')
    legend_y = SVG_HEIGHT - 16
    out.append(f'<text x="{PLOT_LEFT}" y="{legend_y}" fill="#4b5563">hollow grey = TR02 (excluded from calibration, descriptive) · '
               f'same-set provisional: not a generalization estimate</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def normative() -> tuple[dict, dict[str, str]]:
    data = load_inputs()
    result, rows = calibrate(data)
    texts = {"csv": render_csv(rows), "json": json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
             "svg": render_svg(result, rows)}
    return {"protocol_line": data["protocol_line"], "result": result}, texts


def git_state() -> dict:
    head = subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO_ROOT, "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.splitlines()
    return {"head": head, "tracked_changes": dirty}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir")
    parser.add_argument("--emit-normative", action="store_true")
    args = parser.parse_args(argv)
    meta, texts = normative()
    if args.emit_normative:
        sys.stdout.write(json.dumps(texts, ensure_ascii=False, sort_keys=True))
        return 0
    if not args.out_dir:
        raise SystemExit("--out-dir 必填")
    out = {k: os.path.join(args.out_dir, v) for k, v in OUT_FILES.items()}
    existing = [p for p in out.values() if os.path.exists(p)]
    if existing:
        raise ContractViolation(f"拒绝覆盖已有输出: {existing}")
    os.makedirs(args.out_dir, exist_ok=True)
    for key in ("csv", "json", "svg"):
        with open(out[key], "w", encoding="utf-8", newline="") as handle:
            handle.write(texts[key])
    run_b = subprocess.run([sys.executable, os.path.abspath(__file__), "--emit-normative"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=RUN_B_HASH_SEED), cwd=REPO_ROOT)
    run_b_ok = run_b.returncode == 0 and json.loads(run_b.stdout) == texts
    r = meta["result"]
    log = {"event": "s9_calibration_run", "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "git": git_state(), "script_sha256": file_sha256(os.path.abspath(__file__)),
           "protocol": {"file": "DECISIONS.md", "line": meta["protocol_line"], "heading": PROTOCOL_HEADING},
           "inputs": r["inputs"], "contracts_version": r["contracts_version"],
           "TEST_SET_THRESHOLD_CALIBRATION": "YES", "SAME_SET_PROVISIONAL": "YES",
           "normative_sha256": {k: hashlib.sha256(texts[k].encode("utf-8")).hexdigest() for k in ("csv", "json", "svg")},
           "run_b": {"pythonhashseed": RUN_B_HASH_SEED, "returncode": run_b.returncode, "byte_identical": run_b_ok},
           "summary": {k: r[k] for k in ("trap_max", "answer_min", "candidate_threshold", "perfect_same_set_separation",
                                         "proposed_min_relevance", "same_set")}}
    with open(out["log"], "w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(log, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    if not run_b_ok:
        raise ContractViolation("Run A 与 Run B normative 输出不逐字节相同")
    print(json.dumps(log["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
