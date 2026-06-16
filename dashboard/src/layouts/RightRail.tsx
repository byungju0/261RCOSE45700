import { useQuery } from '@tanstack/react-query';
import { Activity as ActivityIcon, Database, RadioTower } from 'lucide-react';
import { statsQueries } from '@/api/stats';
import { useActivityQuery } from '@/api/activity';
import { formatRelativeTime } from '@/lib/time';
import type { SourceHealthItem } from '@/types/api';

const ACTIVITY_DISPLAY_LIMIT = 10;

export function RightRail() {
  const statsQuery = useQuery(statsQueries.byPeriod());
  const activityQuery = useActivityQuery();

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
      <RailSection
        title="활동"
        subtitle="최근 시스템 이벤트"
        icon={<ActivityIcon className="size-3.5" aria-hidden="true" />}
        accent="var(--accent)"
      >
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
      <RailSection
        title="크롤 상태"
        subtitle="소스별 마지막 확인"
        icon={<RadioTower className="size-3.5" aria-hidden="true" />}
        accent="var(--safe)"
      >
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
      <RailSection
        title="데이터 신선도"
        subtitle="마지막 저장 데이터"
        icon={<Database className="size-3.5" aria-hidden="true" />}
        accent="var(--warn, #f59e0b)"
      >
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
    </aside>
  );
}

function sourceStatus(lastCrawledAt: string | null): { label: string; color: string } {
  if (!lastCrawledAt) return { label: '없음', color: 'var(--fg-3)' };
  const diffH = (Date.now() - new Date(lastCrawledAt).getTime()) / 3_600_000;
  if (diffH < 2)   return { label: '방금', color: 'var(--safe)' };
  if (diffH < 24)  return { label: '오늘', color: 'var(--safe)' };
  if (diffH < 168) return { label: '이번 주', color: 'var(--warn, #f59e0b)' };
  return             { label: '오래됨', color: 'var(--fg-3)' };
}

function dataFreshnessStatus(lastIngestedAt: string | null): { label: string; color: string } {
  if (!lastIngestedAt) return { label: '없음', color: 'var(--fg-3)' };
  return sourceStatus(lastIngestedAt);
}

function relativeActionTime(value: string | null, action: '확인' | '저장'): string {
  if (!value) return action === '확인' ? '확인 기록 없음' : '저장 데이터 없음';
  return `${formatRelativeTime(value)} ${action}`;
}

const ACTIVITY_META: Record<string, { variant: ActivityVariant; tag?: string }> = {
  CRAWL_COMPLETED: { variant: 'ok' },
  CRAWL_FAILED:    { variant: 'default' },
  MANUAL_CRAWL_TRIGGERED: { variant: 'self', tag: '나' },
  MANUAL_CRAWL_COMPLETED: { variant: 'ok', tag: '나' },
  MANUAL_CRAWL_FAILED:    { variant: 'default', tag: '나' },
  MANUAL_CRAWL_SKIPPED:   { variant: 'self', tag: '나' },
};

function RailSection({
  title,
  subtitle,
  icon,
  accent,
  children,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col gap-2.5 border-t"
      style={{
        borderColor: 'color-mix(in oklch, var(--border-1) 85%, transparent)',
        paddingTop: '14px',
      }}
    >
      <div className="mb-1.5 flex items-start gap-2">
        <span
          className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-[4px]"
          style={{
            color: accent,
            background: `color-mix(in oklch, ${accent} 12%, transparent)`,
          }}
        >
          {icon}
        </span>
        <span className="min-w-0">
          <span
            className="block text-xs font-semibold"
            style={{ color: 'var(--fg)', lineHeight: 1.25 }}
          >
            {title}
          </span>
          <span
            className="block truncate text-[0.68rem]"
            style={{ color: 'var(--fg-3)', lineHeight: 1.35 }}
          >
            {subtitle}
          </span>
        </span>
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
  const [headline, ...details] = text.split('\n');
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
      <div className="min-w-0">
        <div className="text-[0.95rem] font-medium" style={{ color: 'var(--fg)', lineHeight: 1.5 }}>
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
          {headline}
        </div>
        {details.length > 0 && (
          <div className="mt-1 space-y-0.5" style={{ color: 'var(--fg)', lineHeight: 1.5 }}>
            {details.map((line) => (
              <div key={line} className="text-sm">{line}</div>
            ))}
          </div>
        )}
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
  const sub = relativeActionTime(source.lastCrawledAt, '확인');
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
      <span className="text-right text-xs font-semibold whitespace-nowrap" style={{ color }}>
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
  const sub = relativeActionTime(source.lastIngestedAt, '저장');
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
      <span className="text-right text-xs font-semibold whitespace-nowrap" style={{ color }}>
        {label}
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
