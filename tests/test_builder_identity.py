"""canonical 语料构建权威身份导出（ingest/builder_identity.py）的测试。

覆盖:
  T1–T4  名字 / 配置 / 规则指纹确定、可重复、跨进程与哈希种子一致、不含语料哈希/commit/时间/路径
  T5a    真实构建依赖改变 → 身份必须改变（under-binding 检查）
  T5b    只影响打包/检索/运维的依赖改变 → 身份逐字节不变（over-binding 检查）
  T6     与 core.contracts 当前临时推导的【值】一致（只证值一致，不证依赖完整）
  T7     防静默漏登: AST 从 build_corpus.main/build 出发找出构建可达读取的每个模块级常量，
         要求与登记表双向相等；并证明该检查在漏登时真的失败
  另有: 构建代码指纹 tripwire —— 构建路径上任一函数的 AST 变化都会让它失败，
        逼人按 CORPUS_BUILDER_NAME 的版本规则做一次显式决定后再更新钉住的值。

运行: python3 -m unittest tests.test_builder_identity -v
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import contracts  # noqa: E402
from components.parsers import kaiva_pdf  # noqa: E402
from ingest import builder_identity as bi  # noqa: E402

FIRST_PARTY = ("core", "components", "ingest")
ENTRY = "ingest.build_corpus"
ENTRY_FUNCTIONS = ("main", "build")

# 构建路径代码指纹（Python 3.12 的 ast.dump 口径）。变化时先按 builder_identity 的版本规则
# 判断是否递增 CORPUS_BUILDER_NAME，再更新本值 —— 不许为了让测试通过而直接改这里。
PINNED_CONSTRUCTION_CODE_FINGERPRINT = "ab90418c4ec6ea8dc647456e05d137c5cfd74053933f5ad5413e3864a5807bbb"


# ==============================================================================
# 构建路径 AST 扫描（保守: 方法调用按名字匹配任意同名方法，宁多不少）
# ==============================================================================

def _module_path(root: str, module: str) -> str:
    return os.path.join(root, *module.split(".")) + ".py"


def _strip_docstrings(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]


def scan_construction_path(root: str, entry: str, entry_functions: tuple[str, ...],
                           first_party: tuple[str, ...]) -> tuple[set[str], dict[str, str]]:
    """返回 (可达代码读取的模块级常量 "短模块名.常量名" 集合, {可达函数键: 去 docstring 的 ast.dump})。"""
    trees, aliases = {}, {}
    todo = [entry]
    while todo:
        mod = todo.pop()
        if mod in trees or not os.path.isfile(_module_path(root, mod)):
            continue
        with open(_module_path(root, mod), encoding="utf-8") as handle:
            trees[mod] = ast.parse(handle.read())
        _strip_docstrings(trees[mod])
        amap = aliases[mod] = {}
        for node in ast.walk(trees[mod]):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in first_party:
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    if os.path.isfile(_module_path(root, full)):
                        amap[a.asname or a.name] = ("mod", full)
                        todo.append(full)
                    else:
                        amap[a.asname or a.name] = ("name", node.module, a.name)
                        todo.append(node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in first_party:
                        amap[a.asname or a.name] = ("mod", a.name)
                        todo.append(a.name)

    consts, funcs = {}, {}
    for mod, tree in trees.items():
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(t, ast.Name) and t.id.lstrip("_")[:1].isupper():
                        consts[(mod, t.id)] = node
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                funcs[(mod, node.name)] = node
                if isinstance(node, ast.ClassDef):
                    for sub in node.body:
                        if isinstance(sub, ast.FunctionDef):
                            funcs[(mod, f"{node.name}.{sub.name}")] = sub

    def refs(mod: str, node: ast.AST) -> set[tuple[str, str]]:
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                a = aliases[mod].get(n.id)
                out.add((a[1], a[2]) if a and a[0] == "name" else (mod, n.id))
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                a = aliases[mod].get(n.value.id)
                if a and a[0] == "mod":
                    out.add((a[1], n.attr))
                else:
                    out.update(k for k in funcs if k[1].endswith("." + n.attr))
        return out

    reach, todo2 = set(), [(entry, f) for f in entry_functions]
    while todo2:
        key = todo2.pop()
        if key in reach or (key not in funcs and key not in consts):
            continue
        reach.add(key)
        node = funcs.get(key) or consts.get(key)
        if isinstance(node, ast.ClassDef):
            todo2.extend(k for k in funcs if k[0] == key[0] and k[1].startswith(key[1] + "."))
        todo2.extend(refs(key[0], node))

    read = {f"{m.split('.')[-1]}.{c}" for (m, c) in reach if (m, c) in consts}
    code = {f"{m}:{f}": ast.dump(funcs[(m, f)]) for (m, f) in reach if (m, f) in funcs}
    return read, code


def coverage_problems(read: set[str], registry: dict[str, str]) -> tuple[set[str], set[str]]:
    """(构建读取但未登记, 已登记但构建不再读取)。两者都必须为空。"""
    return read - set(registry), set(registry) - read


def code_fingerprint(code: dict[str, str]) -> str:
    joined = "\n".join(f"{k}\n{code[k]}" for k in sorted(code))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


READ_CONSTANTS, CONSTRUCTION_CODE = scan_construction_path(REPO_ROOT, ENTRY, ENTRY_FUNCTIONS, FIRST_PARTY)


def all_identities() -> tuple[str, str, str]:
    return bi.CORPUS_BUILDER_NAME, bi.effective_chunker_config_identity(), bi.construction_rules_identity()


# ==============================================================================
# T1–T4
# ==============================================================================

class TestDeterminism(unittest.TestCase):

    def test_t1_t2_t3_repeated_calls_identical(self):
        self.assertEqual(all_identities(), all_identities())
        self.assertEqual(bi.construction_rules_manifest(), bi.construction_rules_manifest())

    def test_t3_identical_across_processes_and_hash_seeds(self):
        code = ("import sys; sys.path.insert(0, %r); from ingest import builder_identity as b; "
                "print(b.CORPUS_BUILDER_NAME); print(b.effective_chunker_config_identity()); "
                "print(b.construction_rules_identity())" % REPO_ROOT)
        outputs = set()
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outputs.add(subprocess.run([sys.executable, "-B", "-c", code], env=env, check=True,
                                       capture_output=True, text=True).stdout)
        self.assertEqual(len(outputs), 1, outputs)
        self.assertEqual(outputs.pop().splitlines(), list(all_identities()))

    def test_t1_builder_name_is_filename_safe_and_versioned(self):
        self.assertRegex(bi.CORPUS_BUILDER_NAME, contracts._BUILDER_NAME_RE)
        self.assertRegex(bi.CORPUS_BUILDER_NAME, r"_v[1-9][0-9]*$")

    def test_t4_no_corpus_sha_commit_timestamp_or_path(self):
        """路径与时间戳检查恒执行；commit / 语料哈希只在其来源存在时比对
        （git archive 导出的树没有 .git，corpus/ 被 gitignore）。"""
        text = "\n".join(all_identities()) + repr(bi.construction_rules_manifest())
        forbidden = [REPO_ROOT, os.path.expanduser("~")]
        head = subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.returncode == 0:
            forbidden += [head.stdout.strip(), head.stdout.strip()[:7]]
        corpus_path = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")
        if os.path.isfile(corpus_path):
            with open(corpus_path, "rb") as handle:
                corpus_sha = hashlib.sha256(handle.read()).hexdigest()
            forbidden += [corpus_sha, corpus_sha[:8]]
        for value in forbidden:
            self.assertNotIn(value, text)
        self.assertIsNone(re.search(r"\b\d{4}-\d{2}-\d{2}\b", text))


# ==============================================================================
# T5a / T5b —— under-binding 与 over-binding
# ==============================================================================

class TestBinding(unittest.TestCase):

    def assertChanges(self, patch_target, attr, value, *, chunker_config_changes):
        before = all_identities()
        with mock.patch.object(patch_target, attr, value):
            after = all_identities()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1] != before[1], chunker_config_changes, attr)
        self.assertNotEqual(after[2], before[2], attr)

    def test_t5a_chars_per_token_est_changes_identity(self):
        self.assertChanges(contracts, "CHARS_PER_TOKEN_EST", contracts.CHARS_PER_TOKEN_EST + 1,
                           chunker_config_changes=True)

    def test_t5a_other_numeric_construction_dependencies(self):
        self.assertChanges(contracts, "CHUNK_TARGET_TOKENS", contracts.CHUNK_TARGET_TOKENS + 1,
                           chunker_config_changes=True)
        self.assertChanges(contracts, "CHUNK_MIN_CHARS", contracts.CHUNK_MIN_CHARS + 1,
                           chunker_config_changes=True)

    def test_t5a_non_numeric_construction_rules(self):
        self.assertChanges(kaiva_pdf, "_PARA_SPLIT_RE", re.compile(r"\n"), chunker_config_changes=False)
        self.assertChanges(kaiva_pdf, "PDFTOTEXT_ARGS", ("pdftotext",), chunker_config_changes=False)
        self.assertChanges(kaiva_pdf, "HEADER_SCAN_LINES", kaiva_pdf.HEADER_SCAN_LINES + 1,
                           chunker_config_changes=False)

    def test_t5b_downstream_only_dependencies_do_not_change_identity(self):
        before = all_identities()
        for attr, value in (("MAX_PROMPT_TOKENS", contracts.MAX_PROMPT_TOKENS + 1),
                            ("TOP_K_CONTEXT", contracts.TOP_K_CONTEXT + 1),
                            ("CONTEXT_PACK_MARGIN", contracts.CONTEXT_PACK_MARGIN / 2),
                            ("CITATION_HEADER_EST_TOKENS", contracts.CITATION_HEADER_EST_TOKENS + 1),
                            ("PROMPT_OVERHEAD_RESERVE_TOKENS", contracts.PROMPT_OVERHEAD_RESERVE_TOKENS + 1),
                            ("CHUNK_OVERLAP_TOKENS", contracts.CHUNK_OVERLAP_TOKENS + 1)):
            with self.subTest(attr), mock.patch.object(contracts, attr, value):
                self.assertEqual(all_identities(), before)

    def test_t5b_operational_dependency_does_not_change_identity(self):
        before = all_identities()
        with mock.patch.object(kaiva_pdf, "PDFTOTEXT_TIMEOUT_S", kaiva_pdf.PDFTOTEXT_TIMEOUT_S * 2):
            self.assertEqual(all_identities(), before)


# ==============================================================================
# T6 —— 与契约临时推导的值一致（不证明依赖完整）
# ==============================================================================

class TestContractValueAgreement(unittest.TestCase):

    def test_t6_values_equal_current_executable_constants(self):
        """值一致（不证明依赖完整）: 导出的每个 key=value 等于其登记常量的当前运行值。"""
        exported = dict(pair.split("=", 1) for pair in bi.effective_chunker_config_identity().split(";"))
        for key, category in bi.CONSTRUCTION_DEPENDENCY_REGISTRY.items():
            if category == bi.CHUNKER_CONFIG:
                self.assertEqual(exported[key.split(".", 1)[1].lower()], str(bi._resolve(key)))

    def test_t6_serialization_follows_contract_format(self):
        """契约格式: 键 = 常量名小写，字典序，`key=value`，";" 连接；不含 overlap（H7）。"""
        value = bi.effective_chunker_config_identity()
        keys = [pair.split("=", 1)[0] for pair in value.split(";")]
        self.assertEqual(keys, sorted(keys))
        self.assertTrue(all(k == k.lower() for k in keys))
        self.assertNotIn("overlap", value)

    def test_t8_contract_has_no_competing_chunker_helper(self):
        """v0.3.1 删除了契约侧临时推导；权威只剩本模块（FACADE 不存在，故无 facade purity 可检）。"""
        self.assertFalse(hasattr(contracts, "chunker_config_identity"))

    def test_t6_chunker_config_params_come_from_registry(self):
        from_registry = sorted(k.split(".", 1)[1].lower() for k, c in bi.CONSTRUCTION_DEPENDENCY_REGISTRY.items()
                               if c == bi.CHUNKER_CONFIG)
        exported = [pair.split("=", 1)[0] for pair in bi.effective_chunker_config_identity().split(";")]
        self.assertEqual(exported, from_registry)


# ==============================================================================
# T7 —— 防静默漏登
# ==============================================================================

class TestOmissionDefense(unittest.TestCase):

    def test_t7_registry_equals_constants_read_by_construction_path(self):
        unregistered, stale = coverage_problems(READ_CONSTANTS, bi.CONSTRUCTION_DEPENDENCY_REGISTRY)
        self.assertEqual(unregistered, set(), "构建代码读取了未登记的常量：先在登记表中分类")
        self.assertEqual(stale, set(), "登记表含构建已不再读取的常量：删除或复核")

    def test_t7_registry_entries_resolve_and_use_known_categories(self):
        categories = {bi.CHUNKER_CONFIG, bi.CONSTRUCTION_RULE, bi.RUNTIME_INPUT_DEFAULT, bi.AUDIT_ONLY,
                      bi.OPERATIONAL, bi.VOCABULARY, bi.DOWNSTREAM_ONLY}
        for key, category in bi.CONSTRUCTION_DEPENDENCY_REGISTRY.items():
            with self.subTest(key):
                self.assertIn(category, categories)
                bi._resolve(key)

    def test_t7_check_fails_when_a_registration_is_missing(self):
        for missing in ("kaiva_pdf._PARA_SPLIT_RE", "contracts.CHARS_PER_TOKEN_EST"):
            registry = dict(bi.CONSTRUCTION_DEPENDENCY_REGISTRY)
            del registry[missing]
            unregistered, _ = coverage_problems(READ_CONSTANTS, registry)
            self.assertEqual(unregistered, {missing})

    def test_t7_scanner_detects_a_newly_consumed_dependency(self):
        """合成包: 构建入口新读取一个常量（经模块别名、经 from-import 各一次）→ 扫描必须发现它。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "fakebuild")
            os.makedirs(pkg)
            open(os.path.join(pkg, "__init__.py"), "w").close()
            with open(os.path.join(pkg, "rules.py"), "w", encoding="utf-8") as handle:
                handle.write("OLD_KNOB = 1\nNEW_KNOB = 2\nFROM_IMPORTED = 3\nUNUSED = 4\n"
                             "def helper():\n    return NEW_KNOB\n")
            with open(os.path.join(pkg, "entry.py"), "w", encoding="utf-8") as handle:
                handle.write("from fakebuild import rules\nfrom fakebuild.rules import FROM_IMPORTED\n"
                             "def build():\n    return rules.OLD_KNOB + rules.helper() + FROM_IMPORTED\n")
            read, _ = scan_construction_path(tmp, "fakebuild.entry", ("build",), ("fakebuild",))
        self.assertEqual(read, {"rules.OLD_KNOB", "rules.NEW_KNOB", "rules.FROM_IMPORTED"})
        unregistered, _ = coverage_problems(read, {"rules.OLD_KNOB": bi.CONSTRUCTION_RULE})
        self.assertEqual(unregistered, {"rules.NEW_KNOB", "rules.FROM_IMPORTED"})

    def test_construction_code_fingerprint_tripwire(self):
        self.assertEqual(
            code_fingerprint(CONSTRUCTION_CODE), PINNED_CONSTRUCTION_CODE_FINGERPRINT,
            "构建路径代码的 AST 变了：按 ingest/builder_identity.py 的版本规则判断是否递增 "
            "CORPUS_BUILDER_NAME，再更新 PINNED_CONSTRUCTION_CODE_FINGERPRINT",
        )


if __name__ == "__main__":
    unittest.main()
