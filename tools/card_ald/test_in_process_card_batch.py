from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_card_batch as batch


class InProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="in-process-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.script = self.root / "build_card_data.py"
        self.log = self.root / "log.txt"
        self.old_mode = batch.IN_PROCESS
        batch.IN_PROCESS = True

    def tearDown(self):
        batch.IN_PROCESS = self.old_mode
        self.temp.cleanup()

    def source(self, text):
        self.script.write_text(text, encoding="utf-8")

    def test_reuses_loaded_module_between_cards(self):
        self.source("ROOT = 'old-root'\ncalls = 0\ndef main():\n global calls\n calls += 1\n print(calls)\n")
        first = batch.run_tool([self.script, "0000"], self.log, self.root)
        self.assertEqual(self.log.read_text().strip(), "1")
        second = batch.run_tool([self.script, "0006"], self.log, self.root)
        self.assertEqual(self.log.read_text().strip(), "2")
        self.assertTrue(first["passed"] and second["passed"])
        self.assertEqual(second["execution_mode"], "in-process")
        self.assertEqual(batch.card_module(self.script).ROOT, "old-root")

    def test_changed_exact_tool_bytes_invalidate_module_cache(self):
        self.source("def main(): print('first')\n")
        batch.run_tool([self.script], self.log, self.root)
        self.source("def main(): print('other')\n")
        batch.run_tool([self.script], self.log, self.root)
        self.assertEqual(self.log.read_text().strip(), "other")

    def test_cwd_argv_path_root_and_streams_are_restored(self):
        self.source("import os,sys\nROOT = 'old-root'\ndef main():\n print(str(ROOT))\n print(os.getcwd())\n print(sys.argv[-1])\n print('stderr captured', file=sys.stderr)\n")
        before = os.getcwd(), sys.argv, list(sys.path), sys.stdout, sys.stderr
        result = batch.run_tool([self.script, "last argument"], self.log, self.root)
        self.assertTrue(result["passed"])
        self.assertEqual((os.getcwd(), sys.argv, list(sys.path), sys.stdout, sys.stderr), before)
        lines = self.log.read_text().splitlines()
        self.assertEqual(lines, [str(self.root), str(self.root), "last argument", "stderr captured"])

    def test_exception_is_visible_failure_with_traceback(self):
        self.source("def main(): raise ValueError('visible failure')\n")
        result = batch.run_tool([self.script], self.log, self.root)
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["passed"])
        self.assertIn("ValueError: visible failure", self.log.read_text())

    def test_argparse_exit_preserves_exit_code(self):
        self.source("def main(): raise SystemExit(2)\n")
        result = batch.run_tool([self.script], self.log, self.root)
        self.assertEqual(result["exit_code"], 2)

    def test_interrupt_propagates_with_environment_restored(self):
        self.source("def main(): raise KeyboardInterrupt()\n")
        before = os.getcwd(), sys.argv, list(sys.path), sys.stdout, sys.stderr
        with self.assertRaises(KeyboardInterrupt):
            batch.run_tool([self.script], self.log, self.root)
        self.assertEqual((os.getcwd(), sys.argv, list(sys.path), sys.stdout, sys.stderr), before)

    def test_unknown_and_independent_verifier_use_subprocess(self):
        fake = SimpleNamespace(returncode=0, stdout="independent", stderr=" verification")
        for name in ("verify_current_card_catalog.py", "unrecognized.py"):
            with patch.object(batch.subprocess, "run", return_value=fake) as execute:
                result = batch.run_tool([self.root / name], self.log, self.root)
                execute.assert_called_once()
            self.assertEqual(result["execution_mode"], "subprocess")
            self.assertEqual(self.log.read_text(), "independent verification")

    def test_explicit_subprocess_mode_uses_isolated_interpreter(self):
        batch.IN_PROCESS = False
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=3, stdout="", stderr="failed")) as execute:
            result = batch.run_tool([self.script], self.log, self.root)
        execute.assert_called_once()
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["execution_mode"], "subprocess")


if __name__ == "__main__":
    unittest.main()
