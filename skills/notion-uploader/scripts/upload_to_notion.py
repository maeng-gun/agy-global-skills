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
    md = MarkdownIt()
    tokens = md.parse(md_text)
    
    blocks = []
    current_list_type = None
    
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
            elif level == "h3" or level == "h4" or level == "h5" or level == "h6":
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
            current_list_type = "bulleted_list_item"
        elif token.type == "ordered_list_open":
            current_list_type = "numbered_list_item"
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            current_list_type = None
            
        elif token.type == "list_item_open":
            # Inside list item, there's usually a paragraph
            if i+1 < len(tokens) and tokens[i+1].type == "paragraph_open":
                inline = tokens[i+2]
                if inline.type == "inline":
                    rich_text = parse_inline_tokens(inline)
                    blocks.append({
                        "object": "block",
                        "type": current_list_type,
                        current_list_type: {"rich_text": rich_text}
                    })
            # Advance to list_item_close
            while i < len(tokens) and tokens[i].type != "list_item_close":
                i += 1
                
        elif token.type == "fence" or token.type == "code_block":
            language = token.info.strip() if token.info else "plain text"
            if language == "":
                language = "plain text"
            # Notion only supports specific languages, we use plain text as fallback
            chunks = split_text(token.content)
            for chunk in chunks:
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        "language": "plain text" # Simplify to avoid unsupported language errors
                    }
                })
                
        elif token.type == "blockquote_open":
            inline = tokens[i+2] # usually paragraph_open then inline
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
    
    # Remove the first block if its text exactly matches the title
    if blocks:
        first_block_type = blocks[0].get("type")
        if first_block_type in blocks[0] and "rich_text" in blocks[0][first_block_type]:
            first_block_text = "".join(t["text"]["content"] for t in blocks[0][first_block_type]["rich_text"]).strip()
            if first_block_text == title.strip():
                blocks.pop(0)
    
    # Initialize Notion client
    client = Client(auth=NOTION_API_KEY)
    
    # Retrieve DB schema if MODE has keys
    db_properties = {}
    if mode_props:
        try:
            db_info = client.databases.retrieve(NOTION_DB_ID)
            db_properties = db_info.get("properties", {})
            
            if not db_properties:
                # If properties not in db (e.g., linked DB view), try to infer from a page
                query_res = client.databases.query(database_id=NOTION_DB_ID, page_size=1)
                results = query_res.get("results", [])
                if results:
                    db_properties = results[0].get("properties", {})
        except Exception as e:
            print(f"Warning: Failed to retrieve database schema for MODE processing: {e}", file=sys.stderr)
    
    try:
        # Step 1: Create the page with properties and the first batch of blocks (up to 100)
        first_batch = blocks[:MAX_BLOCKS_PER_REQUEST]
        remaining_blocks = blocks[MAX_BLOCKS_PER_REQUEST:]
        
        properties = {
            "이름": { 
                "title": [{"text": {"content": title}}]
            }
        }
        
        # Apply MODE values, falling back to legacy defaults if missing
        status_val = mode_props.get("읽음상태", meta.get("status", "안읽음"))
        category_val = mode_props.get("구분", meta.get("category", "AI 생성"))
        
        if db_properties:
            # Dynamic mapping if we have schema
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
            # Hardcoded fallback mapping if schema fetch completely failed
            properties["읽음상태"] = {"status": {"name": status_val}}
            properties["구분"] = {"select": {"name": category_val}}
            for key, val in mode_props.items():
                if key not in ["읽음상태", "구분"]:
                    properties[key] = {"rich_text": [{"text": {"content": str(val)}}]}
        
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
