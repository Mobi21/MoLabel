import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

export function registerCalibrationCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const calibration = program
    .command('calibration')
    .description('Calibration queues, which check reviewers against a gold set')

  calibration
    .command('report <queue-id>')
    .description(
      "Score each reviewer of a calibration queue against its gold set: accuracy, exact match and Cohen's kappa, per field",
    )
    .action(async (queueId: string) => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'calibration report')
      await emit(
        await client.getJson(
          `/api/v1/calibration/queues/${encodeURIComponent(queueId)}`,
        ),
        outputMode(options),
      )
    })
}
