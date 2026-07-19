import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LockKeyhole, LogOut, RefreshCw, X } from "lucide-react";
import type { Lead, LeadFilters, LeadVertical, SessionInfo } from "./types";
import { fetchLeads, login, logout, checkSession, continueSession, SessionExpiredError } from "./lib/api";
import { mergeCrmState, clearCrmState } from "./lib/storage";
import { DEMO_LEADS } from "./demo-leads";
import { purgeRealSessionState } from "./lib/session-state";
import { EMPTY_FILTERS, filterLeads, leadCreatedAt, leadName, leadPotential, leadPotentialScore, leadPriority, normalizeLeads, parseVertical, verticalLabel } from "./lib/multi-line";
import { Kpis } from "./components/Kpis";
import { Filters } from "./components/Filters";
import { LeadTable } from "./components/LeadTable";
import { LeadDetail } from "./components/LeadDetail";
import { VerticalSelector } from "./components/VerticalSelector";

// Compatibility invariant: purgeRealSessionState(demoByVertical(vertical),clearCrmState)
function verticalFromUrl(): LeadVertical {
  return parseVertical(new URLSearchParams(window.location.search).get("linea")) || "fotomultas";
}

export default function App() {
  const [activeVertical, setActiveVertical] = useState<LeadVertical>(verticalFromUrl);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ generated_at?: string }>({});
  const [isDemo, setIsDemo] = useState(true);
  const [session, setSession] = useState<SessionInfo>({ authenticated: false, mode: "demo" });
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [idleWarning, setIdleWarning] = useState(false);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<LeadFilters>({ ...EMPTY_FILTERS });
  const [sort, setSort] = useState("potential");
  const lastActivityRef = useRef(Date.now());
  const lastServerTouchRef = useRef(0);
  const absoluteExpiresAtRef = useRef(0);
  const sessionRef = useRef(session);
  const verticalRef = useRef(activeVertical);
  const channelRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => { sessionRef.current = session; }, [session]);
  useEffect(() => { verticalRef.current = activeVertical; }, [activeVertical]);

  const restoreDemoImmediately = useCallback((notice?: string) => {
    const safe = purgeRealSessionState(DEMO_LEADS, clearCrmState);
    const normalized = normalizeLeads(safe.leads).filter((lead) => lead.vertical === verticalRef.current);
    setLeads(normalized);
    setMeta(safe.meta);
    setIsDemo(safe.isDemo);
    setSession(safe.session);
    setPassword("");
    setLoginError(null);
    setIdleWarning(false);
    setLoginOpen(false);
    setSelectedLead(null);
    document.body.classList.remove("filters-open");
    if (notice) setSessionNotice(notice);
  }, []);

  const endRealSession = useCallback((notice: string, broadcast = true) => {
    restoreDemoImmediately(notice);
    void logout().catch(() => undefined);
    if (broadcast) channelRef.current?.postMessage({ type: "session-ended", notice });
  }, [restoreDemoImmediately]);

  const load = useCallback(async (authenticated: boolean, vertical: LeadVertical, userActivity = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchLeads(authenticated, vertical, userActivity);
      const nextLeads = authenticated && !result.isDemo ? mergeCrmState(result.leads) : result.leads;
      setLeads(nextLeads);
      setMeta(result.meta);
      setIsDemo(result.isDemo);
      const requestedLead = new URLSearchParams(window.location.search).get("lead");
      setSelectedLead(requestedLead ? nextLeads.find((lead) => lead.id === requestedLead) || null : null);
    } catch (reason) {
      if (reason instanceof SessionExpiredError) endRealSession("Tu sesión terminó. Volvimos al modo demo.");
      else setError(reason instanceof Error ? reason.message : "Error desconocido");
    } finally { setLoading(false); }
  }, [endRealSession]);

  useEffect(() => {
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel("leadx-session");
      channelRef.current = channel;
      channel.onmessage = (event) => { if (event.data?.type === "session-ended") restoreDemoImmediately(event.data.notice || "La sesión terminó en otra pestaña."); };
      return () => { channel.close(); channelRef.current = null; };
    }
    return undefined;
  }, [restoreDemoImmediately]);

  useEffect(() => {
    const initialVertical = verticalRef.current;
    void (async () => {
      const currentSession = await checkSession();
      setSession(currentSession);
      if (currentSession.authenticated) {
        lastActivityRef.current = currentSession.idleExpiresAt ? currentSession.idleExpiresAt - 20 * 60_000 : Date.now();
        lastServerTouchRef.current = Date.now();
        absoluteExpiresAtRef.current = currentSession.absoluteExpiresAt || Date.now() + 8 * 60 * 60_000;
      }
      await load(currentSession.authenticated, initialVertical);
    })();
  }, [load]);

  useEffect(() => {
    const handlePopState = () => {
      const next = verticalFromUrl();
      verticalRef.current = next;
      setActiveVertical(next);
      setSelectedLead(null);
      setFilters({ ...EMPTY_FILTERS });
      void load(sessionRef.current.authenticated, next);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [load]);

  useEffect(() => {
    const markError = () => { document.documentElement.dataset.pageerror = "true"; };
    window.addEventListener("error", markError);
    window.addEventListener("unhandledrejection", markError);
    return () => { window.removeEventListener("error", markError); window.removeEventListener("unhandledrejection", markError); };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      document.documentElement.dataset.leadxReady = loading ? "false" : "true";
      document.documentElement.dataset.linea = activeVertical;
      document.documentElement.dataset.overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth ? "true" : "false";
    }, 80);
    return () => window.clearTimeout(timer);
  }, [activeVertical, leads, loading, selectedLead]);

  const recordUserActivity = useCallback(() => {
    if (!sessionRef.current.authenticated) return;
    const now = Date.now();
    lastActivityRef.current = now;
    setIdleWarning(false);
    if (now - lastServerTouchRef.current < 60_000) return;
    lastServerTouchRef.current = now;
    void continueSession().then((updated) => { if (updated.absoluteExpiresAt) absoluteExpiresAtRef.current = updated.absoluteExpiresAt; })
      .catch((reason) => { if (reason instanceof SessionExpiredError) endRealSession("Tu sesión terminó. Volvimos al modo demo."); });
  }, [endRealSession]);

  useEffect(() => {
    if (!session.authenticated) return undefined;
    const timer = window.setInterval(() => {
      const idleFor = Date.now() - lastActivityRef.current;
      if ((absoluteExpiresAtRef.current && Date.now() >= absoluteExpiresAtRef.current) || idleFor >= 20 * 60_000) {
        endRealSession(idleFor >= 20 * 60_000 ? "Tu sesión terminó por inactividad. Volvimos al modo demo." : "Tu sesión alcanzó el máximo de 8 horas. Volvimos al modo demo.");
      } else if (idleFor >= 18 * 60_000) setIdleWarning(true);
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [session.authenticated, endRealSession]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSelectedLead(null); setLoginOpen(false); document.body.classList.remove("filters-open");
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  const handleVerticalChange = (vertical: LeadVertical) => {
    if (vertical === activeVertical) return;
    const url = new URL(window.location.href);
    url.searchParams.set("linea", vertical);
    url.searchParams.delete("lead");
    window.history.replaceState({}, "", url);
    verticalRef.current = vertical;
    setActiveVertical(vertical);
    setSelectedLead(null);
    setFilters((current) => ({ ...current, municipality: "", violationType: "", plate: "", brand: "", machineType: "", partNumber: "", urgency: "" }));
    void load(sessionRef.current.authenticated, vertical);
  };

  const handleLogin = async () => {
    setLoginLoading(true); setLoginError(null);
    try {
      const result = await login(password);
      if (result.ok) {
        setPassword("");
        const nextSession = { authenticated: true, mode: "real" as const };
        setSession(nextSession);
        lastActivityRef.current = Date.now(); lastServerTouchRef.current = Date.now(); absoluteExpiresAtRef.current = Date.now() + 8 * 60 * 60_000;
        setSessionNotice(null); setLoginOpen(false);
        await load(true, verticalRef.current, true);
      } else setLoginError(result.error || "Contraseña incorrecta");
    } finally { setLoginLoading(false); }
  };

  const handleLogout = () => endRealSession("Cerraste la sesión. Volvimos al modo demo.");
  const handleContinueSession = async () => {
    try {
      const updated = await continueSession();
      lastActivityRef.current = Date.now(); lastServerTouchRef.current = Date.now();
      if (updated.absoluteExpiresAt) absoluteExpiresAtRef.current = updated.absoluteExpiresAt;
      setIdleWarning(false);
    } catch { endRealSession("Tu sesión terminó por inactividad. Volvimos al modo demo."); }
  };

  const filtered = useMemo(() => {
    const result = filterLeads(leads, activeVertical, search, filters);
    return [...result].sort((a, b) => {
      if (sort === "potential") {
        const difference = leadPotentialScore(b) - leadPotentialScore(a);
        if (difference) return difference;
      }
      if (sort === "name") return leadName(a).localeCompare(leadName(b), "es");
      if (sort === "priority") {
        const rank = { Alta: 3, Media: 2, Baja: 1 };
        const difference = rank[leadPriority(b)] - rank[leadPriority(a)];
        if (difference) return difference;
      }
      return (Date.parse(leadCreatedAt(b) || "") || 0) - (Date.parse(leadCreatedAt(a) || "") || 0);
    });
  }, [activeVertical, filters, leads, search, sort]);

  const exportVisible = () => {
    const rows = [["Lead", "Provincia", "Teléfono", "Canal", "Potencial", "Creado"], ...filtered.map((lead) => [lead.name || lead.persona, lead.province || lead.provincia || "", lead.phone || "", lead.channel || "", leadPotential(lead), lead.created_at || lead.fecha_iso || ""])];
    const csv = rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `leadx-${activeVertical}.csv`; anchor.click(); URL.revokeObjectURL(url);
  };

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand"><h1 className="app__title">LeadX</h1><p className="app__subtitle">{meta.generated_at ? `Actualizado ${new Date(meta.generated_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}` : `CRM · ${verticalLabel(activeVertical)}`}</p></div>
        <div className="app__actions">
          <span className={`mode-badge ${isDemo ? "mode-badge--demo" : "mode-badge--real"}`}>{isDemo ? "Modo demo" : "Datos reales"}</span>
          {session.authenticated ? <><button className="btn btn--ghost" onClick={() => load(true, activeVertical, true)} disabled={loading} aria-label="Sincronizar"><RefreshCw size={16} aria-hidden="true" /></button><button className="btn btn--ghost" onClick={handleLogout} aria-label="Salir"><LogOut size={16} aria-hidden="true" /> Salir</button></>
            : <><form className="login-form desktop-login" onSubmit={(event) => { event.preventDefault(); void handleLogin(); }}><input type="password" className="login-form__input" placeholder="Contraseña" value={password} onChange={(event) => setPassword(event.target.value)} aria-label="Contraseña" autoComplete="current-password" /><button type="submit" className="btn btn--primary" disabled={loginLoading || !password}>{loginLoading ? "…" : "Entrar"}</button></form><button className="btn mobile-unlock" onClick={() => setLoginOpen(true)}><LockKeyhole size={17} />Desbloquear datos reales</button></>}
        </div>
      </header>
      {loginError && <div className="error" role="alert">{loginError}</div>}{error && <div className="error" role="alert">{error}</div>}{sessionNotice && <div className="session-notice" role="status">{sessionNotice}</div>}
      <VerticalSelector value={activeVertical} onChange={handleVerticalChange} />
      {isDemo && <p className="demo-caption">Datos ficticios para explorar el CRM · 12 registros por línea</p>}
      {loginOpen && !session.authenticated && <div className="sheet-layer" onMouseDown={(event) => { if (event.target === event.currentTarget) setLoginOpen(false); }}><form className="login-sheet" onSubmit={(event) => { event.preventDefault(); void handleLogin(); }}><div className="sheet-header"><div><span className="eyebrow">Acceso privado</span><h2>Desbloquear datos reales</h2></div><button type="button" className="icon-button" onClick={() => setLoginOpen(false)} aria-label="Cerrar"><X size={20} /></button></div><label className="login-sheet__field"><span>Contraseña</span><input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>{loginError && <p className="field-error" role="alert">{loginError}</p>}<button className="btn btn--primary login-sheet__submit" disabled={!password || loginLoading}>{loginLoading ? "Ingresando…" : "Ingresar"}</button></form></div>}
      {idleWarning && <div className="modal-backdrop" role="presentation"><div className="session-warning" role="alertdialog" aria-modal="true" aria-labelledby="idle-title"><h2 id="idle-title">Tu sesión se cerrará por inactividad.</h2><div className="session-warning__actions"><button className="btn btn--primary" onClick={() => void handleContinueSession()}>Continuar sesión</button><button className="btn" onClick={() => endRealSession("Cerraste la sesión. Volvimos al modo demo.")}>Salir ahora</button></div></div></div>}
      <Kpis leads={leads} />
      <Filters vertical={activeVertical} leads={leads} search={search} setSearch={setSearch} filters={filters} setFilters={setFilters} sort={sort} setSort={setSort} onExport={exportVisible} onActivity={recordUserActivity} />
      {loading && leads.length === 0 ? <div className="loading"><span className="spinner" aria-hidden="true" />Cargando leads…</div> : <LeadTable leads={filtered} selectedId={selectedLead?.id} onSelect={setSelectedLead} onActivity={recordUserActivity} />}
      {selectedLead && <LeadDetail lead={selectedLead} onClose={() => setSelectedLead(null)} onActivity={recordUserActivity} />}
    </div>
  );
}
