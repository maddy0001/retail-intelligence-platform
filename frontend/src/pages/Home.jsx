import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BadgePercent, Crown, Flame, Gift, Home as HomeIcon, MousePointerClick, Orbit, Package, RadioTower,
  Sparkles, Star, Tag, Ticket, Truck, Waypoints, Zap,
} from 'lucide-react'
import { api } from '../api'
import { Art, CategoryGlyph } from '../art'
import { ErrorBox, Rail, SkeletonGrid } from '../components'
import { money } from '../format'
import TasteGlobe from '../globe'
import { useReveal, useTilt } from '../motion'
import { useApp } from '../state'

const count = (n) => Number(n || 0).toLocaleString('en-IN')
const joinNice = (list) => (list.length <= 1 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`)

// ---- hero: the live taste map ---------------------------------------------------
function TastePanel({ story }) {
  const s = story.source
  return (
    <div className="taste-panel" key={s.id} aria-live="polite">
      <div className="tp-left">
        <div className="tp-head">
          <Art category={s.id} size={22} className="tp-art" />
          <div className="grow">
            <strong>{s.label}</strong>
            <small>{count(s.buyers)} shoppers · {count(s.products)} products</small>
          </div>
        </div>
        <div className="row" style={{ gap: 10, marginTop: 8 }}>
          <Link to={`/search?category=${s.id}`} className="tp-shop">Shop this aisle <ArrowRight size={15} /></Link>
          {story.picked && <span className="tp-picked"><Sparkles size={12} /> Picked for you</span>}
        </div>
      </div>
      {story.neighbours.length > 0 && (
        <div className="tp-right">
          <div className="tp-sub">Its shoppers also buy</div>
          <div className="tp-chips">
            {story.neighbours.map((n, i) => (
              <Link key={n.id} to={`/search?category=${n.id}`} className="tp-chip" style={{ animationDelay: `${1150 + i * 140}ms` }}>
                <CategoryGlyph category={n.id} size={14} />{n.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function OfferPill({ offer, isPlus, user }) {
  if (user && user.role === 'admin') return null
  if (isPlus) {
    return <div className="offer-pill plus"><Crown size={16} /><span><strong>Kartiq Plus</strong> · FREE delivery on every order</span></div>
  }
  const o = offer || { code: 'WELCOME10', title: '10% off your first order' }
  return <div className="offer-pill"><Ticket size={16} /><span><strong>{o.code}</strong> · {o.title}</span></div>
}

function TasteHero({ graph, user, offer, isPlus }) {
  const [story, setStory] = useState(null)
  const first = user && user.role !== 'admin' && user.name ? user.name.split(' ')[0] : null
  const personal = Boolean(graph && graph.signal !== 'popular' && graph.focus.length)
  const labelOf = (id) => (graph ? (graph.nodes.find((n) => n.id === id) || {}).label : null)
  const from = personal ? graph.focus.slice(0, 2).map(labelOf).filter(Boolean) : []
  const toPicks = () => {
    const el = document.getElementById('for-you')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <section className="taste-hero">
      <div className="th-copy">
        <span className="th-eyebrow"><span className="dot" />{personal ? `Your taste map${first ? `, ${first}` : ''}` : 'Live taste map'}</span>
        <h1>{personal ? <>Here&rsquo;s where <em>your taste</em> leads next.</> : <>Discover what shoppers like you <em>love next</em>.</>}</h1>
        <p className="lede">
          {personal
            ? <>It starts from {joinNice(from)} and follows what shoppers with baskets like yours bought next. Tap any aisle to explore it.</>
            : <>Every dot is an aisle. Every line joins two aisles that the same real customers buy from. Tap one to see where its shoppers go next.</>}
        </p>
        <div className="th-ctas">
          {personal
            ? <button type="button" className="btn lg" onClick={toPicks}>See your picks <ArrowRight size={18} /></button>
            : <Link className="btn lg" to="/search">Start shopping <ArrowRight size={18} /></Link>}
          <Link className="btn lg outline" to="/how-it-works"><Orbit size={18} />How it works</Link>
        </div>
        <OfferPill offer={offer} isPlus={isPlus} user={user} />
        {graph && graph.stats && (
          <p className="th-stats"><strong>{count(graph.stats.aisles)}</strong> aisles · <strong>{count(graph.stats.customers)}</strong> real shoppers · <strong>{count(graph.stats.products)}</strong> products</p>
        )}
      </div>
      <div className="th-visual">
        <div className="th-globe">
          {graph && graph.nodes.length > 0
            ? <TasteGlobe graph={graph} onCascade={setStory} label="Kartiq's aisles on a turning globe, linked by what the same shoppers buy" />
            : <div className="globe-skel" aria-hidden="true"><span /></div>}
          <p className="th-hint">Drag to turn · tap an aisle</p>
        </div>
        {story ? <TastePanel story={story} /> : <div className="taste-panel placeholder" aria-hidden="true" />}
      </div>
    </section>
  )
}

// ---- three promo cards with a small looping illustration each ---------------------
function TiltCard({ to, className, children }) {
  const ref = useTilt(5)
  return <Link ref={ref} to={to} className={`promo tilt ${className}`}>{children}<span className="sheen" aria-hidden="true" /></Link>
}

function PromoCards({ feed, user, isPlus, freeDeliveryMin }) {
  const maxOff = Math.max(0, ...((feed && feed.deals) || []).map((d) => d.discount_pct || 0)) || 60
  return (
    <div className="promo-row">
      <TiltCard to="/deals" className="g-sunset">
        <div className="promo-copy">
          <span className="promo-eyebrow"><Flame size={14} /> Today&rsquo;s deals</span>
          <h3>Up to {maxOff}% off top-rated picks</h3>
          <span className="promo-cta">Shop the deals <ArrowRight size={15} /></span>
        </div>
        <div className="promo-art deal-art" aria-hidden="true">
          <span className="tag-swing"><BadgePercent size={40} strokeWidth={1.8} /></span>
        </div>
      </TiltCard>
      <TiltCard to={user ? '/orders' : '/search'} className="g-ocean">
        <div className="promo-copy">
          <span className="promo-eyebrow"><Zap size={14} /> Only on Kartiq</span>
          <h3>Watch your order move, live</h3>
          <span className="promo-cta">{user ? 'Track your orders' : 'Start shopping'} <ArrowRight size={15} /></span>
        </div>
        <div className="promo-art road-art" aria-hidden="true">
          <Package size={22} />
          <span className="road"><span className="truck"><Truck size={20} /></span></span>
          <HomeIcon size={22} />
        </div>
      </TiltCard>
      <TiltCard to="/search?sort=popular" className="g-violet">
        <div className="promo-copy">
          <span className="promo-eyebrow"><Truck size={14} /> FREE delivery</span>
          <h3>{isPlus ? 'Free on every order with your Plus membership' : `On every order over ${money(freeDeliveryMin)}`}</h3>
          <span className="promo-cta">Start shopping <ArrowRight size={15} /></span>
        </div>
        <div className="promo-art box-art" aria-hidden="true">
          <span className="box-bounce"><Gift size={40} strokeWidth={1.8} /></span><span className="box-shadow" />
        </div>
      </TiltCard>
    </div>
  )
}

function Section({ icon: Icon, title, sub, to, children, id }) {
  const ref = useReveal()
  return (
    <section id={id} ref={ref} className="home-section">
      <div className="section-head">
        <div><h2>{Icon && <Icon size={22} color="var(--brand)" />}{title}</h2>{sub && <p>{sub}</p>}</div>
        {to && <Link to={to} className="see-all">See all <ArrowRight size={16} /></Link>}
      </div>
      {children}
    </section>
  )
}

const HOW = [
  [MousePointerClick, 'You shop', 'Views and taps are saved as events'],
  [RadioTower, 'Kartiq notices', 'Change Streams react instantly'],
  [Waypoints, 'It learns your taste', 'Pipelines and three small models'],
  [Zap, 'Your store updates', 'Offers, picks and tracking, live'],
]

function HowTeaser() {
  const ref = useReveal()
  return (
    <section ref={ref} className="how-teaser">
      <div className="ht-copy">
        <span className="th-eyebrow light"><span className="dot" />How Kartiq works</span>
        <h2>From your click to your next great find, in real time.</h2>
        <p>Take a two-minute tour of what happens behind every tap.</p>
        <Link to="/how-it-works" className="btn amber lg">Take the tour <ArrowRight size={18} /></Link>
      </div>
      <ol className="ht-steps">
        {HOW.map(([Icon, title, text], i) => (
          <li key={title} style={{ '--i': i }}>
            <span className="ic"><Icon size={20} /></span>
            <div><strong>{title}</strong><span>{text}</span></div>
            <span className="n">0{i + 1}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function Home() {
  const { user, customer, ready, offer, isPlus, freeDeliveryMin } = useApp()
  const [feed, setFeed] = useState(null)
  const [graph, setGraph] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!ready) return
    api('/api/home').then(setFeed).catch(setError)
    api('/api/taste-graph').then(setGraph).catch(() => setGraph({ nodes: [], edges: [], focus: [], recommended: [], signal: 'popular' }))
  }, [ready, user, customer && customer.segment])

  const recs = feed && feed.recommended
  const recLabel = Object.fromEntries((recs ? recs.categories : []).map((c) => [c.category, c]))
  const why = (p) => {
    const c = recLabel[p.rec_category]
    return c && c.because_label ? `Because you shop in ${c.because_label}` : null
  }

  return (
    <div>
      <TasteHero graph={graph} user={user} offer={offer} isPlus={isPlus} />
      <PromoCards feed={feed} user={user} isPlus={isPlus} freeDeliveryMin={freeDeliveryMin} />
      {error && <div style={{ marginTop: 16 }}><ErrorBox error={error} /></div>}
      {!feed && !error && <div style={{ marginTop: 34 }}><SkeletonGrid count={5} /></div>}

      {feed && recs && recs.products.length > 0 && (
        <Section id="for-you" icon={Sparkles} title={`Recommended for you${user ? `, ${user.name.split(' ')[0]}` : ''}`}
          sub={recs.signal === 'purchases' ? 'Based on what shoppers with similar baskets also buy'
            : recs.signal === 'browsing' ? 'Based on what you have been looking at' : 'Popular picks to get you started'}>
          <Rail items={recs.products} noteFor={why} />
        </Section>
      )}

      {feed && (
        <>
          <Section icon={BadgePercent} title="Today's deals" sub="Prices below the highest price each product has sold for" to="/deals" id="deals">
            <Rail items={feed.deals} />
          </Section>

          <Section icon={Tag} title="Shop by category" to="/search">
            <div className="cat-grid">
              {feed.categories.slice(0, 18).map((c) => (
                <Link key={c.category} to={`/search?category=${c.category}`} className="cat-tile">
                  <Art category={c.category} size={38} />
                  <span>{c.label}</span>
                </Link>
              ))}
            </div>
          </Section>

          <Section icon={Star} title="Best sellers" sub="Most bought, rated 4 stars or more by real buyers" to="/search?sort=popular">
            <Rail items={feed.popular} />
          </Section>

          <Section icon={Gift} title={`Great finds under ${money(feed.budget.max)}`} sub="Highly rated and easy on the wallet"
            to={`/search?max_price=${feed.budget.max}&sort=popular`}>
            <Rail items={feed.budget.items} />
          </Section>

          <HowTeaser />
        </>
      )}
    </div>
  )
}
