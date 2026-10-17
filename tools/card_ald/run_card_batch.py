"""Run the three universal card tools into a private, source-bound batch.

Example: python tools/card_ald/run_card_batch.py --prefix 0 --output-dir PATH
This never publishes candidate pinouts or changes ALD transcriptions.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
IN_PROCESS = True
MODULES = {}
CARD_TOOLS = {"build_card_data.py", "audit_card_uses.py", "generate_card.py"}
SCOPE_LEDGER = "notes/Card-ALD/Scope exclusions.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_cards(repo, prefix):
    require(bool(re.fullmatch(r"[0-9]{1,4}", prefix)), "Use a numeric prefix of one to four digits")
    cards = []
    for path in sorted((repo / "json/Card types current").glob("*.json")):
        if re.fullmatch(r"[0-9]{4}", path.stem) and path.stem.startswith(prefix):
            require(read(path).get("card_type") == path.stem, "Catalog identity differs: " + str(path))
            cards.append(path.stem)
    require(bool(cards), "No current catalog card types match the prefix")
    return cards


def check_inputs(inputs):
    for expected in inputs:
        require(binding(expected["path"]) == expected, "Batch source epoch changed: " + expected["path"])


def scoped_cards(repo, cards):
    path = repo / SCOPE_LEDGER
    if not path.is_file():
        require(not (repo / "notes/Source status.json").exists(), "Current repository needs the direct human card scope ledger")
        return cards, [], None
    ledger = read(path)
    require(ledger.get("schema") == "direct-human-card-diagram-scope-exclusions-v1", "Unknown card scope ledger")
    require(isinstance(ledger.get("instruction"), str) and ledger["instruction"].strip()
            and isinstance(ledger.get("basis"), str) and ledger["basis"].strip(), "Scope exclusion lacks direct human instruction and basis")
    excluded = ledger.get("card_types")
    require(isinstance(excluded, list) and all(isinstance(card, str) and re.fullmatch(r"[0-9]{4}", card) for card in excluded), "Invalid scope exclusion card list")
    require(len(excluded) == len(set(excluded)), "Duplicate scope exclusion")
    selected_exclusions = sorted(set(cards) & set(excluded))
    return [card for card in cards if card not in excluded], selected_exclusions, dict(
        binding=binding(path), instruction=ledger["instruction"], basis=ledger["basis"])


def recheck_sources(repo):
    """Close the shared parse-cache epoch with a complete current-byte check."""
    if not (repo / "tools/card_ald/card_source.py").is_file():
        require(not (repo / "notes/Source status.json").exists(), "Current batch source reader is missing")
        return {"source_models": 0, "current_checkpoint": False}
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(repo / "tools/card_ald"))
        import card_source
        require(Path(card_source.__file__).resolve() == (repo / "tools/card_ald/card_source.py").resolve(),
                "Batch source reader belongs to a different repository")
        return card_source.recheck_epoch(repo)
    finally:
        sys.path[:] = old_path


def card_module(path):
    """Reuse exact tool bytes in this process so shared parsed pages stay cached."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    key = (str(path), fingerprint)
    if key not in MODULES:
        name = "_card_batch_" + path.stem + "_" + hashlib.sha256(str(path).encode()).hexdigest()[:12] + "_" + fingerprint[:12]
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            exec(compile(raw, str(path), "exec"), module.__dict__)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        require(callable(getattr(module, "main", None)), "Card tool has no main entry point: " + str(path))
        MODULES[key] = module
    return MODULES[key]


def execute_in_process(argv, cwd):
    captured = io.StringIO()
    old_argv, old_path, old_cwd = sys.argv, list(sys.path), Path.cwd()
    module = None
    old_root = None
    try:
        with redirect_stdout(captured), redirect_stderr(captured):
            try:
                sys.path.insert(0, str(Path(argv[0]).resolve().parent))
                sys.argv = list(map(str, argv))
                os.chdir(cwd)
                module = card_module(argv[0])
                old_root = getattr(module, "ROOT", None)
                if old_root is not None:
                    module.ROOT = Path(cwd).resolve()
                module.main()
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
                if exc.code and not isinstance(exc.code, int):
                    print(exc.code, file=sys.stderr)
            except Exception:
                traceback.print_exc()
                code = 1
    finally:
        if module is not None and old_root is not None:
            module.ROOT = old_root
        sys.argv = old_argv
        sys.path[:] = old_path
        os.chdir(old_cwd)
    return code, captured.getvalue()


def run_tool(argv, log, cwd):
    started = datetime.now(timezone.utc).isoformat()
    in_process = IN_PROCESS and Path(argv[0]).name in CARD_TOOLS
    if in_process:
        code, output = execute_in_process(argv, cwd)
    else:
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", *map(str, argv)], cwd=cwd,
                                 capture_output=True, text=True, encoding="utf-8")
        code, output = process.returncode, process.stdout + process.stderr
    log.write_text(output, encoding="utf-8")
    return {"argv": list(map(str, argv)), "started_utc": started,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "exit_code": code, "passed": code == 0,
            "execution_mode": "in-process" if in_process else "subprocess",
            "log": binding(log)}


def save_progress(output, manifest):
    write(output / "Batch progress.json", manifest)
    fields = ["card_type", "definition_generated", "builder_review_items", "audit_discrepancies",
              "audit_uncertainties", "txt_files", "build_passed", "audit_passed", "render_passed"]
    with (output / "Batch summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in manifest["results"]:
            writer.writerow({key: item.get(key) for key in fields})


def _run_batch(repo, output, prefix):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    require(not output.exists(), "Use a new output directory; existing results are never overwritten")
    require(not output.is_relative_to(repo), "Batch candidates must stay outside the repository")
    require(not output.is_relative_to(repo.parent / "ALD_Visual_Transcriptions"), "Output overlaps page transcriptions")
    catalog_cards = select_cards(repo, prefix)
    cards, excluded, scope = scoped_cards(repo, catalog_cards)
    uniform_path = repo / "json/Socket listings uniform/Socket listings.json"
    uniform_binding = []
    if uniform_path.is_file():
        uniform = read(uniform_path)
        listed = {record["card_type"] for record in uniform["records"]
                  if isinstance(record.get("card_type"), str)
                  and re.fullmatch(r"[0-9]{4}", record["card_type"])
                  and record["card_type"].startswith(prefix)}
        require(not (listed - set(catalog_cards)), "Current catalog is missing socket-listed card types: "
                + ", ".join(sorted(listed - set(catalog_cards))))
        uniform_binding = [binding(uniform_path)]
    catalog_manifest = repo / "notes/Card types current/Build manifest.json"
    catalog = read(catalog_manifest)
    epoch = [binding(repo / "notes/Reviewed export provenance.json"),
             binding(repo / "notes/Content data manifest.json")]
    require(catalog["source_binding"]["reviewed_export_provenance_sha256"] == epoch[0]["sha256"]
            and catalog["source_binding"]["content_data_manifest_sha256"] == epoch[1]["sha256"],
            "Refresh and verify the current card catalog after applying source corrections first")
    inputs = epoch + uniform_binding + [binding(catalog_manifest), binding(Path(__file__))]
    if scope:
        inputs.append(scope["binding"])
    for relative in ("notes/Source status.json", "json/Card-ALD/component-forms.json", "notes/Card-ALD/Component forms authority.txt"):
        path = repo / relative
        if path.is_file():
            inputs.append(binding(path))
    for relative in ("build_card_data.py", "audit_card_uses.py", "generate_card.py"):
        inputs.append(binding(repo / "tools/card_ald" / relative))
    for folder in ("tools/card_ald", "tools/normalization", "tools/references"):
        inputs.extend(binding(path) for path in sorted((repo / folder).glob("*.py"))
                      if not path.name.startswith("test_") and path.name not in CARD_TOOLS)
    inputs += [binding(repo / "json/Card types current" / (card + ".json")) for card in catalog_cards]
    for card in cards:
        supplement = repo / "json/Card-ALD/build-overrides" / (card + ".json")
        if supplement.is_file():
            inputs.append(binding(supplement))
    output.mkdir(parents=True)
    verifier = run_tool([repo / "tools/references/verify_current_card_catalog.py", "--repo", repo,
                         "--catalog", repo], output / "Catalog verification.txt", repo)
    write(output / "Catalog verification execution.json", verifier)
    require(verifier["passed"], "Current catalog verification failed; see private batch log")
    manifest = {"schema": "universal-card-three-tool-batch-v1", "prefix": prefix,
                "created_utc": datetime.now(timezone.utc).isoformat(), "cards": cards,
                "catalog_cards": catalog_cards, "excluded_by_direct_human_instruction": excluded,
                "scope_exclusions": scope,
                "inputs": inputs, "catalog_verification": verifier, "results": [],
                "published": False, "source_writes": 0,
                "card_tool_execution_mode": "in-process" if IN_PROCESS else "subprocess",
                "scope": "Private candidates and audits; generated diagrams are not independently accepted universal pinouts."}
    write(output / "Batch inputs.json", manifest)
    for card in cards:
        check_inputs(inputs)
        directory = output / card
        directory.mkdir()
        candidate, audit, rendered = directory / "data", directory / "audit", directory / "rendered"
        definition = candidate / (card + ".json")
        supplement = repo / "json/Card-ALD/build-overrides" / (card + ".json")
        layout_args = [] if supplement.is_file() else ["--relayout"]
        commands = {
            "build": [repo / "tools/card_ald/build_card_data.py", card, "--root", repo, "--output-dir", candidate, *layout_args],
            "audit": [repo / "tools/card_ald/audit_card_uses.py", card, "--root", repo,
                      "--definition", definition, "--output-dir", audit],
            "render": [repo / "tools/card_ald/generate_card.py", card, "--definitions", candidate,
                       "--output-dir", rendered],
        }
        item = {"card_type": card, "executions": {},
                "layout_policy": "preserve reviewed supplement" if not layout_args else "current generic graph planner"}
        # Attempt all three explicitly. Missing evidence/definitions remain a
        # visible failure for that card, rather than silently dropping it.
        for name, command in commands.items():
            check_inputs(inputs)
            execution = run_tool(command, directory / (name + ".txt"), repo)
            item["executions"][name] = execution
            item[name + "_passed"] = execution["passed"]
        evidence = candidate / (card + " evidence.json")
        item["definition_generated"] = definition.is_file()
        if evidence.is_file():
            report = read(evidence)
            item["builder_review_items"] = len(report["uncertainties"])
        audit_report = audit / (card + " use audit.json")
        if audit_report.is_file():
            summary = read(audit_report)["summary"]
            item["audit_discrepancies"] = summary["new_discrepancies"]
            item["audit_uncertainties"] = summary["source_uncertainties"]
        item["txt_files"] = len(list(rendered.glob("*.txt"))) if rendered.exists() else 0
        item["outputs"] = [binding(path) for path in sorted(directory.rglob("*")) if path.is_file()]
        manifest["results"].append(item)
        save_progress(output, manifest)
        print(json.dumps({key: value for key, value in item.items() if key not in ("executions", "outputs")} ), flush=True)
    source_recheck = recheck_sources(repo)
    check_inputs(inputs)
    manifest.update(completed_utc=datetime.now(timezone.utc).isoformat(),
                    final_source_epoch_check=source_recheck,
                    all_cards_attempted=len(manifest["results"]) == len(cards),
                    all_three_passed=sum(all(item[name + "_passed"] for name in commands) for item in manifest["results"]))
    save_progress(output, manifest)
    write(output / "Batch receipt.json", manifest)
    return manifest


def run_batch(repo, output, prefix, in_process=True):
    global IN_PROCESS
    previous = IN_PROCESS
    try:
        IN_PROCESS = in_process
        return _run_batch(repo, output, prefix)
    finally:
        IN_PROCESS = previous


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--prefix", default="0")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subprocess", action="store_true", help="Run each card tool in a separate interpreter for comparison/debugging")
    args = parser.parse_args()
    run_batch(args.repo, args.output_dir, args.prefix, in_process=not args.subprocess)
