import type { WorkflowTemplateDocument } from '../types.js'

export const WORKFLOW_TEMPLATES: WorkflowTemplateDocument = {
  version: '0.1.0',
  templates: [
    {
      id: 'quick_agentic_label',
      name: 'Quick Agentic Label',
      description: 'Ingest, agent run, spot-check sample, export.',
      file: 'quick_agentic_label.yaml',
      version: '1.0.0',
      task_family: 'general_labeling',
      capabilities: ['agent_labeling', 'spot_check', 'export'],
      validated_by_benchmarks: [],
    },
    {
      id: 'human_in_the_loop',
      name: 'Human-in-the-Loop Review',
      description: 'Ingest, agent run, human review, quality check, export.',
      file: 'human_in_the_loop.yaml',
      version: '1.0.0',
      task_family: 'general_review',
      capabilities: ['agent_labeling', 'human_review', 'quality_check'],
      validated_by_benchmarks: [],
    },
    {
      id: 'full_quality_pipeline',
      name: 'Full Quality Pipeline',
      description:
        'Ingest, calibration, agent run, human review, adjudication, quality check, export.',
      file: 'full_quality_pipeline.yaml',
      version: '1.0.0',
      task_family: 'general_quality',
      capabilities: [
        'human_calibration',
        'agreement_analysis',
        'human_adjudication',
        'release_validation',
      ],
      validated_by_benchmarks: [],
    },
    {
      id: 'benchmark_authority',
      name: 'Benchmark Authority',
      description:
        'Ingest, multi-round review, adjudication, snapshot as ground truth.',
      file: 'benchmark_authority.yaml',
      version: '1.0.0',
      task_family: 'benchmark_authoring',
      capabilities: ['human_review', 'adjudication', 'snapshot'],
      validated_by_benchmarks: [],
    },
    {
      id: 'agent_comparison',
      name: 'Agent Comparison',
      description:
        'Ingest, parallel agent runs, review, comparison analytics, export.',
      file: 'agent_comparison.yaml',
      version: '1.0.0',
      task_family: 'comparison',
      capabilities: ['agent_compare', 'human_review', 'analytics'],
      validated_by_benchmarks: [],
    },
    {
      id: 'iterative_refinement',
      name: 'Iterative Refinement',
      description:
        'Ingest, agent run, low-confidence review, prompt refinement loop.',
      file: 'iterative_refinement.yaml',
      version: '1.0.0',
      task_family: 'prompt_refinement',
      capabilities: ['agent_labeling', 'low_confidence_review', 'loop'],
      validated_by_benchmarks: [],
    },
    {
      id: 'grounded_classification_review',
      name: 'Grounded Classification Review',
      description:
        'Grounded single-label or multi-label classification with explicit proposer, all-record review, and benchmark artifacts.',
      file: 'grounded_classification_review.yaml',
      version: '1.0.0',
      task_family: 'grounded_classification',
      capabilities: [
        'source_record_ids',
        'agent_labeling',
        'human_review',
        'benchmark_artifacts',
      ],
      validated_by_benchmarks: ['clinc150', 'banking77', 'goemotions'],
    },
    {
      id: 'grounded_evidence_verification',
      name: 'Grounded Evidence Verification',
      description:
        'Verification workflow that preserves stable evidence atom IDs through proposer and review.',
      file: 'grounded_evidence_verification.yaml',
      version: '1.0.0',
      task_family: 'grounded_evidence',
      capabilities: [
        'grouped_evidence_atoms',
        'source_record_ids',
        'human_review',
        'benchmark_artifacts',
      ],
      validated_by_benchmarks: ['feverous', 'scifact'],
    },
    {
      id: 'grounded_rationale_moderation',
      name: 'Grounded Rationale Moderation',
      description:
        'Moderation workflow with explicit rationale-mask preservation and review breakpoint.',
      file: 'grounded_rationale_moderation.yaml',
      version: '1.0.0',
      task_family: 'grounded_rationale',
      capabilities: [
        'rationale_token_mask',
        'source_record_ids',
        'human_review',
        'benchmark_artifacts',
      ],
      validated_by_benchmarks: ['hatexplain'],
    },
    {
      id: 'psychology_survey_codebook',
      name: 'Psychology Survey Codebook',
      description:
        'Psychology and qualitative research workflow with codebook calibration, MiniMax-assisted coding, evidence spans, agreement analysis, adjudication, export, and release proof.',
      file: 'psychology_survey_codebook.yaml',
      version: '1.0.0',
      task_family: 'psychology_research',
      capabilities: [
        'codebook_management',
        'pii_redaction',
        'agent_labeling',
        'human_calibration',
        'human_review',
        'agreement_analysis',
        'human_adjudication',
        'release_validation',
      ],
      validated_by_benchmarks: ['psychology-survey-codebook'],
    },
  ],
}
