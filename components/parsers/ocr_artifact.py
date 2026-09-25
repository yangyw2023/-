"""OCR artifact identity、冻结配置与 candidate/accepted 存储（Phase B Hybrid C）。

职责边界（Design Freeze §6 / §8 / §13 / §14）:
  - 本模块【不执行 OCR】、【不解析 PDF】、【不做任何页面状态判定】。
  - 它只负责: 冻结 OCR baseline configuration、算 cache identity、
    写 candidate artifact、做 acceptance、校验 digest、读取 accepted artifact。
  - parser/build 只能通过 load_accepted() 消费 accepted artifact；
    本模块【不提供】任何触发 OCR 的入口。

命名约定（Design Freeze §8.1，不得违反）:
  - `source_hash` = immutable 源 PDF 的 sha256，是唯一 persisted 字段名。
    `source_pdf_sha256` 只是公式里的可读别名，不落盘。
  - `ocr_artifact_sha256` = accepted artifact 文件自身的 sha256，与 source_hash 绝不混用。

抛出:
  - OcrArtifactError —— 身份不一致、digest 不匹配、试图覆盖 accepted artifact、
    读取不存在的 accepted artifact、artifact 结构不合法。
    绝不返回 None / 空 dict 把失败藏起来。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

# ==============================================================================
# 冻结的 OCR baseline configuration（§2：在查看任何 OCR 输出之前写下）
# ==============================================================================

OCR_ARTIFACT_SCHEMA_VERSION: int = 1

# 光栅化：与 A.1 视觉调查同一条像素路径（pdftoppm -gray → PGM），但 DPI 独立选择。
# 300 dpi 是 Tesseract 文档对 OCR 输入的通用推荐下限；A.1 的 40/100/150 dpi 只用于
# 视觉诊断统计，不适合作为 OCR 输入。本值在看任何 OCR 输出之前固定。
RASTERIZER: str = "pdftoppm"
RASTER_DPI: int = 300
RASTER_FORMAT: str = "pgm"      # -gray 输出 P5 PGM；无压缩、无时间戳，逐字节可比
RASTER_GRAY: bool = True

# OCR 引擎参数：
#   -l eng      当前 tessdata 只有 eng / osd；语料为英文手册（CORPUS_LANG_DEFAULT="en"）
#   --psm 3     全自动版面分割、不做 OSD。不使用 OSD 的理由：OSD 会引入自动旋转，
#               而 Design Freeze §13 要求光栅化不得改变页面语义；不使用即不引入 osd.traineddata。
#   --oem 1     显式固定 LSTM-only，避免依赖 "看当前构建里有什么" 的默认值 3。
#   txt tsv     一次调用产出两份输出：txt 为 body 来源，tsv 仅用于置信度统计（只进审计）。
OCR_ENGINE: str = "tesseract"
OCR_LANG: str = "eng"
OCR_PSM: int = 3
OCR_OEM: int = 1
OCR_OUTPUTS: tuple[str, ...] = ("txt", "tsv")
# 单线程执行：降低多线程带来的复现差异风险。属冻结参数的一部分，不是事后调参。
OCR_ENV: dict[str, str] = {"OMP_THREAD_LIMIT": "1"}

# 文本归一化策略（最小化，不改变列对齐）：
#   1. CRLF/CR → LF
#   2. 去掉 U+000C form feed
#   3. 每行去掉行尾空白（行内空格保持原样 —— 页眉解析依赖 >=2 空格的列间距）
#   4. 去掉文件末尾多余空行，保证以单个 \n 结尾
TEXT_NORMALIZATION: str = "crlf_to_lf; drop_form_feed; rstrip_each_line; single_trailing_newline"

_CR_RE = re.compile(r"\r\n?")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.M)


def normalize_ocr_text(raw: str) -> str:
    """按 TEXT_NORMALIZATION 归一化 OCR 原始文本。纯函数，无副作用。"""
    text = _CR_RE.sub("\n", raw).replace("\f", "")
    text = _TRAILING_WS_RE.sub("", text)
    return text.rstrip("\n") + "\n" if text.strip() else ""


def ocr_argv(image_path: str, out_base: str, tessdata_dir: str) -> list[str]:
    """冻结的 CLI 模板。参数顺序固定，进入 ocr_params_digest。"""
    return [
        OCR_ENGINE, image_path, out_base,
        "--tessdata-dir", tessdata_dir,
        "-l", OCR_LANG,
        "--psm", str(OCR_PSM),
        "--oem", str(OCR_OEM),
        *OCR_OUTPUTS,
    ]


def ocr_params_canonical() -> str:
    """OCR 参数的 canonical 表示。只含影响输出字节的量；不含路径与机器名。"""
    return json.dumps(
        {
            "schema_version": OCR_ARTIFACT_SCHEMA_VERSION,
            "raster": {"rasterizer": RASTERIZER, "dpi": RASTER_DPI,
                       "format": RASTER_FORMAT, "gray": RASTER_GRAY},
            "engine": {"name": OCR_ENGINE, "lang": OCR_LANG, "psm": OCR_PSM,
                       "oem": OCR_OEM, "outputs": list(OCR_OUTPUTS)},
            "env": dict(sorted(OCR_ENV.items())),
            "text_normalization": TEXT_NORMALIZATION,
        },
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    )


def ocr_params_digest() -> str:
    """冻结参数集合的 sha256，进入 cache identity。"""
    return hashlib.sha256(ocr_params_canonical().encode("utf-8")).hexdigest()


# ==============================================================================
# 存储布局
# ==============================================================================

CANDIDATE_DIRNAME: str = "candidates"
ACCEPTED_DIRNAME: str = "accepted"
ACCEPTED_INDEX_FILENAME: str = "index.jsonl"
REPRODUCIBILITY_LOG_FILENAME: str = "reproducibility_events.jsonl"

# artifact JSON 的序列化口径（逐字节确定）。
_JSON_KW: dict[str, Any] = {"sort_keys": True, "ensure_ascii": True, "separators": (",", ":")}

ARTIFACT_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version", "source_hash", "pdf_page",
    "rasterizer", "rasterizer_version", "raster_dpi", "raster_sha256",
    "ocr_engine", "ocr_engine_version", "langpack", "langpack_identity_digest",
    "ocr_params_digest", "text", "text_raw_sha256", "confidence_stats",
)


class OcrArtifactError(RuntimeError):
    """artifact 身份 / digest / 不可变性被破坏。"""


@dataclass(frozen=True)
class CacheIdentity:
    """Design Freeze §8.1 冻结的九元组 cache identity。

    `source_pdf_sha256 := source_hash`（别名，不落盘）。
    """

    source_hash: str
    pdf_page: int
    rasterizer: str
    rasterizer_version: str
    raster_dpi: int
    ocr_engine: str
    ocr_engine_version: str
    langpack_identity_digest: str
    ocr_params_digest: str

    def canonical(self) -> str:
        return json.dumps(self.__dict__, **_JSON_KW)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


def build_cache_identity(source_hash: str, pdf_page: int, rasterizer_version: str,
                         ocr_engine_version: str, langpack_identity_digest: str) -> CacheIdentity:
    """用冻结配置 + 运行期探测到的工具版本组装 cache identity。"""
    if pdf_page < 1:
        raise OcrArtifactError(f"pdf_page 必须从 1 开始: {pdf_page}")
    return CacheIdentity(
        source_hash=source_hash, pdf_page=pdf_page,
        rasterizer=RASTERIZER, rasterizer_version=rasterizer_version, raster_dpi=RASTER_DPI,
        ocr_engine=OCR_ENGINE, ocr_engine_version=ocr_engine_version,
        langpack_identity_digest=langpack_identity_digest, ocr_params_digest=ocr_params_digest(),
    )


def serialize_artifact(payload: dict[str, Any]) -> bytes:
    """artifact → 逐字节确定的 JSON bytes。抛出 OcrArtifactError —— 缺必需字段。"""
    missing = [f for f in ARTIFACT_REQUIRED_FIELDS if f not in payload]
    if missing:
        raise OcrArtifactError(f"artifact 缺字段: {missing}")
    return (json.dumps(payload, **_JSON_KW) + "\n").encode("utf-8")


def artifact_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class OcrArtifactStore:
    """candidate / accepted 两段式 artifact 存储。

    硬规则（Design Freeze §8.2）:
      1. 无 accepted 时才允许创建 candidate；
      2. candidate 未 acceptance 前 parser 不得消费（本类不提供读 candidate 的解析入口）；
      3. accepted artifact immutable；
      4. 同 cache key 已有 accepted → 不得静默覆盖；
      5. 同 cache key 新字节 → 记 reproducibility event，不自动替换；
      6. 本类不提供任何执行 OCR 的方法；
      7. digest mismatch → 抛异常（调用方据此 FAIL_INGEST）。
    """

    def __init__(self, root: str) -> None:
        self.root = root
        self._index_path = os.path.join(root, ACCEPTED_DIRNAME, ACCEPTED_INDEX_FILENAME)
        self._index: dict[str, dict[str, Any]] = {}
        if os.path.isfile(self._index_path):
            with open(self._index_path, encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        row = json.loads(line)
                        self._index[row["cache_key_digest"]] = row

    # ---- 路径 ----
    def _candidate_path(self, identity: CacheIdentity, sha: str) -> str:
        return os.path.join(self.root, CANDIDATE_DIRNAME, identity.source_hash,
                            f"p{identity.pdf_page:04d}-{sha[:16]}.json")

    def _accepted_path(self, identity: CacheIdentity, sha: str) -> str:
        return os.path.join(self.root, ACCEPTED_DIRNAME, identity.source_hash,
                            f"p{identity.pdf_page:04d}-{sha[:16]}.json")

    # ---- 查询 ----
    def accepted_entry(self, identity: CacheIdentity) -> dict[str, Any] | None:
        """返回该 cache key 的 accepted 记录；没有则 None（这是"确实没有"，不是错误）。"""
        return self._index.get(identity.digest())

    def has_accepted(self, identity: CacheIdentity) -> bool:
        return identity.digest() in self._index

    # ---- 写入 ----
    def write_candidate(self, identity: CacheIdentity, payload: dict[str, Any]) -> tuple[str, str]:
        """写 candidate artifact，返回 (path, sha256)。

        抛出 OcrArtifactError —— payload 的 source_hash/pdf_page 与 identity 不一致。
        """
        if payload["source_hash"] != identity.source_hash or int(payload["pdf_page"]) != identity.pdf_page:
            raise OcrArtifactError(
                f"candidate 自述身份与 cache identity 不一致: "
                f"{payload['source_hash']}:{payload['pdf_page']} vs {identity.source_hash}:{identity.pdf_page}"
            )
        data = serialize_artifact(payload)
        sha = artifact_sha256(data)
        path = self._candidate_path(identity, sha)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, "rb") as handle:
                if handle.read() != data:
                    raise OcrArtifactError(f"candidate 路径已存在且内容不同: {path}")
        else:
            with open(path, "wb") as handle:
                handle.write(data)
        return path, sha

    def accept(self, identity: CacheIdentity, candidate_path: str, candidate_sha: str) -> dict[str, Any]:
        """把 candidate 提升为 accepted artifact。

        返回 accepted index 记录。
        抛出 OcrArtifactError —— 同 cache key 已有【不同 digest】的 accepted artifact（规则 4/5），
        或 candidate 文件 digest 与声明不符。
        """
        with open(candidate_path, "rb") as handle:
            data = handle.read()
        if artifact_sha256(data) != candidate_sha:
            raise OcrArtifactError(f"candidate digest 不匹配: {candidate_path}")

        existing = self.accepted_entry(identity)
        if existing is not None:
            if existing["ocr_artifact_sha256"] == candidate_sha:
                return existing  # 幂等：同 key 同字节，已 accepted
            raise OcrArtifactError(
                f"同 cache key 已存在不同 digest 的 accepted artifact，拒绝静默覆盖: "
                f"{identity.source_hash}:p{identity.pdf_page} "
                f"accepted={existing['ocr_artifact_sha256'][:16]} new={candidate_sha[:16]}"
            )

        path = self._accepted_path(identity, candidate_sha)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            raise OcrArtifactError(f"accepted artifact 路径已存在（immutable，不覆盖）: {path}")
        with open(path, "wb") as handle:
            handle.write(data)
        os.chmod(path, 0o444)  # 结构上阻止就地改写

        row = {
            "cache_key_digest": identity.digest(),
            "cache_key": json.loads(identity.canonical()),
            "source_hash": identity.source_hash,
            "pdf_page": identity.pdf_page,
            "artifact_path": os.path.relpath(path, self.root),
            "ocr_artifact_sha256": candidate_sha,
        }
        self._index[identity.digest()] = row
        self._rewrite_index()
        return row

    def record_reproducibility_event(self, identity: CacheIdentity, accepted_sha: str,
                                     new_sha: str, note: str) -> None:
        """同 cache key 产出不同字节时的显式留痕（规则 5）。不改 accepted artifact。"""
        path = os.path.join(self.root, REPRODUCIBILITY_LOG_FILENAME)
        os.makedirs(self.root, exist_ok=True)
        row = {
            "cache_key_digest": identity.digest(), "source_hash": identity.source_hash,
            "pdf_page": identity.pdf_page, "accepted_ocr_artifact_sha256": accepted_sha,
            "new_candidate_sha256": new_sha, "note": note,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, **_JSON_KW) + "\n")

    def _rewrite_index(self) -> None:
        os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
        rows = sorted(self._index.values(), key=lambda r: (r["source_hash"], int(r["pdf_page"])))
        with open(self._index_path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, **_JSON_KW) + "\n")

    # ---- 读取（parser 唯一入口）----
    def load_accepted(self, identity: CacheIdentity) -> dict[str, Any]:
        """读取 accepted artifact 并做双向身份 + digest 校验。

        抛出 OcrArtifactError —— 无 accepted 记录、文件缺失、digest 不匹配、
        artifact 自述的 source_hash/pdf_page 与请求不一致。
        调用方（parser/build）必须把该异常当作 FAIL_INGEST，不得降级。
        """
        entry = self.accepted_entry(identity)
        if entry is None:
            raise OcrArtifactError(
                f"无 accepted artifact: {identity.source_hash}:p{identity.pdf_page}"
                f"（cache_key={identity.digest()[:16]}）"
            )
        path = os.path.join(self.root, entry["artifact_path"])
        if not os.path.isfile(path):
            raise OcrArtifactError(f"accepted artifact 文件缺失: {path}")
        with open(path, "rb") as handle:
            data = handle.read()
        sha = artifact_sha256(data)
        if sha != entry["ocr_artifact_sha256"]:
            raise OcrArtifactError(
                f"accepted artifact digest 不匹配: {path} 实际={sha[:16]} 索引={entry['ocr_artifact_sha256'][:16]}"
            )
        payload = json.loads(data.decode("utf-8"))
        if payload["source_hash"] != identity.source_hash or int(payload["pdf_page"]) != identity.pdf_page:
            raise OcrArtifactError(
                f"artifact 自述身份与请求不一致: {payload['source_hash']}:{payload['pdf_page']} "
                f"vs {identity.source_hash}:{identity.pdf_page}"
            )
        payload["ocr_artifact_sha256"] = sha
        return payload

    def iter_accepted(self) -> Iterator[dict[str, Any]]:
        yield from sorted(self._index.values(), key=lambda r: (r["source_hash"], int(r["pdf_page"])))


def file_sha256(path: str, block: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(block), b""):
            digest.update(chunk)
    return digest.hexdigest()


def confidence_stats(tsv_text: str) -> dict[str, float | int]:
    """从 tesseract TSV 输出算词级置信度统计。

    ⚠️ 只进审计，不参与任何状态判定（Design Freeze §2.4：引擎置信度不是 ground truth）。
    """
    confs: list[float] = []
    for line in tsv_text.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 12 and cols[11].strip() and cols[10] not in ("", "conf"):
            try:
                conf = float(cols[10])
            except ValueError:
                continue
            if conf >= 0:
                confs.append(conf)
    if not confs:
        return {"word_count": 0, "mean_conf": -1.0, "min_conf": -1.0, "p05_conf": -1.0}
    ordered = sorted(confs)
    p05 = ordered[max(0, min(len(ordered) - 1, round(0.05 * (len(ordered) - 1))))]
    return {
        "word_count": len(confs),
        "mean_conf": round(sum(confs) / len(confs), 3),
        "min_conf": round(ordered[0], 3),
        "p05_conf": round(p05, 3),
    }
