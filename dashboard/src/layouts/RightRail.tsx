import { useQuery } from '@tanstack/react-query';
import { statsQueries } from '@/api/stats';
import { useActivityQuery } from '@/api/activity';
import { useCrawlerQueueQuery, useCorruptQueueQuery, useDlqDepthQuery, useProcessingQueueQuery } from '@/api/metrics';
import { formatRelativeTime } from '@/lib/time';
import type { SourceHealthItem } from '@/types/api';

const ACTIVITY_DISPLAY_LIMIT = 10;

export function RightRail() {
  const statsQuery = useQuery(statsQueries.byPeriod());
  const activityQuery = useActivityQuery();
  const crawlerQueueQuery = useCrawlerQueueQuery();
  const processingQueueQuery = useProcessingQueueQuery();
  const dlqQuery = useDlqDepthQuery();
  const corruptQueueQuery = useCorruptQueueQuery();

  const sourceHealth = statsQuery.data?.sourceHealth ?? [];
  const activities = activityQuery.data ?? [];
  const visibleActivities = activities.slice(0, ACTIVITY_DISPLAY_LIMIT);

  return (
    <aside
      aria-label="시스템 활동 패널"
      className="border-border-1 sticky top-0 hidden h-screen flex-col self-start overflow-y-auto border-l lg:flex"
      style={{
        background: 'var(--bg-sunk)',
        padding: 'clamp(20px, 2vw, 36px) clamp(16px, 1.6vw, 28px)',
        gap: 'clamp(24px, 2.5vw, 40px)',
      }}
    >
      {/* 1. Activity */}
      <RailSection title="Activity">
        {activities.length === 0 ? (
          <EmptyRow label={activityQuery.isLoading ? '불러오는 중…' : '활동 없음'} />
        ) : (
          visibleActivities.map((a) => {
            const meta = ACTIVITY_META[a.eventType] ?? { variant: 'default' as ActivityVariant, tag: undefined };
            return (
              <ActivityItem
                key={a.id}
                variant={meta.variant}
                tag={meta.tag}
                text={a.message}
                time={formatRelativeTime(a.occurredAt)}
              />
            );
          })
        )}
      </RailSection>

      {/* 2. Source health */}
      <RailSection title="Source health">
        <div className="flex flex-col">
          {sourceHealth.length === 0 ? (
            <EmptyRow label={statsQuery.isLoading ? '불러오는 중…' : '소스 없음'} />
          ) : (
            sourceHealth.map((source) => (
              <SourceHealthRow key={source.siteName} source={source} />
            ))
          )}
        </div>
      </RailSection>

      {/* 3. Data freshness */}
      <RailSection title="Data freshness">
        <div className="flex flex-col">
          {sourceHealth.length === 0 ? (
            <EmptyRow label={statsQuery.isLoading ? '불러오는 중…' : '데이터 없음'} />
          ) : (
            sourceHealth.map((source) => (
              <DataFreshnessRow key={source.siteName} source={source} />
            ))
          )}
        </div>
      </RailSection>

      {/* 4. Pipeline */}
      <RailSection title="Pipeline">
        <div className="flex flex-col">
          <MetricRow name="Crawler queue" value={fmtQueue(crawlerQueueQuery.data)} />
          <MetricRow name="Processing" value={fmtQueue(processingQueueQuery.data)} />
          <MetricRow name="DLQ" value={fmtQueue(dlqQuery.data)} warn={Boolean(dlqQuery.data && dlqQuery.data > 0)} />
          <MetricRow name="Corrupt" value={fmtQueue(corruptQueueQuery.data)} warn={Boolean(corruptQueueQuery.data && corruptQueueQuery.data > 0)} />
          <MetricRow name="오늘 탐지" value={statsQuery.data ? String(statsQuery.data.todayCount) : '—'} />
          <MetricRow name="전일 대비" value={statsQuery.data ? formatDelta(statsQuery.data.deltaFromYesterday) : '—'} />
        </div>
      </RailSection>
    </aside>
  );
}

function fmtQueue(val: number | undefined): string {
  return val !== undefined ? String(val) : '—';
}

function sourceStatus(lastCrawledAt: string | null): { label: string; color: string } {
  if (!lastCrawledAt) return { label: 'UNKNOWN', color: 'var(--fg-3)' };
  const diffH = (Date.now() - new Date(lastCrawledAt).getTime()) / 3_600_000;
  if (diffH < 2)   return { label: 'ACTIVE',  color: 'var(--safe)' };
  if (diffH < 24)  return { label: 'OK',      color: 'var(--safe)' };
  if (diffH < 168) return { label: 'STALE',   color: 'var(--warn, #f59e0b)' };
  return             { label: 'OLD',    color: 'var(--fg-3)' };
}

function dataFreshnessStatus(lastIngestedAt: string | null): { label: string; color: string } {
  if (!lastIngestedAt) return { label: 'NO DATA', color: 'var(--fg-3)' };
  return sourceStatus(lastIngestedAt);
}

const ACTIVITY_META: Record<string, { variant: ActivityVariant; tag?: string }> = {
  CRAWL_COMPLETED: { variant: 'ok' },
  CRAWL_FAILED:    { variant: 'default' },
  MANUAL_CRAWL_TRIGGERED: { variant: 'self', tag: '나' },
  MANUAL_CRAWL_COMPLETED: { variant: 'ok', tag: '나' },
  MANUAL_CRAWL_FAILED:    { variant: 'default', tag: '나' },
  MANUAL_CRAWL_SKIPPED:   { variant: 'self', tag: '나' },
};

function formatDelta(delta: number): string {
  if (delta === 0) return '±0';
  return delta > 0 ? `+${delta}` : String(delta);
}

function RailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5">
      <div
        className="mb-2 text-xs font-semibold uppercase"
        style={{ color: 'var(--fg-3)', letterSpacing: '0.1em' }}
      >
        {title}
      </div>
      {children}
    </section>
  );
}

type ActivityVariant = 'default' | 'ok' | 'self';

function ActivityItem({
  variant,
  text,
  time,
  tag,
}: {
  variant: ActivityVariant;
  text: string;
  time: string;
  tag?: string;
}) {
  const dotBg =
    variant === 'ok' ? 'var(--safe)' : variant === 'self' ? 'var(--accent)' : 'var(--fg-3)';
  return (
    <div
      className="grid border-b text-sm last:border-b-0"
      style={{
        gridTemplateColumns: '10px 1fr',
        gap: '12px',
        padding: '12px 0',
        borderColor: 'var(--border-1)',
        ...(variant === 'self' && {
          background: 'color-mix(in oklch, var(--accent) 5%, transparent)',
        }),
      }}
    >
      <span
        className="mt-1.5 size-2.5 shrink-0 rounded-full"
        style={{ background: dotBg }}
      />
      <div>
        <div style={{ color: 'var(--fg-2)', lineHeight: 1.5 }}>
          {tag && (
            <span
              className="font-mono mr-1.5 inline-block rounded-[3px] px-1.5 py-px text-xs font-semibold uppercase"
              style={{
                background: 'var(--accent)',
                color: 'var(--on-accent)',
                letterSpacing: '0.04em',
              }}
            >
              {tag}
            </span>
          )}
          {text}
        </div>
        <div
          className="font-mono mt-1 text-xs tabular-nums"
          style={{ color: 'var(--fg-3)' }}
        >
          {time}
        </div>
      </div>
    </div>
  );
}

function SourceHealthRow({ source }: { source: SourceHealthItem }) {
  const { label, color } = sourceStatus(source.lastCrawledAt);
  const title = source.lastCrawledAt
    ? `마지막 크롤 시도: ${new Date(source.lastCrawledAt).toLocaleString('ko-KR')}`
    : '크롤 시도 이력 없음';
  const sub = source.lastCrawledAt
    ? `fetch ${source.fetched} · queue ${source.queued} · skip ${source.validatorSkipped} · fail ${source.failed}`
    : 'run 없음';
  return (
    <div
      className="grid items-center border-b last:border-b-0"
      style={{
        gridTemplateColumns: '16px 1fr auto',
        gap: '12px',
        padding: '10px 0',
        borderColor: 'var(--border-1)',
      }}
      title={title}
    >
      <span className="size-2.5 rounded-full" style={{ background: color }} />
      <span className="min-w-0">
        <span className="font-mono block truncate" style={{ color: 'var(--fg-2)', fontSize: 'var(--text-base-mono)' }}>
          {source.siteName}
        </span>
        <span className="font-mono block truncate text-[0.65rem]" style={{ color: 'var(--fg-3)' }}>
          {sub}
        </span>
      </span>
      <span className="font-mono text-right" style={{ color, fontSize: 'var(--text-base-mono)' }}>
        {label}
      </span>
    </div>
  );
}

function DataFreshnessRow({ source }: { source: SourceHealthItem }) {
  const { label, color } = dataFreshnessStatus(source.lastIngestedAt);
  const title = source.lastIngestedAt
    ? `마지막 저장 데이터: ${new Date(source.lastIngestedAt).toLocaleString('ko-KR')}`
    : '저장된 데이터 없음';
  return (
    <div
      className="grid items-center border-b last:border-b-0"
      style={{
        gridTemplateColumns: '16px 1fr auto',
        gap: '12px',
        padding: '10px 0',
        borderColor: 'var(--border-1)',
      }}
      title={title}
    >
      <span className="size-2.5 rounded-full" style={{ background: color }} />
      <span className="font-mono truncate" style={{ color: 'var(--fg-2)', fontSize: 'var(--text-base-mono)' }}>
        {source.siteName}
      </span>
      <span className="font-mono text-right" style={{ color, fontSize: 'var(--text-base-mono)' }}>
        {label}
      </span>
    </div>
  );
}

function MetricRow({ name, value, warn = false }: { name: string; value: string; warn?: boolean }) {
  return (
    <div
      className="grid items-baseline border-b text-sm last:border-b-0"
      style={{
        gridTemplateColumns: '1fr auto',
        gap: '8px',
        padding: '10px 0',
        borderColor: 'var(--border-1)',
      }}
    >
      <span style={{ color: 'var(--fg-2)' }}>{name}</span>
      <span
        className="font-mono font-medium tabular-nums"
        style={{ color: warn ? 'var(--warn, #f59e0b)' : 'var(--fg)', fontSize: 'var(--text-base-mono)' }}
      >
        {value}
      </span>
    </div>
  );
}

function EmptyRow({ label }: { label: string }) {
  return (
    <span className="text-sm" style={{ color: 'var(--fg-3)' }}>
      {label}
    </span>
  );
}
