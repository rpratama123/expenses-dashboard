import type { PeriodPreference } from './preferences'

function ymd(date: Date): string {
  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function periodDates(period: PeriodPreference, now = new Date()): { from: string; to: string } {
  const jakartaDate = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const [year, month] = jakartaDate.split('-')
  if (period === 'last-30-days') {
    const from = new Date(`${jakartaDate}T00:00:00Z`)
    from.setUTCDate(from.getUTCDate() - 29)
    return { from: ymd(from), to: jakartaDate }
  }
  if (period === 'current-year') return { from: `${year}-01-01`, to: jakartaDate }
  return { from: `${year}-${month}-01`, to: jakartaDate }
}
