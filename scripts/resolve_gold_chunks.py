#!/usr/bin/env python3
"""把评测集 citations 解析到冻结语料的 chunk 上，产出 GoldChunkMap（contracts v0.3.1）。

职责边界:
  - 只读评测集与语料；【从不】修改评测集（不回写 gold_chunk_ids，不输出"resolved testset"）。
  - 单条 citation 的解析语义完全来自 core.contracts 的 MatchLevel 定义：
    片段来自 split_quote_fragments()（含短片段），只看 citation 所在页，
    formal gold = 唯一最小基数 full evidence cover；最小 cover 不唯一 → AMBIGUOUS，不做任何 tie-break。
  - GoldChunkMap 的构建身份只从 ingest.builder_identity 取得，并以该模块本身作为 builder
    传给 validate_gold_chunk_map()；本脚本不手写任何身份值。

用法:
    python3 scripts/resolve_gold_chunks.py --chunks corpus/chunks.jsonl \\
        --testset eval/testset_v5_3.jsonl --corpus-sha <8 位或 64 位小写十六进制> \\
        --out-dir eval/gold_chunk_map/

输出（均在 --out-dir 下，文件名由 GoldChunkMap.filename() / report_filename() 生成）:
  - <map>.report.csv   每条 answer citation 一行，【总是】写出
  - <map>.json         只有全部 answer citation 都解析为 L1/L2 且通过 validate_gold_chunk_map() 时才写出

退出码:
  0                       映射被接受并写出
  EXIT_MAP_NOT_ACCEPTED   存在未解析的 answer citation（fail-closed）：只写 report，不写映射
  其他非零                输入或契约错误（抛异常，不吞）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterator, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts  # noqa: E402
from core.contracts import (  # noqa: E402
    Chunk,
    Citation,
    ContractViolation,
    EvalItem,
    GoldChunkMap,
    is_sole_match_eligible,
    normalize_text,
    serialize_gold_chunk_map,
    split_quote_fragments,
    testset_version_from_path,
    validate_eval_item,
    validate_gold_chunk_map,
)
import ingest.builder_identity as builder_identity  # noqa: E402

# 映射未被接受（存在未解析的 answer citation）时的退出码。
EXIT_MAP_NOT_ACCEPTED: int = 3
# 完整 SHA-256 的十六进制长度（由算法导出，不是手写的 64）。
SHA256_HEX_CHARS: int = hashlib.sha256().digest_size * 2
_HEX_RE = re.compile(r"^[0-9a-f]+$")
# report.csv 里多个 chunk id 的连接符（契约规定）。
CHUNK_ID_SEPARATOR: str = ";"
# report.csv 布尔列的取值。
CSV_TRUE, CSV_FALSE = "true", "false"
HASH_READ_BLOCK_BYTES: int = 1 << 20


class ResolverInputError(Exception):
    """输入文件违反本脚本依赖的格式（坏 JSON、字段不符、重复 id、--corpus-sha 不匹配等）。

    这表示"数据坏了"，不是"没解析出来"：未解析的 citation 进 report，不抛本异常。
    """


# ==============================================================================
# 数据
# ==============================================================================

@dataclass(frozen=True)
class FragmentMatch:
    """一个引文片段在 citation 页上的命中证据。candidate_chunk_ids 按 corpus 顺序。"""
    index: int
    text: str
    sole_match_eligible: bool
    candidate_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class QuoteResolution:
    """单条 quote 在其所在页上的解析结果。

    formal_chunk_ids 只在 level ∈ FORMAL_MATCH_LEVELS 时非空，按 corpus 顺序。
    candidate_chunk_ids = 有片段命中、但不在 formal cover 中的 chunk，按 corpus 顺序。
    """
    level: str
    formal_chunk_ids: tuple[str, ...]
    candidate_chunk_ids: tuple[str, ...]
    fragments: tuple[FragmentMatch, ...]


@dataclass(frozen=True)
class CitationResolution:
    """一条 answer citation 的完整解析记录（report.csv 的一行）。citation_index 为 0-based。"""
    question_id: str
    citation_index: int
    citation: Citation
    section_exact_match: bool
    resolution: QuoteResolution


@dataclass(frozen=True)
class PageChunk:
    """语料中某页的一个 chunk（已按 corpus 顺序排好）。"""
    chunk_id: str
    text: str
    section: str


# ==============================================================================
# 核心解析（纯函数）
# ==============================================================================

def resolve_quote(quote: str, page_chunks: Sequence[tuple[str, str]]) -> QuoteResolution:
    """按 contracts.MatchLevel 的定义解析一条 quote。

    输入:
      - quote: citation 原文引语；片段一律经 split_quote_fragments()（含短片段）。
      - page_chunks: citation 所在页 (doc_id, pdf_page) 的全部 chunk，形如 (chunk_id, text)，
        【按 corpus 顺序】。空序列表示该页在语料中没有 chunk。本函数不看其他页。
    返回 QuoteResolution。只在 quote 为空等契约违反时抛 ContractViolation（来自 split_quote_fragments）。

    语义（逐条对应契约）:
      FAIL       page_chunks 为空
      L1 / L2    存在 full evidence cover，且最小基数 cover 唯一；|cover| = 1 为 L1，≥ 2 为 L2
      AMBIGUOUS  存在 full cover，但最小基数 cover 不唯一（不做任何 tie-break）
      L3         无 full cover，且至少一个 sole-match eligible 片段有 candidate
      L4         页存在，无 full cover，且没有 eligible 片段命中
    corpus 顺序只用于枚举与输出顺序；cover 是否唯一只取决于集合本身，与顺序无关。
    """
    fragments = split_quote_fragments(quote)
    order = [chunk_id for chunk_id, _ in page_chunks]
    if len(set(order)) != len(order):
        raise ResolverInputError(f"同一页出现重复 chunk id: {order}")
    normalized = {chunk_id: normalize_text(text) for chunk_id, text in page_chunks}
    candidates = [tuple(cid for cid in order if fragment in normalized[cid]) for fragment in fragments]
    matches = tuple(
        FragmentMatch(index=i, text=f, sole_match_eligible=is_sole_match_eligible(f), candidate_chunk_ids=c)
        for i, (f, c) in enumerate(zip(fragments, candidates))
    )
    matched_any = [cid for cid in order if any(cid in c for c in candidates)]

    if not page_chunks:
        return QuoteResolution("FAIL", (), (), matches)
    if all(candidates):
        covers = _minimum_covers(matched_any, candidates)
        if len(covers) == 1:
            formal = tuple(cid for cid in order if cid in covers[0])
            level = "L1" if len(formal) == 1 else "L2"
            return QuoteResolution(level, formal, tuple(cid for cid in matched_any if cid not in formal), matches)
        return QuoteResolution("AMBIGUOUS", (), tuple(matched_any), matches)
    if any(m.candidate_chunk_ids and m.sole_match_eligible for m in matches):
        return QuoteResolution("L3", (), tuple(matched_any), matches)
    return QuoteResolution("L4", (), tuple(matched_any), matches)


def _minimum_covers(universe: Sequence[str], candidates: Sequence[tuple[str, ...]]) -> list[frozenset[str]]:
    """返回全部最小基数 full cover（至多两个：两个就足以判定"不唯一"）。

    输入假设: 每个 candidates[i] 非空且 ⊆ universe。按基数从小到大枚举 universe 的组合，
    第一个出现 cover 的基数即最小基数。结果只取决于集合，不取决于枚举顺序。
    """
    needed = [frozenset(c) for c in candidates]
    for size in range(1, len(universe) + 1):
        found: list[frozenset[str]] = []
        for combo in itertools.combinations(universe, size):
            chosen = frozenset(combo)
            if all(chosen & n for n in needed):
                found.append(chosen)
                if len(found) > 1:
                    return found
        if found:
            return found
    raise ContractViolation("全部片段都有 candidate 时必然存在 full cover；不应到达此处")


# ==============================================================================
# 输入
# ==============================================================================

def file_sha256(path: str) -> str:
    """文件字节的完整 SHA-256（小写十六进制）。文件不可读抛 OSError。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _iter_jsonl(path: str) -> Iterator[tuple[int, dict]]:
    """逐行产出 (1-based 行号, JSON 对象)。

    空行（含仅空白的行）视为无意义格式而跳过，与仓库其他 JSONL 读取方
    （OcrArtifactStore、审计脚本、旧版 resolver）一致；行号仍按物理行计。
    非对象行、坏 JSON 一律抛 ResolverInputError。
    """
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ResolverInputError(f"{path}:{line_no}: 非法 JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ResolverInputError(f"{path}:{line_no}: 期望 JSON 对象，得到 {type(record).__name__}")
            yield line_no, record


def load_corpus(path: str) -> tuple[list[str], dict[tuple[str, int], list[PageChunk]]]:
    """读语料。返回 (全部 chunk id 按文件行序, {(doc_id, pdf_page): 该页 chunk 按行序})。

    每行必须恰好构成一个 contracts.Chunk；chunk id 全局唯一；pdf_page 为 ≥1 的 int。违反抛 ResolverInputError。
    """
    ids: list[str] = []
    seen: set[str] = set()
    pages: dict[tuple[str, int], list[PageChunk]] = {}
    for line_no, record in _iter_jsonl(path):
        try:
            chunk = Chunk(**record)
        except TypeError as exc:
            raise ResolverInputError(f"{path}:{line_no}: 不符合 Chunk schema: {exc}") from exc
        if chunk.id in seen:
            raise ResolverInputError(f"{path}:{line_no}: chunk id 重复: {chunk.id!r}")
        page = chunk.pdf_page
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ResolverInputError(f"{path}:{line_no}: pdf_page 必须是 ≥1 的 int，得到 {page!r}")
        seen.add(chunk.id)
        ids.append(chunk.id)
        pages.setdefault((chunk.doc_id, page), []).append(PageChunk(chunk.id, chunk.text, chunk.section))
    return ids, pages


def load_testset(path: str) -> list[EvalItem]:
    """读评测集，逐条构造 EvalItem 并调用 validate_eval_item()。按文件行序返回。

    字段多余/缺失（包括遗留的 gold_chunk_ids）→ ResolverInputError；契约违反 → ContractViolation。
    question id 重复 → ResolverInputError。
    """
    items: list[EvalItem] = []
    for line_no, record in _iter_jsonl(path):
        try:
            fields = dict(record)
            fields["citations"] = tuple(Citation(**c) for c in record.get("citations", ()))
            item = EvalItem(**fields)
        except TypeError as exc:
            raise ResolverInputError(f"{path}:{line_no}: 不符合 EvalItem/Citation schema: {exc}") from exc
        validate_eval_item(item)
        items.append(item)
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise ResolverInputError(f"{path}: question id 重复")
    return items


def check_corpus_sha_assertion(asserted: str, computed: str) -> None:
    """--corpus-sha 只是期望值断言: 必须是 CORPUS_SHA_PREFIX_CHARS 位或完整长度的小写十六进制，
    且是 computed 的前缀。否则抛 ResolverInputError。映射中永远只写 computed。"""
    if len(asserted) not in (contracts.CORPUS_SHA_PREFIX_CHARS, SHA256_HEX_CHARS) or not _HEX_RE.match(asserted):
        raise ResolverInputError(
            f"--corpus-sha 必须是 {contracts.CORPUS_SHA_PREFIX_CHARS} 位或 {SHA256_HEX_CHARS} 位小写十六进制: {asserted!r}"
        )
    if not computed.startswith(asserted):
        raise ResolverInputError(f"--corpus-sha {asserted!r} 与实际语料 sha256 {computed} 不符")


# ==============================================================================
# 解析整个评测集
# ==============================================================================

def resolve_all(items: Sequence[EvalItem],
                pages: dict[tuple[str, int], list[PageChunk]]) -> list[CitationResolution]:
    """解析每道 expected=="answer" 的题的每条 citation。按评测集顺序、citation_index 升序返回。

    拒答题不产生任何行（validate_eval_item 已保证其 citations 为空）。
    """
    out: list[CitationResolution] = []
    for item in items:
        if item.expected != "answer":
            continue
        for index, citation in enumerate(item.citations):
            page = pages.get((citation.doc_id, citation.pdf_page), [])
            resolution = resolve_quote(citation.quote, [(c.chunk_id, c.text) for c in page])
            out.append(CitationResolution(
                question_id=item.id, citation_index=index, citation=citation,
                section_exact_match=any(c.section == citation.section for c in page),
                resolution=resolution,
            ))
    return out


def build_mapping(items: Sequence[EvalItem], resolutions: Sequence[CitationResolution],
                  corpus_ids: Sequence[str]) -> dict[str, list[str]]:
    """mapping[qid] = 该题全部 citation formal cover 的并集，按 corpus 顺序；键按评测集顺序。

    输入假设: 全部 resolution 都是 L1/L2（调用方先做 fail-closed 判断）。
    """
    position = {cid: i for i, cid in enumerate(corpus_ids)}
    union: dict[str, set[str]] = {item.id: set() for item in items if item.expected == "answer"}
    for r in resolutions:
        union[r.question_id].update(r.resolution.formal_chunk_ids)
    return {qid: sorted(ids, key=position.__getitem__) for qid, ids in union.items()}


def identity_map(testset_path: str, testset_sha: str, corpus_sha: str,
                 mapping: dict[str, list[str]]) -> GoldChunkMap:
    """用契约 helper 与权威 builder 构造 GoldChunkMap；本函数不持有任何身份值。"""
    return GoldChunkMap(
        testset_version=testset_version_from_path(testset_path),
        testset_sha256=testset_sha,
        corpus_chunks_sha256=corpus_sha,
        corpus_builder_name=builder_identity.CORPUS_BUILDER_NAME,
        construction_rules_sha256=builder_identity.construction_rules_identity(),
        chunker_config=builder_identity.effective_chunker_config_identity(),
        contracts_version=contracts.CONTRACTS_VERSION,
        mapping=mapping,
        gold_chunk_map_semantics_version=contracts.GOLD_CHUNK_MAP_SEMANTICS_VERSION,
    )


# ==============================================================================
# 输出
# ==============================================================================

def _bool(value: bool) -> str:
    return CSV_TRUE if value else CSV_FALSE


def write_report(resolutions: Sequence[CitationResolution], path: str) -> None:
    """按 contracts.GOLD_CHUNK_MAP_REPORT_COLUMNS 写 report.csv（UTF-8，"\\n" 换行，逐字节确定）。"""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(contracts.GOLD_CHUNK_MAP_REPORT_COLUMNS)
        for r in resolutions:
            res = r.resolution
            fragments_json = json.dumps(
                [{"index": m.index, "text": m.text, "length": len(m.text),
                  "sole_match_eligible": m.sole_match_eligible, "candidate_chunk_ids": list(m.candidate_chunk_ids)}
                 for m in res.fragments],
                ensure_ascii=False, separators=(",", ":"),
            )
            writer.writerow([
                r.question_id, r.citation_index, r.citation.doc_id, r.citation.section, r.citation.pdf_page,
                _bool(r.section_exact_match), len(res.fragments), res.level, contracts.MATCH_LEVEL_REASON[res.level],
                CHUNK_ID_SEPARATOR.join(res.formal_chunk_ids), CHUNK_ID_SEPARATOR.join(res.candidate_chunk_ids),
                _bool(res.level not in contracts.FORMAL_MATCH_LEVELS), fragments_json,
            ])


def _refuse_existing(path: str) -> None:
    """输出文件已存在即拒绝运行：避免旧的"已接受映射"与新的失败 report 并存。"""
    if os.path.exists(path):
        raise ResolverInputError(f"输出文件已存在，拒绝覆盖（请换用新的 --out-dir 或先人工移除）: {path}")


# ==============================================================================
# CLI
# ==============================================================================

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """四个必填参数；不接受缩写，不接受遗留的 --out-testset。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("--chunks", required=True, help="冻结语料 chunks.jsonl")
    parser.add_argument("--testset", required=True, help="评测集 testset_v<MAJOR>_<MINOR>.jsonl（只读）")
    parser.add_argument("--corpus-sha", required=True, help="语料 sha256 期望值断言（8 位或 64 位）")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    return parser.parse_args(argv)


def run(chunks_path: str, testset_path: str, asserted_corpus_sha: str, out_dir: str) -> int:
    """执行一次解析。返回退出码（0 或 EXIT_MAP_NOT_ACCEPTED）；输入/契约错误抛异常。"""
    testset_sha_before = file_sha256(testset_path)
    corpus_sha = file_sha256(chunks_path)
    check_corpus_sha_assertion(asserted_corpus_sha, corpus_sha)

    corpus_ids, pages = load_corpus(chunks_path)
    items = load_testset(testset_path)
    resolutions = resolve_all(items, pages)
    unresolved = [r for r in resolutions if r.resolution.level not in contracts.FORMAL_MATCH_LEVELS]

    naming = identity_map(testset_path, testset_sha_before, corpus_sha, {})
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, naming.report_filename())
    map_path = os.path.join(out_dir, naming.filename())
    _refuse_existing(report_path)
    _refuse_existing(map_path)

    write_report(resolutions, report_path)
    _print_summary(items, resolutions)

    if file_sha256(testset_path) != testset_sha_before:
        raise ResolverInputError("评测集在运行期间被修改")
    if unresolved:
        print(f"MAP NOT ACCEPTED: {len(unresolved)} 条 answer citation 未解析为 L1/L2；只写 report: {report_path}")
        for r in unresolved:
            print(f"  {r.question_id}#{r.citation_index} {r.citation.doc_id} p{r.citation.pdf_page} "
                  f"{r.resolution.level} {contracts.MATCH_LEVEL_REASON[r.resolution.level]}")
        return EXIT_MAP_NOT_ACCEPTED

    gold_map = identity_map(testset_path, testset_sha_before, corpus_sha,
                            build_mapping(items, resolutions, corpus_ids))
    validate_gold_chunk_map(
        gold_map, items, corpus_ids,
        {(r.question_id, r.citation_index): (r.resolution.level, r.resolution.formal_chunk_ids) for r in resolutions},
        current_corpus_chunks_sha256=corpus_sha,
        builder=builder_identity,
    )
    with open(map_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(serialize_gold_chunk_map(gold_map))
    print(f"wrote {map_path}")
    print(f"wrote {report_path}")
    return 0


def _print_summary(items: Sequence[EvalItem], resolutions: Sequence[CitationResolution]) -> None:
    """打印题数、各级别条数；只打到 stdout，不进任何输出文件。"""
    answer = sum(1 for i in items if i.expected == "answer")
    print(f"questions={len(items)} answer={answer} refuse={len(items) - answer} citations={len(resolutions)}")
    for level in contracts.MatchLevel.__args__:
        print(f"  {level:<9} {sum(1 for r in resolutions if r.resolution.level == level)}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return run(args.chunks, args.testset, args.corpus_sha, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
