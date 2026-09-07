import { BarChart3, List, RefreshCw, ReceiptText, Settings } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Summary', icon: BarChart3, end: true },
  { to: '/transactions', label: 'Transactions', icon: List, end: false },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
]

export function AppShell({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(navigator.onLine)
  const [update, setUpdate] = useState<(() => Promise<void>) | null>(null)

  useEffect(() => {
    const onOnline = () => setOnline(true)
    const onOffline = () => setOnline(false)
    const onUpdate = (event: Event) => setUpdate(() => (event as CustomEvent<() => Promise<void>>).detail)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    window.addEventListener('expenses:update-ready', onUpdate)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('expenses:update-ready', onUpdate)
    }
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><ReceiptText /></span><span>Expenses<br /><strong>Dashboard</strong></span></div>
        <nav aria-label="Primary navigation">{links.map(({ icon: Icon, ...link }) => (
          <NavLink key={link.to} {...link} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            <Icon aria-hidden="true" /><span>{link.label}</span>
          </NavLink>
        ))}</nav>
        <div className={`connection ${online ? '' : 'offline'}`}><span />{online ? 'Connected' : 'Offline mode'}</div>
      </aside>
      {!online && <div className="global-notice" role="status">Offline. Showing only exact views saved on this device.</div>}
      {update && <div className="update-notice" role="status">An app update is ready.<button onClick={() => void update()}>Update <RefreshCw /></button></div>}
      <main id="main-content">{children}</main>
      <nav className="bottom-nav" aria-label="Primary navigation">{links.map(({ icon: Icon, ...link }) => (
        <NavLink key={link.to} {...link} className={({ isActive }) => isActive ? 'active' : ''}>
          <Icon aria-hidden="true" /><span>{link.label}</span>
        </NavLink>
      ))}</nav>
    </div>
  )
}
