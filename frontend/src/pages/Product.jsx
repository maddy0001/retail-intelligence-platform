import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { BadgeCheck, ChevronRight, Lock, MapPin, Minus, Plus, RotateCcw, ShoppingCart, Store, Truck, Zap } from 'lucide-react'
import { api } from '../api'
import { Art } from '../art'
import { ErrorBox, PriceBlock, Rail, Spinner, Stars, useDeliveryFree } from '../components'
import { categoryTheme } from '../art'
import { flyToCart } from '../motion'
import { date, deliveryDate, initials, money, titleCase } from '../format'
import { useApp } from '../state'

function ReviewForm({ productId, onDone }) {
  const [rating, setRating] = useState(5)
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try { await api(`/api/products/${productId}/reviews`, { method: 'POST', body: { rating, title, message } }); onDone() }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <form className="card pad" onSubmit={submit} style={{ margin: '14px 0' }}>
      <h3 style={{ marginBottom: 12 }}>Write a review</h3>
      <ErrorBox error={error} />
      <div className="field">
        <label htmlFor="rating">Your rating</label>
        <select id="rating" className="input" value={rating} onChange={(e) => setRating(Number(e.target.value))}>
          {[5, 4, 3, 2, 1].map((s) => <option key={s} value={s}>{s} star{s > 1 ? 's' : ''}</option>)}
        </select>
      </div>
      <div className="field"><label htmlFor="rt">Headline</label><input id="rt" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} /></div>
      <div className="field"><label htmlFor="rm">Your review</label><textarea id="rm" rows={3} value={message} maxLength={1000} onChange={(e) => setMessage(e.target.value)} /></div>
      <button className="btn" disabled={busy}>{busy ? 'Posting…' : 'Post review'}</button>
    </form>
  )
}

export default function Product() {
  const { id } = useParams()
  const { user, refreshCart, toast } = useApp()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [qty, setQty] = useState(1)
  const [busy, setBusy] = useState(false)
  const [reviewPage, setReviewPage] = useState(1)
  const [moreReviews, setMoreReviews] = useState([])

  const load = () => api(`/api/products/${id}`).then((d) => { setData(d); setMoreReviews([]); setReviewPage(1) }).catch(setError)
  useEffect(() => { setData(null); setQty(1); load(); window.scrollTo({ top: 0 }) }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  const free = useDeliveryFree(data ? data.product.price : 0)

  const add = async (thenCheckout, button) => {
    if (!user) { navigate(`/login?next=/product/${id}`); return }
    setBusy(true)
    try {
      await api('/api/cart/items', { method: 'POST', body: { product_id: id, quantity: qty } })
      if (thenCheckout) { await refreshCart(); navigate('/checkout'); return }
      toast('Added to cart', `${qty} × ${data.product.name}`)
      await flyToCart(button, categoryTheme(data.product.category || '').hue)
      await refreshCart()
    } catch (e) { toast('Could not add to cart', e.message) } finally { setBusy(false) }
  }
  const loadMore = async () => {
    const next = reviewPage + 1
    const r = await api(`/api/products/${id}/reviews`, { params: { page: next } })
    setMoreReviews((m) => [...m, ...r.items]); setReviewPage(next)
  }

  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  const p = data.product
  const reviews = [...data.reviews.items, ...moreReviews]
  const total = data.reviews.total
  const dims = p.dimensions_cm || {}
  const isAdmin = user && user.role === 'admin'
  const seller = p.seller ? `${titleCase(p.seller.city || '')}, ${p.seller.state}` : null

  return (
    <div>
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/">Home</Link><ChevronRight size={14} /><Link to={`/search?category=${p.category}`}>{p.category_label}</Link>
        <ChevronRight size={14} /><span>{p.name}</span>
      </nav>
      <div className="product-layout">
        <div className="gallery">
          <Art category={p.category} size={150} big>
            {p.discount_pct ? <span className="deal-tag" style={{ fontSize: '.85rem' }}>{p.discount_pct}% off</span> : null}
          </Art>
          <p className="muted small" style={{ marginTop: 10 }}>Illustration of the {p.category_label} category. The public Olist dataset has no product photos.</p>
        </div>

        <div>
          <Link to={`/search?category=${p.category}`} className="seller-line">Visit the {p.category_label} store</Link>
          <h1 className="p-title">{p.name}</h1>
          <div className="row" style={{ gap: 12 }}>
            <Stars value={p.rating_avg} count={p.review_count} showValue size={17} />
            {p.sales_count > 50 && <span className="badge brand" style={{ textTransform: 'none' }}><Zap size={12} /> {p.sales_count.toLocaleString('en-IN')} bought on Olist</span>}
          </div>
          {p.discount_pct >= 20 && <span className="badge danger" style={{ marginTop: 12 }}>Limited time deal</span>}
          <hr className="divider" />
          <PriceBlock product={p} />
          <hr className="divider" />
          <div className="facts">
            <div className="fact"><small>Ships from</small><strong>{seller || '—'}</strong></div>
            <div className="fact"><small>Sold on Olist</small><strong>{(p.sales_count || 0).toLocaleString('en-IN')} units</strong></div>
            <div className="fact"><small>Weight</small><strong>{p.weight_g ? `${p.weight_g.toLocaleString('en-IN')} g` : '—'}</strong></div>
            <div className="fact"><small>Size</small><strong>{dims.length ? `${dims.length} × ${dims.width} × ${dims.height} cm` : '—'}</strong></div>
          </div>
          {p.mrp && <p className="muted small" style={{ marginTop: 12 }}>M.R.P. is the highest price this product has actually sold for on the marketplace; the % off compares it with today's price.</p>}
        </div>

        {!isAdmin && (
          <aside className="card buybox">
            <PriceBlock product={p} compact />
            <hr className="divider" />
            <div className="row" style={{ marginBottom: 12 }}><MapPin size={16} color="var(--muted)" /><span className="small">
              {free ? 'FREE delivery' : `${money(p.freight)} delivery`} by <strong>{deliveryDate(p.delivery_days)}</strong></span></div>
            <div className="row" style={{ marginBottom: 14 }}>
              <span className="small muted">Quantity</span>
              <div className="qty" aria-label="Quantity">
                <button onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label="Fewer"><Minus size={15} /></button>
                <span>{qty}</span>
                <button onClick={() => setQty((q) => Math.min(20, q + 1))} aria-label="More"><Plus size={15} /></button>
              </div>
            </div>
            <div className="stack" style={{ gap: 8 }}>
              <button className="btn block lg" onClick={(e) => add(false, e.currentTarget)} disabled={busy}><ShoppingCart size={18} />Add to cart</button>
              <button className="btn coral block lg" onClick={() => add(true)} disabled={busy} style={{ marginTop: 8 }}>Buy now</button>
            </div>
            <div className="trust">
              <div><Lock size={15} color="var(--green)" /> Secure transaction</div>
              <div><Store size={15} color="var(--brand)" /> Sold by a seller in {seller || 'Brazil'}</div>
              <div><RotateCcw size={15} color="var(--coral)" /> Free cancellation until it ships</div>
              <div><Truck size={15} color="var(--blue)" /> Live tracking from order to door</div>
            </div>
          </aside>
        )}
      </div>

      {data.also_bought.items.length > 0 && (
        <section>
          <div className="section-head"><h2>{data.also_bought.reason === 'co_purchase' ? 'Customers who bought this also bought' : `More from ${p.category_label}`}</h2></div>
          <Rail items={data.also_bought.items} />
        </section>
      )}

      <section>
        <div className="section-head"><h2>Customer reviews</h2></div>
        <div className="card pad-lg">
          <div className="rating-summary">
            <div>
              <div className="row" style={{ gap: 12 }}><span className="rating-big">{p.rating_avg ? p.rating_avg.toFixed(1) : '—'}</span>
                <div><Stars value={p.rating_avg} size={18} /><div className="muted small">{total.toLocaleString('en-IN')} global ratings</div></div></div>
              <div style={{ marginTop: 14 }}>
                {Object.entries(data.reviews.breakdown).map(([stars, n]) => (
                  <div className="bar-row" key={stars}>
                    <span className="small" style={{ fontWeight: 700 }}>{stars} star</span>
                    <div className="bar"><div style={{ width: `${total ? (100 * n) / total : 0}%` }} /></div>
                    <span className="small muted" style={{ textAlign: 'right' }}>{total ? Math.round((100 * n) / total) : 0}%</span>
                  </div>
                ))}
              </div>
              {data.can_review && <ReviewForm productId={id} onDone={() => { toast('Thanks for your review!'); load() }} />}
            </div>
            <div>
              {reviews.length === 0 && <p className="muted">No written reviews yet.</p>}
              {reviews.map((r, i) => (
                <div className="review" key={i} style={i === 0 ? { borderTop: 0, paddingTop: 0 } : undefined}>
                  <div className="who"><span className="avatar">{initials(r.author || 'Olist buyer')}</span>{r.author || 'Olist buyer'}</div>
                  <div className="row" style={{ marginTop: 6, gap: 8 }}><Stars value={r.rating} size={14} />{r.title && <strong>{r.title}</strong>}</div>
                  <div className="muted small" style={{ margin: '4px 0' }}>Reviewed on {date(r.created_at)} · <span className="verified"><BadgeCheck size={13} style={{ verticalAlign: '-2px' }} /> Verified purchase</span>
                    {r.language === 'pt' ? ' · in Portuguese' : ''}</div>
                  {r.message && <p style={{ margin: 0 }}>{r.message}</p>}
                </div>
              ))}
              {total > data.reviews.with_text && <p className="muted small" style={{ marginTop: 12 }}>{(total - data.reviews.with_text).toLocaleString('en-IN')} more buyers left a star rating without text.</p>}
              {reviews.length < data.reviews.with_text && <button className="btn outline sm" onClick={loadMore}>Show more reviews</button>}
            </div>
          </div>
        </div>
      </section>

      {!isAdmin && (
        <>
          <div className="mobile-buy">
            <button className="btn" onClick={(e) => add(false, e.currentTarget)} disabled={busy}><ShoppingCart size={16} />Add to cart</button>
            <button className="btn coral" onClick={() => add(true)} disabled={busy}>Buy now</button>
          </div>
          <div className="mobile-spacer" />
        </>
      )}
    </div>
  )
}
