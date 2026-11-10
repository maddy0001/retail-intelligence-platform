import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { BadgePercent, Gift, ShieldCheck, Truck, Zap } from 'lucide-react'
import { ErrorBox } from '../components'
import { money } from '../format'
import { Logo } from '../layout'
import { useApp } from '../state'

function useNext(defaultPath = '/') {
  const [params] = useSearchParams()
  const next = params.get('next')
  return next && next.startsWith('/') && !next.startsWith('//') ? next : defaultPath
}

function Side({ title }) {
  const { freeDeliveryMin } = useApp()
  return (
    <div className="auth-side">
      <Logo />
      <h2 style={{ color: '#fff' }}>{title}</h2>
      <p style={{ color: 'rgba(255,255,255,.85)' }}>Real products, genuine reviews, and orders you can watch move.</p>
      <ul>
        <li><span className="ic"><Gift size={20} /></span>10% off your first order with WELCOME10</li>
        <li><span className="ic"><Truck size={20} /></span>FREE delivery on orders over {money(freeDeliveryMin)}</li>
        <li><span className="ic"><Zap size={20} /></span>Live order tracking, no refreshing</li>
        <li><span className="ic"><BadgePercent size={20} /></span>Offers that adapt to how you shop</li>
        <li><span className="ic"><ShieldCheck size={20} /></span>Secure checkout, card details never stored</li>
      </ul>
    </div>
  )
}

export function Login() {
  const { login } = useApp()
  const navigate = useNavigate()
  const next = useNext()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      const r = await login(email, password)
      navigate(r.user.role === 'admin' && next === '/' ? '/admin' : next, { replace: true })
    } catch (err) { setError(err); setBusy(false) }
  }
  return (
    <div className="auth-wrap">
      <Side title="Welcome back" />
      <form className="auth-form" onSubmit={submit}>
        <h1 style={{ marginBottom: 6 }}>Sign in</h1>
        <p className="muted">Good to see you again.</p>
        <ErrorBox error={error} />
        <div className="field" style={{ marginTop: 12 }}><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="field"><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <button className="btn block lg" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <hr className="divider" style={{ margin: '22px 0' }} />
        <p className="small" style={{ textAlign: 'center' }}>New to Kartiq?</p>
        <Link className="btn outline block" to={`/signup${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`}>Create your Kartiq account</Link>
        <p className="notice" style={{ marginTop: 18 }}>Demo accounts (an admin and three shoppers linked to real Olist customers) are listed in the project README.</p>
      </form>
    </div>
  )
}

export function Signup() {
  const { signup } = useApp()
  const navigate = useNavigate()
  const next = useNext()
  const [form, setForm] = useState({ name: '', email: '', password: '', city: '', state: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      await signup({ ...form, state: form.state ? form.state.toUpperCase() : null, city: form.city || null })
      navigate(next, { replace: true })
    } catch (err) { setError(err); setBusy(false) }
  }
  return (
    <div className="auth-wrap">
      <Side title="Join Kartiq" />
      <form className="auth-form" onSubmit={submit}>
        <h1 style={{ marginBottom: 6 }}>Create account</h1>
        <p className="muted">It takes less than a minute.</p>
        <ErrorBox error={error} />
        <div className="field" style={{ marginTop: 12 }}><label htmlFor="name">Your name</label><input id="name" autoComplete="name" value={form.name} onChange={set('name')} required minLength={2} placeholder="First and last name" /></div>
        <div className="field"><label htmlFor="semail">Email</label><input id="semail" type="email" autoComplete="email" value={form.email} onChange={set('email')} required /></div>
        <div className="field">
          <label htmlFor="spass">Password</label>
          <input id="spass" type="password" autoComplete="new-password" value={form.password} onChange={set('password')} required minLength={8} placeholder="At least 8 characters" />
          <div className="hint">Stored only as a salted scrypt hash.</div>
        </div>
        <div className="grid-2">
          <div className="field"><label htmlFor="city">City (optional)</label><input id="city" value={form.city} onChange={set('city')} placeholder="São Paulo" /></div>
          <div className="field"><label htmlFor="state">State (optional)</label><input id="state" value={form.state} maxLength={2} placeholder="SP" onChange={set('state')} /></div>
        </div>
        <button className="btn coral block lg" disabled={busy}>{busy ? 'Creating your account…' : 'Create account & get 10% off'}</button>
        <p className="small" style={{ marginTop: 16, textAlign: 'center' }}>Already have an account? <Link to="/login">Sign in</Link></p>
      </form>
    </div>
  )
}
