# M14 — 자동 검수 UI 연결·Windows 실검증

기준일 2026-10-19. 기준 main `43782c4770cbfbc732eb0393a4e1891911a9aa5d`에서 새 checkout과 고유 검증 home/output을 만들었다. 같은 Ai-manager의 후속 코드·공식 manifest·지정 모델/config·기존 공개 runtime만 사용했다. 기존 앱 home·인증·DB·과거 모델 결과를 새 입력이나 성공 근거로 연결하지 않았다.

## 구현과 보존

기존 9개 화면에 자동 검수 화면을 추가했다. native UI의 원본 입력·제한 관찰·기존 runtime 지정 → 서버 소유 immutable plan/diff → 정확 action/SHA의 명시 승인 → 일회 소비·순차 실행/취소 → 모델별 다축 결과·case/receipt·최근 100개 이력·새 계획을 연결한다. [M14 계약](M14_CONTRACT.md)에 API·상태·보존 경계를 고정했다.

`validation_ui.py`와 기존 server/lifecycle에 전용 API·owned coordinator를 연결했다. 새 상태는 앱 home 하위 별도 validation DB에 둔다. 기존 기능·인벤토리·registry·인증·DB·보안/브라우저 정책을 교체하거나 자동 정리하지 않는다. 원본 모델/runtime은 읽기 전용이며 다운로드·설치는 0이다. loopback Host/Origin·CSRF·JSON 제한을 유지한다.

M13 모델 bridge에는 환경 gate 통과·가중치 전체 SHA 완료 event만 추가했다. 고정 worker/lock·예산·입력/출력·slot·owned Job 계약은 유지했다. 승인 코드 binding에 현재 static 파일을 포함했으므로 화면 수정도 새 계획이 필요하다. `validation_store.py`의 LF 정규화는 실질 2줄의 static binding 추가와 구분한다. raw 코드 SHA는 확인한 Windows checkout bytes를 뜻하며 OS별 EOL이나 commit 식별자와 혼동하지 않는다.

## 게시 raw bytes와 줄바꿈 companion

게시 검토에서 기능/문서/새 static 17개 외의 기존 코드·lock 37개가 원격 Git blob의 LF와 Windows checkout의 CRLF만 달랐다. 현재 실행의 raw code binding을 원격에서도 재현하기 위해, 이 37개는 **비기능 줄바꿈 companion**으로 별도 명시 선택한다. 새로 실행 소스를 변환하거나 가중치/runtime을 변경하지 않고 실제 검증한 현재 bytes를 그대로 게시할 계획이다. 각 파일의 원격/current SHA·Git blob ID·CRLF 개수·canonical LF SHA를 private 감사 목록에 결속했다. 두 파일에서 CRLF→LF만 치환한 bytes가 정확히 같고 BOM·encoding·공백·코드 차이는 없다.

선택은 기능/문서/이번 static 17개와 EOL-only 37개, 합계 54개로 구분한다. `validation_store.py`는 이 기능 선택 17개에 포함되며 static binding 2줄 추가와 기존 CRLF→현재 LF 차이를 함께 기록한다. 기존 코드/lock companion 37개는 원격 LF→현재 CRLF 방향이다. 공개 raw source와 현재 실행의 full code SHA를 일치시키는 목적이며, 선택하지 않은 원격 blob과 기존 tag/Release/assets는 보존한다. 이 절은 게시 대상/검토 근거이고 실제 원격 일치·비선택 보존은 게시 후 별도 readback에서 확정한다.

## 새 CPU·API·빌드 검증

최종 동결 source/static에서 `unittest discover -s tests -v`를 새로 실행했다: **363개 중 356 PASS / 7 SKIP / 실패 0**, 45.055초. 새 M14 테스트 4개는 다음을 실제 fresh store/server/CPU child에서 확인했다.

- exact action/SHA 승인·CPU 권한의 모델 권한 승격 거부·일회 소비 replay·새 plan/case·이력 보존.
- 원본 변경 후 승인 거부·stale 표시·손상 store 원문 보존.
- 긴 CPU probe의 실제 child가 앱 close로 취소되고 조정기 종료를 기다림.
- HTTP CSRF/Origin 보호·client plan 주입 거부·allowlist 미인증 Drive의 dispatch 0·기존 server 회귀.

건너뛴 7개는 `test_tapir_worker.CheckpointTests`의 `test_checkpoint_nan_and_wrong_keys_rejected`, `test_hash_rejected_before_deserialization`, `test_output_shape_nonfinite_and_occlusion`, `test_weights_only_true_and_strict_state` 4개(이 CPU host에 격리 tracking CPU 의존성 없음), 같은 모듈 `VideoTests`의 `test_new_video_decode_and_resize_provenance`, `test_oversized_file_rejected` 2개(tracking decode 의존성 없음), `test_validation_contracts.ValidationContractsTests.test_read_document_symlink_if_supported` 1개(OS가 비관리자 symlink 허용 안 함)다. 이 skip을 PASS로 계산하지 않았다.

TypeScript 검사와 Vite production build, `git diff --check`를 통과했다. React 상태/응답 순서·source 전환의 관찰 제거·busy 입력 잠금·fragment view와 기존 9탭을 독립 검토했다. 독립 검토자는 CPU/HTTP 후보와 승인 주입·replay·stale·미연결/부분 관찰 반례, 실제 receipt/output readback을 owner와 분리해 수행했다.

처음 전체 suite를 source/static 수리와 동시에 돌린 진단은 code-binding stale 거부로 1 FAIL/1 ERROR가 발생했다. 이 기록은 보존하고 성공 근거로 쓰지 않았다. 이후 동결한 첫 후보는 363개/356 PASS·7 SKIP였으며, 아래 마지막 UI 표현 수정 후에도 최종 전체 suite를 다시 동결 상태에서 실행한 위 결과로 판정한다.

## Windows 실제 창과 첫 검증 이력

이번 source의 `server.py`·`desktop.py`·`validation_ui.py`가 실제 import된 절대 경로와 현재 static SHA를 private origin 기록에 저장했다. 공개 라이브러리만 기존 격리 build 환경에서 읽어 사용했다: pywebview 6.2.1, proxy_tools 0.1.0, pythonnet 3.1.0, clr_loader 0.3.1, requests 2.32.5. frontend는 package-lock의 React 19.2.0, TypeScript 5.9.3, Vite 7.3.7 등 기존 공개 의존성을 읽기 전용으로 사용했다. 이전 Ai-manager 코드나 이전 frontend bundle을 import하지 않았다.

이것은 현재 소스의 WebView2 독립 창을 띄운 **임시 source-host 검증**이다. 새 standalone EXE/설치 패키지·Release를 만들거나 기존 설치본을 업데이트한 검증은 아니다. 계정 token이나 기존 설정을 복사하지 않은 격리 home이며 실제 Drive OAuth/scan 성공으로 확대하지 않는다.

첫 후보의 실제 0.6B 검수는 API로 준비한 plan을 native 창에서 선택·검토·동의·승인·시작했다. 같은 실행의 새 입력과 WAV, 13개 필수 파일 2,498,388,392 bytes 전체 SHA·환경/자원 gate·출력 계약·receipt/Job active0을 확인했다. 당시 raw code SHA `76518c0f7f7196f085e9d22dc59d4412b8f3155d158896a6c86b8a698869acec`의 증거다.

이 첫 창에서 native 원본 입력 → metadata 15,194 bytes 새 관찰 → runtime 미지정의 새 plan/case 생성 → 승인 0/batch 0 → 명시 종료를 별도로 확인했다. Drive 허용 폴더 없음/로그인 필요·관찰/계획 버튼 차단, 출처 전환의 오래된 관찰 제거, 키보드 선택·포커스, 정상 close/reopen 후 이력 재선택을 확인했다. 초기 1280×900 창은 도구 관측 1266×846, 초기 900×900 창은 886×893이었다. 좁은 창은 표의 일부 긴 한글/기술값이 여러 줄로 감기며 전체 모바일/스크린리더 검증은 아니다. resize drag 자체는 실패로 보존하고 대표 폭 성공으로 계산하지 않았다. 전역 단축키 충돌 후 해당 단축키 사용을 중단했고 OS/보안 설정을 바꾸지 않았다.

실화면 독립 검토에서 성공 행의 `자산 검사 필요`와 전체 SHA 통과가 충돌하고, invalid 계획이 승인 대기로 보이는 점을 발견했다. 최종 UI는 full-SHA 근거를 우선 표시하고 종료/무효화 이력을 실행 불가로 표시한다. invalid의 원인이 기록되지 않은 경우 사용자 종료라고 추정하지 않는다. 이 두 표시를 수정한 뒤에는 첫 후보 성공을 현재 code의 성공으로 대체하지 않고 아래 새 final 검증을 분리했다.

## 최종 새 입력의 native 전 과정

최종 raw code SHA는 `49d377eebd235bb338417d56b12dc4a2b88944c5a6b5fd84b0181d3e26316e4e`다. 별도 fresh home에서 native UI로 원본 폴더·기존 Python/lock JSON 입력 → 새 metadata 관찰 → plan 생성 완료 → 런타임 SHA/기한/한도 확인 → 명시 동의/승인 → 새 batch 시작까지 실제 수행했다. API로 UI 입력을 대신하지 않았다. 독립 검토자와 부모의 새 한정 GO를 받은 별도 0.6B 1회이며 자동 재시도나 이전 승인 소비가 아니다. model runs 1·다운로드/설치 0, wall 1,800초·case 600초·hash 300초를 고정했다.

최종 batch의 실제 모델 dispatch는 1회이고 결과는 `models_completed`, case는 `succeeded`다. 13개 필수 모델 파일 2,498,388,392 bytes의 전체 SHA·현재 환경/자원·새 입력·고정 worker·WAV decode/PCM 신호·출력 계약·receipt·소유 Job active0을 확인했다. 새 run은 `88a20214780a47be8d5566e116da5f10`, receipt SHA는 `bf7da66a80693499b94dcdbf8f65ac46c848be736bab982ccb117fe41aecbb27`이다. WAV는 303,404 bytes, SHA-256 `e3fc1341a2396c366b627370c5dd31a94d93b46581397496467b1d135e37ea93`다.

고정 fixture recipe와 seed가 같아 첫 검증과 입력/출력 SHA가 같았지만, 이전 WAV를 복사하거나 입력으로 사용하지 않았다. 두 run의 input/output 파일 identity가 다르고 새 plan 뒤 생성 시각·새 worker PID·새 출력 경로·cold 로딩/추론 실측·서로 다른 receipt를 독립 검토자가 확인했다. 이는 서로 다른 문장의 품질 비교가 아니며 동일한 표준 recipe를 각 새 batch에서 독립 실행한 것이다.

독립 검토자는 DB 승인 used=1·dispatch=1, receipt SHA·현재 코드/runtime·원본 fingerprint·manifest의 13항목 기록, 새 input/WAV full SHA와 실제 WAV decode, 기록된 Job active0·종료코드0·현재 worker PID 부재를 다시 확인했다. 모델 전체 가중치를 두 번째로 모두 해시한 검증이나 추가 GPU 실행은 하지 않았고 owner의 이번 full-SHA 기록과 고정 manifest를 대조한 범위다.

최종 native 결과에서 `필수 자산 전체 SHA 통과`, 실제 시도·출력 계약 통과·품질 미평가를 확인했다. 같은 UI의 현재 원본/runtime 입력으로 별도 새 plan/case를 다시 만들고 승인 0/batch 0을 확인한 뒤 명시 종료했다. 수정된 이력은 `종료/무효화 · 실행 불가 · 새 계획 필요`로 표시되며 기존 실제 성공과 혼동되지 않는다. 새 최종 미리보기는 이 수정된 결과/이력의 실제 독립 창이며 이전 후보 이미지를 재사용하지 않았다.

private 실행 별칭은 첫 검증 `M14/verification-f3db57cce6e74cf198c94f66c947719f`, 최종 검증 `M14/verification-final-11c7b0a9925540bf81ff4cabc6f2168e`다. 첫 후보의 정상 재시작/좁은 창/Drive 비연결 확인과, 마지막 표시 2곳만 바꾼 최종 native 전 과정·표현 확인을 분리한다. 최종 code의 새 배포 패키지나 fresh Drive OAuth를 검증한 것으로 확대하지 않는다.

승인된 M14의 source/UI 연결과 확인한 Windows·지정 0.6B 범위의 실제 검증을 완료했다. 저장소 반영·원격 raw byte 대조는 게시 이후 별도 readback으로 확정하며, 게시 전 이를 완료했다고 기록하지 않는다.

## 출처·완료의 한계

기존 허용 자산은 지정된 0.6B 모델 가중치/config·기존 TTS Python/lock·공식 manifest와 공개 라이브러리다. 이번 새 산출물은 UI/API/event 변경·tests·observation/plan/approval/DB·새 입력/출력/receipt·현재 로그/접근성 관찰·native 미리보기다. 첫/최종 검증 디렉터리와 원본은 분리·보존하며, public 저장소에는 개인 root·계정·Drive ID·원시 로그·token·이미지를 넣지 않는다.

확인한 입력/output/runtime/source 경로와 receipt 범위에서 과거 모델 출력이나 다른 프로젝트 코드가 새 성공 입력으로 연결되지 않았음을 검사했다. 개인 디스크나 기존 DB 모든 byte의 전후 감사를 수행했다는 뜻은 아니다. 첫 준비 home은 상태를 먼저 만든 뒤 기존 ACL 검증이 거부해 보존했고, 이후 새 빈 native-home을 기존 앱 보호 초기화로 만든 후 사용했다. 기존 원본이나 보안 정책을 완화하지 않았다.

고급 runtime JSON은 수동 입력이며 자동 환경 발견·일반 사용자의 완전 무설정 검수로 표현하지 않는다. fresh Drive 실인증/실 scan, 다른 모델들의 이번 native 추론·품질 우열, 모든 화면 폭·전면 접근성/스크린리더·장시간 stress·실 GPU crash는 미검증이다. 실제 GPU 취소를 재현하지 않았으며 CPU child의 앱 close 취소와 구분한다. M15의 부분 재개·강제 중단 복구·새 Windows 패키지/Release는 남는다. 이 단계로 원격 GPU·비용·Drive 쓰기·새 모델/환경 설치를 승인하지 않는다.
