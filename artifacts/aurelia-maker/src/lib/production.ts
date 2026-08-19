import type { Production } from '@workspace/api-client-react';

export type ProductionStatus = Production['status'];

export const ACTIVE_STATUSES: ProductionStatus[] = ['QUEUED', 'RUNNING'];

export const isActiveProduction = (status?: ProductionStatus) =>
  Boolean(status && ACTIVE_STATUSES.includes(status));

export const statusLabel = (status?: ProductionStatus) => {
  switch (status) {
    case 'QUEUED':
      return 'Queued';
    case 'RUNNING':
      return 'In production';
    case 'COMPLETED':
      return 'Rendered';
    case 'VALIDATED':
      return 'Validated';
    case 'FAILED':
      return 'Failed';
    case 'BLOCKED':
      return 'Blocked';
    default:
      return 'Awaiting signal';
  }
};

export const statusTone = (status?: ProductionStatus) => {
  switch (status) {
    case 'VALIDATED':
      return 'validated';
    case 'COMPLETED':
      return 'complete';
    case 'FAILED':
    case 'BLOCKED':
      return 'danger';
    case 'RUNNING':
      return 'running';
    default:
      return 'queued';
  }
};

export const formatDate = (value?: string) => {
  if (!value) return 'Date not recorded';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed);
};

export const clampProgress = (progress?: number) =>
  Math.min(100, Math.max(0, Math.round(progress ?? 0)));

export const profileLabel = (profile?: string) => {
  if (profile === 'youtube') return 'YouTube';
  if (profile === 'tiktok') return 'TikTok';
  if (profile === 'both') return 'YouTube + TikTok';
  return 'Default profile';
};
