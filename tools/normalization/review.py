"""Current content-bound review metadata; no implicit human approval."""
from copy import deepcopy
from hashlib import sha256
import math,struct

STATUSES=('unreviewed','partial','wiring-checked','approved','needs-review')
WIRING=('unreviewed','partial','checked')
FIELDS={'status','user_approved','content_sha256','source_status','wiring_status','approved_at','approval_statement'}

def content_digest(document):
    h=sha256()
    def walk(value):
        if value is None:h.update(b'N')
        elif type(value)is bool:h.update(b'B1'if value else b'B0')
        elif type(value)is int:
            data=str(value).encode('ascii');h.update(b'I'+str(len(data)).encode('ascii')+b':'+data)
        elif type(value)is float:
            if not math.isfinite(value):raise ValueError('Nonfinite current content number')
            h.update(b'F'+struct.pack('>d',value))
        elif isinstance(value,str):
            data=value.encode('utf8');h.update(b'S'+str(len(data)).encode('ascii')+b':'+data)
        elif isinstance(value,list):
            h.update(b'A'+str(len(value)).encode('ascii')+b':')
            for item in value:walk(item)
        elif isinstance(value,dict):
            h.update(b'O'+str(len(value)).encode('ascii')+b':')
            for key in sorted(value):walk(key);walk(value[key])
        else:raise ValueError('JSON values required')
    walk({k:v for k,v in document.items()if k!='review'})
    return h.hexdigest()

def make(document,source_status='unreviewed',wiring_status='unreviewed',approval=None):
    approved=approval is not None
    return dict(status='approved'if approved else'wiring-checked'if wiring_status=='checked'else'partial'if wiring_status=='partial'else'unreviewed',
                user_approved=approved,content_sha256=content_digest(document),source_status=source_status,
                wiring_status=wiring_status,approved_at=approval.get('recorded_utc')if approved else None,
                approval_statement=(approval.get('user_statement')or'\n'.join(approval.get('user_approval_statements',[])))if approved else None)

def refresh(document,previous):
    result=deepcopy(previous);current=content_digest(document)
    if result['content_sha256']!=current:
        result.update(content_sha256=current,status='needs-review',user_approved=False,
                      source_status='needs-review',wiring_status='unreviewed',approved_at=None,approval_statement=None)
    return result

def validate(document):
    r=document.get('review')
    if not isinstance(r,dict)or set(r)!=FIELDS:raise ValueError('Canonical review fields required')
    if r['status']not in STATUSES or r['wiring_status']not in WIRING or type(r['user_approved'])is not bool:raise ValueError('Invalid current review state')
    if r['source_status']not in ('reviewed','unreviewed','needs-review'):raise ValueError('Missing source review state')
    if r['content_sha256']!=content_digest(document):raise ValueError('Review belongs to another content version')
    if r['user_approved']!=(r['status']=='approved'):raise ValueError('Approval status and flag disagree')
    if r['user_approved']:
        if not isinstance(r['approved_at'],str)or not isinstance(r['approval_statement'],str)or not r['approval_statement'].strip():raise ValueError('Explicit user approval evidence required')
    elif r['approved_at']is not None or r['approval_statement']is not None:raise ValueError('Unapproved content cannot carry active approval evidence')
    if r['status']=='wiring-checked'and r['wiring_status']!='checked':raise ValueError('Wiring review state disagrees')
    return r

def approve(document,statement,approved_at,expected_content_sha256):
    """Explicit human approval only; caller supplies the reviewed content hash.

    This is a pure candidate operation. Publication must atomically refresh
    Source status, repository inventory and dependent review bindings.
    """
    validate(document)
    if not isinstance(statement,str) or not statement.strip():raise ValueError('Explicit human statement required')
    if not isinstance(approved_at,str) or not approved_at.strip():raise ValueError('Approval timestamp required')
    if expected_content_sha256!=content_digest(document):raise ValueError('Approval targets another content version')
    result=deepcopy(document)
    result['review'].update(status='approved',user_approved=True,approved_at=approved_at,approval_statement=statement)
    validate(result)
    return result
