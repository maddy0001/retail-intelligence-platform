// Kartiq chrome: promo strip, header (search, delivery location, account, cart), category bar, footer, toasts.
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Bell, BellRing, CheckCircle2, ChevronDown, Flame, Gift, LayoutDashboard, LogOut, MapPin, Orbit, Package, Search,
  ShieldCheck, ShoppingBag, ShoppingCart, Truck, User, Zap,
} from 'lucide-react'
import { api } from './api'
import { CategoryGlyph } from './art'
import { money, timeAgo, titleCase } from './format'
import { useApp } from './state'

export function Logo({ light = true }) {
  return (
    <Link to="/" className="logo" aria-label="Kartiq home" style={light ? undefined : { color: 'var(--ink)' }}>
      <span className="mark"><ShoppingBag size={20} color="#fff" strokeWidth={2.4} /></span>
      <span>kart<span className="iq">iq</span></span>
    </Link>
  )
}

let categoryCache = null
export function useCategories() {
  const [cats, setCats] = useState(categoryCache || [])
  useEffect(() => {
    if (categoryCache) return
    api('/api/categories').then((c) => { categoryCache = c; setCats(c) }).catch(() => {})
  }, [])
  return cats
}

function NotificationBell() {
  const { notifications, setNotifications } = useApp()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && notifications.unread > 0) {
      try { await api('/api/notifications/read', { method: 'POST' }) } catch { /* ignore */ }
      setNotifications((n) => ({ ...n, unread: 0 }))
    }
  }
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="head-link" onClick={toggle} aria-label={`Notifications, ${notifications.unread} unread`}>
        {notifications.unread > 0 ? <BellRing size={22} /> : <Bell size={22} />}
        {notifications.unread > 0 && <span className="notif-dot">{notifications.unread}</span>}
      </button>
      {open && (
        <div className="dropdown" role="dialog" aria-label="Notifications">
          <div className="head">Notifications</div>
          {notifications.items.length === 0 && <div className="empty"><span className="ic"><Bell size={26} /></span>You're all caught up.</div>}
          {notifications.items.map((n, i) => (
            <div key={n._id || i} className={`note${n.read ? '' : ' unread'}`}>
              <span className="ic">{n.kind === 'order' ? <Package size={16} /> : <Gift size={16} />}</span>
              <div>
                {n.link ? <Link to={n.link} onClick={() => setOpen(false)}><strong>{n.title}</strong></Link> : <strong>{n.title}</strong>}
                {n.body && <div className="muted">{n.body}</div>}
                <small className="muted">{timeAgo(n.created_at)}</small>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AccountMenu() {
  const { user, logout } = useApp()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  if (!user) {
    return (
      <Link to="/login" className="head-link">
        <User size={22} /><span className="lbl"><small>Hello, sign in</small><strong>Account</strong></span>
      </Link>
    )
  }
  const isAdmin = user.role === 'admin'
  const first = user.name ? user.name.split(' ')[0] : 'there'
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="head-link" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        <User size={22} /><span className="lbl"><small>Hello, {isAdmin ? 'Admin' : first}</small><strong>Account <ChevronDown size={13} style={{ verticalAlign: 'middle' }} /></strong></span>
      </button>
      {open && (
        <div className="dropdown" role="menu" style={{ width: 240 }}>
          <div className="head">{user.name}<div className="muted small" style={{ fontWeight: 500 }}>{user.email}</div></div>
          {isAdmin ? (
            <Link className="note" to="/admin" onClick={() => setOpen(false)}><span className="ic"><LayoutDashboard size={16} /></span><strong>Operations</strong></Link>
          ) : (
            <>
              <Link className="note" to="/account" onClick={() => setOpen(false)}><span className="ic"><User size={16} /></span><strong>Your account</strong></Link>
              <Link className="note" to="/orders" onClick={() => setOpen(false)}><span className="ic"><Package size={16} /></span><strong>Your orders</strong></Link>
            </>
          )}
          <button className="note" style={{ width: '100%', border: 0, background: 'none', cursor: 'pointer', textAlign: 'left' }}
            onClick={() => { setOpen(false); logout(); navigate('/') }}>
            <span className="ic"><LogOut size={16} /></span><strong>Sign out</strong>
          </button>
        </div>
      )}
    </div>
  )
}

// The cart badge bounces when an added item "lands" (see motion.flyToCart).
function useCartBump() {
  const [bump, setBump] = useState(0)
  useEffect(() => {
    const on = () => setBump((b) => b + 1)
    window.addEventListener('kartiq:cart-bump', on)
    return () => window.removeEventListener('kartiq:cart-bump', on)
  }, [])
  return bump
}

export function Header() {
  const { user, customer, cartCount, freeDeliveryMin } = useApp()
  const bump = useCartBump()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const cats = useCategories()
  const [q, setQ] = useState(params.get('q') || '')
  const [cat, setCat] = useState(params.get('category') || '')
  useEffect(() => {
    if (location.pathname === '/search') { setQ(params.get('q') || ''); setCat(params.get('category') || '') }
  }, [location.pathname, params])
  const submit = (e) => {
    e.preventDefault()
    const qs = new URLSearchParams()
    if (q.trim()) qs.set('q', q.trim())
    if (cat) qs.set('category', cat)
    navigate(`/search${qs.toString() ? `?${qs}` : ''}`)
  }
  const isAdmin = user && user.role === 'admin'
  return (
    <>
      <div className="promo-strip">
        <div className="container">
          <span><Truck size={15} /> FREE delivery on orders over {money(freeDeliveryMin)}</span>
          <span><Zap size={15} /> Live order tracking</span>
          <span><Gift size={15} /> 10% off your first order: WELCOME10</span>
        </div>
      </div>
      <header className="header">
        <div className="container header-main">
          <Logo />
          {!isAdmin && (
            <Link to={user ? '/account' : '/login'} className="deliver-to">
              <MapPin size={20} />
              <span><small>Deliver to {user ? user.name.split(' ')[0] : ''}</small>
                <strong>{customer && customer.city ? `${titleCase(customer.city)}${customer.state ? ` ${customer.state}` : ''}` : 'Brazil'}</strong></span>
            </Link>
          )}
          <form className="searchbar" onSubmit={submit} role="search">
            <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Search in category">
              <option value="">All</option>
              {cats.map((c) => <option key={c.category} value={c.category}>{c.label}</option>)}
            </select>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search Kartiq" aria-label="Search" />
            <button type="submit" aria-label="Search"><Search size={22} strokeWidth={2.4} /></button>
          </form>
          <nav className="head-actions">
            {isAdmin && <Link to="/admin" className="head-link"><LayoutDashboard size={22} /><span className="lbl"><small>Store</small><strong>Operations</strong></span></Link>}
            {user && <NotificationBell />}
            <AccountMenu />
            {!isAdmin && (
              <Link to={user ? '/orders' : '/login?next=/orders'} className="head-link">
                <Package size={22} /><span className="lbl"><small>Returns &</small><strong>Orders</strong></span>
              </Link>
            )}
            {!isAdmin && (
              <Link to={user ? '/cart' : '/login?next=/cart'} className="head-link" aria-label={`Cart, ${cartCount} items`}>
                <span className={`cart-ic${bump ? ' bump' : ''}`} key={`i${bump}`} data-cart-icon><ShoppingCart size={26} /></span>
                {cartCount > 0 && <span className={`cart-count${bump ? ' bump' : ''}`} key={`c${bump}`}>{cartCount}</span>}
                <span className="lbl"><strong>Cart</strong></span>
              </Link>
            )}
          </nav>
        </div>
      </header>
      <div className="catbar">
        <div className="container">
          <Link to="/deals" className="deals"><Flame size={16} /> Today's deals</Link>
          <Link to="/how-it-works" className="how"><Orbit size={16} /> How Kartiq works</Link>
          {cats.slice(0, 14).map((c) => (
            <Link key={c.category} to={`/search?category=${c.category}`}><CategoryGlyph category={c.category} size={16} /> {c.label}</Link>
          ))}
        </div>
      </div>
    </>
  )
}

export function Footer() {
  const { store } = useApp()
  return (
    <footer className="footer">
      <div className="container top">
        <div>
          <Logo />
          <p style={{ marginTop: 12 }}>Smart shopping, live. Real products and genuine reviews, with offers and order updates that follow you in real time.</p>
          <div className="row" style={{ gap: 14, marginTop: 10 }}>
            <span className="row" style={{ gap: 6 }}><ShieldCheck size={16} /> Secure checkout</span>
            <span className="row" style={{ gap: 6 }}><CheckCircle2 size={16} /> Real reviews</span>
          </div>
        </div>
        <div>
          <h4>Shop</h4>
          <Link to="/deals">Today's deals</Link>
          <Link to="/search?sort=rating">Top rated</Link>
          <Link to={`/search?max_price=${store.budget_max || 999}&sort=popular`}>Under {money(store.budget_max || 999)}</Link>
          <Link to="/search">All categories</Link>
          <Link to="/how-it-works">How Kartiq works</Link>
        </div>
        <div>
          <h4>Your account</h4>
          <Link to="/account">Your account</Link>
          <Link to="/orders">Your orders</Link>
          <Link to="/cart">Your cart</Link>
          <Link to="/signup">Create an account</Link>
        </div>
        <div>
          <h4>About this store</h4>
          <p className="small">Catalogue, orders and reviews are the real Olist Brazilian e-commerce dataset (2016–2018). Olist publishes no product names or
            photos, so names are derived from category and id, and artwork shows the category. M.R.P. is the highest price a product really sold for.
            Prices are in rupees, converted from the catalogue's Brazilian reais at a fixed ₹{Number(store.inr_per_brl || 17.8).toFixed(2)} per R$1.
            Payments and deliveries are simulated.</p>
        </div>
      </div>
      <div className="container bottom spread">
        <span>© Kartiq · CLA-2 MongoDB Application Development · 21CSE562T SQL and NoSQL for Data Science</span>
        <span>MongoDB · FastAPI · React</span>
      </div>
    </footer>
  )
}

export function Toasts() {
  const { toasts } = useApp()
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div className="toast" key={t.id}>
          <span className="ic"><CheckCircle2 size={17} /></span>
          <div><strong>{t.title}</strong>{t.body}</div>
        </div>
      ))}
    </div>
  )
}
