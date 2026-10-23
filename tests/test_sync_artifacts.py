"""
Automated 4-Tier Test Suite for Antigravity Artifact Synchronization and Migration Toolkit.

Tiers:
- Tier 1: Feature Coverage (>=5 test cases per feature for GDrive detection, Junction management,
          Git ignore, Brain DB extraction, SHA-256 conflict resolution, CLI arguments,
          Project discovery, and Multi-PC Portability static checks)
- Tier 2: Boundary & Corner Cases (empty session titles, Korean UTF-8 characters,
          Windows illegal characters \\/:*?"<>|, missing .metadata.json, pre-existing junction vs dir collision,
          missing target GDrive folder, nested repos like macro_analyzer\\macro_analyzer)
- Tier 3: Cross-Feature Combinations (junction setup + migration + conflict handling in sequential passes)
- Tier 4: Real-world Acceptance Scenarios (greenfield PC setup, 3x repeated idempotency, multi-PC conflict simulation)

Dependencies: Pure Python standard library (unittest, tempfile, pathlib, sqlite3, subprocess, os, sys, hashlib, json, shutil, re).
"""

import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

# Resolve repo root and script path (with staging fallback)
REPO_ROOT = pathlib.Path("C:/Users/infomax/Documents/agy-global-skills")
DOCS_SCRIPT = REPO_ROOT / "tools" / "artifacts_sync" / "sync_artifacts.py"
STAGING_SCRIPT = pathlib.Path("C:/Users/infomax/.gemini/antigravity/scratch/agy_global_skills_staging/tools/artifacts_sync/sync_artifacts.py")
SCRIPT_PATH = DOCS_SCRIPT if DOCS_SCRIPT.exists() else STAGING_SCRIPT

DOCS_TOOLS = REPO_ROOT / "tools" / "artifacts_sync"
STAGING_TOOLS = pathlib.Path("C:/Users/infomax/.gemini/antigravity/scratch/agy_global_skills_staging/tools/artifacts_sync")
TOOLS_DIR = DOCS_TOOLS if DOCS_TOOLS.exists() else STAGING_TOOLS


def run_cmd(cmd, env=None, check=True):
    """Run command with UTF-8 encoding and return CompletedProcess."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env or os.environ.copy(),
        check=check,
    )


def compute_sha256(path: pathlib.Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class SandboxEnvironment:
    """Manages an isolated mock environment for opaque-box testing."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.home = root / "mock_home"
        self.documents = self.home / "Documents"
        self.localappdata = root / "mock_localappdata"
        self.gemini_config = self.home / ".gemini" / "config"
        self.projects_config_dir = self.gemini_config / "projects"
        self.brain_dir = self.home / ".gemini" / "antigravity" / "brain"
        self.db_dir = self.home / ".gemini" / "antigravity"
        self.db_path = self.db_dir / "conversation_summaries.db"
        self.gdrive_root = root / "mock_gdrive"
        self.gdrive_user_root = self.gdrive_root / "내 드라이브"
        self.workspaces_root = self.gdrive_user_root / "Antigravity_Workspaces"

        # Create base hierarchy
        for d in [
            self.documents,
            self.projects_config_dir,
            self.brain_dir,
            self.db_dir,
            self.workspaces_root,
            self.localappdata / "Google" / "DriveFS",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def get_env(self):
        """Return environment dictionary overriding home and localappdata."""
        env = os.environ.copy()
        env["USERPROFILE"] = str(self.home)
        env["HOME"] = str(self.home)
        env["LOCALAPPDATA"] = str(self.localappdata)
        return env

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT "",
                preview TEXT NOT NULL DEFAULT "",
                step_count INTEGER NOT NULL DEFAULT 0,
                last_modified_time DATETIME NOT NULL,
                workspace_uris TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT "",
                source TEXT NOT NULL DEFAULT "",
                project_id TEXT NOT NULL DEFAULT "",
                agent_name TEXT NOT NULL DEFAULT "",
                parent_conversation_id TEXT NOT NULL DEFAULT "",
                nesting_depth INTEGER NOT NULL DEFAULT 0,
                battle_id TEXT NOT NULL DEFAULT "",
                winning_conversation_id TEXT NOT NULL DEFAULT "",
                not_fully_idle NUMERIC NOT NULL DEFAULT 0,
                killed NUMERIC NOT NULL DEFAULT 0,
                last_user_input_time DATETIME NOT NULL,
                last_user_input_step_index INTEGER NOT NULL DEFAULT -1,
                app_data_dir TEXT NOT NULL DEFAULT "",
                raw_summary BLOB,
                group_id TEXT NOT NULL DEFAULT ""
            );
            """
        )
        conn.commit()
        conn.close()

    def add_project(self, name: str, uuid_str: str, relative_path: str = None, git_init: bool = True):
        """Add a mock Git project in Documents and register in projects JSON."""
        proj_dir = self.documents / (relative_path or name)
        proj_dir.mkdir(parents=True, exist_ok=True)
        if git_init:
            run_cmd(["git", "init", str(proj_dir)])
            gi = proj_dir / ".gitignore"
            if not gi.exists():
                gi.write_text("# initial gitignore\n.env\n", encoding="utf-8")

        drive = proj_dir.drive.lower().replace(":", "%3A")
        clean_path = str(proj_dir).replace("\\", "/").split(":", 1)[-1]
        folder_uri = f"file:///{drive}{clean_path}"

        config_data = {
            "name": name,
            "folderUri": folder_uri,
        }
        cfg_file = self.projects_config_dir / f"{uuid_str}.json"
        cfg_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
        return proj_dir

    def add_session(
        self,
        conv_id: str,
        title: str,
        preview: str,
        project_id: str,
        last_modified: str = "2026-08-20 12:00:00.000000+00:00",
        workspace_uris: str = "",
        md_files: dict = None,
    ):
        """Add a mock session in DB and brain folder."""
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO conversation_summaries (
                conversation_id, title, preview, last_modified_time, workspace_uris,
                last_user_input_time, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (conv_id, title, preview, last_modified, workspace_uris, last_modified, project_id),
        )
        conn.commit()
        conn.close()

        session_brain = self.brain_dir / conv_id
        session_brain.mkdir(parents=True, exist_ok=True)

        if md_files:
            for fname, info in md_files.items():
                content, updated_at = info if isinstance(info, tuple) else (info, None)
                fpath = session_brain / fname
                fpath.write_text(content, encoding="utf-8")
                if updated_at:
                    meta_path = session_brain / f"{fname}.metadata.json"
                    meta_data = {
                        "updatedAt": updated_at,
                        "summary": "Mock summary",
                        "userFacing": True,
                        "requestFeedback": False,
                    }
                    meta_path.write_text(json.dumps(meta_data), encoding="utf-8")
        return session_brain

    def run_sync(self, extra_args=None, check=True):
        """Invoke sync_artifacts.py with standard sandbox parameters."""
        if not SCRIPT_PATH.exists():
            raise unittest.SkipTest(f"sync_artifacts.py not found at {SCRIPT_PATH}")

        args = [sys.executable, str(SCRIPT_PATH)]
        if extra_args:
            args.extend(extra_args)

        return run_cmd(args, env=self.get_env(), check=check)


class BaseSandboxTestCase(unittest.TestCase):
    """Base test case providing clean temporary directory and sandbox."""

    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_root = pathlib.Path(self.temp_dir_obj.name)
        self.sandbox = SandboxEnvironment(self.temp_root)

    def tearDown(self):
        try:
            self.temp_dir_obj.cleanup()
        except Exception:
            pass


# =========================================================================
# TIER 1: Feature Coverage (>=5 test cases per feature)
# =========================================================================

class TestTier1GDriveDetection(BaseSandboxTestCase):
    """Tier 1 - Feature 1: Dynamic Google Drive Mount Detection."""

    def test_gdrive_direct_override_cli(self):
        """1.1 Verify --gdrive-root CLI argument overrides detection."""
        custom_gdrive = self.temp_root / "custom_gdrive"
        custom_gdrive.mkdir(parents=True, exist_ok=True)
        res = self.sandbox.run_sync([
            "--gdrive-root", str(custom_gdrive),
            "--dry-run"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn(str(custom_gdrive), res.stdout)

    def test_gdrive_drivefs_db_detection(self):
        """1.2 Verify detection via DriveFS root_preference_sqlite.db media table."""
        mock_drive_root = self.temp_root / "fs_drive"
        mock_drive_root.mkdir(parents=True, exist_ok=True)
        (mock_drive_root / "내 드라이브").mkdir(parents=True, exist_ok=True)

        db_path = self.sandbox.localappdata / "Google" / "DriveFS" / "root_preference_sqlite.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE media (name TEXT, last_mount_point TEXT);")
        conn.execute("INSERT INTO media VALUES ('Google Drive', ?);", (str(mock_drive_root),))
        conn.commit()
        conn.close()

        res = self.sandbox.run_sync(["--dry-run"])
        self.assertEqual(res.returncode, 0)
        self.assertTrue(str(mock_drive_root) in res.stdout or "내 드라이브" in res.stdout)

    def test_gdrive_localized_folder_korean(self):
        """1.3 Verify probe finds Korean localized directory '내 드라이브'."""
        korean_gdrive = self.temp_root / "gdrive_ko"
        ko_user_dir = korean_gdrive / "내 드라이브"
        ko_user_dir.mkdir(parents=True, exist_ok=True)

        res = self.sandbox.run_sync([
            "--gdrive-root", str(korean_gdrive),
            "--dry-run"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("내 드라이브", res.stdout)

    def test_gdrive_localized_folder_english(self):
        """1.4 Verify probe finds English localized directory 'My Drive' when present."""
        eng_gdrive = self.temp_root / "gdrive_en"
        en_user_dir = eng_gdrive / "My Drive"
        en_user_dir.mkdir(parents=True, exist_ok=True)

        res = self.sandbox.run_sync([
            "--gdrive-root", str(eng_gdrive),
            "--dry-run"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue("My Drive" in res.stdout or str(eng_gdrive) in res.stdout)

    def test_gdrive_mount_not_found_error(self):
        """1.5 Verify non-zero exit code and clear error when GDrive cannot be located."""
        empty_root = self.temp_root / "nowhere"
        res = self.sandbox.run_sync(
            ["--gdrive-root", str(empty_root), "--setup-junctions"],
            check=False
        )
        self.assertNotEqual(res.returncode, 0)
        output = res.stderr + res.stdout
        self.assertTrue("not found" in output.lower() or "error" in output.lower() or "drive" in output.lower())


class TestTier1ProjectDiscovery(BaseSandboxTestCase):
    """Tier 1 - Feature 2: Project Discovery & Nested Repos."""

    def test_discover_from_projects_json(self):
        """2.1 Discover project mapped in ~/.gemini/config/projects/*.json."""
        self.sandbox.add_project("proj_alpha", "uuid-alpha-111")
        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--dry-run",
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("proj_alpha", res.stdout)

    def test_discover_fallback_antigravity_config(self):
        """2.2 Fallback discovery in ~/.gemini/antigravity/config/projects/."""
        fallback_dir = self.sandbox.home / ".gemini" / "antigravity" / "config" / "projects"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        proj_dir = self.sandbox.documents / "proj_fallback"
        proj_dir.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "init", str(proj_dir)])

        cfg_data = {"name": "proj_fallback", "folderUri": f"file:///{str(proj_dir).replace('\\', '/')}"}
        (fallback_dir / "fallback-uuid.json").write_text(json.dumps(cfg_data), encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--dry-run",
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("proj_fallback", res.stdout)

    def test_discover_from_documents_scan(self):
        """2.3 Discover unmapped Git repository by scanning Documents directory."""
        unmapped_proj = self.sandbox.documents / "unmapped_git_proj"
        unmapped_proj.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "init", str(unmapped_proj)])

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--dry-run",
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("unmapped_git_proj", res.stdout)

    def test_nested_repo_resolution(self):
        """2.4 Correctly resolve nested Git repository like macro_analyzer/macro_analyzer."""
        outer = self.sandbox.documents / "macro_analyzer"
        inner = outer / "macro_analyzer"
        inner.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "init", str(inner)])

        self.sandbox.add_project(
            "macro_analyzer",
            "uuid-macro-999",
            relative_path="macro_analyzer/macro_analyzer",
            git_init=False
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--dry-run",
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("macro_analyzer", res.stdout)

    def test_permission_error_and_symlink_resilience(self):
        """2.5 Resilience against system reparse points or restricted folders."""
        restricted = self.sandbox.documents / "System_Special_Dir"
        restricted.mkdir(parents=True, exist_ok=True)
        self.sandbox.add_project("healthy_proj", "uuid-healthy-001")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--dry-run",
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertIn("healthy_proj", res.stdout)


class TestTier1JunctionManagement(BaseSandboxTestCase):
    """Tier 1 - Feature 3: Windows Directory Junction Engine."""

    def test_junction_creation_when_target_preexists(self):
        """3.1 Create junction when Google Drive target exists."""
        proj = self.sandbox.add_project("proj_junc1", "uuid-junc-1")
        target_dir = self.sandbox.workspaces_root / "proj_junc1" / "AGY_Artifacts"
        target_dir.mkdir(parents=True, exist_ok=True)

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        link = proj / "AGY_Artifacts"
        self.assertTrue(link.exists())
        self.assertTrue(link.is_junction() or link.is_dir())

    def test_junction_ensures_gdrive_target_created_first(self):
        """3.2 Ensure Google Drive target folder is created before mklink /J."""
        proj = self.sandbox.add_project("proj_junc2", "uuid-junc-2")
        target_dir = self.sandbox.workspaces_root / "proj_junc2" / "AGY_Artifacts"
        self.assertFalse(target_dir.exists())

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue(target_dir.exists())
        link = proj / "AGY_Artifacts"
        self.assertTrue(link.exists())

    def test_junction_idempotent_existing_correct_target(self):
        """3.3 Idempotent execution when junction already points to target."""
        proj = self.sandbox.add_project("proj_junc3", "uuid-junc-3")
        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        link = proj / "AGY_Artifacts"
        self.assertTrue(link.exists())

        res2 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res2.returncode, 0)
        self.assertTrue(link.exists())

    def test_junction_replaces_wrong_target(self):
        """3.4 Replace stale junction pointing to wrong target."""
        proj = self.sandbox.add_project("proj_junc4", "uuid-junc-4")
        wrong_target = self.temp_root / "wrong_place"
        wrong_target.mkdir(parents=True, exist_ok=True)
        link = proj / "AGY_Artifacts"
        run_cmd(["cmd", "/c", "mklink", "/J", str(link), str(wrong_target)])
        self.assertTrue(link.is_junction())

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue(link.exists())
        correct_target = self.sandbox.workspaces_root / "proj_junc4" / "AGY_Artifacts"
        self.assertTrue(correct_target.exists())

    def test_junction_preexisting_directory_collision_migration(self):
        """3.5 Handle pre-existing regular directory by migrating contents and converting to junction."""
        proj = self.sandbox.add_project("proj_junc5", "uuid-junc-5")
        local_dir = proj / "AGY_Artifacts"
        local_dir.mkdir(parents=True, exist_ok=True)
        test_file = local_dir / "pre_existing.txt"
        test_file.write_text("important data", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        link = proj / "AGY_Artifacts"
        self.assertTrue(link.exists())

        gdrive_file = self.sandbox.workspaces_root / "proj_junc5" / "AGY_Artifacts" / "pre_existing.txt"
        self.assertTrue(gdrive_file.exists())
        self.assertEqual(gdrive_file.read_text(encoding="utf-8"), "important data")


class TestTier1GitIgnore(BaseSandboxTestCase):
    """Tier 1 - Feature 4: Git Ignore Management."""

    def test_gitignore_appends_pattern(self):
        """4.1 Append /AGY_Artifacts/ when not present in .gitignore."""
        proj = self.sandbox.add_project("proj_gi1", "uuid-gi-1")
        gi = proj / ".gitignore"
        gi.write_text(".env\nnode_modules/\n", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        content = gi.read_text(encoding="utf-8")
        self.assertIn("AGY_Artifacts", content)

    def test_gitignore_idempotent_exact_match(self):
        """4.2 Idempotent when /AGY_Artifacts/ already present."""
        proj = self.sandbox.add_project("proj_gi2", "uuid-gi-2")
        gi = proj / ".gitignore"
        gi.write_text(".env\n/AGY_Artifacts/\n", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        content = gi.read_text(encoding="utf-8")
        self.assertEqual(content.count("AGY_Artifacts"), 1)

    def test_gitignore_idempotent_relative_match(self):
        """4.3 Idempotent when AGY_Artifacts/ (without leading slash) present."""
        proj = self.sandbox.add_project("proj_gi3", "uuid-gi-3")
        gi = proj / ".gitignore"
        gi.write_text(".env\nAGY_Artifacts/\n", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        content = gi.read_text(encoding="utf-8")
        self.assertEqual(content.count("AGY_Artifacts"), 1)

    def test_gitignore_preserves_existing_content(self):
        """4.4 Preserves all existing .gitignore rules."""
        proj = self.sandbox.add_project("proj_gi4", "uuid-gi-4")
        gi = proj / ".gitignore"
        initial = "# Custom Rules\n*.log\nsecrets.json\n"
        gi.write_text(initial, encoding="utf-8")

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        content = gi.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(initial))
        self.assertIn("AGY_Artifacts", content)

    def test_gitignore_created_if_missing(self):
        """4.5 Creates .gitignore with /AGY_Artifacts/ if file does not exist."""
        proj = self.sandbox.add_project("proj_gi5", "uuid-gi-5", git_init=False)
        run_cmd(["git", "init", str(proj)])
        gi = proj / ".gitignore"
        if gi.exists():
            gi.unlink()

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertTrue(gi.exists())
        self.assertIn("AGY_Artifacts", gi.read_text(encoding="utf-8"))


class TestTier1BrainDBExtraction(BaseSandboxTestCase):
    """Tier 1 - Feature 5: Brain DB Schema & Title/Date Extraction."""

    def test_title_extracted_from_db_title(self):
        """5.1 Session title extracted directly from conversation_summaries.title."""
        self.sandbox.add_project("proj_db1", "uuid-db-1")
        self.sandbox.add_session(
            "sess-title-1",
            title="Clean Explicit Title",
            preview="Some preview",
            project_id="uuid-db-1",
            md_files={"implementation_plan.md": ("# Title Plan", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_db1" / "AGY_Artifacts" / "Clean Explicit Title"
        self.assertTrue(target_folder.exists())

    def test_title_fallback_to_preview_when_title_empty(self):
        """5.2 Title falls back to preview first line when title is empty."""
        self.sandbox.add_project("proj_db2", "uuid-db-2")
        self.sandbox.add_session(
            "sess-title-2",
            title="",
            preview="Preview Extracted Title\nSecond line of preview",
            project_id="uuid-db-2",
            md_files={"task.md": ("# Task details", "2026-08-21T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_db2" / "AGY_Artifacts" / "Preview Extracted Title"
        self.assertTrue(target_folder.exists())

    def test_title_fallback_to_h1_when_preview_empty(self):
        """5.3 Title falls back to first # H1 heading in markdown when title and preview are empty."""
        self.sandbox.add_project("proj_db3", "uuid-db-3")
        self.sandbox.add_session(
            "sess-title-3",
            title="",
            preview="",
            project_id="uuid-db-3",
            md_files={"implementation_plan.md": ("# Heading One Session Title\nPlan content", "2026-08-22T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_db3" / "AGY_Artifacts" / "Heading One Session Title"
        self.assertTrue(target_folder.exists())

    def test_title_fallback_to_session_id(self):
        """5.4 Title falls back to Session_<conv_id[:8]> when title, preview, and H1 are missing."""
        conv_id = "12345678-abcd-ef01-2345-6789abcdef01"
        self.sandbox.add_project("proj_db4", "uuid-db-4")
        self.sandbox.add_session(
            conv_id,
            title="",
            preview="",
            project_id="uuid-db-4",
            md_files={"walkthrough.md": ("No headings here, just raw text.", "2026-08-23T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        expected_folder_prefix = f"Session_{conv_id[:8]}"
        proj_artifacts = self.sandbox.workspaces_root / "proj_db4" / "AGY_Artifacts"
        matches = [d for d in proj_artifacts.iterdir() if d.is_dir() and conv_id[:8] in d.name]
        self.assertTrue(len(matches) > 0, f"Expected folder matching {expected_folder_prefix}")

    def test_date_extraction_hierarchy(self):
        """5.5 Date extraction prioritizes updatedAt from .metadata.json over db last_modified."""
        self.sandbox.add_project("proj_db5", "uuid-db-5")
        self.sandbox.add_session(
            "sess-date-1",
            title="Date Hierarchy Test",
            preview="",
            project_id="uuid-db-5",
            last_modified="2025-01-01 00:00:00.000000+00:00",
            md_files={"walkthrough.md": ("Content", "2026-08-28T14:30:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_db5" / "AGY_Artifacts" / "Date Hierarchy Test"
        expected_file = target_folder / "20260828_walkthrough.md"
        self.assertTrue(expected_file.exists())


class TestTier1ArtifactMigration(BaseSandboxTestCase):
    """Tier 1 - Feature 6: Historical Artifact Migration."""

    def test_migrates_root_md_files(self):
        """6.1 Migrates all root markdown files in session."""
        self.sandbox.add_project("proj_mig1", "uuid-mig-1")
        self.sandbox.add_session(
            "sess-mig-1",
            title="Multi File Session",
            preview="",
            project_id="uuid-mig-1",
            md_files={
                "implementation_plan.md": ("Plan content", "2026-08-20T10:00:00Z"),
                "walkthrough.md": ("Walkthrough content", "2026-08-20T10:00:00Z"),
                "task.md": ("Task content", "2026-08-20T10:00:00Z"),
            }
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_mig1" / "AGY_Artifacts" / "Multi File Session"
        self.assertTrue((target_folder / "20260820_implementation_plan.md").exists())
        self.assertTrue((target_folder / "20260820_walkthrough.md").exists())
        self.assertTrue((target_folder / "20260820_task.md").exists())

    def test_ignores_non_markdown_files(self):
        """6.2 Ignores non-markdown files like .webm and .csv in session."""
        self.sandbox.add_project("proj_mig2", "uuid-mig-2")
        session_brain = self.sandbox.add_session(
            "sess-mig-2",
            title="Binary Files Session",
            preview="",
            project_id="uuid-mig-2",
            md_files={"task.md": ("Task", "2026-08-20T10:00:00Z")}
        )
        (session_brain / "recording.webm").write_bytes(b"\x1a\x45\xdf\xa3")
        (session_brain / "data.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_mig2" / "AGY_Artifacts" / "Binary Files Session"
        self.assertFalse((target_folder / "recording.webm").exists())
        self.assertFalse((target_folder / "20260820_recording.webm").exists())
        self.assertFalse((target_folder / "data.csv").exists())

    def test_ignores_subdirectories(self):
        """6.3 Ignores subdirectories inside brain session folder."""
        self.sandbox.add_project("proj_mig3", "uuid-mig-3")
        session_brain = self.sandbox.add_session(
            "sess-mig-3",
            title="Subdir Session",
            preview="",
            project_id="uuid-mig-3",
            md_files={"task.md": ("Task", "2026-08-20T10:00:00Z")}
        )
        sub = session_brain / ".system_generated"
        sub.mkdir()
        (sub / "nested.md").write_text("nested artifact", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_folder = self.sandbox.workspaces_root / "proj_mig3" / "AGY_Artifacts" / "Subdir Session"
        self.assertFalse((target_folder / ".system_generated").exists())
        self.assertFalse((target_folder / "20260820_nested.md").exists())

    def test_outside_of_project_mapped_to_general(self):
        """6.4 Outside-of-project session migrated to _General/AGY_Artifacts/."""
        self.sandbox.add_session(
            "sess-outside-1",
            title="Outside General Session",
            preview="",
            project_id="outside-of-project",
            md_files={"implementation_plan.md": ("Global Plan", "2026-08-25T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_file = (
            self.sandbox.workspaces_root
            / "_General"
            / "AGY_Artifacts"
            / "Outside General Session"
            / "20260825_implementation_plan.md"
        )
        self.assertTrue(target_file.exists())

    def test_destination_path_structure(self):
        """6.5 Destination adheres strictly to <GDrive>/Antigravity_Workspaces/<Proj>/AGY_Artifacts/<Title>/<YYYYMMDD>_<file>."""
        self.sandbox.add_project("sample_proj", "uuid-sample-1")
        self.sandbox.add_session(
            "sess-path-1",
            title="Structure Check",
            preview="",
            project_id="uuid-sample-1",
            md_files={"task.md": ("Content", "2026-08-29T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        expected = (
            self.sandbox.workspaces_root
            / "sample_proj"
            / "AGY_Artifacts"
            / "Structure Check"
            / "20260829_task.md"
        )
        self.assertTrue(expected.exists())


class TestTier1ConflictResolution(BaseSandboxTestCase):
    """Tier 1 - Feature 7: Multi-PC Merging & SHA-256 Conflict Resolution."""

    def test_new_file_copied_cleanly(self):
        """7.1 New file copied when destination does not exist."""
        self.sandbox.add_project("proj_cr1", "uuid-cr-1")
        self.sandbox.add_session(
            "sess-cr-1",
            title="New File Sync",
            preview="",
            project_id="uuid-cr-1",
            md_files={"plan.md": ("Initial Content", "2026-08-20T10:00:00Z")}
        )

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        dest = self.sandbox.workspaces_root / "proj_cr1" / "AGY_Artifacts" / "New File Sync" / "20260820_plan.md"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(encoding="utf-8"), "Initial Content")

    def test_identical_file_skipped_without_duplicate(self):
        """7.2 Identical SHA-256 skipped without duplicate copy."""
        self.sandbox.add_project("proj_cr2", "uuid-cr-2")
        self.sandbox.add_session(
            "sess-cr-2",
            title="Identical Sync",
            preview="",
            project_id="uuid-cr-2",
            md_files={"plan.md": ("Exact Content", "2026-08-20T10:00:00Z")}
        )

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        target_dir = self.sandbox.workspaces_root / "proj_cr2" / "AGY_Artifacts" / "Identical Sync"
        files_after_1 = list(target_dir.iterdir())
        self.assertEqual(len(files_after_1), 1)

        res2 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res2.returncode, 0)
        files_after_2 = list(target_dir.iterdir())
        self.assertEqual(len(files_after_2), 1)

    def test_conflicting_content_creates_hash_suffixed_file(self):
        """7.3 Conflicting content preserves destination and writes source to hash suffixed file."""
        self.sandbox.add_project("proj_cr3", "uuid-cr-3")
        self.sandbox.add_session(
            "sess-cr-3",
            title="Conflict Session",
            preview="",
            project_id="uuid-cr-3",
            md_files={"plan.md": ("Version A from PC-A", "2026-08-20T10:00:00Z")}
        )

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        target_dir = self.sandbox.workspaces_root / "proj_cr3" / "AGY_Artifacts" / "Conflict Session"
        base_file = target_dir / "20260820_plan.md"
        self.assertEqual(base_file.read_text(encoding="utf-8"), "Version A from PC-A")

        brain_file = self.sandbox.brain_dir / "sess-cr-3" / "plan.md"
        new_content = "Version B from PC-B with different changes"
        brain_file.write_text(new_content, encoding="utf-8")
        source_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()[:8]

        res2 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res2.returncode, 0)

        self.assertEqual(base_file.read_text(encoding="utf-8"), "Version A from PC-A")

        files = list(target_dir.glob("20260820_plan_*.md"))
        self.assertTrue(len(files) >= 1)
        conflict_file = files[0]
        self.assertIn(source_hash, conflict_file.name)
        self.assertEqual(conflict_file.read_text(encoding="utf-8"), new_content)

    def test_multiple_distinct_conflicts(self):
        """7.4 Multiple distinct conflicts produce separate hash-suffixed files."""
        self.sandbox.add_project("proj_cr4", "uuid-cr-4")
        self.sandbox.add_session(
            "sess-cr-4",
            title="Multi Conflict",
            preview="",
            project_id="uuid-cr-4",
            md_files={"plan.md": ("Original", "2026-08-20T10:00:00Z")}
        )

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        target_dir = self.sandbox.workspaces_root / "proj_cr4" / "AGY_Artifacts" / "Multi Conflict"

        brain_file = self.sandbox.brain_dir / "sess-cr-4" / "plan.md"
        brain_file.write_text("Update from PC-B", encoding="utf-8")
        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])

        brain_file.write_text("Update from PC-C", encoding="utf-8")
        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])

        files = list(target_dir.glob("20260820_plan*.md"))
        self.assertEqual(len(files), 3)

    def test_conflict_preserves_destination_mtime_and_content(self):
        """7.5 Conflict resolution preserves destination file content and metadata."""
        self.sandbox.add_project("proj_cr5", "uuid-cr-5")
        self.sandbox.add_session(
            "sess-cr-5",
            title="Preserve Meta",
            preview="",
            project_id="uuid-cr-5",
            md_files={"plan.md": ("Dest content", "2026-08-20T10:00:00Z")}
        )

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        target = self.sandbox.workspaces_root / "proj_cr5" / "AGY_Artifacts" / "Preserve Meta" / "20260820_plan.md"
        initial_stat = target.stat()

        brain_file = self.sandbox.brain_dir / "sess-cr-5" / "plan.md"
        brain_file.write_text("Conflicting update", encoding="utf-8")

        self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])

        after_stat = target.stat()
        self.assertEqual(target.read_text(encoding="utf-8"), "Dest content")
        self.assertEqual(initial_stat.st_size, after_stat.st_size)


class TestTier1CLIArguments(BaseSandboxTestCase):
    """Tier 1 - Feature 8: CLI Arguments & Dry-Run."""

    def test_cli_help(self):
        """8.1 --help displays usage information and returns 0."""
        res = self.sandbox.run_sync(["--help"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("usage:", res.stdout.lower())

    def test_cli_dry_run_does_not_modify_filesystem(self):
        """8.2 --dry-run does not create junctions or copy files."""
        proj = self.sandbox.add_project("proj_cli2", "uuid-cli-2")
        self.sandbox.add_session(
            "sess-cli-2",
            title="Dry Run Session",
            preview="",
            project_id="uuid-cli-2",
            md_files={"task.md": ("Content", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate",
            "--dry-run"
        ])
        self.assertEqual(res.returncode, 0)
        link = proj / "AGY_Artifacts"
        self.assertFalse(link.exists())
        target_file = (
            self.sandbox.workspaces_root
            / "proj_cli2"
            / "AGY_Artifacts"
            / "Dry Run Session"
            / "20260820_task.md"
        )
        self.assertFalse(target_file.exists())

    def test_cli_setup_junctions_flag_only(self):
        """8.3 --setup-junctions creates junctions but does not migrate artifacts."""
        proj = self.sandbox.add_project("proj_cli3", "uuid-cli-3")
        self.sandbox.add_session(
            "sess-cli-3",
            title="Junction Only Session",
            preview="",
            project_id="uuid-cli-3",
            md_files={"task.md": ("Content", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue((proj / "AGY_Artifacts").exists())
        target_file = (
            self.sandbox.workspaces_root
            / "proj_cli3"
            / "AGY_Artifacts"
            / "Junction Only Session"
            / "20260820_task.md"
        )
        self.assertFalse(target_file.exists())

    def test_cli_migrate_flag_only(self):
        """8.4 --migrate migrates artifacts without creating junctions."""
        proj = self.sandbox.add_project("proj_cli4", "uuid-cli-4")
        self.sandbox.add_session(
            "sess-cli-4",
            title="Migrate Only Session",
            preview="",
            project_id="uuid-cli-4",
            md_files={"task.md": ("Content", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertFalse((proj / "AGY_Artifacts").exists())
        target_file = (
            self.sandbox.workspaces_root
            / "proj_cli4"
            / "AGY_Artifacts"
            / "Migrate Only Session"
            / "20260820_task.md"
        )
        self.assertTrue(target_file.exists())

    def test_cli_combined_flags(self):
        """8.5 Running --setup-junctions and --migrate together executes both."""
        proj = self.sandbox.add_project("proj_cli5", "uuid-cli-5")
        self.sandbox.add_session(
            "sess-cli-5",
            title="Combined Session",
            preview="",
            project_id="uuid-cli-5",
            md_files={"task.md": ("Content", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue((proj / "AGY_Artifacts").exists())
        target_file = (
            self.sandbox.workspaces_root
            / "proj_cli5"
            / "AGY_Artifacts"
            / "Combined Session"
            / "20260820_task.md"
        )
        self.assertTrue(target_file.exists())


class TestTier1MultiPCPortabilityStatic(unittest.TestCase):
    """Tier 1 - Feature 9: Multi-PC Portability Static Verification."""

    def test_no_hardcoded_infomax_username(self):
        """9.1 Verify tools/artifacts_sync does NOT contain hardcoded 'infomax' username."""
        if not TOOLS_DIR.exists():
            self.skipTest(f"{TOOLS_DIR} does not exist yet")

        pattern = re.compile(r"\binfomax\b", re.IGNORECASE)
        violating_files = []
        for p in TOOLS_DIR.glob("**/*"):
            if p.is_file() and p.suffix in [".py", ".ps1", ".md", ".json", ".sh"]:
                content = p.read_text(encoding="utf-8", errors="replace")
                if pattern.search(content):
                    violating_files.append(str(p))

        self.assertEqual(
            violating_files,
            [],
            f"Found hardcoded 'infomax' username in files: {violating_files}",
        )

    def test_no_hardcoded_user_c_drive_paths(self):
        """9.2 Verify tools/artifacts_sync does NOT contain hardcoded 'C:\\Users\\' paths."""
        if not TOOLS_DIR.exists():
            self.skipTest(f"{TOOLS_DIR} does not exist yet")

        pattern = re.compile(r"c:[\\/]users[\\/][a-zA-Z0-9_\-]+", re.IGNORECASE)
        violating_files = []
        for p in TOOLS_DIR.glob("**/*"):
            if p.is_file() and p.suffix in [".py", ".ps1"]:
                content = p.read_text(encoding="utf-8", errors="replace")
                if pattern.search(content):
                    violating_files.append(str(p))

        self.assertEqual(
            violating_files,
            [],
            f"Found hardcoded user profile paths in: {violating_files}",
        )

    def test_no_hardcoded_gdrive_without_fallback(self):
        """9.3 Verify script does not assume G:\\내 드라이브 is the sole fixed drive."""
        if not SCRIPT_PATH.exists():
            self.skipTest(f"{SCRIPT_PATH} does not exist yet")

        content = SCRIPT_PATH.read_text(encoding="utf-8", errors="replace")
        has_dynamic_detection = (
            "root_preference_sqlite" in content
            or "GetVolumeInformation" in content
            or "DriveInfo" in content
            or "string.ascii_uppercase" in content
            or "ord('A')" in content
            or "A-Z" in content
            or "chr(" in content
        )
        self.assertTrue(
            has_dynamic_detection,
            "sync_artifacts.py must implement dynamic Google Drive probe across drive letters or DriveFS DB",
        )

    def test_dynamic_home_resolution_used(self):
        """9.4 Verify script uses Path.home() or os.path.expanduser('~')."""
        if not SCRIPT_PATH.exists():
            self.skipTest(f"{SCRIPT_PATH} does not exist yet")

        content = SCRIPT_PATH.read_text(encoding="utf-8", errors="replace")
        has_home = "Path.home()" in content or "expanduser" in content or "USERPROFILE" in content
        self.assertTrue(has_home, "sync_artifacts.py must use Path.home() or expanduser('~')")

    def test_pure_standard_library_imports(self):
        """9.5 Verify sync_artifacts.py imports only Python standard library."""
        if not SCRIPT_PATH.exists():
            self.skipTest(f"{SCRIPT_PATH} does not exist yet")

        forbidden = ["requests", "numpy", "pandas", "dotenv", "yaml", "google", "pydantic", "fastapi"]
        content = SCRIPT_PATH.read_text(encoding="utf-8", errors="replace")
        for pkg in forbidden:
            pattern = rf"^\s*(import|from)\s+{pkg}\b"
            self.assertIsNone(
                re.search(pattern, content, re.MULTILINE),
                f"sync_artifacts.py imports forbidden third-party package: {pkg}",
            )


# =========================================================================
# TIER 2: Boundary & Corner Cases
# =========================================================================

class TestTier2BoundaryAndCornerCases(BaseSandboxTestCase):
    """Tier 2: Boundary & Corner Cases."""

    def test_empty_session_title_and_preview(self):
        """T2.1 Empty title and empty preview handled safely."""
        self.sandbox.add_project("proj_b1", "uuid-b-1")
        conv_id = "a1b2c3d4-e5f6-7890-1234-567890abcdef"
        self.sandbox.add_session(
            conv_id,
            title="",
            preview="",
            project_id="uuid-b-1",
            md_files={"task.md": ("Raw body without markdown headers", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        proj_artifacts = self.sandbox.workspaces_root / "proj_b1" / "AGY_Artifacts"
        dirs = [d.name for d in proj_artifacts.iterdir() if d.is_dir()]
        self.assertTrue(len(dirs) >= 1)
        self.assertIn("a1b2c3d4", dirs[0])

    def test_korean_utf8_session_title_and_paths(self):
        """T2.2 Korean UTF-8 characters in session title and paths handled without corruption."""
        self.sandbox.add_project("proj_b2", "uuid-b-2")
        korean_title = "포트폴리오 대시보드 및 투자 자산 분석"
        self.sandbox.add_session(
            "sess-ko-1",
            title=korean_title,
            preview="",
            project_id="uuid-b-2",
            md_files={"walkthrough.md": ("한국어 내용 테스트", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_dir = self.sandbox.workspaces_root / "proj_b2" / "AGY_Artifacts" / korean_title
        self.assertTrue(target_dir.exists())
        target_file = target_dir / "20260820_walkthrough.md"
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), "한국어 내용 테스트")

    def test_windows_illegal_characters_sanitization(self):
        """T2.3 Illegal characters \\ / : * ? \" < > | sanitized to underscores."""
        self.sandbox.add_project("proj_b3", "uuid-b-3")
        dirty_title = 'Fix: Issue #12 / Path "test" <A|B> *star* ?question?'
        self.sandbox.add_session(
            "sess-dirty-1",
            title=dirty_title,
            preview="",
            project_id="uuid-b-3",
            md_files={"task.md": ("Content", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        proj_artifacts = self.sandbox.workspaces_root / "proj_b3" / "AGY_Artifacts"
        dirs = [d.name for d in proj_artifacts.iterdir() if d.is_dir()]
        self.assertEqual(len(dirs), 1)
        sanitized = dirs[0]
        for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
            self.assertNotIn(char, sanitized)

    def test_missing_companion_metadata_json(self):
        """T2.4 Markdown artifact without companion .metadata.json falls back to db timestamp or mtime."""
        self.sandbox.add_project("proj_b4", "uuid-b-4")
        self.sandbox.add_session(
            "sess-no-meta-1",
            title="No Metadata Companion",
            preview="",
            project_id="uuid-b-4",
            last_modified="2026-07-15 12:00:00.000000+00:00",
            md_files={"task.md": "Raw task content without companion json"}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)
        target_dir = self.sandbox.workspaces_root / "proj_b4" / "AGY_Artifacts" / "No Metadata Companion"
        files = list(target_dir.glob("*_task.md"))
        self.assertEqual(len(files), 1)
        self.assertTrue(re.match(r"^\d{8}_task\.md$", files[0].name))

    def test_preexisting_junction_vs_directory_collision(self):
        """T2.5 Local AGY_Artifacts directory with nested subdirectories and files safely migrated."""
        proj = self.sandbox.add_project("proj_b5", "uuid-b-5")
        local_dir = proj / "AGY_Artifacts"
        nested_dir = local_dir / "Existing_Session"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "old_note.txt").write_text("historical note", encoding="utf-8")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        gdrive_file = (
            self.sandbox.workspaces_root
            / "proj_b5"
            / "AGY_Artifacts"
            / "Existing_Session"
            / "old_note.txt"
        )
        self.assertTrue(gdrive_file.exists())
        self.assertEqual(gdrive_file.read_text(encoding="utf-8"), "historical note")

    def test_missing_target_gdrive_folder(self):
        """T2.6 Entire target hierarchy created automatically when missing on GDrive."""
        fresh_gdrive = self.temp_root / "fresh_gdrive_disk"
        fresh_gdrive.mkdir(parents=True, exist_ok=True)
        proj = self.sandbox.add_project("proj_b6", "uuid-b-6")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(fresh_gdrive),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue((proj / "AGY_Artifacts").exists())

    def test_nested_repository_macro_analyzer(self):
        """T2.7 Nested Git repo macro_analyzer/macro_analyzer receives junction and gitignore."""
        outer = self.sandbox.documents / "macro_analyzer_edge"
        inner = outer / "macro_analyzer_edge"
        inner.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "init", str(inner)])

        self.sandbox.add_project(
            "macro_analyzer_edge",
            "uuid-edge-nested",
            relative_path="macro_analyzer_edge/macro_analyzer_edge",
            git_init=False
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue((inner / "AGY_Artifacts").exists())
        self.assertIn("AGY_Artifacts", (inner / ".gitignore").read_text(encoding="utf-8"))


# =========================================================================
# TIER 3: Cross-Feature Combinations
# =========================================================================

class TestTier3CrossFeatureCombinations(BaseSandboxTestCase):
    """Tier 3: Cross-Feature Combinations."""

    def test_sequential_passes_setup_then_migrate_then_conflict(self):
        """T3.1 Sequential execution of junction setup -> migration -> modification -> conflict sync."""
        proj = self.sandbox.add_project("proj_seq", "uuid-seq-1")
        self.sandbox.add_session(
            "sess-seq-1",
            title="Sequential Test",
            preview="",
            project_id="uuid-seq-1",
            md_files={"plan.md": ("Version 1", "2026-08-20T10:00:00Z")}
        )

        # Pass 1: Setup junctions
        res1 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res1.returncode, 0)
        link = proj / "AGY_Artifacts"
        self.assertTrue(link.exists())

        # Pass 2: Migrate
        res2 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res2.returncode, 0)
        dest_file = self.sandbox.workspaces_root / "proj_seq" / "AGY_Artifacts" / "Sequential Test" / "20260820_plan.md"
        self.assertTrue(dest_file.exists())
        self.assertEqual(dest_file.read_text(encoding="utf-8"), "Version 1")

        # Pass 3: Modify source and re-migrate (conflict)
        (self.sandbox.brain_dir / "sess-seq-1" / "plan.md").write_text("Version 2 Conflict", encoding="utf-8")
        res3 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res3.returncode, 0)
        self.assertEqual(dest_file.read_text(encoding="utf-8"), "Version 1")
        conflicts = list(dest_file.parent.glob("20260820_plan_*.md"))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].read_text(encoding="utf-8"), "Version 2 Conflict")

    def test_discovery_junction_and_gitignore_in_single_run(self):
        """T3.2 Fresh project discovered, junction linked, and git check-ignore verified."""
        proj = self.sandbox.add_project("proj_check_ignore", "uuid-ci-1")

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions"
        ])
        self.assertEqual(res.returncode, 0)
        self.assertTrue((proj / "AGY_Artifacts").exists())

        ci_res = run_cmd(["git", "-C", str(proj), "check-ignore", "-v", "AGY_Artifacts/test.md"])
        self.assertEqual(ci_res.returncode, 0)
        self.assertIn("AGY_Artifacts", ci_res.stdout)

    def test_mixed_projects_and_outside_sessions(self):
        """T3.3 Combined batch migration of multiple project sessions and general sessions."""
        self.sandbox.add_project("proj_a", "uuid-a")
        self.sandbox.add_project("proj_b", "uuid-b")

        self.sandbox.add_session(
            "sess-a",
            title="Project A Session",
            preview="",
            project_id="uuid-a",
            md_files={"task.md": ("Task A", "2026-08-20T10:00:00Z")}
        )
        self.sandbox.add_session(
            "sess-b",
            title="Project B Session",
            preview="",
            project_id="uuid-b",
            md_files={"task.md": ("Task B", "2026-08-20T10:00:00Z")}
        )
        self.sandbox.add_session(
            "sess-gen",
            title="General Session",
            preview="",
            project_id="outside-of-project",
            md_files={"task.md": ("General Task", "2026-08-20T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)

        self.assertTrue(
            (self.sandbox.workspaces_root / "proj_a" / "AGY_Artifacts" / "Project A Session" / "20260820_task.md").exists()
        )
        self.assertTrue(
            (self.sandbox.workspaces_root / "proj_b" / "AGY_Artifacts" / "Project B Session" / "20260820_task.md").exists()
        )
        self.assertTrue(
            (self.sandbox.workspaces_root / "_General" / "AGY_Artifacts" / "General Session" / "20260820_task.md").exists()
        )


# =========================================================================
# TIER 4: Real-World Acceptance Scenarios
# =========================================================================

class TestTier4RealWorldAcceptance(BaseSandboxTestCase):
    """Tier 4: Real-World Acceptance Scenarios."""

    def test_scenario_1_greenfield_pc_setup(self):
        """T4.1 Greenfield PC Setup: Clean environment simulation."""
        p1 = self.sandbox.add_project("my_asset_js", "uuid-p1")
        p2 = self.sandbox.add_project("workspace-automation", "uuid-p2")
        p3 = self.sandbox.add_project("macro_analyzer", "uuid-p3", relative_path="macro_analyzer/macro_analyzer")

        self.sandbox.add_session(
            "sess-101",
            title="Greenfield Session 1",
            preview="",
            project_id="uuid-p1",
            md_files={"implementation_plan.md": ("Plan 101", "2026-08-20T10:00:00Z")}
        )
        self.sandbox.add_session(
            "sess-102",
            title="Greenfield Session 2",
            preview="",
            project_id="uuid-p2",
            md_files={"walkthrough.md": ("Walkthrough 102", "2026-08-21T10:00:00Z")}
        )

        res = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res.returncode, 0)

        self.assertTrue((p1 / "AGY_Artifacts").exists())
        self.assertTrue((p2 / "AGY_Artifacts").exists())
        self.assertTrue((p3 / "AGY_Artifacts").exists())

        for p in [p1, p2, p3]:
            self.assertIn("AGY_Artifacts", (p / ".gitignore").read_text(encoding="utf-8"))

        self.assertTrue(
            (self.sandbox.workspaces_root / "my_asset_js" / "AGY_Artifacts" / "Greenfield Session 1" / "20260820_implementation_plan.md").exists()
        )
        self.assertTrue(
            (self.sandbox.workspaces_root / "workspace-automation" / "AGY_Artifacts" / "Greenfield Session 2" / "20260821_walkthrough.md").exists()
        )

    def test_scenario_2_repeated_execution_zero_duplicates_idempotency(self):
        """T4.2 Re-running sync 3 consecutive times produces 0 duplicate files and 0 errors."""
        self.sandbox.add_project("idempotent_proj", "uuid-idem-1")
        self.sandbox.add_session(
            "sess-idem-1",
            title="Idempotency Test Session",
            preview="",
            project_id="uuid-idem-1",
            md_files={
                "implementation_plan.md": ("Plan body", "2026-08-20T10:00:00Z"),
                "walkthrough.md": ("Walkthrough body", "2026-08-20T10:00:00Z"),
            }
        )

        res1 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res1.returncode, 0)
        target_dir = (
            self.sandbox.workspaces_root
            / "idempotent_proj"
            / "AGY_Artifacts"
            / "Idempotency Test Session"
        )
        files_run1 = sorted([f.name for f in target_dir.iterdir()])
        self.assertEqual(len(files_run1), 2)

        res2 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res2.returncode, 0)
        files_run2 = sorted([f.name for f in target_dir.iterdir()])
        self.assertEqual(files_run1, files_run2)

        res3 = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--setup-junctions",
            "--migrate"
        ])
        self.assertEqual(res3.returncode, 0)
        files_run3 = sorted([f.name for f in target_dir.iterdir()])
        self.assertEqual(files_run1, files_run3)

    def test_scenario_3_multi_pc_conflict_simulation(self):
        """T4.3 Multi-PC Conflict Simulation: PC-A and PC-B sync to shared Google Drive."""
        self.sandbox.add_project("collab_proj", "uuid-collab")

        self.sandbox.add_session(
            "sess-collab-1",
            title="Collaborative Feature",
            preview="",
            project_id="uuid-collab",
            md_files={"walkthrough.md": ("Walkthrough drafted on PC-A", "2026-08-22T10:00:00Z")}
        )
        res_a = self.sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(self.sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res_a.returncode, 0)

        target_file = (
            self.sandbox.workspaces_root
            / "collab_proj"
            / "AGY_Artifacts"
            / "Collaborative Feature"
            / "20260822_walkthrough.md"
        )
        self.assertEqual(target_file.read_text(encoding="utf-8"), "Walkthrough drafted on PC-A")

        pc_b_sandbox = SandboxEnvironment(self.temp_root / "pc_b_sandbox")
        pc_b_sandbox.add_project("collab_proj", "uuid-collab")
        pc_b_sandbox.add_session(
            "sess-collab-1",
            title="Collaborative Feature",
            preview="",
            project_id="uuid-collab",
            md_files={"walkthrough.md": ("Walkthrough modified concurrently on PC-B", "2026-08-22T10:00:00Z")}
        )

        res_b = pc_b_sandbox.run_sync([
            "--gdrive-root", str(self.sandbox.gdrive_root),
            "--projects-dir", str(pc_b_sandbox.documents),
            "--migrate"
        ])
        self.assertEqual(res_b.returncode, 0)

        dest_folder = self.sandbox.workspaces_root / "collab_proj" / "AGY_Artifacts" / "Collaborative Feature"
        self.assertEqual(target_file.read_text(encoding="utf-8"), "Walkthrough drafted on PC-A")

        conflicts = list(dest_folder.glob("20260822_walkthrough_*.md"))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            conflicts[0].read_text(encoding="utf-8"),
            "Walkthrough modified concurrently on PC-B"
        )


if __name__ == "__main__":
    unittest.main()
