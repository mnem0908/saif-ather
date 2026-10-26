# -*- coding: utf-8 -*-
CSS = r'''
:root{--bg:#fbf7f3;--s1:#ffffff;--s2:#f6f0ea;--s3:#ece3db;--line:#e7ddd4;--t1:#241a16;--t2:#6b5d54;--t3:#9b8d83;--ac:#e8431f;--ac2:#c2370f;--ac3:#ff7a2f;--grad:linear-gradient(135deg,#ff7a2f,#e8321f);--ok:#16a05a;--err:#d92d20;--warn:#d97a00;--r:16px;--sh:0 1px 2px rgba(60,30,10,.05),0 8px 24px rgba(60,30,10,.06)}
*{box-sizing:border-box;margin:0;padding:0}html,body{min-height:100%}
body{font-family:'Readex Pro',system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;background:var(--bg);color:var(--t1);font-size:14px;-webkit-tap-highlight-color:transparent}
button,input,select,textarea{font-family:inherit;font-size:inherit;color:inherit}
.in{width:100%;background:var(--s2);border:1px solid var(--line);border-radius:10px;padding:10px 12px;outline:none}.in:focus{border-color:var(--ac)}
.btn{border:none;border-radius:10px;padding:9px 14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;background:var(--s3);border:1px solid var(--line)}
.btn:hover{border-color:var(--ac)}.btn.p{background:var(--grad);color:#fff;font-weight:600;border-color:transparent;box-shadow:0 6px 18px rgba(232,67,31,.28)}.btn.p:hover{filter:brightness(1.05)}.btn.d{color:var(--err)}.btn:disabled{opacity:.45;cursor:not-allowed}.btn.sm{padding:5px 10px;font-size:12px;border-radius:8px}
a.btn{color:var(--t1);text-decoration:none}a.btn.p{color:#fff}
'''
LOGIN = r'''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تسجيل الدخول</title><link rel="icon" href="/icon.svg"><style>''' + CSS + r'''
body{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px;background:radial-gradient(900px 520px at 85% -10%,rgba(255,122,47,.22),transparent),radial-gradient(700px 420px at 0% 110%,rgba(232,50,31,.10),transparent),var(--bg)}
.box{width:100%;max-width:400px;background:var(--s1);border:1px solid var(--line);border-radius:22px;padding:30px 26px;box-shadow:0 30px 80px rgba(120,50,20,.18)}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:6px;font-weight:600;font-size:18px}.logo img{width:40px;height:40px}
.sub{color:var(--t3);font-size:12.5px;margin-bottom:22px;line-height:1.8}
label{display:block;font-size:12px;color:var(--t2);margin:14px 0 6px}
.in{direction:ltr;text-align:left;font-family:'JetBrains Mono',ui-monospace,monospace;letter-spacing:.5px}
.err{background:rgba(239,107,91,.1);border:1px solid rgba(239,107,91,.35);color:var(--err);border-radius:10px;padding:9px 12px;font-size:12.5px;margin-top:14px;display:none;line-height:1.7}
.btn.p{width:100%;margin-top:20px;padding:12px;font-size:15px}
.foot{margin-top:18px;text-align:center;font-size:11.5px;color:var(--t3)}
</style></head><body><form class="box" id="f" autocomplete="on">
<div class="logo"><img src="/icon.svg" alt="">__SITE__</div><div class="sub">استوديو موشن احترافي بالاشتراك فقط. أدخل المعرّف وكلمة المرور اللذين وصلاك من المدير.</div>
<label for="id">المعرّف (ID)</label><input class="in" id="id" name="username" placeholder="SA-XXXXXX أو البريد (للمدير)" autocapitalize="none" spellcheck="false" autocomplete="username" required>
<label for="pw">كلمة المرور</label><input class="in" id="pw" name="password" type="password" placeholder="XXXX-XXXX-XXXX" autocomplete="current-password" required>
<div id="tw" style="display:none"><label for="tp">رمز التحقق (تطبيق المصادقة)</label><input class="in" id="tp" name="totp" inputmode="numeric" maxlength="8" placeholder="000000" autocomplete="one-time-code"></div>
<div class="err" id="e"></div><button class="btn p" id="b" type="submit">دخول</button>
<div class="foot">للاشتراك أو التجديد تواصل مع المدير</div></form>
<script>
const q=new URLSearchParams(location.search).get('e'),e=document.getElementById('e');
const M={kicked:'أُنهيت جلستك لأن الحساب سُجّل دخوله من جهاز آخر.',expired:'انتهى اشتراكك. تواصل مع المدير للتجديد.',suspended:'هذا الحساب موقوف.',pending:'الحساب غير مفعّل.'};
if(M[q]){e.textContent=M[q];e.style.display='block'}
document.getElementById('f').onsubmit=async ev=>{ev.preventDefault();const b=document.getElementById('b');b.disabled=true;b.textContent='جارٍ التحقق...';e.style.display='none';
 try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id.value,password:pw.value,totp:tp.value})});const j=await r.json().catch(()=>({}));
  if(j.need_totp){document.getElementById('tw').style.display='block';tp.focus();b.disabled=false;b.textContent='تأكيد';return}
  if(r.ok){location.href=j.admin?'/admin':'/';return}e.textContent=j.error||('خطأ '+r.status);e.style.display='block'}catch(x){e.textContent='تعذّر الاتصال بالخادم';e.style.display='block'}
 b.disabled=false;b.textContent='دخول'};
</script></body></html>'''

ADMIN = r'''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>لوحة الإدارة</title><link rel="icon" href="/icon.svg"><style>''' + CSS + r'''
.top{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;padding:10px 16px;flex-wrap:wrap}
.top img{width:30px;height:30px}.top b{font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sp{flex:1}
.tabs{display:flex;gap:4px;overflow-x:auto;padding:10px 16px 0;border-bottom:1px solid var(--line);position:sticky;top:51px;z-index:19;background:var(--bg)}
.tab{padding:9px 14px;border-radius:10px 10px 0 0;cursor:pointer;color:var(--t2);white-space:nowrap;border:1px solid transparent;border-bottom:none;font-size:13px}.tab.on{background:var(--s1);color:var(--ac2);font-weight:600;border-color:var(--line);box-shadow:inset 0 3px 0 var(--ac)}
main{max-width:1180px;margin:0 auto;padding:18px 16px 60px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.card{background:var(--s1);border:1px solid var(--line);border-radius:var(--r);padding:16px;margin-bottom:12px;box-shadow:var(--sh)}.card h3{font-size:13.5px;margin-bottom:12px;color:var(--ac2);font-weight:600}
.stat{background:var(--s1);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;box-shadow:var(--sh)}.stat small{color:var(--t3);font-size:11.5px}.stat b{display:block;font-size:26px;margin-top:4px;font-family:'JetBrains Mono',monospace;font-weight:500}
.stat.w b{color:var(--warn)}.stat.g b{color:var(--ok)}.stat.r b{color:var(--err)}
table{width:100%;border-collapse:collapse;font-size:12.5px}th{color:var(--t3);font-weight:400;text-align:right;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
tr.row{cursor:pointer}tr.row:hover td{background:var(--s2)}.mono{font-family:'JetBrains Mono',monospace;direction:ltr;unicode-bidi:embed}
.tw{overflow-x:auto}
.pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;border:1px solid var(--line)}
.pill.active{color:var(--ok);border-color:rgba(123,196,127,.4)}.pill.expired,.pill.suspended{color:var(--err);border-color:rgba(239,107,91,.4)}.pill.pending{color:var(--warn);border-color:rgba(233,180,76,.4)}
.row2{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}.row2>*{flex:1;min-width:140px}
label.l{display:block;font-size:12px;color:var(--t2);margin:0 0 5px}
.chk{display:flex;flex-wrap:wrap;gap:8px}.chk label{display:flex;gap:6px;align-items:center;background:var(--s2);border:1px solid var(--line);border-radius:20px;padding:5px 12px;font-size:12px;cursor:pointer}.chk input:checked+span{color:var(--ac2)}
.bar{height:6px;background:var(--s3);border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:var(--grad)}
.drawer{position:fixed;inset:0;background:rgba(36,26,22,.45);display:none;z-index:50;justify-content:flex-start}.drawer.on{display:flex}
.dp{width:min(640px,100%);height:100%;background:var(--bg);border-right:1px solid var(--line);overflow-y:auto;padding:18px}
.msg{white-space:pre-wrap;background:var(--s2);border:1px dashed var(--ac);border-radius:12px;padding:12px;font-size:13px;line-height:1.9;margin:10px 0}
.kv{display:grid;grid-template-columns:130px 1fr;gap:6px 10px;font-size:12.5px}.kv span{color:var(--t3)}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:var(--t1);color:#fff;border:1px solid var(--ac);border-radius:12px;padding:10px 18px;z-index:99;display:none;max-width:90vw}
.hbar{display:flex;gap:2px;align-items:flex-end;height:46px;direction:ltr}.hbar i{flex:1;background:var(--ac);opacity:.85;border-radius:2px 2px 0 0;min-height:2px}
.ok{color:var(--ok)}.er{color:var(--err)}.mu{color:var(--t3)}
.alertb{border-radius:12px;padding:11px 14px;margin-bottom:10px;font-size:13px;line-height:1.9}.alertb.warn{background:#fff4e5;border:1px solid #f5c88a;color:#8a4b00}.alertb.err{background:#fdecea;border:1px solid #f3b4ad;color:#a1261b}.alertb a{color:inherit;text-decoration:underline}
@media(max-width:700px){.tab{padding:8px 11px}table{font-size:12px}}
</style></head><body>
<div class="top"><img src="/icon.svg" alt=""><b>__SITE__ — لوحة الإدارة</b><span class="sp"></span><a class="btn sm" href="/">الاستوديو</a><a class="btn sm" href="/logout">خروج</a></div>
<div class="tabs" id="tabs"></div><main id="m"></main>
<div class="drawer" id="dr"><div class="dp" id="dp"></div></div><div class="toast" id="ts"></div>
<script>
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let META=null,TAB=localStorage.getItem('adm_tab')||'ov',TIMER=null;
function toast(t,ms=2600){const e=$('ts');e.textContent=t;e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',ms)}
async function api(u,o={}){const r=await fetch(u,{credentials:'same-origin',...o,headers:{'Content-Type':'application/json',...(o.headers||{})},body:o.body&&typeof o.body!=='string'?JSON.stringify(o.body):o.body});
 if(r.status===401){location.href='/login';throw 0}const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j}
const fd=t=>t?new Date(t*1000).toLocaleString('ar-IQ',{dateStyle:'short',timeStyle:'short'}):'—';
const fday=t=>t?new Date(t*1000).toLocaleDateString('en-CA'):'—';
const ago=t=>{if(!t)return'—';const s=Date.now()/1000-t;return s<60?'الآن':s<3600?Math.floor(s/60)+' د':s<86400?Math.floor(s/3600)+' س':Math.floor(s/86400)+' يوم'};
const mb=b=>b>1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(1)+' MB';
const ST={active:'فعّال',expired:'منتهي',suspended:'موقوف',pending:'بانتظار أول دخول'};
const pill=s=>`<span class="pill ${s}">${ST[s]||s}</span>`;
function copy(t){navigator.clipboard.writeText(t).then(()=>toast('تم النسخ ✓'),()=>{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();toast('تم النسخ ✓')})}
const TABS=[['ov','نظرة عامة'],['us','المشتركون'],['nw','اشتراك جديد'],['ac','النشاط'],['jb','العمليات'],['st','التخزين'],['pl','الباقات'],['se','الإعدادات والمفاتيح']];
function drawTabs(){$('tabs').innerHTML=TABS.map(([k,n])=>`<div class="tab ${k===TAB?'on':''}" data-k="${k}">${n}</div>`).join('');document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{TAB=t.dataset.k;localStorage.setItem('adm_tab',TAB);show()})}
async function show(){clearInterval(TIMER);drawTabs();$('m').innerHTML='<div class="mu">جارٍ التحميل...</div>';
 try{({ov,us,nw,ac,jb,st,pl,se})[TAB]()}catch(e){}}
const feats=()=>Object.entries(META.features);
function featBoxes(sel,prefix){return feats().map(([k,n])=>`<label><input type="checkbox" data-f="${k}" ${sel.includes(k)?'checked':''}><span>${n}</span></label>`).join('')}
function quotaInputs(vals){return Object.entries(META.quota_labels).map(([k,n])=>`<div><label class="l">${n}</label><input class="in mono" data-q="${k}" value="${vals[k]??''}" inputmode="numeric"></div>`).join('')}
const readF=root=>[...root.querySelectorAll('[data-f]')].filter(x=>x.checked).map(x=>x.dataset.f);
const readQ=root=>{const o={};root.querySelectorAll('[data-q]').forEach(x=>{if(x.value.trim()!=='')o[x.dataset.q]=parseInt(x.value)});return o};
async function ov(){const d=await api('/api/admin/overview');const s=d.status,v=d.storage;
 const h=(x,ok)=>x.enabled?`<span class="${x.ok===false?'er':'ok'}">${x.ok===false?'متعطل':'يعمل'}</span>`:'<span class="mu">غير مفعّل</span>';
 $('m').innerHTML=`<div class="grid">
 <div class="stat g"><small>مشتركون فعّالون</small><b>${s.active}</b></div><div class="stat w"><small>ينتهون خلال 3 أيام</small><b>${s.expiring}</b></div>
 <div class="stat r"><small>منتهون</small><b>${s.expired}</b></div><div class="stat"><small>موقوفون</small><b>${s.suspended}</b></div>
 <div class="stat"><small>رندرات اليوم</small><b>${d.renders_today}</b></div><div class="stat"><small>عمليات جارية الآن</small><b>${d.running}</b></div>
 <div class="stat"><small>حروف TTS اليوم</small><b>${d.tts_today}</b></div><div class="stat"><small>إجمالي المشتركين</small><b>${d.users}</b></div></div>
 ${(()=>{const al=d.alerts||{};let h='';if(!al.twofa)h+=`<div class="alertb warn">🔐 المصادقة الثنائية للأدمن غير مفعّلة — فعّلها من تبويب الإعدادات لحماية حسابك. <a href="#" id="go2fa">فتح</a></div>`;
  if((al.sharing||[]).length)h+=`<div class="alertb err">⚠️ اشتباه مشاركة حسابات (آخر 24 ساعة):<br>${al.sharing.map(x=>`<a href="#" class="shu" data-id="${x.id}"><b class="mono">${x.id}</b> ${esc(x.name||'')} — طُرد ${x.kicks24} مرة ${x.status==='suspended'?'· موقوف':''}</a>`).join('<br>')}</div>`;
  if(al.fails24>=10)h+=`<div class="alertb warn">محاولات دخول فاشلة آخر 24 ساعة: <b>${al.fails24}</b></div>`;return h})()}
 <div class="card" style="margin-top:12px"><h3>الأجهزة السحابية (GitHub) <span class="mu mono">${d.cloud.used}/${d.cloud.cap}</span> ${d.cloud.queued?'<span class="er">· '+d.cloud.queued+' في الطابور</span>':''}</h3>
 <div style="height:8px;background:var(--s3);border-radius:6px;overflow:hidden;margin:8px 0"><div style="height:100%;width:${Math.min(100,Math.round(100*d.cloud.used/d.cloud.cap))}%;background:var(--grad)"></div></div>
 ${d.cloud.jobs.length?'<table><tr><th>المهمة</th><th>المشترك</th><th>المرحلة</th><th>التقدم</th><th>المدة</th></tr>'+d.cloud.jobs.map(j=>`<tr><td class="mono">${esc(String(j.id||'').slice(0,8))}</td><td class="mono">${esc(j.owner||'')}</td><td>${esc(j.stage||'')} <span class="mu">${esc(j.details||'')}</span></td><td class="mono">${j.progress||0}%</td><td class="mono">${j.age}s</td></tr>`).join('')+'</table>':'<span class="mu">لا توجد عمليات جارية</span>'}</div>
 <div class="grid" style="margin-top:12px"><div class="card"><h3>حالة التخزين الآمن</h3><div class="kv"><span>GitHub</span><div>${h(v.gh)}</div><span>Telegram</span><div>${h(v.tg)}</div>
 <span>ملفات مؤمّنة</span><div class="mono">${d.media.backed} / ${d.media.count} (${d.media.mb}MB)</div><span>حجم القاعدة</span><div class="mono">${(v.db_bytes/1024).toFixed(1)} KB</div><span>معلّق للمزامنة</span><div class="mono">${v.pending.length||'لا شيء'}</div></div></div>
 <div class="card"><h3>الخادم</h3><div class="kv"><span>الإصدار</span><div class="mono">${esc(d.instance.version)}</div><span>التشغيلة</span><div class="mono">#${esc(d.instance.run)}</div><span>مدة التشغيل</span><div class="mono">${Math.floor(d.instance.uptime/3600)}h ${Math.floor(d.instance.uptime%3600/60)}m</div><span>رندر سحابي</span><div>${d.instance.cloud?'<span class="ok">مفعّل</span> '+esc(d.instance.repo):'<span class="er">غير مفعّل</span>'}</div></div></div>
 <div class="card"><h3>الأكثر استخداماً</h3>${d.top.map(u=>`<div style="display:flex;justify-content:space-between;padding:4px 0"><span>${esc(u.name||u.id)} <span class="mu mono">${u.id}</span></span><b class="mono">${u.renders}</b></div>`).join('')||'<span class="mu">—</span>'}</div></div>
 <div class="card"><h3>آخر الأحداث</h3>${evTable(d.recent)}</div>`;document.querySelectorAll('.shu').forEach(a=>a.onclick=e=>{e.preventDefault();openUser(a.dataset.id)});const g2=$('go2fa');if(g2)g2.onclick=e=>{e.preventDefault();TAB='se';show()};TIMER=setInterval(()=>{if(TAB==='ov')ov()},20000)}
const EV={login:'دخول',login_fail:'محاولة دخول فاشلة',create_user:'إنشاء اشتراك',extend:'تمديد',reset_pw:'إعادة كلمة مرور',edit_user:'تعديل',delete_user:'حذف مشترك',render:'رندر',still:'لقطة',upload:'رفع ملف',tts:'توليد صوت',media_delete:'حذف ملف',settings:'تعديل إعدادات',plans:'تعديل باقات',storage_sync:'مزامنة التخزين',force_logout:'إنهاء الجلسات',backup_download:'تنزيل نسخة احتياطية',admin_password_synced:'مزامنة كلمة المدير'};
function evTable(rows){return `<div class="tw"><table><tr><th>الوقت</th><th>الحدث</th><th>المشترك</th><th>تفاصيل</th><th>IP</th></tr>${rows.map(r=>`<tr><td class="mono">${fd(r.t)}</td><td>${EV[r.ev]||esc(r.ev)}</td><td class="mono">${esc(r.uid||'—')}</td><td class="mu">${esc(r.detail)}</td><td class="mono mu">${esc(r.ip||'')}</td></tr>`).join('')||'<tr><td colspan=5 class="mu">لا أحداث</td></tr>'}</table></div>`}
async function us(){$('m').innerHTML=`<div class="row2" style="margin-bottom:12px"><input class="in" id="q" placeholder="بحث بالاسم أو المعرّف أو الملاحظة"><select class="in" id="sf"><option value="">كل الحالات</option><option value="active">فعّال</option><option value="expiring">ينتهي قريباً</option><option value="expired">منتهي</option><option value="suspended">موقوف</option><option value="pending">بانتظار أول دخول</option></select></div><div class="card tw" id="tb"></div>`;
 const load=async()=>{const d=await api('/api/admin/users?q='+encodeURIComponent($('q').value)+'&status='+$('sf').value);
  $('tb').innerHTML=`<table><tr><th>المعرّف</th><th>الاسم</th><th>الباقة</th><th>الحالة</th><th>المتبقي</th><th>ينتهي</th><th>رندر اليوم</th><th>آخر دخول</th><th>أجهزة</th></tr>`+d.items.map(u=>`<tr class="row" data-id="${u.id}"><td class="mono">${u.id}</td><td>${esc(u.name)||'<span class="mu">—</span>'}</td><td>${esc(META.plans[u.plan]?.label||u.plan)}</td><td>${pill(u.status)}</td><td class="mono">${u.days_left==null?(u.status==='pending'?u.days+'ي':'—'):u.days_left+' ي'}</td><td class="mono">${fday(u.expires)}</td><td class="mono">${u.usage.renders||0}/${u.quotas.renders_day}</td><td>${ago(u.last_login)}</td><td class="mono">${u.sessions}${u.kicks24?` <span class="er" title="طُرد ${u.kicks24} مرة">⚠${u.kicks24}</span>`:''}</td></tr>`).join('')+(d.items.length?'':'<tr><td colspan=9 class="mu">لا مشتركين بعد — أنشئ أول اشتراك من تبويب «اشتراك جديد»</td></tr>')+'</table>';
  document.querySelectorAll('tr.row').forEach(r=>r.onclick=()=>openUser(r.dataset.id))};
 let t;$('q').oninput=()=>{clearTimeout(t);t=setTimeout(load,250)};$('sf').onchange=load;load()}
async function nw(){const dp=META.settings.default_plan,pl=META.plans;
 $('m').innerHTML=`<div class="card"><h3>إنشاء اشتراك (يولّد المعرّف وكلمة المرور تلقائياً)</h3>
 <div class="row2"><div><label class="l">اسم المشترك / ملاحظة</label><input class="in" id="nn" placeholder="مثال: أحمد"></div><div><label class="l">عدد الأيام</label><input class="in mono" id="nd" value="30" inputmode="numeric"></div><div><label class="l">عدد الحسابات</label><input class="in mono" id="nc" value="1" inputmode="numeric"></div></div>
 <div class="row2" style="margin-top:10px"><div><label class="l">الباقة</label><select class="in" id="np">${Object.entries(pl).map(([k,v])=>`<option value="${k}" ${k===dp?'selected':''}>${esc(v.label)}</option>`).join('')}</select></div>
 <div><label class="l">بداية الاشتراك</label><select class="in" id="ns"><option value="now">من الآن</option><option value="first_login">عند أول تسجيل دخول</option></select></div></div>
 <label class="l" style="margin-top:12px">مزايا مخصصة (اتركها كما هي لاستخدام مزايا الباقة)</label><div class="chk" id="nf"></div>
 <details style="margin-top:12px"><summary class="mu" style="cursor:pointer">حصص مخصصة (اختياري)</summary><div class="grid" id="nq" style="margin-top:10px"></div></details>
 <button class="btn p" id="ng" style="margin-top:16px;width:100%">توليد الاشتراك</button></div><div id="res"></div>`;
 let custom=false;const sync=()=>{const p=pl[$('np').value];$('nf').innerHTML=featBoxes(p.features);$('nq').innerHTML=quotaInputs({});$('nq').querySelectorAll('input').forEach((x,i)=>x.placeholder=p.quotas[x.dataset.q]);$('nf').querySelectorAll('input').forEach(x=>x.onchange=()=>custom=true);custom=false};
 $('np').onchange=sync;sync();
 $('ng').onclick=async()=>{$('ng').disabled=true;try{const d=await api('/api/admin/users',{method:'POST',body:{name:$('nn').value,days:+$('nd').value,count:+$('nc').value,plan:$('np').value,start:$('ns').value,features:custom?readF($('nf')):null,quotas:readQ($('nq'))}});
  $('res').innerHTML=`<div class="card"><h3>تم الإنشاء ✓ — احفظ كلمة المرور الآن (لا تظهر مرة أخرى)</h3>`+d.created.map(c=>`<div class="msg mono" style="direction:rtl;unicode-bidi:plaintext">${esc(c.message)}</div><button class="btn p sm" onclick='copy(${JSON.stringify(c.message).replace(/'/g,"\\u0027")})'>نسخ الرسالة كاملة</button> `).join('<hr style="border:0;border-top:1px solid var(--line);margin:14px 0">')+(d.created.length>1?`<button class="btn sm" style="margin-top:10px" onclick='copy(${JSON.stringify(d.created.map(c=>c.message).join("\n\n———\n\n")).replace(/'/g,"\\u0027")})'>نسخ الكل</button>`:'')+'</div>';toast('تم إنشاء '+d.created.length+' اشتراك')}catch(e){toast(e.message)}$('ng').disabled=false}}
async function openUser(id){$('dr').classList.add('on');$('dp').innerHTML='<div class="mu">...</div>';const d=await api('/api/admin/users/'+id),u=d.user;const ss=(await api('/api/admin/users/'+id+'/sessions')).items;
 const max=Math.max(1,...d.history.map(x=>x.renders||0));
 $('dp').innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center"><h2 class="mono" style="font-size:18px">${u.id}</h2><button class="btn sm" id="cl">إغلاق ✕</button></div>
 <div style="margin:8px 0 14px">${pill(u.status)} <span class="mu">${esc(u.name)}</span></div>
 <div class="card"><div class="kv"><span>الباقة</span><div><select class="in" id="up" style="padding:5px">${Object.entries(META.plans).map(([k,v])=>`<option value="${k}" ${k===u.plan?'selected':''}>${esc(v.label)}</option>`).join('')}</select></div>
 <span>ينتهي</span><div class="mono">${u.expires?fd(u.expires)+' ('+u.days_left+' يوم)':'يبدأ عند أول دخول ('+u.days+' يوم)'}</div><span>أُنشئ</span><div>${fd(u.created)}</div><span>آخر دخول</span><div>${fd(u.last_login)} · ${u.logins} مرة</div>
 <span>التخزين</span><div class="mono">${u.storage_mb} / ${u.quotas.storage_mb} MB</div><span>الإجمالي</span><div class="mono">رندر ${u.totals.renders||0} · لقطات ${u.totals.stills||0} · TTS ${u.totals.tts_chars||0} حرف · تفريغ ${Math.round(u.totals.asr_min||0)} د</div></div></div>
 <div class="card"><h3>إجراءات</h3><div style="display:flex;gap:6px;flex-wrap:wrap">${[7,30,90].map(n=>`<button class="btn sm" data-ext="${n}">+${n} يوم</button>`).join('')}<button class="btn sm" data-ext="-1">−1 يوم</button>
 <button class="btn sm" id="rs">إعادة كلمة المرور</button><button class="btn sm" id="fl">إنهاء الجلسات</button><button class="btn sm ${u.status==='suspended'?'':'d'}" id="sp">${u.status==='suspended'?'استئناف':'إيقاف'}</button><button class="btn sm d" id="dl">حذف</button></div><div id="out"></div></div>
 <div class="card"><h3>المزايا</h3><div class="chk" id="uf">${featBoxes(u.features)}</div><h3 style="margin-top:14px">الحصص (فارغ = حسب الباقة)</h3><div class="grid" id="uq">${quotaInputs(u.custom_quotas)}</div>
 <div class="row2" style="margin-top:12px"><input class="in" id="un" value="${esc(u.name)}" placeholder="الاسم"><input class="in" id="uo" value="${esc(u.note)}" placeholder="ملاحظة"></div>
 <div style="display:flex;gap:8px;margin-top:12px"><button class="btn p" id="sv" style="flex:1">حفظ التعديلات</button><button class="btn" id="rp">رجوع لمزايا الباقة</button></div></div>
 <div class="card"><h3>الرندر آخر 30 يوم</h3><div class="hbar">${d.history.slice().reverse().map(x=>`<i title="${x.day}: ${x.renders||0}" style="height:${Math.max(4,(x.renders||0)/max*100)}%"></i>`).join('')}</div></div>
 <div class="card"><h3>الجلسات النشطة (${ss.length} / ${u.quotas.max_devices||1} جهاز)</h3>${(u.flag||u.kicks24)?`<div class="alertb err">⚠️ طُرد ${u.kicks24} مرة آخر 24 ساعة — قد يشارك الحساب أكثر من شخص. <button class="btn sm" id="unf">تصفير التنبيه</button></div>`:''}
 ${ss.map(x=>`<div class="mu" style="padding:5px 0;display:flex;gap:8px;align-items:center;border-bottom:1px solid var(--line)"><span class="mono">${esc(x.ip)}</span><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.ua).slice(0,70)}</span><span>${ago(x.last)}</span><button class="btn sm d" data-rv="${x.id}">إنهاء</button></div>`).join('')||'<span class="mu">لا توجد جلسة نشطة</span>'}</div>
 <div class="card"><h3>الملفات (${d.media.length})</h3>${d.media.map(m=>`<div style="display:flex;justify-content:space-between;padding:3px 0"><span>${m.type==='video'?'🎬':'🎵'} ${esc(m.original)}</span><span class="mono mu">${mb(m.size)} ${m.backed?'<span class="ok">✓ مؤمّن</span>':'<span class="er">غير مؤمّن</span>'}</span></div>`).join('')||'<span class="mu">—</span>'}</div>
 <div class="card"><h3>آخر العمليات</h3>${d.jobs.map(j=>`<div class="mu" style="padding:3px 0"><span class="mono">${j.id}</span> ${j.kind} · ${j.status} ${esc(j.error)}</div>`).join('')||'<span class="mu">—</span>'}</div>
 <div class="card"><h3>سجل النشاط</h3>${evTable(d.audit)}</div>`;
 $('cl').onclick=()=>$('dr').classList.remove('on');
 document.querySelectorAll('[data-rv]').forEach(b=>b.onclick=async()=>{await api('/api/admin/sessions/'+b.dataset.rv+'/revoke',{method:'POST'});toast('أُنهيت');openUser(id)});const uf=$('unf');if(uf)uf.onclick=async()=>{await api(`/api/admin/users/${id}/unflag`,{method:'POST'});toast('تم');openUser(id)};
 document.querySelectorAll('[data-ext]').forEach(b=>b.onclick=async()=>{await api(`/api/admin/users/${id}/extend`,{method:'POST',body:{days:+b.dataset.ext}});toast('تم');openUser(id)});
 $('rs').onclick=async()=>{if(!confirm('توليد كلمة مرور جديدة وإنهاء كل جلساته؟'))return;const r=await api(`/api/admin/users/${id}/reset`,{method:'POST'});$('out').innerHTML=`<div class="msg mono" style="direction:rtl;unicode-bidi:plaintext">${esc(r.message)}</div><button class="btn p sm" id="cp">نسخ الرسالة</button>`;$('cp').onclick=()=>copy(r.message)};
 $('fl').onclick=async()=>{await api(`/api/admin/users/${id}/logout`,{method:'POST'});toast('أُنهيت جلساته')};
 $('sp').onclick=async()=>{await api('/api/admin/users/'+id,{method:'PATCH',body:{status:u.status==='suspended'?'active':'suspended'}});openUser(id);if(TAB==='us')us()};
 $('dl').onclick=async()=>{if(!confirm('حذف المشترك وكل ملفاته نهائياً؟'))return;await api('/api/admin/users/'+id,{method:'DELETE'});$('dr').classList.remove('on');toast('حُذف');if(TAB==='us')us()};
 $('sv').onclick=async()=>{await api('/api/admin/users/'+id,{method:'PATCH',body:{plan:$('up').value,name:$('un').value,note:$('uo').value,features:readF($('uf')),quotas:readQ($('uq'))}});toast('تم الحفظ ✓');openUser(id);if(TAB==='us')us()};
 $('rp').onclick=async()=>{await api('/api/admin/users/'+id,{method:'PATCH',body:{features:null,quotas:{}}});toast('عاد لمزايا الباقة');openUser(id)}}
$('dr').onclick=e=>{if(e.target.id==='dr')$('dr').classList.remove('on')};
async function ac(){const d=await api('/api/admin/audit');$('m').innerHTML=`<div class="card">${evTable(d.items)}</div>`}
async function jb(){const d=await api('/api/admin/jobs');$('m').innerHTML=`<div class="card tw"><table><tr><th>المعرّف</th><th>المالك</th><th>النوع</th><th>الحالة</th><th>المرحلة</th><th>التقدم</th><th>منذ</th><th></th></tr>`+d.items.map(j=>`<tr><td class="mono">${j.id}</td><td class="mono">${esc(j.owner||'—')}</td><td>${j.kind}</td><td>${j.status}</td><td class="mu">${esc(j.stage||'')} ${esc(j.error)}</td><td class="mono">${j.progress||0}%</td><td>${ago(j.created)}</td><td>${j.status==='processing'?`<button class="btn sm d" data-c="${j.id}">إلغاء</button>`:''}</td></tr>`).join('')+'</table></div>';
 document.querySelectorAll('[data-c]').forEach(b=>b.onclick=async()=>{await api('/api/cancel/'+b.dataset.c,{method:'POST'});toast('أُرسل الإلغاء');jb()});TIMER=setInterval(()=>{if(TAB==='jb')jb()},6000)}
async function st(){const d=await api('/api/admin/storage');const hs=(n,x)=>`<div class="kv"><span>${n}</span><div>${!x.enabled?'<span class="mu">غير مفعّل</span>':x.ok===false?'<span class="er">متعطل: '+esc(x.err)+'</span>':x.ok?'<span class="ok">يعمل</span> · آخر نجاح '+ago(x.last_ok):'—'}</div></div>`;
 $('m').innerHTML=`<div class="card"><h3>كيف يحمي النظام بياناتك</h3><div class="mu" style="line-height:2">كل البيانات (المشتركون، الاشتراكات، الملفات، التفريغ، الإعدادات) <b>مشفّرة AES-256</b> بمفتاح SA_MASTER وتُحفظ في مكانين مستقلين: فرع <span class="mono">vault</span> وإصدارات GitHub، وقناة تلغرام (اختياري). الملفات المرفوعة تُنسخ تلقائياً فتعود عند أي إعادة تشغيل. القرص المحلي مجرد كاش.</div></div>
 <div class="card"><h3>الحالة</h3>${hs('GitHub',d.gh)}${hs('Telegram',d.tg)}<div class="kv"><span>تحميل القاعدة من</span><div class="mono">${esc((d.loaded_from||[]).join(' · ')||'قاعدة جديدة')}</div><span>السجلات</span><div class="mono">${Object.entries(d.records).map(([k,v])=>k+':'+v).join(' · ')}</div><span>حجم القاعدة</span><div class="mono">${(d.db_bytes/1024).toFixed(1)} KB</div><span>ملفات الوسائط</span><div class="mono">${d.media.count} (${mb(d.media.bytes)}) · مؤمّن ${d.media.backed} · على القرص ${d.media.cached}</div></div>
 ${d.media.unbacked.length?`<div class="er" style="margin-top:10px">ملفات غير مؤمّنة: ${d.media.unbacked.map(x=>esc(x.file)+' '+esc(x.err)).join(' | ')}</div>`:''}</div>
 <div class="card"><h3>إجراءات</h3><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn p" id="a1">مزامنة الآن</button><button class="btn" id="a2">اختبار القراءة والكتابة</button><button class="btn" id="a3">إعادة تأمين الملفات</button><a class="btn" href="/api/admin/backup">تنزيل نسخة احتياطية مشفّرة</a><button class="btn d" id="a4">استعادة من تلغرام</button></div><pre class="mono mu" id="so" style="margin-top:10px;white-space:pre-wrap"></pre></div>`;
 const go=async(p,id)=>{$('so').textContent='...';try{const r=await api('/api/admin/storage/'+p,{method:'POST'});$('so').textContent=JSON.stringify(r,null,1);if(p==='sync')st()}catch(e){$('so').textContent=e.message}};
 $('a1').onclick=()=>go('sync');$('a2').onclick=()=>go('selftest');$('a3').onclick=()=>go('rebackup');$('a4').onclick=()=>{if(confirm('دمج آخر نسخة من تلغرام داخل القاعدة؟'))go('restore_tg')}}
async function pl(){const P=JSON.parse(JSON.stringify(META.plans));
 const draw=()=>{$('m').innerHTML=Object.entries(P).map(([k,v])=>`<div class="card" data-k="${k}"><h3>${esc(k)}</h3><div class="row2"><div><label class="l">الاسم الظاهر</label><input class="in" data-l value="${esc(v.label)}"></div></div><label class="l" style="margin-top:10px">المزايا</label><div class="chk">${featBoxes(v.features)}</div><label class="l" style="margin-top:10px">الحصص</label><div class="grid">${quotaInputs(v.quotas)}</div>${Object.keys(P).length>1?`<button class="btn d sm" data-rm="${k}" style="margin-top:10px">حذف الباقة</button>`:''}</div>`).join('')+`<div style="display:flex;gap:8px"><button class="btn" id="pa">+ باقة جديدة</button><button class="btn p" id="ps">حفظ الباقات</button></div>`;
  document.querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>{collect();delete P[b.dataset.rm];draw()});
  $('pa').onclick=()=>{collect();const n=prompt('اسم المفتاح (إنجليزي صغير، مثال: gold)');if(n&&/^[a-z0-9_]{2,20}$/.test(n)){P[n]={label:n,features:['upload','code','render'],quotas:{renders_day:5,max_duration:60,storage_mb:300,tts_chars_day:0,asr_min_day:0,stills_day:40}};draw()}};
  $('ps').onclick=async()=>{collect();try{const r=await api('/api/admin/plans',{method:'PUT',body:{plans:P}});META.plans=r.plans;toast('تم حفظ الباقات ✓')}catch(e){toast(e.message)}}};
 const collect=()=>document.querySelectorAll('.card[data-k]').forEach(c=>{const k=c.dataset.k;P[k]={label:c.querySelector('[data-l]').value,features:readF(c),quotas:readQ(c)}});draw()}
const PROV=[['gemini_key','Gemini API Key','صوت التعليق TTS (Google AI Studio)','gemini'],['grok_key','Grok (xAI) API Key','صوت التعليق TTS','grok'],['freesound_key','Freesound API Key','مؤثرات + موسيقى','freesound'],['openai_key','OpenAI-compatible Key','TTS اختياري (OpenAI أو أي خدمة متوافقة)','openai'],['groq_key','Groq API Key','تفريغ سريع لمزامنة الكلمات (اختياري)','groq']];
async function tfx(){const st=await api('/api/admin/2fa'),bx=$('tfb');
 if(st.enabled){bx.innerHTML=`<div class="ok" style="margin-bottom:8px">✓ مفعّلة — يُطلب رمز من تطبيق المصادقة عند كل دخول للأدمن.</div><div class="row2"><input class="in mono" id="tfc" placeholder="رمز حالي لإيقافها" inputmode="numeric"><button class="btn d" id="tfo" style="flex:0 0 auto">إيقاف</button></div>`;
  $('tfo').onclick=async()=>{try{await api('/api/admin/2fa?code='+encodeURIComponent($('tfc').value),{method:'DELETE'});toast('أُوقفت');tfx()}catch(e){toast(e.message)}}}
 else{bx.innerHTML=`<div style="margin-bottom:8px">تحمي حساب الأدمن حتى لو سُرّبت كلمة المرور. استخدم Google Authenticator أو أي تطبيق TOTP.</div><button class="btn p" id="tfs">تفعيل</button><div id="tfx"></div>`;
  $('tfs').onclick=async()=>{const r=await api('/api/admin/2fa',{method:'POST',body:{action:'setup'}});$('tfs').style.display='none';
   $('tfx').innerHTML=`<div class="msg mono" style="direction:ltr;text-align:left">${esc(r.secret)}</div><div class="mu" style="margin-bottom:8px">أضف مفتاحاً يدوياً في التطبيق (نوع: مرتبط بالوقت) بهذا السر، ثم اكتب الرمز المكوّن من 6 أرقام:</div><div class="row2"><input class="in mono" id="tfc2" placeholder="000000" inputmode="numeric" maxlength="6"><button class="btn p" id="tfe" style="flex:0 0 auto">تأكيد وتفعيل</button></div><a href="${esc(r.uri)}" class="mu">فتح في تطبيق المصادقة</a>`;
   $('tfe').onclick=async()=>{try{await api('/api/admin/2fa',{method:'POST',body:{action:'enable',code:$('tfc2').value}});toast('فُعّلت ✓');tfx()}catch(e){toast(e.message)}}}}}
async function se(){const s=(await api('/api/admin/settings'));META.settings=s;
 $('m').innerHTML=`<div class="card"><h3>مفاتيح الخدمات (تُحفظ مشفّرة، ولا تظهر للمشتركين)</h3>`+PROV.map(([k,n,d,t])=>`<div class="row2" style="margin-bottom:10px"><div><label class="l">${n} <span class="mu">— ${d}</span> ${s[k].set?'<span class="ok mono">••••'+esc(s[k].tail)+' ✓</span>':'<span class="mu">غير مضبوط</span>'}</label><input class="in mono" data-k="${k}" type="password" placeholder="${s[k].set?'اتركه فارغاً للإبقاء':'الصق المفتاح'}" autocomplete="off"></div><div style="flex:0 0 auto;min-width:0;display:flex;gap:6px"><button class="btn sm" data-t="${t}">اختبار</button>${s[k].set?`<button class="btn sm d" data-del="${k}">حذف</button>`:''}</div></div>`).join('')+
 `<div class="row2"><div><label class="l">Gemini TTS model</label><input class="in mono" data-p="gemini_model" placeholder="gemini-3.1-flash-tts-preview" value="${esc(s.gemini_model)}"></div></div>
 <div class="row2" style="margin-top:10px"><div><label class="l">OpenAI Base URL</label><input class="in mono" data-p="openai_base" placeholder="https://api.openai.com/v1" value="${esc(s.openai_base)}"></div><div><label class="l">OpenAI TTS model</label><input class="in mono" data-p="openai_model" placeholder="gpt-4o-mini-tts" value="${esc(s.openai_model)}"></div></div>
 <div id="tr" class="mono mu" style="margin-top:10px"></div></div>
 <div class="card" id="tf"><h3>🔐 المصادقة الثنائية للأدمن (TOTP)</h3><div id="tfb" class="mu">...</div></div>
 <div class="card"><h3>إعدادات الموقع</h3><div class="row2"><div><label class="l">اسم الموقع</label><input class="in" data-p="site_name" value="${esc(s.site_name)}"></div><div><label class="l">الرابط الدائم (يظهر في رسالة المشترك)</label><input class="in mono" data-p="public_url" value="${esc(s.public_url)}"></div></div>
 <div class="row2" style="margin-top:10px"><div><label class="l">أقصى رندرات سحابية متزامنة</label><input class="in mono" data-p="max_cloud" value="${esc(s.max_cloud)}"></div><div><label class="l">أجهزة GitHub المشتركة (4–19)</label><input class="in mono" data-p="cloud_slots" value="${esc(s.cloud_slots)}"></div><div><label class="l">ثواني لكل جهاز (2–120)</label><input class="in mono" data-p="sec_per_machine" value="${esc(s.sec_per_machine)}"></div><div><label class="l">حد الطرد قبل الإيقاف التلقائي (0 = معطّل)</label><input class="in mono" data-p="share_kicks" value="${esc(s.share_kicks)}"></div><div><label class="l">الباقة الافتراضية</label><select class="in" data-p="default_plan">${Object.entries(META.plans).map(([k,v])=>`<option value="${k}" ${k===s.default_plan?'selected':''}>${esc(v.label)}</option>`).join('')}</select></div></div>
 <label class="l" style="margin-top:10px">نص يُضاف لرسالة المشترك</label><textarea class="in" data-p="welcome" rows="2">${esc(s.welcome)}</textarea>
 <div class="switchrow" style="margin-top:12px"><label class="chk"><label><input type="checkbox" id="mt" ${s.maintenance?'checked':''}><span>وضع الصيانة (يمنع المشتركين مؤقتاً)</span></label></label></div>
 <input class="in" data-p="maintenance_msg" value="${esc(s.maintenance_msg)}" style="margin-top:8px"></div><button class="btn p" id="sv" style="width:100%">حفظ الإعدادات</button>`;
 tfx();
 document.querySelectorAll('[data-t]').forEach(b=>b.onclick=async()=>{b.disabled=true;$('tr').textContent='جارٍ الاختبار...';try{const r=await api('/api/admin/test/'+b.dataset.t,{method:'POST'});$('tr').innerHTML=(r.ok?'<span class="ok">✓ ':'<span class="er">✗ ')+esc(r.msg)+'</span>'}catch(e){$('tr').textContent=e.message}b.disabled=false});
 document.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('حذف المفتاح؟'))return;await api('/api/admin/settings',{method:'PUT',body:{[b.dataset.del]:''}});se()});
 $('sv').onclick=async()=>{const body={maintenance:$('mt').checked};document.querySelectorAll('[data-k]').forEach(i=>{if(i.value.trim())body[i.dataset.k]=i.value.trim()});document.querySelectorAll('[data-p]').forEach(i=>body[i.dataset.p]=i.value);
  try{await api('/api/admin/settings',{method:'PUT',body});toast('تم الحفظ ✓');se()}catch(e){toast(e.message)}}}
(async()=>{try{META=await api('/api/admin/meta')}catch(e){return}show()})();
</script></body></html>'''
