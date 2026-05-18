import { useState } from 'react'
import {
  Settings,
  Sparkles,
  Brain,
  Globe,
  Server,
  Router,
  Plus,
  Pencil,
  Trash2,
  Zap,
  Search,
  Shield,
  FileDown,
  Play,
  UserPlus,
  CheckCircle2,
  Upload,
  ClipboardCheck,
  Clock,
  Moon,
  Sun,
  Save,
  Filter,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { mockReviewers } from '@/mocks/data'

// ── Provider Data ─────────────────────────────────────────────────────────────

interface Provider {
  id: string
  name: string
  description: string
  model: string | null
  apiKey: string | null
  enabled: boolean
  connected: boolean
  icon: typeof Sparkles
  iconColor: string
}

const providers: Provider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT-4o and GPT-4o-mini for pre-labeling and adjudication',
    model: 'gpt-4o',
    apiKey: 'sk-...7x2f',
    enabled: true,
    connected: true,
    icon: Sparkles,
    iconColor: 'text-emerald-500',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description:
      'Claude models for high-accuracy labeling and quality assessment',
    model: 'claude-sonnet-4-20250514',
    apiKey: 'sk-ant-...9k3m',
    enabled: true,
    connected: true,
    icon: Brain,
    iconColor: 'text-orange-500',
  },
  {
    id: 'google',
    name: 'Google AI',
    description: 'Gemini models for multi-modal labeling tasks',
    model: 'gemini-2.5-pro',
    apiKey: 'AIza...x8Qp',
    enabled: true,
    connected: true,
    icon: Globe,
    iconColor: 'text-blue-500',
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Run open-source models locally for offline labeling',
    model: null,
    apiKey: null,
    enabled: false,
    connected: false,
    icon: Server,
    iconColor: 'text-muted-foreground',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'Unified API gateway for 100+ models with automatic fallback',
    model: null,
    apiKey: null,
    enabled: false,
    connected: false,
    icon: Router,
    iconColor: 'text-muted-foreground',
  },
]

// ── Audit Log Data ────────────────────────────────────────────────────────────

interface AuditEvent {
  id: string
  timestamp: string
  action: string
  actionType:
    | 'workspace'
    | 'dataset'
    | 'agent'
    | 'review'
    | 'export'
    | 'settings'
    | 'auth'
    | 'workflow'
  actor: string
  details: string
  resource: string
}

const auditEvents: AuditEvent[] = [
  {
    id: 'aud-001',
    timestamp: '2026-03-26T09:15:00Z',
    action: 'Workspace Created',
    actionType: 'workspace',
    actor: 'Sarah Chen',
    details: 'Created workspace "Autonomous Driving v3"',
    resource: 'ws-001',
  },
  {
    id: 'aud-002',
    timestamp: '2026-03-26T08:42:00Z',
    action: 'Dataset Imported',
    actionType: 'dataset',
    actor: 'Sarah Chen',
    details: 'Imported 24,850 records from COCO JSON',
    resource: 'ds-001',
  },
  {
    id: 'aud-003',
    timestamp: '2026-03-26T08:30:00Z',
    action: 'Agent Run Started',
    actionType: 'agent',
    actor: 'System',
    details: 'Claude Adjudicator started on Urban Scenes batch',
    resource: 'ar-002',
  },
  {
    id: 'aud-004',
    timestamp: '2026-03-26T07:55:00Z',
    action: 'Review Completed',
    actionType: 'review',
    actor: 'Marcus Johnson',
    details: 'Completed 38 reviews with 97.4% agreement',
    resource: 'rq-003',
  },
  {
    id: 'aud-005',
    timestamp: '2026-03-26T06:47:00Z',
    action: 'Agent Run Completed',
    actionType: 'agent',
    actor: 'System',
    details: 'GPT-4o Pre-labeler finished 2,400 records (92.4% accuracy)',
    resource: 'ar-001',
  },
  {
    id: 'aud-006',
    timestamp: '2026-03-25T23:00:00Z',
    action: 'Export Created',
    actionType: 'export',
    actor: 'Sarah Chen',
    details: 'Exported Pedestrian Detection v2.8 as COCO JSON (25,600 records)',
    resource: 'exp-001',
  },
  {
    id: 'aud-007',
    timestamp: '2026-03-25T20:15:00Z',
    action: 'Provider Configured',
    actionType: 'settings',
    actor: 'Sarah Chen',
    details: 'Updated API key for Anthropic provider',
    resource: 'anthropic',
  },
  {
    id: 'aud-008',
    timestamp: '2026-03-25T18:08:00Z',
    action: 'Agent Run Failed',
    actionType: 'agent',
    actor: 'System',
    details: 'GPT-4o rate limit exceeded on Highway Nighttime batch',
    resource: 'ar-004',
  },
  {
    id: 'aud-009',
    timestamp: '2026-03-25T16:00:00Z',
    action: 'Reviewer Added',
    actionType: 'auth',
    actor: 'Sarah Chen',
    details: 'Added Elena Rodriguez as reviewer',
    resource: 'rev-003',
  },
  {
    id: 'aud-010',
    timestamp: '2026-03-25T14:00:00Z',
    action: 'Workflow Updated',
    actionType: 'workflow',
    actor: 'Sarah Chen',
    details: 'Paused Edge Case Triage pipeline',
    resource: 'wf-002',
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function getActionIcon(type: AuditEvent['actionType']) {
  switch (type) {
    case 'workspace':
      return Settings
    case 'dataset':
      return Upload
    case 'agent':
      return Zap
    case 'review':
      return ClipboardCheck
    case 'export':
      return FileDown
    case 'settings':
      return Shield
    case 'auth':
      return UserPlus
    case 'workflow':
      return Play
  }
}

function getActionBadgeVariant(type: AuditEvent['actionType']) {
  switch (type) {
    case 'workspace':
      return 'bg-violet-500/10 text-violet-500'
    case 'dataset':
      return 'bg-blue-500/10 text-blue-500'
    case 'agent':
      return 'bg-amber-500/10 text-amber-500'
    case 'review':
      return 'bg-emerald-500/10 text-emerald-500'
    case 'export':
      return 'bg-cyan-500/10 text-cyan-500'
    case 'settings':
      return 'bg-slate-500/10 text-slate-500'
    case 'auth':
      return 'bg-pink-500/10 text-pink-500'
    case 'workflow':
      return 'bg-orange-500/10 text-orange-500'
  }
}

function formatTimestamp(iso: string) {
  const date = new Date(iso)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function getInitials(name: string) {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
}

// ── Providers Tab ─────────────────────────────────────────────────────────────

function ProvidersTab() {
  const [providerStates, setProviderStates] = useState(
    providers.map((p) => ({ id: p.id, enabled: p.enabled })),
  )

  function toggleProvider(id: string) {
    setProviderStates((prev) =>
      prev.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)),
    )
  }

  function isEnabled(id: string) {
    return providerStates.find((p) => p.id === id)?.enabled ?? false
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">AI Providers</h3>
          <p className="text-sm text-muted-foreground">
            Configure API keys and connection settings for AI model providers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <CheckCircle2 className="h-4 w-4" />
            Test All Connections
          </Button>
          <Button size="sm">
            <Plus className="h-4 w-4" />
            Add Provider
          </Button>
        </div>
      </div>

      <div className="grid gap-4">
        {providers.map((provider) => {
          const Icon = provider.icon
          const enabled = isEnabled(provider.id)

          return (
            <Card
              key={provider.id}
              className={`border bg-card transition-colors ${
                enabled
                  ? 'hover:border-border/80'
                  : 'opacity-60 hover:opacity-75'
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                        enabled ? 'bg-muted' : 'bg-muted/50'
                      }`}
                    >
                      <Icon className={`h-5 w-5 ${provider.iconColor}`} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base">
                          {provider.name}
                        </CardTitle>
                        <div className="flex items-center gap-1.5">
                          <div
                            className={`h-2.5 w-2.5 rounded-full ${
                              provider.connected
                                ? 'bg-emerald-500'
                                : 'bg-muted-foreground/40'
                            }`}
                          />
                          <span
                            className={`text-xs font-medium ${provider.connected ? 'text-emerald-500' : 'text-muted-foreground'}`}
                          >
                            {provider.connected
                              ? 'Connected'
                              : 'Not configured'}
                          </span>
                        </div>
                      </div>
                      <CardDescription className="mt-0.5">
                        {provider.description}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={enabled}
                      onCheckedChange={() => {
                        toggleProvider(provider.id)
                      }}
                    />
                  </div>
                </div>
              </CardHeader>
              {enabled && provider.connected && (
                <CardContent>
                  <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-4 py-3">
                    <div className="flex items-center gap-6">
                      <div>
                        <p className="text-xs text-muted-foreground">Model</p>
                        <p className="font-mono text-sm">{provider.model}</p>
                      </div>
                      <Separator orientation="vertical" className="h-8" />
                      <div>
                        <p className="text-xs text-muted-foreground">API Key</p>
                        <p className="font-mono text-sm">{provider.apiKey}</p>
                      </div>
                    </div>
                    <Button variant="outline" size="sm">
                      Configure
                    </Button>
                  </div>
                </CardContent>
              )}
              {enabled && !provider.connected && (
                <CardContent>
                  <Button variant="outline" size="sm" className="w-full">
                    Configure
                  </Button>
                </CardContent>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}

// ── Reviewers Tab ─────────────────────────────────────────────────────────────

function ReviewersTab() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">Team Members</h3>
          <p className="text-sm text-muted-foreground">
            Manage reviewers and operators who have access to this workspace.
          </p>
        </div>
        <Button size="sm">
          <UserPlus className="h-4 w-4" />
          Add Reviewer
        </Button>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[280px]">Member</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockReviewers.map((reviewer) => (
              <TableRow key={reviewer.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium text-white"
                      style={{ backgroundColor: reviewer.avatarColor }}
                    >
                      {getInitials(reviewer.displayName)}
                    </div>
                    <div>
                      <p className="font-medium">{reviewer.displayName}</p>
                      <p className="text-xs text-muted-foreground">
                        {reviewer.id}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={
                      reviewer.isOperator
                        ? 'border-violet-500/30 bg-violet-500/10 text-violet-500'
                        : ''
                    }
                  >
                    {reviewer.isOperator ? 'Operator' : 'Reviewer'}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="secondary"
                    className="bg-emerald-500/10 text-emerald-500"
                  >
                    Active
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

// ── Preferences Tab ───────────────────────────────────────────────────────────

function PreferencesTab() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [density, setDensity] = useState('default')
  const [autoSave, setAutoSave] = useState(true)
  const [emailOnComplete, setEmailOnComplete] = useState(true)
  const [alertOnDrop, setAlertOnDrop] = useState(true)
  const [dailySummary, setDailySummary] = useState(false)

  return (
    <div className="space-y-8">
      {/* Appearance */}
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Appearance</h3>
          <p className="text-sm text-muted-foreground">
            Customize the look and feel of your workspace.
          </p>
        </div>
        <Card>
          <CardContent className="space-y-6 pt-6">
            <div className="space-y-3">
              <Label>Theme</Label>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setTheme('dark')
                  }}
                  className={`flex flex-1 flex-col items-center gap-2 rounded-lg border-2 p-4 transition-colors ${
                    theme === 'dark'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-border/80'
                  }`}
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-900">
                    <Moon className="h-5 w-5 text-zinc-300" />
                  </div>
                  <span className="text-sm font-medium">Dark</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTheme('light')
                  }}
                  className={`flex flex-1 flex-col items-center gap-2 rounded-lg border-2 p-4 transition-colors ${
                    theme === 'light'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-border/80'
                  }`}
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white">
                    <Sun className="h-5 w-5 text-amber-500" />
                  </div>
                  <span className="text-sm font-medium">Light</span>
                </button>
              </div>
            </div>

            <Separator />

            <div className="space-y-3">
              <Label>Interface Density</Label>
              <RadioGroup
                value={density}
                onValueChange={setDensity}
                className="flex gap-4"
              >
                {(['compact', 'default', 'comfortable'] as const).map(
                  (option) => (
                    <label
                      key={option}
                      className="flex cursor-pointer items-center gap-2"
                    >
                      <RadioGroupItem value={option} />
                      <span className="text-sm capitalize">{option}</span>
                    </label>
                  ),
                )}
              </RadioGroup>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Defaults */}
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Defaults</h3>
          <p className="text-sm text-muted-foreground">
            Set default values for new workflows and agent configurations.
          </p>
        </div>
        <Card>
          <CardContent className="space-y-6 pt-6">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="default-model">Default Model Profile</Label>
                <Select defaultValue="gpt-4o">
                  <SelectTrigger id="default-model">
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gpt-4o">GPT-4o (OpenAI)</SelectItem>
                    <SelectItem value="claude-sonnet">
                      Claude Sonnet 4 (Anthropic)
                    </SelectItem>
                    <SelectItem value="gemini-pro">
                      Gemini 2.5 Pro (Google)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="default-strategy">
                  Default Review Strategy
                </Label>
                <Select defaultValue="consensus">
                  <SelectTrigger id="default-strategy">
                    <SelectValue placeholder="Select strategy" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="consensus">
                      Consensus (majority vote)
                    </SelectItem>
                    <SelectItem value="expert">
                      Expert review (single senior)
                    </SelectItem>
                    <SelectItem value="dual">
                      Dual review (two reviewers)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />

            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-save Drafts</Label>
                <p className="text-sm text-muted-foreground">
                  Automatically save work-in-progress labels and reviews.
                </p>
              </div>
              <Switch checked={autoSave} onCheckedChange={setAutoSave} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Notifications */}
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-medium">Notifications</h3>
          <p className="text-sm text-muted-foreground">
            Configure when and how you receive workspace notifications.
          </p>
        </div>
        <Card>
          <CardContent className="space-y-5 pt-6">
            <div className="flex items-center justify-between">
              <div>
                <Label>Email on Workflow Complete</Label>
                <p className="text-sm text-muted-foreground">
                  Receive an email when a workflow run finishes.
                </p>
              </div>
              <Switch
                checked={emailOnComplete}
                onCheckedChange={setEmailOnComplete}
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <Label>Alert on Quality Drop</Label>
                <p className="text-sm text-muted-foreground">
                  Get notified when label quality metrics drop below threshold.
                </p>
              </div>
              <Switch checked={alertOnDrop} onCheckedChange={setAlertOnDrop} />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <Label>Daily Summary</Label>
                <p className="text-sm text-muted-foreground">
                  Receive a daily digest of workspace activity and metrics.
                </p>
              </div>
              <Switch
                checked={dailySummary}
                onCheckedChange={setDailySummary}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end">
        <Button>
          <Save className="h-4 w-4" />
          Save Preferences
        </Button>
      </div>
    </div>
  )
}

// ── Audit Log Tab ─────────────────────────────────────────────────────────────

function AuditLogTab() {
  const [actionFilter, setActionFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')

  const filteredEvents = auditEvents.filter((event) => {
    const matchesAction =
      actionFilter === 'all' || event.actionType === actionFilter
    const matchesSearch =
      searchQuery === '' ||
      event.action.toLowerCase().includes(searchQuery.toLowerCase()) ||
      event.actor.toLowerCase().includes(searchQuery.toLowerCase()) ||
      event.details.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesAction && matchesSearch
  })

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">Audit Log</h3>
        <p className="text-sm text-muted-foreground">
          A chronological record of all actions taken in this workspace.
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={actionFilter} onValueChange={setActionFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Action type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Actions</SelectItem>
                <SelectItem value="workspace">Workspace</SelectItem>
                <SelectItem value="dataset">Dataset</SelectItem>
                <SelectItem value="agent">Agent</SelectItem>
                <SelectItem value="review">Review</SelectItem>
                <SelectItem value="export">Export</SelectItem>
                <SelectItem value="settings">Settings</SelectItem>
                <SelectItem value="auth">Auth</SelectItem>
                <SelectItem value="workflow">Workflow</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="text"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
              }}
              className="max-w-[260px]"
            />
            <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              Last 7 days
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Events Table */}
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[140px]">Timestamp</TableHead>
              <TableHead className="w-[200px]">Action</TableHead>
              <TableHead className="w-[140px]">Actor</TableHead>
              <TableHead>Details</TableHead>
              <TableHead className="w-[100px]">Resource</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredEvents.map((event) => {
              const Icon = getActionIcon(event.actionType)
              const badgeColor = getActionBadgeVariant(event.actionType)

              return (
                <TableRow key={event.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatTimestamp(event.timestamp)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div
                        className={`flex h-6 w-6 items-center justify-center rounded ${badgeColor}`}
                      >
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <span className="text-sm font-medium">
                        {event.action}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{event.actor}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {event.details}
                  </TableCell>
                  <TableCell>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {event.resource}
                    </code>
                  </TableCell>
                </TableRow>
              )
            })}
            {filteredEvents.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-8 text-center text-sm text-muted-foreground"
                >
                  <Search className="mx-auto mb-2 h-5 w-5" />
                  No events match your filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        Showing {filteredEvents.length} of {auditEvents.length} events
      </p>
    </div>
  )
}

// ── Main Settings Page ────────────────────────────────────────────────────────

export function SettingsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Settings className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
            <p className="text-sm text-muted-foreground">
              Configure workspace preferences, API keys, and user management.
            </p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="providers" className="space-y-6">
        <TabsList>
          <TabsTrigger
            value="providers"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Providers
          </TabsTrigger>
          <TabsTrigger
            value="reviewers"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Reviewers
          </TabsTrigger>
          <TabsTrigger
            value="preferences"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Preferences
          </TabsTrigger>
          <TabsTrigger
            value="audit"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            Audit Log
          </TabsTrigger>
        </TabsList>

        <TabsContent value="providers">
          <ProvidersTab />
        </TabsContent>

        <TabsContent value="reviewers">
          <ReviewersTab />
        </TabsContent>

        <TabsContent value="preferences">
          <PreferencesTab />
        </TabsContent>

        <TabsContent value="audit">
          <AuditLogTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
