import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PieChart } from '@/components/charts/PieChart';
import { BarChart } from '@/components/charts/BarChart';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ChartCard } from '@/components/tracker/ChartCard';
import { EmptyState } from '@/components/tracker/EmptyState';
import { RecentAlertList } from '@/components/tracker/RecentAlertList';
import { useStatsQuery } from '@/api/stats';
import { getTypeLabel } from '@/components/tracker/labels';
import { colorForType } from '@/components/charts/colors';
import { PageContainer } from '@/layouts/PageContainer';

const REVIEWED_FRACTION = 0.25; // mock — 백엔드 붙으면 stats에서 받음
const NEXT_CRAWL_LABEL = '42분 후';
const LAST_CRAWL_LABEL = '18분 전';

export function DashboardPage() {
  const { data, isLoading, error } = useStatsQuery();

  if (error) throw error;

  const typeData = useMemo(
    () =>
      data?.typeDistribution.map((entry) => ({
        name: getTypeLabel(entry.type),
        value: entry.count,
      })) ?? [],
    [data?.typeDistribution],
  );
  const typeColors = useMemo(
    () => data?.typeDistribution.map((entry) => colorForType(entry.type)) ?? [],
    [data?.typeDistribution],
  );
  const siteData = useMemo(
    () =>
      data?.siteDistribution.map((entry) => ({
        name: entry.site,
        value: entry.count,
      })) ?? [],
    [data?.siteDistribution],
  );

  if (isLoading || !data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-8">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const isEmpty = data.todayCount === 0;
  const reviewed = Math.round(data.todayCount * REVIEWED_FRACTION);
  const today = new Date().toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  return (
    <PageContainer>
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
            reviewed={reviewed}
          />

          <RecentAlertList />

          <section style={{ marginBottom: 'var(--pad-section)' }}>
            <SectionTitle>Distribution</SectionTitle>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard
                title="유형별 분포"
                subtitle={`오늘 ${data.todayCount}건 기준`}
                empty={typeData.length === 0}
                emptyMessage="유형별 데이터 없음"
              >
                <PieChart data={typeData} colors={typeColors} />
              </ChartCard>

              <ChartCard
                title="사이트별 분포"
                subtitle={`오늘 ${data.todayCount}건 기준`}
                empty={siteData.length === 0}
                emptyMessage="사이트별 데이터 없음"
              >
                <BarChart data={siteData} />
              </ChartCard>
            </div>
          </section>
        </>
      )}
    </PageContainer>
  );
}

interface HeroProps {
  count: number;
  delta: number;
  reviewed: number;
}

function Hero({ count, delta, reviewed }: HeroProps) {
  const reviewPct = count > 0 ? Math.round((reviewed / count) * 100) : 0;
  const deltaSign = delta > 0 ? '↑ +' : delta < 0 ? '↓ ' : '';
  // mock — backend grouping 필드 합류 시 Detection 응답에서 받음
  const dupCount = Math.floor(count * 0.3);
  const uniqueCount = Math.max(0, count - dupCount);

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
      {/* 1. 시스템 상태 한 줄 */}
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
          마지막 크롤{' '}
          <span className="font-medium" style={{ color: 'var(--fg)' }}>
            {LAST_CRAWL_LABEL}
          </span>
        </span>
        <Sep />
        <span>
          다음 예정{' '}
          <span className="font-medium" style={{ color: 'var(--fg)' }}>
            {NEXT_CRAWL_LABEL}
          </span>
        </span>
        <Sep />
        <span>
          큐 <span className="font-medium" style={{ color: 'var(--fg)' }}>0</span>
        </span>
      </div>

      {/* 2. 카운트 + 진척도 + CTA */}
      <div
        className="grid items-center"
        style={{
          gridTemplateColumns: 'auto 1fr auto',
          gap: 'clamp(20px, 2.5vw, 40px)',
        }}
      >
        {/* 좌: 큰 숫자 */}
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
          <span
            className="font-mono font-semibold tabular-nums"
            style={{
              fontSize: 'var(--size-hero-num)',
              lineHeight: 'var(--lh-tight)',
              letterSpacing: 'var(--tracking-tighter)',
              color: 'var(--fg)',
            }}
          >
            {count.toLocaleString('ko-KR')}
          </span>
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
          {/* Alert correlation 힌트 — automation bias 완화 (Pattern E) */}
          <span
            className="font-mono mt-1.5 inline-flex items-baseline gap-2 self-start rounded-full border px-2.5 py-1 text-xs"
            style={{
              background: 'var(--bg-sunk)',
              borderColor: 'var(--border-1)',
              color: 'var(--fg-3)',
            }}
            title="유사 게시글 그룹화"
          >
            <span className="font-medium" style={{ color: 'var(--fg)' }}>
              {uniqueCount}
            </span>
            <span>unique</span>
            <span style={{ color: 'var(--fg-3)' }}>·</span>
            <span className="font-medium" style={{ color: 'var(--fg)' }}>
              {dupCount}
            </span>
            <span>중복</span>
          </span>
        </div>

        {/* 중: 진척도 */}
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <span
              className="font-mono font-semibold tabular-nums"
              style={{
                fontSize: 'var(--text-xl)',
                letterSpacing: 'var(--tracking-tight)',
              }}
            >
              {reviewed}
              <span style={{ color: 'var(--fg-3)', fontWeight: 400 }}>
                {' '}/ {count}
              </span>
            </span>
            <span
              className="text-xs font-medium uppercase"
              style={{ color: 'var(--fg-3)', letterSpacing: '0.08em' }}
            >
              검토됨
            </span>
          </div>
          <div
            className="relative h-2 overflow-hidden rounded"
            style={{ background: 'var(--bg-sunk)' }}
          >
            <div
              className="h-full rounded transition-all"
              style={{ width: `${reviewPct}%`, background: 'var(--accent)' }}
            />
          </div>
          <div
            className="font-mono flex justify-between text-xs"
            style={{ color: 'var(--fg-3)' }}
          >
            <span>{count - reviewed}건 검토 대기</span>
            <span>{reviewPct}% 완료</span>
          </div>
        </div>

        {/* 우: CTA */}
        <Link
          to="/detections"
          aria-label={`탐지 목록 보러 가기 — ${count.toLocaleString('ko-KR')}건`}
          className="group focus-visible:ring-ring/60 inline-flex items-center gap-2.5 whitespace-nowrap rounded-md text-sm font-semibold no-underline transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2"
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

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-baseline justify-between">
      <span
        className="text-xs font-semibold uppercase"
        style={{ color: 'var(--fg-3)', letterSpacing: 'var(--tracking-wider)' }}
      >
        {children}
      </span>
    </div>
  );
}

function Sep() {
  return <span style={{ color: 'var(--border-2)' }}>·</span>;
}
