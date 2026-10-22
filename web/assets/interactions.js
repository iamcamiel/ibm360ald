import { PAPER_PADDING, clamp, pageCode, pageTitle } from './geometry.js';

export function textRows(text) {
  const rows = [];
  const pattern = /([^\r\n]*)(\r\n|\r|\n|$)/g;
  for (const match of text.matchAll(pattern)) {
    if (!match[0]) break;
    const columns = [0];
    for (const char of match[1]) columns.push(columns.at(-1) + char.length);
    rows.push({ start: match.index, columns, text: match[1] });
  }
  return rows;
}

export function mergeSpans(spans) {
  const sorted = spans.filter(s => s.length === 3 && s.every(Number.isFinite) && s[2] > s[1])
    .map(s => [...s]).sort((a,b) => a[0]-b[0] || a[1]-b[1]);
  const result = [];
  for (const span of sorted) {
    const last = result.at(-1);
    if (last && last[0] === span[0] && span[1] <= last[2]) last[2] = Math.max(last[2], span[2]);
    else result.push(span);
  }
  return result;
}

export function netSpans(net) {
  const spans = [...(net.spans || [])];
  for (const [x1,y1,x2,y2] of net.segments || []) {
    if (y1 === y2) spans.push([y1,Math.min(x1,x2),Math.max(x1,x2)+1]);
    else if (x1 === x2) for (let row=Math.min(y1,y2);row<=Math.max(y1,y2);row++) spans.push([row,x1,x1+1]);
  }
  return mergeSpans(spans);
}

const inBox = (column,row,box) => box && column >= box[0] && column <= box[2] && row >= box[1] && row <= box[3];
const inSpans = (column,row,spans) => spans?.some(s => row === s[0] && column >= s[1] && column < s[2]);

export function hitEntities(data,column,row) {
  const annotations=(data.nets || []).filter(net=>inSpans(column,row,net.spans));
  if(annotations.length)return annotations.map(item=>({kind:'net',item}));
  const blocks = (data.blocks || []).filter(block => inBox(column,row,block.box));
  if (blocks.length) return blocks.map(item => ({kind:'block',item}));
  const portions = (data.portions || []).filter(item => inBox(column,row,item.box) || inSpans(column,row,item.spans));
  if (portions.length) return portions.map(item => ({kind:'portion',item}));
  const sockets = (data.sockets || []).filter(item => inBox(column,row,item.box) || inSpans(column,row,item.spans)
    || item.portions?.some(p => inSpans(column,row,p.spans)));
  if (sockets.length) return sockets.map(item => ({kind:'socket',item}));
  return (data.nets || []).filter(net => inSpans(column,row,netSpans(net))).map(item => ({kind:'net',item}));
}

export function readSelection(url = new URL(location.href)) {
  try {
    const raw = url.searchParams.get('selection');
    if (!raw || raw.length > 1024) return null;
    const value = JSON.parse(raw);
    return value && ['net','block','portion','socket'].includes(value.kind) ? value : null;
  } catch { return null; }
}

export function createInteractions({pre, viewport, inner, getMetrics, getPage, getPages, navigate, catalogueURL}) {
  let data = {}, selection = null, rows = [], request = null, generation = 0, down = null;
  const menu = document.getElementById('selection-menu');
  const clear = document.getElementById('clear-selection');
  const overlay = document.getElementById('selection-overlay');
  const label = document.getElementById('selection-name');
  const customHighlights = Boolean(globalThis.Highlight && globalThis.CSS?.highlights);

  const closeMenu = () => { menu.hidden = true;menu.replaceChildren(); };
  const boxSpans = box => box ? Array.from({length:box[3]-box[1]+1},(_,i)=>[box[1]+i,box[0],box[2]+1]) : [];

  function identify(value) {
    if (!value) return null;
    if (value.kind === 'net') return (data.nets || []).find(item => item.id === value.id);
    if (value.kind === 'block') return (data.blocks || []).find(item => item.id === value.id);
    if (value.kind === 'portion') return (data.portions || []).find(item => item.portion === value.portion && (!value.cardType || item.cardType === value.cardType));
    return (data.sockets || []).find(item => item.id === value.id);
  }

  function spansFor(value,item) {
    if (value.kind === 'net') return netSpans(item);
    if (value.kind === 'block') return boxSpans(item.box);
    if (value.kind === 'portion') return mergeSpans([...(item.spans || []),...boxSpans(item.box)]);
    const matches = (item.portions || []).filter(p => p.portion === value.portion && (!value.page || p.page === value.page));
    return mergeSpans(matches.length ? matches.flatMap(p=>p.spans || []) : item.spans || boxSpans(item.box));
  }

  function replaceBookmark(value) {
    const url = new URL(location.href);
    if (value) url.searchParams.set('selection',JSON.stringify(value));else url.searchParams.delete('selection');
    history.replaceState({...history.state,selection:value},'',url);
  }

  function select(value,{center=false,bookmark=true}={}) {
    closeMenu();overlay.replaceChildren();
    if (customHighlights) CSS.highlights.delete('ald-selected');
    selection = null;clear.hidden = true;
    const item = identify(value);
    if (!item) { if (bookmark) replaceBookmark(null);return false; }
    const spans = spansFor(value,item);
    const ranges = [];
    const text = pre.firstChild;
    for (const [r,a,b] of spans) {
      const line = rows[r];if (!line || !text) continue;
      const lo = clamp(a,0,line.columns.length-1), hi = clamp(b,0,line.columns.length-1);
      if (hi <= lo) continue;
      if (customHighlights) {
        const range = new Range();range.setStart(text,line.start+line.columns[lo]);range.setEnd(text,line.start+line.columns[hi]);ranges.push(range);
      } else {
        const m = getMetrics();const mark = document.createElement('span');
        Object.assign(mark.style,{left:`${PAPER_PADDING+a*m.columnPitch}px`,top:`${PAPER_PADDING+r*m.rowPitch}px`,width:`${(b-a)*m.columnPitch}px`,height:`${m.rowPitch}px`});overlay.append(mark);
      }
    }
    if (customHighlights) CSS.highlights.set('ald-selected',new Highlight(...ranges));
    selection = value;clear.hidden = false;
    label.textContent = value.kind === 'socket'
      ? `${item.label || item.id}${value.portion ? ` · portion ${value.portion}` : ''}`
      : value.kind === 'portion' ? `Portion ${item.cardType || value.cardType || ''}${item.portion}`
      : `${value.kind === 'net' ? 'Net' : 'Block'} ${item.label || item.id}`;
    if(value.kind==='socket' && value.portion && !(item.portions || []).some(p=>p.portion===value.portion && (!value.page || p.page===value.page))) {
      label.textContent=`${item.label || item.id} · portion ${value.portion} not located`;
    }
    clear.title = 'Clear selection (Escape)';
    if (bookmark) replaceBookmark(value);
    if (center && spans.length) {
      const m=getMetrics();const r=spans.map(s=>s[0]);const x=spans.flatMap(s=>[s[1],s[2]]);
      viewport.scrollTo(Math.max(0,m.left+(PAPER_PADDING+(Math.min(...x)+Math.max(...x))*m.columnPitch/2)*m.scaleX-viewport.clientWidth/2),
        Math.max(0,m.top+(PAPER_PADDING+(Math.min(...r)+Math.max(...r)+1)*m.rowPitch/2)*m.scaleY-viewport.clientHeight/2));
    }
    return true;
  }

  function positionMenu(x,y) {
    menu.hidden=false;
    const box=menu.getBoundingClientRect();
    menu.style.left=`${clamp(x,8,Math.max(8,innerWidth-box.width-8))}px`;
    menu.style.top=`${clamp(y,8,Math.max(8,innerHeight-box.height-8))}px`;
    (menu.querySelector('a,button') || menu).focus({preventScroll:true});
  }

  function heading(text) { const h=document.createElement('div');h.className='selection-menu-heading';h.textContent=text;menu.append(h); }
  function note(text) { const p=document.createElement('p');p.textContent=text;menu.append(p); }

  function context(value,x,y) {
    if (!select(value)) return;
    const item=identify(value);heading(item.label || `${value.kind} ${item.id || item.portion || ''}`);
    const links=item.links || [];
    for (const link of links) {
      const page=getPages().find(p=>p.id===link.pageId);
      if (!page) { note(link.note || link.label || 'This target page is not published.');continue; }
      const a=document.createElement('a');a.setAttribute('role','menuitem');
      const direction=value.kind==='net' ? (link.direction==='source' ? 'From ' : link.direction==='destination' ? 'To ' : '') : '';
      a.textContent=direction+(link.label || `${pageCode(page)} ${pageTitle(page)}`);
      const url=new URL(location.href);
      const unique=getPages().filter(p=>pageCode(p)===pageCode(page)).length===1;
      url.searchParams.set('page',unique?pageCode(page):page.id);
      if (link.selection) url.searchParams.set('selection',JSON.stringify(link.selection));else url.searchParams.delete('selection');
      a.href=url.href;
      a.addEventListener('click',event=>{
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();closeMenu();navigate(page,link.selection || null);
      });menu.append(a);
      if(link.note)note(link.note);
    }
    if (!links.length) note(value.kind==='net' ? 'No off-page destination is recorded for this net.' : 'No published card or socket-listing link is available.');
    for (const message of item.notes || []) note(message);
    positionMenu(x,y);
  }

  function asSelection(entity) {
    return entity.kind==='portion' ? {kind:'portion',portion:entity.item.portion,cardType:entity.item.cardType}
      : {kind:entity.kind,id:entity.item.id};
  }

  function locate(event) {
    if (!getMetrics()) return [];
    const rect=pre.getBoundingClientRect(), m=getMetrics();
    return hitEntities(data,Math.floor((event.clientX-rect.left)/(m.columnPitch*m.scaleX)),Math.floor((event.clientY-rect.top)/(m.rowPitch*m.scaleY)));
  }

  function chooseHit(hits,event,openContext) {
    if (!hits.length) { select(null);return; }
    if (hits.length===1) {
      const value=asSelection(hits[0]);if(openContext)context(value,event.clientX,event.clientY);else select(value);return;
    }
    // A plain crossing can contain two independent nets. Never join them or
    // silently choose one from the JSON array order.
    closeMenu();heading('Choose a wire at this crossing');
    for (const entity of hits) {
      const button=document.createElement('button');button.setAttribute('role','menuitem');button.textContent=entity.item.label || entity.item.id;
      button.addEventListener('click',()=>openContext ? context(asSelection(entity),event.clientX,event.clientY) : select(asSelection(entity)));menu.append(button);
    }
    positionMenu(event.clientX,event.clientY);
  }

  viewport.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY,button:event.button};});
  viewport.addEventListener('click',event=>{
    if (event.button!==0 || !down || Math.hypot(event.clientX-down.x,event.clientY-down.y)>4 || !window.getSelection()?.isCollapsed || viewport.classList.contains('can-pan') || viewport.classList.contains('panning')) return;
    chooseHit(locate(event),event,false);
  });
  viewport.addEventListener('contextmenu',event=>{
    if(event.shiftKey) return;
    const hits=locate(event);if(!hits.length)return;
    event.preventDefault();chooseHit(hits,event,true);
  });
  clear.addEventListener('click',()=>select(null));
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target))closeMenu();});
  document.addEventListener('keydown',event=>{
    if(document.querySelector('dialog[open]'))return;
    if(event.key==='Escape'){if(!menu.hidden)closeMenu();else select(null);}
    if(!menu.hidden && ['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      const items=[...menu.querySelectorAll('a,button')];const index=items.indexOf(document.activeElement);
      const next=event.key==='Home'?0:event.key==='End'?items.length-1:clamp(index+(event.key==='ArrowDown'?1:-1),0,items.length-1);
      items[next]?.focus();event.preventDefault();
    }
  });
  viewport.addEventListener('scroll',closeMenu,{passive:true});
  window.addEventListener('resize',closeMenu);

  return {
    async load(page,text,value=null) {
      const current=++generation;request?.abort();request=new AbortController();data={};rows=textRows(text);select(null,{bookmark:false});
      if(!page.interactionURL)return;
      try {
        const url=new URL(page.interactionURL,catalogueURL);
        const live=url.pathname===catalogueURL.pathname && url.searchParams.get('interaction')===page.id;
        if(url.origin!==location.origin || !url.pathname.startsWith(new URL('.',catalogueURL).pathname) || (!url.pathname.endsWith('.json') && !live))throw new Error('Invalid page links URL.');
        const response=await fetch(url,{signal:request.signal,cache:'no-cache'});
        if(!response.ok)throw new Error(`Page links request failed (${response.status}).`);
        const loaded=await response.json();
        if(current!==generation)return;
        if(loaded.textSha256!==page.textSha256 || loaded.schema!=='aldbrowser-interactions-v1')throw new Error('Page links do not match the displayed text.');
        data=loaded;
        if(value && !select(value,{center:true,bookmark:false})) {
          label.textContent='The referenced net or portion is not located on this page.';clear.hidden=false;
        }
      } catch(error) {
        if(error.name!=='AbortError' && current===generation)throw new Error('Wire and block selection could not be loaded. Try again to refresh the page links.',{cause:error});
      }
    },
    reset() { generation++;request?.abort();data={};select(null,{bookmark:false}); },
  };
}
