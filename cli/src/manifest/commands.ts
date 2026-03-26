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
      name: 'workflow list',
      group: 'workflow',
      description: 'List workflows from the backend or local workspace',
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
