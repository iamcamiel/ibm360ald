"""Conservative current-shape metadata cleanup, with compact human notes.

Pure API: prune_history(raw, existing_notes=None) -> (clean_current, compact_notes).
No files are read/written and no source fact, coordinate, terminal alias or
acceptance Boolean is inferred. Unknown/ambiguous fields stay conservatively.
The caller owns current manifest/checkpoint refresh and existing review-notes TXT.
"""
from collections import Counter
from copy import deepcopy
import json,re

# Current data names that resemble provenance are deliberately protected.
CURRENT_KEYS={
 'source_reviewed','review_status','source_unknown_pin','pin_inferred','native_control_role_unresolved',
 'source_unlabelled','unlabeled','passive_terminal','native_commoned_contact','source_undriven','undriven_kind',
 'electrical_driver_unresolved','source_driver_unresolved','candidate_edges','uncertain_edges','fragment_ownership',
 'commoned_outputs','declared_physical_output_drivers','route_owners','source_reference','source_references',
 'source_top_border','source_position','source_wire_gaps','source_wire_status','source_gap_exception',
 'source_label_status','source_unknown_numeric_prefix','source_unknown_border_wedge','source_isolated_readable_port',
 'source_supported_unused','source_unused','source_unused_reason','source_terminal_role','source_printed_role',
 'source_symbol','source_border_symbol','source_unit','source_frame','source_format','source_dimensions',
 'source_gaps','source_open','source_open_reason','source_open_wire_objects','source_partial_wire_gaps',
 'source_uncertain_junctions','source_subcell_caps','source_unreadable_cells','source_exception','source_exceptions',
 'native_multiple_driver_exception','native_external_drivers','native_commoned_output_drivers','native_wired_OR',
 'native_commoned_contact','native_printed_card_portion','native_side','native_physical_side','native_border_qualifier',
 'native_wedge_shape','native_auxiliary_strap','native_geometric_origin','native_isolated_port_pair',
 'native_source_region','native_subcell_wire_interruptions','native_control_role','native_output_absence',
 'source_driver_not_printed','source_derived_reference_recovered','source_label_readable','source_visible',
 'source_pin','source_page','source_id','source_signal','source_pin_label','source_output_literal','source_name',
 'source_y','source_column','source_row','source_end','source_start','source_point','source_border',
 'source_electrical_verified','source_electrical_continuity_verified','visible_electrical_continuity_verified',
 'source_supported_passive_pullup','source_supported_local_jumper','source_supported_shared_physical_card',
 'source_joined_mechanical_contacts','source_right_hand_sink','source_top_border_port','source_mark_classification',
}
SOCKET_PROOF_KEYS={'socket_listing_evidence','supplemental_socket_listing_evidence','A1'}
SOCKET_METADATA={'source_listing','source_listings','native_evidence','detail','reason','source_record_binding','basis',
                 'source_derived_recovery_id','source_model','source_model_sha256','model_binding','source_binding','source_bindings'}
# The exact current match relation is retained, including conflicting alternatives.
SOCKET_FACTS={'kind','board','socket','sockets','physical_sockets','card_type','portion','portions','part_number',
              'full_part_number','location','status','records','record','page_key','actual_A1_page_key','listing_page',
              'A1_printed_page_citation','A1_citation_mismatch','ALD_page','not_applicable','printed_card_portion'}
ROOT_HISTORY={
 'source_review','independent_review','historical_independent_review','prior_independent_review','review_notes','notes',
 'provenance','recovery_provenance','independent_review_history','source_evidence','native_evidence','wiring_evidence',
 'source_review_evidence','source_crop_evidence','source_crops_directory','native_evidence_directory','scan_neighbors',
 'scan_order_neighbors','scan_order_neighbours','original_scan_neighbors','prior_neighbor_filenames','scan_order_evidence',
 'original_scan_inventory','source_inventory','source_output_inventory','source_bytes','source_mtime_ns','previous_verification_path',
 'source_derived_receipt','acceptance_record','coordinator_delegated_acceptance','previous_review_status',
 'previous_verification_sha256','native_visual_review_evidence','native_grid_proof','native_calibration_evidence',
 'physical_copy_review','physical_copy_review_file','physical_copy_review_sha256','human_physical_copy_acceptance',
 'returned_workbook_confirmation','returned_workbook_review','returned_workbook_physical_copy_review',
 'manual_verifications','manual_workbook_confirmations','manual_confirmed_readings','manual_verification_history',
 'manual_resolution_history','manual_resolution_receipt','resolved_by_physical_copy','resolved_manual_checks',
 'source_derived_recoveries','source_derived_recoveries_v2','source_derived_recoveries_v3','source_derived_recovery',
 'source_derived_confirmation','source_supported_resolution_application','firm_resolution_application',
 'source_final_repairs','final_source_corrections','source_native_repair','source_filename_correction','source_rename',
 'source_derived_root_acceptance','source_derived_recovery_validation','source_derived_owner_checks',
}
EXPLICIT_PROOF_KEYS={'evidence','source_evidence','native_evidence','source_note','source_review_note','review_note',
 'native_crop','crop','crop_path','crop_sha256','evidence_path','evidence_sha256','proof','authority','receipt',
 'independent_review','source_review','owner_review','root_review','historical_review','review_history',
 'source_record_binding','model_binding','source_binding','source_bindings','output_route_audit','direction_review',
 'physical_copy_reading','workbook_evidence','source_unused_evidence','role_evidence'}
SEMANTIC_FIELDS={'nodes','boxes','groups','pins','nets','wire_paths','junctions','paths','edges','cells','wire_cells','ports',
 'targets','driver','drivers','terminals','row','column','point','points','bounds','rows','columns','source_position',
 'printed_pins','printed_labels','printed_pin','pin','pin_number','reference','source_reference','source_references',
 'input_pin','output_pin','inputs','outputs','connected','commoned_outputs','board','socket','sockets','portion','card_type'}
HISTORY_NAME=re.compile(r'(?:^|_)(historical|superseded|prior|previous)(?:_|$)|(?:^|_)(corrections?|receipts?|acceptance|approvals?|review_batch[0-9]*)(?:_|$)')
REVIEW_NAME=re.compile(r'(?:^|_)(?:review|audit|approval|acceptance|proof|checks?|validation|verified|passed|findings)(?:_|$)')
MACHINE_ROOT_KEYS={'independent_review_complete','branch_pairs_checked','final_printer_grid_placement_accepted','owner_preview_reviewed','native_vs_text_visual_review_complete','root_passed','staged_complete'}
VALIDATION_GEOMETRY={'canvas','canvas_rows','canvas_columns','rows','columns','canvas_dimensions','printer_canvas','grid','max_width','max_columns','text_rows','maximum_columns'}
HASH_NAME=re.compile(r'(?:^|_)(?:sha256|hash)(?:_|$)')
PATH_PROOF=re.compile(r'(?:[A-Za-z]:[\\/]|(?:^|[/\\])tmp[/\\]|\.(?:png|jpg|tiff?|pdf|json|xlsx|py)(?:\b|$)|[0-9a-f]{64})',re.I)
SIGNIFICANT_NAME=re.compile(r'exception|disagree|conflict|limitation',re.I)
PAIR_KEYS=(('before','after'),('from','to'),('old','new'),('literal_before','literal_after'),('function_before','function_after'),
           ('reference_before','reference_after'),('original','corrected'),('old_function','new_function'),('old_unit','new_unit'))


def _json(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def _scalar(value):return value is None or type(value)in(bool,int,float,str)
def _brief(value):return isinstance(value,str)and len(value)<=320 and not PATH_PROOF.search(value)
def _semantic_payload(value):
    if isinstance(value,dict):return bool(set(value)&SEMANTIC_FIELDS)or any(_semantic_payload(v)for v in value.values())
    if isinstance(value,list):return any(_semantic_payload(v)for v in value)
    return False

def _has_printed_annotation(value):
    if isinstance(value,dict):
        return(bool(set(value)&{'row','column','point','at'})and bool(set(value)&{'text','glyph','label'}))or any(_has_printed_annotation(v)for v in value.values())
    if isinstance(value,list):return any(_has_printed_annotation(v)for v in value)
    return False

def _history_wrapper(key,value,root):
    if key in CURRENT_KEYS or key in SOCKET_PROOF_KEYS:return False
    if root and key in ROOT_HISTORY:return True
    if HISTORY_NAME.search(key):
        # A native correction ledger is history; a current candidate edge or
        # alias declaration is not removed just because it has an unusual name.
        return root or key.startswith(('historical_','superseded_','prior_','previous_'))
    if root and key.startswith(('human_','direct_human_','or_function_human_','additional_function_human_'))and re.search(r'correct|review|confirm|answer|workbook|verif|approval|accept',key):return True
    if root and key.startswith('source_derived_')and re.search(r'recover|infer|accept|receipt|corrobor|confirm|validat|review|owner|damage',key):return True
    if root and key.startswith(('root_','owner_','worker_','independent_'))and REVIEW_NAME.search(key):return True
    return False


def prune_history(raw,existing_notes=None):
    """Return detached current-shape JSON and concise notes; never a raw archive.

    All object/list ordering and scalar types survive outside explicit metadata.
    Ambiguous evidence that could itself encode geometry or electrical facts stays
    in the current model and is counted, rather than silently deleted.
    """
    if not isinstance(raw,dict):raise TypeError('A current page model must be a JSON object')
    corrections=[];exceptions=[];unresolved=[];removed=Counter();ambiguous=Counter();seen=set()
    def add(target,value):
        key=(id(target),_json(value))
        if key not in seen:seen.add(key);target.append(value)
    def harvest(value,category='',locator=None):
        locator=dict(locator or {})
        if isinstance(value,dict):
            for k in ('node','block','id','field','portion','row','column'):
                if k in value and _scalar(value[k])and not(isinstance(value[k],str)and PATH_PROOF.search(value[k])):locator[k]=deepcopy(value[k])
            for before,after in PAIR_KEYS:
                if before in value and after in value and _scalar(value[before])and _scalar(value[after]):
                    a,z=value[before],value[after]
                    if type(a)is type(z)and a==z:continue
                    if isinstance(a,str)and not _brief(a)or isinstance(z,str)and not _brief(z):continue
                    add(corrections,{**locator,'before':deepcopy(a),'after':deepcopy(z)})
            if SIGNIFICANT_NAME.search(category):
                facts={k:deepcopy(v)for k,v in value.items()if not any(w in k.lower()for w in ('sha256','hash','evidence','receipt','proof','review','binding','authority'))and(_scalar(v)and(not isinstance(v,str)or _brief(v)))}
                if facts:add(exceptions,{**locator,**facts})
            for k,v in value.items():
                if k not in ('authority','proof','source_binding','source_bindings','model_binding','independent_review','historical_acceptance'):
                    harvest(v,k,locator)
        elif isinstance(value,list):
            for v in value:harvest(v,category,locator)
        elif SIGNIFICANT_NAME.search(category)and _brief(value):add(exceptions,{**locator,'note':value})
    def proof(value):
        if isinstance(value,list):return [proof(v)for v in value]
        if not isinstance(value,dict):return deepcopy(value)
        result={}
        for k,v in value.items():
            if k in SOCKET_METADATA or HASH_NAME.search(k):removed[k]+=1;continue
            if k in ('records','record'):result[k]=proof(v)
            elif k in SOCKET_FACTS:result[k]=deepcopy(v)
            elif _history_wrapper(k,v,False)or k in EXPLICIT_PROOF_KEYS:removed[k]+=1;harvest(v,k)
            else:result[k]=walk(v,False,True);ambiguous['socket_listing_evidence.'+k]+=1
        return result
    def walk(value,root=False,semantic=False,path=''):
        if isinstance(value,list):return [walk(v,False,semantic,path+'/'+str(i))for i,v in enumerate(value)]
        if not isinstance(value,dict):return deepcopy(value)
        result={}
        for k,v in value.items():
            if k in CURRENT_KEYS:
                result[k]=walk(v,False,True,path+'/'+k)
                if SIGNIFICANT_NAME.search(k):harvest(v,k)
                if k in ('source_unknown_pin','native_control_role_unresolved','electrical_driver_unresolved','source_driver_unresolved')and v is True:add(unresolved,{'field':path+'/'+k,'status':'explicit unresolved current fact retained'})
                continue
            if k in SOCKET_PROOF_KEYS:result[k]=proof(v);continue
            if root and k=='source'and isinstance(v,dict)and any(isinstance(v.get(f),str)and re.search(r'\.tiff?$',v[f],re.I)for f in ('source','path','file','filename')):
                source_current={f:deepcopy(z)for f,z in v.items()if f in ('source','path','file','filename','sha256','source_sha256','page','title','printed_page','printed_title')}
                removed['source historical internals']+=len(v)-len(source_current);result[k]=source_current;continue
            if root and k=='validation':
                if isinstance(v,dict):
                    geometry={f:deepcopy(z)for f,z in v.items()if f in VALIDATION_GEOMETRY}
                    removed['validation machine checks']+=len(v)-len(geometry)
                    if geometry:result[k]=geometry
                else:removed[k]+=1
                continue
            if root and(k in MACHINE_ROOT_KEYS or type(v)is bool and re.search(r'_(?:reviewed|review_complete|checks_passed|review_passed|verified|accepted|checked)$',k)):
                removed[k]+=1;continue
            if root and k in ('source_sha256','native_source_sha256'):
                # One currently declared scan checksum is not an old artifact chain.
                result[k]=deepcopy(v);continue
            if root and k=='notes'and(
                isinstance(v,str)and not PATH_PROOF.search(v)or
                isinstance(v,(list,dict))and _has_printed_annotation(v)):
                result[k]=walk(v,False,True);ambiguous[k]+=1;continue
            if _history_wrapper(k,v,root):removed[k]+=1;harvest(v,k);continue
            if HASH_NAME.search(k):removed[k]+=1;continue
            if k in EXPLICIT_PROOF_KEYS:
                if semantic and(_semantic_payload(v)or type(v)in(bool,int,float)):
                    result[k]=walk(v,False,True);ambiguous[k]+=1
                elif semantic and isinstance(v,str)and v and not PATH_PROOF.search(v):
                    # A short explanation can be the only current exception/role
                    # statement. Keep it pending explicit human/tool disposition.
                    result[k]=v;ambiguous[k]+=1
                    if SIGNIFICANT_NAME.search(k):harvest(v,k)
                else:removed[k]+=1;harvest(v,k)
                continue
            if k=='native_A1_disagreement':removed[k]+=1;harvest(v,'disagreement');continue
            if root and k in ('rendered_text_sha256','preview_sha256','review_notes_sha256','source_mtime_ns','source_bytes'):
                removed[k]+=1;continue
            if root and k=='source_size'and type(v)is int:removed[k]+=1;continue
            if root and(k.startswith(('legacy_','native_','source_'))and any(t in k for t in ('review','correction','recovery','provenance','history','proof'))):
                # Unrecognized mixed facts stay intact, not a broad source_ purge.
                ambiguous[k]+=1
            result[k]=walk(v,False,semantic or k in SEMANTIC_FIELDS,path+'/'+k)
        return result
    clean=walk(raw,True)
    # A short current summary, not a replay of old checks/receipts/every hash.
    source=raw.get('source')
    if isinstance(source,dict):source=next((source[k]for k in ('source','path','file','filename')if isinstance(source.get(k),str)),None)
    notes={'source_scan':deepcopy(source),'current_review_status':{k:deepcopy(raw[k])for k in ('source_reviewed','review_status')if k in raw},
           'significant_literal_corrections':corrections,'exceptions':exceptions,'unresolved':unresolved,
           'cleanup_counts':{'metadata_fields_removed':sum(removed.values()),'ambiguous_fields_retained':sum(ambiguous.values())},
           'retained_ambiguous_field_names':sorted(ambiguous)}
    if isinstance(existing_notes,str):
        # Preserve only concise explicit literal arrows, not previous receipts,
        # hashes, all old uncertainty questions, or full native-review narration.
        for line in existing_notes.splitlines():
            line=line.strip()
            # Reusing this cleaner must not discard the short, current notes
            # produced on an earlier pass. This is not a historical archive.
            match=re.match(r'^(Correction|Exception):\s*(\{.*\})$',line)
            if match:
                try:
                    item=json.loads(match.group(2))
                    if isinstance(item,dict):
                        add(corrections if match.group(1)=='Correction'else exceptions,item)
                        continue
                except json.JSONDecodeError:pass
            if '→'in line and _brief(line):add(corrections,{'note':line})
            elif re.match(r'^(?:CURRENT )?(?:EXCEPTION|LIMITATION):',line,re.I)and _brief(line):add(exceptions,{'note':line})
    return clean,notes


def render_compact_notes(notes):
    """Plain TXT for the existing per-page review-notes file; no new notes tree."""
    lines=[]
    if notes.get('source_scan'):lines.append('Source: '+str(notes['source_scan']))
    status=notes.get('current_review_status',{})
    if status:lines.append('Current review: '+', '.join(k+'='+_json(v)for k,v in status.items()))
    for field,title in [('significant_literal_corrections','Correction'),('exceptions','Exception'),('unresolved','Unresolved')]:
        for item in notes.get(field,[]):lines.append(title+': '+_json(item))
    return '\n'.join(lines)+'\n'
