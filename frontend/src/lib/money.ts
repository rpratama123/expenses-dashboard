const GROUPS = /\B(?=(\d{3})+(?!\d))/g

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
  if (currency === 'USD') {
    const padded = digits.padStart(3, '0')
    const major = padded.slice(0, -2).replace(GROUPS, ',')
    return `${negative ? '-' : ''}US$${major}.${padded.slice(-2)}`
  }
  return `${currency} ${negative ? '-' : ''}${digits.replace(GROUPS, ',')}`
}

export function chartNumber(value: string): number {
  const result = Number(value)
  return Number.isFinite(result) ? result : 0
}
