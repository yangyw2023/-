#!/usr/bin/env python3
"""S5c post-implementation QA：OCR body 的 header/footer residual 普查（只诊断，不改 parser）。

判据在 scratchpad 的 QA preregistration 中先行冻结（见报告引用的 block sha256）。
本脚本只读 corpus / page_quality / accepted OCR artifacts / 源 PDF 的 native 文本。

用法:
    python3 scripts/qa_header_residual_census.py --pdf-dir "raw/KAIVA - Manuals" \\
        --cache-dir ocr_cache --corpus corpus/chunks.jsonl \\
        --page-quality ingest/page_quality.jsonl --out-log <log> --out-csv <csv>

residual 的机械定义（不依赖 doc_id / filename / pdf_page）:
  一条 final body 行被判为 structural residual，当且仅当
    (a) 它在【原始通道文本】中的行位置落在 header 区（前 HEADER_SCAN_LINES 行）
        或 footer 区（后 FOOTER_SCAN_LINES 行）；且
    (b) 它命中 explicit structural signature：
        既有 parser 的页眉标签集合 / `Page N of M` / UNCONTROLLED WHEN PRINTED，
        或它是该文档 header 区内跨页重复 >= REPEAT_PAGE_MIN 页的同一归一化行。
  正文中间出现的 "Section 4.1" 这类引用【不计入】——位置条件不满足。
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import kaiva_pdf as native_parser  # noqa: E402
from components.parsers import ocr_artifact as oa  # noqa: E402
from components.parsers import phase_b_ingest as pb  # noqa: E402
from components.parsers.kaiva_pdf import FILENAME_DOC_ID_MAP, iter_native_pages  # noqa: E402
from core import contracts  # noqa: E402

FOOTER_SCAN_LINES: int = 3          # 与页眉窗口对称的页脚窗口（结构位置，不是内容判断）
REPEAT_PAGE_MIN: int = 5            # header 区内跨页重复行的最小页数
REPEAT_REPORT_MIN: int = 5

_LABEL_SIGNATURE = re.compile(
    r"(?i)\b(DOCUMENT\s*ID|ISSUED\s*BY|SECTION|REV\.?\s*NO|REVISION\s*NO|ISSUE\s*DATE|PAGE\s*NO)\b")
# ⚠️ 仅"含 SECTION 一词"不足以判 header —— native control 已证明正文散文会命中
# （例："...shall be certified as per STCW Section A - II/4."）。
# 结构性页眉行的机械判据：短行（页眉表格被 OCR 压平后仍显著短于散文句）且含标签，
# 或同一行含 >= 2 个不同标签。两者都与 doc_id / filename / pdf_page 无关。
LABEL_DENSE_MAX_CHARS: int = 60
_PAGE_N_OF_M = re.compile(r"(?i)\bpage\s+\d+\s+of\s+\d+\b")
_UNCONTROLLED = re.compile(r"(?i)uncontrolled\s+when\s+printed")


def norm_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def est_tokens(text: str) -> int:
    """项目自有估算口径（与 chunking / packing 同一口径），不改 contracts。"""
    return max(0, len(text) // contracts.CHARS_PER_TOKEN_EST)


def region_index(idx: int, total: int) -> str | None:
    if idx < native_parser.HEADER_SCAN_LINES:
        return "header"
    if idx >= total - FOOTER_SCAN_LINES:
        return "footer"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--page-quality", required=True)
    ap.add_argument("--out-log", required=True)
    ap.add_argument("--out-csv", required=True)
    args = ap.parse_args(argv)

    store = oa.OcrArtifactStore(args.cache_dir)
    pq = load_jsonl(args.page_quality)
    chunks = load_jsonl(args.corpus)
    by_page: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for c in chunks:
        by_page[(c["doc_id"], c["pdf_page"])].append(c)

    native_text: dict[tuple[str, int], str] = {}
    for name, doc_id in sorted(FILENAME_DOC_ID_MAP.items()):
        path = os.path.join(args.pdf_dir, name)
        if os.path.isfile(path):
            pages, _ = iter_native_pages(path)
            for i, text in enumerate(pages, start=1):
                native_text[(doc_id, i)] = text

    # ---- 通道文本与 final body ----
    rows: list[dict[str, Any]] = []
    header_lines_by_doc: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    ocr_pages: list[dict[str, Any]] = []
    for r in pq:
        key = (r["doc_id"], r["pdf_page"])
        channel = r["body_source_channel"]
        if r["ocr_attempted"]:
            entry = next(e for e in store.iter_accepted()
                         if e["source_hash"] == r["source_hash"] and int(e["pdf_page"]) == r["pdf_page"])
            payload = store.load_accepted(oa.CacheIdentity(**entry["cache_key"]))
            channel_text = str(payload["text"])
        else:
            channel_text = native_text[key]
        lines = channel_text.splitlines()
        total = len(lines)
        for idx, line in enumerate(lines):
            if region_index(idx, total) == "header" and norm_line(line):
                header_lines_by_doc[r["doc_id"]][norm_line(line)] += 1
        ocr_pages.append({"rec": r, "channel_text": channel_text, "lines": lines, "total": total})

    repeated_header: dict[str, set[str]] = {
        doc: {ln for ln, n in cnt.items() if n >= REPEAT_PAGE_MIN}
        for doc, cnt in header_lines_by_doc.items()
    }

    # ---- 逐页 residual 统计 ----
    for item in ocr_pages:
        r = item["rec"]
        key = (r["doc_id"], r["pdf_page"])
        body_chunks = by_page.get(key, [])
        if not body_chunks:
            final_body = ""
        else:
            final_body = "\n\n".join(c["text"] for c in body_chunks)
        pos = {norm_line(l): i for i, l in enumerate(item["lines"]) if norm_line(l)}
        residual_lines: list[tuple[str, str, str]] = []   # (line, region, signature)
        for raw in final_body.splitlines():
            key_line = norm_line(raw)
            if not key_line or key_line not in pos:
                continue
            region = region_index(pos[key_line], item["total"])
            if region is None:
                continue
            sig = None
            labels = {m.group(0).upper().replace(" ", "") for m in _LABEL_SIGNATURE.finditer(key_line)}
            if labels and (len(labels) >= 2 or len(key_line) <= LABEL_DENSE_MAX_CHARS):
                sig = "structural_label_line"
            elif _PAGE_N_OF_M.search(key_line):
                sig = "page_n_of_m"
            elif _UNCONTROLLED.search(key_line):
                sig = "uncontrolled_when_printed"
            elif key_line in repeated_header.get(r["doc_id"], set()):
                sig = f"repeated_header_line>={REPEAT_PAGE_MIN}pages"
            if sig:
                residual_lines.append((key_line, region, sig))
        residual_chars = sum(len(l) for l, _, _ in residual_lines)
        rows.append({
            "doc_id": r["doc_id"], "pdf_page": r["pdf_page"],
            "population": ("ocr_admitted" if (r["body_source_channel"] == pb.BODY_CHANNEL_OCR and body_chunks)
                           else "ocr_quarantined" if r["ocr_attempted"]
                           else "native_admitted" if body_chunks else "native_other"),
            "body_source_channel": r["body_source_channel"],
            "remediation_action": r["remediation_action"],
            "final_body_chars": len(final_body),
            "final_body_est_tokens": est_tokens(final_body),
            "residual_line_count": len(residual_lines),
            "residual_chars": residual_chars,
            "residual_est_tokens": est_tokens("\n".join(l for l, _, _ in residual_lines)),
            "residual_char_ratio": round(residual_chars / len(final_body), 6) if final_body else "",
            "residual_signatures": "|".join(sorted({s for _, _, s in residual_lines})),
            "residual_sample": json.dumps([l for l, _, _ in residual_lines][:3], ensure_ascii=True),
            "chunk_count": len(body_chunks),
            "native_metadata_candidate_len": len(r["native_metadata_candidate"] or ""),
            "ocr_metadata_candidate_len": len(r["ocr_metadata_candidate"] or ""),
        })

    # ---- 4.3 native-vs-OCR 结构信息重复 ----
    dup_pages = 0
    dup_chunks = 0
    for row, item in zip(rows, ocr_pages):
        r = item["rec"]
        if row["population"] != "ocr_admitted":
            continue
        cand = (r["native_metadata_candidate"] or "").strip()
        body = "\n\n".join(c["text"] for c in by_page[(r["doc_id"], r["pdf_page"])])
        if cand and len(cand) >= 2 and norm_line(cand) in norm_line(body):
            dup_pages += 1
            dup_chunks += len(by_page[(r["doc_id"], r["pdf_page"])])

    # ---- 4.4 counterfactual：机械剥离后重跑既有分块规则 ----
    boundary_changes = 0
    chunk_delta = 0
    stripped_examples: list[str] = []
    for row, item in zip(rows, ocr_pages):
        if row["population"] != "ocr_admitted" or row["residual_line_count"] == 0:
            continue
        r = item["rec"]
        key = (r["doc_id"], r["pdf_page"])
        current = [c["text"] for c in by_page[key]]
        body = "\n\n".join(current)
        keep = []
        pos = {norm_line(l): i for i, l in enumerate(item["lines"]) if norm_line(l)}
        for line in body.splitlines():
            k = norm_line(line)
            labels_k = {m.group(0).upper().replace(" ", "") for m in _LABEL_SIGNATURE.finditer(k)}
            if k and k in pos and region_index(pos[k], item["total"]) is not None and (
                    (labels_k and (len(labels_k) >= 2 or len(k) <= LABEL_DENSE_MAX_CHARS))
                    or _PAGE_N_OF_M.search(k) or _UNCONTROLLED.search(k)):
                continue
            keep.append(line)
        stripped = "\n".join(keep).strip()
        new_chunks = native_parser.split_body_to_texts(stripped) if len(stripped) >= contracts.CHUNK_MIN_CHARS else []
        if len(new_chunks) != len(current):
            boundary_changes += 1
            if len(stripped_examples) < 6:
                stripped_examples.append(f"{r['doc_id']}:p{r['pdf_page']} chunks {len(current)} → {len(new_chunks)}")
        chunk_delta += len(new_chunks) - len(current)

    # ---- 报表 ----
    def dist(values: list[float]) -> str:
        if not values:
            return "n=0"
        v = sorted(values)
        def q(p: float) -> float:
            return v[max(0, min(len(v) - 1, round(p * (len(v) - 1))))]
        return (f"n={len(v)} min={v[0]:.4f} p50={q(0.5):.4f} p95={q(0.95):.4f} max={v[-1]:.4f}")

    ocr_adm = [r for r in rows if r["population"] == "ocr_admitted"]
    ocr_q = [r for r in rows if r["population"] == "ocr_quarantined"]
    nat_adm = [r for r in rows if r["population"] == "native_admitted"]
    affected = [r for r in ocr_adm if r["residual_line_count"] > 0]

    out: list[str] = ["S5c QA —— OCR header/footer residual census（只诊断，不改 parser）", "=" * 78,
                      f"  python={platform.python_version()} "
                      f"git={subprocess.run(['git','rev-parse','HEAD'],capture_output=True).stdout.decode().strip()}",
                      f"  script sha256={file_sha256(os.path.abspath(__file__))}",
                      f"  corpus sha256={file_sha256(args.corpus)}",
                      f"  page_quality sha256={file_sha256(args.page_quality)}",
                      f"  residual 判据: header 区=前 {native_parser.HEADER_SCAN_LINES} 行, footer 区=后 {FOOTER_SCAN_LINES} 行；"
                      f"重复行阈值={REPEAT_PAGE_MIN} 页；token 口径=CHARS_PER_TOKEN_EST={contracts.CHARS_PER_TOKEN_EST}", ""]
    out.append("§1 population")
    out.append(f"  ocr_admitted={len(ocr_adm)}  ocr_quarantined={len(ocr_q)}  native_admitted(control)={len(nat_adm)}")
    out.append("")
    out.append("§2 structural residual（population A：OCR primary admitted）")
    out.append(f"  affected_pages={len(affected)}/{len(ocr_adm)}")
    out.append(f"  affected_chunks={sum(r['chunk_count'] for r in affected)}")
    out.append(f"  total_residual_chars={sum(r['residual_chars'] for r in affected)}")
    out.append(f"  total_residual_est_tokens={sum(r['residual_est_tokens'] for r in affected)}")
    out.append(f"  total_body_chars={sum(r['final_body_chars'] for r in ocr_adm)}")
    out.append(f"  residual_char_ratio 分布: {dist([float(r['residual_char_ratio']) for r in affected if r['residual_char_ratio'] != ''])}")
    out.append(f"  residual_token_ratio 分布: "
               f"{dist([r['residual_est_tokens']/r['final_body_est_tokens'] for r in affected if r['final_body_est_tokens']])}")
    out.append(f"  signature 分布: {dict(collections.Counter(s for r in affected for s in r['residual_signatures'].split('|') if s))}")
    out.append("")
    out.append("§3 native control（同判据作用在 native admitted 页上）")
    nat_affected = [r for r in nat_adm if r["residual_line_count"] > 0]
    out.append(f"  affected_pages={len(nat_affected)}/{len(nat_adm)}  "
               f"total_residual_chars={sum(r['residual_chars'] for r in nat_affected)}")
    out.append("")
    out.append("§4 native-vs-OCR 结构信息重复（metadata 与 body 同时含同一 section 值）")
    out.append(f"  duplicated_structural_line_pages={dup_pages}  affected_chunks={dup_chunks}")
    out.append("")
    out.append("§5 counterfactual：机械剥离 residual 后重跑既有分块规则")
    out.append(f"  pages_with_chunk_boundary_change={boundary_changes}  chunk_count_delta={chunk_delta:+d}")
    for ex in stripped_examples:
        out.append(f"    {ex}")
    out.append("")
    out.append("§6 逐页（population A，residual_line_count>0，按 residual_chars 降序前 30）")
    for r in sorted(affected, key=lambda x: -x["residual_chars"])[:30]:
        out.append(f"  {r['doc_id']}:p{r['pdf_page']:<4} chunks={r['chunk_count']} body_chars={r['final_body_chars']:<6} "
                   f"residual_lines={r['residual_line_count']} residual_chars={r['residual_chars']:<5} "
                   f"ratio={r['residual_char_ratio']} sig={r['residual_signatures']}")
        out.append(f"      sample={r['residual_sample']}")
    out.append("")
    out.append("§7 header 区跨页重复行（>= %d 页，按文档）" % REPEAT_REPORT_MIN)
    for doc in sorted(repeated_header):
        top = sorted(header_lines_by_doc[doc].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        out.append(f"  {doc}: repeated_lines={len(repeated_header[doc])} top={[(l[:48], n) for l, n in top]}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["doc_id"], r["pdf_page"])))
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"census ocr_admitted={len(ocr_adm)} affected={len(affected)} "
          f"residual_chars={sum(r['residual_chars'] for r in affected)} "
          f"boundary_changes={boundary_changes} chunk_delta={chunk_delta:+d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
