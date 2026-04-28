import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useDetectionsQuery } from '@/api/detections';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DetectionRow } from '@/components/tracker/DetectionRow';
import { EmptyState } from '@/components/tracker/EmptyState';
import { LANG_OPTIONS, TYPE_OPTIONS } from '@/components/tracker/labels';
import { PageContainer } from '@/layouts/PageContainer';
import {
  detectionFilterToParams,
  isFilterActive,
} from '@/lib/detectionFilter';
import { useShortcut } from '@/lib/shortcuts';
import { KNOWN_SOURCES } from '@/lib/sources';
import type { DetectionFilter, DetectionType, Language } from '@/types/api';

const PAGE_SIZE = 20;

export function DetectionListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const filter: DetectionFilter = useMemo(() => {
    const date = searchParams.get('date') ?? undefined;
    const site = searchParams.get('site') ?? undefined;
    const type =
      (searchParams.get('type') as DetectionType | null) ?? undefined;
    const lang = (searchParams.get('lang') as Language | null) ?? undefined;
    const since =
      (searchParams.get('since') as 'triggered' | null) ?? undefined;
    const page = Number(searchParams.get('page') ?? '0');
    return { date, site, type, lang, since, page, size: PAGE_SIZE };
  }, [searchParams]);

  const { data, isLoading, error } = useDetectionsQuery(filter);
  if (error) throw error;

  const [focusedIdx, setFocusedIdx] = useState(0);
  const [visited, setVisited] = useState<Set<number>>(new Set());

  // "previous state in render" — filter ref가 바뀌면 focus 리셋 (effect 회피).
  const [prevFilter, setPrevFilter] = useState(filter);
  if (prevFilter !== filter) {
    setPrevFilter(filter);
    setFocusedIdx(0);
  }

  const items = data?.content ?? [];
  const totalPages = data ? Math.ceil(data.totalElements / data.size) : 1;

  const updateFilter = (next: Partial<DetectionFilter>, resetPage = true) => {
    const merged: DetectionFilter = {
      ...filter,
      ...next,
      page: resetPage ? 0 : (next.page ?? filter.page),
      size: undefined,
    };
    setSearchParams(detectionFilterToParams(merged));
  };

  const resetFilters = () => {
    setSearchParams(new URLSearchParams());
  };

  const openDetail = (id: number) => {
    setVisited((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    navigate(`/detections/${id}`);
  };

  // Keyboard navigation
  useShortcut('j', () => {
    setFocusedIdx((idx) => Math.min(idx + 1, Math.max(items.length - 1, 0)));
  });
  useShortcut('k', () => {
    setFocusedIdx((idx) => Math.max(idx - 1, 0));
  });
  useShortcut('Enter', () => {
    const item = items[focusedIdx];
    if (item) openDetail(item.id);
  });

  const hasActiveFilter = isFilterActive(filter);

  return (
    <PageContainer className="gap-4">
      <header className="flex items-baseline justify-between">
        <h1
          className="text-foreground font-semibold tracking-tight"
          style={{ fontSize: 'var(--size-h1)', lineHeight: 'var(--lh-snug)' }}
        >
          탐지 목록
        </h1>
        {data && (
          <span className="text-muted-foreground text-xs">
            {hasActiveFilter
              ? `필터 적용: ${data.totalElements}건`
              : `${data.totalElements}건`}
          </span>
        )}
      </header>

      <FilterBar
        filter={filter}
        onChange={updateFilter}
        onReset={resetFilters}
        active={hasActiveFilter}
      />

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        hasActiveFilter ? (
          <EmptyState
            variant="filter-empty"
            title="해당 조건에 맞는 탐지 결과가 없습니다"
            message="필터를 초기화하거나 조건을 변경해 보세요."
            action={
              <Button variant="outline" size="sm" onClick={resetFilters}>
                필터 초기화
              </Button>
            }
          />
        ) : (
          <EmptyState
            variant="healthy"
            title="탐지된 게시글이 없습니다"
            message="시스템 정상 작동 중 · 다음 크롤링 주기에 다시 확인하세요"
          />
        )
      ) : (
        <>
          <div className="bg-card overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>신뢰도</TableHead>
                  <TableHead>유형</TableHead>
                  <TableHead>사이트</TableHead>
                  <TableHead>본문 미리보기</TableHead>
                  <TableHead className="text-right">탐지 시각</TableHead>
                  <TableHead className="w-[40px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, idx) => (
                  <DetectionRow
                    key={item.id}
                    detection={item}
                    focused={idx === focusedIdx}
                    visited={visited.has(item.id)}
                    onSelect={() => openDetail(item.id)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>

          {totalPages > 1 && (
            <Pagination
              page={filter.page ?? 0}
              totalPages={totalPages}
              onPage={(p) => updateFilter({ page: p }, false)}
            />
          )}

          <p className="text-muted-foreground text-xs">
            팁: <kbd className="bg-muted rounded px-1 font-mono">j</kbd>/
            <kbd className="bg-muted rounded px-1 font-mono">k</kbd> 다음/이전 ·{' '}
            <kbd className="bg-muted rounded px-1 font-mono">Enter</kbd> 상세
          </p>
        </>
      )}
    </PageContainer>
  );
}

interface FilterBarProps {
  filter: DetectionFilter;
  onChange: (next: Partial<DetectionFilter>) => void;
  onReset: () => void;
  active: boolean;
}

const ALL_VALUE = '__all__';

function FilterBar({ filter, onChange, onReset, active }: FilterBarProps) {
  const sites = KNOWN_SOURCES;

  return (
    <div className="bg-card flex flex-wrap items-center gap-2 rounded-lg border p-3">
      <Select
        value={filter.site ?? ALL_VALUE}
        onValueChange={(v) =>
          onChange({ site: v === ALL_VALUE ? undefined : v })
        }
      >
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder="사이트" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>모든 사이트</SelectItem>
          {sites.map((s) => (
            <SelectItem key={s} value={s} className="font-mono text-xs">
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filter.type ?? ALL_VALUE}
        onValueChange={(v) =>
          onChange({
            type: v === ALL_VALUE ? undefined : (v as DetectionType),
          })
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="유형" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>모든 유형</SelectItem>
          {TYPE_OPTIONS.map((t) => (
            <SelectItem key={t.value} value={t.value}>
              {t.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filter.lang ?? ALL_VALUE}
        onValueChange={(v) =>
          onChange({
            lang: v === ALL_VALUE ? undefined : (v as Language),
          })
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="언어" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>모든 언어</SelectItem>
          {LANG_OPTIONS.map((l) => (
            <SelectItem key={l.value} value={l.value}>
              {l.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {filter.since && (
        <span className="bg-warning/10 text-warning rounded-full px-3 py-1 text-xs font-medium">
          새로 들어온 탐지만
        </span>
      )}

      {active && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="ml-auto"
        >
          필터 초기화
        </Button>
      )}
    </div>
  );
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onPage: (p: number) => void;
}

function Pagination({ page, totalPages, onPage }: PaginationProps) {
  return (
    <div className="text-muted-foreground flex items-center justify-between text-xs">
      <Button
        variant="outline"
        size="sm"
        disabled={page === 0}
        onClick={() => onPage(page - 1)}
        className="gap-1"
      >
        <ChevronLeft className="size-3.5" aria-hidden />
        이전
      </Button>
      <span>
        <span className="font-mono">{page + 1}</span> /{' '}
        <span className="font-mono">{totalPages}</span>
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= totalPages - 1}
        onClick={() => onPage(page + 1)}
        className="gap-1"
      >
        다음
        <ChevronRight className="size-3.5" aria-hidden />
      </Button>
    </div>
  );
}

