#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian Local REST API & MCP Client Helper
-------------------------------------------
Obsidian Local REST API(HTTPS/HTTP)와 통신하여 볼트의 노트를 검색, 조회, 생성,
수정(Patch), 삭제하고, 활성 문서 추적 및 옵시디언 명령어를 원격 실행하는 범용 CLI/라이브러리.

의존성: Python 표준 라이브러리만 사용 (외부 pip 패키지 불필요)
"""

import sys
import os
import ssl
import json
import urllib.request
import urllib.parse
import urllib.error
import argparse
from pathlib import Path

# Windows 콘솔 인코딩 문제 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_env():
    """탐색 순서에 따라 .env 파일에서 환경변수를 로드합니다."""
    candidates = [
        Path.cwd() / ".env",
        Path.home() / ".gemini" / "config" / "skills" / "obsidian-manager" / ".env",
        Path(r"C:\Users\maeng-gun\Desktop\python\agy-global-skills\.env"),
    ]
    for env_path in candidates:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass


load_env()

DEFAULT_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
DEFAULT_URL = os.environ.get("OBSIDIAN_URL", "https://127.0.0.1:27124")


class ObsidianClient:
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY

        # 자체 서명 인증서 허용 SSL 컨텍스트
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def _request(self, method: str, path: str, headers: dict = None, data: bytes = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        req_headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                status = resp.status
                resp_headers = dict(resp.headers)
                content = resp.read()
                return status, resp_headers, content
        except urllib.error.HTTPError as e:
            err_content = e.read()
            return e.code, dict(e.headers), err_content
        except Exception as e:
            raise RuntimeError(f"Connection error to Obsidian Local REST API ({url}): {e}")

    def get_status(self):
        status, _, body = self._request("GET", "/")
        return json.loads(body.decode("utf-8"))

    def list_dir(self, path: str = ""):
        endpoint = f"vault/{urllib.parse.quote(path)}/" if path else "vault/"
        headers = {"Accept": "application/json"}
        status, _, body = self._request("GET", endpoint, headers=headers)
        if status != 200:
            raise RuntimeError(f"Failed to list directory (status {status}): {body.decode('utf-8', errors='replace')}")
        return json.loads(body.decode("utf-8"))

    def read_file(self, path: str):
        endpoint = f"vault/{urllib.parse.quote(path)}"
        headers = {"Accept": "text/markdown, */*"}
        status, resp_headers, body = self._request("GET", endpoint, headers=headers)
        if status != 200:
            raise RuntimeError(f"Failed to read file (status {status}): {body.decode('utf-8', errors='replace')}")
        return body.decode("utf-8", errors="replace"), resp_headers

    def write_file(self, path: str, content: str):
        endpoint = f"vault/{urllib.parse.quote(path)}"
        headers = {"Content-Type": "text/markdown; charset=utf-8"}
        data = content.encode("utf-8")
        status, _, body = self._request("PUT", endpoint, headers=headers, data=data)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to write file (status {status}): {body.decode('utf-8', errors='replace')}")
        return True

    def append_file(self, path: str, content: str):
        endpoint = f"vault/{urllib.parse.quote(path)}"
        headers = {"Content-Type": "text/markdown; charset=utf-8"}
        data = content.encode("utf-8")
        status, _, body = self._request("POST", endpoint, headers=headers, data=data)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to append to file (status {status}): {body.decode('utf-8', errors='replace')}")
        return True

    def delete_file(self, path: str):
        endpoint = f"vault/{urllib.parse.quote(path)}"
        status, _, body = self._request("DELETE", endpoint)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to delete file (status {status}): {body.decode('utf-8', errors='replace')}")
        return True

    def patch_file(self, path: str, content: str, heading: str = None, block: str = None, action: str = "replace"):
        """
        특정 헤딩이나 블록을 대상으로 부분 수정(Patch)합니다.
        action: 'replace', 'append', 'prepend'
        """
        endpoint = f"vault/{urllib.parse.quote(path)}"
        headers = {
            "Content-Type": "text/markdown; charset=utf-8",
            "Operation": action,
        }
        if heading:
            headers["Heading"] = urllib.parse.quote(heading)
        if block:
            headers["Block"] = urllib.parse.quote(block)

        data = content.encode("utf-8")
        status, _, body = self._request("PATCH", endpoint, headers=headers, data=data)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to patch file (status {status}): {body.decode('utf-8', errors='replace')}")
        return True

    def search_simple(self, query: str):
        endpoint = f"search/simple/?query={urllib.parse.quote(query)}"
        status, _, body = self._request("POST", endpoint)
        if status != 200:
            raise RuntimeError(f"Search failed (status {status}): {body.decode('utf-8', errors='replace')}")
        return json.loads(body.decode("utf-8"))

    def get_active(self):
        status, headers, body = self._request("GET", "active/")
        if status != 200:
            raise RuntimeError(f"Failed to get active note (status {status})")
        location = headers.get("Content-Location", "")
        # unquote location
        path = urllib.parse.unquote(location)
        return path, body.decode("utf-8", errors="replace")

    def open_file(self, path: str):
        endpoint = f"open/{urllib.parse.quote(path)}"
        status, _, body = self._request("POST", endpoint)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to open file in Obsidian (status {status}): {body.decode('utf-8', errors='replace')}")
        return True

    def list_commands(self):
        status, _, body = self._request("GET", "commands/")
        if status != 200:
            raise RuntimeError(f"Failed to list commands (status {status})")
        return json.loads(body.decode("utf-8"))

    def execute_command(self, command_id: str):
        endpoint = f"commands/{urllib.parse.quote(command_id)}/"
        status, _, body = self._request("POST", endpoint)
        if status not in (200, 204):
            raise RuntimeError(f"Failed to execute command (status {status})")
        return True


def main():
    parser = argparse.ArgumentParser(description="Obsidian Local REST API Client")
    parser.add_argument("--url", default=DEFAULT_URL, help="Obsidian Local REST API base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API Key token")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Check server status and plugin version")

    # list
    p_list = subparsers.add_parser("list", help="List files in a vault directory")
    p_list.add_argument("path", nargs="?", default="", help="Subdirectory path in vault")

    # read
    p_read = subparsers.add_parser("read", help="Read note content")
    p_read.add_argument("path", help="Relative file path in vault")

    # write
    p_write = subparsers.add_parser("write", help="Create or overwrite note")
    p_write.add_argument("path", help="Relative file path in vault")
    p_write.add_argument("--content", help="Text content to write")
    p_write.add_argument("--file", help="File path containing text content")

    # append
    p_app = subparsers.add_parser("append", help="Append text to existing note")
    p_app.add_argument("path", help="Relative file path in vault")
    p_app.add_argument("--content", help="Text content to append")
    p_app.add_argument("--file", help="File path containing text content")

    # patch
    p_patch = subparsers.add_parser("patch", help="Patch specific heading or block in note")
    p_patch.add_argument("path", help="Relative file path in vault")
    p_patch.add_argument("--heading", help="Target heading text")
    p_patch.add_argument("--block", help="Target block reference")
    p_patch.add_argument("--action", choices=["replace", "append", "prepend"], default="replace")
    p_patch.add_argument("--content", help="New content")
    p_patch.add_argument("--file", help="File path containing content")

    # delete
    p_del = subparsers.add_parser("delete", help="Delete note")
    p_del.add_argument("path", help="Relative file path in vault")

    # search
    p_search = subparsers.add_parser("search", help="Simple full-text search")
    p_search.add_argument("query", help="Search query string")

    # active
    subparsers.add_parser("active", help="Get currently active note path and content")

    # open
    p_open = subparsers.add_parser("open", help="Open note in Obsidian UI")
    p_open.add_argument("path", help="Relative file path in vault")

    # commands
    subparsers.add_parser("commands", help="List available Obsidian commands")

    # exec-command
    p_exec = subparsers.add_parser("exec-command", help="Execute an Obsidian command")
    p_exec.add_argument("command_id", help="Command identifier")

    args = parser.parse_args()

    client = ObsidianClient(base_url=args.url, api_key=args.api_key)

    try:
        if args.command == "status":
            res = client.get_status()
            print(json.dumps(res, indent=2, ensure_ascii=False))

        elif args.command == "list":
            res = client.list_dir(args.path)
            print(json.dumps(res, indent=2, ensure_ascii=False))

        elif args.command == "read":
            content, _ = client.read_file(args.path)
            print(content)

        elif args.command == "write":
            content = args.content
            if args.file:
                with open(args.file, "r", encoding="utf-8") as f:
                    content = f.read()
            if content is None:
                content = sys.stdin.read()
            client.write_file(args.path, content)
            print(f"[OK] Successfully wrote: {args.path}")

        elif args.command == "append":
            content = args.content
            if args.file:
                with open(args.file, "r", encoding="utf-8") as f:
                    content = f.read()
            if content is None:
                content = sys.stdin.read()
            client.append_file(args.path, content)
            print(f"[OK] Successfully appended to: {args.path}")

        elif args.command == "patch":
            content = args.content
            if args.file:
                with open(args.file, "r", encoding="utf-8") as f:
                    content = f.read()
            if content is None:
                content = sys.stdin.read()
            client.patch_file(args.path, content, heading=args.heading, block=args.block, action=args.action)
            print(f"[OK] Successfully patched: {args.path}")

        elif args.command == "delete":
            client.delete_file(args.path)
            print(f"[OK] Successfully deleted: {args.path}")

        elif args.command == "search":
            res = client.search_simple(args.query)
            print(json.dumps(res, indent=2, ensure_ascii=False))

        elif args.command == "active":
            path, content = client.get_active()
            print(f"Active File: {path}\n" + "=" * 40 + "\n" + content)

        elif args.command == "open":
            client.open_file(args.path)
            print(f"[OK] Opened in Obsidian: {args.path}")

        elif args.command == "commands":
            res = client.list_commands()
            print(json.dumps(res, indent=2, ensure_ascii=False))

        elif args.command == "exec-command":
            client.execute_command(args.command_id)
            print(f"[OK] Executed command: {args.command_id}")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
