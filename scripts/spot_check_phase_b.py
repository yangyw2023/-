#!/usr/bin/env python3
"""S5c semantic spot-check：对已知回归样本逐页对比 baseline 与新 corpus。

这是 **implementation QA review**，不是新的 benchmark ground truth，
也不是 independent human ground truth。

用法:
    python3 scripts/spot_check_phase_b.py --baseline-corpus corpus/chunks.jsonl \\
        --build <build_dir> --out-log <log>

页面清单来自 Phase A / A.1 / A.2 / A.2b 的既有证据（不重新搜索页面）。
输出确定性：不含时间戳 / 随机值。
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import platform
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 回归样本（doc_id, pdf_page, 选取依据）——全部来自既有冻结证据
SPOT_PAGES: tuple[tuple[str, int, str], ...] = (
    ("TACM", 38, "Phase A confirmed native-unusable 区间起点"),
    ("TACM", 51, "A.1 视觉抽样标为 business_knowledge_present"),
    ("TACM", 60, "Phase A confirmed_bad 乱码页 + A.1 mixed"),
    ("TACM", 100, "A.1/parser audit：section 值 `9` 与真实章节集合碰撞的反例形状"),
    ("TACM", 103, "confirmed native-unusable 区间终点"),
    ("TACM", 55, "A.1：40/100/150 dpi 全白，blank/noncontent 对照"),
    ("CMM", 112, "A.2：insufficient + 图像化 Appendix V 评分表"),
    ("ERM", 17, "A.2：insufficient + 应急上报流程图（gold 邻近页）"),
    ("CRM", 74, "A.2：insufficient + 超大幅面 bow-tie 风险图"),
    ("QMM", 139, "A.2：整页扫描件（政策正文）"),
    ("QMM", 148, "A.2：整页扫描件（Open Reporting 政策）"),
    ("QMM", 110, "A.2b：class-3 positive control（native usable，视觉层含 MOC 流程图）"),
    ("EMM", 131, "citation audit：gold `Chapter 15` vs parser `15` 的 representation-only 差异"),
    ("EMM", 96, "citation audit：gold `Chapter 10` vs parser `10`"),
    ("ERM", 14, "A.2b：gold citation page 且 VISUAL_KNOWLEDGE_MISSING"),
    ("SMM", 38, "A.2b：gold citation page 且 VISUAL_KNOWLEDGE_MISSING"),
)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def snippet(text: str, n: int = 110) -> str:
    return json.dumps(" ".join(text.split())[:n], ensure_ascii=True)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-corpus", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out-log", required=True)
    args = ap.parse_args(argv)

    old = load_jsonl(args.baseline_corpus)
    new = load_jsonl(os.path.join(args.build, "chunks.jsonl"))
    pq = {(r["doc_id"], r["pdf_page"]): r for r in load_jsonl(os.path.join(args.build, "page_quality.jsonl"))}
    old_by = collections.defaultdict(list)
    new_by = collections.defaultdict(list)
    for c in old:
        old_by[(c["doc_id"], c["pdf_page"])].append(c)
    for c in new:
        new_by[(c["doc_id"], c["pdf_page"])].append(c)

    out: list[str] = ["S5c semantic spot-check（implementation QA review，不是 ground truth）", "=" * 78,
                      f"  python={platform.python_version()} "
                      f"git={subprocess.run(['git','rev-parse','HEAD'],capture_output=True).stdout.decode().strip()}",
                      f"  script sha256={file_sha256(os.path.abspath(__file__))}",
                      f"  baseline corpus sha256={file_sha256(args.baseline_corpus)}",
                      f"  new corpus sha256={file_sha256(os.path.join(args.build, 'chunks.jsonl'))}", ""]
    for doc_id, page, why in SPOT_PAGES:
        key = (doc_id, page)
        rec = pq.get(key)
        if rec is None:
            raise RuntimeError(f"page_quality 缺页: {key}")
        o, n = old_by.get(key, []), new_by.get(key, [])
        out.append(f"── {doc_id} p.{page} —— {why}")
        out.append(f"   baseline: chunks={len(o)} section={json.dumps(o[0]['section'], ensure_ascii=True) if o else '-'}")
        out.append(f"             text: {snippet(o[0]['text']) if o else '-'}")
        out.append(f"   native_body_status={rec['native_body_status']} ({rec['native_body_chars']} chars) "
                   f"ocr_body_status={rec['ocr_body_status']}"
                   + (f" ({rec['ocr_body_chars']} chars)" if rec['ocr_body_chars'] is not None else ""))
        out.append(f"   native_metadata_candidate={json.dumps(rec['native_metadata_candidate'], ensure_ascii=True)}"
                   f" kind={rec['native_metadata_source_kind']}")
        out.append(f"   ocr_metadata_candidate={json.dumps(rec['ocr_metadata_candidate'], ensure_ascii=True)}"
                   f" kind={rec['ocr_metadata_source_kind']}")
        out.append(f"   citation={rec['citation_metadata_status']} ({rec['metadata_reason_code']}) "
                   f"conflict={rec['metadata_conflict']} metadata_channel={rec['metadata_source_channel']}")
        out.append(f"   body_channel={rec['body_source_channel']} policy={rec['content_policy_status']} "
                   f"action={rec['remediation_action']} require_review={rec['require_review']}")
        out.append(f"   completeness={rec['page_content_completeness_status']} "
                   f"(visual diagnostic only: {rec['active_row_diagnostic']})")
        out.append(f"   new: chunks={len(n)} ids={rec['chunk_ids']}")
        out.append(f"        section={json.dumps(n[0]['section'], ensure_ascii=True) if n else '-'}")
        out.append(f"        text: {snippet(n[0]['text']) if n else '-'}")
        out.append("")
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"spot_check pages={len(SPOT_PAGES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
