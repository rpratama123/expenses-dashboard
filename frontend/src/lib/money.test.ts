import { describe, expect, it } from 'vitest'
import { chartNumber, formatIdr, formatOriginal } from './money'

describe('exact money display', () => {
  it('formats IDR integer units without floating point conversion', () => {
    expect(formatIdr('5000')).toBe('Rp5,000')
    expect(formatIdr('900719925474099312345')).toBe('Rp900,719,925,474,099,312,345')
    expect(formatIdr('-12')).toBe('-Rp12')
  })

  it('formats USD minor units with exactly two decimals', () => {
    expect(formatOriginal('566', 'USD')).toBe('US$5.66')
    expect(formatOriginal('5', 'USD')).toBe('US$0.05')
  })

  it('uses numeric conversion only for chart geometry', () => {
    expect(chartNumber('90560')).toBe(90560)
    expect(chartNumber('not-money')).toBe(0)
  })

  it('rejects non-integer API money strings', () => {
    expect(() => formatIdr('1.25')).toThrow('Invalid integer amount')
  })
})
