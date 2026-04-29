import { useEffect, useState } from 'react';
import { Sun, Moon } from 'lucide-react';
import { ManualCrawlButton } from '@/components/tracker/ManualCrawlButton';

type Theme = 'light' | 'dark';

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  // index.html 인라인 스크립트가 이미 data-theme을 설정 — 동일 우선순위 logic이지만
  // 신뢰원은 DOM. localStorage는 Safari Private Mode에서 throw 가능 → guarded.
  const fromDom = document.documentElement.getAttribute('data-theme');
  if (fromDom === 'dark' || fromDom === 'light') return fromDom;
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'light') return saved;
  } catch {
    /* Private Mode → fallthrough */
  }
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

export function Topbar() {
  const [theme, setTheme] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    // 변경 없는 쓰기 차단 — StrictMode 이중 effect / 초기 mount no-op 모두 흡수
    if (document.documentElement.getAttribute('data-theme') !== theme) {
      document.documentElement.setAttribute('data-theme', theme);
    }
    try {
      if (localStorage.getItem('theme') !== theme) {
        localStorage.setItem('theme', theme);
      }
    } catch {
      /* localStorage 쓰기 실패 무시 */
    }
  }, [theme]);

  return (
    <div
      className="flex items-center justify-end gap-2.5 border-b"
      style={{
        height: 'var(--h-topbar)',
        padding: '0 var(--pad-topbar-x)',
        borderColor: 'var(--border-1)',
      }}
    >
      <ManualCrawlButton />
      <ThemeToggle theme={theme} onToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')} />
    </div>
  );
}

function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const Icon = theme === 'dark' ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label="테마 전환"
      title={theme === 'dark' ? '라이트로 전환' : '다크로 전환'}
      className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md border bg-transparent transition-colors"
      style={{
        borderColor: 'var(--border-1)',
        color: 'var(--fg-2)',
      }}
    >
      <Icon className="size-3.5" />
    </button>
  );
}
