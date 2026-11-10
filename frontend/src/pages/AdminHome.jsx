// Operations area: work queues (held orders, risk alerts) fed live by Change Streams,
// plus the analytics and synthetic-traffic controls.
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, Brain, Clock, Play, Search, ShieldAlert, ShoppingBag, Square, TrendingUp, UserPlus, Users } from 'lucide-react'
import { api } from '../api'
import { ErrorBox, HBars, RiskBadge, Spinner } from '../components'
import { dateTime, money, shortId, timeAgo, titleCase } from '../format'
import { useApp, useLive } from '../state'

const SEGMENT_COLORS = {
  'High-Value Loyal': '#5b2ee8', 'Big Spender': '#c63bff', 'Bargain Browser': '#2563eb',
  'At-Risk': '#e8461f', 'New Customer': '#0b8a4f', Unsegmented: '#b9b5c8',
}

function RunSummary({ run }) {
  if (!run) return <p className="muted">No analytics run recorded yet.</p>
  const step = (prefix) => (run.steps || []).find((s) => s.name.startsWith(prefix))
  const km = step('Module 1'); const cf = step('Module 2'); const iso = step('Module 3')
  const cfTest = cf && cf.result.test
  return (
    <div className="stack">
      <p className="muted small" style={{ margin: 0 }}>
        Last run {dateTime(run.started_at)} by {run.triggered_by} · <span className={`badge ${run.status === 'succeeded' ? 'ok' : run.status === 'running' ? 'info' : 'danger'}`}>{run.status}</span> {run.duration_s ? `${run.duration_s}s` : ''}
      </p>
      <div className="table-wrap">
        <table className="table"><tbody>
          {(run.steps || []).map((s) => <tr key={s.name}><td>{s.name}</td><td className="mono" style={{ textAlign: 'right' }}>{s.seconds}s</td></tr>)}
        </tbody></table>
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: '.86rem' }}>
        {km && <li>K-Means: k = {km.result.k}, silhouette {km.result.silhouette_by_k ? km.result.silhouette_by_k[String(km.result.k)] : '—'} over {km.result.customers_labeled?.toLocaleString('en-IN')} customers</li>}
        {cfTest && <li>Recommendations HitRate@3 on held-out customers: hybrid {cfTest.hybrid['hit_rate@3']} vs CF {cfTest.collaborative_filtering['hit_rate@3']} vs popularity {cfTest.popularity_baseline['hit_rate@3']}</li>}
        {iso && iso.result.persona_evaluation && <li>Isolation Forest: {iso.result.customers_scored?.toLocaleString('en-IN')} customers scored; catches {Math.round(100 * (iso.result.persona_evaluation.recall_high || 0))}% of the simulator's known "intense" shoppers as HIGH</li>}
      </ul>
    </div>
  )
}

export default function AdminHome() {
  const navigate = useNavigate()
  const { toast, connected } = useApp()
  const [ov, setOv] = useState(null)
  const [held, setHeld] = useState([])
  const [alerts, setAlerts] = useState([])
  const [feed, setFeed] = useState([])
  const [error, setError] = useState(null)
  const [lookup, setLookup] = useState('')
  const [found, setFound] = useState(null)
  const [rate, setRate] = useState(30)

  const loadAll = useCallback(async () => {
    try {
      const [o, h, a] = await Promise.all([
        api('/api/admin/overview'), api('/api/admin/orders', { params: { status: 'under_review' } }), api('/api/admin/alerts'),
      ])
      setOv(o); setHeld(h); setAlerts(a)
    } catch (e) { setError(e) }
  }, [])
  useEffect(() => { loadAll() }, [loadAll])
  useEffect(() => { const t = setInterval(() => api('/api/admin/overview').then(setOv).catch(() => {}), 15000); return () => clearInterval(t) }, [])

  useLive((msg) => {
    if (msg.type === 'activity') setFeed((f) => [msg.event, ...f].slice(0, 40))
    if (msg.type === 'alert') { setAlerts((a) => [msg.alert, ...a]); toast('New risk alert', msg.alert.reason) }
    if (msg.type === 'order_created' || msg.type === 'order_status') {
      api('/api/admin/orders', { params: { status: 'under_review' } }).then(setHeld).catch(() => {})
      if (msg.type === 'order_created') setFeed((f) => [{ event_type: `order ${msg.order.status}`, customer_id: msg.order.customer_id, source: 'app', timestamp: new Date().toISOString(), category: money(msg.order.total) }, ...f].slice(0, 40))
    }
    if (msg.type === 'analytics_done') { toast('Analytics run finished', msg.status); loadAll() }
    if (msg.type === 'analytics_step') api('/api/admin/overview').then(setOv).catch(() => {})
  })

  const act = async (fn, okMsg) => {
    try { await fn(); toast(okMsg); loadAll() } catch (e) { toast('Action failed', e.message) }
  }
  const search = async (e) => {
    e.preventDefault()
    try { setFound(await api('/api/admin/customers', { params: { q: lookup } })) } catch (err) { setError(err) }
  }

  if (error && !ov) return <ErrorBox error={error} />
  if (!ov) return <Spinner />
  const kpis = [
    [Users, 'Customers', ov.customers.toLocaleString('en-IN')], [UserPlus, 'App sign-ups', ov.app_customers.toLocaleString('en-IN')],
    [ShoppingBag, 'Orders (24 h)', ov.orders_24h], [TrendingUp, 'Revenue (24 h)', money(ov.revenue_24h)],
    [Clock, 'Held for review', ov.held_orders], [AlertTriangle, 'Open risk alerts', ov.open_alerts],
  ]
  const risk = ['HIGH', 'MEDIUM', 'LOW'].map((r) => ({ label: r, value: ov.risk[r] || 0, color: r === 'HIGH' ? '#e5283b' : r === 'MEDIUM' ? '#f29b00' : '#0b8a4f' }))

  return (
    <div className="stack">
      <div className="spread">
        <div><h1>Operations</h1><span className="muted small">Store work queues, updated live from MongoDB Change Streams.</span></div>
        <span className={connected ? 'live-pill' : 'badge neutral'}>{connected ? 'Live connection' : 'Reconnecting…'}</span>
      </div>
      <div className="kpis">{kpis.map(([Icon, l, v]) => <div className="card kpi" key={l}><span className="ic"><Icon size={20} /></span><div><div className="v">{v}</div><div className="l">{l}</div></div></div>)}</div>

      <div className="admin-grid">
        <div className="card">
          <div className="card-head"><h2><Clock size={18} color="var(--coral)" /> Orders held for review</h2><span className="badge neutral">{held.length}</span></div>
          {held.length === 0 ? <div className="empty">No orders waiting. Orders from customers rated HIGH risk land here.</div> : (
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Order</th><th>Customer</th><th>Total</th><th>Risk</th><th /></tr></thead>
              <tbody>
                {held.map((o) => (
                  <tr key={o.id}>
                    <td><Link to={`/orders/${o.id}`}>#{shortId(o.id)}</Link><br /><small className="muted">{timeAgo(o.placed_at)}</small></td>
                    <td>{o.customer_name || '—'}<br /><Link to={`/admin/customers/${o.customer_id}`} className="mono">{o.customer_email || o.customer_id.slice(0, 14)}</Link></td>
                    <td><strong>{money(o.total)}</strong></td>
                    <td><RiskBadge risk={o.risk && o.risk.risk_label} /></td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button className="btn sm" onClick={() => act(() => api(`/api/admin/orders/${o.id}/approve`, { method: 'POST' }), 'Order approved')}>Approve</button>{' '}
                      <button className="btn danger sm" onClick={() => act(() => api(`/api/admin/orders/${o.id}/reject`, { method: 'POST' }), 'Order rejected')}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </div>

        <div className="card">
          <div className="card-head"><h2><ShieldAlert size={18} color="var(--deal)" /> Risk alerts</h2><span className="badge neutral">{alerts.length} open</span></div>
          {alerts.length === 0 ? <div className="empty">No open alerts. One appears the moment a Change Stream trigger rates a customer HIGH.</div> : (
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Customer</th><th>Why</th><th /></tr></thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a._id}>
                    <td><Link to={`/admin/customers/${a.customer_id}`} className="mono">{a.user_email || a.customer_id.slice(0, 16)}</Link><br /><small className="muted">{timeAgo(a.created_at)}</small></td>
                    <td>{a.reason}<br /><small className="muted">was {a.previous_label || 'unscored'} → <RiskBadge risk={a.risk_label} /> score <span className="mono">{a.score}</span></small></td>
                    <td><button className="btn outline sm" onClick={() => act(() => api(`/api/admin/alerts/${a._id}/resolve`, { method: 'POST' }), 'Alert resolved')}>Resolve</button></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </div>
      </div>

      <div className="admin-grid">
        <div className="card">
          <div className="card-head">
            <h2><Activity size={18} color="var(--brand)" /> Live activity</h2>
            <div className="row">
              {ov.simulator.running ? (
                <button className="btn outline sm" onClick={() => act(() => api('/api/admin/simulator', { method: 'POST', body: { action: 'stop' } }), 'Simulated traffic stopped')}><Square size={14} />Stop simulated traffic</button>
              ) : (
                <>
                  <select className="input" style={{ width: 'auto', padding: '6px 10px', borderRadius: 999 }} value={rate} onChange={(e) => setRate(Number(e.target.value))} aria-label="Sessions per minute">
                    {[10, 30, 60, 120].map((n) => <option key={n} value={n}>{n} sessions/min</option>)}
                  </select>
                  <button className="btn sm" onClick={() => act(() => api('/api/admin/simulator', { method: 'POST', body: { action: 'start', sessions_per_min: rate } }), 'Simulated traffic started')}><Play size={14} />Start simulated traffic</button>
                </>
              )}
            </div>
          </div>
          {feed.length === 0 ? <div className="empty">Waiting for events… ({ov.events_last_hour.toLocaleString('en-IN')} in the last hour)</div> : (
            <ul className="feed">
              {feed.map((e, i) => (
                <li key={i}>
                  <span className={`badge ${e.source === 'app' ? 'brand' : 'neutral'}`}>{e.source === 'app' ? 'app' : 'synthetic'}</span>
                  <strong>{titleCase(e.event_type || '')}</strong>
                  <span className="muted">{e.category ? titleCase(String(e.category)) : ''}</span>
                  <Link className="mono" style={{ marginLeft: 'auto' }} to={`/admin/customers/${e.customer_id}`}>{(e.customer_id || '').slice(0, 12)}</Link>
                </li>
              ))}
            </ul>
          )}
          <p className="notice" style={{ margin: 14 }}>"synthetic" events come from the documented event simulator; "app" events come from people using the store.</p>
        </div>

        <div className="card">
          <div className="card-head">
            <h2><Brain size={18} color="var(--brand)" /> Customer intelligence</h2>
            <button className="btn sm" disabled={ov.analytics_running} onClick={() => act(() => api('/api/admin/analytics/run', { method: 'POST' }), 'Analytics run started')}>
              {ov.analytics_running ? 'Running…' : 'Re-run analytics'}
            </button>
          </div>
          <div style={{ padding: 18 }} className="stack">
            <div><h3 style={{ marginBottom: 6 }}>Segments (K-Means on RFM)</h3>
              <HBars rows={ov.segments.map((s) => ({ label: s.label, value: s.count, color: SEGMENT_COLORS[s.label] }))} /></div>
            <div><h3 style={{ marginBottom: 6 }}>Behavioural risk (Isolation Forest)</h3><HBars rows={risk} /></div>
            <RunSummary run={ov.last_run} />
          </div>
        </div>
      </div>

      <div className="card pad">
        <h2 style={{ marginBottom: 12, fontSize: '1.05rem' }}>Find a customer</h2>
        <form className="row" onSubmit={search} style={{ flexWrap: 'nowrap' }}>
          <input className="input grow" value={lookup} onChange={(e) => setLookup(e.target.value)} placeholder="Email, customer id or city (leave empty for HIGH-risk customers)" />
          <button className="btn"><Search size={16} />Search</button>
        </form>
        {found && (found.length === 0 ? <p className="muted" style={{ marginTop: 10 }}>No match.</p> : (
          <div className="table-wrap" style={{ marginTop: 10 }}><table className="table">
            <thead><tr><th>Customer</th><th>City</th><th>Segment</th><th>Risk</th><th>Orders</th></tr></thead>
            <tbody>{found.map((c) => (
              <tr key={c.customer_id} onClick={() => navigate(`/admin/customers/${c.customer_id}`)} style={{ cursor: 'pointer' }}>
                <td className="mono"><Link to={`/admin/customers/${c.customer_id}`}>{c.customer_id.slice(0, 18)}</Link></td>
                <td>{titleCase(c.city || '')} {c.state}</td><td>{c.segment || '—'}</td><td><RiskBadge risk={c.risk} /></td><td>{c.orders}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ))}
      </div>
    </div>
  )
}
