import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent
MANIFEST = ROOT / "three-way-private-stage/AP041 three-way private stage manifest.json"
RECEIPT = ROOT / "AP041 independent three-way private-stage acceptance.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(condition, reason):
    checks.append(reason)
    if not condition:
        failures.append(reason)


def paths_diff(a, b, base=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            yield from paths_diff(a.get(key), b.get(key), f"{base}/{key}")
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            yield from paths_diff(a[i] if i < len(a) else None, b[i] if i < len(b) else None, f"{base}/{i}")
    elif a != b:
        yield base, a, b


checks = []
failures = []
m = json.loads(MANIFEST.read_text(encoding="utf-8"))

for group in ("original_tiff", "source_candidate", "shared_renderer", "font", "stage_script", "comparison"):
    x = m[group]
    check(sha(x["path"]) == x["sha256"], f"{group} SHA-256 pin")
for group in ("before_quartet", "candidate_quartet", "canonical_before_quartet"):
    for name, x in m[group].items():
        check(sha(x["path"]) == x["sha256"], f"{group}.{name} SHA-256 pin")
for i, x in enumerate(m["native_crops"]):
    check(sha(x["path"]) == x["sha256"], f"native crop {i} SHA-256 pin")
for i, x in enumerate(m["corroboration"]):
    check(sha(x["path"]) == x["sha256"], f"corroboration {i} SHA-256 pin")

for name in ("txt", "json", "notes", "preview"):
    check(
        m["before_quartet"][name]["sha256"] == m["canonical_before_quartet"][name]["sha256"],
        f"{name} before stage matches current canonical",
    )

repo_txt = Path(r"D:\Github\IBM360\ibm360ald\ALD\AP Parallel Adder\AP041 PARALLEL ADDER BIT 04.txt")
check(sha(repo_txt) == m["before_quartet"]["txt"]["sha256"], "repository TXT matches before stage")

old_txt = Path(m["before_quartet"]["txt"]["path"]).read_text(encoding="utf-8")
new_txt = Path(m["candidate_quartet"]["txt"]["path"]).read_text(encoding="utf-8")
old_lines = old_txt.splitlines(keepends=True)
new_lines = new_txt.splitlines(keepends=True)
check(len(old_lines) == len(new_lines) == 103, "103 text rows preserved")
expected = list(old_lines)
for edit in m["text_edits"]:
    row = edit["text_zero_based_row"]
    col = edit["text_zero_based_col"]
    old = edit["before"]["text"]
    new = edit["after"]["text"]
    check(len(old) == len(new) == 6, f"{edit['node']} fixed-width printed label")
    check(old_lines[row][col : col + 6] == old, f"{edit['node']} original label exact location")
    expected[row] = expected[row][:col] + new + expected[row][col + 6 :]
    check(new_lines[row][col : col + 6] == new, f"{edit['node']} candidate label exact location")
check("".join(expected) == new_txt, "exactly three TXT character substitutions, no other change")
check(all(len(x.rstrip("\r\n")) == 245 for x in new_lines), "245-column text width preserved")

old_obj = json.loads(Path(m["before_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
new_obj = json.loads(Path(m["candidate_quartet"]["json"]["path"]).read_text(encoding="utf-8"))
actual_diff = list(paths_diff(old_obj, new_obj))
model_expected = {x["json_pointer"]: (x["before"], x["after"]) for x in m["model_edits"]}
check(len(model_expected) == 9, "nine expected model field changes")
for path, pair in model_expected.items():
    check(any(p == path and (a, b) == pair for p, a, b in actual_diff), f"expected model diff {path}")
extra_diff = [(p, a, b) for p, a, b in actual_diff if p not in model_expected]
history_key = m["model_history_key"]
check(len(extra_diff) == 1 and extra_diff[0][0] == "/" + history_key and extra_diff[0][1] is None, "only declared top-level source history added")
history = new_obj.get(history_key)
check(isinstance(history, dict), "source history key present")
if isinstance(history, dict):
    check(history.get("original_tiff", {}).get("sha256") == m["original_tiff"]["sha256"], "source history TIFF pinned")
    check(history.get("candidate", {}).get("sha256") == m["source_candidate"]["sha256"], "source history candidate pinned")
    check(history.get("predecessor_txt_sha256") == m["before_quartet"]["txt"]["sha256"], "source history predecessor TXT pinned")
    check(history.get("predecessor_json_sha256") == m["before_quartet"]["json"]["sha256"], "source history predecessor JSON pinned")
for node_id, portion in (("AS", "K8"), ("AU", "K4"), ("BB", "K6")):
    node = next(x for x in new_obj["nodes"] if x["id"] == node_id)
    check(
        node["portion"] == node["socket_listing_evidence"]["portion"] == portion
        and node["printed_card_portion"] == "4633" + portion,
        f"{node_id} three data labels consistent",
    )
before_nodes = {x["id"]: x for x in old_obj["nodes"]}
for x in new_obj["nodes"]:
    old = before_nodes[x["id"]]
    if x["id"] in ("AS", "AU", "BB"):
        y = copy.deepcopy(x)
        for field in ("portion", "printed_card_portion"):
            y[field] = old[field]
        y["socket_listing_evidence"]["portion"] = old["socket_listing_evidence"]["portion"]
        check(y == old, f"{x['id']} all other node fields unchanged")
    else:
        check(x == old, f"{x['id']} unrelated node unchanged")

old_notes = Path(m["before_quartet"]["notes"]["path"]).read_text(encoding="utf-8")
new_notes = Path(m["candidate_quartet"]["notes"]["path"]).read_text(encoding="utf-8")
check(new_notes.startswith(old_notes), "notes retained as exact prefix")
addition = new_notes[len(old_notes) :]
for token in ("AS/4E OR = 4633K8", "AU/5B A = 4633K4", "BB/6B N = 4633K6", m["original_tiff"]["sha256"]):
    check(token in addition, f"notes provenance contains {token}")

receipt = {
    "schema": "ap041-independent-three-way-private-stage-acceptance-v1",
    "status": "PASS" if not failures else "FAIL",
    "manifest": {"path": str(MANIFEST), "sha256": sha(MANIFEST)},
    "checks": len(checks),
    "failures": failures,
    "model_changes": len(actual_diff),
    "model_extra_history_changes": extra_diff,
    "published_files_modified_by_audit": 0,
}
RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in receipt.items() if k != "model_extra_history_changes"}, indent=2))
raise SystemExit(0 if not failures else 1)
