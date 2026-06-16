import { useState } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  ImageIcon,
  Link2,
} from 'lucide-react';
import { useAgentRunsQuery } from '@/api/detections';
import { getTypeLabel } from '@/components/tracker/labels';
import type {
  AgentRun,
  GenericStageOutput,
  LinkEvidence,
  LinkTraceAgentRun,
  LinkTraceOutput,
  NormalizeAgentRun,
  NormalizeOutput,
  TriageAgentRun,
  TriageOutput,
} from '@/types/api';

function isNormalizeRun(run: AgentRun | undefined): run is NormalizeAgentRun {
  return run?.stage === 'normalize';
}

function isTriageRun(run: AgentRun | undefined): run is TriageAgentRun {
  return run?.stage === 'triage';
}

function isLinkTraceRun(run: AgentRun | undefined): run is LinkTraceAgentRun {
  return run?.stage === 'link_trace';
}

const STAGE_META: Record<AgentRun['stage'], {
  icon: typeof FileText;
  label: string;
  title: string;
}> = {
  normalize: {
    icon: FileText,
    label: '정리',
    title: '본문과 링크를 정리했습니다',
  },
  triage: {
    icon: Brain,
    label: '판단',
    title: 'AI가 게시글 유형을 먼저 판단했습니다',
  },
  image: {
    icon: ImageIcon,
    label: '이미지',
    title: '이미지 증거가 있는지 확인했습니다',
  },
  link_trace: {
    icon: Link2,
    label: '링크',
    title: '외부 링크가 위험 사이트로 이어지는지 확인했습니다',
  },
  synthesize: {
    icon: CheckCircle2,
    label: '결론',
    title: '단계별 증거를 최종 판단으로 정리했습니다',
  },
};

function latencyText(ms: number | null) {
  if (ms === null) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function percent(value: number | undefined) {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '-';
}

function detectionTypeLabel(value: TriageOutput['type']) {
  return value ? getTypeLabel(value) : '-';
}

function linksFromRun(run: AgentRun | undefined): LinkEvidence[] {
  return isLinkTraceRun(run) ? run.output?.links ?? [] : [];
}

function extractedLinksFromRun(run: AgentRun | undefined): string[] {
  return isNormalizeRun(run) ? run.output?.links ?? [] : [];
}

function fetchStatusLabel(status: string) {
  if (status === 'ok') return '접속 확인';
  if (status.startsWith('skipped:messenger')) return '메신저 링크라 열람 생략';
  if (status.startsWith('blocked')) return '안전 정책으로 차단';
  if (status.startsWith('error:http_404')) return '페이지 없음';
  if (status.startsWith('error')) return '접속 실패';
  return status;
}

const dangerSurface = 'color-mix(in oklch, var(--crit) 14%, var(--bg-elev))';
const dangerBorder = 'color-mix(in oklch, var(--crit) 45%, var(--border-1))';
const dangerMuted = 'color-mix(in oklch, var(--crit) 18%, var(--bg-elev))';
const dangerText = 'color-mix(in oklch, var(--crit) 82%, var(--fg))';
const linkSurface = 'color-mix(in oklch, var(--accent) 12%, var(--bg-elev))';
const linkBorder = 'color-mix(in oklch, var(--accent) 45%, var(--border-1))';

function KindBadge({ kind }: { kind: LinkEvidence['kind'] }) {
  const label: Record<string, string> = {
    web: '일반 웹 링크',
    messenger: '메신저 채널',
    file_direct_link: '파일 다운로드 링크',
    blocked: '열람 차단',
    error: '확인 오류',
  };
  return (
    <span
      className="rounded px-1.5 py-0.5 text-xs font-medium"
      style={{
        background: 'var(--bg-sunk)',
        border: '1px solid var(--border-1)',
        color: 'var(--fg-2)',
      }}
    >
      링크 유형: {label[kind] ?? kind}
    </span>
  );
}

function SummaryItem({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'danger' | 'success';
}) {
  const toneClass = {
    default: 'text-foreground',
    danger: '',
    success: 'text-fg',
  }[tone];

  return (
    <div
      className="rounded-md border px-3 py-2"
      style={{
        background: tone === 'danger' ? dangerSurface : 'var(--bg-elev)',
        borderColor: tone === 'danger' ? dangerBorder : 'var(--border-1)',
      }}
    >
      <p className="text-muted-foreground text-xs">{label}</p>
      <p
        className={`mt-0.5 text-sm font-semibold ${toneClass}`}
        style={tone === 'danger' ? { color: dangerText } : undefined}
      >
        {value}
      </p>
    </div>
  );
}

function StageSummary({ data }: { data: AgentRun[] }) {
  const normalizeRun = data.find(isNormalizeRun);
  const triageRun = data.find(isTriageRun);
  const linkRun = data.find(isLinkTraceRun);
  const extractedLinks = extractedLinksFromRun(normalizeRun);
  const checkedLinks = linksFromRun(linkRun);
  const riskyLinks = checkedLinks.filter((link) => link.is_distribution_site);
  const type = detectionTypeLabel(triageRun?.output?.type);
  const confidence = percent(triageRun?.output?.confidence);

  return (
    <div className="border-b px-4 py-4" style={{ background: 'var(--bg-sunk)' }}>
      <div className="grid gap-2 sm:grid-cols-4">
        <SummaryItem label="AI 판단" value={type} />
        <SummaryItem label="신뢰도" value={confidence} />
        <SummaryItem label="본문 링크" value={`${extractedLinks.length}개`} />
        <SummaryItem
          label="위험 링크"
          value={`${riskyLinks.length}개`}
          tone={riskyLinks.length > 0 ? 'danger' : 'success'}
        />
      </div>
      {riskyLinks.length > 0 ? (
        <div
          className="mt-3 rounded-md border p-3"
          style={{ background: dangerSurface, borderColor: dangerBorder }}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" style={{ color: dangerText }} aria-hidden />
            <div className="min-w-0">
              <p className="text-sm font-semibold" style={{ color: dangerText }}>
                가장 중요한 근거: 외부 링크 {riskyLinks.length}개에서 배포·판매 정황을 찾았습니다.
              </p>
              {riskyLinks[0].page_title && (
                <p className="mt-1 text-sm" style={{ color: dangerText }}>
                  {riskyLinks[0].page_title}
                </p>
              )}
              <a
                href={riskyLinks[0].url}
                target="_blank"
                rel="noreferrer"
                className="mt-1.5 inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 break-all font-mono text-xs no-underline hover:underline"
                style={{ borderColor: dangerBorder, background: 'var(--bg-elev)', color: dangerText }}
              >
                <Link2 className="size-3 shrink-0" aria-hidden />
                {riskyLinks[0].url}
                <ExternalLink className="size-3 shrink-0" aria-hidden />
              </a>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded-md border p-3" style={{ background: 'var(--bg-elev)', borderColor: 'var(--border-1)' }}>
          <p className="text-sm font-medium text-foreground">
            확인된 외부 링크에서 직접적인 배포·판매 정황은 발견되지 않았습니다.
          </p>
        </div>
      )}
    </div>
  );
}

function LinkEvidenceCard({ ev }: { ev: LinkEvidence }) {
  return (
    <div
      className="rounded-md border p-3 text-xs"
      style={{
        background: ev.is_distribution_site ? dangerSurface : 'var(--bg-elev)',
        borderColor: ev.is_distribution_site ? dangerBorder : 'var(--border-1)',
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <KindBadge kind={ev.kind} />
        {ev.is_distribution_site && (
          <span
            className="rounded px-1.5 py-0.5 text-xs font-semibold"
            style={{ background: dangerMuted, border: `1px solid ${dangerBorder}`, color: dangerText }}
          >
            위험 근거
          </span>
        )}
      </div>

      {ev.page_title && (
        <p className="text-foreground mt-2.5 text-sm font-semibold leading-snug">
          {ev.page_title}
        </p>
      )}
      <a
        href={ev.url}
        target="_blank"
        rel="noreferrer"
        className="mt-1.5 inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 break-all font-mono text-[11px] no-underline hover:underline"
        style={{ borderColor: linkBorder, background: linkSurface, color: 'var(--accent)' }}
      >
        <Link2 className="size-3 shrink-0" aria-hidden />
        {ev.url}
        <ExternalLink className="size-3 shrink-0" aria-hidden />
      </a>

      <p
        className={`mt-2.5 text-sm font-medium ${ev.is_distribution_site ? '' : 'text-foreground'}`}
        style={ev.is_distribution_site ? { color: dangerText } : undefined}
      >
        {ev.is_distribution_site
          ? '배포·판매 정황이 있는 링크입니다'
          : '직접적인 배포 정황은 확인되지 않았습니다'}
      </p>
      {ev.indicators.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {ev.indicators.map((ind) => (
            <span
              key={ind}
              className="rounded px-1.5 py-0.5 font-mono"
              style={{ background: 'var(--bg-sunk)', color: 'var(--fg-2)' }}
            >
              {ind}
            </span>
          ))}
        </div>
      )}
      <p
        className="text-muted-foreground mt-2.5 border-t pt-2 font-mono"
        style={{ borderColor: 'var(--border-1)' }}
      >
        확인 상태: {fetchStatusLabel(ev.fetch_status)}
      </p>
    </div>
  );
}

function NormalizeDetail({ output }: { output: NormalizeOutput }) {
  const links = output.links;
  const removedChars = output.removed_char_count;
  return (
    <div className="text-muted-foreground mt-3 space-y-2 text-xs">
      {removedChars !== undefined && removedChars > 0 && (
        <p>
          숨김 문자·깨진 문자처럼 판단을 방해할 수 있는 글자{' '}
          <span className="text-foreground font-mono">{removedChars}자</span>를 정리했습니다.
        </p>
      )}
      {links && links.length > 0 ? (
        <div>
          <p className="mb-1">
            본문에서 외부 링크 <span className="text-foreground font-mono">{links.length}개</span>를 찾았습니다.
          </p>
          <div className="space-y-0.5">
            {links.map((url) => (
              <p key={url} className="text-foreground break-all font-mono">{url}</p>
            ))}
          </div>
        </div>
      ) : (
        <p>본문에서 외부 링크는 발견되지 않았습니다.</p>
      )}
    </div>
  );
}

function TriageDetail({ output }: { output: TriageOutput }) {
  return (
    <div className="text-muted-foreground mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <span>
        AI는 이 게시글을{' '}
        <span className="text-foreground font-medium">{detectionTypeLabel(output.type)}</span>
        로 판단했습니다.
      </span>
      <span>신뢰도 <span className="text-foreground font-mono">{percent(output.confidence)}</span></span>
      {output.needs_link_trace && <span className="font-medium text-amber-600">외부 링크 확인 필요</span>}
      {output.needs_image && <span className="font-medium text-amber-600">이미지 확인 필요</span>}
      {output.game_context && (
        <span className="w-full">게임 컨텍스트: <span className="text-foreground">{output.game_context}</span></span>
      )}
    </div>
  );
}

function GenericDetail({ output }: { output: GenericStageOutput }) {
  const summary = output.summary ?? output.reason ?? output.result ?? output.decision;
  if (typeof summary === 'string' && summary.trim().length > 0) {
    return <p className="text-muted-foreground mt-3 text-xs leading-relaxed">{summary}</p>;
  }

  const entries = Object.entries(output).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) {
    return <p className="text-muted-foreground mt-3 text-xs">표시할 세부 결과가 없습니다.</p>;
  }

  return (
    <dl className="text-muted-foreground mt-3 grid gap-1 text-xs sm:grid-cols-[120px_1fr]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="font-mono">{key}</dt>
          <dd className="text-foreground min-w-0 break-words">
            {typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
              ? String(value)
              : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function LinkTraceDetail({ output }: { output: LinkTraceOutput }) {
  const links = output.links;
  if (!links || links.length === 0) return <p className="text-muted-foreground mt-3 text-xs">확인할 외부 링크가 없습니다.</p>;
  const risky = links.filter((ev) => ev.is_distribution_site).length;
  return (
    <div className="mt-3 space-y-2">
      <p
        className={`text-xs font-medium ${risky > 0 ? '' : 'text-muted-foreground'}`}
        style={risky > 0 ? { color: dangerText } : undefined}
      >
        {risky > 0
          ? `외부 링크 ${links.length}개 중 ${risky}개에서 배포·판매 정황을 찾았습니다.`
          : `외부 링크 ${links.length}개를 확인했지만 배포 정황은 확인되지 않았습니다.`}
      </p>
      {links.map((ev) => (
        <LinkEvidenceCard key={ev.url} ev={ev} />
      ))}
    </div>
  );
}

function stageResult(run: AgentRun) {
  if (!run.output) return '처리 결과가 없습니다.';
  if (run.stage === 'normalize') {
    const links = run.output.links?.length ?? 0;
    const removed = run.output.removed_char_count ?? 0;
    return `외부 링크 ${links}개 추출 · 방해 문자 ${removed}자 정리`;
  }
  if (run.stage === 'triage') {
    return `${detectionTypeLabel(run.output.type)} · 신뢰도 ${percent(run.output.confidence)}`;
  }
  if (run.stage === 'link_trace') {
    const links = run.output.links ?? [];
    const risky = links.filter((ev) => ev.is_distribution_site).length;
    return risky > 0
      ? `위험 링크 ${risky}개 확인`
      : `확인한 ${links.length}개 링크에서 직접 배포 정황 없음`;
  }
  const summary = run.output.summary ?? run.output.reason ?? run.output.result ?? run.output.decision;
  return typeof summary === 'string' && summary.trim().length > 0
    ? summary
    : '세부 결과를 접힌 영역에서 확인할 수 있습니다.';
}

function StageRow({ run, index, total }: { run: AgentRun; index: number; total: number }) {
  const links = isLinkTraceRun(run) ? run.output?.links ?? [] : [];
  const hasRisk = links.some((link) => link.is_distribution_site);
  const [open, setOpen] = useState(run.stage === 'link_trace' && hasRisk);
  const meta = STAGE_META[run.stage];
  const Icon = meta.icon;
  const latency = latencyText(run.latencyMs);
  const hasOutput = run.output !== null;

  return (
    <li className="relative grid grid-cols-[32px_1fr] gap-3 pb-4 last:pb-0">
      {index < total - 1 && (
        <span className="absolute left-4 top-8 h-[calc(100%-32px)] w-px bg-border" aria-hidden />
      )}
      <div
        className="z-10 flex size-8 items-center justify-center rounded-full border"
        style={{
          background: hasRisk ? dangerSurface : 'var(--bg-elev)',
          borderColor: hasRisk ? dangerBorder : 'var(--border-2)',
          color: hasRisk ? dangerText : 'var(--fg-3)',
        }}
      >
        {hasRisk ? <AlertTriangle className="size-4" aria-hidden /> : <CheckCircle2 className="size-4" aria-hidden />}
      </div>
      <div
        className="rounded-md border"
        style={{
          background: 'var(--bg-elev)',
          borderColor: hasRisk ? dangerBorder : 'var(--border-1)',
        }}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-start gap-3 p-3 text-left transition-colors hover:bg-muted/50"
          disabled={!hasOutput}
          aria-expanded={open}
        >
          <span className="mt-0.5 rounded bg-muted px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
            {index + 1}
          </span>
          <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">{meta.label}</span>
              <span className="text-sm text-foreground">{meta.title}</span>
              {hasRisk && (
                <span
                  className="rounded px-1.5 py-0.5 text-xs font-semibold"
                  style={{ background: dangerMuted, border: `1px solid ${dangerBorder}`, color: dangerText }}
                >
                  주의 필요
                </span>
              )}
            </span>
            <span className="mt-1 block text-xs text-muted-foreground">{stageResult(run)}</span>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
            {latency && <span className="hidden font-mono text-xs sm:inline">{latency}</span>}
            {hasOutput ? (
              open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />
            ) : null}
          </span>
        </button>

        {open && run.output && (
          <div className="border-t px-4 pb-4">
            {run.stage === 'normalize' && <NormalizeDetail output={run.output} />}
            {run.stage === 'triage' && <TriageDetail output={run.output} />}
            {run.stage === 'link_trace' && <LinkTraceDetail output={run.output} />}
            {(run.stage === 'image' || run.stage === 'synthesize') && <GenericDetail output={run.output} />}
            {(run.model || run.inputTokens > 0 || latency) && (
              <p className="mt-3 font-mono text-[11px] text-muted-foreground">
                기술 로그: {run.model ?? 'LLM 미사용'}
                {run.inputTokens > 0 ? ` · ${run.inputTokens + run.outputTokens}tok` : ''}
                {latency ? ` · ${latency}` : ''}
              </p>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function EmptyAgentRunTrace({ detectionId }: { detectionId: number }) {
  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">
            AI 검증 과정
          </h2>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            로그 없음
          </span>
          <a
            href={`/api/detections/${detectionId}/agent-runs`}
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground no-underline hover:text-foreground"
            title="원본 처리 로그"
            target="_blank"
            rel="noreferrer"
          >
            원본 로그
            <ExternalLink className="size-3.5" />
          </a>
        </div>
      </div>
      <div className="px-4 py-4" style={{ background: 'var(--bg-sunk)' }}>
        <div className="rounded-md border p-4" style={{ background: 'var(--bg-elev)', borderColor: 'var(--border-1)' }}>
          <p className="text-sm font-semibold text-foreground">
            이 탐지는 단계별 검증 로그가 저장되어 있지 않습니다.
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            이전 방식으로 처리된 탐지이거나, agentic 검증 모드가 켜지기 전에 저장된 결과입니다.
            새로 처리되는 탐지부터 게시글 정리, AI 판단, 외부 링크 확인 과정이 표시됩니다.
          </p>
        </div>
      </div>
    </section>
  );
}

export function AgentRunTrace({ detectionId }: { detectionId: number }) {
  const { data, isLoading } = useAgentRunsQuery(detectionId);

  if (isLoading || !data) return null;
  if (data.length === 0) return <EmptyAgentRunTrace detectionId={detectionId} />;
  const linkRun = data.find((run) => run.stage === 'link_trace');
  const riskyLinks = linksFromRun(linkRun).filter((link) => link.is_distribution_site).length;

  return (
    <section className="overflow-hidden rounded-lg border bg-card">
      <div className="border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">
            AI 검증 과정
          </h2>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            {data.length}단계
          </span>
          {riskyLinks > 0 && (
            <span
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold"
              style={{ background: dangerMuted, border: `1px solid ${dangerBorder}`, color: dangerText }}
            >
              <AlertTriangle className="size-3" aria-hidden />
              위험 링크 {riskyLinks}개
            </span>
          )}
          <a
            href={`/api/detections/${detectionId}/agent-runs`}
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground no-underline hover:text-foreground"
            title="원본 처리 로그"
            target="_blank"
            rel="noreferrer"
          >
            원본 로그
            <ExternalLink className="size-3.5" />
          </a>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          먼저 결론을 보고, 필요한 단계만 펼쳐서 근거와 원본 로그를 확인하세요.
        </p>
      </div>

      <StageSummary data={data} />

      <ol className="p-4">
        {data.map((run, index) => (
          <StageRow key={run.id} run={run} index={index} total={data.length} />
        ))}
      </ol>
    </section>
  );
}
