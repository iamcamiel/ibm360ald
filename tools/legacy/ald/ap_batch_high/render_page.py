import json
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

ROOT=Path('D:/Github/IBM360')
OUT=ROOT/'ALD_Visual_Transcriptions/ALD Diagrams'

class Page:
    def __init__(self,page,title,source,work,W=260,H=110):
        self.page=page;self.title=title;self.source=str(source);self.work=Path(work);self.W=W;self.H=H
        self.nodes={};self.paths=[];self.labels=[];self.junctions=[];self.nets={};self.notes=[]
    def node(self,ident,x,y,function,unit,card,location,grid):
        self.nodes[ident]={'id':ident,'column':x,'row':y,'function':function,'unit':unit,'card_type':card[:4],'portion':card[4:],'printed_card_portion':card,'location':location,'grid':grid,'source_reviewed':True}
    def text(self,x,y,s):self.labels.append({'column':x,'row':y,'text':s})
    def wire(self,net,*points):self.paths.append({'net':net,'points':[list(p)for p in points]})
    def join(self,net,x,y):
        value={'net':net,'column':x,'row':y}
        if value not in self.junctions:self.junctions.append(value)
    def pin(self,node,pin,row,side='input',triangle=True,border_marker=None):
        n=self.nodes[node];x=n['column'];label=(pin or '')
        physical_pin=(pin or '').replace('✲','')
        record={'pin':physical_pin or None,'printed_pin':pin or None,'row':row,'side':side,'triangle':triangle,'source_reviewed':True,'border_marker':border_marker}
        if side=='input':
            prior=[r for r in n.get('pins',[])if r['side']=='input']
            existing=next((r for r in prior if r['row']==row and r['pin']==(physical_pin or None)),None)
            record['terminal_id']=existing['terminal_id'] if existing else node+'.'+(physical_pin or 'input'+str(len(prior)+1))
        else:record['terminal_id']=node+'.'+(physical_pin or 'output')
        if record not in n.setdefault('pins',[]):n['pins'].append(record)
        if side=='input':
            self.text(x-len(label),row,label+(border_marker or ('◺'if triangle else '')));record['marker_column']=x if triangle or border_marker else None;return x-len(label)-1,row
        self.text(x+7,row,border_marker or '◺') if triangle or border_marker else None
        self.text(x+8,row,label);record['marker_column']=x+7 if triangle or border_marker else None
        return x+8+len(label),row
    def net(self,name,driver,targets,external=None,classification=None,evidence=None):
        # A visible isolated strap has no source driver. Accept the old private
        # helper token only as a migration aid, never as a claimed output.
        if driver=='LOCAL PRINTED REFERENCE':
            driver=None;classification='isolated_jumper'
        if driver is None:
            assert classification=='isolated_jumper',(name,classification)
        self.nets[name]={'id':name,'driver':driver,'targets':targets,'external':external,'source_reviewed':True}
        if classification:self.nets[name]['classification']=classification
        if evidence:self.nets[name]['native_evidence']=evidence
    def export(self,status='source reviewed'):
        cells=defaultdict(lambda:defaultdict(set));edges=defaultdict(set)
        for p in self.paths:
            for a,b in zip(p['points'],p['points'][1:]):
                x,y=a;X,Y=b;assert x==X or y==Y,(p,a,b)
                dx=(X>x)-(X<x);dy=(Y>y)-(Y<y)
                while(x,y)!=(X,Y):
                    xx,yy=x+dx,y+dy
                    cells[x,y][p['net']].add((dx,dy));cells[xx,yy][p['net']].add((-dx,-dy))
                    edges[tuple(sorted(((x,y),(xx,yy))))].add(p['net']);x,y=xx,yy
        shared=[{'edge':k,'nets':list(v)}for k,v in edges.items()if len(v)>1]
        assert not shared,shared[:20]
        owners=defaultdict(list)
        for net in self.nets.values():
            for target in net['targets']:owners[target].append(net['id'])
        assert all(len(v)==1 for v in owners.values()),dict(owners)
        graphs=defaultdict(lambda:defaultdict(set))
        for(a,b),ns in edges.items():
            for n in ns:graphs[n][a].add(b);graphs[n][b].add(a)
        # Explicitly documented repeated physical pins may carry the same net
        # through a component depiction. These logical links are not printed
        # wire strokes and must never be drawn across the block's text.
        for link in getattr(self,'physical_pin_feedthroughs',[]):
            n=link['net'];a=tuple(link['left_endpoint']);b=tuple(link['right_endpoint'])
            assert a in graphs[n] and b in graphs[n],link
            graphs[n][a].add(b);graphs[n][b].add(a)
        for n,graph in graphs.items():
            seen=set();todo=[next(iter(graph))]
            while todo:
                v=todo.pop()
                if v not in seen:seen.add(v);todo.extend(graph[v]-seen)
            assert len(seen)==len(graph),n
        refs=json.loads((ROOT/'ALD_Visual_Transcriptions/A1 Socket Listing/ALD references.json').read_text(encoding='utf-8'))['ALD_pages'][self.page]
        cards=[r for r in refs if r['kind']=='card portion']
        for n in self.nodes.values():
            match=[r for r in cards if r['board']=='02'+n['location'][:4] and n['location'][4:] in r['sockets'] and r['card_type']==n['card_type'] and r['portion']==n['portion']]
            if len(match)!=1:
                assert getattr(self,'allow_A1_mismatch',False),(n,match)
                n['socket_listing_evidence']=None
                n['A1_match_status']='literal source portion absent from A1 page records'
            else:n['socket_listing_evidence']=match[0]
        # A wire endpoint directly beside a printed pin connects horizontally
        # through that annotation. Include its direction only in the render mask.
        for n in self.nodes.values():
            for pin in n.get('pins',[]):
                label=pin.get('printed_pin') or ''
                x=n['column']-len(label)-1 if pin['side']=='input' else n['column']+8+len(label)
                key=(x,pin['row'])
                if key in cells:
                    direction=(1,0) if pin['side']=='input' else (-1,0)
                    for dirs in cells[key].values():dirs.add(direction)
        grid=[[' ']*self.W for _ in range(self.H)]
        corners={frozenset(((1,0),(0,1))):'┌',frozenset(((-1,0),(0,1))):'┐',frozenset(((1,0),(0,-1))):'└',frozenset(((-1,0),(0,-1))):'┘'}
        crossings=[]
        for(x,y),by in cells.items():
            dirs=set().union(*by.values())
            if len(by)>1:crossings.append({'column':x,'row':y,'nets':list(by),'joined':False})
            grid[y][x]=corners.get(frozenset(dirs),'┼' if len(dirs)>2 else('│'if any(d[1]for d in dirs)else'─'))
        for j in self.junctions:
            assert set(cells[j['column'],j['row']])=={j['net']},j
            grid[j['row']][j['column']]='◇'
        def put(x,y,s):
            assert 0<=y<self.H and 0<=x and x+len(s)<=self.W,(x,y,s)
            grid[y][x:x+len(s)]=s
        for n in self.nodes.values():
            x,y=n['column'],n['row'];put(x,y,'┌──────┐')
            for r in range(1,7):put(x,y+r,'│      │')
            for r,s in ((1,n['function']),(3,n['unit']),(4,n['printed_card_portion']),(5,n['location']),(6,n['grid']+'──'+n['id'])):put(x+1,y+r,s)
        for l in self.labels:put(l['column'],l['row'],l['text'])
        erased=[j for j in self.junctions if grid[j['row']][j['column']]!='◇']
        assert not erased,erased
        erased_turns=[]
        for (x,y),by in cells.items():
            dirs=set().union(*by.values());expected=corners.get(frozenset(dirs))
            if expected and not any(n['column']<=x<n['column']+8 and n['row']<=y<=n['row']+6 for n in self.nodes.values()) and grid[y][x]!=expected:erased_turns.append({'column':x,'row':y,'expected':expected,'actual':grid[y][x],'nets':list(by)})
        assert not erased_turns,erased_turns
        txt='\n'.join(''.join(r)for r in grid)+'\n'
        allowed=json.loads((OUT/'Allowed characters.json').read_text(encoding='utf-8'))['allowed_characters']
        assert not set(txt)-set(allowed),set(txt)-set(allowed)
        lower=sorted(set(ch for ch in txt if ch.islower()));assert not lower,lower
        title_rows=[''.join(r) for r in grid]
        date_line=next(r for r in title_rows[93:103] if 'MACH.' in r)
        part_line=next(r for r in title_rows[93:103] if 'P.N.' in r)
        assert date_line[239]!=' ' and date_line[240]==' ' and date_line[241]=='│',date_line[210:242]
        assert part_line[239]!=' ' and part_line[240]==' ' and part_line[241]=='│',part_line[210:242]
        printed=sum(sum((p['side']=='input' or p.get('role')=='passive receiving terminal')for p in n['pins'])for n in self.nodes.values())
        checked=sum(sum(t.split('.')[0]in self.nodes for t in n['targets'])for n in self.nets.values())
        assert printed==checked,(printed,checked)
        isolated=[n for n in self.nets.values()if n['driver']is None]
        assert all(n.get('classification')=='isolated_jumper'for n in isolated),isolated
        undriven={t for n in isolated for t in n['targets']if t.split('.')[0]in self.nodes}
        driven=printed-len(undriven)
        for n in self.nodes.values():
            for pin in n['pins']:
                if pin['side']=='input' or pin.get('role')=='passive receiving terminal':
                    assert pin['terminal_id'] in owners,pin
                    pin['net']=owners[pin['terminal_id']][0]
                    if pin['terminal_id']in undriven:pin['electrical_status']='undriven isolated jumper terminal'
        bad_ports=[]
        interior_wires=[]
        for n in self.nodes.values():
            x,y=n['column'],n['row']
            for r in range(y+1,y+6):
                for c in range(x+1,x+7):
                    if (c,r) in cells:interior_wires.append({'node':n['id'],'column':c,'row':r,'nets':list(cells[c,r])})
            for pin in n.get('pins',[]):
                label=pin.get('printed_pin') or ''
                endpoint=(x-len(label)-1,pin['row']) if pin['side']=='input' else (x+8+len(label),pin['row'])
                term=pin['terminal_id']
                expected=[q['id'] for q in self.nets.values() if (term in q['targets'] if pin['side']=='input' or pin.get('role')=='passive receiving terminal' else q['driver']==term or term in q.get('physical_drivers',[]))]
                if not expected:bad_ports.append({'node':n['id'],'terminal':term,'reason':'no declared owning net'})
                elif not set(expected).issubset(cells.get(endpoint,{})):bad_ports.append({'node':n['id'],'terminal':term,'endpoint':endpoint,'expected':expected,'actual':list(cells.get(endpoint,{}))})
        assert not interior_wires,interior_wires
        assert not bad_ports,bad_ports
        bank_columns=[50,73,96,119,142,165,188]
        approval_path=self.work/'human grid approval.json'
        grid_approval=None
        if approval_path.exists():
            grid_approval=json.loads(approval_path.read_text(encoding='utf-8'))
            assert grid_approval['page']==self.page and grid_approval.get('apply') is True and grid_approval.get('coordinator_verified_direct_human_approval') is True,grid_approval
            bank_columns=grid_approval['block_left_columns']
        printer_grid=self.W==245 and self.H==103 and all(n['column']==bank_columns[int(n['grid'][0])-1] and n['row'] in range(2,87,7) for n in self.nodes.values())
        assert printer_grid,(self.page,bank_columns)
        checks={'A1_card_portions_matched':sum(n['socket_listing_evidence']is not None for n in self.nodes.values()),'A1_unmatched_nodes':[n['id']for n in self.nodes.values()if n['socket_listing_evidence']is None],'A1_total_card_portions':len(cards),'printed_input_terminals':printed,'input_targets_owned_once':checked,'different_net_shared_segments':shared,'disconnected_nets':[],'junctions_visible_in_txt':len(self.junctions),'wire_turns_erased_by_labels':erased_turns,'unreadable_characters':txt.count('�'),'passed':True,'uppercase_only':True,'title_part_label':'P.N.','title_value_trailing_blank_cells':1,'printer_grid_verified':printer_grid,'physical_ports_without_owning_net':bad_ports,'wire_cells_in_block_interiors':interior_wires}
        checks.update({'driven_input_terminal_count':driven,'driven_input_targets_owned_once':driven,'undriven_terminal_count':len(undriven),'undriven_terminals':sorted(undriven),'isolated_jumper_count':len(isolated)})
        inventory=json.loads((ROOT/'tmp/ald-text/ald/AP source inventory.json').read_text(encoding='utf-8'))
        if isinstance(inventory,dict):inventory=inventory.get('pages',inventory)
        neighbors=next((r for r in inventory if isinstance(r,dict)and r.get('page')==self.page),None) if isinstance(inventory,list)else inventory.get(self.page)
        data={'physical_pin_feedthroughs':getattr(self,'physical_pin_feedthroughs',[]),'native_function_glyph_audit':getattr(self,'function_glyph_audit',None),'page':self.page,'title':self.title,'source':self.source,'source_reviewed':True,'review_status':status,'nodes':list(self.nodes.values()),'nets':list(self.nets.values()),'wire_paths':self.paths,'junctions':self.junctions,'unjoined_crossings':crossings,'printed_labels':self.labels,'review_notes':self.notes,'validation':checks,'scan_neighbors':neighbors,'character_grid':{'width':self.W,'height':self.H,'note':getattr(self,'grid_note','Source character-cell positions normalized to keep separate rails and visible junctions.')}}
        output_dir=Path(getattr(self,'output_dir',OUT));output_dir.mkdir(parents=True,exist_ok=True)
        base=output_dir/Path(self.source).stem;base.with_suffix('.txt').write_text(txt,encoding='utf-8');base.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        notes=f'{self.page} source review\n\n{checks['A1_card_portions_matched']} of {len(self.nodes)} gate portions matched to A1. {len(self.nets)} explicit nets, {printed} printed inputs. All net paths are connected; no different nets share parallel segments. Every diamond remains visible in TXT. Native crops and transcription script are stored in {self.work}.\n\n'
        notes+=f'{driven} driven receiving terminals; {len(undriven)} undriven terminals in {len(isolated)} explicitly isolated local jumpers. No external or active driver is claimed for those straps.\n\n'
        notes+='\n'.join(json.dumps(n,ensure_ascii=False)for n in self.notes)
        notes+='\n\nOriginal scan neighbors\n'+json.dumps(neighbors,ensure_ascii=False,indent=2)+'\n'
        base.with_name(base.name+' review notes.txt').write_text(notes,encoding='utf-8')
        font=ImageFont.truetype(str(ROOT/'tmp/ald-text/JuliaMono-Regular.ttf'),20);im=Image.new('RGB',(self.W*12,self.H*18),'white');d=ImageDraw.Draw(im)
        for y,row in enumerate(txt.splitlines()):
            for x,ch in enumerate(row):
                if ch!=' ':d.text((x*12,y*18),ch,font=font,fill='black')
        im.save(self.work/'preview.png');im.crop((0,0,self.W*12,990)).save(self.work/'preview-upper.png');im.crop((0,990,self.W*12,self.H*18)).save(self.work/'preview-lower.png')
        base.with_name(base.name+' JuliaMono.png').write_bytes((self.work/'preview.png').read_bytes())
        (self.work/'reviewed.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return checks
