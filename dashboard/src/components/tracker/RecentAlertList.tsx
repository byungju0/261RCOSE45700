import { useNavigate, Link } from 'react-router-dom';
import { useDetectionsQuery } from '@/api/detections';
import { ConfidenceBadge } from './ConfidenceBadge';
import { TypeIcon } from './TypeIcon';
import { getTypeLabel } from './labels';
import { severityOf } from '@/lib/severity';
import { formatRelativeTime } from '@/lib/time';
import { cn } from '@/lib/utils';
import type { Detection } from '@/types/api';

const RECENT_LIMIT = 5;

export function RecentAlertList() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useDetectionsQuery({ size: RECENT_LIMIT });

  const items = data?.content ?? [];
  const total = data?.totalElements ?? 0;

  return (
    <section style={{ marginBottom: 'var(--pad-section)' }}>
      <div className="mb-4 flex items-baseline justify-between">
        <span
          className="text-fg-3 text-xs font-semibold uppercase"
          style={{ letterSpacing: 'var(--tracking-wider)' }}
        >
          Recent · High confidence
        </span>
        <Link
          to="/detections"
          className="text-accent text-xs no-underline hover:underline"
        >
          전체 {total}건 →
        </Link>
      </div>

      <div
        role="list"
        className="bg-bg-elev border-border-1 overflow-hidden rounded-md border"
      >
        {isLoading ? (
          <div className="text-fg-3 px-6 py-8 text-center text-sm">
            불러오는 중…
          </div>
        ) : isError ? (
          <div role="alert" className="text-crit px-6 py-8 text-center text-sm">
            탐지 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
          </div>
        ) : items.length === 0 ? (
          <div className="text-fg-3 px-6 py-8 text-center text-sm">
            아직 탐지된 항목이 없습니다
          </div>
        ) : (
          items.map((d) => (
            <AlertRow
              key={d.id}
              detection={d}
              onClick={() => navigate(`/detections/${d.id}`)}
            />
          ))
        )}
      </div>
    </section>
  );
}

function AlertRow({ detection, onClick }: { detection: Detection; onClick: () => void }) {
  const severity = severityOf(detection.confidence);
  const time = formatRelativeTime(detection.detectedAt);
  const snippet = detection.translatedText ?? detection.rawText;

  return (
    <button
      type="button"
      role="listitem"
      onClick={onClick}
      data-severity={severity}
      title={snippet}
      className={cn(
        'group border-border-1 grid w-full cursor-pointer items-center border-t bg-transparent text-left transition-colors first:border-t-0 hover:bg-[var(--hover)]',
        // color-mix tint는 라이트/다크 자동 swap
        'data-[severity=high]:shadow-[inset_6px_0_0_var(--crit-bg)] data-[severity=high]:bg-[color-mix(in_oklch,var(--crit-bg)_8%,transparent)]',
        'data-[severity=medium]:shadow-[inset_6px_0_0_var(--warn-bg)] data-[severity=medium]:bg-[color-mix(in_oklch,var(--warn-bg)_6%,transparent)]',
      )}
      style={{
        gridTemplateColumns: '52px 28px minmax(120px, 180px) minmax(0, 1fr) 90px',
        gap: 'clamp(10px, 1vw, 18px)',
        padding: 'var(--pad-alert-row-y) var(--pad-alert-row-x)',
      }}
    >
      <ConfidenceBadge score={detection.confidence} aria-hidden />
      <TypeIcon type={detection.type} showLabel={false} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <span
          className="text-fg font-medium"
          style={{ fontSize: 'var(--size-alert-type)' }}
        >
          {getTypeLabel(detection.type)}
        </span>
        <span
          className="text-fg-3 font-mono text-xs"
          style={{ fontFeatureSettings: "'liga' off" }}
        >
          {detection.siteName}
        </span>
      </div>
      <span
        className="text-fg-2 overflow-hidden text-ellipsis whitespace-nowrap"
        style={{ fontSize: 'var(--size-alert-snippet)' }}
      >
        {snippet}
      </span>
      <span className="text-fg-3 font-mono text-right text-xs tabular-nums">
        {time}
      </span>
    </button>
  );
}
