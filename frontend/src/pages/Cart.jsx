import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CheckCircle2, Minus, PiggyBank, Plus, ShieldCheck, ShoppingCart, Trash2, Truck } from 'lucide-react'
import { api } from '../api'
import { Art } from '../art'
import { Empty, ErrorBox, MrpLine, Price, Spinner } from '../components'
import { deliveryDate, money } from '../format'
import { useApp } from '../state'

function FreeDeliveryBar({ cart, isPlus }) {
  const d = cart.delivery
  const pct = d.free ? 100 : Math.min(100, (100 * cart.subtotal) / cart.free_delivery_min)
  const [shown, setShown] = useState(0)          // grows from 0 on first paint, then follows the cart
  useEffect(() => { const t = requestAnimationFrame(() => setShown(pct)); return () => cancelAnimationFrame(t) }, [pct])
  return (
    <div className={`card freebar${d.free ? ' unlocked' : ''}`}>
      {d.free ? (
        <div className="row" style={{ color: 'var(--green)', fontWeight: 700 }}><CheckCircle2 size={18} />
          {d.reason === 'plus' || isPlus ? 'FREE delivery with your Kartiq Plus membership' : 'Your order qualifies for FREE delivery'}</div>
      ) : (
        <div className="row"><Truck size={18} color="var(--green)" />
          <span>Add <strong>{money(d.add_for_free)}</strong> more to get <strong style={{ color: 'var(--green)' }}>FREE delivery</strong></span></div>
      )}
      <div className="track">
        <div className="fill" style={{ width: `${shown}%` }} />
        <span className="truck" style={{ left: `${shown}%` }} key={d.free ? 'free' : 'road'}>{d.free ? <CheckCircle2 size={16} /> : <Truck size={15} />}</span>
      </div>
    </div>
  )
}

export default function Cart() {
  const { setCartCount, offer, isPlus } = useApp()
  const navigate = useNavigate()
  const [cart, setCart] = useState(null)
  const [error, setError] = useState(null)

  const apply = (c) => { setCart(c); setCartCount(c.count) }
  useEffect(() => { api('/api/cart').then(apply).catch(setError) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const change = async (pid, quantity) => {
    try { apply(await api(`/api/cart/items/${pid}`, { method: 'PATCH', body: { quantity } })) } catch (e) { setError(e) }
  }
  const remove = async (pid) => {
    try { apply(await api(`/api/cart/items/${pid}`, { method: 'DELETE' })) } catch (e) { setError(e) }
  }

  if (!cart) return error ? <ErrorBox error={error} /> : <Spinner />
  if (cart.items.length === 0) {
    return <Empty Icon={ShoppingCart} title="Your Kartiq cart is empty" text="Deals, best sellers and picks for you are waiting."
      action={<Link className="btn" to="/">Continue shopping</Link>} />
  }
  return (
    <div>
      <h1 style={{ marginBottom: 14 }}>Shopping cart</h1>
      <ErrorBox error={error} />
      <div className="cart-layout">
        <div className="stack" style={{ marginTop: 0 }}>
          <FreeDeliveryBar cart={cart} isPlus={isPlus} />
          <div className="card">
            {cart.items.map((i) => (
              <div className="cart-item" key={i.product_id}>
                <Link to={`/product/${i.product_id}`}><Art category={i.category} size={40} /></Link>
                <div>
                  <Link to={`/product/${i.product_id}`} style={{ color: 'var(--ink)', fontWeight: 700 }}>{i.name}</Link>
                  <div className="small muted" style={{ margin: '2px 0 6px' }}>{i.category_label}</div>
                  <div className="price-row"><Price value={i.price} size="sm" /><MrpLine mrp={i.mrp} discount={i.discount_pct} /></div>
                  <div className="delivery" style={{ marginTop: 4 }}>Arrives by <strong>{deliveryDate(i.delivery_days)}</strong></div>
                  <div className="row" style={{ marginTop: 10 }}>
                    <div className="qty">
                      <button onClick={() => (i.quantity > 1 ? change(i.product_id, i.quantity - 1) : remove(i.product_id))} aria-label="Fewer">
                        {i.quantity > 1 ? <Minus size={15} /> : <Trash2 size={15} />}</button>
                      <span>{i.quantity}</span>
                      <button onClick={() => change(i.product_id, Math.min(20, i.quantity + 1))} aria-label="More"><Plus size={15} /></button>
                    </div>
                    <button className="btn ghost sm" onClick={() => remove(i.product_id)}><Trash2 size={15} />Remove</button>
                  </div>
                </div>
                <strong style={{ fontSize: '1.05rem' }}>{money(i.line_total)}</strong>
              </div>
            ))}
          </div>
        </div>
        <aside className="card summary">
          <h3 style={{ marginBottom: 10 }}>Order summary</h3>
          <div className="line"><span>Items ({cart.count})</span><span>{money(cart.subtotal)}</span></div>
          <div className="line"><span>Delivery</span>
            <span>{cart.delivery.free ? <><s className="muted" style={{ marginRight: 6 }}>{money(cart.delivery.saved)}</s><strong style={{ color: 'var(--green)' }}>FREE</strong></> : money(cart.freight)}</span></div>
          <div className="line total"><span>Total</span><span>{money(cart.total)}</span></div>
          {cart.mrp_savings > 0.5 && <div className="save-note"><PiggyBank size={17} />You save {money(cart.mrp_savings)} on M.R.P.</div>}
          {offer && (
            <p className="small" style={{ marginTop: 12 }}>Your offer: <strong>{offer.title}</strong>.{' '}
              {cart.subtotal >= (offer.min_subtotal || 0) ? `Code ${offer.code} is applied at checkout.`
                : `Add ${money(offer.min_subtotal - cart.subtotal)} more to use code ${offer.code}.`}</p>
          )}
          <button className="btn coral block lg" style={{ marginTop: 14 }} onClick={() => navigate('/checkout')}>Proceed to checkout</button>
          <div className="row small muted" style={{ marginTop: 12, justifyContent: 'center' }}><ShieldCheck size={15} /> Secure checkout · simulated payment</div>
        </aside>
      </div>
    </div>
  )
}
