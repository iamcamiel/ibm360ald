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

    def add_scope(self, repo):
        (repo / "notes/Card-ALD").mkdir(parents=True, exist_ok=True)
        batch.write(repo / "notes/Card-ALD/Scope exclusions.json", {
            "schema": "direct-human-card-diagram-scope-exclusions-v1",
            "instruction": "Leave 1457 and 1724 out if only used on missing RT011.",
            "basis": "Only listed use is missing RT011.", "card_types": ["1457", "1724"]})

    def successful_execution(self, argv, log, cwd):
        log.write_text("fixture execution", encoding="utf-8")
        return {"passed": True, "exit_code": 0, "log": batch.binding(log)}

    def test_direct_human_exclusions_are_explicit_and_catalogue_records_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repo = self.fixture(base)
            for card in ("1124", "1457", "1724"):
                batch.write(repo / "json/Card types current" / (card + ".json"), {"card_type": card})
            self.add_scope(repo)
            with patch.object(batch, "run_tool", side_effect=self.successful_execution) as execute, patch.object(batch, "recheck_sources", return_value={"current_checkpoint": True, "source_models": 12}) as final:
                report = batch.run_batch(repo, base / "results", "1")
            self.assertEqual(report["catalog_cards"], ["1124", "1457", "1724"])
            self.assertEqual(report["cards"], ["1124"])
            self.assertEqual(report["excluded_by_direct_human_instruction"], ["1457", "1724"])
            self.assertEqual(len(execute.call_args_list), 4)
            self.assertTrue((repo / "json/Card types current/1457.json").exists())
            self.assertIn("RT011", report["scope_exclusions"]["instruction"])
            self.assertEqual(report["final_source_epoch_check"]["source_models"], 12)
            final.assert_called_once_with(repo)

    def test_exact_excluded_prefix_reports_empty_scope_without_running_card_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repo = self.fixture(base)
            batch.write(repo / "json/Card types current/1457.json", {"card_type": "1457"})
            self.add_scope(repo)
            with patch.object(batch, "run_tool", side_effect=self.successful_execution) as execute:
                report = batch.run_batch(repo, base / "results", "1457")
            self.assertEqual(report["cards"], [])
            self.assertEqual(report["excluded_by_direct_human_instruction"], ["1457"])
            self.assertEqual(execute.call_count, 1)
            self.assertTrue(report["all_cards_attempted"])

    def test_source_epoch_failure_prevents_final_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repo = self.fixture(base)
            with patch.object(batch, "run_tool", side_effect=self.successful_execution), patch.object(batch, "recheck_sources", side_effect=ValueError("Source changed during final batch guard")):
                with self.assertRaisesRegex(ValueError, "final batch guard"):
                    batch.run_batch(repo, base / "results", "0")
            self.assertFalse((base / "results/Batch receipt.json").exists())

    def test_component_authority_changes_invalidate_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repo = self.fixture(base)
            component = repo / "json/Card-ALD/component-forms.json"
            component.parent.mkdir(parents=True)
            batch.write(component, {"source": "current"})
            authority = repo / "notes/Card-ALD/Component forms authority.txt"
            authority.parent.mkdir(parents=True)
            authority.write_text("Direct human current authority", encoding="utf-8")
            calls = 0
            def mutate(argv, log, cwd):
                nonlocal calls
                calls += 1
                result = self.successful_execution(argv, log, cwd)
                if calls == 2:
                    authority.write_text("Changed authority", encoding="utf-8")
                return result
            with patch.object(batch, "run_tool", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "source epoch changed"):
                    batch.run_batch(repo, base / "results", "0")
            self.assertFalse((base / "results/Batch receipt.json").exists())

    def test_current_repository_requires_scope_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repo = self.fixture(base)
            batch.write(repo / "notes/Source status.json", {"current": True})
            with self.assertRaisesRegex(ValueError, "scope ledger"):
                batch.run_batch(repo, base / "results", "0")
            self.assertFalse((base / "results").exists())

    def test_all_prefix_selects_every_four_digit_catalogue_stem(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=self.fixture(Path(temp))
            batch.write(repo/'json/Card types current/report.json',{'card_type':'report'})
            self.assertEqual(batch.select_cards(repo,'all'),['0141','0494','4191'])
            self.assertEqual(batch.select_cards(repo,'0'),['0141','0494'])
            for invalid in ('','ALL','all3','12345','-1'):
                with self.assertRaises(ValueError):batch.select_cards(repo,invalid)

    def test_all_prefix_preserves_exclusions_and_socket_coverage_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);repo=self.fixture(base)
            for card in ('1124','1457','1724'):
                batch.write(repo/'json/Card types current'/(card+'.json'),{'card_type':card})
            self.add_scope(repo)
            uniform=repo/'json/Socket listings uniform/Socket listings.json';uniform.parent.mkdir(parents=True)
            batch.write(uniform,{'records':[{'card_type':c}for c in ('0141','0494','1124','1457','1724','4191')]})
            with patch.object(batch,'run_tool',side_effect=self.successful_execution),patch.object(batch,'recheck_sources',return_value={'current_checkpoint':True,'source_models':12}):
                report=batch.run_batch(repo,base/'results','all')
            self.assertEqual(report['cards'],['0141','0494','1124','4191'])
            self.assertEqual(report['excluded_by_direct_human_instruction'],['1457','1724'])
            self.assertTrue(report['all_cards_attempted'])
            batch.write(uniform,{'records':[{'card_type':'9999'}]})
            with patch.object(batch,'run_tool')as execute:
                with self.assertRaisesRegex(ValueError,'missing socket-listed'):batch.run_batch(repo,base/'missing','all')
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
