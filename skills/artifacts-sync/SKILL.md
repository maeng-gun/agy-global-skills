---
name: artifacts-sync
description: Synchronizes and migrates Antigravity conversation artifacts to Google Drive, manages directory junctions, and configures dual-save rules.
---

# Antigravity Artifacts Synchronization Skill

This skill synchronizes Antigravity conversation artifacts (`implementation_plan.md`, `walkthrough.md`, `task.md`, and other root markdown artifacts) across multiple PCs by linking local project workspaces to Google Drive via Windows NTFS Directory Junctions (`mklink /J`), enforcing global dual-save mirroring rules, and migrating historical sessions.

---

## Chat Triggers

Activate this skill when the user sends any of the following queries or commands in Korean or English:

### Korean Triggers
- "아티팩트 동기화 세팅해줘"
- "아티팩트 동기화"
- "아티팩트 마이그레이션"
- "구글 드라이브 아티팩트 연동해줘"
- "아티팩트 동기화 상태 확인해줘"
- "작업 산출물 동기화"

### English Triggers
- `/artifacts-sync`
- `sync artifacts`
- `setup artifacts sync`
- `migrate artifacts`
- `sync brain artifacts`

---

## What This Skill Does

1. **Global Dual-Save Rule Deployment**:
   - Ensures `~/.gemini/config/GEMINI.md` contains the Antigravity conversation artifact mirroring rule (delimited by `<!-- AGY_ARTIFACT_MIRROR_RULE_START -->` and `<!-- AGY_ARTIFACT_MIRROR_RULE_END -->`).
   - Ensures all future sessions dual-save markdown artifacts to `./AGY_Artifacts/<Session_Title>/<YYYYMMDD>_<filename>.md`.

2. **Windows Directory Junction Creation**:
   - For all local Git projects (in `~/Documents` or configured in Antigravity), establishes an NTFS Directory Junction from `<ProjectRoot>\AGY_Artifacts` to `<GDrive_Root>\Antigravity_Workspaces\<ProjectName>\AGY_Artifacts`.
   - Any file saved to `./AGY_Artifacts` is transparently synchronized to Google Drive in real-time.

3. **Git Ignore Configuration**:
   - Automatically appends `/AGY_Artifacts/` to each project's `.gitignore` if not already present.

4. **Historical Artifact Migration**:
   - Scans `~/.gemini/antigravity/brain/<conversation_id>` and `conversation_summaries.db`.
   - Migrates historical markdown artifacts into their corresponding project's Google Drive workspace (or `_General` for non-project sessions).
   - Resolves conflicts non-destructively using SHA-256 hash comparison.

---

## Execution Instructions for the AI Agent

When triggered by the user, follow these steps:

### Step 1: Run the One-Click PowerShell Launcher
Execute the PowerShell setup script using `run_command`:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\Documents\agy-global-skills\tools\artifacts_sync\setup_artifacts_sync.ps1"
```

*Note: If the user specifically requested a simulation, test, or dry-run, pass the `-DryRun` flag:*
```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\Documents\agy-global-skills\tools\artifacts_sync\setup_artifacts_sync.ps1" -DryRun
```

*Alternatively, if running via the Python engine directly:*
```powershell
python "$HOME\Documents\agy-global-skills\tools\artifacts_sync\sync_artifacts.py" --setup-junctions --migrate
```

### Step 2: Parse and Present Results
Review the console output from the command and provide a clear, user-friendly summary:
- **Google Drive Location**: Show detected Google Drive path (e.g. `G:\내 드라이브\Antigravity_Workspaces`).
- **Junction Status**: List local projects linked (e.g. `my_asset_js`, `macro_analyzer`, `my_asset`, `agy-global-skills`, `workspace-automation`).
- **Git Ignore Status**: Confirm `/AGY_Artifacts/` added or already present in `.gitignore`.
- **Migration Count**: Number of historical artifacts copied, skipped (identical), or conflict-resolved.
- **Rule & Skill Status**: Confirmation that global mirroring rule in `~/.gemini/config/GEMINI.md` and custom skill are active.
