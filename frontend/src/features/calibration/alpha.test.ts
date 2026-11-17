import { describe, expect, it } from 'vitest'
import { band, formatAlpha, weakestField } from './alpha'

describe('alpha', () => {
  it("reads alpha against Krippendorff's .667 and .800", () => {
    expect(band(0.8)).toBe('reliable')
    expect(band(0.7999)).toBe('tentative')
    expect(band(0.667)).toBe('tentative')
    expect(band(0.56)).toBe('unreliable')
  })

  it('finds the lowest measured field, skipping null alphas', () => {
    expect(
      weakestField({
        intent: { krippendorff_alpha: 0.56 },
        urgent: { krippendorff_alpha: 1 },
        note: { krippendorff_alpha: null },
      }),
    ).toEqual({ field: 'intent', alpha: 0.56 })
    expect(weakestField({ note: { krippendorff_alpha: null } })).toBeNull()
  })

  it('prints three decimals, or a dash for an unmeasured alpha', () => {
    expect(formatAlpha(0.5604)).toBe('0.560')
    expect(formatAlpha(null)).toBe('—')
  })
})
