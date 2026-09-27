# /// script
# requires-python = ">=3.9"
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
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client
from markdown_it import MarkdownIt

# Limits
MAX_BLOCKS_PER_REQUEST = 100
MAX_TEXT_LENGTH = 2000

def split_text(text, limit=MAX_TEXT_LENGTH):
    """Split text into chunks if it exceeds the limit."""
    return [text[i:i+limit] for i in range(0, len(text), limit)] if text else [""]

def parse_inline_tokens(inline_token):
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
        elif child.type == "link_open":
            # Just a simple handling, link URL is in attrs
            href = dict(child.attrs).get("href", "")
            # We'll just append it to the next text node manually or let it be text
            # Proper link handling in rich_text requires setting the 'link' property.
            # For simplicity, we'll just ignore links or let them be plain text for now, 
            # unless we want to track it.
            pass
        elif child.type == "link_close":
            pass
            
    # If no text was added but it's not empty, add an empty string
    if not rich_text:
        rich_text.append({"type": "text", "text": {"content": ""}})
        
    return rich_text

def markdown_to_notion_blocks(md_text):
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
            i += 2  # Skip paragraph_close
            
        elif token.type == "heading_open":
            level = token.tag  # h1, h2, h3
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
                
        elif token.type == "fence" or token.type == "code_block":
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

def main():
    # Load environment variables from the current working directory
    load_dotenv(Path(os.getcwd()) / ".env")
    
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    NOTION_DB_ID = os.getenv("NOTION_DB_ID")
    
    if not NOTION_API_KEY or not NOTION_DB_ID:
        print("Error: NOTION_API_KEY or NOTION_DB_ID is missing from the .env file in the current directory.", file=sys.stderr)
        print("Please ensure the .env file exists and contains both variables.", file=sys.stderr)
        sys.exit(1)
        
    # Check scratch files
    md_path = Path("scratch/notion_upload_temp.md")
    meta_path = Path("scratch/notion_upload_meta.json")
    
    if not md_path.exists() or not meta_path.exists():
        print(f"Error: Missing scratch files. Make sure {md_path} and {meta_path} exist.", file=sys.stderr)
        sys.exit(1)
        
    # Read files
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
            
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        print(f"Error reading scratch files: {e}", file=sys.stderr)
        sys.exit(1)
        
    title = meta.get("title", "Untitled AI Upload")
    icon = meta.get("icon", "📄")
    
    # Check for MODE environment variable
    mode_env = os.getenv("MODE")
    mode_props = {}
    if mode_env:
        try:
            mode_props = json.loads(mode_env)
        except Exception as e:
            print(f"Warning: Failed to parse MODE env var as JSON: {e}", file=sys.stderr)
            
    # Parse markdown to blocks
    blocks = markdown_to_notion_blocks(md_text)
    
    # Remove the first block if it matches title, is a heading_1, or starts with Daily Macro
    if blocks:
        first_block_type = blocks[0].get("type")
        if first_block_type in blocks[0] and "rich_text" in blocks[0][first_block_type]:
            first_block_text = "".join(t["text"]["content"] for t in blocks[0][first_block_type]["rich_text"]).strip()
            if first_block_text == title.strip() or first_block_text.startswith("Daily Macro") or first_block_type == "heading_1":
                blocks.pop(0)
    
    # Initialize Notion client
    client = Client(auth=NOTION_API_KEY)
    
    # Retrieve DB schema
    db_properties = {}
    try:
        db_info = client.databases.retrieve(NOTION_DB_ID)
        db_properties = db_info.get("properties", {})
        if not db_properties and db_info.get("data_sources"):
            ds_id = db_info["data_sources"][0]["id"]
            ds_info = client.data_sources.retrieve(ds_id)
            db_properties = ds_info.get("properties", {})
    except Exception as e:
        print(f"Warning: Failed to retrieve database schema: {e}", file=sys.stderr)
    
    try:
        # Step 1: Create the page with properties and the first batch of blocks (up to 100)
        first_batch = blocks[:MAX_BLOCKS_PER_REQUEST]
        remaining_blocks = blocks[MAX_BLOCKS_PER_REQUEST:]
        
        properties = {}
        title_prop_name = "이름"
        for k, v in db_properties.items():
            if v.get("type") == "title":
                title_prop_name = k
                break
        properties[title_prop_name] = { 
            "title": [{"text": {"content": title}}]
        }
        
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
                s_val = meta.get("status", "안읽음")
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
                c_val = meta.get("category", "AI생성")
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
                import re
                d_val = meta.get("date")
                if not d_val:
                    m = re.search(r"\d{4}-\d{2}-\d{2}", title)
                    if m:
                        d_val = m.group(0)
                    else:
                        from datetime import datetime
                properties[date_prop] = {"date": {"start": d_val}}
                
            # 4. Relation '주제' mapping
            topic_page_id = meta.get("topic_page_id") or meta.get("주제") or os.getenv("NOTION_TOPIC_PAGE_ID")
            if topic_page_id:
                properties["\uc8fc\uc81c"] = {"relation": [{"id": topic_page_id}]}
        
        print("Creating Notion page...")
        new_page = client.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties=properties,
            children=first_batch,
            icon={"type": "emoji", "emoji": icon}
        )
        
        page_id = new_page["id"]
        page_url = new_page["url"]
        
        # Step 2: Append remaining blocks in chunks of 100
        while remaining_blocks:
            batch = remaining_blocks[:MAX_BLOCKS_PER_REQUEST]
            remaining_blocks = remaining_blocks[MAX_BLOCKS_PER_REQUEST:]
            
            print(f"Appending {len(batch)} blocks to the page...")
            client.blocks.children.append(
                block_id=page_id,
                children=batch
            )
            time.sleep(0.5) # Prevent rate limiting
            
        print(f"\nSuccessfully uploaded to Notion!")
        print(f"Page URL: {page_url}")
        
        # Cleanup
        md_path.unlink()
        meta_path.unlink()
        print("Cleaned up temporary scratch files.")
        
    except Exception as e:
        print(f"Error communicating with Notion API: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
