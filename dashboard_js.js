/* dashboard_js.js - Client-side report renderer.
 * Single source of truth for the dashboard JS: dashboard.py reads this file at
 * build time and injects data via the __PLACEHOLDER__ tokens below.
 * Do not rename the placeholders. */

var ALL_DATA   = __ALL_DATA__;
var FIRST_ID   = __FIRST_ID__;
var MMI_COLORS = __MMI_COLORS__;
var ALERT_C    = __ALERT_C__;
var PAGER_DESC = __PAGER_DESC__;

var _map = null, _active = null, _pga = null, _mmi = null,
    _base = null, _sat = null, _satOn = false, _current = null;

// ── Generic helpers ───────────────────────────────────────────────────────────

// Escape any dynamic string before inserting it into HTML (place names, news
// headlines and summaries come from external services and must not be trusted).
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Only allow http(s) links from data.
function safeUrl(u) {
  u = String(u || '');
  return /^https?:\/\//i.test(u) ? u : '';
}

function coordStr(lat, lon) {
  return Math.abs(lat).toFixed(3) + '\u00b0 ' + (lat >= 0 ? 'N' : 'S') + '  '
       + Math.abs(lon).toFixed(3) + '\u00b0 ' + (lon >= 0 ? 'E' : 'W');
}

// ── Seismology helpers ────────────────────────────────────────────────────────

function pgaConvert(p) {
  var g = p / 100, m = g * 9.81;
  return {
    g:   (g < 0.1 ? g.toFixed(3) : g.toFixed(2)) + 'g',
    ms2: (m < 1   ? m.toFixed(2) : m.toFixed(1)) + ' m/s\u00b2'
  };
}
function mmiToPga(m)  { return m > 0 ? Math.min(300, Math.round(Math.pow(10, (m - 1.78) / 2.5))) : 0; }
function pgaLabel(p)  { return p >= 300 ? 'Extreme' : p >= 100 ? 'Very High' : p >= 30 ? 'High' : p >= 10 ? 'Moderate' : p >= 3 ? 'Low-Mod' : 'Low'; }
function pgaColor(p)  { return p >= 100 ? '#d32f2f' : p >= 30 ? '#e65100' : p >= 10 ? '#f9a825' : '#2e7d32'; }
function faultColor(t){ return {'Strike-Slip':'#1565c0','Reverse / Thrust':'#d32f2f','Normal':'#e65100','Oblique Reverse':'#6a1b9a','Oblique Normal':'#00695c'}[t] || '#555'; }
function faultNote(t) { return {'Strike-Slip':'Strong horizontal shaking in narrow corridors.','Reverse / Thrust':'Amplifies vertical acceleration - higher damage per magnitude unit.','Normal':'Lower near-field ground acceleration than thrust faults.','Oblique Reverse':'Mixed compressional - near-thrust characteristics.','Oblique Normal':'Mixed extensional - moderate near-field shaking.'}[t] || ''; }
function probColor(p) { var v = parseFloat(String(p).replace(/[%>~]/g, '')); return isNaN(v) ? '#888' : v >= 50 ? '#d32f2f' : v >= 20 ? '#e65100' : '#2e7d32'; }

// ── Event selection ───────────────────────────────────────────────────────────

function setActive(id) {
  document.querySelectorAll('.ev-item').forEach(function (el) {
    var on = el.dataset.id === id;
    el.style.background = on ? '#e8f0fe' : '';
    el.style.borderLeft = on ? '3px solid #1565c0' : '3px solid transparent';
  });
}

function loadEvent(id) {
  setActive(id);
  var found = null;
  for (var i = 0; i < ALL_DATA.length; i++) {
    if (ALL_DATA[i] && ALL_DATA[i].ev.event_id === id) { found = ALL_DATA[i]; break; }
  }
  if (!found) {
    // Fallback 1: ids can differ only by catalog prefix (us6000t7zc vs 6000t7zc).
    for (var j = 0; j < ALL_DATA.length; j++) {
      var eid2 = ALL_DATA[j] && ALL_DATA[j].ev.event_id;
      if (eid2 && (id.indexOf(eid2) !== -1 || eid2.indexOf(id) !== -1)) { found = ALL_DATA[j]; break; }
    }
  }
  if (!found) {
    // Fallback 2: match by sidebar position (sidebar and ALL_DATA share order).
    var items = Array.prototype.slice.call(document.querySelectorAll('.ev-item'));
    var pos = items.findIndex(function (el) { return el.dataset.id === id; });
    if (pos >= 0 && ALL_DATA[pos]) found = ALL_DATA[pos];
  }
  if (!found) {
    document.getElementById('rp-inner').innerHTML =
      '<div style="padding:40px;color:#888;text-align:center">No data for event: ' + esc(id) + '</div>';
    return;
  }
  _current = found;
  document.querySelector('.rp').scrollTo(0, 0);
  document.getElementById('rp-inner').innerHTML = buildReport(found);
  setTimeout(initMap, 100);
}

// ── HTML building blocks ──────────────────────────────────────────────────────

function mbox(label, val, sub, color) {
  return '<div style="background:rgba(255,255,255,.85);border:1px solid ' + (color || '#e2e6f0') + '40;border-radius:10px;padding:14px 16px;text-align:center">'
    + '<div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px">' + label + '</div>'
    + '<div style="font-size:26px;font-weight:900;color:' + (color || '#1a1f36') + ';line-height:1">' + val + '</div>'
    + (sub ? '<div style="font-size:11px;color:#64748b;margin-top:5px">' + sub + '</div>' : '')
    + '</div>';
}

function kv(k, v, c) {
  return '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
    + '<span style="color:#64748b">' + k + '</span>'
    + '<span style="font-weight:600;text-align:right;max-width:60%;' + (c ? 'color:' + c + ';' : '') + '">' + (v || 'n/a') + '</span>'
    + '</div>';
}

function panel(title, body) {
  return '<div style="background:#fff;border:1px solid #e2e6f0;border-radius:12px;padding:16px 18px">'
    + '<div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e6f0">' + title + '</div>'
    + body + '</div>';
}

function linkBtn(label, url) {
  url = safeUrl(url);
  if (!url) return '';
  return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" style="padding:4px 11px;border-radius:6px;font-size:10px;font-weight:600;color:#1565c0;border:1px solid #e2e6f0;background:#f8f9fc;text-decoration:none;display:inline-block;margin-right:4px;margin-bottom:4px">' + esc(label) + '</a>';
}

// ── Report builder ────────────────────────────────────────────────────────────

function buildReport(data) {
  var ev  = data.ev;
  var sm  = data.sm || {};
  var afs = data.aftershock;
  var foc = data.focal;
  var his = data.historical || [];
  var wea = data.weather;
  var bld = data.building;
  var nws = data.news || [];
  var nar = data.narrative;

  var mmi  = parseFloat(ev.mmi)   || 0;
  var mag  = parseFloat(ev.mag)   || 0;
  var dep  = parseFloat(ev.depth) || 0;
  var ac   = ev.alert_color || '#78909c';
  var mc   = MMI_COLORS[Math.round(mmi) - 1] || '#ccc';
  var pga  = mmiToPga(mmi);
  var pgaC = pgaColor(pga);
  var pgaF = pgaConvert(pga);
  var pgaL = pgaLabel(pga);
  var dn   = ev.depth_note || (dep > 300 ? 'Deep focus' : dep > 70 ? 'Intermediate' : dep > 30 ? 'Shallow' : 'Very shallow');
  var mmiNames = {1:'Not felt',2:'Scarcely felt',3:'Weak',4:'Light',5:'Moderate',
                  6:'Strong',7:'Very Strong',8:'Severe',9:'Violent',10:'Extreme'};
  var mmiDesc  = mmiNames[Math.round(mmi)] || ev.mmi_desc || '';
  var eid      = ev.event_id;
  var pagerTxt = PAGER_DESC[ev.pager_alert] || '';

  // ── Hero ──
  var heroH =
    (ev.tsunami ? '<div style="background:#4a148c;color:#fff;border-radius:10px;padding:8px 16px;margin-bottom:10px;font-weight:700;font-size:12px">TSUNAMI WARNING</div>' : '')
    + (nar ? '<div style="background:#f0f4ff;border:1px solid #c7d7f5;border-radius:12px;padding:14px 18px;margin-bottom:12px;font-size:13px;line-height:1.75;color:#1e2d5a">'
           + '<div style="font-size:9px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">AI Assessment</div>' + esc(nar) + '</div>' : '')
    + '<div style="border-left:5px solid ' + ac + ';padding:20px 22px;margin-bottom:12px;background:linear-gradient(135deg,' + ac + '0a,transparent);border:1px solid ' + ac + '30;border-radius:12px">'
    + '<div style="display:flex;align-items:flex-start;gap:20px;margin-bottom:16px;flex-wrap:wrap">'
    + '<div style="font-size:72px;font-weight:900;line-height:1;color:' + ac + ';letter-spacing:-2px">M' + mag.toFixed(1) + '</div>'
    + '<div style="flex:1;min-width:220px">'
    + '<div style="font-size:20px;font-weight:700;margin-bottom:3px">' + esc(ev.place) + '</div>'
    + '<div style="font-size:11px;color:#64748b;margin-bottom:10px">' + esc(ev.t_str) + ' \u2022 ' + esc(ev.t_age_str) + '</div>'
    + '<span style="padding:4px 12px;border-radius:5px;font-size:11px;font-weight:700;text-transform:uppercase;background:' + ac + ';color:#fff">' + esc(ev.alert_lbl) + '</span>'
    + (pagerTxt ? '<span style="font-size:11px;color:#64748b;margin-left:8px">' + esc(pagerTxt) + '</span>' : '')
    + '</div></div>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">'
    + mbox('MMI Intensity', mmi ? mmi.toFixed(1) : '--', esc(mmiDesc), mc)
    + mbox('Peak Ground Accel.', pga ? pgaF.g : '--', pga ? pgaF.ms2 + ' \u2022 ' + pgaL : '', pgaC)
    + mbox('Depth', dep.toFixed(0) + ' km', esc(dn), '#1565c0')
    + '</div></div>';

  // ── Map ── (data is passed via _current, not DOM attributes)
  var mapH =
    '<div id="map-section" style="margin-bottom:12px">'
    + '<div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px">ShakeMap Ground Motion - PGA / MMI / Satellite</div>'
    + '<div style="position:relative;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.08)">'
    + '<div style="position:absolute;top:10px;right:10px;z-index:1000;display:flex;gap:5px;background:rgba(255,255,255,.97);padding:5px 7px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.12)">'
    + '<button id="btn-pga" data-layer="pga" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">PGA</button>'
    + '<button id="btn-mmi" data-layer="mmi" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">MMI</button>'
    + '<button id="btn-sat" data-layer="sat" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">Satellite</button>'
    + '</div>'
    + '<div id="leaflet-map" style="width:100%;height:500px;background:#eef1f6"></div>'
    + '</div></div>';

  // ── Intelligence and News ──
  var newsH = '';
  for (var ni = 0; ni < nws.length; ni++) {
    var n    = nws[ni];
    var nurl = safeUrl(n.url);
    var ntitle = nurl
      ? '<a href="' + esc(nurl) + '" target="_blank" rel="noopener noreferrer" style="color:#1a1f36;font-weight:600;text-decoration:none">' + esc(n.headline) + '</a>'
      : '<b>' + esc(n.headline) + '</b>';
    var nsumm = n.summary
      ? '<div style="font-size:11px;color:#64748b;margin-top:2px">' + esc(n.summary) + '</div>'
      : '';
    newsH += '<div style="padding:8px 0;border-bottom:1px solid #e2e6f0">'
      + '<div style="font-size:9px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">' + esc(n.source) + '</div>'
      + ntitle + nsumm
      + '</div>';
  }
  var newsPanel = newsH
    ? '<div style="margin-bottom:12px">' + panel('Intelligence and News', newsH) + '</div>'
    : '';

  // ── Event Parameters ──
  var ft = foc && foc.type ? foc.type : 'Pending';
  var paramsH =
    '<div style="font-size:12px">'
    + kv('Coordinates', coordStr(ev.lat, ev.lon))
    + kv('Tectonic', esc(ev.tectonic) || '--')
    + kv('Fault Type', esc(ft))
    + kv('Energy', ev.energy_mt ? ev.energy_mt.toFixed(3) + ' MT TNT' : 'n/a')
    + kv('Rupture Est.', ev.rupture_km ? '~' + Number(ev.rupture_km).toFixed(0) + ' km' : 'n/a')
    + '</div>'
    + '<div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:10px">'
    + linkBtn('USGS Event',      safeUrl(ev.url) || 'https://earthquake.usgs.gov/earthquakes/eventpage/' + encodeURIComponent(eid))
    + linkBtn('ShakeMap',        'https://earthquake.usgs.gov/earthquakes/eventpage/' + encodeURIComponent(eid) + '/shakemap')
    + linkBtn('PAGER',           'https://earthquake.usgs.gov/earthquakes/eventpage/' + encodeURIComponent(eid) + '/pager')
    + linkBtn('Focal Mechanism', 'https://earthquake.usgs.gov/earthquakes/eventpage/' + encodeURIComponent(eid) + '/moment-tensor')
    + linkBtn('EU Civil Protection', 'https://erccportal.jrc.ec.europa.eu/ECHO-Products/Maps')
    + '</div>';

  // ── Aftershock forecast ──
  var afsH = '<div style="font-size:12px;color:#888">Not yet published</div>';
  if (afs && afs.bins && afs.bins.length) {
    var afsRows = '';
    for (var ai = 0; ai < afs.bins.length; ai++) {
      var b = afs.bins[ai];
      afsRows += '<tr>'
        + '<td style="padding:5px 6px;font-weight:700">M' + esc(b.mag) + '+</td>'
        + '<td style="padding:5px 6px;color:' + probColor(b.p_1day) + ';font-weight:700">' + esc(b.p_1day) + '</td>'
        + '<td style="padding:5px 6px;color:' + probColor(b.p_1week) + ';font-weight:700">' + esc(b.p_1week) + '</td>'
        + '<td style="padding:5px 6px;color:' + probColor(b.p_1month) + ';font-weight:700">' + esc(b.p_1month) + '</td>'
        + '<td style="padding:5px 6px;color:#888">' + esc(b.n_1week) + '</td>'
        + '</tr>';
    }
    afsH = '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      + '<tr style="font-size:9px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e6f0">'
      + '<th style="text-align:left;padding:4px 6px">Mag.</th>'
      + '<th style="text-align:left;padding:4px 6px">1 Day</th>'
      + '<th style="text-align:left;padding:4px 6px">1 Week</th>'
      + '<th style="text-align:left;padding:4px 6px">1 Month</th>'
      + '<th style="text-align:left;padding:4px 6px">Est. n(wk)</th>'
      + '</tr>' + afsRows + '</table>'
      + '<div style="font-size:9px;color:#aaa;margin-top:6px">Model: ' + esc(afs.model || 'Reasenberg-Jones') + '</div>';
  }

  // ── Fault mechanism ──
  var focH = '<div style="font-size:12px;color:#888">Moment tensor solution pending</div>';
  if (foc && foc.type) {
    var fc2 = faultColor(foc.type);
    focH = '<span style="display:inline-block;padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;background:' + fc2 + '18;border:1px solid ' + fc2 + '44;color:' + fc2 + ';margin-bottom:8px">' + esc(foc.type) + '</span>'
      + (foc.strike ? '<div style="font-size:11px;color:#64748b;margin-bottom:5px">Strike ' + esc(foc.strike) + '\u00b0 / Dip ' + esc(foc.dip) + '\u00b0 / Rake ' + esc(foc.rake) + '\u00b0</div>' : '')
      + '<div style="font-size:11px;color:#64748b">' + faultNote(foc.type) + '</div>';
  }

  // ── Historical context ──
  var histH = '<div style="font-size:12px;color:#888">No M5.5+ events found within 250 km</div>';
  if (his && his.length) {
    var histRows = '';
    var maxMag = Math.max.apply(null, his.map(function (h) { return h.mag || 0; }));
    for (var hi = 0; hi < his.length; hi++) {
      var hev  = his[hi];
      var hurl = safeUrl(hev.url);
      var hl   = hurl
        ? '<a href="' + esc(hurl) + '" target="_blank" rel="noopener noreferrer" style="color:#1565c0;text-decoration:none">M' + esc(hev.mag) + '</a>'
        : 'M' + esc(hev.mag);
      histRows += '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
        + '<span>' + hl + ' - ' + esc(hev.place) + '</span><span style="color:#888">' + esc(hev.year) + '</span>'
        + '</div>';
    }
    histH = histRows
      + '<div style="font-size:10px;color:#888;margin-top:6px;font-style:italic">'
      + (mag >= maxMag ? 'Largest event on record in this region' : 'Comparable events have occurred in this region')
      + '</div>';
  }

  // ── Secondary hazards and building stock ──
  var hazH = '<div style="font-size:12px;color:#888">No data available</div>';
  if (wea || bld) {
    hazH = '';
    if (wea) {
      var rc  = wea.landslide_risk === 'High' ? '#d32f2f' : wea.landslide_risk === 'Moderate' ? '#e65100' : '#2e7d32';
      var pct = Math.min(100, (wea.precip_3day_mm || 0) / 100 * 100);
      hazH += '<div style="margin-bottom:12px">'
        + '<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:5px">Secondary Hazard</div>'
        + '<div style="font-size:12px;margin-bottom:4px">Rainfall (last 3 days): <b>' + esc(wea.precip_3day_mm) + ' mm</b>'
        + (wea.temp_c != null ? ' \u2022 Current temp: <b>' + esc(wea.temp_c) + ' \u00b0C</b>' : '') + '</div>'
        + '<div style="height:6px;background:#e2e6f0;border-radius:3px;margin-bottom:5px">'
        + '<div style="width:' + pct.toFixed(0) + '%;height:100%;background:' + rc + ';border-radius:3px"></div></div>'
        + '<span style="display:inline-block;padding:3px 12px;border-radius:20px;font-size:11px;font-weight:700;background:' + rc + '18;border:1px solid ' + rc + '44;color:' + rc + '">Landslide: ' + esc(wea.landslide_risk) + ' Risk</span>'
        + '</div>';
    }
    if (bld) {
      var vuln = bld.vulnerability || 'Unknown';
      var vulnColors = {'Very High':'#d32f2f','High':'#e65100','Moderate':'#f9a825','Low-Moderate':'#2e7d32','Low':'#1b5e20','Unknown':'#90a4ae'};
      var vulnPct    = {'Very High':88,'High':68,'Moderate':48,'Low-Moderate':30,'Low':15,'Unknown':5};
      var vc   = vulnColors[vuln] || '#90a4ae';
      var vpct = vulnPct[vuln]    || 5;
      hazH += '<div style="border-top:' + (wea ? '1px solid #e2e6f0' : 'none') + ';padding-top:' + (wea ? '12px' : '0') + '">'
        + '<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:5px">Building Stock</div>'
        + '<div style="height:6px;background:#e2e6f0;border-radius:3px;margin-bottom:5px">'
        + '<div style="width:' + vpct + '%;height:100%;background:' + vc + ';border-radius:3px"></div></div>'
        + '<div style="font-size:12px;font-weight:700;color:' + vc + ';margin-bottom:3px">' + esc(vuln) + ' Vulnerability</div>'
        + '<div style="font-size:11px;color:#64748b;margin-bottom:2px">' + esc(bld.dominant || '') + '</div>'
        + '<div style="font-size:10px;color:#888">' + esc(bld.code_era || '') + '</div>'
        + '</div>';
    }
  }

  // ── Assemble ──
  var g2 = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-bottom:12px';
  return heroH + mapH
    + newsPanel
    + '<div style="' + g2 + '">' + panel('Event Parameters', paramsH) + panel('Aftershock Forecast', afsH) + '</div>'
    + '<div style="' + g2 + '">' + panel('Fault Mechanism', focH) + panel('Historical Context (250 km / 100 yr)', histH) + '</div>'
    + '<div style="' + g2 + '">' + panel('Secondary Hazards and Building Stock', hazH) + '<div></div></div>'
    + '<div style="font-size:10px;color:#aaa;padding-top:6px;border-top:1px solid #e2e6f0">'
    + 'Sources: USGS NEIC / PAGER / ShakeMap / GDACS / GEM / ReliefWeb / Open-Meteo | Preliminary assessment only'
    + '</div>';
}

// ── Map ───────────────────────────────────────────────────────────────────────

function initMap() {
  var el = document.getElementById('leaflet-map');
  if (!el || !_current) return;

  // Leaflet is loaded from a CDN; degrade gracefully when offline.
  if (typeof L === 'undefined') {
    el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:12px;text-align:center;padding:20px">'
      + 'Map unavailable (Leaflet CDN not reachable).<br>Event data below is unaffected.</div>';
    return;
  }

  var ev     = _current.ev;
  var sm     = _current.sm || {};
  var lat    = ev.lat, lon = ev.lon;
  var color  = ev.alert_color || '#78909c';
  var mmiUrl = safeUrl(sm.mmi_url);
  var pgaUrl = safeUrl(sm.pga_url);

  if (_map) { _map.remove(); _map = null; }
  _active = null; _pga = null; _mmi = null; _base = null; _sat = null; _satOn = false;

  _map = L.map('leaflet-map', { zoomControl: false }).setView([lat, lon], 7);
  L.control.zoom({ position: 'bottomright' }).addTo(_map);
  _base = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { attribution: 'OpenStreetMap contributors', maxZoom: 19 });
  _base.addTo(_map);

  L.circle([lat, lon], { radius: 5000, color: color, fillColor: color, fillOpacity: .4, weight: 3, interactive: false }).addTo(_map);
  L.circleMarker([lat, lon], { radius: 10, color: '#fff', fillColor: color, fillOpacity: 1, weight: 2.5 })
    .addTo(_map)
    .bindPopup('<b>Epicentre</b><br>M' + Number(ev.mag).toFixed(1) + ' - ' + esc(ev.place) + '<br>' + esc(ev.t_str))
    .openPopup();

  ['btn-pga', 'btn-mmi', 'btn-sat'].forEach(function (id) {
    var btn = document.getElementById(id);
    if (!btn) return;
    btn.onclick = function () {
      var layer = this.dataset.layer;
      if (layer === 'sat') toggleSat(); else setLayer(layer);
    };
  });

  if (!pgaUrl && !mmiUrl) {
    // No ShakeMap yet: indicative shaking rings.
    [{ r: 60000, op: .18 }, { r: 180000, op: .10 }, { r: 400000, op: .05 }].forEach(function (rg) {
      L.circle([lat, lon], { radius: rg.r, color: color, fillColor: color, fillOpacity: rg.op, weight: 1, dashArray: '5 3' }).addTo(_map);
    });
  }
  if (pgaUrl) {
    fetch(pgaUrl).then(function (r) { return r.json(); }).then(function (d) {
      _pga = L.geoJSON(d, {
        style: function (f) { return { color: f.properties.color || '#999', weight: 2.5, opacity: .95 }; },
        onEachFeature: function (f, l) {
          var fmt = pgaConvert(f.properties.value);
          l.bindTooltip('<b>PGA: ' + fmt.g + ' / ' + fmt.ms2 + '</b>', { sticky: true });
        }
      });
      setLayer('pga');
    }).catch(function () {});
  }
  if (mmiUrl) {
    fetch(mmiUrl).then(function (r) { return r.json(); }).then(function (d) {
      _mmi = L.geoJSON(d, {
        style: function (f) { return { color: f.properties.color || '#999', weight: 2.5, opacity: .95 }; },
        onEachFeature: function (f, l) { l.bindTooltip('<b>MMI ' + esc(f.properties.value) + '</b>', { sticky: true }); }
      });
      if (!pgaUrl) setLayer('mmi');
    }).catch(function () {});
  }
}

function setLayer(type) {
  if (!_map) return;
  if (_active) { _map.removeLayer(_active); _active = null; }
  ['pga', 'mmi'].forEach(function (k) {
    var b = document.getElementById('btn-' + k);
    if (b) { b.style.background = (k === type) ? '#1565c0' : '#e8eaf0'; b.style.color = (k === type) ? '#fff' : '#555'; }
  });
  var layers = { pga: _pga, mmi: _mmi };
  if (layers[type]) { layers[type].addTo(_map); _active = layers[type]; }
}

function toggleSat() {
  if (!_map) return;
  var btn = document.getElementById('btn-sat');
  _satOn = !_satOn;
  if (_satOn) {
    if (_base) _map.removeLayer(_base);
    if (!_sat) _sat = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: 'Esri World Imagery', maxZoom: 19 });
    _sat.addTo(_map);
    if (_active) { _map.removeLayer(_active); _active.addTo(_map); }
    if (btn) { btn.style.background = '#1565c0'; btn.style.color = '#fff'; }
  } else {
    if (_sat)  _map.removeLayer(_sat);
    if (_base) _base.addTo(_map);
    if (_active) { _map.removeLayer(_active); _active.addTo(_map); }
    if (btn) { btn.style.background = '#e8eaf0'; btn.style.color = '#555'; }
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
  // Sidebar clicks via delegation (no inline onclick, no quoting issues).
  var list = document.querySelector('.sb-list');
  if (list) {
    list.addEventListener('click', function (e) {
      var item = e.target.closest('.ev-item');
      if (item && item.dataset.id) loadEvent(item.dataset.id);
    });
  }
  var startId = FIRST_ID || (ALL_DATA.length ? ALL_DATA[0].ev.event_id : null);
  if (startId) loadEvent(startId);
});
