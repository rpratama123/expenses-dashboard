export type ThemePreference = 'system' | 'light' | 'dark'
export type PeriodPreference = 'current-month' | 'last-30-days' | 'current-year'

export interface Preferences { theme: ThemePreference; defaultPeriod: PeriodPreference }

const KEY = 'expenses.preferences.v1'
const defaults: Preferences = { theme: 'system', defaultPeriod: 'current-month' }

export function getPreferences(): Preferences {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '') as Partial<Preferences>
    return {
      theme: ['system', 'light', 'dark'].includes(parsed.theme ?? '') ? parsed.theme as ThemePreference : defaults.theme,
      defaultPeriod: ['current-month', 'last-30-days', 'current-year'].includes(parsed.defaultPeriod ?? '')
        ? parsed.defaultPeriod as PeriodPreference : defaults.defaultPeriod,
    }
  } catch { return defaults }
}

export function savePreferences(value: Preferences): void {
  localStorage.setItem(KEY, JSON.stringify(value))
  applyTheme(value.theme)
}

export function applyTheme(theme: ThemePreference): void {
  const dark = theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}
