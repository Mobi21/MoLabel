import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import {
  API_PORT,
  API_URL,
  REPO,
  WEB_URL,
  e2eRoot,
  seedPath,
  type Seed,
} from './env'

const CLI = join(REPO, 'cli', 'dist', 'bin', 'molabel.js')
const FIXTURE = join(
  REPO,
  'fixtures',
  'smoke-no-key',
  'synthetic_support_tickets.jsonl',
)
const PYTHON = join(
  REPO,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
const LABEL_FIELDS = [
  {
    name: 'intent',
    field_type: 'categorical',
    required: true,
    options: ['refund', 'bug', 'shipping', 'other'],
  },
  { name: 'urgent', field_type: 'bool', required: true },
  {
    name: 'tags',
    field_type: 'multi_select',
    required: false,
    options: ['billing', 'account', 'delivery', 'hardware'],
  },
  { name: 'note', field_type: 'text', required: false },
]

/** Every provider key and MoLabel setting unset, as on a fresh machine. */
function keylessEnv(overrides: Record<string, string>): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const [name, value] of Object.entries(process.env)) {
    if (
      !name.endsWith('_API_KEY') &&
      !name.endsWith('_AUTH_TOKEN') &&
      !name.startsWith('MOLABEL_') &&
      name !== 'ANTHROPIC_BASE_URL'
    ) {
      env[name] = value
    }
  }
  return { ...env, ...overrides }
}

function stop(server: ChildProcess) {
  if (server.pid === undefined || server.exitCode !== null) return
  // On Windows the venv python.exe starts the real interpreter as a child.
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/T', '/F', '/PID', String(server.pid)])
  } else {
    server.kill('SIGTERM')
  }
}

async function waitForHealth(server: ChildProcess) {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`backend exited with code ${String(server.exitCode)}`)
    }
    try {
      if ((await fetch(`${API_URL}/health`)).ok) return
    } catch {
      // not listening yet
    }
    await new Promise((done) => setTimeout(done, 300))
  }
  throw new Error('backend did not answer /health within 60s')
}

function cli(cwd: string, env: NodeJS.ProcessEnv) {
  return (...args: string[]): Record<string, unknown> => {
    const run = spawnSync('node', [CLI, ...args], {
      cwd,
      env,
      encoding: 'utf8',
    })
    if (run.status !== 0) {
      throw new Error(
        `molabel ${args.join(' ')} exited ${String(run.status)}\n${run.stdout}\n${run.stderr}`,
      )
    }
    return JSON.parse(run.stdout) as Record<string, unknown>
  }
}

interface Step {
  step_id: string
  step_type: string
  config: Record<string, unknown>
}

async function seedWorkspace(workspace: string, config: string): Promise<Seed> {
  const molabel = cli(
    workspace,
    keylessEnv({ MOLABEL_BASE_URL: API_URL, XDG_CONFIG_HOME: config }),
  )
  const bootstrap = molabel(
    'workspace',
    'bootstrap',
    '.',
    '--workspace-name',
    'GUI e2e',
  ) as { workspace: { workspace_id: string } }
  const workspaceId = bootstrap.workspace.workspace_id

  mkdirSync(join(workspace, 'data'))
  copyFileSync(FIXTURE, join(workspace, 'data', 'tickets.jsonl'))
  const dataset = molabel(
    'dataset',
    'create',
    '--name',
    'Support tickets',
    '--slug',
    'support-tickets',
    '--source-type',
    'file',
    '--loader-plugin',
    'jsonl',
    '--record-kind',
    'text',
    '--canonical-id-strategy',
    'source_record_id',
    '--indexing-mode',
    'projection',
  ) as { dataset_id: string }
  molabel(
    'dataset',
    'import',
    dataset.dataset_id,
    '--source-uri',
    'data/tickets.jsonl',
  )

  function reviewQueue(
    slug: string,
    title: string,
    policy: string,
    overlap: number,
  ): string {
    const schema = molabel(
      'task-schema',
      'create',
      '--slug',
      slug,
      '--task-type',
      'classification',
      '--title',
      title,
      '--instructions',
      "Pick the ticket's intent and mark urgent tickets.",
      '--blind-review-policy',
      policy,
      '--label-fields-json',
      JSON.stringify(LABEL_FIELDS),
    ) as { task_schema_id: string }
    const template = molabel(
      'workflow',
      'create',
      '--template',
      'quick_agentic_label',
      '--provider',
      'offline',
      '--dataset',
      dataset.dataset_id,
      '--task-schema',
      schema.task_schema_id,
      '--slug',
      `${slug}-template`,
    ) as { steps: Step[] }
    const steps = template.steps
      .filter((s) =>
        ['data_ingest', 'agent_run', 'human_review'].includes(s.step_type),
      )
      .map((s) =>
        s.step_type === 'human_review'
          ? { ...s, config: { ...s.config, overlap_count: overlap } }
          : s,
      )
    const file = join(workspace, `${slug}.workflow.json`)
    writeFileSync(file, JSON.stringify({ name: title, slug, steps }))
    molabel('workflow', 'create', '--file', file)
    const run = molabel('workflow', 'run', slug) as {
      status: string
      current_step_id: string
    }
    if (run.status !== 'paused') {
      throw new Error(`workflow ${slug} did not pause at review: ${run.status}`)
    }
    const queues = molabel('queue', 'list', '--workspace-id', workspaceId) as {
      items: { queue_id: string; task_schema_id: string }[]
    }
    const queue = queues.items.find(
      (q) => q.task_schema_id === schema.task_schema_id,
    )
    if (!queue) throw new Error(`no queue for ${slug}`)
    return queue.queue_id
  }

  const overlap = reviewQueue(
    'ticket-triage',
    'Ticket triage',
    'show_agent_outputs',
    2,
  )
  const blind = reviewQueue(
    'ticket-triage-blind',
    'Ticket triage, blind',
    'hide_agent_outputs_by_default',
    1,
  )
  const thin = reviewQueue(
    'ticket-triage-thin',
    'Ticket triage, three copies',
    'show_agent_outputs',
    3,
  )

  molabel(
    'gold',
    'create',
    'ticket-gold',
    '--task-schema',
    'ticket-triage',
    '--name',
    'Ticket triage gold',
  )

  const reviewers = molabel('session', 'list-reviewers') as {
    items: { id: string; display_name: string }[]
  }
  const first = reviewers.items[0]
  if (!first) throw new Error('bootstrap made no reviewer')
  const created = await fetch(`${API_URL}/api/v1/reviewer-profiles`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      display_name: 'Reviewer 2',
      workspace_id: workspaceId,
    }),
  })
  if (!created.ok) throw new Error(`reviewer 2: HTTP ${String(created.status)}`)
  const second = ((await created.json()) as { id: string }).id

  return {
    workspaceId,
    workspace,
    goldSet: 'ticket-gold',
    reviewers: { first: first.id, second },
    queues: { overlap, blind, thin },
    proposals: {
      'ticket-1': { intent: 'refund', urgent: false },
      'ticket-2': { intent: 'bug', urgent: true },
      'ticket-3': { intent: 'shipping', urgent: false },
      'ticket-4': { intent: 'refund', urgent: false },
      'ticket-5': { intent: 'refund', urgent: false },
      'ticket-6': { intent: 'bug', urgent: false },
    },
  }
}

/**
 * Start the real backend on a temp data folder with no API keys, and seed a
 * workspace through the CLI: a dataset, three task schemas, three offline
 * workflows run to review (one with overlap_count 2, one blind, and one with
 * overlap_count 3 for the two reviewers), and an empty gold set for the first
 * schema.
 */
export default async function globalSetup() {
  if (!existsSync(CLI)) {
    throw new Error(`${CLI} is missing; run npm ci && npm run build in cli/`)
  }
  const root = e2eRoot()
  const [launch, data, workspace, config] = [
    'launch',
    'data',
    'workspace',
    'config',
  ].map((name) => join(root, name)) as [string, string, string, string]
  for (const dir of [launch, data, workspace, config]) {
    mkdirSync(dir, { recursive: true })
  }
  const server = spawn(
    PYTHON,
    [
      '-m',
      'uvicorn',
      'molabel.app.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      String(API_PORT),
    ],
    {
      cwd: launch,
      // The run's folder is under the OS temp folder, outside home on CI. The
      // preview server proxies /api and passes the page's Origin through.
      env: keylessEnv({
        MOLABEL_DATA_DIR: data,
        MOLABEL_ALLOWED_WORKSPACE_ROOTS: root,
        MOLABEL_ALLOWED_ORIGINS: WEB_URL,
      }),
      stdio: 'ignore',
    },
  )
  try {
    await waitForHealth(server)
    writeFileSync(
      seedPath(),
      JSON.stringify(await seedWorkspace(workspace, config)),
    )
  } catch (error) {
    stop(server)
    throw error
  }

  return () => {
    stop(server)
    const written = readdirSync(launch)
    if (written.length > 0) {
      throw new Error(
        `the backend wrote into its launch folder: ${written.join(', ')}`,
      )
    }
    rmSync(root, { recursive: true, force: true, maxRetries: 5 })
  }
}
