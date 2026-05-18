import {
  Activity,
  CheckCircle2,
  FileDiff,
  Fingerprint,
  GitPullRequestArrow,
  HeartPulse,
  ListChecks,
  Network,
  PackageCheck,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const diffQueue = [
  {
    id: 'prop-1482',
    run: 'run-minimax-27-hs',
    target: 'workbench/workflows/psychology_survey_codebook.yaml',
    status: 'proposed',
    risk: 'hash verified',
  },
  {
    id: 'prop-1483',
    run: 'run-minimax-27-hs',
    target: 'workbench/prompts/survey-theme-coding.yaml',
    status: 'conflicted',
    risk: 'stale source hash',
  },
] as const

const auditEvents = [
  {
    event: 'artifact_proposed',
    actor: 'MiniMax operator',
    object: 'prop-1482',
    time: '2 min ago',
  },
  {
    event: 'release_certification_started',
    actor: 'Sarah Chen',
    object: 'release-2026-05-16',
    time: '8 min ago',
  },
  {
    event: 'provider_health_checked',
    actor: 'System',
    object: 'MiniMax-M2.7-highspeed',
    time: '11 min ago',
  },
] as const

const releaseGates = [
  { label: 'Unit suite', value: 100, status: 'pass' },
  { label: 'Integration suite', value: 100, status: 'pass' },
  { label: 'Grounded benchmarks', value: 100, status: 'pass' },
  { label: 'Operator coverage', value: 38, status: 'needs-expansion' },
  { label: 'Psychology certification', value: 20, status: 'needs-run' },
] as const

const providerHealthChecks: Array<{
  label: string
  value: string
  icon: LucideIcon
}> = [
  {
    label: 'Base URL',
    value: 'https://api.minimax.io/anthropic',
    icon: CheckCircle2,
  },
  { label: 'Auth ref', value: 'ANTHROPIC_API_KEY', icon: ShieldCheck },
  { label: 'Model', value: 'MiniMax-M2.7-highspeed', icon: Network },
]

function statusBadge(status: string) {
  if (status === 'pass' || status === 'proposed' || status === 'hash verified') {
    return (
      <Badge className="border-emerald-500/20 bg-emerald-500/10 text-emerald-600">
        {status}
      </Badge>
    )
  }
  return (
    <Badge className="border-amber-500/20 bg-amber-500/10 text-amber-600">
      {status}
    </Badge>
  )
}

function SemanticDiffPanel() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <FileDiff className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Semantic Diff Review</CardTitle>
        </div>
        <CardDescription>
          Proposed workspace changes grouped by run and canonical target.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {diffQueue.map((item) => (
          <div
            key={item.id}
            className="grid gap-3 rounded-lg border border-border p-3 md:grid-cols-[1fr_auto]"
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">
                  {item.id}
                </span>
                {statusBadge(item.status)}
                {statusBadge(item.risk)}
              </div>
              <p className="truncate text-sm font-medium">{item.target}</p>
              <p className="font-mono text-xs text-muted-foreground">
                {item.run}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline">
                <Fingerprint className="h-3.5 w-3.5" />
                Trace
              </Button>
              <Button size="sm" variant="outline">
                <GitPullRequestArrow className="h-3.5 w-3.5" />
                Decide
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function AuditTimelinePanel() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Audit Timeline</CardTitle>
        </div>
        <CardDescription>
          Agent, release, provider, and artifact events in one ledger.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {auditEvents.map((event) => (
          <div key={`${event.event}-${event.object}`} className="flex gap-3">
            <div className="mt-1 h-2.5 w-2.5 rounded-full bg-primary" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{event.event}</span>
                <span className="text-xs text-muted-foreground">
                  {event.time}
                </span>
              </div>
              <p className="truncate text-sm">{event.object}</p>
              <p className="text-xs text-muted-foreground">{event.actor}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ProviderHealthPanel() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Provider Health</CardTitle>
        </div>
        <CardDescription>
          Reachability, auth reference, and model-valid checks.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        {providerHealthChecks.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-lg border p-3">
            <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
            <p className="break-words font-mono text-xs">{value}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ReleaseCertificationPanel() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <PackageCheck className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm">Release Certification</CardTitle>
        </div>
        <CardDescription>
          Proof-manifest gates before a workspace can be approved.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {releaseGates.map((gate) => (
          <div key={gate.label} className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm">{gate.label}</span>
              {statusBadge(gate.status)}
            </div>
            <Progress value={gate.value} className="h-2" />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export function OperationsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Operations</h1>
          <p className="text-sm text-muted-foreground">
            Audit, diff, provider, and release control room.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <TriangleAlert className="h-3.5 w-3.5" />
            Failures
          </Button>
          <Button size="sm">
            <ListChecks className="h-3.5 w-3.5" />
            Certify
          </Button>
        </div>
      </div>

      <Tabs defaultValue="diffs">
        <TabsList>
          <TabsTrigger value="diffs">Diffs</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="release">Release</TabsTrigger>
        </TabsList>
        <TabsContent value="diffs" className="mt-4">
          <SemanticDiffPanel />
        </TabsContent>
        <TabsContent value="audit" className="mt-4">
          <AuditTimelinePanel />
        </TabsContent>
        <TabsContent value="providers" className="mt-4">
          <ProviderHealthPanel />
        </TabsContent>
        <TabsContent value="release" className="mt-4">
          <ReleaseCertificationPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
