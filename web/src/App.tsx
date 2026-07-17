import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, LogOut } from "lucide-react";
import type { Lead, ContactFilter, HeatFilter, LeadStatus, SessionInfo } from "./types";
import { fetchLeads, login, logout, checkSession, continueSession, SessionExpiredError } from "./lib/api";
import { mergeCrmState, clearCrmState } from "./lib/storage";
import { DEMO_LEADS } from "./demo-leads";
import { purgeRealSessionState } from "./lib/session-state";
import { heatLabel } from "./lib/heatmap";
import { Kpis } from "./components/Kpis";
import { Filters } from "./components/Filters";
import { LeadTable } from "./components/LeadTable";

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
  const lastActivityRef = useRef(Date.now());
  const lastServerTouchRef = useRef(0);
  const sessionRef = useRef(session);
  const channelRef = useRef<BroadcastChannel | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "todos">("todos");
  const [contactFilter, setContactFilter] = useState<ContactFilter>("todos");
  const [heatFilter, setHeatFilter] = useState<HeatFilter>("todos");

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
        lastActivityRef.current = Date.now();
        lastServerTouchRef.current = Date.now();
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
    void continueSession().catch((error) => {
      if (error instanceof SessionExpiredError) {
        endRealSession("Tu sesión terminó. Volvimos al modo demo.");
      }
    });
  }, [endRealSession]);

  useEffect(() => {
    if (!session.authenticated) return;
    const timer = window.setInterval(() => {
      const idleFor = Date.now() - lastActivityRef.current;
      if (idleFor >= 20 * 60_000) {
        endRealSession("Tu sesión terminó por inactividad. Volvimos al modo demo.");
      } else if (idleFor >= 18 * 60_000) {
        setIdleWarning(true);
      }
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [session.authenticated, endRealSession]);

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
        setSessionNotice(null);
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
      await continueSession();
      lastActivityRef.current = Date.now();
      lastServerTouchRef.current = Date.now();
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
        if (search) {
          const hay = `${l.persona} ${l.provincia} ${l.title} ${l.snippet} ${l.source_label}`.toLowerCase();
          if (!hay.includes(search.toLowerCase())) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const sa = a._heat_score ?? a.score ?? 0;
        const sb = b._heat_score ?? b.score ?? 0;
        if (sb !== sa) return sb - sa;
        const da = new Date(a.first_seen_at || a.discovery_timestamp || a.fecha_iso || 0).getTime();
        const db = new Date(b.first_seen_at || b.discovery_timestamp || b.fecha_iso || 0).getTime();
        return db - da;
      });
  }, [leads, statusFilter, contactFilter, heatFilter, search]);

  return (
    <div className="app" onPointerDownCapture={recordUserActivity} onKeyDownCapture={recordUserActivity}>
      <header className="app__header">
        <div>
          <h1 className="app__title">LeadX CRM</h1>
          <p className="app__subtitle">
            {meta.generated_at && <>Actualizado {new Date(meta.generated_at).toLocaleString("es-AR")}</>}
          </p>
        </div>
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
            <form className="login-form" onSubmit={(e) => { e.preventDefault(); handleLogin(); }}>
              <input type="password" className="login-form__input" placeholder="Contraseña" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Contraseña" autoComplete="current-password" />
              <button type="submit" className="btn btn--primary" disabled={loginLoading || !password}>
                {loginLoading ? "…" : "Ingresar"}
              </button>
            </form>
          )}
        </div>
      </header>

      {loginError && <div className="error" role="alert">{loginError}</div>}
      {error && <div className="error" role="alert">{error}</div>}
      {sessionNotice && <div className="session-notice" role="status">{sessionNotice}</div>}

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
        heatFilter={heatFilter} setHeatFilter={setHeatFilter} />

      {loading && leads.length === 0 ? (
        <div className="loading"><span className="spinner" aria-hidden="true" />Cargando leads…</div>
      ) : (
        <LeadTable leads={filtered} />
      )}
    </div>
  );
}
