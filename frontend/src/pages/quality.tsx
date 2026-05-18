import {
  Shield,
  CheckCircle,
  TrendingUp,
  Minus,
  AlertTriangle,
  AlertCircle,
  Activity,
  Eye,
  Search,
  Wrench,
  FileWarning,
  BarChart3,
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
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

// ── Data ─────────────────────────────────────────────────────────────────────

const agreementEntities = [
  'Sarah',
  'Marcus',
  'Elena',
  'GPT-4o',
  'Claude',
  'Gemini',
] as const

type Entity = (typeof agreementEntities)[number]

const agreementScores: Record<Entity, Record<Entity, number>> = {
  Sarah: {
    Sarah: 1.0,
    Marcus: 0.91,
    Elena: 0.88,
    'GPT-4o': 0.93,
    Claude: 0.96,
    Gemini: 0.85,
  },
  Marcus: {
    Sarah: 0.91,
    Marcus: 1.0,
    Elena: 0.83,
    'GPT-4o': 0.87,
    Claude: 0.89,
    Gemini: 0.78,
  },
  Elena: {
    Sarah: 0.88,
    Marcus: 0.83,
    Elena: 1.0,
    'GPT-4o': 0.85,
    Claude: 0.9,
    Gemini: 0.82,
  },
  'GPT-4o': {
    Sarah: 0.93,
    Marcus: 0.87,
    Elena: 0.85,
    'GPT-4o': 1.0,
    Claude: 0.94,
    Gemini: 0.88,
  },
  Claude: {
    Sarah: 0.96,
    Marcus: 0.89,
    Elena: 0.9,
    'GPT-4o': 0.94,
    Claude: 1.0,
    Gemini: 0.86,
  },
  Gemini: {
    Sarah: 0.85,
    Marcus: 0.78,
    Elena: 0.82,
    'GPT-4o': 0.88,
    Claude: 0.86,
    Gemini: 1.0,
  },
}

const driftDatasets = [
  { name: 'Urban Scenes', score: 0.012, status: 'green' as const },
  { name: 'Highway Nighttime', score: 0.045, status: 'yellow' as const },
  { name: 'Pedestrian Detection', score: 0.008, status: 'green' as const },
  { name: 'Construction Zones', score: 0.067, status: 'orange' as const },
  { name: 'Adverse Weather', score: 0.023, status: 'green' as const },
] as const

const calibrationBins = [
  { range: '0.0 - 0.2', predicted: 10, actual: 8 },
  { range: '0.2 - 0.4', predicted: 30, actual: 28 },
  { range: '0.4 - 0.6', predicted: 50, actual: 47 },
  { range: '0.6 - 0.8', predicted: 70, actual: 72 },
  { range: '0.8 - 1.0', predicted: 90, actual: 88 },
] as const

const flaggedRecords = [
  {
    id: 'rec-4821',
    dataset: 'Urban Scenes',
    issue: 'Low confidence (0.42)',
    severity: 'High' as const,
    action: 'Review',
  },
  {
    id: 'rec-9103',
    dataset: 'Highway Nighttime',
    issue: 'Drift anomaly',
    severity: 'Medium' as const,
    action: 'Investigate',
  },
  {
    id: 'rec-7290',
    dataset: 'Adverse Weather',
    issue: 'Reviewer disagreement',
    severity: 'Medium' as const,
    action: 'Adjudicate',
  },
  {
    id: 'rec-2341',
    dataset: 'Construction Zones',
    issue: 'Missing labels',
    severity: 'High' as const,
    action: 'Complete',
  },
  {
    id: 'rec-6677',
    dataset: 'Pedestrian Detection',
    issue: 'Schema violation',
    severity: 'Low' as const,
    action: 'Fix',
  },
] as const

// ── Helpers ──────────────────────────────────────────────────────────────────

function heatmapColor(score: number): string {
  if (score >= 0.9) return 'bg-emerald-500/20 text-emerald-400'
  if (score >= 0.8) return 'bg-amber-500/20 text-amber-400'
  if (score >= 0.7) return 'bg-orange-500/20 text-orange-400'
  return 'bg-red-500/20 text-red-400'
}

function driftBarColor(status: 'green' | 'yellow' | 'orange'): string {
  switch (status) {
    case 'green':
      return 'bg-emerald-500'
    case 'yellow':
      return 'bg-amber-400'
    case 'orange':
      return 'bg-orange-500'
  }
}

function driftBadge(status: 'green' | 'yellow' | 'orange') {
  switch (status) {
    case 'green':
      return null
    case 'yellow':
      return (
        <Badge
          variant="outline"
          className="border-amber-500/20 bg-amber-500/10 text-[10px] text-amber-600"
        >
          Flagged
        </Badge>
      )
    case 'orange':
      return (
        <Badge
          variant="outline"
          className="border-orange-500/20 bg-orange-500/10 text-[10px] text-orange-600"
        >
          Alert
        </Badge>
      )
  }
}

function severityBadge(severity: 'High' | 'Medium' | 'Low') {
  switch (severity) {
    case 'High':
      return (
        <Badge
          variant="outline"
          className="border-red-500/20 bg-red-500/10 text-red-600"
        >
          High
        </Badge>
      )
    case 'Medium':
      return (
        <Badge
          variant="outline"
          className="border-amber-500/20 bg-amber-500/10 text-amber-600"
        >
          Medium
        </Badge>
      )
    case 'Low':
      return (
        <Badge
          variant="outline"
          className="border-zinc-500/20 bg-zinc-500/10 text-zinc-600"
        >
          Low
        </Badge>
      )
  }
}

function actionIcon(action: string) {
  switch (action) {
    case 'Review':
      return <Eye className="h-3.5 w-3.5" />
    case 'Investigate':
      return <Search className="h-3.5 w-3.5" />
    case 'Adjudicate':
      return <Activity className="h-3.5 w-3.5" />
    case 'Complete':
      return <FileWarning className="h-3.5 w-3.5" />
    case 'Fix':
      return <Wrench className="h-3.5 w-3.5" />
    default:
      return <Eye className="h-3.5 w-3.5" />
  }
}

// ── Section Components ───────────────────────────────────────────────────────

function HealthSummaryCards() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {/* Inter-Annotator Agreement */}
      <Card className="border bg-card">
        <CardHeader className="pb-2">
          <CardDescription className="text-xs font-medium uppercase tracking-wider">
            Inter-Annotator Agreement
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums text-emerald-600">
              89.2%
            </span>
            <span className="flex items-center gap-0.5 text-xs font-medium text-emerald-600">
              <TrendingUp className="h-3 w-3" />
              +2.1%
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Cohen&apos;s kappa:{' '}
            <span className="font-semibold tabular-nums text-foreground">
              0.84
            </span>
          </p>
        </CardContent>
      </Card>

      {/* Label Drift */}
      <Card className="border bg-card">
        <CardHeader className="pb-2">
          <CardDescription className="text-xs font-medium uppercase tracking-wider">
            Label Drift
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums text-emerald-600">
              0.023
            </span>
            <Badge
              variant="outline"
              className="border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
            >
              Low
            </Badge>
          </div>
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            KL divergence
            <span className="ml-1 flex items-center gap-0.5 font-medium text-zinc-500">
              <Minus className="h-3 w-3" />
              Stable
            </span>
          </p>
        </CardContent>
      </Card>

      {/* Average Confidence */}
      <Card className="border bg-card">
        <CardHeader className="pb-2">
          <CardDescription className="text-xs font-medium uppercase tracking-wider">
            Average Confidence
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums text-blue-600">
              91.4%
            </span>
          </div>
          <div className="flex gap-3 text-xs text-muted-foreground">
            <span>
              Self-reported:{' '}
              <span className="font-semibold tabular-nums text-foreground">
                93.1%
              </span>
            </span>
            <span>
              Composite:{' '}
              <span className="font-semibold tabular-nums text-foreground">
                89.7%
              </span>
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Resolution Rate */}
      <Card className="border bg-card">
        <CardHeader className="pb-2">
          <CardDescription className="text-xs font-medium uppercase tracking-wider">
            Resolution Rate
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tabular-nums text-emerald-600">
              94.5%
            </span>
            <span className="flex items-center gap-0.5 text-xs font-medium text-emerald-600">
              <TrendingUp className="h-3 w-3" />
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            <span className="font-semibold tabular-nums text-foreground">
              176
            </span>{' '}
            resolved of{' '}
            <span className="font-semibold tabular-nums text-foreground">
              186
            </span>{' '}
            found
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function AgreementAnalysis() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Agreement Analysis</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Pairwise agreement heatmap between reviewers and AI models
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="pb-2 pr-2 text-left text-[11px] font-medium text-muted-foreground" />
                {agreementEntities.map((name) => (
                  <th
                    key={name}
                    className="pb-2 text-center text-[11px] font-medium text-muted-foreground"
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agreementEntities.map((row) => (
                <tr key={row}>
                  <td className="py-1 pr-3 text-xs font-medium">{row}</td>
                  {agreementEntities.map((col) => {
                    const score = agreementScores[row][col]
                    const isDiagonal = row === col
                    return (
                      <td key={col} className="p-1 text-center">
                        <div
                          className={`mx-auto flex h-9 w-14 items-center justify-center rounded-md text-xs font-semibold ${
                            isDiagonal
                              ? 'bg-muted text-muted-foreground'
                              : heatmapColor(score)
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

        {/* Legend */}
        <div className="flex flex-wrap items-center justify-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500/20" />
            &gt;0.9
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-500/20" />
            0.8-0.9
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-orange-500/20" />
            0.7-0.8
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-500/20" />
            &lt;0.7
          </span>
        </div>

        <Separator />

        {/* Summary line */}
        <p className="text-xs text-muted-foreground">
          Highest agreement:{' '}
          <span className="font-semibold text-emerald-600">
            Sarah ↔ Claude (0.96)
          </span>
          {' · '}
          Lowest:{' '}
          <span className="font-semibold text-orange-600">
            Marcus ↔ Gemini (0.78)
          </span>
        </p>
      </CardContent>
    </Card>
  )
}

function DriftDetection() {
  const maxScore = 0.1

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Drift Detection</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Distribution shift by dataset (KL divergence)
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col space-y-5">
        {/* Current score */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-2xl font-bold tabular-nums">0.023</p>
            <p className="text-xs text-muted-foreground">Overall Drift Score</p>
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

        {/* Per-dataset bars */}
        <div className="space-y-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Breakdown by Dataset
          </p>
          {driftDatasets.map((ds) => {
            const pct = Math.min((ds.score / maxScore) * 100, 100)
            return (
              <div key={ds.name} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {ds.name}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold tabular-nums">
                      {ds.score.toFixed(3)}
                    </span>
                    {driftBadge(ds.status)}
                  </div>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full ${driftBarColor(ds.status)} transition-all`}
                    style={{ width: `${String(pct)}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-auto pt-2">
          <Button variant="outline" className="w-full gap-1.5">
            <Activity className="h-4 w-4" />
            Run Drift Analysis
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ConfidenceCalibration() {
  const maxPct = 100

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Confidence Calibration</CardTitle>
          </div>
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
          >
            <CheckCircle className="h-3 w-3" />
            Well-calibrated
          </Badge>
        </div>
        <CardDescription className="text-xs">
          Predicted confidence vs actual accuracy across bins
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col space-y-5">
        {/* Paired bar chart */}
        <div className="space-y-4">
          {calibrationBins.map((bin) => {
            const predW = (bin.predicted / maxPct) * 100
            const actW = (bin.actual / maxPct) * 100
            return (
              <div key={bin.range} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-muted-foreground">
                    {bin.range}
                  </span>
                  <span className="text-muted-foreground">
                    <span className="font-semibold tabular-nums text-blue-600">
                      {bin.predicted}%
                    </span>
                    {' / '}
                    <span className="font-semibold tabular-nums text-emerald-600">
                      {bin.actual}%
                    </span>
                  </span>
                </div>
                <div className="space-y-1">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all"
                      style={{ width: `${String(predW)}%` }}
                    />
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${String(actW)}%` }}
                    />
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <Separator />

        {/* Legend */}
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-500" />
            Predicted
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" />
            Actual
          </span>
        </div>
      </CardContent>
    </Card>
  )
}

function FlaggedRecords() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">Flagged Records</CardTitle>
          </div>
          <Badge variant="secondary">{flaggedRecords.length} records</Badge>
        </div>
        <CardDescription className="text-xs">
          Records requiring manual attention or review
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Record</TableHead>
              <TableHead className="text-xs">Dataset</TableHead>
              <TableHead className="text-xs">Issue</TableHead>
              <TableHead className="text-xs">Severity</TableHead>
              <TableHead className="text-right text-xs">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {flaggedRecords.map((rec) => (
              <TableRow key={rec.id}>
                <TableCell className="font-mono text-xs font-medium">
                  {rec.id}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {rec.dataset}
                </TableCell>
                <TableCell className="text-xs">{rec.issue}</TableCell>
                <TableCell>{severityBadge(rec.severity)}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 px-2 text-xs"
                  >
                    {actionIcon(rec.action)}
                    {rec.action}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function QualityPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Shield className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Quality</h1>
            <p className="text-sm text-muted-foreground">
              89.2% agreement · 0.023 drift · 94.5% resolution rate
            </p>
          </div>
        </div>
        <Badge className="gap-1.5 bg-emerald-600 px-3 py-1.5 text-sm hover:bg-emerald-600">
          <CheckCircle className="h-4 w-4" />
          Healthy
        </Badge>
      </div>

      {/* Section 1: Health Summary Cards */}
      <HealthSummaryCards />

      {/* Section 2: Agreement Analysis */}
      <AgreementAnalysis />

      {/* Section 3: Two-column — Drift + Calibration */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DriftDetection />
        <ConfidenceCalibration />
      </div>

      {/* Section 4: Flagged Records */}
      <FlaggedRecords />
    </div>
  )
}
