#!/usr/bin/env python3
"""S4a.9c-final · canonical corpus token / packing measurement（**只测量**）。

本脚本不修改 contracts / corpus / parser / artifacts，也不选择任何新 contract 取值。
protocol 沿用 S4a.9c 旧轮（见 experiments/gate2_raw/_s4a9c_*.log），不重新设计。

五种 token 量严格分离（输出中逐项标注）:
  Q1 CHUNK_TARGET_TOKENS            INPUT_PARAMETER（分块目标，不是实际 chunk token 数）
  Q2 CHUNK_OVERLAP_TOKENS           INPUT_PARAMETER（overlap 参数，不是实测 overlap cost）
  Q3 actual chunk token count       MEASURED_OUTPUT（tokenizer 实测）
  Q4 est_tokens()                   ESTIMATOR_OUTPUT（max(1, chars // CHARS_PER_TOKEN_EST)）
  Q5 rendered context actual cost   MEASURED_OUTPUT（含 citation header / separator / framing 边界效应）

比值方向（全文统一）: ratio = actual / estimated。
  ratio > 1 → estimator 低估真实开销 → **危险侧**
  ratio < 1 → estimator 保守

用法:
    python3 scripts/s4a9c_final_canonical.py --prereg <prereg.txt> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts

# ---- tokenizer identity（与旧 9c 逐位一致，见 _s4a9c_final_real_chunks.log 头部）----
MODEL: str = "phi4-mini:latest"
MODEL_DIGEST: str = "78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753"
API: str = "http://localhost:11434/api/generate"
NUM_CTX: int = 4096
NUM_PREDICT: int = 1

# ---- 旧 protocol 参数（原样恢复，不重新设计）----
WINDOW_K: int = 5
SEPS: tuple[str, ...] = ("\n", "\n\n")
HISTORICAL_CANDIDATE: dict[str, float] = {"X": 950, "O": 206, "m": 0.86, "B": 639}
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9fÿ�]")
WS_RUN_MIN: int = 140          # 旧轮按分布断档取的判断值，不是契约阈值
SECTION_LEN_MAX: int = 60      # 同上
DANGER_THRESHOLDS: tuple[float, ...] = (1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50)
PCTS: tuple[float, ...] = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def count_tokens(prompt: str) -> int:
    """tokenizer 实测：prompt_eval_count。缺该字段一律抛异常，不回退、不估算。"""
    req = urllib.request.Request(
        API,
        data=json.dumps({"model": MODEL, "prompt": prompt, "raw": True, "stream": False,
                         "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as handle:
        payload = json.load(handle)
    if "prompt_eval_count" not in payload:
        raise RuntimeError(f"响应缺 prompt_eval_count: {str(payload)[:200]}")
    return int(payload["prompt_eval_count"])


def render(c: dict) -> str:
    """旧 9c 的 citation rendering，逐字不变。"""
    return f"[{c['doc_id']} §{c['section']} PDF p.{c['pdf_page']}]" + "\n" + c["text"]


def labels_of(c: dict) -> list[str]:
    """旧轮标签判据，原样复用（不得事后重定义）。"""
    out: list[str] = []
    ctrl = bool(CTRL_RE.search(c["text"]) or CTRL_RE.search(c["section"]))
    if ctrl:
        out.append("control_chars")
    if c["doc_id"] == "TACM" and 38 <= c["pdf_page"] <= 93 and ctrl:
        out.append("tacm_garbled")
    if max((len(m) for m in re.findall(r"[ \t]+", c["text"])), default=0) >= WS_RUN_MIN:
        out.append("whitespace_heavy")
    s = c["section"]
    if (CTRL_RE.search(s) or not re.search(r"[A-Za-z0-9]", s) or len(s) > SECTION_LEN_MAX
            or (len(s) and sum(ch.isspace() for ch in s) / len(s) >= 0.5)):
        out.append("section_suspicious")
    return sorted(out) or ["none_observed"]


def q(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def dist_line(xs) -> str:
    parts = [f"n={len(xs)}", f"min={min(xs):.4g}"]
    parts += [f"p{int(p*100)}={q(xs,p):.4g}" for p in PCTS]
    parts += [f"max={max(xs):.4g}", f"mean={sum(xs)/len(xs):.4g}"]
    return "  ".join(parts)


def sha_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="corpus/chunks.jsonl")
    ap.add_argument("--page-quality", default="ingest/page_quality.jsonl")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)

    chunks = [json.loads(l) for l in open(args.corpus, encoding="utf-8") if l.strip()]
    pq = {(r["doc_id"], r["pdf_page"]): r for r in
          (json.loads(l) for l in open(args.page_quality, encoding="utf-8") if l.strip())}

    CF = ("id", "text", "doc_id", "doc_name", "section", "section_title", "pdf_page",
          "printed_page", "issued_by", "revision", "lang", "image_ids", "source_hash")

    rows: list[dict] = []
    renders: list[str] = []
    for c in chunks:
        text_tok = count_tokens(c["text"])
        rend = render(c)
        rend_tok = count_tokens(rend)
        ch = contracts.Chunk(**{k: c[k] for k in CF})
        renders.append(rend)
        rows.append({
            "chunk_id": c["id"], "doc_id": c["doc_id"], "pdf_page": c["pdf_page"],
            "chunk_ordinal": int(c["id"].rsplit(":", 1)[1]),
            "source_channel": pq[(c["doc_id"], c["pdf_page"])]["body_source_channel"],
            "chars": len(c["text"]),
            "actual_text_tokens": text_tok, "actual_rendered_tokens": rend_tok,
            "est_tokens": ch.est_tokens(), "est_prompt_tokens": ch.est_prompt_tokens(),
            "header_increment": rend_tok - text_tok,
            "chars_per_actual_token": round(len(c["text"]) / text_tok, 6),
            "ratio_text_actual_over_est": round(text_tok / ch.est_tokens(), 6),
            "ratio_rendered_actual_over_est_prompt": round(rend_tok / ch.est_prompt_tokens(), 6),
            "labels": ";".join(labels_of(c)),
        })

    # ---- separator：真实相邻 rendered chunk 的增量成本 ----
    sep_rows: list[dict] = []
    for i in range(len(rows) - 1):
        for sep in SEPS:
            joined = count_tokens(renders[i] + sep + renders[i + 1])
            sep_rows.append({
                "pair_index": i, "sep": "\\n" if sep == "\n" else "\\n\\n",
                "left_chunk_id": rows[i]["chunk_id"], "right_chunk_id": rows[i + 1]["chunk_id"],
                "left_rendered_tokens": rows[i]["actual_rendered_tokens"],
                "right_rendered_tokens": rows[i + 1]["actual_rendered_tokens"],
                "joined_tokens": joined,
                "sep_incremental_tokens": joined - rows[i]["actual_rendered_tokens"]
                                          - rows[i + 1]["actual_rendered_tokens"],
            })

    # ---- 窗口：corpus 顺序连续 5 块（旧 protocol），两套预算分栏 ----
    scenarios = {
        "CURRENT_EXECUTABLE": {"X": contracts.MAX_PROMPT_TOKENS,
                               "O": contracts.PROMPT_OVERHEAD_RESERVE_TOKENS,
                               "m": contracts.CONTEXT_PACK_MARGIN,
                               "B": contracts.CONTEXT_PACK_BUDGET_TOKENS},
        "HISTORICAL_CANDIDATE_NOT_EXECUTABLE": dict(HISTORICAL_CANDIDATE),
    }
    ctx_cache: dict[tuple[int, int, str], int] = {}
    wrows: list[dict] = []
    for i in range(len(rows) - WINDOW_K + 1):
        hits = [contracts.Hit(chunk=contracts.Chunk(**{k: chunks[i + j][k] for k in CF}),
                              relevance=1.0 - j * 0.01, match_score=1.0 - j * 0.01)
                for j in range(WINDOW_K)]
        for name, sc in scenarios.items():
            packed = contracts.pack_context(hits, max_tokens=sc["B"], max_chunks=contracts.TOP_K_CONTEXT)
            k = len(packed)
            est_ctx = sum(h.chunk.est_prompt_tokens() for h in packed)
            for sep in SEPS:
                key = (i, k, sep)
                if key not in ctx_cache:
                    ctx_cache[key] = count_tokens(sep.join(renders[i:i + k]))
                actual_ctx = ctx_cache[key]
                wrows.append({
                    "scenario": name, "sep": "\\n" if sep == "\n" else "\\n\\n",
                    "window_index": i, "window_k": k,
                    "est_context_tokens": est_ctx,
                    "actual_context_tokens": actual_ctx,
                    "est_total_prompt_tokens": sc["O"] + est_ctx,
                    "actual_total_prompt_tokens": sc["O"] + actual_ctx,
                    "budget_X": sc["X"], "budget_B": sc["B"],
                    "over_by": sc["O"] + actual_ctx - sc["X"],
                    "overbudget": int(sc["O"] + actual_ctx > sc["X"]),
                    "est_overbudget": int(sc["O"] + est_ctx > sc["X"]),
                    "ratio_actual_over_est_context": round(actual_ctx / est_ctx, 6) if est_ctx else "",
                    "chunk_ids": "|".join(rows[i + j]["chunk_id"] for j in range(k)),
                    "labels": "|".join(rows[i + j]["labels"] for j in range(k)),
                    "all_none_observed": int(all(rows[i + j]["labels"] == "none_observed" for j in range(k))),
                })

    # ---- CSV 输出（确定性排序）----
    tag = args.tag
    cf = ["chunk_id", "doc_id", "pdf_page", "chunk_ordinal", "source_channel", "chars",
          "actual_text_tokens", "actual_rendered_tokens", "est_tokens", "est_prompt_tokens",
          "header_increment", "chars_per_actual_token", "ratio_text_actual_over_est",
          "ratio_rendered_actual_over_est_prompt", "labels"]
    paths = {
        "chunks": os.path.join(args.out_dir, f"_s4a9c_final_canonical_chunks{tag}.csv"),
        "sep": os.path.join(args.out_dir, f"_s4a9c_final_canonical_separator{tag}.csv"),
        "windows": os.path.join(args.out_dir, f"_s4a9c_final_canonical_windows{tag}.csv"),
        "none_obs": os.path.join(args.out_dir, f"_s4a9c_final_canonical_none_observed{tag}.csv"),
        "over": os.path.join(args.out_dir, f"_s4a9c_final_canonical_overbudget{tag}.csv"),
        "log": os.path.join(args.out_dir, f"_s4a9c_final_canonical{tag}.log"),
    }

    def write_csv(path, fields, data):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in data:
                writer.writerow({k: row[k] for k in fields})

    write_csv(paths["chunks"], cf, sorted(rows, key=lambda r: r["chunk_id"]))
    write_csv(paths["none_obs"], cf, sorted((r for r in rows if r["labels"] == "none_observed"),
                                            key=lambda r: r["chunk_id"]))
    sf = ["pair_index", "sep", "left_chunk_id", "right_chunk_id", "left_rendered_tokens",
          "right_rendered_tokens", "joined_tokens", "sep_incremental_tokens"]
    write_csv(paths["sep"], sf, sorted(sep_rows, key=lambda r: (r["sep"], r["pair_index"])))
    wf = ["scenario", "sep", "window_index", "window_k", "est_context_tokens",
          "actual_context_tokens", "est_total_prompt_tokens", "actual_total_prompt_tokens",
          "budget_X", "budget_B", "over_by", "overbudget", "est_overbudget",
          "ratio_actual_over_est_context", "all_none_observed", "chunk_ids", "labels"]
    wsorted = sorted(wrows, key=lambda r: (r["scenario"], r["sep"], r["window_index"]))
    write_csv(paths["windows"], wf, wsorted)
    write_csv(paths["over"], wf, [r for r in wsorted if r["overbudget"]])

    # ---- LOG ----
    out: list[str] = []
    P = out.append
    P("S4a.9c-final · canonical corpus token / packing measurement（measurement only，不改任何 contract）")
    P("=" * 96)
    P("[0] provenance")
    P(f"    corpus                  = {args.corpus} sha256={sha_file(args.corpus)} chunks={len(chunks)}")
    P(f"    page_quality            = {args.page_quality} sha256={sha_file(args.page_quality)}")
    P(f"    accepted_manifest       = experiments/ocr_survey/_phase_b_accepted_artifacts_manifest.jsonl "
      f"sha256={sha_file('experiments/ocr_survey/_phase_b_accepted_artifacts_manifest.jsonl')}")
    P(f"    prereg                  = {os.path.basename(args.prereg)} sha256={sha_file(args.prereg)}")
    P(f"    measurement script      = scripts/s4a9c_final_canonical.py sha256={sha_file(os.path.abspath(__file__))}")
    P(f"    git_commit              = {subprocess.run(['git','rev-parse','HEAD'],capture_output=True).stdout.decode().strip()}")
    P(f"    model / digest          = {MODEL} / {MODEL_DIGEST}")
    P(f"    count method            = /api/generate raw=true prompt_eval_count, num_ctx={NUM_CTX}, num_predict={NUM_PREDICT}")
    P("    render                  = '[{doc_id} §{section} PDF p.{pdf_page}]' + '\\n' + text")
    P("    window construction     = corpus 顺序每个起点取连续 5 块（旧 9c protocol 原样）")
    P("    ratio 方向              = actual / estimated；>1 = estimator 低估 = 危险侧；<1 = 保守")
    P("")
    P("[1] EXECUTABLE_CONTRACT_BEFORE_9C_FINAL（直接 import core.contracts，未修改）")
    for n in ("MAX_PROMPT_TOKENS", "PROMPT_OVERHEAD_RESERVE_TOKENS", "CONTEXT_PACK_MARGIN",
              "CONTEXT_PACK_BUDGET_TOKENS", "CHARS_PER_TOKEN_EST", "CHUNK_TARGET_TOKENS",
              "CHUNK_OVERLAP_TOKENS", "CITATION_HEADER_EST_TOKENS", "TOP_K_CONTEXT"):
        P(f"    {n:32s} = {getattr(contracts, n)}")
    P(f"    HISTORICAL_CANDIDATE (NOT EXECUTABLE CONTRACT) = X=950 O=206 m=0.86 -> B=639")
    P("")
    P("[2] 五种 token 量（不得互相替代）")
    P(f"    Q1 CHUNK_TARGET_TOKENS   INPUT_PARAMETER   = {contracts.CHUNK_TARGET_TOKENS}")
    P(f"    Q2 CHUNK_OVERLAP_TOKENS  INPUT_PARAMETER   = {contracts.CHUNK_OVERLAP_TOKENS}")
    P(f"    Q3 actual chunk tokens   MEASURED_OUTPUT   : {dist_line([r['actual_text_tokens'] for r in rows])}")
    P(f"    Q4 est_tokens()          ESTIMATOR_OUTPUT  = max(1, chars // CHARS_PER_TOKEN_EST={contracts.CHARS_PER_TOKEN_EST})")
    P(f"       est_tokens 分布       : {dist_line([r['est_tokens'] for r in rows])}")
    P(f"    Q5 rendered context cost MEASURED_OUTPUT   = tok(SEP.join(render_j))，含 header/separator/边界合并")
    P("    CHUNK_TARGET_TOKENS != actual chunk token count")
    P("    actual chunk token count != est_tokens()")
    P("    est_tokens() != rendered prompt/context actual token cost")
    P("")
    P("[3] Measurement A —— canonical chunk actual token distribution")
    P(f"    chars                  : {dist_line([r['chars'] for r in rows])}")
    P(f"    actual_text_tokens     : {dist_line([r['actual_text_tokens'] for r in rows])}")
    P(f"    actual_rendered_tokens : {dist_line([r['actual_rendered_tokens'] for r in rows])}")
    P(f"    chars/actual_token     : {dist_line([r['chars_per_actual_token'] for r in rows])}")
    P(f"    header_increment       : {dist_line([r['header_increment'] for r in rows])}"
      f"  （对照 CITATION_HEADER_EST_TOKENS={contracts.CITATION_HEADER_EST_TOKENS}）")
    P("    descriptive breakdown（仅解释证据，不据此调 parser/chunker）:")
    for doc in sorted({r["doc_id"] for r in rows}):
        g = [r for r in rows if r["doc_id"] == doc]
        P(f"      doc={doc:5s} n={len(g):5d} actual_tok p50={q([r['actual_text_tokens'] for r in g],.5):.4g} "
          f"p95={q([r['actual_text_tokens'] for r in g],.95):.4g} "
          f"ratio p50={q([r['ratio_text_actual_over_est'] for r in g],.5):.4f} "
          f"p95={q([r['ratio_text_actual_over_est'] for r in g],.95):.4f}")
    for chn in ("native", "ocr"):
        g = [r for r in rows if r["source_channel"] == chn]
        if g:
            P(f"      channel={chn:6s} n={len(g):5d} chars/token p50={q([r['chars_per_actual_token'] for r in g],.5):.4f} "
              f"p95={q([r['chars_per_actual_token'] for r in g],.95):.4f} max={max(r['chars_per_actual_token'] for r in g):.4f} "
              f"| ratio p50={q([r['ratio_text_actual_over_est'] for r in g],.5):.4f} "
              f"p95={q([r['ratio_text_actual_over_est'] for r in g],.95):.4f} "
              f"max={max(r['ratio_text_actual_over_est'] for r in g):.4f} "
              f"n(>1.15)={sum(1 for r in g if r['ratio_text_actual_over_est']>1.15)}")
    for od in sorted({min(r["chunk_ordinal"], 3) for r in rows}):
        g = [r for r in rows if min(r["chunk_ordinal"], 3) == od]
        lbl = f"ordinal={od}" if od < 3 else "ordinal>=3"
        P(f"      {lbl:12s} n={len(g):5d} ratio p50={q([r['ratio_text_actual_over_est'] for r in g],.5):.4f} "
          f"p95={q([r['ratio_text_actual_over_est'] for r in g],.95):.4f}")
    P("")
    P("[4] Measurement B —— estimator error（ratio = actual / estimated；>1 = 低估 = 危险侧）")
    rt = [r["ratio_text_actual_over_est"] for r in rows]
    rr = [r["ratio_rendered_actual_over_est_prompt"] for r in rows]
    P(f"    text  actual/est_tokens        : {dist_line(rt)}")
    P(f"    rend  actual/est_prompt_tokens : {dist_line(rr)}")
    d = [r["est_tokens"] - r["actual_text_tokens"] for r in rows]
    P(f"    estimated - actual (text)      : {dist_line(d)}")
    P("    危险尾部计数:")
    for t in DANGER_THRESHOLDS:
        n1 = sum(1 for x in rt if x > t)
        n2 = sum(1 for x in rr if x > t)
        P(f"      ratio > {t:.2f}: text n={n1:5d} ({n1/len(rt)*100:6.2f}%)   rendered n={n2:5d} ({n2/len(rr)*100:6.2f}%)")
    P("    最坏 15 个 chunk（text ratio 降序）:")
    for r in sorted(rows, key=lambda r: -r["ratio_text_actual_over_est"])[:15]:
        P(f"      {r['chunk_id']:16s} {r['doc_id']:5s} p.{r['pdf_page']:<4d} {r['source_channel']:6s} "
          f"chars={r['chars']:5d} est={r['est_tokens']:4d} actual={r['actual_text_tokens']:5d} "
          f"ratio={r['ratio_text_actual_over_est']:.4f} [{r['labels']}]")
    P("")
    P("[5] Measurement C —— real separator incremental cost（真实相邻 rendered chunk）")
    P("    注: separator incremental cost 与 CITATION_HEADER_EST_TOKENS 是不同的量。")
    for tag_sep in ("\\n", "\\n\\n"):
        v = [r["sep_incremental_tokens"] for r in sep_rows if r["sep"] == tag_sep]
        P(f"    SEP='{tag_sep}': {dist_line(v)}")
        P(f"      分布: " + "  ".join(f"+{k}:{n}" for k, n in sorted(Counter(v).items())))
    P("")
    P("[6] Measurement D —— real rendered windows（两套预算分栏）")
    for name, sc in scenarios.items():
        mark = "" if name == "CURRENT_EXECUTABLE" else "   ⚠️ NOT EXECUTABLE CONTRACT"
        P(f"    --- {name}: X={sc['X']} O={sc['O']} m={sc['m']} B={sc['B']}{mark} ---")
        for tag_sep in ("\\n", "\\n\\n"):
            sub = [r for r in wrows if r["scenario"] == name and r["sep"] == tag_sep]
            over = [r for r in sub if r["overbudget"]]
            tot = [r["actual_total_prompt_tokens"] for r in sub]
            P(f"      SEP='{tag_sep}': windows={len(sub)}  within_budget={len(sub)-len(over)}  "
              f"overbudget={len(over)}  rate={len(over)/len(sub)*100:.2f}%")
            P(f"        actual_total_prompt : p50={q(tot,.5):.0f} p95={q(tot,.95):.0f} p99={q(tot,.99):.0f} max={max(tot):.0f}")
            P(f"        max_overage={max((r['over_by'] for r in over), default=0)}  "
              f"est_safe_but_actual_over={sum(1 for r in over if not r['est_overbudget'])}  "
              f"est_over_but_actual_safe={sum(1 for r in sub if r['est_overbudget'] and not r['overbudget'])}  "
              f"all_none_observed_over={sum(1 for r in over if r['all_none_observed'])}")
            P(f"        realized k: " + "  ".join(f"k={k}:{n}" for k, n in sorted(Counter(r['window_k'] for r in sub).items())))
            for r in sorted(over, key=lambda r: -r["over_by"])[:5]:
                P(f"        worst: window={r['window_index']} k={r['window_k']} "
                  f"actual_total={r['actual_total_prompt_tokens']} over_by=+{r['over_by']}")
    P("")
    P("[7] none_observed deep dive（旧定义原样恢复）")
    lab = Counter(l for r in rows for l in r["labels"].split(";"))
    P("    全语料标签计数: " + "  ".join(f"{k}={v}" for k, v in sorted(lab.items())))
    nb = [r for r in rows if r["labels"] == "none_observed"]
    nt = [r["ratio_text_actual_over_est"] for r in nb]
    nr = [r["ratio_rendered_actual_over_est_prompt"] for r in nb]
    P(f"    population n={len(nb)}")
    P(f"    text  actual/est_tokens        : {dist_line(nt)}")
    P(f"    rend  actual/est_prompt_tokens : {dist_line(nr)}")
    for t in DANGER_THRESHOLDS:
        P(f"      ratio > {t:.2f}: text n={sum(1 for x in nt if x>t):5d}   rendered n={sum(1 for x in nr if x>t):5d}")
    anom = [r for r in rows if r["labels"] != "none_observed"]
    if anom:
        at = [r["ratio_text_actual_over_est"] for r in anom]
        P(f"    任一异常标签（对照）n={len(anom)}  text ratio p50={q(at,.5):.4f} p95={q(at,.95):.4f} max={max(at):.4f}")
    P("")
    P("注: 本日志只产出 measurement evidence；不选择、不冻结、不修改任何 contract 取值。")
    with open(paths["log"], "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"done chunks={len(rows)} pairs={len(sep_rows)} windows={len(wrows)} out={args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
