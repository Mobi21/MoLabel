import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Sparkles,
  X,
  Send,
  Compass,
  BookOpen,
  Play,
  BarChart3,
  User,
  Bot,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'

// ── Types ────────────────────────────────────────────────────────────────────

type AssistantMode = 'guide' | 'explain' | 'operator' | 'monitor'

interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
}

// ── Data ─────────────────────────────────────────────────────────────────────

const modeConfig: Record<
  AssistantMode,
  { label: string; icon: React.ReactNode }
> = {
  guide: { label: 'Guide', icon: <Compass className="h-3 w-3" /> },
  explain: { label: 'Explain', icon: <BookOpen className="h-3 w-3" /> },
  operator: { label: 'Operator', icon: <Play className="h-3 w-3" /> },
  monitor: { label: 'Monitor', icon: <BarChart3 className="h-3 w-3" /> },
}

const pageTitles: Record<string, string> = {
  '/': 'Home > Dashboard',
  '/mission-control': 'Operations > Mission Control',
  '/data': 'Data > Dataset Catalog',
  '/tasks': 'Tasks > Task Schemas',
  '/workflow': 'Workflow > Pipeline Builder',
  '/agents': 'Agents > Agent Runs',
  '/review': 'Review > Review Queue',
  '/adjudication': 'Adjudication > Disagreements',
  '/quality': 'Quality > Quality Metrics',
  '/curation': 'Curation > Data Curation',
  '/exports': 'Exports > Releases',
  '/plugins': 'Settings > Plugins',
  '/settings': 'Settings > Preferences',
}

const mockMessages: ChatMessage[] = [
  {
    id: 'msg-001',
    role: 'assistant',
    content:
      'Welcome to MoLabel! I can help you navigate your workflow, explain metrics, or run operations. What would you like to do?',
  },
  {
    id: 'msg-002',
    role: 'user',
    content: 'What should I focus on next?',
  },
  {
    id: 'msg-003',
    role: 'assistant',
    content:
      "Based on your current state: The Construction Zones dataset needs attention \u2014 it's only 25% labeled and marked as critical. I recommend running an AI pre-label batch on it first, then routing the results to your review queue. Would you like me to set that up?",
  },
]

const quickActions = [
  "What's next?",
  'Explain this page',
  'Run status',
] as const

// ── Context Badge ────────────────────────────────────────────────────────────

function ContextBar({ pathname }: { pathname: string }) {
  const segments = pathname.split('/').filter(Boolean)
  const base = `/${segments[0] ?? ''}`
  const contextLabel = pageTitles[pathname] ?? pageTitles[base] ?? 'MoLabel'

  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2">
      <span className="text-[11px] text-muted-foreground">You&apos;re on:</span>
      <Badge variant="secondary" className="text-[11px] font-normal">
        {contextLabel}
      </Badge>
    </div>
  )
}

// ── Chat Bubble ──────────────────────────────────────────────────────────────

function ChatBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === 'assistant'

  return (
    <div
      className={cn(
        'flex gap-2.5',
        isAssistant ? 'items-start' : 'flex-row-reverse items-start',
      )}
    >
      <div
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
          isAssistant
            ? 'bg-primary/10 text-primary'
            : 'bg-zinc-500/10 text-zinc-500',
        )}
      >
        {isAssistant ? (
          <Bot className="h-3 w-3" />
        ) : (
          <User className="h-3 w-3" />
        )}
      </div>
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed',
          isAssistant
            ? 'bg-muted text-foreground'
            : 'bg-primary text-primary-foreground',
        )}
      >
        {message.content}
      </div>
    </div>
  )
}

// ── Panel ────────────────────────────────────────────────────────────────────

export function AssistantPanel() {
  const { assistantOpen, toggleAssistant } = useUIStore()
  const location = useLocation()
  const [activeMode, setActiveMode] = useState<AssistantMode>('guide')
  const [inputValue, setInputValue] = useState('')

  return (
    <>
      {/* Backdrop — subtle overlay when open */}
      {assistantOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/10 lg:hidden"
          onClick={toggleAssistant}
        />
      )}

      {/* Panel */}
      <div
        className={cn(
          'fixed right-0 top-0 z-50 flex h-full w-80 flex-col border-l border-border bg-background shadow-lg transition-transform duration-300 ease-in-out',
          assistantOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {/* Header */}
        <div className="flex h-12 items-center justify-between border-b border-border px-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">AI Assistant</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={toggleAssistant}
          >
            <X className="h-3.5 w-3.5" />
            <span className="sr-only">Close assistant</span>
          </Button>
        </div>

        {/* Mode Selector */}
        <div className="border-b border-border px-4 py-2.5">
          <div className="flex gap-1">
            {(Object.keys(modeConfig) as AssistantMode[]).map((mode) => {
              const config = modeConfig[mode]
              return (
                <Button
                  key={mode}
                  variant={activeMode === mode ? 'secondary' : 'ghost'}
                  size="sm"
                  className={cn(
                    'h-7 gap-1 px-2 text-[11px]',
                    activeMode === mode && 'font-semibold',
                  )}
                  onClick={() => setActiveMode(mode)}
                >
                  {config.icon}
                  {config.label}
                </Button>
              )
            })}
          </div>
        </div>

        {/* Context Bar */}
        <div className="border-b border-border px-4 py-2.5">
          <ContextBar pathname={location.pathname} />
        </div>

        {/* Chat Area */}
        <ScrollArea className="flex-1 px-4">
          <div className="space-y-4 py-4">
            {mockMessages.map((msg) => (
              <ChatBubble key={msg.id} message={msg} />
            ))}
          </div>
        </ScrollArea>

        {/* Quick Actions */}
        <div className="border-t border-border px-4 py-2.5">
          <div className="flex flex-wrap gap-1.5">
            {quickActions.map((action) => (
              <Button
                key={action}
                variant="outline"
                size="sm"
                className="h-6 px-2 text-[10px]"
              >
                {action}
              </Button>
            ))}
          </div>
        </div>

        <Separator />

        {/* Input Area */}
        <div className="p-3">
          <div className="flex gap-2">
            <Textarea
              placeholder="Ask about your data, workflow, or quality..."
              className="min-h-[36px] resize-none text-xs"
              rows={1}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  setInputValue('')
                }
              }}
            />
            <Button
              size="icon"
              className="h-9 w-9 shrink-0"
              disabled={inputValue.trim().length === 0}
              onClick={() => setInputValue('')}
            >
              <Send className="h-3.5 w-3.5" />
              <span className="sr-only">Send message</span>
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
