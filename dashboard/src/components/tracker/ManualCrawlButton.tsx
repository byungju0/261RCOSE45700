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
import { Kbd } from '@/components/ui/kbd';
import { useShortcut } from '@/lib/shortcuts';

/** Journey 2 (긴급 대응) 수동 크롤링 트리거 — 확인 Dialog + g+t 단축키. */
export function ManualCrawlButton() {
  const [open, setOpen] = useState(false);
  const mutation = useCrawlTriggerMutation();

  useShortcut('g+t', () => setOpen(true));

  const handleConfirm = async () => {
    try {
      const result = await mutation.mutateAsync();
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
          className="gap-2"
          aria-label="수동 크롤링 트리거 (단축키 g+t)"
        >
          <RefreshCw className="size-3.5" aria-hidden />
          <span>수동 크롤링</span>
          <Kbd
            aria-hidden
            variant="outline"
            size="xs"
            className="ml-0.5 hidden md:inline-flex"
          >
            g+t
          </Kbd>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>지금 크롤링하시겠습니까?</DialogTitle>
          <DialogDescription>
            모든 등록된 사이트에 대해 즉시 크롤링을 실행합니다. 일반적으로 3분
            내외 소요되며, 완료되면 목록·통계가 다음 폴링 주기(최대 60초)에
            자동 갱신됩니다.
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
