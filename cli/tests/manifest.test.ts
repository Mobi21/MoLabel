import { describe, expect, it } from 'vitest'

import { COMMAND_MANIFEST } from '../src/manifest/commands.js'
import { WORKFLOW_TEMPLATES } from '../src/manifest/workflow-templates.js'

describe('manifests', () => {
  it('exposes the expected command groups', () => {
    const commandNames = COMMAND_MANIFEST.commands.map((command) => command.name)
    expect(commandNames).toContain('doctor')
    expect(commandNames).toContain('benchmark inspect')
    expect(commandNames).toContain('provider list')
    expect(commandNames).toContain('provider health')
    expect(commandNames).toContain('model-profile create')
    expect(commandNames).toContain('model-profile test')
    expect(commandNames).toContain('benchmark verify-pack')
    expect(commandNames).toContain('benchmark fetch-source')
    expect(commandNames).toContain('benchmark score')
    expect(commandNames).toContain('benchmark report')
    expect(commandNames).toContain('benchmark compare')
    expect(commandNames).toContain('dataset create')
    expect(commandNames).toContain('workflow create')
    expect(commandNames).toContain('queue claim')
    expect(commandNames).toContain('review submit')
    expect(commandNames).toContain('adjudication detect')
    expect(commandNames).toContain('adjudication build')
    expect(commandNames).toContain('workflow advance')
    expect(commandNames).toContain('release create')
    expect(commandNames).toContain('artifact write')
    expect(commandNames).toContain('skill install')
  })

  it('exposes built-in workflow templates', () => {
    const templateIds = WORKFLOW_TEMPLATES.templates.map((template) => template.id)
    expect(templateIds).toContain('human_in_the_loop')
    expect(templateIds).toContain('iterative_refinement')
  })
})
