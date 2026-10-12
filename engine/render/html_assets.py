"""CSS + JS runtime embedded in every HTML deck (1920x1080 stage, scaled to fit)."""

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:var(--letterbox)}
body{font-family:var(--fb);color:var(--text);-webkit-font-smoothing:antialiased}
.stage{position:absolute;left:50%;top:50%;width:1920px;height:1080px;transform:translate(-50%,-50%) scale(var(--s,1))}
.slide{position:absolute;inset:0;overflow:hidden;background:var(--bg);color:var(--text);opacity:0;visibility:hidden;
  transition:opacity .7s ease,transform .8s cubic-bezier(.2,.7,.2,1),visibility 0s linear .8s}
.slide.active{opacity:1;visibility:visible;transform:none!important;transition:opacity .7s ease,transform .8s cubic-bezier(.2,.7,.2,1),visibility 0s}
[data-transition=slide] .slide{transform:translateX(90px)}
[data-transition=slide] .slide.past{transform:translateX(-90px)}
[data-transition=zoom] .slide{transform:scale(1.05)}
[data-transition=zoom] .slide.past{transform:scale(.95)}
.slide.bg-primary{background:var(--primary)}
.slide.bg-surface{background:var(--surface)}
.slide.bg-dark{background:#0b0b10}
.slide.on-primary{--text:var(--on-primary);--muted:var(--on-primary-muted);--hl:var(--on-primary);--grid:var(--on-primary-grid)}
.slide.on-image{--text:#fff;--muted:rgba(255,255,255,.82);--hl:#fff}

/* entrance animations */
.a{opacity:0}
.slide.active .a{animation:var(--anim,rise) .85s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--d,0)*1ms)}
@keyframes rise{from{opacity:0;transform:translateY(42px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes zoom{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:none}}
@keyframes slide{from{opacity:0;transform:translateX(-70px)}to{opacity:1;transform:none}}
@keyframes wipe{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes growY{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes growX{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes sweep{from{stroke-dasharray:0 100;opacity:1}to{opacity:1}}
@keyframes kb{from{transform:scale(1.14)}to{transform:scale(1)}}
@keyframes reveal{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes floaty{0%,100%{transform:translate(0,0)}50%{transform:translate(-30px,24px)}}

.accent-bar{width:130px;height:10px;border-radius:6px;background:var(--accent);transform:scaleX(0);transform-origin:left}
.slide.active .accent-bar{animation:wipe .9s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--d,0)*1ms)}
.chart{width:100%;height:100%;overflow:visible}
.chart .bar{transform-box:fill-box}
.chart .vbar{transform:scaleY(0);transform-origin:bottom}
.chart .hbar{transform:scaleX(0);transform-origin:left}
.slide.active .chart .vbar{animation:growY 1s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--d,0)*1ms)}
.slide.active .chart .hbar{animation:growX 1s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--d,0)*1ms)}
.chart .line{stroke-dasharray:1;stroke-dashoffset:1}
.slide.active .chart .line{animation:draw 1.5s ease-in-out both;animation-delay:calc(var(--d,0)*1ms)}
.chart .lbl,.chart .pie{opacity:0}
.slide.active .chart .lbl{animation:fade .6s ease both;animation-delay:calc(var(--d,0)*1ms)}
.slide.active .chart .pie{animation:sweep 1.1s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--d,0)*1ms)}
.bgimg{position:absolute;inset:0;background-size:cover;background-position:center}
.slide.active .kb{animation:kb 14s ease-out both}
.shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.05) 25%,rgba(0,0,0,.78) 100%)}
.shade.full{background:linear-gradient(110deg,rgba(0,0,0,.72) 10%,rgba(0,0,0,.25) 100%)}
.deco{position:absolute;border-radius:50%;pointer-events:none}
.deco.d1{right:-260px;top:-260px;width:820px;height:820px;background:radial-gradient(circle at 35% 35%,var(--accent),transparent 68%);opacity:.38}
.deco.d2{left:-180px;bottom:-240px;width:560px;height:560px;background:radial-gradient(circle,var(--accent2),transparent 70%);opacity:.22}
.slide.active .deco{animation:floaty 16s ease-in-out infinite}

/* typography */
h1,h2,.num,.qt{font-family:var(--fh)}
h1{font-size:112px;line-height:1.02;font-weight:800;letter-spacing:-.025em;max-height:360px;overflow:hidden}
h2{font-size:70px;line-height:1.08;font-weight:760;letter-spacing:-.015em;max-height:162px;overflow:hidden}
.sub{font-size:40px;line-height:1.3;color:var(--muted);max-height:160px;overflow:hidden}
.hl{color:var(--hl,var(--primary))}

/* chrome */
.logo{position:absolute;height:66px;max-width:280px;object-fit:contain;z-index:5}
.logo.pill{background:#fff;padding:10px 18px;border-radius:14px;height:86px}
.logo.top-right{top:70px;right:96px}.logo.top-left{top:70px;left:110px}
.logo.bottom-right{bottom:56px;right:96px}.logo.bottom-left{bottom:56px;left:110px}
.logo.big{height:110px;max-width:420px}
.pn,.foot{position:absolute;bottom:52px;font-size:22px;color:var(--muted);letter-spacing:.04em}
.pn{right:110px}.foot{left:110px}
.pn.left{right:auto;left:110px}.foot.center{left:50%;transform:translateX(-50%)}

/* layout regions */
.head{position:absolute;left:110px;right:420px;top:86px;display:flex;flex-direction:column;gap:26px}
.body{position:absolute;left:110px;right:110px;top:316px;bottom:120px}
ul.bul{list-style:none;font-size:46px;line-height:1.28;display:flex;flex-direction:column;gap:.62em;height:100%;overflow:hidden}
ul.bul li{position:relative;padding-left:1.15em}
ul.bul li::before{content:"";position:absolute;left:.12em;top:.47em;width:.4em;height:.4em;border-radius:50%;background:var(--accent)}
ul.bul li b{color:var(--hl,var(--primary));font-weight:750}

.s-title .wrap,.s-closing .wrap{position:absolute;left:110px;right:330px;bottom:190px;display:flex;flex-direction:column;gap:34px}
.s-closing .wrap{left:160px;right:160px;bottom:auto;top:50%;transform:translateY(-50%);align-items:center;text-align:center}
.s-closing .accent-bar{transform-origin:center}
.s-closing .logo{position:static;margin-bottom:20px}
.s-section .wrap{position:absolute;left:110px;right:260px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:22px}
.s-section .num{font-size:230px;font-weight:850;line-height:.9;color:var(--accent);letter-spacing:-.04em}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:72px;height:100%}
.card{background:var(--surface);border-radius:30px;padding:48px 52px;display:flex;flex-direction:column;gap:26px;overflow:hidden}
.slide.bg-surface .card{background:var(--bg)}
.card h3{font-family:var(--fh);font-size:42px;color:var(--hl,var(--primary));font-weight:760}
.card ul.bul{font-size:38px}
.split{display:grid;grid-template-columns:1.75fr 1fr;gap:64px;height:100%;align-items:center}
.split ul.bul{font-size:36px;height:auto;max-height:100%}
.stats{display:grid;gap:44px;height:100%;align-content:center}
.stat{background:var(--surface);border-radius:32px;padding:60px 48px;display:flex;flex-direction:column;gap:18px;min-height:380px;justify-content:center}
.slide.bg-surface .stat{background:var(--bg)}
.stat .v{font-family:var(--fh);font-size:128px;line-height:1;font-weight:820;color:var(--hl,var(--primary));letter-spacing:-.03em;white-space:nowrap}
.stat .l{font-size:36px;color:var(--muted);line-height:1.25}
table.tb{width:100%;border-collapse:separate;border-spacing:0;font-size:32px;border-radius:24px;overflow:hidden}
table.tb th{background:var(--primary);color:var(--on-primary);text-align:left;padding:24px 30px;font-weight:700}
table.tb td{padding:22px 30px;border-bottom:2px solid var(--grid)}
table.tb tr:nth-child(even) td{background:var(--surface)}
.s-image .wrap{position:absolute;left:110px;right:300px;bottom:110px;display:flex;flex-direction:column;gap:26px}
.s-image h2{font-size:84px;max-height:200px}
.s-image_text .pic{position:absolute;left:0;top:0;bottom:0;width:46%;overflow:hidden}
.s-image_text .pic .bgimg{inset:0}
.slide.active .reveal{animation:reveal 1.2s cubic-bezier(.7,0,.2,1) both}
.s-image_text .side{position:absolute;left:52%;right:110px;top:150px;bottom:120px;display:flex;flex-direction:column;gap:30px}
.s-image_text .side ul.bul{font-size:38px;height:auto;flex:1}
.s-quote .mark{position:absolute;left:96px;top:-40px;font-family:Georgia,serif;font-size:520px;line-height:1;color:var(--accent);opacity:.9}
.s-quote .wrap{position:absolute;left:200px;right:200px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:46px}
.s-quote .qt{font-size:70px;line-height:1.2;font-weight:600;font-style:italic;max-height:600px;overflow:hidden}
.s-quote .by{font-size:36px;color:var(--muted)}

/* UI overlays */
.progress{position:fixed;left:0;right:0;bottom:0;height:5px;background:rgba(127,127,127,.18);z-index:20}
.progress i{display:block;height:100%;width:0;background:var(--accent);transition:width .5s ease}
.notes-panel{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);width:min(900px,92vw);max-height:32vh;overflow:auto;
  background:rgba(15,15,20,.92);color:#f3f4f6;font:16px/1.5 system-ui,sans-serif;padding:16px 20px;border-radius:12px;display:none;z-index:30}
.notes-panel.on{display:block}
.hint{position:fixed;right:16px;bottom:16px;font:13px system-ui,sans-serif;color:#9ca3af;background:rgba(0,0,0,.55);padding:6px 10px;border-radius:8px;z-index:25;transition:opacity 1s}
.hint.off{opacity:0}

/* static mode (?static) for screenshots: final state, no motion */
html.static *{animation-duration:0s!important;animation-delay:0s!important;transition:none!important}
html.static .hint{display:none}

@media print{
  @page{size:1920px 1080px;margin:0}
  html,body{overflow:visible;height:auto;background:none}
  .stage{position:static;transform:none!important;width:1920px;height:auto}
  .slide{position:relative;width:1920px;height:1080px;opacity:1!important;visibility:visible!important;transform:none!important;break-after:page}
  .slide *{animation:none!important}
  .a,.chart .lbl,.chart .pie{opacity:1!important}
  .accent-bar,.chart .bar{transform:none!important}
  .chart .line{stroke-dashoffset:0!important}
  .reveal{clip-path:none!important}
  .progress,.notes-panel,.hint{display:none!important}
}
"""

JS = r"""
(()=>{
const root=document.documentElement, stage=document.getElementById('stage');
const slides=[...document.querySelectorAll('.slide')];
const notes=JSON.parse(document.getElementById('deck-notes').textContent||'[]');
const params=new URLSearchParams(location.search);
const isStatic=params.has('static');
if(isStatic) root.classList.add('static');
const bar=document.querySelector('.progress i'), panel=document.querySelector('.notes-panel'), hint=document.querySelector('.hint');
let cur=-1;
function scale(){stage.style.setProperty('--s',Math.min(innerWidth/1920,innerHeight/1080));}
addEventListener('resize',scale);scale();
function fit(){
  document.querySelectorAll('.fit').forEach(el=>{
    let size=parseFloat(getComputedStyle(el).fontSize);const min=parseFloat(el.dataset.min||22);let guard=80;
    while((el.scrollHeight>el.clientHeight+2||el.scrollWidth>el.clientWidth+2)&&size>min&&guard--){size-=2;el.style.fontSize=size+'px';}
  });
}
function countUp(slide){
  slide.querySelectorAll('[data-count]').forEach(el=>{
    const target=parseFloat(el.dataset.count),dec=+el.dataset.dec||0,pre=el.dataset.pre||'',suf=el.dataset.suf||'';
    const f=v=>pre+v.toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec})+suf;
    if(isStatic){el.textContent=f(target);return;}
    const delay=parseFloat(el.closest('[style*="--d"]')?.style.getPropertyValue('--d')||0)+250,dur=1500,t0=performance.now();
    el.textContent=f(0);
    const step=now=>{const t=Math.min(1,Math.max(0,(now-t0-delay)/dur));el.textContent=f(target*(1-Math.pow(1-t,3)));if(t<1&&slide.classList.contains('active'))requestAnimationFrame(step);else el.textContent=f(target);};
    requestAnimationFrame(step);
  });
}
function go(i){
  i=Math.max(0,Math.min(slides.length-1,i));
  if(i===cur)return;
  slides.forEach((s,k)=>{s.classList.toggle('active',k===i);s.classList.toggle('past',k<i);});
  cur=i;countUp(slides[i]);
  if(bar)bar.style.width=((i+1)/slides.length*100)+'%';
  if(panel)panel.textContent=notes[i]||'(no notes)';
  if(!isStatic)history.replaceState(null,'','#'+(i+1));
}
const next=()=>go(cur+1),prev=()=>go(cur-1);
addEventListener('keydown',e=>{
  if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();next();}
  else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();prev();}
  else if(e.key==='Home')go(0);else if(e.key==='End')go(slides.length-1);
  else if(e.key==='f'||e.key==='F'){document.fullscreenElement?document.exitFullscreen():root.requestFullscreen?.();}
  else if(e.key==='n'||e.key==='N')panel?.classList.toggle('on');
});
addEventListener('click',e=>{if(e.target.closest('a,.notes-panel'))return;e.clientX>innerWidth/3?next():prev();});
let tx=null;
addEventListener('touchstart',e=>{tx=e.touches[0].clientX;},{passive:true});
addEventListener('touchend',e=>{if(tx===null)return;const dx=e.changedTouches[0].clientX-tx;if(Math.abs(dx)>40)dx<0?next():prev();tx=null;});
addEventListener('message',e=>{const d=e.data||{};if(d.deckGo!==undefined)go(d.deckGo);});
window.deck={go,next,prev,get index(){return cur},count:slides.length};
const start=()=>{fit();const h=parseInt((location.hash||'#1').slice(1),10);go(isNaN(h)?0:h-1);window.deckReady=true;};
(document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(start);
if(hint)setTimeout(()=>hint.classList.add('off'),4000);
})();
"""
