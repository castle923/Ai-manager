import { useEffect, useState, type RefObject } from "react";
import { Eye, EyeOff, Save, Settings2 } from "lucide-react";
import {
  workspaceApi,
  type PreferenceRecord,
  type ViewPreferences,
} from "./workspace";
type SettingsResponse = {
  preferences: PreferenceRecord;
  workspace: {
    paths: Record<string, string>;
    accounts: Record<string, boolean>;
    drive: { configuration: "configured" | "not_configured" };
    allowed_folder_count: number;
    runtime_dependencies?: {
      role: string;
      python_base: string;
      runtime_root: string;
      reused: boolean;
      base_required: boolean;
    }[];
  };
};
export function SettingsPanel({
  csrf,
  onSaved,
}: {
  csrf: RefObject<string>;
  onSaved: (value: ViewPreferences) => void;
}) {
  const [data, setData] = useState<SettingsResponse | null>(null),
    [draft, setDraft] = useState<ViewPreferences | null>(null),
    [visible, setVisible] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  async function reload() {
    setError("");
    try {
      const r = await workspaceApi<SettingsResponse>("/api/preferences");
      setData(r);
      setDraft({ ...r.preferences.values });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    let live = true;
    workspaceApi<SettingsResponse>("/api/preferences")
      .then((r) => {
        if (live) {
          setData(r);
          setDraft({ ...r.preferences.values });
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, []);
  async function save() {
    if (!draft || !data || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const r = await workspaceApi<{ preferences: PreferenceRecord }>(
        "/api/preferences",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-AiManager-CSRF": csrf.current,
          },
          body: JSON.stringify({
            revision: data.preferences.revision,
            values: draft,
          }),
        },
      );
      setData({ ...data, preferences: r.preferences });
      onSaved(r.preferences.values);
      setMessage(
        "이 작업실의 보기 설정을 저장했습니다. 시간·메모리 표시는 작업 기록과 차트에 바로 적용되며 기본 화면은 다음 시작부터 적용됩니다.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const names: Record<string, string> = {
    home: "현재 작업실",
    settings: "연결·허용 범위 설정",
    preferences: "보기 설정",
    inventory: "수집 인벤토리 DB",
    registry: "등록 모델 DB",
    runtime: "현재 추론 환경",
    outputs: "음성 실행·출력",
  };
  return (
    <div className="workspace-panels">
      <section className="panel settings-card">
        <div className="tts-card-heading">
          <h2>
            <Settings2 size={20} /> 작업실 보기 설정
          </h2>
          <span className="badge">로컬 설정</span>
        </div>
        <p className="muted">
          이 작업실의 화면 표시만 바꿉니다. 계정 권한·허용 폴더·모델·실행 조건은
          변경하지 않습니다.
        </p>
        {error && (
          <div className="banner danger" role="alert">
            {error}
            <button onClick={reload} disabled={busy}>
              현재 값 다시 불러오기
            </button>
          </div>
        )}
        {message && (
          <p className="workspace-message" role="status">
            {message}
          </p>
        )}
        {draft && (
          <form
            className="settings-fields"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <label>
              다음 시작의 기본 화면
              <select
                value={draft.default_section}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    default_section: e.target
                      .value as ViewPreferences["default_section"],
                  })
                }
              >
                <option value="registry">모델 관리</option>
                <option value="history">통합 작업 기록</option>
              </select>
            </label>
            <label>
              작업 기록 한 페이지
              <select
                value={draft.history_page_size}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    history_page_size: Number(e.target.value),
                  })
                }
              >
                {[10, 25, 50].map((n) => (
                  <option key={n} value={n}>
                    {n}개
                  </option>
                ))}
              </select>
            </label>
            <label>
              기록·차트의 시각 표시
              <select
                value={draft.time_display}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    time_display: e.target.value as "local" | "UTC",
                  })
                }
              >
                <option value="local">이 PC의 현지 시각</option>
                <option value="UTC">UTC</option>
              </select>
            </label>
            <label>
              성능 차트의 메모리 단위
              <select
                value={draft.memory_unit}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    memory_unit: e.target.value as "MiB" | "GiB",
                  })
                }
              >
                <option value="GiB">GiB (1,073,741,824 bytes)</option>
                <option value="MiB">MiB (1,048,576 bytes)</option>
              </select>
            </label>
            <button className="primary" disabled={busy || !csrf.current}>
              <Save size={16} />
              {busy ? "저장 중…" : "보기 설정 저장"}
            </button>
            <small>
              저장 버전 {data?.preferences.revision} · 현재 실행 중인 작업의
              입력·환경은 바뀌지 않습니다.
            </small>
          </form>
        )}
      </section>
      <section className="panel settings-card">
        <h2>설정과 자료의 위치</h2>
        <p className="muted">
          개인 경로는 기본으로 가립니다. 아래 위치는 읽기 전용 안내이며 파일
          이동·삭제 기능이 아닙니다.
        </p>
        <button
          className="secondary"
          aria-expanded={visible}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}{" "}
          {visible ? "개인 경로 가리기" : "이 PC의 전체 경로 보기"}
        </button>
        <dl className="workspace-paths">
          {data &&
            Object.entries(data.workspace.paths).map(([key, path]) => (
              <div key={key}>
                <dt>{names[key] || key}</dt>
                <dd>
                  <code>{visible ? path : "개인 경로 가림"}</code>
                </dd>
              </div>
            ))}
        </dl>
        {data?.workspace.runtime_dependencies?.length ? (
          <div>
            <p>
              실행 환경은 아래 Python 기반에 의존합니다. 재사용 중인 이전 앱
              폴더도 이 참조가 유지되는 동안 삭제하거나 이동하지 마세요.
              모델·결과·앱 소스는 이전 버전으로 되돌리지 않습니다.
            </p>
            <ul>
              {data.workspace.runtime_dependencies.map((dependency) => (
                <li key={dependency.role}>
                  {dependency.role}:{" "}
                  {dependency.reused
                    ? "기존 환경 검증 후 참조"
                    : "새 환경 준비 필요"}{" "}
                  ·{" "}
                  <code>
                    {visible ? dependency.python_base : "Python 기반 경로 가림"}
                  </code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {data?.workspace.drive.configuration === 'not_configured' ? <p>Drive 설정 없음 · 자격 증명 저장소는 확인하지 않았습니다. 로컬 모델과 이 작업실 데이터는 유지됩니다.</p> : <p>
          계정 A:{" "}
          {data?.workspace.accounts.A
            ? "자격 증명 저장됨 · 실제 갱신은 계정 화면에서 확인"
            : "연결 정보 없음"}
          <br />
          계정 B:{" "}
          {data?.workspace.accounts.B
            ? "자격 증명 저장됨 · 실제 갱신은 계정 화면에서 확인"
            : "연결 정보 없음"}
          <br />
          설정된 허용 폴더 {data?.workspace.allowed_folder_count ?? "미확인"}개
        </p>}
        <div className="workspace-caveat">
          <strong>보존·복구 범위</strong>
          <p>
            기존 DB 백업·복원 도구는 인벤토리 DB에만 적용됩니다. 모델 등록
            DB·보기 설정·인증·모델·런타임·WAV 전체를 함께 복원하는 기능은
            아닙니다.
          </p>
          <p>
            연결·허용 범위 원본은 이 화면에서 편집하지 않습니다. OS 보안 설정과
            전역 기본 브라우저도 변경하지 않습니다.
          </p>
        </div>
      </section>
    </div>
  );
}
