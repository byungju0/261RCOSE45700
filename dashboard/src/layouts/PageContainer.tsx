import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageContainerProps {
  children: ReactNode;
  className?: string;
}

/** 모든 페이지의 외곽 wrapper — 3-col main 안에서 동일 호흡 (`var(--pad-page)`). */
export function PageContainer({ children, className }: PageContainerProps) {
  return (
    <div
      className={cn('mx-auto flex w-full max-w-[1300px] flex-col', className)}
      style={{ padding: 'var(--pad-page)' }}
    >
      {children}
    </div>
  );
}
