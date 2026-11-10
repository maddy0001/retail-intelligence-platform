import { useEffect, useState } from 'react'
import { Flame } from 'lucide-react'
import { api } from '../api'
import { ErrorBox, ProductGrid } from '../components'

export default function Deals() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api('/api/deals', { params: { limit: 48 } }).then((d) => setItems(d.items)).catch(setError) }, [])
  return (
    <div>
      <div className="offer-banner g-sunset" style={{ marginTop: 0, marginBottom: 20 }}>
        <Flame size={34} />
        <div>
          <h1 style={{ color: '#fff' }}>Today's deals</h1>
          <p style={{ margin: 0, color: 'rgba(255,255,255,.9)' }}>Well-rated products priced 15–60% below the highest price they have really sold for.</p>
        </div>
      </div>
      <ErrorBox error={error} />
      <ProductGrid items={items} />
    </div>
  )
}
