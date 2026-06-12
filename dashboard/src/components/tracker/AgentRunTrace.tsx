import { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { useAgentRunsQuery } from '@/api/detections';
import type { AgentRun, LinkEvidence } from '@/types/api';

const STAGE_LABEL: Record<string, string> = {
  normalize: '정규화',
  triage: '1차 분류',
  image: '이미지 분석',
  link_trace: '링크 추적',
  synthesize: '최종 합성',
};

function latencyText(ms: number | null) {
  if (ms === null) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function KindBadge({ kind }: { kind: LinkEvidence['kind'] }) {
  const map: Record<string, string> = {
    web: 'bg-green-100 text-green-800',
    messenger: 'bg-blue-100 text-blue-800',
    file_direct_link: 'bg-red-100 text-red-800',
    blocked: 'bg-orange-100 text-orange-800',
    error: 'bg-gray-100 text-gray-600',
  };
  const label: Record<string, string> = {
    web: '웹페이지',
    messenger: '메신저',
    file_direct_link: '파일직링크',
    blocked: '차단',
    error: '오류',
  };
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${map[kind] ?? 'bg-gray-100 text-gray-600'}`}>
      {label[kind] ?? kind}
    </span>
  );
}

function LinkEvidenceCard({ ev }: { ev: LinkEvidence }) {
  return (
    <div className={`rounded border p-3 text-xs ${ev.is_distribution_site ? 'border-red-300 bg-red-50' : 'border-border bg-background'}`}>
      <div className="flex items-start gap-2">
        <KindBadge kind={ev.kind} />
        <span className="text-muted-foreground min-w-0 flex-1 break-all font-mono">
          {ev.url}
        </span>
        {ev.is_distribution_site && (
          <span className="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700">
            배포사이트
          </span>
        )}
      </div>
      {ev.page_title && (
        <p className="text-foreground mt-1.5 font-medium">{ev.page_title}</p>
      )}
      {ev.indicators.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {ev.indicators.map((ind) => (
            <span key={ind} className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-gray-700">
              {ind}
            </span>
          ))}
        </div>
      )}
      <p className="text-muted-foreground mt-1 font-mono">{ev.fetch_status}</p>
    </div>
  );
}

function NormalizeDetail({ output }: { output: Record<string, unknown> }) {
  const links = output.links as string[] | undefined;
  const removedChars = output.removed_char_count as number | undefined;
  return (
    <div className="text-muted-foreground mt-2 space-y-1 text-xs">
      {removedChars !== undefined && removedChars > 0 && (
        <p>정규화로 제거된 문자: <span className="text-foreground font-mono">{removedChars}자</span></p>
      )}
      {links && links.length > 0 ? (
        <div>
          <p className="mb-1">추출된 링크 {links.length}개:</p>
          <div className="space-y-0.5">
            {links.map((url) => (
              <p key={url} className="text-foreground break-all font-mono">{url}</p>
            ))}
          </div>
        </div>
      ) : (
        <p>링크 없음</p>
      )}
    </div>
  );
}

function TriageDetail({ output }: { output: Record<string, unknown> }) {
  return (
    <div className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <span>분류: <span className="text-foreground font-medium">{String(output.type ?? '-')}</span></span>
      <span>신뢰도: <span className="text-foreground font-mono">{typeof output.confidence === 'number' ? (output.confidence * 100).toFixed(0) : '-'}%</span></span>
      {Boolean(output.needs_link_trace) && <span className="text-amber-600 font-medium">링크추적 요청</span>}
      {Boolean(output.needs_image) && <span className="text-amber-600 font-medium">이미지분석 요청</span>}
      {Boolean(output.game_context) && (
        <span className="w-full">게임 컨텍스트: <span className="text-foreground">{String(output.game_context)}</span></span>
      )}
    </div>
  );
}

function LinkTraceDetail({ output }: { output: Record<string, unknown> }) {
  const links = output.links as LinkEvidence[] | undefined;
  if (!links || links.length === 0) return <p className="text-muted-foreground mt-2 text-xs">추적된 링크 없음</p>;
  return (
    <div className="mt-2 space-y-2">
      {links.map((ev) => (
        <LinkEvidenceCard key={ev.url} ev={ev} />
      ))}
    </div>
  );
}

function StageRow({ run }: { run: AgentRun }) {
  const [open, setOpen] = useState(run.stage === 'link_trace');
  const label = STAGE_LABEL[run.stage] ?? run.stage;
  const latency = latencyText(run.latencyMs);
  const hasOutput = run.output !== null;

  return (
    <div className="border-b last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/50"
        disabled={!hasOutput}
      >
        <span className="text-muted-foreground w-4 shrink-0">
          {hasOutput ? (
            open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />
          ) : (
            <span className="size-3.5 inline-block" />
          )}
        </span>
        <span className="text-foreground text-sm font-medium">{label}</span>
        {run.model && (
          <span className="text-muted-foreground rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
            {run.model}
          </span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-3">
          {run.inputTokens > 0 && (
            <span className="text-muted-foreground font-mono text-xs">
              {run.inputTokens + run.outputTokens}tok
            </span>
          )}
          {latency && (
            <span className="text-muted-foreground font-mono text-xs">{latency}</span>
          )}
        </span>
      </button>

      {open && run.output && (
        <div className="px-10 pb-4">
          {run.stage === 'normalize' && <NormalizeDetail output={run.output} />}
          {run.stage === 'triage' && <TriageDetail output={run.output} />}
          {run.stage === 'link_trace' && <LinkTraceDetail output={run.output} />}
        </div>
      )}
    </div>
  );
}

export function AgentRunTrace({ detectionId }: { detectionId: number }) {
  const { data, isLoading } = useAgentRunsQuery(detectionId);

  if (isLoading || !data || data.length === 0) return null;

  return (
    <section className="bg-card overflow-hidden rounded-lg border">
      <div className="border-b px-4 py-3 flex items-center gap-2">
        <h2 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          파이프라인 추적
        </h2>
        <span className="text-muted-foreground font-mono text-xs">
          {data.length}단계
        </span>
        <a
          href={`/api/detections/${detectionId}/agent-runs`}
          className="text-muted-foreground hover:text-foreground ml-auto"
          title="raw JSON"
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink className="size-3.5" />
        </a>
      </div>
      {data.map((run) => (
        <StageRow key={run.id} run={run} />
      ))}
    </section>
  );
}
