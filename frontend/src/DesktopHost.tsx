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
  path?: string;
  backup?: string;
  preflight?: {
    component: string;
    expected_bytes: number;
    observed_bytes: number | null;
  };
};
type HostApi = {
  choose_model_directory: () => Promise<HostResult>;
  choose_drive_original: (kind: "client" | "allowlist") => Promise<HostResult>;
  configure_drive: (
    clientPath: string,
    allowlistPath: string,
  ) => Promise<HostResult>;
  drive_setup_status: () => Promise<HostResult>;
  task_runtime_status: (identifier?: string) => Promise<HostResult>;
  prepare_task_runtime: (identifier?: string) => Promise<HostResult>;
  save_task: (id: string, outputId: string) => Promise<HostResult>;
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

export function ModelFolderPicker({
  onSelected,
  disabled,
}: {
  onSelected: (path: string) => void;
  disabled?: boolean;
}) {
  const host = useHost();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  if (!host?.choose_model_directory) return null;
  return (
    <div className="folder-picker">
      <button
        type="button"
        className="secondary"
        disabled={disabled || busy}
        onClick={async () => {
          setBusy(true);
          setMessage("");
          try {
            const result = await host.choose_model_directory();
            if (result.status === "selected" && result.path)
              onSelected(result.path);
            else
              setMessage(
                result.status === "cancelled"
                  ? "선택을 취소했습니다. 입력한 위치는 유지합니다."
                  : "모델 보관 폴더를 선택하지 못했습니다.",
              );
          } catch {
            setMessage("앱 폴더 선택에 연결하지 못했습니다.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "폴더 선택 중…" : "내장·외장 드라이브에서 폴더 선택"}
      </button>
      {message && <small role="status">{message}</small>}
    </div>
  );
}

const driveSetupErrors: Record<string, string> = {
  workspace_busy:
    "진행 중이거나 대기 중인 작업을 먼저 마친 뒤 연결 설정을 적용하세요.",
  drive_setup_inputs_invalid:
    "지정한 OAuth client와 허용 목록 JSON의 전체 경로·형식을 확인하세요. 기존 설정은 유지했습니다.",
  drive_setup_settings_invalid:
    "현재 작업실 설정을 읽지 못했습니다. 기존 파일을 보존하고 설정 경로·무결성을 확인하세요.",
  drive_setup_failed_local_preserved:
    "Drive 설정을 적용하지 못해 로컬 작업실 설정을 복구했습니다. 지정 원본을 확인하세요.",
  drive_setup_recovery_requires_restart:
    "안전한 복구를 완료하지 못했습니다. 기존 자료를 보존했습니다. 앱을 정상 종료한 뒤 현재 설정을 확인하고 다시 열어주세요.",
  drive_already_configured:
    "이미 Drive 설정이 있는 작업실입니다. 아래 계정 연결 상태를 확인하세요.",
};

export function DriveConnectionSetup() {
  const host = useHost();
  const [client, setClient] = useState("");
  const [allowlist, setAllowlist] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!host?.drive_setup_status) return;
    let live = true;
    const update = async () => {
      try {
        const result = await host.drive_setup_status();
        if (live && result.status === "failed")
          setMessage(
            driveSetupErrors[result.error || ""] ||
              "연결 설정 상태를 확인하세요.",
          );
      } catch {
        /* The explicit submit still reports bridge errors. */
      }
    };
    void update();
    const timer = window.setInterval(update, 1500);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [host]);
  async function choose(kind: "client" | "allowlist") {
    if (!host?.choose_drive_original || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await host.choose_drive_original(kind);
      if (result.status === "selected" && result.path)
        (kind === "client" ? setClient : setAllowlist)(result.path);
      else
        setMessage(
          result.status === "cancelled"
            ? "선택을 취소했습니다. 기존 입력을 유지합니다."
            : "지정한 JSON 원본을 선택할 수 없습니다.",
        );
    } catch {
      setMessage("앱 파일 선택에 연결하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel drive-connection-setup"
      aria-label="현재 로컬 작업실에 Google Drive 연결 설정 추가"
    >
      <h2>이 작업실에 Google Drive 연결하기</h2>
      <p>
        현재 작업실은 Drive를 연결하지 않은 로컬 모드입니다. 이전 작업실의
        로그인이 해제됐다는 뜻은 아닙니다. 이 작업실의 모델 등록·DB는 유지하면서
        연결 설정을 추가할 수 있습니다.
      </p>
      <p>
        이번 프로젝트에 지정한 OAuth client와 두 계정의 허용 목록 JSON 원본을
        선택하세요. 설정 원본을 백업하고 연결 화면을 다시 엽니다. 다음 계정
        로그인과 Google 동의는 직접 진행합니다.
      </p>
      <label>
        OAuth client JSON 원본 전체 경로
        <input
          value={client}
          onChange={(event) => setClient(event.target.value)}
          disabled={busy}
        />
      </label>
      <button
        type="button"
        className="secondary"
        disabled={busy || !host?.choose_drive_original}
        onClick={() => choose("client")}
      >
        OAuth client 원본 선택
      </button>
      <label>
        허용 목록 JSON 원본 전체 경로
        <input
          value={allowlist}
          onChange={(event) => setAllowlist(event.target.value)}
          disabled={busy}
        />
      </label>
      <button
        type="button"
        className="secondary"
        disabled={busy || !host?.choose_drive_original}
        onClick={() => choose("allowlist")}
      >
        허용 목록 원본 선택
      </button>
      <p className="caption">
        기존 작업실의 토큰을 복사하거나 자동으로 계정에 로그인하지 않습니다.
        Drive 권한은 읽기 전용입니다.
      </p>
      <button
        type="button"
        className="primary"
        disabled={
          busy || !host?.configure_drive || !client.trim() || !allowlist.trim()
        }
        onClick={async () => {
          if (!host || busy) return;
          setBusy(true);
          setMessage("설정 원본과 작업 상태를 확인합니다…");
          try {
            const result = await host.configure_drive(
              client.trim(),
              allowlist.trim(),
            );
            setMessage(
              result.status === "configured"
                ? "설정을 백업하고 연결 화면을 다시 엽니다. 계정별 로그인은 직접 진행하세요."
                : driveSetupErrors[result.error || ""] ||
                    "연결 설정을 완료하지 못했습니다.",
            );
          } catch {
            setMessage(
              "앱 연결 설정에 응답이 없습니다. 현재 화면과 설정을 확인하세요.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "연결 설정 확인 중…" : "현재 작업실을 보존하고 Drive 설정 적용"}
      </button>
      {!host?.configure_drive && (
        <p role="status">
          이 연결 설정은 Ai Manager Windows 앱에서 사용할 수 있습니다.
        </p>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
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
      <article className="desktop-preparation-card">
        <div className="desktop-runtime-row">
          <div className="desktop-preparation-heading">
            <span className="desktop-step">1단계</span>
            <h2>TTS 추론 환경</h2>
            <p
              className="desktop-preparation-status"
              data-state={denied ? "denied" : state.status}
              role="status"
            >
              {denied
                ? "앱 연결을 확인하지 못했습니다. 앱을 다시 열어주세요."
                : stages[state.stage || ""] || "준비 상태 확인"}
              {state.error ? " · 연결·저장 공간·앱 무결성을 확인해주세요." : ""}
            </p>
            <p className="desktop-preparation-requirement">
              첫 준비에는 인터넷과 수 GB의 저장 공간이 필요합니다.
            </p>
          </div>
          <button
            className="primary"
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
        <details className="desktop-preparation-details">
          <summary>자세히 보기</summary>
          <p>
            Python은 앱에 포함됩니다. 첫 준비에는 인터넷과 수 GB의 저장 공간이
            필요하며 모델 파일은 별도로 준비합니다.
          </p>
          {state.instance_id && (
            <p className="desktop-instance-id">
              현재 앱 환경 ID · {state.instance_id}
            </p>
          )}
        </details>
      </article>
      <article className="desktop-preparation-card">
        <div className="desktop-runtime-row">
          <div className="desktop-preparation-heading">
            <span className="desktop-step">2단계</span>
            <h2>TTS 프로필 파일 준비</h2>
            <p className="caption">
              0.6B와 1.7B는 Qwen3-TTS 실행 프로필 크기입니다. 드라이브 종류가
              아닙니다. 일반 모델 위치는 모델 관리에서 등록하세요.
            </p>
            <p
              className="desktop-preparation-status"
              data-state={denied ? "denied" : model.status}
              role="status"
            >
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
                          : "모델 원본 폴더를 선택하거나 직접 경로를 입력하세요."}
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
              0.6B TTS 원본 폴더 선택
            </button>
            <button
              className="secondary"
              disabled={modelBusy}
              onClick={() => prepareModel("qwen3-tts-1.7b-customvoice")}
            >
              1.7B TTS 원본 폴더 선택
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
          <button
            className="primary"
            disabled={modelBusy || !sourcePath.trim()}
            onClick={() => prepareModel(modelChoice, sourcePath)}
          >
            이 경로로 모델 준비
          </button>
        </div>
        <details className="desktop-preparation-details">
          <summary>자세히 보기</summary>
          <p>
            가중치·구성·토크나이저가 있는 지정 모델 원본 폴더를 선택하세요. 선택
            모델과 입력 폴더를 확인한 뒤 지정 목록의 파일만 새 준비 ID로
            복사하고 해시를 확인하며 원본은 보존합니다.
          </p>
          <p>
            Drive 다운로드는 모델 준비 화면에서 사용할 수 있으며 별도의 Drive
            설정과 인증이 필요합니다.
          </p>
        </details>
      </article>
    </section>
  );
}

export function TaskDownload({
  id,
  outputId,
  url,
  children,
}: {
  id: string;
  outputId: string;
  url: string;
  children: ReactNode;
}) {
  const host = useHost();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save() {
    if (!host || busy) return;
    setBusy(true);
    try {
      const result = await host.save_task(id, outputId);
      setMessage(
        result.status === "saved"
          ? `${result.filename} 저장·무결성 확인 완료`
          : result.status === "cancelled"
            ? "저장을 취소했습니다."
            : "저장하지 못했습니다. 올바른 확장자와 새 저장 위치를 확인하세요.",
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
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => void save()}
        >
          {children}
        </button>
      ) : (
        <a className="secondary" href={`${url}?download=1`} download>
          {children}
        </a>
      )}
      {message ? <small role="status">{message}</small> : null}
    </span>
  );
}

export function TaskRuntime() {
  const host = useHost();
  const [identifier, setIdentifier] = useState("whisper-large-v3-turbo");
  const [state, setState] = useState<HostResult>({ status: "not_started" });
  useEffect(() => {
    if (!host) return;
    let active = true;
    async function update() {
      try {
        const value = await host!.task_runtime_status(identifier);
        if (active) setState(value);
      } catch {
        if (active) setState({ status: "failed" });
      }
    }
    void update();
    const timer = window.setInterval(update, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [host, identifier]);
  if (!host)
    return (
      <p>
        각 모델 유형은 별도 실행 환경을 준비해야 합니다. 독립 앱의 정상 준비
        기능을 사용하세요.
      </p>
    );
  return (
    <div className="desktop-runtime">
      <label>
        격리 실행 환경
        <select
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          disabled={state.status === "running"}
        >
          <option value="whisper-large-v3-turbo">Whisper</option>
          <option value="tapir">BootsTAPIR v2</option>
          <option value="llama-3.1-8b-instruct">Llama</option>
          <option value="qwen-image-2.1">Qwen Image (큰 별도 환경)</option>
        </select>
      </label>
      <p role="status">
        선택한 격리 환경 ·{" "}
        {state.status === "ready"
          ? "설치·CUDA 점검 완료"
          : state.status === "running"
            ? "설치 중 · 공개 패키지를 받습니다"
            : state.status === "failed"
              ? "준비 실패 · 비공개 진단 로그 확인 필요"
              : "준비 필요"}
      </p>
      <button
        type="button"
        className="secondary"
        disabled={state.status === "running" || state.status === "ready"}
        onClick={async () => {
          try {
            setState(await host.prepare_task_runtime(identifier));
          } catch {
            setState({ status: "failed" });
          }
        }}
      >
        선택한 격리 환경 준비
      </button>
    </div>
  );
}
