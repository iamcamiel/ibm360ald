"""Exercise batch coverage, blocked evidence and source-epoch guards."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_card_batch as batch


class BatchTests(unittest.TestCase):
    def fixture(self, base):
        repo = base / "repo"
        for rel in ("notes/Reviewed export provenance.json", "notes/Content data manifest.json"):
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        for card in ("0141", "0494", "4191"):
            path = repo / "json/Card types current" / (card + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            batch.write(path, {"card_type": card})
        for tool in ("build_card_data.py", "audit_card_uses.py", "generate_card.py"):
            path = repo / "tools/card_ald" / tool
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# fixture", encoding="utf-8")
        path = repo / "notes/Card types current/Build manifest.json"
        path.parent.mkdir(parents=True)
        batch.write(path, {"source_binding": {
            "reviewed_export_provenance_sha256": batch.binding(repo / "notes/Reviewed export provenance.json")["sha256"],
            "content_data_manifest_sha256": batch.binding(repo / "notes/Content data manifest.json")["sha256"]}})
        return repo

    def test_every_selected_card_attempts_every_tool_even_without_definition(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.fixture(base)
            supplement = repo / "json/Card-ALD/build-overrides/0141.json"
            supplement.parent.mkdir(parents=True)
            batch.write(supplement, {"card_type": "0141"})
            calls = []

            def execute(argv, log, cwd):
                calls.append(argv)
                tool = Path(argv[0]).name
                ok = tool in ("verify_current_card_catalog.py", "build_card_data.py") or argv[1] == "0141"
                if tool == "build_card_data.py":
                    out = Path(argv[argv.index("--output-dir") + 1])
                    out.mkdir()
                    batch.write(out / (argv[1] + " evidence.json"), {"uncertainties": []})
                    if argv[1] == "0141":
                        batch.write(out / "0141.json", {})
                log.write_text("fixture execution", encoding="utf-8")
                return {"passed": ok, "exit_code": 0 if ok else 2, "log": batch.binding(log)}

            with patch.object(batch, "run_tool", side_effect=execute):
                report = batch.run_batch(repo, base / "results", "0")
            self.assertEqual(report["cards"], ["0141", "0494"])
            self.assertEqual(len(calls), 7)
            builders = [argv for argv in calls if Path(argv[0]).name == "build_card_data.py"]
            self.assertNotIn("--relayout", builders[0])
            self.assertIn("--relayout", builders[1])
            self.assertEqual(report["all_three_passed"], 1)
            self.assertTrue(report["all_cards_attempted"])
            self.assertFalse(report["results"][1]["definition_generated"])
            self.assertFalse(report["published"])

    def test_stale_catalog_stops_before_any_tool_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.fixture(base)
            (repo / "notes/Content data manifest.json").write_text('{"changed": true}', encoding="utf-8")
            with patch.object(batch, "run_tool") as execute:
                with self.assertRaisesRegex(ValueError, "Refresh and verify"):
                    batch.run_batch(repo, base / "results", "0")
            execute.assert_not_called()
            self.assertFalse((base / "results").exists())

    def test_input_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.json"
            path.write_text("first", encoding="utf-8")
            inputs = [batch.binding(path)]
            path.write_text("second", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source epoch changed"):
                batch.check_inputs(inputs)


if __name__ == "__main__":
    unittest.main()
