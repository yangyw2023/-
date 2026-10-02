#!/usr/bin/env python3
"""计算需要 OCR_ATTEMPT 的页面清单（Phase B production rule）。

规则（Design Freeze §4 / §18，冻结）：

    native_body_status ∈ {unusable, insufficient}  →  OCR_ATTEMPT

**无条件**：不读 active-row / ink / bbox 等任何视觉信号。
本脚本只做 native 抽取 + 状态分类，**不执行 OCR**（OCR 在 ingest/run_ocr.py）。

用法:
    python3 ingest/plan_ocr_targets.py --pdf-dir "raw/KAIVA - Manuals" \\
        --out-targets <targets.jsonl> --out-log <log>

失败语义: poppler 失败 / 页数不一致 / 文件名未登记 → 抛异常，非零退出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import ocr_artifact as oa  # noqa: E402
from components.parsers import page_states as ps  # noqa: E402
from components.parsers.kaiva_pdf import FILENAME_DOC_ID_MAP, native_page_view, iter_native_pages  # noqa: E402
from core import contracts  # noqa: E402

PDF_SUFFIX: str = ".pdf"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out-targets", required=True)
    ap.add_argument("--out-log", required=True)
    ap.add_argument("--doc-lang", default=contracts.CORPUS_LANG_DEFAULT)
    args = ap.parse_args(argv)

    names = sorted(f for f in os.listdir(args.pdf_dir) if f.lower().endswith(PDF_SUFFIX))
    targets: list[dict[str, object]] = []
    lines: list[str] = ["Phase B OCR target planning（production rule：insufficient|unusable → OCR_ATTEMPT）",
                        "=" * 78,
                        "  ⚠️ 本规则不读取任何视觉信号（active-row / ink / bbox 均为 diagnostic only）。", ""]
    totals: Counter = Counter()
    for name in names:
        if name not in FILENAME_DOC_ID_MAP:
            raise RuntimeError(f"PDF 文件名未登记: {name}")
        doc_id = FILENAME_DOC_ID_MAP[name]
        path = os.path.join(args.pdf_dir, name)
        source_hash = oa.file_sha256(path)
        pages, _ = iter_native_pages(path)
        per_doc: Counter = Counter()
        for page_no, text in enumerate(pages, start=1):
            body = str(native_page_view(text)["body"])
            status, reason = ps.classify_native_body(body, args.doc_lang)
            per_doc[status] += 1
            totals[status] += 1
            if status in (ps.NATIVE_UNUSABLE, ps.NATIVE_INSUFFICIENT):
                targets.append({"doc_id": doc_id, "pdf_page": page_no, "source_hash": source_hash,
                                "native_body_status": status, "reason": reason})
        lines.append(f"  {doc_id:<5} pages={len(pages):<4} " +
                     " ".join(f"{s}={per_doc[s]}" for s in ps.NATIVE_BODY_STATES))
    targets.sort(key=lambda t: (str(t["doc_id"]), int(t["pdf_page"])))
    lines += ["", f"  totals: " + " ".join(f"{s}={totals[s]}" for s in ps.NATIVE_BODY_STATES),
              f"  OCR targets = {len(targets)}", ""]
    for t in targets:
        lines.append(f"    {t['doc_id']}:p{t['pdf_page']:<4} {t['native_body_status']:<13} {t['reason']}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out_targets)), exist_ok=True)
    with open(args.out_targets, "w", encoding="utf-8") as handle:
        for t in targets:
            handle.write(json.dumps(t, sort_keys=True, ensure_ascii=True) + "\n")
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"targets={len(targets)} " + " ".join(f"{s}={totals[s]}" for s in ps.NATIVE_BODY_STATES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
