import { ArrowUpRight, Check, CircleAlert, LoaderCircle, Timer } from 'lucide-react';
import { Link } from 'wouter';
import type { Production } from '@workspace/api-client-react';
import { clampProgress, formatDate, isActiveProduction, profileLabel, statusLabel, statusTone } from '@/lib/production';

type ProductionCardProps = {
  production: Production;
};

export function ProductionCard({ production }: ProductionCardProps) {
  const progress = clampProgress(production.progress);
  const tone = statusTone(production.status);
  const active = isActiveProduction(production.status);
  return (
    <Link
      href={`/production/${production.jobId}`}
      className="group relative block overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-[0_14px_35px_hsl(203_27%_15%_/.06)] hover:-translate-y-0.5 hover:border-[hsl(var(--secondary)/.7)]"
      data-testid={`card-production-${production.jobId}`}
    >
      <div className="absolute right-0 top-0 h-24 w-24 translate-x-8 -translate-y-8 rounded-full bg-[hsl(var(--secondary)/.1)] blur-xl transition-transform duration-500 group-hover:scale-150" />
      <div className="relative flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl status-icon-${tone}`}>
            {tone === 'validated' || tone === 'complete' ? <Check className="h-4 w-4" /> : tone === 'danger' ? <CircleAlert className="h-4 w-4" /> : active ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Timer className="h-4 w-4" />}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-foreground" data-testid={`text-production-title-${production.jobId}`}>{production.title || 'Untitled production'}</h3>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{production.request}</p>
          </div>
        </div>
        <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground" />
      </div>
      <div className="relative mt-5 flex items-end justify-between gap-4">
        <div>
          <div className={`status-label-${tone} font-mono-ui text-[10px] uppercase tracking-[0.12em]`} data-testid={`status-production-${production.jobId}`}>{statusLabel(production.status)}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">{profileLabel(production.profile)} · {formatDate(production.createdAt)}</div>
        </div>
        {active && <span className="font-mono-ui text-xs text-foreground">{progress}%</span>}
      </div>
      {active && (
        <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div className="meter-stripe h-full rounded-full bg-[hsl(var(--secondary))] transition-[width] duration-700" style={{ width: `${Math.max(progress, 3)}%` }} />
        </div>
      )}
    </Link>
  );
}
