import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { Footer, Header, Toasts } from './layout'
import { AppProvider, useApp } from './state'
import { Spinner } from './components'
import Home from './pages/Home'
import Deals from './pages/Deals'
import Search from './pages/Search'
import Product from './pages/Product'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'
import Account from './pages/Account'
import { Login, Signup } from './pages/Auth'
import AdminHome from './pages/AdminHome'
import AdminCustomer from './pages/AdminCustomer'
import HowItWorks from './pages/HowItWorks'

function RequireAuth({ children, admin = false }) {
  const { user, ready } = useApp()
  const location = useLocation()
  if (!ready) return <Spinner />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  if (!admin && user.role === 'admin') return <Navigate to="/admin" replace />
  return children
}

function NotFound() {
  return <div className="card empty"><h2 style={{ color: 'var(--ink)' }}>Page not found</h2><p>That page doesn't exist.</p><a className="btn" href="/">Back to Kartiq</a></div>
}

// Each page fades in when the path changes (query-string changes, like search filters, don't re-animate).
function Pages() {
  const location = useLocation()
  useEffect(() => { if (!location.hash) window.scrollTo({ top: 0 }) }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <main className="page container page-in" key={location.pathname}>
      <Routes location={location}>
        <Route path="/" element={<Home />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/search" element={<Search />} />
        <Route path="/deals" element={<Deals />} />
        <Route path="/product/:id" element={<Product />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/cart" element={<RequireAuth><Cart /></RequireAuth>} />
        <Route path="/checkout" element={<RequireAuth><Checkout /></RequireAuth>} />
        <Route path="/orders" element={<RequireAuth><Orders /></RequireAuth>} />
        <Route path="/orders/:id" element={<RequireAuth><OrderDetail /></RequireAuth>} />
        <Route path="/account" element={<RequireAuth><Account /></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth admin><AdminHome /></RequireAuth>} />
        <Route path="/admin/customers/:id" element={<RequireAuth admin><AdminCustomer /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </main>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Header />
        <Pages />
        <Footer />
        <Toasts />
      </AppProvider>
    </BrowserRouter>
  )
}
