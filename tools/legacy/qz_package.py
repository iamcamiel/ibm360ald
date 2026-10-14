import json,csv,sys,collections
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
O=Path(__file__).parent;sys.path.insert(0,str(O));from qz_decode import LENGTHS,NAMES
C=O/'qz';OUT=Path(r'D:\Github\IBM360\ALD_Visual_Transcriptions\QZ ROS Listing');OUT.mkdir(exist_ok=True)
seq=list(range(0x58))+list(range(0x80,0xd8));refs=json.loads((C/'manual-references.json').read_text());modes=json.loads((C/'manual-modes.json').read_text());plan=json.loads((O.parent/'ald-renaming'/'rename-plan.json').read_text());source_map={Path(v['newpath']).stem:v for v in plan};records=[];unresolved=[]
def write_text(path,text):
 path.write_bytes(text.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
def line(parts,width=226):
 a=[' ']*width
 for col,value in parts:
  for k,ch in enumerate(value):
   if col+k<len(a):a[col+k]=ch
 return ''.join(a).rstrip()
for p in sorted(C.glob('* resolved.json')):
 stem=p.stem[:-9];unit=int(stem[-4:]);part=int(stem[6:8]);g=json.loads(p.read_text());meta=json.loads((C/(stem+' metadata.json')).read_text());left=json.loads((C/(stem+' fields.json')).read_text());slots=g['geometry']['slots'];headers=[(0,'HEX'),(9,'BINARY'),(29,'PAGE'),(35,'BOX'),(46,'MODE'),(210,'EC LEVEL VERSION')];ranges=[];pos=0
 for name,length in zip(NAMES,LENGTHS):
  headers.append((60+slots[pos],name if not name.startswith('NEXT_') else ''));ranges.append((60+slots[pos],str(pos)));pos+=length
 headers.append((60+slots[47],'NEXT ADDRESS'))
 lines=[line([(9,'ADDRESS'),(29,'CLD'),(108,'BIT CONFIGURATION')]),line(ranges),line(headers)]
 for n,r in enumerate(g['rows']):
  a=r['address'];ref=refs[a];values=r['resolved_bits'];assert len(values)==100;mode=modes.get(a,left[n]['fields']['mode']);mode='SCAN' if mode=='SCAN' else 'ERROR' if mode=='ERROR' else '-';groups={};at=0
  for name,length in zip(NAMES,LENGTHS):groups[name]=''.join(' ' if v is None else v for v in values[at:at+length]);at+=length
  word=''.join(' ' if v is None else v for v in values[1:]);original=''.join(' ' if c.get('scan_value',values[i]) is None else c.get('scan_value',values[i]) for i,c in enumerate(r['cells']))
  recovered=[]
  for cell in r['cells']:
   if cell.get('recovery') and cell['recovery'] not in recovered:recovered.append(cell['recovery'])
  checks=r['parity_checks'];parity_ok=checks==[1,1,1,1] or (checks==[1,0,0,0] and word=='1'+'0'*98);status='unresolved_scan_bits' if r['unknown_columns'] else 'parity_exception' if not parity_ok else 'corrected_or_recovered' if recovered else 'complete';addr=int(a,16);b=f'{addr:012b}';binary=' '.join(b[k:k+4] for k in range(0,12,4))
  rec={'address':a,'plane':unit,'scan_part':part,'source_file':source_map[stem]['newpath'],'source_row':n+1,'hex_printed':f'{addr:03X}','binary_address':b,'cas_page':ref['cas_page'],'cas_box':ref['cas_box'],'reference_verification':ref['verification'],'mode':mode,'ND':groups['ND'],'ros_bits':word,'ros_word':word if ' ' not in word else None,'scan_bits_including_ND':original,'fields':groups,'ec_level':meta[n]['verified_ec_level'],'version':'','parity_checks':checks,'status':status,'cross_check_ready':status in ['complete','corrected_or_recovered'],'unknown_bit_positions':r['unknown_columns'],'recoveries':recovered}
  records.append(rec);data=[(0,f'{addr:03X}'),(9,binary),(29,ref['cas_page']),(35,ref['cas_box']),(46,mode),(210,rec['ec_level'])]
  for i,v in enumerate(values):data.append((60+slots[i],' ' if v is None else v))
  lines.append(line(data))
  for col in r['unknown_columns']:unresolved.append({'address':a,'column':col,'source':stem,'box':r['cells'][col]['box']})
 date='22 MAY 70' if unit==7 else '25 JAN 71' if unit in [10,11,14] else '21 MAY 70';log='046' if unit in [1,4] else '104' if unit==7 else '601' if unit in [10,11,14] else '047'
 history=[('19 MAY 70','713671')]+([('22 MAY 70','714944')] if unit==7 else [('25 JAN 71','714952')] if unit==10 else [('04 SEP 70','714949'),('25 JAN 71','714952')] if unit==11 else [('04 JAN 71','714952')] if unit==14 else [])
 footer=[[(160,'│ ADDRESS LIST          UNIT. '+f'{unit:04}'),(216,'Q')],[(160,'│ DATE  '+date+'       MACH. C7201-02'),(216,'Z')],[(160,'│ LOG   '+log+'   UNIT P.N. '+str(2583900+unit)),(216,f'{unit:02}'[0])],[(160,'│ FRAME 01    PAGE P.N. '+str(2583920+unit)),(216,f'{unit:02}'[1])],[(160,'│ IBM CORP.  SDD   PAGE '+f'{part:02}'),(216,'1')]]
 for i,(hdate,ec) in enumerate(history):footer[5-len(history)+i].append((122,hdate+'   '+ec))
 lines+=['','']+[line(parts) for parts in footer]
 write_text(OUT/(stem+'.txt'),'\n'.join(lines)+'\n')
assert len(records)==2816 and len({r['address'] for r in records})==2816
for plane in range(16):assert [int(r['address'],16)%256 for r in records if r['plane']==plane]==seq
for a in ['0536','0537']:
 r=next(r for r in records if r['address']==a);assert r['parity_checks']==[1,1,1,1] and r['cross_check_ready']
doc={'schema_version':1,'description':'QZ ROS listing, 16 planes, 176 addresses per plane; 100 printed bit cells comprising one ND indicator and 99 ROS bits.','unknown_representation':'Blank characters retain their fixed position; ros_word is null if any bit is unresolved. Unknown positions are listed separately. No question mark stands for an unreadable bit.','parity_validation':'Empirical odd parity checks: all ROS bits 1–99; bits 2–42; bits 43–68 plus bit 85; bits 69–84 plus bits 86–99. The unused-word pattern has bit 1 set and all other ROS bits zero. Parity exceptions are flagged, not silently changed.','field_positions':{name:list(range(sum(LENGTHS[:i]),sum(LENGTHS[:i+1]))) for i,name in enumerate(NAMES)},'control_field_combinations':{'E':'EW (bit 81), then E (21–24)','H':'HW (36–37), then H (38–42)','U':'UA (96), then U (92–95)'},'records':records}
(OUT/'ROS words.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
columns=['address','plane','scan_part','source_row','cas_page','cas_box','mode','ec_level','version','ros_bits','status','cross_check_ready','unknown_bit_positions','parity_checks']+NAMES+['source_file']
with (OUT/'ROS words.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=columns,quoting=csv.QUOTE_ALL);w.writeheader()
 for r in records:
  v={k:r[k] for k in columns if k in r};v.update(r['fields']);v['unknown_bit_positions']=' '.join(map(str,r['unknown_bit_positions']));v['parity_checks']='' if r['parity_checks'] is None else ''.join(map(str,r['parity_checks']));w.writerow(v)
issues=[]
for i,r in enumerate(records):
 if r['cross_check_ready']:continue
 before=records[i-1] if i else None;after=records[i+1] if i+1<len(records) else None
 issues.append({'address':r['address'],'reason':r['status'],'unknown_ros_bit_positions':' '.join(map(str,r['unknown_bit_positions'])),'cas_page':r['cas_page'],'cas_box':r['cas_box'],'source_file':r['source_file'],'source_row':r['source_row'],'preceding_address':before['address'] if before else '','preceding_CAS':(before['cas_page']+' '+before['cas_box']).strip() if before else '','following_address':after['address'] if after else '','following_CAS':(after['cas_page']+' '+after['cas_box']).strip() if after else ''})
with (OUT/'Review index.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['address','reason','unknown_ros_bit_positions','cas_page','cas_box','source_file','source_row','preceding_address','preceding_CAS','following_address','following_CAS'],quoting=csv.QUOTE_ALL);w.writeheader();w.writerows(issues)
count=collections.Counter(r['status'] for r in records);summary={'text_files':80,'ROS_records':2816,'planes':16,'addresses_per_plane':176,'cross_check_ready':sum(r['cross_check_ready'] for r in records),'status_counts':dict(count),'unresolved_bits':len(unresolved),'originals_modified':False}
(OUT/'Validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
notes=['QZ ROS LISTING TEXT AND LOOKUP','', '80 UTF-8 text files; 16 ROS planes; 176 addresses in each plane; 2816 records.','Intentional gaps are preserved: low address bytes 00–57 and 80–D7.','Text uses spaces and fixed character positions, with no tabs. Use a monospaced','font and turn word wrapping off. File names match the TIFF sources.','', 'ROS words.csv and ROS words.json provide the machine-readable lookup.','The address has four hexadecimal digits. The scan prints three hexadecimal','digits and a 12-bit binary address. ND is outside the 99-bit ROS word.','E, H and U each have a separate extension bit or bits, as described in JSON.','', f"{summary['cross_check_ready']} rows have complete bit contents and satisfy the parity checks.",f"{count['parity_exception']} rows have parity exceptions after visual review. Their readings are",'retained and marked cross_check_ready=false pending a CAS or physical check.',f"{count['unresolved_scan_bits']} rows contain {len(unresolved)} unresolved bits. Their positions are blank",'in the text and ros_bits string; ros_word is null. Do not use them to reject','a CAS transcription. Review index.csv gives the source row, CAS location,','and the preceding and following addresses and CAS locations.','Unresolved scan bits.png shows the target bit inside a red rectangle.','', 'Parity agreement is a useful consistency check, not proof of every reading.','CAS references were visually reviewed for all rows. Two faint references','were additionally resolved from their CAS boxes: 0C29 is QQ541 Q6; 0E01 is','QQ451 J4. Core cross_check_ready excludes unreadable bits and parity exceptions.','EC levels and mode fields were checked with scan-specific glyph recognition','and enlarged visual review of difficult cases.','', '0536 and 0537 were recovered from QJ031 G9 and QS051 E6. Both now satisfy','all four parity checks. CAS recovered fields.json records every recovered','field, its bit positions, micro-order, CAS source and reference-page number.','0537 P2=1 was derived from parity and is marked separately.','The tear also affects 0535, whose unresolved bits remain blank.','', 'The table columns and printed bit-group spacing are retained. The heading','and title block are re-set on the same character grid; physical scan skew','and paper damage are not reproduced. Handwriting is excluded.','Original TIFFs have not been changed.']
write_text(OUT/'Read me.txt','\n'.join(notes)+'\n')
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',15);out=Image.new('RGB',(1440,max(1,(len(unresolved)+7)//8)*150),'white');d=ImageDraw.Draw(out);ims={}
if not unresolved:d.text((20,30),'No blank bit cells remain. See CAS reconciliation notes for labelled inferences and corrections.',font=font,fill='black')
for i,v in enumerate(unresolved):
 if v['source'] not in ims:ims[v['source']]=Image.open(C/(v['source']+'.png'))
 x,y,xx,yy=v['box'];cx=(x+xx)/2;cy=(y+yy)/2;patch=ImageOps.autocontrast(ims[v['source']].crop((cx-48,cy-37,cx+48,cy+37)));px=i%8*180;py=i//8*150;d.text((px,py),v['address']+' BIT '+str(v['column']),font=font,fill='blue');out.paste(patch,(px+30,py+25));d.rectangle((px+78-(xx-x)/2,py+26,px+78+(xx-x)/2,py+97),outline='red')
out.save(OUT/'Unresolved scan bits.png')
for p in OUT.glob('QZ*.txt'):
 b=p.read_bytes();assert not b.startswith(b'\xef\xbb\xbf');assert b'\t' not in b;s=b.decode('utf-8');assert len([line for line in s.splitlines() if len(line)>=23 and line[0:3].strip() and all(ch in '0123456789ABCDEF' for ch in line[0:3]) and line[9:13].strip() in ['0000','0001','0010','0011','0100','0101','0110','0111','1000','1001','1010','1011','1100','1101','1110','1111']])==(32 if '-05 ' in p.name else 36)
print(summary)
