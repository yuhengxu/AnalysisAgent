// Generic image -> particle-field sampler (browser only; uses <canvas> pixels).
// Sample a clean source image (not an already-rendered particle image) so that
// density and color stay fully controllable. Pair with the additive sprite
// renderer described in SKILL.md.

export interface SampledParticle {
  baseX: number // normalized, roughly [-1, 1], centered
  baseY: number
  depth: number // pseudo-z for optional 3D wobble
  size: number
  color: string // hex; feed into a cached glow sprite
  alpha: number
  intensity: number // 0..1 source brightness, drives glow
  phase: number
  orbit: number
  layer: 'edge' | 'fill'
}

export interface SampleOptions {
  edgeCount?: number
  fillCount?: number
  sampleSize?: number
  /** How to detect the background that gets dropped. */
  background?: 'auto' | 'light' | 'dark'
  /** true => blue/white palette; false => keep the source image colors. */
  monochrome?: boolean
}

type Rgb = { r: number; g: number; b: number; a: number }

const lum = ({ r, g, b }: Rgb) => 0.299 * r + 0.587 * g + 0.114 * b
const chroma = ({ r, g, b }: Rgb) => Math.max(r, g, b) - Math.min(r, g, b)

function pixelAt(data: Uint8ClampedArray, w: number, x: number, y: number): Rgb {
  const i = (y * w + x) * 4
  return { r: data[i], g: data[i + 1], b: data[i + 2], a: data[i + 3] }
}

// Decide whether the source art sits on a light or dark background by sampling corners.
function detectBackground(data: Uint8ClampedArray, w: number, h: number): 'light' | 'dark' {
  const corners = [
    pixelAt(data, w, 1, 1),
    pixelAt(data, w, w - 2, 1),
    pixelAt(data, w, 1, h - 2),
    pixelAt(data, w, w - 2, h - 2),
  ]
  const avg = corners.reduce((s, c) => s + lum(c), 0) / corners.length
  return avg > 128 ? 'light' : 'dark'
}

function makeIsBackground(mode: 'light' | 'dark') {
  return (px: Rgb): boolean => {
    if (px.a < 48) return true
    if (mode === 'light') return lum(px) > 200 && chroma(px) < 40
    return lum(px) < 40 || (lum(px) < 60 && chroma(px) < 30)
  }
}

function isEdge(
  x: number,
  y: number,
  w: number,
  h: number,
  data: Uint8ClampedArray,
  isBg: (p: Rgb) => boolean,
): boolean {
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      if (dx === 0 && dy === 0) continue
      const nx = x + dx
      const ny = y + dy
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) return true
      if (isBg(pixelAt(data, w, nx, ny))) return true
    }
  }
  return false
}

function tint(px: Rgb, layer: 'edge' | 'fill', monochrome: boolean): string {
  if (!monochrome) {
    const hex = (n: number) => Math.round(n).toString(16).padStart(2, '0')
    return `#${hex(px.r)}${hex(px.g)}${hex(px.b)}`
  }
  if (layer === 'edge') return lum(px) > 168 ? '#f3faff' : '#c2e4ff'
  return px.b > 150 ? '#58a9ff' : '#2f86f0'
}

function intensityOf(px: Rgb, layer: 'edge' | 'fill'): number {
  const raw = Math.max(0, Math.min(1, (lum(px) - 80) / 175))
  return Math.max(layer === 'edge' ? 0.42 : 0.2, raw)
}

function normalize(pts: SampledParticle[]): SampledParticle[] {
  if (!pts.length) return pts
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const p of pts) {
    minX = Math.min(minX, p.baseX); maxX = Math.max(maxX, p.baseX)
    minY = Math.min(minY, p.baseY); maxY = Math.max(maxY, p.baseY)
  }
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const span = Math.max(maxX - minX, maxY - minY, 0.001)
  const scale = 1.92 / span
  return pts.map((p) => ({ ...p, baseX: (p.baseX - cx) * scale, baseY: (p.baseY - cy) * scale }))
}

export function sampleImageToParticles(
  image: HTMLImageElement,
  opts: SampleOptions = {},
): SampledParticle[] {
  const { edgeCount = 2600, fillCount = 1200, sampleSize = 256, monochrome = true } = opts

  const canvas = document.createElement('canvas')
  canvas.width = sampleSize
  canvas.height = sampleSize
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return []

  const scale = Math.min(sampleSize / image.width, sampleSize / image.height) * 0.96
  const w = image.width * scale
  const h = image.height * scale
  ctx.clearRect(0, 0, sampleSize, sampleSize)
  ctx.drawImage(image, (sampleSize - w) / 2, (sampleSize - h) / 2, w, h)
  const { data } = ctx.getImageData(0, 0, sampleSize, sampleSize)

  const mode = opts.background && opts.background !== 'auto'
    ? opts.background
    : detectBackground(data, sampleSize, sampleSize)
  const isBg = makeIsBackground(mode)

  const edges: { x: number; y: number; rgb: Rgb }[] = []
  const fills: { x: number; y: number; rgb: Rgb }[] = []
  for (let y = 1; y < sampleSize - 1; y++) {
    for (let x = 1; x < sampleSize - 1; x++) {
      const rgb = pixelAt(data, sampleSize, x, y)
      if (isBg(rgb)) continue
      const entry = { x, y, rgb }
      if (isEdge(x, y, sampleSize, sampleSize, data, isBg)) edges.push(entry)
      else fills.push(entry)
    }
  }

  const cell = 2
  const used = new Set<string>()
  const pick = (
    pool: typeof edges,
    limit: number,
    layer: 'edge' | 'fill',
  ): SampledParticle[] => {
    const out: SampledParticle[] = []
    if (!pool.length) return out
    const stride = Math.max(1, Math.floor(pool.length / (limit * 3)))
    for (let i = 0; i < pool.length && out.length < limit; i += stride) {
      const c = pool[(i * 7 + 3) % pool.length]
      const key = `${Math.floor(c.x / cell)}:${Math.floor(c.y / cell)}`
      if (used.has(key)) continue
      used.add(key)
      out.push({
        baseX: (c.x / sampleSize) * 2 - 1,
        baseY: (c.y / sampleSize) * 2 - 1,
        depth: (Math.random() - 0.5) * (layer === 'edge' ? 0.1 : 0.18),
        size: layer === 'edge' ? 0.4 + Math.random() * 0.3 : 0.28 + Math.random() * 0.22,
        color: tint(c.rgb, layer, monochrome),
        alpha: layer === 'edge' ? 0.74 + Math.random() * 0.2 : 0.46 + Math.random() * 0.2,
        intensity: intensityOf(c.rgb, layer),
        phase: Math.random() * Math.PI * 2,
        orbit: Math.random() * Math.PI * 2,
        layer,
      })
    }
    return out
  }

  return normalize([...pick(edges, edgeCount, 'edge'), ...pick(fills, fillCount, 'fill')])
}

export function loadImageParticles(
  url: string,
  opts: SampleOptions = {},
): Promise<SampledParticle[]> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(sampleImageToParticles(img, opts))
    img.onerror = () => resolve([])
    img.src = url
  })
}
