// Small, purposeful motion: fly-to-cart, a confetti burst for a placed order,
// scroll reveals and a gentle 3-D tilt. Everything is skipped for people who
// ask their system for reduced motion.
import { useEffect, useRef } from 'react'

export const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches

// A coloured "+1" chip flies from the button to the cart icon in the header,
// then the cart badge gives a little bounce. Resolves when the chip lands.
export function flyToCart(fromEl, hue = 262) {
  const target = document.querySelector('[data-cart-icon]')
  if (!fromEl || !target || reducedMotion() || !document.body.animate) { bumpCart(); return Promise.resolve() }
  const a = fromEl.getBoundingClientRect()
  const b = target.getBoundingClientRect()
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2
  const x1 = b.left + b.width / 2, y1 = b.top + b.height / 2
  const cx = (x0 + x1) / 2 + (x1 > x0 ? -60 : 60), cy = Math.min(y0, y1) - 140   // arc control point
  const chip = document.createElement('div')
  chip.className = 'fly-chip'
  chip.textContent = '+1'
  chip.style.background = `linear-gradient(135deg, hsl(${hue} 85% 58%), hsl(${(hue + 40) % 360} 90% 55%))`
  document.body.appendChild(chip)
  const frames = []
  for (let i = 0; i <= 16; i++) {
    const t = i / 16
    const x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
    const y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
    frames.push({ transform: `translate(${x - 18}px, ${y - 18}px) scale(${1.15 - 0.6 * t}) rotate(${-25 * t}deg)`, opacity: t > 0.9 ? 0.4 : 1 })
  }
  return new Promise((resolve) => {
    const anim = chip.animate(frames, { duration: 760, easing: 'cubic-bezier(.45,.05,.35,1)' })
    const done = () => { chip.remove(); bumpCart(); resolve() }
    anim.onfinish = done
    anim.oncancel = done
  })
}

export function bumpCart() {
  window.dispatchEvent(new CustomEvent('kartiq:cart-bump'))
}

// A short confetti burst in the store's colours (canvas, ~1.8 s, then removed).
export function confetti({ count = 160, duration = 1900 } = {}) {
  if (reducedMotion()) return
  const canvas = document.createElement('canvas')
  canvas.className = 'confetti'
  document.body.appendChild(canvas)
  const dpr = Math.min(2, window.devicePixelRatio || 1)
  const W = window.innerWidth, H = window.innerHeight
  canvas.width = W * dpr; canvas.height = H * dpr
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)
  const colours = ['#5b2ee8', '#ffb020', '#ff5a36', '#0b8a4f', '#ff3d7f', '#2563eb', '#c63bff']
  const parts = Array.from({ length: count }, (_, i) => {
    const fromLeft = i % 2 === 0
    const angle = (fromLeft ? -Math.PI / 3 : -2 * Math.PI / 3) + (Math.random() - 0.5) * 0.9
    const speed = 9 + Math.random() * 9
    return {
      x: fromLeft ? W * 0.15 : W * 0.85, y: H * 0.72,
      vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
      w: 6 + Math.random() * 6, h: 8 + Math.random() * 8, r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.35,
      c: colours[i % colours.length], round: Math.random() < 0.25,
    }
  })
  const t0 = performance.now()
  const tick = (now) => {
    const t = now - t0
    ctx.clearRect(0, 0, W, H)
    for (const p of parts) {
      p.vy += 0.32; p.vx *= 0.985; p.vy *= 0.985
      p.x += p.vx; p.y += p.vy; p.r += p.vr
      ctx.save()
      ctx.globalAlpha = Math.max(0, 1 - Math.max(0, t - duration * 0.6) / (duration * 0.4))
      ctx.translate(p.x, p.y); ctx.rotate(p.r)
      ctx.fillStyle = p.c
      if (p.round) { ctx.beginPath(); ctx.arc(0, 0, p.w / 2, 0, Math.PI * 2); ctx.fill() }
      else ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.r * 2)) + 2)
      ctx.restore()
    }
    if (t < duration) requestAnimationFrame(tick); else canvas.remove()
  }
  requestAnimationFrame(tick)
}

// Fade + rise into view the first time an element scrolls in.
// Content stays visible without JavaScript or IntersectionObserver.
export function useReveal() {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion() || typeof IntersectionObserver === 'undefined') return undefined
    const box = el.getBoundingClientRect()
    if (box.top < window.innerHeight * 0.92) return undefined      // already on screen: no flash
    el.classList.add('reveal')
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { el.classList.add('in'); io.disconnect() }
    }, { rootMargin: '0px 0px -8% 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return ref
}

// A card that tilts a few degrees toward the pointer, with a soft light sheen.
export function useTilt(max = 6) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion() || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return undefined
    let raf = 0
    const move = (e) => {
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        el.style.transform = `perspective(900px) rotateX(${(0.5 - py) * max}deg) rotateY(${(px - 0.5) * max}deg) translateY(-2px)`
        el.style.setProperty('--mx', `${px * 100}%`)
        el.style.setProperty('--my', `${py * 100}%`)
      })
    }
    const leave = () => { cancelAnimationFrame(raf); el.style.transform = '' }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    return () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerleave', leave); cancelAnimationFrame(raf) }
  }, [max])
  return ref
}
