#!/usr/bin/env python3
"""Backfill ``gold_chunk_ids`` on the evaluation set by resolving each citation
onto concrete corpus chunk ids.

One-off data backfill: reads a frozen evaluation set whose ``gold_chunk_ids`` are
all empty, resolves the citations of every ``expected == "answer"`` question
against a parsed corpus, and writes a resolved copy plus a per-citation audit
report. Nothing is written back over the inputs.

Matching contract
-----------------
A citation is resolved by trying four strategies in the order below. The first
strategy that yields at least one chunk wins; its label is recorded as the
citation's ``match_level`` and no later strategy is tried. Comparison is done on
whitespace-normalised text on BOTH sides (runs of whitespace folded to a single
space, ends stripped); no other normalisation is applied, so punctuation, case
and typographic characters must match the corpus byte-for-byte.

    L1  same ``doc_id``, same ``pdf_page``, chunk text contains the whole quote.
    L2  same ``doc_id``, ``pdf_page`` within +/-PAGE_WINDOW, chunk text contains
        the whole quote. Rationale: chunking may spill a page into a neighbour.
    L3  same ``doc_id``, ``pdf_page`` within +/-PAGE_WINDOW, chunk text contains
        the quote's first FUZZY_PREFIX_CHARS characters.
    L4  same ``doc_id``, same ``pdf_page``, every chunk on that page. This is a
        fallback, not a match: it is flagged ``needs_review``.
    FAIL  none of the above produced a chunk, i.e. the corpus holds no chunk at
        that ``(doc_id, pdf_page)`` at all. A FAIL is a signal, not a nuisance:
        it means either the quote or the page in the evaluation set is wrong, or
        the parser dropped that page. It is never silently swallowed.

Known limitation, deliberately not worked around: quotes in which fragments are
joined by an ellipsis ("A ... B") are matched literally, so L1/L2 cannot hit them
and their first FUZZY_PREFIX_CHARS characters usually still span the ellipsis, so
L3 cannot either. Such citations fall through to L4 or FAIL by design.

Failure policy
--------------
Errors are raised, never absorbed. Missing files, malformed JSON, missing or
ill-typed fields, duplicate chunk ids and empty quotes all abort the run. An
unresolvable citation is NOT an error: it is recorded as FAIL and reported.
"""

import argparse
import csv
import json
import re
import sys
from typing import Dict, Iterator, List, NamedTuple, Sequence, Tuple

# --- Matching parameters -----------------------------------------------------
# Half-width of the page window used by L2/L3, in pages. 1 == look at p-1, p, p+1.
PAGE_WINDOW = 1
# Number of leading characters of the normalised quote used as the L3 probe.
FUZZY_PREFIX_CHARS = 40

# --- Report formatting -------------------------------------------------------
# Number of leading characters of the normalised quote written to the report.
QUOTE_HEAD_CHARS = 60
# Separator packing several chunk ids into one CSV cell (comma is the delimiter).
CHUNK_ID_SEPARATOR = ";"
REPORT_COLUMNS = (
    "question_id",
    "doc_id",
    "section",
    "pdf_page",
    "quote_head",
    "match_level",
    "matched_chunk_ids",
    "n_matches",
    "needs_review",
)

# --- Vocabulary --------------------------------------------------------------
EXPECTED_ANSWER = "answer"
LEVEL_L1 = "L1"
LEVEL_L2 = "L2"
LEVEL_L3 = "L3"
LEVEL_L4 = "L4"
LEVEL_FAIL = "FAIL"
# Order used for the report and the terminal summary.
MATCH_LEVELS = (LEVEL_L1, LEVEL_L2, LEVEL_L3, LEVEL_L4, LEVEL_FAIL)
# The single level that means "a human must look at this".
NEEDS_REVIEW_LEVELS = frozenset({LEVEL_L4})

REQUIRED_CHUNK_FIELDS = ("id", "text", "doc_id", "pdf_page")
REQUIRED_QUESTION_FIELDS = ("id", "expected", "citations", "gold_chunk_ids")
REQUIRED_CITATION_FIELDS = ("doc_id", "section", "pdf_page", "quote")

_WHITESPACE_RUN = re.compile(r"\s+")


class GoldChunkResolutionError(Exception):
    """Raised when an input violates the contract this script relies on.

    Signals bad data, not a bad match: an unresolvable citation yields a FAIL row
    instead of this exception.
    """


class IndexedChunk(NamedTuple):
    """A corpus chunk reduced to what matching needs.

    ``norm_text`` is the chunk's text after whitespace normalisation; it is
    precomputed so the same chunk is not renormalised once per citation.
    """

    chunk_id: str
    norm_text: str


class CitationResolution(NamedTuple):
    """The outcome of resolving one citation.

    ``match_level`` is one of MATCH_LEVELS. ``chunk_ids`` is empty if and only if
    ``match_level`` is FAIL, and is ordered as the chunks appear in the corpus
    file. ``needs_review`` is True exactly for the levels in NEEDS_REVIEW_LEVELS.
    """

    question_id: str
    doc_id: str
    section: str
    pdf_page: int
    norm_quote: str
    match_level: str
    chunk_ids: Tuple[str, ...]

    @property
    def needs_review(self) -> bool:
        return self.match_level in NEEDS_REVIEW_LEVELS


# Chunks grouped by their locating pair, preserving corpus order within a page.
PageIndex = Dict[Tuple[str, int], List[IndexedChunk]]


def normalize_whitespace(text: str) -> str:
    """Fold every run of whitespace to a single space and strip the ends.

    The only normalisation applied before comparing quotes to chunk text; callers
    must not assume case, punctuation or typographic characters are touched.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def iter_jsonl(path: str) -> Iterator[Tuple[int, dict]]:
    """Yield ``(line_number, object)`` for each non-blank line of a JSONL file.

    Line numbers are 1-based so they can be quoted back to a human editing the
    file. Blank lines are skipped as insignificant formatting.

    Raises:
        OSError: the file cannot be opened or read.
        json.JSONDecodeError: a line is not valid JSON.
        GoldChunkResolutionError: a line is valid JSON but not a JSON object.
    """
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise GoldChunkResolutionError(
                    f"{path}:{line_no}: expected a JSON object, got {type(record).__name__}"
                )
            yield line_no, record


def _require_fields(record: dict, fields: Sequence[str], where: str) -> None:
    """Assert that every name in ``fields`` is a key of ``record``.

    Raises:
        GoldChunkResolutionError: naming ``where`` and every missing key.
    """
    missing = [name for name in fields if name not in record]
    if missing:
        raise GoldChunkResolutionError(f"{where}: missing required field(s): {', '.join(missing)}")


def load_page_index(chunks_path: str) -> Tuple[PageIndex, int]:
    """Read the corpus and group its chunks by ``(doc_id, pdf_page)``.

    Returns the index and the number of chunks loaded. Chunk ids are required to
    be unique corpus-wide, since a duplicate would make a resolved
    ``gold_chunk_ids`` ambiguous.

    Raises:
        OSError, json.JSONDecodeError: see :func:`iter_jsonl`.
        GoldChunkResolutionError: a chunk lacks a required field, its
            ``pdf_page`` is not an int, or its ``id`` is not unique.
    """
    index: PageIndex = {}
    seen_ids: Dict[str, int] = {}
    for line_no, chunk in iter_jsonl(chunks_path):
        where = f"{chunks_path}:{line_no}"
        _require_fields(chunk, REQUIRED_CHUNK_FIELDS, where)
        chunk_id = str(chunk["id"])
        if chunk_id in seen_ids:
            raise GoldChunkResolutionError(
                f"{where}: duplicate chunk id {chunk_id!r}, first seen on line {seen_ids[chunk_id]}"
            )
        seen_ids[chunk_id] = line_no
        pdf_page = chunk["pdf_page"]
        # bool is an int subclass; a boolean page is a contract violation, not a page.
        if not isinstance(pdf_page, int) or isinstance(pdf_page, bool):
            raise GoldChunkResolutionError(
                f"{where}: pdf_page must be an int, got {type(pdf_page).__name__}"
            )
        key = (str(chunk["doc_id"]), pdf_page)
        index.setdefault(key, []).append(
            IndexedChunk(chunk_id=chunk_id, norm_text=normalize_whitespace(str(chunk["text"])))
        )
    return index, len(seen_ids)


def load_questions(testset_path: str) -> List[dict]:
    """Read the evaluation set, preserving each record's fields and their order.

    Raises:
        OSError, json.JSONDecodeError: see :func:`iter_jsonl`.
        GoldChunkResolutionError: a question or one of its citations lacks a
            required field, ``citations`` is not a list, or a citation's
            ``pdf_page`` is not an int / its ``quote`` is blank. A blank quote is
            rejected because it would match every chunk on the page.
    """
    questions: List[dict] = []
    for line_no, question in iter_jsonl(testset_path):
        where = f"{testset_path}:{line_no}"
        _require_fields(question, REQUIRED_QUESTION_FIELDS, where)
        if not isinstance(question["citations"], list):
            raise GoldChunkResolutionError(
                f"{where}: citations must be a list, got {type(question['citations']).__name__}"
            )
        for position, citation in enumerate(question["citations"]):
            cite_where = f"{where}: question {question['id']!r} citation #{position}"
            if not isinstance(citation, dict):
                raise GoldChunkResolutionError(
                    f"{cite_where}: expected a JSON object, got {type(citation).__name__}"
                )
            _require_fields(citation, REQUIRED_CITATION_FIELDS, cite_where)
            pdf_page = citation["pdf_page"]
            if not isinstance(pdf_page, int) or isinstance(pdf_page, bool):
                raise GoldChunkResolutionError(
                    f"{cite_where}: pdf_page must be an int, got {type(pdf_page).__name__}"
                )
            if not normalize_whitespace(str(citation["quote"])):
                raise GoldChunkResolutionError(f"{cite_where}: quote is empty")
        questions.append(question)
    return questions


def _chunks_on_pages(index: PageIndex, doc_id: str, pages: Sequence[int]) -> List[IndexedChunk]:
    """Collect the chunks of ``doc_id`` on ``pages``, in corpus order per page.

    Pages absent from the corpus contribute nothing; an empty result means the
    document has no chunk on any of those pages.
    """
    collected: List[IndexedChunk] = []
    for page in pages:
        collected.extend(index.get((doc_id, page), ()))
    return collected


def resolve_citation(question_id: str, citation: dict, index: PageIndex) -> CitationResolution:
    """Resolve one citation to chunk ids by trying L1, L2, L3 then L4 in order.

    Assumes ``citation`` has passed the validation in :func:`load_questions`.
    Never raises for an unresolvable citation: that is returned as a FAIL
    resolution carrying no chunk ids.
    """
    doc_id = str(citation["doc_id"])
    pdf_page = citation["pdf_page"]
    norm_quote = normalize_whitespace(str(citation["quote"]))
    same_page = _chunks_on_pages(index, doc_id, (pdf_page,))
    window = range(pdf_page - PAGE_WINDOW, pdf_page + PAGE_WINDOW + 1)

    exact = [c for c in same_page if norm_quote in c.norm_text]
    if exact:
        level, matches = LEVEL_L1, exact
    else:
        neighbours = _chunks_on_pages(index, doc_id, window)
        spilled = [c for c in neighbours if norm_quote in c.norm_text]
        if spilled:
            level, matches = LEVEL_L2, spilled
        else:
            prefix = norm_quote[:FUZZY_PREFIX_CHARS]
            fuzzy = [c for c in neighbours if prefix in c.norm_text]
            if fuzzy:
                level, matches = LEVEL_L3, fuzzy
            elif same_page:
                level, matches = LEVEL_L4, same_page
            else:
                level, matches = LEVEL_FAIL, []

    return CitationResolution(
        question_id=question_id,
        doc_id=doc_id,
        section=str(citation["section"]),
        pdf_page=pdf_page,
        norm_quote=norm_quote,
        match_level=level,
        chunk_ids=tuple(c.chunk_id for c in matches),
    )


def fill_gold_chunk_ids(questions: List[dict], index: PageIndex) -> List[CitationResolution]:
    """Resolve every citation of every ``expected == "answer"`` question.

    Mutates each such question in place, replacing ``gold_chunk_ids`` with the
    union of its citations' matches, de-duplicated and kept in first-seen order.
    Questions expecting a refusal are left untouched — including their citations,
    which document a distractor rather than an answer location.

    Returns one resolution per citation processed, in evaluation-set order.
    """
    resolutions: List[CitationResolution] = []
    for question in questions:
        if question["expected"] != EXPECTED_ANSWER:
            continue
        gold_ids: List[str] = []
        for citation in question["citations"]:
            resolution = resolve_citation(str(question["id"]), citation, index)
            resolutions.append(resolution)
            for chunk_id in resolution.chunk_ids:
                if chunk_id not in gold_ids:
                    gold_ids.append(chunk_id)
        question["gold_chunk_ids"] = gold_ids
    return resolutions


def write_resolved_testset(questions: Sequence[dict], out_path: str) -> None:
    """Write the questions back as JSONL, one record per line.

    Field order and every field other than ``gold_chunk_ids`` are carried over
    untouched; non-ASCII text is written as-is rather than escaped.

    Raises:
        OSError: the destination cannot be written.
    """
    with open(out_path, "w", encoding="utf-8") as handle:
        for question in questions:
            handle.write(json.dumps(question, ensure_ascii=False) + "\n")


def write_report(resolutions: Sequence[CitationResolution], out_path: str) -> None:
    """Write one CSV row per resolved citation, with REPORT_COLUMNS as header.

    ``quote_head`` is the normalised quote truncated to QUOTE_HEAD_CHARS, so a
    reader can eyeball what was searched for; it is not the matching input.

    Raises:
        OSError: the destination cannot be written.
    """
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for r in resolutions:
            writer.writerow(
                [
                    r.question_id,
                    r.doc_id,
                    r.section,
                    r.pdf_page,
                    r.norm_quote[:QUOTE_HEAD_CHARS],
                    r.match_level,
                    CHUNK_ID_SEPARATOR.join(r.chunk_ids),
                    len(r.chunk_ids),
                    r.needs_review,
                ]
            )


def print_summary(resolutions: Sequence[CitationResolution]) -> None:
    """Print per-level counts, the needs-review count, and every failing citation.

    Failures are listed individually and by question id: a FAIL means the quote,
    the page or the parser is wrong, and it is the finding this script exists to
    surface.
    """
    total = len(resolutions)
    print(f"citations resolved: {total}")
    for level in MATCH_LEVELS:
        count = sum(1 for r in resolutions if r.match_level == level)
        share = (count / total * 100) if total else 0.0
        print(f"  {level:<4} {count:>4}  ({share:5.1f}%)")
    print(f"needs_review: {sum(1 for r in resolutions if r.needs_review)}")

    failures = [r for r in resolutions if r.match_level == LEVEL_FAIL]
    print(f"FAILED citations: {len(failures)}")
    if failures:
        failed_qids = []
        for r in failures:
            if r.question_id not in failed_qids:
                failed_qids.append(r.question_id)
        print(f"  failed question_id(s): {', '.join(failed_qids)}")
        for r in failures:
            print(f"    {r.question_id}  {r.doc_id} §{r.section} p.{r.pdf_page}  {r.norm_quote[:QUOTE_HEAD_CHARS]}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the four mandatory path arguments. Exits non-zero on bad usage."""
    parser = argparse.ArgumentParser(
        description="Resolve evaluation-set citations onto corpus chunk ids."
    )
    parser.add_argument("--chunks", required=True, help="input corpus JSONL")
    parser.add_argument("--testset", required=True, help="input evaluation set JSONL")
    parser.add_argument("--out-testset", required=True, help="output evaluation set JSONL")
    parser.add_argument("--out-report", required=True, help="output per-citation CSV report")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> None:
    """Run the backfill end to end and print the summary. Raises on bad input."""
    args = parse_args(argv)
    index, n_chunks = load_page_index(args.chunks)
    questions = load_questions(args.testset)
    print(f"loaded {n_chunks} chunks over {len(index)} (doc_id, pdf_page) pages from {args.chunks}")
    print(f"loaded {len(questions)} questions from {args.testset}")

    resolutions = fill_gold_chunk_ids(questions, index)
    write_resolved_testset(questions, args.out_testset)
    write_report(resolutions, args.out_report)

    answered = sum(1 for q in questions if q["expected"] == EXPECTED_ANSWER)
    print(f"questions with expected=={EXPECTED_ANSWER!r}: {answered}")
    print_summary(resolutions)
    print(f"wrote {args.out_testset}")
    print(f"wrote {args.out_report}")


if __name__ == "__main__":
    main(sys.argv[1:])
