import { KNOWN_SOURCES } from '@/lib/sources';

/**
 * 오른쪽 레일 — Activity / Source health / Pipeline.
 * MVP는 정적 mock 값. 백엔드 API 붙으면 실데이터 swap.
 */
export function RightRail() {
  return (
    <aside
      aria-label="시스템 활동 패널"
      className="border-border-1 sticky top-0 flex h-screen flex-col self-start overflow-y-auto border-l"
      style={{
        background: 'var(--bg-sunk)',
        padding: 'clamp(20px, 2vw, 36px) clamp(16px, 1.6vw, 28px)',
        gap: 'clamp(24px, 2.5vw, 40px)',
      }}
    >
      {/* 1. Activity */}
      <RailSection title="Activity">
        <ActivityItem variant="self" tag="나" text="5건 검토 완료" time="10:14 — 10:38" />
        <ActivityItem variant="ok" text="새 탐지 3건 추가됨" time="3분 전" />
        <ActivityItem variant="self" tag="나" text="2건 FP로 표시" time="11:02" />
        <ActivityItem variant="default" text="크롤링 사이클 완료 (6/6)" time="18분 전" />
        <ActivityItem variant="ok" text="DLQ 비워짐" time="1시간 전" />
      </RailSection>

      {/* 2. Source health */}
      <RailSection title="Source health">
        <div className="flex flex-col">
          {KNOWN_SOURCES.map((src) => (
            <HealthRow key={src} name={src} />
          ))}
        </div>
      </RailSection>

      {/* 3. Pipeline */}
      <RailSection title="Pipeline">
        <div className="flex flex-col">
          <MetricRow name="Crawler queue" value="0" />
          <MetricRow name="Detection processing" value="0" />
          <MetricRow name="DLQ" value="0" />
          <MetricRow name="VARCO RPM" value="12 / 60" />
        </div>
      </RailSection>
    </aside>
  );
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

function HealthRow({ name }: { name: string }) {
  return (
    <div
      className="grid items-center border-b last:border-b-0"
      style={{
        gridTemplateColumns: '16px 1fr auto',
        gap: '12px',
        padding: '10px 0',
        borderColor: 'var(--border-1)',
      }}
    >
      <span className="size-2.5 rounded-full" style={{ background: 'var(--safe)' }} />
      <span className="font-mono" style={{ color: 'var(--fg-2)', fontSize: 'var(--text-base-mono)' }}>
        {name}
      </span>
      <span
        className="font-mono text-right"
        style={{ color: 'var(--fg-3)', fontSize: 'var(--text-base-mono)' }}
      >
        OK
      </span>
    </div>
  );
}

function MetricRow({ name, value }: { name: string; value: string }) {
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
        style={{ color: 'var(--fg)', fontSize: 'var(--text-base-mono)' }}
      >
        {value}
      </span>
    </div>
  );
}
