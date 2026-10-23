---
name: obsidian-manager
description: Obsidian Local REST API 플러그인(MCP)을 통해 옵시디언 볼트의 노트를 검색, 조회, 생성, 수정(surgical patch), 첨부파일 처리 및 옵시디언 앱 명령어를 원격 제어하는 글로벌 스킬입니다.
---

# Obsidian Manager Skill (`obsidian-manager`)

이 스킬은 **Obsidian Local REST API with MCP** 플러그인을 통해 로컬 옵시디언(Obsidian) 볼트와 AI Agent(Antigravity)를 양방향으로 연동하는 글로벌 스킬입니다.

AI Agent는 이 스킬을 통해 볼트 내 노트를 검색하고, 현재 사용자가 보고 있는 활성 노트를 실시간으로 확인하며, 새로운 노트를 작성하거나 기존 노트의 특정 헤딩/블록을 정밀하게 부분 수정(Surgical Patch)할 수 있습니다.

---

## 1. 사전 구성 요건 (Prerequisites)

1. **Obsidian 데스크톱 앱 실행 상태 유지**:
   - 옵시디언 앱이 실행되어 있어야 로컬 REST API 및 MCP 엔드포인트(`https://127.0.0.1:27124`)가 수신 대기합니다.
2. **Local REST API with MCP 커뮤니티 플러그인 활성화**:
   - 옵시디언 설정 > 커뮤니티 플러그인에서 `Local REST API with MCP` 플러그인이 켜져 있어야 합니다.
3. **글로벌 환경 변수 / 설정**:
   - `~/.gemini/config/mcp_config.json`에 `obsidian` MCP 서버가 등록되어 있습니다.
   - 프로젝트 루트 또는 글로벌 `.env`에 `OBSIDIAN_API_KEY`, `OBSIDIAN_PORT`, `OBSIDIAN_URL`이 보관됩니다.

---

## 2. MCP 도구 레퍼런스 (Native MCP Tools)

`obsidian` MCP 서버가 연결되어 있을 때 에이전트는 다음 도구들을 직접 호출할 수 있습니다:

| 도구명 (MCP Tool) | 설명 | 주요 파라미터 예시 |
| :--- | :--- | :--- |
| `obsidian:vault_list` | 지정한 볼트 경로의 하위 디렉터리 및 파일 목록 조회 | `path`: `""` (루트) 또는 `"000. Inbox"` |
| `obsidian:vault_read` | 마크다운 노트의 본문, Frontmatter, 태그, 통계 읽기 | `path`: `"000. Inbox/독서메모.md"` |
| `obsidian:vault_read_binary` | 이미지, PDF 등 첨부파일 바이너리 데이터 읽기 | `path`: `"attachments/chart.png"` |
| `obsidian:vault_write` | 신규 노트를 생성하거나 전체 내용을 덮어쓰기 | `path`: `"Reports/2026-10-13-매크로.md"`, `content`: `"..."` |
| `obsidian:vault_append` | 기존 노트의 맨 끝에 새로운 내용 추가 | `path`: `"Daily/2026-10-13.md"`, `content`: `"\n- [ ] 새 할일"` |
| `obsidian:vault_patch` | **헤딩/블록/프론트매터 단위의 정밀 부분 수정 (Surgical Patch)** | `path`, `heading`, `block`, `content`, `action` |
| `obsidian:vault_delete` | 파일 또는 노트를 볼트에서 삭제 | `path`: `"temp.md"` |
| `obsidian:vault_move` | 파일 경로 이동 또는 이름 변경 (Rename) | `source_path`, `destination_path` |
| `obsidian:vault_copy` | 파일 복사본 생성 | `source_path`, `destination_path` |
| `obsidian:vault_get_document_map` | 문서의 헤딩/블록 계층 구조 맵 조회 | `path`: `"대형노트.md"` |
| `obsidian:active_file_get_path` | **사용자가 현재 옵시디언 화면에서 열어보고 있는 활성 노트 경로 확인** | (파라미터 없음) |
| `obsidian:open_file` | 옵시디언 UI 화면에서 특정 노트를 즉시 포커스하여 열기 | `path`: `"Reports/결과.md"` |
| `obsidian:search_simple` | **볼트 전체 대상 키워드 전문 검색 (Full-text Search)** | `query`: `"키친 사이클"` |
| `obsidian:search_query` | JsonLogic 기반 태그/경로/프론트매터 복합 조건부 검색 | `query`: `{"and": [...]}` |
| `obsidian:tag_list` | 볼트 전체에서 사용 중인 태그 목록 조회 | (파라미터 없음) |
| `obsidian:command_list` | 옵시디언에 등록된 모든 커맨드 팔레트 명령어 목록 조회 | (파라미터 없음) |
| `obsidian:command_execute` | 옵시디언 커맨드 원격 실행 (예: 일일 노트 열기, 퀵스위처 등) | `command_id`: `"daily-notes"` |

---

## 3. Python 헬퍼 CLI 활용 (`obsidian_client.py`)

백그라운드 배치 작업, 파이썬 파이프라인, 또는 터미널 단독 작업 시 내장된 표준 라이브러리 기반 클라이언트를 사용할 수 있습니다:

```bash
# 글로벌 설치 경로:
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py <COMMAND> [OPTIONS]
```

### 주요 커맨드:
```bash
# 1. 서버 상태 및 인증 확인
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py status

# 2. 볼트 파일 목록 조회
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py list
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py list "000. Inbox"

# 3. 노트 내용 조회
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py read "000. Inbox/독서메모.md"

# 4. 현재 활성(열린) 노트 확인
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py active

# 5. 전문 키워드 검색
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py search "키친 사이클"

# 6. 새 노트 생성 / 덮어쓰기
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py write "000. Inbox/AI메모.md" --content "# AI 요약\n\n내용..."
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py write "000. Inbox/AI메모.md" --file "scratch/report.md"

# 7. 기존 노트 끝에 추가 (Append)
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py append "Daily/2026-10-13.md" --content "\n- [x] 작업 완료"

# 8. 특정 헤딩 부분 수정 (Surgical Patch)
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py patch "000. Inbox/독서메모.md" --heading "### 1) 금융장세" --content "수정된 내용..." --action replace

# 9. 옵시디언 UI에서 특정 노트 열기
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py open "000. Inbox/AI메모.md"

# 10. 옵시디언 커맨드 목록 및 실행
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py commands
python ~/.gemini/config/skills/obsidian-manager/scripts/obsidian_client.py exec-command "app:toggle-left-sidebar"
```

---

## 4. 에이전트 작업 모범 사례 (Best Practices)

1. **상대 경로 준수**:
   - 모든 파일 경로는 볼트 루트 기준 상대 경로(예: `000. Inbox/메모.md`)를 사용합니다. 드라이브 문자(`G:\...`)나 절대 경로를 넣지 마십시오.
2. **Surgical Patch 우선 원칙**:
   - 수백 줄에 달하는 방대한 기존 노트를 통째로 `vault_write`로 덮어쓰면 네트워크 오버헤드와 충돌 위험이 큽니다.
   - 특정 섹션이나 헤딩 아래 내용만 갱신할 때는 반드시 `vault_patch` 또는 CLI의 `patch`를 활용하십시오.
3. **현재 컨텍스트(Active Note) 파악**:
   - 사용자가 "지금 보고 있는 노트 요약해줘", "현재 노트에 이 내용 추가해줘"라고 요청할 때는 `obsidian:active_file_get_path` 또는 `active` 명령어로 현재 작업 중인 노트를 즉시 식별합니다.
4. **Frontmatter(YAML) 무결성 유지**:
   - 노트 상단의 YAML Frontmatter(`--- ... ---`)가 포함된 문서를 수정할 때는 프론트매터의 메타데이터 필드가 훼손되지 않도록 주의합니다.
5. **Obsidian 데스크톱 미실행 시 대응**:
   - 연결 거부(`ECONNREFUSED` / `Connection refused`) 에러 발생 시, 사용자에게 옵시디언 앱이 실행되어 있는지와 `Local REST API` 플러그인이 활성화되어 있는지 점검하도록 친절히 안내합니다.
