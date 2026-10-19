# M15 중단 복구·같은 batch 부분 재개 계약

상태: 아래 계약을 후보 2 source `6c2cb6738c0208b7607385658804e85df7f58c5b`에서 구현하고 합성 반례·새 Windows 설치/독립 창·지정 두 TTS의 같은 batch 부분 재개·별도 CPU 소유 owner 중단 복구를 이번 증거로 검증했다. [현재 보고서와 한계](M15_REPORT.md)를 따른다. Release/tag/첨부 원격 게시 gate는 별도이며 실제 GPU/frozen GUI 강제 crash·모든 모델/환경 검증은 아니다. 과거 M14 성공은 이번 성공 증거가 아니다.

## 승인·원장

새 M15 계획은 case당 최대 두 attempt, 모델 시도 총 `2 × case 수`, 전체 가중치 최대 두 pass의 읽기 예산을 처음부터 표시한다. 다운로드·설치는 0이다. 재개는 기존 계획 SHA·현재 batch 상태 SHA에 결속한 별도 명시 승인과 일회 소비를 요구한다. 원래 절대 만료 시각과 누적 wall/read/hash/model-attempt 예약은 되돌리거나 연장하지 않는다. 예약 뒤 실패·불명도 소비로 남는다. 원장과 이벤트의 불일치·유실·음수·상태 불명은 거부한다. 기존 schema-2 DB는 기존 행·store identity를 유지하고 별도 grant/attempt 테이블만 추가한다.

완료·보류 case는 재실행하지 않는다. 미시작 pending은 같은 attempt의 첫 실행을, 취소·중단·실패·timeout case는 남은 예산에서 새 attempt와 새 run ID를 받는다. 현재 case 행은 새 attempt를 가리키며 과거 종결 이벤트에는 attempt 번호와 사유, run 연결을 보존한다. 두 번 소진하거나 만료되면 새 계획이 필요하다. 새 계획은 옛 성공을 새 성공으로 승격하지 않는다.

## 소유권과 중단

같은 home의 coordinator OS lock 아래에서 복구·재개 승인·소비·실행을 직렬화한다. 현재 살아 있는 coordinator가 있으면 복구하지 않는다. 외부 child는 실행 전에 고유 named Windows Job의 `spawning` marker를 flush/fsync하여 기록하고, Job 할당 뒤 `owned`, ActiveProcesses=0 관측 뒤 `drained`를 기록한다. 중단 뒤 exact Job의 부재 또는 active0을 재관찰한다. 접근/조회 실패와 spawn/ownership 사이 불명 marker는 자동 복구하지 않고 dispatch0으로 남긴다. PID 숫자만으로 종료하거나 다른 프로세스를 죽이지 않는다.

복구는 running batch를 interrupted로 바꾸고 실행 중 case의 중단 attempt를 보존한다. queued는 미시작 pending으로, 기존 pending·terminal case는 보존한다. 새 명시 재개 승인 전 실행은 없다. 정상 취소/timeout에서도 다음 case dispatch를 멈추고 소유 Job drain 뒤 상태를 확정한다. 재개 검증 도중 들어온 새 취소는 취소 이벤트 sequence로 재대조하여 지우지 않는다. 정전·디스크 하드웨어 실패의 원자적 복구를 검증했다는 주장은 하지 않는다.

최초 승인 또는 재개 grant 소비가 pending으로 commit된 뒤 coordinator가 running을 주장하기 전 중단된 경우도 복구한다. 최신 소비 event의 PID와 Windows process creation FILETIME을 기록하고 현재 exact identity가 살아 있으면 정상 handoff를 가로채지 않는다. 관찰 불명은 중단하고, 소비 owner가 사라진 pending만 같은 OS lock·소유 child 관찰 아래 interrupted로 바꾼다. pending case의 미시작 attempt 1 또는 이미 배정한 attempt 2는 유지하며 새 명시 재개 전 dispatch0이다.

## 같은 batch 완료 증거와 변경

완료 receipt SHA·batch/case/run/plan/code/profile·소유 cleanup 계약을 검사하고, request/result raw SHA와 실제 input/output bytes·출력 decode 계약을 재검증한다. 같은 batch에서 확인한 완료 TTS만 의존 STT 입력으로 복원할 수 있다. 다른 batch나 과거 작업 WAV fallback은 없다. 원본 관찰·code/static/catalog·runtime Python/lock·승인 설정 변경은 fail-closed이며 새 계획을 요구한다. 일시적 자원 관측은 worker 실행 전에 다시 수행한다.

## UI·배포

UI/API/CLI에 이전 소유권 확인→부분 재개 명시 승인→승인한 재개 시작을 제공한다. polling과 원래 start replay는 재개를 발행하지 않는다. 현재 attempt·시도 원장·원래 만료·누적 예약을 표시한다. WebView2 독립 창과 Python 포함 onedir Windows ZIP은 `0.15.0`이며 모델·OAuth·tokens·DB·개인 출력은 포함하지 않는다.

새 빌드는 clean Git source commit과 raw 소스 SHA를 SOURCE-PROVENANCE에 기록한다. 같은 package-data를 PyInstaller import 원본과 동봉 raw source로 사용한다. frozen 실행은 loader code object와 현재 raw source를 compile한 code object의 정규화 내용을 비교하고 누락·추가·변경 source/static, EXE 및 provenance hash를 거부한다. 시작 시 package 전체 파일을 manifest와 대조한다. 이는 코드서명이나 외부 신뢰 기관의 진위 보증이 아니다. package/source·새 설치·실행·복구·공개 readback은 이번 실행 증거로 따로 판정한다.
