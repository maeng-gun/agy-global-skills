#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Drive Local Storage Manager (gdrive_manager.py)
----------------------------------------------------
Google Drive 데스크톱 앱 기반의 로컬 가상 드라이브(예: G:\\내 드라이브)와
프로젝트 로컬 폴더(input_staging, scratch, archive, secrets 등)를 연결하고
파일 CRUD, 디렉터리 정션(Junction), 보안 파일 동기화를 제공하는 도구입니다.

- 외부 의존성 없음 (Python 표준 라이브러리만 사용)
- Windows / macOS 크로스 플랫폼 지원 (Windows: Directory Junction mklink /J)
- 3단계 계층적 구글 드라이브 경로 자동 감지
"""

import os
import sys
import argparse
import json
import shutil
import subprocess
import platform
from pathlib import Path

# 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_env_file(project_dir: Path) -> dict:
    """프로젝트 루트의 .env 파일을 파싱하여 딕셔너리로 반환합니다."""
    env_vars = {}
    env_path = project_dir / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            print(f"[Warning] Failed to read .env: {e}", file=sys.stderr)
    return env_vars


def load_project_config(project_dir: Path) -> dict:
    """
    프로젝트 설정 로드 우선순위:
    1) .gdrive_config.json
    2) .env 파일의 GDRIVE_* 변수
    3) 기본 규약 (Default conventions)
    """
    config = {
        "account": None,
        "gdrive_path": None,
        "workspace_root": "Antigravity_Workspaces",
        "project_name": project_dir.name,
        "folders": ["input_staging", "scratch", "archive", "secrets"],
        "secret_files": [".env", "auth_state.json"],
    }

    # 1. .gdrive_config.json 로드
    config_file = project_dir / ".gdrive_config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                config.update(data)
        except Exception as e:
            print(f"[Warning] Failed to read .gdrive_config.json: {e}", file=sys.stderr)

    # 2. .env 환경변수 오버라이드
    env_vars = load_env_file(project_dir)
    if "GDRIVE_PATH" in env_vars:
        config["gdrive_path"] = env_vars["GDRIVE_PATH"]
    elif "GDRIVE_PATH" in os.environ:
        config["gdrive_path"] = os.environ["GDRIVE_PATH"]

    if "GDRIVE_ACCOUNT" in env_vars:
        config["account"] = env_vars["GDRIVE_ACCOUNT"]
    elif "GDRIVE_ACCOUNT" in os.environ:
        config["account"] = os.environ["GDRIVE_ACCOUNT"]

    if "GDRIVE_WORKSPACE_ROOT" in env_vars:
        config["workspace_root"] = env_vars["GDRIVE_WORKSPACE_ROOT"]

    if "GDRIVE_PROJECT_NAME" in env_vars:
        config["project_name"] = env_vars["GDRIVE_PROJECT_NAME"]

    if "GDRIVE_SYNC_FOLDERS" in env_vars:
        config["folders"] = [s.strip() for s in env_vars["GDRIVE_SYNC_FOLDERS"].split(",") if s.strip()]

    return config


def detect_windows_google_drives() -> list:
    """
    Windows 환경에서 마운트된 모든 Google Drive 가상 드라이브 정보를 탐색합니다.
    반환 형태: [{'drive_letter': 'G:', 'volume_name': '...', 'root_path': Path(...), 'my_drive': Path(...)}]
    """
    drives = []
    # PowerShell을 통해 드라이브 목록 및 볼륨 이름 조회
    ps_cmd = (
        'Get-CimInstance Win32_LogicalDisk | '
        'Select-Object DeviceID, VolumeName | '
        'ConvertTo-Json -Compress'
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            raw = json.loads(proc.stdout.strip())
            items = [raw] if isinstance(raw, dict) else raw
            for item in items:
                dev_id = item.get("DeviceID") or ""
                vol_name = item.get("VolumeName") or ""
                root_path = Path(dev_id + "\\")
                if not root_path.exists():
                    continue

                is_gdrive = "google" in vol_name.lower() or "google drive" in vol_name.lower()
                my_drive_path = None
                for candidate in ["내 드라이브", "My Drive"]:
                    cand_path = root_path / candidate
                    if cand_path.exists():
                        my_drive_path = cand_path
                        is_gdrive = True
                        break

                if is_gdrive and my_drive_path:
                    drives.append({
                        "drive_letter": dev_id,
                        "volume_name": vol_name,
                        "root_path": root_path,
                        "my_drive": my_drive_path,
                    })
    except Exception as e:
        # PowerShell 호출 실패 시 드라이브 문자 직접 순회 (Fallback)
        pass

    # 만약 위의 PowerShell 쿼리에서 못 찾았을 경우 A~Z 폴백 검색
    if not drives:
        import string
        for letter in string.ascii_uppercase:
            root_path = Path(f"{letter}:\\")
            if root_path.exists():
                for candidate in ["내 드라이브", "My Drive"]:
                    cand_path = root_path / candidate
                    if cand_path.exists():
                        drives.append({
                            "drive_letter": f"{letter}:",
                            "volume_name": "Google Drive",
                            "root_path": root_path,
                            "my_drive": cand_path,
                        })
                        break
    return drives


def detect_macos_google_drives() -> list:
    """macOS 환경에서 Google Drive 경로를 탐색합니다."""
    drives = []
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if cloud_storage.exists():
        for item in cloud_storage.glob("GoogleDrive-*"):
            if item.is_dir():
                my_drive = item / "My Drive"
                if not my_drive.exists():
                    my_drive = item / "내 드라이브"
                if not my_drive.exists():
                    my_drive = item
                drives.append({
                    "drive_letter": str(item),
                    "volume_name": item.name,
                    "root_path": item,
                    "my_drive": my_drive,
                })
    vol_gdrive = Path("/Volumes/GoogleDrive")
    if vol_gdrive.exists():
        my_drive = vol_gdrive / "My Drive"
        if not my_drive.exists():
            my_drive = vol_gdrive / "내 드라이브"
        if not my_drive.exists():
            my_drive = vol_gdrive
        drives.append({
            "drive_letter": "/Volumes/GoogleDrive",
            "volume_name": "GoogleDrive",
            "root_path": vol_gdrive,
            "my_drive": my_drive,
        })
    return drives


def resolve_gdrive_root(project_dir: Path, config: dict) -> Path:
    """
    3단계 계층 탐색으로 최종 구글 드라이브 '내 드라이브' 경로를 결정합니다:
    1) 명시적 경로 (GDRIVE_PATH)
    2) 계정 지정 (GDRIVE_ACCOUNT)
    3) 시스템 자동 탐색
    """
    # 1단계: 명시적 경로
    if config.get("gdrive_path"):
        explicit_path = Path(config["gdrive_path"])
        if explicit_path.exists():
            # 만약 드라이브 루트(예: G:\)만 줬다면 '내 드라이브' 확인
            for cand in ["내 드라이브", "My Drive"]:
                sub = explicit_path / cand
                if sub.exists():
                    return sub
            return explicit_path

    # 플랫폼별 감지
    os_name = platform.system()
    if os_name == "Windows":
        drives = detect_windows_google_drives()
    elif os_name == "Darwin":
        drives = detect_macos_google_drives()
    else:
        drives = []

    if not drives:
        raise FileNotFoundError(
            "구글 드라이브 데스크톱 앱의 로컬 가상 드라이브를 찾을 수 없습니다. "
            "구글 드라이브 앱이 실행 중인지 확인하거나 .env에 GDRIVE_PATH를 직접 지정해 주세요."
        )

    # 2단계: 계정 지정 매칭
    target_account = config.get("account")
    if target_account:
        for d in drives:
            if target_account.lower() in d["volume_name"].lower():
                return d["my_drive"]

    # 3단계: 기본값 (첫 번째 감지된 드라이브)
    return drives[0]["my_drive"]


def get_target_workspace_dir(project_dir: Path, config: dict, gdrive_root: Path) -> Path:
    """구글 드라이브 내 프로젝트 전용 저장소 디렉터리 경로 반환"""
    ws_root = config.get("workspace_root") or "Antigravity_Workspaces"
    proj_name = config.get("project_name") or project_dir.name
    target_dir = gdrive_root / ws_root / proj_name
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def is_junction_or_link(path: Path) -> bool:
    """해당 경로가 Junction(정션) 또는 심볼릭 링크인지 판별"""
    if not path.exists():
        return False
    if path.is_symlink():
        return True
    if platform.system() == "Windows":
        try:
            # os.stat_result.st_file_attributes의 FILE_ATTRIBUTE_REPARSE_POINT (0x400) 플래그 확인
            import stat
            st = os.lstat(str(path))
            if hasattr(st, "st_file_attributes"):
                return bool(st.st_file_attributes & 0x0400)
        except Exception:
            pass
        # PowerShell fallback
        try:
            cmd = f'(Get-Item -LiteralPath "{str(path)}").LinkType'
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", cmd], text=True).strip()
            return out in ["Junction", "SymbolicLink"]
        except Exception:
            pass
    return False


def link_folder(local_folder_path: Path, gdrive_target_subfolder: Path) -> bool:
    """
    로컬 폴더를 구글 드라이브 대상 폴더와 정션(Junction)으로 연결합니다.
    기존 파일이 있으면 안전하게 구글 드라이브로 이전(마이그레이션) 후 연결합니다.
    """
    gdrive_target_subfolder.mkdir(parents=True, exist_ok=True)

    # 이미 정션으로 연결되어 있는 경우
    if is_junction_or_link(local_folder_path):
        print(f"  [Skip] 이미 링크되어 있습니다: {local_folder_path.name} -> {gdrive_target_subfolder}")
        return True

    # 기존 일반 디렉토리가 존재하는 경우
    if local_folder_path.exists() and local_folder_path.is_dir():
        # 데이터 마이그레이션 (기존 파일 복사)
        files = list(local_folder_path.iterdir())
        if files:
            print(f"  [Migrate] 기존 파일 {len(files)}개를 구글 드라이브로 이전 중: {local_folder_path.name}")
            for item in files:
                dest = gdrive_target_subfolder / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(str(dest), ignore_errors=True)
                    shutil.copytree(str(item), str(dest))
                else:
                    shutil.copy2(str(item), str(dest))
        # 기존 로컬 폴더 제거
        try:
            shutil.rmtree(str(local_folder_path))
        except Exception as e:
            print(f"  [Error] 기존 폴더 정리 실패: {e}", file=sys.stderr)
            return False

    # 정션 또는 심볼릭 링크 생성
    if platform.system() == "Windows":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(local_folder_path), str(gdrive_target_subfolder)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if proc.returncode != 0:
            print(f"  [Error] 정션 생성 실패: {proc.stderr or proc.stdout}", file=sys.stderr)
            return False
    else:
        try:
            os.symlink(str(gdrive_target_subfolder), str(local_folder_path), target_is_directory=True)
        except Exception as e:
            print(f"  [Error] 심볼릭 링크 생성 실패: {e}", file=sys.stderr)
            return False

    print(f"  [Linked] {local_folder_path.name} <==> {gdrive_target_subfolder}")
    return True


def unlink_folder(local_folder_path: Path) -> bool:
    """
    정션 연결을 안전하게 해제합니다.
    구글 드라이브 원본 파일은 그대로 유지되며, 로컬에는 빈 일반 폴더가 생성됩니다.
    """
    if not local_folder_path.exists():
        print(f"  [Notice] 해당 경로가 존재하지 않습니다: {local_folder_path}")
        return True

    if not is_junction_or_link(local_folder_path):
        print(f"  [Notice] 정션 또는 링크가 아닙니다: {local_folder_path}")
        return False

    try:
        os.rmdir(str(local_folder_path))
    except Exception as e:
        print(f"  [Error] 정션 해제 실패: {e}", file=sys.stderr)
        return False

    # 빈 일반 디렉터리 복원
    local_folder_path.mkdir(parents=True, exist_ok=True)
    print(f"  [Unlinked] {local_folder_path.name} (원본 구글 드라이브 데이터는 안전하게 보존됨)")
    return True


def push_secrets(project_dir: Path, config: dict, secrets_dir: Path) -> int:
    """프로젝트 루트의 보안 파일들을 secrets/ 폴더로 복사 (백업)"""
    secrets_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for fname in config.get("secret_files", []):
        src = project_dir / fname
        if src.exists() and src.is_file():
            dst = secrets_dir / fname
            shutil.copy2(str(src), str(dst))
            print(f"  [Secrets Push] {fname} -> secrets/{fname}")
            count += 1
    return count


def pull_secrets(project_dir: Path, config: dict, secrets_dir: Path) -> int:
    """secrets/ 폴더의 보안 파일들을 프로젝트 루트로 복사 (복원)"""
    count = 0
    if not secrets_dir.exists():
        return count
    for fname in config.get("secret_files", []):
        src = secrets_dir / fname
        if src.exists() and src.is_file():
            dst = project_dir / fname
            shutil.copy2(str(src), str(dst))
            print(f"  [Secrets Pull] secrets/{fname} -> {fname}")
            count += 1
    return count


# ==========================================
# CLI 커맨드 구현
# ==========================================

def cmd_detect(project_dir: Path):
    """현재 감지된 구글 드라이브 및 계정 정보 출력"""
    config = load_project_config(project_dir)
    print("=" * 60)
    print(" [Google Drive Detection Info] ")
    print("=" * 60)
    if platform.system() == "Windows":
        drives = detect_windows_google_drives()
        for idx, d in enumerate(drives, 1):
            print(f"[{idx}] 드라이브: {d['drive_letter']}")
            print(f"    볼륨 이름: {d['volume_name']}")
            print(f"    내 드라이브 경로: {d['my_drive']}")
    elif platform.system() == "Darwin":
        drives = detect_macos_google_drives()
        for idx, d in enumerate(drives, 1):
            print(f"[{idx}] 마운트: {d['drive_letter']}")
            print(f"    내 드라이브 경로: {d['my_drive']}")
    else:
        drives = []
        print("  현재 플랫폼에서는 자동 감지가 지원되지 않습니다.")

    try:
        resolved = resolve_gdrive_root(project_dir, config)
        print("-" * 60)
        print(f"최종 활성 Google Drive 경로: {resolved}")
        ws_target = get_target_workspace_dir(project_dir, config, resolved)
        print(f"프로젝트 전용 워크스페이스 타깃: {ws_target}")
    except Exception as e:
        print(f"활성 경로 확정 실패: {e}")
    print("=" * 60)


def cmd_status(project_dir: Path):
    """현재 프로젝트의 정션 연결 상태 및 구글 드라이브 대상 경로 출력"""
    config = load_project_config(project_dir)
    try:
        gdrive_root = resolve_gdrive_root(project_dir, config)
        target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    except Exception as e:
        print(f"[Error] 구글 드라이브 연결 실패: {e}")
        return

    print("=" * 60)
    print(f" [Google Drive Storage Status: {config['project_name']}] ")
    print(f" 구글 드라이브 워크스페이스: {target_ws}")
    print("=" * 60)

    for folder_name in config.get("folders", []):
        fpath = project_dir / folder_name
        linked = is_junction_or_link(fpath)
        status_str = "연결됨 (Junction)" if linked else "로컬 일반 폴더"
        print(f" - {folder_name:15}: [{status_str}]")

    print("-" * 60)
    print(" 보안 파일 (secrets):")
    secrets_dir = project_dir / "secrets"
    for sec_file in config.get("secret_files", []):
        root_exists = (project_dir / sec_file).exists()
        vault_exists = (secrets_dir / sec_file).exists() if secrets_dir.exists() else False
        print(f" - {sec_file:15}: 루트 [{ '존재' if root_exists else '없음' }] | 금고(secrets) [{ '존재' if vault_exists else '없음' }]")
    print("=" * 60)


def cmd_init(project_dir: Path):
    """
    원클릭 일괄 초기화:
    1) 구글 드라이브 경로 감지
    2) 모든 폴더(input_staging, scratch, archive, secrets) 정션 마운트
    3) secrets 파일 동기화 (기존 루트에 있으면 금고로 푸시, 새 PC라 금고에만 있으면 루트로 복원)
    """
    config = load_project_config(project_dir)
    print("=" * 60)
    print(f" [Google Drive Storage 원클릭 초기화: {config['project_name']}] ")
    print("=" * 60)

    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    print(f"구글 드라이브 타깃: {target_ws}\n")

    # 1. 폴더 정션 마운트
    print("1. 폴더 정션(Junction) 마운트 시작:")
    for folder_name in config.get("folders", []):
        local_path = project_dir / folder_name
        target_sub = target_ws / folder_name
        link_folder(local_path, target_sub)

    # 2. secrets 동기화
    print("\n2. 보안 파일(secrets) 동기화:")
    secrets_dir = project_dir / "secrets"
    # 루트에 파일이 하나라도 있으면 먼저 push (최신 로컬 백업)
    has_root_secrets = any((project_dir / f).exists() for f in config.get("secret_files", []))
    if has_root_secrets:
        push_secrets(project_dir, config, secrets_dir)
    else:
        # 루트에 없으면 (새 PC 환경) 금고에서 가져옴
        pull_secrets(project_dir, config, secrets_dir)

    print("\n" + "=" * 60)
    print(" [초기화 완료] 모든 폴더가 구글 드라이브와 실시간 동기화됩니다.")
    print("=" * 60)


def cmd_link(folder_name: str, project_dir: Path):
    """특정 폴더 단독 연결"""
    config = load_project_config(project_dir)
    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    local_path = project_dir / folder_name
    target_sub = target_ws / folder_name
    link_folder(local_path, target_sub)


def cmd_unlink(folder_name: str, project_dir: Path):
    """특정 폴더 연결 해제"""
    local_path = project_dir / folder_name
    unlink_folder(local_path)


def cmd_sync_secrets(direction: str, project_dir: Path):
    """보안 파일 수동 동기화"""
    config = load_project_config(project_dir)
    secrets_dir = project_dir / "secrets"
    if direction == "push":
        push_secrets(project_dir, config, secrets_dir)
    elif direction == "pull":
        pull_secrets(project_dir, config, secrets_dir)
    else:
        # auto: 루트에 있는 최신 것을 금고로 보내고, 루트에 없는 것은 금고에서 가져옴
        for fname in config.get("secret_files", []):
            rf = project_dir / fname
            vf = secrets_dir / fname
            if rf.exists() and vf.exists():
                if rf.stat().st_mtime >= vf.stat().st_mtime:
                    shutil.copy2(str(rf), str(vf))
                    print(f"  [Auto-Sync] {fname} -> secrets/{fname}")
                else:
                    shutil.copy2(str(vf), str(rf))
                    print(f"  [Auto-Sync] secrets/{fname} -> {fname}")
            elif rf.exists():
                shutil.copy2(str(rf), str(vf))
                print(f"  [Auto-Sync Push] {fname} -> secrets/{fname}")
            elif vf.exists():
                shutil.copy2(str(vf), str(rf))
                print(f"  [Auto-Sync Pull] secrets/{fname} -> {fname}")


def cmd_save(src_file: str, rel_path: str, project_dir: Path):
    """개별 파일을 구글 드라이브 프로젝트 저장소로 저장"""
    config = load_project_config(project_dir)
    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    dst = target_ws / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, str(dst))
    print(f"[Saved] {src_file} -> {dst}")


def cmd_read(rel_path: str, dest_file: str, project_dir: Path):
    """구글 드라이브 프로젝트 저장소의 파일을 로컬로 복사"""
    config = load_project_config(project_dir)
    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    src = target_ws / rel_path
    if not src.exists():
        print(f"[Error] File not found in Google Drive: {rel_path}", file=sys.stderr)
        sys.exit(1)
    dst = Path(dest_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    print(f"[Read] {src} -> {dest_file}")


def cmd_delete(rel_path: str, project_dir: Path):
    """구글 드라이브 프로젝트 저장소의 파일 삭제"""
    config = load_project_config(project_dir)
    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    target = target_ws / rel_path
    if target.exists():
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
        print(f"[Deleted] {target}")
    else:
        print(f"[Notice] 대상이 존재하지 않습니다: {target}")


def cmd_list(subfolder: str, project_dir: Path):
    """구글 드라이브 프로젝트 저장소의 파일 목록 조회"""
    config = load_project_config(project_dir)
    gdrive_root = resolve_gdrive_root(project_dir, config)
    target_ws = get_target_workspace_dir(project_dir, config, gdrive_root)
    scan_dir = target_ws / subfolder if subfolder else target_ws
    if not scan_dir.exists():
        print(f"[Notice] 디렉터리가 비어있거나 존재하지 않습니다: {scan_dir}")
        return
    print(f"디렉터리 목록: {scan_dir}")
    for p in sorted(scan_dir.rglob("*")):
        rel = p.relative_to(scan_dir)
        t = "DIR " if p.is_dir() else "FILE"
        print(f"  [{t}] {rel}")


def main():
    parser = argparse.ArgumentParser(description="Google Drive Local Storage Manager")
    parser.add_argument("--project-dir", default=os.getcwd(), help="대상 프로젝트 루트 디렉터리 (기본값: 현재 CWD)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("detect", help="감지된 구글 드라이브 및 활성 경로 정보 출력")
    subparsers.add_parser("status", help="프로젝트의 정션 마운트 상태 출력")
    subparsers.add_parser("init", help="원클릭 1회 일괄 마운트 및 secrets 동기화")

    link_p = subparsers.add_parser("link", help="특정 폴더를 구글 드라이브와 정션 연결")
    link_p.add_argument("folder", help="로컬 폴더 이름 (예: input_staging)")

    unlink_p = subparsers.add_parser("unlink", help="특정 폴더의 정션 연결 해제")
    unlink_p.add_argument("folder", help="로컬 폴더 이름 (예: input_staging)")

    sync_p = subparsers.add_parser("sync-secrets", help="보안 파일(.env 등) 동기화")
    sync_p.add_argument("--direction", choices=["push", "pull", "auto"], default="auto", help="동기화 방향")

    save_p = subparsers.add_parser("save", help="개별 파일 구글 드라이브에 저장")
    save_p.add_argument("src", help="저장할 로컬 파일 경로")
    save_p.add_argument("dst_rel", help="구글 드라이브 내 상대 경로")

    read_p = subparsers.add_parser("read", help="구글 드라이브의 파일 가져오기")
    read_p.add_argument("src_rel", help="구글 드라이브 내 상대 경로")
    read_p.add_argument("dst", help="저장할 로컬 파일 경로")

    del_p = subparsers.add_parser("delete", help="구글 드라이브 파일 삭제")
    del_p.add_argument("target_rel", help="삭제할 파일 상대 경로")

    list_p = subparsers.add_parser("list", help="구글 드라이브 내 파일 목록 출력")
    list_p.add_argument("subfolder", nargs="?", default="", help="조회할 하위 폴더")

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    if args.command == "detect":
        cmd_detect(project_dir)
    elif args.command == "status":
        cmd_status(project_dir)
    elif args.command == "init":
        cmd_init(project_dir)
    elif args.command == "link":
        cmd_link(args.folder, project_dir)
    elif args.command == "unlink":
        cmd_unlink(args.folder, project_dir)
    elif args.command == "sync-secrets":
        cmd_sync_secrets(args.direction, project_dir)
    elif args.command == "save":
        cmd_save(args.src, args.dst_rel, project_dir)
    elif args.command == "read":
        cmd_read(args.src_rel, args.dst, project_dir)
    elif args.command == "delete":
        cmd_delete(args.target_rel, project_dir)
    elif args.command == "list":
        cmd_list(args.subfolder, project_dir)


if __name__ == "__main__":
    main()
