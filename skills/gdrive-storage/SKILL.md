---
name: gdrive-storage
description: Google Drive 데스크톱 앱의 로컬 가상 드라이브 경로를 감지하고, 프로젝트 폴더(input_staging, scratch, archive, secrets 등)를 정션(Junction) 마운트하여 실시간 클라우드 동기화 및 파일 관리를 지원하는 글로벌 스킬입니다.
---

# Google Drive 로컬 가상 드라이브 스토리지 스킬 (`gdrive-storage`)

이 스킬은 로컬 Google Drive 데스크톱 앱 기반의 가상 드라이브(예: `G:\내 드라이브`) 경로를 감지하고, 프로젝트 내 작업 폴더들을 디렉터리 정션(`mklink /J`)으로 투명하게 연결하여, **로컬 I/O 속도로 작업하면서도 클라우드로 안전하게 백그라운드 실시간 동기화**되도록 합니다.

---

## 1. 주요 기능

1. **자동 경로 감지 (Auto Detection)**:
   - Windows 및 macOS 환경에서 Google Drive 가상 드라이브 경로와 언어별 루트(`내 드라이브` / `My Drive`)를 자동 탐색합니다.
   - 다중 계정(예: `sarangia85@gmail.com`, `haileyfamily2015@gmail.com`) 환경에서도 `.env` 또는 설정에 따라 정확한 계정을 매핑합니다.
2. **원클릭 일괄 세팅 (`init`)**:
   - 신규 PC나 새로운 환경에서 명령어 단 1회 실행으로 모든 타깃 폴더(`input_staging`, `scratch`, `archive`, `secrets`)를 구글 드라이브와 정션 연결하고, 마스터 보안 파일(`.env`, `auth_state.json`)을 프로젝트 루트로 자동 복원합니다.
3. **무손실 데이터 마이그레이션**:
   - 로컬에 이미 파일이 존재할 경우, 구글 드라이브 대상 디렉터리로 기존 데이터를 안전하게 이전(복사)한 후 정션을 연결합니다.
4. **보안 파일 안전 관리 (`secrets/` 금고 및 미러링)**:
   - GitHub에 올릴 수 없는 보안 필수 파일(`.env`, `auth_state.json` 등)을 구글 드라이브와 연결된 `secrets/` 폴더에 마스터로 보관하고, 프로젝트 루트와 동기화합니다. 기존 코드는 프로젝트 루트 파일을 그대로 참조하므로 **단 1줄의 코드 수정도 필요하지 않습니다**.
5. **개별 파일 CRUD CLI 지원**:
   - 에이전트가 단독으로 파일을 구글 드라이브 워크스페이스에 저장(`save`), 읽기(`read`), 삭제(`delete`), 목록 조회(`list`)할 수 있습니다.

---

## 2. 프로젝트별 설정 규칙 (Configuration)

개별 프로젝트 루트에 `.gdrive_config.json`을 두거나, `.env` 파일에 환경 변수를 지정하여 프로젝트별 맞춤 설정을 할 수 있습니다.

### 방법 A: `.gdrive_config.json` (권장 - 깃허브 관리 가능)
프로젝트 루트에 아래와 같이 구성합니다:
```json
{
  "account": "sarangia85@gmail.com",
  "workspace_root": "Antigravity_Workspaces",
  "project_name": "macro_analyzer",
  "folders": ["input_staging", "scratch", "archive", "secrets"],
  "secret_files": [".env", "auth_state.json"]
}
```

### 방법 B: `.env` 환경 변수 오버라이드
```env
# Google Drive 계정 (다중 계정일 때 우선 매칭)
GDRIVE_ACCOUNT=sarangia85@gmail.com

# 구글 드라이브 경로 직접 강제 지정 (선택 사항)
# GDRIVE_PATH=G:\내 드라이브

# 동기화할 폴더 목록 (쉼표 구분)
GDRIVE_SYNC_FOLDERS=input_staging,scratch,archive,secrets
```

---

## 3. 다른 PC(신규 환경)에서의 1회 세팅 매뉴얼

GitHub에서 프로젝트를 새로 clone 받은 새로운 PC 환경에서 다음 절차를 진행합니다:

### [Step 1] Google Drive 데스크톱 앱 실행 확인
* PC에서 Google Drive 앱이 로그인되어 실행 중인지 확인합니다. (가상 드라이브 마운트 상태)

### [Step 2] 글로벌 스킬 원클릭 초기화 실행
프로젝트 루트 디렉터리 터미널에서 다음 명령어를 실행합니다:

```bash
# Windows (py 실행기 사용)
py ~/.gemini/config/skills/gdrive-storage/scripts/gdrive_manager.py init

# 또는 Python이 활성화된 환경
python ~/.gemini/config/skills/gdrive-storage/scripts/gdrive_manager.py init
```

* **실행 결과**:
  1. 구글 드라이브의 해당 계정 및 `내 드라이브\Antigravity_Workspaces\<프로젝트명>` 경로를 자동 감지합니다.
  2. `input_staging`, `scratch`, `archive`, `secrets` 폴더가 구글 드라이브와 1:1 정션(`mklink /J`)으로 연결됩니다.
  3. 구글 드라이브 `secrets/`에 보관되어 있던 최신 `.env`와 `auth_state.json`이 프로젝트 루트로 자동 복사됩니다.
  4. 모든 초기화가 끝나면, **기존 모든 파이썬 스크립트와 명령어들을 즉시 실행**할 수 있습니다.

---

## 4. CLI 명령어 레퍼런스

글로벌 스크립트 위치: `~/.gemini/config/skills/gdrive-storage/scripts/gdrive_manager.py`

| 서브커맨드 | 설명 | 사용 예시 |
| :--- | :--- | :--- |
| `detect` | 감지된 구글 드라이브 및 활성 경로 정보 조회 | `py .../gdrive_manager.py detect` |
| `status` | 프로젝트 폴더 정션 연결 상태 및 보안 파일 확인 | `py .../gdrive_manager.py status` |
| `init` | 프로젝트 전체 폴더 일괄 마운트 및 보안 파일 복원 | `py .../gdrive_manager.py init` |
| `link <folder>` | 특정 폴더 단독 연결 (기존 데이터 자동 이전) | `py .../gdrive_manager.py link input_staging` |
| `unlink <folder>` | 특정 폴더 연결 해제 (원본 클라우드 데이터 보존) | `py .../gdrive_manager.py unlink input_staging` |
| `sync-secrets` | 루트와 `secrets/` 간의 보안 파일 동기화 | `py .../gdrive_manager.py sync-secrets --direction auto` |
| `save <src> <dst>` | 개별 파일을 구글 드라이브 워크스페이스에 저장 | `py .../gdrive_manager.py save temp.txt reports/daily.txt` |
| `read <src> <dst>` | 구글 드라이브 파일을 로컬로 복사 | `py .../gdrive_manager.py read reports/daily.txt ./daily.txt` |
| `delete <target>` | 구글 드라이브 내 파일/폴더 삭제 | `py .../gdrive_manager.py delete reports/old.txt` |
| `list [subfolder]` | 구글 드라이브 프로젝트 저장소 파일 목록 출력 | `py .../gdrive_manager.py list archive` |
