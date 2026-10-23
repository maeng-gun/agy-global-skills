# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "notion-client",
#     "markdown-it-py",
#     "python-dotenv",
# ]
# ///

import os
import sys
import json
import time
import re
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from notion_client import Client
from markdown_it import MarkdownIt

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("notion_manager")

# Limits
MAX_BLOCKS_PER_REQUEST = 100
MAX_TEXT_LENGTH = 2000

# ==========================================
# Utility Functions
# ==========================================

def normalize_date(date_str: str) -> str:
    """Convert YYYYMMDD or YYYY-MM-DD into YYYY-MM-DD."""
    date_str = str(date_str).strip()
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return date_str

def normalize_uuid(uuid_str: str) -> str:
    """Normalize UUID by removing hyphens and converting to lowercase."""
    return str(uuid_str).strip().replace("-", "").lower()

def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> List[str]:
    """Split text into chunks if it exceeds limit."""
    return [text[i:i+limit] for i in range(0, len(text), limit)] if text else [""]

def get_db_schema_and_datasource(client: Client, db_id: str):
    """Retrieve database schema properties and data_source_id if available."""
    db_properties = {}
    ds_id = None
    try:
        db_info = client.databases.retrieve(db_id)
        db_properties = db_info.get("properties", {})
        if db_info.get("data_sources"):
            ds_id = db_info["data_sources"][0]["id"]
            try:
                ds_info = client.data_sources.retrieve(ds_id)
                db_properties = ds_info.get("properties", db_properties)
            except Exception as e:
                logger.warning(f"Failed to retrieve data_source info ({ds_id}): {e}")
    except Exception as e:
        logger.warning(f"Failed to retrieve database info ({db_id}): {e}")
    return db_properties, ds_id

# ==========================================
# Markdown Parsing to Notion Blocks
# ==========================================

def parse_inline_tokens(inline_token) -> List[Dict[str, Any]]:
    """Parse markdown-it inline tokens into Notion rich_text objects."""
    rich_text = []
    if not inline_token or not inline_token.children:
        return rich_text

    current_annotations = {
        "bold": False,
        "italic": False,
        "strikethrough": False,
        "code": False,
    }

    for child in inline_token.children:
        if child.type == "text":
            chunks = split_text(child.content)
            for chunk in chunks:
                rich_text.append({
                    "type": "text",
                    "text": {"content": chunk},
                    "annotations": current_annotations.copy()
                })
        elif child.type == "strong_open":
            current_annotations["bold"] = True
        elif child.type == "strong_close":
            current_annotations["bold"] = False
        elif child.type == "em_open":
            current_annotations["italic"] = True
        elif child.type == "em_close":
            current_annotations["italic"] = False
        elif child.type == "s_open":
            current_annotations["strikethrough"] = True
        elif child.type == "s_close":
            current_annotations["strikethrough"] = False
        elif child.type == "code_inline":
            chunks = split_text(child.content)
            for chunk in chunks:
                rich_text.append({
                    "type": "text",
                    "text": {"content": chunk},
                    "annotations": {**current_annotations, "code": True}
                })
        elif child.type in ("link_open", "link_close"):
            pass

    if not rich_text:
        rich_text.append({"type": "text", "text": {"content": ""}})

    return rich_text

def markdown_to_notion_blocks(md_text: str) -> List[Dict[str, Any]]:
    """Convert standard markdown text to Notion block structure."""
    md = MarkdownIt().enable("table")
    tokens = md.parse(md_text)

    blocks = []
    list_stack = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "paragraph_open":
            inline = tokens[i+1]
            if inline.type == "inline":
                rich_text = parse_inline_tokens(inline)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text}
                })
            i += 2

        elif token.type == "heading_open":
            level = token.tag
            inline = tokens[i+1]
            notion_type = "heading_1"
            if level == "h2":
                notion_type = "heading_2"
            elif level in ("h3", "h4", "h5", "h6"):
                notion_type = "heading_3"

            if inline.type == "inline":
                rich_text = parse_inline_tokens(inline)
                blocks.append({
                    "object": "block",
                    "type": notion_type,
                    notion_type: {"rich_text": rich_text}
                })
            i += 2

        elif token.type == "bullet_list_open":
            list_stack.append("bulleted_list_item")
            i += 1
        elif token.type == "ordered_list_open":
            list_stack.append("numbered_list_item")
            i += 1
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
            i += 1

        elif token.type == "list_item_open":
            cur_type = list_stack[-1] if list_stack else "bulleted_list_item"
            if i+1 < len(tokens) and tokens[i+1].type == "paragraph_open":
                inline = tokens[i+2]
                if inline.type == "inline":
                    rich_text = parse_inline_tokens(inline)
                    item_block = {
                        "object": "block",
                        "type": cur_type,
                        cur_type: {"rich_text": rich_text}
                    }
                    if len(list_stack) > 1 and blocks and blocks[-1]["type"] in ("bulleted_list_item", "numbered_list_item"):
                        p_type = blocks[-1]["type"]
                        if "children" not in blocks[-1][p_type]:
                            blocks[-1][p_type]["children"] = []
                        blocks[-1][p_type]["children"].append(item_block)
                    else:
                        blocks.append(item_block)
                i += 3
            else:
                i += 1

        elif token.type in ("fence", "code_block"):
            language = token.info.strip() if token.info else "plain text"
            if language == "":
                language = "plain text"
            chunks = split_text(token.content)
            for chunk in chunks:
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        "language": "plain text"
                    }
                })
            i += 1

        elif token.type == "blockquote_open":
            inline = tokens[i+2]
            if inline.type == "inline":
                rich_text = parse_inline_tokens(inline)
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {"rich_text": rich_text}
                })
            while i < len(tokens) and tokens[i].type != "blockquote_close":
                i += 1
            i += 1

        elif token.type == "hr":
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            i += 1

        elif token.type == "table_open":
            rows = []
            has_header = False
            i += 1
            while i < len(tokens) and tokens[i].type != "table_close":
                if tokens[i].type == "thead_open":
                    has_header = True
                    i += 1
                elif tokens[i].type == "tr_open":
                    cells = []
                    i += 1
                    while i < len(tokens) and tokens[i].type != "tr_close":
                        if tokens[i].type in ("th_open", "td_open"):
                            inline = tokens[i+1]
                            if inline.type == "inline":
                                cells.append(parse_inline_tokens(inline))
                            else:
                                cells.append([{"type": "text", "text": {"content": ""}}])
                            i += 3
                        else:
                            i += 1
                    if cells:
                        rows.append({
                            "type": "table_row",
                            "table_row": {"cells": cells}
                        })
                    i += 1
                else:
                    i += 1
            if rows:
                table_width = max(len(r["table_row"]["cells"]) for r in rows)
                for r in rows:
                    while len(r["table_row"]["cells"]) < table_width:
                        r["table_row"]["cells"].append([{"type": "text", "text": {"content": ""}}])
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": table_width,
                        "has_column_header": has_header,
                        "has_row_header": False,
                        "children": rows
                    }
                })
            i += 1
        else:
            i += 1

    return blocks

# ==========================================
# Subcommand: upload
# ==========================================

def run_upload(args):
    load_dotenv(Path(os.getcwd()) / ".env")

    api_key = args.api_key or os.getenv("NOTION_API_KEY")
    db_id = args.db_id or os.getenv("NOTION_DB_ID")

    if not api_key or not db_id:
        logger.error("NOTION_API_KEY or NOTION_DB_ID is missing from environment / arguments.")
        sys.exit(1)

    md_path = Path(args.content)
    meta_path = Path(args.meta)

    if not md_path.exists():
        logger.error(f"Content file not found: {md_path}")
        sys.exit(1)

    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read metadata file ({meta_path}): {e}")

    # CLI args override meta json
    title = args.title or meta.get("title", "Untitled AI Upload")
    icon = args.icon or meta.get("icon", "📄")

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
    except Exception as e:
        logger.error(f"Failed to read content file: {e}")
        sys.exit(1)

    blocks = markdown_to_notion_blocks(md_text)

    # Remove the first block if it duplicates title or is a redundant header
    if blocks:
        first_block_type = blocks[0].get("type")
        if first_block_type in blocks[0] and "rich_text" in blocks[0][first_block_type]:
            first_block_text = "".join(t["text"]["content"] for t in blocks[0][first_block_type]["rich_text"]).strip()
            if first_block_text == title.strip() or first_block_text.startswith("Daily Macro") or first_block_type == "heading_1":
                blocks.pop(0)

    client = Client(auth=api_key)
    db_properties, _ = get_db_schema_and_datasource(client, db_id)

    # Build properties
    properties = {}
    title_prop_name = "이름"
    for k, v in db_properties.items():
        if v.get("type") == "title":
            title_prop_name = k
            break
    properties[title_prop_name] = {
        "title": [{"text": {"content": title}}]
    }

    mode_env = os.getenv("MODE")
    mode_props = {}
    if mode_env:
        try:
            mode_props = json.loads(mode_env)
        except Exception as e:
            logger.warning(f"Failed to parse MODE env var as JSON: {e}")

    if mode_props:
        for key, val in mode_props.items():
            if key in db_properties:
                prop_type = db_properties[key]["type"]
                if prop_type == "select":
                    properties[key] = {"select": {"name": str(val)}}
                elif prop_type == "status":
                    properties[key] = {"status": {"name": str(val)}}
                elif prop_type == "rich_text":
                    properties[key] = {"rich_text": [{"text": {"content": str(val)}}]}
                elif prop_type == "multi_select":
                    properties[key] = {"multi_select": [{"name": str(v)} for v in val] if isinstance(val, list) else [{"name": str(val)}]}
    else:
        # 1. Status mapping
        status_prop = None
        for candidate in ["상태", "읽음상태", "Status"]:
            if candidate in db_properties and db_properties[candidate]["type"] == "status":
                status_prop = candidate
                break
        if status_prop:
            opts = [o["name"] for o in db_properties[status_prop].get("status", {}).get("options", [])]
            s_val = args.status or meta.get("status", "안읽음")
            if s_val not in opts:
                s_val = "미처리" if "미처리" in opts else (opts[0] if opts else s_val)
            properties[status_prop] = {"status": {"name": s_val}}

        # 2. Category mapping
        cat_prop = None
        for candidate in ["구분", "카테고리", "Category"]:
            if candidate in db_properties and db_properties[candidate]["type"] == "select":
                cat_prop = candidate
                break
        if cat_prop:
            opts = [o["name"] for o in db_properties[cat_prop].get("select", {}).get("options", [])]
            c_val = args.category or meta.get("category", "AI생성")
            if c_val not in opts:
                if "AI생성" in opts:
                    c_val = "AI생성"
                elif "AI 생성" in opts:
                    c_val = "AI 생성"
                elif "문서" in opts:
                    c_val = "문서"
                elif opts:
                    c_val = opts[0]
            properties[cat_prop] = {"select": {"name": c_val}}

        # 3. Date mapping
        date_prop = None
        for candidate in ["날짜", "작성일", "Date"]:
            if candidate in db_properties and db_properties[candidate]["type"] == "date":
                date_prop = candidate
                break
        if date_prop:
            d_val = args.date or meta.get("date")
            if not d_val:
                m = re.search(r"\d{4}-\d{2}-\d{2}", title)
                if m:
                    d_val = m.group(0)
            if d_val:
                properties[date_prop] = {"date": {"start": normalize_date(d_val)}}

        # 4. Relation topic mapping
        topic_page_id = args.topic_id or meta.get("topic_page_id") or meta.get("주제") or os.getenv("NOTION_TOPIC_PAGE_ID")
        if topic_page_id:
            rel_prop = args.relation_prop
            if not rel_prop:
                for candidate in ["주제", "Topic"]:
                    if candidate in db_properties and db_properties[candidate]["type"] == "relation":
                        rel_prop = candidate
                        break
            if not rel_prop:
                for k, v in db_properties.items():
                    if v.get("type") == "relation":
                        rel_prop = k
                        break
            if rel_prop:
                properties[rel_prop] = {"relation": [{"id": topic_page_id}]}

    logger.info("Creating Notion page...")
    first_batch = blocks[:MAX_BLOCKS_PER_REQUEST]
    remaining_blocks = blocks[MAX_BLOCKS_PER_REQUEST:]

    try:
        new_page = client.pages.create(
            parent={"database_id": db_id},
            properties=properties,
            children=first_batch,
            icon={"type": "emoji", "emoji": icon}
        )
        page_id = new_page["id"]
        page_url = new_page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

        while remaining_blocks:
            batch = remaining_blocks[:MAX_BLOCKS_PER_REQUEST]
            remaining_blocks = remaining_blocks[MAX_BLOCKS_PER_REQUEST:]
            logger.info(f"Appending {len(batch)} blocks to the page...")
            client.blocks.children.append(
                block_id=page_id,
                children=batch
            )
            time.sleep(0.5)

        print(f"\nSuccessfully uploaded to Notion!")
        print(f"Page URL: {page_url}")

        if not args.no_cleanup:
            if md_path.exists():
                md_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            logger.info("Cleaned up temporary scratch files.")

    except Exception as e:
        logger.error(f"Error communicating with Notion API during upload: {e}")
        sys.exit(1)

# ==========================================
# Subcommand: delete (archive)
# ==========================================

def run_delete(args):
    load_dotenv(Path(os.getcwd()) / ".env")

    api_key = args.api_key or os.getenv("NOTION_API_KEY")
    db_id = args.db_id or os.getenv("NOTION_DB_ID")

    if not api_key or not db_id:
        logger.error("NOTION_API_KEY or NOTION_DB_ID is missing from environment / arguments.")
        sys.exit(1)

    meta_path = Path(args.meta)
    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read metadata file ({meta_path}): {e}")

    # Resolve criteria: CLI takes precedence over meta
    target_date = args.date or meta.get("date")
    topic_id = args.topic_id or meta.get("topic_page_id") or meta.get("주제") or os.getenv("NOTION_TOPIC_PAGE_ID")
    topic_name = args.topic_name or meta.get("topic_name", "매크로 분석 스코어링" if topic_id else "")
    rel_prop_name = args.relation_prop

    if not target_date:
        logger.error("Target date is required for deletion. Provide via --date <YYYY-MM-DD> or --meta <path>.")
        sys.exit(1)

    target_date_iso = normalize_date(target_date)

    # Safety Guard: Require a narrowing filter (topic_id, property, etc.) or explicit --force-all-topics
    if not topic_id and not args.property and not args.force_all_topics:
        logger.error(
            "[SAFETY GUARD] No topic-id or property filter specified for date deletion! "
            "Deleting pages solely by date without specifying a topic/relation risks deleting unrelated pages. "
            "Please specify --topic-id <UUID> (or provide it in --meta), or pass --force-all-topics if you intentionally wish to delete all pages for this date."
        )
        sys.exit(1)

    clean_target_topic_id = normalize_uuid(topic_id) if topic_id else None
    filter_desc = f"date: {target_date_iso}"
    if clean_target_topic_id:
        filter_desc += f", topic: '{topic_name}' ({topic_id})"
    logger.info(f"[Notion Cleanup] Checking existing pages for {filter_desc}")

    client = Client(auth=api_key)
    db_properties, ds_id = get_db_schema_and_datasource(client, db_id)

    # 1. Identify date property
    date_prop = None
    for candidate in ["날짜", "작성일", "Date"]:
        if candidate in db_properties and db_properties[candidate]["type"] == "date":
            date_prop = candidate
            break
    if not date_prop:
        for k, v in db_properties.items():
            if v.get("type") == "date":
                date_prop = k
                break

    if not date_prop:
        logger.warning("No 'date' property found in Notion database. Skipping cleanup.")
        return 0

    # 2. Identify relation property
    topic_prop = rel_prop_name
    if not topic_prop:
        for candidate in ["주제", "Topic"]:
            if candidate in db_properties and db_properties[candidate]["type"] == "relation":
                topic_prop = candidate
                break
    if not topic_prop:
        for k, v in db_properties.items():
            if v.get("type") == "relation":
                topic_prop = k
                break

    # 3. Build compound API filter
    query_filter = {
        "and": [
            {
                "property": date_prop,
                "date": {
                    "equals": target_date_iso
                }
            }
        ]
    }
    if topic_prop and topic_id:
        query_filter["and"].append({
            "property": topic_prop,
            "relation": {
                "contains": topic_id
            }
        })

    results = []
    try:
        if ds_id:
            query_res = client.data_sources.query(data_source_id=ds_id, filter=query_filter)
            results = query_res.get("results", [])
        else:
            query_res = client.request(
                path=f"databases/{db_id}/query",
                method="POST",
                body={"filter": query_filter}
            )
            results = query_res.get("results", [])
    except Exception as e:
        logger.warning(f"Compound query filter failed ({e}). Falling back to date-only query with Python strict validation...")
        date_only_filter = {
            "property": date_prop,
            "date": {
                "equals": target_date_iso
            }
        }
        try:
            if ds_id:
                query_res = client.data_sources.query(data_source_id=ds_id, filter=date_only_filter)
            else:
                query_res = client.request(
                    path=f"databases/{db_id}/query",
                    method="POST",
                    body={"filter": date_only_filter}
                )
            results = query_res.get("results", [])
        except Exception as query_err:
            logger.error(f"Failed to query Notion pages for date {target_date_iso}: {query_err}")
            return 0

    if not results:
        logger.info(f"[Notion Cleanup] No matching existing pages found for {filter_desc}. Ready for new upload.")
        return 0

    # 4. Secondary strict validation in Python before archiving
    archived_count = 0
    for page in results:
        page_id = page.get("id")
        page_props = page.get("properties", {})

        title_blocks = page_props.get("이름", {}).get("title", [])
        page_title = title_blocks[0].get("plain_text", "Untitled") if title_blocks else "Untitled"

        # Validate date
        page_date_obj = page_props.get(date_prop, {}).get("date", {})
        page_date_str = page_date_obj.get("start") if page_date_obj else None
        if page_date_str != target_date_iso:
            logger.info(f"[Notion Cleanup] [SKIP] Page '{page_title}' date ({page_date_str}) does not match target ({target_date_iso}).")
            continue

        # Validate topic / relation ID (Crucial Safety Guard)
        if topic_prop and clean_target_topic_id:
            page_topic_rel = page_props.get(topic_prop, {}).get("relation", [])
            rel_ids = [normalize_uuid(r.get("id")) for r in page_topic_rel if isinstance(r, dict) and "id" in r]

            if clean_target_topic_id not in rel_ids:
                logger.warning(
                    f"[Notion Cleanup] [SAFETY GUARD] Skipping page '{page_title}' (ID: {page_id})! "
                    f"Its '{topic_prop}' relation ({rel_ids}) does NOT match target '{clean_target_topic_id}'. "
                    f"Page preserved safely."
                )
                continue

        if args.dry_run:
            logger.info(f"[Notion Cleanup] [DRY RUN] Page matched for archive: '{page_title}' (ID: {page_id})")
            archived_count += 1
            continue

        try:
            client.pages.update(page_id=page_id, archived=True)
            logger.info(f"[Notion Cleanup] Successfully archived matching page: '{page_title}' (ID: {page_id})")
            archived_count += 1
        except Exception as e:
            logger.error(f"[Notion Cleanup] Failed to archive page {page_id}: {e}")

    logger.info(f"[Notion Cleanup] Finished: {archived_count} matching page(s) cleaned up for {filter_desc}.")
    return archived_count

# ==========================================
# Main CLI Entrypoint
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description="Notion Manager: Upload content or selectively archive/delete pages in a Notion database"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # Upload parser
    up_parser = subparsers.add_parser("upload", help="Upload markdown content to Notion database")
    up_parser.add_argument("--content", default="scratch/notion_upload_temp.md", help="Path to markdown content file (default: scratch/notion_upload_temp.md)")
    up_parser.add_argument("--meta", default="scratch/notion_upload_meta.json", help="Path to metadata JSON file (default: scratch/notion_upload_meta.json)")
    up_parser.add_argument("--title", help="Page title override")
    up_parser.add_argument("--icon", help="Page icon emoji override")
    up_parser.add_argument("--status", help="Status property value override")
    up_parser.add_argument("--category", help="Category property value override")
    up_parser.add_argument("--date", help="Date property value override (YYYY-MM-DD)")
    up_parser.add_argument("--topic-id", help="Topic page UUID relation override")
    up_parser.add_argument("--relation-prop", help="Name of relation property to map topic-id to")
    up_parser.add_argument("--api-key", help="Notion API Key override")
    up_parser.add_argument("--db-id", help="Notion Database ID override")
    up_parser.add_argument("--no-cleanup", action="store_true", help="Do not delete temporary scratch files after upload")

    # Delete parser
    del_parser = subparsers.add_parser("delete", help="Selectively archive/delete Notion pages matching criteria")
    del_parser.add_argument("--date", help="Target date in YYYY-MM-DD or YYYYMMDD format")
    del_parser.add_argument("--topic-id", help="Topic relation page UUID")
    del_parser.add_argument("--topic-name", help="Display name of topic for logging")
    del_parser.add_argument("--relation-prop", help="Name of relation property (default: auto-detected, e.g. 주제, Topic)")
    del_parser.add_argument("--property", help="Additional property filter in key=value format")
    del_parser.add_argument("--meta", default="scratch/notion_upload_meta.json", help="Path to metadata JSON to infer date and topic_id (default: scratch/notion_upload_meta.json)")
    del_parser.add_argument("--api-key", help="Notion API Key override")
    del_parser.add_argument("--db-id", help="Notion Database ID override")
    del_parser.add_argument("--force-all-topics", action="store_true", help="Allow deletion of all pages for the given date without a topic/relation filter")
    del_parser.add_argument("--dry-run", action="store_true", help="Check and print matching pages without archiving")

    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.subcommand == "upload":
        run_upload(args)
    elif args.subcommand == "delete":
        run_delete(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
