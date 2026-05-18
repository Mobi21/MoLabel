import { useState } from 'react'
import {
  Scale,
  Bot,
  User,
  CheckCircle2,
  ArrowRightLeft,
  RotateCcw,
  AlertTriangle,
  ChevronRight,
  Clock,
  FileText,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

// ── Types ────────────────────────────────────────────────────────────────────

type Priority = 'high' | 'medium' | 'low'

interface DisagreementItem {
  id: string
  recordId: string
  field: string
  agentValue: string
  humanValue: string
  priority: Priority
  dataset: string
  agentConfidence: number
  humanConfidence: number
  resolved: boolean
  context: Record<string, string>
  previousResolutions: Array<{
    id: string
    decision: string
    rationale: string
    resolver: string
    timestamp: string
  }>
}

type ResolutionOption =
  | 'adopt-agent'
  | 'adopt-human'
  | 'merge'
  | 're-review'
  | 'escalate'

// ── Mock Data ────────────────────────────────────────────────────────────────

const disagreements: DisagreementItem[] = [
  {
    id: 'dis-001',
    recordId: 'rec-4821',
    field: 'Vehicle count',
    agentValue: '3',
    humanValue: '4',
    priority: 'high',
    dataset: 'Urban Intersection v2',
    agentConfidence: 0.72,
    humanConfidence: 0.95,
    resolved: false,
    context: {
      'Scene type': 'Urban 4-way intersection',
      'Time of day': 'Dusk (18:42)',
      Weather: 'Overcast, light rain',
    },
    previousResolutions: [
      {
        id: 'res-a1',
        decision: 'Adopted human label',
        rationale:
          'Agent miscounted a partially occluded vehicle behind the bus. Human annotator confirmed 4 vehicles via frame-by-frame review.',
        resolver: 'Maria Chen',
        timestamp: '2026-03-24T14:20:00Z',
      },
      {
        id: 'res-a2',
        decision: 'Sent back for re-review',
        rationale:
          'Initial labels were from the first pass. Needed senior annotator verification due to heavy occlusion.',
        resolver: 'James Okafor',
        timestamp: '2026-03-23T09:10:00Z',
      },
    ],
  },
  {
    id: 'dis-002',
    recordId: 'rec-9103',
    field: 'Sign type',
    agentValue: 'speed_limit',
    humanValue: 'speed_advisory',
    priority: 'high',
    dataset: 'Highway Signs v1',
    agentConfidence: 0.68,
    humanConfidence: 0.91,
    resolved: false,
    context: {
      'Scene type': 'Highway on-ramp',
      'Sign shape': 'Diamond (yellow)',
      'Posted value': '35 mph',
    },
    previousResolutions: [],
  },
  {
    id: 'dis-003',
    recordId: 'rec-7290',
    field: 'Occlusion',
    agentValue: 'false',
    humanValue: 'true',
    priority: 'medium',
    dataset: 'Urban Intersection v2',
    agentConfidence: 0.81,
    humanConfidence: 0.88,
    resolved: false,
    context: {
      'Scene type': 'Residential street',
      'Object class': 'Pedestrian',
      Visibility: 'Partial (behind parked car)',
    },
    previousResolutions: [
      {
        id: 'res-c1',
        decision: 'Adopted human label',
        rationale:
          'Pedestrian lower body is behind parked car. Meets occlusion threshold (>30% hidden).',
        resolver: 'Sarah Kim',
        timestamp: '2026-03-25T11:05:00Z',
      },
    ],
  },
  {
    id: 'dis-004',
    recordId: 'rec-1547',
    field: 'Vehicle type',
    agentValue: 'truck',
    humanValue: 'bus',
    priority: 'medium',
    dataset: 'Urban Intersection v2',
    agentConfidence: 0.55,
    humanConfidence: 0.93,
    resolved: false,
    context: {
      'Scene type': 'Downtown bus lane',
      'Vehicle color': 'White with blue stripe',
      'Vehicle length': '~12m',
    },
    previousResolutions: [],
  },
  {
    id: 'dis-005',
    recordId: 'rec-5533',
    field: 'Pedestrian count',
    agentValue: '2',
    humanValue: '2',
    priority: 'low',
    dataset: 'Crosswalk Safety v1',
    agentConfidence: 0.97,
    humanConfidence: 0.99,
    resolved: true,
    context: {
      'Scene type': 'Marked crosswalk',
      'Signal state': 'Walk',
      'Time of day': 'Noon',
    },
    previousResolutions: [
      {
        id: 'res-e1',
        decision: 'Auto-resolved (agreement)',
        rationale: 'Both labels match. Automatically resolved by system.',
        resolver: 'System',
        timestamp: '2026-03-26T06:00:00Z',
      },
    ],
  },
  {
    id: 'dis-006',
    recordId: 'rec-8812',
    field: 'Traffic signs',
    agentValue: '[stop]',
    humanValue: '[stop, yield]',
    priority: 'medium',
    dataset: 'Highway Signs v1',
    agentConfidence: 0.76,
    humanConfidence: 0.89,
    resolved: false,
    context: {
      'Scene type': 'T-intersection',
      'Sign count': '3 visible',
      Visibility: 'Clear, daytime',
    },
    previousResolutions: [],
  },
]

const reviewers = [
  'Maria Chen',
  'James Okafor',
  'Sarah Kim',
  'David Park',
  'Ana Reyes',
]

// ── Helpers ──────────────────────────────────────────────────────────────────

const priorityConfig: Record<
  Priority,
  { label: string; borderClass: string; badgeClass: string }
> = {
  high: {
    label: 'High',
    borderClass: 'border-l-red-500',
    badgeClass: 'border-red-500/20 bg-red-500/10 text-red-600',
  },
  medium: {
    label: 'Medium',
    borderClass: 'border-l-amber-500',
    badgeClass: 'border-amber-500/20 bg-amber-500/10 text-amber-600',
  },
  low: {
    label: 'Low',
    borderClass: 'border-l-emerald-500',
    badgeClass: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600',
  },
}

function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

// ── Disagreement Card ────────────────────────────────────────────────────────

function DisagreementCard({
  item,
  isSelected,
  onSelect,
}: {
  item: DisagreementItem
  isSelected: boolean
  onSelect: () => void
}) {
  const config = priorityConfig[item.priority]

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left rounded-lg border border-l-4 bg-card px-3 py-3 transition-colors ${config.borderClass} ${
        isSelected
          ? 'border-primary bg-accent/50'
          : 'border-border hover:bg-accent/30'
      } ${item.resolved ? 'opacity-60' : ''}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-medium text-muted-foreground">
              {item.recordId}
            </span>
            <Badge
              variant="outline"
              className={`text-[10px] ${config.badgeClass}`}
            >
              {config.label}
            </Badge>
            {item.resolved && (
              <Badge
                variant="outline"
                className="gap-1 border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
              >
                <CheckCircle2 className="h-3 w-3" />
                Resolved
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm font-medium text-foreground">
            {item.field}
          </p>
          <div className="mt-1.5 flex items-center gap-1.5 text-xs">
            <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-1.5 py-0.5 font-mono text-blue-600">
              <Bot className="h-3 w-3" />
              {item.agentValue}
            </span>
            <ArrowRightLeft className="h-3 w-3 text-muted-foreground" />
            <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-emerald-600">
              <User className="h-3 w-3" />
              {item.humanValue}
            </span>
          </div>
        </div>
        <ChevronRight className="mt-1 h-4 w-4 flex-shrink-0 text-muted-foreground" />
      </div>
      <p className="mt-1.5 text-[11px] text-muted-foreground">{item.dataset}</p>
    </button>
  )
}

// ── Resolution Editor ────────────────────────────────────────────────────────

function ResolutionEditor({ item }: { item: DisagreementItem }) {
  const [resolutionType, setResolutionType] =
    useState<ResolutionOption>('adopt-human')
  const [rationale, setRationale] = useState('')
  const [mergedValue, setMergedValue] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [escalationNotes, setEscalationNotes] = useState('')

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1">
        <div className="space-y-6 p-6">
          {/* ── Record Header ─────────────────────────────────────────────── */}
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">
                {item.recordId}
              </h2>
              <Badge variant="outline" className="font-mono text-xs">
                {item.field}
              </Badge>
              <Badge
                variant="outline"
                className={priorityConfig[item.priority].badgeClass}
              >
                {priorityConfig[item.priority].label} Priority
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{item.dataset}</p>
          </div>

          {/* ── Context Section ────────────────────────────────────────────── */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-muted-foreground" />
                Record Context
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(item.context).map(([key, value]) => (
                  <div key={key} className="rounded-md bg-muted/50 px-3 py-2">
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      {key}
                    </p>
                    <p className="mt-0.5 text-sm font-medium">{value}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* ── Conflict Detail — Side by Side ─────────────────────────────── */}
          <div className="grid grid-cols-2 gap-4">
            {/* Agent Side */}
            <Card className="border-blue-500/20 bg-blue-500/[0.02]">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-500/10">
                    <Bot className="h-3.5 w-3.5 text-blue-600" />
                  </div>
                  Agent Output
                </CardTitle>
                <CardDescription>
                  Confidence: {formatConfidence(item.agentConfidence)}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border border-blue-500/20 bg-blue-500/5 px-4 py-3">
                  <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    {item.field}
                  </p>
                  <p
                    className={`mt-1 font-mono text-lg font-semibold ${
                      item.agentValue !== item.humanValue
                        ? 'text-red-500 line-through decoration-red-500/40'
                        : 'text-foreground'
                    }`}
                  >
                    {item.agentValue}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Human Side */}
            <Card className="border-emerald-500/20 bg-emerald-500/[0.02]">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/10">
                    <User className="h-3.5 w-3.5 text-emerald-600" />
                  </div>
                  Human Output
                </CardTitle>
                <CardDescription>
                  Confidence: {formatConfidence(item.humanConfidence)}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
                  <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    {item.field}
                  </p>
                  <p
                    className={`mt-1 font-mono text-lg font-semibold ${
                      item.agentValue !== item.humanValue
                        ? 'text-emerald-600'
                        : 'text-foreground'
                    }`}
                  >
                    {item.humanValue}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Separator />

          {/* ── Resolution Options ─────────────────────────────────────────── */}
          <div>
            <h3 className="mb-4 text-sm font-semibold">Resolution</h3>
            <RadioGroup
              value={resolutionType}
              onValueChange={(v) => {
                setResolutionType(v as ResolutionOption)
              }}
              className="space-y-3"
            >
              {/* Adopt Agent */}
              <div
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  resolutionType === 'adopt-agent'
                    ? 'border-blue-500/40 bg-muted/30 p-4'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <RadioGroupItem value="adopt-agent" id="adopt-agent" />
                  <Label
                    htmlFor="adopt-agent"
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <Bot className="h-4 w-4 text-blue-600" />
                    Adopt agent label
                  </Label>
                </div>
                {resolutionType === 'adopt-agent' && (
                  <div className="mt-3 pl-7">
                    <Textarea
                      placeholder="Rationale for adopting the agent label..."
                      value={rationale}
                      onChange={(e) => {
                        setRationale(e.target.value)
                      }}
                      className="min-h-[80px] resize-none"
                    />
                  </div>
                )}
              </div>

              {/* Adopt Human */}
              <div
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  resolutionType === 'adopt-human'
                    ? 'border-emerald-500/40 bg-muted/30 p-4'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <RadioGroupItem value="adopt-human" id="adopt-human" />
                  <Label
                    htmlFor="adopt-human"
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <User className="h-4 w-4 text-emerald-600" />
                    Adopt human label
                  </Label>
                </div>
                {resolutionType === 'adopt-human' && (
                  <div className="mt-3 pl-7">
                    <Textarea
                      placeholder="Rationale for adopting the human label..."
                      value={rationale}
                      onChange={(e) => {
                        setRationale(e.target.value)
                      }}
                      className="min-h-[80px] resize-none"
                    />
                  </div>
                )}
              </div>

              {/* Merge / Synthesize */}
              <div
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  resolutionType === 'merge'
                    ? 'border-purple-500/40 bg-muted/30 p-4'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <RadioGroupItem value="merge" id="merge" />
                  <Label
                    htmlFor="merge"
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <ArrowRightLeft className="h-4 w-4 text-purple-600" />
                    Merge / synthesize
                  </Label>
                </div>
                {resolutionType === 'merge' && (
                  <div className="mt-3 space-y-3 pl-7">
                    <div>
                      <Label className="text-xs text-muted-foreground">
                        Merged value
                      </Label>
                      <Input
                        placeholder="Enter the merged/synthesized value..."
                        value={mergedValue}
                        onChange={(e) => {
                          setMergedValue(e.target.value)
                        }}
                        className="mt-1 font-mono"
                      />
                    </div>
                    <Textarea
                      placeholder="Rationale for the merged value..."
                      value={rationale}
                      onChange={(e) => {
                        setRationale(e.target.value)
                      }}
                      className="min-h-[80px] resize-none"
                    />
                  </div>
                )}
              </div>

              {/* Send back for re-review */}
              <div
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  resolutionType === 're-review'
                    ? 'border-amber-500/40 bg-muted/30 p-4'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <RadioGroupItem value="re-review" id="re-review" />
                  <Label
                    htmlFor="re-review"
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <RotateCcw className="h-4 w-4 text-amber-600" />
                    Send back for re-review
                  </Label>
                </div>
                {resolutionType === 're-review' && (
                  <div className="mt-3 pl-7">
                    <Label className="text-xs text-muted-foreground">
                      Assign reviewer
                    </Label>
                    <Select value={reviewer} onValueChange={setReviewer}>
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder="Select a reviewer..." />
                      </SelectTrigger>
                      <SelectContent>
                        {reviewers.map((name) => (
                          <SelectItem key={name} value={name}>
                            {name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              {/* Escalate */}
              <div
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  resolutionType === 'escalate'
                    ? 'border-red-500/40 bg-muted/30 p-4'
                    : 'border-border'
                }`}
              >
                <div className="flex items-center gap-3">
                  <RadioGroupItem value="escalate" id="escalate" />
                  <Label
                    htmlFor="escalate"
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    Escalate
                  </Label>
                </div>
                {resolutionType === 'escalate' && (
                  <div className="mt-3 pl-7">
                    <Textarea
                      placeholder="Escalation notes — describe the issue and why it needs elevated review..."
                      value={escalationNotes}
                      onChange={(e) => {
                        setEscalationNotes(e.target.value)
                      }}
                      className="min-h-[80px] resize-none"
                    />
                  </div>
                )}
              </div>
            </RadioGroup>
          </div>

          {/* ── Resolve Button ─────────────────────────────────────────────── */}
          <Button size="lg" className="w-full">
            <CheckCircle2 className="h-4 w-4" />
            Resolve Disagreement
          </Button>

          <Separator />

          {/* ── Previous Resolutions ───────────────────────────────────────── */}
          {item.previousResolutions.length > 0 && (
            <Accordion type="single" collapsible>
              <AccordionItem value="history" className="border-none">
                <AccordionTrigger className="py-2 text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    Previous Resolutions ({item.previousResolutions.length})
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="space-y-3 pt-1">
                    {item.previousResolutions.map((res) => (
                      <div
                        key={res.id}
                        className="rounded-md border bg-muted/30 px-4 py-3"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">
                            {res.decision}
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            {new Date(res.timestamp).toLocaleDateString(
                              'en-US',
                              {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              },
                            )}
                          </span>
                        </div>
                        <p className="mt-1.5 text-sm text-muted-foreground">
                          {res.rationale}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Resolved by{' '}
                          <span className="font-medium text-foreground">
                            {res.resolver}
                          </span>
                        </p>
                      </div>
                    ))}
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────────

export function AdjudicationPage() {
  const [selectedId, setSelectedId] = useState(disagreements[0]?.id ?? '')

  const selectedItem = disagreements.find((d) => d.id === selectedId)

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Scale className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Adjudication
            </h1>
            <p className="text-sm text-muted-foreground">
              Resolve label disagreements between annotators and AI agents.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-red-500" />
            <span className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">186</span>{' '}
              disagreements
            </span>
          </div>
          <Separator orientation="vertical" className="h-5" />
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">42</span> resolved
              today
            </span>
          </div>
          <Separator orientation="vertical" className="h-5" />
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-blue-500" />
            <span className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">89.2%</span>{' '}
              agreement rate
            </span>
          </div>
        </div>
      </div>

      {/* ── Two-Panel Layout ────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1">
        {/* ── Left Panel: Disagreement Queue (40%) ──────────────────────── */}
        <div className="flex w-2/5 flex-col border-r border-border bg-muted/20">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">Disagreement Queue</h2>
            <p className="text-xs text-muted-foreground">
              {disagreements.filter((d) => !d.resolved).length} unresolved of{' '}
              {disagreements.length} total
            </p>
          </div>
          <ScrollArea className="flex-1">
            <div className="space-y-2 p-3">
              {disagreements.map((item) => (
                <DisagreementCard
                  key={item.id}
                  item={item}
                  isSelected={item.id === selectedId}
                  onSelect={() => {
                    setSelectedId(item.id)
                  }}
                />
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* ── Right Panel: Resolution Editor (60%) ──────────────────────── */}
        <div className="flex w-3/5 flex-col bg-muted/5">
          {selectedItem ? (
            <ResolutionEditor key={selectedItem.id} item={selectedItem} />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <div className="text-center">
                <Scale className="mx-auto h-10 w-10 text-muted-foreground/30" />
                <p className="mt-3 text-sm text-muted-foreground">
                  Select a disagreement to begin resolution
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
