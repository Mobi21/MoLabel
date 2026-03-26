import { useState, useCallback, useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
  type EdgeTypes,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  getBezierPath,
  type EdgeProps,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  Database,
  Bot,
  Eye,
  Shield,
  Package,
  Scale,
  Play,
  FileCode,
  Save,
  CheckCircle2,
  Circle,
  Loader2,
  X,
  PanelRightClose,
  PanelRightOpen,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'

// ── Types ─────────────────────────────────────────────────────────────────────

type StepStatus = 'completed' | 'in-progress' | 'pending'
type StepType = 'data' | 'agent' | 'human' | 'quality' | 'output'

interface StepConfig {
  [key: string]: string | number | boolean
}

interface WorkflowNodeData {
  label: string
  subtitle: string
  icon: LucideIcon
  stepType: StepType
  status: StepStatus
  colorScheme: string
  statusTimestamp: string
  config: StepConfig
}

// ── Color Schemes ─────────────────────────────────────────────────────────────

const colorSchemes = {
  blue: {
    border: 'border-l-blue-500',
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    iconBg: 'bg-blue-100 dark:bg-blue-900/50',
    iconText: 'text-blue-600 dark:text-blue-400',
    handleBg: '#3b82f6',
    minimapColor: '#3b82f6',
  },
  purple: {
    border: 'border-l-purple-500',
    bg: 'bg-purple-50 dark:bg-purple-950/30',
    iconBg: 'bg-purple-100 dark:bg-purple-900/50',
    iconText: 'text-purple-600 dark:text-purple-400',
    handleBg: '#a855f7',
    minimapColor: '#a855f7',
  },
  green: {
    border: 'border-l-emerald-500',
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    iconBg: 'bg-emerald-100 dark:bg-emerald-900/50',
    iconText: 'text-emerald-600 dark:text-emerald-400',
    handleBg: '#10b981',
    minimapColor: '#10b981',
  },
  orange: {
    border: 'border-l-orange-500',
    bg: 'bg-orange-50 dark:bg-orange-950/30',
    iconBg: 'bg-orange-100 dark:bg-orange-900/50',
    iconText: 'text-orange-600 dark:text-orange-400',
    handleBg: '#f97316',
    minimapColor: '#f97316',
  },
  indigo: {
    border: 'border-l-indigo-500',
    bg: 'bg-indigo-50 dark:bg-indigo-950/30',
    iconBg: 'bg-indigo-100 dark:bg-indigo-900/50',
    iconText: 'text-indigo-600 dark:text-indigo-400',
    handleBg: '#6366f1',
    minimapColor: '#6366f1',
  },
  amber: {
    border: 'border-l-amber-500',
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    iconBg: 'bg-amber-100 dark:bg-amber-900/50',
    iconText: 'text-amber-600 dark:text-amber-400',
    handleBg: '#f59e0b',
    minimapColor: '#f59e0b',
  },
} as const

type ColorKey = keyof typeof colorSchemes

// ── Status Indicator ──────────────────────────────────────────────────────────

function StatusIndicator({ status }: { status: StepStatus }) {
  if (status === 'completed') {
    return <CheckCircle2 className="h-4 w-4 text-emerald-500" />
  }
  if (status === 'in-progress') {
    return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
  }
  return <Circle className="h-4 w-4 text-zinc-300 dark:text-zinc-600" />
}

function statusLabel(status: StepStatus): string {
  if (status === 'completed') return 'Completed'
  if (status === 'in-progress') return 'In Progress'
  return 'Pending'
}

function statusBadgeClass(status: StepStatus): string {
  if (status === 'completed') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
  if (status === 'in-progress') return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400 border-blue-200 dark:border-blue-800'
  return 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700'
}

// ── Custom Workflow Node ──────────────────────────────────────────────────────

function WorkflowNode({ data, selected }: NodeProps<WorkflowNodeData>) {
  const scheme = colorSchemes[data.colorScheme as ColorKey] ?? colorSchemes.blue
  const Icon = data.icon

  return (
    <div
      className={`
        group relative w-56 rounded-lg border border-l-4 bg-card shadow-sm
        transition-all duration-200
        ${scheme.border}
        ${selected ? 'ring-2 ring-ring shadow-md' : 'hover:shadow-md'}
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white dark:!border-zinc-900"
        style={{ background: scheme.handleBg }}
      />

      <div className="flex items-start gap-3 p-3">
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${scheme.iconBg}`}>
          <Icon className={`h-4.5 w-4.5 ${scheme.iconText}`} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1">
            <span className="truncate text-sm font-semibold leading-snug text-foreground">
              {data.label}
            </span>
            <StatusIndicator status={data.status} />
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {data.subtitle}
          </p>
        </div>
      </div>

      {data.status === 'in-progress' && (
        <div className="absolute inset-0 rounded-lg ring-2 ring-blue-400/40 animate-pulse pointer-events-none" />
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white dark:!border-zinc-900"
        style={{ background: scheme.handleBg }}
      />
    </div>
  )
}

// ── Custom Dashed Edge ────────────────────────────────────────────────────────

function ConditionalEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  return (
    <path
      id={id}
      style={{
        ...style,
        strokeDasharray: '6 4',
        strokeWidth: 2,
        stroke: '#f59e0b',
        fill: 'none',
      }}
      className="react-flow__edge-path"
      d={edgePath}
      markerEnd={markerEnd}
    />
  )
}

// ── Node & Edge Definitions ───────────────────────────────────────────────────

const initialNodes: Node<WorkflowNodeData>[] = [
  {
    id: 'data-ingest',
    type: 'workflowNode',
    position: { x: 50, y: 200 },
    data: {
      label: 'Data Ingest',
      subtitle: 'Urban Scenes 2026-Q1',
      icon: Database,
      stepType: 'data',
      status: 'completed',
      colorScheme: 'blue',
      statusTimestamp: '2026-03-26T06:00:00Z',
      config: {
        source: 'S3 Bucket — autonomous-driving-v3',
        format: 'COCO JSON',
        recordCount: 24850,
      },
    },
  },
  {
    id: 'ai-prelabel',
    type: 'workflowNode',
    position: { x: 340, y: 200 },
    data: {
      label: 'AI Pre-Label',
      subtitle: 'GPT-4o',
      icon: Bot,
      stepType: 'agent',
      status: 'completed',
      colorScheme: 'purple',
      statusTimestamp: '2026-03-26T06:47:00Z',
      config: {
        model: 'gpt-4o',
        promptVersion: 'v2.3',
        batchSize: 50,
      },
    },
  },
  {
    id: 'human-review',
    type: 'workflowNode',
    position: { x: 630, y: 200 },
    data: {
      label: 'Human Review',
      subtitle: '2 reviewers, blind mode',
      icon: Eye,
      stepType: 'human',
      status: 'in-progress',
      colorScheme: 'green',
      statusTimestamp: '2026-03-26T08:30:00Z',
      config: {
        reviewerCount: 2,
        blindMode: true,
        overlapPolicy: 'full',
      },
    },
  },
  {
    id: 'quality-check',
    type: 'workflowNode',
    position: { x: 920, y: 200 },
    data: {
      label: 'Quality Check',
      subtitle: 'Agreement \u2265 0.85',
      icon: Shield,
      stepType: 'quality',
      status: 'pending',
      colorScheme: 'orange',
      statusTimestamp: '',
      config: {
        threshold: 0.85,
        metrics: 'Inter-annotator agreement (Cohen\u2019s \u03BA)',
      },
    },
  },
  {
    id: 'export',
    type: 'workflowNode',
    position: { x: 1210, y: 200 },
    data: {
      label: 'Export',
      subtitle: 'COCO JSON',
      icon: Package,
      stepType: 'output',
      status: 'pending',
      colorScheme: 'indigo',
      statusTimestamp: '',
      config: {
        format: 'COCO JSON',
        destination: 'S3 — releases/urban-scenes-q1/',
      },
    },
  },
  {
    id: 'adjudication',
    type: 'workflowNode',
    position: { x: 920, y: 420 },
    data: {
      label: 'Adjudication',
      subtitle: 'If agreement < 0.85',
      icon: Scale,
      stepType: 'human',
      status: 'pending',
      colorScheme: 'amber',
      statusTimestamp: '',
      config: {
        reviewerCount: 1,
        blindMode: false,
        overlapPolicy: 'none — senior reviewer',
      },
    },
  },
]

const initialEdges: Edge[] = [
  {
    id: 'e-ingest-prelabel',
    source: 'data-ingest',
    target: 'ai-prelabel',
    type: 'smoothstep',
    animated: false,
    style: { strokeWidth: 2, stroke: '#94a3b8' },
  },
  {
    id: 'e-prelabel-review',
    source: 'ai-prelabel',
    target: 'human-review',
    type: 'smoothstep',
    animated: false,
    style: { strokeWidth: 2, stroke: '#94a3b8' },
  },
  {
    id: 'e-review-quality',
    source: 'human-review',
    target: 'quality-check',
    type: 'smoothstep',
    animated: true,
    style: { strokeWidth: 2, stroke: '#3b82f6' },
  },
  {
    id: 'e-quality-export',
    source: 'quality-check',
    target: 'export',
    type: 'smoothstep',
    animated: false,
    style: { strokeWidth: 2, stroke: '#94a3b8' },
  },
  {
    id: 'e-quality-adjudication',
    source: 'quality-check',
    target: 'adjudication',
    type: 'conditional',
    animated: false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: '#f59e0b',
      width: 16,
      height: 16,
    },
    label: 'Agreement < 0.85',
    labelStyle: { fontSize: 11, fill: '#f59e0b', fontWeight: 500 },
    labelBgStyle: { fill: 'var(--card)', fillOpacity: 0.9 },
    labelBgPadding: [6, 4] as [number, number],
    labelBgBorderRadius: 4,
  },
  {
    id: 'e-adjudication-review',
    source: 'adjudication',
    target: 'human-review',
    type: 'conditional',
    animated: false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: '#f59e0b',
      width: 16,
      height: 16,
    },
    label: 'Re-review',
    labelStyle: { fontSize: 11, fill: '#f59e0b', fontWeight: 500 },
    labelBgStyle: { fill: 'var(--card)', fillOpacity: 0.9 },
    labelBgPadding: [6, 4] as [number, number],
    labelBgBorderRadius: 4,
  },
]

// ── Step Type Badge ───────────────────────────────────────────────────────────

function stepTypeBadgeClass(stepType: StepType): string {
  const map: Record<StepType, string> = {
    data: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400',
    agent: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-400',
    human: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400',
    quality: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400',
    output: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400',
  }
  return map[stepType] ?? ''
}

// ── Config Panel for each step type ───────────────────────────────────────────

function DataConfigPanel({ config }: { config: StepConfig }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Source</Label>
        <Input readOnly value={String(config['source'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Format</Label>
        <Input readOnly value={String(config['format'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Record Count</Label>
        <Input
          readOnly
          value={typeof config['recordCount'] === 'number' ? config['recordCount'].toLocaleString() : ''}
          className="h-8 text-sm"
        />
      </div>
    </div>
  )
}

function AgentConfigPanel({ config }: { config: StepConfig }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Model</Label>
        <Input readOnly value={String(config['model'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Prompt Version</Label>
        <Input readOnly value={String(config['promptVersion'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Batch Size</Label>
        <Input readOnly value={String(config['batchSize'] ?? '')} className="h-8 text-sm" />
      </div>
    </div>
  )
}

function HumanConfigPanel({ config }: { config: StepConfig }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Reviewer Count</Label>
        <Input readOnly value={String(config['reviewerCount'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="flex items-center justify-between">
        <Label className="text-xs text-muted-foreground">Blind Mode</Label>
        <Switch checked={config['blindMode'] === true} disabled />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Overlap Policy</Label>
        <Input readOnly value={String(config['overlapPolicy'] ?? '')} className="h-8 text-sm" />
      </div>
    </div>
  )
}

function QualityConfigPanel({ config }: { config: StepConfig }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Threshold</Label>
        <Input readOnly value={String(config['threshold'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Metrics</Label>
        <Input readOnly value={String(config['metrics'] ?? '')} className="h-8 text-sm" />
      </div>
    </div>
  )
}

function OutputConfigPanel({ config }: { config: StepConfig }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Format</Label>
        <Input readOnly value={String(config['format'] ?? '')} className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Destination</Label>
        <Input readOnly value={String(config['destination'] ?? '')} className="h-8 text-sm" />
      </div>
    </div>
  )
}

function ConfigPanelForType({ stepType, config }: { stepType: StepType, config: StepConfig }) {
  switch (stepType) {
    case 'data':
      return <DataConfigPanel config={config} />
    case 'agent':
      return <AgentConfigPanel config={config} />
    case 'human':
      return <HumanConfigPanel config={config} />
    case 'quality':
      return <QualityConfigPanel config={config} />
    case 'output':
      return <OutputConfigPanel config={config} />
    default:
      return null
  }
}

// ── Right Side Panel ──────────────────────────────────────────────────────────

function StepConfigPanel({
  node,
  onClose,
}: {
  node: Node<WorkflowNodeData> | undefined
  onClose: () => void
}) {
  if (!node) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-sm text-muted-foreground text-center">
          Select a step to view configuration
        </p>
      </div>
    )
  }

  const { data } = node
  const Icon = data.icon
  const scheme = colorSchemes[data.colorScheme as ColorKey] ?? colorSchemes.blue

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${scheme.iconBg}`}>
              <Icon className={`h-4 w-4 ${scheme.iconText}`} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">{data.label}</h3>
              <p className="text-xs text-muted-foreground">{data.subtitle}</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        <Separator />

        {/* Type & Status */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Type</span>
            <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${stepTypeBadgeClass(data.stepType)}`}>
              {data.stepType.charAt(0).toUpperCase() + data.stepType.slice(1)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Status</span>
            <div className="flex items-center gap-1.5">
              <StatusIndicator status={data.status} />
              <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${statusBadgeClass(data.status)}`}>
                {statusLabel(data.status)}
              </span>
            </div>
          </div>
          {data.statusTimestamp && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Timestamp</span>
              <span className="text-xs font-mono text-muted-foreground">
                {new Date(data.statusTimestamp).toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          )}
        </div>

        <Separator />

        {/* Step Name */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Step Name</Label>
          <Input defaultValue={data.label} className="h-8 text-sm" />
        </div>

        <Separator />

        {/* Configuration */}
        <div>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Configuration
          </h4>
          <ConfigPanelForType stepType={data.stepType} config={data.config} />
        </div>
      </div>
    </ScrollArea>
  )
}

// ── Minimap Node Color ────────────────────────────────────────────────────────

function minimapNodeColor(node: Node<WorkflowNodeData>): string {
  const scheme = colorSchemes[node.data.colorScheme as ColorKey]
  return scheme?.minimapColor ?? '#94a3b8'
}

// ── Main Page Component ───────────────────────────────────────────────────────

const nodeTypes: NodeTypes = {
  workflowNode: WorkflowNode,
}

const edgeTypes: EdgeTypes = {
  conditional: ConditionalEdge,
}

export function WorkflowPage() {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) as Node<WorkflowNodeData> | undefined,
    [nodes, selectedNodeId],
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
    setPanelOpen(true)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  return (
    <div className="flex h-full flex-col">
      {/* ── Top Toolbar ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b bg-card px-4 py-2.5">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-semibold text-foreground">
            Standard Labeling Pipeline
          </h1>
          <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100">
            <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Active
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5">
            <FileCode className="h-3.5 w-3.5" />
            Edit YAML
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setPanelOpen((v) => !v)}
            title={panelOpen ? 'Close panel' : 'Open panel'}
          >
            {panelOpen
              ? <PanelRightClose className="h-4 w-4" />
              : <PanelRightOpen className="h-4 w-4" />}
          </Button>
          <Separator orientation="vertical" className="mx-1 h-5" />
          <Button variant="outline" size="sm" className="gap-1.5">
            <Save className="h-3.5 w-3.5" />
            Save
          </Button>
          <Button size="sm" className="gap-1.5">
            <Play className="h-3.5 w-3.5" />
            Run Workflow
          </Button>
        </div>
      </div>

      {/* ── Canvas + Panel ──────────────────────────────────────────────── */}
      <div className="relative flex flex-1 overflow-hidden">
        {/* React Flow Canvas */}
        <div className="flex-1 p-2">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            minZoom={0.3}
            maxZoom={2}
            defaultEdgeOptions={{
              type: 'smoothstep',
              style: { strokeWidth: 2 },
            }}

          >
            <Background
              gap={16}
              size={1}
              color="var(--border)"
            />
            <Controls
              position="bottom-left"
              showInteractive={false}
              className="!rounded-lg !border !border-border !bg-card !shadow-sm [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground [&>button:hover]:!bg-accent"
            />
            <MiniMap
              position="bottom-right"
              nodeColor={minimapNodeColor}
              maskColor="rgba(0,0,0,0.08)"
              className="!rounded-lg !border !border-border !bg-card !shadow-sm"
              pannable
              zoomable
            />
          </ReactFlow>
        </div>

        {/* Right Panel */}
        {panelOpen && (
          <div className="w-[300px] shrink-0 border-l border-border bg-card">
            <div className="flex h-10 items-center border-b border-border px-4">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Step Configuration
              </h2>
            </div>
            <div className="h-[calc(100%-2.5rem)]">
              <StepConfigPanel node={selectedNode} onClose={handleClosePanel} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
