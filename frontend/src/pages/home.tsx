import {
  House,
  Database,
  Tag,
  CheckCircle,
  Package,
  Eye,
  Bot,
  Shield,
  ArrowRight,
  AlertTriangle,
  Clock,
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
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  mockDashboardStats,
  mockWorkflows,
  mockActivity,
  mockAgentRuns,
  mockExports,
} from '@/mocks/data'
import type { ActivityItem } from '@/mocks/data'
import { formatNumber, relativeTime } from '@/lib/format'

// ── Helpers ───────────────────────────────────────────────────────────────────

const activityDotColor: Record<ActivityItem['type'], string> = {
  agent_run: 'bg-blue-500',
  review: 'bg-emerald-500',
  export: 'bg-purple-500',
  workflow: 'bg-orange-500',
  system: 'bg-zinc-400',
}

// ── Workflow Steps ────────────────────────────────────────────────────────────

const pipelineSteps = [
  'Ingest',
  'Pre-label',
  'Review',
  'Adjudicate',
  'Export',
] as const

const currentStepIndex = 2 // Review

// ── Stat Cards ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: number
  percentage: number | undefined
  icon: React.ReactNode
}

function StatCard({ label, value, percentage, icon }: StatCardProps) {
  return (
    <Card className="group border-border/50 bg-card transition-colors hover:border-primary/30">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardDescription className="text-xs font-medium uppercase tracking-wider">
          {label}
        </CardDescription>
        <div className="text-muted-foreground/60">{icon}</div>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold tracking-tight">
          {formatNumber(value)}
        </div>
        {percentage !== undefined && (
          <div className="mt-3 space-y-1.5">
            <Progress value={percentage} className="h-1.5 bg-muted" />
            <p className="text-xs text-muted-foreground">
              {percentage.toFixed(1)}% of total
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Step Indicator ────────────────────────────────────────────────────────────

function WorkflowStepIndicator() {
  return (
    <div className="flex items-center gap-1">
      {pipelineSteps.map((step, i) => {
        const isComplete = i < currentStepIndex
        const isCurrent = i === currentStepIndex
        return (
          <div key={step} className="flex items-center gap-1">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
                  isCurrent
                    ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/25'
                    : isComplete
                      ? 'bg-emerald-500/15 text-emerald-600'
                      : 'bg-muted text-muted-foreground'
                }`}
              >
                {isComplete ? <CheckCircle className="h-4 w-4" /> : i + 1}
              </div>
              <span
                className={`text-[11px] font-medium ${
                  isCurrent
                    ? 'text-foreground'
                    : isComplete
                      ? 'text-emerald-600'
                      : 'text-muted-foreground'
                }`}
              >
                {step}
              </span>
            </div>
            {i < pipelineSteps.length - 1 && (
              <div
                className={`mb-5 h-[2px] w-8 rounded-full ${
                  isComplete ? 'bg-emerald-500/30' : 'bg-border'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Activity Row ──────────────────────────────────────────────────────────────

function ActivityRow({ item }: { item: ActivityItem }) {
  return (
    <div className="flex items-start gap-3 py-3">
      <div className="mt-1.5 flex-shrink-0">
        <div
          className={`h-2 w-2 rounded-full ${activityDotColor[item.type]}`}
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug text-foreground">{item.message}</p>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span>{item.actor}</span>
          <span className="text-border">|</span>
          <span>{relativeTime(item.timestamp)}</span>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function HomePage() {
  const stats = mockDashboardStats
  const activeWorkflow = mockWorkflows[0]
  const runningAgents = mockAgentRuns.filter((a) => a.status === 'running')
  const exportInProgress = mockExports.filter((e) => e.status === 'in-progress').length
  const completionPct = Math.round(
    ((currentStepIndex + 0.6) / pipelineSteps.length) * 100,
  )

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <House className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
              <Separator orientation="vertical" className="h-5" />
              <span className="text-sm font-medium text-muted-foreground">
                Autonomous Driving v3
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              Your workspace overview and quick actions.
            </p>
          </div>
        </div>
        <Badge
          variant="secondary"
          className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Pipeline Active
        </Badge>
      </div>

      {/* ── Stat Cards ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Records"
          value={stats.totalRecords}
          percentage={undefined}
          icon={<Database className="h-4 w-4" />}
        />
        <StatCard
          label="Labeled"
          value={stats.totalLabeled}
          percentage={69.5}
          icon={<Tag className="h-4 w-4" />}
        />
        <StatCard
          label="Reviewed"
          value={stats.totalReviewed}
          percentage={51.4}
          icon={<CheckCircle className="h-4 w-4" />}
        />
        <StatCard
          label="Export Ready"
          value={stats.exportReady}
          percentage={41.9}
          icon={<Package className="h-4 w-4" />}
        />
      </div>

      {/* ── Two-Column Body ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* ── Left Column (3/5 = 60%) ──────────────────────────────────── */}
        <div className="flex flex-col gap-6 lg:col-span-3">
          {/* Active Workflow */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <CardTitle className="text-base">Active Workflow</CardTitle>
                  <Badge variant="outline" className="text-xs font-normal">
                    {activeWorkflow?.status}
                  </Badge>
                </div>
                <span className="text-xs text-muted-foreground">
                  {completionPct}% complete
                </span>
              </div>
              <CardDescription>{activeWorkflow?.name}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Progress value={completionPct} className="h-1.5 bg-muted" />
              <div className="flex justify-center pt-1">
                <WorkflowStepIndicator />
              </div>
              <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" />
                  Current step:{' '}
                  <span className="font-medium text-foreground">Review</span>
                </span>
                <span>
                  Last run {relativeTime(activeWorkflow?.lastRun ?? '')}
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Recent Activity */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Recent Activity</CardTitle>
                <Button variant="ghost" size="sm" className="h-7 text-xs">
                  View all
                  <ArrowRight className="ml-1 h-3 w-3" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <ScrollArea className="h-[380px] pr-3">
                <div className="divide-y divide-border">
                  {mockActivity.map((item) => (
                    <ActivityRow key={item.id} item={item} />
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* ── Right Column (2/5 = 40%) ─────────────────────────────────── */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          {/* Quick Actions */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button className="w-full justify-start gap-2.5" size="lg">
                <Eye className="h-4 w-4" />
                Start Review
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-start gap-2.5"
              >
                <Bot className="h-4 w-4" />
                Run Agent
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start gap-2.5"
              >
                <Package className="h-4 w-4" />
                Export Data
              </Button>
              <Button variant="ghost" className="w-full justify-start gap-2.5">
                <Shield className="h-4 w-4" />
                View Quality
              </Button>
            </CardContent>
          </Card>

          {/* Pending Queues */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Pending Queues</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500/10">
                    <Eye className="h-3.5 w-3.5 text-amber-600" />
                  </span>
                  <div className="flex-1">
                    <p className="text-sm font-medium">
                      {formatNumber(stats.pendingReview)} items pending review
                    </p>
                    <Progress
                      value={(stats.pendingReview / stats.totalRecords) * 100}
                      className="mt-1.5 h-1 bg-muted"
                    />
                  </div>
                </div>

                <Separator />

                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-red-500/10">
                    <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                  </span>
                  <p className="text-sm">
                    <span className="font-medium">186</span>{' '}
                    <span className="text-muted-foreground">
                      disagreements to adjudicate
                    </span>
                  </p>
                </div>

                <Separator />

                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-500/10">
                    <Bot className="h-3.5 w-3.5 text-blue-500" />
                  </span>
                  <p className="text-sm">
                    <span className="font-medium">{runningAgents.length}</span>{' '}
                    <span className="text-muted-foreground">
                      {runningAgents.length === 1
                        ? 'agent currently running'
                        : 'agents currently running'}
                    </span>
                  </p>
                </div>

                <Separator />

                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-purple-500/10">
                    <Zap className="h-3.5 w-3.5 text-purple-500" />
                  </span>
                  <p className="text-sm">
                    <span className="font-medium">{exportInProgress}</span>{' '}
                    <span className="text-muted-foreground">
                      export in progress
                    </span>
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Blockers */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Blockers</CardTitle>
                <Badge variant="destructive" className="h-5 px-1.5 text-[10px]">
                  3
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-red-500" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      Construction Zones: only 25% labeled
                    </p>
                    <p className="mt-0.5 text-xs text-red-600/80">Critical</p>
                  </div>
                </div>
              </div>

              <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      Highway Nighttime: label drift detected +2.3%
                    </p>
                    <p className="mt-0.5 text-xs text-amber-600/80">Warning</p>
                  </div>
                </div>
              </div>

              <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      GPT-4o rate limit hit on batch run
                    </p>
                    <p className="mt-0.5 text-xs text-amber-600/80">Warning</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
