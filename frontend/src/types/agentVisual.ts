export type AgentMood =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'analyzing'
  | 'predicting'
  | 'reporting'
  | 'success'
  | 'error'

export interface AgentVisualState {
  mood: AgentMood
  colors: string[]
  particle_speed: number
  glow_intensity: number
  pulse_rate: number
  status_text?: string
}

export const DEFAULT_VISUAL: AgentVisualState = {
  mood: 'idle',
  colors: ['#eaf6ff', '#3fa0ff', '#0a4fce'],
  particle_speed: 0.9,
  glow_intensity: 0.55,
  pulse_rate: 1.0,
  status_text: '在线 · 随时为您服务',
}

export interface LogoParticle {
  baseX: number
  baseY: number
  depth: number
  size: number
  color: string
  alpha: number
  intensity: number
  phase: number
  orbit: number
  layer?: 'edge' | 'fill'
}
