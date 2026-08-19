import { Activity, Film, Home, Library, Settings2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'wouter';
import { useHealthCheck, useListProductions } from '@workspace/api-client-react';
import { getHealthCheckQueryKey, getListProductionsQueryKey } from '@workspace/api-client-react';
import { formatDate, isActiveProduction, statusLabel, statusTone } from '@/lib/production';

type AppShellProps = {
  children: ReactNode;
};

function AurelianMark() {
  return (
    <div className="flex items-center gap-3" data-testid="brand-aurelia">
      <div className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-[11px] bg-[hsl(var(--secondary))] text-[hsl(var(--primary))] shadow-[4px_4px_0_hsl(var(--primary))]">
        <span className="font-mono-ui text-[11px] font-bold tracking-[-0.08em]">AM</span>
        <span className="absolute -bottom-3 -right-2 h-6 w-6 rounded-full border-2 border-[hsl(var(--primary))]" />
      </div>
      <div>
        <div className="font-mono-ui text-[11px] font-bold tracking-[0.18em] text-[hsl(var(--sidebar-foreground))]">AURELIA</div>
        <div className="font-mono-ui text-[9px] tracking-[0.18em] text-[hsl(var(--sidebar-foreground)/.5)]">MAKER / LOCAL-FIRST</div>
      </div>
    </div>
  );
}

function HealthSignal() {
  const health = useHealthCheck({
    query: { queryKey: getHealthCheckQueryKey(), refetchInterval: 30000 },
  });
  const online = health.data?.status === 'ok' || health.data?.status === 'healthy';
  return (
    <div className="flex items-center gap-2 border-t border-[hsl(var(--sidebar-border))] px-5 py-4" data-testid="status-system-health">
      <span className={`h-2 w-2 rounded-full ${online ? 'bg-[hsl(163_38%_57%)]' : health.isLoading ? 'bg-[hsl(var(--secondary))] animate-pulse' : 'bg-[hsl(var(--destructive))]'}`} />
      <span className="font-mono-ui text-[10px] uppercase tracking-[0.14em] text-[hsl(var(--sidebar-foreground)/.62)]">
        {health.isLoading ? 'Checking local engine' : online ? 'Local engine online' : 'Engine needs attention'}
      </span>
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const [location] = useLocation();
  const productions = useListProductions({
    query: { queryKey: getListProductionsQueryKey(), staleTime: 10000 },
  });
  const recent = (productions.data ?? []).slice(0, 4);

  return (
    <div className="aurelia-noise min-h-[100dvh] bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[242px] flex-col bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] md:flex">
        <div className="px-5 pb-7 pt-7">
          <AurelianMark />
        </div>
        <nav className="px-3" aria-label="Primary">
          <div className="mb-3 px-3 font-mono-ui text-[9px] uppercase tracking-[0.2em] text-[hsl(var(--sidebar-foreground)/.36)]">Workspace</div>
          <Link href="/" className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${location === '/' ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-foreground))]' : 'text-[hsl(var(--sidebar-foreground)/.58)] hover:bg-[hsl(var(--sidebar-accent)/.68)] hover:text-[hsl(var(--sidebar-foreground))]'}`} data-testid="link-workspace">
            <Home className="h-4 w-4" strokeWidth={1.7} />
            <span>Current request</span>
            {location === '/' && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[hsl(var(--secondary))]" />}
          </Link>
          <div className="mt-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-[hsl(var(--sidebar-foreground)/.32)]" data-testid="nav-library-disabled">
            <Library className="h-4 w-4" strokeWidth={1.7} />
            <span>Archive</span>
            <span className="ml-auto font-mono-ui text-[9px] uppercase">soon</span>
          </div>
          <div className="mt-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-[hsl(var(--sidebar-foreground)/.32)]" data-testid="nav-settings-disabled">
            <Settings2 className="h-4 w-4" strokeWidth={1.7} />
            <span>Settings</span>
          </div>
        </nav>

        <div className="mt-9 flex-1 overflow-y-auto px-3">
          <div className="mb-3 flex items-center justify-between px-3">
            <span className="font-mono-ui text-[9px] uppercase tracking-[0.2em] text-[hsl(var(--sidebar-foreground)/.36)]">Recent rolls</span>
            <Film className="h-3.5 w-3.5 text-[hsl(var(--sidebar-foreground)/.32)]" />
          </div>
          <div className="space-y-1">
            {productions.isLoading && [1, 2, 3].map((item) => <div className="skeleton mx-3 h-10 rounded-lg bg-[hsl(var(--sidebar-accent))]" key={item} />)}
            {!productions.isLoading && recent.length === 0 && (
              <p className="px-3 text-xs leading-5 text-[hsl(var(--sidebar-foreground)/.42)]" data-testid="empty-recent-productions">No productions yet. Your first roll starts here.</p>
            )}
            {recent.map((production) => (
              <Link
                key={production.jobId}
                href={`/production/${production.jobId}`}
                className="group block rounded-lg px-3 py-2.5 hover:bg-[hsl(var(--sidebar-accent)/.7)]"
                data-testid={`link-recent-production-${production.jobId}`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full status-dot-${statusTone(production.status)}`} />
                  <span className="truncate text-xs text-[hsl(var(--sidebar-foreground)/.7)] group-hover:text-[hsl(var(--sidebar-foreground))]">{production.title || production.request}</span>
                </div>
                <div className="mt-1 pl-4 font-mono-ui text-[9px] text-[hsl(var(--sidebar-foreground)/.35)]">{isActiveProduction(production.status) ? statusLabel(production.status) : formatDate(production.createdAt)}</div>
              </Link>
            ))}
          </div>
        </div>
        <HealthSignal />
      </aside>

      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-[hsl(var(--background)/.88)] px-4 py-4 backdrop-blur-md md:hidden">
        <AurelianMark />
        <div className="flex items-center gap-2 font-mono-ui text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          <Activity className="h-3.5 w-3.5 text-[hsl(var(--secondary))]" /> Live desk
        </div>
      </header>

      <main className="min-h-[100dvh] md:pl-[242px]">
        <div className="mx-auto w-full max-w-[1500px] px-4 py-5 sm:px-7 sm:py-8 lg:px-10">{children}</div>
      </main>
    </div>
  );
}
