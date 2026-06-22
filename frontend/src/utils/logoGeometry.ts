// Procedural geometry of the CNOOC logo, expressed as parametric strokes in a
// normalized design space (x: right+, y: down+, roughly within [-1, 1]).
// No image sampling is involved; every part of the mark is derived by formula
// so that particle density, depth layering and color can be fully controlled.

export type ColorRole = 'white' | 'cyan' | 'blue' | 'deep'

export interface Vec2 {
  x: number
  y: number
}

export interface Stroke {
  // Fine-sampled centerline polyline.
  pts: Vec2[]
  // Total band width across the centerline (particles jitter within +/- width/2).
  width: number
  // Base depth along the view axis (larger = closer to viewer).
  depth: number
  colorRole: ColorRole
  role: 'edge' | 'fill'
}

const TAU = Math.PI * 2
const D = Math.PI / 180

// Sample an arc by arc-length so density stays even regardless of radius.
function arc(cx: number, cy: number, r: number, a0: number, a1: number): Vec2[] {
  const span = Math.abs(a1 - a0)
  const steps = Math.max(8, Math.round((span * r) / 0.01))
  const pts: Vec2[] = []
  for (let i = 0; i <= steps; i++) {
    const a = a0 + ((a1 - a0) * i) / steps
    pts.push({ x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r })
  }
  return pts
}

// Sample a cubic bezier.
function cubic(p0: Vec2, c0: Vec2, c1: Vec2, p1: Vec2, steps = 64): Vec2[] {
  const pts: Vec2[] = []
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const mt = 1 - t
    const a = mt * mt * mt
    const b = 3 * mt * mt * t
    const c = 3 * mt * t * t
    const d = t * t * t
    pts.push({
      x: a * p0.x + b * c0.x + c * c1.x + d * p1.x,
      y: a * p0.y + b * c0.y + c * c1.y + d * p1.y,
    })
  }
  return pts
}

// Densify a coarse polyline so arc-length walking later is smooth.
function poly(points: Vec2[]): Vec2[] {
  const out: Vec2[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const len = Math.hypot(b.x - a.x, b.y - a.y)
    const steps = Math.max(2, Math.round(len / 0.01))
    for (let s = 0; s < steps; s++) {
      const t = s / steps
      out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
    }
  }
  out.push(points[points.length - 1])
  return out
}

// Minimal stroke-font for the letters used in "CNOOC".
function glyph(letter: string, ox: number, oy: number, cw: number, ch: number): Vec2[][] {
  const X = (u: number) => ox + u * cw
  const Y = (v: number) => oy + v * ch
  const r = Math.min(cw, ch) * 0.5
  const cx = ox + cw * 0.5
  const cy = oy + ch * 0.5
  switch (letter) {
    case 'C':
      return [arc(cx, cy, r, 52 * D, 308 * D)]
    case 'O':
      return [arc(cx, cy, r, 0, TAU)]
    case 'N':
      return [poly([
        { x: X(0.12), y: Y(1) },
        { x: X(0.12), y: Y(0) },
        { x: X(0.88), y: Y(1) },
        { x: X(0.88), y: Y(0) },
      ])]
    default:
      return []
  }
}

export function buildLogoStrokes(): Stroke[] {
  const strokes: Stroke[] = []

  // Outer "C" ring: thick blue ring opening on the right (oceanic globe).
  strokes.push({
    pts: arc(0, 0.04, 0.6, 38 * D, 322 * D),
    width: 0.052,
    depth: 0.0,
    colorRole: 'blue',
    role: 'edge',
  })

  // Inner ring "O": opens at the top so the derrick can rise through it.
  strokes.push({
    pts: arc(-0.03, 0.05, 0.32, 296 * D, 244 * D + 360 * D),
    width: 0.04,
    depth: 0.2,
    colorRole: 'cyan',
    role: 'edge',
  })

  // Derrick tower: tall slim spike, the foremost and brightest element.
  const apex = { x: 0, y: -0.82 }
  const baseL = { x: -0.058, y: 0.08 }
  const baseR = { x: 0.058, y: 0.08 }
  strokes.push({
    pts: poly([baseL, apex, baseR]),
    width: 0.02,
    depth: 0.58,
    colorRole: 'white',
    role: 'edge',
  })
  strokes.push({
    pts: poly([apex, { x: 0, y: 0.08 }]),
    width: 0.016,
    depth: 0.5,
    colorRole: 'white',
    role: 'edge',
  })

  // Central "人/N" splay strokes of the CN mark.
  const fork = { x: 0, y: -0.04 }
  strokes.push({
    pts: poly([fork, { x: -0.18, y: 0.26 }]),
    width: 0.024,
    depth: 0.42,
    colorRole: 'white',
    role: 'edge',
  })
  strokes.push({
    pts: poly([fork, { x: 0.18, y: 0.26 }]),
    width: 0.024,
    depth: 0.42,
    colorRole: 'cyan',
    role: 'edge',
  })

  // Three sea-wave ribbons sweeping along the bottom.
  const waves: [Vec2, Vec2, Vec2, Vec2][] = [
    [{ x: -0.52, y: 0.36 }, { x: -0.18, y: 0.52 }, { x: 0.16, y: 0.56 }, { x: 0.52, y: 0.34 }],
    [{ x: -0.5, y: 0.46 }, { x: -0.16, y: 0.62 }, { x: 0.18, y: 0.64 }, { x: 0.54, y: 0.42 }],
    [{ x: -0.46, y: 0.56 }, { x: -0.12, y: 0.71 }, { x: 0.2, y: 0.72 }, { x: 0.5, y: 0.5 }],
  ]
  for (const [p0, c0, c1, p1] of waves) {
    strokes.push({
      pts: cubic(p0, c0, c1, p1),
      width: 0.03,
      depth: -0.26,
      colorRole: 'deep',
      role: 'fill',
    })
  }

  // "CNOOC" block lettering on the right side.
  const text = 'CNOOC'
  const cw = 0.082
  const ch = 0.2
  const advance = 0.1
  const startX = 0.13
  const baseY = 0.06
  for (let i = 0; i < text.length; i++) {
    const ox = startX + i * advance
    for (const sub of glyph(text[i], ox, baseY, cw, ch)) {
      strokes.push({
        pts: sub,
        width: 0.013,
        depth: 0.06,
        colorRole: 'cyan',
        role: 'edge',
      })
    }
  }

  return strokes
}
