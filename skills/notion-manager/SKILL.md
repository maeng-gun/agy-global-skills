---
name: notion-manager
description: Uploads markdown or text content and selectively manages (archives/deletes) pages in a Notion database.
---

# Notion Manager Skill

이 스킬은 노션 데이터베이스의 페이지를 업로드하고 특정 조건에 따라 안전하게 아카이브(삭제) 관리하는 글로벌 스킬입니다.
Markdown 문서를 노션 블록(헤딩, 목록, 코드블록, 표, 인용구 등)으로 정밀하게 변환하여 청킹(Chunking) 업로드하며, 날짜 및 주제(Relation) 등의 조건에 부합하는 기존 페이지를 2중 안전 검증(Safety Guard)을 통해 선별적으로 정리합니다.

## 필수 구성요소 (Prerequisites)
이 스킬을 사용하는 프로젝트 루트 디렉토리의 `.env` 파일에 다음 환경 변수가 정의되어 있어야 합니다:
- `NOTION_API_KEY`: Notion 내부 통합 토큰 (Secret API Key)
- `NOTION_DB_ID`: 대상 Notion 데이터베이스 ID

---

## 1. 노션 페이지 업로드 (Upload)

산출물(마크다운, 리포트, 요약 등)을 노션 데이터베이스에 새 페이지로 업로드할 때 사용합니다.

### 실행 절차:
1. **임시 마크다운 파일 저장**:
   업로드할 본문을 표준 Markdown 규격으로 구조화하여 `scratch/notion_upload_temp.md`로 저장합니다.
2. **임시 메타데이터 JSON 저장**:
   페이지 속성을 정의하는 `scratch/notion_upload_meta.json`을 작성합니다:
   ```json
   {
     "title": "<페이지 제목>",
     "icon": "📊",
     "status": "미처리",
     "category": "AI생성",
     "date": "YYYY-MM-DD",
     "topic_page_id": "<선택: 연계할 주제 페이지 UUID>"
   }
   ```
3. **업로드 스크립트 실행**:
   ```bash
   # 가상환경 또는 시스템 python을 사용하는 경우:
   python ~/.gemini/config/skills/notion-manager/scripts/notion_manager.py upload

   # 또는 uv 환경인 경우:
   uv run ~/.gemini/config/skills/notion-manager/scripts/notion_manager.py upload
   ```
   *(업로드 성공 시 생성된 Notion 페이지 URL이 출력되며, scratch 임시 파일은 자동 정리됩니다.)*

---

## 2. 노션 페이지 선별 삭제/아카이브 (Delete)

재분석 또는 갱신 시, 특정 날짜 및 주제에 해당하는 기존 노션 페이지만 골라내어 안전하게 아카이브(휴지통 이동)합니다.

> [!WARNING]
> **오삭제 방지 안전 보호 (Safety Guard)**:
> 날짜(`--date`)만 단독으로 지정하고 추가 필터(`--topic-id`, `--property` 등)가 없으면, 동일 날짜에 등록된 타 업무나 사용자의 다른 페이지까지 일괄 삭제되는 대형 사고가 발생할 수 있습니다.
> 따라서 `delete` 실행 시에는 **반드시 대상 주제 ID(`--topic-id`)를 지정**하거나, `scratch/notion_upload_meta.json`에 `topic_page_id`가 포함되어 있어야 합니다. (전체 삭제를 의도한 경우에만 `--force-all-topics` 명시 필요)

### 실행 절차:
```bash
# 특정 날짜 및 주제(Topic UUID)를 지정하여 삭제
python ~/.gemini/config/skills/notion-manager/scripts/notion_manager.py delete --date <YYYY-MM-DD> --topic-id <TOPIC_UUID> --topic-name "<표시이름>"

# scratch/notion_upload_meta.json 의 date 및 topic_page_id 를 자동으로 읽어와 삭제
python ~/.gemini/config/skills/notion-manager/scripts/notion_manager.py delete --meta scratch/notion_upload_meta.json

# 실제 삭제 전 대상 페이지만 미리 확인 (Dry-Run)
python ~/.gemini/config/skills/notion-manager/scripts/notion_manager.py delete --date <YYYY-MM-DD> --topic-id <TOPIC_UUID> --dry-run
```

---

## 3. 서브커맨드별 CLI 옵션

### `upload`
- `--content <path>`: 마크다운 파일 경로 (기본값: `scratch/notion_upload_temp.md`)
- `--meta <path>`: 메타데이터 JSON 경로 (기본값: `scratch/notion_upload_meta.json`)
- `--title <text>`: 제목 오버라이드
- `--icon <emoji>`: 아이콘 이모지 오버라이드
- `--status <name>`: 상태 속성값 오버라이드
- `--category <name>`: 구분/카테고리 속성값 오버라이드
- `--date <YYYY-MM-DD>`: 날짜 속성값 오버라이드
- `--topic-id <UUID>`: 주제 관계형 속성 페이지 ID 오버라이드
- `--no-cleanup`: 업로드 후 scratch 임시 파일을 삭제하지 않고 보존

### `delete`
- `--date <YYYY-MM-DD>`: 대상 날짜 (필수, `YYYYMMDD` 또는 `YYYY-MM-DD`)
- `--topic-id <UUID>`: 필터링할 주제 관계형 페이지 UUID (오삭제 방지 핵심 안전장치)
- `--topic-name <name>`: 로그 출력용 주제 표시명
- `--relation-prop <name>`: 관계형 속성 이름 지정 (미지정 시 DB에서 '주제', 'Topic' 등 자동 탐색)
- `--meta <path>`: 메타데이터 JSON 파일 경로 (기본값: `scratch/notion_upload_meta.json`)
- `--force-all-topics`: 주제 필터 없이 해당 일자의 모든 페이지를 삭제 허용 (주의)
- `--dry-run`: 실제 아카이브를 실행하지 않고 일치하는 대상 페이지만 출력
