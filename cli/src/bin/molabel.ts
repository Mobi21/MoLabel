#!/usr/bin/env node

import { runCli } from '../cli.js'

const result = await runCli(process.argv)
process.exitCode = result.exitCode
