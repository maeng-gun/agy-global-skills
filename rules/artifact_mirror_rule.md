<!-- AGY_ARTIFACT_MIRROR_RULE_START -->
# Antigravity Conversation Artifact Mirroring Rule

## Objective
Automatically maintain a persistent, cloud-synchronized dual-save mirror copy of all conversation markdown artifacts (`implementation_plan.md`, `walkthrough.md`, `task.md`, and any user-facing or reviewable markdown artifacts) to Google Drive via local project directory junctions or central general storage.

---

## 1. Trigger Conditions
Apply this rule whenever you:
1. Create a new markdown artifact (e.g., `implementation_plan.md`, `walkthrough.md`, `task.md`, design document, or analysis report).
2. Update or finalize an existing markdown artifact.

---

## 2. Target Path Resolution

### Case A: Working Inside a Project Workspace
When operating within a project workspace (Git repository or local project directory):
1. **Target Mirror Directory**:
   `./AGY_Artifacts/<Session_Title>/`
2. **Target File Path**:
   `./AGY_Artifacts/<Session_Title>/<YYYYMMDD>_<artifact_name>.md`
3. **Transparent Cloud Synchronization**:
   - The `./AGY_Artifacts` directory in each project root is a Windows Directory Junction (`mklink /J`) linked to:
     `G:\내 드라이브\Antigravity_Workspaces\<ProjectName>\AGY_Artifacts` (or detected Google Drive mount).
   - Writing to `./AGY_Artifacts/...` transparently synchronizes the file to Google Drive and other synced PCs.
   - The directory junction is excluded from Git via `.gitignore` (`/AGY_Artifacts/`).

### Case B: Outside a Project Workspace (Global Chat / Scratch / General)
When operating outside of any recognized project repository or in general discussion:
1. **Target Base Path**:
   `G:\내 드라이브\Antigravity_Workspaces\_General\AGY_Artifacts`
   *(If Google Drive is mounted on a different letter or language, use `<GDrive_Root>\Antigravity_Workspaces\_General\AGY_Artifacts`)*
2. **Target File Path**:
   `<GDrive_Root>\Antigravity_Workspaces\_General\AGY_Artifacts\<Session_Title>/<YYYYMMDD>_<artifact_name>.md`

---

## 3. Formatting & Sanitization Specifications

### 3.1 Date Format
- `<YYYYMMDD>`: The current local date in 8-digit format (e.g., `20261023`).

### 3.2 Session Title Sanitization
- Extract `<Session_Title>` from the conversation title, active user topic, or first `# Heading` of the artifact.
- **Sanitization Rules**:
  - Replace Windows-prohibited characters (`\`, `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) with an underscore (`_`).
  - Collapse multiple consecutive whitespace or underscore characters into a single underscore.
  - Trim leading and trailing whitespace, dots (`.`), and underscores.
  - Truncate length to maximum 80 characters to avoid Windows `MAX_PATH` limitations.
  - Fallback if title is empty or uninformative: `Session_<Conversation_ID_First_8_Chars>` or `General_Session`.

### 3.3 Artifact Filename
- Use the base name of the artifact, e.g.:
  - `implementation_plan.md` -> `<YYYYMMDD>_implementation_plan.md`
  - `walkthrough.md` -> `<YYYYMMDD>_walkthrough.md`
  - `task.md` -> `<YYYYMMDD>_task.md`

---

## 4. Execution Protocol
1. Whenever you generate or update an artifact in your primary working location (e.g., `.gemini/antigravity/brain/<conv_id>/` or local workspace), ensure the target mirror folder exists (create if missing).
2. Save or mirror the identical markdown content to the target mirror path.
3. Do not alter or omit your primary task outputs; mirroring is an automatic dual-save operation.
<!-- AGY_ARTIFACT_MIRROR_RULE_END -->
