import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bell, Crown, Gift, LogOut, MapPin, Package, Sparkles, Truck } from 'lucide-react'
import { initials, money, timeAgo, titleCase } from '../format'
import { useApp } from '../state'

const SEGMENT_TEXT = {
  'High-Value Loyal': 'You keep coming back, so delivery is always free for you.',
  'Big Spender': 'You go for bigger, higher-quality purchases.',
  'Bargain Browser': 'You love a good deal on everyday essentials.',
  'At-Risk': "It's been a while. Here's something to welcome you back.",
  'New Customer': 'Welcome! Your profile adapts after your first delivered order.',
}

export default function Account() {
  const { user, customer, offer, isPlus, freeDeliveryMin, notifications, refreshNotifications, refreshMe, logout } = useApp()
  const navigate = useNavigate()
  useEffect(() => { refreshMe(); refreshNotifications() }, [refreshMe, refreshNotifications])
  if (!user) return null
  return (
    <div className="admin-grid">
      <div className="stack" style={{ marginTop: 0 }}>
        <div className="card pad-lg">
          <div className="row" style={{ gap: 16 }}>
            <span className="avatar" style={{ width: 60, height: 60, fontSize: '1.3rem' }}>{initials(user.name)}</span>
            <div className="grow">
              <h1 style={{ fontSize: '1.5rem' }}>{user.name}</h1>
              <div className="muted">{user.email}</div>
              {customer && customer.city && <div className="row small" style={{ gap: 6, marginTop: 4 }}><MapPin size={14} />{titleCase(customer.city)}{customer.state ? `, ${customer.state}` : ''}</div>}
            </div>
          </div>
          <div className="row" style={{ marginTop: 18 }}>
            <Link to="/orders" className="btn outline sm"><Package size={16} />Your orders ({customer ? customer.order_count || 0 : 0})</Link>
            <button className="btn outline sm" onClick={() => { logout(); navigate('/') }}><LogOut size={16} />Sign out</button>
          </div>
        </div>

        {isPlus ? (
          <div className="plus-card">
            <div className="row" style={{ gap: 8, fontWeight: 800, letterSpacing: '.04em', fontSize: '.8rem' }}><Crown size={18} /> KARTIQ PLUS MEMBER</div>
            <h2 style={{ color: '#fff', margin: '10px 0 6px', fontSize: '1.5rem' }}>FREE delivery on every order</h2>
            <p style={{ color: 'rgba(255,255,255,.85)', margin: 0 }}>Unlocked automatically because you shop with us again and again.</p>
          </div>
        ) : customer && customer.segment && (
          <div className="card pad-lg">
            <div className="row small" style={{ gap: 6, color: 'var(--brand)', fontWeight: 800, letterSpacing: '.04em' }}><Sparkles size={16} /> YOUR SHOPPER PROFILE</div>
            <h2 style={{ margin: '8px 0 6px' }}>{customer.segment}</h2>
            <p style={{ margin: 0 }}>{SEGMENT_TEXT[customer.segment] || ''}</p>
            <p className="notice" style={{ marginTop: 12, marginBottom: 0 }}>Kartiq Plus (free delivery always) unlocks automatically for repeat customers.</p>
          </div>
        )}

        {offer && (
          <div className="offer-card">
            <div className="row small" style={{ gap: 6, color: 'var(--coral-600)', fontWeight: 800, letterSpacing: '.04em' }}><Gift size={16} /> YOUR OFFER</div>
            <h2 style={{ margin: '8px 0 6px' }}>{offer.title}</h2>
            <p style={{ marginBottom: 12 }}>{offer.body}</p>
            <span className="code">{offer.code}</span>
          </div>
        )}
        <div className="card pad row" style={{ gap: 12 }}><Truck size={20} color="var(--green)" />
          <span className="small">Orders over {money(freeDeliveryMin)} ship FREE, and every order is tracked live from packing to your door.</span></div>
      </div>

      <div className="card">
        <div className="card-head"><h2><Bell size={18} /> Notifications</h2></div>
        {notifications.items.length === 0 && <div className="empty"><span className="ic"><Bell size={26} /></span>Nothing yet.</div>}
        {notifications.items.map((n, i) => (
          <div key={n._id || i} className="note">
            <span className="ic">{n.kind === 'order' ? <Package size={16} /> : <Gift size={16} />}</span>
            <div>
              {n.link ? <Link to={n.link}><strong>{n.title}</strong></Link> : <strong>{n.title}</strong>}
              {n.body && <div className="muted">{n.body}</div>}
              <small className="muted">{timeAgo(n.created_at)}</small>
            </div>
          </div>
        ))}
        <p className="notice" style={{ margin: 16 }}>Notifications are kept for 30 days (a MongoDB TTL index removes older ones).</p>
      </div>
    </div>
  )
}
