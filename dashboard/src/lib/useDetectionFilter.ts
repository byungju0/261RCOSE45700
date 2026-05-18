import { useMemo, useTransition } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  detectionFilterToParams,
  isFilterActive,
} from './detectionFilter';
import type { DetectionFilter, DetectionType, Language } from '@/types/api';

/**
 * URL search params <-> DetectionFilter 양방향 sync.
 *
 * - filter는 searchParams에서 파생 (URL이 single source of truth)
 * - updateFilter / resetFilters는 useTransition으로 wrap — fetch 동안 이전 화면 유지
 * - hasActiveFilter는 date/site/type/lang 중 하나라도 설정됐는지
 *
 * 페이지 사이즈는 size 파라미터로 받아 URL에 노출하지 않음 (page만 URL 상태).
 */
export function useDetectionFilter(pageSize: number) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const filter: DetectionFilter = useMemo(() => {
    const date = searchParams.get('date') ?? undefined;
    const site = searchParams.get('site') ?? undefined;
    const type =
      (searchParams.get('type') as DetectionType | null) ?? undefined;
    const lang = (searchParams.get('lang') as Language | null) ?? undefined;
    const page = Number(searchParams.get('page') ?? '0');
    return { date, site, type, lang, page, size: pageSize };
  }, [searchParams, pageSize]);

  const updateFilter = (next: Partial<DetectionFilter>, resetPage = true) => {
    const merged: DetectionFilter = {
      ...filter,
      ...next,
      page: resetPage ? 0 : (next.page ?? filter.page),
      size: undefined,
    };
    startTransition(() => {
      setSearchParams(detectionFilterToParams(merged));
    });
  };

  const resetFilters = () => {
    startTransition(() => {
      setSearchParams(new URLSearchParams());
    });
  };

  return {
    filter,
    updateFilter,
    resetFilters,
    hasActiveFilter: isFilterActive(filter),
    isPending,
  };
}
