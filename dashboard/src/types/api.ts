export type DetectionType =
  | '매크로_판매'
  | '핵_배포'
  | '계정_거래'
  | '리세마라'
  | '기타';

export type Language = 'ko' | 'zh-CN' | 'zh-TW';

export interface Detection {
  id: number;
  isIllegal: boolean;
  type: DetectionType;
  confidence: number;
  reason: string;
  rawText: string;
  translatedText: string | null;
  postUrl: string;
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

export interface StatsResponse {
  todayCount: number;
  deltaFromYesterday: number;
  typeDistribution: TypeDistributionEntry[];
  siteDistribution: SiteDistributionEntry[];
  langDistribution: LangDistributionEntry[];
  trend?: TrendEntry[];
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
  site?: string;
  type?: DetectionType;
  lang?: Language;
  /** Journey 2 — 수동 트리거 후 새로 들어온 탐지만 */
  since?: 'triggered';
  page?: number;
  size?: number;
}

export interface CrawlTriggerResponse {
  status: 'triggered' | 'in_progress';
  estimatedMinutes: number;
}

export type StatsPeriod = 'weekly' | 'monthly';
