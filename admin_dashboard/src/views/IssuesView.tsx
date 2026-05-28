import { useState } from "react";
import type { ConnSettings } from "../types";
import ReportsView from "./ReportsView";
import PlagiarismView from "./PlagiarismView";

/** 좌측 레일의 '신고·검토' 단일 탭에 묶인 두 뷰의 서브탭 컨테이너.
 * - '버그 제보'(ReportsView): 사용자가 올린 이슈 검토 큐.
 * - '표절 검토'(PlagiarismView): plagiarism_engine이 잡은 의심 쌍 검토 큐.
 * 두 큐 모두 '운영자가 status를 토글하는 검토 워크플로'로 성격이 같지만 데이터 모양이
 * 달라 단일 테이블로 합치지 않고 서브탭으로 분리한다. 서브탭 상태는 페이지 로컬(새로고침 시 초기화). */

type SubTab = "reports" | "plagiarism";

const TABS: { id: SubTab; label: string; sub: string }[] = [
  { id: "reports",    label: "버그 제보",  sub: "사용자가 올린 이슈 검토 큐" },
  { id: "plagiarism", label: "표절 검토",  sub: "Dolos 구조 유사도로 잡힌 의심 쌍 검토 큐" },
];

export default function IssuesView({ settings }: { settings: ConnSettings }) {
  const [tab, setTab] = useState<SubTab>("reports");
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];

  return (
    <div className="main">
      <div className="issues-tabs" role="tablist" aria-label="신고·검토 서브탭">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`issues-tab${tab === t.id ? " active" : ""}`}
            onClick={() => setTab(t.id)}
            title={t.sub}
          >
            {t.label}
          </button>
        ))}
        <span className="issues-tab-sub">{active.sub}</span>
      </div>

      {/* 내부 뷰는 각자 자체 page-head를 가지고 있어 그대로 마운트한다. */}
      {tab === "reports" && <ReportsView settings={settings} />}
      {tab === "plagiarism" && <PlagiarismView settings={settings} />}
    </div>
  );
}
