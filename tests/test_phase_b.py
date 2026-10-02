"""Phase B 确定性单元测试（S5c）。

覆盖 S5c prompt §27 的 A–G：状态分离、CASE R/S/A、citation gate、artifact 身份与
不可变性、primary body 单 channel 不变量。

真实语料级的 H（page accounting）与 I（determinism）在
scripts/verify_phase_b_ingest.py 的 integration 验收中执行。

运行: python3 -m unittest tests.test_phase_b -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import citation_gate as cg
from components.parsers import kaiva_pdf as kp
from components.parsers import ocr_artifact as oa
from components.parsers import page_states as ps
from components.parsers import phase_b_ingest as pb
from core import contracts

LONG_CLEAN = ("The Master shall ensure that the vessel is operated in accordance with the Company "
              "safety management system and applicable regulations at all times during the voyage. ")
GARBLED = "0123ÿ1563788ÿ91 6 ÿ1 67 " * 6


def native_page(header: str, body: str) -> str:
    return header + "\n" + body


class TestNativeBodyStates(unittest.TestCase):
    """A. 五轴之一：native_body_status 的四态互斥且确定。"""

    def test_usable(self):
        status, _ = ps.classify_native_body(LONG_CLEAN, "en")
        self.assertEqual(status, ps.NATIVE_USABLE)

    def test_unusable_v1_in_scope(self):
        status, reason = ps.classify_native_body(GARBLED, "en")
        self.assertEqual(status, ps.NATIVE_UNUSABLE)
        self.assertIn("alpha_token_ratio=0", reason)

    def test_insufficient_wins_over_unusable(self):
        """短 body 优先判 insufficient：短文本上的比值统计不稳定。"""
        status, _ = ps.classify_native_body("010213433", "en")
        self.assertEqual(status, ps.NATIVE_INSUFFICIENT)

    def test_v1_scope_guard_non_latin_never_unusable(self):
        """V1 作用域外一律 uncertain，绝不自动判 unusable。"""
        status, reason = ps.classify_native_body(GARBLED, "zh")
        self.assertEqual(status, ps.NATIVE_UNCERTAIN)
        self.assertIn("out_of_scope", reason)

    def test_contradictory_signals_uncertain(self):
        status, _ = ps.classify_native_body(LONG_CLEAN + "\x01\x02", "en")
        self.assertEqual(status, ps.NATIVE_UNCERTAIN)

    def test_body_usable_does_not_imply_metadata_supported(self):
        """body usable 不推出 citation metadata supported（两个轴独立）。"""
        status, _ = ps.classify_native_body(LONG_CLEAN, "en")
        self.assertEqual(status, ps.NATIVE_USABLE)
        gate = cg.evaluate(cg.MetadataCandidate("2.1", cg.KIND_TITLE_LINE_FALLBACK, cg.CHANNEL_NATIVE, "2.1 - Foo"),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)


class TestCitationGate(unittest.TestCase):
    """E. citation gate：explicit_supported 只表示证据支持的显式抽取。"""

    def _native(self, value, kind=cg.KIND_EXPLICIT_LABEL, raw="SECTION   2.1"):
        return cg.MetadataCandidate(value, kind, cg.CHANNEL_NATIVE, raw)

    def test_explicit_clean_provenance_supported(self):
        gate = cg.evaluate(self._native("2.1"), cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.EXPLICIT_SUPPORTED)
        self.assertEqual(gate.metadata_source_channel, cg.CHANNEL_NATIVE)

    def test_fallback_is_uncertain_not_failed(self):
        gate = cg.evaluate(self._native("PCL E", cg.KIND_TITLE_LINE_FALLBACK, "PCL E-Learning Matrix Dry"),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)

    def test_inherited_is_uncertain(self):
        gate = cg.evaluate(cg.MetadataCandidate("9", cg.KIND_INHERITED, cg.CHANNEL_NATIVE, None),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)

    def test_candidate_conflict_is_uncertain_and_flagged(self):
        gate = cg.evaluate(self._native("9"),
                           cg.MetadataCandidate("i)", cg.KIND_EXPLICIT_LABEL, cg.CHANNEL_OCR, "SECTION i)"), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)
        self.assertTrue(gate.metadata_conflict)
        self.assertEqual(gate.metadata_source_channel, cg.CHANNEL_NONE)

    def test_corrupted_value_failed(self):
        gate = cg.evaluate(self._native("0123ÿ1563788"), cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.FAILED)
        self.assertIn("mechanical_damage", gate.reason_code)

    def test_damaged_candidate_is_eliminated_not_treated_as_conflict(self):
        """损坏值先被机械判据淘汰；它不得作为否决票与另一 channel 的干净值"冲突"。

        Design Freeze §2.3 的 failed 判据是"值明确损坏【且不存在可接受 candidate】"。
        """
        gate = cg.evaluate(self._native("0123\u00ff1563788", cg.KIND_TITLE_LINE_FALLBACK, "0123"),
                           cg.MetadataCandidate("5", cg.KIND_EXPLICIT_LABEL, cg.CHANNEL_OCR, "SECTION 5"), True)
        self.assertEqual(gate.status, cg.EXPLICIT_SUPPORTED)
        self.assertFalse(gate.metadata_conflict)
        self.assertEqual(gate.metadata_source_channel, cg.CHANNEL_OCR)

    def test_all_candidates_damaged_failed(self):
        gate = cg.evaluate(self._native("0123\u00ff"),
                           cg.MetadataCandidate("\x01\x02", cg.KIND_EXPLICIT_LABEL, cg.CHANNEL_OCR, "x"), True)
        self.assertEqual(gate.status, cg.FAILED)
        self.assertIn("mechanical_damage", gate.reason_code)

    def test_no_candidate_failed(self):
        gate = cg.evaluate(cg.none_candidate(cg.CHANNEL_NATIVE), cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.FAILED)

    def test_page_identity_mismatch_failed(self):
        gate = cg.evaluate(self._native("2.1"), cg.none_candidate(cg.CHANNEL_OCR), False)
        self.assertEqual(gate.status, cg.FAILED)
        self.assertEqual(gate.reason_code, "page_identity_mismatch")

    def test_known_vocabulary_cannot_upgrade_uncertain(self):
        """TACM p.100 型反例：值 `"9"` 看起来合法、甚至与真实章节集合碰撞，

        但只要来源是 fallback / inherited，就不得升级为 explicit_supported。
        gate 的签名里根本没有 vocabulary 入口 —— 结构上不可能走 shortcut。
        """
        gate = cg.evaluate(cg.MetadataCandidate("9", cg.KIND_TITLE_LINE_FALLBACK, cg.CHANNEL_NATIVE, "9"),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)
        import inspect
        params = list(inspect.signature(cg.evaluate).parameters)
        self.assertEqual(params, ["native", "ocr", "page_identity_ok"])

    def test_explicit_supported_is_not_semantic_verification(self):
        """`"9"` 由显式标签取得即可 explicit_supported —— 这只表示抽取有证据，

        不表示语义位置正确。测试锁定该语义边界，防止后续把它当 verified 使用。
        """
        gate = cg.evaluate(self._native("9", raw="SECTION      9"), cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.EXPLICIT_SUPPORTED)
        self.assertNotIn("verified", gate.status)

    def test_rejected_terminology_absent(self):
        self.assertNotIn("verified_structural", cg.CITATION_STATES)


class TestPrimaryBodyInvariant(unittest.TestCase):
    """G. primary body 单 channel：结构上不可能出现 native+OCR 拼接。"""

    def test_returns_exactly_one_channel_text(self):
        for native_status in ps.NATIVE_BODY_STATES:
            for ocr_status in ps.OCR_BODY_STATES:
                body, channel = pb.select_primary_body("NATIVE_TEXT", "OCR_TEXT", native_status, ocr_status)
                self.assertIn(body, ("NATIVE_TEXT", "OCR_TEXT", ""),
                              f"{native_status}/{ocr_status} 产生了非单 channel 正文")
                self.assertNotIn("NATIVE_TEXTOCR_TEXT", body)
                if channel == pb.BODY_CHANNEL_NATIVE:
                    self.assertEqual(body, "NATIVE_TEXT")
                elif channel == pb.BODY_CHANNEL_OCR:
                    self.assertEqual(body, "OCR_TEXT")

    def test_no_concatenation_symbol_in_source(self):
        """源码层面确认没有 native+ocr 拼接路径。"""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "components/parsers/phase_b_ingest.py")
        src = open(path, encoding="utf-8").read()
        for forbidden in ("native_body + ocr", "ocr_body + native", 'native_body + "\\n" + ocr'):
            self.assertNotIn(forbidden, src)


class TestCaseRandS(unittest.TestCase):
    """B / C：CASE R 与 CASE S 的 body 与 metadata 语义。"""

    HEADER = ("                          DOCUMENT ID   TACM\n"
              "Training Manual           SECTION       5\n"
              "                          REV. NO.      1.0\n")
    OCR_HEADER = "DOCUMENT ID TACM\nSECTION 5\nREV. NO. 1.0\n"

    def _artifact(self, text: str, page: int = 60) -> dict:
        return {"source_hash": "S", "pdf_page": page, "text": text,
                "ocr_engine": "tesseract", "ocr_engine_version": "5.5.3",
                "ocr_params_digest": "P", "langpack_identity_digest": "L",
                "rasterizer": "pdftoppm", "rasterizer_version": "26.09.0", "raster_dpi": 300,
                "confidence_stats": {"mean_conf": 95.0}, "ocr_artifact_sha256": "A"}

    def test_case_r_ocr_replaces_garbled_native(self):
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=60,
                           native_text=GARBLED, ocr_artifact=self._artifact(self.OCR_HEADER + LONG_CLEAN))
        res = pb.process_page(inp)
        self.assertEqual(res.record["native_body_status"], ps.NATIVE_UNUSABLE)
        self.assertEqual(res.record["body_source_channel"], pb.BODY_CHANNEL_OCR)
        self.assertTrue(res.chunks)
        for chunk in res.chunks:                       # native 乱码不得进入 body
            self.assertNotIn("ÿ", chunk.text)
        self.assertEqual(res.record["remediation_action"], pb.ACTION_ADMITTED_OCR)

    def test_case_r_metadata_uncertain_not_admitted(self):
        """OCR 正文可用，但两个 channel 的 metadata candidate 冲突 → 不入 corpus。"""
        native_text = self.HEADER + GARBLED          # native 有显式 SECTION=5
        ocr_text = "DOCUMENT ID TACM\nSECTION 7\n" + LONG_CLEAN   # OCR 读成 7
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=60,
                           native_text=native_text, ocr_artifact=self._artifact(ocr_text))
        res = pb.process_page(inp)
        self.assertTrue(res.record["metadata_conflict"])
        self.assertEqual(res.record["citation_metadata_status"], cg.UNCERTAIN)
        self.assertEqual(res.chunks, [])
        self.assertTrue(str(res.record["remediation_action"]).startswith(pb.ACTION_QUARANTINED))

    def test_case_r_keeps_both_candidates(self):
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=60,
                           native_text=self.HEADER + GARBLED,
                           ocr_artifact=self._artifact("DOCUMENT ID TACM\nSECTION 7\n" + LONG_CLEAN))
        rec = pb.process_page(inp).record
        self.assertEqual(rec["native_metadata_candidate"], "5")
        self.assertEqual(rec["ocr_metadata_candidate"], "7")

    def test_case_s_ocr_primary_native_residual_not_concatenated(self):
        native_text = self.HEADER + "Figure 1\n"      # 残余正文 < CHUNK_MIN_CHARS
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=112,
                           native_text=native_text,
                           ocr_artifact=self._artifact(self.OCR_HEADER + LONG_CLEAN, page=112))
        res = pb.process_page(inp)
        self.assertEqual(res.record["native_body_status"], ps.NATIVE_INSUFFICIENT)
        self.assertEqual(res.record["body_source_channel"], pb.BODY_CHANNEL_OCR)
        joined = "\n".join(c.text for c in res.chunks)
        self.assertNotIn("Figure 1", joined)          # native 残余不与 OCR 拼接
        self.assertIn("safety management system", joined)

    def test_case_s_body_and_metadata_channels_may_differ(self):
        """允许 body=ocr、metadata=native（两者相等时记 native），但必须有 provenance。"""
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=112,
                           native_text=self.HEADER + "x\n",
                           ocr_artifact=self._artifact(self.OCR_HEADER + LONG_CLEAN, page=112))
        rec = pb.process_page(inp).record
        self.assertEqual(rec["body_source_channel"], pb.BODY_CHANNEL_OCR)
        self.assertIn(rec["metadata_source_channel"], (cg.CHANNEL_NATIVE, cg.CHANNEL_OCR))
        self.assertIsNotNone(rec["native_metadata_candidate"])

    def test_missing_artifact_fails_closed(self):
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=60,
                           native_text=GARBLED, ocr_artifact=None)
        with self.assertRaises(pb.PageIngestError):
            pb.process_page(inp)

    def test_artifact_identity_mismatch_fails_closed(self):
        art = self._artifact(self.OCR_HEADER + LONG_CLEAN)
        art["pdf_page"] = 61
        inp = pb.PageInput(doc_id="TACM", doc_name="t.pdf", source_hash="S", pdf_page=60,
                           native_text=GARBLED, ocr_artifact=art)
        with self.assertRaises(pb.PageIngestError):
            pb.process_page(inp)


class TestCaseA(unittest.TestCase):
    """D. CASE A：usable native 页不被自动 OCR augment，正文不变。"""

    def test_usable_native_not_augmented(self):
        header = "                 DOCUMENT ID   QMM\n                 SECTION       17\n"
        inp = pb.PageInput(doc_id="QMM", doc_name="q.pdf", source_hash="S", pdf_page=110,
                           native_text=header + LONG_CLEAN, ocr_artifact=None, visual_suspected=True)
        res = pb.process_page(inp)
        self.assertEqual(res.record["native_body_status"], ps.NATIVE_USABLE)
        self.assertFalse(res.record["ocr_attempted"])
        self.assertEqual(res.record["body_source_channel"], pb.BODY_CHANNEL_NATIVE)
        self.assertEqual(res.record["page_content_completeness_status"], ps.COMPLETENESS_NOT_ASSESSED)
        self.assertIn(LONG_CLEAN.strip()[:40], "\n".join(c.text for c in res.chunks))

    def test_visual_signal_never_triggers_ocr(self):
        """视觉信号为 True 也不改变动作（diagnostic only）。"""
        self.assertFalse(pb.needs_ocr(ps.NATIVE_USABLE))
        self.assertTrue(pb.needs_ocr(ps.NATIVE_INSUFFICIENT))
        self.assertTrue(pb.needs_ocr(ps.NATIVE_UNUSABLE))
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "ingest/plan_ocr_targets.py"), encoding="utf-8").read()
        for token in ("active_row", "ink", "bbox", "visual"):
            self.assertNotIn(f"if {token}", src)


class TestArtifactStore(unittest.TestCase):
    """F. artifact identity / immutability / digest。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ocrstore_")
        self.store = oa.OcrArtifactStore(self.root)
        self.identity = oa.build_cache_identity("SRC", 7, "26.09.0", "5.5.3", "LANGDIGEST")
        self.payload = {
            "schema_version": 1, "source_hash": "SRC", "pdf_page": 7,
            "rasterizer": "pdftoppm", "rasterizer_version": "26.09.0", "raster_dpi": 300,
            "raster_sha256": "R", "ocr_engine": "tesseract", "ocr_engine_version": "5.5.3",
            "langpack": "eng", "langpack_identity_digest": "LANGDIGEST",
            "ocr_params_digest": oa.ocr_params_digest(), "text": "hello\n",
            "text_raw_sha256": "T", "confidence_stats": {"mean_conf": 90.0},
        }

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_candidate_not_consumable_before_acceptance(self):
        self.store.write_candidate(self.identity, self.payload)
        with self.assertRaises(oa.OcrArtifactError):
            self.store.load_accepted(self.identity)

    def test_accept_then_load_roundtrip(self):
        path, sha = self.store.write_candidate(self.identity, self.payload)
        entry = self.store.accept(self.identity, path, sha)
        loaded = self.store.load_accepted(self.identity)
        self.assertEqual(loaded["text"], "hello\n")
        self.assertEqual(loaded["ocr_artifact_sha256"], entry["ocr_artifact_sha256"])

    def test_same_key_different_bytes_not_silently_overwritten(self):
        path, sha = self.store.write_candidate(self.identity, self.payload)
        self.store.accept(self.identity, path, sha)
        other = dict(self.payload, text="different\n")
        path2, sha2 = self.store.write_candidate(self.identity, other)
        with self.assertRaises(oa.OcrArtifactError):
            self.store.accept(self.identity, path2, sha2)
        self.assertEqual(self.store.load_accepted(self.identity)["text"], "hello\n")
        self.store.record_reproducibility_event(self.identity, sha, sha2, "unit test")
        self.assertTrue(os.path.isfile(os.path.join(self.root, oa.REPRODUCIBILITY_LOG_FILENAME)))

    def test_same_key_same_bytes_is_idempotent(self):
        path, sha = self.store.write_candidate(self.identity, self.payload)
        first = self.store.accept(self.identity, path, sha)
        second = self.store.accept(self.identity, path, sha)
        self.assertEqual(first["ocr_artifact_sha256"], second["ocr_artifact_sha256"])

    def test_digest_mismatch_fails(self):
        path, sha = self.store.write_candidate(self.identity, self.payload)
        entry = self.store.accept(self.identity, path, sha)
        target = os.path.join(self.root, entry["artifact_path"])
        os.chmod(target, 0o644)
        with open(target, "ab") as handle:
            handle.write(b" ")
        with self.assertRaises(oa.OcrArtifactError):
            self.store.load_accepted(self.identity)

    def test_page_or_source_mismatch_fails(self):
        bad = dict(self.payload, pdf_page=8)
        with self.assertRaises(oa.OcrArtifactError):
            self.store.write_candidate(self.identity, bad)
        bad2 = dict(self.payload, source_hash="OTHER")
        with self.assertRaises(oa.OcrArtifactError):
            self.store.write_candidate(self.identity, bad2)

    def test_cache_identity_is_nine_tuple(self):
        key = json.loads(self.identity.canonical())
        self.assertEqual(sorted(key), sorted([
            "source_hash", "pdf_page", "rasterizer", "rasterizer_version", "raster_dpi",
            "ocr_engine", "ocr_engine_version", "langpack_identity_digest", "ocr_params_digest"]))
        self.assertNotIn("source_pdf_sha256", key)


class TestContractUnchanged(unittest.TestCase):
    """Chunk contract 与 source_hash 语义未变。"""

    def test_chunk_fields_unchanged(self):
        names = {f.name for f in contracts.dataclasses.fields(contracts.Chunk)} if hasattr(contracts, "dataclasses") else None
        import dataclasses as dc
        names = {f.name for f in dc.fields(contracts.Chunk)}
        self.assertEqual(names, {
            "id", "text", "doc_id", "doc_name", "section", "section_title", "pdf_page",
            "printed_page", "issued_by", "revision", "lang", "image_ids", "source_hash"})

    def test_source_hash_is_source_pdf_digest(self):
        header = "                 DOCUMENT ID   QMM\n                 SECTION       17\n"
        inp = pb.PageInput(doc_id="QMM", doc_name="q.pdf", source_hash="SRCPDFSHA", pdf_page=1,
                           native_text=header + LONG_CLEAN)
        res = pb.process_page(inp)
        self.assertTrue(res.chunks)
        self.assertEqual(res.chunks[0].source_hash, "SRCPDFSHA")



class TestWeakEvidenceVsDamage(unittest.TestCase):
    """超长值属"弱结构证据"（uncertain），不是"明确损坏"（failed）。"""

    def test_overlong_value_is_uncertain_not_failed(self):
        long_value = "Risk Rating " * 20
        gate = cg.evaluate(cg.MetadataCandidate(long_value, cg.KIND_TITLE_LINE_FALLBACK,
                                                cg.CHANNEL_NATIVE, long_value),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.UNCERTAIN)
        self.assertIn("weak_structural_evidence", gate.reason_code)

    def test_corruption_still_failed(self):
        gate = cg.evaluate(cg.MetadataCandidate("\x01\x02", cg.KIND_EXPLICIT_LABEL, cg.CHANNEL_NATIVE, "x"),
                           cg.none_candidate(cg.CHANNEL_OCR), True)
        self.assertEqual(gate.status, cg.FAILED)


class TestOcrHeaderStripping(unittest.TestCase):
    """S5c post-QA：OCR channel 的页眉/页脚结构行剥离（只作用于 OCR channel）。"""

    OCR_HEADER = (". DOCUMENT ID CRM\n"
                  "Cyber Risk Management Manual ISSUED BY FLEET IT\n"
                  ". SECTION GP 1.2\n")

    def test_ocr_header_table_lines_removed(self):
        view = kp.ocr_page_view(self.OCR_HEADER + "\n" + LONG_CLEAN)
        self.assertNotIn("DOCUMENT ID", view["body"])
        self.assertNotIn("SECTION GP 1.2", view["body"])
        self.assertIn("The Master shall ensure", view["body"])

    def test_body_sentence_with_section_word_is_kept(self):
        body = ("Personnel shall be certified as per STCW Section A - II/4 before assignment to "
                "bridge watchkeeping duties on any vessel operated by the Company. ") * 3
        view = kp.ocr_page_view(self.OCR_HEADER + "\n" + body)
        self.assertIn("STCW Section A - II/4", view["body"])

    def test_section_line_inside_body_region_is_kept(self):
        filler = "Operational guidance continues for this chapter of the manual. \n" * 12
        view = kp.ocr_page_view(filler + "SECTION GP 1.2\n" + filler)
        self.assertIn("SECTION GP 1.2", view["body"])

    def test_footer_region_label_line_removed(self):
        view = kp.ocr_page_view(LONG_CLEAN + "\n\n" + "REV. NO. 03 ISSUE DATE 01-Jan-2021\n")
        self.assertNotIn("ISSUE DATE", view["body"])

    def test_native_channel_unaffected_by_ocr_rule(self):
        """同一段文本走 native view 时，单空格页眉行不被本规则剥离（native 语义不变）。"""
        text = self.OCR_HEADER + "\n" + LONG_CLEAN
        self.assertIn("DOCUMENT ID", str(kp.native_page_view(text)["body"]))

    def test_metadata_candidate_extracted_from_raw_ocr_text(self):
        """body 剥离不影响 citation candidate —— candidate 从原始 OCR 文本抽取。"""
        header = ". DOCUMENT ID CRM\nSECTION GP 1.2\n"
        cand = cg.extract_ocr_candidate(header + "\n" + LONG_CLEAN, kp.HEADER_SCAN_LINES)
        self.assertEqual(cand.value, "GP 1.2")
        self.assertNotIn("SECTION GP 1.2", kp.ocr_page_view(header + "\n" + LONG_CLEAN)["body"])
        self.assertEqual(cand.source_kind, cg.KIND_EXPLICIT_LABEL)

    def test_header_only_page_yields_empty_body(self):
        """整页只有页眉时 body 为空字符串，而不是异常、也不是原样返回。"""
        self.assertEqual(kp.ocr_page_view(self.OCR_HEADER)["body"], "")

    def test_rule_is_document_agnostic(self):
        """不同 doc_id 的同形页眉被同样剥离（规则不含文档/页码特例）。"""
        for doc in ("QMM", "SMM", "TACM"):
            header = f". DOCUMENT ID {doc}\n. SECTION 4.1\n"
            self.assertNotIn("DOCUMENT ID", kp.ocr_page_view(header + "\n" + LONG_CLEAN)["body"])


class TestActionIdentityVsReviewAttribute(unittest.TestCase):
    """terminal action 身份不得编码 review 属性（+REQUIRE_REVIEW 回归）。"""

    def test_terminal_actions_are_exactly_four_and_suffix_free(self):
        self.assertEqual(len(pb.TERMINAL_ACTIONS), 4)
        for action in pb.TERMINAL_ACTIONS:
            self.assertNotIn("+", action)
            self.assertNotIn("REQUIRE_REVIEW", action)

    def test_require_review_page_keeps_plain_admitted_action(self):
        """legacy uncertain 页要求复核，但 action 仍是裸的 ADMITTED_NATIVE 且仍入库。"""
        header = "                 DOCUMENT ID   QMM\n                 SECTION       " + "X" * 100 + "\n"
        inp = pb.PageInput(doc_id="QMM", doc_name="q.pdf", source_hash="H", pdf_page=1,
                           native_text=header + LONG_CLEAN)
        res = pb.process_page(inp)
        self.assertEqual(res.record["remediation_action"], pb.ACTION_ADMITTED_NATIVE)
        self.assertIn(res.record["remediation_action"], pb.TERMINAL_ACTIONS)
        self.assertTrue(res.record["require_review"])
        self.assertTrue(res.chunks, "require_review 不得使 chunk 归零")

    def test_admission_predicate_holds_for_review_pages(self):
        header = "                 DOCUMENT ID   QMM\n                 SECTION       " + "X" * 100 + "\n"
        res = pb.process_page(pb.PageInput(doc_id="QMM", doc_name="q.pdf", source_hash="H",
                                           pdf_page=2, native_text=header + LONG_CLEAN))
        self.assertIn(res.record["remediation_action"],
                      (pb.ACTION_ADMITTED_NATIVE, pb.ACTION_ADMITTED_OCR))



class TestOcrFailureReasonTaxonomy(unittest.TestCase):
    """S5c closeout：ocr_body_status 仍是四态，三类失败只由 reason code 区分。"""

    OCR_HEADER_ONLY = (". DOCUMENT ID CRM\n"
                       "Cyber Risk Management Manual ISSUED BY FLEET IT\n"
                       ". SECTION GP 1.2\n"
                       "UNCONTROLLED WHEN PRINTED\n")

    def test_r1_engine_failure(self):
        """R1 选为 OCR 目标却没有 accepted artifact → failed + engine-failure reason。"""
        status, reason = ps.classify_ocr_body(None, artifact_present=False, raw_ocr_text=None,
                                              ocr_attempted=True)
        self.assertEqual(status, ps.OCR_FAILED)
        self.assertEqual(reason, ps.OCR_REASON_ENGINE_FAILED)

    def test_r1b_not_attempted_is_not_a_failure(self):
        status, reason = ps.classify_ocr_body(None, artifact_present=False, raw_ocr_text=None,
                                              ocr_attempted=False)
        self.assertEqual(status, ps.OCR_NOT_ATTEMPTED)
        self.assertEqual(reason, ps.OCR_REASON_NOT_ATTEMPTED)
        self.assertNotIn(reason, ps.OCR_FAILURE_REASONS)

    def test_r2_raw_ocr_text_empty(self):
        """R2 OCR 执行成功但原文为空 → failed + raw-empty reason。"""
        status, reason = ps.classify_ocr_body("", artifact_present=True, raw_ocr_text="",
                                              ocr_attempted=True)
        self.assertEqual(status, ps.OCR_FAILED)
        self.assertEqual(reason, ps.OCR_REASON_TEXT_EMPTY_RAW)

    def test_r3_empty_after_structural_strip(self):
        """R3 原文非空、剥离后无业务正文 → failed + empty-after-strip，且终态 SKIPPED_NONCONTENT。"""
        raw = self.OCR_HEADER_ONLY
        body = str(kp.ocr_page_view(raw)["body"])
        self.assertEqual(body, "")
        status, reason = ps.classify_ocr_body(body, artifact_present=True, raw_ocr_text=raw,
                                              ocr_attempted=True)
        self.assertEqual(status, ps.OCR_FAILED)
        self.assertEqual(reason, ps.OCR_REASON_EMPTY_AFTER_STRIP)
        res = pb.process_page(pb.PageInput(
            doc_id="CRM", doc_name="c.pdf", source_hash="H", pdf_page=9, native_text="",
            ocr_artifact={"source_hash": "H", "pdf_page": 9, "text": raw}))
        self.assertEqual(res.record["remediation_action"], pb.ACTION_SKIPPED_NONCONTENT)
        self.assertEqual(res.record["ocr_body_reason"], ps.OCR_REASON_EMPTY_AFTER_STRIP)
        self.assertEqual(res.chunks, [])

    def test_r4_three_reasons_are_mutually_exclusive(self):
        """R4 三类归因互不混用，且 C 不得被描述成引擎失败。"""
        raw = self.OCR_HEADER_ONLY
        got = {
            "A": ps.classify_ocr_body(None, False, None, True)[1],
            "B": ps.classify_ocr_body("", True, "", True)[1],
            "C": ps.classify_ocr_body(str(kp.ocr_page_view(raw)["body"]), True, raw, True)[1],
        }
        self.assertEqual(len(set(got.values())), 3, got)
        self.assertEqual(set(got.values()), set(ps.OCR_FAILURE_REASONS))
        self.assertNotIn("engine", got["C"])

    def test_r5_reason_does_not_change_terminal_action_identity(self):
        """R5 reason / require_review 不改变终态 action 身份。"""
        raw = self.OCR_HEADER_ONLY
        res = pb.process_page(pb.PageInput(
            doc_id="CRM", doc_name="c.pdf", source_hash="H", pdf_page=9, native_text="",
            ocr_artifact={"source_hash": "H", "pdf_page": 9, "text": raw}))
        action = res.record["remediation_action"]
        self.assertIn(action, pb.TERMINAL_ACTIONS)
        self.assertNotIn(ps.OCR_REASON_EMPTY_AFTER_STRIP, action)
        self.assertNotIn("+", action)
        self.assertIn(ps.OCR_REASON_EMPTY_AFTER_STRIP, res.record["remediation_reason"])

    def test_r6_reason_patch_is_behaviour_neutral(self):
        """R6 reason-only patch 不改 Chunk schema / body channel / metadata channel /
        citation gate / page identity / 单 primary body 不变量。"""
        header = "                 DOCUMENT ID   QMM\n                 SECTION       17\n"
        inp = pb.PageInput(doc_id="QMM", doc_name="q.pdf", source_hash="SRC", pdf_page=7,
                           native_text=header + LONG_CLEAN)
        res = pb.process_page(inp)
        rec = res.record
        self.assertEqual((rec["doc_id"], rec["pdf_page"], rec["source_hash"]), ("QMM", 7, "SRC"))
        self.assertEqual(rec["body_source_channel"], "native")
        self.assertEqual(rec["ocr_body_status"], ps.OCR_NOT_ATTEMPTED)
        self.assertEqual(rec["citation_metadata_status"], cg.EXPLICIT_SUPPORTED)
        self.assertEqual(rec["metadata_source_channel"], cg.CHANNEL_NATIVE)
        self.assertEqual(set(res.chunks[0].__dict__), {
            "id", "text", "doc_id", "doc_name", "section", "section_title", "pdf_page",
            "printed_page", "issued_by", "revision", "lang", "image_ids", "source_hash"})
        body, channel = pb.select_primary_body(LONG_CLEAN, "ocr body text", ps.NATIVE_INSUFFICIENT,
                                               ps.OCR_USABLE)
        self.assertEqual((body, channel), ("ocr body text", pb.BODY_CHANNEL_OCR))


class TestKnownPagesIntegration(unittest.TestCase):
    """R7 已知页的 integration 回归（production 规则里没有任何 doc/page 特例）。"""

    LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "ingest", "page_quality.jsonl")

    def test_r7_crm_header_only_pages(self):
        if not os.path.exists(self.LEDGER):
            self.skipTest("page_quality.jsonl 不存在（需先跑 build）")
        with open(self.LEDGER, encoding="utf-8") as handle:
            rows = {(r["doc_id"], r["pdf_page"]): r for r in map(json.loads, handle)}
        for page in (3, 23, 67):
            rec = rows[("CRM", page)]
            self.assertEqual(rec["remediation_action"], pb.ACTION_SKIPPED_NONCONTENT, page)
            self.assertEqual(rec["chunk_ids"], [], page)
            self.assertEqual(rec["ocr_body_reason"], ps.OCR_REASON_EMPTY_AFTER_STRIP, page)
            self.assertEqual(rec["ocr_body_status"], ps.OCR_FAILED, page)

if __name__ == "__main__":
    unittest.main()
