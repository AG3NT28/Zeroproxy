// ─── ZeroProxy · Shared client glue (toasts, sidebar, logout confirm) ──────────
function toast(msg, type = 'ok') {
  const existing = document.querySelector('.ax-toast')
  if (existing) existing.remove()
  const t = document.createElement('div')
  t.className = 'ax-toast ax-toast-' + type
  t.textContent = msg
  document.body.appendChild(t)
  setTimeout(() => t.classList.add('ax-toast-show'), 10)
  setTimeout(() => { t.classList.remove('ax-toast-show'); setTimeout(() => t.remove(), 300) }, 3000)
}
window.toast = toast

document.addEventListener('DOMContentLoaded', () => {
  // Surface Flask flash() messages as toasts
  const flashEl = document.getElementById('flash-messages')
  if (flashEl) {
    try {
      const messages = JSON.parse(flashEl.dataset.messages)
      messages.forEach(([category, msg], i) => setTimeout(() => toast(msg, category), i * 200))
    } catch (e) { /* no-op */ }
  }

  // Sidebar toggle (mobile)
  const sidebar = document.getElementById('sidebar')
  const overlay = document.getElementById('sidebar-overlay')
  const menuToggle = document.getElementById('menu-toggle')
  if (menuToggle && sidebar && overlay) {
    menuToggle.addEventListener('click', () => { sidebar.classList.toggle('open'); overlay.classList.toggle('show') })
    overlay.addEventListener('click', () => { sidebar.classList.remove('open'); overlay.classList.remove('show') })
  }

  // Collapse sidebar to an icon rail (desktop) — state persists across pages
  const sidebarCollapse = document.getElementById('sidebar-collapse')
  if (sidebarCollapse) {
    sidebarCollapse.addEventListener('click', () => {
      const collapsed = document.documentElement.classList.toggle('zp-sidebar-collapsed')
      try { localStorage.setItem('zp-sidebar-collapsed', collapsed ? '1' : '0') } catch (e) { /* storage unavailable */ }
    })
  }

  // User menu dropdown (topbar)
  const userMenu = document.getElementById('user-menu')
  const userTrigger = document.getElementById('user-trigger')
  if (userMenu && userTrigger) {
    userTrigger.addEventListener('click', (e) => { e.stopPropagation(); userMenu.classList.toggle('open') })
    document.addEventListener('click', (e) => { if (!userMenu.contains(e.target)) userMenu.classList.remove('open') })
  }

  // Generic [data-modal-open] / [data-modal-close] wiring for admin modals
  document.querySelectorAll('[data-modal-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = document.getElementById(btn.dataset.modalOpen)
      if (modal) modal.style.display = 'flex'
    })
  })
  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = document.getElementById(btn.dataset.modalClose)
      if (modal) modal.style.display = 'none'
    })
  })

  // [data-confirm] on forms/buttons — ask before submitting destructive actions
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('submit', (e) => { if (!confirm(el.dataset.confirm)) e.preventDefault() })
    if (el.tagName === 'BUTTON' || el.tagName === 'A') {
      el.addEventListener('click', (e) => { if (!confirm(el.dataset.confirm)) e.preventDefault() })
    }
  })
})
