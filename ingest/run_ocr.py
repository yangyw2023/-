#!/usr/bin/env python3
"""岸端 OCR 执行步骤（Phase B Hybrid C 的第 2 步）。

职责:
  光栅化选中页 → 调 Tesseract → 写 candidate artifact → acceptance → 冻结 accepted artifact。

【本脚本是唯一允许执行 OCR 的地方】。parser / build_corpus 绝不隐式调用它。
船端不运行本脚本，也不需要 Tesseract。

用法:
    # PRECHECK 0：对代表页重复执行两次并比较字节
    python3 ingest/run_ocr.py precheck --pdf-dir "raw/KAIVA - Manuals" \\
        --cache-dir ocr_cache --pages TACM:60 TACM:51 CMM:112 QMM:139 TACM:55 CMM:32 \\
        --out-log experiments/ocr_survey/_phase_b_precheck0.log

    # 全量：按 target 列表执行（target 由 ingest/plan_ocr_targets.py 产出）
    python3 ingest/run_ocr.py run --pdf-dir "raw/KAIVA - Manuals" \\
        --cache-dir ocr_cache --targets <targets.jsonl> --out-log <log>

失败语义:
    pdftoppm / tesseract 缺失、返回非零、超时、输出缺失 → 抛异常并以非零码退出。
    已存在 accepted artifact 的 cache key：不重跑 OCR（命中缓存），不覆盖。
    重跑得到不同字节：记 reproducibility event，不自动替换（Design Freeze §8.2 规则 5）。
    禁止 except 后 continue 丢页。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import ocr_artifact as oa  # noqa: E402

POPPLER_TIMEOUT_S: float = 300.0
TESSERACT_TIMEOUT_S: float = 300.0
PDF_SUFFIX: str = ".pdf"

# Phase A / A.1 / A.2 / A.2b 已冻结的文件名 → doc_id 映射来源保持单点：复用 parser 的映射。
from components.parsers.kaiva_pdf import FILENAME_DOC_ID_MAP  # noqa: E402


class OcrRunError(RuntimeError):
    """OCR 执行失败（工具缺失 / 非零返回 / 超时 / 输出缺失）。"""


def run_cmd(argv: Sequence[str], timeout_s: float, env: dict[str, str] | None = None) -> bytes:
    merged = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=timeout_s, env=merged)
    except FileNotFoundError as exc:
        raise OcrRunError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OcrRunError(f"超时 >{timeout_s}s: {' '.join(argv[:3])}") from exc
    if proc.returncode != 0:
        raise OcrRunError(f"{argv[0]} 返回 {proc.returncode}: {proc.stderr.decode('utf-8', 'replace').strip()[:400]}")
    return proc.stdout


def tool_versions() -> dict[str, str]:
    """探测 rasterizer / OCR engine 版本与 langpack 身份。抛出 OcrRunError —— 工具缺失。"""
    ras = subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    ras_text = (ras.stdout + ras.stderr).decode("utf-8", "replace")
    m = re.search(r"pdftoppm version ([0-9.]+)", ras_text)
    if not m:
        raise OcrRunError(f"无法解析 pdftoppm 版本: {ras_text[:200]}")
    tes = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=TESSERACT_TIMEOUT_S)
    tes_text = (tes.stdout + tes.stderr).decode("utf-8", "replace")
    m2 = re.search(r"tesseract ([0-9][0-9A-Za-z.\-]*)", tes_text)
    if not m2:
        raise OcrRunError(f"无法解析 tesseract 版本: {tes_text[:200]}")
    tessdata = tessdata_dir()
    langpack = os.path.join(tessdata, f"{oa.OCR_LANG}.traineddata")
    if not os.path.isfile(langpack):
        raise OcrRunError(f"langpack 缺失: {langpack}")
    return {
        "rasterizer_version": m.group(1),
        "ocr_engine_version": m2.group(1),
        "tessdata_dir": tessdata,
        "langpack_path": langpack,
        "langpack_identity_digest": oa.file_sha256(langpack),
    }


def tessdata_dir() -> str:
    """定位 tessdata 目录（不安装、不下载）。抛出 OcrRunError —— 找不到。"""
    env = os.environ.get("TESSDATA_PREFIX")
    candidates = [env] if env else []
    candidates += ["/opt/homebrew/share/tessdata", "/usr/local/share/tessdata", "/usr/share/tessdata"]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, f"{oa.OCR_LANG}.traineddata")):
            return path
    raise OcrRunError(f"找不到含 {oa.OCR_LANG}.traineddata 的 tessdata 目录: {candidates}")


def rasterize_page(pdf_path: str, pdf_page: int, work_dir: str) -> str:
    """按冻结参数光栅化单页，返回 PGM 路径。抛出 OcrRunError —— 输出文件数 != 1。"""
    prefix = os.path.join(work_dir, "page")
    argv = ["pdftoppm", "-r", str(oa.RASTER_DPI), "-f", str(pdf_page), "-l", str(pdf_page)]
    if oa.RASTER_GRAY:
        argv.append("-gray")
    argv += [pdf_path, prefix]
    run_cmd(argv, POPPLER_TIMEOUT_S)
    outs = sorted(f for f in os.listdir(work_dir) if f.endswith(f".{oa.RASTER_FORMAT}"))
    if len(outs) != 1:
        raise OcrRunError(f"pdftoppm 输出文件数 {len(outs)} != 1: {pdf_path} p{pdf_page}")
    return os.path.join(work_dir, outs[0])


def ocr_image(image_path: str, work_dir: str, tessdata: str) -> tuple[str, str]:
    """对光栅图执行 OCR，返回 (raw_text, tsv_text)。抛出 OcrRunError —— 输出缺失。"""
    out_base = os.path.join(work_dir, "ocr")
    run_cmd(oa.ocr_argv(image_path, out_base, tessdata), TESSERACT_TIMEOUT_S, env=oa.OCR_ENV)
    txt_path, tsv_path = out_base + ".txt", out_base + ".tsv"
    for path in (txt_path, tsv_path):
        if not os.path.isfile(path):
            raise OcrRunError(f"tesseract 未产出 {path}")
    with open(txt_path, "rb") as handle:
        raw = handle.read().decode("utf-8", errors="replace")
    with open(tsv_path, "rb") as handle:
        tsv = handle.read().decode("utf-8", errors="replace")
    return raw, tsv


def build_payload(source_hash: str, pdf_page: int, raster_sha: str, raw_text: str, tsv_text: str,
                  versions: dict[str, str]) -> dict[str, object]:
    """组装 artifact payload（逐字节确定，不含时间戳 / 路径 / 机器名）。"""
    return {
        "schema_version": oa.OCR_ARTIFACT_SCHEMA_VERSION,
        "source_hash": source_hash,
        "pdf_page": pdf_page,
        "rasterizer": oa.RASTERIZER,
        "rasterizer_version": versions["rasterizer_version"],
        "raster_dpi": oa.RASTER_DPI,
        "raster_sha256": raster_sha,
        "ocr_engine": oa.OCR_ENGINE,
        "ocr_engine_version": versions["ocr_engine_version"],
        "langpack": oa.OCR_LANG,
        "langpack_identity_digest": versions["langpack_identity_digest"],
        "ocr_params_digest": oa.ocr_params_digest(),
        "text": oa.normalize_ocr_text(raw_text),
        "text_raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "confidence_stats": oa.confidence_stats(tsv_text),
    }


def ocr_once(pdf_path: str, source_hash: str, pdf_page: int, versions: dict[str, str]) -> tuple[dict[str, object], str]:
    """执行一次完整 OCR（光栅化 + 识别），返回 (payload, raster_sha)。"""
    work = tempfile.mkdtemp(prefix=f"ocr_p{pdf_page}_")
    try:
        image = rasterize_page(pdf_path, pdf_page, work)
        raster_sha = oa.file_sha256(image)
        raw, tsv = ocr_image(image, work, versions["tessdata_dir"])
        return build_payload(source_hash, pdf_page, raster_sha, raw, tsv, versions), raster_sha
    finally:
        shutil.rmtree(work, ignore_errors=True)


def resolve_pdfs(pdf_dir: str) -> dict[str, tuple[str, str]]:
    """doc_id → (path, source_hash)。抛出 OcrRunError —— 目录无 PDF / 文件名未登记。"""
    out: dict[str, tuple[str, str]] = {}
    for name in sorted(os.listdir(pdf_dir)):
        if not name.lower().endswith(PDF_SUFFIX):
            continue
        if name not in FILENAME_DOC_ID_MAP:
            raise OcrRunError(f"PDF 文件名未登记在 FILENAME_DOC_ID_MAP: {name}")
        path = os.path.join(pdf_dir, name)
        out[FILENAME_DOC_ID_MAP[name]] = (path, oa.file_sha256(path))
    if not out:
        raise OcrRunError(f"目录下没有 PDF: {pdf_dir}")
    return out


def env_header(args: argparse.Namespace, versions: dict[str, str]) -> list[str]:
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, timeout=30)
    return [
        f"  python                  = {platform.python_version()}",
        f"  git_commit              = {git.stdout.decode().strip()}",
        f"  script                  = ingest/run_ocr.py sha256={oa.file_sha256(os.path.abspath(__file__))}",
        f"  ocr_artifact_module     = components/parsers/ocr_artifact.py "
        f"sha256={oa.file_sha256(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'components/parsers/ocr_artifact.py'))}",
        f"  rasterizer              = {oa.RASTERIZER} {versions['rasterizer_version']} dpi={oa.RASTER_DPI} "
        f"format={oa.RASTER_FORMAT} gray={oa.RASTER_GRAY}",
        f"  ocr_engine              = {oa.OCR_ENGINE} {versions['ocr_engine_version']}",
        f"  langpack                = {oa.OCR_LANG} path={versions['langpack_path']}",
        f"  langpack_identity_digest= {versions['langpack_identity_digest']}",
        f"  ocr_params_canonical    = {oa.ocr_params_canonical()}",
        f"  ocr_params_digest       = {oa.ocr_params_digest()}",
        f"  cache_dir               = {args.cache_dir}",
    ]


def cmd_precheck(args: argparse.Namespace) -> int:
    """IMPLEMENTATION PRECHECK 0：同配置重复两次 OCR，逐页比较字节。"""
    versions = tool_versions()
    pdfs = resolve_pdfs(args.pdf_dir)
    store = oa.OcrArtifactStore(args.cache_dir)
    out: list[str] = ["Phase B IMPLEMENTATION PRECHECK 0 —— OCR repeatability characterization",
                      "=" * 78, "§0 runtime provenance"]
    out += env_header(args, versions)
    out += ["", "§1 逐页两次独立执行的比较（同 source / page / raster / engine / langpack / params）", ""]
    all_identical = True
    rows: list[dict[str, object]] = []
    for target in args.pages:
        doc_id, page_s = target.split(":")
        pdf_page = int(page_s)
        if doc_id not in pdfs:
            raise OcrRunError(f"未知 doc_id: {doc_id}")
        path, source_hash = pdfs[doc_id]
        p1, raster1 = ocr_once(path, source_hash, pdf_page, versions)
        p2, raster2 = ocr_once(path, source_hash, pdf_page, versions)
        b1, b2 = oa.serialize_artifact(p1), oa.serialize_artifact(p2)
        sha1, sha2 = oa.artifact_sha256(b1), oa.artifact_sha256(b2)
        identical = (raster1 == raster2 and p1["text_raw_sha256"] == p2["text_raw_sha256"] and sha1 == sha2)
        all_identical &= identical
        identity = oa.build_cache_identity(source_hash, pdf_page, versions["rasterizer_version"],
                                           versions["ocr_engine_version"], versions["langpack_identity_digest"])
        cand_path, cand_sha = store.write_candidate(identity, p1)
        entry = store.accept(identity, cand_path, cand_sha)
        if not identical:
            store.record_reproducibility_event(identity, entry["ocr_artifact_sha256"], sha2,
                                               "PRECHECK 0: second run produced different bytes")
        rows.append({"target": target, "identical": identical, "raster1": raster1, "raster2": raster2,
                     "text_raw1": p1["text_raw_sha256"], "text_raw2": p2["text_raw_sha256"],
                     "artifact1": sha1, "artifact2": sha2,
                     "text_chars": len(str(p1["text"])), "conf": p1["confidence_stats"]})
        out.append(f"  {target:<12} byte_identical={identical}")
        out.append(f"    raster_sha256   run1={raster1[:32]}  run2={raster2[:32]}")
        out.append(f"    text_raw_sha256 run1={str(p1['text_raw_sha256'])[:32]}  run2={str(p2['text_raw_sha256'])[:32]}")
        out.append(f"    artifact_sha256 run1={sha1[:32]}  run2={sha2[:32]}")
        out.append(f"    normalized_text_chars={len(str(p1['text']))}  confidence_stats={json.dumps(p1['confidence_stats'], sort_keys=True)}")
        out.append(f"    accepted_artifact={entry['artifact_path']} sha256={entry['ocr_artifact_sha256']}")
        out.append("")
    result = "observed_deterministic_under_tested_configuration" if all_identical else "regeneration_difference_observed"
    out.append(f"§2 OCR_REPEATABILITY_RESULT = {result}")
    out.append("  ⚠️ 该结论只对本次测试配置成立：不得外推到其他 Tesseract 版本、其他 traineddata、")
    out.append("     其他 DPI、其他参数或其他机器。")
    out.append("  ⚠️ OCR runtime available != OCR repeatability characterized != OCR body usable")
    out.append("     != citation metadata supported != S5c PASS。")
    if not all_identical:
        out.append("  差异不推翻 Hybrid C：accepted artifact 一次冻结、同 key 不静默覆盖、")
        out.append("  parser 只消费 accepted digest —— 差异被 artifact freeze 隔离，并已记 reproducibility event。")
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"precheck pages={len(rows)} all_identical={all_identical} result={result}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """按 target 列表执行 OCR：命中 accepted 缓存则跳过，否则 candidate → accept。"""
    versions = tool_versions()
    pdfs = resolve_pdfs(args.pdf_dir)
    store = oa.OcrArtifactStore(args.cache_dir)
    targets: list[dict[str, object]] = []
    with open(args.targets, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                targets.append(json.loads(line))
    targets.sort(key=lambda t: (str(t["doc_id"]), int(t["pdf_page"])))

    out: list[str] = ["Phase B OCR execution step（岸端；parser/build 不得调用本步骤）", "=" * 78,
                      "§0 runtime provenance"]
    out += env_header(args, versions)
    out += ["", f"§1 targets = {len(targets)}", ""]
    t0 = time.perf_counter()
    executed = cached = events = 0
    for target in targets:
        doc_id, pdf_page = str(target["doc_id"]), int(target["pdf_page"])
        if doc_id not in pdfs:
            raise OcrRunError(f"未知 doc_id: {doc_id}")
        path, source_hash = pdfs[doc_id]
        if str(target.get("source_hash", source_hash)) != source_hash:
            raise OcrRunError(f"target 的 source_hash 与当前 PDF 不一致: {doc_id}:p{pdf_page}")
        identity = oa.build_cache_identity(source_hash, pdf_page, versions["rasterizer_version"],
                                           versions["ocr_engine_version"], versions["langpack_identity_digest"])
        entry = store.accepted_entry(identity)
        if entry is not None:
            cached += 1
            out.append(f"  {doc_id}:p{pdf_page:<4} cache_hit  artifact={entry['ocr_artifact_sha256'][:16]}")
            continue
        payload, _ = ocr_once(path, source_hash, pdf_page, versions)
        cand_path, cand_sha = store.write_candidate(identity, payload)
        entry = store.accept(identity, cand_path, cand_sha)
        executed += 1
        stats = payload["confidence_stats"]
        out.append(f"  {doc_id}:p{pdf_page:<4} ocr_done   artifact={entry['ocr_artifact_sha256'][:16]} "
                   f"chars={len(str(payload['text']))} mean_conf={stats['mean_conf']}")
    elapsed = time.perf_counter() - t0
    out += ["", f"§2 executed={executed} cache_hit={cached} reproducibility_events={events}",
            "", "==== 【TIMING】 非确定段 ====", f"  total {elapsed:.1f} s"]
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"ocr targets={len(targets)} executed={executed} cache_hit={cached} elapsed={elapsed:.1f}s")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("precheck", "run"):
        p = sub.add_parser(name)
        p.add_argument("--pdf-dir", required=True)
        p.add_argument("--cache-dir", required=True)
        p.add_argument("--out-log", required=True)
        if name == "precheck":
            p.add_argument("--pages", nargs="+", required=True, help="DOC_ID:PDF_PAGE ...")
        else:
            p.add_argument("--targets", required=True, help="jsonl: {doc_id, pdf_page, source_hash}")
    args = ap.parse_args(argv)
    return cmd_precheck(args) if args.cmd == "precheck" else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
