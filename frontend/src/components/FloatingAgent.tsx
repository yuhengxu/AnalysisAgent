import { useCallback, useState } from 'react'
import AgentAvatar from './AgentAvatar'
import AgentChat from './AgentChat'
import { DEFAULT_VISUAL, type AgentVisualState } from '../types/agentVisual'

export default function FloatingAgent() {
  const [open, setOpen] = useState(false)
  const [visual, setVisual] = useState<AgentVisualState>(DEFAULT_VISUAL)
  const [thinking, setThinking] = useState(false)

  const toggle = useCallback(() => setOpen((v) => !v), [])

  return (
    <>
      <div className="agent-fab pointer-events-none fixed bottom-5 right-5 z-40 flex flex-col items-end">
        <button
          type="button"
          onClick={toggle}
          className="agent-fab-btn pointer-events-auto relative flex h-[12rem] w-[18rem] items-center justify-center border-0 bg-transparent p-0"
          title="打开能源分析助手"
          aria-label="打开能源分析助手"
        >
          <AgentAvatar width={288} height={192} visual={visual} active={thinking || open} />
        </button>
      </div>
      {open && (
        <AgentChat
          onClose={() => setOpen(false)}
          visual={visual}
          onVisualChange={setVisual}
          onThinkingChange={setThinking}
        />
      )}
    </>
  )
}
