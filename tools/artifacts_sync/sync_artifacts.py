#!/usr/bin/env python3
"""Antigravity Artifact Synchronization & Migration Toolkit.

Engine for:
1. Dynamic Google Drive virtual mount detection across multiple PCs.
2. Local project discovery and nested Git repository resolution.
3. Windows Directory Junction (mklink /J) management and .gitignore maintenance.
4. Historical Antigravity conversation artifact migration with SHA-256 conflict resolution.

Zero external dependencies - strictly Python 3 standard library.
Zero hardcoded username paths - dynamically resolves user profile and environment.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import string
import subprocess
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure stdout/stderr handle UTF-8 cleanly on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Constants
WORKSPACES_DIR_NAME = "Antigravity_Workspaces"
ARTIFACTS_DIR_NAME = "AGY_Artifacts"
GENERAL_PROJECT_NAME = "_General"

LOCALIZED_GDRIVE_NAMES = [
    "내 드라이브",
    "My Drive",
    "Mon Drive",
    "Meu Drive",
    "Il mio Drive",
    "Google 드라이브",
]


# ============================================================================
# Google Drive Virtual Mount Detection
# ============================================================================

def get_windows_volume_label(drive_letter: str) -> Optional[str]:
    """Retrieve the volume label of a drive letter using Windows API."""
    if sys.platform != "win32":
        return None
    try:
        root_path = f"{drive_letter.upper()}:\\"
        vol_name = ctypes.create_unicode_buffer(1024)
        fs_name = ctypes.create_unicode_buffer(1024)
        serial = ctypes.c_ulong()
        max_len = ctypes.c_ulong()
        flags = ctypes.c_ulong()
        res = ctypes.windll.kernel32.GetVolumeInformationW(
            root_path,
            vol_name,
            len(vol_name),
            ctypes.byref(serial),
            ctypes.byref(max_len),
            ctypes.byref(flags),
            fs_name,
            len(fs_name),
        )
        if res != 0:
            return vol_name.value
    except Exception:
        pass
    return None


def probe_user_folder_in_drive(drive_path: pathlib.Path) -> Optional[pathlib.Path]:
    """Check if any known localized Google Drive user folder exists in the drive path."""
    if not drive_path.exists():
        return None
    for name in LOCALIZED_GDRIVE_NAMES:
        candidate = drive_path / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    return drive_path


def detect_gdrive_from_drivefs_db() -> Optional[pathlib.Path]:
    """Query Google DriveFS SQLite preference database for the active mount point."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    db_path = pathlib.Path(local_app_data) / "Google" / "DriveFS" / "root_preference_sqlite.db"
    if not db_path.exists():
        return None
    try:
        # Open in read-only URI mode to avoid locking issues
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT last_mount_point FROM media WHERE name = 'Google Drive' AND last_mount_point != ''"
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            mount_path = pathlib.Path(row[0])
            if mount_path.exists():
                return probe_user_folder_in_drive(mount_path)
    except Exception:
        pass
    return None


def detect_gdrive_root(custom_root: Optional[str] = None) -> pathlib.Path:
    """Dynamically detect the Google Drive user root directory across multiple PCs.

    Fallback chain:
    1. CLI --gdrive-root override (if provided and valid).
    2. Direct fast check: G:\\내 드라이브 and G:\\My Drive.
    3. Query %LOCALAPPDATA%\\Google\\DriveFS\\root_preference_sqlite.db.
    4. Scan drive letters A-Z for volume label 'Google Drive' via GetVolumeInformationW.
    5. Scan drive letters A-Z for localized user directories.
    """
    # 1. Custom CLI override
    if custom_root:
        custom_path = pathlib.Path(custom_root).resolve()
        if custom_path.exists() and custom_path.is_dir():
            # If user provided a drive letter or mount point, check if localized folder exists inside
            sub = probe_user_folder_in_drive(custom_path)
            return sub if sub else custom_path
        raise FileNotFoundError(f"Specified --gdrive-root directory does not exist: {custom_root}")

    # 2. Fast check: common default G: drive
    for name in LOCALIZED_GDRIVE_NAMES:
        candidate = pathlib.Path(f"G:\\{name}")
        if candidate.exists() and candidate.is_dir():
            return candidate

    # 3. Check Google DriveFS preferences DB
    from_db = detect_gdrive_from_drivefs_db()
    if from_db and from_db.exists():
        return from_db

    # 4. Scan drive letters A-Z using Windows API volume label
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            try:
                label = get_windows_volume_label(letter)
                if label and "google drive" in label.lower():
                    drive_path = pathlib.Path(f"{letter}:\\")
                    resolved = probe_user_folder_in_drive(drive_path)
                    if resolved and resolved.exists():
                        return resolved
            except Exception:
                continue

    # 5. Scan drive letters A-Z for localized user directories
    for letter in string.ascii_uppercase:
        for name in LOCALIZED_GDRIVE_NAMES:
            candidate = pathlib.Path(f"{letter}:\\{name}")
            if candidate.exists() and candidate.is_dir():
                return candidate

    raise RuntimeError(
        "Google Drive virtual mount not found. Please ensure Google Drive for desktop is running, "
        "or specify --gdrive-root <path> manually."
    )


# ============================================================================
# Local Project Discovery
# ============================================================================

def get_projects_config_dirs() -> List[pathlib.Path]:
    """Return project configuration directory candidates in order of preference."""
    home = pathlib.Path.home()
    return [
        home / ".gemini" / "config" / "projects",
        home / ".gemini" / "antigravity" / "config" / "projects",
    ]


def parse_uri_to_path(uri: str) -> Optional[pathlib.Path]:
    """Parse a file URI (e.g. file:///c%3A/Users/... or file:///C:/Users/...) into a Path."""
    if not uri or not uri.startswith("file:"):
        return None
    try:
        parsed = urllib.parse.urlparse(uri)
        path_str = urllib.parse.unquote(parsed.path)
        # Windows file:///c:/... produces leading slash /c:/...
        if path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
            path_str = path_str[1:]
        path_obj = pathlib.Path(path_str).resolve()
        return path_obj
    except Exception:
        return None


def load_registered_projects() -> Dict[str, Dict[str, Any]]:
    """Parse ~/.gemini/config/projects/*.json files into a mapping by project ID.

    Returns:
        dict: {
            project_id: {
                "id": str,
                "name": str,
                "root_path": Optional[pathlib.Path],
                "json_path": pathlib.Path,
            }
        }
    """
    registered: Dict[str, Dict[str, Any]] = {}
    for cfg_dir in get_projects_config_dirs():
        if not cfg_dir.exists() or not cfg_dir.is_dir():
            continue
        try:
            for json_file in cfg_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pid = data.get("id") or json_file.stem
                    name = data.get("name") or pid

                    # Find root path from projectResources
                    root_path: Optional[pathlib.Path] = None
                    for resource in data.get("projectResources", {}).get("resources", []):
                        gf = resource.get("gitFolder", {})
                        if gf and "folderUri" in gf:
                            parsed = parse_uri_to_path(gf["folderUri"])
                            if parsed:
                                root_path = parsed
                                break
                    if not root_path and "folderUri" in data:
                        root_path = parse_uri_to_path(data["folderUri"])

                    registered[pid] = {
                        "id": pid,
                        "name": name,
                        "root_path": root_path,
                        "json_path": json_file,
                    }
                except Exception:
                    continue
        except Exception:
            continue
    return registered


def scan_local_repositories(
    base_dir: pathlib.Path, max_depth: int = 2
) -> Dict[str, pathlib.Path]:
    """Scan base_dir up to max_depth for Git repositories.

    Resilient to Windows PermissionError and legacy reparse points (e.g. My Music).
    Correctly resolves nested repositories such as Documents/macro_analyzer/macro_analyzer.
    """
    repos: Dict[str, pathlib.Path] = {}
    base_dir = base_dir.resolve()
    if not base_dir.exists() or not base_dir.is_dir():
        return repos

    def safe_iterdir(d: pathlib.Path):
        try:
            for item in d.iterdir():
                yield item
        except (PermissionError, OSError):
            return

    # Check depth 1
    for item in safe_iterdir(base_dir):
        try:
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                continue
            if not item.is_dir():
                continue

            # If depth 1 directory contains .git
            if (item / ".git").exists():
                repos[item.name] = item
                continue

            # Check depth 2
            if max_depth >= 2:
                for subitem in safe_iterdir(item):
                    try:
                        if subitem.is_symlink() or (
                            hasattr(subitem, "is_junction") and subitem.is_junction()
                        ):
                            continue
                        if not subitem.is_dir():
                            continue
                        if (subitem / ".git").exists():
                            # For nested repo like macro_analyzer/macro_analyzer, name as subitem.name
                            repos[subitem.name] = subitem
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            continue

    return repos


def discover_projects(
    projects_dir: Optional[str] = None,
) -> Tuple[Dict[str, pathlib.Path], Dict[str, str]]:
    """Discover local project directories and ID-to-name mappings.

    Returns:
        tuple: (projects_by_name: {name: path}, id_to_name: {id: name})
    """
    registered = load_registered_projects()
    id_to_name: Dict[str, str] = {}
    projects_by_name: Dict[str, pathlib.Path] = {}

    for pid, info in registered.items():
        name = info["name"]
        id_to_name[pid] = name
        root_path = info["root_path"]
        if root_path and root_path.exists():
            projects_by_name[name] = root_path

    # Scan Documents (or custom directory)
    scan_root = (
        pathlib.Path(projects_dir).resolve()
        if projects_dir
        else pathlib.Path.home() / "Documents"
    )
    scanned = scan_local_repositories(scan_root, max_depth=2)

    # Merge scanned into projects_by_name (registered paths take precedence if both exist)
    for name, path in scanned.items():
        if name not in projects_by_name:
            projects_by_name[name] = path

    return projects_by_name, id_to_name


# ============================================================================
# Windows Directory Junction Management
# ============================================================================

def normalize_path_for_comparison(p: str | pathlib.Path) -> str:
    """Normalize a filesystem path string, stripping Windows \\?\\ prefix."""
    s = str(p).replace("\\\\?\\", "").rstrip("/\\")
    try:
        return os.path.normcase(os.path.abspath(s))
    except Exception:
        return os.path.normcase(s)


def is_path_junction(p: pathlib.Path) -> bool:
    """Check if a path is an NTFS directory junction."""
    if not p.exists() and not os.path.islink(p):
        return False
    if hasattr(p, "is_junction"):
        try:
            if p.is_junction():
                return True
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            # Check reparse point attribute (FILE_ATTRIBUTE_REPARSE_POINT = 0x400)
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            if attrs != -1 and (attrs & 0x400):
                return True
        except Exception:
            pass
    return False


def get_junction_target(junction_path: pathlib.Path) -> Optional[str]:
    """Read the target of a directory junction."""
    try:
        target = os.readlink(junction_path)
        return target.replace("\\\\?\\", "").rstrip("/\\")
    except Exception:
        return None


def copy_directory_contents_safe(src: pathlib.Path, dst: pathlib.Path, dry_run: bool = False):
    """Copy contents of src directory into dst directory before converting to junction."""
    if not src.exists() or not src.is_dir():
        return
    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            if not dry_run:
                dest_item.mkdir(parents=True, exist_ok=True)
            copy_directory_contents_safe(item, dest_item, dry_run=dry_run)
        else:
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_item)


def ensure_gitignore_entry(
    repo_root: pathlib.Path, entry: str = "/AGY_Artifacts/", dry_run: bool = False
) -> str:
    """Ensure that the given entry is present in repo_root/.gitignore.

    Returns:
        str: 'already_present', 'added', or 'created'
    """
    gitignore_path = repo_root / ".gitignore"
    clean_entry = entry.strip("/")

    if gitignore_path.exists():
        try:
            content = gitignore_path.read_text(encoding="utf-8")
        except Exception:
            content = gitignore_path.read_text(encoding="latin-1", errors="replace")

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            if line.startswith("#"):
                continue
            stripped = line.strip("/")
            if stripped == clean_entry:
                return "already_present"

        if not dry_run:
            append_str = ("\n" if content and not content.endswith("\n") else "") + f"{entry}\n"
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write(append_str)
        return "added"
    else:
        if not dry_run:
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"{entry}\n")
        return "created"


def setup_project_junction(
    project_name: str,
    project_root: pathlib.Path,
    gdrive_root: pathlib.Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Set up directory junction <ProjectRoot>\\AGY_Artifacts -> <GDrive>\\Antigravity_Workspaces\\<Project>\\AGY_Artifacts.

    Rules:
    - MUST create Google Drive target directory BEFORE creating junction.
    - If link is already junction and points to target: skip (idempotent).
    - If link is junction but points to wrong target: remove junction with os.rmdir() and recreate.
    - If link is regular directory: copy files to target, delete directory, then create junction.
    - If link does not exist: create junction via cmd /c mklink /J.
    - Ensure /AGY_Artifacts/ is in .gitignore.
    """
    target_dir = gdrive_root / WORKSPACES_DIR_NAME / project_name / ARTIFACTS_DIR_NAME
    link_path = project_root / ARTIFACTS_DIR_NAME

    result: Dict[str, Any] = {
        "project": project_name,
        "project_root": str(project_root),
        "target_dir": str(target_dir),
        "link_path": str(link_path),
        "junction_status": "unknown",
        "gitignore_status": "unchanged",
        "error": None,
    }

    try:
        # 1. Target directory must exist before junction creation
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        # 2. Inspect local link path
        target_norm = normalize_path_for_comparison(target_dir)

        if link_path.exists() or os.path.islink(link_path):
            if is_path_junction(link_path):
                current_target = get_junction_target(link_path)
                current_target_norm = (
                    normalize_path_for_comparison(current_target) if current_target else ""
                )
                if current_target_norm == target_norm:
                    result["junction_status"] = "existing_valid"
                else:
                    if not dry_run:
                        os.rmdir(link_path)
                        cmd = ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)]
                        subprocess.run(cmd, capture_output=True, text=True, check=True)
                    result["junction_status"] = "relinked"
            elif link_path.is_dir():
                # Regular directory: migrate existing contents then convert
                if not dry_run:
                    copy_directory_contents_safe(link_path, target_dir, dry_run=False)
                    shutil.rmtree(link_path)
                    cmd = ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)]
                    subprocess.run(cmd, capture_output=True, text=True, check=True)
                result["junction_status"] = "converted_from_dir"
            else:
                raise OSError(f"Cannot create junction: {link_path} exists and is not a directory.")
        else:
            if not dry_run:
                cmd = ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            result["junction_status"] = "created"

        # 3. Update .gitignore
        result["gitignore_status"] = ensure_gitignore_entry(project_root, "/AGY_Artifacts/", dry_run)

    except Exception as e:
        result["error"] = str(e)
        result["junction_status"] = "failed"

    return result


# ============================================================================
# Title, Date & File Sanitization
# ============================================================================

def sanitize_title(title: Optional[str], fallback_id: str) -> str:
    r"""Sanitize a conversation title for use as a filesystem directory name.

    Hierarchy:
    - title.strip() -> first line of preview -> first H1 in .md -> Session_<fallback_id[:8]>
    - Replace Windows illegal chars [\/:*?"<>|] with '_'
    - Collapse consecutive whitespace and underscores
    - Strip leading/trailing dots, spaces, underscores
    """
    if not title or not title.strip():
        return f"Session_{fallback_id[:8]}"

    # Clean leading markdown headers from preview/title
    clean = re.sub(r"^[#* \-\t]+", "", title.strip()).strip()

    # Replace illegal Windows filesystem characters
    clean = re.sub(r'[\x00-\x1f\\/*?:"<>|]', "_", clean)
    clean = re.sub(r"[\t ]*_+[\t ]*", "_", clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"_+", "_", clean)
    clean = clean.strip(" ._")

    if not clean:
        return f"Session_{fallback_id[:8]}"

    # Guard against excessive length for Windows MAX_PATH safety
    if len(clean) > 80:
        clean = clean[:80].strip(" ._")

    return clean


def compute_sha256(file_path: pathlib.Path) -> str:
    """Compute the SHA-256 hexadecimal hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_artifact_date(
    md_file: pathlib.Path,
    metadata_json_path: pathlib.Path,
    db_last_modified: Optional[str] = None,
) -> str:
    """Resolve artifact date formatted as YYYYMMDD.

    Hierarchy:
    1. Companion <filename>.metadata.json updatedAt[:10].replace('-', '')
    2. conversation_summaries.last_modified_time[:10].replace('-', '')
    3. File filesystem mtime (datetime.fromtimestamp(mtime).strftime('%Y%m%d'))
    """
    # 1. Companion metadata.json
    if metadata_json_path.exists():
        try:
            with open(metadata_json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            updated_at = meta.get("updatedAt")
            if updated_at and isinstance(updated_at, str) and len(updated_at) >= 10:
                candidate = updated_at[:10].replace("-", "")
                if re.match(r"^\d{8}$", candidate):
                    return candidate
        except Exception:
            pass

    # 2. Database last_modified_time
    if db_last_modified and isinstance(db_last_modified, str) and len(db_last_modified) >= 10:
        candidate = db_last_modified[:10].replace("-", "")
        if re.match(r"^\d{8}$", candidate):
            return candidate

    # 3. Filesystem mtime
    try:
        mtime = md_file.stat().st_mtime
        return datetime.datetime.fromtimestamp(mtime).strftime("%Y%m%d")
    except Exception:
        return datetime.datetime.now().strftime("%Y%m%d")


def extract_h1_from_md(md_file: pathlib.Path) -> Optional[str]:
    """Extract the first H1 heading (# Heading) from a markdown file."""
    try:
        with open(md_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("# "):
                    heading = line[2:].strip()
                    if heading:
                        return heading
    except Exception:
        pass
    return None


# ============================================================================
# Historical Artifact Migration
# ============================================================================

def get_brain_dir() -> pathlib.Path:
    """Return the path to ~/.gemini/antigravity/brain."""
    return pathlib.Path.home() / ".gemini" / "antigravity" / "brain"


def get_conversation_summaries_db_path() -> pathlib.Path:
    """Return the path to ~/.gemini/antigravity/conversation_summaries.db."""
    return pathlib.Path.home() / ".gemini" / "antigravity" / "conversation_summaries.db"


def load_conversation_summaries_db() -> Dict[str, Dict[str, Any]]:
    """Load all records from conversation_summaries.db."""
    db_path = get_conversation_summaries_db_path()
    records: Dict[str, Dict[str, Any]] = {}
    if not db_path.exists():
        return records

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            return records

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT conversation_id, title, preview, last_modified_time, project_id, parent_conversation_id "
            "FROM conversation_summaries"
        )
        for row in cur.fetchall():
            cid = row[0]
            records[cid] = {
                "conversation_id": cid,
                "title": row[1] or "",
                "preview": row[2] or "",
                "last_modified_time": row[3] or "",
                "project_id": row[4] or "",
                "parent_conversation_id": row[5] or "",
            }
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return records


def migrate_artifacts(
    gdrive_root: pathlib.Path,
    brain_dir: Optional[pathlib.Path] = None,
    dry_run: bool = False,
    known_id_to_name: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Migrate historical root .md artifacts from brain folders into Google Drive.

    Destination:
        <GDriveRoot>\\Antigravity_Workspaces\\<ProjectName>\\AGY_Artifacts\\<Sanitized_Session_Title>\\<YYYYMMDD>_<filename>.md

    Safe multi-PC merging with SHA-256:
    - Destination does not exist: copy source.
    - Destination exists and SHA-256 matches: skip (idempotent).
    - Destination exists and SHA-256 differs: preserve destination, write source to
      <YYYYMMDD>_<filename>_<source_hash[:8]>.md.
    """
    brain = brain_dir if brain_dir else get_brain_dir()
    results: List[Dict[str, Any]] = []

    if not brain.exists() or not brain.is_dir():
        return results

    if known_id_to_name is None:
        _, known_id_to_name = discover_projects()

    db_records = load_conversation_summaries_db()

    for session_folder in sorted(brain.iterdir()):
        if not session_folder.is_dir():
            continue

        # Look only for root .md files (ignore subdirectories like .system_generated, scratch, etc.)
        root_md_files = [f for f in session_folder.iterdir() if f.is_file() and f.suffix.lower() == ".md"]
        if not root_md_files:
            continue

        cid = session_folder.name
        db_info = db_records.get(cid, {})

        # Resolve Project Name
        pid = db_info.get("project_id", "")
        if not pid and db_info.get("parent_conversation_id"):
            parent_info = db_records.get(db_info["parent_conversation_id"], {})
            pid = parent_info.get("project_id", "")

        if not pid or pid == "outside-of-project":
            project_name = GENERAL_PROJECT_NAME
        elif pid in known_id_to_name:
            project_name = known_id_to_name[pid]
        else:
            # Check if pid is already a valid project name or fallback to _General
            project_name = pid if not re.match(r"^[0-9a-fA-F-]{36}$", pid) else GENERAL_PROJECT_NAME

        # Resolve Session Title
        title_candidate = db_info.get("title", "").strip()
        if not title_candidate and db_info.get("preview"):
            preview_lines = db_info["preview"].strip().splitlines()
            if preview_lines:
                title_candidate = preview_lines[0].strip()

        if not title_candidate:
            for md in root_md_files:
                h1 = extract_h1_from_md(md)
                if h1:
                    title_candidate = h1
                    break

        session_title = sanitize_title(title_candidate, cid)

        # Destination session folder on Google Drive
        dest_session_dir = (
            gdrive_root / WORKSPACES_DIR_NAME / project_name / ARTIFACTS_DIR_NAME / session_title
        )

        for md_file in root_md_files:
            meta_file = session_folder / f"{md_file.name}.metadata.json"
            date_str = resolve_artifact_date(
                md_file, meta_file, db_info.get("last_modified_time")
            )

            base_stem = md_file.stem
            dest_filename = f"{date_str}_{base_stem}.md"
            dest_path = dest_session_dir / dest_filename

            source_hash = compute_sha256(md_file)
            status = "unknown"
            action_dest = dest_path

            if not dest_path.exists():
                status = "copied"
                if not dry_run:
                    dest_session_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(md_file, dest_path)
            else:
                dest_hash = compute_sha256(dest_path)
                if source_hash == dest_hash:
                    status = "skipped_identical"
                else:
                    # Non-destructive conflict handling
                    conflict_filename = f"{date_str}_{base_stem}_{source_hash[:8]}.md"
                    conflict_path = dest_session_dir / conflict_filename
                    action_dest = conflict_path

                    if conflict_path.exists() and compute_sha256(conflict_path) == source_hash:
                        status = "skipped_identical_conflict"
                    else:
                        status = "conflict_resolved"
                        if not dry_run:
                            dest_session_dir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(md_file, conflict_path)

            results.append({
                "conversation_id": cid,
                "project": project_name,
                "session_title": session_title,
                "source_file": str(md_file),
                "dest_file": str(action_dest),
                "source_hash": source_hash,
                "status": status,
            })

    return results


# ============================================================================
# CLI and Reporting
# ============================================================================

def format_summary_report(
    gdrive_root: pathlib.Path,
    junction_results: List[Dict[str, Any]],
    migration_results: List[Dict[str, Any]],
    dry_run: bool,
) -> str:
    """Format a clean, structured console report of all sync actions."""
    lines: List[str] = []
    mode_str = " [DRY-RUN - NO CHANGES WRITTEN]" if dry_run else ""
    lines.append("=" * 80)
    lines.append(f" Antigravity Artifact Synchronization Report{mode_str}")
    lines.append("=" * 80)
    lines.append(f"Google Drive User Root: {gdrive_root}")
    lines.append(f"Workspaces Base Target: {gdrive_root / WORKSPACES_DIR_NAME}")
    lines.append("-" * 80)

    # Junctions summary
    if junction_results:
        lines.append(" DIRECTORY JUNCTIONS & .GITIGNORE STATUS:")
        for res in junction_results:
            status = res["junction_status"]
            gi_status = res["gitignore_status"]
            proj = res["project"]
            err = f" (Error: {res['error']})" if res.get("error") else ""
            lines.append(
                f"  * [{status.upper()}] {proj} -> {res['link_path']} (.gitignore: {gi_status}){err}"
            )
        lines.append("-" * 80)

    # Migrations summary
    if migration_results:
        total = len(migration_results)
        copied = sum(1 for r in migration_results if r["status"] == "copied")
        skipped = sum(
            1 for r in migration_results if r["status"] in ("skipped_identical", "skipped_identical_conflict")
        )
        conflicted = sum(1 for r in migration_results if r["status"] == "conflict_resolved")

        lines.append(f" HISTORICAL ARTIFACT MIGRATION ({total} total artifacts found):")
        lines.append(f"  * Copied (New):        {copied}")
        lines.append(f"  * Skipped (Identical): {skipped}")
        lines.append(f"  * Conflicted (Preserved & Hash-Suffixed): {conflicted}")
        lines.append("")

        # Group by project for detailed display
        by_proj: Dict[str, List[Dict[str, Any]]] = {}
        for r in migration_results:
            by_proj.setdefault(r["project"], []).append(r)

        for proj, items in sorted(by_proj.items()):
            lines.append(f"  [{proj}] ({len(items)} files)")
            for item in items:
                st = item["status"]
                fname = pathlib.Path(item["dest_file"]).name
                title = item["session_title"]
                lines.append(f"    - [{st}] {title}/{fname}")
        lines.append("-" * 80)

    lines.append(" Execution Complete.")
    lines.append("=" * 80)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Antigravity Artifact Synchronization & Migration Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--setup-junctions",
        action="store_true",
        help="Set up Windows Directory Junctions (<Project>\\AGY_Artifacts) and update .gitignore for local projects.",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate historical artifacts from ~/.gemini/antigravity/brain into Google Drive.",
    )
    parser.add_argument(
        "--projects-dir",
        type=str,
        default=None,
        help="Custom root directory to scan for local Git projects (default: ~/Documents).",
    )
    parser.add_argument(
        "--gdrive-root",
        type=str,
        default=None,
        help="Custom path to Google Drive root directory (overrides automatic detection).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all actions without creating junctions or copying files.",
    )
    return parser


def main() -> int:
    """Entry point for sync_artifacts."""
    parser = build_parser()
    args = parser.parse_args()

    # Detect Google Drive Root
    try:
        gdrive_root = detect_gdrive_root(args.gdrive_root)
    except Exception as e:
        print(f"Error detecting Google Drive: {e}", file=sys.stderr)
        return 1

    # Discover projects
    projects_by_name, id_to_name = discover_projects(args.projects_dir)

    junction_results: List[Dict[str, Any]] = []
    migration_results: List[Dict[str, Any]] = []

    # If neither flag is provided, display discovery status and help hint
    if not args.setup_junctions and not args.migrate:
        print("=" * 80)
        print(" Antigravity Artifact Synchronization - Status Probe")
        print("=" * 80)
        print(f"Detected Google Drive Root : {gdrive_root}")
        print(f"Target Workspaces Directory: {gdrive_root / WORKSPACES_DIR_NAME}")
        print(f"Discovered Local Projects  : {len(projects_by_name)}")
        for name, path in sorted(projects_by_name.items()):
            print(f"  * {name:20} -> {path}")
        print("\nNo action specified. Run with --setup-junctions, --migrate, or both.")
        print("Example: python sync_artifacts.py --setup-junctions --migrate")
        print("=" * 80)
        return 0

    # 1. Setup Junctions
    if args.setup_junctions:
        for project_name, project_root in sorted(projects_by_name.items()):
            res = setup_project_junction(
                project_name=project_name,
                project_root=project_root,
                gdrive_root=gdrive_root,
                dry_run=args.dry_run,
            )
            junction_results.append(res)

    # 2. Migrate Historical Artifacts
    if args.migrate:
        migration_results = migrate_artifacts(
            gdrive_root=gdrive_root,
            dry_run=args.dry_run,
            known_id_to_name=id_to_name,
        )

    # Output formatted report
    report = format_summary_report(
        gdrive_root=gdrive_root,
        junction_results=junction_results,
        migration_results=migration_results,
        dry_run=args.dry_run,
    )
    print(report)

    # Check for any fatal errors in junction creation
    has_errors = any(r.get("error") for r in junction_results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
