import { describe, expect, it } from 'vitest'

import { COMMAND_MANIFEST } from '../src/manifest/commands.js'
import { WORKFLOW_TEMPLATES } from '../src/manifest/workflow-templates.js'

describe('manifests', () => {
  it('exposes the expected command groups', () => {
    const commandNames = COMMAND_MANIFEST.commands.map(
      (command) => command.name,
    )
    expect(commandNames).toContain('doctor')
    expect(commandNames).toContain('benchmark facts')
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
    expect(commandNames).toContain('workflow new')
    expect(commandNames).toContain('queue claim')
    expect(commandNames).toContain('review submit')
    expect(commandNames).toContain('adjudication detect')
    expect(commandNames).toContain('adjudication build')
    expect(commandNames).toContain('agent-run inspect')
    expect(commandNames).toContain('workflow advance')
    expect(commandNames).toContain('workspace diff')
    expect(commandNames).toContain('workspace apply')
    expect(commandNames).toContain('workspace reject')
    expect(commandNames).toContain('release create')
    expect(commandNames).toContain('release certify')
    expect(commandNames).toContain('artifact write')
    expect(commandNames).toContain('artifact propose')
    expect(commandNames).toContain('artifact trace')
    expect(commandNames).toContain('artifact decide')
    expect(commandNames).toContain('audit timeline')
    expect(commandNames).toContain('audit explain')
    expect(commandNames).toContain('run failures')
    expect(commandNames).toContain('run retry')
    expect(commandNames).toContain('run repair-plan')
    expect(commandNames).toContain('codebook test')
    expect(commandNames).toContain('skill install')
  })

  it('exposes built-in workflow templates', () => {
    const templateIds = WORKFLOW_TEMPLATES.templates.map(
      (template) => template.id,
    )
    expect(templateIds).toContain('human_in_the_loop')
    expect(templateIds).toContain('iterative_refinement')
    expect(templateIds).toContain('grounded_evidence_verification')
    expect(templateIds).toContain('psychology_survey_codebook')
  })
})
