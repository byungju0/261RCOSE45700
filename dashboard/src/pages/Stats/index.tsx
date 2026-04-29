import { useMemo, useState } from 'react';
import { useStatsQuery } from '@/api/stats';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart } from '@/components/charts/BarChart';
import { LineChart } from '@/components/charts/LineChart';
import { PieChart } from '@/components/charts/PieChart';
import { ChartCard } from '@/components/tracker/ChartCard';
import { EmptyState } from '@/components/tracker/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { colorForType } from '@/components/charts/colors';
import { getLangLabel, getTypeLabel } from '@/components/tracker/labels';
import { PageContainer } from '@/layouts/PageContainer';
import type { StatsPeriod } from '@/types/api';

export function StatsPage() {
  const [period, setPeriod] = useState<StatsPeriod>('weekly');
  const { data, isLoading, error } = useStatsQuery(period);
  if (error) throw error;

  // hooks는 early return 위에 — 데이터 없으면 빈 배열로 떨어지게.
  const trendData = useMemo(
    () =>
      data?.trend?.map((entry) => ({
        // 'YYYY-MM-DD' → 'M/D'
        name: entry.date.slice(5).replace('-', '/'),
        value: entry.count,
      })) ?? [],
    [data?.trend],
  );
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
  const langData = useMemo(
    () =>
      data?.langDistribution.map((entry) => ({
        name: getLangLabel(entry.lang),
        value: entry.count,
      })) ?? [],
    [data?.langDistribution],
  );

  if (isLoading || !data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-8">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const trendEmpty = trendData.length === 0;

  return (
    <PageContainer className="gap-4">
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
    </PageContainer>
  );
}
