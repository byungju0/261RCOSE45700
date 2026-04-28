import { http, HttpResponse } from 'msw';
import type { CrawlTriggerResponse, DetectionListResponse } from '@/types/api';
import { MOCK_DETECTIONS, buildStatsResponse, getDetectionById } from './data';

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

// Story 4.5 — 수동 트리거 시점 기록. since=triggered 필터링용.
let lastTriggerAt: number | null = null;

export const handlers = [
  // GET /stats?period=weekly|monthly
  http.get(`${baseUrl}/stats`, ({ request }) => {
    const url = new URL(request.url);
    const period = url.searchParams.get('period');
    if (period && period !== 'weekly' && period !== 'monthly') {
      return HttpResponse.json(
        {
          type: 'about:blank',
          title: 'Invalid period',
          status: 400,
          detail: `period must be 'weekly' or 'monthly', got '${period}'`,
          errorCode: 'INVALID_FILTER_PARAM',
        },
        { status: 400 },
      );
    }
    return HttpResponse.json(
      buildStatsResponse(period as 'weekly' | 'monthly' | null ?? undefined),
    );
  }),

  // GET /detections — list with filters + pagination
  http.get(`${baseUrl}/detections`, ({ request }) => {
    const url = new URL(request.url);
    const date = url.searchParams.get('date');
    const site = url.searchParams.get('site');
    const type = url.searchParams.get('type');
    const lang = url.searchParams.get('lang');
    const since = url.searchParams.get('since');
    const page = Number(url.searchParams.get('page') ?? '0');
    const size = Number(url.searchParams.get('size') ?? '20');

    let filtered = MOCK_DETECTIONS;

    if (date) {
      filtered = filtered.filter((d) => d.detectedAt.startsWith(date));
    }
    if (site) {
      filtered = filtered.filter((d) => d.siteName === site);
    }
    if (type) {
      filtered = filtered.filter((d) => d.type === type);
    }
    if (lang) {
      filtered = filtered.filter((d) => d.language === lang);
    }
    if (since === 'triggered' && lastTriggerAt != null) {
      filtered = filtered.filter(
        (d) => new Date(d.detectedAt).getTime() >= lastTriggerAt!,
      );
    }

    const totalElements = filtered.length;
    const start = page * size;
    const end = start + size;
    const content = filtered.slice(start, end);

    const response: DetectionListResponse = {
      content,
      page,
      size,
      totalElements,
    };
    return HttpResponse.json(response);
  }),

  // GET /detections/:id
  http.get(`${baseUrl}/detections/:id`, ({ params }) => {
    const id = Number(params.id);
    const detection = getDetectionById(id);
    if (!detection) {
      return HttpResponse.json(
        {
          type: 'https://tracker.internal/errors/detection-not-found',
          title: 'Detection Not Found',
          status: 404,
          detail: `Detection with id=${id} does not exist`,
          errorCode: 'DETECTION_NOT_FOUND',
        },
        { status: 404 },
      );
    }
    return HttpResponse.json(detection);
  }),

  // POST /crawl/trigger
  http.post(`${baseUrl}/crawl/trigger`, () => {
    lastTriggerAt = Date.now();
    // 데모 환경: since=triggered 필터가 빈 결과로 안 보이게, 가장 최근 3건의
    // detectedAt을 현재 시각으로 덮어씀. 실배포 백엔드에서는 신규 크롤 결과가
    // 자연스럽게 detectedAt > lastTriggerAt 조건을 만족.
    const now = new Date(lastTriggerAt).toISOString();
    MOCK_DETECTIONS.slice(0, 3).forEach((d) => {
      d.detectedAt = now;
    });
    const response: CrawlTriggerResponse = {
      status: 'triggered',
      estimatedMinutes: 3,
    };
    return HttpResponse.json(response, { status: 202 });
  }),
];
