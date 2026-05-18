import { cp, mkdir, readFile, readdir, stat } from 'node:fs/promises'
import { basename, resolve, relative, isAbsolute, join } from 'node:path'
import { createHash } from 'node:crypto'

import type { Command } from 'commander'
import { parse as parseYaml } from 'yaml'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode } from './context.js'

type JsonObject = Record<string, unknown>

interface BenchmarkPackSummary {
  benchmark_id: string | null
  name: string | null
  description: string | null
  track: string | null
  layout: 'authority' | 'legacy' | 'missing'
  root: string
  authority_root: string | null
  reference_workspace_root: string | null
  scenario_path: string | null
  paper_path: string | null
  packaging_path: string | null
  label_map_path: string | null
  metrics_path: string | null
  baselines_path: string | null
  operator_path: string | null
  source_root: string | null
  profile_names: string[]
  warnings: string[]
}

interface BenchmarkPackLoadResult {
  pack: BenchmarkPackSummary
  scenario: JsonObject | null
  paper: JsonObject | null
  packaging: JsonObject | null
  labelMap: JsonObject | null
  metrics: JsonObject | null
  baselines: JsonObject | null
  operator: JsonObject | null
}

interface BenchmarkRunSummary {
  benchmark_id: string | null
  run_id: string | null
  stage: string | null
  mode: string | null
  variant: string | null
  record_count: number | null
  overall_score: number | null
  primary_metric_id: string | null
  metrics: Array<Record<string, unknown>>
  tax_breakdown: Array<Record<string, unknown>>
  notes: string[]
  path: string
}

export function registerBenchmarkCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const benchmark = program
    .command('benchmark')
    .description('Benchmark operations')

  benchmark
    .command('facts <workflow-execution-id>')
    .description('Show persisted benchmark run facts for a workflow execution')
    .action(async (workflowExecutionId: string) => {
      await runBenchmarkFacts(
        getRuntimeOptions(program, runtime),
        workflowExecutionId,
      )
    })

  benchmark
    .command('inspect <pack-root>')
    .description(
      'Inspect a benchmark authority pack or legacy grounded fixture',
    )
    .action(async (packRoot: string) => {
      await runBenchmarkInspect(getRuntimeOptions(program, runtime), packRoot)
    })

  benchmark
    .command('verify-pack <pack-root>')
    .description('Validate a benchmark pack')
    .option('--strict', 'Treat warnings as errors')
    .action(async function (this: Command, packRoot: string) {
      const options = this.opts<{ strict?: boolean }>()
      await runBenchmarkVerifyPack(
        getRuntimeOptions(program, runtime),
        packRoot,
        options.strict ?? false,
      )
    })

  benchmark
    .command('fetch-source <pack-root>')
    .description('Materialize or summarize the benchmark source payload')
    .option('--output-dir <path>', 'Copy source payload to this directory')
    .action(async function (this: Command, packRoot: string) {
      const options = this.opts<{ outputDir?: string }>()
      await runBenchmarkFetchSource(
        getRuntimeOptions(program, runtime),
        packRoot,
        options.outputDir,
      )
    })

  benchmark
    .command('score <pack-root>')
    .description('Summarize a benchmark run against a pack')
    .option('--run <path>', 'Run directory containing summary.json', '.')
    .action(async function (this: Command, packRoot: string) {
      const options = this.opts<{ run?: string }>()
      await runBenchmarkScore(
        getRuntimeOptions(program, runtime),
        packRoot,
        options.run ?? '.',
      )
    })

  benchmark
    .command('report <pack-root>')
    .description('Render a benchmark report')
    .option('--run <path>', 'Run directory containing summary.json', '.')
    .action(async function (this: Command, packRoot: string) {
      const options = this.opts<{ run?: string }>()
      await runBenchmarkReport(
        getRuntimeOptions(program, runtime),
        packRoot,
        options.run ?? '.',
      )
    })

  benchmark
    .command('compare <pack-root>')
    .description('Compare two benchmark runs')
    .option('--baseline <path>', 'Baseline run directory', '.')
    .option('--candidate <path>', 'Candidate run directory', '.')
    .action(async function (this: Command, packRoot: string) {
      const options = this.opts<{ baseline?: string; candidate?: string }>()
      await runBenchmarkCompare(
        getRuntimeOptions(program, runtime),
        packRoot,
        options.baseline ?? '.',
        options.candidate ?? '.',
      )
    })
}

async function runBenchmarkInspect(
  options: CliRuntimeOptions,
  packRoot: string,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  await emit({ benchmark: pack.pack }, outputMode(options))
}

async function runBenchmarkFacts(
  options: CliRuntimeOptions,
  workflowExecutionId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'benchmark facts')
  const response = await client.getJson(
    `/api/v1/cli/benchmark-run-facts/${encodeURIComponent(workflowExecutionId)}`,
  )
  await emit(response, outputMode(options))
}

async function runBenchmarkVerifyPack(
  options: CliRuntimeOptions,
  packRoot: string,
  strict: boolean,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  const result = validateBenchmarkPack(pack)
  if (strict && result.warnings.length > 0) {
    result.errors.push(...result.warnings)
    result.warnings = []
  }

  await emit(
    {
      benchmark: pack.pack,
      ok: result.errors.length === 0,
      errors: result.errors,
      warnings: result.warnings,
    },
    outputMode(options),
  )

  if (result.errors.length > 0) {
    process.exitCode = 1
  }
}

async function runBenchmarkFetchSource(
  options: CliRuntimeOptions,
  packRoot: string,
  outputDir?: string,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  const sourceRoot = await resolveSourceRoot(pack)

  if (!sourceRoot) {
    await emit(
      {
        benchmark: pack.pack,
        copied: false,
        warnings: [
          'No source/raw directory found. Inspect authority/bootstrap/fetch.yaml for source acquisition steps.',
        ],
      },
      outputMode(options),
    )
    return
  }

  const destination = resolveOutputDir(
    pack.pack.root,
    outputDir,
    'source-materialized',
  )
  await mkdir(destination, { recursive: true })
  const sourceStats = await stat(sourceRoot)
  if (sourceStats.isDirectory()) {
    await cp(sourceRoot, destination, { recursive: true })
  } else {
    await cp(sourceRoot, join(destination, basename(sourceRoot)))
  }

  await emit(
    {
      benchmark: pack.pack,
      copied: true,
      source_root: sourceRoot,
      destination,
      files: await listFiles(destination),
    },
    outputMode(options),
  )
}

async function runBenchmarkScore(
  options: CliRuntimeOptions,
  packRoot: string,
  runRoot: string,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  const run = await loadBenchmarkRun(runRoot)
  const score = buildScoreEnvelope(pack, run)
  await emit(score, outputMode(options))
}

async function runBenchmarkReport(
  options: CliRuntimeOptions,
  packRoot: string,
  runRoot: string,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  const run = await loadBenchmarkRun(runRoot)
  const markdown = renderBenchmarkReport(pack, run)
  const payload = {
    benchmark: pack.pack,
    run,
    markdown,
  }

  if (outputMode(options) === 'raw') {
    await emit(markdown, 'raw')
    return
  }

  await emit(payload, outputMode(options))
}

async function runBenchmarkCompare(
  options: CliRuntimeOptions,
  packRoot: string,
  baselineRoot: string,
  candidateRoot: string,
): Promise<void> {
  const pack = await loadBenchmarkPack(packRoot)
  const baseline = await loadBenchmarkRun(baselineRoot)
  const candidate = await loadBenchmarkRun(candidateRoot)

  const comparison = compareBenchmarkRuns(pack, baseline, candidate)
  await emit(comparison, outputMode(options))
}

async function requireBackendClient(
  options: CliRuntimeOptions,
  commandName: string,
): Promise<NonNullable<Awaited<ReturnType<typeof buildClient>>>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client
}

async function loadBenchmarkPack(
  packRoot: string,
): Promise<BenchmarkPackLoadResult> {
  const root = resolve(packRoot)
  const authorityRoot = (await pathExists(join(root, 'authority')))
    ? join(root, 'authority')
    : null
  const legacyRoot = (await pathExists(join(root, 'workbench', 'benchmarks')))
    ? join(root, 'workbench', 'benchmarks')
    : null

  const layout: BenchmarkPackSummary['layout'] =
    authorityRoot !== null
      ? 'authority'
      : legacyRoot !== null
        ? 'legacy'
        : 'missing'
  const scenarioPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'scenario.yaml') : null,
    legacyRoot ? join(legacyRoot, 'scenario.yaml') : null,
  )
  const packagingPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'packaging.yaml') : null,
    null,
  )
  const paperPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'paper.yaml') : null,
    legacyRoot ? join(legacyRoot, 'paper.yaml') : null,
  )
  const labelMapPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'label-map.yaml') : null,
    legacyRoot ? join(legacyRoot, 'label-map.yaml') : null,
  )
  const metricsPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'metrics.yaml') : null,
    legacyRoot ? join(legacyRoot, 'metrics.yaml') : null,
  )
  const baselinesPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'baselines.yaml') : null,
    legacyRoot ? join(legacyRoot, 'baselines.yaml') : null,
  )
  const operatorPath = await firstExistingPath(
    authorityRoot ? join(authorityRoot, 'operator.yaml') : null,
    legacyRoot ? join(legacyRoot, 'operator.yaml') : null,
  )

  const scenario = await readYamlObject(scenarioPath)
  const paper = await readYamlObject(paperPath)
  const packaging = await readYamlObject(packagingPath)
  const labelMap = await readYamlObject(labelMapPath)
  const metrics = await readYamlObject(metricsPath)
  const baselines = await readYamlObject(baselinesPath)
  const operator = await readYamlObject(operatorPath)

  const benchmarkId =
    readString(scenario?.benchmark_id) ??
    readString(paper?.benchmark_id) ??
    readString(packaging?.benchmark_id) ??
    null
  const name =
    readString(scenario?.name) ?? readString(paper?.paper_title) ?? null
  const description =
    readString(scenario?.description) ?? readString(paper?.task_summary) ?? null
  const track =
    readString(scenario?.track) ?? readString(packaging?.track) ?? null
  const sourcePath = readString(scenario?.source_path) ?? null

  const referenceWorkspaceRoot = (await pathExists(
    join(root, 'reference-workspace'),
  ))
    ? join(root, 'reference-workspace')
    : null
  const sourceRoot = sourcePath
    ? await resolveRelativePath(root, sourcePath)
    : await resolveSourceRoot({
        root,
        sourcePath: null,
        authorityRoot,
      })

  const profileNames = collectProfileNames(packaging, scenario)
  const warnings: string[] = []
  if (layout === 'legacy') {
    warnings.push(
      'Legacy workspace-first layout detected; treat as transitional.',
    )
  }
  if (
    authorityRoot &&
    !(await pathExists(join(authorityRoot, 'manifest.yaml')))
  ) {
    warnings.push(
      'Missing authority/manifest.yaml; verify-pack will fall back to scenario metadata.',
    )
  }

  return {
    pack: {
      benchmark_id: benchmarkId,
      name,
      description,
      track,
      layout,
      root,
      authority_root: authorityRoot,
      reference_workspace_root: referenceWorkspaceRoot,
      scenario_path: scenarioPath,
      paper_path: paperPath,
      packaging_path: packagingPath,
      label_map_path: labelMapPath,
      metrics_path: metricsPath,
      baselines_path: baselinesPath,
      operator_path: operatorPath,
      source_root: sourceRoot,
      profile_names: profileNames,
      warnings,
    },
    scenario,
    paper,
    packaging,
    labelMap,
    metrics,
    baselines,
    operator,
  }
}

function validateBenchmarkPack(pack: BenchmarkPackLoadResult): {
  errors: string[]
  warnings: string[]
} {
  const errors: string[] = []
  const warnings = [...pack.pack.warnings]
  const benchmarkId = pack.pack.benchmark_id

  if (!pack.pack.benchmark_id) {
    errors.push('benchmark_id is required')
  }
  if (!pack.pack.name) {
    errors.push('benchmark name is required')
  }
  if (!pack.pack.scenario_path) {
    errors.push('scenario.yaml is required')
  }
  if (!pack.paper) {
    errors.push('paper.yaml is required')
  } else {
    for (const key of [
      'paper_url',
      'dataset_url',
      'dataset_license',
      'task_summary',
    ]) {
      if (!readString(pack.paper[key])) {
        errors.push(`paper.yaml missing ${key}`)
      }
    }
  }
  if (!pack.labelMap) {
    errors.push('label-map.yaml is required')
  }
  if (!pack.metrics) {
    errors.push('metrics.yaml is required')
  }
  if (!pack.baselines) {
    errors.push('baselines.yaml is required')
  }
  if (!pack.operator) {
    errors.push('operator.yaml is required')
  }

  for (const [label, payload] of [
    ['scenario.yaml', pack.scenario],
    ['paper.yaml', pack.paper],
    ['label-map.yaml', pack.labelMap],
    ['metrics.yaml', pack.metrics],
    ['baselines.yaml', pack.baselines],
    ['operator.yaml', pack.operator],
  ] satisfies Array<[string, JsonObject | null]>) {
    const fileBenchmarkId = readString(payload?.benchmark_id)
    if (benchmarkId && fileBenchmarkId && fileBenchmarkId !== benchmarkId) {
      errors.push(
        `${label} benchmark_id ${fileBenchmarkId} does not match ${benchmarkId}`,
      )
    }
  }

  const metricIds = metricDefinitionIdsFromPack(pack)
  const primaryMetricId = readString(pack.metrics?.primary_metric_id)
  if (!primaryMetricId) {
    errors.push('metrics.yaml missing primary_metric_id')
  } else if (!metricIds.includes(primaryMetricId)) {
    errors.push(
      `metrics.yaml primary_metric_id ${primaryMetricId} is not declared in metrics[]`,
    )
  }
  if (metricIds.length === 0) {
    errors.push('metrics.yaml must declare at least one metric')
  }

  const baselineEntries = baselineEntriesFromPack(pack)
  if (baselineEntries.length === 0) {
    warnings.push(
      'No baselines declared; benchmark score output will lack baseline context.',
    )
  } else if (
    primaryMetricId &&
    !baselineEntries.some((entry) => entry.metrics.has(primaryMetricId))
  ) {
    warnings.push(
      `No baseline declares the primary metric ${primaryMetricId}; baseline comparisons will be incomplete.`,
    )
  }

  if (pack.operator) {
    const checks = Array.isArray(pack.operator.checks)
      ? pack.operator.checks
      : []
    const checkIds = new Set(
      checks
        .map((check) =>
          check && typeof check === 'object' && !Array.isArray(check)
            ? readString((check as JsonObject).check_id)
            : null,
        )
        .filter((checkId): checkId is string => checkId !== null),
    )
    const blockingCheckIds = Array.isArray(pack.operator.blocking_check_ids)
      ? pack.operator.blocking_check_ids
          .map((value) => readString(value))
          .filter((value): value is string => value !== null)
      : []
    for (const checkId of blockingCheckIds) {
      if (!checkIds.has(checkId)) {
        errors.push(
          `operator.yaml blocking_check_ids references missing check ${checkId}`,
        )
      }
    }
  }

  const sourceRoot = pack.pack.source_root
  if (!sourceRoot) {
    warnings.push(
      'No source payload found; source acquisition may be bootstrap-only.',
    )
  } else if (
    !(sourceRoot.endsWith('source/raw') || sourceRoot.includes('/source/raw/'))
  ) {
    warnings.push(
      'Source path is not a source/raw tree; verify authority-pack projection.',
    )
  }

  if (pack.pack.layout === 'authority' && !pack.pack.reference_workspace_root) {
    warnings.push(
      'No reference-workspace/ found; this is acceptable but limits baseline debugging.',
    )
  }

  return { errors, warnings }
}

async function loadBenchmarkRun(runRoot: string): Promise<BenchmarkRunSummary> {
  const root = resolve(runRoot)
  const summaryPath = (await pathExists(join(root, 'summary.json')))
    ? join(root, 'summary.json')
    : root.endsWith('.json')
      ? root
      : null
  if (!summaryPath) {
    throw new Error(`Run summary not found: ${runRoot}`)
  }

  const parsed = await readYamlObject(summaryPath)
  if (!parsed) {
    throw new Error(`Unable to read run summary: ${summaryPath}`)
  }

  return {
    benchmark_id: readString(parsed.benchmark_id),
    run_id: readString(parsed.run_id),
    stage: readString(parsed.stage),
    mode: readString(parsed.mode),
    variant: readString(parsed.variant),
    record_count: readNumber(parsed.record_count),
    overall_score: readNumber(parsed.overall_score),
    primary_metric_id: readString(parsed.primary_metric_id),
    metrics: Array.isArray(parsed.metrics)
      ? (parsed.metrics as Array<Record<string, unknown>>)
      : [],
    tax_breakdown: Array.isArray(parsed.tax_breakdown)
      ? (parsed.tax_breakdown as Array<Record<string, unknown>>)
      : [],
    notes: Array.isArray(parsed.notes)
      ? parsed.notes.map((value) => String(value))
      : [],
    path: summaryPath,
  }
}

function buildScoreEnvelope(
  pack: BenchmarkPackLoadResult,
  run: BenchmarkRunSummary,
): JsonObject {
  const metricMap = new Map<string, number>()
  for (const metric of run.metrics) {
    const metricId = readString(metric.metric_id)
    const value = readNumber(metric.value)
    if (metricId && value !== null) {
      metricMap.set(metricId, value)
    }
  }

  const taxMap = new Map<string, number>()
  for (const tax of run.tax_breakdown) {
    const taxId = readString(tax.tax_id)
    const value = readNumber(tax.value)
    if (taxId && value !== null) {
      taxMap.set(taxId, value)
    }
  }

  const primaryMetricId = resolvePrimaryMetricId(pack, run)
  const baselineComparisons = buildBaselineComparisons(
    pack,
    run,
    primaryMetricId,
  )
  const warnings = summarizeRunWarnings(pack.pack, run)

  return {
    benchmark: pack.pack,
    run,
    summary: {
      benchmark_id: run.benchmark_id ?? pack.pack.benchmark_id,
      run_id: run.run_id,
      stage: run.stage,
      mode: run.mode,
      variant: run.variant,
      record_count: run.record_count,
      overall_score: run.overall_score,
      primary_metric_id: primaryMetricId,
      primary_metric_value: primaryMetricId
        ? (metricMap.get(primaryMetricId) ?? null)
        : null,
      metric_values: Object.fromEntries(metricMap.entries()),
      tax_values: Object.fromEntries(taxMap.entries()),
      baseline_comparisons: baselineComparisons,
      notes: run.notes,
      warnings,
    },
  }
}

function renderBenchmarkReport(
  pack: BenchmarkPackLoadResult,
  run: BenchmarkRunSummary,
): string {
  const primaryMetricId = resolvePrimaryMetricId(pack, run)
  const baselineComparisons = buildBaselineComparisons(
    pack,
    run,
    primaryMetricId,
  )
  const warnings = summarizeRunWarnings(pack.pack, run)
  const lines: string[] = []
  lines.push(`# Grounded Benchmark Report`)
  lines.push(``)
  lines.push(`- Benchmark: ${pack.pack.benchmark_id ?? 'unknown'}`)
  lines.push(`- Name: ${pack.pack.name ?? 'unknown'}`)
  lines.push(`- Layout: ${pack.pack.layout}`)
  lines.push(`- Run: ${run.run_id ?? 'unknown'}`)
  lines.push(`- Stage: ${run.stage ?? 'unknown'}`)
  lines.push(`- Mode: ${run.mode ?? 'unknown'}`)
  lines.push(`- Variant: ${run.variant ?? 'unknown'}`)
  lines.push(`- Overall Score: ${formatNumber(run.overall_score)}`)
  lines.push(`- Primary Metric: ${primaryMetricId ?? 'unknown'}`)
  lines.push(``)
  lines.push(`## Metrics`)
  for (const metric of run.metrics) {
    lines.push(
      `- ${readString(metric.metric_id) ?? 'metric'}: ${formatNumber(readNumber(metric.value))}`,
    )
  }
  if (run.metrics.length === 0) {
    lines.push(`- None`)
  }
  lines.push(``)
  lines.push(`## Taxes`)
  for (const tax of run.tax_breakdown) {
    lines.push(
      `- ${readString(tax.tax_id) ?? 'tax'}: ${formatNumber(readNumber(tax.value))}`,
    )
  }
  if (run.tax_breakdown.length === 0) {
    lines.push(`- None`)
  }
  if (baselineComparisons.length > 0) {
    lines.push(``)
    lines.push(`## Baselines`)
    for (const comparison of baselineComparisons) {
      lines.push(
        `- ${comparison.baseline_id}: ${formatNumber(comparison.baseline_value)} (${comparison.relation} by ${formatNumber(comparison.delta)})`,
      )
    }
  }
  if (warnings.length > 0) {
    lines.push(``)
    lines.push(`## Warnings`)
    for (const warning of warnings) {
      lines.push(`- ${warning}`)
    }
  }
  if (run.notes.length > 0) {
    lines.push(``)
    lines.push(`## Notes`)
    for (const note of run.notes) {
      lines.push(`- ${note}`)
    }
  }
  return lines.join('\n')
}

function compareBenchmarkRuns(
  pack: BenchmarkPackLoadResult,
  baseline: BenchmarkRunSummary,
  candidate: BenchmarkRunSummary,
): JsonObject {
  const baselineMetrics = metricMapFromRun(baseline)
  const candidateMetrics = metricMapFromRun(candidate)
  const metricDeltas: Array<{
    metric_id: string
    baseline: number
    candidate: number
    delta: number
  }> = []
  for (const metricId of new Set([
    ...baselineMetrics.keys(),
    ...candidateMetrics.keys(),
  ])) {
    const baselineValue = baselineMetrics.get(metricId) ?? 0
    const candidateValue = candidateMetrics.get(metricId) ?? 0
    metricDeltas.push({
      metric_id: metricId,
      baseline: baselineValue,
      candidate: candidateValue,
      delta: round(candidateValue - baselineValue),
    })
  }

  const baselineTaxes = taxMapFromRun(baseline)
  const candidateTaxes = taxMapFromRun(candidate)
  const taxDeltas: Array<{
    tax_id: string
    baseline: number
    candidate: number
    delta: number
  }> = []
  for (const taxId of new Set([
    ...baselineTaxes.keys(),
    ...candidateTaxes.keys(),
  ])) {
    const baselineValue = baselineTaxes.get(taxId) ?? 0
    const candidateValue = candidateTaxes.get(taxId) ?? 0
    taxDeltas.push({
      tax_id: taxId,
      baseline: baselineValue,
      candidate: candidateValue,
      delta: round(candidateValue - baselineValue),
    })
  }

  const warnings = summarizeComparisonWarnings(pack.pack, baseline, candidate)

  return {
    benchmark: pack.pack,
    baseline,
    candidate,
    comparison: {
      compatible: warnings.length === 0,
      overall_score_baseline: baseline.overall_score,
      overall_score_candidate: candidate.overall_score,
      overall_score_delta: round(
        (candidate.overall_score ?? 0) - (baseline.overall_score ?? 0),
      ),
      metric_deltas: metricDeltas.sort((left, right) =>
        left.metric_id.localeCompare(right.metric_id),
      ),
      tax_deltas: taxDeltas.sort((left, right) =>
        left.tax_id.localeCompare(right.tax_id),
      ),
      warnings,
    },
  }
}

function resolvePrimaryMetricId(
  pack: BenchmarkPackLoadResult,
  run: BenchmarkRunSummary,
): string | null {
  return run.primary_metric_id ?? readString(pack.metrics?.primary_metric_id)
}

function buildBaselineComparisons(
  pack: BenchmarkPackLoadResult,
  run: BenchmarkRunSummary,
  primaryMetricId: string | null,
): Array<{
  baseline_id: string
  baseline_name: string
  baseline_value: number
  run_value: number
  delta: number
  relation: 'ahead' | 'behind' | 'tied'
}> {
  if (!primaryMetricId) {
    return []
  }

  const runMetrics = metricMapFromRun(run)
  const runValue = runMetrics.get(primaryMetricId)
  if (runValue === undefined) {
    return []
  }

  return baselineEntriesFromPack(pack)
    .filter(
      (baseline) =>
        baseline.mode === run.mode && baseline.variant === run.variant,
    )
    .filter(
      (baseline) => baseline.stage === null || baseline.stage === run.stage,
    )
    .map((baseline) => {
      const baselineValue = baseline.metrics.get(primaryMetricId)
      if (baselineValue === undefined) {
        return null
      }
      const delta = round(runValue - baselineValue)
      const relation: 'ahead' | 'behind' | 'tied' =
        delta > 0 ? 'ahead' : delta < 0 ? 'behind' : 'tied'
      return {
        baseline_id: baseline.baseline_id,
        baseline_name: baseline.name,
        baseline_value: baselineValue,
        run_value: runValue,
        delta,
        relation,
      }
    })
    .filter(
      (comparison): comparison is NonNullable<typeof comparison> =>
        comparison !== null,
    )
    .sort((left, right) => left.baseline_id.localeCompare(right.baseline_id))
}

function metricMapFromRun(run: BenchmarkRunSummary): Map<string, number> {
  const metrics = new Map<string, number>()
  for (const metric of run.metrics) {
    const metricId = readString(metric.metric_id)
    const value = readNumber(metric.value)
    if (metricId && value !== null) {
      metrics.set(metricId, value)
    }
  }
  return metrics
}

function taxMapFromRun(run: BenchmarkRunSummary): Map<string, number> {
  const taxes = new Map<string, number>()
  for (const tax of run.tax_breakdown) {
    const taxId = readString(tax.tax_id)
    const value = readNumber(tax.value)
    if (taxId && value !== null) {
      taxes.set(taxId, value)
    }
  }
  return taxes
}

function collectProfileNames(
  packaging: JsonObject | null,
  scenario: JsonObject | null,
): string[] {
  const profiles = new Set<string>()
  for (const source of [packaging, scenario]) {
    if (!source) {
      continue
    }
    const directProfiles = source.profiles
    if (Array.isArray(directProfiles)) {
      for (const profile of directProfiles) {
        if (typeof profile === 'string' && profile.trim()) {
          profiles.add(profile.trim())
        }
      }
    }
    const benchmarkProfiles = source.benchmark_profiles
    if (Array.isArray(benchmarkProfiles)) {
      for (const profile of benchmarkProfiles) {
        if (typeof profile === 'string' && profile.trim()) {
          profiles.add(profile.trim())
        }
      }
    }
  }
  return [...profiles].sort()
}

function baselineEntriesFromPack(pack: BenchmarkPackLoadResult): Array<{
  baseline_id: string
  name: string
  mode: string | null
  variant: string | null
  stage: string | null
  metrics: Map<string, number>
}> {
  const entries = Array.isArray(pack.baselines?.baselines)
    ? pack.baselines.baselines
    : []
  return entries
    .map((entry) => {
      if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
        return null
      }
      const record = entry as JsonObject
      const rawMetrics = record.metrics
      const metrics = new Map<string, number>()
      if (
        rawMetrics &&
        typeof rawMetrics === 'object' &&
        !Array.isArray(rawMetrics)
      ) {
        for (const [metricId, value] of Object.entries(rawMetrics)) {
          const numeric = readNumber(value)
          if (numeric !== null) {
            metrics.set(metricId, numeric)
          }
        }
      }
      const baselineId = readString(record.baseline_id)
      if (!baselineId) {
        return null
      }
      return {
        baseline_id: baselineId,
        name: readString(record.name) ?? baselineId,
        mode: readString(record.mode),
        variant: readString(record.variant),
        stage: readString(record.stage),
        metrics,
      }
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null)
}

function metricDefinitionIdsFromPack(pack: BenchmarkPackLoadResult): string[] {
  const metrics = Array.isArray(pack.metrics?.metrics)
    ? pack.metrics.metrics
    : []
  return metrics
    .map((metric) =>
      metric && typeof metric === 'object' && !Array.isArray(metric)
        ? readString((metric as JsonObject).metric_id)
        : null,
    )
    .filter((metricId): metricId is string => metricId !== null)
}

function summarizeRunWarnings(
  pack: BenchmarkPackSummary,
  run: BenchmarkRunSummary,
): string[] {
  const warnings: string[] = []
  if (
    pack.benchmark_id &&
    run.benchmark_id &&
    pack.benchmark_id !== run.benchmark_id
  ) {
    warnings.push(
      `Run benchmark_id ${run.benchmark_id} does not match pack benchmark_id ${pack.benchmark_id}.`,
    )
  }
  if (!run.stage) {
    warnings.push(
      'Run summary is missing stage; stage-aware reporting will be incomplete.',
    )
  }
  return warnings
}

function summarizeComparisonWarnings(
  pack: BenchmarkPackSummary,
  baseline: BenchmarkRunSummary,
  candidate: BenchmarkRunSummary,
): string[] {
  const warnings = [
    ...summarizeRunWarnings(pack, baseline),
    ...summarizeRunWarnings(pack, candidate),
  ]
  if (
    baseline.benchmark_id &&
    candidate.benchmark_id &&
    baseline.benchmark_id !== candidate.benchmark_id
  ) {
    warnings.push(
      `Comparing different benchmark ids: ${baseline.benchmark_id} vs ${candidate.benchmark_id}.`,
    )
  }
  if (baseline.stage !== candidate.stage) {
    warnings.push(
      `Comparing different stages: ${baseline.stage ?? 'unknown'} vs ${candidate.stage ?? 'unknown'}.`,
    )
  }
  if (baseline.mode !== candidate.mode) {
    warnings.push(
      `Comparing different modes: ${baseline.mode ?? 'unknown'} vs ${candidate.mode ?? 'unknown'}.`,
    )
  }
  if (baseline.variant !== candidate.variant) {
    warnings.push(
      `Comparing different variants: ${baseline.variant ?? 'unknown'} vs ${candidate.variant ?? 'unknown'}.`,
    )
  }
  return [...new Set(warnings)]
}

async function resolveSourceRoot(
  pack:
    | BenchmarkPackLoadResult
    | { root: string; sourcePath: string | null; authorityRoot: string | null },
): Promise<string | null> {
  const root = 'pack' in pack ? pack.pack.root : pack.root
  const sourcePath = 'pack' in pack ? pack.pack.source_root : pack.sourcePath

  const candidates = [
    sourcePath,
    join(root, 'source', 'raw'),
    join(root, 'data', 'raw'),
    join(root, 'workbench', 'benchmarks', 'splits'),
  ]
  for (const candidate of candidates) {
    if (candidate && (await pathExists(candidate))) {
      return candidate
    }
  }
  return null
}

async function resolveRelativePath(
  root: string,
  value: string,
): Promise<string | null> {
  const absolute = isAbsolute(value) ? value : resolve(root, value)
  return (await pathExists(absolute)) ? absolute : null
}

function resolveOutputDir(
  root: string,
  outputDir: string | undefined,
  defaultName: string,
): string {
  if (outputDir && outputDir.trim()) {
    return resolve(outputDir)
  }
  return join(root, '.molabel', defaultName)
}

async function listFiles(
  root: string,
): Promise<Array<{ path: string; sha256: string }>> {
  const entries: Array<{ path: string; sha256: string }> = []
  await walkFiles(root, async (filePath) => {
    entries.push({
      path: relative(root, filePath),
      sha256: await sha256File(filePath),
    })
  })
  return entries.sort((left, right) => left.path.localeCompare(right.path))
}

async function walkFiles(
  root: string,
  onFile: (filePath: string) => Promise<void>,
): Promise<void> {
  const entries = await readdir(root, { withFileTypes: true }).catch(() => [])
  for (const entry of entries) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) {
      await walkFiles(path, onFile)
      continue
    }
    if (entry.isFile()) {
      await onFile(path)
    }
  }
}

async function sha256File(path: string): Promise<string> {
  const content = await readFile(path)
  return createHash('sha256').update(content).digest('hex')
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await stat(path)
    return true
  } catch {
    return false
  }
}

async function firstExistingPath(
  ...paths: Array<string | null>
): Promise<string | null> {
  for (const candidate of paths) {
    if (candidate && (await pathExists(candidate))) {
      return candidate
    }
  }
  return null
}

async function readYamlObject(path: string | null): Promise<JsonObject | null> {
  if (!path) {
    return null
  }
  const raw = await readFile(path, 'utf8')
  const parsed = parseYaml(raw) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null
  }
  return parsed as JsonObject
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (
    typeof value === 'string' &&
    value.trim() &&
    !Number.isNaN(Number(value))
  ) {
    return Number(value)
  }
  return null
}

function round(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000
}

function formatNumber(value: number | null): string {
  if (value === null) {
    return 'n/a'
  }
  return String(round(value))
}
