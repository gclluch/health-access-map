import { Component, useEffect, useState, type ReactNode } from "react";
import { useStore } from "./store";
import { reportError } from "./lib/observability";
import MapView from "./components/MapView";
import Legend from "./components/Legend";
import SearchBox from "./components/SearchBox";
import RankingsList from "./components/RankingsList";
import DetailPanel from "./components/DetailPanel";
import WeightSliders from "./components/WeightSliders";
import MethodologyPanel from "./components/MethodologyPanel";
import TopControls from "./components/TopControls";
import CompareTray from "./components/CompareTray";
import SiteCredits from "./components/SiteCredits";
import Caret from "./components/Caret";

function Loading() {
  return (
    <div className="absolute inset-0 z-40 grid place-items-center bg-paper">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-hairline border-t-accent rounded-full animate-spin mx-auto" />
        <div className="text-[13px] text-graphite mt-3">
          Loading ~33,000 ZIP areas…
        </div>
      </div>
    </div>
  );
}

function ErrorState({ msg }: { msg: string }) {
  return (
    <div className="absolute inset-0 z-40 grid place-items-center bg-paper">
      <div className="panel rounded-md px-5 py-4 max-w-sm text-center">
        <div className="text-[14px] font-medium text-ink">
          Could not load map data
        </div>
        <div className="text-[12px] text-graphite mt-1">{msg}</div>
        <button
          className="mt-3 text-[12px] text-accent hover:underline"
          onClick={() => location.reload()}
        >
          Retry
        </button>
      </div>
    </div>
  );
}

// Top-level error boundary: a render-time throw anywhere in the tree would otherwise white-screen
// the whole app (ErrorState only covers the data-load promise). Catch it, report it, and show a
// recoverable fallback instead of a blank page.
class ErrorBoundary extends Component<
  { children: ReactNode },
  { crashed: boolean; msg: string }
> {
  state = { crashed: false, msg: "" };

  static getDerivedStateFromError(err: unknown) {
    return {
      crashed: true,
      msg: err instanceof Error ? err.message : String(err),
    };
  }

  componentDidCatch(err: unknown, info: { componentStack?: string | null }) {
    reportError(err instanceof Error ? err.message : String(err), {
      stack: err instanceof Error ? err.stack : undefined,
      componentStack: info.componentStack ?? undefined,
    });
  }

  render() {
    if (this.state.crashed) {
      return (
        <div className="absolute inset-0 z-50 grid place-items-center bg-paper">
          <div className="panel rounded-md px-5 py-4 max-w-sm text-center">
            <div className="text-[14px] font-medium text-ink">
              Something went wrong
            </div>
            <div className="text-[12px] text-graphite mt-1">
              {this.state.msg || "unexpected error"}
            </div>
            <button
              className="mt-3 text-[12px] text-accent hover:underline"
              onClick={() => location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}

function AppInner() {
  const { status, error } = useStore();
  const load = useStore((s) => s.load);
  const selectedZcta = useStore((s) => s.selectedZcta);
  const compareCount = useStore((s) => s.compareZctas.length);
  const showWeights = useStore((s) => s.showWeights);
  const toggleMethodology = useStore((s) => s.toggleMethodology);
  const [isCompactHeight, setCompactHeight] = useState(
    () => window.innerHeight < 520,
  );
  const [railOpen, setRailOpen] = useState(false);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onResize = () => {
      const compact = window.innerHeight < 520;
      setCompactHeight(compact);
      if (compact) setRailOpen(false);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <div className="relative w-full h-full overflow-hidden">
      {/* map (the hero, full-bleed) */}
      <div className="absolute inset-0">
        {status === "ready" && <MapView />}
      </div>

      {status === "loading" && <Loading />}
      {status === "error" && <ErrorState msg={error ?? "unknown error"} />}

      {/* top bar (transparent over map) */}
      <header className="absolute top-0 left-0 right-0 z-30 flex items-start gap-2 px-3 py-2.5 pointer-events-none flex-wrap max-[520px]:px-2 max-[520px]:py-2">
        <div className="pointer-events-auto flex items-center gap-2">
          <span className="font-serif text-[16px] text-ink bg-surface/90 backdrop-blur-sm px-2.5 py-1 rounded border border-hairline max-[520px]:text-[15px]">
            Health Access Map
          </span>
          <FreshnessBadge />
        </div>
        <div className="flex-1 min-w-[8px]" />
        <div className="pointer-events-auto flex items-center gap-1.5 flex-wrap justify-end max-[520px]:gap-1 max-[520px]:max-w-[270px]">
          {status === "ready" && <TopControls />}
          <SearchBox />
          <button
            onClick={() => toggleMethodology(true)}
            className="text-[12px] text-graphite hover:text-accent bg-surface/90 border border-hairline rounded px-2.5 py-1.5 whitespace-nowrap max-[520px]:px-2"
          >
            How to read this
          </button>
        </div>
      </header>

      {/* left rail (desktop) / bottom sheet (mobile): rankings + customize */}
      {status === "ready" && (
        <div className="absolute z-20 left-2 right-2 bottom-2 sm:left-3 sm:right-auto sm:top-14 sm:bottom-auto sm:w-[270px] max-[520px]:bottom-1">
          <div className="panel rounded-md overflow-hidden flex flex-col max-h-[38vh] sm:max-h-[calc(100vh-150px)] max-[520px]:max-h-[34px]">
            <button
              onClick={() => setRailOpen((v) => !v)}
              aria-expanded={railOpen}
              className="px-3 py-2 flex items-center justify-between text-[12px] font-medium text-ink border-b border-hairline max-[520px]:py-1.5"
            >
              Rankings
              <Caret open={railOpen} size={14} className="text-graphite" />
            </button>
            {railOpen && !isCompactHeight && (
              <div className="flex-1 min-h-0 overflow-hidden">
                <RankingsList />
              </div>
            )}
          </div>
        </div>
      )}

      {/* detail panel (on selection): right rail desktop / bottom sheet mobile */}
      {status === "ready" && selectedZcta && (
        <div className="absolute z-30 left-2 right-2 bottom-2 sm:left-auto sm:right-3 sm:top-14 sm:bottom-auto max-[520px]:bottom-1">
          <DetailPanel />
        </div>
      )}

      {/* "What you're seeing" cluster: bottom-center. The legend (color-by metric +
          histogram) and the weighting control are siblings - both govern what the map
          shows - so they live together here. Weights expand UPWARD above the legend.
          Sits below the sheet z-layer on mobile so an open sheet covers it. */}
      {status === "ready" && (
        <div className="absolute z-10 left-1/2 -translate-x-1/2 bottom-[46px] sm:z-20 sm:bottom-4 w-[340px] max-w-[88vw] flex flex-col gap-1.5 max-[520px]:bottom-[40px] max-[520px]:w-[calc(100vw-16px)]">
          {showWeights && (
            <div className="panel rounded-md overflow-hidden max-h-[50vh] overflow-y-auto">
              <WeightSliders />
            </div>
          )}
          <Legend />
        </div>
      )}

      {/* comparison tray (when 1+ ZIPs are pinned): top-center, above the map */}
      {status === "ready" && compareCount > 0 && (
        <div className="absolute z-30 left-2 right-2 top-[52px] sm:left-1/2 sm:-translate-x-1/2 sm:right-auto sm:w-[540px] max-w-[96vw] max-[520px]:top-[126px]">
          <CompareTray />
        </div>
      )}

      {status === "ready" && <SiteCredits />}
      <Toast />
      <MethodologyPanel />
    </div>
  );
}

// "Data as of" freshness badge: makes the build date + source vintages visible at a glance
// (a federal-index omission the audit flagged). Hidden until meta.json loads.
function FreshnessBadge() {
  const meta = useStore((s) => s.meta);
  if (!meta?.generated) return null;
  const v = meta.vintages ?? {};
  const nppes = v.nppes
    ?.replace(/^NPPES_Data_Dissemination_|\.zip$/g, "")
    .replace(/_/g, " ");
  const tip =
    `Built ${meta.generated} from: CDC PLACES (${v.places ?? "?"}), ` +
    `Census ACS 5-yr ${v.acs_year ?? "?"}, TIGER ${v.tiger_year ?? "?"}` +
    (nppes ? `, NPPES ${nppes}` : "") +
    `. ${meta.n_scored?.toLocaleString() ?? "?"} ZIPs scored.`;
  return (
    <span
      title={tip}
      className="hidden sm:inline-block num text-[10px] text-graphite bg-surface/85 border border-hairline rounded px-1.5 py-1 cursor-help"
    >
      data as of {meta.generated}
    </span>
  );
}

function Toast() {
  const toast = useStore((s) => s.toast);
  const setToast = useStore((s) => s.setToast);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast, setToast]);
  if (!toast) return null;
  return (
    <div
      role="status"
      className="absolute z-50 bottom-6 left-1/2 -translate-x-1/2 bg-ink text-paper text-[12px] px-3 py-2 rounded shadow-lg max-w-[90vw]"
    >
      {toast}
    </div>
  );
}
