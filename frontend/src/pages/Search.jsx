import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SlidersHorizontal, Star, X } from 'lucide-react'
import { api } from '../api'
import { ErrorBox, Pager, ProductGrid } from '../components'
import { money } from '../format'

const SORTS = [
  ['relevance', 'Featured'], ['popular', 'Best selling'], ['rating', 'Avg. customer review'],
  ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low'],
]

export default function Search() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const query = Object.fromEntries(params.entries())
  const [wide] = useState(() => { try { return window.matchMedia('(min-width: 961px)').matches } catch { return true } })

  useEffect(() => {
    setError(null); setData(null)
    api('/api/products', { params: { page_size: 24, ...query } })
      .then((d) => { setData(d); window.scrollTo({ top: 0 }) })
      .catch(setError)
  }, [params.toString()]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (changes) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([k, v]) => (v === null || v === undefined || v === '' ? next.delete(k) : next.set(k, v)))
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  const facets = data ? data.facets : { categories: [], price_ranges: [], ratings: [] }
  const priceKey = `${query.min_price || ''}-${query.max_price || ''}`
  const catLabel = query.category && facets.categories.find((c) => c.category === query.category)
  const active = [
    query.category && { key: 'category', label: catLabel ? catLabel.label : query.category },
    (query.min_price || query.max_price) && { key: 'price', label: query.max_price ? `${money(Number(query.min_price || 0))} – ${money(Number(query.max_price))}` : `Over ${money(Number(query.min_price))}` },
    query.min_rating && { key: 'min_rating', label: `${query.min_rating}★ & up` },
  ].filter(Boolean)

  return (
    <div className="search-layout">
      <details className="card filters" open={wide}>
        <summary className="filters-summary"><SlidersHorizontal size={18} /> Filters</summary>
        <h4>Department</h4>
        <ul className="facet-list">
          <li><button className={!query.category ? 'on' : ''} onClick={() => set({ category: null })}><span>All departments</span></button></li>
          {facets.categories.map((c) => (
            <li key={c.category}>
              <button className={query.category === c.category ? 'on' : ''} onClick={() => set({ category: c.category })}>
                <span>{c.label}</span><small>{c.count.toLocaleString('en-IN')}</small>
              </button>
            </li>
          ))}
        </ul>
        <h4>Customer review</h4>
        <ul className="facet-list">
          {[4, 3, 2].map((s) => (
            <li key={s}>
              <button className={query.min_rating === String(s) ? 'on' : ''} onClick={() => set({ min_rating: query.min_rating === String(s) ? null : s })}>
                <span className="stars">{[1, 2, 3, 4, 5].map((i) => <Star key={i} size={14} strokeWidth={0} fill={i <= s ? 'currentColor' : '#e3e0ea'} />)}<span className="val" style={{ fontWeight: 600 }}>& up</span></span>
              </button>
            </li>
          ))}
        </ul>
        <h4>Price</h4>
        <ul className="facet-list">
          <li><button className={priceKey === '-' ? 'on' : ''} onClick={() => set({ min_price: null, max_price: null })}><span>Any price</span></button></li>
          {facets.price_ranges.map((r) => (
            <li key={r.min}>
              <button className={priceKey === `${r.min}-${r.max ?? ''}` ? 'on' : ''} onClick={() => set({ min_price: r.min, max_price: r.max })}>
                <span>{r.max ? `${money(r.min)} – ${money(r.max)}` : `Over ${money(r.min)}`}</span>
                <small>{r.count.toLocaleString('en-IN')}</small>
              </button>
            </li>
          ))}
        </ul>
      </details>

      <section>
        <div className="results-head">
          <div>
            <h1 style={{ fontSize: '1.45rem' }}>{query.q ? <>Results for <span style={{ color: 'var(--brand)' }}>“{query.q}”</span></> : catLabel ? catLabel.label : 'All products'}</h1>
            <span className="muted small">{data ? `${data.total.toLocaleString('en-IN')} products` : 'Searching…'}</span>
          </div>
          <select className="input" style={{ width: 'auto', borderRadius: 999 }} value={query.sort || 'relevance'} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort by">
            {SORTS.map(([v, l]) => <option key={v} value={v}>Sort: {l}</option>)}
          </select>
        </div>
        {active.length > 0 && (
          <div className="chips" style={{ marginBottom: 14 }}>
            {active.map((a) => (
              <button key={a.key} className="chip on" onClick={() => set(a.key === 'price' ? { min_price: null, max_price: null } : { [a.key]: null })}>
                {a.label} <X size={14} />
              </button>
            ))}
          </div>
        )}
        <ErrorBox error={error} />
        <ProductGrid items={data ? data.items : null} />
        {data && <Pager page={data.page} pages={Math.min(data.pages, 500)} onPage={(p) => set({ page: p })} />}
      </section>
    </div>
  )
}
