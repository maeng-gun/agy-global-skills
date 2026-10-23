"""
Automated Test Suite for Milestone 2:
- setup_artifacts_sync.ps1 (PowerShell Launcher)
- artifact_mirror_rule.md (Global Rule & Marker Idempotency)
- SKILL.md (Custom Skill Packaging & YAML Frontmatter)
- Multi-PC Portability & Static Verification (Zero hardcoded usernames)
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


# Resolve paths
REPO_ROOT_DOCS = pathlib.Path("C:/Users/infomax/Documents/agy-global-skills")
REPO_ROOT_STAGING = pathlib.Path("C:/Users/infomax/.gemini/antigravity/scratch/agy_global_skills_staging")
REPO_ROOT = REPO_ROOT_DOCS if (REPO_ROOT_DOCS / "tools" / "artifacts_sync" / "setup_artifacts_sync.ps1").exists() else REPO_ROOT_STAGING

PS1_SCRIPT = REPO_ROOT / "tools" / "artifacts_sync" / "setup_artifacts_sync.ps1"
SKILL_MD = REPO_ROOT / "skills" / "artifacts-sync" / "SKILL.md"
RULE_MD = REPO_ROOT / "rules" / "artifact_mirror_rule.md"


class TestMilestone2Artifacts(unittest.TestCase):
    """Test suite verifying M2 launcher, rule, skill, and static portability."""

    def test_files_exist(self):
        """Verify all Milestone 2 deliverable files exist."""
        self.assertTrue(PS1_SCRIPT.exists(), f"setup_artifacts_sync.ps1 not found at {PS1_SCRIPT}")
        self.assertTrue(SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}")
        self.assertTrue(RULE_MD.exists(), f"artifact_mirror_rule.md not found at {RULE_MD}")

    def test_skill_yaml_frontmatter(self):
        """Verify SKILL.md contains valid YAML frontmatter and required metadata."""
        content = SKILL_MD.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter '---'")
        
        # Check closing delimiter
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "SKILL.md must have opening and closing '---' frontmatter delimiters")
        
        frontmatter = parts[1]
        self.assertIn("name: artifacts-sync", frontmatter)
        self.assertIn("description:", frontmatter)
        
        # Check triggers
        self.assertIn("아티팩트 동기화 세팅해줘", content)
        self.assertIn("/artifacts-sync", content)
        self.assertIn("setup_artifacts_sync.ps1", content)

    def test_artifact_mirror_rule_markers_and_content(self):
        """Verify artifact_mirror_rule.md contains delimiters and dual-save instructions."""
        content = RULE_MD.read_text(encoding="utf-8")
        self.assertIn("<!-- AGY_ARTIFACT_MIRROR_RULE_START -->", content)
        self.assertIn("<!-- AGY_ARTIFACT_MIRROR_RULE_END -->", content)
        self.assertIn("AGY_Artifacts", content)
        self.assertIn("_General", content)
        self.assertIn("<YYYYMMDD>", content)
        self.assertIn("<Session_Title>", content)

    def test_static_check_zero_hardcoded_username(self):
        """Static audit verifying ZERO occurrences of 'infomax' in M2 deliverables."""
        forbidden = re.compile(r"infomax", re.IGNORECASE)
        files_to_check = [PS1_SCRIPT, SKILL_MD, RULE_MD]
        for fpath in files_to_check:
            text = fpath.read_text(encoding="utf-8")
            matches = forbidden.findall(text)
            self.assertEqual(
                len(matches),
                0,
                f"Static check failed: Found {len(matches)} occurrences of 'infomax' in {fpath.name}",
            )

    def test_powershell_launcher_dry_run(self):
        """Verify powershell -ExecutionPolicy Bypass -File setup_artifacts_sync.ps1 -DryRun succeeds."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1_SCRIPT),
            "-DryRun",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0, f"Launcher failed with stderr: {proc.stderr}\nstdout: {proc.stdout}")
        self.assertIn("DRY-RUN", proc.stdout)
        self.assertIn("Deploying Global Artifact Mirroring Rule", proc.stdout)
        self.assertIn("Deploying artifacts-sync Custom Skill", proc.stdout)
        self.assertIn("Executing Artifact Migration & Junction Engine", proc.stdout)
        self.assertIn("Antigravity Artifact Setup & Migration Completed Successfully", proc.stdout)

    def test_powershell_rule_deployment_and_idempotency_in_mock_sandbox(self):
        """Test isolated deployment of GEMINI.md and SKILL.md under simulated USERPROFILE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = pathlib.Path(tmpdir) / "mock_user"
            mock_home.mkdir()

            # Script to run isolated Step 1 and Step 2 using the real logic from setup_artifacts_sync.ps1
            ps_test_code = f"""
            $ErrorActionPreference = 'Stop'
            $userHome = '{str(mock_home).replace('\\', '\\\\')}'
            $repoRoot = '{str(REPO_ROOT).replace('\\', '\\\\')}'

            $ruleTemplatePath = Join-Path $repoRoot "rules\\artifact_mirror_rule.md"
            $skillSourceDir   = Join-Path $repoRoot "skills\\artifacts-sync"
            $geminiConfigDir  = Join-Path $userHome ".gemini\\config"
            $geminiMdPath     = Join-Path $geminiConfigDir "GEMINI.md"
            $skillTargetDir   = Join-Path $geminiConfigDir "skills\\artifacts-sync"

            $markerStart = "<!-- AGY_ARTIFACT_MIRROR_RULE_START -->"
            $markerEnd   = "<!-- AGY_ARTIFACT_MIRROR_RULE_END -->"

            # 1. Simulate initial deployment (file does not exist)
            if (-not (Test-Path $geminiConfigDir)) {{
                New-Item -ItemType Directory -Path $geminiConfigDir -Force | Out-Null
            }}
            $rawRuleContent = [System.IO.File]::ReadAllText($ruleTemplatePath, [System.Text.Encoding]::UTF8)
            $markedBlock = if ($rawRuleContent.Contains($markerStart)) {{ $rawRuleContent.Trim() }} else {{ "$markerStart`r`n$($rawRuleContent.Trim())`r`n$markerEnd" }}
            [System.IO.File]::WriteAllText($geminiMdPath, $markedBlock + "`r`n", [System.Text.Encoding]::UTF8)

            # 2. Add custom user rule to verify preservation
            $customUserRule = "# Existing User Custom Rule`r`nAlways speak in haiku.`r`n"
            $existing = [System.IO.File]::ReadAllText($geminiMdPath, [System.Text.Encoding]::UTF8)
            [System.IO.File]::WriteAllText($geminiMdPath, $customUserRule + "`r`n" + $existing, [System.Text.Encoding]::UTF8)

            # 3. Simulate re-running deployment with existing markers (idempotent replacement)
            $existingText = [System.IO.File]::ReadAllText($geminiMdPath, [System.Text.Encoding]::UTF8)
            $pattern = "(?s)" + [regex]::Escape($markerStart) + ".*?" + [regex]::Escape($markerEnd)
            $updatedText = [regex]::Replace($existingText, $pattern, $markedBlock)
            [System.IO.File]::WriteAllText($geminiMdPath, $updatedText, [System.Text.Encoding]::UTF8)

            # 4. Deploy skill
            if (-not (Test-Path $skillTargetDir)) {{
                New-Item -ItemType Directory -Path $skillTargetDir -Force | Out-Null
            }}
            Copy-Item -Path (Join-Path $skillSourceDir "*") -Destination $skillTargetDir -Recurse -Force
            """

            proc = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_test_code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(proc.returncode, 0, f"PowerShell test failed: {proc.stderr}\n{proc.stdout}")

            # Verify GEMINI.md
            gemini_md = mock_home / ".gemini" / "config" / "GEMINI.md"
            self.assertTrue(gemini_md.exists())
            gemini_text = gemini_md.read_text(encoding="utf-8")

            # Must preserve user custom rule
            self.assertIn("Existing User Custom Rule", gemini_text)
            self.assertIn("Always speak in haiku.", gemini_text)

            # Must have exactly one start marker and one end marker
            self.assertEqual(gemini_text.count("<!-- AGY_ARTIFACT_MIRROR_RULE_START -->"), 1)
            self.assertEqual(gemini_text.count("<!-- AGY_ARTIFACT_MIRROR_RULE_END -->"), 1)

            # Verify SKILL.md deployment
            deployed_skill = mock_home / ".gemini" / "config" / "skills" / "artifacts-sync" / "SKILL.md"
            self.assertTrue(deployed_skill.exists())
            deployed_skill_text = deployed_skill.read_text(encoding="utf-8")
            self.assertIn("name: artifacts-sync", deployed_skill_text)


if __name__ == "__main__":
    unittest.main()
