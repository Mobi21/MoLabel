import { describe, expect, it } from 'vitest'

import { COMMAND_MANIFEST } from '../src/manifest/commands.js'
import { WORKFLOW_TEMPLATES } from '../src/manifest/workflow-templates.js'

describe('manifests', () => {
  it('exposes the expected command groups', () => {
    const commandNames = COMMAND_MANIFEST.commands.map((command) => command.name)
    expect(commandNames).toContain('doctor')
    expect(commandNames).toContain('artifact write')
    expect(commandNames).toContain('skill install')
  })

  it('exposes built-in workflow templates', () => {
    const templateIds = WORKFLOW_TEMPLATES.templates.map((template) => template.id)
    expect(templateIds).toContain('human_in_the_loop')
    expect(templateIds).toContain('iterative_refinement')
  })
})
