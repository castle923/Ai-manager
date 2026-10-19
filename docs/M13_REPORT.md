# M13 구현·실행 보고

기준: 2026-10-19. M12 공개 main `ba5f53a9aebfaafa0ce5ba9db282b2864bdf5adc`에서 새 checkout·새 검증 디렉터리로 시작했다. 이번 결과는 **source-only 검수 workflow 연결과 확인한 Windows 환경의 4프로필 실제 성공**이다. 6프로필 모두 실제 성공·새 UI·새 배포 완료는 아니다. [M13 계약과 CLI](M13_CONTRACT.md)를 따른다.

## 구현

새 모델 bridge·고정 환경 probe·합성 영상 fixture를 추가하고 기존 intake/store/coordinator/CLI에 새 `run_models` 승인 action을 연결했다. 명시1–6개 로컬 root의 하나의 batch, metadata anchor 제한 파싱, manifest 전체 SHA, runtime raw binding·lock EOL-only 동치, 현재 환경/자원 gate, 새 입력·TTS→STT 계보, 기존 고정 worker, 독립 출력 계약과 actual receipt를 연결한다. M12 제어/CPU 승인은 모델 권한으로 바꾸지 않는다.

같은 명시 app-home의 slot은 조정기만 한 번 소유하고 worker는 직접 실행한다. Windows Job의 실제 active0을 확인한 후 다음 case를 발행한다. 기존 image/LLM live RSS/RAM guard·worker output 계약을 유지한다. 새 install/download/Drive 쓰기·cloud 권한은 0이다. 기존 API·대시보드·release 자산·기존 원본/인증/DB를 갱신하는 단계가 아니다.

## 이번 실제 실행

새 batch `bf6e5d146f654f81b5e5620b8bed9272`, plan `ab0a906a96234e85aed02eb0a5436ba8`을 새 local CLI 확인 승인으로 한 번 소비했다. wall1800초, worker/hash 각각300초, model attempts≤5, full-hash 계획 상한24,929,657,972bytes였다. 새 모델 batch의 실제 처리 시간은 약222.449초이며 성능 benchmark로 해석하지 않는다.

| 프로필 | 이번 실제 판정 | 이번 확인과 한계 |
|---|---|---|
| Qwen3-TTS 1.7B CustomVoice | succeeded | 12필수 파일4,520,217,432bytes 전체SHA, 새 한국어 입력·cold worker·독립WAV decode/신호/출력SHA·receipt |
| Qwen3-TTS 0.6B CustomVoice | succeeded | 13필수 파일2,498,388,392bytes 전체SHA, 같은 새 문장/조건·별도run·WAV/receipt |
| Whisper large-v3-turbo | succeeded | 11필수 파일1,622,443,339bytes 전체SHA, 같은batch 1.7B 새WAV→16kHz mono PCM16·전사JSON/TXT 계약/출력SHA |
| TAPIR | succeeded | checkpoint218,886,140bytes 전체SHA, 새8frame 합성MP4·정규화점·tracks/preview 계약/출력SHA |
| Llama 3.1 8B Instruct | deferred / resource_blocked | runtime/current resource probe 수행, 모델worker0·weight full-hash0·응답0. 현재freeVRAM이 보수적 앱 정책보다 작아 차단 |
| Qwen Image 2.1 | 운영 BLOCK / 실제batch 미포함 | 지정 현재 로컬 환경에 준비된 image runtime 부재. CPU 연결/출력 negative 계약과 실제 운영 성공을 구분. 설치/다운로드/다른환경 fallback0 |

실제로 읽고 전체 SHA를 맞춘 자산은 **4프로필37필수 파일·8,859,935,303bytes**다. 이는 모델/필수 config·tokenizer 구성요소이며 환경·전체 폴더·이전 결과의 byte 합계가 아니다. 각 profile revision은 고정 catalogue manifest와 같으며 metadata 이름 일치만으로 판정하지 않았다. 0.6B의 `.gitattributes`는 metadata scanner의 hidden 제외로 ‘관찰 안 됨’이었으나 full-hash 단계에서 실제 파일을 검증했다.

TTS 실제 run은 1.7B `fd20fd6b7e654159bdf6c9f8b217e08c`, 0.6B `3e94771d334946c6aefefb5557ccd7e6`다. 같은 새 입력 SHA와 조건이지만 개별 WAV와 cold 실행이다. Whisper run `5d7f7d14822d46628702820c39f69e82`의 원본은 같은 batch의 **1.7B 새WAV**이며 입력은72,960frames/4.56초/16kHz/mono/PCM16으로 새 변환했다. 과거 WAV·다른 batch 출력·침묵/noise fallback을 쓰지 않았다. TAPIR run은 `c35b3352ba3a49ea86e722a87701f560`이며 합성 표본의 구조 검사이지 실제 로봇 영상 성능 증거가 아니다.

Llama의 실제 관측은 freeVRAM7,459,569,664bytes·total8,589,279,232bytes, availableRAM18,235,805,696bytes, diskfree358,608,756,736bytes였다. 이 구현의 **최소freeVRAM18GiB라는 보수적 admission 정책**에서 차단됐으며 RAM3GiB·disk512MiB 조건은 통과했다. 18GiB를 공식 모델 최소VRAM으로 단정하거나 모든 Llama 실행이 불가능하다고 판단하지 않는다. 환경을 변경하거나 제한을 낮춰 실행하지 않았다.

## 검증과 독립 검토

- validation CPU suite: **79개 중78 PASS/1 SKIP**. 새 full-hash 전체바이트/변조·경로이탈·취소, runtime drift, EOL-only 동치·실제 raw SHA, anchor-only 관찰, 6프로필 종료코드만 성공/foreign run/NaN 출력 거절, 의존 입력·새 파일·source SHA 계보, 자원 차단·미지정 runtime dispatch0을 포함한다.
- 전체 CPU 회귀: **359개 중353 PASS/6 SKIP, failure0/error0**. 선택 기존 runtime에 webview가 없어 desktop dialog3개를 명시 skip한 새 harness를 사용했다. 나머지 skip은 선택한 CPU runtime의 tracking decode dependencies2개·OS의 비관리자 symlink1개다. 누락 의존성을 설치하지 않았으며 desktop dialog3개를 실행한 것으로 보고하지 않는다. 기존 전체 명령의 webview 오류와 최초 driver의 Windows multiprocessing/import 오류 로그는 private에 보존하고, 수정한 **검증 driver**의 최종 로그와 구분했다. 앱 구현 변경으로 이 오류를 숨기지 않았다.
- 새 clone의 기본 Windows EOL 변환이 공식 vendored TAPIR byte SHA와 충돌하는 것을 발견했다. 새 checkout에서 동일 HEAD의 원래 Git bytes를 복원하고 `.gitattributes`로 해당 vendor directory의 byte 보존을 선언했다. vendor 내용·manifest hash·공식 소스를 변경한 것이 아니다. TAPIR 계약9개 중7 PASS/2 decode 의존성 SKIP와 이번 실제 tracking 실행을 별도로 확인했다.
- 독립 검토자는 validation CPU suite와 full-hash synthetic negative, 실제 새 CPU child의 정상/timeout·Job active0을 별도로 확인했다. owner 실모델 실행 후에는 **4receipt의 출력 fullSHA·typed 계약·현재 code/runtime raw lock·모델manifest 항목·DB receipt SHA·소유PID/Jobactive0**을 다시 검사했다. 모델 가중치 전체를 독립으로 두 번째 해시하지 않았으며 owner의 이번 full-hash 기록과 고정 manifest 항목이 일치함을 확인한 범위다.
- 독립 검토자가 같은 batch의 새 sourceWAV 변환을 이번 새 임시 폴더에서 다시 계산해 Whisper 입력SHA·frames·duration을 일치 확인했다. 전체 출력을 읽어 본 검사와 음성 정확도/음질·이미지 미감·일반 추적 성능 평가는 구분한다.
- 종료 후 현재 원본scope metadata·runtime raw binding이 계획과 같고, 4출력계약/fullSHA와 DB receipt SHA·actual code가 그대로임을 새 readback으로 확인했다. 실제 실행 checkout의 raw code SHA는 `76e3f158708c38a38541b1eb55178cb296ac357a808b85285be227e9b5ba2c18`다. OS checkout EOL 차이를 포함한 private 파일별 raw hash manifest를 함께 보존한다.

## 출처·보존·잔여 범위

기존 허용 자산은 같은 Ai-manager의 지정 모델5개 원본·기존 profile runtime/Python·고정 공식 manifest·기존 공개 라이브러리다. 새로 만든 것은 이번 구현·tests·새metadata/plan/approval/store·입력/MP4/WAV/전사/tracks/preview·receipt·현재 검증 로그다. 개인 원본 경로·계정/Drive ID·로그·자격은 public source에 포함하지 않는다. private 실행 별칭은 `M13/verification-533bcda7d09b4bf2b2e8c8fdcf4838c3`이며 이전 준비차단/미소비plan은 별도 보존한다.

이번 source/runtime/input/output 경로와 새 receipt를 확인한 범위에서 다른 프로젝트 코드·과거 모델출력·과거 성공 로그가 새 입력/성공 근거로 연결되지 않았다. 전체 개인 디스크·기존 DB의 모든 byte를 전후 대조한 감사는 아니며 ‘모든 경로 재사용 없음’을 무제한 단정하지 않는다. 원본 모델·runtime·인증·DB·이전 자료를 삭제/이동하거나 보안·OS·브라우저 설정을 변경하지 않았다.

M13 source workflow와 확인 환경의4프로필 실제 검증을 구분해 완료 보고한다. 이미지 운영 환경·Llama 적합 자원 확보는 여전히 BLOCK이며 새 설치·다운로드·원격GPU·유료cloud는 자동 승인되지 않는다. M14 검수UI/종합표, M15 부분 재개·fresh release, 장시간 stress/실제GPU crash·모든환경·품질평가는 남는다. 이 단계는 v0.10.0 기존 태그/Release/ZIP을 변경하지 않는다.
