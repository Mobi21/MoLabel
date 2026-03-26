import type { WorkflowTemplateDocument } from '../types.js'

export const WORKFLOW_TEMPLATES: WorkflowTemplateDocument = {
  version: '0.1.0',
  templates: [
    {
      id: 'quick_agentic_label',
      name: 'Quick Agentic Label',
      description: 'Ingest, agent run, spot-check sample, export.',
      file: 'quick_agentic_label.yaml',
    },
    {
      id: 'human_in_the_loop',
      name: 'Human-in-the-Loop Review',
      description: 'Ingest, agent run, human review, quality check, export.',
      file: 'human_in_the_loop.yaml',
    },
    {
      id: 'full_quality_pipeline',
      name: 'Full Quality Pipeline',
      description:
        'Ingest, calibration, agent run, human review, adjudication, quality check, export.',
      file: 'full_quality_pipeline.yaml',
    },
    {
      id: 'benchmark_authority',
      name: 'Benchmark Authority',
      description: 'Ingest, multi-round review, adjudication, snapshot as ground truth.',
      file: 'benchmark_authority.yaml',
    },
    {
      id: 'agent_comparison',
      name: 'Agent Comparison',
      description: 'Ingest, parallel agent runs, review, comparison analytics, export.',
      file: 'agent_comparison.yaml',
    },
    {
      id: 'iterative_refinement',
      name: 'Iterative Refinement',
      description: 'Ingest, agent run, low-confidence review, prompt refinement loop.',
      file: 'iterative_refinement.yaml',
    },
  ],
}
