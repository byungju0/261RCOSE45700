import type {
  Detection,
  DetectionType,
  Language,
  StatsResponse,
} from '@/types/api';

/**
 * MSW mock 데이터.
 * 백엔드 (Story 4.1·4.2·4.3) 미완 상태에서 프론트가 독립 진행 가능하게 한다.
 * 백엔드 합류 시 VITE_API_BASE_URL만 변경하면 실 데이터로 전환.
 */

const TYPES: DetectionType[] = ['매크로_판매', '핵_배포', '계정_거래', '리세마라', '기타'];

interface SiteDef {
  name: string;
  lang: Language;
}

const SITES: SiteDef[] = [
  { name: 'tailstar.net', lang: 'ko' },
  { name: 'ptt.cc', lang: 'zh-TW' },
  { name: 'dcard.tw', lang: 'zh-TW' },
  { name: 'tieba.baidu.com', lang: 'zh-CN' },
  { name: '52pojie.cn', lang: 'zh-CN' },
  { name: 'bbs.nga.cn', lang: 'zh-CN' },
];

interface SamplePost {
  type: DetectionType;
  rawZh: string;
  rawKo: string;
  translatedKo: string;
  reason: string;
}

const SAMPLE_POSTS: SamplePost[] = [
  {
    type: '매크로_판매',
    rawZh:
      '游戏脚本可以让你自动刷副本，价格优惠。每天24小时挂机，自动战斗、自动收集材料、自动卖装备。详细信息私聊QQ群123456。',
    rawKo:
      '게임 매크로 판매합니다. 자동사냥, 자동퀘스트, 자동수령. 카톡 문의 daily-grind99. 가격 협의 가능, 24시간 안정적 운영 보장. 환불 가능.',
    translatedKo:
      '게임 스크립트로 자동으로 던전을 돌 수 있습니다. 가격 우대. 매일 24시간 자동 사냥, 자동 전투, 자동 재료 수집, 자동 장비 판매. 자세한 정보는 QQ 그룹 123456로 비밀 채팅.',
    reason:
      '게임 자동화 도구의 가격이 명시되어 있고 구매 안내(QQ/카톡)와 동작 보장 문구가 함께 포함되어 있어 매크로 판매 게시글로 판단됨.',
  },
  {
    type: '핵_배포',
    rawZh:
      '最新游戏辅助工具下载 — 屏蔽反作弊系统，安全无封号。支持windows和android双平台。点击链接 short.url/abc123 下载。',
    rawKo: '최신 게임 핵 배포 — 안티치트 우회 보장. 무료 다운로드 링크 short.url/xyz999.',
    translatedKo:
      '최신 게임 보조 도구 다운로드 — 안티치트 시스템 우회, 정지 없음 안전. Windows와 Android 양 플랫폼 지원. 링크 클릭 short.url/abc123 다운로드.',
    reason:
      '안티치트 우회를 명시하고 다운로드 링크를 게시한 핵 배포 게시글. 플랫폼별 지원과 "정지 없음" 보장은 핵·치트 도구의 전형적 마케팅 문구.',
  },
  {
    type: '계정_거래',
    rawZh: '遊戲帳號買賣 — 99級滿等帳號出售，附贈裝備全套。聯絡LINE: account_seller123。',
    rawKo: '계정 매매 - 99레벨 만렙, 풀세트 장비. 카톡 account-trade88로 문의.',
    translatedKo:
      '게임 계정 매매 — 99레벨 만렙 계정 판매, 장비 풀세트 증정. LINE 연락: account_seller123.',
    reason:
      '레벨/장비를 명시한 계정 매매 게시글. 외부 연락처를 통한 거래 유도가 약관 위반(계정 거래 금지)에 해당.',
  },
  {
    type: '리세마라',
    rawZh: 'リセマラ代行 — 빠른 작업, 만족 보장. 신규 가챠 SSR 보장 안 되면 환불.',
    rawKo: '리세마라 대행 빠른 작업 만족 보장. 카톡 reroll-pro 문의. SSR 미획득 시 100% 환불.',
    translatedKo: '리세마라 대행 — 빠른 작업, 만족 보장. 신규 가챠 SSR 미보장 시 환불.',
    reason:
      '리세마라(reroll) 대행을 유료로 제공하고 외부 연락처(카톡)로 거래 유도. 일부 게임의 약관에서 외주 대행을 명시적 금지.',
  },
  {
    type: '기타',
    rawZh: '游戏代练服务，专业陪练。任何级别任何副本，价格透明。',
    rawKo: '게임 대리 운영 서비스, 전문 페어. 어떤 레벨 어떤 던전이든 가격 투명.',
    translatedKo: '게임 대리 플레이 서비스, 전문 페어 도움. 어떤 레벨 어떤 던전이든 가격 투명.',
    reason: '게임 대리 운영(부스팅) 서비스 광고. 약관상 명확히 분류되지 않는 회색 영역으로 "기타" 유형.',
  },
];

function pseudoRandom(seed: number): number {
  // 결정론적 mock 데이터를 위한 의사 난수 (LCG)
  return (seed * 9301 + 49297) % 233280 / 233280;
}

/** 12건 mock detections 생성 (오늘 탐지 분포) */
function generateMockDetections(count: number): Detection[] {
  const now = Date.now();
  const detections: Detection[] = [];

  for (let i = 0; i < count; i++) {
    const seed = i + 1;
    const sample = SAMPLE_POSTS[i % SAMPLE_POSTS.length];
    const site = SITES[Math.floor(pseudoRandom(seed * 7) * SITES.length)];
    const minutesAgo = Math.floor(pseudoRandom(seed * 13) * 60 * 8); // 0~8시간 전
    const detectedAt = new Date(now - minutesAgo * 60 * 1000).toISOString();

    // 신뢰도: 임계값 0.70 이상만 (FR22)
    const confidence = 0.70 + pseudoRandom(seed * 17) * 0.30;

    const isKorean = site.lang === 'ko';
    const rawText = isKorean ? sample.rawKo : sample.rawZh;
    const translatedText = isKorean ? null : sample.translatedKo;

    detections.push({
      id: 1000 + i,
      isIllegal: true,
      type: sample.type,
      confidence: Math.round(confidence * 100) / 100,
      reason: sample.reason,
      rawText,
      translatedText,
      postUrl: `https://${site.name}/post/${i + 100000}`,
      siteName: site.name,
      language: site.lang,
      detectedAt,
    });
  }

  // 신뢰도 내림차순 정렬 (Story 4.5 AC: 정렬)
  detections.sort((a, b) => b.confidence - a.confidence);

  return detections;
}

export const MOCK_DETECTIONS = generateMockDetections(12);

export function getDetectionById(id: number): Detection | undefined {
  return MOCK_DETECTIONS.find((d) => d.id === id);
}

/** 7일 추이 (오늘 포함) */
function generateTrend(days: number): { date: string; count: number }[] {
  const trend: { date: string; count: number }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10); // YYYY-MM-DD
    const seed = i * 31 + 7;
    const baseCount = i === 0 ? 12 : 5 + Math.floor(pseudoRandom(seed) * 12);
    trend.push({ date: dateStr, count: baseCount });
  }

  return trend;
}

const trend7 = generateTrend(7);
const trend30 = generateTrend(30);

const todayCount = MOCK_DETECTIONS.length;
const yesterdayCount = trend7.length >= 2 ? trend7[trend7.length - 2].count : 9;

function buildStatsBase(): Omit<StatsResponse, 'trend'> {
  // typeDistribution
  const typeCount = new Map<DetectionType, number>();
  TYPES.forEach((t) => typeCount.set(t, 0));
  MOCK_DETECTIONS.forEach((d) => {
    typeCount.set(d.type, (typeCount.get(d.type) ?? 0) + 1);
  });

  // siteDistribution
  const siteCount = new Map<string, number>();
  MOCK_DETECTIONS.forEach((d) => {
    siteCount.set(d.siteName, (siteCount.get(d.siteName) ?? 0) + 1);
  });

  // langDistribution
  const langCount = new Map<Language, number>();
  MOCK_DETECTIONS.forEach((d) => {
    langCount.set(d.language, (langCount.get(d.language) ?? 0) + 1);
  });

  return {
    todayCount,
    deltaFromYesterday: todayCount - yesterdayCount,
    typeDistribution: TYPES.filter((t) => (typeCount.get(t) ?? 0) > 0).map(
      (t) => ({ type: t, count: typeCount.get(t)! }),
    ),
    siteDistribution: Array.from(siteCount.entries())
      .map(([site, count]) => ({ site, count }))
      .sort((a, b) => b.count - a.count),
    langDistribution: Array.from(langCount.entries()).map(([lang, count]) => ({
      lang,
      count,
    })),
  };
}

const STATS_BASE = buildStatsBase();

export function buildStatsResponse(period?: 'weekly' | 'monthly'): StatsResponse {
  if (!period) return STATS_BASE;
  return {
    ...STATS_BASE,
    trend: period === 'monthly' ? trend30 : trend7,
  };
}
