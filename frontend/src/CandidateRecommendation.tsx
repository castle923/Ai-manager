import "./candidateRecommendation.css";

export const purposeOptions = [
  { id: "tts", label: "음성 생성" },
  { id: "stt", label: "음성 인식·전사" },
  { id: "image", label: "이미지 생성 · 편집 미확인" },
  { id: "llm", label: "텍스트 대화" },
  { id: "tracking", label: "영상의 지정 지점 추적" },
];

export type Recommendation = {
  purpose: string;
  rank: number | null;
  eligible: boolean;
  related: boolean;
  status: string;
  profile_name_candidates: { id: string; purpose: string }[];
  reasons: string[];
  reason_codes: string[];
  limitations: string[];
};

export type RecommendationPolicy = {
  purpose: string;
  purposes: { id: string; label: string }[];
  criteria: string[];
  rank_requirements: string[];
  tie_break: string;
  limitations: string[];
  recommended: number;
  related: number;
};

export function RecommendationNotes({ value, compact = false }: { value?: Recommendation; compact?: boolean }) {
  if (!value) return <span className="muted">추천 근거 미확인</span>;
  const label = value.rank != null ? `검토 추천 ${value.rank}위` : value.eligible ? "추천 조건 충족 · 번호는 현재 목록 기준" : !value.purpose ? "작업 선택 전" : value.related ? "관련 후보 · 순위 보류" : "추천번호 없음";
  const shownReasons = compact && !value.eligible ? value.reasons.filter((_, i) => !["purpose_match", "profile_name_only"].includes(value.reason_codes[i])) : value.reasons;
  return <div className={`recommendation-notes ${compact ? "compact" : ""}`}>
    <strong className={value.rank != null ? "recommendation-rank" : "muted"}>{label}</strong>
    {!compact && <p>목적: {({tts:"음성 생성",stt:"음성 인식·전사",image:"이미지 생성 · 편집 미확인",llm:"텍스트 대화",tracking:"영상의 지정 지점 추적"} as Record<string,string>)[value.purpose] || "미선택 · 전체 후보"}</p>}
    <ul>{shownReasons.slice(0, compact ? 2 : undefined).map(reason => <li key={reason}>{reason}</li>)}</ul>
    {compact && shownReasons.length > 2 && <small>나머지 근거·순위 보류 사유는 상세에서 확인</small>}
    {!compact && <>
      {value.profile_name_candidates.length > 0 && <p>이름 후보: {value.profile_name_candidates.map(p => p.id).join(" · ")} · 확정 식별 아님</p>}
      <ul className="recommendation-limits">{value.limitations.map(note => <li key={note}>{note}</li>)}</ul>
    </>}
  </div>;
}

export function RecommendationSummary({ policy, files }: { policy?: RecommendationPolicy; files: boolean }) {
  if (!policy) return null;
  return <section className="recommendation-policy" aria-label="추천 기준과 확인 범위">
    <p><strong>현재 수집된 파일 후보 기준</strong> · 현재 작업실의 선택된 Drive 수집 기록만 비교합니다.</p>
    <p>{!policy.purpose ? "하고 싶은 작업을 선택하세요. 선택 전에는 전체 후보에 추천번호를 부여하지 않습니다." : files ? "그룹 단위만 모델 추천순위가 있습니다. 전체 파일에는 작업 관련성 근거를 표시하며, 구성 파일·shard를 별도 모델로 추천하지 않습니다. 실제 표시 순서는 선택한 정렬을 따릅니다." : policy.recommended ? `현재 검색·필터 안에서 검토 추천 ${policy.recommended}개 · 관련 후보 ${policy.related}개` : policy.related ? "관련 후보는 있지만 모델 root·필수 관찰 근거 또는 수집 범위가 불충분해 순위를 보류했습니다. 상세 사유를 확인하세요." : "현재 검색·계정·용도·수집 필터 안에 추천할 근거가 없습니다. 다른 필터와 선택한 작업을 확인하세요."}</p>
    <p>추천순위는 실측 성능·품질 순위가 아니며 실행 가능성을 보장하지 않습니다.</p>
    <p>동일 조건은 이름·계정·ID 순의 검토번호입니다. 큰 모델이나 많은 파일이 더 좋은 품질이라는 뜻이 아닙니다.</p>
    {policy.purpose === "image" && <p>현재 고정 이미지 프로필은 생성용입니다. 이미지 편집 지원은 미확인입니다.</p>}
    <details><summary>순위 조건·동점 기준·미확인 항목</summary>
      <p>번호는 다음 조건을 모두 만족하는 후보 그룹에만 부여합니다.</p>
      <ul>{policy.rank_requirements.map(item => <li key={item}>{item}</li>)}</ul>
      <p>{policy.tie_break}</p>
      <ul>{policy.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details>
  </section>;
}
