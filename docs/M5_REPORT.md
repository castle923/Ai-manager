# M5 두 모델 새 A/B 비교 보고서

갱신일: 2026-10-17 (Asia/Seoul) · 버전: v0.5.0 · 판정: 원계획의 승인된 M5 새 A/B 비교 기능 검증 완료(확인한 로컬 환경·정상 지원 Edge A/B 저장 경로 범위). Chrome의 차단 원인·별도 시도 종결은 미확정이며 선택 품질 평가와 M6는 별도다. 모든 브라우저·입력·장애·환경의 범용 성공을 보장하지 않는다.

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

123개 회귀·최종 UI·wheel은 앞선 동일 M5 구현의 검증 이력이다. 후속 갱신은 기존 기록 진단·별도 6개 timeout mock 테스트와 아래 서버 진단 코드의 4개 신규/3개 기존 서버 테스트로 구분한다. 이전 123개 테스트·GPU 실행·wheel을 새로 수행한 것으로 표시하지 않는다.

| 항목 | 확인 상태 | 확인 범위·한계 |
|---|---|---|
| 최종 자동 회귀·독립 반례 | 실행 코드 회귀·독립 반례 123개 PASS·18.59초 | 회귀 실행 당시 코드·테스트·frontend 33개 파일 전후 SHA-256 일치. 당시 후속 UI 출처 표시 수정까지 실행 코드 5개는 유지됐으나, 이후 아래 새 승인 범위의 서버 진단 로그 구현은 별도 변경이다. 최종 UI는 새 빌드·DOM 검증으로 별도 확인. 이전 단발 socket 10053 원인은 미확정 |
| 비교 등록 저장 실패·모델 바인딩 | BLOCK 수정 후 독립 검증 PASS | admitted commit barrier·eligible scheduler로 저장 실패의 미등록 작업 실행 차단. 실제 CPU worker 0개·재시작 interrupted 확인. model ID/name/revision 변조 6개 반례 차단 |
| 최종 UI 빌드·의존성·대표 폭 | TypeScript 포함 빌드 PASS·npm 전체 audit 0·최신 번들 정상/부분 완료 독립 검토 PASS | 768/1280/1440/1920에서 가로 넘침 0·사이드바 top 0, 정상 audio 2·부분 audio 1·평가 차단·Tab 포커스 3px. reduced motion 초기 검토 PASS·최종 1440 화면 시각 검토 양호 |
| 1.7B 준비 | 실제 UI 다운로드·12개 파일 전량 크기·정확한 집합·원시 SHA-256 독립 검증 PASS | 준비 ID `410b980f87f3414bbe2a054b9daf22aa`. 필수 config 2,336 bytes 공식 pin 일치·Drive 원본 보존. 실제 두 번째 모델 로딩·새 추론도 PASS |
| 실제 새 A/B 생성 | PASS | 동일한 새 20자 한국어 입력·seed·공통 조건, A→B 콜드 순차 실행·새 두 WAV·출처/해시 연결 |
| 비교 브라우저 재생·평가 | PASS | 두 native audio ended·error 없음·길이 도달·상호 배타 재생 확인. undecided 평가·기능 검증용 메모 저장/재조회 PASS; 사람의 품질 평가 아님 |
| 실제 부분 취소 | PASS | 새 비교 A 성공·B running 중 UI 취소→partial. A 오디오 보존·B 파일/출력/오디오 없음·API 409·평가 비활성·worker 0·active 없음 |
| 최초 A 브라우저 저장 기록 | 확인 | 이번 M5의 기존 다운로드 파일 207,404 bytes가 원본 A WAV SHA-256과 일치. Chrome 기존 이력 complete·interrupt 0·danger 0과 연결. 새 다운로드 E2E 재실행은 아님 |
| 당시 Chrome 후속 A/B 다운로드 | BLOCK·원인 미해결 | 두 후속 기록은 state 4·interrupt 11 FILE_BLOCKED·danger 4 MAYBE_DANGEROUS_CONTENT·0 bytes. 최초 A 저장 성공과 후속 차단을 별개로 기록 |
| 정상 지원 Edge A/B 저장 | PASS | A 207,404 bytes·B 157,484 bytes의 completed·지원 경로·실제 원본 SHA 일치·독립 서버/파일 검증. 각 명시 승인 1회 |
| 배포용 wheel | 최종 UI 포함 새 v0.5.0 wheel PASS | 새 staging에서 빌드한 당시 19개 package 파일이 빌드 시점 소스·두 manifest·최종 UI 번들과 원시 SHA-256 일치. 이후 서버 진단 코드 변경을 포함한 현재 wheel 검증을 뜻하지 않음 |
| 공개 대상 검토 | PASS | M5 최초 게시 20개 파일의 원문 대조·비변경 blob 보존 완료. 이번 진단 코드·문서 갱신도 확정 whitelist의 원격 고정 커밋 UTF-8 원문 대조·비변경 blob 보존·삭제 0 절차 적용 |

기존 실제 GPU 검증 시점의 소스는 inference SHA-256 `c879355fa05f55f97660ef3a5e64fcfa2f2ad5b151665f5bce2b7fbe8919cfe8`, worker SHA-256 `f861269a1c0ac58efa2e5a9b468cf641642c55ce12a5c36b65cf3c61f6adf059`에 연결한다. 당시 마지막 UI 표시 수정은 모델 실행 소스를 바꾸지 않았다. 이후 서버 진단 코드의 별도 변경과 구분한다. 당시 최종 새 wheel은 138,473 bytes이며 SHA-256은 `2d7e9e4fc9d61b0f3fb77c028cdcb0717ab375f909b21640af9e067ca8c35a13`다. 새 staging의 출처·빌드·19개 원시 파일 대조 기록은 `<private_app>/m5-final-wheel-eaca08f706fb43d984e98c99107ea974/`에 보존한다. 이전 wheel을 재사용하지 않았다. 공개 저장소에는 wheel·생성 UI 번들 자체를 넣지 않는다.

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

사용자는 자동검증 timeout 수정과 새 발견의 문서·저장소 반영, 추가 다운로드 없이 원인을 조사하는 범위를 승인했다. 앞선 읽기 전용 단계에서는 기존 기록만 읽고 추가 다운로드 재시도·다른 도구로 파일 저장·파일명 변경 우회·보안 설정 변경을 하지 않았다. timeout 수정의 자체 검증과 기존 브라우저 기록 진단을 분리했으며 당시 신규 브라우저 다운로드 검증은 수행하지 않았다. 이후 별도 승인된 한정 재현은 아래에 구분한다.

이번 정상·부분 취소 증거는 해당 기능 검증에만 사용한다. M4 WAV·로그·측정값을 현재 비교 성공 근거로 사용하지 않았다. **당시 판정:** 구현·핵심 A/B GPU 실행·재생·부분 취소와 최초 A 저장을 확인했지만 당시 후속 Chrome 차단은 미해결이어서 모든 기능 완료를 단정하지 않았다. 이후 Edge A/B 결과와 최종 완료 범위는 아래 잔여 표에서 별도 판정한다. M6 이후는 미승인이다.

## 자동검증 timeout 수정과 검증 범위

기존 자동검증 호출은 저장소의 앱 코드가 아닌 채팅 CUA 호출이었다. 이번 수정은 production 앱을 바꾸지 않고 새 오프라인 헬퍼 `scripts/download_validation.mjs`, 모의 테스트 `tests/download_validation.test.mjs`, [호출 계약 안내](DOWNLOAD_VALIDATION.md)를 추가한 것이다. 내부 `downloadMedia` 제한 120,000ms·외부 CUA `timeout_ms` 150,000ms를 명시하고 최소 30초 여유를 둔다. A/B는 각각 별도 단일 호출이며 기본값은 실행 차단이다. 현재 브라우저 adapter와 연결되지 않은 오프라인 호출 구성이다. 30초 여유는 호출 예산이며 브라우저 대화상자·사용자 확인 대기 시간을 보장하지 않는다.

영속 ledger의 in_flight를 동작 전에 저장하고 timeout·도구 오류·응답 누락 후 결과를 indeterminate로 기록한다. 같은 세션에서 A 재클릭과 B 진행을 중단하며 경로 반환만으로 무결성 PASS를 선언하지 않는다. 이번 6개 오프라인 mock 테스트는 이 계약만 검증했다. CUA의 150,000ms 인자 수용은 단순 출력으로만 확인했으며 150초 지속 실행·브라우저 동작·다운로드·GPU 실행은 수행하지 않았다. 이것은 추가 다운로드 권한이나 Chrome 차단 해결의 근거가 아니다.

## 로그 보강 전 1차 제한 재현

사용자는 앞선 읽기 전용 조사 후 보안 설정을 유지하고 원인 로그를 먼저 준비한 제한 다운로드 재현·검증·문서·저장소 반영을 별도로 승인했다. 이번 지정 진단에 한해 기존 추가 다운로드 중단 지시를 대체하며 자동 반복·다른 방식 저장·정책/보안/확장/CDP 설정 변경을 허용하지 않는다. 같은 M5 기존 WAV는 이 재현의 지정 원본으로만 사용하고 새 TTS 성공 근거로 사용하지 않는다.

새 진단 `download-diagnosis-20261017T010601-61560c19`에서 기준 기록과 원본 A 파일 해시를 먼저 보존하고 원래 A 저장 링크를 한 번 클릭했다. 외부 150,000ms·내부 클릭 120,000ms 제한을 명시했으며 클릭 호출은 약 0.31초에 정상 반환했다. 이번 호출에는 wrapper timeout이 없었다. `downloadMedia`의 저장 성공을 시험한 호출로 바꾸어 해석하지 않는다.

읽기 전용 지원 이벤트에서 A 다운로드 시작과 progress canceled·0 bytes를 확인했고 같은 항목의 새 브라우저 기록은 state 4·FILE_BLOCKED 11·danger 4·0 bytes·빈 MIME이었다. 기준 해당 기록은 3개에서 4개가 됐으며 대상 파일은 없었다. 이벤트와 새 기록의 연결은 비공개 식별값으로 확인하고 공개하지 않는다. A 클릭 1회·B 0회·재시도 0회·보안/정책/확장/CDP 설정 변경 0회·새 모델 추론 0회다.

읽기 전용 Network 이벤트 조회에서는 해당 요청·응답·loadingFailed·ExtraInfo 이벤트를 얻지 못했고, 확인한 서버 실행 stdout/stderr도 비어 있었다. 당시 앱 handler는 요청 로그를 남기지 않았다. 따라서 GET의 서버 도달 여부는 미확정이며 0 bytes·빈 MIME만으로 HTTP 응답 이전에 차단됐다고 확정하지 않는다.

**명시 timeout을 적용한 정상 클릭 반환 뒤에도 FILE_BLOCKED가 재현됐으므로 timeout 수정은 현재 차단의 해결이 아니다.** 보안 callback·대상 결정의 발신 원인 로그는 포착하지 못해 근본 원인은 여전히 미확정이다. 이번 결과는 기존 원본의 다운로드 진단이며 새 TTS 성공이나 M5 전체 PASS가 아니다. 독립 읽기 전용 검토에서 기존 3개 기록의 모든 기존 필드 불변·새 항목 정확히 1개·이벤트와 새 브라우저 항목의 연결·대상 파일 부재를 확인했다. 이벤트 결과는 hasMore=false·truncated=false였고 클릭은 313ms 정상 반환이었다. 비공개에는 baseline·단일 시도 ledger·이벤트·사후 기록·독립 검토를 보존한다. [한정 승인](APPROVALS.md) · [호출 계약](DOWNLOAD_VALIDATION.md)

## 로그 보강 후 2차 제한 재현

앞선 1회 재현은 위 결과로 완료됐다. 사용자는 이어 서버의 opt-in 개인정보 최소화 진단 로그 구현·검증·로컬 재시작, 지원되는 브라우저 관찰 로그 준비, 준비 후 보안 설정을 유지한 별도 1회 재현·결과 반영을 새로 승인했다. 서버 진단 코드 구현·검증·로컬 기동과 이번 별도 단일 재현을 수행했다. 서버 응답은 확인했지만 브라우저 종결 결과는 indeterminate다. 앞선 관측을 이번 실행 결과로 대체하지 않는다.

같은 M5 기존 A WAV만 진단 원본으로 지정하고 새 TTS 추론은 하지 않는다. 쿠키·토큰·비밀값 수집, 정책·보안·확장·CDP download behavior 변경, 다른 방식 저장 우회와 자동 반복은 금지한다. 새 진단 출처·원시 로그는 비공개에 보존한다. 서버 코드가 바뀌므로 기존 GPU·123개 테스트·wheel 검증은 당시 이력이며 새 진단 코드의 검증·재현 증거를 별도로 기록한다. 기존 wheel에는 새 진단 코드가 없고 이번 진단 코드 포함 wheel을 새로 만들지 않았다. [새 한정 승인](APPROVALS.md)

### 서버 opt-in 개인정보 최소화 로그 구현

새 `download_diagnostics.py`와 서버 연결은 프로세스 환경변수 `AI_MANAGER_DOWNLOAD_DIAGNOSTICS=1`일 때만 동작한다. 기본값 off에서는 로그 파일을 만들지 않으며 진단 health 경로는 404다. 활성화 시 새 비공개 세션 폴더에 JSONL을 생성한다. 로그는 GET 오디오·진단 health 경로만 관찰하고 route 별칭·생성 request ID·시각·응답 상태·allowlist MIME·안전한 attachment filename·길이·기록 단계·서버가 쓴 바이트 수를 남긴다. 원시 헤더·query·body·입력 텍스트·개인 파일 경로·쿠키·인증 토큰을 기록하지 않는다.

세션당 1,000개 레코드 상한·thread lock·flush를 적용한다. 로그 I/O 실패는 앱 처리를 유지하되 진단 health를 false로 만든다. 서버의 request_received→response_prepared→headers_sent→body_written→response_complete 또는 오류 단계를 구분한다. 서버 write/flush 완료는 브라우저 수신·다운로드 저장 완료를 증명하지 않는다.

새 서버 진단 코드 SHA-256은 `319407cfbe4ab9e4c6a233970c29253fd793f5497ccc998784cbb3b00012657d`(server.py), `2b64de9df819432fd44e8a52485bb06c18eaddc07f544bcc6cf7e946c039ef78`(download_diagnostics.py)다. 새 합성 테스트 4개와 기존 서버 테스트 3개를 통과했다. 기본 off 무파일, query/비밀값 제외·thread 동시 기록·상한, 로그 실패 health, 합성 HTTP 성공/403/404·응답 헤더 보존을 확인했다. 승인된 기존 idle 서버를 정상 종료하고 앱의 기존 가상환경으로 진단을 켠 새 서버를 기동했다. health healthy=true와 실제 JSONL 5단계의 비민감 health 응답을 확인했으며 이 준비 검증에서 실제 오디오 요청은 0회였다. 초기 잘못 선택한 시스템 Python은 의존성 부재로 종료했고 기존 앱 환경으로 바로잡았다. 새 패키지 설치·보안 설정 변경은 하지 않았다.

### 브라우저 관찰 로그 준비와 이번 서버 관측

설치 버전의 지원 기능으로 `Network.enable`을 호출해 네트워크 이벤트 관찰을 준비했다. download behavior·보안 설정 변경과 구분한다. callback 주체나 OS 보안 제품의 원인 코드까지 포착한다고 보장하지 않으며 쿠키·인증 헤더는 보존하지 않는다. 사전 준비에서 health 요청의 브라우저 Network request/response 200·loadingFinished와 서버 5단계 기록을 확인해 관찰 기능 준비를 검증했다. 이후 이번 지정 A 원본 링크를 한 번 클릭했고 323ms에 정상 반환했다. 서버 독립 로그는 기준 30개에서 35개로 늘었으며 attachment 요청 하나의 GET 수신→응답 준비→헤더 전송→body write→flush 완료 5단계가 연결됐다. HTTP 200·audio/wav·정확한 A attachment filename·Content-Length 207,404·쓰기 207,404 bytes를 확인했다. 정확한 파일명과 원시 로그는 비공개에 보존하고 공개하지 않는다. 원시 시각상 클릭은 UTC 16:22:30.585~16:22:30.908, 서버 응답 단계는 UTC 16:22:30.656~16:22:30.690으로 기록됐다. 독립 서버 로그 검토도 새 request 1개·5개 단계와 write/flush 바이트를 확인했다.

이번에는 GET의 서버 도달과 응답 바이트 작성·flush를 직접 확인했다. 앞선 재현의 서버 도달 미확인 한계는 그 이전 시도에 그대로 적용한다. 이번 서버 작성 완료도 브라우저 수신·파일 저장 성공을 증명하지 않는다. 브라우저 다운로드 시작 이벤트는 관찰했지만 progress·Browser 종결 이벤트나 정확한 오디오 Network 실패 이벤트는 확인하지 못했다. 당시 조회는 truncated=false였으나 관찰되지 않은 이벤트의 원인이나 저장 상태를 확정하지 않았다. 활성 History의 일반 읽기 전용(mode=ro) 조회는 확인한 두 프로필에서 오류가 났고 rollback journal이 존재했다. immutable 조회에서 새 행이 없다는 사실만으로 최신 이력을 온전히 읽었다고 보장할 수 없어 완료·실패·차단으로 판정하지 않는다.

JavaScript dialog 조회는 null이었지만 native 저장·권한 prompt의 존재 여부를 판정하지 못한다. 사용자에게 추가 버튼을 누르지 않고 현재 표시 문구만 확인해 달라고 요청했고, 사용자는 현재 저장·허용·native prompt가 보이지 않는다고 답했다. 이는 현재 화면의 사용자 관찰이며 과거 또는 관찰되지 않은 대화상자 여부까지 배제하지 않는다. 추가 클릭·B 진행·재시도·보안 설정 변경은 하지 않았다. 현재 결과는 **서버 도달·응답 작성 확인 / 브라우저 수신·저장·종료 상태 indeterminate / 근본 원인 미확정**이다. 앞선 FILE_BLOCKED 기록을 이번 시도의 종결 결과로 대체하지 않는다. 사용자 관찰 이후 같은 시도의 기존 이벤트·History를 한 번 더 읽기 전용으로 확인했다. Page/Browser terminal 이벤트 필터의 일치 항목은 0개였지만 응답이 truncated=true여서 전체 종결 이벤트 부재를 단정하지 않는다. 일반 mode=ro·query_only로 확인한 3개 프로필 중 하나는 읽기에 성공했으나 해당 GUID 기록이 없었고, 활성 두 프로필은 database locked였다. 활성 DB에는 rollback journal이 남아 있어 immutable fallback을 최신 상태 판정으로 사용하지 않았다. 공개 문서에 GUID·프로필 경로·원시 DB 식별값은 넣지 않는다.

최종 확인 범위는 **서버 HTTP 200·audio/wav·attachment 207,404바이트 write/flush 확정, 사용자 현재 prompt 없음 관찰 / client 종결·저장 무결성·근본 원인 미확정**이다. 이번 단계의 추가 클릭·다운로드는 0회다. 사용자 답변은 새 재시도 승인으로 해석하지 않으며 다시 실행하지 않는다. 최종 상태·한계는 비공개 출처 기록과 단일 시도 ledger에 보존한다. 완료·차단·원인 해결을 추정하지 않는다.

## 명시적 Edge 전환의 별도 진단

사용자는 Edge로 전환해 진행할 것을 명시 승인했다. 정상 지원 연결로 앱·health·네트워크/서버 로그를 준비한 뒤 같은 M5 기존 A 원본의 정상 다운로드를 1회 진단하는 한정 범위다. Chrome·Edge의 보안·정책·확장·CDP download behavior 변경이나 저장 우회는 하지 않는다. Edge에서 명시적인 deny가 나오면 중단한다. Edge에 관리 정책·위험 분류가 없다고 확인 없이 가정하지 않는다.

Edge 앱 접근·로그 준비 뒤 승인된 A 저장 링크를 한 번 클릭했다. 원시 UTC 시각은 16:48:40.824~16:48:41.121(약 297ms)이고 지원 download 이벤트 대기는 16:48:41.221에 경로를 반환했다. Page 다운로드 시작→207,404/207,404 bytes 진행→completed 이벤트를 관찰했고 결과는 truncated=false였다. 다운로드 파일은 이번 시도의 수정 시각·207,404 bytes를 확인했고 SHA-256 `6e6938e0c2eb5ceea6394a4fbbb72deb68d75f8ce958cd6a5dec06481f96a0d8`로 지정 M5 A 원본과 일치했다. 독립 읽기 전용 파일 검사도 같은 크기·해시를 확인했다. 파일 재생·복사로 검증을 대체하지 않았다.

서버 독립 로그는 기준 60→65개로 정확히 요청 하나의 5단계가 추가됐고 UTC 16:48:41.010620~16:48:41.041182의 GET·HTTP 200·audio/wav·정확한 A attachment·길이/쓰기 207,404 bytes·flush 완료를 확인했다. 준비 단계에서는 health의 브라우저 Network request/response와 서버 5단계로 관찰 준비를 검증했다. 이번에는 서버 응답만이 아니라 지원 download 경로 반환·completed 이벤트·실제 파일 무결성까지 연결했다. Edge History는 잠겨 있어 추가 조회하지 않았으며 이 항목을 History 종결 확인이라고 표시하지 않는다. 이전 Chrome의 사용자 최신 항목 없음 관찰과 서버 응답만 확인된 불확정 결과는 별도 이력이다. Edge 결과를 Chrome의 종결 또는 차단 원인 증거로 바꾸어 해석하지 않는다. 사전 준비 관측만의 별도 호출에서 기본 30초 제한으로 timeout·kernel reset이 한 번 발생했지만 그때 다운로드 클릭은 0회였다. 실제 단일 재현은 클릭 전에 지원 download observer를 설치하고 원래 anchor 클릭과 같은 호출에서 외부 150,000ms·observer 45,000ms·클릭 120,000ms 제한으로 수행해 완료했다. 추가 클릭·재시도·보안/정책/확장/CDP download behavior 변경·소스 변경은 없었다.

이번 전환은 브라우저뿐 아니라 관찰 호출 경로도 달라진 조건이다. Edge 정상 경로의 결과로만 기록하며 Chrome 근본 원인 특정·기존 차단 해결·모든 조건 성공·M5 전체 PASS로 확대하지 않는다. 새 진단 `edge-download-20261017T014422-0169f8da`의 baseline·준비·브라우저 이벤트·단일 시도 ledger·파일 무결성·독립 서버/파일 검토와 실제 경로는 비공개에 보존한다. 당시 A 단계 판정은 **명시 승인된 정상 Edge 경로의 A 단일 다운로드 PASS / Chrome 차단 원인·앞선 Chrome 로그 보강 시도의 종결 미확정 / M5 전체 PASS 아님**이다. 당시 A 단계에서는 Edge B가 미검증이고 B 다운로드·재시도·downloadMedia·새 모델 추론·보안 설정 변경은 0회였다. 이후 B의 별도 승인 결과는 다음 절에 구분한다. 이번 프로젝트의 이후 브라우저 작업은 사용자 요청에 따라 Edge를 선호하지만 전역 기본 설정은 변경하지 않는다. [Edge 한정 승인](APPROVALS.md)

## Edge B 한정 검증의 승인과 실제 결과

사용자는 같은 M5 B 원본의 정상 Edge 다운로드 1회·파일 무결성 확인·결과 반영을 명시 승인했다. 대상은 157,484 bytes·SHA-256 `443376fc599adb0de1aed293ba8c764166fb517b62df91e62ab6b0b0ee3d4aa2`이며 새 TTS 추론은 하지 않는다. A 재다운로드·자동 재시도·다른 저장 방식·보안 설정 변경은 허용하지 않는다. 처음에는 지원 Edge 연결이 없어 다운로드 클릭 0회로 준비를 보류했다. 사용자가 Edge를 열었다고 확인한 뒤 정상 연결로 이번 B 원본 링크를 승인 범위에서 한 번 클릭했다. UTC 17:31:37.474~17:31:37.761(287ms)에 정상 반환했고 정확한 B 다운로드 시작·157,484/157,484 bytes·completed 이벤트와 지원 observer 경로 반환을 확인했다. 실제 B 파일은 157,484 bytes이고 SHA-256 `443376fc599adb0de1aed293ba8c764166fb517b62df91e62ab6b0b0ee3d4aa2`로 지정 B 원본과 일치했다. 독립 읽기 전용 검사도 크기·해시·이번 시도의 수정 시각을 확인했다.

서버 독립 로그는 기준 90→95개로 B attachment 요청 하나의 정확한 5단계를 확인했다. UTC 17:31:37.513341~17:31:37.533907 사이 GET 수신·HTTP 200·audio/wav·정확한 B attachment·길이 157,484·쓰기/flush 157,484 bytes가 클릭 구간과 연결됐다. 따라서 Edge B 단일 원본 링크는 completed 이벤트·지원 경로·실제 파일 무결성·독립 서버 로그를 연결해 PASS로 판정한다. 실제 파일명·경로·브라우저 식별값은 공개하지 않는다.

새 진단 `edge-B-download-20261017T022749-401096d0`의 준비·단일 시도·이벤트·서버/파일 독립 검토를 비공개에 보존한다. 이번 B 클릭은 1회, A 추가 클릭·재시도·새 모델 추론·소스 변경·보안/정책/확장/CDP download behavior 변경은 0회다. Edge A와 B는 각각 별도 명시 승인된 1회 저장 검증이다. 사람이 직접 클릭한 경로와 모든 브라우저 조합을 검증한 것은 아니다. [B 한정 승인](APPROVALS.md)

## 원계획에 따른 M5 완료 기준과 잔여 항목

판정 근거는 [마일스톤 M5 행](MILESTONES.md)과 [품질 게이트의 M5 행](QUALITY_GATES.md), [제품 범위의 재생·저장 및 비교 기능](PLAN.md)다. 기존 계획은 두 모델 각각의 새 실행·공통 조건·재생·평가·부분 실패·취소·실측 근거를 요구한다. Chrome 원인 해결, 모든 브라우저 지원, 자동 품질 승자 선정 또는 모든 입력·장시간 성능을 M5 필수 gate로 정하지 않았다. 사용자가 추가로 승인한 다운로드 확인은 실제 지원 경로·무결성 증거로 별도 연결한다.

| 구분 | 항목 | 증거·현재 상태 | 잔여 또는 판정 범위 |
|---|---|---|---|
| M5 필수 | 두 모델의 동일 새 입력·seed·공통 옵션·콜드 순차 실제 실행 | 정상 비교 ID와 새 두 run_id·모델/입력/소스/런타임/WAV 해시·실측 확인 | PASS. 모델당 표본 1회·현재 입력/환경 범위 |
| M5 필수 | 무결성·준비와 실제 결과의 분리 | 13/12개 모델 바이트·고정 revision·환경과 실제 PCM16 WAV 연결 | PASS. 임의 모델 범용 실행 주장이 아님 |
| M5 필수 | A/B 재생·측정 조건·사용자 평가 기능 | 두 native audio 재생·exclusive pause·undecided/메모 저장·재조회·표본/메모리 범위 표시 | PASS. 기능 검증이며 사람의 품질 우열 평가 아님 |
| M5 필수 | 부분 실패·취소·캐시 유입 방지 | 실제 별도 새 비교 A 성공/B running 취소→partial·평가 차단·B 오디오 409·worker 종료, 자동 반례 | PASS. 실패/취소가 성공으로 표시되지 않음 |
| M5 품질 | 상태 UI·한국어 가독성·대표 폭·키보드 | 정상/부분 완료 768/1280/1440/1920·넘침 0·포커스 3px·시각 검토 | 확인한 목표 PASS. WCAG 인증이나 모든 보조기술 검증은 아님 |
| 제품 저장 기능 및 추가 승인 검증 | 정상 Edge A/B WAV 다운로드 무결성 | Edge A 207,404 bytes·B 157,484 bytes, 각각 원본 SHA·completed·지원 경로·서버/파일 독립 검증 PASS | 확인한 정상 지원 Edge A/B 단일 저장 경로 완료. Chrome 또는 모든 브라우저 보장은 아님 |
| M5 필수 | 보존·출처·공개 개인정보 제외 | 새 비교 입력/출력 계약·허용 모델·공개 whitelist·고정 커밋 원문/비변경 blob 검증 | 확인한 경로 범위 PASS. 전 디스크의 재사용 부재 주장이 아님 |
| 알려진 환경 제한·추가 진단 | Chrome FILE_BLOCKED 원인과 로그 보강 시도의 client 종결 | 이전 차단 기록 보존, 서버 응답 확인·client indeterminate·로그 한계 공개 | 미해결. 원계획 M5 필수 gate로 추가하지 않음. Edge 성공이 Chrome 해결을 뜻하지 않음 |
| 선택 품질·성능 평가 | 사람 청취·ASR·발음/자연스러움 우열·더 많은 문장/반복·실제 GPU OOM | 수행하지 않음 | 미검증. 원계획이 보장하지 않은 객관 품질/일반 성능 주장을 하지 않음 |
| M6 별도 범위 | 최신 진단 코드 포함 출시 wheel·신규 환경 설치·인증/DB/작업 재시작 복구·전체 출시 회귀 | 기존 wheel은 당시 소스만 포함, 새 진단 소스 포함 wheel은 미작성 | M6 미승인·미완료. M5 비교 기능에 임의로 편입하지 않음 |

M5 원계획의 필수 비교 기능과 요청된 Edge A/B 저장 무결성 확인을 위 증거로 완료 판정한다. 완료 범위는 확인한 로컬 환경·두 지정 모델·동일 새 입력 비교·정상 지원 Edge 경로다. Chrome 원인 조사, 선택 품질 평가, M6의 설치·복구·출시는 완료 범위가 아니다. 기존 실패·불확정 기록은 보존하고 환경 제한과 다음 확인 조건을 계속 표시한다. 이 구분은 기존 gate를 낮추거나 새로운 gate를 추가한 것이 아니라 원계획 요구와 실제 검증 범위를 대응한 것이다.

## 보존·재사용·공개 범위

허용 모델·공개 라이브러리·동일 프로젝트의 코드·문서만 후속 갱신에 사용한다. 새 입력·run_id·comparison_id·고유 출력 디렉터리·새 로그·새 검증 결과를 생성한다. 이전 WAV·결과 캐시·다른 프로젝트의 코드나 산출물을 입력으로 연결하지 않는다. 기존 Drive 원본·중간 실패 기록은 보존한다.

확인 범위는 두 정상 실행과 새 부분 취소의 입력 계약·모델 준비·출처·출력·현재 코드/런타임 연결, 공개 whitelist다. 다른 프로젝트 전체나 전 디스크를 감사한 것은 아니므로 전체 과거 프로젝트의 재사용 부재를 단정하지 않는다. 공개 저장소에는 소스·테스트·lock·manifest·문서 whitelist만 반영하며 개인 계정·Drive ID·인벤토리·실제 절대경로·자격 증명·입력·WAV·스크린샷·로그를 제외한다. 상위 작업공간 AGENTS.md 승인 상태 변경은 로컬에만 남긴다.
