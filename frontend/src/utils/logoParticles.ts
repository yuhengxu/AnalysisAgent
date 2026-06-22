import type { LogoParticle } from '../types/agentVisual'
import { buildLogoStrokes, type ColorRole, type Stroke, type Vec2 } from './logoGeometry'

// Base distance between samples along a stroke centerline, in normalized units.
// `density` scales this: higher density => smaller step => more particles.
// Kept airy on purpose so the mark reads clearly with breathing room (see demo).
const BASE_STEP = 0.021
// Spacing of the perpendicular samples that give a stroke its band width.
const CROSS_STEP = 0.03

const COLOR_HEX: Record<ColorRole, string> = {
  white: '#f3faff',
  cyan: '#c2e4ff',
  blue: '#58a9ff',
  deep: '#2f86f0',
}

const BASE_INTENSITY: Record<ColorRole, number> = {
  white: 0.95,
  cyan: 0.78,
  blue: 0.56,
  deep: 0.42,
}

function strokeLength(pts: Vec2[]): number {
  let len = 0
  for (let i = 1; i < pts.length; i++) {
    len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
  }
  return len
}

// Walk a polyline at a fixed arc-length step, returning position + unit normal.
function walk(pts: Vec2[], step: number): { p: Vec2; nx: number; ny: number }[] {
  const out: { p: Vec2; nx: number; ny: number }[] = []
  let carry = 0
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]
    const b = pts[i]
    const dx = b.x - a.x
    const dy = b.y - a.y
    const seg = Math.hypot(dx, dy)
    if (seg < 1e-6) continue
    const ux = dx / seg
    const uy = dy / seg
    // Normal is the tangent rotated 90deg.
    const nx = -uy
    const ny = ux
    let d = carry
    while (d <= seg) {
      out.push({ p: { x: a.x + ux * d, y: a.y + uy * d }, nx, ny })
      d += step
    }
    carry = d - seg
  }
  return out
}

function makeParticle(
  x: number,
  y: number,
  stroke: Stroke,
): LogoParticle {
  const edge = stroke.role === 'edge'
  const intensity = Math.min(
    1,
    Math.max(0.32, BASE_INTENSITY[stroke.colorRole] + (Math.random() - 0.5) * 0.14),
  )
  return {
    baseX: x,
    baseY: y,
    depth: stroke.depth + (Math.random() - 0.5) * 0.07 + Math.sin(x * 4.3 + y * 3.1) * 0.02,
    size: edge ? 0.4 + Math.random() * 0.3 : 0.28 + Math.random() * 0.22,
    color: COLOR_HEX[stroke.colorRole],
    alpha: edge ? 0.74 + Math.random() * 0.2 : 0.46 + Math.random() * 0.2,
    intensity,
    phase: Math.random() * Math.PI * 2,
    orbit: Math.random() * Math.PI * 2,
    layer: stroke.role,
  }
}

function normalizeParticles(pts: LogoParticle[]): LogoParticle[] {
  if (!pts.length) return pts
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const p of pts) {
    minX = Math.min(minX, p.baseX)
    maxX = Math.max(maxX, p.baseX)
    minY = Math.min(minY, p.baseY)
    maxY = Math.max(maxY, p.baseY)
  }
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const span = Math.max(maxX - minX, maxY - minY, 0.001)
  const scale = 1.92 / span
  return pts.map((p) => ({
    ...p,
    baseX: (p.baseX - cx) * scale,
    baseY: (p.baseY - cy) * scale,
  }))
}

// Build the full particle field for the CNOOC mark.
// `density` ~= 1 yields a field whose density approximates the reference image
// (clearly readable, not overly dense). Higher values pack particles tighter.
export function buildLogoParticles(density = 1): LogoParticle[] {
  const strokes = buildLogoStrokes()
  const step = BASE_STEP / Math.max(0.2, density)
  const particles: LogoParticle[] = []

  for (const stroke of strokes) {
    if (strokeLength(stroke.pts) < 1e-4) continue
    const samples = walk(stroke.pts, step)
    const crossN = Math.max(1, Math.round(stroke.width / CROSS_STEP))
    const half = stroke.width / 2
    for (const { p, nx, ny } of samples) {
      for (let k = 0; k < crossN; k++) {
        const base = crossN === 1 ? 0 : (k / (crossN - 1)) * 2 - 1
        const off = base * half + (Math.random() - 0.5) * CROSS_STEP * 0.8
        const along = (Math.random() - 0.5) * step * 0.7
        // Tangent direction is (ny, -nx) since normal = (nx, ny).
        const x = p.x + nx * off + ny * along
        const y = p.y + ny * off - nx * along
        particles.push(makeParticle(x, y, stroke))
      }
    }
  }

  return normalizeParticles(particles)
}
