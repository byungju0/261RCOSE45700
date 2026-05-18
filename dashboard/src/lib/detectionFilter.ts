import type { DetectionFilter } from '@/types/api';

/** filter → URLSearchParams. 빈 값 / page=0 / size 기본은 생략. */
export function detectionFilterToParams(filter: DetectionFilter): URLSearchParams {
  const params = new URLSearchParams();
  if (filter.date) params.set('date', filter.date);
  if (filter.site) params.set('site', filter.site);
  if (filter.type) params.set('type', filter.type);
  if (filter.lang) params.set('lang', filter.lang);
  if (filter.page !== undefined && filter.page > 0) {
    params.set('page', String(filter.page));
  }
  if (filter.size !== undefined) params.set('size', String(filter.size));
  return params;
}

/** date / site / type / lang 중 하나라도 설정되어 있으면 active. */
export function isFilterActive(filter: DetectionFilter): boolean {
  return !!(filter.date || filter.site || filter.type || filter.lang);
}
