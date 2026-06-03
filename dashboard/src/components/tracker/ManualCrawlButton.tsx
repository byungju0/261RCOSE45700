import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  useCrawlJobStatusQuery,
  useCrawlTriggerMutation,
} from '@/api/detections';
import { useLogActivityMutation } from '@/api/activity';
import { Kbd } from '@/components/ui/kbd';
import { useShortcut } from '@/lib/shortcuts';
import {
  estimatedMinutesToDurationMs,
  formatCrawlRemaining,
  getCrawlProgressSnapshot,
} from '@/lib/crawlProgress';
import type { CrawlJobStatus } from '@/types/api';

interface CrawlProgressWindow {
  startedAtMs: number;
  durationMs: number;
}

const TERMINAL_STATUSES = new Set<CrawlJobStatus>([
  'succeeded',
  'failed',
  'skipped',
]);

function crawlStatusTitle(status: CrawlJobStatus | undefined): string {
  switch (status) {
    case 'succeeded':
      return '크롤링 완료';
    case 'failed':
      return '크롤링 실패';
    case 'skipped':
      return '크롤링 건너뜀';
    default:
      return '크롤링 진행 중';
  }
}

/** Journey 2 (긴급 대응) 수동 크롤링 트리거 — 확인 Dialog + g+t 단축키. */
export function ManualCrawlButton() {
  const [open, setOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [progressWindow, setProgressWindow] =
    useState<CrawlProgressWindow | null>(() => {
      try {
        const s = sessionStorage.getItem('crawl:progressWindow');
        return s ? (JSON.parse(s) as CrawlProgressWindow) : null;
      } catch { return null; }
    });
  const [jobId, setJobId] = useState<string | null>(
    () => sessionStorage.getItem('crawl:jobId'),
  );

  const persistJobId = useCallback((id: string | null) => {
    setJobId(id);
    if (id) sessionStorage.setItem('crawl:jobId', id);
    else sessionStorage.removeItem('crawl:jobId');
  }, []);

  const persistProgressWindow = useCallback((pw: CrawlProgressWindow | null) => {
    setProgressWindow(pw);
    if (pw) sessionStorage.setItem('crawl:progressWindow', JSON.stringify(pw));
    else sessionStorage.removeItem('crawl:progressWindow');
  }, []);
  const mutation = useCrawlTriggerMutation();
  const { mutate: logActivity } = useLogActivityMutation();
  const jobStatusQuery = useCrawlJobStatusQuery(jobId);
  const jobStatus = jobStatusQuery.data;
  const jobStatusStatus = jobStatus?.status;
  const loggedJobIdRef = useRef<string | null>(null);

  const estimatedProgress = useMemo(() => {
    if (!progressWindow) return null;
    return getCrawlProgressSnapshot(
      progressWindow.startedAtMs,
      progressWindow.durationMs,
      nowMs,
    );
  }, [nowMs, progressWindow]);

  const isTerminal = jobStatusStatus ? TERMINAL_STATUSES.has(jobStatusStatus) : false;
  const progressPercent = jobStatus?.percent ?? estimatedProgress?.percent ?? 0;
  const isCrawlActive =
    jobStatus !== undefined
      ? !isTerminal
      : estimatedProgress !== null && !estimatedProgress.isComplete;
  const statusTitle = crawlStatusTitle(jobStatus?.status);
  const progressLabel = jobStatus
    ? `${progressPercent}% · ${jobStatus.message || '상태 확인 중'}`
    : estimatedProgress
      ? `${estimatedProgress.percent}% · ${formatCrawlRemaining(estimatedProgress.remainingMs)}`
      : null;

  useShortcut('g+t', () => setOpen(true));

  useEffect(() => {
    if (!progressWindow) return undefined;

    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);

    return () => window.clearInterval(intervalId);
  }, [progressWindow]);

  useEffect(() => {
    if (!isTerminal || !jobStatusStatus || !jobId) return;
    if (loggedJobIdRef.current === jobId) return;
    loggedJobIdRef.current = jobId;

    if (jobStatusStatus === 'succeeded') {
      logActivity({ eventType: 'MANUAL_CRAWL_COMPLETED', message: '수동 크롤링 완료' });
    } else if (jobStatusStatus === 'failed') {
      logActivity({ eventType: 'MANUAL_CRAWL_FAILED', message: '수동 크롤링 실패' });
    } else if (jobStatusStatus === 'skipped') {
      logActivity({ eventType: 'MANUAL_CRAWL_SKIPPED', message: '수동 크롤링 스킵 — 이미 실행 중' });
    }
  }, [isTerminal, jobStatusStatus, jobId, logActivity]);

  useEffect(() => {
    if (!estimatedProgress?.isComplete && !isTerminal) return undefined;

    const timeoutId = window.setTimeout(() => {
      persistProgressWindow(null);
      persistJobId(null);
    }, 3_000);

    return () => window.clearTimeout(timeoutId);
  }, [estimatedProgress?.isComplete, isTerminal, persistJobId, persistProgressWindow]);

  const handleConfirm = async () => {
    try {
      const result = await mutation.mutateAsync();
      logActivity({ eventType: 'MANUAL_CRAWL_TRIGGERED', message: '수동 크롤링 트리거됨' });
      const startedAtMs = Date.now();
      setNowMs(startedAtMs);
      persistJobId(result.jobId);
      persistProgressWindow({
        startedAtMs,
        durationMs: estimatedMinutesToDurationMs(result.estimatedMinutes),
      });
      toast.success('수동 크롤링 트리거 완료', {
        description: `예상 ${result.estimatedMinutes}분 소요. 60초 폴링으로 새 탐지가 화면에 반영됩니다.`,
        duration: 3000,
      });
      setOpen(false);
    } catch (err) {
      toast.error('트리거 실패', {
        description:
          err instanceof Error ? err.message : '잠시 후 다시 시도해 주세요.',
        duration: 5000,
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="relative min-w-[7.25rem] overflow-hidden gap-2"
          aria-label="수동 크롤링 트리거 (단축키 g+t)"
        >
          <span
            className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-primary/70 transition-transform duration-500"
            style={{
              transform: `scaleX(${progressPercent / 100})`,
            }}
            aria-hidden
          />
          <RefreshCw
            className={`size-3.5 ${isCrawlActive ? 'animate-spin' : ''}`}
            aria-hidden
          />
          <span>{isCrawlActive ? '크롤링 중' : '수동 크롤링'}</span>
          {isCrawlActive ? (
            <span className="hidden text-[0.68rem] text-muted-foreground tabular-nums lg:inline">
              {progressLabel}
            </span>
          ) : (
            <Kbd
              aria-hidden
              variant="outline"
              size="xs"
              className="ml-0.5 hidden md:inline-flex"
            >
              g+t
            </Kbd>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>지금 크롤링하시겠습니까?</DialogTitle>
          <DialogDescription>
            모든 등록된 사이트에 대해 즉시 크롤링을 실행합니다. 일반적으로 3분
            내외 소요되며, 완료되면 대시보드·목록이 다음 폴링 주기(최대 60초)에
            자동 갱신됩니다.
          </DialogDescription>
        </DialogHeader>
        {progressLabel && (
          <div
            className="space-y-2 rounded-lg border border-border bg-muted/40 p-3"
            aria-live="polite"
          >
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium">{statusTitle}</span>
              <span className="text-muted-foreground tabular-nums">
                {progressLabel}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-background"
              role="progressbar"
              aria-valuenow={progressPercent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="수동 크롤링 진행률"
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            {jobStatus && (
              <p className="text-xs text-muted-foreground">
                {jobStatus.completedSites}/{jobStatus.totalSites}개 사이트 완료
                {jobStatus.currentSite ? ` · 현재 ${jobStatus.currentSite}` : ''}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={mutation.isPending}
          >
            취소
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={mutation.isPending || isCrawlActive}
            className="gap-1.5"
          >
            {mutation.isPending && (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            )}
            {mutation.isPending
              ? '실행 중...'
              : isCrawlActive
                ? '이미 실행 중'
                : '실행'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
