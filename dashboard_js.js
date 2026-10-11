/* dashboard_js.js - Client-side report renderer.
 * Single source of truth for the dashboard JS: dashboard.py reads this file at
 * build time and injects data via the __PLACEHOLDER__ tokens below.
 * Do not rename the placeholders.
 *
 * Every number shown here is a value published by USGS (or another named source) and is passed
 * through unchanged. Nothing is estimated in the browser. Units: intensity in MMI, PGA and
 * spectral acceleration in g, velocity in cm/s, distances in km. */

var ALL_DATA         = __ALL_DATA__;
var FIRST_ID         = __FIRST_ID__;
var MMI_COLORS       = __MMI_COLORS__;
var MMI_SCALE        = __MMI_SCALE__;
var ALERT_C          = __ALERT_C__;
var PAGER_THRESHOLDS = __PAGER_THRESHOLDS__;

var _map = null, _active = null, _pga = null, _mmi = null,
    _base = null, _sat = null, _satOn = false, _current = null, _legend = null, _fitted = false;

// ── Generic helpers ───────────────────────────────────────────────────────────

// Escape any dynamic string before inserting it into HTML (place names and link titles
// come from external services and must not be trusted).
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
  return Math.abs(lat).toFixed(3) + '° ' + (lat >= 0 ? 'N' : 'S') + '  '
       + Math.abs(lon).toFixed(3) + '° ' + (lon >= 0 ? 'E' : 'W');
}

function fmtNum(n) { return Number(n).toLocaleString('en-US'); }

// Population figures are model estimates, so they are rounded rather than shown to the person.
function fmtPeople(n) {
  n = Number(n) || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, '') + ' million';
  if (n >= 1e3) return fmtNum(Math.round(n / 1e3) * 1e3);
  return fmtNum(Math.round(n));
}

function fmtProb(p) {
  if (p == null) return '–';
  if (p >= 0.995) return '>99%';
  if (p < 0.01) return '<1%';
  return Math.round(p * 100) + '%';
}
function probColor(p) { return p == null ? '#888' : p >= 0.5 ? '#d32f2f' : p >= 0.2 ? '#e65100' : '#2e7d32'; }

function fmtG(v) {
  if (v == null) return 'n/a';
  return (v < 0.1 ? v.toFixed(3) : v.toFixed(2)) + ' g';
}

function ageText(ms) {
  if (!ms) return '';
  var h = (Date.now() - ms) / 36e5;
  if (h < 0) return '';
  if (h < 1) return Math.max(1, Math.round(h * 60)) + ' min ago';
  if (h < 48) return Math.floor(h) + 'h ' + Math.floor((h % 1) * 60) + 'm ago';
  return Math.floor(h / 24) + 'd ago';
}

function toRoman(n) {
  var r = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
  return r[Math.max(0, Math.min(10, Math.round(n)))] || '';
}

// "10 to 100" fatalities from a PAGER probability bin (the bins are order-of-magnitude ranges).
function fatalityRange(top) {
  if (!top) return '';
  if (top.max != null && top.max <= 1) return 'fewer than 1 fatality';
  return fmtNum(top.min) + ' to ' + fmtNum(top.max) + ' fatalities';
}
// PAGER economic bins are in millions of US dollars.
function usdWords(m) { return m >= 1000 ? (m / 1000) + ' billion' : m + ' million'; }
function lossRange(top) {
  if (!top) return '';
  if (top.max != null && top.max <= 1) return 'under US$1 million';
  if (top.min >= 1000) return 'US$' + (top.min / 1000) + ' to ' + (top.max / 1000) + ' billion';
  if (top.max <= 1000) return 'US$' + top.min + ' to ' + top.max + ' million';
  return 'US$' + usdWords(top.min) + ' to ' + usdWords(top.max);
}

function lvlColor(level) { return ALERT_C[String(level || '').toUpperCase()] || '#78909c'; }
function lvlChip(level, label) {
  var c = lvlColor(level), lv = String(level || '').toLowerCase();
  var fg = lv === 'yellow' ? '#10151f' : '#fff';   // dark text only on yellow; the Sentinel theme darkens all chip text
  return '<span class="lvl-chip lvl-' + esc(lv) + '" style="display:inline-block;padding:2px 9px;border-radius:5px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.4px;background:' + c + ';color:' + fg + '"'
    + (PAGER_THRESHOLDS[String(level || '').toUpperCase()] ? ' title="' + esc(label || '') + '"' : '') + '>' + esc(level || 'n/a') + '</span>';
}

// ── Seismology display helpers ────────────────────────────────────────────────

function faultColor(t) { return {'Strike-Slip':'#1565c0','Reverse / Thrust':'#d32f2f','Normal':'#e65100','Oblique Reverse':'#6a1b9a','Oblique Normal':'#00695c'}[t] || '#555'; }

// Plain description of what a nodal plane is doing (rake: 0 left-lateral, +/-180 right-lateral, +90 reverse, -90 normal).
function planeSense(p) {
  if (!p) return '';
  var s = p.style, l = p.sense ? p.sense.toLowerCase() : '';
  if (s === 'Strike-Slip') return l + ' strike-slip';
  if (s === 'Reverse / Thrust') return 'reverse (thrust)';
  if (s === 'Normal') return 'normal';
  if (s === 'Oblique Reverse') return 'reverse with ' + l + ' component';
  if (s === 'Oblique Normal') return 'normal with ' + l + ' component';
  return '';
}
function faultNote(t) {
  return {
    'Strike-Slip': 'The two sides of the fault slide horizontally past each other.',
    'Reverse / Thrust': 'The hanging wall moves up and over the footwall (crust is shortened); typical of subduction zones and collision belts.',
    'Normal': 'The hanging wall moves down relative to the footwall (crust is extended).',
    'Oblique Reverse': 'Reverse slip combined with horizontal (strike-slip) motion.',
    'Oblique Normal': 'Normal slip combined with horizontal (strike-slip) motion.'
  }[t] || '';
}

function mmiRef(mmi) {
  if (!mmi) return null;
  return MMI_SCALE[String(Math.max(1, Math.min(10, Math.round(mmi))))] || null;   // [roman, shaking, damage, colour, pga %g, pgv cm/s]
}

// ── Event selection ───────────────────────────────────────────────────────────

function setActive(id) {
  document.querySelectorAll('.ev-item').forEach(function (el) {
    var on = el.dataset.id === id;
    el.classList.toggle('ev-sel', on);
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
  refreshAges();
  setTimeout(initMap, 100);
}

// Ages are computed in the browser so they stay correct however long the page stays open.
function refreshAges() {
  document.querySelectorAll('.ev-age, .hero-age').forEach(function (el) {
    var t = Number(el.dataset.t);
    if (t) el.textContent = ageText(t);
  });
}

// ── HTML building blocks ──────────────────────────────────────────────────────

function mbox(label, val, sub, color) {
  return '<div class="mbox" style="background:rgba(255,255,255,.85);border:1px solid ' + (color || '#e2e6f0') + '40;border-radius:10px;padding:14px 16px;text-align:center">'
    + '<div class="mbox-l" style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px">' + label + '</div>'
    + '<div class="mbox-v" style="font-size:26px;font-weight:900;color:' + (color || '#1a1f36') + ';line-height:1">' + val + '</div>'
    + (sub ? '<div class="mbox-s" style="font-size:11px;color:#64748b;margin-top:5px">' + sub + '</div>' : '')
    + '</div>';
}

function kv(k, v, c) {
  return '<div class="sx-kv" style="display:flex;justify-content:space-between;gap:14px;padding:5px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
    + '<span style="color:#64748b;flex:0 0 auto">' + k + '</span>'
    + '<span style="font-weight:600;text-align:right;' + (c ? 'color:' + c + ';' : '') + '">' + (v || 'n/a') + '</span>'
    + '</div>';
}

function panel(title, body) {
  return '<div class="sx-panel" style="background:#fff;border:1px solid #e2e6f0;border-radius:12px;padding:16px 18px">'
    + '<div class="sx-panel-t" style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e6f0">' + title + '</div>'
    + body + '</div>';
}

function note(t) { return '<div style="font-size:10px;color:#888;margin-top:8px;line-height:1.5">' + t + '</div>'; }
function empty(t) { return '<div style="font-size:12px;color:#888">' + t + '</div>'; }

function linkBtn(label, url) {
  url = safeUrl(url);
  if (!url) return '';
  return '<a class="sx-chip" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" style="padding:4px 11px;border-radius:6px;font-size:10px;font-weight:600;color:#1565c0;border:1px solid #e2e6f0;background:#f8f9fc;text-decoration:none;display:inline-block;margin-right:4px;margin-bottom:4px">' + esc(label) + '</a>';
}

// One row of the Media / General link lists: a short title, nothing else.
var EXT_ICON = '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:0 0 auto;opacity:.55"><path d="M7 17L17 7M8 7h9v9"/></svg>';
function linkRow(lead, title, url, muted) {
  url = safeUrl(url);
  if (!url) return '';
  return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:baseline;gap:8px;padding:7px 0;border-bottom:1px solid #e2e6f0;text-decoration:none;font-size:12.5px;line-height:1.4;color:' + (muted ? '#64748b' : '#1a1f36') + '">'
    + (lead ? '<span style="flex:0 0 auto;font-size:9.5px;font-weight:800;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;min-width:64px">' + esc(lead) + '</span>' : '')
    + '<span style="flex:1;min-width:0;font-weight:' + (muted ? '500' : '600') + '">' + esc(title) + '</span>' + EXT_ICON + '</a>';
}

// ── Report builder ────────────────────────────────────────────────────────────

function buildReport(data) {
  var ev  = data.ev;

  if (data.data_unavailable) {
    return '<div style="padding:16px 0">'
      + panel('Data unavailable', ''
        + '<div style="font-size:13px;color:#374151;line-height:1.6;margin-bottom:10px">'
        + 'The detailed USGS record for this event did not respond, so the ShakeMap, PAGER estimate, mechanism and aftershock forecast could not be loaded. '
        + 'Only the basic summary below is confirmed from the USGS earthquake feed.'
        + '</div>'
        + kv('Magnitude', 'M' + (ev.mag || 'n/a'))
        + kv('Location', esc(ev.place || 'n/a'))
        + kv('Time', esc(ev.t_str || 'n/a'))
        + kv('Depth', ev.depth != null ? Number(ev.depth).toFixed(1) + ' km' : 'n/a')
        + (ev.url ? '<div style="margin-top:10px">' + linkBtn('View on USGS', ev.url) + '</div>' : ''))
      + '</div>';
  }

  var sm   = data.sm || {};
  var peak = sm.peak || null;
  var pg   = data.pager || null;
  var gf   = data.ground_failure || null;
  var org  = data.origin || null;
  var ff   = data.finite_fault || null;
  var foc  = data.focal || null;
  var afs  = data.aftershock || null;
  var his  = data.historical || [];
  var wea  = data.weather || null;
  var txt  = data.summary || null;
  var nar  = data.narrative || null;

  var mag  = parseFloat(ev.mag) || 0;
  var dep  = parseFloat(ev.depth) || 0;
  var ac   = ev.alert_color || '#78909c';
  var mmi  = (peak && peak.mmi) || parseFloat(ev.mmi) || 0;     // ShakeMap maximum intensity
  var ref  = mmiRef(mmi);
  var mc   = (ref && ref[3]) || '#ccc';
  var eid  = ev.event_id;
  var base = safeUrl(ev.url) || 'https://earthquake.usgs.gov/earthquakes/eventpage/' + encodeURIComponent(eid);

  // ── Tsunami notice (the USGS tsunami flag does not confirm a tsunami) ──
  var tsuH = ev.tsunami
    ? '<div style="background:#4a148c;color:#fff;border-radius:10px;padding:9px 16px;margin-bottom:10px;font-size:12px;line-height:1.5">'
      + '<b>Tsunami flag set by USGS.</b> This marks a large earthquake in an oceanic region and does not confirm a tsunami. '
      + 'Official messages: <a href="https://www.tsunami.gov" target="_blank" rel="noopener noreferrer" style="color:#fff;font-weight:700">tsunami.gov</a>.</div>'
    : '';

  // ── Hero ──
  var pagerRow;
  if (pg && (pg.fatality || pg.economic)) {
    pagerRow = '<span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.6px;margin-right:2px">USGS PAGER</span>'
      + (pg.fatality ? '<span style="font-size:11px;color:#64748b">Fatalities</span> ' + lvlChip(pg.fatality.level, 'Fatalities: ' + ((PAGER_THRESHOLDS[String(pg.fatality.level).toUpperCase()] || {}).fatalities || '')) : '')
      + (pg.economic ? '<span style="font-size:11px;color:#64748b;margin-left:6px">Economic</span> ' + lvlChip(pg.economic.level, 'Losses: ' + ((PAGER_THRESHOLDS[String(pg.economic.level).toUpperCase()] || {}).losses || '')) : '');
  } else if (ev.pager_alert) {
    pagerRow = '<span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.6px;margin-right:2px">USGS PAGER</span> ' + lvlChip(ev.pager_alert, '');
  } else {
    pagerRow = '<span style="font-size:11px;color:#64748b">USGS PAGER impact estimate not yet issued</span>';
  }
  var statusChip = ev.status === 'reviewed'
    ? '<span style="font-size:10px;font-weight:700;color:#2e7d32;border:1px solid #2e7d3255;border-radius:10px;padding:1px 8px">USGS reviewed</span>'
    : '<span style="font-size:10px;font-weight:700;color:#b45309;border:1px solid #b4530955;border-radius:10px;padding:1px 8px" title="Automatic solution: values can change as USGS reviews the event">Automatic solution</span>';

  var heroH =
    tsuH
    + (nar ? '<div style="background:#f0f4ff;border:1px solid #c7d7f5;border-radius:12px;padding:14px 18px;margin-bottom:12px;font-size:13px;line-height:1.75;color:#1e2d5a">'
           + '<div style="font-size:9px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">AI Assessment</div>' + esc(nar) + '</div>' : '')
    + '<div class="hero-card" style="border-left:5px solid ' + ac + ';padding:20px 22px;margin-bottom:12px;background:linear-gradient(135deg,' + ac + '0a,transparent);border:1px solid ' + ac + '30;border-radius:12px">'
    + '<div class="hero-row" style="display:flex;align-items:flex-start;gap:20px;margin-bottom:16px;flex-wrap:wrap">'
    + '<div class="hero-mag" style="font-size:72px;font-weight:900;line-height:1;color:' + ac + ';letter-spacing:-2px" title="' + esc(ev.mag_type ? 'Magnitude type: ' + ev.mag_type : '') + '">M' + mag.toFixed(1) + '</div>'
    + '<div class="hero-main" style="flex:1;min-width:220px">'
    + '<div style="font-size:20px;font-weight:700;margin-bottom:3px">' + esc(ev.place) + '</div>'
    + '<div style="font-size:11px;color:#64748b;margin-bottom:10px">' + esc(ev.t_str) + ' • <span class="hero-age" data-t="' + esc(ev.t_ms) + '"></span> • ' + statusChip + '</div>'
    + '<div class="hero-alert" style="display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px">' + pagerRow + '</div>'
    + '</div></div>'
    + '<div class="mbox-row" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">'
    + mbox('Shaking intensity', ref ? ref[0] : '--', ref ? 'MMI ' + mmi.toFixed(1) + ' · ' + esc(ref[1]) : 'ShakeMap pending', mc)
    + mbox('Peak ground accel.', peak && peak.pga_g != null ? fmtG(peak.pga_g) : '--', peak && peak.pgv_cms != null ? 'PGV ' + peak.pgv_cms.toFixed(0) + ' cm/s' : 'ShakeMap pending', '#1565c0')
    + mbox('Depth', dep.toFixed(0) + ' km', esc((ev.depth_note || '').split(' (')[0]), '#1565c0')
    + '</div></div>';

  // ── Map ── (data is passed via _current, not DOM attributes)
  var mapH =
    '<div id="map-section" style="margin-bottom:12px">'
    + '<div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px">ShakeMap ground motion - PGA / MMI contours</div>'
    + '<div style="position:relative;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.08)">'
    + '<div style="position:absolute;top:10px;right:10px;z-index:1000;display:flex;gap:5px;background:rgba(255,255,255,.97);padding:5px 7px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.12)">'
    + '<button id="btn-pga" data-layer="pga" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">PGA</button>'
    + '<button id="btn-mmi" data-layer="mmi" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">MMI</button>'
    + '<button id="btn-sat" data-layer="sat" style="padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:11px;font-weight:700;background:#e8eaf0;color:#555">Satellite</button>'
    + '</div>'
    + '<div id="leaflet-map" style="width:100%;height:500px;background:#eef1f6"></div>'
    + '</div>'
    + ((typeof L !== 'undefined' && L.Browser.mobile) ? '<div style="font-size:11px;color:#64748b;margin-top:6px">Pinch or use + / - to zoom the map; scroll the page with one finger.</div>' : '')
    + '</div>';

  // ── Media and General: links only, one short title each ──
  var media = data.media || [], general = data.general || [];
  var mediaRows = '';
  media.forEach(function (m) {
    mediaRows += linkRow(m.outlet, m.title, m.url, m.kind === 'search');
  });
  var generalRows = '';
  general.forEach(function (g) {
    var parts = String(g.title || '').split(' — ');
    generalRows += linkRow(parts.length > 1 ? parts[0] : '', parts.length > 1 ? parts.slice(1).join(' — ') : g.title, g.url, false);
  });
  var g2 = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:12px;margin-bottom:12px';
  var linksH = '<div style="' + g2 + '">'
    + panel('Media', (mediaRows || empty('No coverage links available.')) + note('Headlines link to the outlet via Google News. Rows in grey open that outlet’s own search.'))
    + panel('General', generalRows || empty('No reference links available.'))
    + '</div>';

  // ── USGS summary (key points, tectonic setting, reported impacts) ──
  var sumBody = '';
  if (txt) {
    if (txt.key_points && txt.key_points.length) {
      sumBody += '<div style="font-size:10px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Key points' + (txt.key_points_updated ? ' <span style="font-weight:500;color:#888;text-transform:none;letter-spacing:0">(updated ' + esc(txt.key_points_updated) + ')</span>' : '') + '</div>'
        + '<ul style="margin:0 0 10px 16px;padding:0;font-size:12px;line-height:1.55;color:#1a1f36">'
        + txt.key_points.map(function (k) { return '<li style="margin-bottom:3px">' + esc(k) + '</li>'; }).join('') + '</ul>';
    }
    if (txt.impacts) {
      sumBody += '<div style="font-size:10px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin:6px 0 4px">Reported impacts</div>'
        + '<div style="font-size:12px;line-height:1.55;color:#1a1f36;margin-bottom:10px">' + esc(txt.impacts) + '</div>';
    }
    if (txt.tectonic) {
      sumBody += '<div style="font-size:10px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin:6px 0 4px">Tectonic setting</div>'
        + '<div style="font-size:12px;line-height:1.55;color:#1a1f36">' + esc(txt.tectonic) + '</div>';
    }
    sumBody += '<div style="margin-top:10px">' + linkBtn('Full USGS text', base + '#executive') + '</div>'
      + note('Text as published by the USGS National Earthquake Information Center. It may lag behind the latest solution.');
  }
  var sumPanel = panel('USGS Summary', sumBody || empty('The USGS has not yet published a summary for this earthquake.')
    + '<div style="margin-top:10px">' + linkBtn('USGS event page', base) + '</div>');

  // ── Impact estimate (USGS PAGER) ──
  var impBody = '';
  if (pg && (pg.fatality || pg.economic)) {
    function lvlRow(label, blk, rangeFn, thr) {
      if (!blk) return '';
      return '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
        + '<span style="color:#64748b;flex:0 0 auto">' + label + '</span>'
        + '<span style="text-align:right">' + lvlChip(blk.level, thr)
        + (blk.top ? '<div style="font-size:11px;color:#64748b;margin-top:3px">most likely ' + esc(rangeFn(blk.top)) + ' (' + fmtProb(blk.top.p) + ' probability)</div>' : '') + '</span></div>';
    }
    var tf = PAGER_THRESHOLDS[String((pg.fatality || {}).level || '').toUpperCase()] || {};
    var te = PAGER_THRESHOLDS[String((pg.economic || {}).level || '').toUpperCase()] || {};
    impBody += lvlRow('Fatalities', pg.fatality, fatalityRange, 'Fatalities: ' + (tf.fatalities || ''))
             + lvlRow('Economic losses', pg.economic, lossRange, 'Losses: ' + (te.losses || ''));
    var cm = pg.comments || {};
    if (cm.impact && cm.impact.length) {
      impBody += '<div style="font-size:12px;line-height:1.55;color:#1a1f36;margin-top:10px">' + cm.impact.map(esc).join('<br>') + '</div>';
    }
    // Population exposed to each shaking intensity
    var expo = (pg.exposure || []).filter(function (e) { return e.mmi >= 5 && e.pop > 0; });
    if (expo.length) {
      var maxPop = Math.max.apply(null, expo.map(function (e) { return e.pop; }));
      impBody += '<div style="font-size:10px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 4px">Population exposed to shaking</div>'
        + expo.map(function (e) {
            var r = MMI_SCALE[String(e.mmi)] || [];
            var w = Math.max(3, Math.round(e.pop / maxPop * 100));
            return '<div style="display:grid;grid-template-columns:62px minmax(0,1fr) 78px;align-items:center;gap:8px;font-size:11px;padding:2px 0">'
              + '<span style="font-weight:700;color:#1a1f36">MMI ' + esc(r[0] || e.mmi) + '</span>'
              + '<span style="height:7px;background:#e2e6f0;border-radius:4px"><span style="display:block;width:' + w + '%;height:100%;background:' + (r[3] || '#999') + ';border-radius:4px"></span></span>'
              + '<span style="text-align:right;color:#64748b">' + fmtPeople(e.pop) + '</span></div>';
          }).join('');
    }
    if (cm.structures) {
      impBody += '<div style="font-size:10px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 4px">Typical construction in the region</div>'
        + '<div style="font-size:11.5px;line-height:1.55;color:#1a1f36">' + esc(cm.structures) + '</div>';
    }
    impBody += '<div style="margin-top:10px">' + linkBtn('PAGER report', base + '/pager') + '</div>'
      + note('USGS PAGER is an automatic, preliminary estimate. Alert levels: fatalities green / yellow 1-99 / orange 100-999 / red 1,000+; losses green / yellow US$1M-100M / orange US$100M-1B / red US$1B+.');
  }
  var impPanel = panel('Impact Estimate (USGS PAGER)', impBody || empty('A PAGER impact estimate has not been issued for this earthquake.'));

  // ── Ground motion (ShakeMap) and observed intensity ──
  var gmBody = '';
  if (peak && (peak.pga_g != null || peak.mmi)) {
    gmBody += kv('Maximum intensity', ref ? esc(ref[0]) + ' (MMI ' + mmi.toFixed(1) + ') – ' + esc(ref[1]) + ' shaking, ' + esc(String(ref[2]).toLowerCase()) + ' damage potential' : 'n/a', mc)
      + kv('Peak ground acceleration', fmtG(peak.pga_g))
      + kv('Peak ground velocity', peak.pgv_cms != null ? peak.pgv_cms.toFixed(1) + ' cm/s' : 'n/a')
      + kv('Spectral accel. 0.3 s', fmtG(peak.sa03_g))
      + kv('Spectral accel. 1.0 s', fmtG(peak.sa10_g))
      + kv('Spectral accel. 3.0 s', fmtG(peak.sa30_g));
    gmBody += note('ShakeMap maxima over the whole map (modelled, corrected with station data where available), not values at a particular site. For an intensity ' + (ref ? esc(ref[0]) : '') + ' USGS lists a typical PGA of ' + (ref ? esc(ref[4]) : '') + ' %g and PGV of ' + (ref ? esc(ref[5]) : '') + ' cm/s. '
      + 'ShakeMap v' + esc(sm.version || '?') + ', ' + esc(sm.status || 'unknown') + ' status'
      + (sm.processed ? ', processed ' + esc(String(sm.processed).replace('T', ' ').replace('Z', ' UTC')) : '') + '.');
  } else {
    gmBody = empty('The ShakeMap has not been published yet.');
  }
  if (ev.felt) {
    gmBody += '<div style="margin-top:10px">' + kv('Felt reports (Did You Feel It?)', fmtNum(ev.felt) + (ev.cdi ? ' – max intensity ' + ev.cdi.toFixed(1) : '')) + '</div>';
  }
  var gmPanel = panel('Ground Motion (USGS ShakeMap)', gmBody);

  // ── Ground failure: landslides and liquefaction ──
  var gfBody = '';
  if (gf) {
    ['landslide', 'liquefaction'].forEach(function (hz) {
      var g = gf[hz];
      if (!g) return;
      gfBody += '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
        + '<span style="color:#64748b;text-transform:capitalize;flex:0 0 auto">' + hz + '</span>'
        + '<span style="text-align:right">' + lvlChip(g.alert, '')
        + '<div style="font-size:11px;color:#64748b;margin-top:3px">'
        + (g.hazard_km2 != null ? 'high-hazard area ~' + fmtNum(g.hazard_km2) + ' km²' : '')
        + (g.pop != null ? ' · ~' + fmtPeople(g.pop) + ' people exposed' : '') + '</div></span></div>';
    });
    gfBody += '<div style="margin-top:10px">' + linkBtn('USGS ground failure', base + '#ground-failure') + '</div>'
      + note('Alert levels from the USGS ground-failure models (landslides: Nowicki Jessee et al. 2018; liquefaction: Zhu et al. 2017), driven by the ShakeMap. They show where failure is more likely, not that it has occurred.');
  } else {
    gfBody = empty('The USGS ground-failure assessment is not available for this earthquake.');
  }
  if (wea && wea.precip_3day_mm != null) {
    gfBody += '<div style="margin-top:10px">' + kv('Rainfall, 3 days before (at epicentre)', esc(wea.precip_3day_mm) + ' mm')
      + note('Open-Meteo. Wet ground can raise landslide potential; this figure is shown for context and is not part of the USGS alert.') + '</div>';
  }
  if (pg && pg.comments && pg.comments.secondary) {
    gfBody += note('PAGER: ' + esc(pg.comments.secondary));
  }
  var gfPanel = panel('Landslide and Liquefaction (USGS Ground Failure)', gfBody);

  // ── Event parameters ──
  var magLine = 'M' + mag.toFixed(1) + (ev.mag_type ? ' ' + esc(ev.mag_type.charAt(0).toUpperCase() + ev.mag_type.slice(1)) : '')
    + (org && org.mag_err != null ? ' ±' + org.mag_err.toFixed(2) : '');
  var rup = ff
    ? ff.length_km + ' × ' + (ff.width_km != null ? ff.width_km : '?') + ' km (USGS finite-fault model)' + (ff.max_slip_m != null ? ', max slip ' + ff.max_slip_m.toFixed(1) + ' m' : '')
    : (ev.rupture_km ? '~' + Math.round(ev.rupture_km) + ' km long (expected for this magnitude)' : 'n/a');
  var paramsH =
    '<div style="font-size:12px">'
    + kv('Magnitude', magLine)
    + kv('Origin time (UTC)', esc(ev.t_str))
    + kv('Coordinates', coordStr(ev.lat, ev.lon) + (org && org.h_err_km != null ? ' ±' + org.h_err_km + ' km' : ''))
    + kv('Depth', dep.toFixed(1) + ' km' + (org && org.depth_type ? ' (' + esc(org.depth_type) + ')' : ''))
    + kv('Depth class', esc(ev.depth_note || 'n/a'))
    + kv('Solution', (ev.status === 'reviewed' ? 'Reviewed' : 'Automatic') + (org && org.stations ? ' · ' + org.stations + ' stations' : ''))
    + kv('Rupture size', rup)
    + kv('Radiated energy', ev.energy_mt ? '≈ ' + (ev.energy_mt >= 10 ? ev.energy_mt.toFixed(0) : ev.energy_mt.toFixed(1)) + ' Mt TNT equivalent' : 'n/a')
    + '</div>'
    + note('Rupture length without a finite-fault model: Wells &amp; Coppersmith (1994) average. Energy: Gutenberg-Richter relation, a comparison figure.');

  // ── Fault mechanism ──
  var focH = empty('The USGS moment-tensor solution is not available yet.');
  if (foc && foc.type) {
    var fc2 = faultColor(foc.type);
    focH = '<span style="display:inline-block;padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;background:' + fc2 + '18;border:1px solid ' + fc2 + '44;color:' + fc2 + ';margin-bottom:8px">' + esc(foc.type) + '</span>'
      + '<div style="font-size:11.5px;color:#1a1f36;line-height:1.5;margin-bottom:8px">' + faultNote(foc.type) + '</div>'
      + (foc.planes && foc.planes.length
        ? '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:6px"><tr style="font-size:9px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e6f0">'
          + '<th style="text-align:left;padding:4px 6px">Plane</th><th style="text-align:left;padding:4px 6px">Strike</th><th style="text-align:left;padding:4px 6px">Dip</th><th style="text-align:left;padding:4px 6px">Rake</th><th style="text-align:left;padding:4px 6px">Slip</th></tr>'
          + foc.planes.map(function (p, i) {
              return '<tr style="border-bottom:1px solid #eef0f5"><td style="padding:5px 6px;font-weight:700">' + (i + 1) + '</td><td style="padding:5px 6px">' + esc(p.strike) + '°</td><td style="padding:5px 6px">' + esc(p.dip) + '°</td><td style="padding:5px 6px">' + esc(p.rake) + '°</td><td style="padding:5px 6px;color:#64748b">' + esc(planeSense(p)) + '</td></tr>';
            }).join('') + '</table>'
        : '')
      + '<div style="font-size:11px;color:#64748b">'
      + (foc.mw != null ? esc(foc.mw_type || 'Mw') + ' ' + foc.mw.toFixed(1) : '') + (foc.dc_pct != null ? ' · ' + foc.dc_pct + '% double-couple' : '') + (foc.source ? ' · source: ' + esc(String(foc.source).toUpperCase()) : '') + '</div>'
      + note('Moment tensor from the USGS. The fault plane is one of the two nodal planes; the data alone cannot say which. ' + (ff && ff.strike != null ? 'The finite-fault model uses strike ' + ff.strike + '° / dip ' + ff.dip + '°.' : ''));
  }

  // ── Aftershock forecast ──
  var afsH = empty('The USGS has not issued an aftershock forecast for this earthquake.');
  if (afs && afs.rows && afs.rows.length) {
    var afsRows = afs.rows.map(function (r) {
      function cell(p) { return '<td style="padding:5px 6px;color:' + probColor(p) + ';font-weight:700">' + fmtProb(p) + '</td>'; }
      return '<tr><td style="padding:5px 6px;font-weight:700">M' + esc(r.mag) + '+</td>' + cell(r.day) + cell(r.week) + cell(r.month) + cell(r.year) + '</tr>';
    }).join('');
    var obs = (afs.observed || []).filter(function (o) { return o.count != null; })
      .map(function (o) { return 'M' + o.mag + '+: ' + fmtNum(o.count); }).join(' · ');
    afsH = '<div style="font-size:11px;color:#64748b;margin-bottom:6px">Probability of at least one aftershock of at least this magnitude</div>'
      + '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      + '<tr style="font-size:9px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e6f0">'
      + '<th style="text-align:left;padding:4px 6px">Mag.</th><th style="text-align:left;padding:4px 6px">1 Day</th><th style="text-align:left;padding:4px 6px">1 Week</th><th style="text-align:left;padding:4px 6px">1 Month</th><th style="text-align:left;padding:4px 6px">1 Year</th></tr>'
      + afsRows + '</table>'
      + (afs.m3_week && afs.m3_week.median != null ? '<div style="font-size:12px;margin-top:10px">Expected M3+ aftershocks in the next week: <b>' + fmtNum(afs.m3_week.median) + '</b> <span style="color:#64748b">(95% range ' + fmtNum(afs.m3_week.lo) + ' to ' + fmtNum(afs.m3_week.hi) + ')</span></div>' : '')
      + (obs ? '<div style="font-size:12px;margin-top:6px">Recorded so far: <span style="color:#64748b">' + esc(obs) + '</span></div>' : '')
      + note('USGS operational aftershock forecast' + (afs.model ? ' (' + esc(afs.model) + ')' : '') + (afs.issued_ms ? ', issued ' + esc(new Date(afs.issued_ms).toISOString().slice(0, 16).replace('T', ' ')) + ' UTC' : '') + '. Probabilities change as the sequence develops.')
      + '<div style="margin-top:8px">' + linkBtn('USGS aftershock forecast', base + '/oaf/forecast') + '</div>';
  }

  // ── Historical context ──
  var histH = empty('No M5.5+ earthquakes found within 250 km in the last 100 years.');
  if (his && his.length) {
    var histRows = '';
    var maxMag = Math.max.apply(null, his.map(function (h) { return h.mag || 0; }));
    for (var hi = 0; hi < his.length; hi++) {
      var hev  = his[hi];
      var hurl = safeUrl(hev.url);
      var hl   = hurl
        ? '<a href="' + esc(hurl) + '" target="_blank" rel="noopener noreferrer" style="color:#1565c0;text-decoration:none;font-weight:700">M' + Number(hev.mag).toFixed(1) + '</a>'
        : '<b>M' + Number(hev.mag).toFixed(1) + '</b>';
      histRows += '<div style="display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid #e2e6f0;font-size:12px">'
        + '<span>' + hl + ' - ' + esc(hev.place) + '</span><span style="color:#888;white-space:nowrap">' + esc((hev.month ? hev.month + ' ' : '') + hev.year) + (hev.dist_km != null ? ' · ' + esc(hev.dist_km) + ' km' : '') + '</span>'
        + '</div>';
    }
    histH = histRows
      + '<div style="font-size:10px;color:#888;margin-top:6px;font-style:italic">'
      + (mag >= maxMag ? 'Larger than every M5.5+ earthquake found within 250 km in the last 100 years.' : 'Earthquakes of M5.5+ within 250 km, largest first; distances are from this epicentre.')
      + '</div>'
      + (pg && pg.comments && pg.comments.historical ? '<div style="font-size:11.5px;line-height:1.55;color:#1a1f36;margin-top:10px"><b>USGS PAGER:</b> ' + esc(pg.comments.historical) + '</div>' : '');
  }

  // ── Assemble ──
  return heroH + mapH + linksH
    + '<div style="' + g2 + '">' + sumPanel + impPanel + '</div>'
    + '<div style="' + g2 + '">' + gmPanel + gfPanel + '</div>'
    + '<div style="' + g2 + '">' + panel('Event Parameters', paramsH) + panel('Fault Mechanism', focH) + '</div>'
    + '<div style="' + g2 + '">' + panel('Aftershock Forecast', afsH) + panel('Historical Context (250 km / 100 yr)', histH) + '</div>'
    + '<div style="font-size:10px;color:#aaa;padding-top:6px;border-top:1px solid #e2e6f0;line-height:1.6">'
    + 'Sources: USGS (ShakeMap, PAGER, Ground Failure, moment tensor, finite fault, aftershock forecast, Did You Feel It?) · Open-Meteo · links to Wikipedia, EMSC, GDACS, GEM, ReliefWeb and news outlets. '
    + 'Automatic USGS solutions are preliminary and can change. For situational awareness only, not for emergency or life-safety decisions.'
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
  _active = null; _pga = null; _mmi = null; _base = null; _sat = null; _satOn = false; _legend = null; _fitted = false;

  // touch devices: one-finger drag scrolls the page (the map is a big share of a phone screen); pinch and +/- still work
  _map = L.map('leaflet-map', { zoomControl: false, dragging: !L.Browser.mobile }).setView([lat, lon], 7);
  L.control.zoom({ position: 'bottomright' }).addTo(_map);
  _base = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Tiles &copy; Esri', maxZoom: 19 });
  _base.addTo(_map);

  var epiMarker = L.circleMarker([lat, lon], { radius: 9, color: '#fff', fillColor: color, fillOpacity: 1, weight: 2.5 })
    .addTo(_map)
    .bindPopup('<b>Epicentre</b><br>M' + Number(ev.mag).toFixed(1) + ' - ' + esc(ev.place) + '<br>' + esc(ev.t_str));
  if (!window.matchMedia('(max-width:760px)').matches) epiMarker.openPopup();   // on phones it covers the shaking contours; tap the marker instead

  ['btn-pga', 'btn-mmi', 'btn-sat'].forEach(function (id) {
    var btn = document.getElementById(id);
    if (!btn) return;
    btn.onclick = function () {
      var layer = this.dataset.layer;
      if (layer === 'sat') toggleSat(); else setLayer(layer);
    };
  });

  if (!pgaUrl && !mmiUrl) {
    // No ShakeMap yet: say so rather than draw invented shaking rings.
    var notice = L.control({ position: 'bottomleft' });
    notice.onAdd = function () {
      var d = L.DomUtil.create('div');
      d.style.cssText = 'background:rgba(255,255,255,.95);padding:6px 10px;border-radius:6px;font-size:11px;color:#475569;box-shadow:0 1px 6px rgba(0,0,0,.15)';
      d.textContent = 'ShakeMap not published yet - epicentre only';
      return d;
    };
    notice.addTo(_map);
  }

  // Contours: a thin dark line underneath keeps the pale ShakeMap colours visible on a light map.
  function contourLayer(d, tip) {
    var opts = function (f, casing) {
      var major = (f.properties.weight || 2) >= 4;
      return casing ? { color: 'rgba(15,35,80,.55)', weight: (major ? 4.2 : 3.2), opacity: .8 }
                    : { color: f.properties.color || '#999', weight: (major ? 2.6 : 1.8), opacity: 1 };
    };
    var casing = L.geoJSON(d, { style: function (f) { return opts(f, true); }, interactive: false });
    var lines  = L.geoJSON(d, {
      style: function (f) { return opts(f, false); },
      onEachFeature: function (f, l) { l.bindTooltip(tip(f.properties.value), { sticky: true }); }
    });
    var grp = L.layerGroup([casing, lines]);
    grp.getBounds = function () { return lines.getBounds(); };
    grp._features = (d.features || []).map(function (f) { return { v: f.properties.value, c: f.properties.color }; });
    return grp;
  }
  function firstFit(g) {
    if (_fitted) return;
    try {
      var b = g.getBounds();
      if (b && b.isValid()) { _map.fitBounds(b, { padding: [24, 24], maxZoom: 9 }); _fitted = true; }
    } catch (e) {}
  }

  if (pgaUrl) {
    fetch(pgaUrl).then(function (r) { return r.json(); }).then(function (d) {
      _pga = contourLayer(d, function (v) { return '<b>PGA ' + (v < 1 ? v.toFixed(1) : Math.round(v)) + ' %g</b> (' + (v / 100).toFixed(v < 10 ? 3 : 2) + ' g)'; });
      setLayer('pga');
      firstFit(_pga);
    }).catch(function () {});
  }
  if (mmiUrl) {
    fetch(mmiUrl).then(function (r) { return r.json(); }).then(function (d) {
      _mmi = contourLayer(d, function (v) { return '<b>MMI ' + (v % 1 ? v.toFixed(1) : toRoman(v)) + '</b>' + (v % 1 ? '' : ' (' + v + ')'); });
      if (!pgaUrl) { setLayer('mmi'); firstFit(_mmi); }
    }).catch(function () {});
  }
}

// Legend built from the contours actually drawn (value + colour), so it can never disagree with the map.
function updateLegend(type) {
  if (!_map) return;
  if (_legend) { _map.removeControl(_legend); _legend = null; }
  var layer = type === 'pga' ? _pga : _mmi;
  if (!layer || !layer._features || !layer._features.length) return;
  var seen = {}, items = [];
  layer._features.forEach(function (f) { if (!seen[f.v]) { seen[f.v] = 1; items.push(f); } });
  items.sort(function (a, b) { return a.v - b.v; });
  _legend = L.control({ position: 'bottomleft' });
  _legend.onAdd = function () {
    var d = L.DomUtil.create('div');
    d.style.cssText = 'background:rgba(255,255,255,.96);padding:7px 9px;border-radius:7px;font-size:10.5px;color:#334155;box-shadow:0 1px 6px rgba(0,0,0,.18);line-height:1.5;max-width:150px';
    var title = type === 'pga' ? 'Peak ground acceleration (%g)' : 'Shaking intensity (MMI)';
    d.innerHTML = '<div style="font-weight:700;margin-bottom:3px">' + title + '</div>'
      + items.map(function (i) {
          var lab = type === 'pga' ? (i.v < 1 ? i.v.toFixed(1) : Math.round(i.v)) : (i.v % 1 ? i.v.toFixed(1) : toRoman(i.v));
          return '<div style="display:flex;align-items:center;gap:6px"><span style="width:16px;height:0;border-top:3px solid ' + esc(i.c || '#999') + ';box-shadow:0 0 0 1px rgba(15,35,80,.35);flex:0 0 auto"></span><span>' + lab + '</span></div>';
        }).join('');
    return d;
  };
  _legend.addTo(_map);
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
  updateLegend(type);
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
  setInterval(refreshAges, 60000);
});
