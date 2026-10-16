# Windows 로컬 설치와 실행

대상: Ai-manager v0.6.0 사용자 범위 배포. 이 안내는 현재 installer/CLI 계약을 설명하며 최종 출시 검증 상태는 [M6 보고서](https://github.com/castle923/Ai-manager/blob/main/docs/M6_REPORT.md)를 따른다. 기존 Python 3.10이 필요하고 standalone exe가 아니다. [프로그램 배포 형태 비교](https://github.com/castle923/Ai-manager/blob/main/docs/WINDOWS_DISTRIBUTION.md)

## 준비와 보존

배포 폴더의 `MANIFEST.json`, v0.6.0 wheel, `requirements.lock`, `install_windows.ps1`, 이 안내와 `RECOVERY.md`를 확인한다. 신뢰한 배포 출처의 버전·파일 집합·SHA-256과 실제 파일을 대조한다. MANIFEST와 파일을 함께 받았다는 사실만으로 게시자 신뢰를 보장하지 않는다.

설치 경로와 앱 home은 서로 포함되지 않는 별도 절대경로이며 두 경로 모두 새 경로여야 한다. 기존 개발 환경·앱 home·토큰·inventory·출력·모델을 이동/삭제/덮어쓰지 않는다. installer는 wheel/lock 해시, Python 3.10, wheel identity `ai-manager-local`/`0.6.0`을 확인하고 기존 경로·reparse 경로를 거부한다. 실패한 새 설치는 자동 삭제하지 않아 실패 증거가 남는다.

전역 PATH·PowerShell 실행 정책·브라우저 보안 설정을 변경하지 않는다. 스크립트 실행이 현재 정책으로 차단되면 정책 우회 대신 차단 상태를 기록하고 지원되는 실행 방법을 검토한다. 자격 증명·개인 설정 원본은 배포 폴더에 넣지 않는다.

## 새 환경 설치

아래 PowerShell 값은 사용자 자신이 선택한 절대경로로 바꾼다. 실제 개인 경로·파일 내용은 공개하지 않는다. `$bundleRoot`는 배포 폴더이고 `$basePython`은 기존 Python 3.10의 `python.exe`다. `$installRoot`와 `$appHome`은 아직 없는 별도 경로다.

```powershell
$bundleRoot = '<absolute_release_directory>'
$basePython = '<absolute_python_3_10_executable>'
$installRoot = '<new_absolute_install_directory>'
$appHome = '<new_absolute_private_home>'
$releaseManifest = Get-Content -LiteralPath (Join-Path $bundleRoot 'MANIFEST.json') -Raw | ConvertFrom-Json
$wheelInfo = @($releaseManifest.artifacts | Where-Object { $_.name -eq 'ai_manager_local-0.6.0-py3-none-any.whl' })
$lockInfo = @($releaseManifest.artifacts | Where-Object { $_.name -eq 'requirements.lock' })
if ($wheelInfo.Count -ne 1 -or $lockInfo.Count -ne 1) { throw 'Unexpected release artifact set' }
& (Join-Path $bundleRoot 'install_windows.ps1') -Wheel (Join-Path $bundleRoot $wheelInfo[0].name) -WheelSha256 $wheelInfo[0].sha256 -Requirements (Join-Path $bundleRoot $lockInfo[0].name) -RequirementsSha256 $lockInfo[0].sha256 -InstallDirectory $installRoot -HomeDirectory $appHome -PythonExecutable $basePython
if ($LASTEXITCODE -ne 0) { throw 'Installation did not complete' }
```

신규 venv에 lock 의존성과 wheel을 설치하고 `pip check`를 수행한다. `installation.json`에는 새 app home·앱 Python·wheel/lock 해시와 credentials_copied=false를 기록한다. 설치 완료는 계정 로그인·수집·추론 완료가 아니다. 현 installer는 새 설치 전용이며 기존 설치/home을 갱신하는 updater가 아니다. 검증된 기존 home을 명시 연결하는 별도 절차는 아래에 구분한다. home 초기화는 다음 단계에서 명시적으로 수행한다.

```powershell
$appPython = Join-Path $installRoot 'venv/Scripts/python.exe'
& $appPython -m pip check
& $appPython -c "import importlib.metadata as m; print(m.version('ai-manager-local'))"
```

버전 0.6.0·설치 manifest의 해시와 실제 설치 파일/정적 UI·모델 manifest가 일치하는지는 해당 배포 검증 기록과 연결한다. 기존 Python이나 소스 checkout을 잘못 읽은 성공으로 대체하지 않는다.

## fresh 설정과 두 계정 연결

이번 프로젝트에 지정한 allowlist·Desktop OAuth client 원본만 입력한다. installer는 이전 home의 토큰/state/output/inventory를 복사하지 않는다. `init`은 이미 초기화한 설정을 덮어쓰지 않는다. 아래 `--home`은 subcommand 앞에 둔다.

```powershell
$allowlistSource = '<designated_absolute_allowlist_json>'
$oauthClientSource = '<designated_absolute_desktop_oauth_client_json>'
& $appPython -m ai_manager.cli --home $appHome init --allowlist $allowlistSource --client $oauthClientSource
& $appPython -m ai_manager.cli --home $appHome connect A
& $appPython -m ai_manager.cli --home $appHome connect B
& $appPython -m ai_manager.cli --home $appHome refresh A
& $appPython -m ai_manager.cli --home $appHome refresh B
& $appPython -m ai_manager.cli --home $appHome scan A
& $appPython -m ai_manager.cli --home $appHome scan B
& $appPython -m ai_manager.cli --home $appHome status
```

로그인·OAuth 동의는 사용자가 시스템 브라우저에서 직접 수행한다. 계정·scope 일치와 refresh 결과, 새 scan의 complete/partial·오류를 각각 확인한다. credential_saved는 저장된 인증 존재 표시이며 현재 권한·API 성공과 같지 않다. 개인 비밀번호·인증 코드·토큰을 로그나 채팅에 넣지 않는다.

## 화면 시작과 종료

설치 폴더의 `Start-AiManager.cmd`를 실행하면 설치된 앱 Python·installation.json의 home으로 시작한다. 이 파일은 설치된 Python을 호출하는 launcher이며 독립 exe가 아니다. 기본 브라우저 자동 열기는 시스템 브라우저 설정을 따르고 전역 기본 브라우저를 변경하지 않는다.

Edge를 명시적으로 사용할 때는 다음처럼 자동 브라우저 열기를 생략하고 콘솔에 출력된 `127.0.0.1` URL을 Edge에서 연다. 기본 포트 0은 빈 포트를 자동 선택한다.

```powershell
& $appPython -m ai_manager.cli --home $appHome serve --port 0 --no-browser
```

특정 빈 포트가 필요하면 `--port <port>`를 사용한다(0~65535). 이미 사용 중인 포트나 다른 앱을 강제 종료하지 않는다. `Start-AiManager.ps1 -Port <port> -NoBrowser`도 같은 설치 경로에서 선택할 수 있다. CMD launcher는 설치된 Python launcher에 CLI 인수를 전달하므로 `--port <port>`·`--no-browser`를 사용할 수 있다. 경로는 따옴표로 처리하고 delayed expansion을 끄며, Python은 subprocess 인수 목록으로 실행한다. 모든 shell 문자·임의 인수 조합의 동작을 보장하는 것은 아니다.

콘솔의 Ctrl+C로 이 앱을 정상 종료한다. 브라우저 탭을 닫는 것만으로 backend 종료를 보장하지 않는다. 다른 앱·소유권이 불명확한 프로세스를 PID 이름만으로 종료하지 않는다. 재시작·작업 복구는 [RECOVERY.md](RECOVERY.md)를 따른다.

## 검증된 기존 home을 새 설치본에 명시 연결

fresh installer는 기존 home을 계속 거부한다. 다만 이번 M6에서 이미 새 인증·수집을 완료한 home을 최종 새 설치본에서 그대로 사용하려면 별도 `scripts/link_existing_home.py`를 명시 실행할 수 있다. 자동 update·마이그레이션이 아니며 다른 프로젝트나 임의 기존 home을 검색해 가져오는 기능도 아니다.

먼저 새 설치본과 대상 home의 출처·범위·호환성을 확인하고 대상 `settings.json`의 검증된 SHA-256을 준비한다. 새 설치 폴더와 home은 서로 별도 절대경로여야 하며 reparse 경로를 사용하지 않는다. 작업 중인 소유 앱이 있으면 정상 종료한 뒤 전환한다.

```powershell
$verifiedHome = '<absolute_verified_same_project_home>'
$expectedSettingsSha = '<verified_64_hex_settings_sha256>'
& $appPython (Join-Path $bundleRoot 'scripts/link_existing_home.py') --install $installRoot --home $verifiedHome --settings-sha256 $expectedSettingsSha
if ($LASTEXITCODE -ne 0) { throw 'Explicit home link did not complete' }
```

도구는 settings 해시를 대조하고 기존 `installation.json`을 `installation-before-home-link.json`에 배타적으로 새로 보존한 뒤, 새 설치본의 manifest home pointer와 명시 연결 표시·settings hash만 변경한다. 토큰·DB·state·output·모델을 복사하거나 대상 home의 내용을 쓰지 않는다. 새 설치의 기존 빈 home도 자동 삭제하지 않는다. 백업이 이미 있거나 경로·해시가 맞지 않으면 중단하며 실패 흔적을 지워 반복 실행하지 않는다.

성공 후 `installation.json`의 앱 Python이 새 설치본인지, home·settings hash가 지정 값인지 확인한다. CLI 직접 실행도 `--home $verifiedHome`로 같은 명시 home을 선택할 수 있다. CMD launcher는 다음처럼 옵션을 전달한다. 예시 포트는 실제 사용 중이지 않은 포트로 선택한다.

```powershell
& (Join-Path $installRoot 'Start-AiManager.cmd') --no-browser --port 2966
```

한글·공백 경로는 따옴표 처리된 인수로 전달한다. 실제 현재 릴리스에서 검증된 경로·옵션 범위는 M6 보고서를 따르고 모든 경로 문자 조합을 인증했다고 주장하지 않는다. 새 설치본의 Edge 화면·상태·실제 작업은 연결 뒤 별도로 검증한다.

## 지정 모델과 별도 추론 환경

앱 wheel은 모델 가중치·GPU 드라이버·Torch 추론 환경·개인 인증을 포함하지 않는다. 새 추론 환경이 필요하면 배포의 명시 home/기존 Python 인수를 사용한다. 기존 runtime/venv가 있으면 덮어쓰지 않는다.

```powershell
& (Join-Path $bundleRoot 'scripts/setup_runtime.ps1') -HomeDirectory $appHome -PythonExecutable $basePython
& $appPython -m ai_manager.cli --home $appHome runtime-check
```

이 과정은 공개 고정 의존성 설치·환경 검사이며 실제 추론이 아니다. CUDA/드라이버 호환성과 실제 생성은 따로 확인한다. 허용 모델 파일을 로컬에서 준비할 경우 지정한 모델 구성 경로만 사용한다.

```powershell
& $appPython -m ai_manager.cli --home $appHome prepare-local --model-id qwen3-tts-0.6b-customvoice --source '<designated_absolute_0_6b_model_assets>'
& $appPython -m ai_manager.cli --home $appHome prepare-local --model-id qwen3-tts-1.7b-customvoice --source '<designated_absolute_1_7b_model_assets>'
```

준비는 새 실행 디렉터리로 필요한 모델 파일만 복사·해시 검증한다. 과거 WAV·로그·결과 폴더를 source로 지정하지 않는다. 같은 모델 자산은 허용되지만 이전 성공 기록을 이번 실행으로 대체하지 않는다. 실제 생성·비교·재생·저장·취소는 새 입력·새 run_id로 확인한다.
