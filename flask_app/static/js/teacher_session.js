// ─── Live Session view: timer, polling for present-list updates, QR rotation ──
;(function () {
  const cfg = window.LIVE_SESSION
  if (!cfg) return

  function formatTime(value) {
    const h = Math.floor(value / 3600), m = Math.floor((value % 3600) / 60), s = value % 60
    return h ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
             : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const timerEl = document.getElementById('sl-timer')
  function tickTimer() {
    if (!timerEl) return
    const elapsed = Math.max(0, Math.floor((Date.now() - cfg.startTime) / 1000))
    timerEl.textContent = formatTime(elapsed)
  }
  tickTimer()
  setInterval(tickTimer, 1000)

  // QR rotation countdown + image refresh
  let cd = Math.round(cfg.rotateMs / 1000)
  const cdEl = document.getElementById('qr-cd')
  const qrImg = document.getElementById('qr-img')
  function tickCountdown() {
    cd--
    if (cd < 0) cd = Math.round(cfg.rotateMs / 1000)
    if (cdEl) cdEl.textContent = cd + 's'
  }
  setInterval(tickCountdown, 1000)
  setInterval(() => { if (qrImg) qrImg.src = cfg.qrUrl + '?t=' + Date.now() }, cfg.rotateMs)

  // Poll the live endpoint for present-list, count and current code
  const listEl = document.getElementById('sl-list')
  const presentEl = document.getElementById('sl-present')
  const tokenDisp = document.getElementById('qr-token-disp')
  const copyBtn = document.getElementById('copy-token-btn')

  // Manually-added entries carry free-text name/roll from the teacher's form —
  // escape before inserting via innerHTML so that text can't be read as markup.
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
  }

  function renderList(attendees) {
    if (!listEl) return
    listEl.innerHTML = attendees.length ? attendees.map(e => `
      <div class="row-item">
        <div class="avatar av-sm av-green">${esc((e.name[0] || '?').toUpperCase())}</div>
        <div class="ri-main"><div class="ri-title">${esc(e.name)}</div><div class="ri-sub">${esc(e.roll)} · ${esc(e.time)}${e.manual ? ' · Manual' : ''}</div></div>
        <span class="badge badge-green">Present</span>
      </div>`).join('') : '<div class="empty-state">Waiting for students to scan...</div>'
  }

  async function poll() {
    try {
      const res = await fetch(cfg.liveUrl)
      if (!res.ok) return
      const data = await res.json()
      if (presentEl) presentEl.textContent = data.present
      if (tokenDisp) tokenDisp.textContent = data.currentCode
      if (copyBtn) copyBtn.dataset.token = data.currentCode
      renderList(data.attendees)
      if (!data.active) location.reload()
    } catch (e) { /* network hiccup — try again next tick */ }
  }
  poll()
  setInterval(poll, 2000)

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const token = copyBtn.dataset.token || ''
      navigator.clipboard?.writeText(token).then(() => toast('Token copied!', 'ok')).catch(() => toast(token, 'info'))
    })
  }
})()
