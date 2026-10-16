# M5 두 모델 새 A/B 비교 보고서

갱신일: 2026-10-17 (Asia/Seoul) · 버전: v0.5.0 · 판정: 구현·핵심 A/B GPU 실행·재생·부분 취소 검증 완료, 최초 A 브라우저 저장 확인·후속 A/B 다운로드 차단 원인 미해결. M5 전체 PASS 또는 모든 검증 완료로 판정하지 않는다. 실제 실행의 원시 시각은 비공개 출처 기록에 그대로 보존한다.

## 승인과 허용 자산

사용자는 같은 계열 두 TTS 모델의 동일한 새 한국어 입력 A/B 비교 구현·실제 검증·문서·비식별 저장소 반영을 명시 승인했다. 같은 범위의 설치·읽기 전용 모델 다운로드·필수 공식 config 보완·수정·로컬 실행·검증·게시에는 반복 승인을 요구하지 않는다. M6 이후·다른 모델 계열·원격 GPU·Drive 쓰기·작업공간 커스텀은 범위에 포함하지 않는다.

| 자산 | 고정 출처·용도 | 현재 확인 상태 |
|---|---|---|
| Qwen3-TTS 0.6B CustomVoice | 공식 revision `85e237c12c027371202489a0ec509ded67b5e4b5`, 지정 모델 13개 파일·2,498,388,392 bytes | 동일 프로젝트의 허용 모델 자산. M5 매 추론에서 바이트 해시를 새로 확인하며 M4 성공 기록을 새 검증으로 대체하지 않음 |
| Qwen3-TTS 1.7B CustomVoice | 공식 revision `0c0e3051f131929182e2c023b9537f8b1c68adfe`, 지정 Drive 모델 가중치·필수 구성요소 | 준비 UI의 읽기 전용 다운로드 완료. 12개 파일·4,520,217,432 bytes의 정확한 파일 집합·원시 SHA-256 독립 검증 PASS. 실제 로딩·새 한국어 추론 PASS |
| 필수 speech tokenizer config | 같은 1.7B revision의 공식 `speech_tokenizer/config.json`, 2,336 bytes | 지정 Drive 파일의 빈 바이트를 보존하고 별도 보완. SHA-256 `ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167` 고정; 다른 가중치의 외부 대체 없음 |
| 공개 런타임 | Python 3.10.11, qwen-tts 0.1.1, torch 2.9.1+cu128, transformers 4.57.3, RTX 3070 8 GiB | 새 환경 probe와 두 모델 실제 로딩·새 추론 PASS; 이번 입력·표본의 확인이며 모든 입력의 자원 요구를 보장하지 않음 |

공식 출처는 [0.6B 모델](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/85e237c12c027371202489a0ec509ded67b5e4b5), [1.7B 모델](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/tree/0c0e3051f131929182e2c023b9537f8b1c68adfe), [Qwen3-TTS 공식 라이브러리](https://github.com/QwenLM/Qwen3-TTS)다. 모델 manifest의 파일별 출처·크기·SHA-256과 비공개 준비 기록을 연결한다. 실제 계정·Drive ID·로컬 절대경로는 공개하지 않는다.

## 구현과 측정 계약

비교마다 새 comparison_id와 두 run_id를 만들고 동일한 새 한국어 입력·seed·공통 생성 조건을 연결한다. Korean / Sohee / batch 1, instruct 제외, 최대 300자·600초·1,024개 신규 토큰 조건이다. GPU 작업은 한 번에 1개이며 각 모델을 콜드 순차 실행하고 실행 순서를 기록한다. 모델당 표본은 1회이므로 결과를 일반적인 성능 순위로 해석하지 않는다.

공통 sampling 9개 항목은 `do_sample=true`, `top_k=50`, `top_p=1.0`, `temperature=0.9`, `repetition_penalty=1.05`, `subtalker_dosample=true`, `subtalker_top_k=50`, `subtalker_top_p=1.0`, `subtalker_temperature=0.9`다. 입력 해시·seed·조건·모델 revision·소스·런타임·WAV 해시가 두 새 실행과 연결되어야 한다. 한쪽 실패는 부분 완료이며 자동 승자를 표시하지 않는다. 사용자 평가는 두 모델 모두 성공한 경우에만 저장한다.

`total_seconds`는 worker controller가 해당 실행 처리를 시작한 이후의 준비·해시 검사 시간을 포함하고 큐 대기는 제외하는 범위다. 최종 `_execute` 코드와 실제 기록으로 확인했다. 종료·파일 검증·하위 프로세스 정리도 전체 처리 시간에 포함된다. 모델 로딩·추론 시간과 오디오 길이·PyTorch peak GPU allocated memory는 각 새 실행의 측정 범위를 표시한다. PyTorch peak allocated는 전체 장치 VRAM이나 다른 프로세스의 사용량을 포함하지 않는다. 사람의 청취·발음·내용 정확도와 파일 검증은 별개다.

## M5 핵심 검증 이력과 현재 다운로드 상태

123개 회귀·최종 UI·wheel은 앞선 동일 M5 구현의 검증 이력이다. 이번 후속 갱신은 기존 기록 진단과 별도 6개 mock 테스트이며, 이전 123개 테스트·GPU 실행·wheel을 새로 수행한 것으로 표시하지 않는다.

| 항목 | 확인 상태 | 확인 범위·한계 |
|---|---|---|
| 최종 자동 회귀·독립 반례 | 실행 코드 회귀·독립 반례 123개 PASS·18.59초 | 회귀 실행 당시 코드·테스트·frontend 33개 파일 전후 SHA-256 일치. 이후 UI 출처 표시 문구만 수정했고 실행 코드 5개는 유지. 최종 UI는 새 빌드·DOM 검증으로 별도 확인. 이전 단발 socket 10053 원인은 미확정 |
| 비교 등록 저장 실패·모델 바인딩 | BLOCK 수정 후 독립 검증 PASS | admitted commit barrier·eligible scheduler로 저장 실패의 미등록 작업 실행 차단. 실제 CPU worker 0개·재시작 interrupted 확인. model ID/name/revision 변조 6개 반례 차단 |
| 최종 UI 빌드·의존성·대표 폭 | TypeScript 포함 빌드 PASS·npm 전체 audit 0·최신 번들 정상/부분 완료 독립 검토 PASS | 768/1280/1440/1920에서 가로 넘침 0·사이드바 top 0, 정상 audio 2·부분 audio 1·평가 차단·Tab 포커스 3px. reduced motion 초기 검토 PASS·최종 1440 화면 시각 검토 양호 |
| 1.7B 준비 | 실제 UI 다운로드·12개 파일 전량 크기·정확한 집합·원시 SHA-256 독립 검증 PASS | 준비 ID `410b980f87f3414bbe2a054b9daf22aa`. 필수 config 2,336 bytes 공식 pin 일치·Drive 원본 보존. 실제 두 번째 모델 로딩·새 추론도 PASS |
| 실제 새 A/B 생성 | PASS | 동일한 새 20자 한국어 입력·seed·공통 조건, A→B 콜드 순차 실행·새 두 WAV·출처/해시 연결 |
| 비교 브라우저 재생·평가 | PASS | 두 native audio ended·error 없음·길이 도달·상호 배타 재생 확인. undecided 평가·기능 검증용 메모 저장/재조회 PASS; 사람의 품질 평가 아님 |
| 실제 부분 취소 | PASS | 새 비교 A 성공·B running 중 UI 취소→partial. A 오디오 보존·B 파일/출력/오디오 없음·API 409·평가 비활성·worker 0·active 없음 |
| 최초 A 브라우저 저장 기록 | 확인 | 이번 M5의 기존 다운로드 파일 207,404 bytes가 원본 A WAV SHA-256과 일치. Chrome 기존 이력 complete·interrupt 0·danger 0과 연결. 새 다운로드 E2E 재실행은 아님 |
| 후속 A/B 브라우저 다운로드 | BLOCK·원인 미해결 | 두 후속 기록은 state 4·interrupt 11 FILE_BLOCKED·danger 4 MAYBE_DANGEROUS_CONTENT·0 bytes. 최초 A 저장 성공과 후속 차단을 별개로 기록 |
| 배포용 wheel | 최종 UI 포함 새 v0.5.0 wheel PASS | 새 staging에서 빌드한 19개 package 파일이 현재 소스·두 manifest·최종 UI 번들과 원시 SHA-256 일치. 빌드 전후 현재 파일 불변·오래된 static 없음 |
| 공개 대상 검토 | PASS | M5 최초 게시 20개 파일의 원문 대조·비변경 blob 보존 완료. 이번 후속 갱신도 확정 whitelist의 원격 고정 커밋 UTF-8 원문 대조·비변경 blob 보존·삭제 0 절차 적용 |

최종 GPU 검증 소스는 inference SHA-256 `c879355fa05f55f97660ef3a5e64fcfa2f2ad5b151665f5bce2b7fbe8919cfe8`, worker SHA-256 `f861269a1c0ac58efa2e5a9b468cf641642c55ce12a5c36b65cf3c61f6adf059`에 연결한다. 마지막 UI 표시 수정은 모델 실행 소스를 바꾸지 않는다. 최종 새 wheel은 138,473 bytes이며 SHA-256은 `2d7e9e4fc9d61b0f3fb77c028cdcb0717ab375f909b21640af9e067ca8c35a13`다. 새 staging의 출처·빌드·19개 원시 파일 대조 기록은 `<private_app>/m5-final-wheel-eaca08f706fb43d984e98c99107ea974/`에 보존한다. 이전 wheel을 재사용하지 않았다. 공개 저장소에는 wheel·생성 UI 번들 자체를 넣지 않는다.

## 실제 새 정상 비교

비교 ID는 `84d616dd0e0249a1ae79e0de2d15e410`다. 입력 전문은 비공개에 보관하고 새 한국어 20자 입력의 SHA-256 `d65b1066a6327fb433e1a34762248f7c11d053b8253170c463ae5fef3a34e6e4`만 공개한다. 공통 seed는 `36440264`이며 실행 순서는 A 0.6B 다음 B 1.7B다. 각 모델 표본 1회의 콜드 실행이다.

| 측정 | A: 0.6B | B: 1.7B |
|---|---|---|
| 새 run_id | `44994904d13149c8b135de83c5f9367e` | `a5c3e30d42154844bab8178a1138981c` |
| 모델 로딩 | 6.156초 | 9.453초 |
| 추론 | 55.187초 | 45.938초 |
| 전체 처리(큐 대기 제외) | 92.500초 | 75.406초 |
| PyTorch peak allocated | 2,299,809,792 bytes | 4,289,589,248 bytes |
| 새 WAV 길이 | 4.32초 | 3.28초 |
| 새 WAV 크기 | 207,404 bytes | 157,484 bytes |
| WAV SHA-256 | `6e6938e0c2eb5ceea6394a4fbbb72deb68d75f8ce958cd6a5dec06481f96a0d8` | `443376fc599adb0de1aed293ba8c764166fb517b62df91e62ab6b0b0ee3d4aa2` |

두 WAV 모두 PCM16·mono·24 kHz·clipping 0을 확인했다. 로컬 파일·state·worker·API 응답의 바이트 해시가 일치하고 현재 5개 실행 코드·provenance·모델 13/12개 바이트·런타임 lock·cold/offline·실제 순차 실행 연결을 확인했다. native audio는 두 파일 모두 길이 끝까지 진행하고 ended=true·error 없음이며 한쪽 재생 시 다른 쪽이 멈춘다. 사용자 평가 undecided와 기능 검증용 메모의 저장·재조회도 확인했다. 이것은 청취 품질 판단이나 자동 승자 선정이 아니다.

출력 길이가 서로 다르며 표본이 1회뿐이다. 측정값을 모델 전반의 속도·품질 순위나 다른 문장의 VRAM 상한으로 해석하지 않는다. 사람의 발음·내용 정확도·자연스러움 평가, ASR 검증, 실제 GPU OOM·300자 전 범위·장시간 반복은 수행하지 않았다.

## 실제 새 부분 취소

별도의 새 20자 입력과 seed `4206902751`로 비교 `edd7b82e0adc4292af223fa7e37736de`를 생성했다. A `c937a57e430e469c8eddc21b95a09ecc`는 succeeded이며 새 WAV 3.84초·184,364 bytes, SHA-256 `003c18d8736a06703926cb7d647b3d411e357a2a95c767b1ebe58f84061a5f62`다. B `3e7a045e2ce34bbbbf75d0668812a2c4`가 running인 동안 UI에서 취소했고 비교가 partial로 종료했다.

A 성공 오디오를 보존하고 B는 WAV 파일·성공 output·audio URL이 없으며 오디오 요청은 409다. 부분 완료에서는 평가가 비활성이다. 두 worker가 종료되고 active가 없음을 독립 확인했다. 정상 비교의 결과를 이 부분 취소 입력이나 출력으로 재사용하지 않았다.

## 브라우저 다운로드 기존 기록 진단과 정정

2026-10-17 읽기 전용 후속 진단에서 최초 A 다운로드가 실제 완료됐음을 확인했다. 기존 파일은 207,404 bytes이고 SHA-256 `6e6938e0c2eb5ceea6394a4fbbb72deb68d75f8ce958cd6a5dec06481f96a0d8`로 이번 정상 비교 A 원본과 일치한다. Chrome 기존 다운로드 이력도 complete(state 1)·interrupt 0·danger 0으로 확인됐다. 사용자는 별도의 직접 클릭을 하지 않았다고 확인했다. 따라서 이전 보고의 브라우저 저장 완료 미확인 판정을 **최초 A 저장 완료 확인**으로 정정한다.

후속 A/B 두 기록은 state 4·interrupt 11(`FILE_BLOCKED`)·danger 4(`MAYBE_DANGEROUS_CONTENT`)·0 bytes다. 사용자가 첨부한 조직에서 차단함 표시와 함께 후속 차단 상태를 보존한다. 이 결과는 같은 M5 실행의 기존 파일·기록 진단이며 새 다운로드 E2E PASS나 새 비교 결과가 아니다. 최초 A 성공만으로 B 저장·후속 다운로드·원인 해결 또는 M5 전체 PASS를 주장하지 않는다. 기존 파일·기록은 보존하고 새 모델 입력·성능 측정으로 사용하지 않았다.

최초 완료 기록은 약 54.8초이며 자동검증의 바깥 CUA 호출은 30.0595초에 timeout·kernel reset으로 끝났다. 내부 `downloadMedia`는 별도 timeout 인수 없이 기본 120초 대기 조건이었다. 따라서 바깥 호출 timeout과 실제 다운로드 완료 시점의 어긋남이 관찰된다. 정확한 도구 시계와 브라우저 시계를 대조하지 않았으므로 인과관계나 정확한 동일 타임라인을 확정하지 않는다. timeout 실패를 브라우저 저장 실패와 동일시하지 않는다.

정책 화면에 DownloadRestrictions 등 정책이 없다는 사용자 확인, 관련 로컬 레지스트리 키 부재, Defender 보호 기록 부재, 빈 관리 화면만으로 모든 차단 원인을 배제하지 않는다. 확장 프로그램은 활성화되어 있으나 개별 확장이 원인이라고 확정하지 않는다. 보안 분류·브라우저/자동화 환경·다른 차단 경로의 원인은 미확정이다. `FILE_BLOCKED` 및 danger 값은 관찰된 분류이며 실제 악성 파일 판정의 근거로 확대하지 않는다.

공식 Chromium `155.0.8059.80` 소스도 읽기 전용으로 대조했다. [DownloadItemImpl의 target interrupt 처리](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.80/components/download/internal/common/download_item_impl.cc#1845)는 위험 분류를 갱신하기 전에 반환할 수 있으므로 DB danger 4가 초기 상태로 남았을 가능성이 있다. 이 숫자만으로 Safe Browsing·악성 콘텐츠 원인을 판정하지 않는다. [다운로드 delegate](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.80/chrome/browser/download/chrome_download_manager_delegate.cc#2267)는 정책 차단에도 FILE_BLOCKED를 사용한다. [insecure download 처리](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.80/chrome/browser/download/insecure_download_blocking.cc#275)는 localhost를 제외하므로 localhost HTTP라는 사실만으로 불안전 다운로드 차단 원인을 확정하지 않는다. 이는 가능한 코드 경로의 구분이며 이번 원인이 해당 경로였다는 실행 증거는 아니다. 같은 버전의 [DevTools 다운로드 delegate](https://chromium.googlesource.com/chromium/src/+/refs/tags/155.0.8059.80/content/browser/devtools/protocol/devtools_download_manager_delegate.cc#101)는 deny 경로에서 USER_CANCELED를 사용하며 이번 FILE_BLOCKED와 달라 이를 원인으로 확정하지 않는다. 검토한 확장 다운로드 API와 다운로드 limiter 파일에서는 직접 FILE_BLOCKED를 만드는 경로를 찾지 못했지만 확장 전체 동작이나 외부 보안 경로를 배제한 것은 아니다. 당시 target 결정·security callback 로그가 보존되지 않아 현재 승인된 읽기 전용 조사 범위에서 근본 원인을 확정할 수 없다.

사용자는 자동검증 timeout 수정과 새 발견의 문서·저장소 반영, 추가 다운로드 없이 원인을 조사하는 범위를 승인했다. 이후 조사는 기존 기록만 읽고 추가 다운로드 재시도·다른 도구로 파일 저장·파일명 변경 우회·보안 설정 변경 없이 진행한다. timeout 수정의 자체 검증과 기존 브라우저 기록 진단을 분리하며 신규 브라우저 다운로드 검증은 수행하지 않는다.

이번 정상·부분 취소 증거는 해당 기능 검증에만 사용한다. M4 WAV·로그·측정값을 현재 비교 성공 근거로 사용하지 않았다. **구현·핵심 A/B GPU 실행·재생·부분 취소와 최초 A 저장을 확인했으며, 후속 A/B 다운로드 차단 원인은 미해결이다. M5 전체 PASS나 모든 기능 검증 완료로 단정하지 않는다.** M6 이후는 미승인이다.

## 자동검증 timeout 수정과 검증 범위

기존 자동검증 호출은 저장소의 앱 코드가 아닌 채팅 CUA 호출이었다. 이번 수정은 production 앱을 바꾸지 않고 새 오프라인 헬퍼 `scripts/download_validation.mjs`, 모의 테스트 `tests/download_validation.test.mjs`, [호출 계약 안내](DOWNLOAD_VALIDATION.md)를 추가한 것이다. 내부 `downloadMedia` 제한 120,000ms·외부 CUA `timeout_ms` 150,000ms를 명시하고 최소 30초 여유를 둔다. A/B는 각각 별도 단일 호출이며 기본값은 실행 차단이다. 현재 브라우저 adapter와 연결되지 않은 오프라인 호출 구성이다. 30초 여유는 호출 예산이며 브라우저 대화상자·사용자 확인 대기 시간을 보장하지 않는다.

영속 ledger의 in_flight를 동작 전에 저장하고 timeout·도구 오류·응답 누락 후 결과를 indeterminate로 기록한다. 같은 세션에서 A 재클릭과 B 진행을 중단하며 경로 반환만으로 무결성 PASS를 선언하지 않는다. 이번 6개 오프라인 mock 테스트는 이 계약만 검증했다. CUA의 150,000ms 인자 수용은 단순 출력으로만 확인했으며 150초 지속 실행·브라우저 동작·다운로드·GPU 실행은 수행하지 않았다. 이것은 추가 다운로드 권한이나 Chrome 차단 해결의 근거가 아니다.

## 보존·재사용·공개 범위

허용 모델·공개 라이브러리·동일 프로젝트의 코드·문서만 후속 갱신에 사용한다. 새 입력·run_id·comparison_id·고유 출력 디렉터리·새 로그·새 검증 결과를 생성한다. 이전 WAV·결과 캐시·다른 프로젝트의 코드나 산출물을 입력으로 연결하지 않는다. 기존 Drive 원본·중간 실패 기록은 보존한다.

확인 범위는 두 정상 실행과 새 부분 취소의 입력 계약·모델 준비·출처·출력·현재 코드/런타임 연결, 공개 whitelist다. 다른 프로젝트 전체나 전 디스크를 감사한 것은 아니므로 전체 과거 프로젝트의 재사용 부재를 단정하지 않는다. 공개 저장소에는 소스·테스트·lock·manifest·문서 whitelist만 반영하며 개인 계정·Drive ID·인벤토리·실제 절대경로·자격 증명·입력·WAV·스크린샷·로그를 제외한다. 상위 작업공간 AGENTS.md 승인 상태 변경은 로컬에만 남긴다.
