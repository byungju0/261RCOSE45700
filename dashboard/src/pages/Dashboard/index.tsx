import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { LineChart } from '@/components/charts/LineChart';
import { ChartCard } from '@/components/tracker/ChartCard';
import { EmptyState } from '@/components/tracker/EmptyState';
import { RecentAlertList } from '@/components/tracker/RecentAlertList';
import { getTypeLabel } from '@/components/tracker/labels';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useDetectionsSuspenseQuery } from '@/api/detections';
import { useStatsSuspenseQuery } from '@/api/stats';
import { PageContainer } from '@/layouts/PageContainer';
import {
  langDistributionToSeries,
  siteDistributionToSeries,
  typeDistributionToSeries,
} from '@/lib/statsView';
import { detectionFilterToParams } from '@/lib/detectionFilter';
import { formatRelativeTime } from '@/lib/time';
import type { Detection, DetectionFilter, StatsPeriod, Tier } from '@/types/api';

export function DashboardPage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<StatsPeriod>('weekly');
  // dataUpdatedAt이 60s polling마다 갱신 → TanStack Query subscription이 자동 re-render
  // 유발. ticker 불필요. 자정 롤오버도 다음 polling tick(<60s)에 자연 반영.
  const { data, dataUpdatedAt } = useStatsSuspenseQuery(period);
  const { data: detectionData } = useDetectionsSuspenseQuery({ size: 100 });

  const trendData =
    data.trend?.map((entry) => ({
      name: entry.date.slice(5).replace('-', '/'),
      value: entry.count,
      date: entry.date,
    })) ?? [];
  const typeData = typeDistributionToSeries(data.typeDistribution);
  const siteData = siteDistributionToSeries(data.siteDistribution);
  const langData = langDistributionToSeries(data.langDistribution);
  const hotspots = buildHotspots(detectionData.content);

  const isEmpty = data.todayCount === 0;
  const todayDate = useMemo(
    () => new Date(dataUpdatedAt).toLocaleDateString('en-CA'),
    [dataUpdatedAt],
  );
  const today = new Date(dataUpdatedAt).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const freshness = formatRelativeTime(dataUpdatedAt);
  const openDetections = (filter: DetectionFilter) => {
    const params = detectionFilterToParams(filter);
    const query = params.toString();
    navigate(`/detections${query ? `?${query}` : ''}`);
  };

  return (
    <PageContainer>
      <title>대시보드 · Tracker</title>
      <div style={{ marginBottom: 'var(--pad-page-head)' }}>
        <h1
          className="m-0 mb-1 font-semibold"
          style={{
            fontSize: 'var(--size-h1)',
            lineHeight: 'var(--lh-snug)',
            letterSpacing: 'var(--tracking-tight)',
          }}
        >
          오늘의 탐지 현황
        </h1>
        <span
          className="font-mono text-xs tabular-nums"
          style={{ color: 'var(--fg-3)' }}
        >
          {today} KST · 60s 자동 폴링
        </span>
      </div>

      {isEmpty ? (
        <EmptyState
          variant="healthy"
          title="오늘 탐지된 게시글이 없습니다"
          message="시스템 정상 작동 중 · 다음 크롤링 주기에 다시 확인하세요"
        />
      ) : (
        <>
          <Hero
            count={data.todayCount}
            delta={data.deltaFromYesterday}
            freshness={freshness}
            onToday={() => openDetections({ date: todayDate })}
          />

          <RecentAlertList />

          <section style={{ marginBottom: 'var(--pad-section)' }}>
            <div className="mb-4 flex items-baseline justify-between">
              <SectionTitle>Hotspots</SectionTitle>
            </div>
            <HotspotCard
              data={hotspots}
              typeData={typeData}
              siteData={siteData}
              langData={langData}
              onSelect={(entry) => openDetections({ type: entry.type, site: entry.site })}
              onFilter={openDetections}
            />
          </section>

          <section style={{ marginBottom: 'var(--pad-section)' }}>
            <div className="mb-4 flex items-baseline justify-between gap-3">
              <SectionTitle>Period</SectionTitle>
              <Tabs
                value={period}
                onValueChange={(v) => setPeriod(v as StatsPeriod)}
              >
                <TabsList>
                  <TabsTrigger value="weekly">주간</TabsTrigger>
                  <TabsTrigger value="monthly">월간</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            <ChartCard
              title={period === 'weekly' ? '주간 탐지 추이' : '월간 탐지 추이'}
              subtitle="날짜를 클릭하면 해당 일자 탐지 목록으로 이동"
              empty={trendData.length === 0}
              emptyMessage="기간 추이 데이터 없음"
            >
              <div className="flex w-full flex-col gap-3">
                <LineChart data={trendData} />
                <DateDrilldownRow
                  data={trendData}
                  onSelect={(date) => openDetections({ date })}
                />
              </div>
            </ChartCard>
          </section>
        </>
      )}
    </PageContainer>
  );
}

interface HeroProps {
  count: number;
  delta: number;
  freshness: string;
  onToday: () => void;
}

function Hero({ count, delta, freshness, onToday }: HeroProps) {
  const deltaSign = delta > 0 ? '↑ +' : delta < 0 ? '↓ ' : '';

  return (
    <section
      className="mb-8 flex flex-col rounded-md border"
      style={{
        background: 'var(--bg-elev)',
        borderColor: 'var(--border-1)',
        padding: 'var(--pad-hero)',
        gap: 'var(--gap-hero)',
      }}
    >
      <div
        className="font-mono flex flex-wrap items-center gap-4 border-b text-xs"
        style={{
          color: 'var(--fg-3)',
          borderColor: 'var(--border-1)',
          paddingBottom: 'var(--pad-hero-status)',
        }}
      >
        <span className="inline-flex items-center gap-1.5">
          <span
            className="size-2 rounded-full"
            style={{
              background: 'var(--safe)',
              boxShadow: '0 0 0 3px oklch(0.58 0.17 145 / 0.18)',
            }}
          />
          <span className="font-medium" style={{ color: 'var(--safe)' }}>
            시스템 정상
          </span>
        </span>
        <Sep />
        <span>
          데이터 갱신{' '}
          <span className="font-medium" style={{ color: 'var(--fg)' }}>
            {freshness}
          </span>
        </span>
      </div>

      <div
        className="flex flex-wrap items-center justify-between"
        style={{ gap: 'clamp(20px, 2.5vw, 40px)' }}
      >
        <div className="flex flex-col gap-1.5">
          <span
            className="text-xs font-medium uppercase"
            style={{
              color: 'var(--fg-3)',
              letterSpacing: 'var(--tracking-wider)',
            }}
          >
            Today's detections
          </span>
          <button
            type="button"
            onClick={onToday}
            title="오늘 탐지 목록 보기"
            aria-label={`오늘 탐지 목록 보기 — ${count.toLocaleString('ko-KR')}건`}
            className="w-fit cursor-pointer border-0 bg-transparent p-0 text-left hover:opacity-80"
            style={{ color: 'var(--fg)' }}
          >
          <span
            className="font-mono font-semibold tabular-nums"
            style={{
              fontSize: 'var(--size-hero-num)',
              lineHeight: 'var(--lh-tight)',
              letterSpacing: 'var(--tracking-tighter)',
            }}
          >
            {count.toLocaleString('ko-KR')}
          </span>
          </button>
          <span
            className="inline-flex items-baseline gap-2 text-sm font-medium"
            style={{
              color:
                delta > 0 ? 'var(--crit)' : delta < 0 ? 'var(--safe)' : 'var(--fg-2)',
            }}
          >
            {delta === 0 ? (
              <>전일과 동일</>
            ) : (
              <>
                {deltaSign}
                {Math.abs(delta)}
                <span className="text-xs font-normal" style={{ color: 'var(--fg-2)' }}>
                  전일 대비
                </span>
              </>
            )}
          </span>
        </div>

        <Link
          to="/detections"
          aria-label={`탐지 목록 보러 가기 — ${count.toLocaleString('ko-KR')}건`}
          className="group focus-visible:ring-ring/60 inline-flex w-full items-center justify-center gap-2.5 whitespace-nowrap rounded-md text-sm font-semibold no-underline transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 md:w-auto md:justify-start"
          style={{
            padding: '14px 22px',
            background: 'var(--accent)',
            color: 'var(--on-accent)',
          }}
        >
          <span>탐지 목록 보기</span>
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </section>
  );
}

type DrillDatum = {
  name: string;
  value: number;
  type?: DetectionFilter['type'];
  site?: string;
  lang?: DetectionFilter['lang'];
};

type TrendDatum = {
  name: string;
  value: number;
  date: string;
};

function DateDrilldownRow({
  data,
  onSelect,
}: {
  data: TrendDatum[];
  onSelect: (date: string) => void;
}) {
  return (
    <div className="border-border-1 flex gap-1.5 overflow-x-auto border-t pt-3">
      {data.map((entry) => (
        <button
          key={entry.date}
          type="button"
          onClick={() => onSelect(entry.date)}
          aria-label={`${entry.date} 탐지 목록 보기`}
          className="text-fg-2 hover:bg-bg-overlay hover:text-fg shrink-0 rounded-[5px] border px-2 py-1 text-xs transition-colors"
          style={{ borderColor: 'var(--border-1)' }}
        >
          <span className="font-mono">{entry.name}</span>
          <span className="font-mono ml-1 tabular-nums">{entry.value}</span>
        </button>
      ))}
    </div>
  );
}

interface HotspotEntry {
  type: Detection['type'];
  typeLabel: string;
  site: string;
  count: number;
  maxConfidence: number;
  tier: Tier;
}

const TIER_ORDER: Record<Tier, number> = {
  T1: 0,
  T2: 1,
  T3: 2,
  T4: 3,
};

function buildHotspots(detections: readonly Detection[]): HotspotEntry[] {
  const groups = new Map<string, HotspotEntry>();

  detections
    .filter((d) => d.isIllegal)
    .forEach((d) => {
      const key = `${d.type}::${d.siteName}`;
      const prev = groups.get(key);
      if (!prev) {
        groups.set(key, {
          type: d.type,
          typeLabel: getTypeLabel(d.type),
          site: d.siteName,
          count: 1,
          maxConfidence: d.confidence,
          tier: d.tier,
        });
        return;
      }
      prev.count += 1;
      prev.maxConfidence = Math.max(prev.maxConfidence, d.confidence);
      if (TIER_ORDER[d.tier] < TIER_ORDER[prev.tier]) {
        prev.tier = d.tier;
      }
    });

  return Array.from(groups.values())
    .sort((a, b) =>
      TIER_ORDER[a.tier] - TIER_ORDER[b.tier] ||
      b.count - a.count ||
      b.maxConfidence - a.maxConfidence ||
      a.site.localeCompare(b.site),
    )
    .slice(0, 6);
}

function HotspotCard({
  data,
  typeData,
  siteData,
  langData,
  onSelect,
  onFilter,
}: {
  data: HotspotEntry[];
  typeData: DrillDatum[];
  siteData: DrillDatum[];
  langData: DrillDatum[];
  onSelect: (entry: HotspotEntry) => void;
  onFilter: (filter: DetectionFilter) => void;
}) {
  return (
    <ChartCard
      title="우선 조치 패턴"
      subtitle="유형과 출처가 함께 몰린 조합 · 행 클릭 시 조합 필터"
      empty={data.length === 0}
      emptyMessage="우선 조치할 조합이 없습니다"
    >
      <div className="flex w-full flex-col gap-4">
        <div
          className="border-border-1 flex flex-col gap-2 border-b pb-3"
        >
          <span
            className="text-xs font-semibold uppercase"
            style={{ color: 'var(--fg-3)', letterSpacing: 'var(--tracking-wider)' }}
          >
            Quick filters
          </span>
          <FilterChipRow
            data={[
              ...typeData.slice(0, 3),
              ...siteData.slice(0, 3),
              ...langData.slice(0, 2),
            ]}
            onSelect={(entry) => {
              if (entry.type) onFilter({ type: entry.type });
              else if (entry.site) onFilter({ site: entry.site });
              else if (entry.lang) onFilter({ lang: entry.lang });
            }}
          />
        </div>

        <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          {data.map((entry, idx) => (
            <HotspotRow
              key={`${entry.type}-${entry.site}`}
              entry={entry}
              rank={idx + 1}
              onSelect={() => onSelect(entry)}
            />
          ))}
        </div>
      </div>
    </ChartCard>
  );
}

function FilterChipRow({
  data,
  onSelect,
}: {
  data: DrillDatum[];
  onSelect: (entry: DrillDatum) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {data.map((entry) => (
        <button
          key={`${entry.name}-${entry.value}`}
          type="button"
          onClick={() => onSelect(entry)}
          className="text-fg-2 hover:bg-bg-overlay hover:text-fg rounded-[5px] border px-2 py-1 text-xs transition-colors"
          style={{ borderColor: 'var(--border-1)' }}
        >
          {entry.name} {entry.value.toLocaleString('ko-KR')}
        </button>
      ))}
    </div>
  );
}

function tierTone(tier: Tier) {
  switch (tier) {
    case 'T1':
      return { bg: 'oklch(0.58 0.22 28 / 0.14)', fg: 'var(--crit)' };
    case 'T2':
      return { bg: 'oklch(0.7 0.18 55 / 0.14)', fg: 'var(--warn, #b45309)' };
    case 'T3':
      return { bg: 'oklch(0.58 0.15 255 / 0.12)', fg: 'var(--accent)' };
    case 'T4':
      return { bg: 'var(--bg-overlay)', fg: 'var(--fg-3)' };
  }
}

function HotspotRow({
  entry,
  rank,
  onSelect,
}: {
  entry: HotspotEntry;
  rank: number;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="group border-border-1 hover:bg-bg-overlay focus-visible:ring-ring/60 grid w-full cursor-pointer items-center gap-3 rounded-[5px] border bg-transparent px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2"
      style={{ gridTemplateColumns: '28px minmax(0,1fr) auto' }}
      aria-label={`${entry.typeLabel} ${entry.site} 탐지 목록 보기 — ${entry.count.toLocaleString('ko-KR')}건`}
    >
      <span
        className="font-mono text-xs tabular-nums"
        style={{ color: 'var(--fg-3)' }}
      >
        {String(rank).padStart(2, '0')}
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="flex min-w-0 items-center gap-2">
          <span
            className="font-mono rounded-[4px] px-1.5 py-px text-[0.68rem] font-semibold"
            style={{
              background: tierTone(entry.tier).bg,
              color: tierTone(entry.tier).fg,
            }}
          >
            {entry.tier}
          </span>
          <span
            className="text-fg truncate font-medium"
            style={{ fontSize: '0.875rem' }}
          >
            {entry.typeLabel}
          </span>
        </span>
        <span className="font-mono truncate text-xs" style={{ color: 'var(--fg-3)' }}>
          {entry.site} · 최고 신뢰도 {Math.round(entry.maxConfidence * 100)}%
        </span>
      </span>
      <span
        className="font-mono text-sm font-semibold tabular-nums"
        style={{ color: 'var(--fg)' }}
      >
        {entry.count.toLocaleString('ko-KR')}건
      </span>
    </button>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-xs font-semibold uppercase"
      style={{ color: 'var(--fg-3)', letterSpacing: 'var(--tracking-wider)' }}
    >
      {children}
    </span>
  );
}

function Sep() {
  return <span style={{ color: 'var(--border-2)' }}>·</span>;
}
