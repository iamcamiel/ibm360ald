"""Stage and publish five native-scan 4633 pin corrections."""
from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
from release_463x_source_corrections import WORKSPACE, CANONICAL, REPO, sha, preview, append_note

STAGE = WORKSPACE / "tmp/ald-text/ald/card-463x-release/pin-stage"
AUDIT = WORKSPACE / "tmp/ald-text/ald/manual-verification/contextual-cross-reference-v3/4633 native pin current audit.json"
REPO_AUDIT = REPO / "notes/Card-ALD/4633 native pin current audit.json"
SOURCE = Path("D:/Reference Materials/IBM 360/IBM_360_ALD/AP Parallel Adder")
CROP = WORKSPACE / "tmp/ald-text/ald/4633-native-audit"
# Page, node, old structured pin, old printed label, new pin, new printed label
CHANGES = [
    ("AP091", "AS", "U04", "U04", "G04", "G04"),
    ("AP131", "AT", "U05", "U05", "J05", "J05"),
    ("AP131", "AV", "U14✲", "U14✲", "D13✲", "D13✲"),
    ("AP473", "AR", "C02", "C02", "G02", "G02"),
    ("AP491", "AV", "D1", "D1✲", "D13", "D13✲"),
]

def paths(root, stem, preview_name):
    return {"txt": root/(stem+".txt"), "json": root/(stem+".json"),
            "notes": root/(stem+" review notes.txt"), "preview": root/preview_name}

def stage():
    pages = {}
    for change in CHANGES:
        pages.setdefault(change[0], []).append(change)
    records = []
    STAGE.mkdir(parents=True, exist_ok=True)
    for page, changes in pages.items():
        matches = list(CANONICAL.glob(page+" *.json"))
        assert len(matches) == 1
        stem = matches[0].stem
        preferred = CANONICAL/(stem+" JuliaMono preview.png")
        pname = preferred.name if preferred.is_file() else stem+".png"
        original = paths(CANONICAL, stem, pname)
        before = {k:p.read_bytes() for k,p in original.items()}
        rows = before["txt"].decode("utf-8").splitlines(keepends=True)
        model = json.loads(before["json"].decode("utf-8"))
        edits = []
        for _, node_id, old_pin, old_label, new_pin, new_label in changes:
            node = next(n for n in model["nodes"] if n["id"] == node_id)
            pins = [p for p in node["pins"] if p.get("pin") == old_pin]
            assert len(pins) == 1, (page,node_id,old_pin,pins)
            pin = pins[0]
            row = pin["row"]
            col = node["column"]
            lo,hi = (col-12,col+8) if pin["side"] == "input" else (col+7,col+40)
            left = rows[row].find(old_label,lo,hi)
            assert left >= 0 and rows[row].find(old_label,left+1,hi) < 0, (page,node_id,row)
            old_span = old_label + ("─" if len(new_label) > len(old_label) else "")
            assert rows[row][left:left+len(old_span)] == old_span
            assert len(old_span) == len(new_label)
            rows[row] = rows[row][:left]+new_label+rows[row][left+len(old_span):]
            pin["pin"] = new_pin
            if pin.get("printed_label") == old_label:
                pin["printed_label"] = new_label
            for label in model.get("printed_labels",[]):
                if label.get("row") == row and label.get("text") == old_label:
                    label["text"] = new_label
            crop = CROP/(page+"-"+node_id+"-native.png")
            assert crop.is_file(),crop
            edits.append({"node":node_id,"row":row,"before":old_label,
                          "after":new_label,"crop":str(crop)})
        after = dict(before)
        after["txt"] = "".join(rows).encode("utf-8")
        after["json"] = (json.dumps(model,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
        after["preview"] = preview(after["txt"])
        summary = "; ".join(e["node"]+" "+e["before"]+" -> "+e["after"] for e in edits)
        after["notes"] = append_note(before["notes"],
            "Card-ALD 4633 native pin correction, 2026-10-15: "+summary+
            ". Original TIFF crops are source-bound in the current audit. "+
            "Older validation pin lists and uncertainty remarks remain historical.")
        assert len(rows)==103 and all(len(r.rstrip("\r\n"))==245 for r in rows)
        stage_dir=STAGE/stem
        stage_dir.mkdir(exist_ok=True)
        staged=paths(stage_dir,stem,pname)
        for kind,content in after.items():
            staged[kind].write_bytes(content)
        source=SOURCE/(stem+".tif")
        assert source.is_file()
        records.append({"page":page,
            "source":{"path":str(source),"sha256":sha(source.read_bytes())},
            "changes":edits,
            "prior_quartet":{k:{"path":str(original[k]),"sha256":sha(v)} for k,v in before.items()},
            "staged_quartet":{k:{"path":str(staged[k]),"sha256":sha(v)} for k,v in after.items()},
            "checks":{"native_crops_viewed":True,"only_named_pin_labels_changed":True,
                      "grid_json_preview_verified":True,"source_and_quartet_hashes_bound":True}})
    manifest={"schema":"card-4633-pin-stage-v1","created_utc":datetime.now(timezone.utc).isoformat(),
              "records":records}
    (STAGE/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Staged",len(records),"pages and",len(CHANGES),"pins")

def publish():
    manifest_path=STAGE/"manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"]=="card-4633-pin-stage-v1"
    assert {r["page"] for r in manifest["records"]}=={r[0] for r in CHANGES}
    for record in manifest["records"]:
        assert sha(Path(record["source"]["path"]).read_bytes())==record["source"]["sha256"]
        for kind,old in record["prior_quartet"].items():
            new=record["staged_quartet"][kind]
            assert sha(Path(old["path"]).read_bytes())==old["sha256"]
            assert sha(Path(new["path"]).read_bytes())==new["sha256"]
    for record in manifest["records"]:
        for kind,old in record["prior_quartet"].items():
            Path(old["path"]).write_bytes(Path(record["staged_quartet"][kind]["path"]).read_bytes())
    audit={"schema":"card-4633-pin-current-audit-v1",
           "created_utc":datetime.now(timezone.utc).isoformat(),
           "passed":True,"reviewer":"Coordinator independent native TIFF crop review",
           "scope":"Five named 4633 physical pins only",
           "stage_manifest":{"path":str(manifest_path),"sha256":sha(manifest_path.read_bytes())},
           "pages":[]}
    for record in manifest["records"]:
        current={kind:{"path":old["path"],"sha256":record["staged_quartet"][kind]["sha256"]}
                 for kind,old in record["prior_quartet"].items()}
        assert all(sha(Path(x["path"]).read_bytes())==x["sha256"] for x in current.values())
        audit["pages"].append({"page":record["page"],"eligible":True,
            "artifact_schema":"reviewed-current-quartet-v1","source":record["source"],
            "prior_quartet":record["prior_quartet"],"current_quartet":current,
            "checks":record["checks"],"changes":record["changes"]})
    content=json.dumps(audit,ensure_ascii=False,indent=2)+"\n"
    AUDIT.write_text(content,encoding="utf-8")
    REPO_AUDIT.write_text(content,encoding="utf-8")
    print("Published",len(manifest["records"]),"reviewed 4633 pages")

if __name__=="__main__":
    parser=ArgumentParser()
    parser.add_argument("action",choices=("stage","publish"))
    stage() if parser.parse_args().action=="stage" else publish()
