import type { Workspace } from '@/stores/workspace-store'
import type { Reviewer } from '@/stores/auth-store'

// ── Workspace ──────────────────────────────────────────────────────────────

export const mockWorkspace: Workspace = {
  id: 'ws-001',
  name: 'Autonomous Driving v3',
  slug: 'autonomous-driving-v3',
  rootPath: '/data/projects/autonomous-driving-v3',
  datasetCount: 5,
  workflowCount: 3,
}

// ── Reviewers ──────────────────────────────────────────────────────────────

export const mockReviewers: Reviewer[] = [
  {
    id: 'rev-001',
    displayName: 'Sarah Chen',
    avatarColor: '#6366f1',
    isOperator: true,
  },
  {
    id: 'rev-002',
    displayName: 'Marcus Johnson',
    avatarColor: '#22c55e',
    isOperator: false,
  },
  {
    id: 'rev-003',
    displayName: 'Elena Rodriguez',
    avatarColor: '#f59e0b',
    isOperator: false,
  },
]

// ── Datasets ───────────────────────────────────────────────────────────────

export interface Dataset {
  id: string
  name: string
  description: string
  recordCount: number
  labeledCount: number
  reviewedCount: number
  healthStatus: 'healthy' | 'warning' | 'critical'
  format: string
  createdAt: string
  updatedAt: string
  tags: string[]
}

export const mockDatasets: Dataset[] = [
  {
    id: 'ds-001',
    name: 'Urban Scenes 2026-Q1',
    description:
      'High-resolution urban driving scenes from San Francisco and Portland metro areas',
    recordCount: 24_850,
    labeledCount: 18_640,
    reviewedCount: 12_320,
    healthStatus: 'healthy',
    format: 'COCO JSON',
    createdAt: '2026-01-15T08:00:00Z',
    updatedAt: '2026-03-25T14:30:00Z',
    tags: ['urban', 'daytime', 'q1-2026'],
  },
  {
    id: 'ds-002',
    name: 'Highway Nighttime',
    description:
      'Nighttime highway footage with varying weather conditions and traffic density',
    recordCount: 15_200,
    labeledCount: 9_120,
    reviewedCount: 5_840,
    healthStatus: 'warning',
    format: 'COCO JSON',
    createdAt: '2026-02-01T10:00:00Z',
    updatedAt: '2026-03-24T16:45:00Z',
    tags: ['highway', 'nighttime', 'weather'],
  },
  {
    id: 'ds-003',
    name: 'Pedestrian Detection',
    description:
      'Focused pedestrian detection dataset from crosswalks and residential areas',
    recordCount: 31_400,
    labeledCount: 28_200,
    reviewedCount: 25_600,
    healthStatus: 'healthy',
    format: 'Pascal VOC',
    createdAt: '2025-11-20T09:00:00Z',
    updatedAt: '2026-03-26T09:15:00Z',
    tags: ['pedestrian', 'safety-critical', 'verified'],
  },
  {
    id: 'ds-004',
    name: 'Construction Zones',
    description:
      'Temporary road modifications, cones, barriers, and construction signage',
    recordCount: 8_600,
    labeledCount: 2_150,
    reviewedCount: 800,
    healthStatus: 'critical',
    format: 'COCO JSON',
    createdAt: '2026-03-01T11:00:00Z',
    updatedAt: '2026-03-25T19:00:00Z',
    tags: ['construction', 'edge-case', 'priority'],
  },
  {
    id: 'ds-005',
    name: 'Adverse Weather',
    description:
      'Rain, fog, snow, and glare conditions across urban and highway environments',
    recordCount: 12_750,
    labeledCount: 6_375,
    reviewedCount: 3_100,
    healthStatus: 'warning',
    format: 'YOLO',
    createdAt: '2026-02-10T14:00:00Z',
    updatedAt: '2026-03-23T11:20:00Z',
    tags: ['weather', 'edge-case', 'multi-condition'],
  },
]

// ── Dashboard Stats ────────────────────────────────────────────────────────

export interface DashboardStats {
  totalRecords: number
  totalLabeled: number
  totalReviewed: number
  exportReady: number
  labelingRate: number
  reviewRate: number
  activeAgents: number
  pendingReview: number
}

export const mockDashboardStats: DashboardStats = {
  totalRecords: 92_800,
  totalLabeled: 64_485,
  totalReviewed: 47_660,
  exportReady: 38_920,
  labelingRate: 1_240,
  reviewRate: 890,
  activeAgents: 3,
  pendingReview: 16_825,
}

// ── Workflows ──────────────────────────────────────────────────────────────

export interface Workflow {
  id: string
  name: string
  description: string
  status: 'active' | 'paused' | 'draft'
  steps: number
  lastRun: string
  createdAt: string
}

export const mockWorkflows: Workflow[] = [
  {
    id: 'wf-001',
    name: 'Standard Labeling Pipeline',
    description:
      'AI pre-label, human review, adjudication, quality check, export',
    status: 'active',
    steps: 5,
    lastRun: '2026-03-26T08:00:00Z',
    createdAt: '2026-01-10T09:00:00Z',
  },
  {
    id: 'wf-002',
    name: 'Edge Case Triage',
    description:
      'Identify edge cases via model uncertainty, route to senior reviewers',
    status: 'active',
    steps: 4,
    lastRun: '2026-03-25T22:00:00Z',
    createdAt: '2026-02-15T14:00:00Z',
  },
  {
    id: 'wf-003',
    name: 'Quality Audit Batch',
    description:
      'Sample-based quality audit with inter-annotator agreement scoring',
    status: 'draft',
    steps: 3,
    lastRun: '2026-03-20T16:00:00Z',
    createdAt: '2026-03-18T10:00:00Z',
  },
]

// ── Task Schemas ───────────────────────────────────────────────────────────

export interface TaskSchema {
  id: string
  name: string
  type: 'classification' | 'bounding-box' | 'segmentation' | 'ner'
  labelCount: number
  description: string
}

export const mockTaskSchemas: TaskSchema[] = [
  {
    id: 'ts-001',
    name: 'Vehicle Detection',
    type: 'bounding-box',
    labelCount: 12,
    description:
      'Detect and classify vehicles: car, truck, bus, motorcycle, bicycle, emergency vehicle, etc.',
  },
  {
    id: 'ts-002',
    name: 'Road Sign Classification',
    type: 'classification',
    labelCount: 48,
    description:
      'Classify road signs into regulatory, warning, guide, and construction categories',
  },
]

// ── Agent Runs ─────────────────────────────────────────────────────────────

export interface AgentRun {
  id: string
  agentName: string
  provider: string
  model: string
  status: 'completed' | 'running' | 'failed' | 'queued'
  recordsProcessed: number
  accuracy: number
  cost: number
  duration: string
  startedAt: string
}

export const mockAgentRuns: AgentRun[] = [
  {
    id: 'ar-001',
    agentName: 'GPT-4o Pre-labeler',
    provider: 'OpenAI',
    model: 'gpt-4o',
    status: 'completed',
    recordsProcessed: 2_400,
    accuracy: 0.924,
    cost: 18.72,
    duration: '47m 12s',
    startedAt: '2026-03-26T06:00:00Z',
  },
  {
    id: 'ar-002',
    agentName: 'Claude Adjudicator',
    provider: 'Anthropic',
    model: 'claude-sonnet-4-20250514',
    status: 'running',
    recordsProcessed: 1_180,
    accuracy: 0.951,
    cost: 12.45,
    duration: '23m 08s',
    startedAt: '2026-03-26T08:30:00Z',
  },
  {
    id: 'ar-003',
    agentName: 'Gemini Edge Detector',
    provider: 'Google',
    model: 'gemini-2.5-pro',
    status: 'completed',
    recordsProcessed: 850,
    accuracy: 0.887,
    cost: 6.32,
    duration: '18m 45s',
    startedAt: '2026-03-25T22:00:00Z',
  },
  {
    id: 'ar-004',
    agentName: 'GPT-4o Pre-labeler',
    provider: 'OpenAI',
    model: 'gpt-4o',
    status: 'failed',
    recordsProcessed: 340,
    accuracy: 0,
    cost: 2.88,
    duration: '8m 20s',
    startedAt: '2026-03-25T18:00:00Z',
  },
  {
    id: 'ar-005',
    agentName: 'Quality Scorer',
    provider: 'Anthropic',
    model: 'claude-sonnet-4-20250514',
    status: 'queued',
    recordsProcessed: 0,
    accuracy: 0,
    cost: 0,
    duration: '—',
    startedAt: '2026-03-26T09:00:00Z',
  },
]

// ── Review Queue ───────────────────────────────────────────────────────────

export interface ReviewItem {
  id: string
  recordId: string
  datasetName: string
  taskType: string
  priority: 'high' | 'medium' | 'low'
  assignee: string | null
  createdAt: string
}

export const mockReviewQueue: ReviewItem[] = [
  {
    id: 'rq-001',
    recordId: 'rec-4821',
    datasetName: 'Urban Scenes 2026-Q1',
    taskType: 'Vehicle Detection',
    priority: 'high',
    assignee: 'Sarah Chen',
    createdAt: '2026-03-26T07:30:00Z',
  },
  {
    id: 'rq-002',
    recordId: 'rec-4822',
    datasetName: 'Construction Zones',
    taskType: 'Vehicle Detection',
    priority: 'high',
    assignee: null,
    createdAt: '2026-03-26T07:31:00Z',
  },
  {
    id: 'rq-003',
    recordId: 'rec-9103',
    datasetName: 'Highway Nighttime',
    taskType: 'Road Sign Classification',
    priority: 'medium',
    assignee: 'Marcus Johnson',
    createdAt: '2026-03-25T22:15:00Z',
  },
  {
    id: 'rq-004',
    recordId: 'rec-1547',
    datasetName: 'Pedestrian Detection',
    taskType: 'Vehicle Detection',
    priority: 'low',
    assignee: null,
    createdAt: '2026-03-25T20:00:00Z',
  },
  {
    id: 'rq-005',
    recordId: 'rec-7290',
    datasetName: 'Adverse Weather',
    taskType: 'Vehicle Detection',
    priority: 'medium',
    assignee: 'Elena Rodriguez',
    createdAt: '2026-03-25T19:45:00Z',
  },
]

// ── Quality Metrics ────────────────────────────────────────────────────────

export interface QualityMetrics {
  interAnnotatorAgreement: number
  labelDriftScore: number
  averageConfidence: number
  disagreementRate: number
  samplesAudited: number
  issuesFound: number
  resolutionRate: number
}

export const mockQualityMetrics: QualityMetrics = {
  interAnnotatorAgreement: 0.892,
  labelDriftScore: 0.023,
  averageConfidence: 0.914,
  disagreementRate: 0.078,
  samplesAudited: 4_200,
  issuesFound: 186,
  resolutionRate: 0.945,
}

// ── Plugins ────────────────────────────────────────────────────────────────

export interface Plugin {
  id: string
  name: string
  description: string
  version: string
  author: string
  enabled: boolean
  category: 'provider' | 'export' | 'quality' | 'integration'
  icon: string
}

export const mockPlugins: Plugin[] = [
  {
    id: 'pl-001',
    name: 'OpenAI Provider',
    description: 'GPT-4o and GPT-4o-mini for pre-labeling and adjudication',
    version: '1.2.0',
    author: 'MoLabel Core',
    enabled: true,
    category: 'provider',
    icon: 'Sparkles',
  },
  {
    id: 'pl-002',
    name: 'Anthropic Provider',
    description:
      'Claude models for high-accuracy labeling and quality assessment',
    version: '1.1.0',
    author: 'MoLabel Core',
    enabled: true,
    category: 'provider',
    icon: 'Brain',
  },
  {
    id: 'pl-003',
    name: 'Google AI Provider',
    description: 'Gemini models for multi-modal labeling tasks',
    version: '1.0.0',
    author: 'MoLabel Core',
    enabled: true,
    category: 'provider',
    icon: 'Globe',
  },
  {
    id: 'pl-004',
    name: 'COCO Exporter',
    description: 'Export labels in COCO JSON format with validation',
    version: '2.0.1',
    author: 'MoLabel Core',
    enabled: true,
    category: 'export',
    icon: 'FileJson',
  },
  {
    id: 'pl-005',
    name: 'YOLO Exporter',
    description: 'Export bounding boxes in YOLO format',
    version: '1.3.0',
    author: 'MoLabel Core',
    enabled: true,
    category: 'export',
    icon: 'FileText',
  },
  {
    id: 'pl-006',
    name: 'Label Quality Analyzer',
    description:
      'Statistical analysis of label quality, drift detection, and agreement scoring',
    version: '1.0.0',
    author: 'MoLabel Core',
    enabled: true,
    category: 'quality',
    icon: 'BarChart3',
  },
  {
    id: 'pl-007',
    name: 'Slack Notifications',
    description: 'Send workflow events and alerts to Slack channels',
    version: '0.9.0',
    author: 'Community',
    enabled: false,
    category: 'integration',
    icon: 'MessageSquare',
  },
  {
    id: 'pl-008',
    name: 'S3 Data Connector',
    description: 'Import and export data directly from AWS S3 buckets',
    version: '1.1.0',
    author: 'Community',
    enabled: false,
    category: 'integration',
    icon: 'Cloud',
  },
]

// ── Activity Feed ──────────────────────────────────────────────────────────

export interface ActivityItem {
  id: string
  type: 'agent_run' | 'review' | 'export' | 'workflow' | 'system'
  message: string
  actor: string
  timestamp: string
}

export const mockActivity: ActivityItem[] = [
  {
    id: 'act-001',
    type: 'agent_run',
    message: 'GPT-4o Pre-labeler completed 2,400 records with 92.4% accuracy',
    actor: 'System',
    timestamp: '2026-03-26T06:47:00Z',
  },
  {
    id: 'act-002',
    type: 'review',
    message: 'Sarah Chen completed 145 reviews on Urban Scenes 2026-Q1',
    actor: 'Sarah Chen',
    timestamp: '2026-03-26T05:30:00Z',
  },
  {
    id: 'act-003',
    type: 'workflow',
    message: 'Standard Labeling Pipeline triggered for Construction Zones',
    actor: 'System',
    timestamp: '2026-03-26T04:00:00Z',
  },
  {
    id: 'act-004',
    type: 'export',
    message: 'Pedestrian Detection v2.8 exported to COCO JSON (25,600 records)',
    actor: 'Sarah Chen',
    timestamp: '2026-03-25T23:00:00Z',
  },
  {
    id: 'act-005',
    type: 'agent_run',
    message:
      'Gemini Edge Detector processed 850 edge cases from Adverse Weather',
    actor: 'System',
    timestamp: '2026-03-25T22:45:00Z',
  },
  {
    id: 'act-006',
    type: 'review',
    message: 'Marcus Johnson adjudicated 38 disagreements on Highway Nighttime',
    actor: 'Marcus Johnson',
    timestamp: '2026-03-25T20:15:00Z',
  },
  {
    id: 'act-007',
    type: 'agent_run',
    message:
      'GPT-4o Pre-labeler failed on Highway Nighttime batch — rate limit exceeded',
    actor: 'System',
    timestamp: '2026-03-25T18:08:00Z',
  },
  {
    id: 'act-008',
    type: 'system',
    message:
      'Quality alert: label drift detected on Construction Zones (+2.3%)',
    actor: 'System',
    timestamp: '2026-03-25T16:00:00Z',
  },
  {
    id: 'act-009',
    type: 'review',
    message: 'Elena Rodriguez completed 92 reviews on Adverse Weather',
    actor: 'Elena Rodriguez',
    timestamp: '2026-03-25T15:30:00Z',
  },
  {
    id: 'act-010',
    type: 'workflow',
    message: 'Edge Case Triage paused — awaiting senior reviewer availability',
    actor: 'System',
    timestamp: '2026-03-25T14:00:00Z',
  },
]

// ── Exports & Releases ─────────────────────────────────────────────────────

export interface ExportRelease {
  id: string
  name: string
  datasetName: string
  format: string
  recordCount: number
  version: string
  status: 'completed' | 'in-progress' | 'failed'
  createdBy: string
  createdAt: string
  fileSize: string
}

export const mockExports: ExportRelease[] = [
  {
    id: 'exp-001',
    name: 'Pedestrian Detection v2.8',
    datasetName: 'Pedestrian Detection',
    format: 'COCO JSON',
    recordCount: 25_600,
    version: '2.8.0',
    status: 'completed',
    createdBy: 'Sarah Chen',
    createdAt: '2026-03-25T23:00:00Z',
    fileSize: '1.2 GB',
  },
  {
    id: 'exp-002',
    name: 'Urban Scenes Q1 Checkpoint',
    datasetName: 'Urban Scenes 2026-Q1',
    format: 'COCO JSON',
    recordCount: 12_320,
    version: '1.3.0',
    status: 'completed',
    createdBy: 'Sarah Chen',
    createdAt: '2026-03-20T18:00:00Z',
    fileSize: '680 MB',
  },
  {
    id: 'exp-003',
    name: 'Adverse Weather YOLO',
    datasetName: 'Adverse Weather',
    format: 'YOLO',
    recordCount: 3_100,
    version: '0.5.0',
    status: 'in-progress',
    createdBy: 'Marcus Johnson',
    createdAt: '2026-03-26T08:00:00Z',
    fileSize: '—',
  },
  {
    id: 'exp-004',
    name: 'Highway Night v1',
    datasetName: 'Highway Nighttime',
    format: 'Pascal VOC',
    recordCount: 5_840,
    version: '1.0.0',
    status: 'completed',
    createdBy: 'Elena Rodriguez',
    createdAt: '2026-03-18T14:00:00Z',
    fileSize: '420 MB',
  },
]
