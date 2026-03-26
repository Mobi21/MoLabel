import {
  Activity,
  AlertTriangle,
  AlertCircle,
  Bot,
  CheckCircle,
  Clock,
  ExternalLink,
  Gauge,
  Heart,
  ListChecks,
  Pause,
  Radio,
  Server,
  Shield,
  XCircle,
  Zap,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { mockActivity } from '@/mocks/data'
import type { ActivityItem } from '@/mocks/data'
import { relativeTime } from '@/lib/format'

// ── Helpers ──────────────────────────────────────────────────────────────────

const activityDotColor: Record<ActivityItem['type'], string> = {
  agent_run: 'bg-blue-500',
  review: 'bg-emerald-500',
  export: 'bg-purple-500',
  workflow: 'bg-orange-500',
  system: 'bg-zinc-400',
}

// ── Status Bar ───────────────────────────────────────────────────────────────

function StatusBar() {
  const indicators = [
    {
      label: 'Active Agents',
      value: '3 running',
      dotClass: 'bg-emerald-500',
      animate: true,
    },
    {
      label: 'Queue Depth',
      value: '16,825 pending',
      dotClass: 'bg-orange-500',
      animate: false,
    },
    {
      label: 'Failed Steps',
      value: '1 failure',
      dotClass: 'bg-red-500',
      animate: false,
    },
    {
      label: 'Human Decisions',
      value: '186 waiting',
      dotClass: 'bg-amber-500',
      animate: false,
    },
    {
      label: 'Release Blockers',
      value: '2 blockers',
      dotClass: 'bg-red-500',
      animate: false,
    },
  ] as const

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {indicators.map((ind) => (
            <div key={ind.label} className="flex items-center gap-3">
              <div className="relative flex h-3 w-3 items-center justify-center">
                <span
                  className={`absolute inline-flex h-full w-full rounded-full ${ind.dotClass} ${
                    ind.animate ? 'animate-ping opacity-75' : ''
                  }`}
                />
                <span
                  className={`relative inline-flex h-2.5 w-2.5 rounded-full ${ind.dotClass}`}
                />
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {ind.label}
                </span>
                <span className="text-base font-semibold tabular-nums">
                  {ind.value}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Active Workflows ─────────────────────────────────────────────────────────

function ActiveWorkflows() {
  const workflows = [
    {
      name: 'Standard Labeling Pipeline',
      progress: 62,
      currentStep: 'Human Review',
      eta: '~4 hours',
      status: 'active' as const,
    },
    {
      name: 'Edge Case Triage',
      progress: 35,
      currentStep: 'AI Pre-Label',
      eta: '~2 hours',
      status: 'active' as const,
    },
  ] as const

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Active Workflows</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {workflows.map((wf) => (
          <div
            key={wf.name}
            className="space-y-3 rounded-lg border border-border bg-muted/30 p-4"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{wf.name}</span>
              <Badge
                variant="outline"
                className="gap-1 border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                Active
              </Badge>
            </div>
            <Progress value={wf.progress} className="h-2.5 bg-muted" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Step:{' '}
                  <span className="font-medium text-foreground">
                    {wf.currentStep}
                  </span>
                </span>
                <span>
                  ETA:{' '}
                  <span className="font-medium text-foreground">{wf.eta}</span>
                </span>
              </div>
              <span className="font-semibold tabular-nums text-foreground">
                {wf.progress}%
              </span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ── Running Agents ───────────────────────────────────────────────────────────

function RunningAgents() {
  const agents = [
    {
      name: 'Claude Adjudicator',
      model: 'claude-sonnet-4',
      provider: 'Anthropic',
      dataset: 'Highway Nighttime',
      processed: 1_180,
      total: 2_400,
      cost: 12.45,
      status: 'running' as const,
    },
    {
      name: 'Quality Scorer',
      model: 'claude-sonnet-4',
      provider: 'Anthropic',
      dataset: 'Standard Pipeline',
      processed: 0,
      total: 0,
      cost: 0,
      status: 'queued' as const,
    },
  ] as const

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Running Agents</CardTitle>
          <Badge variant="secondary" className="ml-auto text-[10px]">
            2 agents
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {agents.map((agent) => {
          const isRunning = agent.status === 'running'
          const progressPct =
            agent.total > 0
              ? Math.round((agent.processed / agent.total) * 100)
              : 0

          return (
            <div
              key={agent.name}
              className="space-y-3 rounded-lg border border-border bg-muted/30 p-4"
            >
              {/* Header */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{agent.name}</span>
                  <Badge variant="outline" className="text-[10px]">
                    {agent.model}
                  </Badge>
                </div>
                {isRunning ? (
                  <Badge
                    variant="outline"
                    className="gap-1 border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
                  >
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    </span>
                    Running
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="gap-1 border-zinc-500/20 bg-zinc-500/10 text-[10px] text-zinc-500"
                  >
                    <Clock className="h-2.5 w-2.5" />
                    Queued
                  </Badge>
                )}
              </div>

              {/* Dataset and progress */}
              {isRunning ? (
                <>
                  <div className="text-xs text-muted-foreground">
                    Running on{' '}
                    <span className="font-medium text-foreground">
                      {agent.dataset}
                    </span>
                  </div>
                  <Progress value={progressPct} className="h-1.5 bg-muted" />
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="tabular-nums">
                      {agent.processed.toLocaleString()} /{' '}
                      {agent.total.toLocaleString()} records
                    </span>
                    <span className="font-semibold tabular-nums text-foreground">
                      ${agent.cost.toFixed(2)}
                    </span>
                  </div>
                </>
              ) : (
                <div className="text-xs text-muted-foreground">
                  Waiting for{' '}
                  <span className="font-medium text-foreground">
                    {agent.dataset}
                  </span>{' '}
                  step 3 to complete
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1 px-2.5 text-xs"
                  disabled={!isRunning}
                >
                  <Pause className="h-3 w-3" />
                  Pause
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1 px-2.5 text-xs text-red-600 hover:bg-red-500/10 hover:text-red-600"
                >
                  <XCircle className="h-3 w-3" />
                  Cancel
                </Button>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

// ── Recent Events ────────────────────────────────────────────────────────────

function RecentEvents() {
  const events = mockActivity.slice(0, 5)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Recent Events</CardTitle>
          <div className="relative ml-auto flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
          </div>
        </div>
        <CardDescription className="text-xs">Live event feed</CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[240px] pr-2">
          <div className="divide-y divide-border">
            {events.map((item, i) => (
              <div key={item.id} className="flex items-start gap-3 py-3">
                <div className="mt-1.5 flex-shrink-0">
                  <div className="relative flex h-2 w-2 items-center justify-center">
                    {i === 0 && (
                      <span
                        className={`absolute inline-flex h-full w-full animate-ping rounded-full ${activityDotColor[item.type]} opacity-75`}
                      />
                    )}
                    <span
                      className={`relative inline-flex h-2 w-2 rounded-full ${activityDotColor[item.type]}`}
                    />
                  </div>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs leading-snug text-foreground">
                    {item.message}
                  </p>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span>{item.actor}</span>
                    <span className="text-border">|</span>
                    <span>{relativeTime(item.timestamp)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

// ── Active Alerts ────────────────────────────────────────────────────────────

function ActiveAlerts() {
  const alerts = [
    {
      id: 'alert-001',
      severity: 'critical' as const,
      message: 'Construction Zones — only 25% labeled',
      timestamp: '2026-03-26T08:15:00Z',
    },
    {
      id: 'alert-002',
      severity: 'warning' as const,
      message: 'Highway Nighttime — drift detected +2.3%',
      timestamp: '2026-03-26T07:45:00Z',
    },
    {
      id: 'alert-003',
      severity: 'warning' as const,
      message: 'GPT-4o rate limit hit — retrying in 5 minutes',
      timestamp: '2026-03-26T07:30:00Z',
    },
  ] as const

  function alertBorder(severity: 'critical' | 'warning'): string {
    return severity === 'critical'
      ? 'border-red-500/30 bg-red-500/5'
      : 'border-amber-500/30 bg-amber-500/5'
  }

  function alertBadge(severity: 'critical' | 'warning') {
    return severity === 'critical' ? (
      <Badge
        variant="outline"
        className="border-red-500/20 bg-red-500/10 text-[10px] uppercase text-red-600"
      >
        Critical
      </Badge>
    ) : (
      <Badge
        variant="outline"
        className="border-amber-500/20 bg-amber-500/10 text-[10px] uppercase text-amber-600"
      >
        Warning
      </Badge>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Active Alerts</CardTitle>
          <Badge variant="destructive" className="ml-auto h-5 px-1.5 text-[10px]">
            {alerts.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`rounded-lg border border-l-4 px-3 py-3 ${alertBorder(alert.severity)}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                {alert.severity === 'critical' ? (
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-red-500" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                )}
                <div className="space-y-1.5">
                  {alertBadge(alert.severity)}
                  <p className="text-xs font-medium text-foreground">
                    {alert.message}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {relativeTime(alert.timestamp)}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 shrink-0 px-2 text-[10px]"
              >
                Acknowledge
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ── Release Blockers ─────────────────────────────────────────────────────────

function ReleaseBlockers() {
  const blockers = [
    {
      id: 'blocker-001',
      message: 'Urban Scenes Q1: 3 records have unresolved disagreements',
      link: 'adjudication',
    },
    {
      id: 'blocker-002',
      message:
        'Adverse Weather: quality check not passed (agreement 0.78 < 0.85 threshold)',
      link: 'quality',
    },
  ] as const

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Release Blockers</CardTitle>
          <Badge variant="destructive" className="ml-auto h-5 px-1.5 text-[10px]">
            {blockers.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {blockers.map((blocker) => (
          <div
            key={blocker.id}
            className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-3"
          >
            <div className="flex items-start gap-2">
              <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-red-500" />
              <div className="min-w-0 flex-1 space-y-2">
                <p className="text-xs font-medium text-foreground">
                  {blocker.message}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 gap-1 px-2 text-[10px] text-primary"
                >
                  <ExternalLink className="h-2.5 w-2.5" />
                  Go to {blocker.link}
                </Button>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ── System Health ────────────────────────────────────────────────────────────

function SystemHealth() {
  const metrics = [
    {
      label: 'API Latency',
      value: '45ms',
      status: 'green' as const,
      icon: <Zap className="h-3.5 w-3.5" />,
    },
    {
      label: 'Database',
      value: '2.1 GB / 10 GB',
      status: 'green' as const,
      icon: <Server className="h-3.5 w-3.5" />,
    },
    {
      label: 'Active Sessions',
      value: '3',
      status: 'green' as const,
      icon: <Gauge className="h-3.5 w-3.5" />,
    },
    {
      label: 'Uptime',
      value: '14 days',
      status: 'green' as const,
      icon: <Heart className="h-3.5 w-3.5" />,
    },
  ] as const

  function statusDot(status: 'green' | 'yellow' | 'red'): string {
    switch (status) {
      case 'green':
        return 'bg-emerald-500'
      case 'yellow':
        return 'bg-amber-500'
      case 'red':
        return 'bg-red-500'
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Heart className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">System Health</CardTitle>
          <Badge
            variant="outline"
            className="ml-auto gap-1 border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
          >
            <CheckCircle className="h-2.5 w-2.5" />
            All Clear
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {metrics.map((metric, i) => (
          <div key={metric.label}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 text-muted-foreground">
                {metric.icon}
                <span className="text-xs">{metric.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tabular-nums">
                  {metric.value}
                </span>
                <span
                  className={`h-2 w-2 rounded-full ${statusDot(metric.status)}`}
                />
              </div>
            </div>
            {i < metrics.length - 1 && <Separator className="mt-3" />}
          </div>
        ))}

        {/* DB progress bar */}
        <div className="space-y-1 pt-1">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Storage usage</span>
            <span className="tabular-nums">21%</span>
          </div>
          <Progress value={21} className="h-1.5 bg-muted" />
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function MissionControlPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Mission Control
            </h1>
            <p className="text-sm text-muted-foreground">
              Live operations view
            </p>
          </div>
        </div>
      </div>

      {/* Status Bar */}
      <StatusBar />

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Left Column (60%) */}
        <div className="flex flex-col gap-6 lg:col-span-3">
          <ActiveWorkflows />
          <RunningAgents />
          <RecentEvents />
        </div>

        {/* Right Column (40%) */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          <ActiveAlerts />
          <ReleaseBlockers />
          <SystemHealth />
        </div>
      </div>
    </div>
  )
}
