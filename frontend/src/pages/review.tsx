import { useState, useEffect, useCallback } from 'react'
import {
  Eye,
  Clock,
  ArrowLeft,
  CheckCircle,
  Pencil,
  X,
  SkipForward,
  AlertTriangle,
  Shield,
  User,
  ChevronLeft,
  ChevronRight,
  Info,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { mockReviewQueue, mockReviewers, mockDashboardStats } from '@/mocks/data'
import type { ReviewItem } from '@/mocks/data'
import { formatNumber, relativeTime } from '@/lib/format'

// ── Constants ────────────────────────────────────────────────────────────────

const CURRENT_USER = 'Sarah Chen'

const MOCK_RECORD_PAYLOAD = {
  image_path: '/data/urban-scenes/batch-047/frame_4821.jpg',
  capture_timestamp: '2026-03-25T14:32:18Z',
  camera_id: 'cam-front-center',
  resolution: '1920x1080',
  location: { lat: 37.7749, lng: -122.4194 },
  weather: 'partly_cloudy',
  time_of_day: 'afternoon',
  scene_type: 'intersection',
  num_objects_detected: 8,
  metadata: {
    batch_id: 'batch-047',
    pipeline_version: '2.1.0',
    preprocessing: 'standard_normalize',
  },
}

const MOCK_AI_LABELS = {
  vehicle_type: 'truck',
  vehicle_count: 3,
  is_occluded: true,
  confidence_note: 'Partial occlusion on rear vehicle, high confidence on lead truck',
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function priorityColor(priority: ReviewItem['priority']): {
  border: string
  badge: string
  text: string
  label: string
} {
  switch (priority) {
    case 'high':
      return {
        border: 'border-l-red-500',
        badge: 'bg-red-500/10 text-red-600 border-red-500/20',
        text: 'text-red-600',
        label: 'High',
      }
    case 'medium':
      return {
        border: 'border-l-amber-500',
        badge: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
        text: 'text-amber-600',
        label: 'Medium',
      }
    case 'low':
      return {
        border: 'border-l-gray-400',
        badge: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
        text: 'text-gray-500',
        label: 'Low',
      }
  }
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0] ?? '')
    .join('')
    .toUpperCase()
}

function getAvatarColor(name: string): string {
  const reviewer = mockReviewers.find((r) => r.displayName === name)
  return reviewer?.avatarColor ?? '#94a3b8'
}

// ── Queue View ───────────────────────────────────────────────────────────────

function QueueView({
  onReview,
}: {
  onReview: (item: ReviewItem) => void
}) {
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [datasetFilter, setDatasetFilter] = useState<string>('all')
  const [taskTypeFilter, setTaskTypeFilter] = useState<string>('all')
  const [myItemsOnly, setMyItemsOnly] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)

  const datasets = [...new Set(mockReviewQueue.map((item) => item.datasetName))]
  const taskTypes = [...new Set(mockReviewQueue.map((item) => item.taskType))]

  const filtered = mockReviewQueue.filter((item) => {
    if (priorityFilter !== 'all' && item.priority !== priorityFilter) return false
    if (datasetFilter !== 'all' && item.datasetName !== datasetFilter) return false
    if (taskTypeFilter !== 'all' && item.taskType !== taskTypeFilter) return false
    if (myItemsOnly && item.assignee !== CURRENT_USER) return false
    return true
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / 5))
  const pageItems = filtered.slice((currentPage - 1) * 5, currentPage * 5)

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Eye className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Review Queue</h1>
          <p className="text-sm text-muted-foreground">
            Human review queue for verifying and correcting AI-generated labels.
          </p>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-6 rounded-lg border border-border bg-muted/30 px-5 py-3">
        <div className="flex items-center gap-2 text-sm">
          <div className="h-2 w-2 rounded-full bg-amber-500" />
          <span className="font-medium">{formatNumber(mockDashboardStats.pendingReview)}</span>
          <span className="text-muted-foreground">pending</span>
        </div>
        <Separator orientation="vertical" className="h-4" />
        <div className="flex items-center gap-2 text-sm">
          <User className="h-3.5 w-3.5 text-primary" />
          <span className="font-medium">5</span>
          <span className="text-muted-foreground">claimed by you</span>
        </div>
        <Separator orientation="vertical" className="h-4" />
        <div className="flex items-center gap-2 text-sm">
          <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
          <span className="font-medium">186</span>
          <span className="text-muted-foreground">disagreements</span>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={priorityFilter} onValueChange={setPriorityFilter}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Priorities</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        <Select value={datasetFilter} onValueChange={setDatasetFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Dataset" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Datasets</SelectItem>
            {datasets.map((ds) => (
              <SelectItem key={ds} value={ds}>
                {ds}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={taskTypeFilter} onValueChange={setTaskTypeFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Task Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Task Types</SelectItem>
            {taskTypes.map((tt) => (
              <SelectItem key={tt} value={tt}>
                {tt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="my-items" className="text-sm text-muted-foreground">
            My Items
          </Label>
          <Switch
            id="my-items"
            checked={myItemsOnly}
            onCheckedChange={setMyItemsOnly}
          />
        </div>
      </div>

      {/* Queue list */}
      <div className="flex flex-col gap-3">
        {pageItems.length === 0 && (
          <div className="flex items-center justify-center rounded-lg border border-dashed border-border p-12">
            <p className="text-sm text-muted-foreground">
              No items match your current filters.
            </p>
          </div>
        )}
        {pageItems.map((item) => {
          const pc = priorityColor(item.priority)
          const isAssignedToMe = item.assignee === CURRENT_USER
          const isUnassigned = item.assignee === null

          return (
            <Card
              key={item.id}
              className={`border border-l-4 bg-card ${pc.border} transition-colors hover:bg-muted/30`}
            >
              <CardContent className="flex items-center gap-4 py-5 px-4">
                {/* Priority + Record ID */}
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-semibold">{item.recordId}</code>
                    <Badge variant="outline" className={pc.badge}>
                      {pc.label}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{item.datasetName}</span>
                    <span className="text-border">|</span>
                    <span>{item.taskType}</span>
                  </div>
                </div>

                {/* Assignee */}
                <div className="flex items-center gap-2">
                  {item.assignee !== null ? (
                    <>
                      <Avatar className="h-6 w-6">
                        <AvatarFallback
                          className="text-[10px] text-white"
                          style={{ backgroundColor: getAvatarColor(item.assignee) }}
                        >
                          {getInitials(item.assignee)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-sm">{item.assignee}</span>
                    </>
                  ) : (
                    <span className="text-sm text-muted-foreground">Unassigned</span>
                  )}
                </div>

                {/* Time in queue */}
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  <span>{relativeTime(item.createdAt)}</span>
                </div>

                {/* Action button */}
                {isAssignedToMe ? (
                  <Button size="sm" onClick={() => onReview(item)}>
                    Review
                  </Button>
                ) : isUnassigned ? (
                  <Button size="sm" variant="outline" onClick={() => onReview(item)}>
                    Claim
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" disabled>
                    Assigned
                  </Button>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing {pageItems.length} of {filtered.length} items
        </p>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="px-3 text-sm text-muted-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            disabled={currentPage >= totalPages}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Review Mode ──────────────────────────────────────────────────────────────

function ReviewMode({
  item,
  onBack,
}: {
  item: ReviewItem
  onBack: () => void
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [blindMode, setBlindMode] = useState(true)

  // Form state
  const [vehicleType, setVehicleType] = useState<string>('')
  const [vehicleCount, setVehicleCount] = useState<string>('')
  const [isOccluded, setIsOccluded] = useState(false)
  const [confidenceNote, setConfidenceNote] = useState('')

  // Timer
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedSeconds((s) => s + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const formatTimer = useCallback((seconds: number): string => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }, [])

  const handleRevealAI = () => {
    setBlindMode(false)
  }

  const handleAction = (action: string) => {
    // TODO: submit via API
    void action
    onBack()
  }

  const pc = priorityColor(item.priority)

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-4 border-b border-border bg-background px-4 py-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back to Queue
        </Button>
        <Separator orientation="vertical" className="h-5" />
        <div className="flex items-center gap-2">
          <code className="text-sm font-semibold">{item.recordId}</code>
          <Badge variant="outline" className={pc.badge}>
            {pc.label}
          </Badge>
        </div>
        <span className="text-sm text-muted-foreground">{item.datasetName}</span>
        <div className="ml-auto flex items-center gap-4">
          <span className="text-sm text-muted-foreground">3 of 145</span>
          <div className="flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1">
            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono text-sm">{formatTimer(elapsedSeconds)}</span>
          </div>
        </div>
      </div>

      {/* Main content: two panels */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel: Record Data (60%) */}
        <div className="flex w-[60%] flex-col border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Record Data</h2>
            <Badge variant="secondary" className="ml-auto text-xs">
              {item.taskType}
            </Badge>
          </div>
          <ScrollArea className="flex-1">
            <div className="space-y-4 p-5">
              {/* Source data fields */}
              <div>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Source Fields
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(MOCK_RECORD_PAYLOAD).map(([key, value]) => {
                    if (typeof value === 'object' && value !== null) return null
                    return (
                      <div
                        key={key}
                        className="flex flex-col gap-0.5 rounded-md bg-muted/40 px-3 py-2"
                      >
                        <span className="text-xs text-muted-foreground">{key}</span>
                        <span className="font-mono text-sm">{String(value)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              <Separator />

              {/* Nested objects */}
              <div>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Location
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-0.5 rounded-md bg-muted/40 px-3 py-2">
                    <span className="text-xs text-muted-foreground">lat</span>
                    <span className="font-mono text-sm">{MOCK_RECORD_PAYLOAD.location.lat}</span>
                  </div>
                  <div className="flex flex-col gap-0.5 rounded-md bg-muted/40 px-3 py-2">
                    <span className="text-xs text-muted-foreground">lng</span>
                    <span className="font-mono text-sm">{MOCK_RECORD_PAYLOAD.location.lng}</span>
                  </div>
                </div>
              </div>

              <Separator />

              <div>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Metadata
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(MOCK_RECORD_PAYLOAD.metadata).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex flex-col gap-0.5 rounded-md bg-muted/40 px-3 py-2"
                    >
                      <span className="text-xs text-muted-foreground">{key}</span>
                      <span className="font-mono text-sm">{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Large content area — image placeholder */}
              <div>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Record Payload
                </h3>
                <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border bg-muted/20">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Eye className="h-8 w-8" />
                    <span className="text-sm">Image preview area</span>
                    <span className="text-xs">{MOCK_RECORD_PAYLOAD.image_path}</span>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>

        {/* Right panel: Review Form (40%) */}
        <div className="flex w-[40%] flex-col">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3">
            <Pencil className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Review Form</h2>
          </div>
          <ScrollArea className="flex-1">
            <div className="space-y-5 p-5">
              {/* Blind mode banner */}
              {blindMode && (
                <div className="flex items-start gap-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-4">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-blue-600">
                      AI labels hidden
                    </p>
                    <p className="mt-0.5 text-xs text-blue-500/80">
                      Submit your labels first, then reveal to compare.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRevealAI}
                    className="shrink-0 border-blue-500/30 text-blue-600 hover:bg-blue-500/10"
                  >
                    Reveal AI
                  </Button>
                </div>
              )}

              {/* Label fields */}
              <div className="space-y-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Label Fields
                </h3>

                {/* vehicle_type */}
                <div className="space-y-2">
                  <Label htmlFor="vehicle-type">
                    vehicle_type <span className="text-red-500">*</span>
                  </Label>
                  <div className="flex gap-2">
                    <Select value={vehicleType} onValueChange={setVehicleType}>
                      <SelectTrigger id="vehicle-type" className="flex-1">
                        <SelectValue placeholder="Select type..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="car">car</SelectItem>
                        <SelectItem value="truck">truck</SelectItem>
                        <SelectItem value="bus">bus</SelectItem>
                        <SelectItem value="motorcycle">motorcycle</SelectItem>
                        <SelectItem value="bicycle">bicycle</SelectItem>
                        <SelectItem value="emergency">emergency</SelectItem>
                      </SelectContent>
                    </Select>
                    {!blindMode && (
                      <DiffIndicator
                        humanValue={vehicleType}
                        aiValue={MOCK_AI_LABELS.vehicle_type}
                      />
                    )}
                  </div>
                </div>

                {/* vehicle_count */}
                <div className="space-y-2">
                  <Label htmlFor="vehicle-count">
                    vehicle_count <span className="text-red-500">*</span>
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id="vehicle-count"
                      type="number"
                      min={0}
                      max={50}
                      placeholder="0"
                      value={vehicleCount}
                      onChange={(e) => setVehicleCount(e.target.value)}
                      className="flex-1"
                    />
                    {!blindMode && (
                      <DiffIndicator
                        humanValue={vehicleCount}
                        aiValue={String(MOCK_AI_LABELS.vehicle_count)}
                      />
                    )}
                  </div>
                </div>

                {/* is_occluded */}
                <div className="space-y-2">
                  <Label>is_occluded</Label>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="is-occluded"
                        checked={isOccluded}
                        onCheckedChange={(checked) =>
                          setIsOccluded(checked === true)
                        }
                      />
                      <Label htmlFor="is-occluded" className="text-sm font-normal">
                        Object is occluded
                      </Label>
                    </div>
                    {!blindMode && (
                      <DiffIndicator
                        humanValue={String(isOccluded)}
                        aiValue={String(MOCK_AI_LABELS.is_occluded)}
                      />
                    )}
                  </div>
                </div>

                {/* confidence_note */}
                <div className="space-y-2">
                  <Label htmlFor="confidence-note">confidence_note</Label>
                  <div className="flex gap-2">
                    <Textarea
                      id="confidence-note"
                      placeholder="Optional note about labeling confidence..."
                      value={confidenceNote}
                      onChange={(e) => setConfidenceNote(e.target.value)}
                      className="min-h-[80px] flex-1"
                    />
                  </div>
                  {!blindMode && MOCK_AI_LABELS.confidence_note && (
                    <div className="rounded-md bg-muted/50 px-3 py-2">
                      <span className="text-xs font-medium text-muted-foreground">
                        AI note:
                      </span>
                      <p className="mt-0.5 text-xs">{MOCK_AI_LABELS.confidence_note}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* AI labels comparison panel (after reveal) */}
              {!blindMode && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Agent Labels (Revealed)
                    </h3>
                    <div className="rounded-lg border border-border bg-muted/20 p-4">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs text-muted-foreground">vehicle_type</span>
                          <span className="font-mono text-sm">{MOCK_AI_LABELS.vehicle_type}</span>
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs text-muted-foreground">vehicle_count</span>
                          <span className="font-mono text-sm">{MOCK_AI_LABELS.vehicle_count}</span>
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs text-muted-foreground">is_occluded</span>
                          <span className="font-mono text-sm">
                            {String(MOCK_AI_LABELS.is_occluded)}
                          </span>
                        </div>
                        <div className="col-span-2 flex flex-col gap-0.5">
                          <span className="text-xs text-muted-foreground">confidence_note</span>
                          <span className="text-sm">{MOCK_AI_LABELS.confidence_note}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </ScrollArea>

          {/* Action buttons — pinned to bottom */}
          <div className="border-t border-border p-4">
            <div className="grid grid-cols-4 gap-2">
              <Button
                className="bg-emerald-600 text-white hover:bg-emerald-700"
                onClick={() => handleAction('accept')}
              >
                <CheckCircle className="h-4 w-4" />
                Accept
              </Button>
              <Button
                variant="default"
                onClick={() => handleAction('correct')}
              >
                <Pencil className="h-4 w-4" />
                Correct
              </Button>
              <Button
                variant="outline"
                className="border-red-500/30 text-red-600 hover:bg-red-500/10"
                onClick={() => handleAction('reject')}
              >
                <X className="h-4 w-4" />
                Reject
              </Button>
              <Button
                variant="ghost"
                onClick={() => handleAction('skip')}
              >
                <SkipForward className="h-4 w-4" />
                Skip
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Diff Indicator ───────────────────────────────────────────────────────────

function DiffIndicator({
  humanValue,
  aiValue,
}: {
  humanValue: string
  aiValue: string
}) {
  if (humanValue === '') {
    return null
  }
  if (humanValue === aiValue) {
    return (
      <div className="flex h-9 items-center rounded-md bg-emerald-500/10 px-2">
        <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
      </div>
    )
  }
  return (
    <div className="flex h-9 items-center gap-1 rounded-md bg-amber-500/10 px-2">
      <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
      <span className="font-mono text-xs text-amber-600">{aiValue}</span>
    </div>
  )
}

// ── Page Export ───────────────────────────────────────────────────────────────

export function ReviewPage() {
  const [activeItem, setActiveItem] = useState<ReviewItem | null>(null)

  if (activeItem !== null) {
    return (
      <ReviewMode
        item={activeItem}
        onBack={() => setActiveItem(null)}
      />
    )
  }

  return <QueueView onReview={setActiveItem} />
}
