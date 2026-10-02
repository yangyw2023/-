#!/usr/bin/env python3
"""OCR fallback Phase A.2 —— visual detector (V2) threshold validation，仅限 88 个 parser-dropped 页。

只读诊断脚本。不 OCR、不改 parser / corpus / contracts / Phase A 与 A.1 产物。

用法:
    python3 scripts/ocr_visual_threshold_validation.py \\
        --phase-a-csv experiments/ocr_survey/_page_signals.csv \\
        --visual-csv experiments/ocr_survey/_visual_page_signals.csv \\
        --a1-log experiments/ocr_survey/_visual_detector_analysis.log \\
        --pdf-dir "raw/KAIVA - Manuals" \\
        --corpus corpus/chunks.jsonl \\
        --out-csv experiments/ocr_survey/_visual_threshold_validation.csv \\
        --out-log experiments/ocr_survey/_visual_threshold_validation.log \\
        [--seed 20260917] [--prereg-only]

--prereg-only:
    只写 log 头（环境指纹）+ 预注册段（PREREGISTRATION），不读 review 标签、不渲染、不计算。
    用于在查看剩余页面之前冻结定义与判据。

标签来源（reviewer = claude_visual_review，不是独立人类 ground truth）:
    - A.1 已 review 的 dropped 页：读 --visual-csv 的 review_observation / review_dpi / review_note。
    - A.2 新 review 的 dropped 页：本文件 A2_REVIEW_LABELS 常量（可版本化）。
    两者重叠或 88 页中有页缺标签 → 抛异常。

失败语义:
    Phase A population ≠ 88、A.1 CSV 缺列、重渲染 PGM sha256 与 A.1 CSV 不一致、
    重算 F1 与 A.1 CSV 不一致、pdftoppm 失败 → 直接抛异常，不产出部分结果。

输出确定性:
    CSV 逐字节确定；log 除标记为【TIMING】的末段外逐字节确定。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts  # noqa: E402

# ==============================================================================
# 模块常量
# ==============================================================================

EXPECTED_CORPUS_SHA256: str = "8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa"
EXPECTED_CHUNK_COUNT: int = 3383
EXPECTED_POPULATION: int = 88
DEFAULT_SEED: int = 20260917

PDF_SUFFIX: str = ".pdf"
POPPLER_TIMEOUT_S: float = 120.0
HASH_READ_BLOCK_BYTES: int = 1 << 20
RATIO_DECIMALS: int = 6

DPIS: tuple[int, ...] = (40, 100)
GRAY_THRESHOLDS: tuple[int, ...] = (250, 245, 235)
# 与 A.1 完全一致的分区定义（scripts/ocr_visual_survey.py REGION_TOP_END / REGION_MIDDLE_END）。
REGION_TOP_END: float = 0.15
REGION_MIDDLE_END: float = 0.85

REVIEWER: str = "claude_visual_review"
LABELS: tuple[str, ...] = (
    "visual_business_content", "form_or_template", "mostly_header_footer",
    "cover_or_frontmatter", "blank_or_separator", "uncertain",
)
POSITIVE_LABELS: frozenset[str] = frozenset({"visual_business_content"})
NEGATIVE_LABELS: frozenset[str] = frozenset({"mostly_header_footer", "cover_or_frontmatter", "blank_or_separator"})
SET_POS: str = "POSITIVE_VISUAL_RECOVERY_CANDIDATE"
SET_NEG: str = "NEGATIVE_NON_CONTENT"
SET_FORM: str = "excluded_form_or_template"
SET_UNC: str = "excluded_uncertain"

# 验证分支切换点（用户规格 §5，预注册）。
NEG_MIN_FOR_HOLDOUT: int = 12
DEV_FRACTION_NUM: int = 2
DEV_FRACTION_DEN: int = 3

FEATURES: tuple[str, ...] = ("F1", "F2")
# 候选配置里固定的灰度阈值（预注册 P9；与 A.1 V3 检查所用 245 一致，选择先于结果）。
PRIMARY_GRAY: int = 245
MAX_CANDIDATES: int = 3
# CRM p.74 压力判据（预注册 P8）。
STRESS_DOC: str = "CRM"
STRESS_PAGE: int = 74
F2A_MARGIN_FACTOR: float = 2.0
F2A_MIN_CELLS: int = 4

# §11 调查边界观察用：A.1 备注指出的“原生正文 + 图像流程图”页，与 reviewer 从渲染图转录的图内标签。
BOUNDARY_DOC: str = "QMM"
BOUNDARY_PAGE: int = 110
BOUNDARY_PHRASES: tuple[str, ...] = (
    "Concur with parameters for change", "Identify risk assessment team",
    "Close out and Sign Off", "Replacement in kind",
)

V1_ALPHA_TOKEN_RATIO_MAX: float = 0.0  # Phase A B_alpha_token_ratio@t_recall，本轮不调

TIMING_MARKER: str = "==== 【TIMING】 非确定段：确定性比较时删除本行及其后全部内容 ===="

PREREGISTRATION: str = """\
==== PREREGISTRATION（查看剩余 50 页之前写下；之后不修改） ====
P1 population := Phase A _page_signals.csv 中 parser_body_chars < CHUNK_MIN_CHARS 的全部页；必须 = 88，否则抛异常。
P2 标签（只允许这 6 个）：
   visual_business_content: 页面视觉层包含可用于 RAG 的业务事实、程序、政策、流程、表格数据、技术结构、职责、
     数值、规则或其他实质知识，而 native body extraction 没有充分获得这些内容。
   form_or_template: 页面主要是待填写表单、重复评分界面、空模板或交互脚手架；可以存在文字与视觉内容，
     但“是否值得索引”属于后续 content policy，不能由 visual detector 决定。
   mostly_header_footer: 中部无实质业务正文，主要只有页眉、页脚、页码或装饰。
   cover_or_frontmatter: 封面、扉页或类似前置页面，不含值得进入 RAG 的主体业务知识。
   blank_or_separator: 视觉上为空白或仅承担分隔作用。
   uncertain: 当前 rendered page 不足以可靠判断。
P3 reviewer = claude_visual_review（Claude 查看 rendered page 的人工视觉观察；不是独立人类 ground truth）。
   A.1 已 review 的 38 页沿用 A.1 标签（A.1 也是 Claude 视觉观察，同一标注者类型）；剩余 50 页本轮 review，
   优先 100 dpi PNG，不可读时 150 dpi；不 OCR。review 时不查看该页的 F1/F2 数值。
P4 集合：POSITIVE = visual_business_content；NEGATIVE = mostly_header_footer ∪ cover_or_frontmatter ∪ blank_or_separator；
   form_or_template 与 uncertain 不进入 threshold 选择，也不计入 positive recall / negative trigger，单独报告。
P5 验证分支：NEGATIVE N >= 12 → stratified development/holdout（seed=20260917，分层 = POS/NEG；
   每层按 (doc_id, pdf_page) 排序后 random.Random(seed).shuffle，dev = 前 round(2n/3) 页）；
   NEGATIVE N < 12 → leave-one-out（对 POS ∪ NEG 每页一折，按 (doc_id, pdf_page) 排序）。
P6 特征（只比较这两个；middle 区 = 行 [floor(0.15h), floor(0.85h))、全部列；nonwhite := gray < t）：
   F1 = middle_nonwhite_count / middle_area（= A.1 middle_nonwhite_ratio，逐页与 A.1 CSV 核对）
   F2 = middle_nonwhite_count / middle_bbox_area（middle 区 nonwhite 的最小外接矩形）
   另记 F2_bbox_area_ratio = middle_bbox_area / middle_area（只报告，不做阈值）。
   middle_nonwhite_count = 0 → F2 无定义：不参与阈值候选值，决策恒为 not triggered。
   配置空间 = {F1,F2} × dpi{40,100} × gray{250,245,235} = 12；不增加任何其他特征。
P7 阈值规则（每个训练集、每个配置独立执行）：trigger iff signal > tau。
   P_min = 训练 POS 中有定义信号的最小值；V_below = 训练 POS∪NEG 中严格小于 P_min 的最大有定义信号。
   存在 V_below → tau = (V_below + P_min) / 2（训练观测值之间的 midpoint）；
   不存在 → 退回 observed boundary：trigger iff signal >= P_min。
   训练 POS 无有定义信号或训练 NEG = 0 → insufficient data（不产出阈值）。
   该规则优先 0 positive miss，其次在此前提下取最松阈值；不做连续搜索。
P8 CRM p.74 压力测试（在任何 threshold validation 之前计算与判定）：
   对 6 个 (dpi, gray) 单元，各算 CRM p.74 的 F1、F2 与 NEGATIVE 全体的 max_neg_F1、max_neg_F2：
   mult = signal / max_neg（max_neg > 0 时），abs_gap = signal - max_neg。
   单元“可比” iff max_neg_F1 > 0 且 max_neg_F2 > 0。
   CASE F2-A iff 可比单元 >= 4 且其中 >= 4 个单元满足 F2_mult >= 2.0 × F1_mult 且 F2_abs_gap > 0；否则 CASE F2-B。
   F2-A → primary feature = F2；F2-B → primary feature = F1，且把“大幅面/局部内容稀释”记为已知 failure mode，不下调 F1 阈值。
P9 候选配置（<= 3）：
   LOO 分支：C1 = (primary, 40 dpi, gray 245)，C2 = (primary, 100 dpi, gray 245)，C3 = (另一 feature, 40 dpi, gray 245) 作对照；
     12 个配置全部做 LOO 作为 sensitivity 表，不是候选。
   dev/holdout 分支：只在 dev 上对 12 配置排序 (dev POS miss 升序, dev NEG trigger 升序, primary feature 优先,
     40 dpi 优先, gray 按 245,250,235)，取前 3；写 THRESHOLD FREEZE POINT 后才计算 holdout。
P10 leave-one-document-out（描述性）：对每个 doc_id、每个候选，训练 = 其他文档的 POS∪NEG，按 P7 定阈值；
   训练 POS=0 或 NEG=0 → insufficient data。报告被留出文档的 POS recall、NEG trigger、form/uncertain trigger。
P11 40 vs 100 dpi：对 primary feature @ gray 245，比较 (a) 全体 POS∪NEG 定阈值后对 88 页的 trigger 集（in-sample，描述性），
   (b) LOO 留出决策；列出全部 flip 页。
P12 V1 = Phase A alpha_token_ratio <= 0（不重拟合），只报告它在 88 页上的触发，不与 V2 合成分数。
P13 V2 状态判据（对 C1 或 C2 任一满足即 sufficiently_validated_for_Phase_B_candidate，否则 still_underdetermined）：
   (i) 样本外（LOO 留出 / holdout）POS miss = 0；(ii) 样本外 NEG trigger = 0；
   (iii) 每个数据充分的 LODO 折：被留出文档 POS recall = 1 且 NEG trigger = 0；
   (iv) 阈值稳定：所有折的 tau 都落在全体 POS∪NEG 的同一个间隙内（即任一折阈值对【未留出】的已标注页决策与全体阈值一致）。
   无论结果如何，小 N 下 0/N 不表示“不会误触发”；结论只针对当前 9 份 PDF，且只相对 Claude visual-review 标签。
==== END PREREGISTRATION ===="""

# ------------------------------------------------------------------------------
# A.2 新 review 标签（reviewer = claude_visual_review）。键 (doc_id, pdf_page) → (label, review_dpi, note)。
# 在写入 PREREGISTRATION 之后填写。
# ------------------------------------------------------------------------------
_V = "visual_business_content"
_F = "form_or_template"
A2_REVIEW_LABELS: dict[tuple[str, int], tuple[str, int, str]] = {
    ("CMM", 73): (_V, 100, "船员投诉处理流程图（HOD 3 天 / Master 5 天 / DPA 10 天 / Union 或 Flag 20 天），框内文字为图像"),
    ("CMM", 114): (_V, 100, "Appendix V 表 Engine KPI 1（高级轮机员）考核指标与 5 级评分描述，整表为图像"),
    ("CMM", 115): (_V, 100, "Appendix V 表 BC2（初级高级船员与实习生）行为特征评分描述，整表为图像"),
    ("CMM", 116): (_V, 100, "Appendix V 表 Deck KPI 2 考核指标与评分描述，整表为图像"),
    ("CMM", 118): (_V, 100, "Appendix V 表 BC3 行为特征评分描述，整表为图像"),
    ("CMM", 119): (_V, 100, "Appendix V 表 KPI 3 考核指标与评分描述，整表为图像"),
    ("CMM", 120): (_V, 100, "Appendix VI 船上人员职责汇报关系图（只占页面上部约 40%）"),
    ("CMM", 121): (_V, 100, "Appendix VI 实习生选拔流程图"),
    ("CMM", 127): (_V, 100, "Appendix VI 甲板/轮机/电子电气职业晋升路径图（含年限、COC 等级）"),
    ("CMM", 129): (_V, 100, "Appendix VI Monitoring Expenses 泳道流程图（内容较少：月度 VOE 审核）"),
    ("CMM", 130): (_V, 100, "Appendix VI Cash To Master 泳道流程图（CCA、应急现金上限 USD 5,000、表单 C-2/C-4/C-5）"),
    ("CRM", 32): (_V, 100, "Server BCDR Strategy 时间轴（RPO 23h、RTO 24h/24-72h/4-6 周、MTD 2-4 天），横版"),
    ("CRM", 33): (_V, 100, "VSAT BCDR 流程图（Iridium/FB、Inmarsat C、4G 分支）"),
    ("CRM", 35): (_V, 100, "ECDIS BCDR 流程图（第二台 ECDIS / ENS Tablet / SSD 分支）"),
    ("CRM", 37): (_V, 100, "GPS BCDR 流程图"),
    ("CRM", 38): (_V, 100, "GPS BCDR Strategy 时间轴（RTO < 1h / < 1 周，MTD < 1 周），横版"),
    ("CRM", 40): (_V, 100, "Email BCDR Strategy 时间轴（RTO < 3h / 24-72h / 4-6 周，MTD 3h），横版"),
    ("CRM", 42): (_V, 100, "SSAS BCDR 流程图 + 时间轴（MTD < 1 周）"),
    ("CRM", 46): (_V, 100, "GP 1.4 Fleet Incident Management Process 流程图，含 24/7 支持电话与邮箱"),
    ("CRM", 83): (_V, 100, "SF 4.4 数据分级参考表（Level 0-3 与评估标准），横版，整表为图像"),
    ("CRM", 97): (_V, 100, "SP 2.3 事件上报流程图（与 CRM p.46 高度相似）"),
    ("EMM", 1): ("cover_or_frontmatter", 100, "EMM 封面：logo + 手册标题"),
    ("ERM", 15): (_V, 100, "4.1.3 应急通信流程图（Master → DPA/CSO → GM/FD → CEO → CRT/CMT）"),
    ("ERM", 16): (_V, 100, "4.1.4 应急管理组织分级（ERT/LRT/CRT/CMT 及职责）"),
    ("ERM", 96): (_V, 100, "B.11.2 运河/狭水道舵机失灵处置流程图"),
    ("ERM", 121): (_V, 100, "D.1 岸基 CRT 响应流程图 + 外部相关方清单（>12h 分班规则）"),
    ("ERM", 123): (_V, 100, "D.1 危机管理与响应团队组织图（按 Level 1 / 2-3 / 4-5 事件分层）"),
    ("FMM", 45): (_V, 100, "1.5 防爆电气设备铭牌识别图 + ATEX/IEC 标记含义表，均为图像"),
    ("FMM", 48): (_V, 100, "1.5 电缆格兰头/接地/密封接头检查示意图与图内说明文字"),
    ("QMM", 19): (_V, 100, "1 General 相关方关系图（船管与各相关方的关系标注），图内文字倾斜、较小但可读"),
    ("QMM", 105): (_V, 100, "Flowchart Q-15.6 业务流程（询价 → 报价 → 接船 → 续约）"),
    ("QMM", 114): (_V, 100, "17 MOC 临时变更流程图"),
    ("QMM", 161): (_V, 100, "B.1 PTM 组织架构图（含人名与职务）"),
    ("QMM", 163): (_V, 100, "B.3 PSM 组织架构图 + ECP 汇报关系"),
    ("QMM", 164): (_V, 100, "B.4 PPSB 组织架构图 + 共享服务"),
    ("SMM", 31): (_V, 100, "2.1.10 风险评估流程图（RA、DPA 审批、Take 5）"),
    ("SMM", 34): (_V, 100, "2.2 Take 5 海报：5 个步骤；以卡通图为主，文字较少"),
    ("TACM", 29): (_V, 100, "8 Predictive Index 评估流程图"),
    ("TACM", 39): (_F, 100, "Microsoft Forms 课程评估 Q3-5（适用对象 / 授课方式 / 结构）"),
    ("TACM", 41): (_F, 100, "Microsoft Forms Q10-14 Yes/No 与评论框"),
    ("TACM", 42): (_F, 100, "Microsoft Forms Q15-18 + Forms 页脚"),
    ("TACM", 44): (_F, 100, "Microsoft Forms 培训机构评估 Q4-7；题目下有核查指引（如 IMO 白名单）"),
    ("TACM", 45): (_F, 100, "Microsoft Forms Q8-11，含空输入框与 5 星评分"),
    ("TACM", 46): (_F, 100, "Microsoft Forms Q12-15；题目下有核查指引（PPE、AED、消防）"),
    ("TACM", 47): (_F, 100, "Microsoft Forms Q16-19 + Forms 页脚"),
    ("TACM", 49): (_F, 100, "Microsoft Forms 培训反馈 Q5-9（1-5 李克特量表 + 输入框）"),
    ("TACM", 50): (_F, 100, "Microsoft Forms Q10 + Forms 页脚，页面大部分空白"),
    ("TACM", 52): (_F, 100, "Microsoft Forms 'General' 段：被评估者姓名输入框"),
    ("TACM", 73): (_F, 100, "Microsoft Forms Q26 Communication and Influencing 总评 1-5 选项"),
    ("TACM", 85): (_F, 100, "Microsoft Forms Q40 Decision Making 总评 1-5 选项"),
}

# A.1 已有、本轮只复用不重算的视觉列（进入 master CSV）。
A1_REUSED_COLUMNS: tuple[str, ...] = tuple(
    f"d{d}_{m}_{t}" for d in DPIS for t in GRAY_THRESHOLDS
    for m in ("nonwhite_ratio", "top_nonwhite_ratio", "bottom_nonwhite_ratio", "ink_bbox_area_ratio")
)

PHASE_A_REQUIRED: tuple[str, ...] = (
    "doc_id", "source_filename", "pdf_page", "label", "font_count", "extracted_chars",
    "alpha_token_ratio", "parser_body_chars", "corpus_chunk_count",
)
VISUAL_REQUIRED: tuple[str, ...] = (
    "doc_id", "source_filename", "pdf_page", "review_observation", "review_dpi", "review_note", "img_object_count",
    *(f"d{d}_{c}" for d in DPIS for c in ("render_status", "pgm_sha256", "width_px", "height_px")),
    *(f"d{d}_{m}_{t}" for d in DPIS for t in GRAY_THRESHOLDS
      for m in ("nonwhite_ratio", "top_nonwhite_ratio", "middle_nonwhite_ratio", "bottom_nonwhite_ratio",
                "middle_nonwhite_count", "ink_bbox_area_ratio")),
)


# ==============================================================================
# 基础工具
# ==============================================================================

class ValidationError(RuntimeError):
    """输入不一致或环境错误。"""


def run_cmd(argv: Sequence[str]) -> str:
    """跑命令返回 stdout。抛出 ValidationError —— 命令不存在 / 非零返回 / 超时。"""
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=POPPLER_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise ValidationError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValidationError(f"超时: {' '.join(argv)}") from exc
    if proc.returncode != 0:
        raise ValidationError(f"{argv[0]} 返回 {proc.returncode}: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", errors="replace")


def tool_version(tool: str) -> str:
    proc = subprocess.run([tool, "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if not text:
        raise ValidationError(f"{tool} -v 无输出")
    return text.splitlines()[0]


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt(x: float | None) -> str:
    return "" if x is None else f"{x:.{RATIO_DECIMALS}f}"


def pct(values: Sequence[float], p: int) -> float:
    """最近秩分位（确定性）。输入非空。"""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))]


def read_csv(path: str, required: Sequence[str]) -> list[dict[str, str]]:
    """读 CSV；缺列抛 ValidationError。"""
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ValidationError(f"{path} schema 不匹配，缺列: {missing}")
        return list(reader)


def environment(args: argparse.Namespace) -> list[str]:
    """日志头：环境与全部输入指纹。抛出 ValidationError —— corpus 与冻结值不一致。"""
    corpus_sha = file_sha256(args.corpus)
    with open(args.corpus, encoding="utf-8") as handle:
        chunk_count = sum(1 for line in handle if line.strip())
    if corpus_sha != EXPECTED_CORPUS_SHA256 or chunk_count != EXPECTED_CHUNK_COUNT:
        raise ValidationError(f"corpus 与冻结值不一致: sha={corpus_sha} chunks={chunk_count}")
    lines = [
        f"  python        = {platform.python_version()}",
        f"  numpy         = {np.__version__}",
        f"  pdftoppm      = {tool_version('pdftoppm')}",
        f"  git_commit    = {run_cmd(['git', 'rev-parse', 'HEAD']).strip()}",
        f"  script        = scripts/ocr_visual_threshold_validation.py sha256={file_sha256(os.path.abspath(__file__))}",
        f"  phase_a_csv   = {args.phase_a_csv} sha256={file_sha256(args.phase_a_csv)}",
        f"  a1_visual_csv = {args.visual_csv} sha256={file_sha256(args.visual_csv)}",
        f"  a1_log        = {args.a1_log} sha256={file_sha256(args.a1_log)}",
        f"  corpus        = {args.corpus} sha256={corpus_sha} chunks={chunk_count}（与冻结值一致，已校验）",
        f"  seed          = {args.seed}",
        f"  CHUNK_MIN_CHARS (contracts) = {contracts.CHUNK_MIN_CHARS}",
        f"  PREREGISTRATION block sha256 = {hashlib.sha256(PREREGISTRATION.encode('utf-8')).hexdigest()}",
    ]
    for fn in sorted(f for f in os.listdir(args.pdf_dir) if f.lower().endswith(PDF_SUFFIX)):
        lines.append(f"  pdf sha256={file_sha256(os.path.join(args.pdf_dir, fn))}  {fn}")
    return lines


# ==============================================================================
# 渲染与特征
# ==============================================================================

def parse_pgm(raw: bytes) -> np.ndarray:
    """P5 8-bit PGM → (h, w) uint8。抛出 ValidationError —— 格式不符。"""
    tokens: list[bytes] = []
    i, n = 0, len(raw)
    while len(tokens) < 4:
        while i < n and raw[i:i + 1].isspace():
            i += 1
        if i < n and raw[i:i + 1] == b"#":
            while i < n and raw[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while j < n and not raw[j:j + 1].isspace():
            j += 1
        if j == i:
            raise ValidationError("PGM 头不完整")
        tokens.append(raw[i:j])
        i = j
    i += 1
    if tokens[0] != b"P5" or int(tokens[3]) != 255:
        raise ValidationError(f"不支持的 PGM: {tokens!r}")
    width, height = int(tokens[1]), int(tokens[2])
    if n - i != width * height:
        raise ValidationError(f"PGM 像素字节数 {n - i} != {width}x{height}")
    return np.frombuffer(raw, dtype=np.uint8, count=width * height, offset=i).reshape(height, width)


def render_page(path: str, dpi: int, page: int) -> bytes:
    """单页 pdftoppm -gray 渲染为 PGM 字节。抛出 ValidationError —— 失败或输出文件数 != 1。"""
    tmp = tempfile.mkdtemp(prefix=f"a2_r{dpi}_")
    try:
        run_cmd(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(page), "-l", str(page), path, os.path.join(tmp, "p")])
        names = [n for n in os.listdir(tmp) if n.endswith(".pgm")]
        if len(names) != 1:
            raise ValidationError(f"pdftoppm 输出文件数 {len(names)} != 1: {path} p{page} {dpi}dpi")
        with open(os.path.join(tmp, names[0]), "rb") as handle:
            return handle.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def middle_features(a: np.ndarray, gray: int) -> dict[str, object]:
    """middle 区 F1 / F2 与 bbox。F2 在 middle 无 nonwhite 时为 None（无定义）。"""
    h, w = a.shape
    top_end, mid_end = math.floor(h * REGION_TOP_END), math.floor(h * REGION_MIDDLE_END)
    mask = a[top_end:mid_end] < gray
    area = (mid_end - top_end) * w
    count = int(mask.sum())
    out: dict[str, object] = {"middle_count": count, "F1": count / area if area else None}
    if count == 0:
        out.update(F2=None, bbox_ratio=None, bbox=None)
        return out
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    y0, y1, x0, x1 = int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])
    bbox_area = (y1 - y0 + 1) * (x1 - x0 + 1)
    out.update(F2=count / bbox_area, bbox_ratio=bbox_area / area,
               bbox=(x0, y0 + top_end, x1, y1 + top_end))
    return out


# ==============================================================================
# 阈值规则（P7）与评估
# ==============================================================================

@dataclass(frozen=True)
class Threshold:
    tau: float
    inclusive: bool  # True → signal >= tau（observed boundary）；False → signal > tau（midpoint）
    how: str

    def fires(self, value: float | None) -> bool:
        if value is None:
            return False
        return value >= self.tau if self.inclusive else value > self.tau

    def text(self) -> str:
        return f"signal {'>=' if self.inclusive else '>'} {self.tau:.6f} ({self.how})"


def fit_threshold(pos: Sequence[float | None], neg: Sequence[float | None]) -> Threshold | None:
    """P7。训练 POS 无有定义值或训练 NEG 为空 → None（insufficient data）。"""
    pos_defined = [v for v in pos if v is not None]
    if not pos_defined or not neg:
        return None
    p_min = min(pos_defined)
    below = [v for v in (*pos_defined, *(x for x in neg if x is not None)) if v < p_min]
    if below:
        v_below = max(below)
        return Threshold((v_below + p_min) / 2, False, f"midpoint({v_below:.6f}, {p_min:.6f})")
    return Threshold(p_min, True, f"observed_boundary(P_min={p_min:.6f})")


Config = tuple[str, int, int]  # (feature, dpi, gray)


def cfg_name(c: Config) -> str:
    return f"{c[0]}@{c[1]}dpi/g{c[2]}"


def sig(page: dict[str, object], c: Config) -> float | None:
    return page["feat"][(c[1], c[2])][c[0]]  # type: ignore[index]


def key_str(page: dict[str, object]) -> str:
    return f"{page['doc_id']}:p{page['pdf_page']}"


# ==============================================================================
# 主流程
# ==============================================================================

def build_population(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[tuple[str, int], dict[str, str]]]:
    """Phase A population（P1）+ A.1 visual 行。抛出 ValidationError —— 数量或 schema 不符。"""
    phase_a = read_csv(args.phase_a_csv, PHASE_A_REQUIRED)
    visual = {(r["doc_id"], int(r["pdf_page"])): r for r in read_csv(args.visual_csv, VISUAL_REQUIRED)}
    pop = [r for r in phase_a if int(r["parser_body_chars"]) < contracts.CHUNK_MIN_CHARS]
    if len(pop) != EXPECTED_POPULATION:
        raise ValidationError(f"population = {len(pop)} != {EXPECTED_POPULATION}")
    pages: list[dict[str, object]] = []
    for r in sorted(pop, key=lambda x: (x["doc_id"], int(x["pdf_page"]))):
        key = (r["doc_id"], int(r["pdf_page"]))
        if key not in visual:
            raise ValidationError(f"A.1 visual CSV 缺页: {key}")
        v = visual[key]
        if v["source_filename"] != r["source_filename"]:
            raise ValidationError(f"文件名不一致: {key}")
        atr = r["alpha_token_ratio"]
        pages.append({
            "doc_id": key[0], "pdf_page": key[1], "source_filename": r["source_filename"],
            "phase_a_label": r["label"], "extracted_chars": int(r["extracted_chars"]),
            "parser_body_chars": int(r["parser_body_chars"]), "font_count": int(r["font_count"]),
            "alpha_token_ratio": atr, "img_object_count": v["img_object_count"],
            "v1_trigger": int(atr != "" and float(atr) <= V1_ALPHA_TOKEN_RATIO_MAX),
            "a1": {c: v[c] for c in A1_REUSED_COLUMNS},
        })
    return pages, visual


def attach_labels(pages: list[dict[str, object]], visual: dict[tuple[str, int], dict[str, str]]) -> None:
    """合并 A.1 与 A.2 标签。抛出 ValidationError —— 重叠 / 缺失 / 非法标签 / A2 标签不在 population。"""
    pop_keys = {(p["doc_id"], p["pdf_page"]) for p in pages}
    for key in A2_REVIEW_LABELS:
        if key not in pop_keys:
            raise ValidationError(f"A2 标签页不在 population: {key}")
    for p in pages:
        key = (p["doc_id"], p["pdf_page"])
        v = visual[key]
        a1 = v["review_observation"].strip()
        if a1 and key in A2_REVIEW_LABELS:
            raise ValidationError(f"A.1 与 A.2 标签重叠: {key}")
        if a1:
            label, dpi, note, source = a1, int(v["review_dpi"]), v["review_note"], "A.1"
        elif key in A2_REVIEW_LABELS:
            label, dpi, note = A2_REVIEW_LABELS[key]
            source = "A.2"
        else:
            raise ValidationError(f"缺 review 标签: {key}")
        if label not in LABELS:
            raise ValidationError(f"非法标签 {label!r}: {key}")
        p.update(review_label=label, review_dpi=dpi, review_note=note, review_source=source, reviewer=REVIEWER)
        p["eval_set"] = (SET_POS if label in POSITIVE_LABELS else SET_NEG if label in NEGATIVE_LABELS
                         else SET_FORM if label == "form_or_template" else SET_UNC)


def attach_features(pages: list[dict[str, object]], visual: dict[tuple[str, int], dict[str, str]], pdf_dir: str) -> int:
    """重渲染 88 页 × 2 dpi，核对 PGM sha 与 F1，计算 F2。返回渲染次数。抛出 ValidationError —— 不一致。"""
    renders = 0
    for p in pages:
        key = (p["doc_id"], p["pdf_page"])
        v = visual[key]
        p["feat"] = {}
        for dpi in DPIS:
            raw = render_page(os.path.join(pdf_dir, str(p["source_filename"])), dpi, int(p["pdf_page"]))
            renders += 1
            sha = hashlib.sha256(raw).hexdigest()
            if v[f"d{dpi}_render_status"] != "ok" or sha != v[f"d{dpi}_pgm_sha256"]:
                raise ValidationError(f"重渲染 PGM sha 与 A.1 不一致: {key} {dpi}dpi {sha} vs {v[f'd{dpi}_pgm_sha256']}")
            a = parse_pgm(raw)
            p[f"d{dpi}_width_px"], p[f"d{dpi}_height_px"] = a.shape[1], a.shape[0]
            for gray in GRAY_THRESHOLDS:
                f = middle_features(a, gray)
                if fmt(f["F1"]) != v[f"d{dpi}_middle_nonwhite_ratio_{gray}"]:  # type: ignore[arg-type]
                    raise ValidationError(f"F1 与 A.1 不一致: {key} {dpi}/{gray}")
                p["feat"][(dpi, gray)] = f  # type: ignore[index]
    return renders


def fit_on(train: Sequence[dict[str, object]], c: Config) -> Threshold | None:
    return fit_threshold([sig(p, c) for p in train if p["eval_set"] == SET_POS],
                         [sig(p, c) for p in train if p["eval_set"] == SET_NEG])


def loo(evalp: Sequence[dict[str, object]], c: Config) -> list[dict[str, object]]:
    """P5/P7 leave-one-out。抛出 ValidationError —— 某折训练数据不足（不伪造阈值）。"""
    folds: list[dict[str, object]] = []
    for held in evalp:
        th = fit_on([p for p in evalp if p is not held], c)
        if th is None:
            raise ValidationError(f"LOO 折训练数据不足: {cfg_name(c)} held={key_str(held)}")
        folds.append({"held": held, "th": th, "value": sig(held, c), "fired": th.fires(sig(held, c))})
    return folds


def loo_summary(evalp: Sequence[dict[str, object]], c: Config, folds: Sequence[dict[str, object]], full: Threshold) -> dict[str, object]:
    pos_miss = [f for f in folds if f["held"]["eval_set"] == SET_POS and not f["fired"]]  # type: ignore[index]
    neg_hit = [f for f in folds if f["held"]["eval_set"] == SET_NEG and f["fired"]]  # type: ignore[index]
    unstable = []
    for f in folds:
        th: Threshold = f["th"]  # type: ignore[assignment]
        for p in evalp:
            if p is not f["held"] and th.fires(sig(p, c)) != full.fires(sig(p, c)):
                unstable.append((key_str(f["held"]), key_str(p)))  # type: ignore[arg-type]
    taus = [f["th"].tau for f in folds]  # type: ignore[union-attr]
    return {"pos_n": sum(1 for p in evalp if p["eval_set"] == SET_POS), "neg_n": sum(1 for p in evalp if p["eval_set"] == SET_NEG),
            "pos_miss": pos_miss, "neg_hit": neg_hit, "unstable": unstable,
            "tau_min": min(taus), "tau_p50": pct(taus, 50), "tau_max": max(taus)}


def analyze(args: argparse.Namespace, out: list[str], t0: float) -> int:
    w = out.append
    pages, visual = build_population(args)
    attach_labels(pages, visual)
    t_render = time.perf_counter()
    renders = attach_features(pages, visual, args.pdf_dir)
    render_s = time.perf_counter() - t_render
    pos = [p for p in pages if p["eval_set"] == SET_POS]
    neg = [p for p in pages if p["eval_set"] == SET_NEG]
    form = [p for p in pages if p["eval_set"] == SET_FORM]
    unc = [p for p in pages if p["eval_set"] == SET_UNC]
    evalp = pos + neg
    evalp.sort(key=lambda p: (p["doc_id"], p["pdf_page"]))

    # ---- §1 ----
    w("§1 88 parser-dropped 页 review 结果（reviewer = claude_visual_review；不是独立人类 ground truth）")
    w(f"  population = {len(pages)}；复用 A.1 标签 = {sum(1 for p in pages if p['review_source'] == 'A.1')}；"
      f"A.2 新 review = {sum(1 for p in pages if p['review_source'] == 'A.2')}；未标注 = 0（缺失会抛异常）")
    w(f"  review_dpi 分布: {json.dumps(dict(sorted(Counter(str(p['review_dpi']) for p in pages).items())))}")
    labels = Counter(p["review_label"] for p in pages)
    for lab in LABELS:
        w(f"  {lab:<26} {labels.get(lab, 0)}")
    w("  按 doc_id:")
    docs = sorted({str(p["doc_id"]) for p in pages})
    for d in docs:
        c = Counter(p["review_label"] for p in pages if p["doc_id"] == d)
        w(f"    {d:<5} n={sum(c.values()):<3} " + " ".join(f"{lab}={c[lab]}" for lab in LABELS if c[lab]))
    w(f"  uncertain 页: {', '.join(key_str(p) for p in unc) or '(none)'}")
    w("  逐页标签:")
    for p in pages:
        w(f"    {key_str(p):<10} src={p['review_source']} dpi={p['review_dpi']} label={p['review_label']:<24} "
          f"phase_a_label={p['phase_a_label']:<13} note={p['review_note']}")

    # ---- §2 ----
    w("")
    w("§2 验证策略（按 P5 预注册规则）")
    w(f"  POSITIVE N = {len(pos)}  NEGATIVE N = {len(neg)}  form_or_template N = {len(form)}  uncertain N = {len(unc)}")
    if len(neg) >= NEG_MIN_FOR_HOLDOUT:
        raise ValidationError("NEGATIVE >= 12：应走 stratified dev/holdout 分支；本脚本在该数据下未实现此分支，拒绝静默改用 LOO")
    w(f"  NEGATIVE N = {len(neg)} < {NEG_MIN_FOR_HOLDOUT} → leave-one-out（不做一次性 2/3:1/3 holdout）")
    w("  NEGATIVE 页: " + ", ".join(f"{key_str(p)}({p['review_label']})" for p in neg))
    w("  ⚠️ 小 N：NEG 只有个位数，0/N trigger 不能写成“证明不会误触发”。")

    # ---- §3 CRM p.74 ----
    w("")
    w("§3 CRM p.74 压力测试（P8；在任何 threshold validation 之前计算与判定）")
    stress = next((p for p in pages if p["doc_id"] == STRESS_DOC and p["pdf_page"] == STRESS_PAGE), None)
    if stress is None:
        raise ValidationError("CRM p.74 不在 population")
    others = [p for p in pages if p is not stress]
    for dpi in DPIS:
        for dim in ("width_px", "height_px"):
            vals = [float(p[f"d{dpi}_{dim}"]) for p in others]  # type: ignore[arg-type]
            w(f"  d{dpi} {dim:<9}: CRM p.74 = {stress[f'd{dpi}_{dim}']}；其余 87 页 min={pct(vals, 0):g} p50={pct(vals, 50):g} "
              f"p95={pct(vals, 95):g} max={pct(vals, 100):g}")
    comparable = 0
    favourable = 0
    w(f"  {'cell':<12} {'F1_p74':>9} {'maxnegF1':>9} {'F1_mult':>8} {'F1_gap':>9} | {'F2_p74':>9} {'maxnegF2':>9} {'F2_mult':>8} {'F2_gap':>9} {'bbox/mid':>8} | cond")
    for dpi in DPIS:
        for gray in GRAY_THRESHOLDS:
            sf = stress["feat"][(dpi, gray)]  # type: ignore[index]
            cells = {}
            for feat in FEATURES:
                negvals = [(p["feat"][(dpi, gray)][feat], key_str(p)) for p in neg if p["feat"][(dpi, gray)][feat] is not None]  # type: ignore[index]
                mx = max(negvals) if negvals else (0.0, "(all undefined)")
                val = sf[feat]
                mult = (val / mx[0]) if (val is not None and mx[0] > 0) else None
                gap = (val - mx[0]) if val is not None else None
                cells[feat] = (val, mx, mult, gap)
            comp = cells["F1"][1][0] > 0 and cells["F2"][1][0] > 0
            ok = False
            if comp:
                comparable += 1
                ok = (cells["F2"][2] is not None and cells["F1"][2] is not None
                      and cells["F2"][2] >= F2A_MARGIN_FACTOR * cells["F1"][2] and cells["F2"][3] > 0)
                favourable += int(ok)
            f1, f2 = cells["F1"], cells["F2"]
            w(f"  d{dpi}/g{gray:<5} {fmt(f1[0]):>9} {fmt(f1[1][0]):>9} {fmt(f1[2]):>8} {fmt(f1[3]):>9} | "
              f"{fmt(f2[0]):>9} {fmt(f2[1][0]):>9} {fmt(f2[2]):>8} {fmt(f2[3]):>9} {fmt(sf['bbox_ratio']):>8} | "
              f"comparable={int(comp)} F2_mult>=2xF1_mult&gap>0={int(ok)}  maxneg F1@{f1[1][1]} F2@{f2[1][1]}")
    case_a = comparable >= F2A_MIN_CELLS and favourable >= F2A_MIN_CELLS
    primary = "F2" if case_a else "F1"
    other = "F1" if case_a else "F2"
    w(f"  可比单元 = {comparable}；满足 F2-A 条件的单元 = {favourable} → CASE {'F2-A' if case_a else 'F2-B'} → primary feature = {primary}")
    if not case_a:
        w("  CASE F2-B：F2 未明显改善分离；“大幅面 / 局部内容导致 ratio 被稀释”保留为已知 failure mode；不下调 F1 阈值来掩盖。")

    # ---- §4 候选 ----
    cands: list[Config] = [(primary, 40, PRIMARY_GRAY), (primary, 100, PRIMARY_GRAY), (other, 40, PRIMARY_GRAY)]
    w("")
    w("§4 候选配置（P9，LOO 分支；阈值规则 P7）")
    full_th: dict[Config, Threshold] = {}
    loo_res: dict[Config, list[dict[str, object]]] = {}
    summaries: dict[Config, dict[str, object]] = {}
    all_cfgs: list[Config] = [(f, d, g) for f in FEATURES for d in DPIS for g in GRAY_THRESHOLDS]
    for c in all_cfgs:
        th = fit_on(evalp, c)
        if th is None:
            raise ValidationError(f"全体 POS∪NEG 训练数据不足: {cfg_name(c)}")
        full_th[c] = th
        loo_res[c] = loo(evalp, c)
        summaries[c] = loo_summary(evalp, c, loo_res[c], th)
    for i, c in enumerate(cands, 1):
        role = "对照" if c[0] == other else "primary"
        w(f"  C{i} = {cfg_name(c)}（{role}）  全体 POS∪NEG 阈值（仅描述，in-sample）: {full_th[c].text()}")

    # ---- §5 LOO ----
    w("")
    w("§5 leave-one-out 结果（每折阈值只用其余 POS∪NEG 页；样本外 = 留出页的决策）")
    for i, c in enumerate(cands, 1):
        s = summaries[c]
        form_hit = [key_str(p) for p in form if full_th[c].fires(sig(p, c))]
        w(f"  [C{i} {cfg_name(c)}]")
        w(f"    POS recall (LOO) = {s['pos_n'] - len(s['pos_miss'])}/{s['pos_n']}；missed: "
          + (", ".join(f"{key_str(f['held'])}(signal={fmt(f['value'])}, fold_tau={f['th'].tau:.6f})" for f in s["pos_miss"]) or "(none)"))  # type: ignore[union-attr,index]
        w(f"    NEG trigger (LOO) = {len(s['neg_hit'])}/{s['neg_n']}")
        for f in loo_res[c]:
            if f["held"]["eval_set"] == SET_NEG:  # type: ignore[index]
                w(f"      NEG held={key_str(f['held']):<10} label={f['held']['review_label']:<22} signal={fmt(f['value']):>9} "  # type: ignore[index,arg-type]
                  f"fold_tau={f['th'].tau:.6f} triggered={int(f['fired'])}")  # type: ignore[union-attr]
        w(f"    fold tau: min={s['tau_min']:.6f} p50={s['tau_p50']:.6f} max={s['tau_max']:.6f}")
        w(f"    阈值稳定性（P13-iv）：折阈值改变【未留出】已标注页决策的次数 = {len(s['unstable'])}"
          + (("；例: " + ", ".join(f"held={a}→flip {b}" for a, b in s["unstable"][:10])) if s["unstable"] else ""))  # type: ignore[index]
        w(f"    form_or_template 触发（全体阈值；这些页不参与拟合，故对它们是样本外）= {len(form_hit)}/{len(form)}: {', '.join(form_hit) or '(none)'}")
        w(f"    uncertain = {len(unc)}")
        w("    逐折:")
        for f in loo_res[c]:
            h = f["held"]
            w(f"      held={key_str(h):<10} label={h['review_label']:<24} feature={c[0]} dpi={c[1]} gray={c[2]} "  # type: ignore[index]
              f"training_threshold={f['th'].text()} held_out_signal={fmt(f['value'])} triggered={int(f['fired'])}")  # type: ignore[union-attr]
    w("  sensitivity（12 配置全部 LOO；不是候选）:")
    for c in all_cfgs:
        s = summaries[c]
        w(f"    {cfg_name(c):<16} POS miss={len(s['pos_miss']):<2} NEG trig={len(s['neg_hit'])}/{s['neg_n']} "
          f"tau[min/p50/max]={s['tau_min']:.6f}/{s['tau_p50']:.6f}/{s['tau_max']:.6f} unstable={len(s['unstable'])} "
          f"missed={','.join(key_str(f['held']) for f in s['pos_miss']) or '-'}")  # type: ignore[union-attr,index]

    # ---- §6 LODO ----
    w("")
    w("§6 leave-one-document-out（描述性；不是显著性检验）")
    lodo_ok: dict[Config, bool] = {}
    for i, c in enumerate(cands, 1):
        w(f"  [C{i} {cfg_name(c)}]")
        ok_all = True
        for d in docs:
            train = [p for p in evalp if p["doc_id"] != d]
            test = [p for p in pages if p["doc_id"] == d]
            tp = sum(1 for p in train if p["eval_set"] == SET_POS)
            tn = sum(1 for p in train if p["eval_set"] == SET_NEG)
            hp = [p for p in test if p["eval_set"] == SET_POS]
            hn = [p for p in test if p["eval_set"] == SET_NEG]
            th = fit_on(train, c)
            if th is None:
                w(f"    {d:<5} train POS={tp} NEG={tn} | held POS={len(hp)} NEG={len(hn)} | insufficient data")
                continue
            miss = [key_str(p) for p in hp if not th.fires(sig(p, c))]
            nhit = [key_str(p) for p in hn if th.fires(sig(p, c))]
            fhit = [key_str(p) for p in test if p["eval_set"] in (SET_FORM, SET_UNC) and th.fires(sig(p, c))]
            if miss or nhit:
                ok_all = False
            recall = f"{len(hp) - len(miss)}/{len(hp)}" if hp else "n/a"
            w(f"    {d:<5} train POS={tp} NEG={tn} tau={th.text()} | held POS={len(hp)} NEG={len(hn)} | "
              f"POS recall={recall} missed={','.join(miss) or '-'} | NEG trigger={len(nhit)}/{len(hn)} {','.join(nhit)} | "
              f"form/uncertain trigger={','.join(fhit) or '-'}")
        lodo_ok[c] = ok_all

    # ---- §7 40 vs 100 ----
    w("")
    w(f"§7 40 vs 100 dpi（primary = {primary} @ gray {PRIMARY_GRAY}）")
    c40, c100 = (primary, 40, PRIMARY_GRAY), (primary, 100, PRIMARY_GRAY)
    set40 = {key_str(p) for p in pages if full_th[c40].fires(sig(p, c40))}
    set100 = {key_str(p) for p in pages if full_th[c100].fires(sig(p, c100))}
    w(f"  (a) 全体阈值 trigger 集（in-sample，描述性）: 40dpi n={len(set40)}  100dpi n={len(set100)}  完全相同={int(set40 == set100)}")
    for p in pages:
        k = key_str(p)
        if (k in set40) != (k in set100):
            w(f"    flip {p['doc_id']} p{p['pdf_page']} label={p['review_label']} 40={fmt(sig(p, c40))} 100={fmt(sig(p, c100))} "
              f"dec40={int(k in set40)} dec100={int(k in set100)}")
    f40 = {key_str(f["held"]): f["fired"] for f in loo_res[c40]}  # type: ignore[index]
    f100 = {key_str(f["held"]): f["fired"] for f in loo_res[c100]}  # type: ignore[index]
    flips = [k for k in f40 if f40[k] != f100[k]]
    w(f"  (b) LOO 留出决策（POS∪NEG）: flip 数 = {len(flips)}")
    for k in flips:
        p = next(x for x in evalp if key_str(x) == k)
        w(f"    flip {k} label={p['review_label']} 40={fmt(sig(p, c40))} 100={fmt(sig(p, c100))} dec40={int(f40[k])} dec100={int(f100[k])}")
    s40, s100 = summaries[c40], summaries[c100]
    w(f"  LOO 对比: 40dpi POS miss={len(s40['pos_miss'])} NEG trig={len(s40['neg_hit'])}；100dpi POS miss={len(s100['pos_miss'])} NEG trig={len(s100['neg_hit'])}")

    # ---- §8 V1 ----
    w("")
    w("§8 V1（Phase A alpha_token_ratio <= 0；不重拟合）在 88 页上的触发，按标签")
    for lab in LABELS:
        grp = [p for p in pages if p["review_label"] == lab]
        if grp:
            hit = [key_str(p) for p in grp if p["v1_trigger"]]
            w(f"  {lab:<26} {len(hit)}/{len(grp)} {', '.join(hit)}")

    # ---- §9 V2 状态 ----
    w("")
    w("§9 V2 状态（P13 判据逐条）")
    status = "still_underdetermined"
    for c in cands[:2]:
        s = summaries[c]
        cond = {"(i) LOO POS miss=0": not s["pos_miss"], "(ii) LOO NEG trigger=0": not s["neg_hit"],
                "(iii) LODO 充分折全部通过": lodo_ok[c], "(iv) 阈值稳定": not s["unstable"]}
        passed = all(cond.values())
        w(f"  {cfg_name(c)}: " + "；".join(f"{k}={int(v)}" for k, v in cond.items()) + f" → {'满足' if passed else '不满足'}")
        if passed:
            status = "sufficiently_validated_for_Phase_B_candidate"
    w(f"  V2 threshold status = {status}")
    w("  限定：validated/underdetermined 均只相对 Claude visual-review 标签、当前 9 份 PDF；不是 human / ground-truth validated。")

    # ---- §10 TACM p.55 ----
    w("")
    w("§10 TACM p.55")
    p55 = next(p for p in pages if p["doc_id"] == "TACM" and p["pdf_page"] == 55)
    w(f"  historical_label = {p55['phase_a_label']}；current_content_observation = {p55['review_label']}（{p55['review_note']}）；"
      f"label_semantics_review_required = yes")

    # ---- §11 调查边界：native body 充分但内容在视觉层 ----
    w("")
    w("§11 调查边界检查：native body 充分（不在本轮 population）但业务内容在视觉层的页")
    w("  方法（描述性，非 detector）：A.1 review 备注把 QMM p.110 记为“MOC 流程图（图像）+ 原生正文”。")
    w("  本轮由 reviewer 从 A.1 已有的 100 dpi 渲染图转录该流程图中的 4 个标签，在冻结 corpus 全文里检索。")
    rows = [json.loads(line) for line in open(args.corpus, encoding="utf-8")]
    target = [c for c in rows if c["doc_id"] == BOUNDARY_DOC and c["pdf_page"] == BOUNDARY_PAGE]
    w(f"  {BOUNDARY_DOC} p.{BOUNDARY_PAGE}: corpus chunk 数={len(target)} 正文字符={sum(len(c['text']) for c in target)} "
      f"（>= CHUNK_MIN_CHARS，故不在 88 页 population 内）")
    for phrase in BOUNDARY_PHRASES:
        hits = sorted({(c["doc_id"], c["pdf_page"]) for c in rows if phrase.lower() in c["text"].lower()})
        w(f"    转录短语 {phrase!r}: 全 corpus 命中 {len(hits)} 处 {hits}")
    w("  观察：该页 native 正文可用（V1 不触发），页面又不在 native-body-insufficient population 内（V2 不适用），")
    w("  但图内至少 3 个流程标签在全 corpus 中不存在 → 当前 9 份 PDF 中存在【V1/V2 都不覆盖】的 confirmed 实例。")
    w("  未量化：此类页面在全语料中的数量；本轮不扩大调查。")

    # ---- CSV ----
    write_csv(args.out_csv, pages, cands, full_th, loo_res)

    w("")
    w(TIMING_MARKER)
    w(f"  pdftoppm 重渲染次数 = {renders}（88 页 × 2 dpi，用于 F2 与 sha 核对）；耗时 {render_s:.3f} s")
    w(f"  total {time.perf_counter() - t0:.3f} s")
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"pages={len(pages)} POS={len(pos)} NEG={len(neg)} FORM={len(form)} UNC={len(unc)} primary={primary} status={status}")
    return 0


def write_csv(path: str, pages: Sequence[dict[str, object]], cands: Sequence[Config],
              full_th: dict[Config, Threshold], loo_res: dict[Config, list[dict[str, object]]]) -> None:
    base = ["doc_id", "source_filename", "pdf_page", "phase_a_label", "extracted_chars", "parser_body_chars", "font_count",
            "img_object_count", "alpha_token_ratio", "v1_trigger",
            "d40_width_px", "d40_height_px", "d100_width_px", "d100_height_px"]
    feat_cols = [f"d{d}_{k}_{g}" for d in DPIS for g in GRAY_THRESHOLDS
                 for k in ("middle_nonwhite_count", "F1_middle_nonwhite_ratio", "F2_bbox_density", "F2_bbox_area_ratio",
                           "middle_bbox_x0", "middle_bbox_y0", "middle_bbox_x1", "middle_bbox_y1")]
    review_cols = ["reviewer", "review_source", "review_dpi", "review_label", "review_note", "eval_set"]
    cand_cols = [f"C{i}_{cfg_name(c)}_{k}" for i, c in enumerate(cands, 1)
                 for k in ("full_threshold", "full_trigger", "loo_fold_threshold", "loo_trigger")]
    cols = base + feat_cols + list(A1_REUSED_COLUMNS) + review_cols + cand_cols
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        for p in pages:
            row: dict[str, object] = {k: p[k] for k in base}
            for d in DPIS:
                for g in GRAY_THRESHOLDS:
                    f = p["feat"][(d, g)]  # type: ignore[index]
                    bbox = f["bbox"] or ("", "", "", "")
                    row.update({f"d{d}_middle_nonwhite_count_{g}": f["middle_count"],
                                f"d{d}_F1_middle_nonwhite_ratio_{g}": fmt(f["F1"]),
                                f"d{d}_F2_bbox_density_{g}": fmt(f["F2"]),
                                f"d{d}_F2_bbox_area_ratio_{g}": fmt(f["bbox_ratio"]),
                                f"d{d}_middle_bbox_x0_{g}": bbox[0], f"d{d}_middle_bbox_y0_{g}": bbox[1],
                                f"d{d}_middle_bbox_x1_{g}": bbox[2], f"d{d}_middle_bbox_y1_{g}": bbox[3]})
            row.update(p["a1"])  # type: ignore[arg-type]
            row.update({k: p[k] for k in review_cols})
            for i, c in enumerate(cands, 1):
                fold = next((f for f in loo_res[c] if f["held"] is p), None)
                row[f"C{i}_{cfg_name(c)}_full_threshold"] = full_th[c].text()
                row[f"C{i}_{cfg_name(c)}_full_trigger"] = int(full_th[c].fires(sig(p, c)))
                row[f"C{i}_{cfg_name(c)}_loo_fold_threshold"] = fold["th"].text() if fold else ""  # type: ignore[union-attr]
                row[f"C{i}_{cfg_name(c)}_loo_trigger"] = int(fold["fired"]) if fold else ""  # type: ignore[arg-type]
            writer.writerow(row)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase-a-csv", required=True)
    ap.add_argument("--visual-csv", required=True)
    ap.add_argument("--a1-log", required=True)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-log", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--prereg-only", action="store_true")
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    out: list[str] = ["OCR fallback Phase A.2 —— V2 visual threshold validation（population = 88 parser-dropped pages）",
                      "=" * 78, "§0 环境与冻结输入"]
    out += environment(args)
    out += ["", PREREGISTRATION, ""]
    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    if args.prereg_only:
        pages, _ = build_population(args)
        out.append(f"§P prereg-only：population 重算 = {len(pages)}（= {EXPECTED_POPULATION}）。未读取 review 标签，未渲染，未计算特征。")
        with open(args.out_log, "w", encoding="utf-8") as handle:
            handle.write("\n".join(out) + "\n")
        return 0
    return analyze(args, out, t0)


if __name__ == "__main__":
    sys.exit(main())
