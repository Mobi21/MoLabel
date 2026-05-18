import { useState } from 'react'
import {
  Filter,
  SlidersHorizontal,
  Eye,
  Download,
  Plus,
  Clock,
  Hash,
  X,
  Crosshair,
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
import { Separator } from '@/components/ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { mockDatasets } from '@/mocks/data'
import { formatNumber, relativeTime } from '@/lib/format'

// ── Available tags for the multi-select ──────────────────────────────────────

const availableTags = [
  'urban',
  'highway',
  'nighttime',
  'weather',
  'pedestrian',
  'safety-critical',
  'edge-case',
  'construction',
  'priority',
  'verified',
] as const

// ── Existing subsets data ────────────────────────────────────────────────────

const existingSubsets = [
  {
    id: 'sub-001',
    name: 'High-Confidence Vehicle Detection',
    description:
      'Vehicle detection labels with confidence above 0.85 across all urban datasets',
    recordCount: 18_200,
    filterCount: 3,
    filters: [
      'confidence > 0.85',
      'task = vehicle-detection',
      'status = reviewed',
    ],
    createdAt: '2026-03-24T10:00:00Z',
  },
  {
    id: 'sub-002',
    name: 'Disagreement Cases',
    description:
      'Records where reviewers disagree on the correct label assignment',
    recordCount: 186,
    filterCount: 1,
    filters: ['flag = disagreement'],
    createdAt: '2026-03-25T14:00:00Z',
  },
  {
    id: 'sub-003',
    name: 'Export Candidates',
    description:
      'All records that have passed quality checks and are ready for export',
    recordCount: 38_920,
    filterCount: 1,
    filters: ['status = export-ready'],
    createdAt: '2026-03-23T08:00:00Z',
  },
] as const

// ── Challenge sets data ──────────────────────────────────────────────────────

const challengeSets = [
  {
    id: 'cs-001',
    name: 'Nighttime Pedestrian Edge Cases',
    description: 'Used for model calibration and performance benchmarking',
    recordCount: 45,
    purpose: 'calibration',
    status: 'archived' as const,
  },
  {
    id: 'cs-002',
    name: 'Construction Zone Ambiguities',
    description:
      'Ambiguous construction signage and barrier cases under active review',
    recordCount: 28,
    purpose: 'review',
    status: 'active' as const,
  },
] as const

// ── Section 1: Subset Builder ────────────────────────────────────────────────

function SubsetBuilder() {
  const [subsetName, setSubsetName] = useState(
    'Edge Cases \u2014 Low Confidence',
  )
  const [sourceDataset, setSourceDataset] = useState('')
  const [confidenceRange, setConfidenceRange] = useState(
    [0, 0.6] as [number, number],
  )
  const [labelStatuses, setLabelStatuses] = useState({
    labeled: true,
    reviewed: false,
    exportReady: false,
  })
  const [selectedTags, setSelectedTags] = useState(['edge-case'])
  const [recordFlags, setRecordFlags] = useState({
    disagreement: true,
    drift: false,
    missingLabels: false,
  })

  function toggleTag(tag: string) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">Subset Builder</CardTitle>
        </div>
        <CardDescription>
          Create a filtered data subset for targeted labeling or export.
          Configure the filters below to narrow down records by confidence,
          status, tags, and flags.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Name */}
        <div className="space-y-2">
          <Label htmlFor="subset-name" className="text-xs">
            Subset Name
          </Label>
          <Input
            id="subset-name"
            value={subsetName}
            onChange={(e) => {
              setSubsetName(e.target.value)
            }}
            placeholder="Enter subset name..."
          />
        </div>

        {/* Source Dataset */}
        <div className="space-y-2">
          <Label className="text-xs">Source Dataset</Label>
          <Select value={sourceDataset} onValueChange={setSourceDataset}>
            <SelectTrigger>
              <SelectValue placeholder="Select a dataset..." />
            </SelectTrigger>
            <SelectContent>
              {mockDatasets.map((ds) => (
                <SelectItem key={ds.id} value={ds.id}>
                  {ds.name} ({formatNumber(ds.recordCount)} records)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Separator />

        {/* Filters */}
        <div className="space-y-4">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Filters
          </p>

          {/* Confidence Range */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-xs">Confidence Range</Label>
                <p className="text-[11px] text-muted-foreground">
                  Filter records by their predicted confidence score
                </p>
              </div>
              <span className="text-xs font-medium tabular-nums text-muted-foreground">
                {confidenceRange[0].toFixed(1)} &mdash;{' '}
                {confidenceRange[1].toFixed(1)}
              </span>
            </div>
            <div className="space-y-2">
              <div className="relative h-3 w-full rounded-full bg-primary/20">
                <div
                  className="absolute h-full rounded-full bg-primary"
                  style={{
                    left: `${String(confidenceRange[0] * 100)}%`,
                    right: `${String(100 - confidenceRange[1] * 100)}%`,
                  }}
                />
              </div>
              <div className="flex items-center gap-3">
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-[10px] text-muted-foreground">Min</span>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.1}
                    value={confidenceRange[0]}
                    onChange={(e) => {
                      setConfidenceRange([
                        Number(e.target.value),
                        confidenceRange[1],
                      ])
                    }}
                    className="h-7 w-20 text-xs tabular-nums"
                  />
                </div>
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-[10px] text-muted-foreground">Max</span>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.1}
                    value={confidenceRange[1]}
                    onChange={(e) => {
                      setConfidenceRange([
                        confidenceRange[0],
                        Number(e.target.value),
                      ])
                    }}
                    className="h-7 w-20 text-xs tabular-nums"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Label Status */}
          <div className="space-y-2.5">
            <Label className="text-xs">Label Status</Label>
            <p className="text-[11px] text-muted-foreground">
              Include records with these statuses
            </p>
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="status-labeled"
                  checked={labelStatuses.labeled}
                  onCheckedChange={(checked) => {
                    setLabelStatuses((s) => ({
                      ...s,
                      labeled: checked === true,
                    }))
                  }}
                />
                <label htmlFor="status-labeled" className="text-xs">
                  Labeled
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="status-reviewed"
                  checked={labelStatuses.reviewed}
                  onCheckedChange={(checked) => {
                    setLabelStatuses((s) => ({
                      ...s,
                      reviewed: checked === true,
                    }))
                  }}
                />
                <label htmlFor="status-reviewed" className="text-xs">
                  Reviewed
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="status-export-ready"
                  checked={labelStatuses.exportReady}
                  onCheckedChange={(checked) => {
                    setLabelStatuses((s) => ({
                      ...s,
                      exportReady: checked === true,
                    }))
                  }}
                />
                <label htmlFor="status-export-ready" className="text-xs">
                  Export-ready
                </label>
              </div>
            </div>
          </div>

          {/* Tags Multi-select */}
          <div className="space-y-2.5">
            <Label className="text-xs">Tags</Label>
            <p className="text-[11px] text-muted-foreground">
              Filter by record tags (click to toggle)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {availableTags.map((tag) => {
                const isSelected = selectedTags.includes(tag)
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => {
                      toggleTag(tag)
                    }}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
                      isSelected
                        ? 'border-primary/30 bg-primary/10 text-primary'
                        : 'border-border bg-muted/50 text-muted-foreground hover:bg-muted'
                    }`}
                  >
                    {tag}
                    {isSelected && <X className="h-3 w-3" />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Record Flags */}
          <div className="space-y-2.5">
            <Label className="text-xs">Record Flags</Label>
            <p className="text-[11px] text-muted-foreground">
              Include records with specific quality flags
            </p>
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="flag-disagreement"
                  checked={recordFlags.disagreement}
                  onCheckedChange={(checked) => {
                    setRecordFlags((f) => ({
                      ...f,
                      disagreement: checked === true,
                    }))
                  }}
                />
                <label htmlFor="flag-disagreement" className="text-xs">
                  Disagreement
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="flag-drift"
                  checked={recordFlags.drift}
                  onCheckedChange={(checked) => {
                    setRecordFlags((f) => ({ ...f, drift: checked === true }))
                  }}
                />
                <label htmlFor="flag-drift" className="text-xs">
                  Drift
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="flag-missing"
                  checked={recordFlags.missingLabels}
                  onCheckedChange={(checked) => {
                    setRecordFlags((f) => ({
                      ...f,
                      missingLabels: checked === true,
                    }))
                  }}
                />
                <label htmlFor="flag-missing" className="text-xs">
                  Missing Labels
                </label>
              </div>
            </div>
          </div>
        </div>

        <Separator />

        {/* Preview */}
        <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2.5">
          <div className="flex items-center gap-2 text-sm">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Estimated:</span>
            <span className="font-semibold">1,240 records</span>
            <span className="text-muted-foreground">matching filters</span>
          </div>
        </div>

        <Button className="w-full gap-2">
          <Plus className="h-4 w-4" />
          Create Subset
        </Button>
      </CardContent>
    </Card>
  )
}

// ── Section 2: Existing Subsets ──────────────────────────────────────────────

function SubsetCard({ subset }: { subset: (typeof existingSubsets)[number] }) {
  return (
    <Card className="group transition-all hover:border-primary/40 hover:shadow-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate text-sm">{subset.name}</CardTitle>
            <CardDescription className="mt-1 line-clamp-1 text-xs">
              {subset.description}
            </CardDescription>
          </div>
          <Badge variant="secondary" className="shrink-0 tabular-nums">
            {formatNumber(subset.recordCount)} records
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Filter badges */}
        <div className="flex flex-wrap gap-1.5">
          {subset.filters.map((filter) => (
            <Badge
              key={filter}
              variant="outline"
              className="border-blue-500/20 bg-blue-500/10 text-[10px] text-blue-600"
            >
              <Filter className="mr-1 h-2.5 w-2.5" />
              {filter}
            </Badge>
          ))}
        </div>

        <Separator />

        {/* Footer */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="h-3 w-3" />
            {relativeTime(subset.createdAt)}
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
            >
              <Eye className="h-3 w-3" />
              View
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
            >
              <Download className="h-3 w-3" />
              Export
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ExistingSubsets() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Existing Subsets</h2>
          <p className="text-xs text-muted-foreground">
            {existingSubsets.length} saved subsets
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {existingSubsets.map((subset) => (
          <SubsetCard key={subset.id} subset={subset} />
        ))}
      </div>
    </div>
  )
}

// ── Section 3: Challenge Sets ────────────────────────────────────────────────

function ChallengeSetCard({
  challengeSet,
}: {
  challengeSet: (typeof challengeSets)[number]
}) {
  const statusColor =
    challengeSet.status === 'active'
      ? {
          dot: 'bg-emerald-500',
          bg: 'bg-emerald-500/10',
          text: 'text-emerald-600',
          border: 'border-emerald-500/20',
        }
      : {
          dot: 'bg-zinc-400',
          bg: 'bg-zinc-500/10',
          text: 'text-zinc-600',
          border: 'border-zinc-500/20',
        }

  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/30">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{challengeSet.name}</p>
          <Badge
            variant="outline"
            className={`shrink-0 gap-1.5 ${statusColor.bg} ${statusColor.text} ${statusColor.border}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${statusColor.dot}`} />
            {challengeSet.status === 'active' ? 'Active Review' : 'Archived'}
          </Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {challengeSet.description}
        </p>
      </div>
      <div className="ml-4 shrink-0">
        <Badge variant="secondary" className="tabular-nums">
          {challengeSet.recordCount} records
        </Badge>
      </div>
    </div>
  )
}

function ChallengeSets() {
  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center gap-2">
          <Crosshair className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">Challenge Sets</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Create challenge sets from edge cases, disagreements, and
          low-confidence items
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {challengeSets.map((cs) => (
          <ChallengeSetCard key={cs.id} challengeSet={cs} />
        ))}

        <Separator />

        <Button variant="outline" className="w-full gap-2">
          <Plus className="h-4 w-4" />
          Create Challenge Set
        </Button>
      </CardContent>
    </Card>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function CurationPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Filter className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Curation</h1>
            <p className="text-sm text-muted-foreground">
              Curate and filter datasets for targeted labeling and model
              training.
            </p>
          </div>
        </div>
      </div>

      {/* Two-column layout: builder + challenge sets on the side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="flex flex-col gap-6 lg:col-span-3">
          <SubsetBuilder />
        </div>
        <div className="flex flex-col gap-6 lg:col-span-2">
          <ChallengeSets />
        </div>
      </div>

      {/* Existing Subsets */}
      <ExistingSubsets />
    </div>
  )
}
