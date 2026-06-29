// ---------- Bar chart data ----------
const realmobileData = [
  {name:'Xiaomi-GUI-0-30B-A3B', val:72.0, ours:true},
  {name:'Gemini 3.1 Pro', val:85.0},
  {name:'Seed 2.0 Pro', val:80.0},
  {name:'Seed 1.8', val:65.0},
  {name:'Claude Opus 4.7', val:60.0},
  {name:'Gemini 3.1 Flash', val:58.0},
  {name:'MAI-UI-8B', val:33.0},
  {name:'GUI-Owl-1.5-32B-Thk', val:31.0},
  {name:'UI-Venus-1.5-30B', val:21.0},
  {name:'Step-GUI-8B', val:15.0},
];

const androidworldData = [
  {name:'Xiaomi-GUI-0-30B-A3B', val:78.9, ours:true},
  {name:'UI-Venus-1.5-30B-A3B', val:77.6},
  {name:'UI-Venus-1.5-8B', val:73.7},
  {name:'UI-TARS-2', val:73.3},
  {name:'GUI-Owl-1.5-8B-Thk', val:71.6},
  {name:'Seed 1.8', val:70.7},
  {name:'MAI-UI-8B', val:70.7},
  {name:'GUI-Owl-1.5-32B-Inst', val:69.8},
  {name:'Step-GUI-8B', val:67.7},
  {name:'UI-TARS-1.5', val:64.2},
];

function renderBars(containerId, data){
  const el = document.getElementById(containerId);
  if(!el) return;
  const max = Math.max(...data.map(d=>d.val));
  // sort descending so the chart reads as a ranking
  data.slice().sort((a,b)=>b.val-a.val).forEach(d=>{
    const row = document.createElement('div');
    row.className = 'bar-row' + (d.ours ? ' ours' : '');
    row.innerHTML = `
      <div class="bar-label" title="${d.name}">${d.name}</div>
      <div class="bar-track"><div class="bar-fill${d.ours?' is-ours':''}" data-w="${(d.val/max*100).toFixed(1)}"></div></div>
      <div class="bar-val">${d.val.toFixed(1)}</div>`;
    el.appendChild(row);
  });
}
renderBars('bars-realmobile', realmobileData);
renderBars('bars-androidworld', androidworldData);

// ---------- Animate bars when visible ----------
const barObserver = new IntersectionObserver((entries)=>{
  entries.forEach(e=>{
    if(e.isIntersecting){
      e.target.querySelectorAll('.bar-fill').forEach(f=>{
        f.style.width = f.dataset.w + '%';
      });
      barObserver.unobserve(e.target);
    }
  });
},{threshold:0.2});
document.querySelectorAll('.bars').forEach(b=>barObserver.observe(b));

// ---------- Reveal on scroll ----------
const revealEls = document.querySelectorAll('.card, .pillar, .figure, .domain-card, .method-block, .cite-box, .contrib-grid, .train-flow, .grounding-stats, .stat');
revealEls.forEach(el=>el.classList.add('reveal'));
const revObserver = new IntersectionObserver((entries)=>{
  entries.forEach(e=>{
    if(e.isIntersecting){ e.target.classList.add('in'); revObserver.unobserve(e.target); }
  });
},{threshold:0.12});
revealEls.forEach(el=>revObserver.observe(el));

// ---------- Copy BibTeX ----------
function copyCite(btn){
  const text = document.getElementById('bibtex').innerText;
  navigator.clipboard.writeText(text).then(()=>{
    const old = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(()=>btn.textContent = old, 1600);
  });
}

// ---------- PDF link placeholder handling ----------
document.querySelectorAll('[data-pdf]').forEach(a=>{
  a.addEventListener('click', (e)=>{
    // If no PDF has been wired up yet, guide the user.
    if(a.getAttribute('href') === '#'){
      e.preventDefault();
      alert('Add the report PDF as assets/Xiaomi-GUI-0.pdf and point this button to it.');
    }
  });
});

// ---------- Close mobile menu on link click ----------
document.querySelectorAll('#navlinks a').forEach(a=>{
  a.addEventListener('click', ()=>document.getElementById('navlinks').classList.remove('open'));
});

// ---------- Demo carousel ----------
(function(){
  const track = document.getElementById('demoTrack');
  if(!track) return;
  const slides = track.children.length;
  const dots = Array.from(document.querySelectorAll('.demo-dot'));
  let idx = 0;

  function go(n){
    idx = (n + slides) % slides;
    track.style.transform = `translateX(-${idx*100}%)`;
    dots.forEach((d,i)=>d.classList.toggle('active', i===idx));
    // pause every video when switching away
    track.querySelectorAll('video').forEach(v=>v.pause());
  }

  document.getElementById('demoPrev').addEventListener('click', ()=>go(idx-1));
  document.getElementById('demoNext').addEventListener('click', ()=>go(idx+1));
  dots.forEach(d=>d.addEventListener('click', ()=>go(parseInt(d.dataset.idx,10))));

  // keyboard arrows, only while the demos section is in view
  let inView = false;
  const section = document.getElementById('demos');
  if(section){
    new IntersectionObserver((entries)=>{
      inView = entries[0].isIntersecting;
    },{threshold:0.4}).observe(section);
  }
  document.addEventListener('keydown', (e)=>{
    if(!inView) return;
    const t = e.target.tagName;
    if(t==='INPUT'||t==='TEXTAREA') return;
    if(e.key==='ArrowLeft') go(idx-1);
    else if(e.key==='ArrowRight') go(idx+1);
  });
})();

// ---------- Case study lightbox ----------
(function(){
  const box = document.getElementById('lightbox');
  if(!box) return;
  const img = document.getElementById('lightboxImg');
  const close = document.getElementById('lightboxClose');

  function open(src){
    img.src = src;
    box.classList.add('open');
    box.setAttribute('aria-hidden','false');
    document.body.style.overflow = 'hidden';
  }
  function hide(){
    box.classList.remove('open');
    box.setAttribute('aria-hidden','true');
    document.body.style.overflow = '';
    img.src = '';
  }

  document.querySelectorAll('.case-img[data-zoom]').forEach(btn=>{
    btn.addEventListener('click', ()=>open(btn.dataset.zoom));
  });
  close.addEventListener('click', hide);
  box.addEventListener('click', (e)=>{ if(e.target===box) hide(); });
  document.addEventListener('keydown', (e)=>{ if(e.key==='Escape' && box.classList.contains('open')) hide(); });
})();
