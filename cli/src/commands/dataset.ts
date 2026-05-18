import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'
import { parse as parseYaml } from 'yaml'

import { emit } from '../output.js'
import { readInputText } from '../artifacts/input.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  detectWorkspaceRoot,
  getRuntimeOptions,
  outputMode,
} from './context.js'

type JsonObject = Record<string, unknown>

export function registerDatasetCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const dataset = program.command('dataset').description('Dataset operations')

  dataset
    .command('list')
    .description('List datasets')
    .action(async () => {
      await runDatasetList(getRuntimeOptions(program, runtime))
    })

  dataset
    .command('get <dataset-id>')
    .description('Get a dataset')
    .action(async (datasetId: string) => {
      await runDatasetGet(getRuntimeOptions(program, runtime), datasetId)
    })

  dataset
    .command('create')
    .description('Create a dataset')
    .option('--file <path>', 'JSON file with the request body')
    .option('--workspace-id <id>', 'Workspace ID override')
    .option('--name <name>')
    .option('--slug <slug>')
    .option('--source-type <type>')
    .option('--description <text>')
    .option('--loader-plugin <plugin>')
    .option('--record-kind <kind>')
    .option('--canonical-id-strategy <strategy>')
    .option('--indexing-mode <mode>')
    .option('--source-config-json <json>')
    .option('--tags-json <json>')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{
        canonicalIdStrategy?: string
        description?: string
        file?: string
        indexingMode?: string
        loaderPlugin?: string
        name?: string
        recordKind?: string
        slug?: string
        sourceConfigJson?: string
        sourceType?: string
        tagsJson?: string
        workspaceId?: string
      }>()
      await runDatasetCreate(
        getRuntimeOptions(program, runtime),
        commandOptions,
      )
    })

  dataset
    .command('import <dataset-id>')
    .description('Import data into a dataset')
    .option('--file <path>', 'JSON file with the request body')
    .option('--source-uri <uri>')
    .option('--mapping-id <id>')
    .option('--options-json <json>')
    .action(async function (this: Command, datasetId: string) {
      const commandOptions = this.opts<{
        file?: string
        mappingId?: string
        optionsJson?: string
        sourceUri?: string
      }>()
      await runDatasetImport(
        getRuntimeOptions(program, runtime),
        datasetId,
        commandOptions,
      )
    })

  dataset
    .command('records <dataset-id>')
    .description('List records in a dataset')
    .action(async (datasetId: string) => {
      await runDatasetRecords(getRuntimeOptions(program, runtime), datasetId)
    })

  dataset
    .command('record <dataset-id> <record-id>')
    .description('Get a record in a dataset')
    .action(async (datasetId: string, recordId: string) => {
      await runDatasetRecord(
        getRuntimeOptions(program, runtime),
        datasetId,
        recordId,
      )
    })

  dataset
    .command('analytics <dataset-id>')
    .description('Show dataset analytics')
    .action(async (datasetId: string) => {
      await runDatasetAnalytics(getRuntimeOptions(program, runtime), datasetId)
    })

  const snapshots = dataset
    .command('snapshots')
    .description('Dataset snapshots')
  snapshots
    .command('list <dataset-id>')
    .description('List snapshots for a dataset')
    .action(async function (this: Command, datasetId: string) {
      await runSnapshotList(getRuntimeOptions(program, runtime), datasetId)
    })
  snapshots
    .command('create <dataset-id>')
    .description('Create a dataset snapshot')
    .option('--file <path>', 'JSON file with the request body')
    .option('--name <name>')
    .option('--description <text>')
    .option('--snapshot-type <type>')
    .action(async function (this: Command, datasetId: string) {
      const commandOptions = this.opts<{
        description?: string
        file?: string
        name?: string
        snapshotType?: string
      }>()
      await runSnapshotCreate(
        getRuntimeOptions(program, runtime),
        datasetId,
        commandOptions,
      )
    })
  snapshots
    .command('diff <dataset-id> <snapshot-id>')
    .description('Compare a snapshot to another snapshot')
    .option('--compare-to <snapshot-id>')
    .action(async function (
      this: Command,
      datasetId: string,
      snapshotId: string,
    ) {
      const commandOptions = this.opts<{ compareTo?: string }>()
      await runSnapshotDiff(
        getRuntimeOptions(program, runtime),
        datasetId,
        snapshotId,
        commandOptions.compareTo,
      )
    })
}

async function runDatasetList(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options, 'dataset list')
  const response = await client.getJson('/api/v1/datasets')
  await emit(response, outputMode(options))
}

async function runDatasetGet(
  options: CliRuntimeOptions,
  datasetId: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset get')
  const response = await client.getJson(`/api/v1/datasets/${datasetId}`)
  await emit(response, outputMode(options))
}

async function runDatasetCreate(
  options: CliRuntimeOptions,
  commandOptions: {
    canonicalIdStrategy?: string
    description?: string
    file?: string
    indexingMode?: string
    loaderPlugin?: string
    name?: string
    recordKind?: string
    slug?: string
    sourceConfigJson?: string
    sourceType?: string
    tagsJson?: string
    workspaceId?: string
  },
): Promise<void> {
  const client = await requireClient(options, 'dataset create')
  let body: JsonObject
  if (commandOptions.file) {
    body = await readJsonFile(commandOptions.file)
  } else {
    body = {
      dataset_name: commandOptions.name,
      dataset_slug: commandOptions.slug,
      workspace_id: await resolveWorkspaceId(
        options,
        commandOptions.workspaceId,
      ),
      source_type: commandOptions.sourceType,
      description: commandOptions.description,
      source_config: parseJsonOption(
        commandOptions.sourceConfigJson,
        'source-config-json',
      ),
      loader_plugin: commandOptions.loaderPlugin,
      record_kind: commandOptions.recordKind,
      canonical_id_strategy: commandOptions.canonicalIdStrategy,
      indexing_mode: commandOptions.indexingMode,
      tags: parseJsonOption(commandOptions.tagsJson, 'tags-json'),
    }
  }

  if (!commandOptions.file) {
    requireField(body, 'dataset_name', 'dataset create')
    requireField(body, 'source_type', 'dataset create')
    if (!body.workspace_id) {
      body.workspace_id = await resolveWorkspaceId(
        options,
        commandOptions.workspaceId,
      )
    }
  } else if (!body.workspace_id) {
    body.workspace_id = await resolveWorkspaceId(
      options,
      commandOptions.workspaceId,
    )
  }

  const response = await client.postJson('/api/v1/datasets', body)
  await emit(response, outputMode(options))
}

async function runDatasetImport(
  options: CliRuntimeOptions,
  datasetId: string,
  commandOptions: {
    file?: string
    mappingId?: string
    optionsJson?: string
    sourceUri?: string
  },
): Promise<void> {
  const client = await requireClient(options, 'dataset import')
  let body: JsonObject
  if (commandOptions.file) {
    body = await readJsonFile(commandOptions.file)
  } else {
    body = {
      source_uri: commandOptions.sourceUri,
      mapping_id: commandOptions.mappingId,
      options: parseJsonOption(commandOptions.optionsJson, 'options-json'),
    }
  }
  if (!commandOptions.file) {
    requireField(body, 'source_uri', 'dataset import')
  }
  const response = await client.postJson(
    `/api/v1/datasets/${datasetId}/import`,
    body,
  )
  await emit(response, outputMode(options))
}

async function runDatasetRecords(
  options: CliRuntimeOptions,
  datasetId: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset records')
  const response = await client.getJson(`/api/v1/datasets/${datasetId}/records`)
  await emit(response, outputMode(options))
}

async function runDatasetRecord(
  options: CliRuntimeOptions,
  datasetId: string,
  recordId: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset record')
  const response = await client.getJson(
    `/api/v1/datasets/${datasetId}/records/${recordId}`,
  )
  await emit(response, outputMode(options))
}

async function runDatasetAnalytics(
  options: CliRuntimeOptions,
  datasetId: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset analytics')
  const response = await client.getJson(
    `/api/v1/datasets/${datasetId}/analytics`,
  )
  await emit(response, outputMode(options))
}

async function runSnapshotList(
  options: CliRuntimeOptions,
  datasetId: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset snapshots list')
  const response = await client.getJson(
    `/api/v1/datasets/${datasetId}/snapshots`,
  )
  await emit(response, outputMode(options))
}

async function runSnapshotCreate(
  options: CliRuntimeOptions,
  datasetId: string,
  commandOptions: {
    description?: string
    file?: string
    name?: string
    snapshotType?: string
  },
): Promise<void> {
  const client = await requireClient(options, 'dataset snapshots create')
  let body: JsonObject
  if (commandOptions.file) {
    body = await readJsonFile(commandOptions.file)
  } else {
    body = {
      name: commandOptions.name,
      description: commandOptions.description,
      snapshot_type: commandOptions.snapshotType,
    }
  }
  if (!commandOptions.file) {
    requireField(body, 'name', 'dataset snapshots create')
  }
  const response = await client.postJson(
    `/api/v1/datasets/${datasetId}/snapshots`,
    body,
  )
  await emit(response, outputMode(options))
}

async function runSnapshotDiff(
  options: CliRuntimeOptions,
  datasetId: string,
  snapshotId: string,
  compareTo?: string,
): Promise<void> {
  const client = await requireClient(options, 'dataset snapshots diff')
  const path = new URL(
    `/api/v1/datasets/${datasetId}/snapshots/${snapshotId}/diff`,
    'http://local',
  )
  if (compareTo) {
    path.searchParams.set('compare_to', compareTo)
  }
  const response = await client.getJson(path.pathname + path.search)
  await emit(response, outputMode(options))
}

async function resolveWorkspaceId(
  options: CliRuntimeOptions,
  explicitWorkspaceId?: string,
): Promise<string> {
  if (explicitWorkspaceId) {
    return explicitWorkspaceId
  }

  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.manifestPath) {
    throw new Error(
      'workspace_id is required when no workspace manifest is available',
    )
  }

  const manifest = await readFile(workspace.manifestPath, 'utf8')
  const parsed = parseYaml(manifest) as { workspace_id?: string } | null
  const workspaceId = parsed?.workspace_id
  if (!workspaceId) {
    throw new Error(
      'workspace_id is required; pass --workspace-id or bootstrap a workspace',
    )
  }
  return workspaceId
}

async function readJsonFile(path: string): Promise<JsonObject> {
  const raw = await readInputText({
    file: resolve(path),
    text: undefined,
    errorMessage: `Unable to read JSON file: ${path}`,
  })
  try {
    return JSON.parse(raw) as JsonObject
  } catch (error) {
    throw new Error(`Invalid JSON in ${path}: ${(error as Error).message}`)
  }
}

function parseJsonOption(value: string | undefined, flagName: string): unknown {
  if (!value) {
    return undefined
  }
  try {
    return JSON.parse(value) as unknown
  } catch (error) {
    throw new Error(
      `Invalid JSON for --${flagName}: ${(error as Error).message}`,
    )
  }
}

function requireField(
  body: JsonObject,
  key: string,
  commandName: string,
): void {
  if (
    !(key in body) ||
    body[key] === undefined ||
    body[key] === null ||
    body[key] === ''
  ) {
    throw new Error(`${commandName} requires ${key}`)
  }
}

async function requireClient(
  options: CliRuntimeOptions,
  commandName: string,
): Promise<NonNullable<Awaited<ReturnType<typeof buildClient>>>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client
}
