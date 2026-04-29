import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { RightRail } from './RightRail';
import { useShortcut } from '@/lib/shortcuts';

/**
 * 3-column 레이아웃 — Sidebar | Main(Topbar + Outlet) | RightRail
 * mockup: ux-direction-a-v3-with-rail.html 와 동일 구조.
 */
export function RootLayout() {
  const navigate = useNavigate();
  useShortcut('g+d', () => navigate('/'));
  useShortcut('g+l', () => navigate('/detections'));
  useShortcut('g+s', () => navigate('/stats'));

  return (
    <div
      className="grid min-h-screen"
      style={{
        gridTemplateColumns:
          'clamp(240px, 18vw, 400px) minmax(0, 1fr) clamp(240px, 17vw, 340px)',
      }}
    >
      <Sidebar />
      <main className="flex min-w-0 flex-col">
        <Topbar />
        <Outlet />
      </main>
      <RightRail />
    </div>
  );
}
