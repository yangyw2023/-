#!/usr/bin/env python3
"""OCR fallback Phase A.1：rendered 视觉内容信号调查 + native page usability detector 对比。

只读诊断脚本。不做 OCR、不改 parser / corpus / contracts、不装任何依赖。
像素读取路径: pdftoppm -gray → PGM(P5) → numpy.frombuffer（Pillow 不可用，刻意不引入）。

用法（三种模式，参数相同）:
    python3 scripts/ocr_visual_survey.py --mode pilot|review-render|full \\
        --pdf-dir "raw/KAIVA - Manuals" \\
        --corpus corpus/chunks.jsonl \\
        --phase-a-csv experiments/ocr_survey/_page_signals.csv \\
        --work-dir <scratchpad>/a1_work \\
        --out-csv experiments/ocr_survey/_visual_page_signals.csv \\
        --out-log experiments/ocr_survey/_visual_detector_analysis.log

    pilot          20 页固定清单，逐页调用 pdftoppm，测 40 / 100 dpi（及少数页 150 dpi）耗时。只打印。
    review-render  全量 40 dpi 信号 → 生成确定性人工 review 清单 → 把 review 页渲染成 PNG 写进 --work-dir。
                   PNG 只供人读，不进 repo。
    full           全量采集 + 与 Phase A join + detector 分析，写 CSV 与 log。

确定性:
    CSV 不含任何耗时；log 的耗时集中在 "§T" 段，标注为非确定。
    固定 DPI / 阈值集合 / 抽样 seed / 排序 / 数值格式（比值 6 位小数）。
    每页 PGM 字节的 sha256 记入 CSV，可直接检验 rasterizer 输出本身是否确定。

人工观察（REVIEW_OBSERVATIONS / TACM_OBSERVATIONS）:
    由阅读 review-render 产出的 PNG 得到，写死在本文件中并随脚本版本化。
    观察者是 Claude（模型读图），不是人类审核者 —— 需要人工复核后才能作为 ground truth。
    这些观察只作为 detector 比较的参照集，不是 OCR-required 标签。

失败语义:
    - 输入缺失 / Phase A CSV 与 PDF 页数不符 / review 观察引用了不在清单里的页 → 抛 SurveyError。
    - 单页 rasterization 失败（缺文件、PGM 解析失败）→ 记入 render_status，不跳过该行；
      写完产物后以退出码 1 结束。整份 pdftoppm 返回非零 → 该文档全部页记失败。
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
from typing import Callable, Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts  # noqa: E402

# ==============================================================================
# 模块常量
# ==============================================================================

PDF_SUFFIX: str = ".pdf"
POPPLER_TIMEOUT_S: float = 600.0
HASH_READ_BLOCK_BYTES: int = 1 << 20
RATIO_DECIMALS: int = 6

# 采集 DPI。40 = 全量；100 = 全量或分层（由 pilot 决定，见 FULL_100DPI_STRATEGY）；150 = 仅关键人工页。
DPI_LOW: int = 40
DPI_HIGH: int = 100
DPI_REVIEW_MAX: int = 150
# 灰度"非白"阈值：像素值 < t 视为 nonwhite。三个值只做 sensitivity analysis，不宣布 production 阈值。
NONWHITE_THRESHOLDS: tuple[int, ...] = (250, 245, 235)
# 页面分区（按归一化高度）。行索引: top=[0, floor(h*0.15)) middle=[floor(h*0.15), floor(h*0.85)) bottom=其余。
REGION_TOP_END: float = 0.15
REGION_MIDDLE_END: float = 0.85
# active row/column: 该行（列）nonwhite 像素数 >= ceil(frac × 行宽（列高）)，至少 1。frac 做 sensitivity。
ACTIVE_FRACTIONS: tuple[float, ...] = (0.001, 0.01, 0.05)

# pilot 与 100 dpi 全量策略（选择依据写入 log §2，数字来自 pilot 实测）。
# "full" = 全量 40 dpi + 全量 100 dpi。pilot 实测整份渲染 100 dpi ≈ 0.014 s/页（外推 1335 页 ≈ 18 s），
# 成本不构成缩小样本的理由。分层集合仍计算，只作为分析分组标注（d100_strata 列），不再决定采集范围。
FULL_100DPI_STRATEGY: str = "full"
# 分层 100 dpi 的正常页 control sample 规模与 seed。
SAMPLE_SEED: int = 20260917
CONTROL_SAMPLE_SIZE_100DPI: int = 60

# 已冻结输入（用户规格 §0）。
EXPECTED_CORPUS_SHA256: str = "8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa"
EXPECTED_CHUNK_COUNT: int = 1 * 3383
# Phase A 实测成本（引用 _criterion_calibration.log §3，不在本轮重测）。
PHASE_A_PDFFONTS_S: float = 55.750
PHASE_A_OUTPUT_SIGNALS_S: float = 0.9
BUILD_CORPUS_S: float = 2.8

LABEL_CONFIRMED_BAD: str = "confirmed_bad"
TACM: str = "TACM"
TACM_BAD_RANGE: tuple[int, int] = (38, 103)

# pilot 固定 20 页（类别来自 Phase A 已知观察；类别名是抽样意图，不是标签）。
PILOT_PAGES: tuple[tuple[str, int, str], ...] = (
    ("SMM", 20, "native_text"), ("FMM", 100, "native_text"), ("NPM", 27, "native_text"), ("QMM", 33, "native_text"),
    ("CRM", 31, "parser_dropped"), ("ERM", 17, "parser_dropped"), ("CMM", 113, "parser_dropped"), ("QMM", 161, "parser_dropped"),
    ("TACM", 38, "tacm_confirmed_bad"), ("TACM", 60, "tacm_confirmed_bad"), ("TACM", 80, "tacm_confirmed_bad"), ("TACM", 103, "tacm_confirmed_bad"),
    ("QMM", 139, "image_or_flowchart"), ("CRM", 74, "image_or_flowchart"), ("EMM", 103, "image_or_flowchart"), ("SMM", 71, "image_or_flowchart"),
    ("TACM", 55, "near_blank_candidate"), ("CRM", 77, "near_blank_candidate"), ("CMM", 1, "near_blank_candidate"), ("EMM", 1, "near_blank_candidate"),
)
PILOT_150DPI_PAGES: tuple[tuple[str, int], ...] = (("TACM", 55), ("QMM", 139), ("SMM", 20))

# 人工 review 分组（用户规格 §14）。
GROUP_A_PAGES: tuple[tuple[str, int], ...] = (
    ("QMM", 139), ("QMM", 148), ("CRM", 74), ("CRM", 31), ("ERM", 17), ("TACM", 12), ("EMM", 103), ("SMM", 71), ("CMM", 113),
)
GROUP_B_PAGES: tuple[tuple[str, int], ...] = ((TACM, 55),)
GROUP_D_SAMPLE_SIZE: int = 16
GROUP_E_SAMPLE_SIZE: int = 10
GROUP_F_PER_TAIL: int = 5
# TACM p.38-103 视觉抽样（§16）：必选页 + 分层补充。
TACM_REQUIRED_PAGES: tuple[int, ...] = (38, 40, 55, 60, 80, 103)
TACM_STRATA_EXTRA: int = 1  # 每个补充层取 1 页

GENERAL_OBS_LABELS: tuple[str, ...] = (
    "blank_or_separator", "visual_business_content", "mostly_header_footer",
    "cover_or_frontmatter", "form_or_template", "uncertain",
)
TACM_OBS_LABELS: tuple[str, ...] = (
    "business_knowledge_present", "repeated_form_scaffolding", "mixed", "blank", "uncertain",
)

# ------------------------------------------------------------------------------
# 人工观察（Claude 读 review-render 产出的 PNG；需人工复核）
# 键 (doc_id, pdf_page) → (label, 读图 dpi, 备注)。备注里 new_observation: 表示新形态。
# ------------------------------------------------------------------------------
_VBC = "visual_business_content"
_HF = "mostly_header_footer"
_NT = "native_text_control: 正文为原生文本，视觉上有业务内容"
REVIEW_OBSERVATIONS: dict[tuple[str, int], tuple[str, int, str]] = {
    # ---- A: Phase A 已看过的 visual-content dropped pages ----
    ("QMM", 139): (_VBC, 100, "new_observation: 整页扫描件（页眉表格与正文均为图像），公司愿景/使命/目标政策"),
    ("QMM", 148): (_VBC, 100, "整页扫描件：Open Reporting System 政策正文 + 热线/QR 海报"),
    ("CRM", 74): (_VBC, 100, "new_observation: 超大幅面横版页（100dpi 5168x3655px），4 张 bow-tie 技术风险图只占左侧约 1/3 宽，文字很小 → 比值类信号被页面面积稀释"),
    ("CRM", 31): (_VBC, 100, "Server BCDR 流程图（框内文字非原生文本）"),
    ("ERM", 17): (_VBC, 100, "4.1 Reporting 应急上报流程图，框内大量程序文字"),
    ("TACM", 12): (_VBC, 100, "行为能力评估流程图 + 左侧说明框"),
    ("EMM", 103): (_VBC, 100, "11.8 Open Reporting Policy 以图片嵌入（政策正文 + 热线海报）"),
    ("SMM", 71): (_VBC, 100, "2.15.4 Hot Work Schematic：职责/流程/时限三栏图"),
    ("CMM", 113): (_VBC, 100, "Appendix V 绩效考核 KPI 表格整体为图像"),
    # ---- B ----
    ("TACM", 55): ("blank_or_separator", 150, "40/100/150 dpi 全部像素 = 255，肉眼全白"),
    # ---- C: 其余 extracted_chars == 0 ----
    ("CRM", 77): (_VBC, 100, "船舶网络拓扑图（VSAT/Certus/防火墙/网段），横版"),
    ("QMM", 140): (_VBC, 100, "扫描件：HSEQA 政策全文"),
    ("QMM", 141): (_VBC, 100, "扫描件：Drug and Alcohol 政策"),
    ("QMM", 142): (_VBC, 100, "扫描件：Smoking 政策"),
    ("QMM", 143): (_VBC, 100, "扫描件：Stop Work 政策（大字海报式，文字少）"),
    ("QMM", 144): (_VBC, 100, "扫描件：Maritime Security 政策"),
    ("QMM", 145): (_VBC, 100, "扫描件：Navigation 政策"),
    ("QMM", 146): (_VBC, 100, "扫描件：Social Media 政策"),
    ("QMM", 147): (_VBC, 100, "扫描件：Anti-Corruption & Anti-Bribery 政策"),
    # ---- D: parser-dropped 且 native chars > 0（seed 抽样） ----
    ("CMM", 1): ("cover_or_frontmatter", 100, "手册封面"),
    ("CRM", 23): (_HF, 100, "只有页眉表格与页脚，正文区空白"),
    ("CRM", 34): (_VBC, 100, "VSAT BCDR Strategy 时间轴图（RTO/MTD 数值在图内）"),
    ("CRM", 36): (_VBC, 100, "ECDIS BCDR Strategy 时间轴图"),
    ("CRM", 39): (_VBC, 100, "Email BCDR 流程图"),
    ("CRM", 41): (_VBC, 100, "AIS BCDR 流程图 + 时间轴"),
    ("EMM", 113): (_VBC, 100, "new_observation: 以照片为主（封条安装示例）+ 原生图注；OCR 可回收文字极少"),
    ("ERM", 18): (_VBC, 100, "4.1.6 Office 应急响应流程图"),
    ("ERM", 36): (_VBC, 100, "CRT Team Brief 流程图 + 空白模板表格"),
    ("ERM", 95): (_VBC, 100, "B.11 舵机失灵流程图"),
    ("ERM", 126): (_VBC, 100, "CRT Briefing Guidelines 流程图（与 ERM p.36 内容几乎相同）"),
    ("FMM", 46): (_VBC, 100, "防爆设备铭牌说明图 + 标记含义表（均为图像）"),
    ("QMM", 162): (_VBC, 100, "PTSUS 组织架构图"),
    ("TACM", 40): ("form_or_template", 100, "Microsoft Forms 评估表 Q6-9（含简短核查指引）"),
    ("TACM", 48): ("form_or_template", 100, "Safety of Navigation Training 问卷首页"),
    ("TACM", 54): ("form_or_template", 100, "表单尾页，仅 'Others (Mention Rank below)' 与一个空输入框"),
    # ---- E: 正常 control ----
    ("CMM", 44): (_VBC, 100, _NT),
    ("CMM", 52): (_VBC, 100, _NT),
    ("CMM", 88): (_VBC, 100, _NT),
    ("EMM", 66): (_VBC, 100, _NT),
    ("EMM", 127): (_VBC, 100, _NT + "；另含流程测试照片"),
    ("ERM", 88): (_VBC, 100, _NT),
    ("FMM", 106): (_VBC, 100, _NT),
    ("FMM", 278): (_VBC, 100, _NT),
    ("NPM", 17): (_VBC, 100, _NT),
    ("QMM", 111): (_VBC, 100, _NT),
    # ---- F: 视觉极低 ----
    ("CRM", 3): (_HF, 100, "Part II Record of Revision：只有页眉页脚"),
    ("CRM", 67): (_HF, 100, "GP 1.7：只有页眉页脚"),
    ("FMM", 257): (_HF, 100, "只有页眉页脚 + 空的 Interval/Action/By 表头行"),
    ("NPM", 13): (_HF, 100, "续页：页眉页脚 + 2 行原生正文（有 chunk）"),
    ("SMM", 89): (_HF, 100, "续页：页眉页脚 + 2 行原生正文（有 chunk）"),
    # ---- F: 视觉极高 ----
    ("EMM", 88): (_VBC, 100, "深色底纹 PDCA 表格（原生文本）"),
    ("EMM", 118): (_VBC, 100, "大幅照片 + 原生正文"),
    ("EMM", 119): (_VBC, 100, "大幅照片 + 原生正文"),
    ("EMM", 124): (_VBC, 100, "照片 + 标注框（标注文字性质未核实）"),
    ("QMM", 110): (_VBC, 100, "MOC 流程图（图像）+ 原生正文"),
}
# TACM p.38-103 抽样：business_knowledge_present / repeated_form_scaffolding / mixed / blank / uncertain
TACM_OBSERVATIONS: dict[int, tuple[str, int, str]] = {
    38: ("mixed", 100, "Course/Training Evaluation Form 11.2：含评估周期 18-24 个月等说明 + 表单题目"),
    39: ("repeated_form_scaffolding", 100, "Q3-5 选项"),
    40: ("repeated_form_scaffolding", 100, "Q6-9，含一句面谈核查指引"),
    41: ("repeated_form_scaffolding", 100, "Q10-14 Yes/No"),
    51: ("business_knowledge_present", 100, "11.4 行为能力评估说明：评分等级定义 + 填写规则 + COMPAS 更新要求"),
    55: ("blank", 150, "全白"),
    60: ("mixed", 100, "A Team Working 能力定义段落 + 日期/活动输入框"),
    61: ("mixed", 100, "A1 Participation 正/负行为指标表 + 评分选项"),
    73: ("repeated_form_scaffolding", 100, "整体平均评分 1-5 选项"),
    75: ("mixed", 100, "C1 Awareness of Vessel Systems and Crew 行为指标表 + 评分选项"),
    78: ("repeated_form_scaffolding", 100, "评论框 + 评分选项"),
    80: ("mixed", 100, "D Decision Making 能力定义段落 + 日期输入"),
    81: ("mixed", 100, "D1 Problem Definition and Diagnosis 行为指标表 + 评分选项"),
    82: ("mixed", 100, "D2 Option Generation 行为指标表 + 评分选项"),
    103: ("repeated_form_scaffolding", 100, "表单结尾：选择下一能力或提交 + Microsoft Forms 页脚"),
}


class SurveyError(RuntimeError):
    """输入/环境错误，整轮调查前提不成立。"""


# ==============================================================================
# 基础工具
# ==============================================================================

def run_cmd(argv: Sequence[str]) -> str:
    """跑命令返回 stdout。抛出 SurveyError —— 不存在 / 非零返回 / 超时。"""
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=POPPLER_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise SurveyError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SurveyError(f"超时 >{POPPLER_TIMEOUT_S}s: {' '.join(argv)}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise SurveyError(f"{argv[0]} 返回 {proc.returncode}: {detail[-300:]}")
    return proc.stdout.decode("utf-8", errors="replace")


def tool_version(tool: str) -> str:
    proc = subprocess.run([tool, "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if not text:
        raise SurveyError(f"{tool} -v 无输出")
    return text.splitlines()[0]


def pillow_version() -> str:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return "not installed (not used)"
    return f"{PIL.__version__} (installed, not used)"


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt_ratio(x: float | None) -> str:
    return "" if x is None else f"{x:.{RATIO_DECIMALS}f}"


def parse_pgm(raw: bytes) -> np.ndarray:
    """解析 8-bit P5 PGM 为 (h, w) uint8 数组。

    抛出 SurveyError —— 魔数不是 P5、maxval != 255、像素字节数与尺寸不符。
    """
    tokens: list[bytes] = []
    i = 0
    n = len(raw)
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
            raise SurveyError("PGM 头不完整")
        tokens.append(raw[i:j])
        i = j
    i += 1  # 头与像素之间恰好一个空白
    if tokens[0] != b"P5":
        raise SurveyError(f"不是 P5 PGM: {tokens[0]!r}")
    width, height, maxval = int(tokens[1]), int(tokens[2]), int(tokens[3])
    if maxval != 255:
        raise SurveyError(f"PGM maxval={maxval}，只支持 8-bit")
    if n - i != width * height:
        raise SurveyError(f"PGM 像素字节数 {n - i} != {width}x{height}")
    return np.frombuffer(raw, dtype=np.uint8, count=width * height, offset=i).reshape(height, width)


# ==============================================================================
# 视觉信号
# ==============================================================================

def region_bounds(height: int) -> tuple[int, int]:
    return math.floor(height * REGION_TOP_END), math.floor(height * REGION_MIDDLE_END)


def visual_columns(prefix: str) -> list[str]:
    cols = [f"{prefix}_render_status", f"{prefix}_pgm_sha256", f"{prefix}_width_px", f"{prefix}_height_px",
            f"{prefix}_total_pixels", f"{prefix}_grayscale_mean", f"{prefix}_grayscale_std"]
    for t in NONWHITE_THRESHOLDS:
        cols += [f"{prefix}_nonwhite_count_{t}", f"{prefix}_nonwhite_ratio_{t}",
                 f"{prefix}_bbox_x_min_{t}", f"{prefix}_bbox_y_min_{t}", f"{prefix}_bbox_x_max_{t}", f"{prefix}_bbox_y_max_{t}",
                 f"{prefix}_ink_bbox_area_ratio_{t}",
                 f"{prefix}_top_nonwhite_ratio_{t}", f"{prefix}_middle_nonwhite_ratio_{t}", f"{prefix}_bottom_nonwhite_ratio_{t}",
                 f"{prefix}_middle_nonwhite_count_{t}"]
        for frac in ACTIVE_FRACTIONS:
            tag = frac_tag(frac)
            cols += [f"{prefix}_active_row_ratio_{t}_{tag}", f"{prefix}_active_column_ratio_{t}_{tag}",
                     f"{prefix}_middle_active_row_ratio_{t}_{tag}"]
    return cols


def frac_tag(frac: float) -> str:
    return f"f{frac:g}".replace(".", "p")


def visual_signals(prefix: str, raw: bytes) -> dict[str, str]:
    """一页 PGM 字节 → 视觉信号字典（全为格式化字符串）。抛出 SurveyError —— PGM 解析失败。"""
    a = parse_pgm(raw)
    h, w = a.shape
    total = h * w
    top_end, mid_end = region_bounds(h)
    out: dict[str, str] = {
        f"{prefix}_render_status": "ok",
        f"{prefix}_pgm_sha256": hashlib.sha256(raw).hexdigest(),
        f"{prefix}_width_px": str(w), f"{prefix}_height_px": str(h), f"{prefix}_total_pixels": str(total),
        f"{prefix}_grayscale_mean": fmt_ratio(float(a.mean(dtype=np.float64))),
        f"{prefix}_grayscale_std": fmt_ratio(float(a.std(dtype=np.float64))),
    }
    for t in NONWHITE_THRESHOLDS:
        mask = a < t
        count = int(mask.sum())
        out[f"{prefix}_nonwhite_count_{t}"] = str(count)
        out[f"{prefix}_nonwhite_ratio_{t}"] = fmt_ratio(count / total)
        rows_any = np.flatnonzero(mask.any(axis=1))
        cols_any = np.flatnonzero(mask.any(axis=0))
        if count == 0:
            for k in ("bbox_x_min", "bbox_y_min", "bbox_x_max", "bbox_y_max", "ink_bbox_area_ratio"):
                out[f"{prefix}_{k}_{t}"] = ""  # 无 nonwhite → bbox 为 null，不伪造 0
        else:
            x0, x1, y0, y1 = int(cols_any[0]), int(cols_any[-1]), int(rows_any[0]), int(rows_any[-1])
            out[f"{prefix}_bbox_x_min_{t}"] = str(x0)
            out[f"{prefix}_bbox_y_min_{t}"] = str(y0)
            out[f"{prefix}_bbox_x_max_{t}"] = str(x1)
            out[f"{prefix}_bbox_y_max_{t}"] = str(y1)
            out[f"{prefix}_ink_bbox_area_ratio_{t}"] = fmt_ratio((x1 - x0 + 1) * (y1 - y0 + 1) / total)
        regions = ((0, top_end, "top"), (top_end, mid_end, "middle"), (mid_end, h, "bottom"))
        for lo, hi, name in regions:
            size = (hi - lo) * w
            region_count = int(mask[lo:hi].sum())
            out[f"{prefix}_{name}_nonwhite_ratio_{t}"] = fmt_ratio(region_count / size) if size else ""
            if name == "middle":
                out[f"{prefix}_middle_nonwhite_count_{t}"] = str(region_count)
        row_counts = mask.sum(axis=1)
        col_counts = mask.sum(axis=0)
        for frac in ACTIVE_FRACTIONS:
            tag = frac_tag(frac)
            row_min = max(1, math.ceil(frac * w))
            col_min = max(1, math.ceil(frac * h))
            active_rows = row_counts >= row_min
            out[f"{prefix}_active_row_ratio_{t}_{tag}"] = fmt_ratio(float(active_rows.mean()))
            out[f"{prefix}_active_column_ratio_{t}_{tag}"] = fmt_ratio(float((col_counts >= col_min).mean()))
            mid = active_rows[top_end:mid_end]
            out[f"{prefix}_middle_active_row_ratio_{t}_{tag}"] = fmt_ratio(float(mid.mean())) if mid.size else ""
    return out


def failed_visual(prefix: str, status: str) -> dict[str, str]:
    row = {c: "" for c in visual_columns(prefix)}
    row[f"{prefix}_render_status"] = status
    return row


_PGM_NAME_RE = re.compile(r"-(\d+)\.pgm$")


def render_range(path: str, dpi: int, first: int, last: int, work_dir: str) -> dict[int, bytes]:
    """pdftoppm -gray 渲染 [first, last] 页，返回 {pdf_page: PGM 字节}。

    抛出 SurveyError —— pdftoppm 返回非零。缺页不抛（由调用方记为该页失败）。
    """
    tmp = tempfile.mkdtemp(prefix=f"r{dpi}_", dir=work_dir)
    try:
        run_cmd(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(first), "-l", str(last), path, os.path.join(tmp, "p")])
        out: dict[int, bytes] = {}
        for name in os.listdir(tmp):
            m = _PGM_NAME_RE.search(name)
            if m:
                with open(os.path.join(tmp, name), "rb") as handle:
                    out[int(m.group(1))] = handle.read()
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_png(path: str, dpi: int, page: int, out_root: str) -> str:
    """把一页渲染成灰度 PNG（仅供人读）。返回文件路径。抛出 SurveyError。"""
    run_cmd(["pdftoppm", "-gray", "-png", "-singlefile", "-r", str(dpi), "-f", str(page), "-l", str(page), path, out_root])
    return out_root + ".png"


# ==============================================================================
# pdfimages object signals
# ==============================================================================

PDFIMAGES_COLUMNS: tuple[str, ...] = (
    "img_object_count", "img_image_type_count", "img_smask_or_stencil_count",
    "img_max_width_px", "img_max_height_px", "img_total_object_pixels",
    "img_types", "img_colors", "img_bpc", "img_min_x_ppi",
)


def pdfimages_signals(path: str, n_pages: int) -> dict[int, dict[str, str]]:
    """pdfimages -list 解析为逐页 object-level 信号。object signals != rendered coverage。

    抛出 SurveyError —— 命令失败或表头不符。
    """
    lines = run_cmd(["pdfimages", "-list", path]).splitlines()
    if len(lines) < 2 or not lines[0].split()[:3] == ["page", "num", "type"]:
        raise SurveyError(f"pdfimages -list 表头不符: {lines[:1]}")
    per: dict[int, list[list[str]]] = defaultdict(list)
    for line in lines[2:]:
        parts = line.split()
        if not parts:
            continue
        per[int(parts[0])].append(parts)
    out: dict[int, dict[str, str]] = {}
    for page in range(1, n_pages + 1):
        rows = per.get(page, [])
        widths = [int(r[3]) for r in rows]
        heights = [int(r[4]) for r in rows]
        xppi = [int(r[12]) for r in rows if r[12].isdigit()]
        out[page] = {
            "img_object_count": str(len(rows)),
            "img_image_type_count": str(sum(1 for r in rows if r[2] == "image")),
            "img_smask_or_stencil_count": str(sum(1 for r in rows if r[2] != "image")),
            "img_max_width_px": str(max(widths)) if rows else "0",
            "img_max_height_px": str(max(heights)) if rows else "0",
            "img_total_object_pixels": str(sum(wd * ht for wd, ht in zip(widths, heights))),
            "img_types": "|".join(sorted({r[2] for r in rows})),
            "img_colors": "|".join(sorted({r[5] for r in rows})),
            "img_bpc": "|".join(sorted({r[7] for r in rows})),
            "img_min_x_ppi": str(min(xppi)) if xppi else "",
        }
    return out


# ==============================================================================
# 输入
# ==============================================================================

@dataclass
class Inputs:
    files: dict[str, dict[str, object]]  # doc_id -> {filename, path, pages, sha256}
    phase_a: dict[tuple[str, int], dict[str, str]]
    corpus_sha256: str
    chunk_count: int
    phase_a_sha256: str


def load_inputs(args: argparse.Namespace) -> Inputs:
    """读取并校验冻结输入。抛出 SurveyError —— corpus 哈希/条数不符、Phase A 与 PDF 页数不符。"""
    corpus_sha = file_sha256(args.corpus)
    with open(args.corpus, encoding="utf-8") as handle:
        chunk_count = sum(1 for line in handle if line.strip())
    if corpus_sha != EXPECTED_CORPUS_SHA256 or chunk_count != EXPECTED_CHUNK_COUNT:
        raise SurveyError(f"冻结 corpus 不符: sha256={corpus_sha} chunks={chunk_count}")
    phase_a: dict[tuple[str, int], dict[str, str]] = {}
    name_to_doc: dict[str, str] = {}
    with open(args.phase_a_csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["doc_id"], int(row["pdf_page"]))
            if key in phase_a:
                raise SurveyError(f"Phase A CSV 重复页: {key}")
            phase_a[key] = row
            name_to_doc[row["source_filename"]] = row["doc_id"]
    if not os.path.isdir(args.pdf_dir):
        raise SurveyError(f"PDF 目录不存在: {args.pdf_dir}")
    files: dict[str, dict[str, object]] = {}
    for filename in sorted(f for f in os.listdir(args.pdf_dir) if f.lower().endswith(PDF_SUFFIX)):
        if filename not in name_to_doc:
            raise SurveyError(f"PDF 不在 Phase A CSV 中: {filename}")
        doc_id = name_to_doc[filename]
        path = os.path.join(args.pdf_dir, filename)
        pages = 0
        for line in run_cmd(["pdfinfo", path]).splitlines():
            if line.startswith("Pages:"):
                pages = int(line.split(":", 1)[1])
        a_pages = sum(1 for k in phase_a if k[0] == doc_id)
        if pages != a_pages:
            raise SurveyError(f"{doc_id}: pdfinfo {pages} 页 != Phase A {a_pages} 页")
        files[doc_id] = {"filename": filename, "path": path, "pages": pages, "sha256": file_sha256(path)}
    return Inputs(files, phase_a, corpus_sha, chunk_count, file_sha256(args.phase_a_csv))


def num(row: dict[str, str], key: str) -> float | None:
    v = row.get(key, "")
    return None if v == "" else float(v)


# ==============================================================================
# pilot
# ==============================================================================

def run_pilot(inputs: Inputs, work_dir: str) -> list[str]:
    """20 页逐页渲染 + 信号计算计时；外加整份渲染吞吐（NPM）。返回日志行。"""
    out: list[str] = []
    w = out.append
    w("§P timing pilot（⚠️ 耗时非确定）")
    w("  固定 20 页（逐页调用 pdftoppm；类别=抽样意图）:")
    for doc, page, cat in PILOT_PAGES:
        w(f"    {doc} p{page}  {cat}")
    totals: dict[int, float] = {}
    for dpi in (DPI_LOW, DPI_HIGH):
        started = time.perf_counter()
        per_page: list[str] = []
        for doc, page, _cat in PILOT_PAGES:
            t0 = time.perf_counter()
            pgm = render_range(str(inputs.files[doc]["path"]), dpi, page, page, work_dir)
            t1 = time.perf_counter()
            sig = visual_signals(f"d{dpi}", pgm[page])
            t2 = time.perf_counter()
            per_page.append(f"{doc}p{page}:render={t1 - t0:.3f}s,signal={t2 - t1:.3f}s,"
                            f"mid245={sig[f'd{dpi}_middle_nonwhite_ratio_245']}")
        totals[dpi] = time.perf_counter() - started
        w(f"  {dpi} dpi: 20 页总计 {totals[dpi]:.2f}s  per_page={totals[dpi] / len(PILOT_PAGES):.3f}s")
        for item in per_page:
            w(f"      {item}")
    started = time.perf_counter()
    for doc, page in PILOT_150DPI_PAGES:
        pgm = render_range(str(inputs.files[doc]["path"]), DPI_REVIEW_MAX, page, page, work_dir)
        visual_signals(f"d{DPI_REVIEW_MAX}", pgm[page])
    t150 = time.perf_counter() - started
    w(f"  {DPI_REVIEW_MAX} dpi: {len(PILOT_150DPI_PAGES)} 页总计 {t150:.2f}s per_page={t150 / len(PILOT_150DPI_PAGES):.3f}s")
    npm = inputs.files["NPM"]
    for dpi in (DPI_LOW, DPI_HIGH):
        t0 = time.perf_counter()
        pgms = render_range(str(npm["path"]), dpi, 1, int(npm["pages"]), work_dir)
        t1 = time.perf_counter()
        for page in sorted(pgms):
            visual_signals(f"d{dpi}", pgms[page])
        t2 = time.perf_counter()
        per = (t2 - t0) / len(pgms)
        w(f"  整份渲染 NPM({len(pgms)} 页) {dpi} dpi: render={t1 - t0:.2f}s signal={t2 - t1:.2f}s per_page={per:.4f}s "
          f"→ 外推 1335 页 ≈ {per * 1335:.1f}s（顺序）")
    n = sum(int(f["pages"]) for f in inputs.files.values())
    for dpi in (DPI_LOW, DPI_HIGH):
        w(f"  逐页调用外推 {n} 页 {dpi} dpi ≈ {totals[dpi] / len(PILOT_PAGES) * n:.1f}s")
    w(f"  逐页调用外推双 DPI ≈ {(totals[DPI_LOW] + totals[DPI_HIGH]) / len(PILOT_PAGES) * n:.1f}s")
    return out


# ==============================================================================
# 全量采集
# ==============================================================================

def collect_visual(inputs: Inputs, dpi: int, pages_by_doc: dict[str, set[int]] | None, work_dir: str,
                   timing: dict[str, float]) -> dict[tuple[str, int], dict[str, str]]:
    """按文档整份（或分层页集合）渲染并计算信号。pages_by_doc=None 表示全量。

    单页失败记入 render_status；整份 pdftoppm 失败 → 该文档请求的页全部记失败（不抛）。
    """
    prefix = f"d{dpi}"
    result: dict[tuple[str, int], dict[str, str]] = {}
    render_s = signal_s = 0.0
    for doc_id in sorted(inputs.files):
        info = inputs.files[doc_id]
        n_pages = int(info["pages"])
        wanted = set(range(1, n_pages + 1)) if pages_by_doc is None else pages_by_doc.get(doc_id, set())
        if not wanted:
            continue
        # 连续页段合并为一次 pdftoppm 调用。
        spans: list[tuple[int, int]] = []
        for page in sorted(wanted):
            if spans and spans[-1][1] == page - 1:
                spans[-1] = (spans[-1][0], page)
            else:
                spans.append((page, page))
        for first, last in spans:
            t0 = time.perf_counter()
            try:
                pgms = render_range(str(info["path"]), dpi, first, last, work_dir)
                span_error = ""
            except SurveyError as exc:
                pgms = {}
                span_error = f"error: pdftoppm: {exc}"
            render_s += time.perf_counter() - t0
            t0 = time.perf_counter()
            for page in range(first, last + 1):
                if page not in pgms:
                    result[(doc_id, page)] = failed_visual(prefix, span_error or "error: page image missing")
                    continue
                try:
                    result[(doc_id, page)] = visual_signals(prefix, pgms[page])
                except SurveyError as exc:
                    result[(doc_id, page)] = failed_visual(prefix, f"error: {exc}")
            signal_s += time.perf_counter() - t0
    timing[f"{prefix}_render_s"] = render_s
    timing[f"{prefix}_signal_s"] = signal_s
    return result


def stratified_100dpi_pages(inputs: Inputs, low: dict[tuple[str, int], dict[str, str]]) -> dict[tuple[str, int], list[str]]:
    """分层 100 dpi 页集合 → 每页所属层（可多层）。层定义见 log §2。"""
    strata: dict[tuple[str, int], list[str]] = defaultdict(list)
    normal: list[tuple[str, int]] = []
    for key, row in sorted(inputs.phase_a.items()):
        chars = int(row["extracted_chars"])
        if row["parser_dropped_short"] == "1":
            strata[key].append("A_parser_dropped")
        if row["label"] == LABEL_CONFIRMED_BAD:
            strata[key].append("B_tacm_confirmed_bad")
        if chars == 0:
            strata[key].append("E_extracted_chars_0")
        elif chars < contracts.CHUNK_MIN_CHARS:
            strata[key].append("F_extracted_chars_1_119")
        if row["parser_dropped_short"] == "0" and row["label"] != LABEL_CONFIRMED_BAD:
            normal.append(key)
    for key in GROUP_A_PAGES + GROUP_B_PAGES:
        strata[key].append("D_phase_a_reviewed")
    rng = random.Random(SAMPLE_SEED)
    for key in sorted(rng.sample(normal, CONTROL_SAMPLE_SIZE_100DPI)):
        strata[key].append("C_normal_control")
    for key in review_sample(inputs, low):
        strata[key].append("R_review_sample")
    return {k: sorted(set(v)) for k, v in strata.items()}


def review_sample(inputs: Inputs, low: dict[tuple[str, int], dict[str, str]]) -> dict[tuple[str, int], list[str]]:
    """确定性人工 review 清单（§14 组 A-F + §16 TACM 抽样）→ 每页所属组。"""
    rng = random.Random(SAMPLE_SEED)
    groups: dict[tuple[str, int], list[str]] = defaultdict(list)
    for key in GROUP_A_PAGES:
        groups[key].append("A_phase_a_visual_dropped")
    for key in GROUP_B_PAGES:
        groups[key].append("B_tacm_p55")
    taken = set(GROUP_A_PAGES) | set(GROUP_B_PAGES)
    zero = sorted(k for k, r in inputs.phase_a.items() if int(r["extracted_chars"]) == 0 and k not in taken)
    for key in zero:  # 组 C 全取
        groups[key].append("C_extracted_chars_0")
    taken |= set(zero)
    dropped_pos = sorted(k for k, r in inputs.phase_a.items()
                         if r["parser_dropped_short"] == "1" and int(r["extracted_chars"]) > 0 and k not in taken)
    for key in sorted(rng.sample(dropped_pos, min(GROUP_D_SAMPLE_SIZE, len(dropped_pos)))):
        groups[key].append("D_dropped_native_chars_gt0")
    taken |= set(groups)
    normal = sorted(k for k, r in inputs.phase_a.items()
                    if r["parser_dropped_short"] == "0" and r["label"] != LABEL_CONFIRMED_BAD
                    and int(r["parser_body_chars"]) >= contracts.CHUNK_MIN_CHARS * 4 and k not in taken)
    for key in sorted(rng.sample(normal, GROUP_E_SAMPLE_SIZE)):
        groups[key].append("E_normal_control")
    taken |= set(groups)
    metric = "d40_middle_nonwhite_ratio_245"
    ranked = sorted((float(low[k][metric]), k) for k in low
                    if low[k][metric] != "" and k not in taken and inputs.phase_a[k]["label"] != LABEL_CONFIRMED_BAD)
    for _, key in ranked[:GROUP_F_PER_TAIL]:
        groups[key].append("F_visual_extreme_low")
    for _, key in ranked[-GROUP_F_PER_TAIL:]:
        groups[key].append("F_visual_extreme_high")
    for page in tacm_sample(inputs):
        groups[(TACM, page)].append("T_tacm_38_103_visual_sample")
    return {k: sorted(set(v)) for k, v in sorted(groups.items())}


def tacm_sample(inputs: Inputs) -> list[int]:
    """§16：必选页 + 分层补充（前/中/后部、字符少/多、font_count=0、不同乱码 pattern）。"""
    lo, hi = TACM_BAD_RANGE
    rows = {p: inputs.phase_a[(TACM, p)] for p in range(lo, hi + 1)}
    chosen = list(TACM_REQUIRED_PAGES)
    third = (hi - lo + 1) // 3

    def pick(cands: list[int]) -> None:
        for p in cands:
            if p not in chosen:
                chosen.append(p)
                return

    pick([p for p in range(lo, lo + third)])                         # 前部
    pick([p for p in range(lo + third, lo + 2 * third)])             # 中部
    pick([p for p in range(lo + 2 * third, hi + 1)])                 # 后部
    by_chars = sorted(rows, key=lambda p: (int(rows[p]["extracted_chars"]), p))
    pick(by_chars)                                                  # 字符最少
    pick(list(reversed(by_chars)))                                  # 字符最多
    pick([p for p in rows if rows[p]["font_count"] == "0"])         # font_count=0
    # 不同乱码 pattern：按 text_head_200 的前 12 字符分组，每个未覆盖 pattern 取最小页。
    patterns: dict[str, list[int]] = defaultdict(list)
    for p in sorted(rows):
        patterns[json.loads(rows[p]["text_head_200"] or '""')[:12]].append(p)
    covered = {json.loads(rows[p]["text_head_200"] or '""')[:12] for p in chosen}
    for pat in sorted(patterns, key=lambda s: (-len(patterns[s]), s)):
        if pat not in covered:
            pick(patterns[pat])
            covered.add(pat)
        if len(chosen) >= len(TACM_REQUIRED_PAGES) + 9:
            break
    return sorted(chosen)


# ==============================================================================
# detector
# ==============================================================================

@dataclass(frozen=True)
class Detector:
    name: str
    rule: str
    predicate: Callable[[dict[str, str]], bool]
    cost_note: str


def reviewed_label(key: tuple[str, int]) -> str | None:
    if key in REVIEW_OBSERVATIONS:
        return REVIEW_OBSERVATIONS[key][0]
    return None


def evaluate(det: Detector, rows: dict[tuple[str, int], dict[str, str]]) -> dict[str, object]:
    bad = [k for k, r in rows.items() if r["label"] == LABEL_CONFIRMED_BAD]
    bad_trig = [k for k in bad if det.predicate(rows[k])]
    img = [k for k, r in rows.items() if reviewed_label(k) == "visual_business_content" and r["parser_dropped_short"] == "1"]
    img_trig = [k for k in img if det.predicate(rows[k])]
    blank = [k for k in rows if reviewed_label(k) == "blank_or_separator"]
    blank_trig = [k for k in blank if det.predicate(rows[k])]
    unrev = [k for k, r in rows.items() if r["label"] != LABEL_CONFIRMED_BAD and k not in REVIEW_OBSERVATIONS]
    unrev_trig = [k for k in unrev if det.predicate(rows[k])]
    all_trig = sorted(k for k in rows if det.predicate(rows[k]))
    return {"bad": (len(bad_trig), len(bad), sorted(set(bad) - set(bad_trig))),
            "img": (len(img_trig), len(img), sorted(set(img) - set(img_trig))),
            "blank": (len(blank_trig), len(blank), sorted(blank_trig)),
            "unrev": (len(unrev_trig), len(unrev), sorted(unrev_trig)),
            "all": all_trig}


def compact(keys: Sequence[tuple[str, int]]) -> str:
    by: dict[str, list[int]] = defaultdict(list)
    for d, p in keys:
        by[d].append(p)
    parts = []
    for d in sorted(by):
        pages = sorted(by[d])
        spans: list[str] = []
        start = prev = pages[0]
        for p in pages[1:] + [None]:  # type: ignore[list-item]
            if p is not None and p == prev + 1:
                prev = p
                continue
            spans.append(f"{start}" if start == prev else f"{start}-{prev}")
            if p is not None:
                start = prev = p
        parts.append(f"{d}:p{','.join(spans)}")
    return " ; ".join(parts) if parts else "(none)"


# ==============================================================================
# 主流程
# ==============================================================================

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OCR fallback Phase A.1 视觉信号调查（只读）")
    ap.add_argument("--mode", choices=("pilot", "review-render", "full"), required=True)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--phase-a-csv", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-log", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.work_dir, exist_ok=True)

    t_start = time.perf_counter()
    inputs = load_inputs(args)

    if args.mode == "pilot":
        print("\n".join(run_pilot(inputs, args.work_dir)))
        return 0

    timing: dict[str, float] = {}
    t0 = time.perf_counter()
    low = collect_visual(inputs, DPI_LOW, None, args.work_dir, timing)
    timing["full_40dpi_total_s"] = time.perf_counter() - t0

    if args.mode == "review-render":
        sample = review_sample(inputs, low)
        png_dir = os.path.join(args.work_dir, "review_png")
        os.makedirs(png_dir, exist_ok=True)
        for (doc, page), groups in sample.items():
            dpis = [DPI_HIGH]
            if "B_tacm_p55" in groups or "T_tacm_38_103_visual_sample" in groups:
                dpis = [DPI_LOW, DPI_HIGH, DPI_REVIEW_MAX]
            for dpi in dpis:
                render_png(str(inputs.files[doc]["path"]), dpi, page, os.path.join(png_dir, f"{doc}_p{page:03d}_{dpi}dpi"))
            print(f"{doc} p{page} {','.join(groups)}")
        print(f"review pages={len(sample)} png_dir={png_dir}")
        return 0

    # ---- full ----
    for key in list(REVIEW_OBSERVATIONS) + [(TACM, p) for p in TACM_OBSERVATIONS]:
        if key not in inputs.phase_a:
            raise SurveyError(f"观察引用了不存在的页: {key}")
    sample = review_sample(inputs, low)
    for key in REVIEW_OBSERVATIONS:
        if key not in sample:
            raise SurveyError(f"REVIEW_OBSERVATIONS 中的页不在确定性 review 清单里: {key}")
    for key, (label, _dpi, _note) in REVIEW_OBSERVATIONS.items():
        if label not in GENERAL_OBS_LABELS:
            raise SurveyError(f"非法观察标签 {label} @ {key}")
    for page, (label, _dpi, _note) in TACM_OBSERVATIONS.items():
        if label not in TACM_OBS_LABELS:
            raise SurveyError(f"非法 TACM 观察标签 {label} @ p{page}")

    strata = stratified_100dpi_pages(inputs, low)
    wanted: dict[str, set[int]] = defaultdict(set)
    for doc, page in strata:
        wanted[doc].add(page)
    t0 = time.perf_counter()
    high = collect_visual(inputs, DPI_HIGH, None if FULL_100DPI_STRATEGY == "full" else wanted, args.work_dir, timing)
    timing["full_100dpi_total_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    p150_pages = {(TACM, 55)} | {(TACM, p) for p in TACM_OBSERVATIONS if TACM_OBSERVATIONS[p][1] >= DPI_REVIEW_MAX}
    w150: dict[str, set[int]] = defaultdict(set)
    for doc, page in p150_pages:
        w150[doc].add(page)
    top = collect_visual(inputs, DPI_REVIEW_MAX, w150, args.work_dir, timing)
    timing["d150_total_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    images: dict[tuple[str, int], dict[str, str]] = {}
    for doc_id in sorted(inputs.files):
        for page, sig in pdfimages_signals(str(inputs.files[doc_id]["path"]), int(inputs.files[doc_id]["pages"])).items():
            images[(doc_id, page)] = sig
    timing["pdfimages_scan_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rows: dict[tuple[str, int], dict[str, str]] = {}
    for key in sorted(inputs.phase_a):
        a = inputs.phase_a[key]
        row = {
            "doc_id": key[0], "source_filename": a["source_filename"], "pdf_page": str(key[1]),
            "label": a["label"], "font_count": a["font_count"], "extracted_chars": a["extracted_chars"],
            "alpha_token_ratio": a["alpha_token_ratio"], "parser_body_chars": a["parser_body_chars"],
            "parser_dropped_short": a["parser_dropped_short"], "corpus_chunk_count": a["corpus_chunk_count"],
            "d100_strata": "|".join(strata.get(key, [])),
            "review_groups": "|".join(sample.get(key, [])),
            "review_observation": REVIEW_OBSERVATIONS.get(key, ("", 0, ""))[0],
            "review_dpi": str(REVIEW_OBSERVATIONS[key][1]) if key in REVIEW_OBSERVATIONS else "",
            "review_note": REVIEW_OBSERVATIONS.get(key, ("", 0, ""))[2],
            "tacm_observation": TACM_OBSERVATIONS[key[1]][0] if key[0] == TACM and key[1] in TACM_OBSERVATIONS else "",
            "tacm_note": TACM_OBSERVATIONS[key[1]][2] if key[0] == TACM and key[1] in TACM_OBSERVATIONS else "",
        }
        row.update(low[key])
        row.update(high.get(key, failed_visual("d100", "not_sampled")))
        row.update(top.get(key, failed_visual("d150", "not_sampled")))
        row.update(images[key])
        rows[key] = row
    timing["join_s"] = time.perf_counter() - t0

    columns = (["doc_id", "source_filename", "pdf_page", "label", "font_count", "extracted_chars", "alpha_token_ratio",
                "parser_body_chars", "parser_dropped_short", "corpus_chunk_count", "d100_strata", "review_groups",
                "review_observation", "review_dpi", "review_note", "tacm_observation", "tacm_note"]
               + visual_columns("d40") + visual_columns("d100") + visual_columns("d150") + list(PDFIMAGES_COLUMNS))
    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])

    timing["total_s"] = time.perf_counter() - t_start
    pilot_lines = run_pilot(inputs, args.work_dir)
    write_log(args, inputs, rows, strata, sample, timing, pilot_lines)
    failed = sorted(k for k, r in rows.items()
                    if any(r[f"{p}_render_status"].startswith("error") for p in ("d40", "d100", "d150")))
    if failed:
        print(f"rasterization 失败 {len(failed)} 页: {compact(failed)}", file=sys.stderr)
        return 1
    return 0



# ==============================================================================
# 分析与日志
# ==============================================================================

NON_CONTENT_LABELS: frozenset[str] = frozenset({"blank_or_separator", "mostly_header_footer", "cover_or_frontmatter"})
PERCENTILES: tuple[int, ...] = (0, 5, 25, 50, 75, 95, 100)
V2_DPI_PREFIX: str = "d40"
V2_AUX_DPI_PREFIX: str = "d100"
MIDDLE_METRIC: str = "middle_nonwhite_ratio"
WHOLE_METRIC: str = "nonwhite_ratio"


def fnum(row: dict[str, str], key: str) -> float | None:
    v = row.get(key, "")
    return None if v == "" else float(v)


def pct(values: Sequence[float], q: int) -> float:
    """最近秩分位。values 非空。"""
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(q / 100 * len(ordered)) - 1))
    return ordered[idx]


def dist(values: Sequence[float]) -> str:
    if not values:
        return "n=0"
    return f"n={len(values)} " + " ".join(f"p{q}={pct(values, q):.4f}" for q in PERCENTILES)


def ranks(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    order = np.argsort(arr, kind="mergesort")
    r = np.empty(len(arr), dtype=np.float64)
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum()) / denom if denom else float("nan")


def v1_predicate(row: dict[str, str]) -> bool:
    """Phase A B_alpha_token_ratio@t_recall：alpha_token_ratio <= 0；无定义（无文本）恒不触发。"""
    v = fnum(row, "alpha_token_ratio")
    return v is not None and v <= 0


def low_text(row: dict[str, str]) -> bool:
    """native body evidence insufficient := parser_body_chars < contracts.CHUNK_MIN_CHARS（parser 自身丢页条件）。"""
    return int(row["parser_body_chars"]) < contracts.CHUNK_MIN_CHARS


def derive_v2_threshold(rows: dict[tuple[str, int], dict[str, str]], prefix: str, t: int) -> dict[str, object]:
    """从人工 review 的 parser-dropped 页推导 middle ink 阈值。

    正例 = review 为 visual_business_content 的 dropped 页；反例 = review 为 NON_CONTENT_LABELS 的 dropped 页。
    tau = 反例 middle ratio 的最大值；规则为 middle > tau（不触发任何已 review 反例的最松阈值）。
    同时报告正例最小值与二者是否可分。阈值与评估用同一批 review 页 → in-sample，必然乐观。
    """
    key = f"{prefix}_{MIDDLE_METRIC}_{t}"
    pos = sorted((float(rows[k][key]), k) for k in rows
                 if reviewed_label(k) == "visual_business_content" and rows[k]["parser_dropped_short"] == "1" and rows[k][key] != "")
    neg = sorted((float(rows[k][key]), k) for k in rows
                 if reviewed_label(k) in NON_CONTENT_LABELS and rows[k]["parser_dropped_short"] == "1" and rows[k][key] != "")
    tau = neg[-1][0] if neg else 0.0
    return {"key": key, "tau": tau, "pos": pos, "neg": neg, "separable": bool(pos) and pos[0][0] > tau}


def fmt_eval(name: str, rule: str, res: dict[str, object]) -> list[str]:
    bt, bn, bmiss = res["bad"]  # type: ignore[misc]
    it, inn, imiss = res["img"]  # type: ignore[misc]
    kt, kn, ktrig = res["blank"]  # type: ignore[misc]
    ut, un, utrig = res["unrev"]  # type: ignore[misc]
    return [
        f"  [{name}] rule: {rule}",
        f"    A confirmed_bad TACM recall        = {bt}/{bn}" + (f" = {bt / bn:.4f}" if bn else "") + f"   missed: {compact(bmiss)}",
        f"    B reviewed image-content dropped   = {it}/{inn}" + (f" = {it / inn:.4f}" if inn else "") + f"   missed: {compact(imiss)}",
        f"    C reviewed blank/separator trigger = {kt}/{kn}   {compact(ktrig)}",
        f"    D unreviewed trigger               = {ut}/{un} = {ut / un:.4f}   pages: {compact(utrig)}",
        f"    E all trigger pages ({len(res['all'])}): {compact(res['all'])}",  # type: ignore[arg-type]
    ]


def evaluate_extra(det_pred: Callable[[dict[str, str]], bool], rows: dict[tuple[str, int], dict[str, str]]) -> str:
    noncontent = [k for k in rows if reviewed_label(k) in NON_CONTENT_LABELS]
    trig = [k for k in noncontent if det_pred(rows[k])]
    return f"    C' reviewed non-content (blank+header_footer+cover) trigger = {len(trig)}/{len(noncontent)}   {compact(trig)}"


def code_dependency_evidence(repo_root: str) -> list[str]:
    """§21：读实际代码，报告 BM25 / renderer 是否实现、是否读取 section，以及本脚本的依赖。"""
    out: list[str] = []
    for sub in ("components/retrievers", "components/generators", "components/chunkers", "components/embedders", "serve"):
        d = os.path.join(repo_root, sub)
        files = sorted(f for f in os.listdir(d) if f.endswith(".py"))
        detail = []
        for f in files:
            with open(os.path.join(d, f), encoding="utf-8") as handle:
                text = handle.read()
            detail.append(f"{f}(lines={len(text.splitlines())}, mentions_section={'section' in text})")
        out.append(f"    {sub}: {', '.join(detail) or '(no .py)'}")
    with open(os.path.join(repo_root, "core", "pipeline.py"), encoding="utf-8") as handle:
        pipe = handle.read()
    out.append(f"    core/pipeline.py: raises NotImplementedError={'raise NotImplementedError' in pipe}, mentions_section={'section' in pipe}")
    with open(os.path.abspath(__file__), encoding="utf-8") as handle:
        me = handle.read()
    imports = sorted(set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", me, flags=re.MULTILINE)))
    out.append(f"    本脚本 import: {imports}")
    out.append(f"    本脚本是否 import kaiva_pdf: {'kaiva_pdf' in ' '.join(imports)}；"
               f"是否读取 Chunk.section / corpus section 字段: {'[\"section\"]' in me}")
    return out


def write_log(args: argparse.Namespace, inputs: Inputs, rows: dict[tuple[str, int], dict[str, str]],
              strata: dict[tuple[str, int], list[str]], sample: dict[tuple[str, int], list[str]],
              timing: dict[str, float], pilot_lines: list[str]) -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out: list[str] = []
    w = out.append

    w("OCR fallback Phase A.1 —— rendered 视觉信号调查与 detector 对比")
    w("=" * 78)
    w("§A 环境指纹（确定性段）")
    w(f"  python     = {platform.python_version()}")
    w(f"  numpy      = {np.__version__}")
    w(f"  Pillow     = {pillow_version()}")
    w(f"  pixel path = pdftoppm -gray → PGM(P5) → numpy.frombuffer")
    for tool in ("pdftoppm", "pdfimages", "pdfinfo"):
        w(f"  {tool:<10} = {tool_version(tool)}")
    w(f"  git_commit = {run_cmd(['git', '-C', repo_root, 'rev-parse', 'HEAD']).strip()}")
    w(f"  script     = scripts/ocr_visual_survey.py sha256={file_sha256(os.path.abspath(__file__))}")
    w(f"  phase_a    = {args.phase_a_csv} sha256={inputs.phase_a_sha256}")
    w(f"  corpus     = {args.corpus} sha256={inputs.corpus_sha256} chunks={inputs.chunk_count}（与冻结值一致，已校验）")
    for doc_id in sorted(inputs.files):
        f = inputs.files[doc_id]
        w(f"  pdf {doc_id:<5}  = {json.dumps(f['filename'], ensure_ascii=False)} pages={f['pages']} sha256={f['sha256']}")
    w(f"  CHUNK_MIN_CHARS (contracts) = {contracts.CHUNK_MIN_CHARS}")
    w("")

    w("§B 定义与判据（先于结果写下）")
    w(f"  B.1 rasterization: pdftoppm -gray -r DPI，整份文档按连续页段一次调用。DPI_LOW={DPI_LOW}（全量）"
      f" DPI_HIGH={DPI_HIGH}（策略={FULL_100DPI_STRATEGY}）DPI_REVIEW_MAX={DPI_REVIEW_MAX}（仅 TACM p.55 等关键页）")
    w(f"  B.2 nonwhite(t) := 灰度 < t，t ∈ {NONWHITE_THRESHOLDS}，仅作 sensitivity，不宣布 production 阈值")
    w(f"      bbox：该阈值下 nonwhite 的最小外接矩形；无 nonwhite → bbox 与 ink_bbox_area_ratio 为空（null），不写 0")
    w(f"      分区（行索引）：top=[0, floor(0.15h))  middle=[floor(0.15h), floor(0.85h))  bottom=[floor(0.85h), h)")
    w(f"      active row(t, f) := 该行 nonwhite 数 >= max(1, ceil(f × 宽))；active column 同理用高；f ∈ {ACTIVE_FRACTIONS}")
    w("      middle_active_row_ratio := middle 区内 active row 占比")
    w("  B.3 pdfimages -list：object-level 信号（数量 / 像素尺寸 / 类型 / 色彩 / bpc / x-ppi）。")
    w("      ⚠️ object signals != rendered coverage：对象可被裁剪、缩放、遮挡或本身为白底；不参与任何 detector。")
    w("  B.4 人工观察：观察者 = Claude 读 100 dpi（p.55 为 150 dpi）PNG。不是人类 ground truth，需人工复核。")
    w(f"      通用标签 {GENERAL_OBS_LABELS}；TACM 标签 {TACM_OBS_LABELS}")
    w(f"      review 清单确定性：seed={SAMPLE_SEED}；组 A/B 固定，C 全取，D 抽 {GROUP_D_SAMPLE_SIZE}，"
      f"E 抽 {GROUP_E_SAMPLE_SIZE}（body >= 4×CHUNK_MIN_CHARS 的正常页），F 为 d40 middle245 两端各 {GROUP_F_PER_TAIL}（排除已入组与 confirmed_bad）")
    w("  B.5 TACM p.55 判据（看高 DPI 结果前写下）:")
    w("      若 100/150 dpi 在三阈值下 nonwhite 绝对数≈0、middle≈0、肉眼无业务内容 → observation=blank_or_separator，")
    w("        即 detector 不触发它可能是合理行为；若出现稳定 nonwhite 簇（尤其 middle）→ '40 dpi insufficient'，可能是真漏报。")
    w("      无论哪种结果都不修改 confirmed_bad 标签，不为 66/66 调阈值。")
    w("  B.6 detectors（目标 = 升级 OCR 候选，不是判定页面坏）:")
    w("      V1 = Phase A 原 detector B_alpha_token_ratio@t_recall：alpha_token_ratio <= 0（无文本页无定义，恒不触发）。本轮不调。")
    w(f"      V2(t) = low_text AND middle_visual：low_text := parser_body_chars < CHUNK_MIN_CHARS（parser 自身丢页条件，非新阈值）；")
    w(f"              middle_visual := {V2_DPI_PREFIX}_{MIDDLE_METRIC}_t > tau(t)，tau(t) = 已 review 的 dropped 非内容页（{sorted(NON_CONTENT_LABELS)}）")
    w("              的 middle ratio 最大值（不触发任何已 review 反例的最松阈值）。⚠️ 阈值与评估同一批 review 页 → in-sample 乐观。")
    w("      V1∪V2 = text + visual 组合。")
    w("      V3 = V1∪V2 再加 structural（pdffonts）证据；只有当 structural 在 review/confirmed_bad 集上带来 V1∪V2 之外的区分时才提出。")
    w("      指标: A confirmed_bad recall / B reviewed image-content dropped recall / C reviewed blank_or_separator trigger")
    w("            （另报 C' 含 header_footer+cover）/ D unreviewed trigger rate（unreviewed := 非 confirmed_bad 且不在 REVIEW_OBSERVATIONS）/ E 全部触发页")
    w("  B.7 禁止的推理: high ink→OCR required；image object→OCR required；low native text→OCR required；OCR candidate→extraction failure confirmed；")
    w("      detector 没触发 p.55→detector bug；TACM 抽样重复→全部 p.38-103 无 RAG 价值。")
    w("")

    # §1-3
    n_pages = len(rows)
    w("§1 覆盖与失败")
    for prefix in ("d40", "d100", "d150"):
        st = Counter(r[f"{prefix}_render_status"] if not r[f"{prefix}_render_status"].startswith("error") else "error" for r in rows.values())
        errs = sorted(k for k, r in rows.items() if r[f"{prefix}_render_status"].startswith("error"))
        w(f"  {prefix}: {dict(sorted(st.items()))}  errors={compact(errs)}")
    w(f"  pages total = {n_pages}")
    w("  PGM 字节 sha256 逐页写入 CSV（*_pgm_sha256）；CSV 双跑逐字节一致 ⇒ rasterizer 像素输出在本机确定。")
    w("")

    w("§2 DPI 策略")
    w(f"  选择: A = full corpus {DPI_LOW} dpi + full corpus {DPI_HIGH} dpi；{DPI_REVIEW_MAX} dpi 仅关键人工页。")
    w("  依据: pilot（§T，非确定耗时段）实测整份渲染吞吐：40 dpi ≈ 0.007 s/页、100 dpi ≈ 0.014 s/页；外推 1335 页 100 dpi 约 20 s 量级。")
    w("        成本不构成缩小样本的理由，因此不采用分层 100 dpi。分层集合仍写入 d100_strata 列作为分析分组。")
    strata_counts = Counter(s for v in strata.values() for s in v)
    w(f"  d100_strata 分组计数（可多属）: {dict(sorted(strata_counts.items()))}")
    w("")

    groups: dict[str, list[tuple[str, int]]] = {
        "parser_dropped": sorted(k for k, r in rows.items() if r["parser_dropped_short"] == "1"),
        "confirmed_bad": sorted(k for k, r in rows.items() if r["label"] == LABEL_CONFIRMED_BAD),
        "normal_with_chunks": sorted(k for k, r in rows.items() if r["parser_dropped_short"] == "0" and r["label"] != LABEL_CONFIRMED_BAD),
        "extracted_chars_0": sorted(k for k, r in rows.items() if int(r["extracted_chars"]) == 0),
    }
    w("§3 视觉信号分布（最近秩分位）")
    for prefix in ("d40", "d100"):
        for t in NONWHITE_THRESHOLDS:
            for metric in (WHOLE_METRIC, MIDDLE_METRIC, "top_nonwhite_ratio", "bottom_nonwhite_ratio"):
                key = f"{prefix}_{metric}_{t}"
                w(f"  {key}")
                for g, keys in groups.items():
                    vals = [float(rows[k][key]) for k in keys if rows[k][key] != ""]
                    w(f"      {g:<20} {dist(vals)}")
    for prefix in ("d40", "d100"):
        for frac in ACTIVE_FRACTIONS:
            key = f"{prefix}_middle_active_row_ratio_245_{frac_tag(frac)}"
            w(f"  {key}")
            for g, keys in groups.items():
                vals = [float(rows[k][key]) for k in keys if rows[k][key] != ""]
                w(f"      {g:<20} {dist(vals)}")
    w("  40 vs 100 dpi 稳定性（全部页，middle / whole ratio）:")
    for t in NONWHITE_THRESHOLDS:
        for metric in (MIDDLE_METRIC, WHOLE_METRIC):
            a_key, b_key = f"d40_{metric}_{t}", f"d100_{metric}_{t}"
            keys = [k for k in sorted(rows) if rows[k][a_key] != "" and rows[k][b_key] != ""]
            a = [float(rows[k][a_key]) for k in keys]
            bb = [float(rows[k][b_key]) for k in keys]
            diffs = [x - y for x, y in zip(a, bb)]
            ratio = [x / y for x, y in zip(a, bb) if y > 0]
            w(f"      {metric}_{t}: spearman={spearman(a, bb):.4f}  diff(40-100) {dist(diffs)}  ratio(40/100) median={pct(ratio, 50):.3f}")
    w("  注: 40 dpi 抗锯齿使细笔画变宽变灰 → 同页 40 dpi ratio 系统性高于 100 dpi；阈值必须按 DPI 分别定义。")
    w("")

    # §4 pdfimages
    w("§4 pdfimages object signals（object != rendered coverage）")
    for g, keys in groups.items():
        with_img = [k for k in keys if int(rows[k]["img_image_type_count"]) > 0]
        w(f"  {g:<20} pages={len(keys)} with_image_object={len(with_img)}  total_object_pixels {dist([float(rows[k]['img_total_object_pixels']) for k in keys])}")
    reviewed_vbc_dropped = sorted(k for k in rows if reviewed_label(k) == "visual_business_content" and rows[k]["parser_dropped_short"] == "1")
    w("  reviewed image-content dropped 页的 object 情况:")
    for k in reviewed_vbc_dropped:
        r = rows[k]
        w(f"    {k[0]} p{k[1]}: image_objects={r['img_image_type_count']} smask/stencil={r['img_smask_or_stencil_count']} "
          f"max={r['img_max_width_px']}x{r['img_max_height_px']} d40_middle245={r['d40_middle_nonwhite_ratio_245']}")
    no_img_vbc = [k for k in reviewed_vbc_dropped if int(rows[k]["img_image_type_count"]) == 0]
    w(f"  其中无 image object 的页: {compact(no_img_vbc)}")
    logo_like = sum(1 for k in groups["normal_with_chunks"] if int(rows[k]["img_image_type_count"]) > 0)
    w(f"  正常有 chunk 页中带 image object 的比例: {logo_like}/{len(groups['normal_with_chunks'])}"
      "（KAIVA 页眉 logo 本身即图像对象 → '有 image object' 在本语料几乎无区分度）")
    img_low_mid = sorted(k for k, r in rows.items() if int(r["img_image_type_count"]) > 0 and r["d40_middle_nonwhite_ratio_245"] != ""
                         and float(r["d40_middle_nonwhite_ratio_245"]) < 0.01)
    w(f"  有 image object 但 d40 middle245 < 0.01 的页: {len(img_low_mid)}  {compact(img_low_mid)[:600]}")
    w("")

    # §5 TACM p55
    r55 = rows[(TACM, 55)]
    w("§5 TACM p.55")
    for prefix in ("d40", "d100", "d150"):
        w(f"  {prefix}: status={r55[f'{prefix}_render_status']} size={r55[f'{prefix}_width_px']}x{r55[f'{prefix}_height_px']} "
          + " ".join(f"nonwhite_{t}={r55[f'{prefix}_nonwhite_count_{t}']} middle_count_{t}={r55[f'{prefix}_middle_nonwhite_count_{t}']}" for t in NONWHITE_THRESHOLDS)
          + f" gray_mean={r55[f'{prefix}_grayscale_mean']} gray_std={r55[f'{prefix}_grayscale_std']}")
    w(f"  pdfimages: image_objects={r55['img_image_type_count']} all_objects={r55['img_object_count']}；Phase A font_count={r55['font_count']} extracted_chars={r55['extracted_chars']}")
    w(f"  human observation: {REVIEW_OBSERVATIONS[(TACM, 55)]}")
    all_zero = all(r55[f"{p}_nonwhite_count_{t}"] == "0" and r55[f"{p}_middle_nonwhite_count_{t}"] == "0"
                   for p in ("d40", "d100", "d150") for t in NONWHITE_THRESHOLDS)
    if all_zero and REVIEW_OBSERVATIONS[(TACM, 55)][0] == "blank_or_separator":
        w("  按 B.5 判据 → observation=blank_or_separator；V1 不触发它与'无内容'一致，不构成 detector bug 的证据。")
        w("  label review required: YES（confirmed_bad 区间含一张渲染全白页）；本轮不修改标签。")
    else:
        w("  按 B.5 判据 → 高 DPI 出现 nonwhite 或人工观察非空白 → '40 dpi insufficient' 待查；label review required: unresolved")
    w("  未排除的机制: 以白色绘制/被隐藏的可选内容层（OCG）/注释不渲染 —— pdftoppm 默认渲染不会显示，本轮未检查。")
    w("")

    # §6 dropped
    w("§6 88 parser-dropped 页")
    dropped = groups["parser_dropped"]
    for t in NONWHITE_THRESHOLDS:
        vals = [float(rows[k][f"d40_{MIDDLE_METRIC}_{t}"]) for k in dropped]
        w(f"  d40 middle_{t}: {dist(vals)}")
    lab = Counter(reviewed_label(k) or "(unreviewed)" for k in dropped)
    w(f"  review 标签分布（dropped 内）: {dict(sorted(lab.items()))}")
    w("  逐页（doc p | label | font_count | extracted | body | img_obj | d40 mid250/245/235 | d100 mid245 | review）:")
    for k in dropped:
        r = rows[k]
        w(f"    {k[0]:<4} p{k[1]:<4} {r['label']:<13} fonts={r['font_count']:<2} ext={r['extracted_chars']:<5} body={r['parser_body_chars']:<4} "
          f"img={r['img_image_type_count']:<2} d40mid={r['d40_middle_nonwhite_ratio_250']}/{r['d40_middle_nonwhite_ratio_245']}/{r['d40_middle_nonwhite_ratio_235']} "
          f"d100mid245={r['d100_middle_nonwhite_ratio_245']} review={r['review_observation'] or '-'}")
    w("  failure surface（观察，不是规则）: 已 review 的 dropped 页中 visual_business_content 占多数，形态包括扫描件、流程图、")
    w("  图像化表格、网络/组织图、照片；非内容页（页眉页脚页 / 封面 / 空白）同样存在于 dropped 集合 → body<120 ≠ OCR required。")
    w("")

    # §7 TACM sample
    w("§7 TACM p.38-103 视觉抽样（只报告抽样结果，不外推 66 页，不决定是否 OCR）")
    tl = Counter(v[0] for v in TACM_OBSERVATIONS.values())
    w(f"  sampled pages = {sorted(TACM_OBSERVATIONS)}")
    w(f"  counts: " + " ".join(f"{label}={tl.get(label, 0)}" for label in TACM_OBS_LABELS))
    for page in sorted(TACM_OBSERVATIONS):
        r = rows[(TACM, page)]
        label, dpi, note = TACM_OBSERVATIONS[page]
        w(f"    p{page:<4} {label:<28} read@{dpi}dpi ext={r['extracted_chars']:<5} fonts={r['font_count']} d40mid245={r['d40_middle_nonwhite_ratio_245']}  {note}")
    w("")

    # §8 detectors
    w("§8 detector 对比")
    v1 = Detector("V1_text_only", "alpha_token_ratio <= 0", v1_predicate, "Phase A output signals ≈ +0.9 s")
    for line in fmt_eval(v1.name, v1.rule, evaluate(v1, rows)):
        w(line)
    w(evaluate_extra(v1.predicate, rows))
    v2_by_t: dict[int, Detector] = {}
    for prefix in (V2_DPI_PREFIX, V2_AUX_DPI_PREFIX):
        for t in NONWHITE_THRESHOLDS:
            d = derive_v2_threshold(rows, prefix, t)
            key, tau = str(d["key"]), float(d["tau"])  # type: ignore[arg-type]
            w(f"  阈值推导 {key}: 反例(dropped 非内容) n={len(d['neg'])} max={tau:.6f} ({compact([x[1] for x in d['neg'][-1:]])})；"  # type: ignore[index]
              f"正例(dropped image-content) n={len(d['pos'])} min={d['pos'][0][0]:.6f} ({compact([d['pos'][0][1]])})；可分={d['separable']}")  # type: ignore[index]
            w(f"      反例值: " + ", ".join(f"{k[0]}p{k[1]}={v:.4f}" for v, k in d["neg"]))  # type: ignore[union-attr]
            w(f"      正例最低 5: " + ", ".join(f"{k[0]}p{k[1]}={v:.4f}" for v, k in d["pos"][:5]))  # type: ignore[index]

            def pred(row: dict[str, str], _key: str = key, _tau: float = tau) -> bool:
                return low_text(row) and row[_key] != "" and float(row[_key]) > _tau

            det = Detector(f"V2_{prefix}_t{t}", f"parser_body_chars < {contracts.CHUNK_MIN_CHARS} AND {key} > {tau:.6f}", pred, "rendered")
            for line in fmt_eval(det.name, det.rule, evaluate(det, rows)):
                w(line)
            w(evaluate_extra(det.predicate, rows))
            if prefix == V2_DPI_PREFIX:
                v2_by_t[t] = det
    for t, det in v2_by_t.items():
        def union(row: dict[str, str], _d: Detector = det) -> bool:
            return v1_predicate(row) or _d.predicate(row)
        name = f"V1_or_V2_{V2_DPI_PREFIX}_t{t}"
        for line in fmt_eval(name, f"({v1.rule}) OR ({det.rule})", evaluate(Detector(name, "", union, ""), rows)):
            w(line)
        w(evaluate_extra(union, rows))
    w("  V3 structural 增益检查（基于 V1∪V2_d40_t245 的漏检/误触发，是否有 pdffonts 信号能单独区分）:")
    base = v2_by_t[245]

    def union245(row: dict[str, str]) -> bool:
        return v1_predicate(row) or base.predicate(row)

    res = evaluate(Detector("u", "", union245, ""), rows)
    missed = list(res["bad"][2]) + list(res["img"][2])  # type: ignore[index]
    w(f"    V1∪V2 漏检: {compact(missed)}")
    for k in missed:
        r = rows[k]
        w(f"      {k[0]} p{k[1]}: font_count={r['font_count']} extracted={r['extracted_chars']} img={r['img_image_type_count']} review={r['review_observation'] or r['label']}")
    fonts0_dropped = sorted(k for k, r in rows.items() if r["font_count"] == "0")
    w(f"    font_count == 0 的全部页: {compact(fonts0_dropped)}；其 review: "
      + ", ".join(f"{k[0]}p{k[1]}={reviewed_label(k) or rows[k]['label']}" for k in fonts0_dropped))
    missed_blank = all(rows[k]["d100_nonwhite_count_250"] == "0" for k in missed)
    f0_labels = {reviewed_label(k) for k in fonts0_dropped}
    if missed_blank and {"visual_business_content", "blank_or_separator"} <= f0_labels:
        w("    结论（观察）: V1∪V2 的漏检全部是 100 dpi 渲染全白页；font_count==0 同时覆盖已 review 的扫描/图像页与全白页，")
        w("    不能区分二者 → structural 信号未显示出 V1∪V2 之外的区分价值 → 本轮不提出 V3 规则；+55.8 s 成本无对应收益证据。")
    else:
        w("    结论: 漏检并非全为渲染全白页，或 font_count==0 未同时覆盖两类 → structural 增益 unresolved，需逐页复核。")
    w("")

    w("§9 信号泛化边界")
    tags = (
        ("alpha_token_ratio (V1)", "language-dependent（依赖 ASCII 拉丁字母词；中文/印地语页会被误判为无词）", "layout-agnostic"),
        ("parser_body_chars", "language-agnostic（字符计数）", "document-layout-dependent（依赖 KAIVA 页眉剥离逻辑）"),
        ("nonwhite / middle ratio", "language-agnostic", "layout-dependent：页面尺寸（CRM p.74 超大幅面稀释）、页眉占比、分区比例 15/85、DPI"),
        ("active row/column ratio", "language-agnostic", "layout-dependent：栏宽、表格线、底纹"),
        ("pdfimages object signals", "language-agnostic", "producer-dependent：同一视觉效果可以是图像或矢量；不等于显示面积"),
        ("pdffonts structural", "language-agnostic", "producer-dependent（Type3/Custom 编码随生成工具而变）"),
    )
    for name, lang, layout in tags:
        w(f"  {name:<28} | {lang} | {layout}")
    w("  visual trigger != useful OCR content：logo / 照片 / 封面 / 空模板表格同样产生 ink（见 EMM p.113 照片页、ERM p.36 空表格）。")
    w("  本 9 份 PDF 上的可分性不是一般规律；阈值 in-sample。")
    w("")

    w("§10 §21 代码依赖证据（section source line 未剥离 与 本 visual detector）")
    for line in code_dependency_evidence(repo_root):
        w(line)
    w("")

    w("§11 review 清单（组 → 观察）")
    for key in sorted(sample):
        obs = REVIEW_OBSERVATIONS.get(key)
        tobs = TACM_OBSERVATIONS.get(key[1]) if key[0] == TACM else None
        w(f"  {key[0]:<4} p{key[1]:<4} groups={'|'.join(sample[key])} general={obs[0] if obs else '-'} tacm={tobs[0] if tobs else '-'} "
          f"note={(obs or tobs or ('', 0, ''))[2]}")
    w("")

    w("§T 耗时（⚠️ 非确定段；确定性比较时排除本段及其后全部内容）")
    for k in sorted(timing):
        w(f"  {k} = {timing[k]:.3f}")
    n = len(rows)
    render40 = timing.get("d40_render_s", 0.0) + timing.get("d40_signal_s", 0.0)
    w("  production ingest 增量估算（相对 build_corpus ≈ 2.8 s）:")
    w(f"    text-only (Phase A output signals)       ≈ +{PHASE_A_OUTPUT_SIGNALS_S:.1f} s")
    w(f"    text + rendered visual 40 dpi            ≈ +{PHASE_A_OUTPUT_SIGNALS_S + render40:.1f} s  (40 dpi render+signal 实测 {render40:.2f} s / {n} 页)")
    w(f"    text + visual + pdffonts                 ≈ +{PHASE_A_OUTPUT_SIGNALS_S + render40 + PHASE_A_PDFFONTS_S:.1f} s")
    w(f"    pdfimages scan（辅助通道，若使用）         ≈ +{timing.get('pdfimages_scan_s', 0.0):.2f} s")
    for line in pilot_lines:
        w(line)

    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")

if __name__ == "__main__":
    raise SystemExit(main())
