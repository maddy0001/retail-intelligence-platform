import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CreditCard, Home as HomeIcon, MapPin, Package, ShieldAlert, Truck } from 'lucide-react'
import { api } from '../api'
import { Art } from '../art'
import { ErrorBox, Spinner, StatusBadge } from '../components'
import { dateTime, money, shortId, titleCase } from '../format'
import { confetti } from '../motion'
import { useApp, useLive } from '../state'

const STEPS = [['processing', 'Ordered', Package], ['shipped', 'Shipped', Truck], ['delivered', 'Delivered', HomeIcon]]

function Tracker({ status }) {
  if (status === 'canceled' || status === 'unavailable') return <p style={{ margin: 0 }}><StatusBadge status={status} /> This order was {status}.</p>
  if (status === 'under_review') {
    return <div className="row" style={{ color: 'var(--coral-600)', fontWeight: 600 }}><ShieldAlert size={20} />
      We're doing a quick security check before we prepare this order. You'll be notified here the moment it's approved.</div>
  }
  const idx = Math.max(0, STEPS.findIndex(([s]) => s === (status === 'invoiced' || status === 'approved' ? 'processing' : status)))
  return (
    <div className="tracker" aria-label={`Order status: ${status}`} style={{ '--progress': idx / (STEPS.length - 1) }}>
      <div className="tracker-line"><span /></div>
      {STEPS.map(([s, label, Icon], i) => (
        <div key={s} className={`s${i <= idx ? ' done' : ''}${i === idx && status !== 'delivered' ? ' now' : ''}`} style={{ '--i': i }}>
          <span className="pin"><Icon size={20} /></span>{label}
        </div>
      ))}
    </div>
  )
}

export default function OrderDetail() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const { toast } = useApp()
  const [order, setOrder] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => api(`/api/orders/${id}`).then(setOrder).catch(setError), [id])
  useEffect(() => { load() }, [load])
  const celebrated = useRef(false)
  useEffect(() => {      // a short confetti burst the first time a just-placed order is shown
    if (order && params.get('placed') && !celebrated.current) { celebrated.current = true; setTimeout(() => confetti(), 250) }
  }, [order, params])
  useLive((msg) => { if (msg.type === 'order_status' && msg.order_id === id) load() })

  const cancel = async () => {
    if (!window.confirm('Cancel this order?')) return
    setBusy(true)
    try { setOrder(await api(`/api/orders/${id}/cancel`, { method: 'POST' })); toast('Order canceled') }
    catch (e) { setError(e) } finally { setBusy(false) }
  }

  if (error) return <ErrorBox error={error} />
  if (!order) return <Spinner />
  const pay = order.payment || {}
  const addr = order.shipping_address
  const isApp = order.source === 'app'
  return (
    <div className="stack">
      {params.get('placed') && (
        <div className="success placed">
          <svg className="check-draw" viewBox="0 0 30 30" aria-hidden="true"><circle cx="15" cy="15" r="15" /><path d="M8.5 15.5l4.2 4.2L21.5 11" /></svg>
          <span><strong>Order placed, thank you!</strong> This page updates by itself as your order moves.</span>
        </div>
      )}
      <div className="spread">
        <div>
          <h1>Order #{shortId(order.id)}</h1>
          <span className="muted small">Placed {dateTime(order.placed_at)}{!isApp ? ' · past order from the Olist dataset' : ''}</span>
        </div>
        <div className="row">{isApp && <span className="live-pill">Live</span>}<StatusBadge status={order.status} /></div>
      </div>

      <div className="card pad-lg">
        <Tracker status={order.status} />
        {order.status_history && order.status_history.length > 0 && (
          <ul className="timeline" style={{ marginTop: 14 }}>
            {[...order.status_history].reverse().map((h, i) => (
              <li key={i}><StatusBadge status={h.status} /><span>{h.note}</span><span className="muted small" style={{ marginLeft: 'auto' }}>{dateTime(h.at)}</span></li>
            ))}
          </ul>
        )}
        {!isApp && order.timeline && (
          <p className="muted small" style={{ margin: '10px 0 0' }}>Delivered {dateTime(order.timeline.delivered_at)} · estimated {dateTime(order.timeline.estimated_delivery_at)}</p>
        )}
      </div>

      <div className="cart-layout">
        <div className="card">
          {order.line_items.map((li) => (
            <div className="cart-item" key={li.product_id}>
              <Link to={`/product/${li.product_id}`}><Art category={li.category} size={36} /></Link>
              <div>
                <Link to={`/product/${li.product_id}`} style={{ color: 'var(--ink)', fontWeight: 700 }}>{li.name || li.category_label || titleCase(li.category)}</Link>
                <div className="small muted">Qty {li.quantity} · {money(li.unit_price)} each</div>
                {order.status === 'delivered' && isApp && <Link className="btn outline sm" style={{ marginTop: 10 }} to={`/product/${li.product_id}`}>Write a review</Link>}
              </div>
              <strong>{money(li.unit_price * li.quantity)}</strong>
            </div>
          ))}
        </div>
        <aside className="card summary">
          <h3 style={{ marginBottom: 10 }}>Order summary</h3>
          {order.items_total !== null && order.items_total !== undefined && <div className="line"><span>Items</span><span>{money(order.items_total)}</span></div>}
          {order.freight_total !== null && order.freight_total !== undefined && <div className="line"><span>Delivery</span><span>{order.freight_total === 0 ? <strong style={{ color: 'var(--green)' }}>FREE</strong> : money(order.freight_total)}</span></div>}
          {order.discount && <div className="line" style={{ color: 'var(--green)', fontWeight: 700 }}><span>Code {order.discount.code}</span><span>−{money(order.discount.amount)}</span></div>}
          <div className="line total"><span>Paid</span><span>{money(order.total)}</span></div>
          <div className="row small" style={{ marginTop: 14, alignItems: 'flex-start', flexWrap: 'nowrap' }}><CreditCard size={16} color="var(--muted)" />
            <span>{titleCase(pay.type || '')}{pay.card ? ` · ${titleCase(pay.card.brand)} ending ${pay.card.last4}` : ''}{pay.installments > 1 ? ` · ${pay.installments} installments` : ''}
              {pay.simulated && <span className="muted"> · simulated ({pay.transaction_id})</span>}</span></div>
          {addr && <div className="row small" style={{ marginTop: 10, alignItems: 'flex-start', flexWrap: 'nowrap' }}><MapPin size={16} color="var(--muted)" />
            <span><strong>{addr.name}</strong><br />{addr.street}<br />{addr.city} – {addr.state}, {addr.zip}</span></div>}
          {order.can_cancel && <button className="btn danger block" style={{ marginTop: 16 }} onClick={cancel} disabled={busy}>Cancel order</button>}
        </aside>
      </div>
    </div>
  )
}
