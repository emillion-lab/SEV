// SEV — карта + timeline на софийски събития с такси demand прозорци
document.addEventListener('DOMContentLoaded', () => {
  const $ = id => document.getElementById(id);
  const map = L.map('map', {zoomControl: false}).setView([42.687, 23.335], 12.4);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution: '© OpenStreetMap', maxZoom: 19}).addTo(map);

  const DUR = 2.5 * 3600e3;           // типична продължителност на събитие
  const PRE = 2 * 3600e3;             // dropoff прозорец: 2ч преди старт
  const POST = 45 * 60e3;             // pickup прозорец: 45мин след края
  const fmtT = d => d.toLocaleTimeString('bg', {hour:'2-digit', minute:'2-digit'});
  const fmtD = d => d.toLocaleDateString('bg', {weekday:'long', day:'numeric', month:'long'});

  function heat(cap) {
    if (cap >= 8000) return {c:'#d32f2f', cls:'c-hot', r:22, lbl:'МЕГА'};
    if (cap >= 2500) return {c:'#e08a00', cls:'c-warm', r:15, lbl:'СИЛНО'};
    return {c:'#2e7d32', cls:'c-ok', r:9, lbl:'средно'};
  }

  fetch('events.json?t=' + Date.now()).then(r => r.json()).then(data => {
    const now = Date.now();
    const evs = (data.events || []).map(e => {
      const start = new Date(e.start).getTime();
      return {...e, startMs: start, endMs: start + DUR};
    }).filter(e => e.endMs + POST > now).sort((a,b) => a.startMs - b.startMs);

    // статус badge
    const gen = data.generated ? new Date(data.generated) : null;
    const ageD = gen ? (now - gen.getTime()) / 864e5 : 999;
    const badge = $('stBadge');
    if (ageD <= 8) { badge.textContent = 'LIVE'; badge.className = 'badge b-ok'; }
    else { badge.textContent = `данни от ${Math.round(ageD)}д`; badge.className = 'badge b-stale'; }
    $('stTxt').innerHTML = `${evs.length} събития · ${ (data.sources_ok||[]).join('+') || 'няма източник' }`;

    if (!evs.length) { $('empty').style.display = 'block'; }

    // ---- КАРТА: агрегирано по зала ----
    const byVenue = {};
    evs.forEach(e => {
      if (!e.lat) return;
      const k = e.venue;
      (byVenue[k] = byVenue[k] || {lat:e.lat, lon:e.lon, cap:e.cap, list:[]}).list.push(e);
    });
    Object.entries(byVenue).forEach(([name, v]) => {
      const h = heat(v.cap);
      const next = v.list[0];
      const active = next && now > next.startMs - PRE && now < next.endMs + POST;
      const mk = L.circleMarker([v.lat, v.lon], {
        radius: h.r, color: h.c, weight: active ? 3 : 1.5,
        fillColor: h.c, fillOpacity: active ? 0.7 : 0.4
      }).addTo(map);
      const rows = v.list.slice(0,5).map(e => {
        const s = new Date(e.startMs), en = new Date(e.endMs);
        return `<div style="margin:6px 0"><b>${e.name}</b><br>` +
          `<span style="color:#667">${fmtD(s)} ${fmtT(s)}</span><br>` +
          `🚕 Dropoff: <b>${fmtT(new Date(e.startMs-PRE))}–${fmtT(s)}</b><br>` +
          `🚕 Pickup: <b>${fmtT(en)}–${fmtT(new Date(e.endMs+POST))}</b></div>`;
      }).join('');
      mk.bindPopup(`<b style="font-size:14px">${name}</b> <small>(~${v.cap.toLocaleString('bg')})</small>${rows}`);
      if (active) {
        L.circleMarker([v.lat, v.lon], {radius: h.r+8, color: h.c, weight: 1,
          fill: false, opacity: 0.5}).addTo(map);
      }
    });

    // ---- TIMELINE ----
    const list = $('list');
    let lastDay = '';
    evs.forEach(e => {
      const s = new Date(e.startMs), en = new Date(e.endMs);
      const day = fmtD(s);
      if (day !== lastDay) {
        lastDay = day;
        const dh = document.createElement('div');
        dh.className = 'day'; dh.textContent = day;
        list.appendChild(dh);
      }
      const h = heat(e.cap);
      const el = document.createElement('div');
      el.className = 'ev';
      el.innerHTML =
        `<div class="cap ${h.cls}">${e.cap>=1000 ? Math.round(e.cap/1000)+'k' : e.cap}<small>${h.lbl}</small></div>` +
        `<div style="flex:1"><div class="nm">${e.name}</div>` +
        `<div class="vn">📍 ${e.venue} · ${fmtT(s)} <small style="opacity:.6">(${e.src})</small></div>` +
        `<div class="win">🚕 dropoff <b>${fmtT(new Date(e.startMs-PRE))}–${fmtT(s)}</b> · ` +
        `pickup <b>${fmtT(en)}–${fmtT(new Date(e.endMs+POST))}</b></div></div>`;
      if (e.lat) el.onclick = () => {
        $('tMap').click();
        map.setView([e.lat, e.lon], 15);
      };
      list.appendChild(el);
    });
  }).catch(err => {
    $('stTxt').textContent = 'грешка при зареждане';
    console.error(err);
  });

  // табове
  $('tMap').onclick = () => { tab(true); };
  $('tList').onclick = () => { tab(false); };
  function tab(m) {
    $('tMap').classList.toggle('on', m);
    $('tList').classList.toggle('on', !m);
    $('map').style.display = m ? 'block' : 'none';
    $('list').style.display = m ? 'none' : 'block';
    if (m) map.invalidateSize();
  }
});
