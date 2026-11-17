/**
 * Krippendorff's reading of alpha: rely on .800 and above, and draw only
 * tentative conclusions from .667 to .800 (Content Analysis, 2nd ed., 2004,
 * p. 241). The same thresholds back min_agreement in the workflow templates.
 */
export const RELIABLE = 0.8
export const TENTATIVE = 0.667

export type Band = 'reliable' | 'tentative' | 'unreliable'

export function band(alpha: number): Band {
  if (alpha >= RELIABLE) return 'reliable'
  if (alpha >= TENTATIVE) return 'tentative'
  return 'unreliable'
}

/** The lowest measured per-field alpha, which min_agreement gates on. */
export function weakestField(
  fields: Record<string, { krippendorff_alpha?: number | null }> | undefined,
): { field: string; alpha: number } | null {
  let weakest: { field: string; alpha: number } | null = null
  for (const [field, summary] of Object.entries(fields ?? {})) {
    const alpha = summary.krippendorff_alpha
    if (
      alpha !== null &&
      alpha !== undefined &&
      (!weakest || alpha < weakest.alpha)
    ) {
      weakest = { field, alpha }
    }
  }
  return weakest
}

export function formatAlpha(alpha: number | null | undefined): string {
  return alpha === null || alpha === undefined ? '—' : alpha.toFixed(3)
}

export function formatShare(share: number | null | undefined): string {
  return share === null || share === undefined
    ? '—'
    : `${(share * 100).toFixed(1)}%`
}
