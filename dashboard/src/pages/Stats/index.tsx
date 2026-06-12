import { useState } from 'react';
import { useStatsSuspenseQuery, useCrawlPipelineStatsSuspenseQuery } from '@/api/stats';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart } from '@/components/charts/BarChart';
import { LineChart } from '@/components/charts/LineChart';
import { PieChart } from '@/components/charts/PieChart';
import { ChartCard } from '@/components/tracker/ChartCard';
import { EmptyState } from '@/components/tracker/EmptyState';
import { PageContainer } from '@/layouts/PageContainer';
import {
  langDistributionToSeries,
  siteDistributionToSeries,
  typeDistributionToColors,
  typeDistributionToSeries,
} from '@/lib/statsView';
import type { StatsPeriod } from '@/types/api';

export function StatsPage() {
  const [period, setPeriod] = useState<StatsPeriod>('weekly');
  const { data } = useStatsSuspenseQuery(period);
  const { data: crawlStats } = useCrawlPipelineStatsSuspenseQuery();

  // 'YYYY-MM-DD' → 'M/D' (trend X축 label)
  const trendData =
    data.trend?.map((entry) => ({
      name: entry.date.slice(5).replace('-', '/'),
      value: entry.count,
    })) ?? [];
  const typeData = typeDistributionToSeries(data.typeDistribution);
  const typeColors = typeDistributionToColors(data.typeDistribution);
  const siteData = siteDistributionToSeries(data.siteDistribution);
  const langData = langDistributionToSeries(data.langDistribution);

  const trendEmpty = trendData.length === 0;

  return (
    <PageContainer className="gap-4">
      <title>통계 · Tracker</title>
      <header className="flex items-baseline justify-between">
        <h1
          className="text-foreground font-semibold tracking-tight"
          style={{ fontSize: 'var(--size-h1)', lineHeight: 'var(--lh-snug)' }}
        >
          통계
        </h1>
        <Tabs
          value={period}
          onValueChange={(v) => setPeriod(v as StatsPeriod)}
        >
          <TabsList>
            <TabsTrigger value="weekly">주간</TabsTrigger>
            <TabsTrigger value="monthly">월간</TabsTrigger>
          </TabsList>
        </Tabs>
      </header>

      <ChartCard
        title={period === 'weekly' ? '주간 탐지 추이' : '월간 탐지 추이'}
        subtitle={`최근 ${period === 'weekly' ? '7' : '30'}일 일별 탐지 건수`}
        empty={trendEmpty}
        emptyMessage="해당 기간에 탐지 데이터가 없습니다"
      >
        <LineChart data={trendData} />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="유형별 분포"
          subtitle="현재 기준"
          empty={data.typeDistribution.length === 0}
          emptyMessage="유형별 데이터 없음"
        >
          <PieChart data={typeData} colors={typeColors} />
        </ChartCard>

        <ChartCard
          title="사이트별 분포"
          subtitle="현재 기준"
          empty={data.siteDistribution.length === 0}
          emptyMessage="사이트별 데이터 없음"
        >
          <BarChart data={siteData} />
        </ChartCard>

        <ChartCard
          title="언어별 분포"
          subtitle="현재 기준"
          empty={data.langDistribution.length === 0}
          emptyMessage="언어별 데이터 없음"
        >
          <PieChart data={langData} />
        </ChartCard>

        <div className="bg-card flex flex-col justify-center gap-2 rounded-lg border p-6 text-sm">
          <h2 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
            오늘 요약
          </h2>
          <p className="text-foreground">
            <span className="font-mono text-2xl font-semibold">
              {data.todayCount}
            </span>
            <span className="text-muted-foreground ml-2">건 탐지됨</span>
          </p>
          <p className="text-muted-foreground text-xs">
            전일 대비{' '}
            <span
              className={
                data.deltaFromYesterday > 0
                  ? 'text-destructive'
                  : 'text-muted-foreground'
              }
            >
              {data.deltaFromYesterday > 0 ? '+' : ''}
              {data.deltaFromYesterday}
            </span>
          </p>
          {trendEmpty ? null : (
            <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
              이 화면을 캡처해 주간 보고서에 첨부할 수 있습니다.
              <br />
              CSV 내보내기는 추후 지원 예정입니다.
            </p>
          )}
        </div>
      </div>

      {trendEmpty && (
        <EmptyState
          variant="filter-empty"
          title="해당 기간에 데이터가 없습니다"
          message={`${period === 'weekly' ? '주간' : '월간'} 기간 동안의 탐지 데이터가 비어 있습니다.`}
        />
      )}

      <ChartCard
        title="크롤 파이프라인 Funnel"
        subtitle={crawlStats.recordedAt ? `마지막 실행: ${crawlStats.recordedAt.replace('T', ' ').slice(0, 16)} UTC` : '실행 기록 없음'}
        empty={crawlStats.listingBoards === 0}
        emptyMessage="아직 크롤링이 실행되지 않았습니다"
      >
        <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-4">
          <FunnelStat label="보드" value={crawlStats.listingBoards} />
          <FunnelStat label="후보 발견" value={crawlStats.listingDiscoveredTotal} />
          <FunnelStat
            label="선택"
            value={crawlStats.listingUrlsSelected}
            sub={`P2 ${crawlStats.selectedP2} · P3 ${crawlStats.selectedP3}`}
          />
          <FunnelStat label="본문 fetch" value={crawlStats.attempted} />
          <FunnelStat label="큐 적재" value={crawlStats.enqueued} highlight />
          <FunnelStat label="URL중복" value={crawlStats.skippedSeenUrl} muted />
          <FunnelStat label="본문중복" value={crawlStats.skippedDedup} muted />
          <FunnelStat label="공지/캡차" value={crawlStats.skippedSticky + crawlStats.skippedBlocked} muted />
          <FunnelStat label="빈글/미확인" value={crawlStats.skippedEmpty + crawlStats.skippedUnknown} muted />
          <FunnelStat label="실패" value={crawlStats.failed} danger={crawlStats.failed > 0} />
        </div>
      </ChartCard>
    </PageContainer>
  );
}

function FunnelStat({
  label,
  value,
  sub,
  highlight = false,
  muted = false,
  danger = false,
}: {
  label: string;
  value: number;
  sub?: string;
  highlight?: boolean;
  muted?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span
        className={
          danger
            ? 'text-destructive font-mono text-lg font-semibold'
            : highlight
              ? 'text-foreground font-mono text-lg font-semibold'
              : muted
                ? 'text-muted-foreground font-mono text-base'
                : 'text-foreground font-mono text-base font-medium'
        }
      >
        {value.toLocaleString()}
      </span>
      {sub && <span className="text-muted-foreground text-xs">{sub}</span>}
    </div>
  );
}
