'use strict';
/* lane-board. Three screens — home, work, memory — and one command bar above them.
   Navigation is the palette (Cmd-K); esc always steps back out to home. */

const T=window.__T;
const THEMES=['system','light','dark'];
function applyTheme(v){if(v==='light'||v==='dark')document.documentElement.dataset.theme=v;else delete document.documentElement.dataset.theme;
  try{localStorage.setItem('lane-theme',v)}catch{}
  const b=document.getElementById('theme');if(b){b.textContent=v==='light'?'☀':v==='dark'?'☾':'◐';b.title='Theme: '+v+'. Click to cycle system → light → dark'}}
{let th=new URLSearchParams(location.search).get('theme');if(!th){try{th=localStorage.getItem('lane-theme')}catch{}}applyTheme(THEMES.includes(th)?th:'system')}

const S={view:'home',board:null,lane:null,repo:null,sel:{},data:null,diff:null,diffKey:'',busy:null,dialog:false,
  filter:'',startedAt:null,fails:0,diffAll:false,mem:null,mscope:'cross',mfile:null,
  pal:{open:false,q:'',rows:[],i:0}};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const api=async(p,o={})=>{const r=await fetch(p,{...o,headers:{'X-Token':T,'Content-Type':'application/json'}});let j={};try{j=await r.json()}catch{}
  if(r.status===403){toast('err','Server restarted — reload the page');throw new Error('restarted')}
  if(!r.ok)throw Object.assign(new Error(j.error||j.output||r.statusText),{output:j.output});return j};
/* where you were: a browser refresh should not cost you your place. Home stays the
   fallback for a first visit or a lane that has since gone away. */
const LSg=(k,d)=>{try{return localStorage.getItem(k)??d}catch{return d}};
const LSs=(k,v)=>{try{v==null?localStorage.removeItem(k):localStorage.setItem(k,v)}catch{}};
function rememberPlace(){LSs('lane-view',S.view);LSs('lane-last',S.lane||'');LSs('lane-lastrepo',S.repo||'')}
const ico=(n,c='')=>`<svg class="ic${c?' '+c:''}" viewBox="0 0 16 16"><use href="#g-${n}"/></svg>`;
const plural=(n,w)=>`${n} ${w}${n===1?'':'s'}`;

function prettyName(id,ticket){
  // the ticket field holds a full Jira URL — a visitor wants the key, not the link
  let tk=(/([A-Z]+-\d+)/.exec(ticket||'')||[])[1]||'';
  const m=/^([A-Z]+-\d+)-(.+)$/.exec(id);
  let s=id;
  if(m){tk=tk||m[1];s=m[2]}
  // a tail like "6237" is a second ticket number, not a name — then the id itself is the name
  if(!s||/^[\d-]+$/.test(s))return[id,''];
  s=s.replace(/[-_]+/g,' ').trim();
  return[s.charAt(0).toUpperCase()+s.slice(1),tk];
}
// Goal and resume notes are written by and for developers, in markdown. Show one clean sentence,
// not a wall of prose with backticks and branch names in it.
function plain(s){
  return String(s||'')
    .replace(/`([^`]*)`/g,'$1').replace(/\*\*([^*]*)\*\*/g,'$1')
    .replace(/(^|\s)[_*]([^_*\n]+)[_*](?=\s|$)/g,'$1$2')
    .replace(/\[([^\]]+)\]\([^)]*\)/g,'$1')
    .replace(/https?:\/\/\S+/g,'').replace(/\s+/g,' ').trim();
}
function firstSentence(s,max){
  s=plain(s);if(!s)return'';
  const m=/^(.{20,}?[.!?])(\s|$)/.exec(s);
  let out=m?m[1]:s;
  if(out.length>max)out=out.slice(0,max).replace(/\s+\S*$/,'')+'…';
  return out;
}
function daysAgo(d){
  if(!d)return'';
  const t=new Date(d+'T00:00:00'),n=new Date();n.setHours(0,0,0,0);
  const k=Math.round((n-t)/86400000);
  return k<=0?'today':k===1?'yesterday':k<7?k+' days ago':k<14?'last week':k<60?Math.round(k/7)+' weeks ago':'a while ago';
}
const mem=()=>{const w=S.lane&&(S.sel[S.lane]||(S.sel[S.lane]={repo:null,files:{}}));return w};
const rmem=()=>{const w=mem();if(!w||!S.repo)return null;return w.files[S.repo]||(w.files[S.repo]={file:null,staged:false,tab:'diff',scroll:0})};
const cur=()=>S.board?.lanes.find(w=>w.id===S.lane);
const curRepo=()=>cur()?.repos.find(r=>r.repo===S.repo);
const shortOf=r=>r.short||r.repo;
/* A stable colour per repo, so a repo is the same shade everywhere it appears. Assigned
   explicitly: with six repos a hash collides (three of them all landed on the same slot),
   and a colour that is not distinct is worse than no colour. Unknown repos fall back to a
   hash over the slots nobody has claimed. */
const REPO_COLOUR={
  'web':'rp6',        // mauve
  'api':'rp3',          // indigo
  'worker':'rp5',          // teal
  'agent':'rp4',      // umber
  'tools':'rp2',   // olive
  'lib':'rp0',               // steel
  'docs':'rp1',                    // plum
};
function repoClass(repo){
  const s=String(repo||'');
  if(REPO_COLOUR[s])return REPO_COLOUR[s];
  const taken=new Set(Object.values(REPO_COLOUR));
  const free=['rp0','rp1','rp2','rp3','rp4','rp5','rp6','rp7'].filter(c=>!taken.has(c));
  const pool=free.length?free:['rp0','rp1','rp2','rp3','rp4','rp5','rp6','rp7'];
  let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))>>>0;
  return pool[h%pool.length];
}

/* ---------- toasts ---------- */
function toast(kind,text,opts={}){const box=$('#toasts');if(opts.replace&&opts.replace.isConnected)opts.replace.remove();const t=document.createElement('div');t.className='toast '+(kind==='ok'?'ok':kind==='err'?'err':'');t.textContent=text;
  if(kind==='err'){const r=document.createElement('div');r.className='tr';if(opts.fix){const b=document.createElement('button');b.textContent=opts.fix.label;b.onclick=()=>{t.remove();opts.fix.run()};r.appendChild(b)}const sp=document.createElement('span');sp.className='sp';r.appendChild(sp);const c=document.createElement('button');c.className='txt';c.textContent='Copy';c.onclick=()=>navigator.clipboard?.writeText(text);r.appendChild(c);const x=document.createElement('button');x.className='txt';x.textContent='✕';x.onclick=()=>t.remove();r.appendChild(x);t.appendChild(r)}
  box.appendChild(t);while(box.children.length>3)box.firstChild.remove();if(kind==='ok')setTimeout(()=>t.remove(),3000);return t}
/* ---------- board ---------- */
async function memAct(action,file,to,lane){try{const j=await api('/api/memory',{method:'POST',body:JSON.stringify({action,file,to,lane})});toast('ok',j.output||'done');S.mfile=null;await loadMemory()}catch(e){toast('err',e.message)}}
function scopeOptions(){return (S.mem?.scopes||[]).filter(s=>!['drafts'].includes(s.id)).map(s=>`<option value="${esc(s.id)}">${esc(s.label)} — ${esc(s.hint)}</option>`).join('')}
function memMoveDlg(file){const d=openDlg(`<h3>Move ${esc(file)}</h3><div class="hint">Scope is about lifetime: cross-repo stays true everywhere, a repo scope stays true for that repo after a ticket ships. The index lines are rewritten for you.</div><label>New scope</label><select id="sc" style="width:100%;padding:var(--s-2);border:1px solid var(--line);border-radius:var(--r);background:var(--surface);color:var(--text)">${scopeOptions()}</select>`,
  async d=>memAct('move',file,d.querySelector('#sc').value));d.querySelector('#dok').textContent='Move'}
function memFileDlg(file){const d=openDlg(`<h3>File ${esc(file)}</h3><div class="hint">Where does it belong? Ask yourself how long it stays true.</div><label>Scope</label><select id="sc" style="width:100%;padding:var(--s-2);border:1px solid var(--line);border-radius:var(--r);background:var(--surface);color:var(--text)">${scopeOptions()}${(S.board?.lanes||[]).filter(w=>w.status==='active').map(w=>`<option value="lane:${esc(w.id)}">lane ${esc(w.id)} — only while this work is live</option>`).join('')}</select>`,
  async d=>{const v=d.querySelector('#sc').value;return v.startsWith('lane:')?memAct('file',file,'lane',v.slice(3)):memAct('file',file,v)});d.querySelector('#dok').textContent='File it'}
function memRmDlg(file){openDlg(`<h3>Delete ${esc(file)}?</h3><div class="hint">The file and its index line are removed. This cannot be undone from here.</div>`,async()=>memAct('rm',file));$('#dok').textContent='Delete';$('#dok').className='danger'}
/* ---------- selection memory ---------- */
async function loadRepo(silent){const r=curRepo();const w=cur();if(!w){goHome();return}
  if(!r||!r.exists){S.data=null;renderRepo();return}
  try{const d=await api(`/api/repo?lane=${encodeURIComponent(S.lane)}&repo=${encodeURIComponent(S.repo)}`);const prev=S.data;
    const sig=dataSig(d);const same=silent&&sig===S.dataSig;S.dataSig=sig;S.data=d;
    if(!same)renderRepo();
    const rm=rmem();if(rm.file){const f=d.files.find(x=>x.file===rm.file&&(rm.staged?x.staged:x.unstaged));if(!f){rm.file=null;renderStage(true)}else{const key=JSON.stringify([S.lane,S.repo,rm.file,rm.staged,f.add,f.del,f.add_staged,f.del_staged,d.log[0]?.sha]);if(key!==S.diffKey||!prev)await loadDiff(key)}}
  }catch(e){$('#files').innerHTML=`<div class="empty">Could not read this worktree. <button class="txt" onclick="loadRepo(false)">Retry</button><br><span class="mono">${esc(e.message)}</span></div>`}}
function fname(f){const i=f.lastIndexOf('/');return i<0?esc(f):`<span class="dir">${esc(f.slice(0,i+1))}</span>${esc(f.slice(i+1))}`}
function frow(f,staged){const rm=rmem();const sel=rm.file===f.file&&rm.staged===staged;const letter=staged?(f.index||'M'):(f.untracked?'?':(f.work||'M'));const cls=letter==='A'?'ok':letter==='D'?'bad':letter==='R'?'acc':letter==='?'?'muted':'warn';const a=staged?f.add_staged:f.add,dl=staged?f.del_staged:f.del;
  return`<div class="frow ${sel?'sel':''}" data-file="${esc(f.file)}" data-staged="${staged?1:0}" tabindex="0" title="${esc(f.file)}"><input type="checkbox" ${staged?'checked':''} ${f.partial&&!staged?'data-ind=1':''} tabindex="-1"><span class="st ${cls}" title="${({M:'modified',A:'added',D:'deleted',R:'renamed','?':'untracked (new, not in git yet)',C:'copied',U:'conflict'})[letter]||letter}">${esc(letter)}</span><span class="nm">${f.old?`<span class="dir">${esc(f.old)} → </span>`:''}${fname(f.file)}</span>${f.secret?'<span class="secret">secret</span>':''}${a!=null?`<span class="cnt" title="${a} line(s) added, ${dl} removed"><b class="ok">+${a}</b> <b class="bad">−${dl}</b></span>`:''}</div>`}
function inline(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g,'$1<i>$2</i>').replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g,'$1<i>$2</i>').replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank">$1</a>').replace(/(^|\s)(https?:\/\/[^\s<]+)/g,'$1<a href="$2" target="_blank">$2</a>')}
function md(src){const out=[];const lines=src.replace(/\r/g,'').split('\n');let i=0;
  if(lines[0]==='---'){const j=lines.indexOf('---',1);if(j>0){const rows=[];for(const l of lines.slice(1,j)){const m=/^(\s*)(?:- )?([\w.-]+):\s*(.*)$/.exec(l);if(m)rows.push(`<tr><td>${'&nbsp;'.repeat(m[1].length)}${esc(m[2])}</td><td>${inline(m[3])}</td></tr>`)}out.push(`<table class="fm">${rows.join('')}</table>`);i=j+1}}
  let list=null,para=[],code=null;
  const flushP=()=>{if(para.length){out.push(`<p>${inline(para.join(' '))}</p>`);para=[]}};const flushL=()=>{if(list){out.push(`<${list.t}>${list.items.map(x=>`<li>${inline(x)}</li>`).join('')}</${list.t}>`);list=null}};
  for(;i<lines.length;i++){const l=lines[i];
    if(code!==null){if(/^```/.test(l)){out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);code=null}else code.push(l);continue}
    if(/^```/.test(l)){flushP();flushL();code=[];continue}
    const h=/^(#{1,6})\s+(.*)$/.exec(l);if(h){flushP();flushL();out.push(`<h${h[1].length+1}>${inline(h[2])}</h${h[1].length+1}>`);continue}
    if(/^\s*[-*+]\s+/.test(l)){flushP();if(!list||list.t!=='ul'){flushL();list={t:'ul',items:[]}}list.items.push(l.replace(/^\s*[-*+]\s+/,''));continue}
    if(/^\s*\d+[.)]\s+/.test(l)){flushP();if(!list||list.t!=='ol'){flushL();list={t:'ol',items:[]}}list.items.push(l.replace(/^\s*\d+[.)]\s+/,''));continue}
    if(/^\s*(---|\*\*\*)\s*$/.test(l)){flushP();flushL();out.push('<hr>');continue}
    if(/^>\s?/.test(l)){flushP();flushL();out.push(`<blockquote>${inline(l.replace(/^>\s?/,''))}</blockquote>`);continue}
    if(!l.trim()){flushP();flushL();continue}
    if(list&&/^\s{2,}/.test(l)){list.items[list.items.length-1]+=' '+l.trim();continue}
    para.push(l.trim())}
  flushP();flushL();if(code)out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);return `<div class="md">${out.join('')}</div>`}
/* ---------- pane ---------- */
const PT={diff:'Diff',history:'History',notes:'Notes',refs:'Refs',spec:'Spec',sessions:'Sessions'};
const PT_TIP={refs:'Outside folders or files attached to this lane for reference (per lane)',diff:'Changes in the selected file (per file)',history:'Recent commits on this branch (per repo)',notes:'Goal and resume note from the lane file (per lane)',spec:'The whole lane file: frontmatter, goal, note, log (per lane)',sessions:'Old Claude conversations for this repo (per repo)'};
const srcLine=(what,scope)=>`<div class="src">${what}<span class="scope">${scope}</span></div>`;
async function loadDiff(key){const rm=rmem();S.diffKey=key||S.diffKey;S.diffAll=false;try{S.diff=await api(`/api/diff?lane=${encodeURIComponent(S.lane)}&repo=${encodeURIComponent(S.repo)}&file=${encodeURIComponent(rm.file)}&staged=${rm.staged?1:0}`)}catch(e){S.diff={error:e.message}}if(feedOf()!=='history'&&rm.file){S.stageSig=null;renderStage(true)}}
function renderDiff(){const rm=rmem(),d=S.data,body=$('#pbody');const f=d.files.find(x=>x.file===rm.file&&(rm.staged?x.staged:x.unstaged));if(!f){body.innerHTML='<div class="center">No changes in this file.</div>';return}
  const a=rm.staged?f.add_staged:f.add,dl=rm.staged?f.del_staged:f.del;
  const head=`<div class="dh"><span class="fn" title="${esc(f.file)}">${esc(f.file)}</span><span class="muted">${rm.staged?'staged':f.untracked?'untracked':'unstaged'}</span>${a!=null?`<span><span class="ok">+${a}</span> <span class="bad">-${dl}</span></span>`:''}<span class="sp"></span><button class="txt" onclick="stage(['${esc(f.file)}'],${!rm.staged})">${rm.staged?'Unstage':'Stage'}</button>${rm.staged?'':`<button class="txt" onclick="discardDlg(['${esc(f.file)}'])">Discard</button>`}</div>`;
  const D=S.diff;if(!D){body.innerHTML=head+'<div class="center">Loading diff…</div>';return}
  if(D.error){body.innerHTML=head+`<div class="center">Could not read the diff.<br><span class="mono">${esc(D.error)}</span><br><br><button onclick="loadDiff()">Retry</button></div>`;return}
  if(D.secret){body.innerHTML=head+`<div class="center"><b>Secret file. The contents are never shown here.</b><br><br><span class="mono">Edit it in ${esc(D.mirror)}</span><br>You can still stage and commit it.</div>`;return}
  if(D.binary){body.innerHTML=head+`<div class="center">Binary or very large file — ${(D.size/1048576).toFixed(1)} MB. Not shown.</div>`;return}
  if(!D.diff.trim()){body.innerHTML=head+'<div class="center">No changes in this file.</div>';return}
  const R=diffBody(D.diff,false,rm.file);
  body.innerHTML=head+R.meta+`<div class="diff">${R.rows}</div>`+moreLine(D,'showAll()')}

/* ---------- syntax highlighting ----------
   Small on purpose: no library, works offline, and it hands back token ranges rather than
   HTML so the word-level <mark> from the diff can be sliced into the same output.
   One line at a time — a diff has no state across lines — so an unterminated block comment
   or template literal only colours its own line. */
const SYN_EXT={ts:'js',tsx:'js',mts:'js',cts:'js',js:'js',jsx:'js',mjs:'js',cjs:'js',
  java:'java',kt:'java',py:'py',rb:'py',go:'go',rs:'go',c:'java',h:'java',cpp:'java',cs:'java',
  css:'css',scss:'css',less:'css',json:'json',jsonc:'json',yml:'yaml',yaml:'yaml',toml:'yaml',
  sh:'sh',bash:'sh',zsh:'sh',sql:'sql',md:'md',markdown:'md',html:'xml',xml:'xml',svg:'xml',vue:'xml'};
const SYN_KW={
  js:'as async await break case catch class const continue debugger default delete do else enum export extends false finally for from function get if implements import in instanceof interface let new null of private protected public readonly return satisfies set static super switch this throw true try type typeof undefined var void while yield keyof infer declare namespace abstract',
  java:'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record sealed yield',
  py:'and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield match case self',
  go:'break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var nil true false let mut fn pub use impl struct enum match where async await move ref Self',
  css:'important from to and not or only media supports keyframes import charset font-face',
  sql:'select from where group by order having join left right inner outer on as insert into values update set delete create table alter drop index view union all distinct limit offset and or not null is in between like case when then else end',
  sh:'if then else elif fi for while do done case esac function return local export source alias unset in select time until',
  json:'true false null',yaml:'true false null yes no on off',md:'',xml:''};
const SYN_CACHE={};
function synRules(lang){
  if(SYN_CACHE[lang])return SYN_CACHE[lang];
  const kw=(SYN_KW[lang]||'').trim().split(/\s+/).filter(Boolean);
  const kwRe=kw.length?new RegExp('^(?:'+kw.join('|')+')$'):null;
  const parts=[];
  if(lang==='md'){
    parts.push(['com',/^(?:#{1,6}\s.*|\s*>.*)/],['str',/^`[^`]*`/],['kw',/^(?:\*\*[^*]+\*\*|_[^_]+_|\*[^*]+\*)/],
      ['fn',/^\[[^\]]*\]\([^)]*\)/],['pun',/^[-*+]\s/]);
  }else if(lang==='xml'){
    parts.push(['com',/^<!--[\s\S]*?(?:-->|$)/],['str',/^"(?:\\.|[^"\\])*"?|^'(?:\\.|[^'\\])*'?/],
      ['typ',/^<\/?[A-Za-z][\w:.-]*/],['att',/^[A-Za-z_:][\w:.-]*(?==)/],['pun',/^[<>/=]/]);
  }else{
    if(lang==='py'||lang==='yaml'||lang==='sh')parts.push(['com',/^#.*/]);
    if(lang==='sql')parts.push(['com',/^--.*/]);
    if(lang!=='py'&&lang!=='yaml'&&lang!=='sh'&&lang!=='sql')parts.push(['com',/^\/\/.*/],['com',/^\/\*[\s\S]*?(?:\*\/|$)/]);
    if(lang==='py')parts.push(['str',/^(?:[rbfu]{0,2})(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$))/]);
    parts.push(['str',/^`(?:\\.|[^`\\])*`?/],['str',/^"(?:\\.|[^"\\])*"?/],['str',/^'(?:\\.|[^'\\])*'?/]);
    if(lang==='sh')parts.push(['typ',/^\$\{?[A-Za-z_][\w]*\}?/]);
    if(lang==='css')parts.push(['typ',/^[.#][A-Za-z_-][\w-]*/],['att',/^--[\w-]+/],['num',/^-?\d*\.?\d+(?:px|rem|em|%|vh|vw|s|ms|fr|deg)?/]);
    if(lang==='yaml')parts.push(['att',/^[A-Za-z_][\w.-]*(?=\s*:)/]);
    if(lang==='json')parts.push(['att',/^"(?:\\.|[^"\\])*"(?=\s*:)/]);
    parts.push(['num',/^-?(?:0[xX][\da-fA-F]+|\d[\d_]*\.?\d*(?:[eE][+-]?\d+)?)\b/]);
    parts.push(['word',/^[A-Za-z_$@][\w$]*/]);
    parts.push(['pun',/^[{}()[\];,.:?!<>=+\-*/%&|^~]+/]);
  }
  const r={parts,kwRe};SYN_CACHE[lang]=r;return r;
}
/* -> [[start, end, class], ...] covering the whole line, plain runs included */
function synTokens(text,lang){
  const out=[];if(!lang||!SYN_KW.hasOwnProperty(lang)){out.push([0,text.length,'']);return out}
  const{parts,kwRe}=synRules(lang);
  let i=0,plain=0;
  const flush=(to)=>{if(to>plain)out.push([plain,to,''])};
  while(i<text.length){
    const rest=text.slice(i);
    let hit=null;
    for(const[cls,re]of parts){const m=re.exec(rest);if(m&&m[0].length){hit=[cls,m[0].length];break}}
    if(!hit){i++;continue}
    let[cls,len]=hit;
    if(cls==='word'){
      const w=text.slice(i,i+len);
      const next=text.slice(i+len).match(/^\s*\(/);
      cls=kwRe&&kwRe.test(w)?'kw':/^[A-Z]/.test(w)?'typ':next?'fn':/^[@$]/.test(w)?'att':'';
    }
    if(cls===''){i+=len;continue}
    flush(i);out.push([i,i+len,cls]);i+=len;plain=i;
  }
  flush(text.length);
  return out.sort((a,b)=>a[0]-b[0]);
}
/* escape + colour + slice in the word-level diff mark, all in one pass */
function code(text,lang,mark){
  text=String(text??'');
  const toks=synTokens(text,lang);
  const[ms,me]=mark&&mark[1]>mark[0]?mark:[-1,-1];
  let html='',open=false;
  for(const[a,b,cls]of toks){
    let p=a;
    while(p<b){
      const inMark=ms>=0&&p>=ms&&p<me;
      const stop=Math.min(b,inMark?me:(ms>p?ms:b));
      const piece=esc(text.slice(p,stop));
      if(inMark&&!open){html+='<mark>';open=true}
      if(!inMark&&open){html+='</mark>';open=false}
      html+=cls?`<span class="k-${cls}">${piece}</span>`:piece;
      p=stop;
    }
  }
  if(open)html+='</mark>';
  return html;
}
const langOf=f=>SYN_EXT[String(f||'').split('.').pop().toLowerCase()]||'';

function diffBody(text,fileHeaders,file){
  let o=0,n=0;let lang=langOf(file);const rows=[];const meta=[];const lines=String(text||'').split('\n');
  const pair=(a,b)=>{let i=0;while(i<a.length&&i<b.length&&a[i]===b[i])i++;let j=0;while(j<a.length-i&&j<b.length-i&&a[a.length-1-j]===b[b.length-1-j])j++;
    if(i+j===0||(a.length-i-j)>a.length*.8&&(b.length-i-j)>b.length*.8)return[[a,null],[b,null]];
    return[[a,[i,a.length-j]],[b,[i,b.length-j]]]};
  const g=(a,b,s,cls,txt)=>`<div class="dl ${cls}"><span class="g">${a}</span><span class="g">${b}</span><span class="s">${s}</span><span class="t">${txt}</span></div>`;
  for(let k=0;k<lines.length;k++){const l=lines[k];
    if(l.startsWith('@@')){const m=/@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(l);o=m?+m[1]:0;n=m?+m[2]:0;rows.push(g('','','','h',esc(l.replace(/^(@@[^@]*@@)\s?/,'$1  '))));continue}
    if(l.startsWith('diff ')){const m=/ b\/(.+)$/.exec(l);if(m)lang=langOf(m[1]);if(fileHeaders){rows.push(`<div class="dfile">${esc(m?m[1]:l)}</div>`)}continue}
    if(l.startsWith('index ')||l.startsWith('+++')||l.startsWith('---')){continue}
    if(l.startsWith('new file')||l.startsWith('deleted file')||l.startsWith('similarity')||l.startsWith('rename')||l.startsWith('old mode')||l.startsWith('new mode')){meta.push(l);continue}
    if(l.startsWith('-')){let dels=[];while(k<lines.length&&lines[k].startsWith('-')&&!lines[k].startsWith('---'))dels.push(lines[k++].slice(1));let adds=[];while(k<lines.length&&lines[k].startsWith('+')&&!lines[k].startsWith('+++'))adds.push(lines[k++].slice(1));k--;
      const paired=dels.length===adds.length;const marked=[];
      for(let x=0;x<dels.length;x++){const[[da,dm],[aa,am]]=paired?pair(dels[x],adds[x]):[[dels[x],null],[adds[x]??'',null]];
        rows.push(g(o++,'','-','d',code(da,lang,dm)));if(paired)marked[x]=code(aa,lang,am)}
      for(let x=0;x<adds.length;x++)rows.push(g('',n++,'+','a',paired?marked[x]:code(adds[x],lang,null)));continue}
    if(l.startsWith('+')){rows.push(g('',n++,'+','a',code(l.slice(1),lang,null)));continue}
    if(l.startsWith('\\')){rows.push(g('','','','m',esc(l)));continue}
    if(l==='')continue;
    rows.push(g(o++,n++,'','',code(l.slice(1),lang,null)))}
  return{rows:rows.join(''),meta:meta.length?`<div class="dfile">${esc(meta.join(' · '))}</div>`:''}}

function moreLine(D,fn){return D.truncated?`<div class="center sm">Showing ${D.total_lines>2000?2000:D.total_lines} of ${D.total_lines} lines. <button class="txt" onclick="${fn}">Show all</button></div>`:''}

// One commit, rendered with the same diff engine. Secret files are stripped server-side.
async function showCommit(sha,all){
  const body=$('#pbody');
  if(!all&&S.commitSha===sha&&body.dataset.sha===sha&&body.childElementCount)return;  // already showing it
  S.commitSha=sha;
  body.innerHTML='<div class="center">Loading commit…</div>';
  let C;try{C=await api(`/api/show?lane=${encodeURIComponent(S.lane)}&repo=${encodeURIComponent(S.repo)}&sha=${encodeURIComponent(sha)}${all?'&all=1':''}`)}
  catch(e){body.innerHTML=`<div class="center">Could not read that commit.<br><span class="mono">${esc(e.message)}</span></div>`;return}
  if(C.error){body.innerHTML=`<div class="center">${esc(C.error)}</div>`;return}
  const R=diffBody(C.diff,true);
  const hidden=C.hidden?`<div class="dfile">${C.hidden} secret file${C.hidden===1?'':'s'} in this commit — contents never shown.</div>`:'';
  body.innerHTML=`<div class="dh"><button class="txt" onclick="backToChanges()">‹ Back</button>
      <span class="fn" title="${esc(C.subject)}">${esc(C.subject)}</span>
      <span class="muted">${esc(C.short)}</span><span class="sp"></span>
      <button class="txt" onclick="navigator.clipboard?.writeText('${esc(C.sha)}');toast('ok','Copied ${esc(C.short)}')">Copy hash</button></div>
    <div class="cmeta">${esc(C.author)} · ${esc(C.date)} · ${C.files} file${C.files===1?'':'s'}</div>
    ${C.body?`<pre class="raw">${esc(C.body)}</pre>`:''}
    ${hidden}${R.meta}<div class="diff">${R.rows}</div>`+moreLine(C,`showCommit('${esc(sha)}',1)`);
  body.dataset.sha=sha;body.scrollTop=0;
}
async function showAll(){const rm=rmem();S.stageSig=null;S.diff=await api(`/api/diff?lane=${encodeURIComponent(S.lane)}&repo=${encodeURIComponent(S.repo)}&file=${encodeURIComponent(rm.file)}&staged=${rm.staged?1:0}&all=1`);renderDiff()}
async function pickFile(file,staged){const rm=rmem();rm.file=file;rm.staged=staged;rm.sha=null;
  const f=S.data.files.find(x=>x.file===file);S.diff=null;renderFiles();renderStage(true);
  await loadDiff(JSON.stringify([S.lane,S.repo,file,staged,f?.add,f?.del,f?.add_staged,f?.del_staged,S.data.log[0]?.sha]))}
/* ---------- actions ---------- */
function setBusy(b){S.busy=b;$('#prog').classList.toggle('on',!!b);if(S.data)renderActbar();updateCommitBtn()}
async function stage(files,on){try{await api('/api/stage',{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo,files,stage:on})});await refreshRepo()}catch(e){toast('err',e.message)}}
async function commit(){const msg=$('#msg').value;if(!msg.trim()||!S.data?.files.some(f=>f.staged))return;setBusy({id:'commit',label:'Committing…'});try{const j=await api('/api/commit',{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo,message:msg})});$('#msg').value='';toast('ok','Committed '+j.output);}catch(e){toast('err','Commit failed\n'+(e.output||e.message))}setBusy(null);await refreshRepo()}
async function act(a){const st=S.data?.state||{};const label=a==='push'?'Pushing…':'Pulling…';setBusy({id:a==='push'&&!st.upstream?'publish':a,label});const t=toast('prog',a==='push'?`Pushing to origin/${st.branch}…`:'Pulling…');
  try{const j=await api('/api/'+a,{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo})});toast('ok',(j.output||'').split('\n').slice(-2).join('\n')||a+' done',{replace:t})}
  catch(e){const out=e.output||e.message;t.remove();if(a==='push'&&/rejected|fetch first|non-fast-forward/i.test(out))toast('err','Push rejected — the remote has work you do not have.\n\n'+out,{fix:{label:`Pull ${st.behind||''}`.trim(),run:()=>act('pull')}});else if(a==='pull')toast('err','Pull needs a merge — fast-forward only. Sort it out in the terminal.\n\n'+out);else toast('err',out)}
  setBusy(null);await refreshRepo()}
async function primary(){const na=S.data?.nextAction;if(!na)return;switch(na.id){case'pull':return act('pull');case'push':case'publish':return act('push');case'commit':$('#msg').focus();return;case'stage_all':return stage(S.data.files.filter(f=>f.unstaged).map(f=>f.file),true);case'create_pr':{try{const j=await api('/api/pr',{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo})});window.open(j.url,'_blank')}catch(e){toast('err',e.message)}return}case'open_pr':if(na.url)window.open(na.url,'_blank');return;case'finish':return finishDlg();case'resume':return laneRun({action:'resume',id:S.lane})}}
async function laneRun(b){const labels={start:'Starting…',resume:'Resuming…',park:'Parking…',done:'Finishing…'};setBusy({id:b.action,label:labels[b.action]});const t=toast('prog',labels[b.action]);
  try{const j=await api('/api/lane',{method:'POST',body:JSON.stringify(b)});toast('ok',(j.output||'ok').split('\n').slice(-3).join('\n'),{replace:t});setBusy(null);S.board=await api('/api/board');if(b.action==='start'){S.boardSig=null;await openWs(b.id)}else if(b.action==='done'){S.lane=null;S.repo=null;renderHome();renderCrumb();goHome()}else{renderHome();renderCrumb();renderRepos();await loadRepo(false)}}
  catch(e){t.remove();toast('err',(b.action+' failed\n\n'+(e.output||e.message)));setBusy(null)}}
async function refReveal(path){try{await api('/api/ref',{method:'POST',body:JSON.stringify({lane:S.lane,action:'reveal',path})})}catch(e){toast('err',e.message)}}
async function refRm(name){openDlg(`<h3>Detach reference ${esc(name)}?</h3><div class="hint">Only the link under lanes/${esc(S.lane)}/refs/ and the registry line are removed. The folder or file itself is not touched.</div>`,async()=>{const j=await api('/api/ref',{method:'POST',body:JSON.stringify({lane:S.lane,action:'rm',name})});toast('ok',j.output);await refreshWs()});$('#dok').textContent='Detach'}
function refAddDlg(){const d=openDlg(`<h3>Attach a reference to ${esc(S.lane)}</h3><label>Path</label><input id="rp" placeholder="~/Desktop/some-folder  or  ~/Downloads/spec.pdf" autocomplete="off"><div class="hint">A folder or file outside the repos. It will appear as lanes/${esc(S.lane)}/refs/&lt;name&gt;.</div><label>Note</label><input id="rn" placeholder="why it matters for this work" autocomplete="off"><label style="display:flex;gap:var(--s-3);align-items:center;margin-top:var(--s-5)"><input type="checkbox" id="rw" style="width:14px;height:14px;margin:0"> Allow Claude to edit it (default is read-only)</label>`,
    async d=>{const j=await api('/api/ref',{method:'POST',body:JSON.stringify({lane:S.lane,action:'add',path:d.querySelector('#rp').value.trim(),note:d.querySelector('#rn').value.trim(),rw:d.querySelector('#rw').checked})});toast('ok',j.output.split('\n').filter(l=>l.startsWith('ref')).join('\n')||'attached');await refreshWs()},d=>d.querySelector('#rp').value.trim().length>0);d.querySelector('#dok').textContent='Attach';d.querySelector('#rp').focus()}
function discardDlg(list){
  if(!list.length)return;
  const d=S.data;const info=list.map(f=>d.files.find(x=>x.file===f)).filter(Boolean);
  const gone=info.filter(f=>f.untracked),edited=info.filter(f=>!f.untracked);
  openDlg(`<h3>Discard changes to ${list.length} file${list.length===1?'':'s'}?</h3>
    <div class="warnbox bad"><b>This cannot be undone.</b> Git keeps no copy of uncommitted work.
      <ul>${edited.length?`<li>${edited.length} file${edited.length===1?'':'s'} go back to the last commit</li>`:''}
         ${gone.length?`<li>${gone.length} new file${gone.length===1?'':'s'} are deleted from disk</li>`:''}</ul>
      <div class="mono sm">${info.slice(0,12).map(f=>esc(f.file)+(f.untracked?' (new)':'')).join('<br>')}
        ${info.length>12?`<br>…and ${info.length-12} more`:''}</div></div>`,
    async()=>{try{const j=await api('/api/discard',{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo,files:list})});
      toast('ok',j.output||'discarded');const rm=rmem();if(rm&&list.includes(rm.file))rm.file=null;await refreshRepo()}
      catch(e){toast('err',e.output||e.message)}});
  const ok=$('#dlg').querySelector('#dok');ok.textContent='Discard';ok.className='danger';
}
// Amending is fine until the commit is shared; the server refuses it after that and says why.
function amendDlg(){
  const d=S.data;if(!d)return;const last=d.log&&d.log[0];if(!last){toast('err','Nothing to amend yet.');return}
  const staged=d.files.filter(f=>f.staged).length;
  const typed=$('#msg').value.trim();
  openDlg(`<h3>Amend the last commit?</h3>
    <div class="warnbox"><b>Rewrites</b> “${esc(last.subject)}”.
      <ul><li>${staged?`${staged} staged file${staged===1?'':'s'} join that commit`:'No staged files — only the message changes'}</li>
          <li>Refused if it is already pushed</li></ul></div>
    <label>Message</label><textarea id="am" rows="3">${esc(typed||last.subject)}</textarea>
    <div class="hint">Leave as is to keep the message.</div>`,
    async dd=>{try{const j=await api('/api/amend',{method:'POST',body:JSON.stringify({lane:S.lane,repo:S.repo,message:dd.querySelector('#am').value})});
      toast('ok',j.output||'amended');$('#msg').value='';await refreshRepo()}
      catch(e){toast('err',e.output||e.message)}});
  $('#dlg').querySelector('#dok').textContent='Amend';
}
/* ---------- dialogs ---------- */
function openDlg(html,onOk,validate){const d=$('#dlg');S.dialog=true;d.innerHTML=html+`<div class="row"><button type="button" id="dcancel">Cancel</button><button type="button" class="pri" id="dok">OK</button></div>`;d.showModal();const ok=d.querySelector('#dok');d.querySelector('#dcancel').onclick=()=>d.close();
  const check=()=>{ok.disabled=validate?!validate(d):false};d.oninput=check;check();ok.onclick=async()=>{if(ok.disabled)return;d.close();try{await onOk(d)}catch(e){toast('err',e.message)}};d.onclose=()=>{S.dialog=false};d.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&e.target.tagName!=='TEXTAREA'){e.preventDefault();ok.click()}};return d}
function startDlg(){const repos=S.board?.repos||[];const d=openDlg(`<h3>Start a lane</h3><label>Id</label><input id="i" placeholder="ABC-123-short-name" autocomplete="off"><div class="hint" id="ih">Ticket key or a short slug.</div><label>Repos</label><input id="r" placeholder="api@develop web" autocomplete="off"><div class="hint">name[:branch][@base], space separated.</div><div class="chips">${repos.map(r=>`<span class="chip" data-r="${esc(r)}">${esc(r)}</span>`).join('')}</div>`,
    d=>laneRun({action:'start',id:d.querySelector('#i').value.trim(),repos:d.querySelector('#r').value.trim()}),d=>{const id=d.querySelector('#i').value.trim();const okId=/^[A-Za-z0-9._-]+$/.test(id);d.querySelector('#ih').textContent=id&&!okId?'Letters, numbers, dot, dash, underscore.':'Ticket key or a short slug.';return okId&&d.querySelector('#r').value.trim().length>0});
  d.querySelector('#dok').textContent='Start';d.querySelectorAll('.chip[data-r]').forEach(c=>c.onclick=()=>{const r=d.querySelector('#r');r.value=(r.value+' '+c.dataset.r).trim();d.oninput()});d.querySelector('#i').focus()}
function parkDlg(){const w=cur();if(!w)return;const dirty=w.repos.filter(r=>r.exists&&(r.unstaged||r.staged));const unp=w.repos.filter(r=>r.exists&&r.ahead);
  const warn=`<div class="warnbox"><b>What parking does</b><ul>${dirty.length?dirty.map(r=>`<li>${esc(shortOf(r))}: ${(r.unstaged||0)+(r.staged||0)} uncommitted file(s) will be committed as <span class="mono">wip: park ${esc(w.id)}</span> on <span class="mono">${esc(r.branch)}</span></li>`).join(''):'<li>No uncommitted work — nothing will be committed.</li>'}${unp.length?`<li>${esc(unp.map(shortOf).join(', '))}: unpushed commits stay local until you push.</li>`:''}<li>Worktrees stay on disk. The lane leaves the active list; Resume brings it back.</li></ul></div>`;
  const d=openDlg(`<h3>Park ${esc(w.id)}</h3>${warn}<label>Resume note</label><textarea id="n" rows="4" placeholder="where things stand, next step, blockers"></textarea><div class="hint">Required, at least 10 characters — you will read it in a week.</div>`,
    d=>laneRun({action:'park',id:w.id,note:d.querySelector('#n').value.trim()}),d=>d.querySelector('#n').value.trim().length>=10);d.querySelector('#dok').textContent='Park';d.querySelector('#n').focus()}
function finishDlg(){const w=cur();if(!w)return;const bad=w.repos.filter(r=>r.exists&&(r.unstaged||r.staged||r.ahead));const d=openDlg(`<h3>Finish ${esc(w.id)}?</h3><div class="warnbox ${bad.length?'bad':''}"><b>This removes the worktrees</b> under lanes/${esc(w.id)}/ and archives the lane file. Branches and commits stay in git. ${bad.length?'Refused right now:':'Nothing uncommitted or unpushed was found.'}</div><div class="mono" style="margin-top:var(--s-5)">${w.repos.map(r=>{const ok=!r.exists||!(r.unstaged||r.staged||r.ahead);return`<div class="${ok?'ok':'bad'}">${esc(shortOf(r))}  ${!r.exists?'no worktree':ok?'clean, pushed':`${(r.unstaged||0)+(r.staged||0)} uncommitted, ${r.ahead||0} unpushed`}</div>`}).join('')}</div>${bad.length?`<div class="hint bad">Commit and push ${esc(bad.map(shortOf).join(', '))} first.</div>`:''}`,
    ()=>laneRun({action:'done',id:w.id}),()=>bad.length===0);const ok=d.querySelector('#dok');ok.textContent='Finish';ok.className='danger'}
/* ---------- events ---------- */
/* ---------- screens ---------- */
function setView(v){S.view=v;rememberPlace();
  $('#home').classList.toggle('hidden',v!=='home');
  $('#work').classList.toggle('hidden',v!=='work');
  $('#memory').classList.toggle('hidden',v!=='memory');
  renderCrumb();
  if(v==='home')renderHome();else if(v==='memory')loadMemory();}
function goHome(){S.view='home';location.hash='';setView('home');$('#home').focus()}

/* how long since this worktree last moved */
/* Relative time, one unit, largest that still reads true: 5 min, 3 hours, 2 days, 3 weeks.
   A lane touched an hour ago and one touched this morning are different situations;
   "touched today" flattened both. Takes epoch seconds; returns '' for nothing. */
function ago(ts){
  if(!ts)return'';
  const s=Math.max(0,Math.floor(Date.now()/1000-ts));
  if(s<45)return'just now';
  if(s<3600)return `${Math.floor(s/60)} min ago`;
  if(s<86400){const n=Math.floor(s/3600);return `${n} hour${n===1?'':'s'} ago`}
  if(s<604800){const n=Math.floor(s/86400);return `${n} day${n===1?'':'s'} ago`}
  if(s<2629800){const n=Math.round(s/604800);return `${n} week${n===1?'':'s'} ago`}
  if(s<31557600){const n=Math.round(s/2629800);return `${n} month${n===1?'':'s'} ago`}
  const n=Math.round(s/31557600);return `${n} year${n===1?'':'s'} ago`;
}
/* the lane file records a date, not a timestamp: read it as local midnight */
function agoDate(d){
  if(!d)return'';
  const t=Date.parse(d+'T00:00:00');
  return isNaN(t)?'':ago(t/1000);
}
const exact=ts=>ts?new Date(ts*1000).toLocaleString(undefined,
  {weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'';
const sinceCommit=ago;
const laneTouched=w=>Math.max(0,...w.repos.map(r=>r.last||0));
const changed=r=>(r.unstaged||0)+(r.staged||0);
const laneChanged=w=>w.repos.reduce((n,r)=>n+changed(r),0);
const laneAhead=w=>w.repos.reduce((n,r)=>n+(r.ahead||0),0);
const laneDrift=w=>Math.max(0,...w.repos.map(r=>r.base_behind||0));

/* a repo's state as one chip: the loudest true thing about it */
function repoChip(r){
  const s=esc(shortOf(r));
  if(!r.exists)return`<span class="rchip" title="${s}: no worktree (parked)"><b class="${repoClass(r.repo)}">${s}</b>no worktree</span>`;
  const ch=changed(r);
  if(r.pr_failing)return`<span class="rchip beh" title="${s}: PR checks failing"><b class="${repoClass(r.repo)}">${s}</b>${ico('warn','sm')}checks failing</span>`;
  if(ch)return`<span class="rchip att" title="${s}: ${ch} uncommitted file(s)"><b class="${repoClass(r.repo)}">${s}</b>${ico('diff','sm')}${ch} changed</span>`;
  if(r.base_behind>2)return`<span class="rchip drift" title="${s}: ${r.base_behind} commit(s) behind ${esc(r.base_branch||'its base')}${r.base_from_pr?' \u2014 the branch its PR merges into':''}. Not a failure; it just gets harder to merge the longer it sits."><b class="${repoClass(r.repo)}">${s}</b>${ico('pull','sm')}${r.base_behind} behind ${esc(r.base_branch||'')}</span>`;
  if(r.ahead)return`<span class="rchip acc" title="${s}: ${r.ahead} commit(s) to push"><b class="${repoClass(r.repo)}">${s}</b>${ico('push','sm')}${r.ahead} to push</span>`;
  return`<span class="rchip" title="${s}: clean and in sync"><b class="${repoClass(r.repo)}">${s}</b>${ico('check','sm')}</span>`;
}

/* ---------- home: a reading of the situation, not a list ---------- */
function homeLede(b){
  const act=b.lanes.filter(w=>w.status==='active');
  const dirty=act.filter(w=>laneChanged(w)),ahead=act.filter(w=>laneAhead(w));
  const failing=act.filter(w=>w.repos.some(r=>r.pr_failing));
  const drift=act.map(w=>[w,laneDrift(w)]).filter(([,d])=>d>2).sort((a,b2)=>b2[1]-a[1])[0];
  const bits=[];
  if(dirty.length)bits.push(`${dirty.length===1?'One lane has':plural(dirty.length,'lane')+' have'} <span class="att">uncommitted work</span>`);
  else bits.push('Nothing is uncommitted');
  const ac=ahead.reduce((n,w)=>n+laneAhead(w),0);
  if(ac)bits.push(`${plural(ac,'commit')} <span class="cool">waiting to push</span>`);
  bits.push(failing.length?`<span class="att">${plural(failing.length,'PR')} failing</span>`:'nothing is failing');
  let s=bits.join(', ').replace(/,([^,]*)$/,', and$1')+'.';
  if(drift)s+=` The one that has drifted is <b>${esc(drift[0].id)}</b> — ${plural(drift[1],'commit')} behind its base branch.`;
  return s;
}
function todoList(b){
  const out=[],act=b.lanes.filter(w=>w.status==='active');
  const drift=act.map(w=>{const r=w.repos.filter(x=>x.exists).sort((a,c)=>(c.base_behind||0)-(a.base_behind||0))[0];return[w,r]})
                 .filter(([,r])=>r&&r.base_behind>2).sort((a,c)=>(c[1].base_behind)-(a[1].base_behind))[0];
  if(drift){const[w,r]=drift;const ch=changed(r);
    out.push({tone:'drift',ic:'pull',html:`<b>${esc(shortOf(r))}</b> in <b>${esc(w.id)}</b> is ${r.base_behind} behind <b>${esc(r.base_branch||'its base')}</b>${r.base_from_pr?', the branch its PR merges into':''}${ch?`, while ${plural(ch,'file')} sit open on it`:''}. The longer that sits, the worse the merge.`,
      act:'Open it',go:[w.id,r.repo]});}
  const dirty=act.filter(w=>laneChanged(w));
  if(dirty.length){const total=dirty.reduce((n,w)=>n+laneChanged(w),0);const w=dirty.sort((a,c)=>laneChanged(c)-laneChanged(a))[0];
    const r=w.repos.filter(x=>changed(x)).sort((a,c)=>changed(c)-changed(a))[0];
    out.push({tone:'',ic:'diff',html:`${plural(total,'file')} changed across ${plural(dirty.length,'lane')}, none committed yet.`,
      act:`Review ${esc(shortOf(r))} in ${esc(w.id)}`,go:[w.id,r.repo]});}
  const push=act.filter(w=>laneAhead(w)&&!laneChanged(w));
  if(push.length){const n=push.reduce((x,w)=>x+laneAhead(w),0);
    out.push({tone:'calm',ic:'push',html:`${plural(n,'branch')==='1 branchs'?'One branch is':plural(push.length,'lane')+' are'} ahead of origin with nothing uncommitted — safe to push.`,
      act:`Open ${esc(push[0].id)}`,go:[push[0].id,push[0].repos.find(r=>r.ahead)?.repo]});}
  if(!out.length)out.push({tone:'calm',ic:'check',html:'Everything is committed, pushed and passing. Nothing wants a decision.',act:'',go:null});
  return out;
}
/* The ticket field is hand-written and comes in three shapes: a bare Jira URL,
   "ABC-123  https://...", or empty. Pull out whichever of key and url are there;
   build the url from the key when only the key was written. */
// Where ticket keys link to comes from registry/config.yml, not from this file.
const trackerTemplate=()=>String(S.board?.tracker||'');
function ticketOf(w){
  const raw=String(w?.ticket||'').trim();
  const url=(raw.match(/https?:\/\/\S+/)||[])[0]||'';
  const key=(raw.match(/\b([A-Z][A-Z0-9]+-\d+)\b/)||[])[1]
        ||(url.match(/\/browse\/([A-Z][A-Z0-9]+-\d+)/)||[])[1]
        ||(/^([A-Z][A-Z0-9]+-\d+)-/.exec(w?.id||'')||[])[1]||'';
  if(!key&&!url)return null;
  const tpl=trackerTemplate();
  const built=key&&tpl?(tpl.includes('{key}')?tpl.replace(/\{key\}/g,key):tpl.replace(/\/?$/,'/')+key):'';
  return {key:key||'ticket', url:url||built};
}
function ticketChip(w,cls='tk'){
  const t=ticketOf(w);if(!t)return'';
  if(!t.url)return `<span class="${cls} ticket">${esc(t.key)}</span>`;
  return `<a class="${cls} ticket link" href="${esc(t.url)}" target="_blank" rel="noopener"
    title="Open ${esc(t.key)} in Jira" onclick="event.stopPropagation()">${esc(t.key)}${ico('ext','sm')}</a>`;
}
function homeCard(w,park){
  const ch=laneChanged(w),ahead=laneAhead(w),drift=laneDrift(w),fail=w.repos.some(r=>r.pr_failing);
  const now=!park&&(ch||fail||drift>2);
  const goal=firstSentence(w.goal,200),note=firstSentence(w.note,150);
  return`<div class="card ${now?'now':''} ${park?'park':''}" data-open="${esc(w.id)}" tabindex="0">
    <div class="ch"><span class="nm">${esc(w.id)}</span>${ticketChip(w)}
      <span class="tk state ${park?'parked':'active'}">${park?'parked':'active'}</span>
      <span class="when" title="${esc(park?'parked, lane file updated '+w.updated:exact(laneTouched(w))||w.updated)}">${esc(park?'parked '+agoDate(w.updated):ago(laneTouched(w))||agoDate(w.updated))}</span></div>
    ${goal?`<p class="goal">${esc(goal)}</p>`:''}
    ${note&&!park?`<div class="say"><b>Last note:</b> ${esc(note)}</div>`:''}
    <div class="repos">${w.repos.map(repoChip).join('')}
      <button class="txt" style="margin-left:auto;font-size:11px" data-about="${esc(w.id)}">about this work \u2192</button></div></div>`;
}
function renderHome(){
  const b=S.board,el=$('#home');
  if(!b||!b.lanes){el.innerHTML='<div class="hmain"><div class="none">Loading…</div></div>';return}
  const act=b.lanes.filter(w=>w.status==='active'),park=b.lanes.filter(w=>w.status!=='active');
  const wants=act.filter(w=>laneChanged(w)||laneDrift(w)>2||w.repos.some(r=>r.pr_failing));
  const rest=act.filter(w=>!wants.includes(w));
  const now=new Date();
  const date=now.toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'})+' · '+
             now.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
  const todos=todoList(b);
  const tally=[['branch','active',act.length],['branch','parked',park.length],
    ['diff','files changed',act.reduce((n,w)=>n+laneChanged(w),0)],
    ['push','commits to push',act.reduce((n,w)=>n+laneAhead(w),0)],
    ['pull','behind base',Math.max(0,...act.map(laneDrift))],
    ['warn','checks failing',act.reduce((n,w)=>n+w.repos.filter(r=>r.pr_failing).length,0)]];
  el.innerHTML=`<div class="hmain">
    <div class="date">${esc(date)}</div>
    <p class="lede">${homeLede(b)}</p>
    ${wants.length?`<div class="hgrp">Wants a decision</div>${wants.map(w=>homeCard(w,false)).join('')}`:''}
    ${rest.length?`<div class="hgrp">${wants.length?'The rest':'Active'}</div>${rest.map(w=>homeCard(w,false)).join('')}`:''}
    ${park.length?`<div class="hgrp">Parked · no worktree</div><div class="parked">${park.map(w=>`<span class="pk" data-open="${esc(w.id)}" tabindex="0">${ico('branch','sm')}${esc(w.id)}</span>`).join('')}</div>`:''}
    ${!b.lanes.length?'<div class="none">No lanes yet.</div>':''}
  </div>
  <div class="hside">
    <h5>What to do about it</h5>
    <div class="todo">${todos.map((t,i)=>`<div class="ti ${t.tone}">${ico(t.ic)}<span class="tx">${t.html}
      ${t.act?`<button class="do" data-todo="${i}">${t.act} →</button>`:''}</span></div>`).join('')}</div>
    <h5>Everything at a glance</h5>
    <div class="tally">${tally.map(([i,l,n])=>`<div class="tl">${ico(i,'sm')}${l}<span class="n">${n}</span></div>`).join('')}</div>
    <div style="margin-top:var(--s6)"><button class="pri" onclick="startDlg()" style="width:100%">${ico('plus','sm')}Start a lane</button></div>
  </div>`;
  el.querySelectorAll('[data-todo]').forEach(btn=>{const t=todos[+btn.dataset.todo];
    btn.onclick=()=>{if(t.go)openWs(t.go[0],t.go[1])}});
}

/* ---------- command bar ---------- */
function renderCrumb(){
  const w=cur();
  const c=$('#crumb');
  if(S.view==='home'){c.innerHTML=S.board?`<b>Home</b><span class="sep">·</span><span>${S.board.lanes.filter(x=>x.status==='active').length} active, ${S.board.lanes.filter(x=>x.status!=='active').length} parked</span>`:'<b>Home</b>';}
  else if(S.view==='memory'){c.innerHTML='<b>Memory</b><span class="sep">/</span><span>'+esc(S.mscope)+'</span>';}
  else if(w){const r=curRepo();c.innerHTML=`<b class="link" title="About this lane (i)">${esc(w.id)}</b>${r?`<span class="sep">/</span><b>${esc(shortOf(r))}</b>`:''}`;
    c.innerHTML+=ticketChip(w)+`<span class="tk state ${esc(w.status)}">${esc(w.status)}</span>`;}
  else c.innerHTML='';
  let chips='';
  if(S.view==='work'&&w){
    const ch=laneChanged(w),ah=laneAhead(w),fail=w.repos.filter(r=>r.pr_failing).length;
    if(ch)chips+=`<span class="chip att">${ico('diff','sm')} ${ch} changed</span>`;
    if(ah)chips+=`<span class="chip acc">${ico('push','sm')} ${ah}</span>`;
    if(fail)chips+=`<span class="chip bad">${ico('warn','sm')} ${fail} failing</span>`;
    const dr=w.repos.filter(r=>r.base_behind>2).sort((a,b)=>b.base_behind-a.base_behind)[0];
    if(dr)chips+=`<span class="chip drift" title="behind ${esc(dr.base_branch||'base')} \u2014 drift, not a failure">${ico('pull','sm')} ${dr.base_behind} behind ${esc(dr.base_branch||'')}</span>`;
    if(!ch&&!ah&&!fail)chips+=`<span class="chip ok">${ico('check','sm')} clean</span>`;
  }else if(S.board){
    const a=S.board.lanes.filter(x=>x.status==='active');
    const ch=a.reduce((n,x)=>n+laneChanged(x),0),ah=a.reduce((n,x)=>n+laneAhead(x),0);
    if(ch)chips+=`<span class="chip att">${ico('diff','sm')} ${ch} changed</span>`;
    if(ah)chips+=`<span class="chip">${ico('push','sm')} ${ah} to push</span>`;
  }
  $('#chips').innerHTML=chips;
  let act='';
  if(S.view==='work'&&w){
    if(w.status!=='active')act=`<button class="pri" onclick="laneRun({action:'resume',id:'${esc(w.id)}'})">${ico('play','sm')}Resume</button>`;
    else{const allDone=w.repos.every(r=>r.exists&&!r.unstaged&&!r.staged&&!r.ahead&&(r.pr_state==='MERGED'||r.pr_state==null));
      act=(allDone?`<button class="pri" onclick="finishDlg()">${ico('flag','sm')}Finish</button>`:'')
        +`<button onclick="parkDlg()" title="Write a resume note and put this lane down">${ico('park','sm')}Park</button>`;}
  }
  $('#cmdact').innerHTML=act;
  $('#aboutBtn').classList.toggle('hidden',!(S.view==='work'&&w));
  $('#memBtn').classList.toggle('on',S.view==='memory');
  $('#memBtn').title=S.view==='memory'?'Back to your work (m)':'Memory: preferences, facts, per-repo notes (m)';
}

/* ---------- work: repos, files, diff, one action bar ---------- */
function repoTab(r,i){
  const s=esc(shortOf(r)),ch=changed(r);
  let badge='';
  if(!r.exists)badge='<span class="faint">no worktree</span>';
  else if(r.pr_failing)badge=`<span class="bad stat">${ico('warn','sm')}failing</span>`;
  else if(ch)badge=`<span class="warn stat">${ico('diff','sm')}${ch}</span>`;
  else if(r.ahead)badge=`<span class="acc stat">${ico('push','sm')}${r.ahead}</span>`;
  else badge=`<span class="faint stat">${ico('check','sm')}</span>`;
  const drift=r.exists&&r.base_behind>2?`<span class="drift stat" title="${r.base_behind} commit(s) behind ${esc(r.base_branch||'its base')}${r.base_from_pr?' (the PR\u2019s base branch)':''} \u2014 drift, not a failure">${ico('pull','sm')}${r.base_behind} behind ${esc(r.base_branch||'')}</span>`:'';
  return`<button class="r ${r.repo===S.repo?'sel':''} ${r.exists?'':'nowt'}" data-repo="${esc(r.repo)}"
    title="${esc(r.repo)} · branch ${esc(r.branch)}${r.base?' from '+esc(r.base):''} · press ${i+1}"><span class="repotag ${repoClass(r.repo)}">${s}</span>${badge}${drift}</button>`;
}
function renderRepos(){
  const w=cur();if(!w){$('#repos').innerHTML='';return}
  const d=S.data,st=d?.state,pr=d?.pr;
  let meta='';
  if(st)meta=`<span class="meta">${ico('branch','sm')} ${esc(st.branch)} ${st.upstream?`<span class="faint">→ ${esc(st.upstream)}</span>`:'<span class="warn">not published</span>'}
    ${pr&&!pr.error?`<a class="chip ${pr.state==='MERGED'?'ok':pr.checks?.failing?'bad':pr.isDraft?'':'ok'}" href="${esc(pr.url)}" target="_blank">${ico('pr','sm')} #${pr.number} ${pr.state==='MERGED'?'merged':pr.checks?.failing?pr.checks.failing+' failing':pr.checks?.pending?'running':pr.isDraft?'draft':'passing'}</a>`:''}</span>`;
  $('#repos').innerHTML=w.repos.map(repoTab).join('')+meta;
}
function renderRepo(){
  const w=cur(),r=curRepo();if(!w){goHome();return}
  renderRepos();renderCrumb();
  if(!r||!r.exists){
    $('#files').innerHTML=`<div class="empty">${w.status!=='active'?'Worktrees are removed while parked.':'No worktree for this repo yet.'}</div>`;
    $('#commit').classList.add('hidden');$('#stagehead').innerHTML='';
    $('#pbody').innerHTML=`<div class="center">No worktree here.<br><br><button class="pri" onclick="openSheet()">About this lane</button></div>`;
    renderActbar();return}
  $('#commit').classList.remove('hidden');
  renderFiles();renderStage();renderActbar();updateCommitBtn();
}
/* the action bar says what happens next in words, then offers it */
function renderActbar(){
  const d=S.data,w=cur();
  if(!d){$('#actwhy').innerHTML='';$('#actbtns').innerHTML=w&&w.status!=='active'?`<button class="pri" onclick="laneRun({action:'resume',id:'${esc(w.id)}'})">Resume this lane</button>`:'';return}
  const st=d.state,na=d.nextAction||{id:'none',label:'Nothing to do'};
  const staged=d.files.filter(f=>f.staged).length,unst=d.files.filter(f=>f.unstaged).length;
  const r=curRepo();
  let why='';
  if(staged&&unst)why=`<b>${plural(staged,'file')}</b> staged, ${unst} still open — commit what is ready, or press <b>a</b> to stage the rest.`;
  else if(staged)why=`<b>${plural(staged,'file')}</b> staged and nothing left open.`;
  else if(unst)why=`<b>${plural(unst,'file')}</b> changed, none staged yet — tick the ones that belong together, or press <b>a</b> for all.`;
  else if(st.ahead)why=`Working tree clean. <b>${plural(st.ahead,'commit')}</b> waiting to go to ${esc(st.upstream||'origin')}.`;
  else if(st.behind)why=`Working tree clean. <b>${plural(st.behind,'commit')}</b> to pull.`;
  else if(r&&r.base_behind>2)why=`Clean and in sync, but <b>${r.base_behind} behind ${esc(r.base_branch||'master')}</b> — worth pulling that in before you carry on.`;
  else why='Clean, in sync, nothing to do here.';
  $('#actwhy').innerHTML=why;
  const busy=S.busy;const primLabel=busy&&busy.id===na.id?busy.label:na.label;
  const btns=[];
  if(unst)btns.push(`<button onclick="stage(${esc(JSON.stringify(d.files.filter(f=>f.unstaged).map(f=>f.file)))},true)" ${busy?'disabled':''}>${ico('diff','sm')}Stage all</button>`);
  if(staged)btns.push(`<button class="txt" onclick="stage(${esc(JSON.stringify(d.files.filter(f=>f.staged).map(f=>f.file)))},false)">Unstage all</button>`);
  if(st.upstream&&st.behind&&na.id!=='pull')btns.push(`<button onclick="act('pull')" ${busy?'disabled':''}>${ico('pull','sm')}Pull ${st.behind}</button>`);
  if(staged)btns.push(`<button class="pri" id="commitBtn" onclick="commit()">${ico('commit','sm')}Commit</button>`);
  else{const pi={pull:'pull',push:'push',publish:'push',commit:'commit',stage_all:'diff',create_pr:'pr',open_pr:'pr',finish:'flag',resume:'play'}[na.id];
    btns.push(`<button class="pri ${na.tone||''}" id="primary" onclick="primary()" ${na.id==='none'||busy?'disabled':''}>${pi?ico(pi,'sm'):''}${esc(primLabel)}</button>`);}
  $('#actbtns').innerHTML=btns.join('');
  updateCommitBtn();
}

function backToChanges(){const rm=rmem();if(rm){rm.sha=null}setFeed('changes')}
/* ---------- the lane sheet ----------
   Goal, resume note, findings, references and past conversations: everything that is about
   the work rather than the code. Reachable any time with i, from the lane name in the
   bar, and from a Home card - visible on demand, never in the way of a diff. */
function openSheet(id){if(id&&id!==S.lane){S.lane=id}
  if(!cur())return;$('#sheetwrap').classList.remove('hidden');renderSheet();$('#sheetClose').focus()}
function closeSheet(){$('#sheetwrap').classList.add('hidden')}
function toggleSheet(){$('#sheetwrap').classList.contains('hidden')?openSheet():closeSheet()}
function setSTab(k){S.stab=k;renderSheet()}
const SHEET_TABS=[['work','Goal & notes'],['refs','References'],['sess','Conversations'],['raw','The file']];
function parseSessions(txt){
  return (txt||'').trim().split('\n').slice(1).map(l=>{
    const m=/^\s*(\S+ \S+)\s+(\S{8,})\s+(\d+) turns\s+(.*)$/.exec(l);
    return m?{when:m[1],id:m[2],turns:+m[3],first:m[4]}:null}).filter(Boolean);
}
async function renderSheet(){
  const w=cur();if(!w)return;
  if(!S.stab)S.stab='work';
  $('#sheetname').innerHTML=`<span class="nm">${ico('branch')} ${esc(w.id)}</span>
    ${ticketChip(w)}<span class="tk state ${esc(w.status)}">${esc(w.status)}</span>`;
  const refs=w.refs||[];
  const sessions=parseSessions(S.data?.sessions);
  const counts={refs:refs.length,sess:sessions.length};
  $('#stabs').innerHTML=SHEET_TABS.map(([k,label])=>`<span class="st ${S.stab===k?'sel':''}" data-stab="${k}">${esc(label)}
    ${counts[k]?`<span class="n">${counts[k]}</span>`:''}</span>`).join('');
  const body=$('#sheetbody');
  if(S.stab==='raw'){
    body.innerHTML='<pre class="raw muted">Reading the lane file\u2026</pre>';
    try{const j=await api(`/api/spec?lane=${encodeURIComponent(w.id)}`);
      body.innerHTML=`<div class="wrapw"><div class="kv"><b>file</b><span>registry/lanes/${esc(w.id)}.md</span></div>`
        +(j.spec?md(j.spec):'<p>No file.</p>')+'</div>';
    }catch(e){body.innerHTML=`<pre class="raw bad">${esc(e.message)}</pre>`}
    return;
  }
  if(S.stab==='refs'){
    body.innerHTML=`<div class="wrapw">
      <p class="big">Outside code and docs attached to this work.</p>
      <div class="kv"><b>they appear at</b><span>lanes/${esc(w.id)}/refs/&lt;name&gt;</span>
        <b>read-only unless</b><span>attached with --rw</span></div>
      ${refs.length?`<div class="reflist">${refs.map(r=>`<div class="ref">${ico('folder','sm')}
          <span>${esc(r.name||r.path.split('/').pop())}</span>
          <span class="faint" style="overflow:hidden;text-overflow:ellipsis">${esc(r.note||r.path)}</span>
          <span class="mode">${esc(r.mode||'read')}</span></div>`).join('')}</div>`
        :'<p>Nothing attached to this lane.</p>'}
      <p style="margin-top:16px"><button onclick="refAddDlg()">+ Attach a reference</button></p></div>`;
    return;
  }
  if(S.stab==='sess'){
    const byTurns=[...sessions].sort((a,b)=>b.turns-a.turns);
    const deep=byTurns.filter(s=>s.turns>=10),quick=byTurns.filter(s=>s.turns<10);
    const row=s=>`<div class="sessrow" data-resume="${esc(s.id)}" title="Click to copy: claude --resume ${esc(s.id)}">
      <span class="faint">${esc(s.when.slice(5,10))}</span><span class="tx">${esc(s.first)}</span>
      <span class="turns">${s.turns} turns</span><span class="cp">copy resume \u2318</span></div>`;
    body.innerHTML=`<div class="wrapw">
      <p class="big">Past Claude conversations recorded for ${esc(S.repo||'this repo')}.</p>
      <div class="kv"><b>scope</b><span>this repo, every lane, all time</span>
        <b>to continue one</b><span>claude --resume &lt;id&gt;</span></div>
      ${deep.length?`<div class="sgrp">Substantial <span class="q">\u00b7 ten turns or more</span></div><div class="sess">${deep.map(row).join('')}</div>`:''}
      ${quick.length?`<div class="sgrp">Quick lookups</div><div class="sess">${quick.map(row).join('')}</div>`:''}
      ${!sessions.length?'<p>None recorded for this repo.</p>':''}</div>`;
    return;
  }
  const fnd=(w.findings||'').replace(/^\(things learned[\s\S]*?\)$/m,'').trim();
  body.innerHTML=`<div class="wrapw">
    <div class="sgrp">Goal</div>${w.goal?md(w.goal):'<p>No goal written yet.</p>'}
    <div class="sgrp">Resume note</div>${w.note?`<div class="note">${md(w.note)}</div>`:'<p>No resume note.</p>'}
    ${fnd?`<div class="sgrp">Findings <span class="q">\u00b7 kept only while this work is live</span></div>${md(fnd)}`:''}
    ${(w.links||[]).length?`<div class="sgrp">Links <span class="q">\u00b7 hand-written in the lane file</span></div>
      <div class="reflist">${w.links.map(l=>`<div class="ref">${ico('folder','sm')}<span>${esc(l.label)}</span>
        <a class="faint" href="${esc(l.url)}" target="_blank" rel="noreferrer" style="overflow:hidden;text-overflow:ellipsis">${esc(l.url)}</a></div>`).join('')}</div>`:''}
    <div class="sgrp">Repos</div>
    <div class="reflist">${w.repos.map(r=>`<div class="ref">${ico('repo','sm')}<span>${esc(r.repo)}</span>
      <span class="faint">${esc(r.branch)}${r.base?' from '+esc(r.base):''}</span>
      <span class="mode">${r.exists?(changed(r)?plural(changed(r),'file')+' open':'clean'):'no worktree'}</span></div>`).join('')}</div>
  </div>`;
}
/* ---------- the left column is a source picker; the pane is one stage ----------
   Changes feeds it file diffs, History feeds it commit diffs. History answers the
   question at two widths: this repo's branch, or every repo of the lane
   interleaved — a lane spans four repos, so "what happened on this work"
   is four logs, not one. */
const feedOf=()=>{const m=mem();return m?(m.feed||'changes'):'changes'};
const hscopeOf=()=>{const m=mem();return m?(m.hscope||'repo'):'repo'};
/* 'work' = origin/<base>..HEAD, the commits this lane added. 'all' = the branch tail,
   which on a branch behind its base is mostly commits that arrived with the base. */
const hrangeOf=()=>{const m=mem();if(!m)return'work';
  if(hscopeOf()==='lane')return'work';          // the lane view is this work, by definition
  return m.hrange||'work'};
function setHRange(r){const m=mem();if(!m)return;m.hrange=r;
  if(hscopeOf()==='lane')loadWsLog();renderFeedBar();renderFiles();renderStage(true)}
function setFeed(f){const m=mem();if(!m)return;m.feed=f;
  if(f==='history'&&hscopeOf()==='lane')loadWsLog();
  renderFeedBar();renderFiles();renderStage(true)}
function setHScope(sc){const m=mem();if(!m)return;m.hscope=sc;
  if(sc==='lane')loadWsLog();renderFeedBar();renderFiles();renderStage(true)}
function renderFeedBar(){
  const feed=feedOf(),hs=hscopeOf(),d=S.data;
  document.querySelectorAll('#feeds .feed').forEach(b=>b.classList.toggle('sel',b.dataset.feed===feed));
  $('#feedcount').textContent=d?(d.files.length||''):'';
  $('#scopebar').classList.toggle('hidden',feed!=='history');
  document.querySelectorAll('#scopebar .sc').forEach(b=>b.classList.toggle('sel',b.dataset.scope===hs));
  $('#ffilter').placeholder=feed==='history'
    ? (hs==='lane'?'Filter commits across all repos':'Filter commits on this branch')
    : (d&&d.files.length?`Filter ${d.files.length} files`:'Filter files');
}
async function loadWsLog(){
  const whole=hrangeOf()==='all';const key=`${S.lane}|${whole?'all':'work'}`;
  if(S.wslogKey===key&&S.wslog)return;
  try{const j=await api(`/api/lanelog?lane=${encodeURIComponent(S.lane)}${whole?'&all=1':''}`);
    S.wslog=j.log;S.wslogKey=key;
    if(feedOf()==='history')renderFiles()}catch(e){toast('err',e.message)}}
function crow(c,withRepo){
  const rm=rmem();const sel=rm&&rm.sha===c.sha;
  const refs=(c.refs||'').split(',').map(x=>x.trim().replace(/^HEAD -> /,'')).filter(x=>x&&x!=='HEAD').slice(0,1);
  return`<div class="crow ${sel?'sel':''}" data-sha="${esc(c.sha)}" data-repo="${esc(c.repo||'')}" tabindex="0" title="${esc(c.date||'')}">
    <span class="sha">${esc(c.sha)}</span><span class="sub">${esc(c.subject)}</span>
    <span class="meta">${withRepo&&c.short?`<span class="rp ${repoClass(c.repo)}">${esc(c.short)}</span>`:''}${esc(c.author.split(' ')[0])} · ${esc(c.when)}
      ${refs.length?`<span class="ref">${esc(refs[0])}</span>`:''}</span></div>`;
}
function folderOf(f){const i=f.lastIndexOf('/');return i<0?'(root)':f.slice(0,i)}
function renderFiles(){
  const d=S.data;if(!d)return;
  renderFeedBar();
  const flt=S.filter.toLowerCase();const el=$('#files');const scroll=el.scrollTop;
  if(feedOf()==='history'){
    const lane=hscopeOf()==='lane',work=hrangeOf()==='work';
    const src=lane?(S.wslog||null):(work?d.worklog:d.log);
    if(!src){el.innerHTML='<div class="empty">Reading every repo\u2026</div>';return}
    const rows=src.filter(c=>`${c.subject} ${c.sha} ${c.author} ${c.short||''}`.toLowerCase().includes(flt));
    const base=esc(curRepo()?.base_branch||'the base branch');
    const foot=lane?'' :work
      ?`<button class="histmore txt" onclick="setHRange('all')">Show earlier commits that came from ${base} \u2193</button>`
      :`<button class="histmore txt" onclick="setHRange('work')">\u2191 Hide ${base}'s commits \u2014 show only this work</button>`;
    el.innerHTML=(rows.map(c=>crow(c,lane)).join('')
      ||`<div class="empty">${S.filter?'No commits match that filter.'
        :work?`Nothing committed yet beyond <b>${base}</b>.`
             :'No commits on this branch.'}</div>`)+foot;
    $('#fcount').textContent=S.filter?`${rows.length} of ${src.length}`
      :`${plural(src.length,'commit')}${work?'':' (all)'}`;
    el.scrollTop=scroll;return;
  }
  const list=d.files.filter(f=>f.file.toLowerCase().includes(flt));
  const focus=document.activeElement?.closest?.('.frow')?.dataset;
  const groups=new Map();
  for(const f of list){const k=folderOf(f.file);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(f)}
  let html='';
  for(const[dir,fs]of groups){
    const all=fs.map(f=>f.file),anyUn=fs.some(f=>f.unstaged);
    html+=`<div class="fold">${ico('folder','sm')}<span>${esc(dir)}</span><span class="c">${fs.length}</span>
      ${anyUn?`<button class="txt" onclick="event.stopPropagation();stage(${esc(JSON.stringify(all))},true)">stage</button>`:''}</div>`;
    html+=fs.map(f=>frow(f,!!f.staged)).join('');
  }
  el.innerHTML=html||'<div class="empty">Working tree clean.</div>';
  const tot=d.files.length;
  $('#fcount').textContent=S.filter?`${list.length} of ${tot}`:(tot?plural(tot,'file'):'');
  document.querySelectorAll('.frow input[data-ind]').forEach(i=>i.indeterminate=true);
  el.scrollTop=scroll;
  if(focus)$(`.frow[data-file="${CSS.escape(focus.file)}"]`)?.focus();
}
/* the stage: one reading surface, whatever the picker points at */
function stageSig(){
  const d=S.data,rm=rmem();if(!d||!rm)return 'none';
  return feedOf()==='history'
    ? ['c',rm.sha||'',S.diffAll?1:0].join('|')
    : ['f',rm.file||'',rm.staged?1:0,S.diffKey,S.diff?(S.diff.diff||'').length:-1].join('|');
}
function renderStage(force){
  const d=S.data,rm=rmem();const head=$('#stagehead');
  const sig=stageSig();
  if(!force&&sig===S.stageSig&&$('#pbody').childElementCount)return;   // nothing changed: keep the scroll
  S.stageSig=sig;
  if(!d){head.innerHTML='';$('#pbody').innerHTML='<div class="center">No worktree for this repo.</div>';return}
  if(feedOf()==='history'){
    if(rm&&rm.sha){showCommit(rm.sha);return}
    head.innerHTML=`${ico('commit','sm')}<span class="dim">Pick a commit to read it</span>`;
    $('#pbody').innerHTML='<div class="center">Commits on '+esc(hscopeOf()==='lane'?'every repo of this lane':d.state.branch)+'.<br><br>Click one to see exactly what it changed.</div>';
    return;
  }
  if(!rm||!rm.file){
    head.innerHTML=`${ico('diff','sm')}<span class="dim">${d.files.length?'Pick a file to read its diff':'Working tree clean'}</span>`;
    $('#pbody').innerHTML=`<div class="center">${d.files.length?'Select a file on the left.':`<b>Working tree clean.</b><br><br>Last commit ${esc(d.log[0]?.when||'')}: \u201c${esc(d.log[0]?.subject||'')}\u201d`}</div>`;
    return;
  }
  const f=d.files.find(x=>x.file===rm.file);
  head.innerHTML=`${ico('diff','sm')}<b title="${esc(rm.file)}">${esc(rm.file)}</b>
    <span class="faint">${rm.staged?'staged':f&&f.untracked?'untracked':'unstaged'}</span><span class="sp"></span>
    ${f&&f.add!=null?`<span class="ok">+${rm.staged?f.add_staged:f.add}</span> <span class="bad">\u2212${rm.staged?f.del_staged:f.del}</span>`:''}`;
  renderDiff();
}
function updateCommitBtn(){
  const d=S.data;const n=d?d.files.filter(f=>f.staged).length:0;const msg=$('#msg').value;
  const first=msg.split('\n')[0];const mc=$('#mcount');mc.textContent=first.length;mc.className=first.length>72?'warn':'';
  const b=$('#commitBtn');if(!b)return;
  const busy=S.busy?.id==='commit';
  b.textContent=busy?'Committing…':`Commit ${plural(n,'file')}`;
  b.disabled=busy||!n||!msg.trim();
  b.title=!n?'Tick a file first':!msg.trim()?'Write a message first':'';
}

/* ---------- selection ---------- */
async function openWs(id,repo){
  S.lane=id;const w=cur();if(!w)return goHome();
  const m=mem();
  S.repo=repo&&w.repos.find(r=>r.repo===repo)?repo:
    (m.repo&&w.repos.find(r=>r.repo===m.repo)?m.repo:
     (w.repos.filter(r=>r.exists).sort((a,b)=>(changed(b)?1:0)-(changed(a)?1:0)||(b.ahead||0)-(a.ahead||0))[0]||w.repos[0])?.repo||null);
  m.repo=S.repo;rememberPlace();
  location.hash=`lane=${encodeURIComponent(id)}${S.repo?`&repo=${encodeURIComponent(S.repo)}`:''}`;
  setView('work');await loadRepo(false);
}
async function pickRepo(repo){S.repo=repo;mem().repo=repo;rememberPlace();
  location.hash=`lane=${encodeURIComponent(S.lane)}&repo=${encodeURIComponent(repo)}`;renderRepos();await loadRepo(false)}

/* ---------- board polling ---------- */
/* Signatures: what the screen draws, with the per-poll timestamps left out. */
function boardSig(b){
  return JSON.stringify((b?.lanes||[]).map(w=>[w.id,w.status,w.updated,w.goal,w.note,(w.refs||[]).length,
    w.repos.map(r=>[r.repo,r.branch,r.exists,r.dirty,r.staged,r.unstaged,r.ahead,r.behind,
      r.pr_state,r.pr_failing,r.base_behind,r.last])]));
}
function dataSig(d){
  if(!d)return 'none';
  return JSON.stringify([d.state,d.files,(d.log||[]).map(c=>c.sha),d.pr?[d.pr.number,d.pr.state,d.pr.checks]:null,
    d.nextAction,(d.sessions||'').length]);
}
async function loadBoard(){
  if(S.busy||S.dialog)return;
  try{const b=await api('/api/board');
    if(S.startedAt&&b.serverStartedAt!==S.startedAt){toast('err','Server restarted — reload the page');return}
    S.startedAt=b.serverStartedAt;S.fails=0;
    const sig=boardSig(b);const changedNow=sig!==S.boardSig;S.boardSig=sig;S.board=b;
    $('#clock').textContent=b.generated;$('#clock').classList.remove('warn');
    if(changedNow){renderCrumb();
      if(S.view==='home')renderHome();
      else if(S.view==='work'){if(S.lane&&S.repo&&cur()?.repos.find(r=>r.repo===S.repo)?.exists)await loadRepo(true);else renderRepo()}}
  }catch(e){if(e.message==='restarted')return;S.fails++;const c=$('#clock');c.classList.add('warn');
    c.textContent=S.fails>=3?'offline — server stopped?':'stale · retrying'}}
async function refreshRepo(){S.board=await api('/api/board');renderCrumb();await loadRepo(true)}
async function refreshWs(){S.board=await api('/api/board');renderCrumb();renderRepos();await loadRepo(true)}

/* ---------- memory screen ---------- */
async function loadMemory(){try{S.mem=await api('/api/memory');renderMemory()}catch(e){$('#mbody').innerHTML=`<div class="center">${esc(e.message)}</div>`}}
function mscope(){return S.mem?.scopes.find(s=>s.id===S.mscope)||S.mem?.scopes[0]}
function renderMemory(){
  const m=S.mem;if(!m)return;
  const s=mscope();if(s)S.mscope=s.id;
  $('#mscopes').innerHTML=m.scopes.map(sc=>{
    const repoish=!['cross','pref','drafts'].includes(sc.id);
    return`<div class="scope ${sc.id===S.mscope?'sel':''}" data-scope="${esc(sc.id)}">${ico(repoish?'repo':'dot')}${esc((sc.label||sc.id).replace(/^repo:/,''))}<span class="c">${sc.files.length}</span></div>`}).join('');
  const files=s?.files||[];
  if(!files.find(f=>f.file===S.mfile))S.mfile=files[0]?.file||null;
  $('#mfiles').innerHTML=files.map(f=>`<div class="mrow ${f.file===S.mfile?'sel':''}" data-mfile="${esc(f.file)}">
    <div class="t">${esc(f.name||f.file.replace(/\.md$/,''))}</div><div class="d">${esc(f.description||'')}</div></div>`).join('')
    ||'<div class="empty">Nothing in this scope yet.</div>';
  renderMemBody();
  renderCrumb();
}
async function renderMemBody(){
  const s=mscope();const f=s?.files.find(x=>x.file===S.mfile);const b=$('#mbody');
  if(!f){b.innerHTML='<div class="center">Pick a memory on the left.</div>';return}
  b.innerHTML='<div class="center">Reading…</div>';
  try{const j=await api(`/api/memfile?scope=${encodeURIComponent(S.mscope)}&file=${encodeURIComponent(S.mfile)}`);
    b.innerHTML=`<div class="src">${esc(j.path)}<span class="scope">${esc(S.mscope)}</span></div>`+md(j.content||'_Empty._')
      +`<div class="md" style="padding-top:0"><button class="txt" onclick="memMoveDlg('${esc(S.mfile)}')">Move scope</button>
        &nbsp;&nbsp;<button class="txt" onclick="memRmDlg('${esc(S.mfile)}')">Delete</button></div>`;
  }catch(e){b.innerHTML=`<div class="center">${esc(e.message)}</div>`}
}

/* ---------- palette ---------- */
function palRows(q){
  const b=S.board;if(!b)return[];
  const norm=s=>String(s||'').toLowerCase();
  const terms=norm(q).split(/\s+/).filter(Boolean);
  const hit=(hay)=>terms.every(t=>norm(hay).includes(t));
  const rows=[];
  const w=cur();
  if(w)for(const r of w.repos){
    const hay=`${r.repo} ${shortOf(r)} ${w.id}`;
    if(hit(hay))rows.push({kind:'repo',group:'In this lane',lane:w.id,repo:r.repo,
      name:r.repo,sub:r.exists?(changed(r)?plural(changed(r),'file')+' changed':r.ahead?plural(r.ahead,'commit')+' to push':'in sync'):'no worktree',r});
  }
  for(const x of b.lanes){
    if(x.id===S.lane)continue;
    if(hit(`${x.id} ${x.ticket||''} ${x.repos.map(r=>r.repo+' '+shortOf(r)).join(' ')}`))
      rows.push({kind:'lane',group:x.status==='active'?'Lanes':'Parked',lane:x.id,repo:null,
        name:x.id,sub:`${plural(x.repos.length,'repo')}${x.status==='active'?'':' · parked'}`,w:x});
  }
  if(hit('memory'))rows.push({kind:'mem',group:'Elsewhere',name:'Memory',sub:'preferences, facts, per-repo notes'});
  if(hit('home board overview'))rows.push({kind:'home',group:'Elsewhere',name:'Home',sub:'every lane, and what wants a decision'});
  return rows;
}
function markMatch(name,q){
  const terms=q.toLowerCase().split(/\s+/).filter(Boolean);let out=esc(name);
  for(const t of terms){const i=out.toLowerCase().indexOf(t);if(i<0)continue;
    out=out.slice(0,i)+'<em>'+out.slice(i,i+t.length)+'</em>'+out.slice(i+t.length)}
  return out;
}
function renderPal(){
  const rows=S.pal.rows,q=S.pal.q;
  if(S.pal.i>=rows.length)S.pal.i=Math.max(0,rows.length-1);
  let html='',group=null;
  rows.forEach((r,i)=>{
    if(r.group!==group){group=r.group;html+=`<div class="pgrp">${esc(group)}</div>`}
    const icon=r.kind==='repo'?'repo':r.kind==='lane'?'branch':r.kind==='mem'?'book':'home';
    let state='';
    if(r.kind==='repo'&&r.r){const ch=changed(r.r);
      if(ch)state=`<span class="warn stat">${ico('diff','sm')}${ch}</span>`;
      else if(r.r.ahead)state=`<span class="acc stat">${ico('push','sm')}${r.r.ahead}</span>`;}
    if(r.kind==='lane'&&r.w){const ch=laneChanged(r.w);if(ch)state=`<span class="warn stat">${ico('diff','sm')}${ch}</span>`}
    html+=`<div class="prow ${i===S.pal.i?'on':''}" data-i="${i}">${ico(icon)}
      <span class="nm">${markMatch(r.name,q)}</span><span class="sub">${esc(r.sub||'')}</span>
      <span class="c">${state}${i===S.pal.i?'<span class="acc">open ⏎</span>':''}</span></div>`;
  });
  $('#pallist').innerHTML=html||'<div class="empty">Nothing matches.</div>';
  $('#palcount').textContent=rows.length?`${rows.length} match${rows.length===1?'':'es'}`:'';
  $('#pallist').querySelector('.prow.on')?.scrollIntoView({block:'nearest'});
}
function openPal(){S.pal={open:true,q:'',rows:palRows(''),i:0};$('#palwrap').classList.remove('hidden');
  $('#palq').value='';renderPal();$('#palq').focus()}
function closePal(){S.pal.open=false;$('#palwrap').classList.add('hidden')}
function palGo(){
  const r=S.pal.rows[S.pal.i];if(!r)return;closePal();
  if(r.kind==='home')return goHome();
  if(r.kind==='mem'){setView('memory');return}
  if(r.kind==='repo')return pickRepo(r.repo);
  return openWs(r.lane);
}

/* ---------- wiring ---------- */
document.addEventListener('click',e=>{
  const ab=e.target.closest('[data-about]');if(ab){e.stopPropagation();S.lane=ab.dataset.about;openSheet(ab.dataset.about);return}
  const open=e.target.closest('[data-open]');if(open){openWs(open.dataset.open);return}
  const r=e.target.closest('#repos .r');if(r){pickRepo(r.dataset.repo);return}
  const fd=e.target.closest('#feeds .feed');if(fd){setFeed(fd.dataset.feed);return}
  const sc2=e.target.closest('#scopebar .sc');if(sc2){setHScope(sc2.dataset.scope);return}
  const cr=e.target.closest('.crow');if(cr){const rm=rmem();if(rm){rm.sha=cr.dataset.sha;rm.file=null}
    if(cr.dataset.repo&&cr.dataset.repo!==S.repo){pickRepo(cr.dataset.repo).then(()=>{const r2=rmem();if(r2)r2.sha=cr.dataset.sha;renderFiles();renderStage(true)})}
    else{renderFiles();renderStage(true)}return}
  const sn=e.target.closest('#crumb b.link');if(sn){openSheet();return}
  const stb=e.target.closest('#stabs .st');if(stb){setSTab(stb.dataset.stab);return}
  const rs=e.target.closest('[data-resume]');if(rs){const cmd='claude --resume '+rs.dataset.resume;
    navigator.clipboard?.writeText(cmd);toast('ok','Copied: '+cmd.slice(0,34)+'\u2026');return}
  if(e.target.id==='sheetwrap'){closeSheet();return}
  const f=e.target.closest('.frow');if(f){
    if(e.target.type==='checkbox'){stage([f.dataset.file],e.target.checked);return}
    pickFile(f.dataset.file,f.dataset.staged==='1');return}
  const sc=e.target.closest('#mscopes .scope');if(sc){S.mscope=sc.dataset.scope;S.mfile=null;renderMemory();return}
  const mf=e.target.closest('[data-mfile]');if(mf){S.mfile=mf.dataset.mfile;renderMemory();return}
  const pr=e.target.closest('#pal .prow');if(pr){S.pal.i=+pr.dataset.i;palGo();return}
  if(e.target.id==='palwrap'){closePal();return}
  const h=e.target.closest('.hrow');if(h){showCommit(h.dataset.sha);return}
});
$('#homeBtn').onclick=goHome;
$('#sheetClose').onclick=closeSheet;
$('#aboutBtn').onclick=()=>{if(cur())openSheet()};
$('#memBtn').onclick=()=>setView(S.view==='memory'?(S.lane?'work':'home'):'memory');
$('#switchBtn').onclick=openPal;
$('#theme').onclick=()=>{const cur=(()=>{try{return localStorage.getItem('lane-theme')||'system'}catch{return'system'}})();
  applyTheme(THEMES[(THEMES.indexOf(cur)+1)%3])};
$('#ffilter').addEventListener('input',e=>{S.filter=e.target.value;renderFiles()});
$('#ffilter').addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();
  if(e.target.value){e.target.value='';S.filter='';renderFiles()}else e.target.blur()}});
$('#msg').addEventListener('input',updateCommitBtn);
$('#palq').addEventListener('input',e=>{S.pal.q=e.target.value;S.pal.rows=palRows(e.target.value);S.pal.i=0;renderPal()});
$('#palq').addEventListener('keydown',e=>{
  if(e.key==='ArrowDown'||(e.key==='n'&&e.ctrlKey)){e.preventDefault();S.pal.i=Math.min(S.pal.rows.length-1,S.pal.i+1);renderPal()}
  else if(e.key==='ArrowUp'||(e.key==='p'&&e.ctrlKey)){e.preventDefault();S.pal.i=Math.max(0,S.pal.i-1);renderPal()}
  else if(e.key==='Enter'){e.preventDefault();palGo()}
  else if(e.key==='Escape'){e.preventDefault();closePal()}});

document.addEventListener('keydown',e=>{
  const inField=/INPUT|TEXTAREA/.test(e.target.tagName);const meta=e.metaKey||e.ctrlKey;
  if(meta&&(e.key==='k'||e.key==='K')){e.preventDefault();return S.pal.open?closePal():openPal()}
  if(S.pal.open)return;
  if(meta&&e.key==='Enter'){e.preventDefault();return commit()}
  if(meta&&(e.key==='p'||e.key==='P')){e.preventDefault();return primary()}
  if(e.key==='Escape'){if(S.dialog)return;
    if(!$('#sheetwrap').classList.contains('hidden')){closeSheet();return}
    if(S.filter){S.filter='';$('#ffilter').value='';renderFiles();return}
    const t=$('#toasts').lastChild;if(t){t.remove();return}
    if(S.view!=='home')goHome();return}
  if(inField||S.dialog)return;
  if(e.key==='i'){if(cur())toggleSheet();return}
  if(e.key==='?')return helpDlg();
  if(e.key==='r')return S.view==='memory'?loadMemory():loadBoard();
  if(e.key==='m')return setView(S.view==='memory'?'home':'memory');
  if(e.key==='g')return goHome();
  if(e.key==='c'){$('#msg')?.focus();return}
  if(e.key==='/'){e.preventDefault();$('#ffilter')?.focus();return}
  if(S.view!=='work')return;
  const w=cur();
  if(/^[1-9]$/.test(e.key)){const r=w?.repos[+e.key-1];if(r)pickRepo(r.repo);return}
  if(e.key==='['||e.key===']'){const i=w.repos.findIndex(r=>r.repo===S.repo);
    const n=(i+(e.key===']'?1:w.repos.length-1))%w.repos.length;pickRepo(w.repos[n].repo);return}
  if(e.key==='a'&&S.data){e.preventDefault();stage(S.data.files.filter(f=>f.unstaged).map(f=>f.file),true);return}
  if(e.key==='h')return setFeed(feedOf()==='history'?'changes':'history');
  if(e.key==='d')return setFeed('changes');
  if(e.key===' '){const f=document.activeElement?.closest?.('.frow');
    if(f){e.preventDefault();stage([f.dataset.file],f.dataset.staged!=='1')}return}
  if(e.key==='j'||e.key==='k'||e.key==='ArrowDown'||e.key==='ArrowUp'){
    const down=e.key==='j'||e.key==='ArrowDown';const list=[...document.querySelectorAll('.frow')];
    if(!list.length)return;e.preventDefault();
    const i=list.indexOf(document.activeElement);
    const nx=list[Math.min(list.length-1,Math.max(0,(i<0?(down?0:list.length-1):i+(down?1:-1))))];
    nx.focus();nx.scrollIntoView({block:'nearest'})}
});

function helpDlg(){openDlg(`<h3>Keys</h3><div class="hint">Navigation is the palette; everything else is one letter.</div>
<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 18px;font-size:12px">
<kbd>⌘K</kbd><span>jump to a lane or repo</span>
<kbd>esc</kbd><span>back out to Home</span>
<kbd>g</kbd><span>Home</span><kbd>m</kbd><span>Memory</span>
<kbd>1</kbd>–<kbd>9</kbd><span>repo</span><kbd>[</kbd> <kbd>]</kbd><span>previous / next repo</span>
<kbd>j</kbd> <kbd>k</kbd><span>move in the file list</span><kbd>space</kbd><span>stage / unstage</span>
<kbd>a</kbd><span>stage everything</span><kbd>/</kbd><span>filter files</span>
<kbd>c</kbd><span>commit message</span><kbd>⌘⏎</kbd><span>commit</span><kbd>⌘P</kbd><span>the primary action</span>
<kbd>d h n e s v</kbd><span>Diff · History · Notes · rEfs · Spec · Sessions</span>
<kbd>r</kbd><span>refresh</span><kbd>?</kbd><span>this list</span></div>`,()=>{});
  $('#dok').textContent='Close'}

/* ---------- boot: always on Home ---------- */
(async function boot(){
  applyTheme((()=>{try{return localStorage.getItem('lane-theme')||'system'}catch{return'system'}})());
  $('#home').classList.remove('hidden');
  await loadBoard();
  const h=new URLSearchParams(location.hash.replace(/^#/,''));
  const wantWs=h.get('lane')||LSg('lane-last','');
  const wantRepo=h.get('repo')||LSg('lane-lastrepo','');
  const wantView=location.hash?'work':LSg('lane-view','home');
  const known=wantWs&&S.board?.lanes.some(w=>w.id===wantWs);
  if(wantView==='work'&&known)await openWs(wantWs,wantRepo||null);
  else if(wantView==='memory')setView('memory');
  else{setView('home');renderHome()}
  setInterval(loadBoard,4000);
})();
