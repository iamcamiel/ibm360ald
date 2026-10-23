"""Fail closed on page-format drift. Run this before imports/publication and in CI."""
from pathlib import Path
from collections import Counter
import argparse,json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'page_text'))
from pages import SCHEMA,validate_current_page

def _pairs(items):
    value={}
    for key,item in items:
        if key in value:raise ValueError('Duplicate JSON key: '+key)
        value[key]=item
    return value
def loads(data):
    def invalid(value):raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(data.decode('utf-8-sig'),object_pairs_hook=_pairs,parse_constant=invalid)
def schema_check(value,schema,root=None,path='$'):
    """Check the closed JSON Schema vocabulary emitted by this release.

    Semantic reprojection and review digest validation add cross-field checks
    which JSON Schema alone cannot express.
    """
    import re
    root=schema if root is None else root
    if '$ref'in schema:
        ref=schema['$ref']
        if not ref.startswith('#/$defs/'):raise ValueError('External schema references are not allowed')
        return schema_check(value,root['$defs'][ref.split('/')[-1]],root,path)
    if 'anyOf'in schema:
        for alternative in schema['anyOf']:
            try:schema_check(value,alternative,root,path);return
            except ValueError:pass
        raise ValueError(path+': no declared representation matches')
    kind='null'if value is None else'boolean'if type(value)is bool else'integer'if type(value)is int else'number'if type(value)is float else'string'if isinstance(value,str)else'array'if isinstance(value,list)else'object'
    types=schema.get('type');types=[types]if isinstance(types,str)else types
    if types and kind not in types and not(kind=='integer'and'number'in types):raise ValueError(path+': incorrect JSON type')
    if 'const'in schema and value!=schema['const']:raise ValueError(path+': incorrect schema version')
    if 'enum'in schema and not any(type(value)is type(v)and value==v for v in schema['enum']):raise ValueError(path+': unknown enumerated value')
    if isinstance(value,dict):
        if not set(schema.get('required',[]))<=set(value):raise ValueError(path+': missing required fields')
        properties=schema.get('properties',{})
        if schema.get('additionalProperties')is False and set(value)-set(properties):raise ValueError(path+': unregistered fields '+str(sorted(set(value)-set(properties))))
        for key,item in value.items():
            if key in properties:schema_check(item,properties[key],root,path+'/'+key)
    elif isinstance(value,list):
        if len(value)<schema.get('minItems',0)or len(value)>schema.get('maxItems',float('inf')):raise ValueError(path+': incorrect item count')
        for i,item in enumerate(value):
            if 'items'in schema:schema_check(item,schema['items'],root,path+'/'+str(i))
    elif isinstance(value,str)and'pattern'in schema:
        if re.search(schema['pattern'],value)is None:raise ValueError(path+': incorrect text format')
    elif type(value)in(int,float)and'minimum'in schema and value<schema['minimum']:raise ValueError(path+': value below minimum')

def check_file(path,schema):
    data=Path(path).read_bytes();document=loads(data);schema_check(document,schema);validate_current_page(document)
    expected=(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf8')
    if data!=expected:raise ValueError('Canonical UTF-8/key-order/number serialization required')
    return document

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--model',type=Path);a=parser.parse_args()
    schema=loads((Path(__file__).parent/'ALD page schema.json').read_bytes());failures=[];counts=Counter();bindings={}
    if a.model:paths=[a.model]
    else:
        status=loads((a.repo/'notes/Source status.json').read_bytes());paths=[a.repo/r['repository']['json']['path']for r in status['records']if'json'in r['repository']]
        bindings={(a.repo/r['repository']['json']['path']).resolve():r['repository']for r in status['records']if'json'in r['repository']}
        expected={p.resolve()for p in paths}
        for path in(a.repo/'json').rglob('*.json'):
            if path.resolve()in expected:continue
            data=loads(path.read_bytes())
            if isinstance(data,dict)and str(data.get('schema','')).startswith('ibm360-ald-page-'):failures.append(dict(path=str(path),error='Unregistered page model outside current source status'))
    for i,path in enumerate(paths):
        try:
            document=check_file(path,schema)
            if path.resolve()in bindings:
                import layout
                binding=bindings[path.resolve()];text=(a.repo/binding['txt']['path']).read_bytes()
                if hashlib.sha256(path.read_bytes()).hexdigest()!=binding['json']['sha256']or hashlib.sha256(text).hexdigest()!=binding['txt']['sha256']or layout.render(document)!=text:raise ValueError('Current JSON/TXT checkpoint or exact render differs')
            counts['pages']+=1;counts['approved']+=int(document['review']['user_approved']);counts[document['current_extensions']['page_type']]+=1
        except(ValueError,KeyError,TypeError,OSError)as exc:failures.append(dict(path=str(path),error=str(exc)))
        if(i+1)%250==0:print(json.dumps(dict(checked=i+1,failures=len(failures))),flush=True)
    print(json.dumps(dict(passed=not failures,schema=SCHEMA,counts=dict(counts),failures=failures),ensure_ascii=False),flush=True)
    return int(bool(failures))
if __name__=='__main__':sys.exit(main())
