import { isRouteErrorResponse, useRouteError } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProblemDetailError } from '@/api/client';

export function ErrorBoundary() {
  const error = useRouteError();

  let title = '문제가 발생했습니다';
  let detail = '잠시 후 다시 시도해 주세요.';
  let errorCode: string | undefined;

  if (error instanceof ProblemDetailError) {
    title = error.problem.title;
    detail = error.problem.detail;
    errorCode = error.errorCode;
  } else if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`;
    detail = typeof error.data === 'string' ? error.data : detail;
  } else if (error instanceof Error) {
    detail = error.message || detail;
  }

  return (
    <div role="alert" className="mx-auto max-w-xl px-8 py-12">
      <div className="bg-card flex flex-col items-start gap-3 rounded-lg border p-8">
        <AlertCircle className="text-destructive size-6" aria-hidden />
        <h2 className="text-foreground text-lg font-semibold">{title}</h2>
        <p className="text-muted-foreground text-sm">{detail}</p>
        {errorCode && (
          <p className="text-muted-foreground text-xs">
            오류 코드: <code className="font-mono">{errorCode}</code>
          </p>
        )}
        <Button
          variant="default"
          size="sm"
          onClick={() => window.location.reload()}
          className="mt-2"
        >
          새로고침
        </Button>
      </div>
    </div>
  );
}
