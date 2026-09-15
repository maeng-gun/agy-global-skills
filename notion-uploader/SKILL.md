---
name: notion-uploader
description: Uploads markdown or text content to a Notion database by converting it to Notion blocks.
---

# Notion Uploader Skill

This skill allows the agent to upload content to a Notion database. It uses a standalone Python script to convert markdown to Notion blocks and push it to the Notion API, safely handling rate limits and block limits (chunking).

## Prerequisites
The target project (where this agent is currently running) MUST have a `.env` file in its root directory containing:
- `NOTION_API_KEY`: The Notion internal integration token.
- `NOTION_DB_ID`: The ID of the target Notion database.

## Instructions

When the user asks to upload content to Notion (or when the context requires saving an artifact to Notion), follow these steps:

1. **Identify the Content**: Determine what content the user wants to upload. This could be an existing file (like a markdown or text file), a summary you just generated, or the result of a previous task.
2. **Structure the Content**: Format the content into standard Markdown. Optimize the structure with headings, bullet points, and code blocks for better readability in Notion. 
3. **Save Temporary Markdown**: Create a directory named `scratch` in your current working directory if it doesn't exist. Save the formatted markdown content to `scratch/notion_upload_temp.md`.
4. **Determine Metadata**: Determine a suitable title for the Notion page based on the content. Also, pick a single relevant emoji to serve as the page icon (e.g., "📊", "📝", "🚀").
5. **Save Temporary Metadata**: Create a JSON file at `scratch/notion_upload_meta.json` with the following structure:
   ```json
   {
     "title": "<The title you determined>",
     "icon": "<The single emoji you picked>",
     "status": "안읽음",
     "category": "AI 생성"
   }
   ```
6. **Execute Upload Script**: Run the following exact command in your shell to execute the global uploader script:
   ```bash
   uv run ~/.gemini/config/skills/notion-uploader/scripts/upload_to_notion.py
   ```
   *(Note: The python script will automatically read the scratch files and the project's `.env` file. It will also clean up the scratch files upon success.)*
7. **Verify and Report**: If the command is successful, it will output the URL of the newly created Notion page. Present this URL to the user and confirm that the upload was successful. If the script fails, report the error details to the user so they can troubleshoot.
