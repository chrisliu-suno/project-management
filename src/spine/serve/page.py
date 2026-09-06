"""The dashboard's single self-contained HTML document."""

from __future__ import annotations

PAGE_TITLE = "spine"

_STYLE = """
:root {
  --ground:#FAFBFC; --surface:#FFF; --sunk:#F1F4F6; --ink:#141C22;
  --muted:#5A6873; --faint:#8695A1; --rule:#DCE3E8; --accent:#0F7A85;
  --ok:#1B7F45; --warn:#96690F; --problem:#AE2A32;
  --ok-soft:#E4F2EA; --warn-soft:#F7EEDC; --problem-soft:#F8E7E8;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#0D1317; --surface:#141C21; --sunk:#1A2429; --ink:#E4EBEF;
  --muted:#9CADB8; --faint:#6E818D; --rule:#243138; --accent:#45BAC4;
  --ok:#5DC186; --warn:#D6A63F; --problem:#E8747C;
  --ok-soft:#12291D; --warn-soft:#2C2413; --problem-soft:#2E1719;
}}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.6;margin:0;padding:2.5rem 1.5rem 5rem}
.wrap{max-width:64rem;margin:0 auto;display:flex;flex-direction:column;gap:2.5rem}
h1{font-family:var(--mono);font-size:1.75rem;font-weight:600;letter-spacing:-.02em;margin:0}
h2{font-family:var(--mono);font-size:1.15rem;font-weight:600;margin:0}
.eyebrow{font-family:var(--mono);font-size:.75rem;text-transform:uppercase;
  letter-spacing:.11em;color:var(--faint);margin:0 0 .5rem}
.sub{color:var(--muted);margin:.35rem 0 0}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:2px;
  border-left:3px solid var(--edge,var(--rule));padding:1.25rem 1.4rem;
  display:flex;flex-direction:column;gap:1rem}
.card.ok{--edge:var(--ok)} .card.warn{--edge:var(--warn)} .card.problem{--edge:var(--problem)}
.cardhead{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}
.slug{font-family:var(--mono);font-size:.8rem;color:var(--faint)}
.metrics{display:flex;flex-wrap:wrap;gap:1.5rem}
.metric{display:flex;flex-direction:column}
.metric .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:1.2rem;font-weight:600}
.metric .k{font-size:.75rem;color:var(--faint);text-transform:uppercase;letter-spacing:.07em}
.tallies{display:flex;flex-wrap:wrap;gap:.4rem}
.tally{font-family:var(--mono);font-size:.72rem;background:var(--sunk);
  color:var(--muted);padding:.15em .5em;border-radius:2px;white-space:nowrap}
.findings{display:flex;flex-direction:column;gap:.5rem;margin:0;padding:0;list-style:none}
.finding{display:flex;gap:.7rem;align-items:flex-start;font-size:.875rem}
.sev{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;
  padding:.2em .5em;border-radius:2px;white-space:nowrap;flex-shrink:0;margin-top:.1rem}
.sev.ok{background:var(--ok-soft);color:var(--ok)}
.sev.warn{background:var(--warn-soft);color:var(--warn)}
.sev.problem{background:var(--problem-soft);color:var(--problem)}
.finding .detail{color:var(--muted);font-size:.82rem}
.ids{font-family:var(--mono);font-size:.72rem;color:var(--faint);
  margin-top:.2rem;word-break:break-all}
form{display:flex;gap:.6rem;flex-wrap:wrap;align-items:stretch}
input,select,button{font-family:inherit;font-size:.9rem;padding:.55rem .7rem;
  border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink)}
input{flex:1;min-width:16rem}
button{background:var(--accent);color:#fff;border-color:var(--accent);cursor:pointer;font-weight:600}
button:hover{opacity:.9}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.picklist{display:flex;flex-direction:column;gap:.3rem;margin:0;padding:0;list-style:none}
.pickrow{display:flex;gap:.7rem;align-items:baseline;font-size:.85rem;
  padding:.35rem .5rem;background:var(--sunk);border-radius:2px}
.pickrow.cut{opacity:.55;background:transparent;border:1px dashed var(--rule)}
.pickrow .doc{font-family:var(--mono);font-size:.78rem;flex:1;word-break:break-all}
.pickrow .grp{font-family:var(--mono);font-size:.68rem;color:var(--faint);white-space:nowrap}
.pickrow .ln{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:.72rem;color:var(--faint);white-space:nowrap}
.reason{font-family:var(--mono);font-size:.78rem;color:var(--muted)}
.err{color:var(--problem);font-size:.875rem}
footer{border-top:1px solid var(--rule);padding-top:1.2rem;font-size:.8rem;color:var(--faint)}
code{font-family:var(--mono);font-size:.85em;background:var(--sunk);padding:.1em .35em;border-radius:2px}
"""

_SCRIPT = """
const el=(t,c,x)=>{const n=document.createElement(t);if(c)n.className=c;
  if(x!==undefined)n.textContent=x;return n};

function metric(k,v){const m=el('div','metric');m.append(el('span','v',String(v)),
  el('span','k',k));return m}

function findingRow(f){
  const li=el('li','finding');
  li.append(el('span','sev '+f.severity,f.severity));
  const body=el('div');
  body.append(el('div',null,f.headline),el('div','detail',f.detail));
  if(f.doc_ids&&f.doc_ids.length)body.append(el('div','ids',f.doc_ids.join('  ')));
  li.append(body);return li;
}

function projectCard(p){
  const card=el('section','card '+p.worst_severity);
  const head=el('div','cardhead');
  const left=el('div');
  left.append(el('h2',null,p.name),el('div','slug',p.slug+'  ·  '+p.docs_dir));
  head.append(left);
  card.append(head);
  const m=el('div','metrics');
  m.append(metric('docs',p.doc_count),metric('entries',p.entry_count),
    metric('links',p.link_count),metric('lines',p.total_lines));
  card.append(m);
  const t=el('div','tallies');
  Object.entries(p.read_when_counts).forEach(([k,v])=>t.append(el('span','tally',k+' '+v)));
  Object.entries(p.kind_counts).forEach(([k,v])=>t.append(el('span','tally',k+' '+v)));
  card.append(t);
  if(p.findings.length){const ul=el('ul','findings');
    p.findings.forEach(f=>ul.append(findingRow(f)));card.append(ul)}
  return card;
}

function pickRow(d,isCut){
  const li=el('li','pickrow'+(isCut?' cut':''));
  li.append(el('span','doc',d.doc_id),el('span','grp',d.read_when),
    el('span','ln',d.line_count+'L'));
  return li;
}

async function loadProjects(){
  const host=document.getElementById('projects');
  host.textContent='';
  try{
    const r=await fetch('/api/projects');const j=await r.json();
    if(j.error){host.append(el('p','err',j.error));return}
    if(!j.projects.length){host.append(el('p','err',
      'No projects registered. Run: spine registry add <slug> --docs-dir <path>'));return}
    const sel=document.getElementById('project');sel.textContent='';
    j.projects.forEach(p=>{
      host.append(projectCard(p));
      const o=document.createElement('option');o.value=p.slug;o.textContent=p.slug;sel.append(o);
    });
  }catch(e){host.append(el('p','err','Could not reach the server: '+e.message))}
}

async function runPick(ev){
  ev.preventDefault();
  const out=document.getElementById('pickout');out.textContent='';
  const slug=document.getElementById('project').value;
  const task=document.getElementById('task').value;
  try{
    const r=await fetch('/api/pick?project='+encodeURIComponent(slug)+
      '&task='+encodeURIComponent(task));
    const j=await r.json();
    if(j.error){out.append(el('p','err',j.error));return}
    out.append(el('p','reason',j.chosen.length+' selected · '+j.total_lines+
      ' lines · '+j.reason));
    const ul=el('ul','picklist');
    j.chosen.forEach(d=>ul.append(pickRow(d,false)));
    j.dropped.forEach(d=>ul.append(pickRow(d,true)));
    out.append(ul);
  }catch(e){out.append(el('p','err','Selection failed: '+e.message))}
}

document.getElementById('pickform').addEventListener('submit',runPick);
loadProjects();
"""


def render_page() -> str:
    """The whole dashboard: no external stylesheet, script, font, or image."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{PAGE_TITLE}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
  <header>
    <p class="eyebrow">project context</p>
    <h1>spine</h1>
    <p class="sub">Corpus health per project, and what would be loaded for a task.</p>
  </header>

  <div id="projects"></div>

  <section class="card">
    <div>
      <p class="eyebrow">what would spine load</p>
      <h2>Selection preview</h2>
    </div>
    <form id="pickform">
      <select id="project" aria-label="Project"></select>
      <input id="task" placeholder="describe a task, e.g. close the trashed-clip leak on the feed"
             aria-label="Task">
      <button type="submit">Preview</button>
    </form>
    <div id="pickout"></div>
  </section>

  <footer>
    Read-only. Refresh to re-read the corpora.
    Populate with <code>spine classify run</code> then <code>spine index build</code>.
  </footer>
</div>
<script>{_SCRIPT}</script>
</body>
</html>
"""
