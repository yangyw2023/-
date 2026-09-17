"""语料构建脚本：把一个目录下的 KAIVA 手册全部解析成 chunks.jsonl 与报表。

用法:
    python3 ingest/build_corpus.py "raw/KAIVA - Manuals" corpus

产出（均写在 <出目录> 下）:
    chunks.jsonl         每行一个 chunk 的 JSON（ensure_ascii=False）
    ingest_report.csv    每份成功解析的文档一行
    ingest_failures.csv  每份解析失败的文档一行（file, error_type, error）

单份文档失败【跳过并继续】，不中断整批 —— 这正是 contracts.ParseError 的契约。
只依赖标准库与 poppler 命令行。
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import statistics
import sys
import time
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers.kaiva_pdf import UNKNOWN_SECTION, KaivaPdfParser  # noqa: E402
from core import contracts  # noqa: E402

# ==============================================================================
# 模块常量
# ==============================================================================

CHUNKS_FILENAME: str = "chunks.jsonl"
REPORT_FILENAME: str = "ingest_report.csv"
FAILURES_FILENAME: str = "ingest_failures.csv"

PDF_SUFFIX: str = ".pdf"

# 打印 chunks.jsonl 指纹时截取的十六进制位数。后续派生产物（索引包等）用它命名。
CORPUS_HASH_PREFIX_LEN: int = 8

REPORT_COLUMNS: tuple[str, ...] = (
    "file", "doc_id", "chunks", "pages_covered", "sections", "unknown_section",
    "chars_min", "chars_median", "chars_max", "parse_sec",
)
FAILURE_COLUMNS: tuple[str, ...] = ("file", "error_type", "error")

# 读取 chunks.jsonl 求 sha256 时的分块大小（字节）。
HASH_READ_BLOCK_BYTES: int = 1 << 20


def _report_row(filename: str, chunks: Sequence[contracts.Chunk], parse_sec: float) -> dict[str, object]:
    """把一份文档的解析结果汇成报表的一行。

    输入假设: chunks 非空（解析器契约保证：无有效内容会抛 ParseError）。
    """
    lengths = sorted(len(c.text) for c in chunks)
    return {
        "file": filename,
        "doc_id": chunks[0].doc_id,
        "chunks": len(chunks),
        "pages_covered": len({c.pdf_page for c in chunks}),
        "sections": len({c.section for c in chunks}),
        "unknown_section": sum(1 for c in chunks if c.section == UNKNOWN_SECTION),
        "chars_min": lengths[0],
        "chars_median": int(statistics.median(lengths)),
        "chars_max": lengths[-1],
        "parse_sec": round(parse_sec, 2),
    }


def _sha256_prefix(path: str, length: int) -> str:
    """文件 sha256 的前 length 位十六进制。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()[:length]


def build_corpus(source_dir: str, out_dir: str) -> int:
    """解析 source_dir 下所有 *.pdf，写出语料与报表，返回成功解析的文档数。

    输入假设: source_dir 存在且可读；out_dir 不存在时会被创建。
    异常语义:
      - source_dir 不存在 / 不含任何 PDF → 抛 FileNotFoundError（整批无从开始，
        与"某一份坏了"是两回事，不能混为一谈）。
      - 单份文档的 contracts.ParseError → 记入 ingest_failures.csv 并继续。
    返回: 成功解析的文档数（不含失败的）。
    """
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"源目录不存在: {source_dir}")
    pdfs = sorted(f for f in os.listdir(source_dir) if f.lower().endswith(PDF_SUFFIX))
    if not pdfs:
        raise FileNotFoundError(f"源目录下没有 {PDF_SUFFIX} 文件: {source_dir}")

    os.makedirs(out_dir, exist_ok=True)
    chunks_path = os.path.join(out_dir, CHUNKS_FILENAME)
    report_path = os.path.join(out_dir, REPORT_FILENAME)
    failures_path = os.path.join(out_dir, FAILURES_FILENAME)

    parser = KaivaPdfParser()
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    total_chunks = 0

    with open(chunks_path, "w", encoding="utf-8") as sink:
        for filename in pdfs:
            path = os.path.join(source_dir, filename)
            started = time.perf_counter()
            try:
                chunks = parser.parse(path)
            except contracts.ParseError as exc:
                # 契约: 单份失败跳过并继续，不中断整批。
                failures.append({
                    "file": filename,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                print(f"  FAIL {filename}: {exc}", file=sys.stderr)
                continue
            elapsed = time.perf_counter() - started

            for chunk in chunks:
                sink.write(json.dumps(dataclasses.asdict(chunk), ensure_ascii=False) + "\n")
            total_chunks += len(chunks)
            rows.append(_report_row(filename, chunks, elapsed))
            print(f"  OK   {filename}: {len(chunks)} chunks in {elapsed:.1f}s")

    with open(report_path, "w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with open(failures_path, "w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=FAILURE_COLUMNS)
        writer.writeheader()
        writer.writerows(failures)

    print(f"\n解析成功 {len(rows)}/{len(pdfs)}    chunk 总数 {total_chunks}")
    print(f"chunks.jsonl sha256[:{CORPUS_HASH_PREFIX_LEN}] = "
          f"{_sha256_prefix(chunks_path, CORPUS_HASH_PREFIX_LEN)}")
    return len(rows)


def main(argv: Sequence[str]) -> int:
    """命令行入口。返回进程退出码：全部成功为 0，有文档失败为 1。"""
    if len(argv) != 3:
        print(f"用法: python3 {argv[0]} <源目录> <出目录>", file=sys.stderr)
        return 2
    source_dir, out_dir = argv[1], argv[2]
    started = time.perf_counter()
    succeeded = build_corpus(source_dir, out_dir)
    total = len([f for f in os.listdir(source_dir) if f.lower().endswith(PDF_SUFFIX)])
    print(f"全量耗时 {time.perf_counter() - started:.1f}s")
    return 0 if succeeded == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
