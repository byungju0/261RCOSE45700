import { LANG_OPTIONS, TYPE_OPTIONS } from '@/components/tracker/labels';
import { KNOWN_SOURCES } from './sources';

export interface FilterSelectOption {
  value: string;
  label: string;
  className?: string;
}

export function detectionFilterOptions() {
  return {
    rangeOptions: [
      { value: '7d', label: '최근 7일' },
      { value: '30d', label: '최근 30일' },
    ],
    siteOptions: KNOWN_SOURCES.map((source) => ({
      value: source,
      label: source,
      className: 'font-mono text-xs',
    })),
    typeOptions: TYPE_OPTIONS.map((type) => ({
      value: type.value,
      label: type.label,
    })),
    langOptions: LANG_OPTIONS.map((lang) => ({
      value: lang.value,
      label: lang.label,
    })),
  } satisfies Record<string, FilterSelectOption[]>;
}
