// ─── Scan QR page: network/GPS verification, camera+jsQR scan, manual entry ───
;(function () {
  const cfg = window.SCAN_CONFIG
  if (!cfg) return

  const verifyCard = document.getElementById('verify-card')
  const scanCard = document.getElementById('scan-card')
  const blockedCard = document.getElementById('blocked-card')
  const recheckBtn = document.getElementById('recheck-btn')

  function delay(ms) { return new Promise(r => setTimeout(r, ms)) }

  // ─── WebRTC local IP discovery (ported from getLocalIPs in helpers.js) ───────
  async function getLocalIPs() {
    const RTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection
    if (!RTCPeerConnection) return []
    const ips = new Set()
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }], iceTransportPolicy: 'all' })
    pc.createDataChannel('ax-netcheck')
    const candidatePromise = new Promise(resolve => {
      pc.onicecandidate = (event) => {
        if (!event.candidate) { resolve(); return }
        const match = event.candidate.candidate.match(/([0-9]{1,3}(?:\.[0-9]{1,3}){3})/)
        if (match && match[1]) ips.add(match[1])
      }
    })
    try {
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      await Promise.race([candidatePromise, delay(2000)])
    } catch (e) { console.warn('IP discovery failed', e) }
    pc.close()
    return Array.from(ips)
  }

  // ─── IP allow-list matching (ported from match_ip_pattern/is_ip_allowed) ─────
  function parseIPv4(ip) {
    return ip.split('.').reduce((acc, o) => ((acc * 256) + (parseInt(o, 10) & 0xff)), 0) >>> 0
  }
  function matchIpPattern(ip, pattern) {
    if (!ip || !pattern) return false
    ip = ip.trim(); pattern = pattern.trim()
    try {
      if (pattern.includes('/')) {
        const [base, mask] = pattern.split('/')
        const prefix = parseInt(mask, 10)
        if (prefix < 0 || prefix > 32) return false
        const maskVal = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0
        return (parseIPv4(ip) & maskVal) === (parseIPv4(base) & maskVal)
      }
      if (pattern.includes('*')) {
        const regex = new RegExp('^' + pattern.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$')
        return regex.test(ip)
      }
      return ip === pattern
    } catch (e) { return false }
  }
  function isIpAllowed(ip, patterns) {
    if (!ip || !patterns || !patterns.length) return false
    return patterns.some(p => matchIpPattern(ip, p))
  }

  function haversine(lat1, lng1, lat2, lng2) {
    const r = 6371000
    const dLat = (lat2 - lat1) * Math.PI / 180
    const dLng = (lng2 - lng1) * Math.PI / 180
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  }

  // ─── Verification flow ────────────────────────────────────────────────────────
  function setStep(id, state, desc) {
    const marks = { pend: '·', chk: '⏳', ok: '✓', fail: '✕' }
    const el = document.getElementById('step-' + id)
    el.className = 'step-item ' + state
    el.querySelector('.step-ico').textContent = state === 'pend' ? (id === 'wifi' ? '📶' : '📍') : marks[state]
    el.querySelector('.step-sub').textContent = desc
  }

  async function checkNetwork() {
    const ips = await getLocalIPs()
    const matchedSource = ips.find(ip => isIpAllowed(ip, cfg.allowedPatterns))
    return { ips, allowed: Boolean(matchedSource), matchedSource: matchedSource || '' }
  }

  function checkLocation() {
    return new Promise(resolve => {
      if (!navigator.geolocation) { resolve(true); return }
      navigator.geolocation.getCurrentPosition(
        pos => resolve(haversine(pos.coords.latitude, pos.coords.longitude, cfg.collegeLat, cfg.collegeLng) <= cfg.collegeRadius),
        () => resolve(true), { timeout: 3000 }
      )
      setTimeout(() => resolve(true), 3500)
    })
  }

  async function runVerify() {
    verifyCard.style.display = 'block'
    scanCard.style.display = 'none'
    blockedCard.style.display = 'none'
    recheckBtn.style.display = 'none'
    setStep('wifi', 'chk', 'Checking network connection...')
    setStep('loc', 'pend', 'Waiting...')
    await delay(1000)
    const net = await checkNetwork()
    if (net.allowed) setStep('wifi', 'ok', `Allowed network: ${net.matchedSource}`)
    else if (!net.ips.length) setStep('wifi', 'fail', 'No local IP detected — please allow camera/network access')
    else setStep('wifi', 'fail', `No allowed IP found: ${net.ips.join(', ')}`)
    setStep('loc', 'chk', 'Getting GPS location...')
    await delay(1300)
    const locOk = await checkLocation()
    setStep('loc', locOk ? 'ok' : 'fail', locOk ? 'Inside campus boundary ✓' : 'Outside campus range — move closer')
    if (net.allowed) {
      scanCard.style.display = 'block'
    } else {
      blockedCard.style.display = 'block'
      recheckBtn.style.display = 'block'
    }
  }

  // ─── Camera scanning (jsQR) ───────────────────────────────────────────────────
  let camStream = null, scanAnimFrame = null, lastScannedToken = '', lastScanTime = 0

  function stopCam() {
    if (scanAnimFrame) { cancelAnimationFrame(scanAnimFrame); scanAnimFrame = null }
    if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null }
    const v = document.getElementById('cam-video')
    if (v) v.srcObject = null
  }

  function startScanning() {
    const video = document.getElementById('cam-video')
    if (!video) return
    if (typeof window.jsQR !== 'function') {
      toast('QR decoder failed to load — use manual mode', 'err')
      return
    }
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    function scanFrame() {
      if (!camStream) return
      // Guard the decode step — a single bad frame (e.g. zero-size canvas while
      // the camera is still warming up) must not throw and silently kill the
      // requestAnimationFrame loop, which would look like "scanning does nothing".
      try {
        if (video.readyState === video.HAVE_ENOUGH_DATA && video.videoWidth && video.videoHeight) {
          canvas.width = video.videoWidth
          canvas.height = video.videoHeight
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
          const code = window.jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'dontInvert' })
          if (code && code.data) {
            const token = code.data.toString().trim()
            if (token !== lastScannedToken || Date.now() - lastScanTime > 3000) {
              lastScannedToken = token
              lastScanTime = Date.now()
              mark(token)
            }
          }
        }
      } catch (e) { console.warn('QR decode frame skipped', e) }
      scanAnimFrame = requestAnimationFrame(scanFrame)
    }
    scanAnimFrame = requestAnimationFrame(scanFrame)
  }

  document.getElementById('cam-btn').addEventListener('click', async () => {
    document.getElementById('cam-section').style.display = 'block'
    document.getElementById('manual-section').style.display = 'none'
    document.getElementById('att-success').style.display = 'none'
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      camStream = stream
      document.getElementById('cam-video').srcObject = stream
      toast('Camera started', 'ok')
      startScanning()
    } catch (e) {
      console.error(e)
      toast('Camera unavailable — use manual mode', 'err')
    }
  })

  document.getElementById('manual-btn').addEventListener('click', () => {
    document.getElementById('manual-section').style.display = 'block'
    document.getElementById('cam-section').style.display = 'none'
    document.getElementById('att-success').style.display = 'none'
    stopCam()
  })

  document.getElementById('stop-cam-btn').addEventListener('click', () => {
    stopCam()
    document.getElementById('cam-section').style.display = 'none'
  })

  // ─── Manual entry ─────────────────────────────────────────────────────────────
  const qrInput = document.getElementById('qr-in')
  qrInput.addEventListener('input', e => {
    const code = e.target.value.trim()
    const help = document.getElementById('qr-help')
    if (/^\d{4}$/.test(code)) {
      const matched = (cfg.activeSessions || []).find(s => s.currentCode === code || s.currentToken === code)
      help.textContent = matched ? `Matched session: ${matched.code} · ${matched.dept} Sec ${matched.cls}` : 'No active session matches that code.'
    } else {
      help.textContent = 'Enter the 4-digit code, paste the QR link, or paste the raw token.'
    }
  })

  document.getElementById('mark-btn').addEventListener('click', () => {
    const raw = qrInput.value.trim()
    if (!raw) { toast('Enter a code or token', 'err'); return }
    mark(raw)
  })

  document.getElementById('scan-again-btn').addEventListener('click', () => {
    document.getElementById('att-success').style.display = 'none'
  })

  document.getElementById('retry-btn').addEventListener('click', runVerify)
  recheckBtn.addEventListener('click', runVerify)

  // ─── Server-side mark request ─────────────────────────────────────────────────
  async function mark(token) {
    try {
      const res = await fetch(cfg.markUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      const data = await res.json()
      if (data.ok) {
        document.getElementById('manual-section').style.display = 'none'
        document.getElementById('cam-section').style.display = 'none'
        document.getElementById('att-success').style.display = 'block'
        document.getElementById('att-success-detail').textContent = data.detail || ''
        stopCam()
        toast(data.message || 'Attendance marked!', 'ok')
        if (data.alert) {
          toast(data.alert.parentEmail ? `⚠ Alert sent to ${data.alert.parentEmail}` : '⚠ Parent email not set — update profile', 'warn')
        }
      } else {
        toast(data.message || 'Could not mark attendance', 'err')
      }
    } catch (e) {
      toast('Network error — try again', 'err')
    }
  }

  runVerify()
})()
