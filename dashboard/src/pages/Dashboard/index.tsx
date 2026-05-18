import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PieChart } from '@/components/charts/PieChart';
import { BarChart } from '@/components/charts/BarChart';
import { ChartCard } from '@/components/tracker/ChartCard';
import { EmptyState } from '@/components/tracker/EmptyState';
import { RecentAlertList } from '@/components/tracker/RecentAlertList';
import { useStatsSuspenseQuery } from '@/api/stats';
import { PageContainer } from '@/layouts/PageContainer';
import {
  siteDistributionToSeries,
  typeDistributionToColors,
  typeDistributionToSeries,
} from '@/lib/statsView';
import { formatRelativeTime } from '@/lib/time';

export function DashboardPage() {
  // dataUpdatedAt이 60s polling마다 갱신 → TanStack Query subscription이 자동 re-render
  // 유발. ticker 불필요. 자정 롤오버도 다음 polling tick(<60s)에 자연 반영.
  const { data, dataUpdatedAt } = useStatsSuspenseQuery();

  const typeData = typeDistributionToSeries(data.typeDistribution);
  const typeColors = typeDistributionToColors(data.typeDistribution);
  const siteData = siteDistributionToSeries(data.siteDistribution);

  const isEmpty = data.todayCount === 0;
  const today = new Date(dataUpdatedAt).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const freshness = formatRelativeTime(dataUpdatedAt);

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
  freshness: string;
}

function Hero({ count, delta, freshness }: HeroProps) {
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
