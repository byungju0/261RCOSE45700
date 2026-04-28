import { ArrowLeft, Copy, ExternalLink } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';

import { useDetectionQuery } from '@/api/detections';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { BilingualPanel } from '@/components/tracker/BilingualPanel';
import { ConfidenceBadge } from '@/components/tracker/ConfidenceBadge';
import { TypeIcon } from '@/components/tracker/TypeIcon';
import { PageContainer } from '@/layouts/PageContainer';
import { useShortcut } from '@/lib/shortcuts';
import { formatRelativeTime } from '@/lib/time';

export function DetectionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ? Number(params.id) : undefined;
  const navigate = useNavigate();

  const { data, isLoading, error } = useDetectionQuery(id);
  if (error) throw error;

  const handleOpen = () => {
    if (!data) return;
    window.open(data.postUrl, '_blank', 'noopener,noreferrer');
  };

  const handleCopy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.postUrl);
      toast.success('링크 복사됨', { duration: 2000 });
    } catch {
      toast.error('링크 복사 실패', { duration: 3000 });
    }
  };

  useShortcut('o', () => handleOpen());
  useShortcut('c', () => void handleCopy());
  useShortcut('Escape', () => navigate('/detections'));

  if (isLoading || !data) {
    return (
      <PageContainer className="gap-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageContainer>
    );
  }

  const detectedTime = formatRelativeTime(data.detectedAt);

  return (
    <PageContainer className="gap-4">
      <div className="flex items-center justify-between">
        <Link
          to="/detections"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs transition-colors"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          목록으로
        </Link>
        <span className="text-muted-foreground font-mono text-xs">
          ID: {data.id}
        </span>
      </div>

      <section className="bg-card flex flex-col gap-3 rounded-lg border p-6">
        <header className="flex flex-wrap items-center gap-3">
          <ConfidenceBadge score={data.confidence} />
          <TypeIcon type={data.type} />
          <span className="text-muted-foreground font-mono text-xs">
            {data.siteName}
          </span>
          <span className="text-muted-foreground ml-auto text-xs">
            {detectedTime}
          </span>
        </header>
        <div className="border-t pt-3">
          <h2 className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wide">
            AI 판단 근거
          </h2>
          <p className="text-foreground text-sm leading-relaxed">{data.reason}</p>
        </div>
      </section>

      <BilingualPanel
        originalText={data.rawText}
        originalLang={data.language}
        translatedText={data.translatedText}
      />

      <section className="bg-card flex flex-col gap-3 rounded-lg border p-6">
        <h2 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          조치
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={handleOpen} className="gap-1.5">
            <ExternalLink className="size-4" aria-hidden />
            원본 게시글 열기
            <kbd className="bg-primary-foreground/15 ml-2 rounded px-1.5 py-0.5 font-mono text-xs">
              o
            </kbd>
          </Button>
          <Button variant="outline" onClick={handleCopy} className="gap-1.5">
            <Copy className="size-4" aria-hidden />
            링크 복사
            <kbd className="bg-muted ml-2 rounded px-1.5 py-0.5 font-mono text-xs">
              c
            </kbd>
          </Button>
          <span className="text-muted-foreground ml-auto text-xs font-mono">
            <kbd className="bg-muted rounded px-1.5 py-0.5">esc</kbd> 목록 복귀
          </span>
        </div>
        <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
          이 게시글은 신뢰도 임계값(0.70) 이상으로 분류된 탐지 결과입니다. 원본
          사이트로 이동해 외부 신고 절차를 진행하세요. AI 판단을 절대화하지
          않으며, 최종 판단은 담당자가 수행합니다.
        </p>
      </section>
    </PageContainer>
  );
}
