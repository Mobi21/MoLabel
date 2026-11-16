import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { afterEach, describe, expect, it } from 'vitest'

import { runCli } from '../src/cli.js'

const tempDirs: string[] = []

afterEach(async () => {
  const dirs = tempDirs.splice(0)
  await Promise.all(
    dirs.map(async (dir) => {
      await rm(dir)
    }),
  )
})

async function rm(path: string): Promise<void> {
  const { rm } = await import('node:fs/promises')
  await rm(path, { recursive: true, force: true })
}

async function captureCliJson(
  argv: string[],
): Promise<{ exitCode: number; json: unknown }> {
  const chunks: string[] = []
  const originalWrite = process.stdout.write.bind(process.stdout)
  process.stdout.write = ((chunk: string | Uint8Array) => {
    chunks.push(
      typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'),
    )
    return true
  })

  try {
    const result = await runCli(argv)
    const stdout = chunks.join('').trim()
    return {
      exitCode: result.exitCode,
      json: stdout ? (JSON.parse(stdout) as unknown) : null,
    }
  } finally {
    process.stdout.write = originalWrite
  }
}

async function createPack(): Promise<{
  root: string
  runA: string
  runB: string
  copied: string
}> {
  const root = await mkdtemp(join(tmpdir(), 'molabel-benchmark-cli-'))
  tempDirs.push(root)
  const authority = join(root, 'authority')
  const sourceRaw = join(root, 'source', 'raw')
  const runA = join(root, 'runs', 'run-a')
  const runB = join(root, 'runs', 'run-b')
  const copied = join(root, 'copied-source')
  await Promise.all([
    mkdir(join(authority, 'gold', 'paper-direct'), { recursive: true }),
    mkdir(join(authority, 'gold', 'molabel-operated'), { recursive: true }),
    mkdir(join(authority, 'humans', 'gold'), { recursive: true }),
    mkdir(join(authority, 'humans', 'flawed'), { recursive: true }),
    mkdir(join(authority, 'eval'), { recursive: true }),
    mkdir(sourceRaw, { recursive: true }),
    mkdir(runA, { recursive: true }),
    mkdir(runB, { recursive: true }),
  ])

  await Promise.all([
    writeFile(
      join(authority, 'manifest.yaml'),
      [
        'benchmark_id: demo-grounded',
        'name: Demo Grounded Benchmark',
        'track: grounded',
        'profiles:',
        '  - canonical',
        '  - operator-primary',
        '  - smoke',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'packaging.yaml'),
      [
        'benchmark_id: demo-grounded',
        'redistribution_status: allowed',
        'source_policy: vendored',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'paper.yaml'),
      [
        'benchmark_id: demo-grounded',
        'paper_title: Demo Paper',
        'paper_url: https://example.com/paper',
        'citation: Example et al. (2026)',
        'publication_year: 2026',
        'dataset_name: Demo Dataset',
        'dataset_url: https://example.com/dataset',
        'dataset_license: CC BY 4.0',
        'redistribution_status: allowed',
        'task_summary: Demo task summary.',
        'original_task_definition: Demo task definition.',
        'original_metrics:',
        '  - accuracy',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'scenario.yaml'),
      [
        'benchmark_id: demo-grounded',
        'track: grounded',
        'name: Demo Grounded Benchmark',
        'description: Demo benchmark for CLI tests.',
        'raw_format: jsonl',
        'source_path: source/raw/test.jsonl',
        'loader_plugin: molabel.loaders.jsonl',
        'record_id_field: record_id',
        'paper_metadata_path: authority/paper.yaml',
        'label_map_path: authority/label-map.yaml',
        'metrics_path: authority/metrics.yaml',
        'baselines_path: authority/baselines.yaml',
        'operator_path: authority/operator.yaml',
        'evaluation_modes:',
        '  - model',
        '  - workflow',
        '  - operator',
        'scoring_variants:',
        '  - paper_direct',
        '  - molabel_operated',
        'default_model_profile:',
        '  provider_type: anthropic',
        '  provider_name: MiniMax',
        '  model_identifier: MiniMax-M2.7-highspeed',
        '  sdk_stack: anthropic_sdk',
        '  agent_role: proposer',
        'profiles:',
        '  - canonical',
        '  - operator-primary',
        '  - smoke',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'label-map.yaml'),
      [
        'benchmark_id: demo-grounded',
        'record_id_field: record_id',
        'dataset_label_fields:',
        '  - label',
        'target_label_fields:',
        '  - label',
        'field_mappings:',
        '  - dataset_field: label',
        '    target_field: label',
        '    mapping:',
        '      positive: positive',
        '      negative: negative',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'metrics.yaml'),
      [
        'benchmark_id: demo-grounded',
        'aggregation: weighted_mean',
        'primary_metric_id: accuracy',
        'metrics:',
        '  - metric_id: accuracy',
        '    name: Accuracy',
        '    metric_type: accuracy',
        '    modes:',
        '      - operator',
        '    variants:',
        '      - molabel_operated',
        'tax_definitions: []',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'baselines.yaml'),
      [
        'benchmark_id: demo-grounded',
        'baselines:',
        '  - baseline_id: floor',
        '    name: Floor Baseline',
        '    source: molabel_local',
        '    mode: operator',
        '    variant: molabel_operated',
        '    stage: operator_reviewed',
        '    split_id: test',
        '    metrics:',
        '      accuracy: 0.5',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(authority, 'operator.yaml'),
      [
        'benchmark_id: demo-grounded',
        'goal: Demo operator goal',
        'current_labeling_engine: MiniMax 2.7 highspeed',
        'label_quality_weight: 0.7',
        'checklist_weight: 0.3',
        'blocking_check_ids:',
        '  - uses_public_surfaces',
        'checks:',
        '  - check_id: uses_public_surfaces',
        '    phase: setup',
        '    description: Uses public CLI surfaces only.',
        '',
      ].join('\n'),
    ),
    writeFile(
      join(sourceRaw, 'test.jsonl'),
      '{"record_id":"r1","text":"alpha"}\n',
    ),
    writeFile(
      join(root, 'authority', 'gold', 'paper-direct', 'test.jsonl'),
      '{"record_id":"r1","labels":{"label":"positive"}}\n',
    ),
    writeFile(
      join(root, 'authority', 'gold', 'molabel-operated', 'test.jsonl'),
      '{"record_id":"r1","labels":{"label":"positive"}}\n',
    ),
    writeFile(
      join(runA, 'summary.json'),
      JSON.stringify(
        {
          benchmark_id: 'demo-grounded',
          run_id: 'run-a',
          stage: 'operator_reviewed',
          mode: 'operator',
          variant: 'molabel_operated',
          record_count: 1,
          overall_score: 0.75,
          primary_metric_id: 'accuracy',
          metrics: [{ metric_id: 'accuracy', value: 0.75 }],
          tax_breakdown: [{ tax_id: 'operator_tax', value: 0.05 }],
          notes: ['baseline run'],
        },
        null,
        2,
      ),
    ),
    writeFile(
      join(runB, 'summary.json'),
      JSON.stringify(
        {
          benchmark_id: 'demo-grounded',
          run_id: 'run-b',
          stage: 'operator_reviewed',
          mode: 'operator',
          variant: 'molabel_operated',
          record_count: 1,
          overall_score: 0.9,
          primary_metric_id: 'accuracy',
          metrics: [{ metric_id: 'accuracy', value: 0.9 }],
          tax_breakdown: [{ tax_id: 'operator_tax', value: 0.02 }],
          notes: ['candidate run'],
        },
        null,
        2,
      ),
    ),
  ])

  return { root, runA, runB, copied }
}

describe('benchmark cli', () => {
  it('inspects a benchmark pack', async () => {
    const pack = await createPack()
    const result = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'inspect',
      pack.root,
    ])
    expect(result.exitCode).toBe(0)
    const payload = result.json as {
      benchmark: { benchmark_id: string; layout: string }
    }
    expect(payload.benchmark.benchmark_id).toBe('demo-grounded')
    expect(payload.benchmark.layout).toBe('authority')
  })

  it('verifies a benchmark pack and fails on missing required files', async () => {
    const pack = await createPack()
    const success = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'verify-pack',
      pack.root,
    ])
    expect(success.exitCode).toBe(0)
    const successPayload = success.json as {
      ok: boolean
      warnings: string[]
    }
    expect(successPayload.ok).toBe(true)
    expect(successPayload.warnings).toContain(
      'No reference-workspace/ found; this is acceptable but limits baseline debugging.',
    )

    const strict = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'verify-pack',
      pack.root,
      '--strict',
    ])
    expect(strict.exitCode).toBe(1)
    const strictPayload = strict.json as {
      ok: boolean
      errors: string[]
      warnings: string[]
    }
    expect(strictPayload.ok).toBe(false)
    expect(strictPayload.errors).toContain(
      'No reference-workspace/ found; this is acceptable but limits baseline debugging.',
    )
    expect(strictPayload.warnings).toEqual([])

    const invalidRoot = await mkdtemp(
      join(tmpdir(), 'molabel-benchmark-invalid-'),
    )
    tempDirs.push(invalidRoot)
    await mkdir(join(invalidRoot, 'authority'), { recursive: true })
    await writeFile(
      join(invalidRoot, 'authority', 'scenario.yaml'),
      [
        'benchmark_id: invalid',
        'name: Invalid Benchmark',
        'track: grounded',
        '',
      ].join('\n'),
    )
    const failure = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'verify-pack',
      invalidRoot,
    ])
    expect(failure.exitCode).toBe(1)
    const failurePayload = failure.json as { ok: boolean; errors: string[] }
    expect(failurePayload.ok).toBe(false)
    expect(failurePayload.errors.length).toBeGreaterThan(0)
  })

  it('fetches source payload into an output directory', async () => {
    const pack = await createPack()
    const result = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'fetch-source',
      pack.root,
      '--output-dir',
      pack.copied,
    ])
    expect(result.exitCode).toBe(0)
    const payload = result.json as {
      copied: boolean
      files: Array<{ path: string }>
    }
    expect(payload.copied).toBe(true)
    expect(payload.files.map((file) => file.path)).toContain('test.jsonl')
  })

  it('scores, reports, and compares runs', async () => {
    const pack = await createPack()
    const score = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'score',
      pack.root,
      '--run',
      pack.runA,
    ])
    expect(score.exitCode).toBe(0)
    const scorePayload = score.json as {
      summary: {
        run_id: string
        stage: string
        overall_score: number
        primary_metric_value: number
        baseline_comparisons: Array<{
          baseline_id: string
          delta: number
          relation: string
        }>
      }
    }
    expect(scorePayload.summary.run_id).toBe('run-a')
    expect(scorePayload.summary.stage).toBe('operator_reviewed')
    expect(scorePayload.summary.overall_score).toBe(0.75)
    expect(scorePayload.summary.primary_metric_value).toBe(0.75)
    expect(scorePayload.summary.baseline_comparisons).toEqual([
      expect.objectContaining({
        baseline_id: 'floor',
        delta: 0.25,
        relation: 'ahead',
      }),
    ])

    const report = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'report',
      pack.root,
      '--run',
      pack.runA,
    ])
    expect(report.exitCode).toBe(0)
    const reportPayload = report.json as { markdown: string }
    expect(reportPayload.markdown).toContain('Grounded Benchmark Report')
    expect(reportPayload.markdown).toContain('run-a')
    expect(reportPayload.markdown).toContain('Stage: operator_reviewed')
    expect(reportPayload.markdown).toContain('## Baselines')
    expect(reportPayload.markdown).toContain('floor: 0.5 (ahead by 0.25)')

    const compare = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'compare',
      pack.root,
      '--baseline',
      pack.runA,
      '--candidate',
      pack.runB,
    ])
    expect(compare.exitCode).toBe(0)
    const comparePayload = compare.json as {
      comparison: {
        compatible: boolean
        overall_score_delta: number
        metric_deltas: Array<{ metric_id: string }>
        warnings: string[]
      }
    }
    expect(comparePayload.comparison.compatible).toBe(true)
    expect(comparePayload.comparison.overall_score_delta).toBe(0.15)
    expect(
      comparePayload.comparison.metric_deltas.map((metric) => metric.metric_id),
    ).toContain('accuracy')
    expect(comparePayload.comparison.warnings).toEqual([])
  })

  it('flags incompatible run comparisons', async () => {
    const pack = await createPack()
    const runC = join(pack.root, 'runs', 'run-c')
    await mkdir(runC, { recursive: true })
    await writeFile(
      join(runC, 'summary.json'),
      JSON.stringify(
        {
          benchmark_id: 'demo-grounded',
          run_id: 'run-c',
          stage: 'workflow_reviewed',
          mode: 'workflow',
          variant: 'molabel_operated',
          record_count: 1,
          overall_score: 0.8,
          primary_metric_id: 'accuracy',
          metrics: [{ metric_id: 'accuracy', value: 0.8 }],
          tax_breakdown: [],
          notes: [],
        },
        null,
        2,
      ),
    )

    const compare = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'compare',
      pack.root,
      '--baseline',
      pack.runA,
      '--candidate',
      runC,
    ])
    expect(compare.exitCode).toBe(0)
    const comparePayload = compare.json as {
      comparison: { compatible: boolean; warnings: string[] }
    }
    expect(comparePayload.comparison.compatible).toBe(false)
    expect(comparePayload.comparison.warnings).toContain(
      'Comparing different stages: operator_reviewed vs workflow_reviewed.',
    )
    expect(comparePayload.comparison.warnings).toContain(
      'Comparing different modes: operator vs workflow.',
    )
  })

  it('rejects packs with an undeclared primary metric', async () => {
    const root = await mkdtemp(
      join(tmpdir(), 'molabel-benchmark-invalid-primary-'),
    )
    tempDirs.push(root)
    const authority = join(root, 'authority')
    await mkdir(authority, { recursive: true })

    await Promise.all([
      writeFile(
        join(authority, 'scenario.yaml'),
        [
          'benchmark_id: invalid-primary',
          'track: grounded',
          'name: Invalid Primary',
          'description: Broken metrics wiring.',
          'raw_format: jsonl',
          'source_path: source/raw/test.jsonl',
          'loader_plugin: molabel.loaders.jsonl',
          'paper_metadata_path: authority/paper.yaml',
          'label_map_path: authority/label-map.yaml',
          'metrics_path: authority/metrics.yaml',
          'baselines_path: authority/baselines.yaml',
          'operator_path: authority/operator.yaml',
          'default_model_profile:',
          '  provider_type: anthropic',
          '  provider_name: MiniMax',
          '  model_identifier: MiniMax-M2.7-highspeed',
          '  sdk_stack: anthropic_sdk',
          '',
        ].join('\n'),
      ),
      writeFile(
        join(authority, 'paper.yaml'),
        [
          'benchmark_id: invalid-primary',
          'paper_title: Invalid Primary Paper',
          'paper_url: https://example.com/paper',
          'citation: Example et al. (2026)',
          'publication_year: 2026',
          'dataset_name: Invalid Dataset',
          'dataset_url: https://example.com/dataset',
          'dataset_license: CC BY 4.0',
          'redistribution_status: allowed',
          'task_summary: Invalid benchmark.',
          'original_task_definition: Invalid benchmark.',
          '',
        ].join('\n'),
      ),
      writeFile(
        join(authority, 'label-map.yaml'),
        [
          'benchmark_id: invalid-primary',
          'record_id_field: record_id',
          'field_mappings: []',
          '',
        ].join('\n'),
      ),
      writeFile(
        join(authority, 'metrics.yaml'),
        [
          'benchmark_id: invalid-primary',
          'aggregation: weighted_mean',
          'primary_metric_id: missing_metric',
          'metrics:',
          '  - metric_id: accuracy',
          '    name: Accuracy',
          '    metric_type: accuracy',
          '    modes:',
          '      - operator',
          '    variants:',
          '      - molabel_operated',
          '',
        ].join('\n'),
      ),
      writeFile(
        join(authority, 'baselines.yaml'),
        ['benchmark_id: invalid-primary', 'baselines: []', ''].join('\n'),
      ),
      writeFile(
        join(authority, 'operator.yaml'),
        [
          'benchmark_id: invalid-primary',
          'goal: Invalid operator goal',
          'checks:',
          '  - check_id: uses_public_surfaces',
          '    phase: setup',
          '    description: Uses public CLI surfaces only.',
          '',
        ].join('\n'),
      ),
    ])

    const result = await captureCliJson([
      'node',
      'molabel',
      'benchmark',
      'verify-pack',
      root,
    ])
    expect(result.exitCode).toBe(1)
    const payload = result.json as { ok: boolean; errors: string[] }
    expect(payload.ok).toBe(false)
    expect(payload.errors).toContain(
      'metrics.yaml primary_metric_id missing_metric is not declared in metrics[]',
    )
  })
})
