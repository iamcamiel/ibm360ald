"""Read-only native functional-v4 browser view. No v3 source or conversion."""
import argparse, hashlib, importlib.util, json, math, os, re
from pathlib import Path
SCHEMA='https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json'
QUALIFIED_RENDERER_SHA256='a969a8d990aa69c0a1bd6b42a56322bfa562fd1e46e648d8b3700f3c095ae4fa'
def strict_json(text):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate JSON object key: '+key)
            value[key]=item
        return value
    def constant(token):raise ValueError('Non-finite JSON number: '+token)
    def number(token):
        value=float(token)
        if not math.isfinite(value):raise ValueError('Non-finite JSON number: '+token)
        return value
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant,parse_float=number)

def load(path):
    path=Path(path).resolve(strict=True)
    data=strict_json(path.read_text('utf-8'))
    if data.get('$schema')!=SCHEMA or not isinstance(data.get('page'),dict) or any(not isinstance(data.get(k),list) for k in ('blocks','nets','inputs','outputs')):
        raise ValueError('Unsupported functional page schema or structure')
    details=None; review=data.get('review',{})
    ref=review.get('details')
    if ref is not None:
        if not isinstance(ref,str) or not ref or '\\' in ref or ':' in ref or any(x in ('','..','.') for x in ref.split('/')):
            raise ValueError('Unsafe review details reference')
        target=(path.parent/ref).resolve(strict=True)
        if not target.is_relative_to(path.parent):raise ValueError('Review details escape page directory')
        details=strict_json(target.read_text('utf-8'))
        digest=hashlib.sha256(json.dumps({k:v for k,v in data.items() if k!='review'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if not isinstance(details,dict) or details.get('page')!=data['page'].get('page') or details.get('content sha256')!=digest:raise ValueError('Review details content hash mismatch')
    elif review.get('unresolved discrepancies') is True:
        raise ValueError('Unresolved page requires content-bound review details')
    return data,details

def publication_issues(details):
    issues = (details or {}).get('publication issues')
    if not isinstance(issues, dict):
        return None
    result = {}
    for key, limit in (('status', 64), ('summary', 1200)):
        value = issues.get(key)
        if isinstance(value, str):
            value = ' '.join(value.split())
            if value:
                result[key] = value if len(value) <= limit else value[:limit - 1] + '…'
    return result or None


def input_source_reference(entry):
    style = entry.get('reference style', 'inline')
    if style not in ('inline', 'hanging'):
        raise ValueError('Unknown input reference style')
    return entry.get('real net number', entry['net number']) if style == 'hanging' else entry['net number']

def view(path,renderer_path):
    data,details=load(path)
    if hashlib.sha256(Path(renderer_path).read_bytes()).hexdigest()!=QUALIFIED_RENDERER_SHA256:
        raise ValueError('Renderer semantics differ from the qualified browser geometry adapter; review required')
    spec=importlib.util.spec_from_file_location('aldbrowser_standalone_renderer',renderer_path)
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    options=(details or {}).get('writer options',{})
    if not isinstance(options,dict):raise ValueError('Invalid writer options')
    ending=options.get('line ending','LF');trim=options.get('trim trailing spaces',False)
    if ending not in ('LF','CRLF') or type(trim) is not bool:raise ValueError('Invalid writer options')
    text=renderer.render_page(data,details,trim_trailing_spaces=trim,line_ending='\r\n' if ending=='CRLF' else '\n').decode('utf-8')
    offsets={d['num']:d['deviation'] for d in data.get('column deviations',[]) if d['type']=='block'}
    blocks=[]
    for b in data['blocks']:
        n=int(b['grid position'][:-1]);x=27+23*n+offsets.get(n,0);y=2+7*renderer.GRID_LETTERS.index(b['grid position'][-1])
        blocks.append({'id':b['serial'],'label':b['serial']+' · '+str(b.get('function','')),'cardType':b.get('card',''),'portion':b.get('portion',''),'site':b.get('socket',''),'box':[x,y,x+7,y+b.get('height',6)]})
    outputs={o['net number']:o for o in data['outputs']};inputs={i['net number']:i for i in data['inputs']}
    footer_spans={};footer_index=0
    masks={u['field']:u.get('visible text') for u in (details or {}).get('uncertainties',[]) if u.get('status')=='unresolved' and isinstance(u.get('visible text'),str)}
    for n in sorted(data['nets'],key=lambda n:n['net number'] or ''):
        if not n.get('connectors'):continue
        number=n['net number'];printed=masks.get('outputs/'+number+'/net number',number[len(data['page']['page']):])
        for i,connector in enumerate(n['connectors']):
            local=connector[2:] if connector and len(connector)>=2 and connector[:2].isdigit() else connector
            literal=printed+' '+local if i==0 else '  '+connector
            col=35+14*(footer_index//9);row=94+footer_index%9
            footer_spans.setdefault(number,[]).append([row,col,col+len(literal)]);footer_index+=1
    nets=[]
    for net in data['nets']:
        number=net['net number'];segments=[]
        for route in net['routing']:
            segments.extend([a+b for a,b in zip(route,route[1:]) if a!=b])
        out=outputs.get(number)
        if out and len(out['sinks'])>1:
            c=204-out.get('hanging wire length',1)
            for i in range(0,len(out['sinks']),4):
                below=out['line']+1+i//4
                segments.extend([[c,out['line'],c,below],[c,below,205,below]])
        spans=list(footer_spans.get(number,[]));source_refs=[]
        member_inputs=[i for identity,i in inputs.items() if 'inputs/'+identity in net['nodes']]
        for inp in member_inputs:
            row=inp['line'];offset=sum(d['deviation'] for d in data.get('column deviations',[]) if d['type']=='entry-reference')
            spans.append([row,1,1+len(inp['name'])])
            identity=inp['net number'];source_refs.append(input_source_reference(inp))
            refrow=row+(inp.get('reference style','inline')=='hanging')
            spans.append([refrow,32+offset,32+offset+len(renderer.input_reference_display(identity,details))])
            if refrow!=row:spans.append([refrow,1,2+len(inp.get('real net number',identity))])
            elif inp.get('real net number',identity)!=identity:
                spans.append([row+1,1,2+len(inp['real net number'])])
        targets=[]
        if out:
            row=out['line'];spans.append([row,211,242+len(number)-len(data['page']['page'])])
            for i,sink in enumerate(out['sinks']):
                col=205 if len(out['sinks'])==1 else renderer.SINK_COLUMNS[i%4]
                r=row if len(out['sinks'])==1 else row+1+i//4
                spans.append([r,col,col+len(sink)])
            for sink in out['sinks']:
                m=re.match(r'^([A-Z]{2}\d{3})',sink)
                if m and m[1] not in targets:targets.append(m[1])
        nets.append({'id':number,'identity':number,'label':number,'segments':segments,'spans':spans,'destinationPages':targets,'sourceReferences':list(dict.fromkeys(source_refs))})
    return {'modelSha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'format':'v4','page':data['page']['page'],'title':' '.join(data['page'].get('title',[])), 'text':text,'textSha256':hashlib.sha256(text.encode()).hexdigest(),'userApproved':False,'reviewStatus':data.get('review',{}).get('status','unreviewed'),'reviewBound':details is not None,'publicationIssues':publication_issues(details),'unresolvedCount':sum(u.get('status')=='unresolved' for u in (details or {}).get('uncertainties',[])),'blocks':blocks,'nets':nets}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('page');p.add_argument('renderer');a=p.parse_args()
    print(json.dumps(view(a.page,a.renderer),ensure_ascii=False,separators=(',',':')))
