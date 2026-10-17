import { useEffect, useState, type ReactNode } from "react";

type HostResult = {
  status: string;
  stage?: string;
  error?: string;
  filename?: string;
  model_id?: string;
  files_verified?: number;
  instance_id?: string;
  source_directory?: string;
  preflight?: {
    component: string;
    expected_bytes: number;
    observed_bytes: number | null;
  };
};
type HostApi = {
  save_audio: (id: string) => Promise<HostResult>;
  runtime_status: () => Promise<HostResult>;
  prepare_runtime: () => Promise<HostResult>;
  model_status: () => Promise<HostResult>;
  prepare_model: (id: string, source_path?: string) => Promise<HostResult>;
  cancel_model: () => Promise<HostResult>;
};
declare global {
  interface Window {
    pywebview?: { api: HostApi };
  }
}

function useHost() {
  const [host, setHost] = useState<HostApi | undefined>(
    () => window.pywebview?.api,
  );
  useEffect(() => {
    const ready = () => setHost(window.pywebview?.api);
    window.addEventListener("pywebviewready", ready);
    ready();
    return () => window.removeEventListener("pywebviewready", ready);
  }, []);
  return host;
}

export function AudioDownload({
  id,
  url,
  children,
}: {
  id: string;
  url: string;
  children: ReactNode;
}) {
  const host = useHost();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save() {
    if (!host || busy) return;
    setBusy(true);
    setMessage("저장 위치를 선택해주세요.");
    try {
      const result = await host.save_audio(id);
      setMessage(
        result.status === "saved"
          ? `${result.filename} 저장·무결성 확인 완료`
          : result.status === "cancelled"
            ? "저장을 취소했습니다."
            : "저장하지 못했습니다. 기존 파일과 겹치지 않는 새 위치를 선택해주세요.",
      );
    } catch {
      setMessage("앱 저장 기능에 연결하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="desktop-save">
      {host ? (
        <button className="secondary" disabled={busy} onClick={save}>
          {children}
        </button>
      ) : (
        <a className="secondary" href={`${url}?download=1`} download>
          {children}
        </a>
      )}
      {message && <small role="status">{message}</small>}
    </span>
  );
}

const stages: Record<string, string> = {
  awaiting_user: "첫 준비가 필요합니다",
  verifying_bundled_python: "앱에 포함된 Python 전체 파일 확인",
  creating_app_local_environment: "별도 추론 환경 생성",
  installing_package_manager: "패키지 관리자 준비",
  downloading_installing_cuda_runtime:
    "CUDA 추론 패키지 다운로드·설치 (큰 파일)",
  installing_model_dependencies: "모델 의존성 설치",
  checking_dependencies: "의존성 확인",
  ready_for_runtime_check: "설치 완료 · 모델 준비 화면에서 런타임 검사 필요",
  retry_available:
    "준비가 중단되거나 실패했습니다. 원인을 확인한 뒤 다시 준비할 수 있습니다.",
};
export function DesktopRuntime() {
  const host = useHost();
  const [state, setState] = useState<HostResult>({
    status: "not_started",
    stage: "awaiting_user",
  });
  const [model, setModel] = useState<HostResult>({ status: "idle" });
  const [selecting, setSelecting] = useState(false);
  const [modelChoice, setModelChoice] = useState("qwen3-tts-1.7b-customvoice");
  const [sourcePath, setSourcePath] = useState("");
  useEffect(() => {
    if (!host) return;
    let active = true;
    const update = async () => {
      try {
        const [result, modelResult] = await Promise.all([
          host.runtime_status(),
          host.model_status(),
        ]);
        if (active) {
          setState(result);
          setModel(modelResult);
        }
      } catch {
        if (active) setState({ status: "failed", error: "host_unavailable" });
      }
    };
    void update();
    const interval = window.setInterval(update, 1500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [host]);
  if (!host) return null;
  const denied = state.status === "denied" || model.status === "denied";
  const running = state.status === "running";
  const modelBusy =
    denied ||
    selecting ||
    model.status === "running" ||
    model.status === "cancelling";
  async function prepareModel(id: string, path?: string) {
    if (!host || modelBusy) return;
    setSelecting(true);
    try {
      setModel(await host.prepare_model(id, path));
    } catch {
      setModel({ status: "failed" });
    } finally {
      setSelecting(false);
    }
  }
  return (
    <section className="desktop-runtime" aria-label="독립 앱 준비">
      <div className="desktop-runtime-row">
        <div>
          <strong>앱 추론 환경</strong>
          <p role="status">
            {denied
              ? "앱 연결을 확인하지 못했습니다. 앱을 다시 열어주세요."
              : stages[state.stage || ""] || "준비 상태 확인"}
            {state.error ? " · 연결·저장 공간·앱 무결성을 확인해주세요." : ""}
          </p>
          <small>
            Python은 앱에 포함됩니다. 첫 준비는 인터넷과 수 GB의 저장 공간이
            필요합니다. 모델 파일·Google 로그인은 별도로 준비합니다.
          </small>
          {state.instance_id && <p>현재 앱 환경 ID · {state.instance_id}</p>}
        </div>
        <button
          className="secondary"
          disabled={denied || running || state.status === "ready"}
          onClick={async () => {
            try {
              setState(await host.prepare_runtime());
            } catch {
              setState({ status: "failed", error: "host_unavailable" });
            }
          }}
        >
          {running
            ? "준비 중…"
            : state.status === "ready"
              ? "설치 완료"
              : state.status === "failed" || state.status === "interrupted"
                ? "다시 준비"
                : "추론 환경 준비"}
        </button>
      </div>
      <div className="desktop-runtime-row">
        <div>
          <strong>지정 모델 파일로 새 준비</strong>
          <p>
            모델의 가중치·구성·토크나이저 폴더를 직접 선택합니다. 지정 목록의
            파일만 새 준비 ID로 복사하고 해시를 확인합니다.
          </p>
          <p role="status">
            {selecting
              ? "지정 모델 폴더를 선택해주세요."
              : model.status === "running"
                ? `모델 파일 확인·복사 중 · ${model.files_verified || 0}개 확인`
                : model.status === "ready"
                  ? "모델 파일 준비·무결성 확인 완료"
                  : model.status === "cancelled"
                    ? "모델 준비를 취소했습니다. 원본은 보존됩니다."
                    : model.status === "failed"
                      ? "지정 모델 폴더·파일 무결성·저장 공간을 확인해주세요."
                      : model.status === "cancelling"
                        ? "현재 파일 처리를 중단합니다…"
                        : "모델 폴더를 선택하거나 모델 준비 화면에서 Drive 다운로드를 사용하세요."}
          </p>
          {model.model_id && (
            <p>
              선택 모델 ·{" "}
              {model.model_id === "qwen3-tts-1.7b-customvoice"
                ? "1.7B CustomVoice"
                : "0.6B CustomVoice"}
            </p>
          )}
          {model.source_directory && (
            <p className="desktop-source-path">
              선택 원본 폴더 · {model.source_directory}
            </p>
          )}
          {model.status === "failed" && model.preflight && (
            <p role="alert">
              확인 파일 · {model.preflight.component} · 기대{" "}
              {model.preflight.expected_bytes.toLocaleString()} bytes / 실제{" "}
              {model.preflight.observed_bytes === null
                ? "파일 확인 불가"
                : `${model.preflight.observed_bytes.toLocaleString()} bytes`}
            </p>
          )}
        </div>
        <div className="desktop-model-actions">
          <button
            className="secondary"
            disabled={modelBusy}
            onClick={() => prepareModel("qwen3-tts-0.6b-customvoice")}
          >
            0.6B 폴더 선택
          </button>
          <button
            className="secondary"
            disabled={modelBusy}
            onClick={() => prepareModel("qwen3-tts-1.7b-customvoice")}
          >
            1.7B 폴더 선택
          </button>
          {model.status === "running" && (
            <button
              className="danger"
              onClick={async () => {
                setModel(await host.cancel_model());
              }}
            >
              모델 준비 취소
            </button>
          )}
        </div>
      </div>
      <div className="desktop-path-entry">
        <label htmlFor="desktop-model-choice">직접 경로로 준비할 모델</label>
        <select
          id="desktop-model-choice"
          value={modelChoice}
          disabled={modelBusy}
          onChange={(event) => setModelChoice(event.target.value)}
        >
          <option value="qwen3-tts-0.6b-customvoice">0.6B CustomVoice</option>
          <option value="qwen3-tts-1.7b-customvoice">1.7B CustomVoice</option>
        </select>
        <label htmlFor="desktop-model-source">
          지정 모델 원본 폴더 전체 절대경로
        </label>
        <input
          id="desktop-model-source"
          value={sourcePath}
          disabled={modelBusy}
          onChange={(event) => setSourcePath(event.target.value)}
          placeholder="찾아보기 대신 원본 폴더의 전체 경로를 입력할 수 있습니다"
        />
        <p>
          선택 모델과 입력 폴더를 확인한 뒤 준비하세요. 지정 파일만 새 준비
          기록으로 복사하며 원본은 보존합니다.
        </p>
        <button
          className="secondary"
          disabled={modelBusy || !sourcePath.trim()}
          onClick={() => prepareModel(modelChoice, sourcePath)}
        >
          이 경로로 모델 준비
        </button>
      </div>
    </section>
  );
}
