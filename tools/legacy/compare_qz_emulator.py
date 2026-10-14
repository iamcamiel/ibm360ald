import json, re, hashlib, collections, csv, sys
from pathlib import Path
ROOT=Path(r'D:\Github\IBM360')
OUT=ROOT/'ALD_Visual_Transcriptions'/'QZ ROS Listing'
SRC=ROOT/'ibm360m65'/'src'/'ros.txt'
VHDL=ROOT/'ibm360m65'/'src'/'vhdl'/'rosmem.vhd'
doc=json.loads((OUT/'ROS words.json').read_text(encoding='utf-8'))
positions=doc['field_positions']; names=list(positions)
def parity(bits):
 return [sum(int(bits[i]) for i in rng)%2 for rng in [range(1,100),range(2,43),list(range(43,69))+[85],list(range(69,85))+list(range(86,100))]]
def decoded(bits):
 fields={f:''.join(bits[i] for i in pp) for f,pp in positions.items()}
 active={f:int(fields[f],2) for f in names if f not in ['ND','P1','P2','P3','P4','HW','EW','UA','NEXT_HI','NEXT_MID','NEXT_LO']}
 active['E']=int(fields['EW']+fields['E'],2)
 active['H']=int(fields['HW']+fields['H'],2)
 active['U']=int(fields['UA']+fields['U'],2)
 active['NEXT']=int(fields['NEXT_HI']+fields['NEXT_MID']+fields['NEXT_LO'],2)<<2
 return fields,active
emu={};format_issues=[]
for n,line in enumerate(SRC.read_text().splitlines(),1):
 if not line.strip():continue
 tokens=line.split();a=f'{int(tokens[0],16):04X}';groups=tokens[1:]
 assert a not in emu,(a,n)
 assert len(tokens[0])==3 and all(set(g)<=set('01') for g in groups),(a,n)
 well_formed=len(groups)==len(names) and all(len(g)==len(positions[f]) for g,f in zip(groups,names))
 # Reproduce the loader's character loop. Unwritten bits begin zero in ros[].
 dta=[0]*100;d=0;loaded=[]
 for ch in line[4:]:
  if len(loaded)>=100:break
  if ch in '01':dta[d]=2*dta[d]+int(ch);loaded.append(ch)
  elif ch==' ':d+=1;dta[d]=0
  else:raise ValueError((a,n,ch))
 bits=''.join(loaded).ljust(100,'0');assert len(bits)==100
 if not well_formed:format_issues.append({'address':a,'line':n,'group_widths':[len(g) for g in groups],'printed_bit_count':len(''.join(groups)),'loaded_bit_count':len(loaded),'effect':'Field boundaries are decoded exactly as the loader does; any unwritten bit cells retain their zero initialization.'})
 loader_controls={f:dta[names.index(f)] for f in ['W','A','B','C','D','F','G','L','K','J','M','N','P','Q','R','T','V']}
 loader_controls.update(E=dta[8]|(dta[22]<<4),H=dta[12]|(dta[11]<<5),U=dta[28]|(dta[29]<<4),NEXT=((dta[14]<<6)|(dta[15]<<2)|dta[16])<<2)
 emu[a]={'bits':bits,'line':n,'loader_controls':loader_controls,'well_formed':well_formed}
qz={r['address']:r for r in doc['records']}
assert len(emu)==len(qz)==2816 and set(emu)==set(qz)
records=[];field_count=collections.Counter();plane=collections.defaultdict(collections.Counter)
for a,q in qz.items():
 eb=emu[a]['bits'];qb=q['ND']+q['ros_bits'];assert len(qb)==100 and set(qb)<=set('01')
 qfields,qactive=decoded(qb);efields,eactive=decoded(eb)
 if emu[a]['well_formed']:assert eactive==emu[a]['loader_controls'],a
 eactive=emu[a]['loader_controls']
 assert qfields==q['fields']
 diffs=[i for i,(x,y) in enumerate(zip(qb,eb)) if x!=y]
 controls=[{'field':f,'qz':qactive[f],'emulator':eactive[f]} for f in qactive if qactive[f]!=eactive[f]]
 field_diffs=[{'field':f,'qz_bits':qfields[f],'emulator_bits':efields[f],'positions':[i for i in positions[f] if i in diffs]} for f in names if qfields[f]!=efields[f]]
 category='control or next-address difference' if controls else 'parity only' if any(i in diffs for i in [1,20,85,91]) else 'ND only' if diffs else 'exact match'
 if controls and all(c['field']=='NEXT' for c in controls):category='next-address only'
 if controls and qfields['P1']!=efields['P1']:category='word allocation difference'
 if qb[1]!=eb[1]:category='loader word-validity difference'
 elif controls and not diffs:category='field-boundary decode difference'
 elif controls and qb[1]==eb[1]=='1':category='stray bits in unused word'
 field_count.update(f['field'] for f in field_diffs)
 plane[q['plane']][category]+=1
 p=parity(eb);unused=eb[1:]=='1'+'0'*98
 rec={'address':a,'category':category,'all_100_cells_match':not diffs,'ROS_99_bits_match':qb[1:]==eb[1:],'ND_matches':qb[0]==eb[0],
      'differing_bit_positions':diffs,'field_differences':field_diffs,'decoded_control_differences':controls,'qz_bits_including_ND':qb,'emulator_bits_including_ND':eb,
      'qz_parity_checks':q['parity_checks'],'emulator_parity_checks':p,'emulator_unused_word':unused,'emulator_parity_valid':p==[1,1,1,1] or unused,
      'qz_unused_word':qb[1:]=='1'+'0'*98,'qz_ec_level':q['ec_level'],'cas_page':q['cas_page'],'cas_box':q['cas_box'],'qz_source_file':q['source_file'],'qz_source_row':q['source_row'],
      'qz_word_valid_flag':qb[1]=='0','emulator_word_valid_flag':eb[1]=='0',
      'emulator_loader_parity_valid':eb[1]=='1' or p[1:]==[1,1,1],
      'emulator_source_line':emu[a]['line'],'emulator_input_well_formed':emu[a]['well_formed'],'qz_recoveries':q['recoveries'],'qz_CAS_reconciliation':q.get('cas_reconciliation')}
 records.append(rec)
vhdl={};order=[]
for n,line in enumerate(VHDL.read_text().splitlines(),1):
 m=re.search(r'"([01]{100})"\s*,?\s*-- ROS word ([0-9a-fA-F]{3,4})',line)
 if m:
  a=f'{int(m[2],16):04X}';assert a not in vhdl;vhdl[a]={'bits':m[1],'line':n};order.append(a)
assert len(vhdl)==2816 and set(vhdl)==set(emu)
for index,a in enumerate(order):
 value=int(a,16);actual=((value & 0x07c)<<5)|((value & 0xf80)>>5)|(value & 3)
 assert index==actual,(index,a,actual)
vhdl_diffs=[{'address':a,'source_line':v['line'],'bit_positions':[i for i,(x,y) in enumerate(zip(emu[a]['bits'],v['bits'])) if x!=y],
             'emulator_bits':emu[a]['bits'],'vhdl_bits':v['bits']} for a,v in vhdl.items() if v['bits']!=emu[a]['bits']]
vhdl_decode_diffs=[]
for a,v in vhdl.items():
 fields,controls=decoded(v['bits']);loader=emu[a]['loader_controls']
 diff=[{'field':f,'VHDL':controls[f],'software_loader':loader[f]} for f in controls if controls[f]!=loader[f]]
 if diff:vhdl_decode_diffs.append({'address':a,'fields':diff})
summary={'addresses_compared':len(records),'missing_from_emulator':[],'extra_in_emulator':[],
 'exact_100_cell_matches':sum(r['all_100_cells_match'] for r in records),'exact_99_bit_ROS_matches':sum(r['ROS_99_bits_match'] for r in records),
 'words_with_control_or_next_address_differences':sum(bool(r['decoded_control_differences']) for r in records),
 'category_counts':dict(collections.Counter(r['category'] for r in records)), 'differing_fields_word_counts':dict(field_count),
 'differing_bit_cells':sum(len(r['differing_bit_positions']) for r in records),'noncanonical_parity_or_unused_patterns':[r['address'] for r in records if not r['emulator_parity_valid']],
 'emulator_loader_parity_failures':[r['address'] for r in records if not r['emulator_loader_parity_valid']],
 'loader_word_validity_differences':[r['address'] for r in records if r['qz_word_valid_flag']!=r['emulator_word_valid_flag']],
 'by_plane':{str(k):dict(v) for k,v in plane.items()},'emulator_input_format_issues':format_issues,'VHDL_words_compared':len(vhdl),'VHDL_words_differing_from_emulator':len(vhdl_diffs),'VHDL_vs_software_loader_control_differences':vhdl_decode_diffs}
result={'summary':summary,'sources':{'QZ_lookup':str(OUT/'ROS words.json'),'emulator_ROS':str(SRC),'emulator_loader':str(ROOT/'ibm360m65'/'hercules'/'360_ros.cpp'),'VHDL_ROS':str(VHDL)},
 'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC,VHDL,ROOT/'ibm360m65'/'hercules'/'360_ros.cpp',OUT/'ROS words.json']},
 'method':'Compare all 100 printed cells without reversal: ND at index 0, 99 ROS bits at 1..99. Group widths and field order checked against the emulator input loader. Decode E/H/U extension bits and ten-bit next-address base as the emulator does. Parity/ND differences are separated from executable controls. No input or source-code changes are made.',
 'records':records,'VHDL_vs_emulator_differences':vhdl_diffs,'VHDL_vs_software_loader_control_differences':vhdl_decode_diffs}
report_name='ROS source validation' if '--post-fix' in sys.argv else 'Emulator comparison'
csv_name='ROS source validation differences' if '--post-fix' in sys.argv else 'Emulator differences'
(OUT/(report_name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/(csv_name+'.csv')).open('w',encoding='utf-8',newline='') as f:
 cols=['address','category','cas_page','cas_box','qz_ec_level','decoded_field_differences','raw_field_differences','differing_bit_positions','qz_source_row','emulator_source_line','qz_source_file']
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for r in records:
  if r['all_100_cells_match'] and not r['decoded_control_differences']:continue
  row={k:r[k] for k in cols if k in r}
  row['decoded_field_differences']='; '.join(f"{d['field']}: QZ {d['qz']:03X} vs emulator {d['emulator']:03X}" if d['field']=='NEXT' else f"{d['field']}: QZ {d['qz']} vs emulator {d['emulator']}" for d in r['decoded_control_differences'])
  row['raw_field_differences']='; '.join(f"{d['field']}: {d['qz_bits']} / {d['emulator_bits']}" for d in r['field_differences'])
  row['differing_bit_positions']=' '.join(map(str,r['differing_bit_positions']));w.writerow(row)
print(json.dumps(summary,indent=2))
print('CONTROL DIFFERENCES')
for r in records:
 if r['decoded_control_differences']:print(r['address'],r['category'],r['cas_page'],r['cas_box'],r['decoded_control_differences'])
print('VHDL differences',[(r['address'],r['bit_positions']) for r in vhdl_diffs])
