import { useState } from 'react'
import {
  Database,
  Search,
  Plus,
  Eye,
  BarChart3,
  Clock,
  Hash,
  FileText,
  CheckCircle,
  AlertTriangle,
  Users,
  Shield,
  TrendingUp,
  GitBranch,
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
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { mockDatasets } from '@/mocks/data'
import type { Dataset } from '@/mocks/data'
import { formatNumber, relativeTime } from '@/lib/format'

// ── Helpers ───────────────────────────────────────────────────────────────────

function healthColor(status: Dataset['healthStatus']): {
  dot: string
  bg: string
  text: string
  border: string
} {
  switch (status) {
    case 'healthy':
      return {
        dot: 'bg-emerald-500',
        bg: 'bg-emerald-500/10',
        text: 'text-emerald-600',
        border: 'border-emerald-500/20',
      }
    case 'warning':
      return {
        dot: 'bg-amber-500',
        bg: 'bg-amber-500/10',
        text: 'text-amber-600',
        border: 'border-amber-500/20',
      }
    case 'critical':
      return {
        dot: 'bg-red-500',
        bg: 'bg-red-500/10',
        text: 'text-red-600',
        border: 'border-red-500/20',
      }
  }
}

function formatBadge(format: string): {
  bg: string
  text: string
  border: string
} {
  switch (format) {
    case 'COCO JSON':
      return {
        bg: 'bg-blue-500/10',
        text: 'text-blue-600',
        border: 'border-blue-500/20',
      }
    case 'Pascal VOC':
      return {
        bg: 'bg-violet-500/10',
        text: 'text-violet-600',
        border: 'border-violet-500/20',
      }
    case 'YOLO':
      return {
        bg: 'bg-orange-500/10',
        text: 'text-orange-600',
        border: 'border-orange-500/20',
      }
    default:
      return {
        bg: 'bg-zinc-500/10',
        text: 'text-zinc-600',
        border: 'border-zinc-500/20',
      }
  }
}

// ── Tab 1: Dataset Catalog ────────────────────────────────────────────────────

function DatasetCard({ dataset }: { dataset: Dataset }) {
  const labeledPct = Math.round(
    (dataset.labeledCount / dataset.recordCount) * 100,
  )
  const health = healthColor(dataset.healthStatus)
  const fmt = formatBadge(dataset.format)

  return (
    <Card className="group border bg-card transition-all hover:border-primary/40 hover:shadow-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="cursor-pointer truncate text-sm transition-colors group-hover:text-primary">
              {dataset.name}
            </CardTitle>
            <CardDescription className="mt-1 line-clamp-1 text-xs">
              {dataset.description}
            </CardDescription>
          </div>
          <Badge
            variant="outline"
            className={`shrink-0 gap-1.5 ${health.bg} ${health.text} ${health.border}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${health.dot}`} />
            {dataset.healthStatus}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Record count + progress */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              {formatNumber(dataset.labeledCount)} /{' '}
              {formatNumber(dataset.recordCount)} labeled
            </span>
            <span className="font-medium tabular-nums">{labeledPct}%</span>
          </div>
          <Progress value={labeledPct} className="h-1.5 bg-muted" />
        </div>

        {/* Format + Tags row */}
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant="outline"
            className={`text-[10px] ${fmt.bg} ${fmt.text} ${fmt.border}`}
          >
            {dataset.format}
          </Badge>
          {dataset.tags.map((tag) => (
            <Badge
              key={tag}
              variant="secondary"
              className="text-[10px] font-normal"
            >
              {tag}
            </Badge>
          ))}
        </div>

        <Separator />

        {/* Footer row */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="h-3 w-3" />
            {relativeTime(dataset.updatedAt)}
          </span>
          <div className="flex gap-1.5">
            <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs">
              <Eye className="h-3 w-3" />
              Records
            </Button>
            <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs">
              <BarChart3 className="h-3 w-3" />
              Analytics
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function DatasetCatalogTab() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [formatFilter, setFormatFilter] = useState<string>('all')

  const filtered = mockDatasets.filter((ds) => {
    const matchesSearch =
      search === '' ||
      ds.name.toLowerCase().includes(search.toLowerCase()) ||
      ds.description.toLowerCase().includes(search.toLowerCase())
    const matchesStatus =
      statusFilter === 'all' || ds.healthStatus === statusFilter
    const matchesFormat =
      formatFilter === 'all' || ds.format === formatFilter
    return matchesSearch && matchesStatus && matchesFormat
  })

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col gap-3 rounded-lg bg-muted/50 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative max-w-xs flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search datasets..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="healthy">Healthy</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
            </SelectContent>
          </Select>
          <Select value={formatFilter} onValueChange={setFormatFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Format" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Formats</SelectItem>
              <SelectItem value="COCO JSON">COCO JSON</SelectItem>
              <SelectItem value="Pascal VOC">Pascal VOC</SelectItem>
              <SelectItem value="YOLO">YOLO</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button className="gap-1.5">
          <Plus className="h-4 w-4" />
          Import Dataset
        </Button>
      </div>

      {/* Dataset Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((ds) => (
          <DatasetCard key={ds.id} dataset={ds} />
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <Database className="h-8 w-8 text-muted-foreground/40" />
          <p className="mt-2 text-sm text-muted-foreground">
            No datasets match your filters.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Tab 2: Record Inspector ───────────────────────────────────────────────────

function FieldRow({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean | undefined
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span
        className={`text-right text-xs font-medium ${mono ? 'font-mono' : ''}`}
      >
        {value}
      </span>
    </div>
  )
}

function TimelineEntry({
  label,
  detail,
  time,
  isLast,
  color,
}: {
  label: string
  detail: string
  time: string
  isLast?: boolean | undefined
  color: string
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />
        {!isLast && (
          <div className="w-px flex-1 bg-border" />
        )}
      </div>
      <div className={`pb-4 ${isLast ? 'pb-0' : ''}`}>
        <p className="text-xs font-medium leading-none">{label}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>
        <p className="mt-0.5 text-[10px] text-muted-foreground/60">{time}</p>
      </div>
    </div>
  )
}

function RecordInspectorTab() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Source Data Panel */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Source Data</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Raw record fields for rec-4821
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border">
            <FieldRow
              label="external_id"
              value="urban-sf-frame-4821"
              mono
            />
            <FieldRow label="sequence_index" value="4821" mono />
            <FieldRow label="content_hash" value="a3f8c2..." mono />
            <FieldRow label="source" value="cameras/front_center" mono />
            <FieldRow
              label="timestamp"
              value="2026-01-15T14:23:41Z"
              mono
            />
            <FieldRow label="resolution" value="1920x1080" />
            <FieldRow label="weather" value="overcast" />
          </div>
        </CardContent>
      </Card>

      {/* Labels Panel */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Labels</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Agent output and human review
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Agent labels */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium">Agent: GPT-4o</span>
              <Badge
                variant="outline"
                className="border-blue-500/20 bg-blue-500/10 text-[10px] text-blue-600"
              >
                confidence 0.92
              </Badge>
            </div>
            <div className="rounded-md bg-muted/50 p-2.5 font-mono text-[11px] leading-relaxed">
              <div className="flex gap-1">
                <span className="text-muted-foreground">vehicle_count:</span>
                <span className="font-semibold">3</span>
              </div>
              <div className="flex gap-1">
                <span className="text-muted-foreground">
                  pedestrian_count:
                </span>
                <span className="font-semibold">1</span>
              </div>
              <div className="flex gap-1">
                <span className="text-muted-foreground">traffic_signs:</span>
                <span className="font-semibold">
                  [&quot;stop&quot;, &quot;speed_limit_30&quot;]
                </span>
              </div>
            </div>
          </div>

          <Separator />

          {/* Human review */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium">
                Human: Sarah Chen
              </span>
              <Badge
                variant="outline"
                className="border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
              >
                approved w/ corrections
              </Badge>
            </div>
            <div className="rounded-md bg-muted/50 p-2.5 font-mono text-[11px] leading-relaxed">
              <div className="flex gap-1">
                <span className="text-muted-foreground">vehicle_count:</span>
                <span className="font-semibold text-amber-600">
                  4{' '}
                  <span className="text-[10px] font-normal text-muted-foreground">
                    (was 3)
                  </span>
                </span>
              </div>
              <div className="flex gap-1">
                <span className="text-muted-foreground">
                  pedestrian_count:
                </span>
                <span className="font-semibold">1</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-md bg-emerald-500/5 px-3 py-2 text-xs">
            <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
            <span className="font-medium text-emerald-600">
              Human correction adopted
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Quality Panel */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Quality Metrics</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Record-level quality assessment
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Confidence */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Confidence</span>
              <span className="font-medium tabular-nums">0.92</span>
            </div>
            <Progress value={92} className="h-1.5 bg-muted" />
          </div>

          {/* Agreement */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Agreement</span>
              <span className="font-medium tabular-nums">
                3/4 reviewers (75%)
              </span>
            </div>
            <Progress value={75} className="h-1.5 bg-muted" />
          </div>

          <Separator />

          {/* Status flags */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-center">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Export Eligible
              </p>
              <p className="mt-0.5 text-sm font-semibold text-emerald-600">
                Yes
              </p>
            </div>
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-center">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Flags
              </p>
              <p className="mt-0.5 text-sm font-semibold text-muted-foreground">
                None
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lineage Panel */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Lineage</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Record processing history
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-0">
            <TimelineEntry
              label="Ingested"
              detail="Imported from cameras/front_center batch"
              time="2026-01-15 14:23:41 UTC"
              color="bg-zinc-400"
            />
            <TimelineEntry
              label="Pre-labeled"
              detail="GPT-4o agent run ar-001 / confidence 0.92"
              time="2026-01-16 02:14:08 UTC"
              color="bg-blue-500"
            />
            <TimelineEntry
              label="Reviewed"
              detail="Sarah Chen reviewed and flagged correction"
              time="2026-01-17 09:42:15 UTC"
              color="bg-amber-500"
            />
            <TimelineEntry
              label="Corrected"
              detail="vehicle_count updated 3 -> 4"
              time="2026-01-17 09:43:02 UTC"
              color="bg-orange-500"
            />
            <TimelineEntry
              label="Quality Checked"
              detail="Passed automated quality gate (score 0.94)"
              time="2026-01-17 10:00:00 UTC"
              color="bg-emerald-500"
            />
            <TimelineEntry
              label="Export Cleared"
              detail="Eligible for COCO JSON export v1.3.0"
              time="2026-01-17 10:01:12 UTC"
              color="bg-purple-500"
              isLast
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Tab 3: Analytics ──────────────────────────────────────────────────────────

const labelDistribution = [
  { label: 'vehicle', count: 18_200, color: 'bg-blue-500' },
  { label: 'pedestrian', count: 12_400, color: 'bg-emerald-500' },
  { label: 'traffic_sign', count: 8_900, color: 'bg-amber-500' },
  { label: 'road_marking', count: 6_200, color: 'bg-violet-500' },
  { label: 'construction', count: 2_100, color: 'bg-red-500' },
] as const

const maxLabelCount = labelDistribution[0]?.count ?? 1

const qualityTrend = [62, 68, 71, 74, 78, 82, 85, 88, 89, 91, 91, 92] as const

const agreementMatrix = [
  { name: 'Sarah C.', scores: [1.0, 0.89, 0.84] },
  { name: 'Marcus J.', scores: [0.89, 1.0, 0.81] },
  { name: 'Elena R.', scores: [0.84, 0.81, 1.0] },
] as const

const reviewerNames = ['Sarah C.', 'Marcus J.', 'Elena R.'] as const

const driftTrend = [
  0.018, 0.015, 0.019, 0.021, 0.017, 0.020, 0.022, 0.023,
] as const

function LabelDistributionCard() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Label Distribution</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Total label counts across all datasets
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {labelDistribution.map((item) => {
          const pct = Math.round((item.count / maxLabelCount) * 100)
          return (
            <div key={item.label} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono text-muted-foreground">
                  {item.label}
                </span>
                <span className="font-medium tabular-nums">
                  {formatNumber(item.count)}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full ${item.color} transition-all`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function QualityOverTimeCard() {
  const max = 100
  const chartHeight = 120
  const points = qualityTrend.map((v, i) => ({
    x: (i / (qualityTrend.length - 1)) * 100,
    y: chartHeight - (v / max) * chartHeight,
  }))

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
    .join(' ')

  const areaD = `${pathD} L 100 ${chartHeight} L 0 ${chartHeight} Z`

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Quality Over Time</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Average quality score trend (12 weeks)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between pb-1 text-[10px] text-muted-foreground">
          <span>W1</span>
          <span>W6</span>
          <span>W12</span>
        </div>
        <svg
          viewBox={`0 0 100 ${chartHeight}`}
          className="h-[120px] w-full"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="qualityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.3" />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <path d={areaD} fill="url(#qualityGrad)" />
          <path
            d={pathD}
            fill="none"
            stroke="hsl(var(--primary))"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          {points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r="2"
              fill="hsl(var(--primary))"
              className="opacity-0 transition-opacity hover:opacity-100"
            />
          ))}
        </svg>
        <div className="mt-2 flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Current</span>
          <span className="font-semibold text-emerald-600">
            {qualityTrend[qualityTrend.length - 1]}%
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function heatmapColor(score: number): string {
  if (score >= 0.95) return 'bg-emerald-500'
  if (score >= 0.85) return 'bg-emerald-400'
  if (score >= 0.8) return 'bg-amber-400'
  return 'bg-red-400'
}

function AgreementMatrixCard() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Agreement Matrix</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Inter-annotator agreement scores
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="pb-2 text-left text-[10px] font-medium text-muted-foreground" />
                {reviewerNames.map((name) => (
                  <th
                    key={name}
                    className="pb-2 text-center text-[10px] font-medium text-muted-foreground"
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agreementMatrix.map((row) => (
                <tr key={row.name}>
                  <td className="py-1 pr-3 text-xs font-medium">{row.name}</td>
                  {row.scores.map((score, j) => {
                    const rName = reviewerNames[j]
                    const isDiagonal = row.name === rName
                    return (
                      <td key={rName} className="p-1 text-center">
                        <div
                          className={`mx-auto flex h-9 w-14 items-center justify-center rounded-md text-xs font-semibold ${
                            isDiagonal
                              ? 'bg-muted text-muted-foreground'
                              : `${heatmapColor(score)} text-white`
                          }`}
                        >
                          {score.toFixed(2)}
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center justify-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" />
            &gt;0.95
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-400" />
            0.85-0.95
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-400" />
            0.80-0.85
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-400" />
            &lt;0.80
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function DriftDetectionCard() {
  const currentDrift = driftTrend[driftTrend.length - 1] ?? 0
  const maxDrift = 0.05
  const barHeight = 48

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Drift Detection</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Label distribution shift over time
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Drift score headline */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-2xl font-bold tabular-nums">
              {currentDrift.toFixed(3)}
            </p>
            <p className="text-xs text-muted-foreground">Drift Score</p>
          </div>
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Low
          </Badge>
        </div>

        <Separator />

        {/* Trend bars */}
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            8-Week Trend
          </p>
          <div className="flex items-end gap-1.5">
            {driftTrend.map((val, i) => {
              const h = Math.max(4, (val / maxDrift) * barHeight)
              const isLast = i === driftTrend.length - 1
              return (
                <div
                  key={i}
                  className="flex flex-1 flex-col items-center gap-1"
                >
                  <div
                    className={`w-full rounded-sm transition-colors ${
                      isLast ? 'bg-primary' : 'bg-primary/30'
                    }`}
                    style={{ height: `${h}px` }}
                  />
                </div>
              )
            })}
          </div>
          <div className="mt-1 flex justify-between text-[9px] text-muted-foreground/60">
            <span>W1</span>
            <span>W8</span>
          </div>
        </div>

        <Separator />

        <p className="text-xs leading-relaxed text-muted-foreground">
          Drift score measures the statistical distance between the current
          label distribution and the baseline. Scores below{' '}
          <span className="font-medium text-foreground">0.05</span> are
          considered stable.
        </p>
      </CardContent>
    </Card>
  )
}

function AnalyticsTab() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <LabelDistributionCard />
      <QualityOverTimeCard />
      <AgreementMatrixCard />
      <DriftDetectionCard />
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function DataPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Database className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Data</h1>
            <p className="text-sm text-muted-foreground">
              Browse datasets, inspect records, and view data analytics.
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="catalog">
        <TabsList>
          <TabsTrigger value="catalog" className="gap-1.5 text-base data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            <Database className="h-3.5 w-3.5" />
            Dataset Catalog
          </TabsTrigger>
          <TabsTrigger value="inspector" className="gap-1.5 text-base data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            <Eye className="h-3.5 w-3.5" />
            Record Inspector
          </TabsTrigger>
          <TabsTrigger value="analytics" className="gap-1.5 text-base data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            <BarChart3 className="h-3.5 w-3.5" />
            Analytics
          </TabsTrigger>
        </TabsList>

        <TabsContent value="catalog">
          <DatasetCatalogTab />
        </TabsContent>

        <TabsContent value="inspector">
          <RecordInspectorTab />
        </TabsContent>

        <TabsContent value="analytics">
          <AnalyticsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
