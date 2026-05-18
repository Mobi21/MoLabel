import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

interface ProviderHealthOptions {
  providerBaseUrl?: string
  authRef?: string
  modelId?: string
}

export function registerProviderCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const provider = program
    .command('provider')
    .description('Provider discovery and health')

  provider
    .command('list')
    .description('List discovered providers')
    .action(async () => {
      await runProviderList(getRuntimeOptions(program, runtime))
    })

  provider
    .command('scan')
    .description('Trigger provider discovery')
    .action(async () => {
      await runProviderScan(getRuntimeOptions(program, runtime))
    })

  provider
    .command('health <providerType>')
    .description('Check provider health')
    .option(
      '--provider-base-url <url>',
      'Override provider base URL for the health check',
    )
    .option(
      '--auth-ref <env-var>',
      'Override provider auth env var name for the health check',
    )
    .option('--model-id <id>', 'Model identifier to validate')
    .action(async function (this: Command, providerType: string) {
      await runProviderHealth(
        getRuntimeOptions(program, runtime),
        providerType,
        this.opts<ProviderHealthOptions>(),
      )
    })

  provider
    .command('models <providerType>')
    .description('List models for a provider type')
    .action(async (providerType: string) => {
      await runProviderModels(getRuntimeOptions(program, runtime), providerType)
    })

  provider
    .command('hf-auth')
    .description('Check Hugging Face authentication state')
    .action(async () => {
      await runProviderHfAuth(getRuntimeOptions(program, runtime))
    })
}

async function runProviderList(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options)
  const response = await client.getJson('/api/v1/providers')
  await emit(response, outputMode(options))
}

async function runProviderScan(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options)
  const response = await client.postJson('/api/v1/providers/scan', {})
  await emit(response, outputMode(options))
}

async function runProviderHealth(
  options: CliRuntimeOptions,
  providerType: string,
  query: ProviderHealthOptions,
): Promise<void> {
  const client = await requireClient(options)
  const search = new URLSearchParams()
  if (query.providerBaseUrl?.trim()) {
    search.set('base_url', query.providerBaseUrl.trim())
  }
  if (query.authRef?.trim()) {
    search.set('auth_ref', query.authRef.trim())
  }
  if (query.modelId?.trim()) {
    search.set('model_id', query.modelId.trim())
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : ''
  const response = await client.getJson(
    `/api/v1/providers/health/${providerType}${suffix}`,
  )
  await emit(response, outputMode(options))
}

async function runProviderModels(
  options: CliRuntimeOptions,
  providerType: string,
): Promise<void> {
  const client = await requireClient(options)
  const response = await client.getJson(
    `/api/v1/providers/models/${providerType}`,
  )
  await emit(response, outputMode(options))
}

async function runProviderHfAuth(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options)
  const response = await client.getJson('/api/v1/providers/hf/auth')
  await emit(response, outputMode(options))
}
