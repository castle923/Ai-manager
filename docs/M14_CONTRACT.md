# M14 — Windows 앱의 자동 검수 UI

같은 Ai-manager의 M12 영속 계획·승인과 M13 고정 worker를 기존 React/WebView2 앱에 연결한다. 이 단계는 source 구현과 현재 Windows에서의 검증이며, 기존 v0.10.0 설치본·태그·Release를 갱신하지 않는다. 새 패키지와 부분 재개는 M15다.

## 입력과 계획

기존 9개 화면을 유지하고 `자동 검수` 화면을 추가한다. 원본은 사용자가 명시한 로컬 폴더 1–6개 또는 현재 앱 설정의 Drive allowlist 항목이다. 다른 폴더·계정·기존 출력·토큰을 자동 탐색하거나 가져오지 않는다.

`원본 관찰만`은 로컬 폴더 1개 또는 선택한 Drive 범위의 제한된 metadata를 관찰한다. complete/partial·후보·사유·읽은 metadata bytes와 모델 미실행을 표시한다. 후보가 없거나 지원 밖이어도 관찰 결과를 볼 수 있다. 부분 관찰은 모델 정상/고장 판정이 아니다. 모델 계획 생성은 별도로 새 관찰을 수행하며 M13의 anchor-only 정책·중복 root/profile·bounded complete 계약을 따른다.

Drive는 현재 앱의 계정·allowlist·인증 관리자를 사용한다. 미연결 또는 허용 폴더 없음은 안내하고 계획/dispatch를 막는다. `run_models`는 로컬 원본만 허용한다. Drive metadata 관찰과 제어 계획 확인/CPU 확인이 실제 모델 실행 권한으로 승격되지 않는다. 새로운 OAuth 로그인·동의는 사용자 직접행위이며, 기존 token 복사나 Drive 쓰기는 없다.

실제 모델 검수는 고급 입력에서 프로필별 기존 `python`·`lock` 경로를 JSON으로 지정한다. 서버가 현재 파일의 SHA·고정 lock/package 계약을 검사해 spec과 immutable plan을 만든다. shared-home은 서버의 현재 앱 home으로 고정하며 client가 plan·승인·shared-home을 주입할 수 없다. 로컬 Python은 사용자가 신뢰하는 기존 프로그램을 선택해야 한다. SHA 결속이 프로그램의 안전성 인증이나 OS sandbox를 뜻하지 않는다. 환경 자동 탐색·설치·다운로드는 구현하지 않는다.

## 명시 승인과 실행

계획 화면은 plan ID/SHA·action·원본 범위·카탈로그/코드 SHA·기한·가중치 전체 읽기 예산·한도·선택 case·기존 runtime SHA/lock/timeout을 보여준다. 이전 계획과 action·limits·code·catalog·observation·runtime/recipe 변경을 구분한다. 원본/환경의 현재 동일성은 승인·소비·dispatch 직전 재확인하며, 화면 조회를 무결성 통과로 표시하지 않는다.

동의 checkbox와 `이 계획 명시 승인`으로 정확한 action/SHA에 한 번의 승인을 발급한다. 별도의 `승인한 검수 시작`이 그 승인을 소비한다. 기존 M12/M13 기한·누적 예산·source/runtime/code 재검사·같은 home slot·owned Job·출력 계약을 보존한다. 중복 POST는 같은 batch를 관찰하고 새 worker를 발급하지 않는다. polling은 GET만 수행한다. 다운로드 bytes·설치 권한은 0이다.

`이 계획 종료 · 새 계획 작성 허용`은 정확 SHA의 미실행 또는 종료한 계획만 invalid로 표시한다. pending/running batch는 먼저 취소해야 한다. 원문·승인·case·기존 성공을 지우지 않는다. invalid의 예전 발생 이유를 사용자 종료라고 추정하지 않으며, 이력에서는 `종료/무효화 · 실행 불가`로 표시한다. 재검수는 새 관찰·plan/case·승인·batch·새 입력을 사용한다. M15의 같은 batch 부분 재개를 제공하지 않는다.

## 진행·결과·보존

진행은 영속 event의 실제 단계와 파일 SHA 확인을 표시하며 임의 진행률을 만들지 않는다. 취소 요청과 종료를 구분한다. 앱의 정상 close는 새 dispatch를 막고 조정기에 종료를 전달하며, 소유 worker/Job 정리가 끝날 때까지 기다린다. 실제 CPU child 취소/앱 close와 모델 worker 정상 Job active0 검증을 구분한다. 강제 프로세스 종료나 모든 crash 복구를 보장하지 않는다.

모델별 표는 식별·전체 SHA·환경/자원 gate·실제 시도·출력 계약·품질 축을 분리한다. 성공 행의 자산 표시는 현재 full-SHA event 근거를 우선하며, 최초 metadata 관찰 상태를 현재 무결성 미검사라고 표시하지 않는다. `models_completed`는 계획 처리가 끝났다는 뜻이며 성공/미수행·보류/실패·취소/중단 건수를 함께 표시한다. `model_test_performed`는 시도 여부다. 품질은 항상 미평가이며 음질·전사 정확도·미감 우열을 주장하지 않는다.

case 상세는 새 run ID·receipt SHA·검증 파일/bytes·당시 환경 관측·출력 SHA/bytes·Job 정리 근거를 보여준다. 실패/취소에서도 dispatch/run ID를 보존한다. 성공 receipt를 현재 DB SHA·plan/case/profile/code와 다시 대조하고 변경/부재는 출력 근거 미확인으로 표시한다. 원시 worker 로그·PID·내부 source 경로는 결과 요약에서 제외한다. 승인에 필요한 원본/runtime 경로는 private local UI에만 표시하며 공개 보고서에 넣지 않는다.

같은 앱 home 하위 `validation`에 별도 DB와 observation/input/output/cache/receipt를 둔다. 기존 인벤토리·registry·인증·DB·과거 출력은 변경하거나 이동/삭제하지 않는다. 저장소가 손상됐거나 scope가 다르면 초기화/자동수리하지 않는다. 이력은 최근 100개 계획을 명시적으로 표시하고 개별 계획은 ID로 조회한다. 모든 과거 결과는 당시 실행 기록이다.

## API와 현재 한계

기존 loopback Host/Origin·JSON body 크기·CSRF 보호를 그대로 사용한다. GET `/api/validation`, `/scopes`, `/<plan ID>`와 POST `/observe`, `/plan`, `/approve`, `/start`, `/cancel`, `/supersede`를 추가한다. 새 UI의 출처 변경은 이전 관찰을 비우고 늦은 응답을 폐기한다. native view 상태는 query 대신 기존 fragment를 유지한다. 승인 code SHA는 shipped Python/manifest/lock에 현재 static 파일도 포함하므로 UI가 바뀌어도 새 계획이 필요하다.

검증 범위와 실측은 [M14 보고서](M14_REPORT.md)를 따른다. 고급 runtime JSON 수동 입력, 최근 100개 이력 제한, 새 Drive OAuth 실인증·실 Drive scan 미검증, 전면 접근성/스크린리더·390px·모든 PC/모델 품질, 강제 종료/부분 재개·새 Release는 남는다. 같은 소스의 Windows WebView2 임시 host 실창 검증은 새 배포 패키지의 설치 검증과 다르다.
