const GROUPS = /\B(?=(\d{3})+(?!\d))/g

// Mirrors backend `CURRENCY_SCALES`: minor units per major unit.
const CURRENCY_SCALES: Record<string, number> = { IDR: 1, USD: 100, SGD: 100, MYR: 100 }
const CURRENCY_PREFIX: Record<string, string> = { IDR: 'Rp', USD: 'US$' }

function normalizeInteger(value: string): { negative: boolean; digits: string } {
  if (!/^-?\d+$/.test(value)) throw new Error('Invalid integer amount')
  const negative = value.startsWith('-')
  const digits = value.replace('-', '').replace(/^0+(?=\d)/, '')
  return { negative, digits }
}

export function formatIdr(value: string): string {
  const { negative, digits } = normalizeInteger(value)
  return `${negative ? '-' : ''}Rp${digits.replace(GROUPS, ',')}`
}

export function formatOriginal(value: string, currency: string): string {
  const { negative, digits } = normalizeInteger(value)
  if (currency === 'IDR') return formatIdr(value)
  const sign = negative ? '-' : ''
  const scale = CURRENCY_SCALES[currency]
  if (scale === undefined || scale === 1) return `${currency} ${sign}${digits.replace(GROUPS, ',')}`
  const decimals = String(scale).length - 1
  const padded = digits.padStart(decimals + 1, '0')
  const major = padded.slice(0, -decimals).replace(GROUPS, ',')
  const prefix = CURRENCY_PREFIX[currency] ?? `${currency} `
  return `${sign}${prefix}${major}.${padded.slice(-decimals)}`
}

export function chartNumber(value: string): number {
  const result = Number(value)
  return Number.isFinite(result) ? result : 0
}
