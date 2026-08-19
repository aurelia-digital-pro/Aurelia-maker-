import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Check, CircleAlert, Clock3, Copy, Download, FileCheck2, Film, History, LoaderCircle, RefreshCw, ShieldCheck, Terminal, UploadCloud } from 'lucide-react';
import { Link, useParams } from 'wouter';
import { useGetProduction, useGetProductionVideo } from '@workspace/api-client-react';
import { getGetProductionQueryKey, getGetProductionVideoQueryKey } from '@workspace/api-client-react';
import { clampProgress, formatDate, isActiveProduction, profileLabel, statusLabel, statusTone } from '@/lib/production';

function DetailSkeleton() {
  return (
    <div className="space-y-6" data-testid="loading-production-detail">
      <div className="skeleton h-10 w-2/3 rounded-lg" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(300px,.75fr)]">
        <div className="space-y-5"><div className="skeleton h-36 rounded-2xl" /><div className="skeleton h-72 rounded-2xl" /><div className="skeleton h-52 rounded-2xl" /></div>
        <div className="space-y-5"><div className="skeleton h-52 rounded-2xl" /><div className="skeleton h-60 rounded-2xl" /></div>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status?: string }) {
  const tone = statusTone(status as never);
  return <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono-ui text-[10px] uppercase tracking-[0.12em] status-pill-${tone}`} data-testid="status-production-detail"><span className={`h-1.5 w-1.5 rounded-full status-dot-${tone}`} />{statusLabel(status as never)}</span>;
}

function StageRail({ production }: { production: { status: string; stage: string; progress: number; logs: string[] } }) {
  const current = production.stage || 'Preparing production';
  const stages = ['Request received', 'Source assembled', 'Scenes rendered', 'Validation pass', 'Final MP4'];
  const progress = clampProgress(production.progress);
  const activeIndex = Math.min(stages.length - 1, Math.max(0, Math.floor((progress / 100) * stages.length)));
  return (
    <div className="rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="panel-production-stages">
      <div className="flex items-start justify-between gap-5">
        <div><div className="font-mono-ui text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Execution timeline</div><h2 className="mt-1 text-lg font-semibold tracking-[-0.02em]">From request to validation</h2></div>
        <div className="font-mono-ui text-sm text-[hsl(var(--accent))]" data-testid="text-production-progress">{progress}%</div>
      </div>
      <div className="mt-6 h-2 overflow-hidden rounded-full bg-muted">
        <div className="meter-stripe h-full rounded-full bg-[hsl(var(--secondary))] transition-[width] duration-700" style={{ width: `${Math.max(progress, production.status === 'QUEUED' ? 2 : 0)}%` }} />
      </div>
      <div className="mt-7 space-y-0">
        {stages.map((label, index) => {
          const complete = progress >= ((index + 1) / stages.length) * 100 || production.status === 'VALIDATED' || (production.status === 'COMPLETED' && index < 4);
          const currentStage = !complete && index === activeIndex;
          return (
            <div className="relative flex gap-4" key={label}>
              {index !== stages.length - 1 && <div className={`absolute left-[9px] top-6 h-[calc(100%-2px)] w-px ${complete ? 'bg-[hsl(var(--secondary)/.8)]' : 'bg-border'}`} />}
              <div className={`relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${complete ? 'border-[hsl(var(--secondary))] bg-[hsl(var(--secondary))] text-[hsl(var(--primary))]' : currentStage ? 'border-[hsl(var(--accent))] bg-[hsl(var(--accent)/.12)] text-[hsl(var(--accent))]' : 'border-border bg-card text-muted-foreground'}`}>
                {complete ? <Check className="h-3 w-3" /> : currentStage ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" /> : <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" />}
              </div>
              <div className={`pb-5 text-sm ${complete || currentStage ? 'text-foreground' : 'text-muted-foreground'}`}>
                <div className="font-medium">{label}</div>
                {currentStage && <div className="mt-1 text-xs text-[hsl(var(--accent))]" data-testid="text-current-stage">{current}</div>}
                {complete && index === stages.length - 1 && <div className="mt-1 text-xs text-[hsl(var(--chart-2))]">Artifact is ready for handoff</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VideoPanel({ jobId, finalMp4, downloadUrl, status, videoSource, videoError }: { jobId: string; finalMp4?: string | null; downloadUrl?: string | null; status: string; videoSource?: string; videoError: boolean }) {
  const ready = status === 'VALIDATED' || status === 'COMPLETED';
  return (
    <div className="overflow-hidden rounded-2xl border border-[hsl(var(--primary)/.14)] bg-[hsl(var(--primary))] shadow-[0_20px_50px_hsl(203_27%_15%_/.13)]" data-testid="panel-final-video">
      <div className="flex items-center justify-between border-b border-[hsl(var(--sidebar-border))] px-5 py-4">
        <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-[hsl(var(--sidebar-foreground)/.66)]"><Film className="h-3.5 w-3.5 text-[hsl(var(--secondary))]" /> Final picture</div>
        {ready && <span className="flex items-center gap-1.5 font-mono-ui text-[9px] uppercase tracking-[0.12em] text-[hsl(var(--chart-2))]"><ShieldCheck className="h-3.5 w-3.5" /> Validated artifact</span>}
      </div>
      <div className={`relative flex aspect-video items-center justify-center ${videoSource ? 'bg-black' : 'bg-[hsl(203_28%_10%)]'}`}>
        {videoSource ? <video src={videoSource} controls playsInline className="h-full w-full" data-testid={`video-production-${jobId}`} /> : (
          <div className="px-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-[hsl(var(--sidebar-border))] text-[hsl(var(--secondary))]"><LoaderCircle className={`h-5 w-5 ${isActiveProduction(status as never) ? 'animate-spin' : ''}`} /></div>
            <p className="mt-4 text-sm text-[hsl(var(--sidebar-foreground)/.76)]">{videoError ? 'The video preview could not be loaded.' : ready ? 'Fetching the validated preview.' : 'The final picture will appear here.'}</p>
            <p className="mt-1 text-xs text-[hsl(var(--sidebar-foreground)/.42)]">{videoError ? 'The artifact may still be available from its download link.' : 'AURELIA keeps this surface honest while the engine works.'}</p>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-3 border-t border-[hsl(var(--sidebar-border))] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="font-mono-ui text-[10px] uppercase tracking-[0.12em] text-[hsl(var(--sidebar-foreground)/.44)]">{finalMp4 ? 'MP4 / source-linked' : 'MP4 / pending'}</div>
        {downloadUrl ? <a href={downloadUrl} download target="_blank" rel="noreferrer" className="inline-flex items-center justify-center gap-2 rounded-lg bg-[hsl(var(--secondary))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))] hover:bg-[hsl(39_61%_62%)]" data-testid={`button-download-production-${jobId}`}><Download className="h-3.5 w-3.5" /> Download MP4</a> : <button type="button" disabled className="inline-flex items-center justify-center gap-2 rounded-lg border border-[hsl(var(--sidebar-border))] px-3 py-2 text-xs font-semibold text-[hsl(var(--sidebar-foreground)/.36)]" data-testid={`button-download-production-disabled-${jobId}`}><Download className="h-3.5 w-3.5" /> Download pending</button>}
      </div>
    </div>
  );
}

function EvidenceRail({ production }: { production: { source: string; episodeId: string; language?: string; profile?: string; createdAt: string; metadata?: Record<string, unknown> } }) {
  const evidence = [
    ['Source', production.source || 'Source not reported'],
    ['Episode', production.episodeId || 'Not assigned'],
    ['Language', production.language || 'Not reported'],
    ['Profile', profileLabel(production.profile)],
  ];
  return (
    <aside className="space-y-4" aria-label="Production evidence">
      <div className="rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="panel-source-provenance">
        <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-muted-foreground"><FileCheck2 className="h-3.5 w-3.5 text-[hsl(var(--chart-2))]" /> Source provenance</div>
        <p className="mt-4 text-sm leading-6 text-foreground">This production carries its origin forward. No source, no silent completion.</p>
        <div className="mt-5 divide-y divide-border border-y border-border">
          {evidence.map(([label, value]) => <div className="flex items-center justify-between gap-4 py-3" key={label}><span className="font-mono-ui text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{label}</span><span className="max-w-[62%] truncate text-right text-xs font-medium text-foreground" data-testid={`text-evidence-${label.toLowerCase()}`}>{value}</span></div>)}
        </div>
        <div className="mt-4 flex items-start gap-2.5 rounded-lg bg-[hsl(var(--chart-2)/.09)] p-3 text-xs leading-5 text-[hsl(var(--chart-2))]"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /> Evidence is attached to this job, not inferred from the interface.</div>
      </div>
      <div className="rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="panel-production-metadata">
        <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-muted-foreground"><Clock3 className="h-3.5 w-3.5 text-[hsl(var(--accent))]" /> Session record</div>
        <div className="mt-4 flex items-center justify-between text-xs"><span className="text-muted-foreground">Created</span><span className="text-right font-medium text-foreground" data-testid="text-production-created">{formatDate(production.createdAt)}</span></div>
        {production.metadata && Object.entries(production.metadata).slice(0, 5).map(([key, value]) => <div className="mt-3 flex items-center justify-between gap-4 text-xs" key={key}><span className="truncate text-muted-foreground">{key}</span><span className="truncate font-mono-ui text-[10px] text-foreground">{String(value)}</span></div>)}
        <div className="mt-5 flex items-center gap-2 border-t border-border pt-4 font-mono-ui text-[9px] uppercase tracking-[0.12em] text-muted-foreground"><UploadCloud className="h-3.5 w-3.5" /> Local session ledger</div>
      </div>
    </aside>
  );
}

export function ProductionDetail() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId ?? '';
  const productionQuery = useGetProduction(jobId, {
    query: {
      queryKey: getGetProductionQueryKey(jobId),
      enabled: Boolean(jobId),
      refetchInterval: (productionQuery) => {
        const status = (productionQuery.state.data as { status?: string } | undefined)?.status;
        return isActiveProduction(status as never) ? 3000 : false;
      },
    },
  });
  const production = productionQuery.data;
  const videoReady = Boolean(production && (production.status === 'VALIDATED' || production.status === 'COMPLETED'));
  const videoQuery = useGetProductionVideo(jobId, {
    query: {
      queryKey: getGetProductionVideoQueryKey(jobId),
      enabled: Boolean(jobId && videoReady),
      staleTime: Infinity,
    },
  });
  const [videoObjectUrl, setVideoObjectUrl] = useState<string>();

  useEffect(() => {
    if (!videoQuery.data) return;
    const objectUrl = URL.createObjectURL(videoQuery.data);
    setVideoObjectUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [videoQuery.data]);

  const source = useMemo(() => production?.finalMp4 || videoObjectUrl || undefined, [production?.finalMp4, videoObjectUrl]);

  if (productionQuery.isLoading) return <DetailSkeleton />;
  if (productionQuery.isError || !production) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center" data-testid="error-production-detail">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[hsl(var(--destructive)/.1)] text-[hsl(var(--destructive))]"><CircleAlert className="h-6 w-6" /></div>
        <h1 className="mt-5 font-display text-3xl">This production is out of frame.</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">AURELIA could not retrieve the evidence for <span className="font-mono-ui text-xs">{jobId || 'this job'}</span>.</p>
        <div className="mt-6 flex items-center justify-center gap-3"><button type="button" onClick={() => productionQuery.refetch()} className="inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-2.5 text-xs font-bold text-[hsl(var(--primary-foreground))]" data-testid="button-retry-production-detail"><RefreshCw className="h-3.5 w-3.5" /> Retry</button><Link href="/" className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-xs font-semibold text-foreground" data-testid="link-back-workspace-error">Back to workspace</Link></div>
      </div>
    );
  }

  const tone = statusTone(production.status);
  return (
    <div className="space-y-7">
      <div className="flex items-center justify-between gap-4">
        <Link href="/" className="inline-flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground" data-testid="link-back-workspace"><ArrowLeft className="h-3.5 w-3.5" /> Back to workspace</Link>
        <div className="hidden items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:flex"><span className="h-1 w-1 rounded-full bg-[hsl(var(--secondary))]" /> Job <span className="text-foreground">{production.jobId}</span><Copy className="h-3 w-3" /></div>
      </div>
      <header className="relative overflow-hidden rounded-2xl border border-border bg-card px-5 py-6 sm:px-8 sm:py-8" data-testid="header-production-detail">
        <div className={`absolute right-0 top-0 h-full w-1/3 bg-gradient-to-l ${tone === 'danger' ? 'from-[hsl(var(--destructive)/.12)]' : 'from-[hsl(var(--secondary)/.12)]'} to-transparent`} />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-3"><StatusPill status={production.status} /><span className="font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{production.stage || 'Production state recorded'}</span></div>
          <h1 className="mt-4 max-w-3xl font-display text-[clamp(2.5rem,6vw,5rem)] leading-[.88] tracking-[-0.035em] text-foreground" data-testid="text-detail-title">{production.title || 'Untitled production'}</h1>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-muted-foreground">{production.request}</p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(300px,.75fr)]">
        <div className="space-y-5">
          <StageRail production={production} />
          <VideoPanel jobId={production.jobId} finalMp4={production.finalMp4} downloadUrl={production.downloadUrl} status={production.status} videoSource={source} videoError={videoQuery.isError} />
          {production.error && <div className="flex items-start gap-3 rounded-2xl border border-[hsl(var(--destructive)/.3)] bg-[hsl(var(--destructive)/.07)] p-5" data-testid="error-production-status"><CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[hsl(var(--destructive))]" /><div><div className="text-sm font-semibold text-[hsl(var(--destructive))]">Execution stopped before validation.</div><p className="mt-1 text-xs leading-5 text-muted-foreground">{production.error}</p></div></div>}
          <div className="rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="panel-production-logs">
            <div className="flex items-center justify-between"><div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-muted-foreground"><Terminal className="h-3.5 w-3.5 text-[hsl(var(--accent))]" /> Execution log</div><History className="h-4 w-4 text-muted-foreground" /></div>
            {production.logs.length > 0 ? <div className="mt-5 space-y-2">{production.logs.map((log, index) => <div className="flex gap-3 rounded-lg bg-[hsl(var(--muted)/.55)] px-3 py-2.5 font-mono-ui text-[10px] leading-5 text-muted-foreground" key={`${log}-${index}`} data-testid={`log-production-${index}`}><span className="shrink-0 text-[hsl(var(--accent))]">{String(index + 1).padStart(2, '0')}</span><span>{log}</span></div>)}</div> : <div className="mt-5 rounded-lg border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground" data-testid="empty-production-logs">No log entries have been reported yet.</div>}
          </div>
        </div>
        <EvidenceRail production={production} />
      </div>
    </div>
  );
}
