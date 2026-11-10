// Customer 360: everything the three intelligence modules know about one customer.
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, LineChart, RiskBadge, Spinner, StatusBadge } from '../components'
import { date, dateTime, money, shortId, timeAgo, titleCase } from '../format'
import { useLive } from '../state'

const fmt = (v, digits = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(digits))

export default function AdminCustomer() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => api(`/api/admin/customers/${id}`).then(setData).catch(setError), [id])
  useEffect(() => { setData(null); load() }, [load])
  useLive((msg) => {
    const mine = (msg.type === 'risk_update' && msg.customer_id === id) || (msg.type === 'activity' && msg.event && msg.event.customer_id === id)
    if (mine) load()
  })

  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  const c = data.customer; const seg = c.segment || {}; const an = c.anomaly || {}; const rfm = data.rfm
  const points = data.rolling_metrics.map((r) => ({ x: new Date(r.timestamp), y: r.rolling_event_count_7d || 0 }))
  const latest = data.rolling_metrics[data.rolling_metrics.length - 1]

  return (
    <div className="stack">
      <p><Link to="/admin">← Operations</Link></p>
      <div className="spread">
        <div>
          <h1 style={{ marginBottom: 0 }}>{data.user ? data.user.name : 'Customer'} <small className="mono">{c._id}</small></h1>
          <small>{data.user ? `${data.user.email} · ` : ''}{titleCase(c.customer_city || '')} {c.customer_state} · source: {c.source}</small>
        </div>
        <div className="row"><span className="badge info">{seg.label || 'Unsegmented'}</span><RiskBadge risk={an.risk_label} /></div>
      </div>

      <div className="grid-3">
        <div className="card pad">
          <h3>Segment · Module 1</h3>
          <p><strong>{seg.label || '—'}</strong> <small className="muted">({seg.method || 'n/a'})</small></p>
          {rfm ? (
            <dl className="specs">
              <dt>Recency</dt><dd>{fmt(rfm.recency_days, 0)} days</dd>
              <dt>Frequency</dt><dd>{rfm.frequency} order(s)</dd>
              <dt>Monetary</dt><dd>{money(rfm.monetary)}</dd>
              <dt>Last order</dt><dd>{date(rfm.last_order_date)}</dd>
            </dl>
          ) : <p className="muted">No completed orders yet (Pipeline A has no row).</p>}
        </div>
        <div className="card pad">
          <h3>Recommendations · Module 2</h3>
          {data.affinity.length > 0 && <p className="muted" style={{ fontSize: '0.85rem' }}>Buys in: {data.affinity.map((a) => `${a.label} (${money(a.spend)})`).join(', ')}</p>}
          <ol style={{ paddingLeft: 18, margin: 0 }}>
            {data.recommendations.map((r) => (
              <li key={r.category}>{r.label} <small className="muted">— {r.reason === 'collaborative_filtering' ? `similar buyers of ${r.because_label}` : r.reason}</small></li>
            ))}
          </ol>
        </div>
        <div className="card pad">
          <h3>Behaviour risk · Module 3</h3>
          <p><RiskBadge risk={an.risk_label} /> score <span className="mono">{fmt(an.score, 3)}</span> <small className="muted">({an.method || 'not scored'})</small></p>
          {latest ? (
            <dl className="specs">
              <dt>Events, last 7 days</dt><dd>{latest.rolling_event_count_7d}</dd>
              <dt>Avg gap (last 10)</dt><dd>{fmt(latest.avg_session_gap_seconds, 0)} s</dd>
              <dt>Purchase share</dt><dd>{fmt(latest.cart_to_purchase_trend, 2)}</dd>
              <dt>Abandon share</dt><dd>{fmt(latest.cart_abandon_trend, 2)}</dd>
            </dl>
          ) : <p className="muted">No behavioural events yet.</p>}
          {an.flags && an.flags.length > 0 && <p style={{ fontSize: '0.85rem' }}>Triggers: {an.flags.join('; ')}</p>}
        </div>
      </div>

      <div className="card pad">
        <h3>7-day rolling event count ($setWindowFields, Pipeline C)</h3>
        <LineChart points={points} label="Rolling 7-day event count over time" />
      </div>

      <div className="admin-grid">
        <div className="card">
          <div className="card-head"><h2>Recent events</h2></div>
          {data.recent_events.length === 0 ? <div className="empty">None.</div> : (
            <ul className="feed">
              {data.recent_events.map((e, i) => (
                <li key={i}>
                  <span className={`badge ${(e.metadata || {}).source === 'app' ? 'brand' : 'neutral'}`}>{(e.metadata || {}).source === 'app' ? 'app' : 'synthetic'}</span>
                  <strong>{titleCase(e.event_type)}</strong><span className="muted">{titleCase(e.category || '')}</span>
                  <small className="muted" style={{ marginLeft: 'auto' }}>{timeAgo(e.timestamp)}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <div className="card-head"><h2>Orders</h2></div>
          {data.orders.length === 0 ? <div className="empty">None.</div> : (
            <table className="table"><tbody>
              {data.orders.map((o) => (
                <tr key={o.id}><td><Link to={`/orders/${o.id}`}>{shortId(o.id)}</Link></td><td>{dateTime(o.placed_at)}</td><td><StatusBadge status={o.status} /></td><td>{money(o.total)}</td></tr>
              ))}
            </tbody></table>
          )}
        </div>
      </div>
    </div>
  )
}
