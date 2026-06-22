import { useEffect, useRef } from 'react'
import type { AgentVisualState, LogoParticle } from '../types/agentVisual'
import { buildLogoParticles } from '../utils/logoParticles'

interface Props {
  size?: number
  width?: number
  height?: number
  visual: AgentVisualState
  active?: boolean
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

// Pre-render a soft glowing dot (white-hot core + colored halo) to an offscreen
// canvas once. Per-frame we only drawImage these sprites, so there is NO costly
// per-particle shadowBlur and the whole field stays cheap to paint.
function makeGlowSprite(hex: string): HTMLCanvasElement {
  const s = 64
  const c = document.createElement('canvas')
  c.width = s
  c.height = s
  const g = c.getContext('2d')!
  const [r, gg, b] = hexToRgb(hex)
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.16, `rgba(${r},${gg},${b},0.96)`)
  grad.addColorStop(0.42, `rgba(${r},${gg},${b},0.34)`)
  grad.addColorStop(1, `rgba(${r},${gg},${b},0)`)
  g.fillStyle = grad
  g.fillRect(0, 0, s, s)
  return c
}

export default function AgentAvatar({ size = 88, width = size, height = size, visual, active = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<LogoParticle[]>([])
  const spritesRef = useRef<Map<string, HTMLCanvasElement>>(new Map())
  const hotSpriteRef = useRef<HTMLCanvasElement | null>(null)
  const visualRef = useRef(visual)
  const activeRef = useRef(active)
  const rafRef = useRef(0)

  visualRef.current = visual
  activeRef.current = active

  useEffect(() => {
    // Fewer particles for small avatars keeps every instance smooth.
    const density = Math.max(0.4, Math.min(1, Math.min(width, height) / 200))
    const pts = buildLogoParticles(density)
    particlesRef.current = pts

    const cache = new Map<string, HTMLCanvasElement>()
    for (const p of pts) {
      if (!cache.has(p.color)) cache.set(p.color, makeGlowSprite(p.color))
    }
    spritesRef.current = cache
    hotSpriteRef.current = makeGlowSprite('#f6fbff')
  }, [width, height])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const focal = 2.7
    let last = 0

    const draw = (now: number) => {
      // Cap to ~60fps and skip duplicate frames to avoid wasted work.
      if (now - last < 15) {
        rafRef.current = requestAnimationFrame(draw)
        return
      }
      last = now

      const v = visualRef.current
      const speed = v.particle_speed * (activeRef.current ? 1.18 : 1)
      const glow = v.glow_intensity
      const breath = 1 + Math.sin(now * 0.001 * v.pulse_rate) * 0.028
      const pts = particlesRef.current
      const sprites = spritesRef.current
      const hot = hotSpriteRef.current

      ctx.clearRect(0, 0, width, height)

      drawWaveRibbons(ctx, now, width, height, speed, glow)

      const cx = width / 2
      const cy = height / 2
      const radius = Math.min(width, height) * 0.44 * breath
      const floatY = Math.sin(now * 0.0011) * height * 0.012

      const yaw = Math.sin(now * 0.00028 * speed) * 0.42
      const pitch = -0.05 + Math.sin(now * 0.00022) * 0.1
      const cosY = Math.cos(yaw)
      const sinY = Math.sin(yaw)
      const cosP = Math.cos(pitch)
      const sinP = Math.sin(pitch)

      const sweepA = ((((now * 0.00024 * speed) % 2.6) + 2.6) % 2.6) - 1.3
      const sweepB = 1.3 - ((((now * 0.00017 * speed + 0.6) % 2.6) + 2.6) % 2.6)

      // Single additive pass. Because 'lighter' blending is order-independent we
      // skip depth sorting entirely and draw each particle's cached sprite once.
      ctx.globalCompositeOperation = 'lighter'

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i]
        const zc = p.depth * 0.92
        const x1 = p.baseX * cosY + zc * sinY
        const z1 = -p.baseX * sinY + zc * cosY
        const y2 = p.baseY * cosP - z1 * sinP
        const z2 = p.baseY * sinP + z1 * cosP
        const persp = focal / (focal - z2)

        const diag = p.baseX * 0.7 + p.baseY * 0.72
        const sa = Math.exp(-(((diag - sweepA) / 0.2) ** 2))
        const sb = Math.exp(-(((diag - sweepB) / 0.26) ** 2))
        const flow = sa + sb * 0.7

        const drift = now * 0.00045 * speed + p.orbit
        const driftX = Math.cos(drift + p.baseY * 4.2) * 0.5
        const driftY = Math.sin(drift + p.baseX * 4.0) * 0.42

        const light = p.intensity
        const depthShade = 0.86 + Math.max(-0.35, Math.min(0.5, z2)) * 0.4
        const bright = depthShade * (0.6 + light * 0.7 + flow * 0.5) * (0.7 + glow * 0.6)
        const alpha = Math.min(1, p.alpha * bright)

        const x = cx + x1 * radius * persp + driftX
        const y = cy + y2 * radius * persp * 0.96 + driftY + floatY

        const isHot = flow > 0.55 || light > 0.86
        const sprite = isHot && hot ? hot : sprites.get(p.color)
        if (!sprite) continue
        const r = Math.max(1.2, p.size * persp * (3.6 + flow * 2.2) * (p.layer === 'edge' ? 1 : 0.78))

        ctx.globalAlpha = alpha
        ctx.drawImage(sprite, x - r, y - r, r * 2, r * 2)
      }

      ctx.globalCompositeOperation = 'source-over'
      ctx.globalAlpha = 1

      rafRef.current = requestAnimationFrame(draw)
    }
    rafRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafRef.current)
  }, [height, width])

  return <canvas ref={canvasRef} className="agent-avatar-canvas block" aria-hidden />
}

// Soft deep-blue silk ribbons drifting behind the mark (requirement 6).
// Uses translucent gradient strokes only -- no per-segment shadowBlur.
function drawWaveRibbons(
  ctx: CanvasRenderingContext2D,
  now: number,
  w: number,
  h: number,
  speed: number,
  glow: number,
) {
  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  const ribbons = 4
  const stepX = Math.max(4, w / 48)
  for (let i = 0; i < ribbons; i++) {
    const t = i / (ribbons - 1)
    const baseY = h * (0.32 + t * 0.42)
    const amp = h * (0.05 + t * 0.04)
    const freq = (1.6 + t * 0.7) / w
    const phase = now * 0.00045 * speed + i * 1.7
    const grad = ctx.createLinearGradient(0, 0, w, 0)
    grad.addColorStop(0, 'rgba(8, 38, 96, 0)')
    grad.addColorStop(0.5, `rgba(40, 120, 230, ${0.1 + glow * 0.08})`)
    grad.addColorStop(1, 'rgba(8, 38, 96, 0)')

    ctx.beginPath()
    for (let x = 0; x <= w; x += stepX) {
      const y =
        baseY +
        Math.sin(x * freq * Math.PI * 2 + phase) * amp +
        Math.sin(x * freq * Math.PI * 4.3 + phase * 1.3) * amp * 0.3
      if (x === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.strokeStyle = grad
    ctx.lineWidth = h * (0.05 + t * 0.03)
    ctx.stroke()

    ctx.beginPath()
    for (let x = 0; x <= w; x += stepX) {
      const y =
        baseY +
        Math.sin(x * freq * Math.PI * 2 + phase) * amp +
        Math.sin(x * freq * Math.PI * 4.3 + phase * 1.3) * amp * 0.3
      if (x === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.strokeStyle = `rgba(150, 205, 255, ${0.1 + glow * 0.08})`
    ctx.lineWidth = Math.max(0.6, h * 0.006)
    ctx.stroke()
  }
  ctx.restore()
}
