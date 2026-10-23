#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Drive Storage Manager Unit Test
"""

import sys
import unittest
from pathlib import Path

# 테스트 대상 스크립트 모듈 임포트
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gdrive_manager


class TestGDriveManager(unittest.TestCase):

    def setUp(self):
        self.project_dir = Path(__file__).resolve().parent.parent
        self.config = gdrive_manager.load_project_config(self.project_dir)

    def test_01_detect_google_drives(self):
        """구글 드라이브 감지 기능 테스트"""
        drives = gdrive_manager.detect_windows_google_drives()
        self.assertGreater(len(drives), 0, "최소 1개 이상의 구글 드라이브가 감지되어야 합니다.")
        print(f"\n[Test] 감지된 드라이브 수: {len(drives)}")
        for d in drives:
            print(f"       -> {d['drive_letter']} ({d['volume_name']}) : {d['my_drive']}")
            self.assertTrue(d["my_drive"].exists(), f"{d['my_drive']} 경로가 존재해야 합니다.")

    def test_02_resolve_gdrive_root(self):
        """3단계 계층 탐색으로 구글 드라이브 루트 확인"""
        resolved = gdrive_manager.resolve_gdrive_root(self.project_dir, self.config)
        self.assertTrue(resolved.exists(), f"결정된 루트 경로 {resolved}가 실제로 존재해야 합니다.")
        print(f"\n[Test] 확정된 구글 드라이브 루트: {resolved}")

    def test_03_target_workspace_dir(self):
        """타깃 워크스페이스 디렉터리 생성 및 확인"""
        resolved = gdrive_manager.resolve_gdrive_root(self.project_dir, self.config)
        target_ws = gdrive_manager.get_target_workspace_dir(self.project_dir, self.config, resolved)
        self.assertTrue(target_ws.exists())
        print(f"\n[Test] 타깃 워크스페이스: {target_ws}")

    def test_04_junction_link_and_unlink(self):
        """임시 폴더에 대한 정션 연결, 파일 I/O 및 안전 해제 테스트"""
        resolved = gdrive_manager.resolve_gdrive_root(self.project_dir, self.config)
        target_ws = gdrive_manager.get_target_workspace_dir(self.project_dir, self.config, resolved)

        test_local = self.project_dir / "_test_temp_junction"
        test_gdrive_sub = target_ws / "_test_temp_junction"

        # 1. 로컬에 임시 파일 생성
        test_local.mkdir(parents=True, exist_ok=True)
        sample_file = test_local / "hello.txt"
        sample_file.write_text("Hello GDrive Test", encoding="utf-8")

        # 2. 링크 실행 (기존 파일 이전 + 정션 연결)
        success = gdrive_manager.link_folder(test_local, test_gdrive_sub)
        self.assertTrue(success, "정션 연결이 성공해야 합니다.")
        self.assertTrue(gdrive_manager.is_junction_or_link(test_local), "정션 상태여야 합니다.")

        # 3. 데이터 보존 확인
        self.assertTrue((test_local / "hello.txt").exists(), "로컬 정션을 통해 파일이 읽혀야 합니다.")
        self.assertTrue((test_gdrive_sub / "hello.txt").exists(), "구글 드라이브 실타깃에 파일이 존재해야 합니다.")

        # 4. 정션 해제
        unlink_success = gdrive_manager.unlink_folder(test_local)
        self.assertTrue(unlink_success, "정션 해제가 성공해야 합니다.")
        self.assertFalse(gdrive_manager.is_junction_or_link(test_local), "정션이 해제되어야 합니다.")
        self.assertTrue((test_gdrive_sub / "hello.txt").exists(), "구글 드라이브 원본 데이터는 보존되어야 합니다.")

        # 정리
        if test_local.exists():
            test_local.rmdir()
        if test_gdrive_sub.exists():
            import shutil
            shutil.rmtree(str(test_gdrive_sub))
        print("\n[Test] 정션 연결 및 데이터 보존/해제 테스트 완료")


if __name__ == "__main__":
    unittest.main()
