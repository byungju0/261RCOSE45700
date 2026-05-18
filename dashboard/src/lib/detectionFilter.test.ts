import { describe, expect, it } from 'vitest';
import { detectionFilterToParams, isFilterActive } from './detectionFilter';

describe('detectionFilterToParams', () => {
  it('omits empty values', () => {
    expect(detectionFilterToParams({}).toString()).toBe('');
  });

  it('serializes all filter fields', () => {
    const params = detectionFilterToParams({
      date: '2026-05-12',
      site: 'tailstar',
      type: '핵_배포',
      lang: 'zh-CN',
    });
    expect(params.get('date')).toBe('2026-05-12');
    expect(params.get('site')).toBe('tailstar');
    expect(params.get('type')).toBe('핵_배포');
    expect(params.get('lang')).toBe('zh-CN');
  });

  it('drops page when 0 (default)', () => {
    expect(detectionFilterToParams({ page: 0 }).has('page')).toBe(false);
    expect(detectionFilterToParams({ page: 1 }).get('page')).toBe('1');
  });
});

describe('isFilterActive', () => {
  it('returns false for empty filter', () => {
    expect(isFilterActive({})).toBe(false);
    expect(isFilterActive({ page: 5, size: 20 })).toBe(false);
  });

  it('returns true when any filter field is set', () => {
    expect(isFilterActive({ date: '2026-05-12' })).toBe(true);
    expect(isFilterActive({ site: 'tailstar' })).toBe(true);
    expect(isFilterActive({ type: '핵_배포' })).toBe(true);
    expect(isFilterActive({ lang: 'ko' })).toBe(true);
  });
});
