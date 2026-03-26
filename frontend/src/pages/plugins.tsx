import { useState } from 'react'
import {
  Puzzle,
  Search,
  Settings,
  Sparkles,
  Brain,
  Globe,
  FileJson,
  FileText,
  BarChart3,
  MessageSquare,
  Cloud,
  type LucideIcon,
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
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { mockPlugins } from '@/mocks/data'
import type { Plugin } from '@/mocks/data'

// ── Icon mapping ─────────────────────────────────────────────────────────────

const iconMap: Record<string, LucideIcon> = {
  Sparkles,
  Brain,
  Globe,
  FileJson,
  FileText,
  BarChart3,
  MessageSquare,
  Cloud,
}

function getPluginIcon(iconName: string): LucideIcon {
  return iconMap[iconName] ?? Puzzle
}

// ── Category badge helper ────────────────────────────────────────────────────

function categoryBadge(category: Plugin['category']) {
  switch (category) {
    case 'provider':
      return (
        <Badge
          variant="outline"
          className="border-purple-500/20 bg-purple-500/10 text-[10px] text-purple-600"
        >
          Provider
        </Badge>
      )
    case 'export':
      return (
        <Badge
          variant="outline"
          className="border-blue-500/20 bg-blue-500/10 text-[10px] text-blue-600"
        >
          Export
        </Badge>
      )
    case 'quality':
      return (
        <Badge
          variant="outline"
          className="border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-600"
        >
          Quality
        </Badge>
      )
    case 'integration':
      return (
        <Badge
          variant="outline"
          className="border-orange-500/20 bg-orange-500/10 text-[10px] text-orange-600"
        >
          Integration
        </Badge>
      )
  }
}

// ── Plugin Card ──────────────────────────────────────────────────────────────

function PluginCard({
  plugin,
  enabled,
  onToggle,
}: {
  plugin: Plugin
  enabled: boolean
  onToggle: (checked: boolean) => void
}) {
  const Icon = getPluginIcon(plugin.icon)

  return (
    <Card
      className={`border bg-card transition-all ${
        enabled
          ? 'hover:border-primary/40 hover:shadow-md'
          : 'opacity-50'
      }`}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                enabled ? 'bg-primary/10' : 'bg-muted'
              }`}
            >
              <Icon
                className={`h-4.5 w-4.5 ${
                  enabled ? 'text-primary' : 'text-muted-foreground'
                }`}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <CardTitle className="truncate text-sm">
                  {plugin.name}
                </CardTitle>
                <Badge
                  variant="secondary"
                  className="shrink-0 font-mono text-[10px]"
                >
                  v{plugin.version}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                enabled ? 'bg-emerald-500' : 'bg-zinc-300'
              }`}
            />
            <Switch checked={enabled} onCheckedChange={onToggle} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="line-clamp-1 text-xs">
          {plugin.description}
        </CardDescription>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">
              {plugin.author}
            </span>
            <span className="text-border">|</span>
            {categoryBadge(plugin.category)}
          </div>
        </div>

        <Separator />

        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            disabled={!enabled}
          >
            <Settings className="h-3 w-3" />
            Configure
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function PluginsPage() {
  const [pluginStates, setPluginStates] = useState<Record<string, boolean>>(
    () => {
      const states: Record<string, boolean> = {}
      for (const p of mockPlugins) {
        states[p.id] = p.enabled
      }
      return states
    },
  )

  function togglePlugin(id: string, checked: boolean) {
    setPluginStates((prev) => ({ ...prev, [id]: checked }))
  }

  const enabledCount = Object.values(pluginStates).filter(Boolean).length
  const disabledCount = mockPlugins.length - enabledCount
  const updatesAvailable = 4

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Puzzle className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-semibold tracking-tight">Plugins</h1>
              <Badge variant="secondary" className="text-xs font-normal">
                {enabledCount} enabled, {disabledCount} disabled
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              Manage AI providers, exporters, quality tools, and integrations.
            </p>
          </div>
        </div>
      </div>

      {/* Plugin Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {mockPlugins.map((plugin) => (
          <PluginCard
            key={plugin.id}
            plugin={plugin}
            enabled={pluginStates[plugin.id] ?? false}
            onToggle={(checked) => togglePlugin(plugin.id, checked)}
          />
        ))}
      </div>

      {/* Bottom Section */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Discover Plugins */}
        <Card className="transition-all hover:border-primary/40 hover:shadow-md">
          <CardContent className="flex items-center gap-4 p-6">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Search className="h-6 w-6 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">Discover Plugins</p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Browse the plugin marketplace for additional loaders, exporters,
                and integrations
              </p>
            </div>
            <Button variant="outline" className="shrink-0">
              Browse
            </Button>
          </CardContent>
        </Card>

        {/* Plugin Stats */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Plugin Summary
            </p>
            <div className="mt-3 flex items-center gap-3">
              <div className="flex items-center gap-4 text-sm">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-primary" />
                  <span className="font-medium">{mockPlugins.length}</span>
                  <span className="text-muted-foreground">installed</span>
                </span>
                <span className="text-border">&middot;</span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  <span className="font-medium">{enabledCount}</span>
                  <span className="text-muted-foreground">enabled</span>
                </span>
                <span className="text-border">&middot;</span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-zinc-300" />
                  <span className="font-medium">{disabledCount}</span>
                  <span className="text-muted-foreground">disabled</span>
                </span>
                <span className="text-border">&middot;</span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  <span className="font-medium">{updatesAvailable}</span>
                  <span className="text-muted-foreground">updates available</span>
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
