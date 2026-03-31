/**
 * WLC CT2504 Card — Home Assistant Lovelace Custom Card
 * Proiect: Network Monitoring Dashboard
 * Tema: Dark Industrial (Rajdhani + Share Tech Mono)
 *
 * YAML config (one-liner):
 *   type: custom:wlc-card
 *   prefix: wlc_ct2504
 *
 * Entitati asteptate (prefix_<slug>):
 *   System:   _cpu, _memory, _uptime, _temperature, _firmware, _serial, _model
 *   Network:  _ip_mgmt, _ap_manager_ip, _capwap_status
 *   AP:       _ap_<n>_name, _ap_<n>_status, _ap_<n>_clients, _ap_<n>_channel_24,
 *             _ap_<n>_channel_5, _ap_<n>_txpower_24, _ap_<n>_txpower_5, _ap_<n>_model, _ap_<n>_ip
 *   Clients:  _clients_total, _clients_24, _clients_5
 *   SSID:     _ssid_<n>_name, _ssid_<n>_status, _ssid_<n>_clients, _ssid_<n>_vlan,
 *             _ssid_<n>_band, _ssid_<n>_security
 */

class WlcCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    if (!config.prefix) throw new Error('WLC Card: "prefix" este obligatoriu in config.');
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  // ─────────────────────────────────────────
  // HELPERS
  // ─────────────────────────────────────────
  _e(slug) {
    const id = `sensor.${this._config.prefix}_${slug}`;
    return this._hass?.states?.[id] ?? null;
  }

  _v(slug, fallback = '—') {
    const s = this._e(slug);
    if (!s) return fallback;
    const v = s.state;
    if (v === 'unavailable' || v === 'unknown' || v === undefined) return fallback;
    return v;
  }

  _attr(slug, attr, fallback = '—') {
    const s = this._e(slug);
    if (!s) return fallback;
    const v = s.attributes?.[attr];
    if (v === undefined || v === null) return fallback;
    return String(v);
  }

  _num(slug, fallback = 0) {
    const v = parseFloat(this._v(slug, String(fallback)));
    return isNaN(v) ? fallback : v;
  }

  // Cauta toate entityid-urile care matchuiesc prefix_ap_<N>_name
  _getApIndexes() {
    if (!this._hass) return [];
    const prefix = `sensor.${this._config.prefix}_ap_`;
    const indexes = new Set();
    Object.keys(this._hass.states).forEach(id => {
      if (id.startsWith(prefix) && id.endsWith('_name')) {
        const mid = id.slice(prefix.length, -5); // extrage indexul
        if (/^\d+$/.test(mid)) indexes.add(Number(mid));
      }
    });
    return [...indexes].sort((a, b) => a - b);
  }

  _getSsidIndexes() {
    if (!this._hass) return [];
    const prefix = `sensor.${this._config.prefix}_ssid_`;
    const indexes = new Set();
    Object.keys(this._hass.states).forEach(id => {
      if (id.startsWith(prefix) && id.endsWith('_name')) {
        const mid = id.slice(prefix.length, -5);
        if (/^\d+$/.test(mid)) indexes.add(Number(mid));
      }
    });
    return [...indexes].sort((a, b) => a - b);
  }

  _pct(slug) {
    const v = this._num(slug, 0);
    return Math.min(100, Math.max(0, v));
  }

  _barColor(pct) {
    if (pct >= 85) return 'crit';
    if (pct >= 65) return 'warn';
    return '';
  }

  _apStatus(idx) {
    const v = this._v(`ap_${idx}_status`, 'unknown').toLowerCase();
    if (v === '1' || v === 'up' || v === 'associated' || v === 'registered') return 'up';
    return 'down';
  }

  _fmtUptime(raw) {
    if (raw === '—' || !raw) return '—';
    // raw poate fi in secunde (SNMP sysUpTime e in ticks/100)
    const secs = typeof raw === 'string' && raw.includes('d')
      ? raw  // deja formatat
      : (() => {
          const n = parseFloat(raw);
          if (isNaN(n)) return raw;
          const ticks = n; // assume secunde daca vine din SNMP sensor formatat
          const d = Math.floor(ticks / 86400);
          const h = Math.floor((ticks % 86400) / 3600);
          const m = Math.floor((ticks % 3600) / 60);
          return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
        })();
    return secs;
  }

  _bandTag(band) {
    if (!band || band === '—') return `<span class="band-tag dual">Dual</span>`;
    const b = String(band).toLowerCase();
    if (b.includes('2.4') || b === '1') return `<span class="band-tag g24">2.4G</span>`;
    if (b.includes('5') || b === '2') return `<span class="band-tag g5">5G</span>`;
    return `<span class="band-tag dual">Dual</span>`;
  }

  // ─────────────────────────────────────────
  // AP TABLE ROWS
  // ─────────────────────────────────────────
  _renderApRows() {
    const indexes = this._getApIndexes();
    if (indexes.length === 0) {
      return `<div class="empty-row">Nu s-au detectat AP-uri (verifică prefixul)</div>`;
    }
    return indexes.map(i => {
      const name    = this._v(`ap_${i}_name`, `AP-${i}`);
      const model   = this._v(`ap_${i}_model`, '—');
      const ip      = this._v(`ap_${i}_ip`, '—');
      const clients = this._v(`ap_${i}_clients`, '—');
      const ch24    = this._v(`ap_${i}_channel_24`, '—');
      const ch5     = this._v(`ap_${i}_channel_5`, '—');
      const tx24    = this._v(`ap_${i}_txpower_24`, '—');
      const status  = this._apStatus(i);
      const channel = ch24 !== '—' && ch5 !== '—' ? `${ch24} / ${ch5}` : ch24 !== '—' ? ch24 : ch5;
      const tx      = tx24 !== '—' ? `${tx24} dBm` : '—';

      return `
        <div class="ap-row">
          <div class="ap-name">
            ${this._esc(name)}
            <span>${this._esc(model)} · ${this._esc(ip)}</span>
          </div>
          <div class="ap-cell">
            <span class="ap-status ${status}">
              <span class="ap-status-dot"></span>${status.toUpperCase()}
            </span>
          </div>
          <div class="ap-cell cyan-val">${this._esc(clients)}</div>
          <div class="ap-cell">${this._esc(channel)}</div>
          <div class="ap-cell">${this._esc(tx)}</div>
        </div>`;
    }).join('');
  }

  // ─────────────────────────────────────────
  // SSID TABLE ROWS
  // ─────────────────────────────────────────
  _renderSsidRows() {
    const indexes = this._getSsidIndexes();
    if (indexes.length === 0) {
      return `<div class="empty-row">Nu s-au detectat SSID-uri (verifică prefixul)</div>`;
    }
    return indexes.map(i => {
      const name     = this._v(`ssid_${i}_name`, `WLAN-${i}`);
      const clients  = this._v(`ssid_${i}_clients`, '—');
      const vlan     = this._v(`ssid_${i}_vlan`, '—');
      const band     = this._v(`ssid_${i}_band`, 'dual');
      const security = this._v(`ssid_${i}_security`, 'WPA2');

      return `
        <div class="ssid-row">
          <div class="ssid-name-col">
            <svg class="ssid-icon" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="11" r="1.2" fill="var(--cyan)"/>
              <path d="M4.5 9C5.2 8.1 6 7.6 7 7.6s1.8.5 2.5 1.4" stroke="var(--cyan)" stroke-width="1.2" stroke-linecap="round" fill="none"/>
              <path d="M2.5 7.2C3.7 5.6 5.2 4.7 7 4.7s3.3.9 4.5 2.5" stroke="var(--cyan)" stroke-width="1.2" stroke-linecap="round" fill="none" opacity="0.5"/>
            </svg>
            <span class="ssid-name">${this._esc(name)}</span>
          </div>
          <div class="ssid-cell">${this._bandTag(band)}</div>
          <div class="ssid-cell"><span class="sec-tag">${this._esc(security)}</span></div>
          <div class="ssid-cell text-primary">${vlan !== '—' ? 'VLAN ' + this._esc(vlan) : '—'}</div>
          <div class="ssid-cell cyan-val">${this._esc(clients)}</div>
        </div>`;
    }).join('');
  }

  _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ─────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────
  _render() {
    if (!this._config.prefix) return;

    const cpu      = this._pct('cpu');
    const mem      = this._pct('memory');
    const flash    = this._pct('flash');
    const uptime   = this._fmtUptime(this._v('uptime'));
    const temp     = this._v('temperature', '—');
    const firmware = this._v('firmware', this._config.firmware || '—');
    const serial   = this._v('serial', '—');
    const model    = this._v('model', 'AIR-CT2504');
    const ipMgmt   = this._v('ip_mgmt', this._config.ip || '—');
    const apMgr    = this._v('ap_manager_ip', '—');
    const capwap   = this._v('capwap_status', '—');
    const licUsed  = this._v('ap_license_used', '—');
    const licTotal = this._v('ap_license_total', '25');
    const rfCountry= this._v('rf_country', 'RO');

    const clientsTotal = this._v('clients_total', '—');
    const clients24    = this._v('clients_24', '—');
    const clients5     = this._v('clients_5', '—');

    const apIndexes   = this._getApIndexes();
    const apTotal     = apIndexes.length;
    const apUp        = apIndexes.filter(i => this._apStatus(i) === 'up').length;
    const ssidCount   = this._getSsidIndexes().length;

    const title       = this._config.title || 'Cisco WLC 2504';
    const isOnline    = this._e('cpu') !== null || this._e('uptime') !== null;

    this.shadowRoot.innerHTML = `
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :host {
          --bg-card:       #161b22;
          --bg-section:    #0d1117;
          --bg-box:        #1c2330;
          --border:        #2a3441;
          --text-primary:  #e6edf3;
          --text-secondary:#8b9ab0;
          --text-dim:      #556070;
          --cyan:          #39d0d8;
          --cyan-dim:      rgba(57,208,216,0.12);
          --green:         #3fb950;
          --green-dim:     rgba(63,185,80,0.12);
          --amber:         #d29922;
          --amber-dim:     rgba(210,153,34,0.12);
          --red:           #f85149;
          --red-dim:       rgba(248,81,73,0.12);
          --blue:          #58a6ff;
          --blue-dim:      rgba(88,166,255,0.12);
          --mono:          'Share Tech Mono', monospace;
          display: block;
          font-family: 'Rajdhani', sans-serif;
        }

        ha-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 4px 24px rgba(0,0,0,0.5);
        }

        /* HEADER */
        .card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 16px 12px;
          border-bottom: 1px solid var(--border);
          background: linear-gradient(135deg, #1a2232 0%, var(--bg-card) 100%);
        }
        .header-left { display: flex; align-items: center; gap: 10px; }
        .device-icon { width: 36px; height: 36px; flex-shrink: 0; }
        .header-titles { display: flex; flex-direction: column; gap: 1px; }
        .card-title { font-size: 17px; font-weight: 700; color: var(--text-primary); letter-spacing: 0.5px; line-height: 1.2; }
        .card-subtitle { font-size: 11px; font-weight: 500; color: var(--text-dim); letter-spacing: 1.5px; text-transform: uppercase; font-family: var(--mono); }
        .header-right { display: flex; align-items: center; gap: 8px; }
        .status-badge { display: flex; align-items: center; gap: 5px; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; font-family: var(--mono); }
        .status-badge.online { background: var(--green-dim); border: 1px solid rgba(63,185,80,0.3); color: var(--green); }
        .status-badge.offline { background: var(--red-dim); border: 1px solid rgba(248,81,73,0.3); color: var(--red); }
        .status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
        .status-badge.online .status-dot { box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }
        .uptime-badge { font-size: 11px; font-family: var(--mono); color: var(--text-dim); background: var(--bg-box); border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; }

        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

        /* SECTION LABEL */
        .section-label { font-size: 10px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: var(--text-dim); padding: 10px 16px 6px; font-family: var(--mono); display: flex; align-items: center; gap: 6px; }
        .section-label::after { content: ''; flex: 1; height: 1px; background: var(--border); }

        /* STATS ROW */
        .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 0 12px 10px; }
        .stat-box { background: var(--bg-box); border: 1px solid var(--border); border-radius: 8px; padding: 10px 8px; text-align: center; position: relative; overflow: hidden; }
        .stat-box::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
        .stat-box.cyan::before  { background: var(--cyan); }
        .stat-box.green::before { background: var(--green); }
        .stat-box.amber::before { background: var(--amber); }
        .stat-box.blue::before  { background: var(--blue); }
        .stat-val { font-size: 26px; font-weight: 700; line-height: 1; font-family: var(--mono); margin-bottom: 2px; }
        .stat-unit { font-size: 12px; font-weight: 500; color: var(--text-dim); }
        .stat-box.cyan  .stat-val { color: var(--cyan); }
        .stat-box.green .stat-val { color: var(--green); }
        .stat-box.amber .stat-val { color: var(--amber); }
        .stat-box.blue  .stat-val { color: var(--blue); }
        .stat-label { font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 4px; }

        /* INFO GRID */
        .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 12px 10px; }
        .info-box { background: var(--bg-box); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
        .info-title { font-size: 10px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: var(--cyan); margin-bottom: 8px; font-family: var(--mono); }
        .info-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; border-bottom: 1px solid rgba(42,52,65,0.5); }
        .info-row:last-child { border-bottom: none; }
        .info-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
        .info-val { font-size: 12px; color: var(--text-primary); font-family: var(--mono); }
        .info-val.green { color: var(--green); }
        .info-val.cyan  { color: var(--cyan); }
        .info-val.amber { color: var(--amber); }

        /* RESOURCES */
        .res-box { background: var(--bg-box); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
        .res-title { font-size: 10px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: var(--cyan); margin-bottom: 10px; font-family: var(--mono); }
        .res-item { margin-bottom: 9px; }
        .res-item:last-child { margin-bottom: 0; }
        .res-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
        .res-name { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
        .res-pct  { font-size: 12px; font-family: var(--mono); color: var(--text-primary); }
        .res-track { height: 5px; background: rgba(42,52,65,0.8); border-radius: 3px; overflow: hidden; }
        .res-fill { height: 100%; border-radius: 3px; background: var(--cyan); transition: width 0.6s ease; }
        .res-fill.warn { background: var(--amber); }
        .res-fill.crit { background: var(--red); }
        .mini-grid { margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
        .mini-box { background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; text-align: center; }
        .mini-label { font-size: 11px; font-family: var(--mono); color: var(--text-dim); margin-bottom: 2px; }
        .mini-val   { font-size: 16px; font-weight: 700; font-family: var(--mono); }
        .mini-val.green { color: var(--green); }
        .mini-val.cyan  { color: var(--cyan); }

        /* AP TABLE */
        .ap-box { background: var(--bg-box); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin: 0 12px 10px; }
        .ap-table-head { display: grid; grid-template-columns: 1fr 90px 70px 70px 70px; padding: 6px 10px; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); }
        .ap-th { font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--text-dim); font-family: var(--mono); }
        .ap-th:not(:first-child) { text-align: center; }
        .ap-row { display: grid; grid-template-columns: 1fr 90px 70px 70px 70px; padding: 7px 10px; border-bottom: 1px solid rgba(42,52,65,0.4); align-items: center; transition: background 0.15s; }
        .ap-row:last-child { border-bottom: none; }
        .ap-row:hover { background: rgba(57,208,216,0.04); }
        .ap-name { font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: var(--mono); }
        .ap-name span { display: block; font-size: 10px; color: var(--text-dim); font-weight: 400; margin-top: 1px; }
        .ap-cell { text-align: center; font-size: 12px; font-family: var(--mono); color: var(--text-secondary); }
        .ap-cell.cyan-val { color: var(--cyan); }
        .ap-status { display: inline-flex; align-items: center; justify-content: center; gap: 4px; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }
        .ap-status.up   { background: var(--green-dim); border: 1px solid rgba(63,185,80,0.25); color: var(--green); }
        .ap-status.down { background: var(--red-dim);   border: 1px solid rgba(248,81,73,0.25); color: var(--red); }
        .ap-status-dot  { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
        .ap-status.up .ap-status-dot { animation: pulse 2s infinite; }

        /* SSID TABLE */
        .ssid-box { background: var(--bg-box); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin: 0 12px 10px; }
        .ssid-head { display: grid; grid-template-columns: 1fr 60px 80px 80px 60px; padding: 6px 10px; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); }
        .ssid-th { font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--text-dim); font-family: var(--mono); }
        .ssid-th:not(:first-child) { text-align: center; }
        .ssid-row { display: grid; grid-template-columns: 1fr 60px 80px 80px 60px; padding: 7px 10px; border-bottom: 1px solid rgba(42,52,65,0.4); align-items: center; transition: background 0.15s; }
        .ssid-row:last-child { border-bottom: none; }
        .ssid-row:hover { background: rgba(57,208,216,0.04); }
        .ssid-name-col { display: flex; align-items: center; gap: 6px; }
        .ssid-icon { width: 14px; height: 14px; flex-shrink: 0; }
        .ssid-name { font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: var(--mono); }
        .ssid-cell { text-align: center; font-size: 12px; font-family: var(--mono); color: var(--text-secondary); }
        .ssid-cell.text-primary { color: var(--text-primary); }
        .ssid-cell.cyan-val     { color: var(--cyan); }
        .band-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; font-family: var(--mono); }
        .band-tag.g24  { background: var(--blue-dim);  border: 1px solid rgba(88,166,255,0.25); color: var(--blue); }
        .band-tag.g5   { background: var(--cyan-dim);  border: 1px solid rgba(57,208,216,0.25); color: var(--cyan); }
        .band-tag.dual { background: var(--amber-dim); border: 1px solid rgba(210,153,34,0.25); color: var(--amber); }
        .sec-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; font-family: var(--mono); background: var(--green-dim); border: 1px solid rgba(63,185,80,0.25); color: var(--green); }

        /* FOOTER */
        .card-footer { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-top: 1px solid var(--border); background: rgba(0,0,0,0.15); flex-wrap: wrap; gap: 6px; }
        .footer-stat { font-size: 11px; color: var(--text-dim); font-family: var(--mono); }
        .footer-stat span { color: var(--text-secondary); }
        .footer-divider { width: 1px; height: 12px; background: var(--border); }

        /* MISC */
        .empty-row { padding: 12px; text-align: center; color: var(--text-dim); font-size: 12px; font-family: var(--mono); }
      </style>

      <ha-card>

        <!-- HEADER -->
        <div class="card-header">
          <div class="header-left">
            <svg class="device-icon" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="36" height="36" rx="8" fill="#1c2330"/>
              <path d="M18 23 C18 23 18 23 18 23" stroke="#39d0d8" stroke-width="2" stroke-linecap="round"/>
              <path d="M14.5 20.5 C15.5 19 16.7 18 18 18 C19.3 18 20.5 19 21.5 20.5" stroke="#39d0d8" stroke-width="1.5" stroke-linecap="round" fill="none"/>
              <path d="M11.5 18 C13 15.5 15.3 14 18 14 C20.7 14 23 15.5 24.5 18" stroke="#39d0d8" stroke-width="1.5" stroke-linecap="round" fill="none" opacity="0.7"/>
              <path d="M8.5 15.5 C10.5 12 14 10 18 10 C22 10 25.5 12 27.5 15.5" stroke="#39d0d8" stroke-width="1.5" stroke-linecap="round" fill="none" opacity="0.4"/>
              <circle cx="18" cy="23" r="1.5" fill="#39d0d8"/>
              <rect x="10" y="26" width="16" height="2.5" rx="1.25" fill="#2a3441"/>
              <rect x="14" y="24.5" width="8" height="1.5" rx="0.75" fill="#2a3441"/>
            </svg>
            <div class="header-titles">
              <div class="card-title">${this._esc(title)}</div>
              <div class="card-subtitle">Wireless LAN Controller · AIR-CT2504</div>
            </div>
          </div>
          <div class="header-right">
            <div class="uptime-badge">↑ ${this._esc(uptime)}</div>
            <div class="status-badge ${isOnline ? 'online' : 'offline'}">
              <div class="status-dot"></div>
              ${isOnline ? 'Online' : 'Offline'}
            </div>
          </div>
        </div>

        <!-- KPI STATS -->
        <div class="section-label">Overview</div>
        <div class="stats-row">
          <div class="stat-box green">
            <div class="stat-val">${apUp}<span class="stat-unit">/${apTotal}</span></div>
            <div class="stat-label">AP Online</div>
          </div>
          <div class="stat-box cyan">
            <div class="stat-val">${this._esc(clientsTotal)}</div>
            <div class="stat-label">Clienți</div>
          </div>
          <div class="stat-box amber">
            <div class="stat-val">${ssidCount || '—'}</div>
            <div class="stat-label">SSID-uri</div>
          </div>
          <div class="stat-box blue">
            <div class="stat-val">${this._esc(clients5)}</div>
            <div class="stat-label">Pe 5GHz</div>
          </div>
        </div>

        <!-- DEVICE + RESOURCES -->
        <div class="section-label">Device</div>
        <div class="info-grid">
          <div class="info-box">
            <div class="info-title">System Info</div>
            <div class="info-row">
              <span class="info-label">Model</span>
              <span class="info-val cyan">${this._esc(model)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Software</span>
              <span class="info-val">${this._esc(firmware)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">IP Mgmt</span>
              <span class="info-val">${this._esc(ipMgmt)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Serial</span>
              <span class="info-val">${this._esc(serial)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Licență AP</span>
              <span class="info-val green">${this._esc(licUsed)} / ${this._esc(licTotal)}</span>
            </div>
          </div>

          <div class="res-box">
            <div class="res-title">Resurse sistem</div>
            <div class="res-item">
              <div class="res-header">
                <span class="res-name">CPU</span>
                <span class="res-pct">${cpu}%</span>
              </div>
              <div class="res-track"><div class="res-fill ${this._barColor(cpu)}" style="width:${cpu}%"></div></div>
            </div>
            <div class="res-item">
              <div class="res-header">
                <span class="res-name">Memorie</span>
                <span class="res-pct">${mem}%</span>
              </div>
              <div class="res-track"><div class="res-fill ${this._barColor(mem)}" style="width:${mem}%"></div></div>
            </div>
            <div class="res-item">
              <div class="res-header">
                <span class="res-name">Flash</span>
                <span class="res-pct">${flash}%</span>
              </div>
              <div class="res-track"><div class="res-fill ${this._barColor(flash)}" style="width:${flash}%"></div></div>
            </div>
            <div class="mini-grid">
              <div class="mini-box">
                <div class="mini-label">TEMP</div>
                <div class="mini-val ${parseFloat(temp) > 65 ? 'amber' : 'green'}">${this._esc(temp)}°C</div>
              </div>
              <div class="mini-box">
                <div class="mini-label">2.4G</div>
                <div class="mini-val cyan">${this._esc(clients24)}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- NETWORK + WIRELESS GLOBAL -->
        <div class="info-grid" style="padding-top:0">
          <div class="info-box">
            <div class="info-title">Network</div>
            <div class="info-row">
              <span class="info-label">Service Port</span>
              <span class="info-val">${this._esc(ipMgmt)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">AP-Manager</span>
              <span class="info-val">${this._esc(apMgr)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">CAPWAP</span>
              <span class="info-val ${capwap.toLowerCase().includes('enable') || capwap === '1' ? 'green' : 'amber'}">${this._esc(capwap)}</span>
            </div>
            <div class="info-row">
              <span class="info-label">RF Country</span>
              <span class="info-val">${this._esc(rfCountry)}</span>
            </div>
          </div>

          <div class="info-box">
            <div class="info-title">Wireless Global</div>
            <div class="info-row">
              <span class="info-label">802.11b/g/n</span>
              <span class="info-val green">${this._v('radio_24_status', 'Enabled')}</span>
            </div>
            <div class="info-row">
              <span class="info-label">802.11a/n</span>
              <span class="info-val green">${this._v('radio_5_status', 'Enabled')}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Band Select</span>
              <span class="info-val cyan">${this._v('band_select', '—')}</span>
            </div>
            <div class="info-row">
              <span class="info-label">RRM</span>
              <span class="info-val cyan">${this._v('rrm_status', '—')}</span>
            </div>
          </div>
        </div>

        <!-- AP TABLE -->
        <div class="section-label">Access Points</div>
        <div class="ap-box">
          <div class="ap-table-head">
            <span class="ap-th">Nume / Model</span>
            <span class="ap-th">Status</span>
            <span class="ap-th">Clienți</span>
            <span class="ap-th">Channel</span>
            <span class="ap-th">TxPower</span>
          </div>
          ${this._renderApRows()}
        </div>

        <!-- SSID TABLE -->
        <div class="section-label">SSID / WLAN</div>
        <div class="ssid-box">
          <div class="ssid-head">
            <span class="ssid-th">SSID</span>
            <span class="ssid-th">Band</span>
            <span class="ssid-th">Securitate</span>
            <span class="ssid-th">VLAN</span>
            <span class="ssid-th">Clienți</span>
          </div>
          ${this._renderSsidRows()}
        </div>

        <!-- FOOTER -->
        <div class="card-footer">
          <span class="footer-stat">Firmware <span>${this._esc(firmware)}</span></span>
          <div class="footer-divider"></div>
          <span class="footer-stat">Porturi <span>4 × GbE</span></span>
          <div class="footer-divider"></div>
          <span class="footer-stat">Licențe <span>${this._esc(licUsed)} / ${this._esc(licTotal)} AP</span></span>
          <div class="footer-divider"></div>
          <span class="footer-stat">Uptime <span>${this._esc(uptime)}</span></span>
        </div>

      </ha-card>`;
  }

  getCardSize() { return 8; }

  static getConfigElement() {
    return document.createElement('wlc-card-editor');
  }

  static getStubConfig() {
    return { prefix: 'wlc_ct2504' };
  }
}

customElements.define('wlc-card', WlcCard);

// ─────────────────────────────────────────
// EDITOR (GUI config in Lovelace)
// ─────────────────────────────────────────
class WlcCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  get _prefix() { return this._config?.prefix || ''; }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .editor { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        label { font-size: 13px; color: var(--primary-text-color); display: block; margin-bottom: 4px; }
        input { width: 100%; padding: 8px 10px; border: 1px solid var(--divider-color); border-radius: 6px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 13px; }
      </style>
      <div class="editor">
        <div>
          <label>Prefix entități (ex: wlc_ct2504)</label>
          <input id="prefix" value="${this._prefix}" placeholder="wlc_ct2504">
        </div>
        <div>
          <label>Titlu card (opțional)</label>
          <input id="title" value="${this._config?.title || ''}" placeholder="Cisco WLC 2504">
        </div>
      </div>`;

    this.querySelector('#prefix').addEventListener('change', e => {
      this._config = { ...this._config, prefix: e.target.value };
      this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this._config }, bubbles: true, composed: true }));
    });
    this.querySelector('#title').addEventListener('change', e => {
      this._config = { ...this._config, title: e.target.value };
      this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this._config }, bubbles: true, composed: true }));
    });
  }
}

customElements.define('wlc-card-editor', WlcCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'wlc-card',
  name: 'WLC CT2504 Card',
  description: 'Dashboard card pentru Cisco Wireless LAN Controller 2504',
  preview: true,
});
