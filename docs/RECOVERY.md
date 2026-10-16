# 보존 우선 로컬 복구 안내

대상: Ai-manager v0.6.0의 명시 `--home`과 `db-backup`/`db-restore`. 이 안내는 현재 코드 계약이며 실제 통과·미확인 범위는 [M6 보고서](https://github.com/castle923/Ai-manager/blob/main/docs/M6_REPORT.md)를 따른다. 모든 예시 경로는 절대경로로 대체하고 개인 내용은 공개하지 않는다.

## 이 기능이 복원하는 범위

`db-backup`은 현재 home의 `inventory.sqlite3`를 SQLite backup API로 일관된 **새 파일**에 snapshot한다. `db-restore`도 검증한 정상 source를 **새 destination**에 복사한다. 손상된 원본 DB 자체를 수리하거나 기존 파일에 덮어쓰는 기능이 아니다.

지원 대상은 이 앱의 canonical inventory schema(scans/files)다. integrity/foreign key·컬럼·테이블·trigger/view·정확한 canonical schema를 검증하며 임의 SQLite·변형 schema를 자동 이식하지 않는다. inventory 복원은 OAuth 토큰·DPAPI 상태·모델·추론 환경·TTS/비교 run 파일·WAV 복원이 아니다. 이 데이터는 별도 경로로 보존한다.

## 정상 snapshot 새로 만들기

이번 설치본의 앱 Python과 지정 home을 사용한다. `--home`은 subcommand 앞이다. destination은 없는 새 절대 파일 경로여야 한다.

```powershell
$appPython = '<absolute_installed_app_python>'
$appHome = '<absolute_current_private_home>'
$backupFile = '<new_absolute_inventory_snapshot_file>'
& $appPython -m ai_manager.cli --home $appHome db-backup --destination $backupFile
```

성공 결과 `copied_to_new_target`·integrity=ok·supported schema·bytes·SHA-256를 비공개 복구 기록에 남긴다. source와 기존 destination은 보존한다. backup은 단순 DB 파일 복사와 달리 SQLite snapshot을 사용하지만 lock·디스크·파일 권한·schema 때문에 실패할 수 있다.

## 정상 backup에서 새 대상 복원

복원 source는 위 정상 snapshot 또는 명시 검증한 같은 앱 정상 DB다. destination은 기존 DB와 다른 새 절대경로다.

```powershell
$restoreTarget = '<new_absolute_restore_target_file>'
& $appPython -m ai_manager.cli --home $appHome db-restore --source $backupFile --destination $restoreTarget
```

성공한 새 파일의 integrity·schema·행 수·비공개 상태를 별도로 확인한다. byte SHA가 원본과 항상 같아야 하는 일반 파일 복사로 해석하지 않는다. 복원 명령은 설치본 설정을 자동 전환하거나 기존 app home의 inventory를 교체하지 않는다.

새 home에서 사용할 때는 설정 원본을 명시해 초기화한 별도 home의 **아직 없는** inventory 경로를 destination으로 선택하는 절차를 검토한다. 기존 home이나 손상 원본을 삭제·이동하지 않는다. 같은 지정 allowlist/계정 설정과 복원 inventory의 출처가 맞는지 확인하고 필요한 fresh OAuth 로그인·동의는 사용자가 수행한다. 기존 토큰·state·output을 자동 복사하지 않는다.

## 손상·잠금·중단 시의 처리

- source가 손상됐거나 schema가 지원되지 않으면 복원 source로 채택하지 않는다. source·오류 기록을 보존하고 정상 snapshot이 있는지 확인한다. 정상 backup이 없으면 이 명령이 손상 원본을 수리할 수 있다고 주장하지 않는다.
- 기존 destination은 거부하므로 실패 후 같은 파일을 지우고 재시도하지 않는다. 상태를 확인한 뒤 별도의 새 destination을 명시한다.
- active lock은 짧은 busy 대기와 backup 진행 제한으로 실패할 수 있다. 현재 코드는 busy_timeout 250ms·backup progress 약 10초 deadline을 적용한다. 모든 전처리 I/O가 정확히 10초 안에 끝난다는 보장은 아니다.
- lock/timeout/디스크 오류 후 남은 고유 `.sqlite3.tmp`는 실패 증거다. 자동 삭제·원본 교체를 하지 않는다. 점유가 해소됐는지 확인한 뒤 새 대상으로 다시 검증할지 결정한다.
- 읽기 전용·권한·reparse 경로·같은 대상·상대경로 문제를 보안 설정 해제로 우회하지 않는다. CLI는 raw 개인 경로·예외를 공개하지 않고 일반 오류 코드로 보고할 수 있다.

## 인증·작업·설치 복구와의 구분

인증 오류는 계정 A/B 상태와 갱신 결과를 확인한 뒤 필요한 계정만 재로그인한다. 연결 해제는 명시 대상 계정에 수행하고 기존 home 전체 삭제로 해결하지 않는다. 만료·권한 거부·네트워크 실패를 같은 원인으로 단정하지 않는다.

앱의 실행 중단은 실패/취소/중단 상태로 표시해야 하며 재시작이 미완료 작업을 성공으로 바꾸지 않아야 한다. 이전 worker의 생존·소유권과 실제 종료를 확인한다. 기록만 바꾸어 GPU 작업을 재개했다고 주장하지 않는다. 재실행이 필요하면 새 입력·새 실행 ID·새 출력 경로를 사용한다.

설치 실패는 새 설치 디렉터리와 기록을 보존하고 wheel/lock 해시·Python 버전·패키지 identity·pip check를 확인한다. 새 버전은 새 설치 폴더에서 검증하고 이전 개인 home을 자동 삭제하지 않는다. 현 installer는 기존 home을 거부하는 새 설치 전용이며 자동 update 도구가 아니다. 같은 프로젝트의 검증된 home을 새 설치본에 연결하는 별도 `scripts/link_existing_home.py`는 명시 install/home/settings SHA-256을 요구한다. 현재 manifest를 `installation-before-home-link.json`에 새로 보존하고 home pointer만 바꾸며 토큰·DB·state·output을 복사하거나 home을 수정하지 않는다. 대상 출처·호환성·검증된 settings hash를 먼저 확인하고 [명시 연결 절차](INSTALL.md)를 따른다. 백업·중간 실패 파일을 자동 삭제하거나 재시도하지 않는다. CLI의 `--home`으로 직접 같은 명시 home을 선택할 수도 있다. venv 폴더 이동만으로 새 환경 설치를 대체하지 않는다. 전역 PATH·실행 정책·브라우저 보안 설정은 변경하지 않는다. [설치 안내](INSTALL.md) · [배포 형식 검토](https://github.com/castle923/Ai-manager/blob/main/docs/WINDOWS_DISTRIBUTION.md)
