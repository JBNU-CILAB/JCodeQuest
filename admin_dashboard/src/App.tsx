import { useState, useCallback, useEffect } from "react";
import type { ConnSettings, ConnStatus, Route } from "./types";
import { loadSettings, saveSettings, adminFetch } from "./api";
import { RailIcons } from "./components/Icons";
import SettingsModal from "./components/SettingsModal";
import HomeView from "./views/HomeView";
import RunsView from "./views/RunsView";
import ProblemsView from "./views/ProblemsView";
import SubmissionsView from "./views/SubmissionsView";
import NoticesView from "./views/NoticesView";
import IssuesView from "./views/IssuesView";
import UsersView from "./views/UsersView";

const NAV: { route: Route; label: string; Icon: (p: React.SVGProps<SVGSVGElement>) => React.JSX.Element }[] = [
  { route: "home",        label: "통합 현황",       Icon: RailIcons.home },
  { route: "runs",        label: "파이프라인 runs", Icon: RailIcons.runs },
  // 문제·통계: 원본/변형 관리 + 채점·앙상블 통계 + 원본-변형 비교를 단일 5탭 바로 묶음.
  { route: "problems",    label: "문제 · 통계",     Icon: RailIcons.problems },
  { route: "submissions", label: "풀이 기록",       Icon: RailIcons.submissions },
  { route: "notices",     label: "공지사항",        Icon: RailIcons.notices },
  // 신고·검토: 버그 제보 + 표절 검토를 서브탭으로 묶은 단일 진입점.
  { route: "reports",     label: "신고·검토",       Icon: RailIcons.reports },
  { route: "users",       label: "유저 / 권한",     Icon: RailIcons.users },
];

const ROUTE_TITLE: Record<Route, string> = {
  home:        "통합 현황",
  runs:        "파이프라인 runs",
  problems:    "문제 · 통계",
  submissions: "풀이 기록",
  notices:     "공지 관리",
  reports:     "신고·검토",
  users:       "사용자 관리",
};

const CONN_LABEL: Record<ConnStatus, string> = {
  idle: "연결 전",
  ok: "연결됨",
  error: "연결 실패",
  loading: "확인 중",
};

export default function App() {
  const [settings, setSettings] = useState<ConnSettings>(loadSettings);
  const [showSettings, setShowSettings] = useState(false);
  const [connStatus, setConnStatus] = useState<ConnStatus>("idle");
  const [route, setRoute] = useState<Route>("home");

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

  return (
    <div className="app">
      {/* ── Rail ── */}
      <aside className="rail">
        <div className="rail-logo">JC</div>
        {NAV.map(({ route: r, label, Icon }) => (
          <button
            key={r}
            className={`rail-btn${route === r ? " active" : ""}`}
            onClick={() => setRoute(r)}
            aria-label={label}
          >
            <Icon />
            <span className="tip">{label}</span>
          </button>
        ))}
        <div className="rail-spacer" />
        <button
          className="rail-btn"
          onClick={() => setShowSettings(true)}
          aria-label="연결 설정"
          title="연결 설정"
        >
          <span className="avatar-pip" style={{ width: 28, height: 28, margin: 0, fontSize: 12 }}>A</span>
          {connStatus === "error" && <span className="rail-dot" />}
        </button>
      </aside>

      {/* ── Topbar ── */}
      <header className="topbar">
        <div className="crumbs">
          <strong>JCode-Quest</strong>
          <span className="sep">/</span>
          <span>Admin</span>
          <span className="sep">/</span>
          <strong>{ROUTE_TITLE[route]}</strong>
        </div>
        <div className="topbar-right">
          <button
            className={`conn-pill ${connStatus}`}
            onClick={() => pingHealth(settings)}
            title="연결 상태 새로고침"
          >
            <span className="dot" />
            {CONN_LABEL[connStatus]}
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => setShowSettings(true)}>
            ⚙ 설정
          </button>
        </div>
      </header>

      {/* ── Main view ── */}
      {route === "home" && <HomeView settings={settings} />}
      {route === "runs" && <RunsView settings={settings} />}
      {route === "problems" && <ProblemsView settings={settings} />}
      {route === "submissions" && <SubmissionsView settings={settings} />}
      {route === "notices" && <NoticesView settings={settings} />}
      {route === "reports" && <IssuesView settings={settings} />}
      {route === "users" && <UsersView settings={settings} />}

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
