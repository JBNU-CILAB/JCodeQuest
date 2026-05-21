import { useState, useCallback, useEffect } from "react";
import type { ConnSettings, ConnStatus, Route } from "./types";
import { loadSettings, saveSettings, adminFetch } from "./api";
import SettingsModal from "./components/SettingsModal";
import ProblemsView from "./views/ProblemsView";
import SubmissionsView from "./views/SubmissionsView";
import NoticesView from "./views/NoticesView";
import ReportsView from "./views/ReportsView";
import StatsView from "./views/StatsView";
import UsersView from "./views/UsersView";

const NAV: { route: Route; label: string; icon: string }[] = [
  { route: "problems",    label: "문제 관리",   icon: "⬡" },
  { route: "submissions", label: "풀이 기록",   icon: "⊞" },
  { route: "notices",     label: "공지",        icon: "◈" },
  { route: "reports",     label: "버그 제보",   icon: "⚠" },
  { route: "stats",       label: "통계",        icon: "⬟" },
  { route: "users",       label: "사용자",      icon: "○" },
];

export default function App() {
  const [settings, setSettings] = useState<ConnSettings>(loadSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [connStatus, setConnStatus] = useState<ConnStatus>("idle");
  const [route, setRoute] = useState<Route>("problems");

  const pingHealth = useCallback(async (s: ConnSettings) => {
    setConnStatus("loading");
    try {
      const r = await adminFetch("/api/health", s);
      setConnStatus(r.ok ? "ok" : "error");
    } catch {
      setConnStatus("error");
    }
  }, []);

  useEffect(() => { pingHealth(settings); }, []);

  function handleSaveSettings(s: ConnSettings) {
    saveSettings(s);
    setSettings(s);
    setShowSettings(false);
    pingHealth(s);
  }

  const routeTitle: Record<Route, string> = {
    problems:    "문제 관리",
    submissions: "풀이 기록",
    notices:     "공지 관리",
    reports:     "버그 제보",
    stats:       "통계 · 분석",
    users:       "사용자 관리",
  };

  const connLabels: Record<ConnStatus, string> = {
    idle:    "연결 전",
    ok:      "연결됨",
    error:   "연결 실패",
    loading: "연결 확인 중",
  };

  return (
    <div className="layout">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="brand">
            <div className="logomark">J</div>
            <div className="brand-text">
              <span className="brand-name">JCodeQuest</span>
              <span className="brand-tag">Admin</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">메뉴</div>
          {NAV.map(({ route: r, label, icon }) => (
            <button
              key={r}
              className={`nav-item${route === r ? " active" : ""}`}
              onClick={() => setRoute(r)}
            >
              <span className="nav-icon">{icon}</span>
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar-conn">
          <div className="conn-row">
            <div className={`conn-dot ${connStatus}`} />
            <span className="conn-label">{connLabels[connStatus]}</span>
            <button className="btn-settings" onClick={() => setShowSettings(true)}>⚙</button>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <div className="main-area">
        <header className="page-header">
          <div className="page-title">
            <div className="route-dot" />
            {routeTitle[route]}
          </div>
          <div className="page-actions">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => pingHealth(settings)}
            >
              {connStatus === "loading" ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "↻"}&nbsp;상태 확인
            </button>
          </div>
        </header>

        <main className="page-content">
          {route === "problems"    && <ProblemsView    settings={settings} />}
          {route === "submissions" && <SubmissionsView settings={settings} />}
          {route === "notices"     && <NoticesView     settings={settings} />}
          {route === "reports"     && <ReportsView     settings={settings} />}
          {route === "stats"       && <StatsView       settings={settings} />}
          {route === "users"       && <UsersView       settings={settings} />}
        </main>
      </div>

      {showSettings && (
        <SettingsModal
          initial={settings}
          onSave={handleSaveSettings}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}
