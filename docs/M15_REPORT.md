# M15 구현·새 Windows 배포 검증 기록

상태: 최종 후보 2의 새 Windows 패키지·격리 설치·독립 창·지정 두 TTS의 같은 batch 부분 재개·별도 CPU 소유 중단 복구를 이번 실행으로 검증했다. GitHub Release 게시와 태그 고정은 최종 공개 gate이며 아직 완료로 기록하지 않는다. 아래 확인 환경과 제한을 따른다. 아래 후보 checkpoint와 초기 시험은 당시 진행 기록으로 보존한다.

## 최종 후보 2 패키지와 설치

빌드 소스는 clean commit `6c2cb6738c0208b7607385658804e85df7f58c5b`, code/static SHA-256은 `f2a15a5290696fc4ef0fa080595a9ff5229a73ed22e02bf1b6932a56bf18c386`다. 문서 후속 commit과 실제 패키지의 고정 소스를 구분한다. 초기 checkout부터 `core.autocrlf=false`로 raw Git blob을 대조했고, 공개한 정확 변경 집합과 비대상 blob/type/mode를 원격에서 다시 읽어 확인했다. 기존 태그 세 개와 Release/assets도 당시 baseline과 일치했다.

| 항목 | 이번 후보 2 결과 |
|---|---|
| Windows ZIP | `AiManager-0.15.0-windows.zip`, 113,164,275 bytes |
| ZIP SHA-256 | `5f6bf3e656ac18730f5d535baa11b3abb80b1bcf6a1724c3e17563606e2b3363` |
| 설치 EXE SHA-256 | `951d5fe7a863eba16c4fc7b912e7b91a40934f482d20129ae72a5c13564aad03` |
| ZIP/manifest | 8,311 entries, manifest 대상 8,310파일 전량 SHA·CRC 대조, 추가·누락·중복·불일치0 |
| source binding | raw source76개와 고정 commit bytes 일치, SOURCE-PROVENANCE·EXE·실제 frozen import code와 raw/code SHA 검사 PASS |
| 라이선스/공개 검사 | dependency license28개와 CPython 두 runtime LICENSE, 개인 경로·계정·key material의 명시 패턴 검사0; 서명 없는 EXE |

공개 desktop 의존성은 새 격리 build 환경에 고정 버전으로 설치했다. 해당 pip 출력은 캐시 사용으로 관찰했으며 배포 archive 두 개도 공식 고정 size/SHA와 일치하는 허용 캐시를 사용했다. 이것을 모든 준비 단계의 네트워크 수신0으로 확대하지 않는다. 모델 가중치 복사·다운로드와 새 모델 runtime 설치는0이었다.

새 설치 대상과 새 home을 작업 디렉터리 안에 만들고 기존 경로 미존재를 확인한 뒤 설치 엔진을 실행했다. 설치 엔진 호출에는 공개 build Python을 사용했으므로 사용자 GUI 설치 경로 선택을 검증했다고 표현하지 않는다. 설치된 `AiManager.exe`는 PYTHONHOME/PYTHONPATH를 제거하고 자식 PATH에서 사용자 Python을 제외한 환경에서 실제 WebView2 독립 창으로 실행했다. frozen 자체 검사·설치 내부 module 경로·설치본 `python310.dll`을 확인했고 정상 닫기/같은 home 재시작을 수행했다. 앱 호스트의 Python 별도 설치 불필요와 모델 worker의 지정 기존 Python/runtime 요구는 구분한다. sys.path 전체를 직접 관찰했다고 주장하지 않는다.

설치 payload 8,310개의 전량 SHA와 추가·누락0을 설치 직후, 실제 두 TTS 뒤, CPU 중단 복구 뒤 각각 새로 확인했다. 후보 1의 설치나 selfcheck를 이 결과로 대체하지 않았다.

## 실제 두 TTS의 같은 batch 부분 재개

새 입력·plan·batch·run과 새 home을 사용했다. 지정 Qwen3-TTS 0.6B/1.7B CustomVoice 자산과 runtime을 읽기 바인딩하고 이번 batch에서 모델25파일의 전체 SHA를 확인했다. 과거 WAV·로그·스크린샷·캐시 출력을 입력이나 성공 근거로 사용하지 않았다.

고정 plan의 실제 순서는 0.6B→1.7B였다. 정상 API로 승인/시작1회 후 첫 case 진행을 확인하고 `현재 작업은 완료한 뒤 일시중지` 요청1회를 보냈다. 첫 TTS가 새 WAV와 receipt를 완료한 checkpoint에서 다음 case dispatch0·정확 Job 부재를 확인했다. 첫 case의 input/request/result/output/receipt 다섯 파일 SHA와 file identity·수정 시각을 보존했다. 별도 API를 사용한 시작/일시중지와 native UI에서 확인한 재개 조작을 구분한다.

독립 창을 정상 종료하고 같은 새 home으로 다시 실행한 뒤 native UI에서 같은 이력을 선택하고 명시 재개 확인→새 일회 승인→재개 시작을 수행했다. 완료한 첫 case를 다시 실행하지 않고 미시작 1.7B만 첫 attempt1·새 run으로 실행했다. 두 receipt의 input/request/result/output SHA·WAV decode·현재 code/runtime/자산 scope와 정확 Job 부재를 대조했다. 첫 다섯 파일은 재개 전후 동일했다.

최종 DB는 시작1·일시중지1·재개 grant 소비1·모델 dispatch2·각 case attempt1을 기록했다. 원래 plan expiry는 바뀌지 않았고 누적 read_bytes는 **7,027,008,920**, consumed_ms는 **473,791**이었다. 승인 상한 wall1,800초·worker600초·hash300초·모델 시도4·hash 예산14,037,211,648 bytes와 download/install0을 초기화하거나 임의 연장하지 않았다. 독립 검토자가 새 DB/receipt/파일과 event를 직접 읽어 같은 결과를 확인했다. 이는 두 지정 모델의 이번 로컬 흐름 검증이며 품질 우열·모든 모델 성공을 뜻하지 않는다.

## 별도 CPU 소유 owner 중단 복구

새 CPU 전용 home에서 설치본 raw code를 공개 base Python과 공개 build 의존성으로 import했다. `-B`와 bytecode 쓰기 금지를 적용했으며 frozen GUI의 CPU probe나 실제 GPU crash라고 표현하지 않는다. metadata-only 관찰·5초 CPU probe·wall300초·timeout10초의 새 plan을 사용했고 모델 실행0이었다.

새로 실행한 전용 owner 한 개만 외부 `TerminateProcess`로 한 번 중단했다. 정확 process handle의 image·creation FILETIME·Popen PID·script/home과 현재 child identity·owned Job을 증거 기록 후 종료 직전에 다시 대조했다. 기존 설치 앱·다른 프로세스·GPU worker 종료0, 다른 종료 방법·자동 재시도0이다. owner/원래 child identity 부재와 정확 Job 부재를 확인한 뒤 같은 batch를 interrupted attempt1로 복구하고, 새 명시 일회 grant로 attempt2·서로 다른 run을 실행해 `control_validated`를 확인했다. 첫 attempt 이력과 원래 expiry·누적 read/wall은 보존됐다. 최종 read_bytes4,201,548·consumed_ms5,951이며 독립 검토에서 원장을 다시 대조했다.

## 기존 자료 보존과 확인 한계

지정 기존 두 home의 선정 파일11개 SHA/file identity, 읽기 전용 SQLite 세 파일의 행수, 지정 모델25파일의 metadata를 이번 검증 전후 새로 수집했다. 저장된 전후 JSON은 동일했다. 사후 수집 helper가 메모리 tuple과 JSON list를 직접 비교해 assertion을 한 번 냈으나, 두 저장 snapshot을 동일 JSON 방식으로 비교하여 차이0을 확인하고 그 오류와 재대조를 별도로 기록했다. 원본이나 사후 증거를 덮어쓰지 않았다. 이 한정 대조를 기존 home 전체 불변 주장으로 확대하지 않는다. 인증 토큰·state·개인 DB·기존 output을 fresh home으로 복사하지 않았다.

fresh OAuth 로그인·실 Drive 재수집, 별도 PC/Windows 환경, 나머지 네 고정 프로필·모든 모델·모든 화면 폭·전면 접근성·스크린리더, 장시간 stress, 정전 내구성, 실제 GPU/frozen GUI 강제 crash와 음성 품질 우열은 미검증이다. Google 로그인·동의는 사용자 직접행위이며 이번 로컬 모델 검증에 불필요한 인증을 요구하지 않았다. 서명 구매·OS/브라우저 보안 변경·Drive 쓰기·원격 비용·다른 모델 다운로드는 수행하지 않았다.

## 후보 2 수리 당시 checkpoint

후보 1 소스 `5fb2704bab6fa6a544eba36e1d0561de8816f46f`의 ZIP/frozen 자체 검사·격리 설치 엔진·설치본 전량 SHA·독립 창 시작/새 지정 설정 적용/정상 닫기까지 확인했다. 사용자 PATH에서 Python 경로를 제거한 실행에서 설치본의 `python310.dll`을 관찰했다. 설치 엔진은 공개 build Python에서 호출했으므로 GUI 설치 경로 선택 완료로 표현하지 않는다. 이 후보는 아직 실제 모델·강제 중단 검증을 시작하지 않았다.

그 뒤 독립 검토에서 승인 소비 직후 pending commit→coordinator claim 이전 owner 종료 시 복구할 수 없는 P1을 발견했다. 후보 1 ZIP·설치·증거는 보존하고 최종 후보 성공 근거로 대체하지 않는다. 후보 2는 최신 소비 owner의 PID+creation identity를 기록하여 살아 있는 정상 handoff는 거부하고 orphan pending만 명시 복구하며, resume 소비 직후 동일 중단도 이미 배정한 attempt를 유지한다. UI는 pending에서도 복구 확인을 제공한다. 새 네 반례를 포함한 focused 44개는 15.530초에 모두 PASS했다. 독립 검토의 같은 44개도 16.431초에 모두 PASS했다. 최종 전체 회귀는 **381개 중 374 PASS·7 SKIP·실패0**, 53.677초이며 code/static SHA는 `f2a15a5290696fc4ef0fa080595a9ff5229a73ed22e02bf1b6932a56bf18c386`다. 일곱 SKIP은 tracking CPU 의존성 부재 4개, tracking decode 의존성 부재 2개, OS가 일반 사용자 symlink 생성을 허용하지 않는 1개다. 이 환경에 해당 추가 모델 의존성을 설치하지 않았다. 후보 2의 새 clean build/설치/실제 실행·Release gate는 후속 이번 증거로 별도 확정한다.

기준 소스는 M14 main `090b68dedbf5ee461448ebe096f2d4240f2bd81c`다. 새 checkout을 초기 `core.autocrlf=false`로 확보하고 추적 파일 186개의 raw Git blob 일치/불일치0을 먼저 확인했다. 같은 프로젝트 코드·문서 후속 변경과 지정 모델/config·공식 공개 런타임을 사용한다. 과거 WAV/로그/스크린샷/배포물은 이번 성공 증거로 재사용하지 않는다.

## 구현과 검토

[M15 계약](M15_CONTRACT.md)의 명시 일회 재개 grant·append-only 시도 예약/events·누적 예산·완료 receipt/input/output 재검증·named Job 관찰·source/runtime/code stale 거부를 구현했다. UI/API/CLI와 0.15.0 Windows package version·설치 안내·SOURCE-PROVENANCE·frozen import/raw source 비교를 연결했다.

독립 중간 반례에서 CPU 성공 기록의 drain 순서, 완료 input binding, 현재 attempt의 dispatch 한정, 원장 유실, 재개 중 새 취소 경합, static 하위 디렉터리를 파일로 보는 오류를 발견하고 수리했다. 빌드 입력의 untracked code와 Git source commit 불일치도 clean tree gate로 거부한다. 검토 완료/GO는 최종 후보에서 별도로 기록한다.

## 초기 검증 이력

- 새 격리 build 환경에 저장소 고정 desktop 의존성을 설치했다. 전역 Python·보안 설정은 변경하지 않았다.
- 초기 host Python은 requests가 없어 import 4 ERROR였으며 성공으로 계산하지 않았다. 새 환경에서 기존 validation 범위 83개/82 PASS·1 SKIP를 확인했다.
- 이후 package code guard의 static 디렉터리 오판으로 실패한 진단을 보존하고 수리했다. 현재 validation 92개/91 PASS·1 SKIP, 실패0을 확인했다. 추가된 9개는 명시 승인·새 attempt·동일 batch·terminal/pending 보존·source/code stale·원래 만료·원장 유실·취소 경합·불명/live Job·세 번째 attempt 거부를 포함한다.
- 후보 1 동결 code/static에서 전체 회귀 **377개 중 370 PASS·7 SKIP·실패0**, 50.320초를 확인했다. 위 후보 2 회귀와 구분한다. 새 M15 recovery 12개와 package binding 2개를 포함했다. 직전 전체 회귀의 1 FAIL은 ContractError 상세 사유를 일반 ValueError 처리에서 덮는 오류였고, 별도 재전파로 수리한 결과와 구분한다. 기존 7 SKIP의 실제 사유는 tracking CPU 4개·tracking decode 2개의 격리 의존성 부재 및 symlink 생성 권한 1개이며 전부 symlink 제한으로 기록했던 문구를 바로잡았다.
- 독립 검토자는 별도 새 검토 경로에서 recovery/package/control 40개를 새로 실행해 **40 PASS**, 14.562초와 현재 소스의 blocking finding 없음을 보고했다. clean source commit과 동일 code/static이라는 조건으로 package build 검토를 권고했으며, 실제 GPU/설치/UI/Release GO와 구분한다.
- 최종 frontend TypeScript 검사와 production build를 통과했다. 당시 최종 package/frozen/selfcheck·실설치·새 GPU/중단 복구 결과는 미기록이었다. CRLF를 포함하는 원본 파일을 불필요하게 정규화하지 않고 `git -c core.whitespace=cr-at-eol diff --cached --check`로 실제 공백 오류0을 확인했다.

## 초기 계획과 남은 공개 gate

위 초기 계획의 설치·native UI·지정 두 모델의 부분 재개·별도 CPU 소유 중단은 이번 새 증거와 독립 검토로 확인했다. CPU 독립 검토는 attempt1 interrupted 이력→grant1 소비→attempt2의 서로 다른 run·Job 부재·모델 dispatch0·원래 expiry와 read2,104,396→4,201,548·wall440→5,951의 누적 보존을 다시 확인했다. 보존 파일 현재 SHA/identity와 설치 사후 전량 SHA도 독립 재대조했다. 남은 공개 gate는 이 문서의 정확 변경 집합 게시와 위 고정 source를 대상으로 한 새 태그/Release·ZIP 첨부·원격 readback이다. 실제 source/runtime/model/receipt/hash·실행 ID는 비공개 출처 기록에 연결하고 공개 저장소에는 개인 계정·Drive ID·실제 경로·자격 증명·개인 로그·출력을 포함하지 않는다. 기존 설치·모델·인증·DB·Release/assets는 보존한다. fresh OAuth·다른 모델·모든 환경/품질을 이번 일부 성공으로 대체하지 않는다.
