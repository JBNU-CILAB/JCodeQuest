import { useState } from "react";
import type { ConnSettings } from "../types";

interface Props {
  initial: ConnSettings;
  onSave: (s: ConnSettings) => void;
  onClose: () => void;
}

export default function SettingsModal({ initial, onSave, onClose }: Props) {
  const [s, setS] = useState<ConnSettings>(initial);
  const upd = (k: keyof ConnSettings) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setS((prev) => ({ ...prev, [k]: e.target.value }));

  return (
    <div className="modal-bg" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">⚙&nbsp; 연결 설정</div>

        <div className="form-grid">
          <div className="field span-2">
            <label>Authoring Engine URL</label>
            <input
              type="text"
              value={s.baseUrl}
              onChange={upd("baseUrl")}
              placeholder="http://localhost:8001"
            />
          </div>
          <div className="field span-2">
            <label>Authoring 관리자 토큰</label>
            <input
              type="password"
              value={s.baseToken}
              onChange={upd("baseToken")}
              placeholder="Bearer 토큰 (없으면 비워두기)"
            />
          </div>
          <div className="field span-2">
            <label>Judge Engine URL</label>
            <input
              type="text"
              value={s.judgeUrl}
              onChange={upd("judgeUrl")}
              placeholder="http://localhost:8002"
            />
          </div>
          <div className="field span-2">
            <label>Judge 관리자 토큰</label>
            <input
              type="password"
              value={s.judgeToken}
              onChange={upd("judgeToken")}
              placeholder="Bearer 토큰 (없으면 비워두기)"
            />
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>취소</button>
          <button className="btn btn-primary" onClick={() => onSave(s)}>저장 · 연결 테스트</button>
        </div>
      </div>
    </div>
  );
}
