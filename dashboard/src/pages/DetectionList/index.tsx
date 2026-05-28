import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, SlidersHorizontal, X } from 'lucide-react';
import { useDetectionsSuspenseQuery } from '@/api/detections';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Kbd } from '@/components/ui/kbd';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DetectionCard } from '@/components/tracker/DetectionCard';
import { DetectionRow } from '@/components/tracker/DetectionRow';
import { EmptyState } from '@/components/tracker/EmptyState';
import { LANG_OPTIONS, TYPE_OPTIONS } from '@/components/tracker/labels';
import { PageContainer } from '@/layouts/PageContainer';
import { useDetectionFilter } from '@/lib/useDetectionFilter';
import { useShortcut } from '@/lib/shortcuts';
import { KNOWN_SOURCES } from '@/lib/sources';
import { cn } from '@/lib/utils';
import type { DetectionFilter, DetectionType, Language } from '@/types/api';

const PAGE_SIZE = 20;

export function DetectionListPage() {
  const navigate = useNavigate();
  const { filter, updateFilter, resetFilters, hasActiveFilter, isPending } =
    useDetectionFilter(PAGE_SIZE);
  const { data } = useDetectionsSuspenseQuery(filter);

  const [focusedIdx, setFocusedIdx] = useState(-1);
  const [visited, setVisited] = useState<Set<number>>(() => new Set());

  // "previous state in render" — filter ref가 바뀌면 focus 리셋 (effect 회피).
  const [prevFilter, setPrevFilter] = useState(filter);
  if (prevFilter !== filter) {
    setPrevFilter(filter);
    setFocusedIdx(0);
  }

  const items = data.content;
  const totalPages = Math.ceil(data.totalElements / data.size);

  const openDetail = (id: number) => {
    setVisited((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    navigate(`/detections/${id}`);
  };

  useShortcut('j', () => {
    setFocusedIdx((idx) => Math.min(idx < 0 ? 0 : idx + 1, Math.max(items.length - 1, 0)));
  });
  useShortcut('k', () => {
    setFocusedIdx((idx) => Math.max(idx < 0 ? 0 : idx - 1, 0));
  });
  useShortcut('Enter', () => {
    const item = items[focusedIdx];
    if (item) openDetail(item.id);
  });

  return (
    <PageContainer className="gap-4">
      <title>탐지 목록 · Tracker</title>
      <header className="flex items-baseline justify-between">
        <h1
          className="text-foreground font-semibold tracking-tight"
          style={{ fontSize: 'var(--size-h1)', lineHeight: 'var(--lh-snug)' }}
        >
          탐지 목록
        </h1>
        <span className="text-muted-foreground text-xs">
          {hasActiveFilter
            ? `필터 적용: ${data.totalElements}건`
            : `${data.totalElements}건`}
        </span>
      </header>

      <FilterBar
        filter={filter}
        onChange={updateFilter}
        onReset={resetFilters}
        active={hasActiveFilter}
      />

      <div
        // useTransition pending 동안 살짝 dim — 이전 데이터가 보이지만 fetch 진행 중임 표시.
        aria-busy={isPending || undefined}
        className={cn(
          'flex flex-col gap-4 transition-opacity',
          isPending && 'opacity-60',
        )}
      >
      {items.length === 0 ? (
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
          {/* Mobile (< md) — 카드 리스트, 키보드 네비 미적용 (터치 우선) */}
          <div className="bg-card overflow-hidden rounded-lg border md:hidden">
            {items.map((item) => (
              <DetectionCard
                key={item.id}
                detection={item}
                visited={visited.has(item.id)}
                onSelect={() => openDetail(item.id)}
              />
            ))}
          </div>
          <div className="bg-card hidden overflow-hidden rounded-lg border md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>위험도</TableHead>
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

          <p className="text-muted-foreground hidden text-xs md:block">
            팁: <Kbd size="xs">j</Kbd>/<Kbd size="xs">k</Kbd> 다음/이전 ·{' '}
            <Kbd size="xs">Enter</Kbd> 상세 · <Kbd size="xs">?</Kbd> 전체 단축키
          </p>
        </>
      )}
      </div>
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

interface FilterSelectOption {
  value: string;
  label: string;
  className?: string;
}

interface FilterSelectProps {
  value: string;
  allLabel: string;
  options: FilterSelectOption[];
  onChange: (value: string) => void;
  triggerClassName?: string;
}

function FilterSelect({ value, allLabel, options, onChange, triggerClassName }: FilterSelectProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={triggerClassName}>
        <SelectValue placeholder={allLabel} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_VALUE}>{allLabel}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value} className={o.className}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function FilterBar(props: FilterBarProps) {
  return (
    <>
      <MobileFilterBar {...props} />
      <DesktopFilterBar {...props} />
    </>
  );
}

function DesktopFilterBar({ filter, onChange, onReset, active }: FilterBarProps) {
  const siteOptions = KNOWN_SOURCES.map((s) => ({ value: s, label: s, className: 'font-mono text-xs' }));
  const typeOptions = TYPE_OPTIONS.map((t) => ({ value: t.value, label: t.label }));
  const langOptions = LANG_OPTIONS.map((l) => ({ value: l.value, label: l.label }));

  return (
    <div className="bg-card hidden flex-wrap items-center gap-2 rounded-lg border p-3 md:flex">
      <FilterSelect
        value={filter.site ?? ALL_VALUE}
        allLabel="모든 사이트"
        options={siteOptions}
        onChange={(v) => onChange({ site: v === ALL_VALUE ? undefined : v })}
        triggerClassName="w-[180px]"
      />
      <FilterSelect
        value={filter.type ?? ALL_VALUE}
        allLabel="모든 유형"
        options={typeOptions}
        onChange={(v) => onChange({ type: v === ALL_VALUE ? undefined : (v as DetectionType) })}
        triggerClassName="w-[160px]"
      />
      <FilterSelect
        value={filter.lang ?? ALL_VALUE}
        allLabel="모든 언어"
        options={langOptions}
        onChange={(v) => onChange({ lang: v === ALL_VALUE ? undefined : (v as Language) })}
        triggerClassName="w-[160px]"
      />
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

function FilterChip({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClear}
      aria-label={`필터 해제: ${label}`}
      className="bg-bg-overlay border-border-1 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium"
      style={{ color: 'var(--fg-2)' }}
    >
      {label}
      <X className="size-3" aria-hidden />
    </button>
  );
}

function MobileFilterBar({ filter, onChange, onReset, active }: FilterBarProps) {
  const siteOptions = KNOWN_SOURCES.map((s) => ({ value: s, label: s, className: 'font-mono text-xs' }));
  const typeOptions = TYPE_OPTIONS.map((t) => ({ value: t.value, label: t.label }));
  const langOptions = LANG_OPTIONS.map((l) => ({ value: l.value, label: l.label }));

  const typeLabel = TYPE_OPTIONS.find((t) => t.value === filter.type)?.label;
  const langLabel = LANG_OPTIONS.find((l) => l.value === filter.lang)?.label;

  return (
    <div className="bg-card flex flex-wrap items-center gap-2 rounded-lg border p-3 md:hidden">
      <Drawer>
        <DrawerTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <SlidersHorizontal className="size-3.5" aria-hidden />
            필터
            {active && (
              <span
                className="ml-1 inline-flex size-4 items-center justify-center rounded-full text-[10px] font-semibold"
                style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
              >
                {[filter.site, filter.type, filter.lang].filter(Boolean).length}
              </span>
            )}
          </Button>
        </DrawerTrigger>
        <DrawerContent className="max-h-[85vh]">
          <DrawerHeader>
            <DrawerTitle>필터</DrawerTitle>
            <DrawerDescription className="sr-only">
              사이트·유형·언어를 선택하고 완료를 누르세요.
            </DrawerDescription>
          </DrawerHeader>
          <div className="flex flex-col gap-3 px-4 pb-2">
            {(
              [
                { label: '사이트', options: siteOptions, value: filter.site, onChange: (v: string) => onChange({ site: v === ALL_VALUE ? undefined : v }) },
                { label: '유형',   options: typeOptions,  value: filter.type, onChange: (v: string) => onChange({ type: v === ALL_VALUE ? undefined : (v as DetectionType) }) },
                { label: '언어',   options: langOptions,  value: filter.lang, onChange: (v: string) => onChange({ lang: v === ALL_VALUE ? undefined : (v as Language) }) },
              ] as const
            ).map(({ label, options, value, onChange: onRowChange }) => (
              <label key={label} className="flex flex-col gap-1.5">
                <span className="text-fg-3 text-xs font-medium uppercase tracking-wide">
                  {label}
                </span>
                <FilterSelect
                  value={value ?? ALL_VALUE}
                  allLabel={`모든 ${label}`}
                  options={options as FilterSelectOption[]}
                  onChange={onRowChange}
                  triggerClassName="w-full"
                />
              </label>
            ))}
          </div>
          <DrawerFooter>
            <Button onClick={onReset} variant="outline" disabled={!active}>
              초기화
            </Button>
            <DrawerClose asChild>
              <Button>완료</Button>
            </DrawerClose>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {filter.site && (
        <FilterChip
          label={filter.site}
          onClear={() => onChange({ site: undefined })}
        />
      )}
      {filter.type && typeLabel && (
        <FilterChip
          label={typeLabel}
          onClear={() => onChange({ type: undefined })}
        />
      )}
      {filter.lang && langLabel && (
        <FilterChip
          label={langLabel}
          onClear={() => onChange({ lang: undefined })}
        />
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
        className="min-h-[40px] min-w-[88px] gap-1 md:min-h-0 md:min-w-0"
      >
        <ChevronLeft className="size-3.5" aria-hidden />
        이전
      </Button>
      <span className="hidden md:inline">
        <span className="font-mono">{page + 1}</span> /{' '}
        <span className="font-mono">{totalPages}</span>
      </span>
      <span className="text-fg-3 font-mono text-xs tabular-nums md:hidden">
        {page + 1} / {totalPages}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= totalPages - 1}
        onClick={() => onPage(page + 1)}
        className="min-h-[40px] min-w-[88px] gap-1 md:min-h-0 md:min-w-0"
      >
        다음
        <ChevronRight className="size-3.5" aria-hidden />
      </Button>
    </div>
  );
}

