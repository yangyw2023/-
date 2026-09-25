#!/usr/bin/env python3
"""S5c acceptance verification：机械验证 Phase B 的 acceptance invariants。

用法:
    python3 scripts/verify_phase_b_ingest.py \\
        --pdf-dir "raw/KAIVA - Manuals" --cache-dir ocr_cache \\
        --build-a <dir1> --build-b <dir2> \\
        --baseline-corpus corpus/chunks.jsonl --out-log <log>

每条 invariant 逐条判 PASS / FAIL；任何一条 FAIL → 退出码非零。
本脚本只读，不修改 corpus / artifact / 源 PDF。
"""

from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import fields as dc_fields
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import citation_gate as cg  # noqa: E402
from components.parsers import ocr_artifact as oa  # noqa: E402
from components.parsers import page_states as ps  # noqa: E402
from components.parsers import phase_b_ingest as pb  # noqa: E402
from components.parsers.kaiva_pdf import FILENAME_DOC_ID_MAP, iter_native_pages  # noqa: E402
from core import contracts  # noqa: E402

EXPECTED_SOURCE_PAGES: int = 1335
PRODUCTION_MODULES: tuple[str, ...] = (
    "components/parsers/kaiva_pdf.py", "components/parsers/phase_b_ingest.py",
    "components/parsers/page_states.py", "components/parsers/citation_gate.py",
    "components/parsers/ocr_artifact.py", "ingest/build_corpus.py", "ingest/plan_ocr_targets.py",
)
# 生产代码里不得出现的文档/页码硬编码（FILENAME_DOC_ID_MAP 是登记表，单独豁免）
DOC_IDS: tuple[str, ...] = ("SMM", "ERM", "NPM", "CRM", "FMM", "QMM", "TACM", "CMM", "EMM")


class Checker:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: int = 0

    def check(self, ident: str, name: str, ok: bool, detail: str = "") -> bool:
        self.lines.append(f"  [{'PASS' if ok else 'FAIL'}] {ident} {name}" + (f" | {detail}" if detail else ""))
        if not ok:
            self.failures += 1
        return ok

    def note(self, text: str) -> None:
        self.lines.append(f"         {text}")


def load_jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--build-a", required=True)
    ap.add_argument("--build-b", required=True)
    ap.add_argument("--baseline-corpus", required=True)
    ap.add_argument("--out-log", required=True)
    args = ap.parse_args(argv)

    ck = Checker()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chunks_a = load_jsonl(os.path.join(args.build_a, "chunks.jsonl"))
    pq_a = load_jsonl(os.path.join(args.build_a, "page_quality.jsonl"))
    store = oa.OcrArtifactStore(args.cache_dir)
    pdf_sha = {FILENAME_DOC_ID_MAP[n]: file_sha256(os.path.join(args.pdf_dir, n))
               for n in os.listdir(args.pdf_dir) if n in FILENAME_DOC_ID_MAP}

    ck.lines.append("§0 环境与输入")
    ck.note(f"python={platform.python_version()} "
            f"git={subprocess.run(['git','rev-parse','HEAD'],capture_output=True).stdout.decode().strip()}")
    ck.note(f"script sha256={file_sha256(os.path.abspath(__file__))}")
    ck.note(f"design_freeze sha256={file_sha256(os.path.join(repo, 'experiments/ocr_survey/_phase_b_design_freeze.md'))}")
    ck.note(f"baseline corpus sha256={file_sha256(args.baseline_corpus)}")
    ck.note(f"build_a chunks sha256={file_sha256(os.path.join(args.build_a, 'chunks.jsonl'))}")
    ck.note(f"build_a page_quality sha256={file_sha256(os.path.join(args.build_a, 'page_quality.jsonl'))}")
    ck.note(f"ocr_params_digest={oa.ocr_params_digest()}")
    ck.lines.append("")
    ck.lines.append("§1 acceptance invariants")

    # A. deterministic double build
    same_chunks = file_sha256(os.path.join(args.build_a, "chunks.jsonl")) == \
        file_sha256(os.path.join(args.build_b, "chunks.jsonl"))
    same_pq = file_sha256(os.path.join(args.build_a, "page_quality.jsonl")) == \
        file_sha256(os.path.join(args.build_b, "page_quality.jsonl"))
    ck.check("A", "同 frozen input 两次 build 逐字节一致", same_chunks and same_pq,
             f"chunks_identical={same_chunks} page_quality_identical={same_pq}")

    # B. page accounting
    source_pages = 0
    per_doc_pages: dict[str, int] = {}
    for name, doc_id in sorted(FILENAME_DOC_ID_MAP.items()):
        path = os.path.join(args.pdf_dir, name)
        if not os.path.isfile(path):
            continue
        pages, expected = iter_native_pages(path)
        per_doc_pages[doc_id] = expected
        source_pages += expected
    keys = [(r["doc_id"], r["pdf_page"]) for r in pq_a]
    dup = [k for k, c in collections.Counter(keys).items() if c > 1]
    missing = [(d, p) for d, n in per_doc_pages.items() for p in range(1, n + 1) if (d, p) not in set(keys)]
    extra = [k for k in keys if k[1] > per_doc_pages.get(k[0], 0)]
    ck.check("B", "page_quality 每个 source page 恰一条",
             len(pq_a) == source_pages == EXPECTED_SOURCE_PAGES and not dup and not missing and not extra,
             f"source_pages={source_pages} rows={len(pq_a)} duplicates={len(dup)} missing={len(missing)} extra={len(extra)}")

    # C. 无静默丢页：每页有终态 + reason；未入库页 chunk_ids 为空且有 reason
    bad_state = [r for r in pq_a if r["remediation_action"] not in pb.TERMINAL_ACTIONS or not r["remediation_reason"]]
    admitted = {(r["doc_id"], r["pdf_page"]) for r in pq_a
                if r["remediation_action"] in (pb.ACTION_ADMITTED_NATIVE, pb.ACTION_ADMITTED_OCR)}
    non_admitted_with_chunks = [r for r in pq_a if r["remediation_action"] not in
                                (pb.ACTION_ADMITTED_NATIVE, pb.ACTION_ADMITTED_OCR) and r["chunk_ids"]]
    chunk_pages = {(c["doc_id"], c["pdf_page"]) for c in chunks_a}
    ck.check("C", "无静默丢页：终态+reason 齐全，未入库页无 chunk",
             not bad_state and not non_admitted_with_chunks and chunk_pages == admitted,
             f"bad_state={len(bad_state)} non_admitted_with_chunks={len(non_admitted_with_chunks)} "
             f"admitted_pages={len(admitted)} chunk_pages={len(chunk_pages)}")

    # D. OCR artifact 双向身份校验
    ocr_pages = [r for r in pq_a if r["ocr_attempted"]]
    id_ok = True
    for r in ocr_pages:
        entry = next((e for e in store.iter_accepted()
                      if e["source_hash"] == r["source_hash"] and int(e["pdf_page"]) == r["pdf_page"]), None)
        if entry is None or entry["ocr_artifact_sha256"] != r["ocr_artifact_sha256"]:
            id_ok = False
            break
        payload = store.load_accepted(oa.CacheIdentity(**entry["cache_key"]))
        if payload["source_hash"] != r["source_hash"] or int(payload["pdf_page"]) != r["pdf_page"]:
            id_ok = False
            break
    ck.check("D", "所有 OCR artifact 的 source_hash / pdf_page 双向校验", id_ok,
             f"ocr_pages={len(ocr_pages)}")

    # E. accepted artifact immutable + 同 key 不静默覆盖
    entries = list(store.iter_accepted())
    digest_ok = all(file_sha256(os.path.join(args.cache_dir, e["artifact_path"])) == e["ocr_artifact_sha256"]
                    for e in entries)
    readonly = all((os.stat(os.path.join(args.cache_dir, e["artifact_path"])).st_mode & 0o222) == 0 for e in entries)
    key_unique = len({e["cache_key_digest"] for e in entries}) == len(entries)
    ck.check("E", "accepted artifact immutable 且同 key 唯一", digest_ok and readonly and key_unique,
             f"accepted={len(entries)} digest_ok={digest_ok} readonly={readonly} key_unique={key_unique}")

    # F. parser/build 不隐式运行 OCR（AST 静态检查：只看可执行代码，不看 docstring/注释）
    offenders: list[str] = []
    for rel in PRODUCTION_MODULES:
        src = open(os.path.join(repo, rel), encoding="utf-8").read()
        mod = ast.parse(src)
        for node in ast.walk(mod):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for nm in names:
                    if nm and "run_ocr" in nm:
                        offenders.append(f"{rel}:imports:{nm}")
            if isinstance(node, ast.Call):
                called = ast.unparse(node.func)
                if called.endswith(("ocr_argv", "ocr_image", "rasterize_page", "ocr_once")) and \
                        rel != "components/parsers/ocr_artifact.py":
                    offenders.append(f"{rel}:calls:{called}")
                for arg in node.args:
                    text = ast.unparse(arg)
                    if "tesseract" in text or "pdftoppm" in text:
                        offenders.append(f"{rel}:spawns:{text[:40]}")
    ck.check("F", "parser/build 无隐式 OCR 调用（AST）", not offenders, f"offenders={offenders}")

    # G. single primary body invariant
    violations: list[str] = []
    by_page: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for c in chunks_a:
        by_page[(c["doc_id"], c["pdf_page"])].append(c)
    for r in pq_a:
        key = (r["doc_id"], r["pdf_page"])
        if key not in by_page:
            continue
        if r["body_source_channel"] not in (pb.BODY_CHANNEL_NATIVE, pb.BODY_CHANNEL_OCR):
            violations.append(f"{key}:channel={r['body_source_channel']}")
    ck.check("G", "admitted page 的 primary body 只有一个 channel", not violations, f"violations={len(violations)}")

    # H. CASE R：native 乱码不得进入 body
    case_r = [r for r in pq_a if r["native_body_status"] == ps.NATIVE_UNUSABLE]
    r_admitted = [r for r in case_r if r["remediation_action"] == pb.ACTION_ADMITTED_OCR]
    garbled_leak = []
    for r in r_admitted:
        for c in by_page[(r["doc_id"], r["pdf_page"])]:
            if chr(0xFF) in c["text"] or any(ps.is_control_char(ch) for ch in c["text"]):
                garbled_leak.append(c["id"])
    ck.check("H", "CASE R：native 乱码正文不进入 corpus", not garbled_leak,
             f"case_r_pages={len(case_r)} admitted={len(r_admitted)} leaked={len(garbled_leak)}")

    # I. CASE S：native residual 不与 OCR 拼接
    case_s = [r for r in pq_a if r["native_body_status"] == ps.NATIVE_INSUFFICIENT]
    s_admitted = [r for r in case_s if r["remediation_action"] == pb.ACTION_ADMITTED_OCR]
    concat = [r for r in s_admitted
              if r["native_body_chars"] and r["ocr_body_chars"] and
              sum(len(c["text"]) for c in by_page[(r["doc_id"], r["pdf_page"])]) >
              r["ocr_body_chars"] + contracts.CHUNK_MIN_CHARS]
    ck.check("I", "CASE S：native 残余正文未与 OCR 拼接", not concat,
             f"case_s_pages={len(case_s)} admitted={len(s_admitted)} suspicious={len(concat)}")

    # J. CASE A：usable native 页不被自动 augment
    case_a_bad = [r for r in pq_a if r["native_body_status"] == ps.NATIVE_USABLE and
                  (r["ocr_attempted"] or r["body_source_channel"] != pb.BODY_CHANNEL_NATIVE or
                   r["page_content_completeness_status"] != ps.COMPLETENESS_NOT_ASSESSED)]
    ck.check("J", "CASE A：usable native 页未被自动 OCR augment", not case_a_bad,
             f"usable_pages={sum(1 for r in pq_a if r['native_body_status']==ps.NATIVE_USABLE)} bad={len(case_a_bad)}")

    # K. OCR path 非 explicit_supported 不入库
    k_bad = [r for r in pq_a if r["body_source_channel"] == pb.BODY_CHANNEL_OCR and r["chunk_ids"]
             and r["citation_metadata_status"] != cg.EXPLICIT_SUPPORTED]
    ck.check("K", "OCR path：citation != explicit_supported 一律不入 corpus", not k_bad, f"violations={len(k_bad)}")

    # L. legacy native uncertain metadata 未被批量重写 / quarantine
    legacy_uncertain = [r for r in pq_a if r["native_body_status"] == ps.NATIVE_USABLE
                        and r["citation_metadata_status"] == cg.UNCERTAIN]
    legacy_quarantined = [r for r in legacy_uncertain if r["remediation_action"] == pb.ACTION_QUARANTINED]
    ck.check("L", "legacy native uncertain metadata 保持 baseline 行为",
             len(legacy_uncertain) > 0 and not legacy_quarantined,
             f"legacy_uncertain={len(legacy_uncertain)} quarantined={len(legacy_quarantined)}")

    # M. Chunk schema 未变
    names = {f.name for f in dc_fields(contracts.Chunk)}
    expected_names = {"id", "text", "doc_id", "doc_name", "section", "section_title", "pdf_page",
                      "printed_page", "issued_by", "revision", "lang", "image_ids", "source_hash"}
    ck.check("M", "Chunk schema 未变", names == expected_names, f"fields={len(names)}")

    # N. Chunk.source_hash 仍是源 PDF sha256
    n_bad = [c["id"] for c in chunks_a if c["source_hash"] != pdf_sha.get(c["doc_id"])]
    ck.check("N", "Chunk.source_hash = 源 PDF sha256", not n_bad, f"mismatched={len(n_bad)}")

    # O. 视觉信号不参与 production action
    action_src = open(os.path.join(repo, "components/parsers/phase_b_ingest.py"), encoding="utf-8").read()
    tree = ast.parse(action_src)
    decide = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_decide_action")
    decide_src = ast.get_source_segment(action_src, decide) or ""
    visual_tokens = [t for t in ("visual", "active_row", "ink", "bbox", "completeness") if t in decide_src]
    # plan_ocr_targets：只扫描【可执行代码里的标识符】，docstring/注释里的禁止性说明不计入
    plan_tree = ast.parse(open(os.path.join(repo, "ingest/plan_ocr_targets.py"), encoding="utf-8").read())
    plan_idents: set[str] = set()
    for node in ast.walk(plan_tree):
        if isinstance(node, ast.Name):
            plan_idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            plan_idents.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node is not None:
            pass  # 字符串常量（含 docstring）不计入标识符
    plan_visual = sorted(i for i in plan_idents
                         if any(t in i.lower() for t in ("active_row", "ink", "bbox", "visual")))
    ck.check("O", "视觉信号不 production-gate OCR / action",
             not visual_tokens and not plan_visual,
             f"in_decide_action={visual_tokens} in_plan_targets={plan_visual}")

    # P. 无 doc / page 硬编码
    hard: list[str] = []
    for rel in PRODUCTION_MODULES:
        src = open(os.path.join(repo, rel), encoding="utf-8").read()
        body = src.split("FILENAME_DOC_ID_MAP: dict[str, str] = {")[-1] if "FILENAME_DOC_ID_MAP: dict" in src else src
        for doc in DOC_IDS:
            for pattern in (f'doc_id == "{doc}"', f"doc_id=='{doc}'", f'== "{doc}"'):
                if pattern in body:
                    hard.append(f"{rel}:{pattern}")
        for pattern in (r"pdf_page\s*==\s*\d+", r"pdf_page\s+in\s+range\(\d+", r"38\s*<=\s*", r"pdf_page\s*<=\s*10[0-9]"):
            if re.search(pattern, src):
                hard.append(f"{rel}:{pattern}")
    ck.check("P", "生产代码无文档名 / 页码硬编码", not hard, f"hits={hard}")

    # S. 所有 quarantine / failure / conflict 都有记录
    quarantined = [r for r in pq_a if r["remediation_action"] == pb.ACTION_QUARANTINED]
    conflicts = [r for r in pq_a if r["metadata_conflict"]]
    ocr_bad = [r for r in pq_a if r["ocr_body_status"] in (ps.OCR_DEGRADED, ps.OCR_FAILED)]
    s_ok = all(r["remediation_reason"] and r["metadata_reason_code"] for r in quarantined + conflicts + ocr_bad)
    ck.check("S", "quarantine / failure / conflict 均有 page_quality 记录与 reason", s_ok,
             f"quarantined={len(quarantined)} conflicts={len(conflicts)} ocr_degraded_or_failed={len(ocr_bad)}")

    # ---- 统计报表 ----
    ck.lines.append("")
    ck.lines.append("§2 统计")
    for key in ("remediation_action", "native_body_status", "ocr_body_status", "citation_metadata_status",
                "content_policy_status", "body_source_channel", "metadata_source_channel",
                "page_content_completeness_status"):
        ck.note(f"{key:34} {dict(sorted(collections.Counter(str(r[key]) for r in pq_a).items()))}")
    ck.note(f"{'require_review':34} {sum(1 for r in pq_a if r['require_review'])}")
    ck.note(f"{'metadata_conflict':34} {len(conflicts)}")
    baseline = load_jsonl(args.baseline_corpus)
    ck.lines.append("")
    ck.lines.append("§3 corpus delta（baseline → new）")
    ob = collections.Counter(c["doc_id"] for c in baseline)
    nb = collections.Counter(c["doc_id"] for c in chunks_a)
    for doc in sorted(set(ob) | set(nb)):
        ck.note(f"{doc:<6} old={ob[doc]:<5} new={nb[doc]:<5} delta={nb[doc]-ob[doc]:+d}")
    ck.note(f"TOTAL  old={len(baseline):<5} new={len(chunks_a):<5} delta={len(chunks_a)-len(baseline):+d}")
    ck.note(f"baseline_sha256={file_sha256(args.baseline_corpus)}")
    ck.note(f"new_sha256={file_sha256(os.path.join(args.build_a, 'chunks.jsonl'))}")

    ck.lines.append("")
    ck.lines.append("§4 全部 QUARANTINED 页（逐页）")
    for r in sorted(quarantined, key=lambda r: (r["doc_id"], r["pdf_page"])):
        ck.note(f"{r['doc_id']}:p{r['pdf_page']:<4} native={r['native_body_status']:<12} "
                f"ocr={r['ocr_body_status']:<12} citation={r['citation_metadata_status']:<18} "
                f"reason={r['remediation_reason']}")
    ck.lines.append("")
    ck.lines.append("§5 OCR degraded / failed 页")
    for r in sorted(ocr_bad, key=lambda r: (r["doc_id"], r["pdf_page"])):
        ck.note(f"{r['doc_id']}:p{r['pdf_page']:<4} {r['ocr_body_status']:<10} {r['ocr_body_reason']} "
                f"action={r['remediation_action']}")
    ck.lines.append("")
    ck.lines.append("§6 metadata conflict 页")
    for r in sorted(conflicts, key=lambda r: (r["doc_id"], r["pdf_page"])):
        ck.note(f"{r['doc_id']}:p{r['pdf_page']:<4} native={r['native_metadata_candidate']!r} "
                f"ocr={r['ocr_metadata_candidate']!r} action={r['remediation_action']}")

    verdict = "PASS" if ck.failures == 0 else "FAIL"
    ck.lines.insert(0, f"S5c ACCEPTANCE VERIFICATION = {verdict}（failures={ck.failures}）")
    ck.lines.insert(1, "=" * 78)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(ck.lines) + "\n")
    print(f"verification={verdict} failures={ck.failures}")
    return 0 if ck.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
