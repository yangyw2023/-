"""语料构建脚本（Phase B）：native + accepted OCR artifact → chunks.jsonl + page_quality.jsonl。

用法:
    python3 ingest/build_corpus.py "raw/KAIVA - Manuals" <out_dir> \\
        --cache-dir ocr_cache \\
        [--visual-signals-csv experiments/ocr_survey/_visual_page_signals.csv] \\
        [--visual-labels-csv experiments/ocr_survey/_visual_threshold_validation.csv]

产出（均写在 <out_dir> 下）:
    chunks.jsonl         每行一个 chunk 的 JSON（ensure_ascii=False）
    page_quality.jsonl   **每个 source page 恰一条**的 page accounting ledger
    ingest_report.csv    每份文档一行

硬约束（Design Freeze）:
  - **本脚本绝不执行 OCR**：只通过 OcrArtifactStore.load_accepted() 消费已冻结 artifact。
    需要 OCR 的页面没有 accepted artifact → FAIL_INGEST（整批失败），不静默退回 native。
  - **page accounting**：source page 数 == page_quality 行数，(doc_id, pdf_page) 唯一。
    任何未入库页都必须带 state + reason + remediation_action，禁止 silent continue。
  - **primary body 单 channel**：由 phase_b_ingest.select_primary_body 保证。
  - 视觉信号只用于 completeness 审计，不参与任何动作。
  - Chunk schema 不变；`Chunk.source_hash` 仍是【源 PDF】的 sha256。
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import ocr_artifact as oa  # noqa: E402
from components.parsers import phase_b_ingest as pb  # noqa: E402
from components.parsers.kaiva_pdf import FILENAME_DOC_ID_MAP, iter_native_pages  # noqa: E402
from core import contracts  # noqa: E402

CHUNKS_FILENAME: str = "chunks.jsonl"
PAGE_QUALITY_FILENAME: str = "page_quality.jsonl"
REPORT_FILENAME: str = "ingest_report.csv"
PDF_SUFFIX: str = ".pdf"
HASH_READ_BLOCK_BYTES: int = 1 << 20
CORPUS_HASH_PREFIX_LEN: int = 8

REPORT_COLUMNS: tuple[str, ...] = (
    "file", "doc_id", "pages", "chunks", "admitted_native", "admitted_ocr",
    "quarantined", "skipped_noncontent", "ocr_attempted", "chars_min", "chars_median", "chars_max",
)

# 视觉诊断（audit only）：A.2 冻结的 feature 与 midpoint 阈值规则。
VISUAL_FEATURE_COLUMN: str = "d40_active_row_ratio_245_f0p01"
VISUAL_LABEL_POS: str = "POSITIVE_VISUAL_RECOVERY_CANDIDATE"
VISUAL_LABEL_NEG: str = "NEGATIVE_NON_CONTENT"


class BuildError(RuntimeError):
    """构建失败（FAIL_INGEST）。"""


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def load_visual_diagnostic(signals_csv: str | None, labels_csv: str | None
                           ) -> tuple[dict[tuple[str, int], float], float | None, str]:
    """加载 A.1 视觉信号与 A.2 冻结标签，按 A.2 预注册的 midpoint 规则重算 tau。

    ⚠️ 只用于 completeness 审计；**不参与任何动作**，也不得重新搜索 feature / 阈值。
    返回 (signal_by_page, tau, note)。缺输入时返回 ({}, None, 原因)。
    """
    if not signals_csv or not labels_csv:
        return {}, None, "visual_diagnostic_inputs_not_provided"
    if not (os.path.isfile(signals_csv) and os.path.isfile(labels_csv)):
        raise BuildError(f"视觉诊断输入缺失: {signals_csv} / {labels_csv}")
    signals: dict[tuple[str, int], float] = {}
    with open(signals_csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = row.get(VISUAL_FEATURE_COLUMN, "")
            if raw:
                signals[(row["doc_id"], int(row["pdf_page"]))] = float(raw)
    pos: list[float] = []
    neg: list[float] = []
    with open(labels_csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["doc_id"], int(row["pdf_page"]))
            if key not in signals:
                continue
            if row["eval_set"] == VISUAL_LABEL_POS:
                pos.append(signals[key])
            elif row["eval_set"] == VISUAL_LABEL_NEG:
                neg.append(signals[key])
    if not pos or not neg:
        raise BuildError("A.2 冻结标签中缺 POS/NEG，无法按冻结规则重算 tau")
    p_min = min(pos)
    below = [v for v in (*pos, *neg) if v < p_min]
    tau = (max(below) + p_min) / 2 if below else p_min
    return signals, tau, f"frozen_midpoint_rule:feature={VISUAL_FEATURE_COLUMN};pos={len(pos)};neg={len(neg)}"


def build(args: argparse.Namespace) -> dict[str, Any]:
    """执行一次完整构建。抛出 BuildError / PageIngestError —— 任何硬门不通过。"""
    names = sorted(f for f in os.listdir(args.pdf_dir) if f.lower().endswith(PDF_SUFFIX))
    if not names:
        raise BuildError(f"目录下没有 PDF: {args.pdf_dir}")
    store = oa.OcrArtifactStore(args.cache_dir)
    signals, tau, tau_note = load_visual_diagnostic(args.visual_signals_csv, args.visual_labels_csv)

    all_chunks: list[contracts.Chunk] = []
    all_records: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    versions_seen: set[tuple[str, str, str]] = set()

    for name in names:
        if name not in FILENAME_DOC_ID_MAP:
            raise BuildError(f"PDF 文件名未登记在 FILENAME_DOC_ID_MAP: {name}")
        doc_id = FILENAME_DOC_ID_MAP[name]
        path = os.path.join(args.pdf_dir, name)
        source_hash = file_sha256(path)
        pages, expected = iter_native_pages(path)          # page identity 硬门 1：pdfinfo == 分页符数
        doc_chunks: list[contracts.Chunk] = []
        doc_actions: Counter = Counter()
        inherited: str | None = None
        ocr_attempted = 0

        for page_no, native_text in enumerate(pages, start=1):
            artifact = _load_artifact_if_needed(store, doc_id, source_hash, page_no, native_text,
                                                args.doc_lang, versions_seen)
            if artifact is not None:
                ocr_attempted += 1
            suspected = None
            if tau is not None and (doc_id, page_no) in signals:
                suspected = signals[(doc_id, page_no)] > tau
            result = pb.process_page(pb.PageInput(
                doc_id=doc_id, doc_name=name, source_hash=source_hash, pdf_page=page_no,
                native_text=native_text, doc_lang=args.doc_lang, ocr_artifact=artifact,
                visual_suspected=suspected,
                visual_signal_summary=(f"{VISUAL_FEATURE_COLUMN}={signals[(doc_id, page_no)]:.6f};tau={tau:.6f}"
                                       if (tau is not None and (doc_id, page_no) in signals) else None),
                inherited_section=inherited,
            ))
            inherited = result.section_for_inheritance
            doc_chunks.extend(result.chunks)
            all_records.append(result.record)
            doc_actions[str(result.record["remediation_action"]).split("+")[0]] += 1

        # page identity 硬门 2：本文档写出的 page 记录数必须等于源页数
        written = sum(1 for r in all_records if r["doc_id"] == doc_id)
        if written != expected:
            raise BuildError(f"page accounting 不闭合: {doc_id} 源页数={expected} 记录数={written}")

        all_chunks.extend(doc_chunks)
        lengths = sorted(len(c.text) for c in doc_chunks) or [0]
        report_rows.append({
            "file": name, "doc_id": doc_id, "pages": expected, "chunks": len(doc_chunks),
            "admitted_native": doc_actions[pb.ACTION_ADMITTED_NATIVE],
            "admitted_ocr": doc_actions[pb.ACTION_ADMITTED_OCR],
            "quarantined": doc_actions[pb.ACTION_QUARANTINED],
            "skipped_noncontent": doc_actions[pb.ACTION_SKIPPED_NONCONTENT],
            "ocr_attempted": ocr_attempted,
            "chars_min": lengths[0], "chars_median": int(statistics.median(lengths)), "chars_max": lengths[-1],
        })

    os.makedirs(args.out_dir, exist_ok=True)
    chunks_path = os.path.join(args.out_dir, CHUNKS_FILENAME)
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for chunk in all_chunks:
            handle.write(json.dumps(dataclasses.asdict(chunk), ensure_ascii=False) + "\n")
    pq_path = os.path.join(args.out_dir, PAGE_QUALITY_FILENAME)
    with open(pq_path, "w", encoding="utf-8") as handle:
        for record in sorted(all_records, key=lambda r: (str(r["doc_id"]), int(r["pdf_page"]))):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    with open(os.path.join(args.out_dir, REPORT_FILENAME), "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report_rows)

    return {
        "chunks_path": chunks_path, "page_quality_path": pq_path,
        "chunk_count": len(all_chunks), "page_count": len(all_records),
        "corpus_sha256": file_sha256(chunks_path), "page_quality_sha256": file_sha256(pq_path),
        "tau_note": tau_note, "tau": tau,
    }


def _load_artifact_if_needed(store: oa.OcrArtifactStore, doc_id: str, source_hash: str, page_no: int,
                             native_text: str, doc_lang: str,
                             versions_seen: set[tuple[str, str, str]]) -> dict[str, Any] | None:
    """按 production rule 判断是否需要 OCR，并【只读】加载 accepted artifact。

    本函数不执行 OCR。需要而没有 accepted artifact → BuildError（FAIL_INGEST）。
    """
    from components.parsers import kaiva_pdf as native
    from components.parsers import page_states as ps
    body = str(native.native_page_view(native_text)["body"])
    status, _ = ps.classify_native_body(body, doc_lang)
    if not pb.needs_ocr(status):
        return None
    entries = [e for e in store.iter_accepted() if e["source_hash"] == source_hash and int(e["pdf_page"]) == page_no]
    if not entries:
        raise BuildError(
            f"FAIL_INGEST: {doc_id}:p{page_no} 需要 OCR（native_body_status={status}）但没有 accepted artifact。"
            f" 请先运行 ingest/run_ocr.py（build 绝不隐式执行 OCR）。"
        )
    if len(entries) > 1:
        raise BuildError(f"FAIL_INGEST: {doc_id}:p{page_no} 有多个 accepted artifact，cache identity 不唯一")
    entry = entries[0]
    identity = oa.CacheIdentity(**entry["cache_key"])
    payload = store.load_accepted(identity)              # digest + 双向身份校验
    payload["cache_key_digest"] = entry["cache_key_digest"]
    versions_seen.add((str(payload["ocr_engine"]), str(payload["ocr_engine_version"]),
                       str(payload["ocr_params_digest"])))
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--visual-signals-csv", default=None)
    ap.add_argument("--visual-labels-csv", default=None)
    ap.add_argument("--doc-lang", default=contracts.CORPUS_LANG_DEFAULT)
    args = ap.parse_args(argv)

    started = time.perf_counter()
    result = build(args)
    elapsed = time.perf_counter() - started
    print(f"pages={result['page_count']} chunks={result['chunk_count']} "
          f"corpus_sha256={result['corpus_sha256']} "
          f"page_quality_sha256={result['page_quality_sha256']} elapsed={elapsed:.1f}s")
    print(f"corpus_id={result['corpus_sha256'][:CORPUS_HASH_PREFIX_LEN]} visual_tau={result['tau']} ({result['tau_note']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
