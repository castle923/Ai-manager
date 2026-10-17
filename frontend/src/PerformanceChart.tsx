import { useEffect, useId, useState } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import {
  formatTime,
  statusLabel,
  workspaceApi,
  type ViewPreferences,
} from "./workspace";
type Metric =
  | "total_seconds"
  | "loading_seconds"
  | "inference_seconds"
  | "peak_gpu_allocated_bytes";
type Row = {
  side: string;
  run_id: string | null;
  status: string;
  model: { id: string; name: string; revision: string | null } | null;
  input_sha256: string | null;
  seed: number | null;
  measured_at: string | null;
  metrics: Record<Metric, number | null>;
  output_integrity: string;
  provenance_available: boolean;
  manifest_sha256: string | null;
  runtime_lock_sha256: string | null;
  recorded_conditions: Record<string, string | boolean | null>;
};
type Performance = {
  comparison_id: string;
  status: string;
  rows: Row[];
  common_checks: Record<string, boolean>;
  common_conditions_confirmed: boolean;
  sample_count_per_model: number | null;
  parameters: Record<string, unknown> | null;
};
const metrics: Record<Metric, string> = {
  total_seconds: "총 처리 시간",
  loading_seconds: "모델 로딩 시간",
  inference_seconds: "음성 생성 시간",
  peak_gpu_allocated_bytes: "PyTorch 최대 할당 메모리",
};
const conditions: Record<string, string> = {
  input_sha256: "입력 해시",
  parameters: "seed·언어·화자·생성 조건",
  runtime_code_scope: "당시 런타임·코드 해시",
  device: "GPU 장치",
  dtype: "연산 정밀도",
  attention: "Attention 방식",
  cold_loading: "콜드 로딩",
  comparison_policy: "새 실행·캐시 미사용·표본 수",
};
export function PerformanceChart({
  comparisonId,
  preferences,
  refreshKey,
  onRun,
}: {
  comparisonId: string;
  preferences: ViewPreferences;
  refreshKey?: string;
  onRun?: (id: string) => void;
}) {
  const [data, setData] = useState<Performance | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [reload, setReload] = useState(0),
    [metric, setMetric] = useState<Metric>("total_seconds");
  const chartId = useId();
  useEffect(() => {
    let live = true;
    setBusy(true);
    setError("");
    setData(null);
    workspaceApi<Performance>("/api/performance/" + comparisonId)
      .then((r) => {
        if (live) setData(r);
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setBusy(false);
      });
    return () => {
      live = false;
    };
  }, [comparisonId, refreshKey, reload]);
  const factor =
    metric === "peak_gpu_allocated_bytes"
      ? preferences.memory_unit === "GiB"
        ? 2 ** 30
        : 2 ** 20
      : 1;
  const unit =
    metric === "peak_gpu_allocated_bytes" ? preferences.memory_unit : "초";
  function value(row: Row, key: Metric) {
    const n = row.metrics[key];
    return typeof n === "number" && Number.isFinite(n) && n >= 0 ? n : null;
  }
  function text(row: Row, key: Metric) {
    const n = value(row, key);
    const divisor =
      key === "peak_gpu_allocated_bytes"
        ? preferences.memory_unit === "GiB"
          ? 2 ** 30
          : 2 ** 20
        : 1;
    return n === null
      ? "미수집 (N/A)"
      : (n / divisor).toLocaleString("ko-KR", { maximumFractionDigits: 3 }) +
          (key === "peak_gpu_allocated_bytes"
            ? " " + preferences.memory_unit
            : " 초");
  }
  const values = data?.rows.map((r) => value(r, metric)) ?? [];
  const max = Math.max(
    0,
    ...values.filter((v): v is number => v !== null).map((v) => v / factor),
  );
  return (
    <section
      className="panel performance-panel"
      aria-labelledby={chartId + "-heading"}
      aria-busy={busy}
    >
      <div className="tts-card-heading">
        <h2 id={chartId + "-heading"}>
          <BarChart3 size={20} /> 기록된 A/B 성능
        </h2>
        <button onClick={() => setReload((n) => n + 1)} disabled={busy}>
          <RefreshCw size={16} /> 측정 기록 확인
        </button>
      </div>
      <p className="muted">
        완료된 실행의 측정 기록을 조회합니다. 과거 결과를 새 실행 성공으로
        바꾸지 않습니다.
      </p>
      {error && (
        <p className="banner danger" role="alert">
          {error}
        </p>
      )}
      {busy && !data && (
        <p role="status">비교 출처와 출력 해시를 확인합니다…</p>
      )}
      {data && (
        <>
          <div className="performance-condition-heading">
            <span
              className={
                data.common_conditions_confirmed ? "badge green" : "badge amber"
              }
            >
              {data.common_conditions_confirmed
                ? "기록된 공통 조건 일치"
                : "공통 조건·출처 미확인 또는 불일치"}
            </span>
            <span className="badge">
              모델별 n={data.sample_count_per_model ?? "미확인"} · 평균·순위
              계산 없음
            </span>
          </div>
          <div className="performance-model-labels">
            {data.rows.map((row) => (
              <p key={row.side}>
                <strong>
                  {row.side} · {row.model?.name || "모델 미확인"}
                </strong>
                <small>
                  {formatTime(row.measured_at, preferences.time_display)}
                </small>
              </p>
            ))}
          </div>
          <p>
            모델과 manifest 차이는 비교 대상의 차이입니다. 시간·메모리 수치로
            음질 승자를 정하지 않습니다.
          </p>
          <label className="chart-metric-label">
            차트 측정 항목
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as Metric)}
            >
              {Object.entries(metrics).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {data.common_conditions_confirmed ? (
            <svg
              className="performance-svg"
              viewBox="0 0 640 168"
              role="img"
              aria-labelledby={chartId + "-title " + chartId + "-desc"}
            >
              <title id={chartId + "-title"}>
                {metrics[metric]} A/B 비교 ({unit})
              </title>
              <desc id={chartId + "-desc"}>
                {data.rows
                  .map((r) => r.side + ": " + text(r, metric))
                  .join(". ")}
                . 표본은 모델별1개이며 상세 원천값은 아래 표에 있습니다.
              </desc>
              {[0, 0.5, 1].map((t) => (
                <g key={t}>
                  <line
                    x1={62 + 410 * t}
                    y1="28"
                    x2={62 + 410 * t}
                    y2="145"
                    className="chart-grid"
                  />
                  <text
                    x={62 + 410 * t}
                    y="18"
                    textAnchor="middle"
                    className="chart-tick"
                  >
                    {(max * t).toLocaleString("ko-KR", {
                      maximumFractionDigits: 2,
                    })}
                  </text>
                </g>
              ))}
              {data.rows.map((row, i) => {
                const n = value(row, metric);
                const width =
                  n !== null && max > 0 ? (n / factor / max) * 410 : 0;
                return (
                  <g key={row.side}>
                    <text x="28" y={64 + i * 64} className="chart-side">
                      {row.side}
                    </text>
                    {n !== null && (
                      <rect
                        x="62"
                        y={42 + i * 64}
                        width={width}
                        height="32"
                        rx="4"
                        className={i === 0 ? "chart-bar-a" : "chart-bar-b"}
                      />
                    )}
                    <text
                      x={Math.min(62 + width + 10, 495)}
                      y={64 + i * 64}
                      className="chart-value"
                    >
                      {text(row, metric)}
                    </text>
                  </g>
                );
              })}
              <text x="618" y="161" textAnchor="end" className="chart-tick">
                단위: {unit}
              </text>
            </svg>
          ) : (
            <div className="chart-unavailable">
              <strong>동일 조건 차트: 미확인 (N/A)</strong>
              <p>
                아래에서 각 실행의 기록값을 확인할 수 있습니다. 누락·실패
                값은0으로 표시하지 않으며 출처를 확인하기 전 성능 비교로 합치지
                않습니다.
              </p>
            </div>
          )}
          <div className="table-wrap">
            <table className="performance-table">
              <caption>
                같은 원천값의 표 · 총 처리에는 로딩·파일 검사·프로세스 부가
                시간이 포함됩니다.
              </caption>
              <thead>
                <tr>
                  <th scope="col">실행</th>
                  <th scope="col">총 처리 (초)</th>
                  <th scope="col">로딩 (초)</th>
                  <th scope="col">생성 (초)</th>
                  <th scope="col">최대 할당 ({preferences.memory_unit})</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.side}>
                    <th scope="row">
                      {row.side} · {statusLabel[row.status] || "확인 불가"}
                    </th>
                    {(Object.keys(metrics) as Metric[]).map((key) => (
                      <td key={key}>{text(row, key)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="workspace-caveat">
            메모리는 PyTorch 최대 할당량입니다. GPU 전체 VRAM 사용량·PC 전체
            메모리와 다릅니다. 한 번의 순차 측정은 통계적 우열·동일 성능의
            재현을 증명하지 않습니다.
          </p>
          <details className="performance-provenance">
            <summary>비교 조건과 원본 출처</summary>
            <ul className="condition-checks">
              {Object.entries(data.common_checks).map(([key, ok]) => (
                <li key={key}>
                  <span>{conditions[key] || key}</span>
                  <strong>{ok ? "일치 확인" : "불일치·미확인"}</strong>
                </li>
              ))}
            </ul>
            <p>
              비교 ID <code>{data.comparison_id}</code>
            </p>
            {data.rows.map((row) => (
              <article key={row.side}>
                <h3>
                  {row.side} · {row.model?.name || "모델 미확인"}
                </h3>
                <dl className="workspace-paths">
                  <div>
                    <dt>실행 ID</dt>
                    <dd>
                      <code>{row.run_id || "미확인"}</code>
                      {row.run_id && onRun && (
                        <button onClick={() => onRun(row.run_id!)}>
                          원본 실행 기록
                        </button>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>모델 revision</dt>
                    <dd>
                      <code>{row.model?.revision || "미확인"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>manifest SHA-256</dt>
                    <dd>
                      <code>{row.manifest_sha256 || "미확인"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>입력 SHA-256 / seed</dt>
                    <dd>
                      <code>{row.input_sha256 || "미확인"}</code> /{" "}
                      {row.seed ?? "미확인"}
                    </dd>
                  </div>
                  <div>
                    <dt>당시 장치·연산</dt>
                    <dd>
                      {row.recorded_conditions.device ?? "미확인"} /{" "}
                      {row.recorded_conditions.dtype ?? "미확인"} /{" "}
                      {row.recorded_conditions.attention ?? "미확인"}
                    </dd>
                  </div>
                  <div>
                    <dt>콜드 로딩·캐시</dt>
                    <dd>
                      콜드{" "}
                      {row.recorded_conditions.cold_loading === true
                        ? "확인"
                        : "미확인"}{" "}
                      · 캐시{" "}
                      {row.recorded_conditions.cache_reuse === false
                        ? "사용 안 함"
                        : "미확인"}
                    </dd>
                  </div>
                  <div>
                    <dt>런타임 lock / 코드 범위</dt>
                    <dd>
                      <code>{row.runtime_lock_sha256 || "미확인"}</code>
                      <br />
                      <code>
                        {row.recorded_conditions.runtime_code_scope || "미확인"}
                      </code>
                    </dd>
                  </div>
                  <div>
                    <dt>측정 완료 시각</dt>
                    <dd>
                      {formatTime(row.measured_at, preferences.time_display)}
                    </dd>
                  </div>
                  <div>
                    <dt>출처·출력</dt>
                    <dd>
                      실행 출처{" "}
                      {row.provenance_available ? "연결 확인" : "미확인"} · 출력
                      해시{" "}
                      {row.output_integrity === "matched" ? "일치" : "미확인"}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
            {data.parameters && (
              <pre className="condition-json">
                {JSON.stringify(data.parameters, null, 2)}
              </pre>
            )}
          </details>
        </>
      )}
    </section>
  );
}
