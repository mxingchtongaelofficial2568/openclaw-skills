---
name: zotero-local-import-en
description: Import local PDF files into Zotero from the command line on Windows/macOS/Linux via the Zotero local connector (127.0.0.1). Use for single-PDF import, folder batch import, importing into an existing collection, listing collections, and verifying recent imported attachments. Requires Zotero desktop setting to allow local app communication and a user-provided connector port. Tested only on Windows 11 with Python 3.14.
---

# Zotero Local Import Skill (Windows / macOS / Linux)

Before using this skill, make sure Zotero Desktop is open and configured:

1. Open **Zotero → Settings → Advanced**
2. Enable: **Allow other applications on this computer to communicate with Zotero**
3. Note the connector port (commonly `23119`) and provide it to the agent via `--port`

> This skill imports only into **existing collections**. It does **not** create collections.
> If `--collection` is omitted, imports default to **My Library**.

## Script location

- `scripts/zotero_tool.py`

## Features

1. Import a single PDF
2. Import all PDFs in a folder (optional recursive mode)
3. Import into an existing collection
4. List local Zotero collections
5. Check recently imported attachments (read-only from `zotero.sqlite`)

## Agent pre-execution contract

The agent must support and auto-handle all input forms below:

1. A folder path
2. A single PDF path
3. Multiple PDF paths
4. Selected PDFs inside one folder (file-name list such as `x.pdf, y.pdf, z.pdf`)

The agent must also collect:

- Zotero connector port
- Optional collection name (if omitted, use My Library)

Required flow:

1. Run `doctor --auto-install-deps`
2. If successful, run `import`

Natural-language parsing (paths, file names, port, collection) must be done by the **agent**. The script accepts structured arguments only.

## Command usage

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py --help
```

### 0) Environment check (required)

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py doctor \
  --port <USER_ZOTERO_PORT> \
  --auto-install-deps
```

### A) Import one PDF

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --pdf "<ABSOLUTE_PDF_PATH>" \
  --port <USER_ZOTERO_PORT>
```

### A2) Import multiple PDFs

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --pdf "<PDF_PATH_1>" \
  --pdf "<PDF_PATH_2>" \
  --pdf "<PDF_PATH_3>" \
  --port <USER_ZOTERO_PORT>
```

### B) Import folder (non-recursive)

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --dir "<ABSOLUTE_FOLDER_PATH>" \
  --port <USER_ZOTERO_PORT>
```

### C) Import folder (recursive)

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --dir "<ABSOLUTE_FOLDER_PATH>" \
  --recursive \
  --port <USER_ZOTERO_PORT>
```

### D) Import into an existing collection

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --dir "<ABSOLUTE_FOLDER_PATH>" \
  --recursive \
  --collection "<EXISTING_COLLECTION_NAME>" \
  --port <USER_ZOTERO_PORT>
```

### D2) Import selected PDFs from a folder

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --dir "<ABSOLUTE_FOLDER_PATH>" \
  --pick "x.pdf,y.pdf,z.pdf" \
  --collection "<EXISTING_COLLECTION_NAME>" \
  --port <USER_ZOTERO_PORT>
```

or

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py import \
  --dir "<ABSOLUTE_FOLDER_PATH>" \
  --pick "x.pdf" \
  --pick "y.pdf" \
  --pick "z.pdf" \
  --port <USER_ZOTERO_PORT>
```

### E) List collections

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py list-collections --port <USER_ZOTERO_PORT>
```

### F) Check recent imports

```bash
python skills/zotero-local-import-en/scripts/zotero_tool.py check --limit 10
```

## Key parameters

- `--port`: Zotero connector port (defaults to `ZOTERO_PORT`, fallback `23119`)
- `--timeout`: HTTP timeout in seconds (default `90`)
- `--collection`: existing target collection name
- `--db`: custom `zotero.sqlite` path for `check`

## Platform notes

- Windows: supported (UTF-8 output enhancement enabled)
- macOS: requires `open`
- Linux: requires `xdg-open`

## Failure handling

- `error=collection not found`: create the collection manually in Zotero first
- Connection errors: confirm Zotero is running, communication is enabled, and port is correct
- Import errors: retry with one PDF first, then run batch import
