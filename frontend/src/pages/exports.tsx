import { useState } from 'react'
import {
  Package,
  Download,
  Eye,
  Plus,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  Clock,
  XCircle,
  Loader2,
  FileText,
  Shield,
  ArrowRight,
  User,
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
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { mockExports, mockDatasets } from '@/mocks/data'
import { formatNumber, formatDate, relativeTime } from '@/lib/format'

// ── Status badge helper ──────────────────────────────────────────────────────

function statusBadge(status: 'completed' | 'in-progress' | 'failed') {
  switch (status) {
    case 'completed':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
        >
          <CheckCircle className="h-3 w-3" />
          Completed
        </Badge>
      )
    case 'in-progress':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-blue-500/20 bg-blue-500/10 text-blue-600"
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          In Progress
        </Badge>
      )
    case 'failed':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-red-500/20 bg-red-500/10 text-red-600"
        >
          <XCircle className="h-3 w-3" />
          Failed
        </Badge>
      )
  }
}

function formatBadge(format: string) {
  const colors: Record<string, { bg: string; text: string; border: string }> = {
    'COCO JSON': {
      bg: 'bg-blue-500/10',
      text: 'text-blue-600',
      border: 'border-blue-500/20',
    },
    'Pascal VOC': {
      bg: 'bg-violet-500/10',
      text: 'text-violet-600',
      border: 'border-violet-500/20',
    },
    YOLO: {
      bg: 'bg-orange-500/10',
      text: 'text-orange-600',
      border: 'border-orange-500/20',
    },
    JSONL: {
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-600',
      border: 'border-emerald-500/20',
    },
    CSV: {
      bg: 'bg-zinc-500/10',
      text: 'text-zinc-600',
      border: 'border-zinc-500/20',
    },
    Parquet: {
      bg: 'bg-amber-500/10',
      text: 'text-amber-600',
      border: 'border-amber-500/20',
    },
    'HuggingFace Hub': {
      bg: 'bg-yellow-500/10',
      text: 'text-yellow-700',
      border: 'border-yellow-500/20',
    },
  }
  const c = colors[format] ?? {
    bg: 'bg-zinc-500/10',
    text: 'text-zinc-600',
    border: 'border-zinc-500/20',
  }

  return (
    <Badge variant="outline" className={`${c.bg} ${c.text} ${c.border}`}>
      {format}
    </Badge>
  )
}

// ── Exports Tab ──────────────────────────────────────────────────────────────

function ExportWizard() {
  const [isOpen, setIsOpen] = useState(true)
  const [dataset, setDataset] = useState('')
  const [format, setFormat] = useState('')
  const [inclusions, setInclusions] = useState({
    recordData: true,
    labels: true,
    metadata: true,
    qualityScores: false,
    lineage: false,
  })
  const [minAgreement, setMinAgreement] = useState('0.8')
  const [excludeFlagged, setExcludeFlagged] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card>
        <CardHeader className="pb-3">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center justify-between"
            >
              <div className="flex items-center gap-2">
                <Package className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-base">Export Wizard</CardTitle>
              </div>
              {isOpen ? (
                <ChevronUp className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
          </CollapsibleTrigger>
          <CardDescription className="text-xs">
            Configure and create a new dataset export
          </CardDescription>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-5">
            {/* Dataset + Format row */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-xs">Dataset</Label>
                <Select value={dataset} onValueChange={setDataset}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select dataset..." />
                  </SelectTrigger>
                  <SelectContent>
                    {mockDatasets.map((ds) => (
                      <SelectItem key={ds.id} value={ds.id}>
                        {ds.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Format</Label>
                <Select value={format} onValueChange={setFormat}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select format..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="jsonl">JSONL</SelectItem>
                    <SelectItem value="csv">CSV</SelectItem>
                    <SelectItem value="parquet">Parquet</SelectItem>
                    <SelectItem value="coco-json">COCO JSON</SelectItem>
                    <SelectItem value="huggingface">HuggingFace Hub</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />

            {/* Inclusion checkboxes */}
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Include
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="inc-records"
                    checked={inclusions.recordData}
                    onCheckedChange={(c) => {
                      setInclusions((s) => ({ ...s, recordData: c === true }))
                    }}
                  />
                  <label htmlFor="inc-records" className="text-xs">
                    Record Data
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="inc-labels"
                    checked={inclusions.labels}
                    onCheckedChange={(c) => {
                      setInclusions((s) => ({ ...s, labels: c === true }))
                    }}
                  />
                  <label htmlFor="inc-labels" className="text-xs">
                    Labels
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="inc-metadata"
                    checked={inclusions.metadata}
                    onCheckedChange={(c) => {
                      setInclusions((s) => ({ ...s, metadata: c === true }))
                    }}
                  />
                  <label htmlFor="inc-metadata" className="text-xs">
                    Metadata
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="inc-quality"
                    checked={inclusions.qualityScores}
                    onCheckedChange={(c) => {
                      setInclusions((s) => ({
                        ...s,
                        qualityScores: c === true,
                      }))
                    }}
                  />
                  <label htmlFor="inc-quality" className="text-xs">
                    Quality Scores
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="inc-lineage"
                    checked={inclusions.lineage}
                    onCheckedChange={(c) => {
                      setInclusions((s) => ({ ...s, lineage: c === true }))
                    }}
                  />
                  <label htmlFor="inc-lineage" className="text-xs">
                    Lineage
                  </label>
                </div>
              </div>
            </div>

            <Separator />

            {/* Filters */}
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Filters
              </p>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                <div className="space-y-2">
                  <Label htmlFor="min-agreement" className="text-xs">
                    Min Agreement
                  </Label>
                  <Input
                    id="min-agreement"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={minAgreement}
                    onChange={(e) => {
                      setMinAgreement(e.target.value)
                    }}
                    className="h-9 w-28 tabular-nums"
                  />
                </div>
                <div className="flex items-center gap-3 pb-0.5">
                  <Switch
                    id="exclude-flagged"
                    checked={excludeFlagged}
                    onCheckedChange={setExcludeFlagged}
                  />
                  <Label htmlFor="exclude-flagged" className="text-xs">
                    Exclude Flagged Records
                  </Label>
                </div>
              </div>
            </div>

            <Separator />

            {/* Preview */}
            <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2.5">
              <div className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Preview:</span>
                <span className="font-semibold">25,600 records</span>
                <span className="text-muted-foreground">,</span>
                <span className="text-muted-foreground">estimated size</span>
                <span className="font-semibold">1.2 GB</span>
              </div>
            </div>

            <Button className="w-full gap-2">
              <Shield className="h-4 w-4" />
              Validate & Export
            </Button>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

function ExportsTab() {
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {mockExports.length} exports
        </p>
        <Button className="gap-1.5">
          <Plus className="h-4 w-4" />
          Create Export
        </Button>
      </div>

      {/* Exports Table */}
      <Card className="bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Dataset</TableHead>
              <TableHead>Format</TableHead>
              <TableHead className="text-right">Records</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Created By</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockExports.map((exp) => (
              <TableRow key={exp.id}>
                <TableCell className="font-medium">{exp.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {exp.datasetName}
                </TableCell>
                <TableCell>{formatBadge(exp.format)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(exp.recordCount)}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    v{exp.version}
                  </Badge>
                </TableCell>
                <TableCell>{statusBadge(exp.status)}</TableCell>
                <TableCell className="text-muted-foreground">
                  {exp.fileSize}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {exp.createdBy}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(exp.createdAt)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1 px-2 text-xs"
                      disabled={exp.status !== 'completed'}
                    >
                      <Download className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1 px-2 text-xs"
                    >
                      <Eye className="h-3 w-3" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Export Wizard */}
      <ExportWizard />
    </div>
  )
}

// ── Releases Tab ─────────────────────────────────────────────────────────────

const releasePipelineSteps = [
  'Draft',
  'Validating',
  'Pending Approval',
  'Approved',
  'Released',
] as const

type ReleaseStatus =
  | 'draft'
  | 'validating'
  | 'pending-approval'
  | 'approved'
  | 'released'

interface Release {
  id: string
  name: string
  status: ReleaseStatus
  recordCount: number
  datasetName: string
  version: string
  approvedBy: string | null
  createdAt: string
  validationResults: {
    schemaValid: boolean
    qualityGatePassed: boolean
    completenessCheck: boolean
    duplicateCheck: boolean
  }
}

const mockReleases: Release[] = [
  {
    id: 'rel-001',
    name: 'Pedestrian Detection v2.8',
    status: 'released',
    recordCount: 25_600,
    datasetName: 'Pedestrian Detection',
    version: '2.8.0',
    approvedBy: 'Sarah Chen',
    createdAt: '2026-03-25T22:00:00Z',
    validationResults: {
      schemaValid: true,
      qualityGatePassed: true,
      completenessCheck: true,
      duplicateCheck: true,
    },
  },
  {
    id: 'rel-002',
    name: 'Urban Scenes Q1 v1.3',
    status: 'pending-approval',
    recordCount: 12_320,
    datasetName: 'Urban Scenes 2026-Q1',
    version: '1.3.0',
    approvedBy: null,
    createdAt: '2026-03-26T06:00:00Z',
    validationResults: {
      schemaValid: true,
      qualityGatePassed: true,
      completenessCheck: true,
      duplicateCheck: true,
    },
  },
  {
    id: 'rel-003',
    name: 'Adverse Weather v0.5',
    status: 'draft',
    recordCount: 3_100,
    datasetName: 'Adverse Weather',
    version: '0.5.0',
    approvedBy: null,
    createdAt: '2026-03-26T08:00:00Z',
    validationResults: {
      schemaValid: true,
      qualityGatePassed: false,
      completenessCheck: false,
      duplicateCheck: true,
    },
  },
]

function releaseStatusToStepIndex(status: ReleaseStatus): number {
  switch (status) {
    case 'draft':
      return 0
    case 'validating':
      return 1
    case 'pending-approval':
      return 2
    case 'approved':
      return 3
    case 'released':
      return 4
  }
}

function releaseStatusBadge(status: ReleaseStatus) {
  switch (status) {
    case 'released':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
        >
          <CheckCircle className="h-3 w-3" />
          Released
        </Badge>
      )
    case 'approved':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
        >
          <CheckCircle className="h-3 w-3" />
          Approved
        </Badge>
      )
    case 'pending-approval':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-amber-500/20 bg-amber-500/10 text-amber-600"
        >
          <Clock className="h-3 w-3" />
          Pending Approval
        </Badge>
      )
    case 'validating':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-blue-500/20 bg-blue-500/10 text-blue-600"
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          Validating
        </Badge>
      )
    case 'draft':
      return (
        <Badge
          variant="outline"
          className="gap-1.5 border-zinc-500/20 bg-zinc-500/10 text-zinc-600"
        >
          <FileText className="h-3 w-3" />
          Draft
        </Badge>
      )
  }
}

function ReleasePipeline() {
  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-base">Release Pipeline</CardTitle>
        <CardDescription className="text-xs">
          Standard release workflow stages
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-center">
          <div className="flex items-center gap-1">
            {releasePipelineSteps.map((step, i) => (
              <div key={step} className="flex items-center gap-1">
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className={`flex h-9 min-w-[80px] items-center justify-center rounded-lg px-3 text-xs font-medium transition-colors ${
                      i === 0
                        ? 'bg-zinc-500/10 text-zinc-600'
                        : i === 1
                          ? 'bg-blue-500/10 text-blue-600'
                          : i === 2
                            ? 'bg-amber-500/10 text-amber-600'
                            : i === 3
                              ? 'bg-emerald-500/10 text-emerald-600'
                              : 'bg-primary/10 text-primary'
                    }`}
                  >
                    {step}
                  </div>
                </div>
                {i < releasePipelineSteps.length - 1 && (
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/40" />
                )}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ReleaseDetailCard({ release }: { release: Release }) {
  const vr = release.validationResults
  const checks = [
    { label: 'Schema Validation', passed: vr.schemaValid },
    { label: 'Quality Gate', passed: vr.qualityGatePassed },
    { label: 'Completeness Check', passed: vr.completenessCheck },
    { label: 'Duplicate Check', passed: vr.duplicateCheck },
  ]
  const passedCount = checks.filter((c) => c.passed).length

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm">{release.name}</CardTitle>
            <CardDescription className="mt-1 text-xs">
              {release.datasetName} &middot; v{release.version}
            </CardDescription>
          </div>
          {releaseStatusBadge(release.status)}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-md bg-muted/50 px-3 py-2 text-center">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Records
            </p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums">
              {formatNumber(release.recordCount)}
            </p>
          </div>
          <div className="rounded-md bg-muted/50 px-3 py-2 text-center">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Checks
            </p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums">
              {passedCount}/{checks.length}
            </p>
          </div>
          <div className="rounded-md bg-muted/50 px-3 py-2 text-center">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Stage
            </p>
            <p className="mt-0.5 text-sm font-semibold">
              {releaseStatusToStepIndex(release.status) + 1}/5
            </p>
          </div>
        </div>

        {/* Validation results */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">
            Validation Results
          </p>
          <div className="space-y-1.5">
            {checks.map((check) => (
              <div
                key={check.label}
                className="flex items-center justify-between rounded-md bg-muted/30 px-3 py-1.5"
              >
                <span className="text-xs">{check.label}</span>
                {check.passed ? (
                  <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-red-500" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Approval */}
        {release.approvedBy ? (
          <div className="flex items-center gap-2 rounded-md bg-emerald-500/5 px-3 py-2 text-xs">
            <User className="h-3.5 w-3.5 text-emerald-600" />
            <span className="text-muted-foreground">Approved by</span>
            <span className="font-medium text-emerald-600">
              {release.approvedBy}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            Awaiting approval
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ReleasesTab() {
  const [selectedRelease, setSelectedRelease] = useState('rel-001')
  const selected =
    mockReleases.find((r) => r.id === selectedRelease) ?? mockReleases[0]

  return (
    <div className="space-y-4">
      {/* Pipeline Visualization */}
      <ReleasePipeline />

      {/* Two-column: table + detail */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Release</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Records</TableHead>
                  <TableHead>Approved By</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockReleases.map((rel) => (
                  <TableRow
                    key={rel.id}
                    className={`cursor-pointer ${
                      selectedRelease === rel.id ? 'bg-muted/50' : ''
                    }`}
                    onClick={() => {
                      setSelectedRelease(rel.id)
                    }}
                  >
                    <TableCell>
                      <div>
                        <p className="font-medium">{rel.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {rel.datasetName}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell>{releaseStatusBadge(rel.status)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(rel.recordCount)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {rel.approvedBy ?? '\u2014'}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {relativeTime(rel.createdAt)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
        <div className="lg:col-span-2">
          {selected && <ReleaseDetailCard release={selected} />}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function ExportsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Package className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Exports & Releases
            </h1>
            <p className="text-sm text-muted-foreground">
              Package and export labeled datasets with versioning and
              validation.
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="exports">
        <TabsList>
          <TabsTrigger
            value="exports"
            className="gap-1.5 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            <Download className="h-3.5 w-3.5" />
            Exports
          </TabsTrigger>
          <TabsTrigger
            value="releases"
            className="gap-1.5 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            <Package className="h-3.5 w-3.5" />
            Releases
          </TabsTrigger>
        </TabsList>

        <TabsContent value="exports">
          <ExportsTab />
        </TabsContent>

        <TabsContent value="releases">
          <ReleasesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
