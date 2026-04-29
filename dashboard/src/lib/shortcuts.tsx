/* eslint-disable react-refresh/only-export-components --
 * GlobalShortcutProvider(컴포넌트)와 useShortcut(훅)을 같은 모듈에서 export.
 * 둘은 하나의 응집된 API라 분리 시 import 경로만 늘어남. HMR 영향 미미.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';

/**
 * Tracker 전역 키보드 단축키 (UX Spec Pattern 2 — Keyboard Navigation Layer).
 *
 * 운영 도구는 키보드만으로 Critical Loop 완주 가능해야 한다 (P3 Friction 감소).
 * input/textarea focus 시 자동 비활성화되어 폼 입력과 충돌하지 않는다.
 *
 * Chord 지원: 'g+t', 'g+d', 'g+l', 'g+s' 형태로 두 키 연속 입력 처리.
 */

type Handler = (event: KeyboardEvent) => void;

interface ShortcutMap {
  [key: string]: Handler;
}

interface ShortcutContextValue {
  register: (key: string, handler: Handler) => () => void;
}

const ShortcutContext = createContext<ShortcutContextValue | null>(null);

const CHORD_TIMEOUT_MS = 1000;

function isInputElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  if (target.isContentEditable) return true;
  return false;
}

interface GlobalShortcutProviderProps {
  children: ReactNode;
}

export function GlobalShortcutProvider({ children }: GlobalShortcutProviderProps) {
  const handlersRef = useRef<ShortcutMap>({});
  const chordPrefixRef = useRef<{ key: string; at: number } | null>(null);

  const register = useCallback((key: string, handler: Handler) => {
    handlersRef.current[key] = handler;
    return () => {
      delete handlersRef.current[key];
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isInputElement(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const key = event.key;

      const prefix = chordPrefixRef.current;
      if (
        prefix &&
        Date.now() - prefix.at < CHORD_TIMEOUT_MS &&
        prefix.key === 'g'
      ) {
        const chordKey = `g+${key}`;
        chordPrefixRef.current = null;
        const handler = handlersRef.current[chordKey];
        if (handler) {
          event.preventDefault();
          handler(event);
        }
        return;
      }

      if (key === 'g') {
        chordPrefixRef.current = { key, at: Date.now() };
        return;
      }

      const handler = handlersRef.current[key];
      if (handler) {
        event.preventDefault();
        handler(event);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const value = useMemo(() => ({ register }), [register]);

  return (
    <ShortcutContext.Provider value={value}>
      {children}
    </ShortcutContext.Provider>
  );
}

/**
 * 컴포넌트 단위 단축키 등록.
 *
 * 사용 예: useShortcut('o', () => window.open(post.url, '_blank'))
 *          useShortcut('g+t', () => triggerCrawl())
 */
export function useShortcut(key: string, handler: Handler): void {
  const ctx = useContext(ShortcutContext);
  if (!ctx) {
    throw new Error('useShortcut must be used within a GlobalShortcutProvider');
  }
  // handler를 ref로 저장해 deps 변경 시 register 재호출 방지.
  // ref 갱신은 useEffect 안에서 수행해 render 중 ref mutation 회피.
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    return ctx.register(key, (event) => handlerRef.current(event));
  }, [ctx, key]);
}
