import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Package } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorBox, Spinner, StatusBadge } from '../components'
import { date, money, shortId } from '../format'
import { useLive } from '../state'

export default function Orders() {
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => api('/api/orders').then(setOrders).catch(setError), [])
  useEffect(() => { load() }, [load])
  useLive((msg) => { if (msg.type === 'order_status') load() })

  if (error) return <ErrorBox error={error} />
  if (!orders) return <Spinner />
  return (
    <div>
      <div className="spread" style={{ marginBottom: 14 }}>
        <h1>Your orders</h1>
        <span className="live-pill">Live updates on</span>
      </div>
      {orders.length === 0 ? (
        <Empty Icon={Package} title="No orders yet" text="When you place an order, you can track it here in real time."
          action={<Link className="btn" to="/">Start shopping</Link>} />
      ) : (
        <div className="card">
          {orders.map((o) => (
            <Link key={o.id} to={`/orders/${o.id}`} className="order-card">
              <div>
                <div className="row" style={{ gap: 10 }}>
                  <strong>Order #{shortId(o.id)}</strong><StatusBadge status={o.status} />
                  {o.source === 'olist' && <span className="badge neutral">Past order</span>}
                </div>
                <div className="small muted" style={{ marginTop: 4 }}>Placed {date(o.placed_at)} · {o.items_count} item(s)</div>
                <div className="small" style={{ marginTop: 4 }}>{(o.preview || []).join(' · ')}</div>
              </div>
              <div className="row" style={{ gap: 14 }}>
                <strong style={{ fontSize: '1.05rem' }}>{money(o.total)}</strong>
                <ChevronRight size={20} color="var(--muted)" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
