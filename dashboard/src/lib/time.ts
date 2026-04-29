import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

/** ISO 시각 → "N분 전" 한국어 표기. 파싱 실패 시 "—" fallback. */
export function formatRelativeTime(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '—';
  return formatDistanceToNow(new Date(t), { addSuffix: true, locale: ko });
}
