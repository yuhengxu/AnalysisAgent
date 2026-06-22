---
name: image-to-particle-logo
description: Convert any image (logo, icon, silhouette) into a glowing particle field and render it performantly on an HTML canvas. Use when turning a picture/logo into animated light particles, building a particle avatar, or sampling an image into points for a Three.js/canvas particle effect.
---

# Image to Particle Logo

Turn a source image into a field of glowing particles, then render it with a
high-performance, additive-glow canvas loop. Two reusable pieces:

- `scripts/sampleImageParticles.ts` - samples an image into particles (browser, uses `<canvas>` pixel data).
- A rendering recipe (below) that stays smooth with thousands of particles.

## When to use

- "Make this logo into glowing particles / a particle avatar."
- "Sample this image into points for a particle animation."
- Reusing the effect for a new image: only the source URL + color/background options change.

## Quick start

1. Copy `scripts/sampleImageParticles.ts` into the project (e.g. `src/utils/`).
2. Load particles from any image URL:

```ts
import { loadImageParticles } from './utils/sampleImageParticles'

const particles = await loadImageParticles('/my-logo.png', {
  edgeCount: 3000,      // bright outline particles
  fillCount: 1400,      // dimmer interior particles
  background: 'auto',   // 'light' (white bg), 'dark', or 'auto'
  monochrome: true,     // map to blue/white; false keeps source colors
})
```

3. Render with the performant loop in "Rendering recipe".

## Sampling options

| Option | Default | Meaning |
|--------|---------|---------|
| `edgeCount` | 2600 | Target number of outline particles (controls visible density) |
| `fillCount` | 1200 | Target number of interior particles |
| `sampleSize` | 256 | Offscreen sampling resolution (higher = finer, slower) |
| `background` | `'auto'` | How to detect the background to drop: `'light'`, `'dark'`, `'auto'` |
| `monochrome` | `true` | `true` = blue/white palette; `false` = keep the image's own colors |

Density rule of thumb: pick `edgeCount` so the shape is clearly readable but not
a solid mass. For a logo, ~3000-4000 edge particles reads well; halve it for small avatars.

## Rendering recipe (must stay performant)

The single most important performance rule: **never call `ctx.shadowBlur` per
particle.** With thousands of particles that destroys the frame rate. Instead:

1. Pre-render one soft glow sprite per color to an offscreen canvas ONCE
   (radial gradient: white core -> color -> transparent).
2. Each frame, set `ctx.globalCompositeOperation = 'lighter'` (additive) and
   `drawImage` the cached sprite for every particle. Additive blending is
   order-independent, so **skip depth sorting**.
3. Modulate brightness with `ctx.globalAlpha` and sprite scale, not shadows.

```ts
function makeGlowSprite(hex: string): HTMLCanvasElement {
  const s = 64
  const c = document.createElement('canvas'); c.width = c.height = s
  const g = c.getContext('2d')!
  const n = parseInt(hex.slice(1), 16)
  const [r, gg, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.16, `rgba(${r},${gg},${b},0.96)`)
  grad.addColorStop(0.42, `rgba(${r},${gg},${b},0.34)`)
  grad.addColorStop(1, `rgba(${r},${gg},${b},0)`)
  g.fillStyle = grad; g.fillRect(0, 0, s, s)
  return c
}

// Per frame (pts = particles, sprites = Map<color, canvas>):
ctx.clearRect(0, 0, w, h)
ctx.globalCompositeOperation = 'lighter'
for (const p of pts) {
  const x = cx + p.baseX * radius
  const y = cy + p.baseY * radius
  const rad = p.size * (p.layer === 'edge' ? 5 : 3.5)
  ctx.globalAlpha = Math.min(1, p.alpha * (0.6 + p.intensity * 0.7))
  const sprite = sprites.get(p.color)!
  ctx.drawImage(sprite, x - rad, y - rad, rad * 2, rad * 2)
}
ctx.globalCompositeOperation = 'source-over'
```

### Optional polish (cheap)

- 3D wobble: rotate `(baseX, depth)` around Y by a small oscillating `yaw`, then
  perspective-divide. Use `depth` to push some parts forward.
- Flow/streaks: add a moving gaussian band over a diagonal coordinate
  `d = baseX*0.7 + baseY*0.7` and add its value to brightness.
- Cap the loop to ~60fps (`if (now - last < 15) return`) and clamp
  `devicePixelRatio` to 2 on hi-dpi screens.

## Performance checklist

- [ ] No `shadowBlur` inside the per-particle loop
- [ ] Glow sprites pre-rendered once and cached by color
- [ ] `globalCompositeOperation = 'lighter'`, no depth sort
- [ ] Particle count scaled down for small render sizes
- [ ] Frame rate capped; `devicePixelRatio` clamped

## Notes

- Sampling reads pixels via `<canvas>`, so the image must be same-origin or
  served with CORS (`img.crossOrigin = 'anonymous'`).
- Do NOT sample from an already-rendered particle image; sample the clean source
  art so density and color stay controllable.
