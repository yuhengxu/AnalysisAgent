export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

export const AGENT_CHAT_WELCOME =
  '您好，我是 AI 助手，具备能源行业专业分析能力，也可自由讨论各类话题。' +
  '可检索互联网资讯、解读平台数据；也可明确要求生成「预测分析表」「月报」等交付物。'

const STORAGE_KEY = 'agent_chat_history'
export const MAX_CHAT_ROUNDS = 10
const MAX_HISTORY_MSGS = MAX_CHAT_ROUNDS * 2

function isWelcomeMessage(msg: ChatMsg) {
  return msg.role === 'assistant' && msg.content === AGENT_CHAT_WELCOME
}

export function defaultChatMessages(): ChatMsg[] {
  return [{ role: 'assistant', content: AGENT_CHAT_WELCOME }]
}

export function trimChatHistory(messages: ChatMsg[]): ChatMsg[] {
  if (!messages.length) return defaultChatMessages()
  const hasWelcome = isWelcomeMessage(messages[0])
  const rest = hasWelcome ? messages.slice(1) : messages
  const trimmed = rest.slice(-MAX_HISTORY_MSGS)
  return hasWelcome ? [{ role: 'assistant', content: AGENT_CHAT_WELCOME }, ...trimmed] : trimmed
}

export function loadChatHistory(): ChatMsg[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultChatMessages()
    const parsed = JSON.parse(raw) as ChatMsg[]
    if (!Array.isArray(parsed) || parsed.length === 0) return defaultChatMessages()
    const valid = parsed.filter(
      (m) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string',
    )
    return trimChatHistory(valid.length ? valid : defaultChatMessages())
  } catch {
    return defaultChatMessages()
  }
}

export function saveChatHistory(messages: ChatMsg[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimChatHistory(messages)))
}

export function clearChatHistory(): ChatMsg[] {
  localStorage.removeItem(STORAGE_KEY)
  return defaultChatMessages()
}
