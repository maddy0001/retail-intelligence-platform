// App-wide state: the logged-in user, cart badge, notifications, toasts,
// and the WebSocket that receives live pushes from the server's Change Stream worker.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, getToken, setToken } from './api'

const AppContext = createContext(null)
export const useApp = () => useContext(AppContext)

// Subscribe a component to live WebSocket messages while it is mounted.
export function useLive(handler) {
  const { subscribe } = useApp()
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => subscribe((msg) => ref.current(msg)), [subscribe])
}

export function AppProvider({ children }) {
  const [user, setUser] = useState(null)
  const [customer, setCustomer] = useState(null)
  const [offer, setOffer] = useState(null)
  const [isPlus, setIsPlus] = useState(false)
  const [freeDeliveryMin, setFreeDeliveryMin] = useState(2500)
  const [store, setStore] = useState({ inr_per_brl: 17.8, budget_max: 999 })
  const [ready, setReady] = useState(false)
  const [cartCount, setCartCount] = useState(0)
  const [notifications, setNotifications] = useState({ unread: 0, items: [] })
  const [toasts, setToasts] = useState([])
  const [connected, setConnected] = useState(false)
  const listeners = useRef(new Set())

  const toast = useCallback((title, body = '') => {
    const id = `${Date.now()}-${Math.random()}`
    setToasts((t) => [...t.slice(-3), { id, title, body }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5500)
  }, [])

  const refreshMe = useCallback(async () => {
    if (!getToken()) { setUser(null); setCustomer(null); setOffer(null); setIsPlus(false); return }
    try {
      const me = await api('/api/auth/me')
      setUser(me.user); setCustomer(me.customer); setOffer(me.offer)
      setIsPlus(Boolean(me.is_plus)); if (me.free_delivery_min) setFreeDeliveryMin(me.free_delivery_min)
    } catch (e) {
      if (e.status === 401) { setToken(null); setUser(null); setCustomer(null); setOffer(null); setIsPlus(false) }
    }
  }, [])

  const refreshCart = useCallback(async () => {
    if (!getToken()) { setCartCount(0); return }
    try { setCartCount((await api('/api/cart')).count) } catch { setCartCount(0) }
  }, [])

  const refreshNotifications = useCallback(async () => {
    if (!getToken()) return
    try { setNotifications(await api('/api/notifications')) } catch { /* ignore */ }
  }, [])

  useEffect(() => { refreshMe().finally(() => setReady(true)) }, [refreshMe])
  // Store currency + delivery rule (for visitors who are not signed in, too).
  useEffect(() => {
    api('/api/store').then((s) => { setStore(s); if (s.free_delivery_min) setFreeDeliveryMin(s.free_delivery_min) }).catch(() => {})
  }, [])
  useEffect(() => {
    if (!user) return
    refreshNotifications()
    if (user.role !== 'admin') refreshCart()
  }, [user, refreshCart, refreshNotifications])

  // One WebSocket per logged-in tab, with reconnect + keep-alive.
  useEffect(() => {
    if (!user) return undefined
    let ws; let timer; let ping; let closed = false; let retry = 0
    const open = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${window.location.host}/ws?token=${encodeURIComponent(getToken() || '')}`)
      ws.onopen = () => {
        setConnected(true); retry = 0
        ping = setInterval(() => { if (ws.readyState === 1) ws.send('ping') }, 25000)
      }
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'notification' && msg.notification) {
          setNotifications((n) => ({ unread: n.unread + 1, items: [msg.notification, ...n.items].slice(0, 30) }))
          toast(msg.notification.title, msg.notification.body)
          if (msg.notification.kind === 'offer') refreshMe()
        }
        listeners.current.forEach((fn) => fn(msg))
      }
      ws.onclose = () => {
        setConnected(false); clearInterval(ping)
        if (!closed) timer = setTimeout(open, Math.min(15000, 1000 * 2 ** retry++))
      }
    }
    open()
    return () => { closed = true; clearTimeout(timer); clearInterval(ping); if (ws) ws.close() }
  }, [user, toast, refreshMe])

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  const login = async (email, password) => {
    const r = await api('/api/auth/login', { method: 'POST', body: { email, password } })
    setToken(r.token); await refreshMe(); return r
  }
  const signup = async (payload) => {
    const r = await api('/api/auth/signup', { method: 'POST', body: payload })
    setToken(r.token); await refreshMe(); return r
  }
  const logout = () => {
    setToken(null); setUser(null); setCustomer(null); setOffer(null); setIsPlus(false); setCartCount(0)
    setNotifications({ unread: 0, items: [] })
  }

  const value = {
    user, customer, offer, isPlus, freeDeliveryMin, store, ready, cartCount, setCartCount, refreshCart, refreshMe, notifications,
    setNotifications, refreshNotifications, toast, toasts, connected, subscribe, login, signup, logout,
  }
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
