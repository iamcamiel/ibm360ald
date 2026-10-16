"""Stage and publish source-bound SLT pin readings and recorded human answers.

The queue and visual review are immutable inputs. Numeric wire annotations and
wire asterisks are retained separately from physical contacts where the existing
page model already makes that distinction. Historical recovery records stay as
history; active pin and net references are changed together.
"""
from argparse import ArgumentParser
from collections import defaultdict, Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT.parent
sys.path.insert(0, str(ROOT / "tools/card_ald"))
from release_463x_source_corrections import preview, append_note

NOTES = ROOT / "notes/Pin validation"
EVIDENCE = WORK / "tmp/ald-text/ald/slt-supply-visual"
STAGE = EVIDENCE / "release-stage"
AUDIT = WORK / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/Supply pin visual and human current audit.json"
NAME = "Supply pin visual and human current audit.json"
PIN = re.compile(r"^(?P<prefix>\d*)(?P<contact>[A-Z]\d{2})(?P<suffix>[✲*T]?)$")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def binding(path):
    return {"file": str(path.resolve()), "sha256": digest(path)}


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def contact(value):
    m = PIN.fullmatch(value)
    assert m, value
    return m.group("contact")


def selections():
    review = read(NOTES / "SLT supply-pin visual review.json")
    with (ROOT / "csv/Pin validation/SLT supply-pin review queue.csv").open(encoding="utf-8-sig", newline="") as f:
        queue = list(csv.DictReader(f))
    targets = {r["queue_index"]: {"answer": r["proposed_pin"], "authority": "independent_native_visual_review"}
               for r in review["rows"] if r["verdict"] == "clear_misread"}
    for name in ["SLT supply-pin manual answers.json", "Electrical rule manual answers.json"]:
        ledger = read(NOTES / name)
        assert all(q["answer"] for q in ledger["questions"])
        for q in ledger["questions"]:
            targets[q["queue_index"]] = {"answer": q["answer"], "authority": "direct_human_answer", "human_record": q}
    assert len(targets) == 120
    for index, target in targets.items():
        target.update({"queue_index": index, "review": review["rows"][index], "queue": queue[index]})
    return targets


def quartet(entry, model_source):
    txt = Path(entry["transcription_source"])
    stem = txt.stem
    candidates = [p for p in txt.parent.glob(stem + "*.png")
                  if p.name in [stem + " preview.png", stem + " JuliaMono preview.png", stem + " JuliaMono.png", stem + ".png"]]
    assert len(candidates) == 1, (entry["page"], candidates)
    return {"txt": txt, "json": Path(model_source), "notes": txt.with_name(stem + " review notes.txt"), "preview": candidates[0]}


def active_replace(value, replacements):
    """Replace whole endpoint references atomically, without changing history."""
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [active_replace(v, replacements) for v in value]
    if isinstance(value, dict):
        return {replacements.get(k, k): active_replace(v, replacements) for k, v in value.items()}
    return value


def replace_contact_in_reference(value, old, new):
    return re.sub(r"(?<![A-Z0-9])" + re.escape(old) + r"(?![A-Z0-9])", new, value)


def label_view(label):
    if isinstance(label, dict):
        return label.get("column"), label.get("row"), label.get("text")
    if isinstance(label, list) and len(label) >= 3:
        return label[0], label[1], label[2]
    return None, None, None


def set_label_text(label, text):
    if isinstance(label, dict):
        label["text"] = text
    else:
        label[2] = text


def stage():
    targets = selections()
    exports = read(ROOT / "notes/Reviewed export provenance.json")["exported"]
    entries = {e["page"]: e for e in exports}
    models = {Path(i["path"]).as_posix(): i for i in read(ROOT / "notes/Content data manifest.json")["files"]
              if i.get("role") == "Published page content model"}
    groups = defaultdict(list)
    for t in targets.values():
        groups[t["review"]["page"]].append(t)
    STAGE.mkdir(parents=True, exist_ok=True)
    bound_files = {}

    def verify(path, expected):
        path = Path(path)
        if str(path) not in bound_files:
            bound_files[str(path)] = digest(path)
        assert bound_files[str(path)] == expected, (path, "stale evidence")

    records = []
    for page, changes in sorted(groups.items()):
        entry = entries[page]
        model_item = models[changes[0]["queue"]["model"].replace("\\", "/")]
        paths = quartet(entry, model_item["source"])
        before = {k: p.read_bytes() for k, p in paths.items()}
        assert sha256(before["txt"]).hexdigest() == entry["text_sha256"]
        assert sha256(before["json"]).hexdigest() == model_item["sha256"]
        model = json.loads(before["json"].decode("utf-8-sig"))
        original_model = deepcopy(model)
        rows = before["txt"].decode("utf-8").splitlines(keepends=True)
        assert len(rows) == 103 and all(len(x.rstrip("\r\n")) <= 245 for x in rows), page
        originals = list(rows)
        source = changes[0]["review"]
        verify(source["scan_path"], source["scan_sha256"])
        edits, replacements = [], {}
        touched_cells = {}
        for t in changes:
            r, qr = t["review"], t["queue"]
            verify(r["scan_path"], r["scan_sha256"])
            verify(r["crop_path"], r["crop_sha256"])
            if t.get("human_record"):
                h = t["human_record"]
                verify(h["crop_path"], h["crop_sha256"])
            node = next(n for n in model["nodes"] if n["id"] == r["block"])
            pin_index = int(qr["pin_index"])
            pin = node["pins"][pin_index]
            assert str(node["card_type"]) == r["card_type"]
            assert str(pin["pin"]) == qr["printed_pin"], (page, r["block"], pin)
            if page == "RR141":
                continue  # the independently checked complete block reconciliation below
            old_pin = pin["pin"]
            old_contact = contact(old_pin)
            answer = PIN.fullmatch(t["answer"])
            assert answer, t
            new_contact = answer.group("contact")
            assert new_contact[0] in 'BDGJ' or (node['card_type'] == '3707' and new_contact == 'E11'), (page, new_contact)
            # Display text can carry a prefix or wire suffix outside pin['pin'].
            old_label = str(pin.get("printed_label") or pin.get("printed_pin") or old_pin)
            if pin.get("printed_prefix") and not old_label.startswith(str(pin["printed_prefix"])):
                old_label = str(pin["printed_prefix"]) + old_label
            if pin.get("printed_suffix") and not old_label.endswith(str(pin["printed_suffix"])):
                old_label += str(pin["printed_suffix"])
            parsed = PIN.fullmatch(old_label)
            assert parsed, (page, old_label)
            new_prefix = answer.group("prefix") or parsed.group("prefix")
            new_suffix = answer.group("suffix") or parsed.group("suffix")
            if t["queue_index"] == 11:
                new_suffix = ""  # native FE331 crop disproves the old asterisk
            new_label = new_prefix + new_contact + new_suffix
            new_pin = replace_contact_in_reference(old_pin, old_contact, new_contact)
            # Whole bare pin values have no separator; replace directly.
            new_pin = PIN.fullmatch(old_pin).group("prefix") + new_contact + PIN.fullmatch(old_pin).group("suffix")
            if PIN.fullmatch(old_pin).group("prefix") and answer.group("prefix"):
                new_pin = new_prefix + new_contact + PIN.fullmatch(old_pin).group("suffix")
            if t["queue_index"] == 11:
                new_pin = new_contact
            row = pin.get("absolute_row", pin["row"])
            lo, hi = ((node["column"] - 15, node["column"] + 1) if pin["side"] == "input"
                      else (node["column"] + 7, node["column"] + 24))
            starts = [i for i in range(max(0, lo), min(245, hi)) if originals[row].startswith(old_label, i)]
            # A suffix might be modeled separately but printed after a space.
            if not starts and new_suffix and old_label.endswith(new_suffix):
                short = old_label[:-len(new_suffix)]
                starts = [i for i in range(max(0, lo), min(245, hi)) if originals[row].startswith(short, i)]
                if starts:
                    old_label, new_label = short, new_label[:-len(new_suffix)]
            if len(starts) > 1:
                # A short bank gap can also contain the next block's input.
                starts = [min(starts) if pin["side"] == "output" else max(starts)]
            assert len(starts) == 1, (page, node["id"], row, old_label, starts, originals[row][max(0, lo):hi])
            col = starts[0]
            assert len(new_label) <= len(old_label), (page, old_label, new_label)
            text_replacement = new_label + "─" * (len(old_label) - len(new_label))
            for pos, (a, b) in enumerate(zip(old_label, text_replacement), col):
                if a != b:
                    key = (row, pos)
                    assert key not in touched_cells or touched_cells[key] == b, (page, key)
                    touched_cells[key] = b
            for key in ["reference", "terminal_id"]:
                value = pin.get(key)
                if isinstance(value, str):
                    replacement = replace_contact_in_reference(value, old_pin, new_pin)
                    if replacement == value and old_contact != new_contact:
                        replacement = replace_contact_in_reference(value, old_contact, new_contact)
                    if replacement != value:
                        assert value not in replacements or replacements[value] == replacement
                        replacements[value] = replacement
            if old_contact != new_contact:
                replacements[f'{node["id"]}.{old_contact}'] = f'{node["id"]}.{new_contact}'
                if old_pin != old_contact:
                    replacements[f'{node["id"]}.{old_pin}'] = f'{node["id"]}.{new_pin}'
            for key in ["pin", "physical_pin", "printed_pin", "printed_label", "printed_annotation"]:
                if key in pin and isinstance(pin[key], str):
                    value = pin[key]
                    if key == "pin":
                        pin[key] = new_pin
                    elif key == "physical_pin":
                        pin[key] = new_contact
                    else:
                        m = PIN.fullmatch(value)
                        if m:
                            pre = new_prefix if m.group("prefix") else ""
                            pin[key] = pre + new_contact + ("" if t["queue_index"] == 11 else m.group("suffix"))
            for key in ["printed_qualifier", "printed_prefix", "qualifier"]:
                if key in pin and pin[key] is not None and (str(pin[key]).isdigit() or new_prefix):
                    pin[key] = new_prefix or pin[key]
            # Printed-label objects carry positions; only the label at this pin changes.
            label_edits = []
            for label in model.get("printed_labels", []):
                lc, lr, text = label_view(label)
                if lr != row or not isinstance(text, str):
                    continue
                lc = col if lc is None else lc
                if not (col - 2 <= lc <= col + len(old_label)):
                    continue
                updated = re.sub(re.escape(old_label), lambda _: new_label, text)
                if updated == text and old_contact != new_contact:
                    updated = replace_contact_in_reference(text, old_contact, new_contact)
                if updated != text:
                    label_edits.append({"column": lc, "before": text, "after": updated})
                    set_label_text(label, updated)
            edits.append({"queue_index": t["queue_index"], "node": node["id"], "pin_index": pin_index,
                          "row": row, "column": col, "side": pin["side"], "before": old_pin, "after": new_pin,
                          "printed_before": old_label, "printed_after": new_label,
                          "authority": t["authority"], "source_crop": binding(Path(r["crop_path"])),
                          "printed_label_edits": label_edits})

        # AP531 AF has a second wrong digit outside the original supply-contact queue.
        if page == "AP531":
            node = next(n for n in model["nodes"] if n["id"] == "AF")
            pin = next(p for p in node["pins"] if p["row"] == 13 and p["side"] == "input")
            assert pin["pin"] == "D05"
            for key in ["reference", "terminal_id"]:
                if isinstance(pin.get(key), str):
                    replacements[pin[key]] = replace_contact_in_reference(pin[key], "D05", "B05")
            replacements['AF.D05'] = 'AF.B05'
            for key in ["pin", "printed_label", "printed_pin", "physical_pin"]:
                if key in pin:
                    assert pin[key] == "D05", pin
                    pin[key] = "B05"
            starts = [i for i in range(node["column"]-10,node["column"]) if originals[13].startswith('D05',i)]
            assert len(starts) == 1
            col = starts[0]
            assert originals[13][col:col+3] == "D05"
            touched_cells[(13, col)] = "B"
            for label in model.get("printed_labels", []):
                lc, lr, text = label_view(label)
                if lr == 13 and lc is not None and col-2 <= lc <= col+1:
                    set_label_text(label, text.replace("D05", "B05"))
            edits.append({"node": "AF", "row": 13, "column": col, "side": "input", "before": "D05", "after": "B05",
                          "authority": "independent_native_AP531_paired_pin_review"})
        for key in ["nodes", "nets", "wire_paths", "wires", "connections", "terminals", "junctions", "unjoined_crossings", "printed_labels", "physical_pin_feedthroughs"]:
            if key in model:
                model[key] = active_replace(model[key], replacements)
        for (row, col), char in touched_cells.items():
            rows[row] = rows[row][:col] + char + rows[row][col+1:]

        if page == "RR141":
            reconciliation = read(EVIDENCE / "rr141-reconciliation.json")
            assert digest(paths["json"]) == reconciliation["model_sha256"]
            assert digest(paths["txt"]) == reconciliation["text_sha256"]
            for edit in reconciliation["model_edits"]:
                parts = edit["path"].strip("/").split("/")
                current = model
                for part in parts[:-1]:
                    current = current[int(part)] if isinstance(current, list) else current[part]
                key = int(parts[-1]) if isinstance(current, list) else parts[-1]
                assert current[key] == edit["before"], edit["path"]
                current[key] = edit["after"]
            for edit in reconciliation["text_cell_edits"]:
                assert rows[edit["row"]][edit["column"]] == edit["before"]
                rr, cc = edit["row"], edit["column"]
                rows[rr] = rows[rr][:cc] + edit["after"] + rows[rr][cc+1:]
            edits.append({"node": "AR", "authority": "independent_complete_native_RR141_block_review",
                          "reconciliation": binding(EVIDENCE / "rr141-reconciliation.json"),
                          "description": "AR is A/U03AF/0147A1; D04 D05 D11 B12 inputs; D06✲ D13 outputs. D11 branches from INV_ at the upper 3308C1 input junction."})

        assert [len(x.rstrip("\r\n")) for x in rows] == [len(x.rstrip("\r\n")) for x in originals]
        paragraph = "SLT supply-pin source and human review, 2026-10-16: " + "; ".join(
            f'{e["node"]} {e.get("printed_before", e.get("before", "complete block"))} -> {e.get("printed_after", e.get("after", "native source reconciliation"))}'
            for e in edits) + ". Numeric wire qualifiers and asterisks are retained. Ground ties and the S21AA transformer ground reference are preserved where confirmed. Human answers and source hashes are recorded in the Pin validation release audit; older remarks remain historical."
        confirmations = [t["human_record"] for t in changes if t.get("human_record")]
        for h in confirmations:
            if h.get("human_observation"):
                paragraph += " " + h["human_observation"]
            if h.get("human_interpretation"):
                paragraph += " User interpretation: " + h["human_interpretation"]
        after = {"txt": "".join(rows).encode("utf-8"), "json": json_bytes(model),
                 "notes": append_note(before["notes"], paragraph)}
        if model == original_model:
            after["json"] = before["json"]
        padded_preview_text = ("\n".join(x.ljust(245) for x in after["txt"].decode("utf-8").splitlines()) + "\n").encode("utf-8")
        after["preview"] = preview(padded_preview_text) if after["txt"] != before["txt"] else before["preview"]
        directory = STAGE / page
        directory.mkdir(exist_ok=True)
        for kind, raw in before.items():
            (directory / ("before-" + paths[kind].name)).write_bytes(raw)
            (directory / paths[kind].name).write_bytes(after[kind])
        records.append({"page": page, "source": {"path": source["scan_path"], "sha256": source["scan_sha256"]},
                        "edits": edits, "confirmed_questions": confirmations,
                        "prior_quartet": {k: {"path": str(p), "sha256": sha256(before[k]).hexdigest()} for k, p in paths.items()},
                        "staged_quartet": {k: {"path": str(directory / p.name), "sha256": sha256(after[k]).hexdigest()} for k, p in paths.items()},
                        "reference_changes": replacements,
                        "changed_kinds": [k for k in before if before[k] != after[k]],
                        "checks": {"source_and_human_evidence_bound": True, "fixed_grid_preserved": True,
                                   "pin_labels_and_active_references_updated": True, "preview_matches_text": True,
                                   "historical_annotations_retained": True}})
        print(page, len(edits), ','.join(records[-1]['changed_kinds']), flush=True)
    inputs_dir = STAGE / 'inputs'
    inputs_dir.mkdir(exist_ok=True)
    input_bindings = []
    for name in ["SLT supply-pin visual review.json", "SLT supply-pin manual answers.json", "Electrical rule manual answers.json"]:
        saved = inputs_dir / name
        saved.write_bytes((NOTES / name).read_bytes())
        input_bindings.append(binding(saved))
    manifest = {"schema": "slt-supply-pin-release-stage-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "inputs": input_bindings,
                "scope": "95 visually resolved queue entries, five prior manual answers, twenty electrical-review answers, paired AP531 input and native RR141 block reconciliation",
                "records": records, "evidence_hashes": bound_files}
    (STAGE / "manifest.json").write_bytes(json_bytes(manifest))
    print(json.dumps({"pages": len(records), "changed_text_pages": sum('txt' in r['changed_kinds'] for r in records), "changed_model_pages": sum('json' in r['changed_kinds'] for r in records)}))


def publish():
    manifest_path = STAGE / "manifest.json"
    manifest = read(manifest_path)
    approval_path = EVIDENCE / "Supply pin staged independent review.json"
    approval = read(approval_path)
    assert approval["passed"] and approval["manifest_sha256"] == digest(manifest_path)
    for item in manifest["inputs"]:
        assert digest(Path(item["file"])) == item["sha256"]
    for path, expected in manifest["evidence_hashes"].items():
        assert digest(Path(path)) == expected, path
    for r in manifest["records"]:
        assert digest(Path(r["source"]["path"])) == r["source"]["sha256"]
        for key in r["prior_quartet"]:
            assert digest(Path(r["prior_quartet"][key]["path"])) == r["prior_quartet"][key]["sha256"]
            assert digest(Path(r["staged_quartet"][key]["path"])) == r["staged_quartet"][key]["sha256"]
    for r in manifest["records"]:
        for key, prior in r["prior_quartet"].items():
            Path(prior["path"]).write_bytes(Path(r["staged_quartet"][key]["path"]).read_bytes())
    publication = {"schema": "slt-supply-pin-publication-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                   "stage_manifest": binding(manifest_path), "independent_review": binding(approval_path),
                   "published_pages": [r["page"] for r in manifest["records"]]}
    publication_path = STAGE / "publication.json"
    publication_path.write_bytes(json_bytes(publication))
    authority = STAGE / "Human answers immutable snapshot.json"
    authority.write_bytes(json_bytes({"manual": read(NOTES / "SLT supply-pin manual answers.json"),
                                     "electrical": read(NOTES / "Electrical rule manual answers.json")}))
    audit = {"schema": "slt-supply-pin-source-bound-current-audit-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
             "passed": True, "scope": manifest["scope"], "pages": []}
    for r in manifest["records"]:
        current = {key: {"path": prior["path"], "sha256": digest(Path(prior["path"]))} for key, prior in r["prior_quartet"].items()}
        assert all(current[k]["sha256"] == r["staged_quartet"][k]["sha256"] for k in current)
        audit["pages"].append({"page": r["page"], "eligible": True, "artifact_schema": "reviewed-current-quartet-v1",
                               "source": r["source"], "prior_quartet": r["prior_quartet"], "current_quartet": current,
                               "checks": {**r["checks"], "independent_staged_delta_review_passed": True},
                               "independent_audit": binding(approval_path), "human_authority": binding(authority),
                               "physical_pin_stage_manifest": binding(manifest_path), "physical_pin_publication": binding(publication_path)})
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_bytes(json_bytes(audit))
    (NOTES / NAME).write_bytes(json_bytes(audit))
    print('Published', len(audit['pages']), 'source-bound page quartets.')


def finalize():
    """Verify mirrored current text/models/notes, then close the answer ledgers."""
    audit = read(AUDIT)
    manifest = read(STAGE / 'manifest.json')
    exported = {e['page']: e for e in read(ROOT / 'notes/Reviewed export provenance.json')['exported']}
    content = {Path(e['source']).resolve(): e for e in read(ROOT / 'notes/Content data manifest.json')['files']
               if e.get('role') == 'Published page content model'}
    for item in audit['pages']:
        page = item['page']
        current = item['current_quartet']
        for b in current.values():
            assert digest(Path(b['path'])) == b['sha256'], (page, b)
        entry = exported[page]
        assert entry['review_record'].endswith(NAME), page
        assert digest(Path(entry['destination'])) == current['txt']['sha256'], page
        exported_notes = Path(entry['notes_destination'])
        assert digest(exported_notes) == entry['notes_sha256'], page
        # Exported notes add catalogue provenance and normalize line endings.
        original_note_text = Path(current['notes']['path']).read_text(encoding='utf-8-sig').rstrip()
        assert original_note_text in exported_notes.read_text(encoding='utf-8-sig'), page
        model = content[Path(current['json']['path']).resolve()]
        assert model['sha256'] == current['json']['sha256'] == digest(ROOT / model['path']), page
    stamp = datetime.now(timezone.utc).isoformat()
    for name in ['SLT supply-pin manual answers.json', 'Electrical rule manual answers.json']:
        path = NOTES / name
        ledger = read(path)
        assert all(q['answer'] for q in ledger['questions'])
        ledger.update({'status': 'applied_and_repository_mirror_verified', 'updates_applied': True,
                       'canonical_updates_applied': True, 'repository_mirror_verified': True,
                       'verified_utc': stamp, 'current_audit': str(AUDIT)})
        path.write_bytes(json_bytes(ledger))
    selected = selections()
    review = read(NOTES / 'SLT supply-pin visual review.json')
    rows = []
    for r in review['rows']:
        t = selected.get(r['queue_index'])
        rows.append({'page': r['page'], 'block': r['block'], 'queue_index': r['queue_index'],
                     'original_modeled_pin': r['modeled_pin'],
                     'reviewed_reading': t['answer'] if t else r['native_reading'],
                     'authority': t['authority'] if t else 'native_visual_review_literal_retained',
                     'status': 'applied_or_confirmed' if t else 'retained_as_printed',
                     'original_scan': r['scan_path']})
    csv_path = ROOT / 'csv/Pin validation/SLT supply-pin completed review.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r['page'], r['block'], r['queue_index'])))
    result = {'schema': 'slt-supply-pin-completed-review-v1', 'verified_utc': stamp,
              'reviewed_pages': len(audit['pages']),
              'updated_text_and_model_pages': sum('txt' in r['changed_kinds'] for r in manifest['records']),
              'recorded_human_answers': 25, 'unanswered_manual_questions': 0,
              'reviewed_queue_entries': len(rows), 'selected_correction_or_confirmation_entries': len(selected),
              'canonical_and_repository_text_models_byte_equal_notes_preserved': True,
              'current_audit': binding(AUDIT), 'independent_stage_review': binding(EVIDENCE / 'Supply pin staged independent review.json'),
              'remaining_interpretation': 'Meaning of numeric 8 annotation remains unresolved; literal 8D03 preserved. L-as-latch explanation remains a recorded human hypothesis.',
              'completed_review_csv': binding(csv_path)}
    (NOTES / 'SLT supply-pin completed review.json').write_bytes(json_bytes(result))
    print(json.dumps({k: result[k] for k in ['reviewed_pages', 'updated_text_and_model_pages', 'recorded_human_answers', 'unanswered_manual_questions']}))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "publish", "finalize"])
    args = parser.parse_args()
    {'stage': stage, 'publish': publish, 'finalize': finalize}[args.action]()
