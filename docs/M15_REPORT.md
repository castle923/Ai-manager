# M15 구현·새 Windows 배포 검증 기록

상태: 구현·독립 검토·새 검증 진행 중. 실제 GPU/강제 중단/새 설치/Release 게시 완료 전이며 아래 결과를 그 범위로 확대하지 않는다.

기준 소스는 M14 main `090b68dedbf5ee461448ebe096f2d4240f2bd81c`다. 새 checkout을 초기 `core.autocrlf=false`로 확보하고 추적 파일 186개의 raw Git blob 일치/불일치0을 먼저 확인했다. 같은 프로젝트 코드·문서 후속 변경과 지정 모델/config·공식 공개 런타임을 사용한다. 과거 WAV/로그/스크린샷/배포물은 이번 성공 증거로 재사용하지 않는다.

## 구현과 검토

[M15 계약](M15_CONTRACT.md)의 명시 일회 재개 grant·append-only 시도 예약/events·누적 예산·완료 receipt/input/output 재검증·named Job 관찰·source/runtime/code stale 거부를 구현했다. UI/API/CLI와 0.15.0 Windows package version·설치 안내·SOURCE-PROVENANCE·frozen import/raw source 비교를 연결했다.

독립 중간 반례에서 CPU 성공 기록의 drain 순서, 완료 input binding, 현재 attempt의 dispatch 한정, 원장 유실, 재개 중 새 취소 경합, static 하위 디렉터리를 파일로 보는 오류를 발견하고 수리했다. 빌드 입력의 untracked code와 Git source commit 불일치도 clean tree gate로 거부한다. 검토 완료/GO는 최종 후보에서 별도로 기록한다.

## 이번 검증

- 새 격리 build 환경에 저장소 고정 desktop 의존성을 설치했다. 전역 Python·보안 설정은 변경하지 않았다.
- 초기 host Python은 requests가 없어 import 4 ERROR였으며 성공으로 계산하지 않았다. 새 환경에서 기존 validation 범위 83개/82 PASS·1 SKIP를 확인했다.
- 이후 package code guard의 static 디렉터리 오판으로 실패한 진단을 보존하고 수리했다. 현재 validation 92개/91 PASS·1 SKIP, 실패0을 확인했다. 추가된 9개는 명시 승인·새 attempt·동일 batch·terminal/pending 보존·source/code stale·원래 만료·원장 유실·취소 경합·불명/live Job·세 번째 attempt 거부를 포함한다.
- 최종 동결 code/static에서 전체 회귀 **377개 중 370 PASS·7 SKIP·실패0**, 50.320초를 확인했다. 7 SKIP은 기존 Windows symlink 권한 관련 제한이다. 새 M15 recovery 12개와 package binding 2개를 포함한다. 직전 전체 회귀의 1 FAIL은 ContractError 상세 사유를 일반 ValueError 처리에서 덮는 오류였고, 별도 재전파로 수리한 최종 결과와 구분한다.
- 독립 검토자는 별도 새 검토 경로에서 recovery/package/control 40개를 새로 실행해 **40 PASS**, 14.562초와 현재 소스의 blocking finding 없음을 보고했다. clean source commit과 동일 code/static이라는 조건으로 package build 검토를 권고했으며, 실제 GPU/설치/UI/Release GO와 구분한다.
- 최종 frontend TypeScript 검사와 production build를 통과했다. 최종 package/frozen/selfcheck·실설치·새 GPU/중단 복구 결과는 아직 미기록이다. CRLF를 포함하는 원본 파일을 불필요하게 정규화하지 않고 `git -c core.whitespace=cr-at-eol diff --cached --check`로 실제 공백 오류0을 확인했다.

## 남은 gate와 보존

최종 합성 반례·전체 회귀·frozen package 결속 독립 검토 뒤, 승인된 독립/부모 GO를 받아 이번에 새로 만든 격리 home/input/output에서 설치·native UI·새 지정 모델 검수·소유 중단·같은 batch 재개를 실제 검증한다. 실제 source/runtime/model/receipt/hash·실행 ID는 비공개 출처 기록에 연결하고 공개 저장소에는 개인 계정·Drive ID·실제 경로·자격 증명·개인 로그·출력을 포함하지 않는다. 기존 설치·모델·인증·DB·Release/assets는 보존한다. fresh OAuth·다른 모델·모든 환경/품질을 이번 일부 성공으로 대체하지 않는다.
