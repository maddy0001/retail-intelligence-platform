import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Banknote, CreditCard, Info, Lock, Receipt, Ticket, Wallet } from 'lucide-react'
import { api } from '../api'
import { Art } from '../art'
import { ErrorBox, Spinner } from '../components'
import { deliveryDate, money, titleCase } from '../format'
import { useApp } from '../state'

const METHODS = [
  ['credit_card', 'Credit card', CreditCard], ['debit_card', 'Debit card', Wallet], ['boleto', 'Boleto', Receipt], ['voucher', 'Voucher', Ticket],
]

function Step({ n, title, children }) {
  return (
    <div className="card pad">
      <div className="step">
        <span className="num">{n}</span>
        <div className="grow"><h2 style={{ fontSize: '1.15rem', marginBottom: 14 }}>{title}</h2>{children}</div>
      </div>
    </div>
  )
}

export default function Checkout() {
  const { user, customer, offer, setCartCount, refreshMe } = useApp()
  const navigate = useNavigate()
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [couponError, setCouponError] = useState(null)
  const [coupon, setCoupon] = useState(offer ? offer.code : '')
  const [applied, setApplied] = useState('')
  const [busy, setBusy] = useState(false)
  const [ship, setShip] = useState({
    name: user ? user.name : '', street: '', city: customer && customer.city ? titleCase(customer.city) : '',
    state: (customer && customer.state) || 'SP', zip: '',
  })
  const [pay, setPay] = useState({ method: 'credit_card', installments: 1, card_number: '', card_name: '', expiry: '', cvv: '' })

  const loadPreview = async (code, silent = false) => {
    setCouponError(null)
    try {
      setPreview(await api('/api/checkout/preview', { params: { coupon_code: code || undefined } }))
      setApplied(code || '')
    } catch (e) {
      if (e.status === 400) { navigate('/cart'); return }
      if (code) {
        // The offer is tried automatically; if the cart doesn't qualify yet, just show the hint instead of an error.
        if (!silent) setCouponError(e)
        else setCoupon('')
        setPreview(await api('/api/checkout/preview')); setApplied('')
      } else setError(e)
    }
  }
  // Price the cart first; apply the shopper's offer only when the cart qualifies (no failed request for the coupon).
  useEffect(() => {
    (async () => {
      try {
        const base = await api('/api/checkout/preview')
        if (offer && base.subtotal >= (offer.min_subtotal || 0)) await loadPreview(offer.code, true)
        else { setPreview(base); setApplied(''); setCoupon('') }
      } catch (e) { if (e.status === 400) navigate('/cart'); else setError(e) }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const leave = async () => {
    // Leaving checkout with a full cart counts as an abandoned cart (watched by the Change Stream).
    try { await api('/api/events', { method: 'POST', body: { event_type: 'cart_abandon' } }) } catch { /* ignore */ }
    navigate('/cart')
  }

  const placeOrder = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    const payment = { method: pay.method, installments: pay.method === 'credit_card' ? Number(pay.installments) : 1 }
    if (pay.method.endsWith('_card')) Object.assign(payment, { card_number: pay.card_number, card_name: pay.card_name, expiry: pay.expiry, cvv: pay.cvv })
    try {
      const order = await api('/api/checkout', { method: 'POST', body: { shipping: ship, payment, coupon_code: applied || null } })
      setCartCount(0)
      refreshMe()
      navigate(`/orders/${order.id}?placed=1`)
    } catch (err) { setError(err); setBusy(false) }
  }

  if (!preview) return error ? <ErrorBox error={error} /> : <Spinner />
  const field = (obj, setObj, key, label, props = {}) => (
    <div className="field">
      <label htmlFor={key}>{label}</label>
      <input id={key} value={obj[key]} onChange={(e) => setObj({ ...obj, [key]: e.target.value })} required {...props} />
    </div>
  )
  const isCard = pay.method.endsWith('_card')
  const latest = Math.max(...preview.lines.map((l) => l.delivery_days || 10))

  return (
    <form onSubmit={placeOrder}>
      <div className="spread" style={{ marginBottom: 14 }}>
        <h1>Checkout</h1>
        <button type="button" className="btn ghost" onClick={leave}><ArrowLeft size={16} />Back to cart</button>
      </div>
      <div className="cart-layout">
        <div className="stack" style={{ marginTop: 0 }}>
          <Step n={1} title="Delivery address">
            {field(ship, setShip, 'name', 'Full name', { autoComplete: 'name' })}
            {field(ship, setShip, 'street', 'Street and number', { autoComplete: 'street-address', placeholder: 'Rua Augusta, 1500' })}
            <div className="grid-3">
              {field(ship, setShip, 'city', 'City', { autoComplete: 'address-level2' })}
              {field(ship, setShip, 'state', 'State (UF)', { maxLength: 2, autoComplete: 'address-level1' })}
              {field(ship, setShip, 'zip', 'CEP', { autoComplete: 'postal-code', placeholder: '01310-100' })}
            </div>
          </Step>
          <Step n={2} title="Payment method">
            <div className="pay-methods" role="radiogroup">
              {METHODS.map(([v, l, Icon]) => (
                <label key={v} className={pay.method === v ? 'on' : ''}>
                  <input type="radio" name="method" value={v} checked={pay.method === v} onChange={() => setPay({ ...pay, method: v })} />
                  <Icon size={22} />{l}
                </label>
              ))}
            </div>
            <div className="testcards"><Info size={16} />
              <span>Demo store: payments are simulated and nothing is charged. Use test card <span className="mono">4242 4242 4242 4242</span> (any future expiry, any CVV),
                or <span className="mono">4000 0000 0000 0002</span> to see a declined payment.</span></div>
            {isCard && (
              <>
                {field(pay, setPay, 'card_number', 'Card number', { inputMode: 'numeric', autoComplete: 'off', placeholder: '4242 4242 4242 4242' })}
                {field(pay, setPay, 'card_name', 'Name on card', { autoComplete: 'off' })}
                <div className="grid-3">
                  {field(pay, setPay, 'expiry', 'Expiry (MM/YY)', { placeholder: '12/30', autoComplete: 'off', maxLength: 5 })}
                  {field(pay, setPay, 'cvv', 'CVV', { inputMode: 'numeric', autoComplete: 'off', maxLength: 4 })}
                  {pay.method === 'credit_card' && (
                    <div className="field">
                      <label htmlFor="inst">Installments</label>
                      <select id="inst" className="input" value={pay.installments} onChange={(e) => setPay({ ...pay, installments: e.target.value })}>
                        {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n}× {money(preview.total / n)}{n > 1 ? ' interest-free' : ''}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              </>
            )}
            {pay.method === 'boleto' && <p className="muted small" style={{ margin: 0 }}><Banknote size={15} style={{ verticalAlign: '-3px' }} /> A boleto normally clears in 1–3 days; in this demo it clears instantly.</p>}
          </Step>
          <Step n={3} title="Review items and delivery">
            {preview.lines.map((l) => (
              <div key={l.product_id} className="row" style={{ gap: 14, padding: '8px 0', borderTop: '1px solid var(--line-2)', flexWrap: 'nowrap' }}>
                <div style={{ width: 56 }}><Art category={l.category} size={24} /></div>
                <div className="grow"><strong className="small">{l.name}</strong><div className="small muted">Qty {l.quantity} · {money(l.unit_price)} each</div></div>
                <strong>{money(l.unit_price * l.quantity)}</strong>
              </div>
            ))}
            <p className="small" style={{ margin: '10px 0 0', color: 'var(--green)', fontWeight: 700 }}>
              {preview.delivery && preview.delivery.free ? 'FREE delivery' : `Delivery ${money(preview.freight)}`} · arrives by {deliveryDate(latest)}
            </p>
          </Step>
        </div>

        <aside className="card summary">
          <button className="btn coral block lg" disabled={busy}>{busy ? 'Placing your order…' : `Place your order · ${money(preview.total)}`}</button>
          <p className="small muted" style={{ textAlign: 'center', margin: '10px 0 14px' }}><Lock size={13} style={{ verticalAlign: '-2px' }} /> One MongoDB transaction: everything is saved, or nothing is.</p>
          <ErrorBox error={error} />
          <h3 style={{ margin: '12px 0 8px' }}>Order summary</h3>
          <div className="line"><span>Items</span><span>{money(preview.subtotal)}</span></div>
          <div className="line"><span>Delivery</span><span>{preview.delivery && preview.delivery.free
            ? <><s className="muted" style={{ marginRight: 6 }}>{money(preview.delivery.saved)}</s><strong style={{ color: 'var(--green)' }}>FREE</strong></> : money(preview.freight)}</span></div>
          {preview.discount && <div className="line" style={{ color: 'var(--green)', fontWeight: 700 }}><span>Code {preview.discount.code}</span><span>−{money(preview.discount.amount)}</span></div>}
          <div className="line total"><span>Order total</span><span>{money(preview.total)}</span></div>
          <div className="field" style={{ marginTop: 16 }}>
            <label htmlFor="coupon">Coupon code</label>
            <div className="row" style={{ flexWrap: 'nowrap' }}>
              <input id="coupon" className="input" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="WELCOME10" />
              <button type="button" className="btn outline sm" onClick={() => loadPreview(coupon)}>Apply</button>
            </div>
            {offer && !applied && (
              <div className="hint">Your offer: {offer.title} (code {offer.code})
                {offer.min_subtotal > preview.subtotal ? ` · add ${money(offer.min_subtotal - preview.subtotal)} more to use it` : ''}</div>
            )}
            {applied && <div className="hint" style={{ color: 'var(--green)', fontWeight: 700 }}>Code {applied} applied</div>}
          </div>
          <ErrorBox error={couponError} />
        </aside>
      </div>
    </form>
  )
}
