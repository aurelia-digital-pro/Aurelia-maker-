import { useMemo, useState } from 'react';
import { ArrowRight, ChevronDown, Command, Film, LoaderCircle, Plus, RefreshCw, Send, Sparkles } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Link, useLocation } from 'wouter';
import { Form } from '@/components/ui/form';
import { useCreateProduction, useListProductions } from '@workspace/api-client-react';
import { getListProductionsQueryKey } from '@workspace/api-client-react';
import type { Production, ProductionInput } from '@workspace/api-client-react';
import { ProductionInputProfile } from '@workspace/api-client-react';
import { ProductionCard } from '@/components/production-card';
import { isActiveProduction } from '@/lib/production';

type FormValues = {
  request: string;
  episodeId: string;
  profile: ProductionInputProfile;
};

function WorkspaceSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.24fr)_minmax(330px,.76fr)]">
      <div className="skeleton h-[420px] rounded-3xl" />
      <div className="space-y-4">
        <div className="skeleton h-28 rounded-2xl" />
        <div className="skeleton h-48 rounded-2xl" />
      </div>
    </div>
  );
}

function RequestComposer() {
  const [, setLocation] = useLocation();
  const [showOptions, setShowOptions] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const form = useForm<FormValues>({
    defaultValues: { request: '', episodeId: '', profile: ProductionInputProfile.youtube },
  });
  const createProduction = useCreateProduction();
  const request = form.watch('request');
  const profile = form.watch('profile');

  const submit = (values: FormValues) => {
    setSubmitError('');
    const input: ProductionInput = {
      request: values.request.trim(),
      ...(values.episodeId.trim() ? { episodeId: values.episodeId.trim() } : {}),
      ...(values.profile ? { profile: values.profile } : {}),
    };
    if (!input.request) {
      setSubmitError('Write the request you want the local engine to produce.');
      return;
    }
    createProduction.mutate({ data: input }, {
      onSuccess: (production) => setLocation(`/production/${production.jobId}`),
      onError: (error) => setSubmitError(error instanceof Error ? error.message : 'The production could not be started. Try again.'),
    });
  };

  return (
    <div className="film-grid relative overflow-hidden rounded-[24px] border border-[hsl(var(--primary)/.12)] bg-[hsl(var(--card)/.78)] shadow-[0_24px_60px_hsl(203_27%_15%_/.08)]" data-testid="panel-request-composer">
      <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full border border-[hsl(var(--secondary)/.18)]" />
      <div className="absolute -right-8 -top-12 h-48 w-48 rounded-full border border-[hsl(var(--secondary)/.15)]" />
      <div className="relative flex items-center justify-between border-b border-border/80 px-5 py-4 sm:px-7">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--secondary))]"><Command className="h-3.5 w-3.5" /></span>
          <span className="font-mono-ui text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Director's desk / 01</span>
        </div>
        <span className="font-mono-ui text-[10px] uppercase tracking-[0.16em] text-[hsl(var(--chart-2))]">Local execution</span>
      </div>
      <div className="relative p-5 sm:p-8">
        <div className="max-w-2xl">
          <div className="mb-2 flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-[hsl(var(--accent))]"><span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--accent))]" /> New production</div>
          <h1 className="font-display text-[clamp(2.7rem,7vw,5.9rem)] leading-[.86] tracking-[-0.035em] text-foreground">What should<br /><em className="text-[hsl(var(--accent))]">exist next?</em></h1>
          <p className="mt-5 max-w-md text-sm leading-6 text-muted-foreground sm:text-base">Give AURELIA one clear request. It will turn the brief into a source-traceable video, then show you exactly what happened.</p>
        </div>
        <Form {...form}>
        <form className="mt-9" onSubmit={form.handleSubmit(submit)} data-testid="form-create-production">
          <label htmlFor="production-request" className="sr-only">Production request</label>
          <textarea
            id="production-request"
            rows={5}
            placeholder="Make a 45-second vertical episode about the first radio signal from deep space. Calm, curious, no hype."
            className="w-full resize-none rounded-2xl border border-[hsl(var(--primary)/.18)] bg-[hsl(var(--background)/.72)] px-4 py-4 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-[hsl(var(--secondary))] focus:ring-4 focus:ring-[hsl(var(--secondary)/.14)] sm:px-5 sm:py-5"
            {...form.register('request')}
            data-testid="input-production-request"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <button type="button" onClick={() => setShowOptions((value) => !value)} className="group inline-flex items-center gap-2 rounded-lg px-2 py-2 font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:bg-muted hover:text-foreground" data-testid="button-toggle-production-options">
              <span className="flex h-5 w-5 items-center justify-center rounded border border-border"><ChevronDown className={`h-3 w-3 transition-transform ${showOptions ? 'rotate-180' : ''}`} /></span>
              Tune the brief
            </button>
            <span className="font-mono-ui text-[10px] text-muted-foreground">{request?.length ?? 0} / 1200</span>
          </div>
          {showOptions && (
            <div className="mt-4 grid gap-3 rounded-xl border border-border bg-[hsl(var(--muted)/.55)] p-4 sm:grid-cols-2" data-testid="panel-production-options">
              <div>
                <label htmlFor="episode-id" className="mb-2 block font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Episode ID <span className="normal-case tracking-normal opacity-60">optional</span></label>
                <input id="episode-id" placeholder="e.g. ep-014" className="h-10 w-full rounded-lg border border-input bg-card px-3 text-xs outline-none focus:border-[hsl(var(--secondary))]" {...form.register('episodeId')} data-testid="input-episode-id" />
              </div>
              <div>
                <label htmlFor="profile" className="mb-2 block font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Output profile</label>
                <select id="profile" className="h-10 w-full rounded-lg border border-input bg-card px-3 text-xs outline-none focus:border-[hsl(var(--secondary))]" {...form.register('profile')} data-testid="select-production-profile">
                  <option value={ProductionInputProfile.youtube}>YouTube</option>
                  <option value={ProductionInputProfile.tiktok}>TikTok</option>
                  <option value={ProductionInputProfile.both}>YouTube + TikTok</option>
                </select>
              </div>
            </div>
          )}
          {submitError && <p className="mt-4 rounded-lg border border-[hsl(var(--destructive)/.25)] bg-[hsl(var(--destructive)/.08)] px-3 py-2.5 text-xs text-[hsl(var(--destructive))]" data-testid="error-create-production">{submitError}</p>}
          <div className="mt-5 flex flex-col-reverse items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Sparkles className="h-4 w-4 text-[hsl(var(--secondary))]" />
              <span>Source evidence stays attached.</span>
            </div>
            <button type="submit" disabled={createProduction.isPending} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[hsl(var(--primary))] px-5 py-3 text-xs font-bold uppercase tracking-[0.1em] text-[hsl(var(--primary-foreground))] shadow-[4px_4px_0_hsl(var(--secondary))] hover:bg-[hsl(203_27%_22%)] disabled:cursor-wait disabled:opacity-70" data-testid="button-start-production">
              {createProduction.isPending ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Starting roll</> : <><Send className="h-4 w-4" /> Start production</>}
            </button>
          </div>
        </form>
        </Form>
      </div>
    </div>
  );
}

function SignalPanel({ productions }: { productions: Production[] | undefined }) {
  const activeCount = productions?.filter((production) => isActiveProduction(production.status)).length ?? 0;
  return (
    <div className="rounded-2xl border border-border bg-[hsl(var(--primary))] p-5 text-[hsl(var(--sidebar-foreground))] shadow-[0_18px_35px_hsl(203_27%_15%_/.1)] sm:p-6" data-testid="panel-production-signal">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-[hsl(var(--sidebar-foreground)/.58)]"><RadioDot /> Engine signal</div>
        <span className="font-mono-ui text-[10px] text-[hsl(var(--secondary))]">SESSION / LOCAL</span>
      </div>
      <div className="mt-7 flex items-end justify-between">
        <div>
          <div className="font-display text-5xl leading-none text-[hsl(var(--secondary))]">{activeCount}</div>
          <div className="mt-2 text-xs text-[hsl(var(--sidebar-foreground)/.62)]">active production{activeCount === 1 ? '' : 's'}</div>
        </div>
        <div className="text-right">
          <div className="font-mono-ui text-[10px] uppercase tracking-[0.12em] text-[hsl(var(--sidebar-foreground)/.42)]">handoff</div>
          <div className="mt-1 text-sm text-[hsl(var(--sidebar-foreground)/.82)]">Request → MP4</div>
        </div>
      </div>
      <div className="mt-7 h-px bg-[hsl(var(--sidebar-foreground)/.12)]" />
      <div className="mt-4 flex items-center gap-2 text-xs text-[hsl(var(--sidebar-foreground)/.65)]"><span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--chart-2))]" /> No hidden execution state</div>
    </div>
  );
}

function RadioDot() {
  return <span className="relative flex h-3 w-3 items-center justify-center"><span className="absolute h-3 w-3 animate-ping rounded-full bg-[hsl(var(--chart-2)/.2)]" /><span className="relative h-1.5 w-1.5 rounded-full bg-[hsl(var(--chart-2))]" /></span>;
}

export function Workspace() {
  const productions = useListProductions({
    query: { queryKey: getListProductionsQueryKey(), refetchInterval: 10000 },
  });
  const [filter, setFilter] = useState<'all' | 'active' | 'finished'>('all');
  const list = useMemo(() => {
    const values = productions.data ?? [];
    if (filter === 'active') return values.filter((item) => isActiveProduction(item.status));
    if (filter === 'finished') return values.filter((item) => !isActiveProduction(item.status));
    return values;
  }, [filter, productions.data]);
  const activeCount = (productions.data ?? []).filter((item) => isActiveProduction(item.status)).length;
  const finishedCount = (productions.data ?? []).filter((item) => !isActiveProduction(item.status)).length;

  return (
    <div className="space-y-9">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="rise-in">
          <div className="mb-2 flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.2em] text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--secondary))]" /> Production workspace</div>
          <h2 className="font-display text-3xl leading-none tracking-[-0.03em] text-foreground sm:text-4xl">Make the next cut count.</h2>
        </div>
        <div className="flex items-center gap-3 font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground rise-in rise-in-delay-1">
          <span>{productions.data?.length ?? 0} total rolls</span>
          <span className="h-1 w-1 rounded-full bg-[hsl(var(--secondary))]" />
          <span>{activeCount} live</span>
        </div>
      </div>

      {productions.isLoading && !productions.data ? <WorkspaceSkeleton /> : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.24fr)_minmax(330px,.76fr)]">
          <div className="rise-in rise-in-delay-1"><RequestComposer /></div>
          <div className="space-y-4 rise-in rise-in-delay-2">
            <SignalPanel productions={productions.data} />
            <div className="rounded-2xl border border-border bg-card p-5" data-testid="panel-workflow-note">
              <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.16em] text-muted-foreground"><Film className="h-3.5 w-3.5 text-[hsl(var(--accent))]" /> The AURELIA promise</div>
              <p className="mt-4 font-display text-xl leading-tight text-foreground">If the render is not validated, it is not finished.</p>
              <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground"><span className="font-mono-ui text-[10px] text-[hsl(var(--accent))]">01</span> Every stage leaves a visible trace.</div>
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"><span className="font-mono-ui text-[10px] text-[hsl(var(--accent))]">02</span> Every artifact keeps its source.</div>
            </div>
          </div>
        </div>
      )}

      <section className="rise-in rise-in-delay-3" aria-labelledby="productions-heading">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-muted-foreground">The edit bay</div>
            <h2 id="productions-heading" className="mt-1 text-xl font-semibold tracking-[-0.02em] text-foreground">Recent productions</h2>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1" role="tablist" aria-label="Filter productions">
            {([['all', `All ${productions.data?.length ?? 0}`], ['active', `Active ${activeCount}`], ['finished', `Finished ${finishedCount}`]] as const).map(([value, label]) => (
              <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded-md px-2.5 py-1.5 font-mono-ui text-[9px] uppercase tracking-[0.08em] ${filter === value ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]' : 'text-muted-foreground hover:text-foreground'}`} data-testid={`button-filter-${value}`}>{label}</button>
            ))}
          </div>
        </div>
        {productions.isError && (
          <div className="flex flex-col items-start justify-between gap-4 rounded-2xl border border-[hsl(var(--destructive)/.28)] bg-[hsl(var(--destructive)/.06)] p-5 sm:flex-row sm:items-center" data-testid="error-list-productions">
            <div><p className="text-sm font-semibold text-[hsl(var(--destructive))]">The session archive is unavailable.</p><p className="mt-1 text-xs text-muted-foreground">The local engine did not return the production list.</p></div>
            <button type="button" onClick={() => productions.refetch()} className="inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--destructive)/.3)] px-3 py-2 text-xs font-semibold text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive)/.08)]" data-testid="button-retry-productions"><RefreshCw className="h-3.5 w-3.5" /> Retry</button>
          </div>
        )}
        {!productions.isLoading && !productions.isError && list.length === 0 && (
          <div className="film-grid rounded-2xl border border-dashed border-border bg-card/60 px-6 py-12 text-center" data-testid="empty-productions">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[hsl(var(--muted))] text-[hsl(var(--accent))]"><Plus className="h-5 w-5" /></div>
            <h3 className="mt-4 text-sm font-semibold text-foreground">{filter === 'all' ? 'The bay is quiet.' : `No ${filter} productions.`}</h3>
            <p className="mx-auto mt-2 max-w-sm text-xs leading-5 text-muted-foreground">{filter === 'all' ? 'Start with a request above. The first frame begins with a sentence.' : 'Change the filter to see the rest of this session.'}</p>
            {filter !== 'all' && <button type="button" onClick={() => setFilter('all')} className="mt-4 text-xs font-semibold text-[hsl(var(--accent))] underline underline-offset-4" data-testid="button-clear-production-filter">View all productions</button>}
          </div>
        )}
        {list.length > 0 && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{list.map((production) => <ProductionCard key={production.jobId} production={production} />)}</div>}
      </section>
      <div className="flex items-center justify-between border-t border-border pt-5 text-[10px] text-muted-foreground">
        <span className="font-mono-ui uppercase tracking-[0.15em]">AURELIA Maker / v0.1</span>
        <Link href="/" className="inline-flex items-center gap-1.5 hover:text-foreground" data-testid="link-workspace-footer">Return to desk <ArrowRight className="h-3 w-3" /></Link>
      </div>
    </div>
  );
}
