export type DetectionType =
  | '핵_치트'
  | '사설서버'
  | '불법프로그램_배포'
  | '계정_거래'
  | '매크로_판매'
  | '리세마라'
  | '현금화'
  | '광고_도배'
  | '기타';

export type Language = 'ko' | 'zh-CN' | 'zh-TW';
export type Tier = 'T1' | 'T2' | 'T3' | 'T4';
export type DetectionDateRange = '7d' | '30d';

export interface Detection {
  id: number;
  isIllegal: boolean;
  type: DetectionType;
  tier: Tier;
  confidence: number;
  reason: string;
  rawText: string;
  translatedText: string | null;
  postUrl: string | null;
  siteName: string;
  language: Language;
  detectedAt: string;
}

export interface DetectionListResponse {
  content: Detection[];
  page: number;
  size: number;
  totalElements: number;
}

export interface TypeDistributionEntry {
  type: DetectionType;
  count: number;
}

export interface SiteDistributionEntry {
  site: string;
  count: number;
}

export interface LangDistributionEntry {
  lang: Language;
  count: number;
}

export interface TrendEntry {
  date: string;
  count: number;
}

export interface SourceHealthItem {
  siteName: string;
  lastCrawledAt: string | null;
}

export interface StatsResponse {
  todayCount: number;
  deltaFromYesterday: number;
  typeDistribution: TypeDistributionEntry[];
  siteDistribution: SiteDistributionEntry[];
  langDistribution: LangDistributionEntry[];
  trend?: TrendEntry[];
  sourceHealth?: SourceHealthItem[];
}

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  errorCode: string;
}

export interface DetectionFilter {
  date?: string; // YYYY-MM-DD
  range?: DetectionDateRange;
  site?: string;
  type?: DetectionType;
  lang?: Language;
  page?: number;
  size?: number;
}

export interface CrawlTriggerResponse {
  jobId: string;
  status: 'triggered' | 'in_progress';
  estimatedMinutes: number;
  statusUrl: string;
}

export type CrawlJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'skipped';

export interface CrawlJobStatusResponse {
  jobId: string;
  status: CrawlJobStatus;
  totalSites: number;
  completedSites: number;
  percent: number;
  currentSite: string;
  message: string;
  failedSites: string[];
  requestedAt: string;
  startedAt: string;
  updatedAt: string;
  finishedAt: string;
}

export type StatsPeriod = 'weekly' | 'monthly';

export interface CrawlPipelineStatsResponse {
  listingBoards: number;
  listingDiscoveredTotal: number;
  listingUrlsSelected: number;
  listingKeywordMatched: number;
  listingKeywordUnmatched: number;
  selectedP0: number;
  selectedP1: number;
  selectedP2: number;
  selectedP3: number;
  attempted: number;
  enqueued: number;
  skippedSeenUrl: number;
  skippedDedup: number;
  skippedEmpty: number;
  skippedSticky: number;
  skippedBlocked: number;
  skippedUnknown: number;
  failed: number;
  recordedAt: string;
}

export type NotificationChannelType =
  | 'GENERIC_WEBHOOK'
  | 'DISCORD'
  | 'GOOGLE_CHAT'
  | 'SLACK_WORKFLOW'
  | 'SLACK_WEBHOOK'
  | 'TEAMS_WORKFLOW';

export interface NotificationChannel {
  id: number;
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  configPreview: string;
  lastTestedAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NotificationRule {
  id: number;
  name: string;
  enabled: boolean;
  channelId: number;
  channelName: string;
  minConfidence: number | null;
  minTier: Tier | null;
  detectionType: DetectionType | null;
  sourceSiteName: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NotificationDelivery {
  id: number;
  detectionId: number | null;
  channelId: number | null;
  channelName: string | null;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED';
  responseCode: number | null;
  errorMessage: string | null;
  attemptedAt: string;
  sentAt: string | null;
}

export interface NotificationTestResponse {
  success: boolean;
  responseCode: number | null;
  errorMessage: string | null;
}
