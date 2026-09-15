# Notion Uploader Global Skill Implementation Plan

이 계획은 로컬 마크다운(.md) 및 텍스트(.txt) 파일을 노션 데이터베이스의 새 페이지로 업로드하는 글로벌 스킬(`notion-uploader`)을 제작하기 위한 것입니다.

## 목표
- 현재 프로젝트 폴더 내(`notion-uploader/SKILL.md`)에 스킬을 제작하여 Git으로 버전 관리.
- 글로벌 설정 파일(`~/.gemini/config/skills.json`)에 프로젝트 경로를 등록하여 글로벌 스킬로 동작하도록 설정.
- **이 스킬을 사용하는 개별 프로젝트의 루트 폴더에 위치한 `.env` 파일에서 Notion Database ID를 읽어오기.**
- 사용자 프롬프트에 따라 동적으로 제목(Title)과 속성(Properties)을 설정하여 노션 데이터베이스에 빈 페이지를 생성 (`API-post-page` 사용).
- 생성된 페이지에 마크다운 파일의 전체 내용을 업데이트 (`API-update-page-markdown` 사용).
- 에러 발생 시 즉시 실패(Fail-fast)하고 상세 로그를 제공.

## User Review Required
> [!IMPORTANT]  
> 스킬이 `c:\Users\maeng-gun\Desktop\python\agy-global-skills\notion-uploader\SKILL.md` 에 생성되며, 글로벌 사용을 위해 `C:\Users\maeng-gun\.gemini\config\skills.json`에 해당 디렉토리가 등록됩니다.

> [!NOTE]  
> 스킬 코드는 에이전트가 실행되는 **현재 작업 디렉토리(개별 프로젝트의 루트 폴더)** 에서 `.env` 파일을 찾도록 작성됩니다.

## Proposed Changes

---

### Skill Implementation (Version Controlled)

#### [NEW] notion-uploader/SKILL.md(file:///c:/Users/maeng-gun/Desktop/python/agy-global-skills/notion-uploader/SKILL.md)
새로운 스킬을 현재 프로젝트 내에 정의합니다.
- **주요 내용**:
  1. 사용자 프롬프트를 분석하여 업로드할 대상 파일 경로 파악 및 제목(Title)/추가 속성(Properties) 결정.
  2. 에이전트가 실행 중인 **대상 프로젝트의 현재 작업 디렉토리**에 있는 `.env` 파일에서 대상 노션 데이터베이스 ID 추출.
  3. `notion-mcp-server`의 `API-post-page`를 호출하여 새 페이지 생성.
  4. 파일 내용을 읽은 후, 생성된 페이지의 `page_id`를 사용하여 `API-update-page-markdown` 호출 (`replace_content` 모드).
  5. 과정 중 오류(API 에러, 파일 읽기 에러 등) 발생 시 작업을 즉각 중지하고 오류 원인을 상세히 보고.

---

### Global Registration

#### [MODIFY/NEW] skills.json(file:///C:/Users/maeng-gun/.gemini/config/skills.json)
글로벌 스킬로 인식되도록 Antigravity 설정에 프로젝트 경로를 등록합니다.
```json
{
  "entries": [
    {
      "path": "c:\\Users\\maeng-gun\\Desktop\\python\\agy-global-skills"
    }
  ]
}
```

## Verification Plan

### Manual Verification
1. `skills.json` 등록 후 에이전트가 글로벌하게 `notion-uploader` 스킬을 인식하는지 확인.
2. 에이전트를 다른 임의의 테스트 프로젝트 폴더로 이동하여 실행.
3. 해당 테스트 프로젝트의 루트 폴더에 `.env` 파일을 만들고 테스트용 `NOTION_DATABASE_ID` 지정.
4. 해당 프로젝트 내에 테스트용 마크다운 파일을 생성한 뒤, 에이전트에게 `test.md 파일을 notion-uploader 스킬을 사용해 업로드해줘. 제목은 '테스트 업로드'로 해줘.` 라고 요청.
5. 노션 데이터베이스에 정상적으로 페이지가 생성되고 본문이 채워지는지 확인.
