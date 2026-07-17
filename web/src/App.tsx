import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LockKeyhole, LogOut, RefreshCw, X } from "lucide-react";
import type { Lead, ContactFilter, HeatFilter, LeadStatus, SessionInfo } from "./types";
import { fetchLeads, login, logout, checkSession, continueSession, SessionExpiredError } from "./lib/api";
import { mergeCrmState, clearCrmState } from "./lib/storage";
import { DEMO_LEADS } from "./demo-leads";
import { purgeRealSessionState } from "./lib/session-state";
import { heatLabel } from "./lib/heatmap";
import { Kpis } from "./components/Kpis";
import { Filters } from "./components/Filters";
import { LeadTable } from "./components/LeadTable";
import { LeadDetail } from "./components/LeadDetail";

export default function App() {
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
  const lastActivityRef = useRef(Date.now());
  const lastServerTouchRef = useRef(0);
  const absoluteExpiresAtRef = useRef(0);
  const sessionRef = useRef(session);
  const channelRef = useRef<BroadcastChannel | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "todos">("todos");
  const [contactFilter, setContactFilter] = useState<ContactFilter>("todos");
  const [heatFilter, setHeatFilter] = useState<HeatFilter>("todos");
  const [provinceFilter, setProvinceFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [sort, setSort] = useState("priority");

  useEffect(() => { sessionRef.current = session; }, [session]);

  const restoreDemoImmediately = useCallback((notice?: string) => {
    const safe = purgeRealSessionState(DEMO_LEADS, clearCrmState);
    setLeads(safe.leads);
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

  const load = async (authenticated: boolean, userActivity = false) => {
    setLoading(true);
    setError(null);
    try {
      const { leads: raw, meta, isDemo } = await fetchLeads(authenticated, userActivity);
      setLeads(authenticated && !isDemo ? mergeCrmState(raw) : raw);
      setMeta(meta);
      setIsDemo(isDemo);
    } catch (e) {
      if (e instanceof SessionExpiredError) {
        endRealSession("Tu sesión terminó. Volvimos al modo demo.");
      } else {
        setError(e instanceof Error ? e.message : "Error desconocido");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel("leadx-session");
      channelRef.current = channel;
      channel.onmessage = (event) => {
        if (event.data?.type === "session-ended") {
          restoreDemoImmediately(event.data.notice || "La sesión terminó en otra pestaña.");
        }
      };
      return () => { channel.close(); channelRef.current = null; };
    }
  }, [restoreDemoImmediately]);

  useEffect(() => {
    (async () => {
      const sess = await checkSession();
      setSession(sess);
      if (sess.authenticated) {
        lastActivityRef.current = sess.idleExpiresAt ? sess.idleExpiresAt - 20 * 60_000 : Date.now();
        lastServerTouchRef.current = Date.now();
        absoluteExpiresAtRef.current = sess.absoluteExpiresAt || Date.now() + 8 * 60 * 60_000;
      }
      await load(sess.authenticated);
    })();
  }, []); // Initial session bootstrap only.

  const recordUserActivity = useCallback(() => {
    if (!sessionRef.current.authenticated) return;
    const now = Date.now();
    lastActivityRef.current = now;
    setIdleWarning(false);
    if (now - lastServerTouchRef.current < 60_000) return;
    lastServerTouchRef.current = now;
    void continueSession().then((updated) => {
      if (updated.absoluteExpiresAt) absoluteExpiresAtRef.current = updated.absoluteExpiresAt;
    }).catch((error) => {
      if (error instanceof SessionExpiredError) {
        endRealSession("Tu sesión terminó. Volvimos al modo demo.");
      }
    });
  }, [endRealSession]);

  useEffect(() => {
    if (!session.authenticated) return;
    const timer = window.setInterval(() => {
      const idleFor = Date.now() - lastActivityRef.current;
      if ((absoluteExpiresAtRef.current && Date.now() >= absoluteExpiresAtRef.current) || idleFor >= 20 * 60_000) {
        endRealSession(idleFor >= 20 * 60_000
          ? "Tu sesión terminó por inactividad. Volvimos al modo demo."
          : "Tu sesión alcanzó el máximo de 8 horas. Volvimos al modo demo.");
      } else if (idleFor >= 18 * 60_000) {
        setIdleWarning(true);
      }
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [session.authenticated, endRealSession]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSelectedLead(null);
      setLoginOpen(false);
      document.body.classList.remove("filters-open");
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  const handleLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);
    try {
      const result = await login(password);
      if (result.ok) {
        setPassword("");
        const sess = { authenticated: true, mode: "real" as const };
        setSession(sess);
        lastActivityRef.current = Date.now();
        lastServerTouchRef.current = Date.now();
        absoluteExpiresAtRef.current = Date.now() + 8 * 60 * 60_000;
        setSessionNotice(null);
        setLoginOpen(false);
        await load(true, true);
      } else {
        setLoginError(result.error || "Contraseña incorrecta");
      }
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    endRealSession("Cerraste la sesión. Volvimos al modo demo.");
  };

  const handleContinueSession = async () => {
    try {
      const updated = await continueSession();
      lastActivityRef.current = Date.now();
      lastServerTouchRef.current = Date.now();
      if (updated.absoluteExpiresAt) absoluteExpiresAtRef.current = updated.absoluteExpiresAt;
      setIdleWarning(false);
    } catch {
      endRealSession("Tu sesión terminó por inactividad. Volvimos al modo demo.");
    }
  };

  const filtered = useMemo(() => {
    return leads
      .filter((l) => {
        if (statusFilter !== "todos" && l._status !== statusFilter) return false;
        if (contactFilter === "whatsapp" && !(l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone)) return false;
        if (contactFilter === "messenger" && !(l.fb_username || l.fb_author_id)) return false;
        if (contactFilter === "email" && !(l.email_publico || l.email)) return false;
        if (contactFilter === "sin_contacto" && (l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone || l.fb_username || l.fb_author_id || l.email_publico || l.email)) return false;
        if (heatFilter !== "todos" && heatLabel(l) !== heatFilter) return false;
        if (provinceFilter && l.provincia !== provinceFilter) return false;
        if (sourceFilter && (l.source_label || l.platform) !== sourceFilter) return false;
        if (search) {
          const hay = `${l.persona} ${l.provincia} ${l.title} ${l.snippet} ${l.source_label}`.toLowerCase();
          if (!hay.includes(search.toLowerCase())) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sort === "name") return (a.persona || "").localeCompare(b.persona || "", "es");
        const sa = a._heat_score ?? a.score ?? 0;
        const sb = b._heat_score ?? b.score ?? 0;
        const da = new Date(a.first_seen_at || a.discovery_timestamp || a.fecha_iso || 0).getTime();
        const db = new Date(b.first_seen_at || b.discovery_timestamp || b.fecha_iso || 0).getTime();
        if (sort === "recent") return db - da;
        if (sb !== sa) return sb - sa;
        return db - da;
      });
  }, [leads, statusFilter, contactFilter, heatFilter, provinceFilter, sourceFilter, search, sort]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand"><h1 className="app__title">LeadX</h1><p className="app__subtitle">{meta.generated_at ? `Actualizado ${new Date(meta.generated_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}` : "CRM de fotomultas"}</p></div>
        <div className="app__actions">
          <span className={`mode-badge ${isDemo ? "mode-badge--demo" : "mode-badge--real"}`}>
            {isDemo ? "Modo demo" : "Datos reales"}
          </span>
          {session.authenticated ? (
            <>
              <button className="btn btn--ghost" onClick={() => load(true, true)} disabled={loading} aria-label="Sincronizar">
                <RefreshCw size={16} aria-hidden="true" />
              </button>
              <button className="btn btn--ghost" onClick={handleLogout} aria-label="Salir">
                <LogOut size={16} aria-hidden="true" /> Salir
              </button>
            </>
          ) : (
            <>
            <form className="login-form desktop-login" onSubmit={(e) => { e.preventDefault(); handleLogin(); }}>
              <input type="password" className="login-form__input" placeholder="Contraseña" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Contraseña" autoComplete="current-password" />
              <button type="submit" className="btn btn--primary" disabled={loginLoading || !password}>
                {loginLoading ? "…" : "Entrar"}
              </button>
            </form>
            <button className="btn mobile-unlock" onClick={() => setLoginOpen(true)}><LockKeyhole size={17} />Desbloquear datos reales</button>
            </>
          )}
        </div>
      </header>

      {loginError && <div className="error" role="alert">{loginError}</div>}
      {error && <div className="error" role="alert">{error}</div>}
      {sessionNotice && <div className="session-notice" role="status">{sessionNotice}</div>}
      {isDemo && <p className="demo-caption">Datos ficticios para explorar el CRM</p>}

      {loginOpen && !session.authenticated && (
        <div className="sheet-layer" onMouseDown={(e) => { if (e.target === e.currentTarget) setLoginOpen(false); }}>
          <form className="login-sheet" onSubmit={(e) => { e.preventDefault(); handleLogin(); }}>
            <div className="sheet-header"><div><span className="eyebrow">Acceso privado</span><h2>Desbloquear datos reales</h2></div>
              <button type="button" className="icon-button" onClick={() => setLoginOpen(false)} aria-label="Cerrar"><X size={20} /></button></div>
            <label className="login-sheet__field"><span>Contraseña</span><input autoFocus type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
            {loginError && <p className="field-error" role="alert">{loginError}</p>}
            <button className="btn btn--primary login-sheet__submit" disabled={!password || loginLoading}>{loginLoading ? "Ingresando…" : "Ingresar"}</button>
          </form>
        </div>
      )}

      {idleWarning && (
        <div className="modal-backdrop" role="presentation">
          <div className="session-warning" role="alertdialog" aria-modal="true" aria-labelledby="idle-title">
            <h2 id="idle-title">Tu sesión se cerrará por inactividad.</h2>
            <div className="session-warning__actions">
              <button className="btn btn--primary" onClick={handleContinueSession}>Continuar sesión</button>
              <button className="btn" onClick={() => endRealSession("Cerraste la sesión. Volvimos al modo demo.")}>Salir ahora</button>
            </div>
          </div>
        </div>
      )}

      <Kpis leads={leads} />

      <Filters leads={leads} search={search} setSearch={setSearch}
        statusFilter={statusFilter} setStatusFilter={setStatusFilter}
        contactFilter={contactFilter} setContactFilter={setContactFilter}
        heatFilter={heatFilter} setHeatFilter={setHeatFilter}
        provinceFilter={provinceFilter} setProvinceFilter={setProvinceFilter}
        sourceFilter={sourceFilter} setSourceFilter={setSourceFilter}
        sort={sort} setSort={setSort} onActivity={recordUserActivity} />

      {loading && leads.length === 0 ? (
        <div className="loading"><span className="spinner" aria-hidden="true" />Cargando leads…</div>
      ) : (
        <LeadTable leads={filtered} selectedId={selectedLead?.id} onSelect={setSelectedLead} onActivity={recordUserActivity} />
      )}
      {selectedLead && <LeadDetail lead={selectedLead} onClose={() => setSelectedLead(null)} onActivity={recordUserActivity} />}
    </div>
  );
}
