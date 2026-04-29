import { useState } from 'react';
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
import { useCrawlTriggerMutation } from '@/api/detections';
import { useShortcut } from '@/lib/shortcuts';

/**
 * Journey 2 (긴급 대응) — 수동 크롤링 트리거 + 확인 모달 + 진행 추적.
 *
 * Flow:
 *   클릭 / `g+t` 단축키 → Dialog 열림 → 확인 →
 *   버튼 비활성화 + 스피너 → Toast "트리거 완료, 예상 3분" →
 *   60초 후 폴링 자동 갱신 (api/detections invalidate).
 */
export function ManualCrawlButton() {
  const [open, setOpen] = useState(false);
  const mutation = useCrawlTriggerMutation();

  // g+t 단축키로 모달 열기
  useShortcut('g+t', () => setOpen(true));

  const handleConfirm = async () => {
    try {
      const result = await mutation.mutateAsync();
      toast.success('수동 크롤링 트리거 완료', {
        description: `예상 ${result.estimatedMinutes}분 소요. 완료 시 자동으로 알림됩니다.`,
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
          className="gap-2"
          aria-label="수동 크롤링 트리거 (단축키 g+t)"
        >
          <RefreshCw className="size-3.5" aria-hidden />
          <span>수동 크롤링</span>
          <kbd
            aria-hidden
            className="font-mono ml-0.5 rounded-[3px] px-1.5 py-px text-[10px] font-normal"
            style={{ background: 'var(--bg-sunk)', color: 'var(--fg-3)' }}
          >
            g+t
          </kbd>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>지금 크롤링하시겠습니까?</DialogTitle>
          <DialogDescription>
            모든 등록된 사이트에 대해 즉시 크롤링을 실행합니다. 일반적으로 3분
            내외 소요되며, 완료되면 새로 들어온 탐지가 헤더에 알림됩니다.
          </DialogDescription>
        </DialogHeader>
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
            disabled={mutation.isPending}
            className="gap-1.5"
          >
            {mutation.isPending && (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            )}
            {mutation.isPending ? '실행 중...' : '실행'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
