import { NavLink } from 'react-router-dom';
import { LayoutDashboard, ListChecks, BarChart3 } from 'lucide-react';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { to: '/', label: '대시보드', end: true, Icon: LayoutDashboard },
  { to: '/detections', label: '탐지 목록', end: false, Icon: ListChecks },
  { to: '/stats', label: '통계', end: false, Icon: BarChart3 },
] as const;

export function Sidebar() {
  return (
    <aside
      aria-label="주 탐색"
      className="border-border-1 sticky top-0 h-screen self-start border-r"
      style={{
        background: 'var(--bg-sunk)',
        padding: 'clamp(16px, 1.5vw, 28px) clamp(10px, 0.8vw, 16px)',
      }}
    >
      <div
        className="flex items-center gap-2.5 px-2 pb-7 text-base font-semibold"
        style={{ letterSpacing: 'var(--tracking-tight)' }}
      >
        <span
          className="font-mono inline-flex size-6 items-center justify-center rounded-[5px] text-xs font-bold"
          style={{ background: 'var(--fg)', color: 'var(--bg)' }}
        >
          T
        </span>
        <span>Tracker</span>
      </div>
      <nav className="flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ to, label, end, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-[5px] px-3 py-2.5 text-sm font-medium no-underline transition-colors',
                // 색상은 className만으로 처리 — inline style이 hover를 가로채지 않게.
                isActive
                  ? 'bg-bg-elev text-fg'
                  : 'text-fg-2 hover:bg-bg-overlay hover:text-fg',
              )
            }
          >
            <Icon className="size-4 shrink-0 opacity-85" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
