/**
 * 알려진 소스 사이트. 백엔드가 `/sources` 엔드포인트 노출 전까지 단일점.
 * MSW mock data, RightRail health 표시, FilterBar 옵션이 모두 이 목록 참조.
 */
export const KNOWN_SOURCES = [
  'tailstar.net',
  'ptt.cc',
  'dcard.tw',
  'tieba.baidu.com',
  '52pojie.cn',
  'bbs.nga.cn',
] as const;

export type KnownSource = (typeof KNOWN_SOURCES)[number];
