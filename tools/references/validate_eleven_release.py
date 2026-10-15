"""Fail-closed proof that the accepted eleven-page function corrections reached the repository."""
import copy
import hashlib
import json
from pathlib import Path

HISTORY_KEY = "source_eleven_function_corrections_v1"
HUMAN_TEXT = "AP531 is `✲A`; DT001 is A, with a triangle on its output, show me an example of a matching shape that reads OR please; XM181 is A; AS201 is TD; AP313 is A"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def require(condition,message):
    if not condition:raise ValueError("Eleven-function release: "+message)

def ref_ok(ref):
    return isinstance(ref,dict) and isinstance(ref.get("path"),str) and isinstance(ref.get("sha256"),str) and sha(ref["path"])==ref["sha256"]

def pointer_get(obj,pointer):
    for part in pointer.lstrip("/").split("/"):
        part=part.replace("~1","/").replace("~0","~")
        obj=obj[int(part)] if isinstance(obj,list) else obj[part]
    return obj

def pointer_set(obj,pointer,value):
    parts=[p.replace("~1","/").replace("~0","~") for p in pointer.lstrip("/").split("/")]
    target=obj
    for p in parts[:-1]:target=target[int(p)] if isinstance(target,list) else target[p]
    last=parts[-1]
    if isinstance(target,list):target[int(last)]=value
    else:target[last]=value

def exact_original_json_bytes(obj,current_bytes):
    for newline in ("\n","\r\n"):
        for end in ("","\n"):
            candidate=(json.dumps(obj,indent=2,ensure_ascii=False)+end).replace("\n",newline).encode("utf-8")
            if candidate==current_bytes:return newline,end
    raise ValueError("Eleven-function release: accepted JSON serialization changed")

def validate(release_path,repo,pages,sources,file_sources):
    release=read(release_path)
    require(release.get("schema_version")=="card-db-eleven-function-release-v1","release schema mismatch")
    require(release.get("history_key")==HISTORY_KEY,"history key mismatch")
    bindings={}
    for key in ("stage_manifest","independent_acceptance","publication_receipt","native_candidate_record","human_candidate_record"):
        binding=release.get(key)
        require(ref_ok(binding),"missing/stale "+key)
        bindings[key]=read(binding["path"])
    stage,audit,pub=bindings["stage_manifest"],bindings["independent_acceptance"],bindings["publication_receipt"]
    native,human=bindings["native_candidate_record"],bindings["human_candidate_record"]
    require(stage.get("history_key")==HISTORY_KEY and len(stage.get("pages",[]))==11,"stage page set/history mismatch")
    require(stage.get("native_candidate_record")==release["native_candidate_record"] and stage.get("human_candidate_record")==release["human_candidate_record"],"stage evidence binding mismatch")
    require(human.get("direct_human_authority",{}).get("text")==HUMAN_TEXT and stage.get("direct_human_authority",{}).get("text")==HUMAN_TEXT and release.get("direct_human_authority",{}).get("text")==HUMAN_TEXT,"verbatim human authority mismatch")
    require(audit.get("passed") is True and not audit.get("failures") and audit.get("manifest")==release["stage_manifest"] and audit.get("counts",{}).get("pages")==11,"independent audit mismatch")
    require(pub.get("manifest")==release["stage_manifest"] and pub.get("independent_audit")==release["independent_acceptance"] and pub.get("pages")==11 and pub.get("canonical_quartet_files")==44 and pub.get("repository_writes")==0 and pub.get("original_scan_writes")==0,"publication mismatch")
    require(len(release.get("releases",[]))==11,"release entry count mismatch")
    stage_pages={p["page"]:p for p in stage["pages"]}
    audit_pages={p["page"]:p for p in audit["reviewed_pages"]}
    release_pages={p["page"]:p for p in release["releases"]}
    require(len(stage_pages)==len(audit_pages)==len(release_pages)==11 and set(stage_pages)==set(audit_pages)==set(release_pages),"page identity set mismatch")
    require(sum(p["authority_kind"]=="native" for p in release_pages.values())==7 and sum(p["authority_kind"]=="direct-human" for p in release_pages.values())==4,"authority split mismatch")
    published={str(x["path"]).replace("/","\\"):x["sha256"] for x in pub["canonical_destinations"]}
    required={(p["page"],str(p["scan_id"])) for p in stage_pages.values()}
    result={}
    for page_name,staged in stage_pages.items():
        entry=release_pages[page_name];audited=audit_pages[page_name]
        scan=str(staged["scan_id"])
        require((page_name,scan) in required and scan==str(entry["scan_id"])==str(audited["scan_id"]),"scan mismatch "+page_name)
        require(entry["authority_kind"]==staged["authority_kind"]==audited["authority_kind"],"authority kind mismatch "+page_name)
        require(entry["authority_kind"] in ("native","direct-human"),"unrecognized authority kind "+page_name)
        require(entry["text_span"]==staged["text_edit"]==audited["text_edit"],"text span mismatch "+page_name)
        require(entry["active_model_changes"]==staged["active_model_changes"]==audited["active_model_changes"],"active alias mismatch "+page_name)
        require(staged["authority_record"]==release["native_candidate_record" if entry["authority_kind"]=="native" else "human_candidate_record"],"candidate authority mismatch "+page_name)
        require(ref_ok(staged["source_crop"]) and ref_ok(staged["broad_context_crop"]),"source crops stale "+page_name)
        require(staged["source"]["sha256"]==entry["original_TIFF_sha256"]==audited["source"]["sha256"],"original source mismatch "+page_name)
        page=pages.get(scan)
        require(page and page["page"]==page_name and page["text_path"]==entry["text_path"],"current accepted text identity mismatch "+page_name)
        source_sha=sources[page["original_source_id"]]["sha256"]
        require(source_sha==entry["original_TIFF_sha256"],"current original source hash mismatch "+page_name)
        model_rel=entry["model_path"]
        require(model_rel in file_sources,"current accepted model absent "+page_name)
        text_sha=sources[page["text_source_id"]]["sha256"]
        model_sha=sources[file_sources[model_rel]]["sha256"]
        require(text_sha==entry["accepted_text_sha256"]==staged["candidate_quartet"]["txt"]["sha256"]==audited["candidate_text_sha256"],"current accepted text hash mismatch "+page_name)
        require(model_sha==entry["accepted_model_sha256"]==staged["candidate_quartet"]["json"]["sha256"]==audited["candidate_model_sha256"],"current accepted model hash mismatch "+page_name)
        for kind in ("txt","json","notes","preview"):
            c=staged["canonical_quartet"][kind]
            q=staged["candidate_quartet"][kind]
            require(published.get(str(c["path"]).replace("/","\\"))==q["sha256"]==sha(c["path"]),"published quartet mismatch "+page_name+" "+kind)
        text_bytes=(repo/entry["text_path"]).read_bytes(); text=text_bytes.decode("utf-8")
        lines=text.splitlines(keepends=True);span=entry["text_span"]
        row,col,before,after=span["row"],span["column"],span["before"],span["after"]
        require(isinstance(row,int) and isinstance(col,int) and len(before)==len(after) and 0<=row<len(lines) and lines[row][col:col+len(after)]==after,"corrected text cell mismatch "+page_name)
        lines[row]=lines[row][:col]+before+lines[row][col+len(after):]
        require(hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()==staged["before_quartet"]["txt"]["sha256"],"text differs beyond approved span "+page_name)
        model_bytes=(repo/model_rel).read_bytes();model=json.loads(model_bytes)
        newline,end=exact_original_json_bytes(model,model_bytes)
        history=model.pop(HISTORY_KEY,None)
        require(history==staged["history"] and history.get("authority_kind")==entry["authority_kind"],"exact new model history mismatch "+page_name)
        require(hashlib.sha256(json.dumps(history,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()==entry["history_sha256"],"history hash mismatch "+page_name)
        require(history.get("predecessor_text_sha256")==staged["before_quartet"]["txt"]["sha256"] and history.get("predecessor_model_sha256")==staged["before_quartet"]["json"]["sha256"],"history predecessor mismatch "+page_name)
        for change in entry["active_model_changes"]:
            require(pointer_get(model,change["pointer"])==change["after"],"current active alias mismatch "+page_name)
            pointer_set(model,change["pointer"],change["before"])
        restored=(json.dumps(model,indent=2,ensure_ascii=False)+end).replace("\n",newline).encode("utf-8")
        require(hashlib.sha256(restored).hexdigest()==staged["before_quartet"]["json"]["sha256"],"model differs beyond approved aliases/history "+page_name)
        ptr=entry["node_pointer"]
        require(ptr==entry["active_model_changes"][0]["pointer"].rsplit("/",1)[0],"node pointer mismatch "+page_name)
        result[(scan,ptr)]={"page":page_name,"authority_kind":entry["authority_kind"],"text_span":span,"history_JSON_pointer":"/"+HISTORY_KEY,"release_page":page_name}
    return result
