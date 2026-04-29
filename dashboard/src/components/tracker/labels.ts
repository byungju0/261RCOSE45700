import type { DetectionType, Language } from '@/types/api';

const TYPE_LABEL: Record<DetectionType, string> = {
  매크로_판매: '매크로 판매',
  핵_배포: '핵 배포',
  계정_거래: '계정 거래',
  리세마라: '리세마라',
  기타: '기타',
};

const LANG_LABEL: Record<Language, string> = {
  ko: '한국어',
  'zh-CN': '중국어 (간체)',
  'zh-TW': '중국어 (번체)',
};

export function getTypeLabel(type: DetectionType): string {
  return TYPE_LABEL[type];
}

export function getLangLabel(lang: Language): string {
  return LANG_LABEL[lang];
}

export const TYPE_OPTIONS: { value: DetectionType; label: string }[] = (
  Object.keys(TYPE_LABEL) as DetectionType[]
).map((value) => ({ value, label: TYPE_LABEL[value] }));

export const LANG_OPTIONS: { value: Language; label: string }[] = (
  Object.keys(LANG_LABEL) as Language[]
).map((value) => ({ value, label: LANG_LABEL[value] }));
