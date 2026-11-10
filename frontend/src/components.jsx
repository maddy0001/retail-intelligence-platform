// Shared building blocks: price block, product cards, rails, stars, badges, small charts.
import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, ChevronLeft, ChevronRight, PackageOpen, ShoppingCart, Star } from 'lucide-react'
import { api } from './api'
import { Art, categoryTheme } from './art'
import { deliveryDate, money, priceParts } from './format'
import { flyToCart } from './motion'
import { useApp } from './state'

// Big price with a small raised ₹ and paise: ₹1,600 or ₹12.95
export function Price({ value, size = 'md' }) {
  if (value === null || value === undefined) return <span className="muted">Unavailable</span>
  const { int, paise } = priceParts(value)
  return (
    <span className={`price ${size}`} aria-label={money(value)}>
      <span className="cur">₹</span><span className="int">{int}</span>{paise && <span className="cents">.{paise}</span>}
    </span>
  )
}

export function MrpLine({ mrp, discount, size }) {
  if (!mrp || !discount) return null
  return (
    <>
      <span className="mrp">M.R.P: <s>{money(mrp)}</s></span>
      <span className="off" style={size === 'lg' ? { color: 'var(--ink)', fontWeight: 500 } : undefined}>({discount}% off)</span>
    </>
  )
}

export function PlusBadge() {
  return (
    <span className="plus-badge" title="Kartiq Plus: free delivery on every order">
      <span className="tick"><Check size={15} strokeWidth={3.2} /></span><span className="word">plus</span>
    </span>
  )
}

export function useDeliveryFree(price) {
  const { isPlus, freeDeliveryMin } = useApp()
  return isPlus || (price || 0) >= freeDeliveryMin
}

export function DeliveryLine({ price, days }) {
  const free = useDeliveryFree(price)
  return (
    <div className="delivery">
      {free ? <><span className="free">FREE delivery</span> <strong>{deliveryDate(days)}</strong></>
        : <>Get it by <strong>{deliveryDate(days)}</strong></>}
    </div>
  )
}

// The product-page price block, laid out like a big marketplace: price, M.R.P., % off,
// an offer line, the membership badge, and the delivery promise.
export function PriceBlock({ product, compact = false }) {
  const { offer, isPlus, freeDeliveryMin } = useApp()
  const free = useDeliveryFree(product.price)
  const offerText = offer ? `Extra ${offer.discount_pct ? `${offer.discount_pct}% off` : 'savings'} with code ${offer.code}${offer.min_subtotal ? ` on orders over ${money(offer.min_subtotal)}` : ''}`
    : 'Extra 10% off your first order with code WELCOME10'
  if (compact) {
    return (
      <div className="price-block">
        <div className="price-row"><Price value={product.price} size="md" /></div>
        {product.mrp ? <div className="price-row" style={{ marginTop: 4 }}><MrpLine mrp={product.mrp} discount={product.discount_pct} /></div> : null}
      </div>
    )
  }
  return (
    <div className="price-block lg">
      <div className="price-row lg">
        <Price value={product.price} size="lg" />
        <MrpLine mrp={product.mrp} discount={product.discount_pct} size="lg" />
      </div>
      <div className="offer-line" title={offerText}>{offerText}</div>
      <PlusBadge />
      <div className="delivery">
        {free ? <><span className="free" style={{ fontWeight: 500, color: 'var(--ink)' }}>FREE delivery</span> <strong>{deliveryDate(product.delivery_days)}</strong></>
          : <>{money(product.freight)} delivery <strong>{deliveryDate(product.delivery_days)}</strong></>}
      </div>
      {!free && !isPlus && <div className="muted small" style={{ marginTop: 4 }}>FREE delivery on orders over {money(freeDeliveryMin)}, or always with Kartiq Plus</div>}
    </div>
  )
}

export function Stars({ value, count, showValue = false, size = 14 }) {
  if (value === null || value === undefined) return <span className="muted small">No ratings yet</span>
  return (
    <span className="stars" title={`${value.toFixed(1)} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} size={size} strokeWidth={0} fill={i <= Math.round(value) ? 'currentColor' : '#e3e0ea'} />
      ))}
      {showValue && <span className="val">{value.toFixed(1)}</span>}
      {count !== undefined && <span className="count">{count.toLocaleString('en-IN')}</span>}
    </span>
  )
}

export function AddToCartButton({ productId, category, label = 'Add to cart', className = 'btn sm block', quantity = 1, onAdded }) {
  const { user, refreshCart, toast } = useApp()
  const navigate = useNavigate()
  const [state, setState] = useState('idle')      // idle | busy | added
  if (user && user.role === 'admin') return null
  const add = async (e) => {
    e.preventDefault(); e.stopPropagation()
    if (!user) { navigate(`/login?next=/product/${productId}`); return }
    const button = e.currentTarget
    setState('busy')
    try {
      await api('/api/cart/items', { method: 'POST', body: { product_id: productId, quantity } })
      setState('added')
      if (onAdded) onAdded(); else toast('Added to cart', 'Ready when you are.')
      await flyToCart(button, categoryTheme(category || '').hue)
      await refreshCart()
      setTimeout(() => setState('idle'), 1100)
    } catch (err) { toast('Could not add to cart', err.message); setState('idle') }
  }
  return (
    <button className={`${className}${state === 'added' ? ' added' : ''}`} onClick={add} disabled={state === 'busy'}>
      {state === 'added' ? <><Check size={16} strokeWidth={3} />Added</> : <><ShoppingCart size={16} />{state === 'busy' ? 'Adding…' : label}</>}
    </button>
  )
}

export function ProductCard({ p, note }) {
  return (
    <div className="pcard">
      <Link to={`/product/${p.product_id}`} className="pcard-link">
        <div className="media">
          {p.discount_pct ? <span className="deal-tag">{p.discount_pct}% off</span> : null}
          <Art category={p.category} size={54} />
          <span className="cat-tag">{p.category_label}</span>
        </div>
        <div className="body">
          <span className="name">{p.name}</span>
          <Stars value={p.rating_avg} count={p.review_count} />
          <div className="price-row" style={{ marginTop: 2 }}>
            <Price value={p.price} size="md" />
          </div>
          {p.mrp ? <div className="price-row"><MrpLine mrp={p.mrp} discount={p.discount_pct} /></div> : null}
          <DeliveryLine price={p.price} days={p.delivery_days} />
          {note && <span className="why">{note}</span>}
        </div>
      </Link>
      <div className="add"><AddToCartButton productId={p.product_id} category={p.category} /></div>
    </div>
  )
}

export function ProductGrid({ items, noteFor }) {
  if (!items) return <SkeletonGrid />
  if (items.length === 0) return <Empty title="Nothing here yet" text="Try another search or category." />
  return <div className="grid-products">{items.map((p) => <ProductCard key={p.product_id} p={p} note={noteFor ? noteFor(p) : null} />)}</div>
}

export function Rail({ items, noteFor }) {
  const ref = useRef(null)
  if (!items) return <SkeletonGrid count={5} />
  if (items.length === 0) return null
  const scroll = (dir) => ref.current && ref.current.scrollBy({ left: dir * ref.current.clientWidth * 0.85, behavior: 'smooth' })
  return (
    <div className="rail-wrap">
      <button className="rail-arrow left" onClick={() => scroll(-1)} aria-label="Scroll left"><ChevronLeft size={20} /></button>
      <div className="rail" ref={ref}>
        {items.map((p) => <ProductCard key={p.product_id} p={p} note={noteFor ? noteFor(p) : null} />)}
      </div>
      <button className="rail-arrow right" onClick={() => scroll(1)} aria-label="Scroll right"><ChevronRight size={20} /></button>
    </div>
  )
}

export function SkeletonGrid({ count = 8 }) {
  return (
    <div className="grid-products" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="pcard"><div className="skel" style={{ aspectRatio: '5 / 4', borderRadius: 0 }} />
          <div className="body"><div className="skel" style={{ height: 14 }} /><div className="skel" style={{ height: 14, width: '60%' }} />
            <div className="skel" style={{ height: 26, width: '45%' }} /></div></div>
      ))}
    </div>
  )
}

export function Spinner() {
  return <div className="stack" aria-busy="true"><div className="skel" style={{ height: 180 }} /><SkeletonGrid count={4} /></div>
}

export function Empty({ title, text, action, Icon = PackageOpen }) {
  return (
    <div className="card empty">
      <span className="ic"><Icon size={30} /></span>
      <h3 style={{ color: 'var(--ink)' }}>{title}</h3>
      {text && <p style={{ margin: 0 }}>{text}</p>}
      {action}
    </div>
  )
}

const STATUS_LABEL = { under_review: 'under review' }
export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{STATUS_LABEL[status] || status}</span>
}

export function RiskBadge({ risk }) {
  if (!risk) return <span className="badge neutral">no data</span>
  return <span className={`badge ${risk}`}>{risk}</span>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="error" role="alert">{error.message || String(error)}</div>
}

export function Pager({ page, pages, onPage }) {
  if (!pages || pages <= 1) return null
  return (
    <div className="pager">
      <button className="btn outline sm" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={16} />Previous</button>
      <span className="muted small">Page {page} of {pages.toLocaleString('en-IN')}</span>
      <button className="btn outline sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next<ChevronRight size={16} /></button>
    </div>
  )
}

export function HBars({ rows, format = (v) => v.toLocaleString('en-IN') }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div>
      {rows.map((r) => (
        <div className="hbar" key={r.label}>
          <span>{r.label}</span>
          <div className="track"><div className="fill" style={{ width: `${(100 * r.value) / max}%`, background: r.color || 'var(--brand)' }} /></div>
          <span style={{ textAlign: 'right', fontWeight: 700 }}>{format(r.value)}</span>
        </div>
      ))}
    </div>
  )
}

export function LineChart({ points, height = 170, label }) {
  if (!points || points.length < 2) return <Empty title="Not enough activity yet" text="The trend appears after a few events." />
  const w = 640; const h = height; const pad = 28
  const xs = points.map((p) => +p.x); const ys = points.map((p) => p.y)
  const minX = Math.min(...xs); const maxX = Math.max(...xs); const maxY = Math.max(1, ...ys)
  const sx = (x) => pad + ((x - minX) / Math.max(1, maxX - minX)) * (w - pad * 2)
  const sy = (y) => h - pad - (y / maxY) * (h - pad * 2)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(+p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ')
  const area = `${d} L${sx(+points[points.length - 1].x).toFixed(1)},${h - pad} L${sx(+points[0].x).toFixed(1)},${h - pad} Z`
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={label}>
      <defs><linearGradient id="lc" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#5b2ee8" stopOpacity=".25" /><stop offset="1" stopColor="#5b2ee8" stopOpacity="0" /></linearGradient></defs>
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#e8e5f0" />
      <text x={pad - 6} y={pad + 4} fontSize="11" textAnchor="end" fill="#6b6680">{maxY}</text>
      <text x={pad - 6} y={h - pad} fontSize="11" textAnchor="end" fill="#6b6680">0</text>
      <path d={area} fill="url(#lc)" />
      <path d={d} fill="none" stroke="#5b2ee8" strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  )
}
