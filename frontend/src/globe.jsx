// The home page's 3-D "taste map", drawn on a <canvas> with no 3-D library.
//
// Every dot is one of the store's aisles (a product category), sized by how many
// real customers bought in it. Every line is a similarity from Module 2 (the
// collaborative-filtering model): aisles that the same shoppers buy from. That is
// the same table "Recommended for you" reads, so the animation shows the real
// reasoning: interest in one aisle ripples out to its most similar aisles.
//
// The globe turns slowly, can be dragged, and every few seconds a "cascade" starts
// from the shopper's own aisles (or the best-sellers) and lights up its neighbours.
import { useEffect, useRef } from 'react'
import { categoryTheme } from './art'

const TAU = Math.PI * 2
const CAMERA = 3.4            // camera distance in sphere radii (mild perspective)
const DRIFT = 0.09            // idle spin, radians per second
const CASCADE_EVERY = 5200    // ms between automatic cascades
const PULSE_MS = 1000         // time a pulse takes to travel one line
const GLOW_MS = 3200          // how long a reached aisle stays lit
const SILHOUETTE = CAMERA / Math.sqrt(CAMERA * CAMERA - 1)

const clamp = (v, a, b) => Math.max(a, Math.min(b, v))
const angleDiff = (a, b) => (((a - b + Math.PI) % TAU) + TAU) % TAU - Math.PI
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

function seeded(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), seed | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Place the aisles on a sphere so that similar aisles sit close together:
// springs along the similarity lines, repulsion between every pair, and every
// step projected back onto the unit sphere. Deterministic (seeded), ~10 ms.
export function layoutOnSphere(nodes, edges, iterations = 260) {
  const n = nodes.length
  const index = new Map(nodes.map((nd, i) => [nd.id, i]))
  const rand = seeded(11)
  const order = [...Array(n).keys()]
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [order[i], order[j]] = [order[j], order[i]] }
  const pos = new Float64Array(n * 3)
  order.forEach((i, k) => {                     // even start: a Fibonacci sphere
    const y = 1 - (2 * (k + 0.5)) / n
    const r = Math.sqrt(1 - y * y)
    const th = k * Math.PI * (3 - Math.sqrt(5))
    pos[i * 3] = Math.cos(th) * r; pos[i * 3 + 1] = y; pos[i * 3 + 2] = Math.sin(th) * r
  })
  const links = edges.map((e) => [index.get(e.a), index.get(e.b), e.w]).filter((e) => e[0] !== undefined && e[1] !== undefined)
  const f = new Float64Array(n * 3)
  for (let it = 0; it < iterations; it++) {
    f.fill(0)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = pos[i * 3] - pos[j * 3], dy = pos[i * 3 + 1] - pos[j * 3 + 1], dz = pos[i * 3 + 2] - pos[j * 3 + 2]
        const k = 0.010 / (dx * dx + dy * dy + dz * dz + 0.004)
        f[i * 3] += dx * k; f[i * 3 + 1] += dy * k; f[i * 3 + 2] += dz * k
        f[j * 3] -= dx * k; f[j * 3 + 1] -= dy * k; f[j * 3 + 2] -= dz * k
      }
    }
    for (const [a, b, w] of links) {
      const k = 0.05 * (0.4 + w)
      const dx = pos[b * 3] - pos[a * 3], dy = pos[b * 3 + 1] - pos[a * 3 + 1], dz = pos[b * 3 + 2] - pos[a * 3 + 2]
      f[a * 3] += dx * k; f[a * 3 + 1] += dy * k; f[a * 3 + 2] += dz * k
      f[b * 3] -= dx * k; f[b * 3 + 1] -= dy * k; f[b * 3 + 2] -= dz * k
    }
    const step = 0.08 + 0.9 * (1 - it / iterations)
    for (let i = 0; i < n; i++) {
      let mx = f[i * 3] * step, my = f[i * 3 + 1] * step, mz = f[i * 3 + 2] * step
      const m = Math.hypot(mx, my, mz)
      if (m > 0.12) { mx *= 0.12 / m; my *= 0.12 / m; mz *= 0.12 / m }
      const x = pos[i * 3] + mx, y = pos[i * 3 + 1] + my, z = pos[i * 3 + 2] + mz
      const len = Math.hypot(x, y, z) || 1
      pos[i * 3] = x / len; pos[i * 3 + 1] = y / len; pos[i * 3 + 2] = z / len
    }
  }
  return pos
}

// A point along the great circle from a to b, lifted off the surface like a flight path.
function arcPoint(pos, a, b, t, out) {
  const ax = pos[a * 3], ay = pos[a * 3 + 1], az = pos[a * 3 + 2]
  const bx = pos[b * 3], by = pos[b * 3 + 1], bz = pos[b * 3 + 2]
  const dot = clamp(ax * bx + ay * by + az * bz, -1, 1)
  const om = Math.acos(dot)
  const so = Math.sin(om)
  let k1 = 1 - t, k2 = t
  if (so > 1e-3) { k1 = Math.sin((1 - t) * om) / so; k2 = Math.sin(t * om) / so }
  let x = k1 * ax + k2 * bx, y = k1 * ay + k2 * by, z = k1 * az + k2 * bz
  const len = Math.hypot(x, y, z) || 1
  const lift = 1 + Math.min(0.2, 0.09 * om) * Math.sin(Math.PI * t)
  out[0] = (x / len) * lift; out[1] = (y / len) * lift; out[2] = (z / len) * lift
  return out
}

export default function TasteGlobe({ graph, onCascade, onPick, label = 'Map of Kartiq aisles' }) {
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const tipRef = useRef(null)
  const callbacks = useRef({})
  callbacks.current = { onCascade, onPick }

  useEffect(() => {
    if (!graph || !graph.nodes || graph.nodes.length === 0) return undefined
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    const tip = tipRef.current
    const ctx = canvas.getContext('2d')
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const nodes = graph.nodes
    const N = nodes.length
    const index = new Map(nodes.map((n, i) => [n.id, i]))
    const pos = layoutOnSphere(nodes, graph.edges)
    const edges = graph.edges.map((e) => ({ a: index.get(e.a), b: index.get(e.b), w: e.w }))
      .filter((e) => e.a !== undefined && e.b !== undefined)
    const adj = Array.from({ length: N }, () => [])
    edges.forEach((e) => { adj[e.a].push([e.b, e.w]); adj[e.b].push([e.a, e.w]) })
    adj.forEach((list) => list.sort((x, y) => y[1] - x[1]))
    const maxBuyers = Math.max(1, ...nodes.map((n) => n.buyers))
    const hue = nodes.map((n) => categoryTheme(n.id).hue)
    const baseR = nodes.map((n) => 2.6 + 7.4 * Math.sqrt(n.buyers / maxBuyers))
    const byBuyers = [...nodes.keys()].sort((a, b) => nodes[b].buyers - nodes[a].buyers)
    const alwaysLabel = new Set(byBuyers.slice(0, 7))
    const ids = (list) => (list || []).map((id) => index.get(id)).filter((i) => i !== undefined)
    const focus = ids(graph.focus)
    const picks = new Set(ids(graph.recommended))
    const cycle = [...new Set([...focus, ...picks, ...byBuyers.slice(0, 12)])]

    const view = { yaw: 0.5, pitch: 0.34, vyaw: 0, vpitch: 0, targetYaw: null, targetPitch: 0, w: 0, h: 0, dpr: 1, hover: -1 }
    const proj = new Float64Array(N * 4)   // x, y, depth, scale for every aisle
    const lit = new Float64Array(N).fill(-1e9)
    const litEdge = new Map()               // "a-b" -> time the pulse arrived
    let pulses = []
    let visited = new Set()
    let seq = 0
    let cycleAt = 0
    let nextAuto = performance.now() + 700
    let raf = 0
    let running = false
    let last = performance.now()
    const tmp = [0, 0, 0]

    function resize() {
      const r = wrap.getBoundingClientRect()
      view.w = Math.max(1, r.width); view.h = Math.max(1, r.height)
      view.dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(view.w * view.dpr); canvas.height = Math.round(view.h * view.dpr)
      canvas.style.width = `${view.w}px`; canvas.style.height = `${view.h}px`
      if (!running) draw(performance.now())
    }

    function startCascade(i, now, auto) {
      if (i === undefined || i < 0) return
      seq += 1
      visited = new Set([i])
      lit[i] = now
      pulses = []
      const first = adj[i].slice(0, 3)
      first.forEach(([j], k) => pulses.push({ a: i, b: j, t0: now + 300 + k * 140, gen: 1, seq }))
      const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2]
      view.targetYaw = -Math.atan2(x, z)
      view.targetPitch = clamp(Math.atan2(y, Math.hypot(x, z)) * 0.85 + 0.12, -0.75, 0.9)
      if (reduced) {           // no travelling pulses: light the neighbours straight away
        view.yaw = view.targetYaw; view.pitch = view.targetPitch; view.targetYaw = null
        first.forEach(([j]) => { lit[j] = now; litEdge.set(`${i}-${j}`, now) })
        pulses = []
      }
      const cb = callbacks.current.onCascade
      if (cb) cb({ source: nodes[i], neighbours: first.map(([j]) => nodes[j]), auto, picked: picks.has(i) })
    }

    function nextSource() {
      const i = cycle[cycleAt % cycle.length]
      cycleAt += 1
      return i
    }

    function advance(now) {
      for (const p of pulses) {
        if (p.done || now < p.t0 + PULSE_MS) continue
        p.done = true
        if (p.seq !== seq) continue
        litEdge.set(`${p.a}-${p.b}`, now)
        if (visited.has(p.b)) continue
        visited.add(p.b)
        lit[p.b] = now
        if (p.gen < 2) {
          adj[p.b].filter(([j]) => !visited.has(j)).slice(0, 2)
            .forEach(([j], k) => pulses.push({ a: p.b, b: j, t0: now + 90 + k * 160, gen: p.gen + 1, seq }))
        }
      }
      pulses = pulses.filter((p) => !p.done)
    }

    function draw(now) {
      const { w, h, dpr } = view
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const cx = w / 2, cy = h / 2
      const R = Math.min(w * 0.42, h * 0.43)
      const cyw = Math.cos(view.yaw), syw = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch)
      const project = (x, y, z, out) => {
        const x1 = x * cyw + z * syw, z1 = -x * syw + z * cyw
        const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp
        const s = CAMERA / (CAMERA - z2)
        out[0] = cx + x1 * R * s; out[1] = cy - y2 * R * s; out[2] = z2; out[3] = s
        return out
      }

      // the globe itself: a lit sphere with a soft rim
      const body = ctx.createRadialGradient(cx - R * 0.38, cy - R * 0.42, R * 0.08, cx, cy, R * SILHOUETTE)
      body.addColorStop(0, 'rgba(255,255,255,1)')
      body.addColorStop(0.62, 'rgba(244,240,255,0.92)')
      body.addColorStop(1, 'rgba(222,212,255,0.9)')
      ctx.fillStyle = body
      ctx.beginPath(); ctx.arc(cx, cy, R * SILHOUETTE, 0, TAU); ctx.fill()
      ctx.strokeStyle = 'rgba(91,46,232,0.16)'; ctx.lineWidth = 1; ctx.stroke()

      // latitude rings give the sphere its shape as it tilts
      const p0 = [0, 0, 0, 0], p1 = [0, 0, 0, 0]
      for (const lat of [-0.62, 0, 0.62]) {
        const ry = Math.sin(lat), rr = Math.cos(lat)
        for (let k = 0; k < 72; k++) {
          const a0 = (k / 72) * TAU, a1 = ((k + 1) / 72) * TAU
          project(Math.cos(a0) * rr, ry, Math.sin(a0) * rr, p0)
          project(Math.cos(a1) * rr, ry, Math.sin(a1) * rr, p1)
          const d = (p0[2] + 1) / 2
          ctx.strokeStyle = `rgba(91,46,232,${0.025 + 0.085 * d * d})`
          ctx.beginPath(); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]); ctx.stroke()
        }
      }

      for (let i = 0; i < N; i++) {
        project(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2], p0)
        proj[i * 4] = p0[0]; proj[i * 4 + 1] = p0[1]; proj[i * 4 + 2] = p0[2]; proj[i * 4 + 3] = p0[3]
      }

      // similarity lines, as arcs over the surface
      ctx.lineCap = 'round'
      const SEG = 14
      for (const e of edges) {
        const key1 = litEdge.get(`${e.a}-${e.b}`), key2 = litEdge.get(`${e.b}-${e.a}`)
        const hit = Math.max(key1 === undefined ? -1e9 : key1, key2 === undefined ? -1e9 : key2)
        const glow = clamp(1 - (now - hit) / GLOW_MS, 0, 1)
        const d = ((proj[e.a * 4 + 2] + proj[e.b * 4 + 2]) / 2 + 1) / 2
        const alpha = (0.035 + 0.2 * d ** 1.6) * (0.55 + 0.45 * e.w)
        ctx.strokeStyle = glow > 0 ? `rgba(91,46,232,${alpha + 0.55 * glow * d})` : `rgba(59,54,80,${alpha})`
        ctx.lineWidth = glow > 0 ? 1 + 1.2 * glow : 1
        ctx.beginPath()
        for (let k = 0; k <= SEG; k++) {
          arcPoint(pos, e.a, e.b, k / SEG, tmp)
          project(tmp[0], tmp[1], tmp[2], p0)
          if (k === 0) ctx.moveTo(p0[0], p0[1]); else ctx.lineTo(p0[0], p0[1])
        }
        ctx.stroke()
      }

      // aisles, back to front
      const order = [...Array(N).keys()].sort((a, b) => proj[a * 4 + 2] - proj[b * 4 + 2])
      for (const i of order) {
        const px = proj[i * 4], py = proj[i * 4 + 1], z = proj[i * 4 + 2], s = proj[i * 4 + 3]
        const d = (z + 1) / 2
        const age = now - lit[i]
        const glow = age >= 0 && age < GLOW_MS ? 1 - age / GLOW_MS : 0
        const r = baseR[i] * s * (1 + 0.5 * glow) * (i === view.hover ? 1.25 : 1)
        const a = 0.25 + 0.75 * d ** 1.3
        if (glow > 0) {
          const halo = ctx.createRadialGradient(px, py, r * 0.4, px, py, r * 3.4)
          halo.addColorStop(0, `hsla(${hue[i]}, 95%, 60%, ${0.42 * glow * a})`)
          halo.addColorStop(1, `hsla(${hue[i]}, 95%, 60%, 0)`)
          ctx.fillStyle = halo
          ctx.beginPath(); ctx.arc(px, py, r * 3.4, 0, TAU); ctx.fill()
        }
        if (age >= 0 && age < 1200) {            // arrival ripple
          const k = age / 1200
          ctx.strokeStyle = `hsla(${hue[i]}, 90%, 55%, ${(1 - k) * 0.6 * a})`
          ctx.lineWidth = 2
          ctx.beginPath(); ctx.arc(px, py, r + 3 + k * 24, 0, TAU); ctx.stroke()
        }
        ctx.fillStyle = `hsla(${hue[i]}, 74%, ${50 + 10 * glow}%, ${a})`
        ctx.beginPath(); ctx.arc(px, py, r, 0, TAU); ctx.fill()
        if (z > -0.15) { ctx.strokeStyle = `rgba(255,255,255,${0.95 * a})`; ctx.lineWidth = 1.6; ctx.stroke() }
        if (picks.has(i) && z > 0) {             // the model's picks for this shopper
          ctx.strokeStyle = `rgba(255,176,32,${a})`; ctx.lineWidth = 2
          ctx.beginPath(); ctx.arc(px, py, r + 3.5, 0, TAU); ctx.stroke()
        }
      }

      // travelling pulses with a short comet tail
      for (const p of pulses) {
        if (now < p.t0) continue
        const t = easeInOut(clamp((now - p.t0) / PULSE_MS, 0, 1))
        const TAIL = 9
        for (let k = 0; k < TAIL; k++) {
          const t0 = Math.max(0, t - 0.22 * (1 - k / TAIL)), t1 = Math.max(0, t - 0.22 * (1 - (k + 1) / TAIL))
          arcPoint(pos, p.a, p.b, t0, tmp); project(tmp[0], tmp[1], tmp[2], p0)
          arcPoint(pos, p.a, p.b, t1, tmp); project(tmp[0], tmp[1], tmp[2], p1)
          const d = (p1[2] + 1) / 2
          ctx.strokeStyle = `rgba(255,${150 + 40 * (k / TAIL)},32,${(0.1 + 0.85 * (k + 1) / TAIL) * (0.35 + 0.65 * d)})`
          ctx.lineWidth = 0.8 + 2.6 * ((k + 1) / TAIL)
          ctx.beginPath(); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]); ctx.stroke()
        }
        arcPoint(pos, p.a, p.b, t, tmp); project(tmp[0], tmp[1], tmp[2], p0)
        ctx.save()
        ctx.shadowColor = 'rgba(255,140,0,0.9)'; ctx.shadowBlur = 12
        ctx.fillStyle = '#ffb020'
        ctx.beginPath(); ctx.arc(p0[0], p0[1], 3.4 * p0[3], 0, TAU); ctx.fill()
        ctx.restore()
      }

      // labels: the biggest aisles, plus every aisle that is lit, picked or hovered
      ctx.font = '600 12px "Plus Jakarta Sans Variable", "Plus Jakarta Sans", system-ui, sans-serif'
      ctx.textBaseline = 'middle'
      const boxes = []
      for (let k = order.length - 1; k >= 0; k--) {
        const i = order[k]
        const z = proj[i * 4 + 2]
        if (z < 0.08) continue
        const age = now - lit[i]
        const isLit = age >= 0 && age < GLOW_MS
        if (!(alwaysLabel.has(i) || isLit || picks.has(i) || i === view.hover)) continue
        const px = proj[i * 4], py = proj[i * 4 + 1]
        const r = baseR[i] * proj[i * 4 + 3]
        const text = nodes[i].label
        const tw = ctx.measureText(text).width
        const pill = isLit || i === view.hover
        let bx = px + r + 7
        if (bx + tw + 12 > view.w - 4) bx = px - r - 7 - tw
        const box = [bx - 7, py - 11, tw + 14, 22]
        if (boxes.some((b) => box[0] < b[0] + b[2] && box[0] + box[2] > b[0] && box[1] < b[1] + b[3] && box[1] + box[3] > b[1])) continue
        boxes.push(box)
        const a = clamp((z - 0.08) / 0.25, 0, 1) * (pill ? 1 : 0.8)
        if (pill) {
          ctx.fillStyle = `rgba(255,255,255,${0.95 * a})`
          ctx.strokeStyle = `hsla(${hue[i]}, 70%, 55%, ${0.55 * a})`
          ctx.lineWidth = 1
          ctx.beginPath()
          if (ctx.roundRect) ctx.roundRect(box[0], box[1], box[2], box[3], 11); else ctx.rect(box[0], box[1], box[2], box[3])
          ctx.fill(); ctx.stroke()
        } else {
          ctx.strokeStyle = `rgba(255,255,255,${0.9 * a})`; ctx.lineWidth = 3.5; ctx.lineJoin = 'round'
          ctx.strokeText(text, bx, py)
        }
        ctx.fillStyle = `rgba(22,18,31,${a})`
        ctx.fillText(text, bx, py)
      }

      // keep the hover tooltip pinned to its aisle
      if (view.hover >= 0 && tip) {
        const i = view.hover
        tip.style.transform = `translate(${proj[i * 4]}px, ${proj[i * 4 + 1] - baseR[i] * proj[i * 4 + 3] - 10}px) translate(-50%, -100%)`
      }
    }

    function frame(now) {
      raf = requestAnimationFrame(frame)
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (!dragging) {
        if (view.targetYaw !== null) {
          const k = 1 - Math.exp(-dt * 2.4)
          const dy = angleDiff(view.targetYaw, view.yaw)
          view.yaw += dy * k
          view.pitch += (view.targetPitch - view.pitch) * k
          if (Math.abs(dy) < 0.003) view.targetYaw = null
        } else {
          view.yaw += (view.hover >= 0 || reduced ? 0 : DRIFT * dt) + view.vyaw
          view.pitch = clamp(view.pitch + view.vpitch, -1.1, 1.1)
          view.vyaw *= 0.93; view.vpitch *= 0.93
        }
      }
      if (now >= nextAuto) { startCascade(nextSource(), now, true); nextAuto = now + CASCADE_EVERY }
      advance(now)
      draw(now)
    }

    function start() { if (!running) { running = true; last = performance.now(); raf = requestAnimationFrame(frame) } }
    function stop() { running = false; cancelAnimationFrame(raf) }

    // ---- pointer: drag to turn, hover for a tooltip, tap an aisle to explore it
    let down = null
    let dragging = false
    const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] }
    const hitTest = (x, y) => {
      let best = -1, bestD = Infinity
      for (let i = 0; i < N; i++) {
        if (proj[i * 4 + 2] < -0.05) continue
        const d = Math.hypot(proj[i * 4] - x, proj[i * 4 + 1] - y)
        if (d < baseR[i] * proj[i * 4 + 3] + 9 && d < bestD) { best = i; bestD = d }
      }
      return best
    }
    const setHover = (i) => {
      if (i === view.hover) return
      view.hover = i
      canvas.style.cursor = i >= 0 ? 'pointer' : (dragging ? 'grabbing' : 'grab')
      if (!tip) return
      if (i < 0) { tip.classList.remove('on'); return }
      const n = nodes[i]
      tip.querySelector('strong').textContent = n.label
      tip.querySelector('span').textContent = `${n.buyers.toLocaleString('en-IN')} shoppers · ${n.products.toLocaleString('en-IN')} products`
      tip.classList.add('on')
    }
    const onDown = (e) => {
      const [x, y] = local(e)
      down = { x, y, yaw: view.yaw, pitch: view.pitch, t: performance.now(), lx: x, ly: y, lt: performance.now() }
      view.targetYaw = null
      try { canvas.setPointerCapture(e.pointerId) } catch { /* ignore */ }
    }
    const onMove = (e) => {
      const [x, y] = local(e)
      if (down) {
        const dx = x - down.x, dy = y - down.y
        if (!dragging && Math.hypot(dx, dy) > 5) { dragging = true; setHover(-1); canvas.style.cursor = 'grabbing' }
        if (dragging) {
          const now = performance.now()
          view.yaw = down.yaw + dx * 0.0085
          view.pitch = clamp(down.pitch + dy * 0.0065, -1.1, 1.1)
          const ddt = Math.max(1, now - down.lt)
          view.vyaw = ((x - down.lx) * 0.0085) * (16 / ddt)
          view.vpitch = ((y - down.ly) * 0.0065) * (16 / ddt)
          down.lx = x; down.ly = y; down.lt = now
        }
        return
      }
      if (e.pointerType === 'mouse') setHover(hitTest(x, y))
    }
    const onUp = (e) => {
      if (!down) return
      const [x, y] = local(e)
      if (!dragging) {
        const i = hitTest(x, y)
        if (i >= 0) {
          const now = performance.now()
          startCascade(i, now, false)
          nextAuto = now + CASCADE_EVERY * 2
          const cb = callbacks.current.onPick
          if (cb) cb(nodes[i])
        }
      } else {
        view.vyaw = clamp(view.vyaw, -0.08, 0.08); view.vpitch = clamp(view.vpitch, -0.05, 0.05)
      }
      dragging = false
      down = null
      canvas.style.cursor = view.hover >= 0 ? 'pointer' : 'grab'
    }
    const onLeave = () => { if (!down) setHover(-1) }

    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', onUp)
    canvas.addEventListener('pointercancel', onUp)
    canvas.addEventListener('pointerleave', onLeave)

    const ro = new ResizeObserver(resize)
    ro.observe(wrap)
    resize()
    const io = new IntersectionObserver(([entry]) => { if (entry.isIntersecting && !document.hidden) start(); else stop() })
    io.observe(wrap)
    const onVis = () => { if (document.hidden) stop(); else if (wrap.getBoundingClientRect().bottom > 0) start() }
    document.addEventListener('visibilitychange', onVis)
    canvas.style.cursor = 'grab'

    return () => {
      stop()
      ro.disconnect(); io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp)
      canvas.removeEventListener('pointercancel', onUp)
      canvas.removeEventListener('pointerleave', onLeave)
    }
  }, [graph])

  return (
    <div className="globe" ref={wrapRef}>
      <canvas ref={canvasRef} role="img" aria-label={label} />
      <div className="globe-tip" ref={tipRef} aria-hidden="true"><strong /><span /></div>
    </div>
  )
}
