import type { CommandManifestDocument } from '../types.js'

export const COMMAND_MANIFEST: CommandManifestDocument = {
  version: '0.1.0',
  package: '@molabel/cli',
  commands: [
    {
      name: 'doctor',
      group: 'core',
      description: 'Check local workspace and backend reachability',
      flags: [
        { name: '--base-url', description: 'Backend base URL' },
        { name: '--workspace', description: 'Workspace root override' },
        { name: '--json', description: 'Force JSON output' },
      ],
    },
    {
      name: 'status',
      group: 'core',
      description: 'Show workspace and backend status',
      flags: [
        { name: '--base-url', description: 'Backend base URL' },
        { name: '--workspace', description: 'Workspace root override' },
      ],
    },
    {
      name: 'manifest',
      group: 'core',
      description: 'Print the machine-readable CLI manifest',
      flags: [{ name: '--json', description: 'Output JSON' }],
    },
    {
      name: 'session whoami',
      group: 'session',
      description: 'Show the current reviewer profile',
      flags: [{ name: '--base-url', description: 'Backend base URL' }],
    },
    {
      name: 'session list-reviewers',
      group: 'session',
      description: 'List reviewer profiles for the current workspace',
    },
    {
      name: 'session select',
      group: 'session',
      description: 'Create a CLI session for a reviewer profile',
    },
    {
      name: 'session switch',
      group: 'session',
      description: 'Switch the active CLI session to a different reviewer',
    },
    {
      name: 'workspace detect',
      group: 'workspace',
      description: 'Detect the nearest MoLabel workspace',
      flags: [{ name: 'path', description: 'Optional search root' }],
    },
    {
      name: 'workspace bootstrap',
      group: 'workspace',
      description: 'Bootstrap a workspace through the backend',
      flags: [{ name: 'path', description: 'Workspace root to bootstrap' }],
    },
    {
      name: 'provider list',
      group: 'provider',
      description: 'List discovered providers',
    },
    {
      name: 'provider scan',
      group: 'provider',
      description: 'Trigger provider discovery',
    },
    {
      name: 'provider health',
      group: 'provider',
      description: 'Check provider health',
      flags: [
        { name: '--provider-base-url', description: 'Override provider base URL' },
        { name: '--auth-ref', description: 'Override provider auth env var name' },
      ],
    },
    {
      name: 'provider models',
      group: 'provider',
      description: 'List models for a provider type',
    },
    {
      name: 'provider hf-auth',
      group: 'provider',
      description: 'Check Hugging Face authentication state',
    },
    {
      name: 'model-profile list',
      group: 'model-profile',
      description: 'List model profiles',
      flags: [{ name: '--provider-type', description: 'Provider type filter' }],
    },
    {
      name: 'model-profile create',
      group: 'model-profile',
      description: 'Create a model profile',
      flags: [
        { name: '--file', description: 'JSON body file' },
        { name: '--body-text', description: 'JSON body text' },
      ],
    },
    {
      name: 'model-profile get',
      group: 'model-profile',
      description: 'Get a model profile',
    },
    {
      name: 'model-profile update',
      group: 'model-profile',
      description: 'Update a model profile',
      flags: [
        { name: '--file', description: 'JSON body file' },
        { name: '--body-text', description: 'JSON body text' },
      ],
    },
    {
      name: 'model-profile delete',
      group: 'model-profile',
      description: 'Delete a model profile',
    },
    {
      name: 'model-profile test',
      group: 'model-profile',
      description: 'Test model profile connectivity',
    },
    {
      name: 'benchmark inspect',
      group: 'benchmark',
      description: 'Inspect a benchmark authority pack or legacy grounded fixture',
    },
    {
      name: 'benchmark verify-pack',
      group: 'benchmark',
      description: 'Validate a benchmark pack',
      flags: [{ name: '--strict', description: 'Treat warnings as errors' }],
    },
    {
      name: 'benchmark fetch-source',
      group: 'benchmark',
      description: 'Materialize or summarize the benchmark source payload',
      flags: [{ name: '--output-dir', description: 'Copy source payload to this directory' }],
    },
    {
      name: 'benchmark score',
      group: 'benchmark',
      description: 'Summarize a benchmark run against a pack',
      flags: [{ name: '--run', description: 'Run directory containing summary.json' }],
    },
    {
      name: 'benchmark report',
      group: 'benchmark',
      description: 'Render a benchmark report',
      flags: [{ name: '--run', description: 'Run directory containing summary.json' }],
    },
    {
      name: 'benchmark compare',
      group: 'benchmark',
      description: 'Compare two benchmark runs',
      flags: [
        { name: '--baseline', description: 'Baseline run directory' },
        { name: '--candidate', description: 'Candidate run directory' },
      ],
    },
    {
      name: 'dataset list',
      group: 'dataset',
      description: 'List datasets',
    },
    {
      name: 'dataset create',
      group: 'dataset',
      description: 'Create a dataset',
    },
    {
      name: 'dataset import',
      group: 'dataset',
      description: 'Import data into a dataset',
    },
    {
      name: 'task-schema list',
      group: 'task-schema',
      description: 'List task schemas',
    },
    {
      name: 'task-schema create',
      group: 'task-schema',
      description: 'Create a task schema',
    },
    {
      name: 'prompt list',
      group: 'prompt',
      description: 'List prompt templates',
    },
    {
      name: 'prompt create',
      group: 'prompt',
      description: 'Create a prompt template',
    },
    {
      name: 'workflow list',
      group: 'workflow',
      description: 'List workflows from the backend or local workspace',
    },
    {
      name: 'workflow create',
      group: 'workflow',
      description: 'Create a workflow definition from JSON or YAML',
      flags: [
        { name: '--file', description: 'Workflow definition file' },
        { name: '--workspace-id', description: 'Workspace ID override' },
        { name: '--name', description: 'Workflow name' },
        { name: '--slug', description: 'Workflow slug' },
        { name: '--description', description: 'Workflow description' },
        { name: '--file-path', description: 'Workspace file path' },
      ],
    },
    {
      name: 'workflow run',
      group: 'workflow',
      description: 'Execute a workflow by slug or identifier',
    },
    {
      name: 'workflow templates',
      group: 'workflow',
      description: 'Show built-in workflow templates',
    },
    {
      name: 'workflow executions',
      group: 'workflow',
      description: 'List executions for a workflow',
    },
    {
      name: 'workflow execution',
      group: 'workflow',
      description: 'Get workflow execution detail',
    },
    {
      name: 'workflow advance',
      group: 'workflow',
      description: 'Advance a paused workflow step',
    },
    {
      name: 'workflow pause',
      group: 'workflow',
      description: 'Pause a workflow execution',
    },
    {
      name: 'workflow cancel',
      group: 'workflow',
      description: 'Cancel a workflow execution',
    },
    {
      name: 'queue status',
      group: 'queue',
      description: 'Show queue status',
    },
    {
      name: 'queue claim',
      group: 'queue',
      description: 'Claim the next available review task',
    },
    {
      name: 'review submit',
      group: 'review',
      description: 'Submit a review task',
    },
    {
      name: 'review reveal-ai',
      group: 'review',
      description: 'Reveal attached agent output for a review task',
    },
    {
      name: 'review skip',
      group: 'review',
      description: 'Skip a claimed review task and release it back to the queue',
    },
    {
      name: 'review release',
      group: 'review',
      description: 'Release a claimed review task without submitting',
    },
    {
      name: 'review draft',
      group: 'review',
      description: 'Save draft labels for a claimed review task',
    },
    {
      name: 'review correct',
      group: 'review',
      description: 'Submit a correction that supersedes a previous review',
    },
    {
      name: 'adjudication queue',
      group: 'adjudication',
      description: 'Inspect the adjudication queue',
    },
    {
      name: 'adjudication detect',
      group: 'adjudication',
      description: 'Detect disagreements from review events',
    },
    {
      name: 'adjudication build',
      group: 'adjudication',
      description: 'Detect disagreements and build an adjudication queue',
    },
    {
      name: 'adjudication resolve',
      group: 'adjudication',
      description: 'Resolve an adjudication item',
    },
    {
      name: 'agent-run list',
      group: 'agent-run',
      description: 'List agent runs',
    },
    {
      name: 'agent-run start',
      group: 'agent-run',
      description: 'Start an agent run',
    },
    {
      name: 'agent-run compare',
      group: 'agent-run',
      description: 'Start a comparison run',
    },
    {
      name: 'quality dashboard',
      group: 'quality',
      description: 'Show quality dashboard metrics',
    },
    {
      name: 'export list',
      group: 'export',
      description: 'List exports',
    },
    {
      name: 'export create',
      group: 'export',
      description: 'Create an export',
    },
    {
      name: 'release list',
      group: 'release',
      description: 'List releases',
    },
    {
      name: 'release create',
      group: 'release',
      description: 'Create a release',
    },
    {
      name: 'artifact read',
      group: 'artifact',
      description: 'Read a canonical artifact from disk',
    },
    {
      name: 'artifact diff',
      group: 'artifact',
      description: 'Compare a canonical artifact to a candidate',
    },
    {
      name: 'artifact write',
      group: 'artifact',
      description: 'Write a canonical artifact safely',
    },
    {
      name: 'skill install',
      group: 'skill',
      description: 'Install the bundled skill package',
    },
  ],
}
