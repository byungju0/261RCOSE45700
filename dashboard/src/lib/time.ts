import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

/** ISO 시각 / Date / ms timestamp → "N분 전" 한국어 표기. 파싱 실패 시 "—" fallback. */
export function formatRelativeTime(input: string | number | Date): string {
  const t = typeof input === 'string' ? Date.parse(input) : input instanceof Date ? input.getTime() : input;
  if (!Number.isFinite(t)) return '—';
  return formatDistanceToNow(new Date(t), { addSuffix: true, locale: ko });
}

/** ISO 시각 / Date / ms timestamp → "MM/DD HH:mm" 표기. 파싱 실패 시 "—" fallback. */
export function formatDateTime(input: string | number | Date): string {
  const date = typeof input === 'string' ? new Date(input) : input instanceof Date ? input : new Date(input);
  const t = date.getTime();
  if (!Number.isFinite(t)) return '—';

  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${month}/${day} ${hour}:${minute}`;
}
