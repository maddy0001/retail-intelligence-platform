// "How Kartiq works": a scroll story. The picture on the left stays pinned while
// four steps scroll past on the right; each step plays its own small animation.
// The steps describe what the app really does (events, Change Streams,
// aggregation pipelines + three models, live updates), in shoppers' words.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, Bell, CheckCircle2, Home as HomeIcon, Lamp, Lock, MousePointerClick, Package, RadioTower, ShieldCheck,
  Smartphone, Truck, Waypoints, Zap,
} from 'lucide-react'
import { reducedMotion } from '../motion'

const STEPS = [
  {
    icon: MousePointerClick, kicker: 'Step 1', title: 'You shop.',
    text: 'Every product you open, every search and every add-to-cart is saved as a small event. That is all Kartiq needs to understand what you like. Your card details are never stored.',
    tech: ['events collection', 'insert_one per action', 'write-light indexes'],
  },
  {
    icon: RadioTower, kicker: 'Step 2', title: 'Kartiq notices, instantly.',
    text: 'MongoDB tells the store the moment something changes, through a Change Stream. Your page updates itself over a live connection, so there is no refresh button anywhere in Kartiq.',
    tech: ['Change Streams', 'resume tokens', 'WebSockets'],
  },
  {
    icon: Waypoints, kicker: 'Step 3', title: 'It learns your taste.',
    text: 'Aggregation pipelines add up what 99,441 real orders say. Three small models then group shoppers with similar habits, link aisles the same people buy from, and flag unusual activity before it costs anyone money.',
    tech: ['$group · $lookup · $merge', '$setWindowFields', 'K-Means · collaborative filtering · Isolation Forest'],
  },
  {
    icon: Zap, kicker: 'Step 4', title: 'Your store updates, live.',
    text: 'Your offer, your picks and your order’s journey change while you watch. Checkout is one all-or-nothing transaction, and when your order ships you are re-scored on the spot, so a new perk can arrive the same minute.',
    tech: ['multi-document transactions', 'live re-segmentation', 'TTL notifications'],
  },
]

// ---- scene 1: a click turns into events ----------------------------------------
function SceneShop() {
  return (
    <svg viewBox="0 0 520 440" className="scene-svg" aria-hidden="true">
      <defs>
        <linearGradient id="s1img" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#f2edff" /><stop offset="1" stopColor="#dccfff" /></linearGradient>
      </defs>
      <g className="s1-card">
        <rect x="44" y="52" width="210" height="300" rx="20" fill="#fff" stroke="#e8e5f0" />
        <rect x="60" y="68" width="178" height="132" rx="14" fill="url(#s1img)" />
        <circle cx="149" cy="134" r="40" fill="#fff" opacity=".55" />
        <Lamp x={124} y={109} size={50} color="#5b2ee8" strokeWidth={1.6} />
        <rect x="60" y="216" width="150" height="11" rx="5.5" fill="#16121f" opacity=".85" />
        <rect x="60" y="234" width="96" height="9" rx="4.5" fill="#cfcadb" />
        <text x="60" y="270" className="s1-stars">★★★★★</text>
        <text x="60" y="300" className="s1-price"><tspan fontSize="13" dy="-8">₹</tspan><tspan dy="8">1,600</tspan></text>
        <g className="s1-btn">
          <rect x="60" y="314" width="178" height="26" rx="13" fill="#ffb020" />
          <text x="149" y="331" textAnchor="middle" className="s1-btn-text">Add to cart</text>
        </g>
      </g>
      <g className="s1-cursor">
        <path d="M0 0 L0 22 L6 17 L10 27 L14 25 L10 15 L18 15 Z" fill="#16121f" stroke="#fff" strokeWidth="1.5" />
      </g>
      <text x="300" y="70" className="s-label">db.events</text>
      {[['view_product', 'Lamps & lighting'], ['add_to_cart', '₹1,600'], ['search', '“desk lamp”']].map(([type, detail], i) => (
        <g key={type} className={`s1-chip c${i}`}>
          <rect x="300" y={96 + i * 62} width="190" height="46" rx="12" fill="#fff" stroke="#e4dbff" />
          <circle cx="322" cy={119 + i * 62} r="7" fill={['#5b2ee8', '#ffb020', '#0b8a4f'][i]} />
          <text x="338" y={115 + i * 62} className="s1-chip-type">{type}</text>
          <text x="338" y={131 + i * 62} className="s1-chip-detail">{detail}</text>
        </g>
      ))}
      <path d="M254 200 C 275 200, 280 150, 298 130" className="s1-flow" />
    </svg>
  )
}

// ---- scene 2: the database speaks up (Change Stream -> your screen) --------------
function SceneStream({ active }) {
  const ref = useRef(null)
  useEffect(() => {
    const svg = ref.current
    if (!svg || !svg.pauseAnimations) return
    if (active && !reducedMotion()) svg.unpauseAnimations(); else svg.pauseAnimations()
  }, [active])
  const toDb = 'M92 228 C 150 228, 170 300, 236 300'
  const toYou = 'M300 268 C 350 240, 360 150, 420 140'
  return (
    <svg viewBox="0 0 520 440" className="scene-svg" ref={ref} aria-hidden="true">
      <g>
        <rect x="38" y="160" width="70" height="128" rx="14" fill="#fff" stroke="#e8e5f0" />
        <rect x="48" y="176" width="50" height="34" rx="7" fill="#f2edff" />
        <rect x="48" y="218" width="40" height="6" rx="3" fill="#cfcadb" />
        <rect x="48" y="230" width="28" height="6" rx="3" fill="#cfcadb" />
        <rect x="48" y="252" width="50" height="16" rx="8" fill="#ffb020" />
        <text x="73" y="312" textAnchor="middle" className="s-label">your tap</text>
      </g>
      <path d={toDb} className="s2-pipe" />
      <path d={toYou} className="s2-pipe" />
      {/* negative begin times: every dot is already somewhere on its path at the start */}
      {[0, -0.8, -1.6].map((b) => (
        <circle key={`a${b}`} r="6" fill="#ffb020" className="s2-dot">
          <animateMotion dur="2.4s" begin={`${b}s`} repeatCount="indefinite" path={toDb} />
        </circle>
      ))}
      {[-1.2, -0.4, -2.0].map((b) => (
        <circle key={`b${b}`} r="6" fill="#5b2ee8" className="s2-dot">
          <animateMotion dur="2.4s" begin={`${b}s`} repeatCount="indefinite" path={toYou} />
        </circle>
      ))}
      <g className="s2-db">
        <ellipse cx="268" cy="262" rx="44" ry="13" fill="#0b8a4f" />
        <rect x="224" y="262" width="88" height="62" fill="#0b8a4f" />
        <ellipse cx="268" cy="324" rx="44" ry="13" fill="#097443" />
        <ellipse cx="268" cy="262" rx="44" ry="13" fill="#34d399" />
        <path d="M224 284 q44 20 88 0 M224 304 q44 20 88 0" stroke="#e6f6ee" strokeOpacity=".5" fill="none" strokeWidth="2" />
        <text x="268" y="356" textAnchor="middle" className="s-label">MongoDB</text>
        <circle cx="268" cy="290" r="58" className="s2-ring" />
      </g>
      <g className="s2-bell">
        <circle cx="440" cy="132" r="30" fill="#fff" stroke="#e4dbff" />
        <Bell x={424} y={116} size={32} color="#5b2ee8" strokeWidth={1.8} />
      </g>
      <text x="440" y="186" textAnchor="middle" className="s-label">Change Stream</text>
      <g className="s2-toast">
        <rect x="306" y="374" width="196" height="52" rx="14" fill="#16121f" />
        <circle cx="330" cy="400" r="11" fill="#0b8a4f" />
        <path d="M324 400 l4 4 l8 -8" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <text x="350" y="396" className="s2-toast-title">Your order is on its way</text>
        <text x="350" y="413" className="s2-toast-text">Updated just now · no refresh</text>
      </g>
    </svg>
  )
}

// ---- scene 3: shoppers fall into groups (K-Means), aisles link up --------------
const GROUPS = [
  { label: 'High-Value Loyal', color: '#5b2ee8', cx: 140, cy: 140 },
  { label: 'Big Spender', color: '#ffb020', cx: 380, cy: 130 },
  { label: 'Bargain Browser', color: '#0b8a4f', cx: 150, cy: 320 },
  { label: 'At-Risk', color: '#ff5a36', cx: 385, cy: 320 },
]
function SceneLearn({ active }) {
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    if (!active) { setPhase(0); return undefined }
    if (reducedMotion()) { setPhase(1); return undefined }
    const t0 = setTimeout(() => setPhase(1), 500)
    const t = setInterval(() => setPhase((p) => (p ? 0 : 1)), 3600)
    return () => { clearTimeout(t0); clearInterval(t) }
  }, [active])
  const dots = useMemo(() => {
    let seed = 7
    const r = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646 }
    return Array.from({ length: 36 }, (_, i) => {
      const g = GROUPS[i % 4]
      const a = r() * Math.PI * 2, d = 12 + r() * 38
      return { g, sx: 40 + r() * 440, sy: 50 + r() * 340, cx: g.cx + Math.cos(a) * d, cy: g.cy + Math.sin(a) * d * 0.8 }
    })
  }, [])
  return (
    <svg viewBox="0 0 520 440" className={`scene-svg s3 ${phase ? 'grouped' : ''}`} aria-hidden="true">
      {GROUPS.map((g) => (
        <g key={g.label} className="s3-group">
          <circle cx={g.cx} cy={g.cy} r="66" fill={g.color} opacity=".08" />
          <text x={g.cx} y={g.cy + 86} textAnchor="middle" className="s3-label" fill={g.color}>{g.label}</text>
        </g>
      ))}
      <text x="260" y="30" textAnchor="middle" className="s-label">{phase ? 'K-Means groups shoppers with similar habits' : '96,096 real shoppers'}</text>
      {dots.map((d, i) => (
        <circle key={i} r="7" cx="0" cy="0" className="s3-dot"
          style={{ transform: `translate(${phase ? d.cx : d.sx}px, ${phase ? d.cy : d.sy}px)`, fill: phase ? d.g.color : '#b9b3c9', transitionDelay: `${(i % 12) * 30}ms` }} />
      ))}
    </svg>
  )
}

// ---- scene 4: the phone updates itself ------------------------------------------
function SceneLive() {
  return (
    <svg viewBox="0 0 520 440" className="scene-svg s4" aria-hidden="true">
      <rect x="150" y="20" width="220" height="400" rx="34" fill="#16121f" />
      <rect x="160" y="30" width="200" height="380" rx="26" fill="#f5f4fa" />
      <rect x="160" y="30" width="200" height="56" rx="26" fill="#3a199f" />
      <rect x="160" y="60" width="200" height="26" fill="#3a199f" />
      <text x="178" y="66" className="s4-logo">kart<tspan fill="#ffb020">iq</tspan></text>
      <g className="s4-offer a">
        <rect x="174" y="102" width="172" height="74" rx="14" fill="#fff3e8" stroke="#ffd9c9" />
        <text x="188" y="128" className="s4-k">WELCOME10</text>
        <text x="188" y="150" className="s4-t">10% off your first order</text>
      </g>
      <g className="s4-offer b">
        <rect x="174" y="102" width="172" height="74" rx="14" fill="#5b2ee8" />
        <text x="188" y="128" className="s4-k light">✓ plus</text>
        <text x="188" y="150" className="s4-t light">FREE delivery, every order</text>
      </g>
      <text x="176" y="210" className="s4-h">Order #8F2C1A</text>
      <line x1="196" y1="246" x2="324" y2="246" stroke="#e8e5f0" strokeWidth="6" strokeLinecap="round" />
      <line x1="196" y1="246" x2="324" y2="246" stroke="#0b8a4f" strokeWidth="6" strokeLinecap="round" className="s4-progress" />
      {[196, 260, 324].map((x, i) => <circle key={x} cx={x} cy="246" r="11" className={`s4-pin p${i}`} />)}
      <g className="s4-truck"><Truck x={-12} y={-34} size={24} color="#0b8a4f" strokeWidth={2} /></g>
      <text x="196" y="276" textAnchor="middle" className="s4-cap">Ordered</text>
      <text x="260" y="276" textAnchor="middle" className="s4-cap">Shipped</text>
      <text x="324" y="276" textAnchor="middle" className="s4-cap">Delivered</text>
      <g className="s4-toast">
        <rect x="172" y="320" width="176" height="62" rx="14" fill="#16121f" />
        <text x="188" y="345" className="s2-toast-title">New perk unlocked</text>
        <text x="188" y="364" className="s2-toast-text">You are now a Kartiq Plus member</text>
      </g>
      <g className="s4-live"><rect x="390" y="120" width="96" height="30" rx="15" fill="#e6f6ee" /><circle cx="408" cy="135" r="5" fill="#0b8a4f" className="s4-blink" /><text x="420" y="140" className="s4-live-text">Live</text></g>
      <g className="s4-side"><rect x="24" y="250" width="110" height="44" rx="12" fill="#fff" stroke="#e8e5f0" /><text x="40" y="270" className="s4-side-k">Picks for you</text><text x="40" y="285" className="s4-side-t">updated 2s ago</text></g>
    </svg>
  )
}

const SCENES = [SceneShop, SceneStream, SceneLearn, SceneLive]

export default function HowItWorks() {
  const [step, setStep] = useState(0)
  const stepRefs = useRef([])

  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setStep(Number(e.target.dataset.step)) })
    }, { rootMargin: '-48% 0px -48% 0px' })      // the step crossing the middle of the screen is "on"
    stepRefs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [])

  const go = (i) => {
    const el = stepRefs.current[i]
    if (el) el.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'center' })
  }

  return (
    <div className="hiw">
      <header className="hiw-intro">
        <span className="th-eyebrow"><span className="dot" />How Kartiq works</span>
        <h1>Smart shopping, <em>live</em>.</h1>
        <p className="lede">Kartiq reacts to what you do while you do it. Here is what happens between your tap and your next great find, in four steps.</p>
        <div className="hiw-jump">
          {STEPS.map((s, i) => (
            <button key={s.title} type="button" className={`chip${step === i ? ' on' : ''}`} onClick={() => go(i)}>
              <s.icon size={15} />{s.title.replace('.', '')}
            </button>
          ))}
        </div>
      </header>

      <div className="hiw-story">
        <div className="hiw-stage-wrap">
          <div className="hiw-stage" data-step={step}>
            {SCENES.map((Scene, i) => (
              <div key={i} className={`scene${step === i ? ' on' : ''}`} aria-hidden={step !== i}>
                <Scene active={step === i} />
              </div>
            ))}
            <div className="hiw-progress" aria-hidden="true">
              {STEPS.map((s, i) => <span key={s.title} className={i <= step ? 'on' : ''} />)}
            </div>
          </div>
        </div>
        <div className="hiw-steps">
          {STEPS.map((s, i) => (
            <section key={s.title} data-step={i} ref={(el) => { stepRefs.current[i] = el }} className={`hiw-step${step === i ? ' on' : ''}`}>
              <span className="hiw-kicker"><span className="ic"><s.icon size={18} /></span>{s.kicker}</span>
              <h2>{s.title}</h2>
              <p>{s.text}</p>
              <div className="hiw-tech" aria-label="Under the hood">
                <span className="label">Under the hood</span>
                {s.tech.map((t) => <span key={t} className="tech">{t}</span>)}
              </div>
            </section>
          ))}
        </div>
      </div>

      <section className="hiw-end">
        <div className="hiw-trust">
          <span><ShieldCheck size={18} /> Card details are never stored</span>
          <span><Lock size={18} /> Payments in this demo are simulated</span>
          <span><CheckCircle2 size={18} /> Real products and real reviews</span>
        </div>
        <h2>Ready to see it on your own orders?</h2>
        <div className="row" style={{ justifyContent: 'center', gap: 12 }}>
          <Link to="/search" className="btn lg">Start shopping <ArrowRight size={18} /></Link>
          <Link to="/" className="btn lg outline"><Smartphone size={18} />Back to your taste map</Link>
        </div>
        <p className="muted small" style={{ marginTop: 14 }}>
          <Package size={14} style={{ verticalAlign: '-2px' }} /> Ordered <ArrowRight size={12} /> <Truck size={14} style={{ verticalAlign: '-2px' }} /> Shipped <ArrowRight size={12} /> <HomeIcon size={14} style={{ verticalAlign: '-2px' }} /> Delivered, all pushed live.
        </p>
      </section>
    </div>
  )
}
