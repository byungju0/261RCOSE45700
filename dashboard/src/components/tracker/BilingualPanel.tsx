import { cn } from '@/lib/utils';
import { getLangLabel } from './labels';
import type { Language } from '@/types/api';

interface BilingualPanelProps {
  originalText: string;
  originalLang: Language;
  translatedText: string | null;
  className?: string;
}

/**
 * Tracker 시그니처 인터랙션 — 원문/번역 side-by-side. 한국어이거나 번역이 없으면
 * 단일 컬럼. 폰트는 `lang` 속성으로 CSS 측에서 자동 매칭(zh-CN/zh-TW 시스템 스택).
 */
export function BilingualPanel({
  originalText,
  originalLang,
  translatedText,
  className,
}: BilingualPanelProps) {
  const isMonolingual = translatedText === null || originalLang === 'ko';
  const originalHeading = `원문 (${getLangLabel(originalLang)})`;

  if (isMonolingual) {
    return (
      <section aria-label="원문" className={cn('bg-card rounded-lg border p-6', className)}>
        <PanelHeading>{originalHeading}</PanelHeading>
        <PanelText lang={originalLang}>{originalText}</PanelText>
      </section>
    );
  }

  return (
    <section
      aria-label="원문과 번역"
      className={cn(
        'bg-card grid grid-cols-1 gap-0 rounded-lg border md:grid-cols-2',
        className,
      )}
    >
      <div className="border-b p-6 md:border-b-0 md:border-r">
        <PanelHeading>{originalHeading}</PanelHeading>
        <PanelText lang={originalLang}>{originalText}</PanelText>
      </div>
      <div className="p-6">
        <PanelHeading>번역 (한국어)</PanelHeading>
        <PanelText lang="ko">{translatedText}</PanelText>
      </div>
    </section>
  );
}

function PanelHeading({ children }: { children: React.ReactNode }) {
  return (
    <header className="text-muted-foreground mb-3 text-xs font-medium uppercase tracking-wide">
      {children}
    </header>
  );
}

function PanelText({ lang, children }: { lang: Language; children: React.ReactNode }) {
  return (
    <p
      lang={lang}
      className="text-foreground whitespace-pre-wrap text-sm"
      style={{ lineHeight: 'var(--lh-reading, 1.7)' }}
    >
      {children}
    </p>
  );
}
