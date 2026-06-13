import { http, HttpResponse } from 'msw';
import type {
  AgentRun,
  CrawlJobStatusResponse,
  CrawlPipelineStatsResponse,
  CrawlTriggerResponse,
  DetectionListResponse,
  NotificationChannel,
  NotificationDelivery,
  NotificationRule,
} from '@/types/api';
import { MOCK_DETECTIONS, buildStatsResponse, getDetectionById } from './data';

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

const mockNotificationChannels: NotificationChannel[] = [];
const mockNotificationRules: NotificationRule[] = [];
const mockNotificationDeliveries: NotificationDelivery[] = [];
const mockActivityLog: { id: number; eventType: string; message: string; occurredAt: string }[] = [];

function maskWebhookUrl(value: string) {
  return `••••${value.slice(-6)}`;
}

export const handlers = [
  // GET /stats?days=N
  http.get(`${baseUrl}/stats`, ({ request }) => {
    const url = new URL(request.url);
    const period = url.searchParams.get('period');
    const daysParam = url.searchParams.get('days');
    const days = daysParam ? Number(daysParam) : undefined;
    if (days !== undefined && (!Number.isFinite(days) || days < 1 || days > 365)) {
      return HttpResponse.json(
        {
          type: 'about:blank',
          title: 'Invalid days',
          status: 400,
          detail: `days must be between 1 and 365, got '${daysParam}'`,
          errorCode: 'INVALID_FILTER_PARAM',
        },
        { status: 400 },
      );
    }
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
      buildStatsResponse(days ?? (period === 'monthly' ? 30 : period === 'weekly' ? 7 : undefined)),
    );
  }),

  // GET /detections — list with filters + pagination
  http.get(`${baseUrl}/detections`, ({ request }) => {
    const url = new URL(request.url);
    const date = url.searchParams.get('date');
    const range = url.searchParams.get('range');
    const site = url.searchParams.get('site');
    const type = url.searchParams.get('type');
    const lang = url.searchParams.get('lang');
    const tier = url.searchParams.get('tier');
    const page = Number(url.searchParams.get('page') ?? '0');
    const size = Number(url.searchParams.get('size') ?? '20');

    let filtered = MOCK_DETECTIONS;

    if (date) {
      filtered = filtered.filter((d) => d.detectedAt.startsWith(date));
    } else if (range) {
      const days = Number(range.toLowerCase().endsWith('d') ? range.slice(0, -1) : range);
      const from = new Date();
      from.setHours(0, 0, 0, 0);
      from.setDate(from.getDate() - (days - 1));
      filtered = filtered.filter((d) => Date.parse(d.detectedAt) >= from.getTime());
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
    if (tier) {
      filtered = filtered.filter((d) => d.tier === tier);
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

  // GET /detections/:id/agent-runs — agentic 파이프라인 추적 모크
  http.get(`${baseUrl}/detections/:id/agent-runs`, ({ params }) => {
    const id = Number(params.id);

    const runs: AgentRun[] = [
      {
        id: id * 10 + 1,
        stage: 'normalize',
        model: null,
        inputTokens: 0,
        outputTokens: 0,
        costUsd: 0,
        latencyMs: 12,
        output: {
          links: ['https://short.url/abc123', 'https://t.me/hacktools'],
          removed_char_count: 3,
        },
      },
      {
        id: id * 10 + 2,
        stage: 'triage',
        model: 'gpt-4o-mini',
        inputTokens: 312,
        outputTokens: 48,
        costUsd: 0.000095,
        latencyMs: 820,
        output: {
          type: '핵_치트',
          confidence: 0.91,
          game_context: '배틀그라운드',
          needs_image: false,
          needs_link_trace: true,
        },
      },
      {
        id: id * 10 + 3,
        stage: 'link_trace',
        model: null,
        inputTokens: 0,
        outputTokens: 0,
        costUsd: 0,
        latencyMs: 1340,
        output: {
          links: [
            {
              url: 'https://short.url/abc123',
              kind: 'web',
              fetch_status: 'ok',
              page_title: 'Free PUBG Hack Download — No Ban Guaranteed',
              is_distribution_site: true,
              indicators: ['hack download', 'no ban', 'crack', '무료 다운로드'],
            },
            {
              url: 'https://t.me/hacktools',
              kind: 'messenger',
              fetch_status: 'skipped:messenger',
              page_title: null,
              is_distribution_site: false,
              indicators: [],
            },
          ],
        },
      },
    ];
    return HttpResponse.json(runs);
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
    const response: CrawlTriggerResponse = {
      jobId: 'mock-crawl-job',
      status: 'triggered',
      statusUrl: '/api/crawl/jobs/mock-crawl-job',
    };
    return HttpResponse.json(response, { status: 202 });
  }),

  // GET /crawl/stats
  http.get(`${baseUrl}/crawl/stats`, () => {
    const response: CrawlPipelineStatsResponse = {
      listingBoards: 14,
      listingDiscoveredTotal: 182,
      listingUrlsSelected: 109,
      listingKeywordMatched: 43,
      listingKeywordUnmatched: 69,
      selectedP0: 0,
      selectedP1: 4,
      selectedP2: 48,
      selectedP3: 61,
      attempted: 98,
      enqueued: 61,
      skippedSeenUrl: 14,
      skippedDedup: 8,
      skippedEmpty: 3,
      skippedSticky: 11,
      skippedBlocked: 2,
      skippedUnknown: 1,
      failed: 1,
      recordedAt: '2026-06-05T03:00:00Z',
    };
    return HttpResponse.json(response);
  }),

  // GET /crawl/jobs/:jobId
  http.get(`${baseUrl}/crawl/jobs/:jobId`, ({ params }) => {
    const response: CrawlJobStatusResponse = {
      jobId: String(params.jobId),
      status: 'running',
      totalSites: 8,
      completedSites: 3,
      percent: 38,
      currentSite: 'bahamut',
      message: 'bahamut 처리 중',
      failedSites: [],
      requestedAt: '2026-05-28T00:00:00Z',
      startedAt: '2026-05-28T00:00:01Z',
      updatedAt: '2026-05-28T00:01:00Z',
      finishedAt: '',
    };
    return HttpResponse.json(response);
  }),

  http.get(`${baseUrl}/notifications/channels`, () => (
    HttpResponse.json(mockNotificationChannels)
  )),

  http.post(`${baseUrl}/notifications/channels`, async ({ request }) => {
    const body = await request.json() as {
      name: string;
      type: NotificationChannel['type'];
      webhookUrl: string;
      enabled: boolean;
    };
    const now = new Date().toISOString();
    const channel: NotificationChannel = {
      id: mockNotificationChannels.length + 1,
      name: body.name,
      type: body.type,
      enabled: body.enabled,
      configPreview: maskWebhookUrl(body.webhookUrl),
      lastTestedAt: null,
      lastSuccessAt: null,
      lastFailureAt: null,
      createdAt: now,
      updatedAt: now,
    };
    mockNotificationChannels.unshift(channel);
    return HttpResponse.json(channel, { status: 201 });
  }),

  http.post(`${baseUrl}/notifications/channels/:id/test`, ({ params }) => {
    const id = Number(params.id);
    const channel = mockNotificationChannels.find((item) => item.id === id);
    if (channel) {
      const now = new Date().toISOString();
      channel.lastTestedAt = now;
      channel.lastSuccessAt = now;
      mockNotificationDeliveries.unshift({
        id: mockNotificationDeliveries.length + 1,
        detectionId: null,
        channelId: channel.id,
        channelName: channel.name,
        status: 'SUCCESS',
        responseCode: 200,
        errorMessage: null,
        attemptedAt: now,
        sentAt: now,
      });
    }
    return HttpResponse.json({ success: true, responseCode: 200, errorMessage: null });
  }),

  http.get(`${baseUrl}/notifications/rules`, () => (
    HttpResponse.json(mockNotificationRules)
  )),

  http.post(`${baseUrl}/notifications/rules`, async ({ request }) => {
    const body = await request.json() as {
      name: string;
      channelId: number;
      enabled: boolean;
      minConfidence: number | null;
      minTier: NotificationRule['minTier'];
      detectionType: NotificationRule['detectionType'];
      sourceSiteName: string | null;
    };
    const channel = mockNotificationChannels.find((item) => item.id === body.channelId);
    const now = new Date().toISOString();
    const rule: NotificationRule = {
      id: mockNotificationRules.length + 1,
      name: body.name,
      enabled: body.enabled,
      channelId: body.channelId,
      channelName: channel?.name ?? '알 수 없는 채널',
      minConfidence: body.minConfidence,
      minTier: body.minTier,
      detectionType: body.detectionType,
      sourceSiteName: body.sourceSiteName,
      createdAt: now,
      updatedAt: now,
    };
    mockNotificationRules.unshift(rule);
    return HttpResponse.json(rule, { status: 201 });
  }),

  http.get(`${baseUrl}/notifications/deliveries`, () => (
    HttpResponse.json(mockNotificationDeliveries)
  )),

  // GET /activity
  http.get(`${baseUrl}/activity`, () => HttpResponse.json(mockActivityLog)),

  // POST /activity
  http.post(`${baseUrl}/activity`, async ({ request }) => {
    const body = await request.json() as { eventType: string; message: string };
    mockActivityLog.unshift({
      id: mockActivityLog.length + 1,
      eventType: body.eventType,
      message: body.message,
      occurredAt: new Date().toISOString(),
    });
    return new HttpResponse(null, { status: 204 });
  }),
];
