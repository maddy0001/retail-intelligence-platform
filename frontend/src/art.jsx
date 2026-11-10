// Category artwork. Olist publishes no product photos, so every product gets a
// consistent illustrated tile: a line icon for its category on a tinted background.
import {
  Armchair, Baby, Bath, BedDouble, BookOpen, Briefcase, Cake, Camera, Car, CookingPot, Disc3, Dumbbell, Factory, Fan, Film,
  Flower2, Gamepad2, Gem, Gift, Hammer, Headphones, Laptop, Lightbulb, Luggage, Monitor, Music, Package, Palette, PawPrint,
  PenTool, Plug, Printer, Shield, Shirt, ShoppingBag, Smartphone, Sofa, Sparkles, Sprout, Store, Tablet, Tractor, TreePine,
  Tv, UtensilsCrossed, Watch, Wine, Wrench, Coffee, Footprints, Home,
} from 'lucide-react'

// [keyword in the category id, icon, hue]
const MAP = [
  ['bed_bath', BedDouble, 265], ['bath', Bath, 200], ['health_beauty', Sparkles, 330], ['perfum', Gem, 300],
  ['sports', Dumbbell, 145], ['furniture_living', Sofa, 30], ['furniture_bedroom', BedDouble, 30], ['furniture', Armchair, 30],
  ['office_furniture', Briefcase, 220], ['computers_accessories', Monitor, 215], ['computers', Laptop, 215], ['pc_gamer', Gamepad2, 275],
  ['consoles', Gamepad2, 275], ['tablets', Tablet, 205], ['telephony', Smartphone, 230], ['watches', Watch, 45],
  ['housewares', Home, 25], ['home_appliances', CookingPot, 12], ['small_appliances', CookingPot, 12], ['kitchen', UtensilsCrossed, 18],
  ['la_cuisine', UtensilsCrossed, 18], ['portable_kitchen', CookingPot, 12], ['home_construction', Hammer, 35], ['home_comfort', Sofa, 30],
  ['home_confort', Sofa, 30], ['garden', Sprout, 120], ['flowers', Flower2, 340], ['auto', Car, 210], ['toys', Gift, 52],
  ['baby', Baby, 190], ['diapers', Baby, 190], ['cool_stuff', Sparkles, 285], ['electronics', Plug, 225], ['audio', Headphones, 255],
  ['music', Music, 280], ['cds', Disc3, 280], ['dvds', Film, 260], ['cine', Camera, 260], ['stationery', PenTool, 200],
  ['books', BookOpen, 20], ['party', Cake, 330], ['art', Palette, 320], ['fashion_shoes', Footprints, 350], ['fashion', Shirt, 345],
  ['luggage', Luggage, 25], ['pet', PawPrint, 28], ['food', Coffee, 22], ['drink', Wine, 350], ['christmas', TreePine, 140],
  ['security', Shield, 220], ['signaling', Lightbulb, 48], ['lights', Lightbulb, 48],
  ['air_conditioning', Fan, 195], ['agro', Tractor, 95], ['industry', Factory, 210], ['construction_tools', Wrench, 35],
  ['costruction', Wrench, 35], ['tools', Wrench, 35], ['market_place', Store, 265], ['printing', Printer, 215], ['fixed_telephony', Smartphone, 230],
  ['tv', Tv, 225], ['gift', Gift, 52], ['package', Package, 30],
]

export function categoryTheme(category = '') {
  const hit = MAP.find(([key]) => category.includes(key))
  return hit ? { Icon: hit[1], hue: hit[2] } : { Icon: ShoppingBag, hue: 262 }
}

export function Art({ category, size = 56, big = false, className = '', children }) {
  const { Icon, hue } = categoryTheme(category)
  const style = { background: `linear-gradient(150deg, hsl(${hue} 95% 96%) 0%, hsl(${hue} 85% 88%) 100%)` }
  return (
    <div className={`art${big ? ' big' : ''} ${className}`} style={style} aria-hidden="true">
      <span className="ring" />
      <Icon className="glyph" size={size} strokeWidth={1.6} color={`hsl(${hue} 55% 38%)`} />
      {children}
    </div>
  )
}

export function CategoryGlyph({ category, size = 18 }) {
  const { Icon, hue } = categoryTheme(category)
  return <Icon size={size} strokeWidth={2} color={`hsl(${hue} 55% 42%)`} />
}
