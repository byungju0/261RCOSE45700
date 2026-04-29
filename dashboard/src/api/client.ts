import axios, { type AxiosError } from 'axios';
import type { ProblemDetail } from '../types/api';

export class ProblemDetailError extends Error {
  readonly problem: ProblemDetail;
  readonly errorCode: string;
  readonly status: number;

  constructor(problem: ProblemDetail) {
    super(`${problem.title}: ${problem.detail}`);
    this.name = 'ProblemDetailError';
    this.problem = problem;
    this.errorCode = problem.errorCode;
    this.status = problem.status;
  }
}

function isProblemDetail(value: unknown): value is ProblemDetail {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.type === 'string' &&
    typeof v.title === 'string' &&
    typeof v.status === 'number' &&
    typeof v.detail === 'string' &&
    typeof v.errorCode === 'string'
  );
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 10_000,
});

apiClient.interceptors.request.use((config) => {
  config.headers.set('X-Correlation-ID', crypto.randomUUID());
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const data = error.response?.data;
    if (isProblemDetail(data)) {
      return Promise.reject(new ProblemDetailError(data));
    }
    return Promise.reject(error);
  },
);
