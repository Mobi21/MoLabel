import {
  Bot,
  Play,
  Plus,
  Settings2,
  FlaskConical,
  Sparkles,
  Brain,
  Globe,
  TrendingUp,
  BarChart3,
  GitCompare,
  CircleDot,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  DollarSign,
  Gauge,
  Timer,
  Target,
  Zap,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { mockAgentRuns } from '@/mocks/data'
import type { AgentRun } from '@/mocks/data'

// ── Types ────────────────────────────────────────────────────────────────────

interface ModelProfile {
  id: string
  name: string
  provider: string
  model: string
  icon: typeof Sparkles
  iconColor: string
  costInput: number
  costOutput: number
  accuracy: number
  latency: number
  status: 'connected' | 'disconnected'
}

interface ComparisonMetric {
  label: string
  values: [number, number, number]
  format: 'percent' | 'currency' | 'seconds'
  bestIs: 'highest' | 'lowest'
}

interface ConfusionPair {
  predicted: string
  actual: string
  count: number
  percent: number
}

interface AccuracyTrendPoint {
  label: string
  gpt4o: number
  claude: number
  gemini: number
}

// ── Mock Data ────────────────────────────────────────────────────────────────

const modelProfiles: ModelProfile[] = [
  {
    id: 'mp-001',
    name: 'OpenAI GPT-4o',
    provider: 'OpenAI',
    model: 'gpt-4o',
    icon: Sparkles,
    iconColor: 'text-emerald-500',
    costInput: 2.5,
    costOutput: 10.0,
    accuracy: 0.924,
    latency: 1.2,
    status: 'connected',
  },
  {
    id: 'mp-002',
    name: 'Anthropic Claude Sonnet',
    provider: 'Anthropic',
    model: 'claude-sonnet-4-20250514',
    icon: Brain,
    iconColor: 'text-orange-500',
    costInput: 3.0,
    costOutput: 15.0,
    accuracy: 0.951,
    latency: 1.8,
    status: 'connected',
  },
  {
    id: 'mp-003',
    name: 'Google Gemini 2.5 Pro',
    provider: 'Google',
    model: 'gemini-2.5-pro',
    icon: Globe,
    iconColor: 'text-blue-500',
    costInput: 1.25,
    costOutput: 5.0,
    accuracy: 0.887,
    latency: 2.1,
    status: 'connected',
  },
]

const comparisonMetrics: ComparisonMetric[] = [
  {
    label: 'Accuracy',
    values: [92.4, 95.1, 88.7],
    format: 'percent',
    bestIs: 'highest',
  },
  {
    label: 'Cost',
    values: [0.78, 1.24, 0.42],
    format: 'currency',
    bestIs: 'lowest',
  },
  {
    label: 'Agreement',
    values: [87, 91, 82],
    format: 'percent',
    bestIs: 'highest',
  },
  {
    label: 'Speed',
    values: [47, 68, 52],
    format: 'seconds',
    bestIs: 'lowest',
  },
]

const confusionPairs: ConfusionPair[] = [
  { predicted: 'SUV', actual: 'Truck', count: 34, percent: 14.2 },
  { predicted: 'Van', actual: 'Bus', count: 28, percent: 11.7 },
  { predicted: 'Motorcycle', actual: 'Bicycle', count: 22, percent: 9.2 },
  { predicted: 'Sedan', actual: 'SUV', count: 18, percent: 7.5 },
  { predicted: 'Pickup', actual: 'SUV', count: 15, percent: 6.3 },
]

const accuracyTrend: AccuracyTrendPoint[] = [
  { label: 'Week 1', gpt4o: 85.2, claude: 87.3, gemini: 80.1 },
  { label: 'Week 2', gpt4o: 87.8, claude: 89.5, gemini: 82.9 },
  { label: 'Week 3', gpt4o: 89.1, claude: 91.2, gemini: 85.3 },
  { label: 'Week 4', gpt4o: 90.6, claude: 93.0, gemini: 86.8 },
  { label: 'Week 5', gpt4o: 91.4, claude: 94.2, gemini: 87.9 },
  { label: 'Week 6', gpt4o: 92.4, claude: 95.1, gemini: 88.7 },
]

const sampleRecordOutputs = [
  {
    model: 'GPT-4o',
    label: 'SUV',
    confidence: 0.89,
    bbox: '[142, 85, 310, 220]',
    attributes: 'color: white, orientation: rear-left',
  },
  {
    model: 'Claude Sonnet',
    label: 'SUV',
    confidence: 0.94,
    bbox: '[140, 83, 312, 222]',
    attributes: 'color: silver, orientation: rear-left',
  },
  {
    model: 'Gemini Pro',
    label: 'Truck',
    confidence: 0.72,
    bbox: '[145, 88, 308, 218]',
    attributes: 'color: white, orientation: rear',
  },
]

// ── Helpers ──────────────────────────────────────────────────────────────────

function getStatusConfig(status: AgentRun['status']) {
  switch (status) {
    case 'completed':
      return {
        dot: 'bg-emerald-500',
        badge: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
        icon: CheckCircle2,
        rowBg: '',
      }
    case 'running':
      return {
        dot: 'bg-blue-500 animate-pulse',
        badge: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
        icon: Loader2,
        rowBg: 'bg-blue-500/[0.03]',
      }
    case 'failed':
      return {
        dot: 'bg-red-500',
        badge: 'bg-red-500/10 text-red-500 border-red-500/20',
        icon: XCircle,
        rowBg: '',
      }
    case 'queued':
      return {
        dot: 'bg-zinc-400',
        badge: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
        icon: Clock,
        rowBg: '',
      }
  }
}

function formatAccuracy(value: number): string {
  if (value === 0) return '--'
  return `${(value * 100).toFixed(1)}%`
}

function getAccuracyColor(value: number): string {
  if (value === 0) return 'text-muted-foreground'
  if (value >= 0.95) return 'text-emerald-500'
  if (value >= 0.9) return 'text-emerald-400'
  if (value >= 0.85) return 'text-amber-500'
  return 'text-red-500'
}

function formatCost(value: number): string {
  if (value === 0) return '--'
  return `$${value.toFixed(2)}`
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function computeSummary() {
  let completed = 0
  let running = 0
  let failed = 0
  let queued = 0
  let totalCost = 0

  for (const run of mockAgentRuns) {
    totalCost += run.cost
    switch (run.status) {
      case 'completed':
        completed++
        break
      case 'running':
        running++
        break
      case 'failed':
        failed++
        break
      case 'queued':
        queued++
        break
    }
  }

  const parts: string[] = []
  if (completed > 0) parts.push(`${String(completed)} completed`)
  if (running > 0) parts.push(`${String(running)} running`)
  if (failed > 0) parts.push(`${String(failed)} failed`)
  if (queued > 0) parts.push(`${String(queued)} queued`)

  return { text: parts.join(', '), totalCost }
}

// ── Tab 1: Agent Runs ────────────────────────────────────────────────────────

function AgentRunsTab() {
  const summary = computeSummary()

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">Agent Runs</h3>
          <p className="text-sm text-muted-foreground">
            Monitor active and historical agent execution runs.
          </p>
        </div>
        <Button size="sm">
          <Play className="h-4 w-4" />
          Run New Agent
        </Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[130px]">Status</TableHead>
              <TableHead className="w-[180px]">Agent Name</TableHead>
              <TableHead className="w-[90px]">Provider</TableHead>
              <TableHead className="w-[180px]">Model</TableHead>
              <TableHead className="w-[100px] text-right">Records</TableHead>
              <TableHead className="w-[90px] text-right">Accuracy</TableHead>
              <TableHead className="w-[80px] text-right">Cost</TableHead>
              <TableHead className="w-[100px] text-right">Duration</TableHead>
              <TableHead className="w-[130px]">Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockAgentRuns.map((run) => {
              const config = getStatusConfig(run.status)
              const StatusIcon = config.icon

              return (
                <TableRow
                  key={run.id}
                  className={`hover:bg-muted/50 ${config.rowBg}`}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full ${config.dot}`} />
                      <Badge
                        variant="outline"
                        className={`text-[11px] font-medium ${config.badge}`}
                      >
                        <StatusIcon
                          className={`mr-1 h-3 w-3 ${run.status === 'running' ? 'animate-spin' : ''}`}
                        />
                        {run.status}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell className="font-medium">{run.agentName}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {run.provider}
                  </TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {run.model}
                    </code>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {run.recordsProcessed > 0
                      ? run.recordsProcessed.toLocaleString()
                      : '--'}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono text-sm font-medium ${getAccuracyColor(run.accuracy)}`}
                  >
                    {formatAccuracy(run.accuracy)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatCost(run.cost)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm text-muted-foreground">
                    {run.duration}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTimestamp(run.startedAt)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>

      {/* Summary bar */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-muted px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <CircleDot className="h-3.5 w-3.5" />
          <span>{summary.text}</span>
        </div>
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
          Total cost: ${summary.totalCost.toFixed(2)}
        </div>
      </div>
    </div>
  )
}

// ── Tab 2: Model Profiles ────────────────────────────────────────────────────

function ModelProfilesTab() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">Model Profiles</h3>
          <p className="text-sm text-muted-foreground">
            Configured AI models available for agent runs.
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-4 w-4" />
          Add Model Profile
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {modelProfiles.map((profile) => {
          const Icon = profile.icon

          return (
            <Card key={profile.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                      <Icon className={`h-5 w-5 ${profile.iconColor}`} />
                    </div>
                    <div>
                      <CardTitle className="text-base">
                        {profile.name}
                      </CardTitle>
                      <CardDescription className="mt-0.5">
                        {profile.provider}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="h-2 w-2 rounded-full bg-emerald-500" />
                    <span className="text-xs text-emerald-500">Connected</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 space-y-4">
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Model
                  </p>
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {profile.model}
                  </code>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">Input</p>
                    <p className="text-sm font-semibold">
                      ${profile.costInput.toFixed(2)}
                      <span className="text-[10px] font-normal text-muted-foreground">
                        /1M
                      </span>
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">Output</p>
                    <p className="text-sm font-semibold">
                      ${profile.costOutput.toFixed(2)}
                      <span className="text-[10px] font-normal text-muted-foreground">
                        /1M
                      </span>
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">
                      Avg Accuracy
                    </p>
                    <p
                      className={`text-sm font-semibold ${getAccuracyColor(profile.accuracy)}`}
                    >
                      {(profile.accuracy * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                    <p className="text-[11px] text-muted-foreground">
                      Avg Latency
                    </p>
                    <p className="text-sm font-semibold">
                      {profile.latency.toFixed(1)}s
                    </p>
                  </div>
                </div>
              </CardContent>
              <CardFooter className="gap-2 border-t border-border pt-4">
                <Button variant="outline" size="sm" className="flex-1">
                  <Settings2 className="h-3.5 w-3.5" />
                  Configure
                </Button>
                <Button variant="outline" size="sm" className="flex-1">
                  <FlaskConical className="h-3.5 w-3.5" />
                  Test
                </Button>
              </CardFooter>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

// ── Tab 3: Comparison ────────────────────────────────────────────────────────

function ComparisonTab() {
  const modelNames = ['GPT-4o', 'Claude Sonnet', 'Gemini Pro'] as const
  const modelColors = [
    'text-emerald-500',
    'text-orange-500',
    'text-blue-500',
  ] as const

  function formatMetricValue(
    value: number,
    format: ComparisonMetric['format'],
  ): string {
    switch (format) {
      case 'percent':
        return `${String(value)}%`
      case 'currency':
        return `$${value.toFixed(2)}`
      case 'seconds':
        return `${String(value)}s`
    }
  }

  function getBestIndex(
    values: [number, number, number],
    bestIs: 'highest' | 'lowest',
  ): number {
    if (bestIs === 'highest') {
      return values.indexOf(Math.max(...values))
    }
    return values.indexOf(Math.min(...values))
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">Model Comparison</h3>
        <p className="text-sm text-muted-foreground">
          Side-by-side performance comparison across models.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center gap-2">
            <GitCompare className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">
              Vehicle Detection &mdash; Urban Scenes Sample (100 records)
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-0">
          {/* Column headers */}
          <div className="grid grid-cols-4 gap-4 border-b border-border pb-3">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Metric
            </div>
            {modelNames.map((name, i) => {
              const color = modelColors[i]
              return (
                <div
                  key={name}
                  className={`text-center text-sm font-semibold ${color ?? ''}`}
                >
                  {name}
                </div>
              )
            })}
          </div>

          {/* Metric rows */}
          {comparisonMetrics.map((metric) => {
            const bestIdx = getBestIndex(metric.values, metric.bestIs)

            return (
              <div
                key={metric.label}
                className="grid grid-cols-4 gap-4 border-b border-border/50 py-3 last:border-0"
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  {metric.label === 'Accuracy' && (
                    <Target className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {metric.label === 'Cost' && (
                    <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {metric.label === 'Agreement' && (
                    <Gauge className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {metric.label === 'Speed' && (
                    <Timer className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  {metric.label}
                </div>
                {metric.values.map((value, i) => {
                  const isBest = i === bestIdx

                  return (
                    <div
                      key={`${metric.label}-${String(i)}`}
                      className={`text-center font-mono text-sm ${
                        isBest
                          ? 'font-bold text-emerald-500'
                          : 'text-foreground'
                      }`}
                    >
                      {formatMetricValue(value, metric.format)}
                      {isBest && (
                        <span className="ml-1 text-[10px] font-medium text-emerald-500">
                          best
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </CardContent>
      </Card>

      {/* Sample record comparison */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">
            Sample Record: rec-4821 &mdash; Vehicle Detection
          </CardTitle>
          <CardDescription>
            Model outputs with disagreement highlighting
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {sampleRecordOutputs.map((output, i) => {
              const isDisagreement = output.label !== 'SUV'
              const colorClass = modelColors[i]

              return (
                <div
                  key={output.model}
                  className={`rounded-lg border p-4 ${
                    isDisagreement
                      ? 'border-red-500/30 bg-red-500/[0.03]'
                      : 'border-border'
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between">
                    <span
                      className={`text-sm font-semibold ${colorClass ?? ''}`}
                    >
                      {output.model}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">
                      conf: {output.confidence.toFixed(2)}
                    </span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        Label
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                          isDisagreement
                            ? 'bg-red-500/10 text-red-500'
                            : 'bg-emerald-500/10 text-emerald-500'
                        }`}
                      >
                        {output.label}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        BBox
                      </span>
                      <code className="text-[11px] text-muted-foreground">
                        {output.bbox}
                      </code>
                    </div>
                    <div className="flex items-start justify-between gap-2">
                      <span className="shrink-0 text-xs text-muted-foreground">
                        Attrs
                      </span>
                      <span
                        className={`text-right text-[11px] ${
                          output.attributes.includes('silver')
                            ? 'text-amber-500'
                            : output.attributes.includes('rear\n')
                              ? 'text-amber-500'
                              : 'text-muted-foreground'
                        }`}
                      >
                        {output.attributes.split(', ').map((attr, attrIdx) => {
                          const otherAttrs = sampleRecordOutputs
                            .filter((_, oi) => oi !== i)
                            .map((o) => o.attributes)
                          const isDiff = !otherAttrs.every((oa) =>
                            oa.includes(attr),
                          )

                          return (
                            <span key={`${output.model}-${String(attrIdx)}`}>
                              {attrIdx > 0 && ', '}
                              <span
                                className={
                                  isDiff
                                    ? 'rounded bg-amber-500/10 px-0.5 text-amber-500'
                                    : ''
                                }
                              >
                                {attr}
                              </span>
                            </span>
                          )
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Tab 4: Performance ───────────────────────────────────────────────────────

function AccuracyBarChart() {
  const models = [
    { name: 'Claude Sonnet', value: 95.1, color: 'bg-orange-500' },
    { name: 'GPT-4o', value: 92.4, color: 'bg-emerald-500' },
    { name: 'Gemini Pro', value: 88.7, color: 'bg-blue-500' },
  ]

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Accuracy by Model</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {models.map((m) => (
          <div key={m.name} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">{m.name}</span>
              <span className="font-mono font-semibold">{m.value}%</span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-all ${m.color}`}
                style={{ width: `${String(m.value)}%` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function CostPerLabelChart() {
  const models = [
    { name: 'Gemini Pro', value: 0.0047, color: 'bg-blue-500', barPct: 37 },
    { name: 'GPT-4o', value: 0.0078, color: 'bg-emerald-500', barPct: 62 },
    {
      name: 'Claude Sonnet',
      value: 0.0126,
      color: 'bg-orange-500',
      barPct: 100,
    },
  ]

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <DollarSign className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Cost per Correct Label</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {models.map((m) => (
          <div key={m.name} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">{m.name}</span>
              <span className="font-mono font-semibold">
                ${m.value.toFixed(4)}
              </span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-all ${m.color}`}
                style={{ width: `${String(m.barPct)}%` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function AccuracyTrendChart() {
  const minY = 78
  const maxY = 98
  const range = maxY - minY
  const chartW = 500
  const chartH = 180
  const padX = 40
  const padY = 20
  const plotW = chartW - padX * 2
  const plotH = chartH - padY * 2

  function toX(i: number): number {
    return padX + (i / (accuracyTrend.length - 1)) * plotW
  }

  function toY(v: number): number {
    return padY + plotH - ((v - minY) / range) * plotH
  }

  function makePath(key: 'gpt4o' | 'claude' | 'gemini'): string {
    return accuracyTrend
      .map(
        (pt, i) =>
          `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(pt[key]).toFixed(1)}`,
      )
      .join(' ')
  }

  const lines = [
    { key: 'claude' as const, color: '#f97316', label: 'Claude' },
    { key: 'gpt4o' as const, color: '#10b981', label: 'GPT-4o' },
    { key: 'gemini' as const, color: '#3b82f6', label: 'Gemini' },
  ]

  const yTicks = [80, 85, 90, 95]

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Accuracy Trend</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <svg
          viewBox={`0 0 ${String(chartW)} ${String(chartH)}`}
          className="w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Grid lines */}
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={padX}
                y1={toY(tick)}
                x2={chartW - padX}
                y2={toY(tick)}
                stroke="currentColor"
                strokeOpacity={0.08}
                strokeDasharray="4 4"
              />
              <text
                x={padX - 6}
                y={toY(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                fill="currentColor"
                fillOpacity={0.4}
                fontSize={10}
              >
                {tick}%
              </text>
            </g>
          ))}

          {/* X labels */}
          {accuracyTrend.map((pt, i) => (
            <text
              key={pt.label}
              x={toX(i)}
              y={chartH - 2}
              textAnchor="middle"
              fill="currentColor"
              fillOpacity={0.4}
              fontSize={9}
            >
              {pt.label.replace('Week ', 'W')}
            </text>
          ))}

          {/* Lines */}
          {lines.map((line) => (
            <path
              key={line.key}
              d={makePath(line.key)}
              fill="none"
              stroke={line.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}

          {/* Dots on last point */}
          {lines.map((line) => {
            const lastPt = accuracyTrend[accuracyTrend.length - 1]
            if (!lastPt) return null
            return (
              <circle
                key={`dot-${line.key}`}
                cx={toX(accuracyTrend.length - 1)}
                cy={toY(lastPt[line.key])}
                r={3.5}
                fill={line.color}
              />
            )
          })}
        </svg>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-center gap-5">
          {lines.map((line) => (
            <div key={line.key} className="flex items-center gap-1.5">
              <div
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: line.color }}
              />
              <span className="text-xs text-muted-foreground">
                {line.label}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ErrorAnalysisTable() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Error Analysis</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Top confusion pairs across all models
        </CardDescription>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Predicted</TableHead>
              <TableHead>Actual</TableHead>
              <TableHead className="text-right">Count</TableHead>
              <TableHead className="pr-6 text-right">% of Errors</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {confusionPairs.map((pair) => (
              <TableRow key={`${pair.predicted}-${pair.actual}`}>
                <TableCell className="pl-6">
                  <code className="rounded bg-red-500/10 px-1.5 py-0.5 text-xs text-red-500">
                    {pair.predicted}
                  </code>
                </TableCell>
                <TableCell>
                  <code className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-xs text-emerald-500">
                    {pair.actual}
                  </code>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {pair.count}
                </TableCell>
                <TableCell className="pr-6 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-red-500/60"
                        style={{
                          width: `${String((pair.percent / 15) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="w-10 text-right font-mono text-xs text-muted-foreground">
                      {pair.percent}%
                    </span>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function PerformanceTab() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">Performance Dashboard</h3>
        <p className="text-sm text-muted-foreground">
          Aggregate metrics and trends across all model runs.
        </p>
      </div>

      {/* Summary metric cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: 'Best Accuracy',
            value: '95.1%',
            sub: 'Claude Sonnet',
            icon: Target,
            color: 'text-emerald-500',
          },
          {
            label: 'Lowest Cost/Label',
            value: '$0.0047',
            sub: 'Gemini Pro',
            icon: DollarSign,
            color: 'text-blue-500',
          },
          {
            label: 'Fastest Model',
            value: '1.2s avg',
            sub: 'GPT-4o',
            icon: Zap,
            color: 'text-amber-500',
          },
          {
            label: 'Total Records',
            value: '4,430',
            sub: 'across 5 runs',
            icon: BarChart3,
            color: 'text-violet-500',
          },
        ].map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label}>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">
                      {stat.label}
                    </p>
                    <p className="mt-1 text-2xl font-bold tracking-tight">
                      {stat.value}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {stat.sub}
                    </p>
                  </div>
                  <div className={`rounded-md bg-muted p-2 ${stat.color}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <AccuracyBarChart />
        <CostPerLabelChart />
        <AccuracyTrendChart />
        <ErrorAnalysisTable />
      </div>
    </div>
  )
}

// ── Main Agents Page ─────────────────────────────────────────────────────────

export function AgentsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
            <p className="text-sm text-muted-foreground">
              Configure AI agents, monitor runs, and compare model performance.
            </p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="runs" className="space-y-6">
        <TabsList>
          <TabsTrigger
            value="runs"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Agent Runs
          </TabsTrigger>
          <TabsTrigger
            value="models"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Model Profiles
          </TabsTrigger>
          <TabsTrigger
            value="comparison"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Comparison
          </TabsTrigger>
          <TabsTrigger
            value="performance"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Performance
          </TabsTrigger>
        </TabsList>

        <TabsContent value="runs">
          <AgentRunsTab />
        </TabsContent>

        <TabsContent value="models">
          <ModelProfilesTab />
        </TabsContent>

        <TabsContent value="comparison">
          <ComparisonTab />
        </TabsContent>

        <TabsContent value="performance">
          <PerformanceTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
