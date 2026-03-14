

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


@dataclass
class ProviderSpec:
    provider: str
    mode: str  # openai-compatible | anthropic-compatible
    base_url: str
    api_key: str


def log(msg: str) -> None:
    print(msg, flush=True)


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def ensure_python_package(pkg: str) -> None:
    try:
        __import__(pkg.replace("-", "_"))
        return
    except Exception:
        pass
    log(f"[setup] installing python package: {pkg}")
    subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_pdf2zh_config_path(custom: str | None) -> Path:
    if custom:
        return Path(custom).expanduser().resolve()
    if os.name == "nt":
        return Path.home() / ".config" / "pdf2zh" / "config.v3.toml"
    return Path.home() / ".config" / "pdf2zh" / "config.v3.toml"


def detect_pdf2zh_cli() -> list[str] | None:
    # uv tool install usually exposes one of these entrypoints
    cli_candidates = [
        "pdf2zh_next",
        "pdf2zh-next",
        "pdf2zh",
    ]
    for name in cli_candidates:
        path = shutil.which(name)
        if path:
            return [path]

    # Common uv user-bin locations
    extra_paths = [
        Path.home() / ".local" / "bin" / "pdf2zh_next",
        Path.home() / ".local" / "bin" / "pdf2zh_next.exe",
        Path.home() / "AppData" / "Roaming" / "Python" / "Scripts" / "pdf2zh_next.exe",
    ]
    for p in extra_paths:
        if p.exists():
            return [str(p)]
    return None


def ensure_pdf2zh_config_exists(config_path: Path) -> None:
    if config_path.exists():
        return
    common = (
        "Common locations: Linux/macOS ~/.config/pdf2zh/config.v3.toml ; "
        "Windows C:/Users/<username>/.config/pdf2zh/config.v3.toml"
    )
    raise RuntimeError(
        f"config file not found: {config_path}. Please provide the config file path via --config-path. {common}"
    )


def parse_toml_to_dict(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if tomllib is None:
        ensure_python_package("tomli")
        import tomli  # type: ignore

        return tomli.loads(text)
    return tomllib.loads(text)


def merge_provider_into_config_text(raw: str, spec: ProviderSpec, prefer_siliconflow: bool, keep_existing_qps: bool) -> str:
    # Replace existing managed block to avoid duplicated TOML keys.
    begin = "# ---- managed by translator-pdf2zh-workflow skill (begin) ----"
    end = "# ---- managed by translator-pdf2zh-workflow skill (end) ----"
    if begin in raw and end in raw:
        pre = raw.split(begin, 1)[0].rstrip()
        post = raw.split(end, 1)[1].lstrip()
        raw = (pre + "\n\n" + post).strip()

    managed = [
        "",
        begin,
        "[translation]",
        "qps = 1",
        "pool_max_workers = 1",
        "no_auto_extract_glossary = true",
        "save_auto_extracted_glossary = false",
    ]
    if keep_existing_qps and "qps" in raw:
        managed[3] = "# qps kept as-is (existing config)"
        managed[4] = "# pool_max_workers kept as-is (existing config)"

    # First disable known providers conservatively.
    provider_flags = [
        "openai", "openaicompatible", "anthropic", "siliconflow", "siliconflowfree",
        "deepseek", "azureopenai", "aliyun", "bing", "google", "gemini",
    ]
    managed.append("[services]")
    for flag in provider_flags:
        managed.append(f"{flag} = false")

    if prefer_siliconflow:
        managed.append("siliconflowfree = true")
    else:
        managed.extend([
            "[custom_provider]",
            f"provider = \"{spec.provider}\"",
            f"mode = \"{spec.mode}\"",
            f"base_url = \"{spec.base_url}\"",
            f"api_key = \"{spec.api_key}\"",
            "enabled = true",
        ])

    managed.append(end)
    return raw.rstrip() + "\n" + "\n".join(managed) + "\n"


def resolve_provider(
    provider_choice: str,
    custom_provider: str | None,
    custom_mode: str | None,
    custom_base_url: str | None,
    custom_api_key: str | None,
) -> ProviderSpec:
    # Agent should resolve model/provider mapping before calling this script.
    if provider_choice == "siliconflowfree":
        return ProviderSpec("siliconflowfree", "openai-compatible", "", "")

    if provider_choice == "custom":
        if not (custom_provider and custom_base_url and custom_api_key):
            raise ValueError("custom provider requires --provider-name --provider-base-url --provider-api-key")
        mode = custom_mode or "openai-compatible"
        return ProviderSpec(custom_provider, mode, custom_base_url, custom_api_key)

    raise ValueError("unsupported provider-choice; use siliconflowfree or custom")


def gather_pdfs(files: list[str], folders: list[str], include_globs: list[str], recursive: bool = True) -> list[Path]:
    out: list[Path] = []
    for fp in files:
        p = Path(fp).expanduser().resolve()
        if p.exists() and p.suffix.lower() == ".pdf":
            out.append(p)

    for folder in folders:
        d = Path(folder).expanduser().resolve()
        if not d.exists() or not d.is_dir():
            continue
        pattern = "**/*.pdf" if recursive else "*.pdf"
        out.extend(d.glob(pattern))

    # unique + stable
    uniq: dict[str, Path] = {}
    for p in out:
        uniq[str(p)] = p
    merged = sorted(uniq.values(), key=lambda x: str(x).lower())

    # optional subset filter for "some PDFs in folder"
    if include_globs:
        selected: list[Path] = []
        for p in merged:
            rel_name = p.name
            rel_full = str(p)
            if any(p.match(g) or Path(rel_name).match(g) or Path(rel_full).match(g) for g in include_globs):
                selected.append(p)
        return selected

    return merged


def ensure_output_dir(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


async def translate_one_api(pdf: Path, out_dir: Path, stream: bool) -> tuple[bool, str]:
    from pdf2zh_next.high_level import do_translate_async_stream  # type: ignore
    from pdf2zh_next.settings import SettingsModel  # type: ignore

    settings = SettingsModel()
    settings.basic.output = str(out_dir)
    settings.basic.validate_settings()

    try:
        async for event in do_translate_async_stream(settings, pdf):
            et = event.get("type")
            if stream and et in {"progress_start", "progress_update", "progress_end", "error"}:
                log(f"[{pdf.name}] {event}")
            if et == "error":
                return False, str(event)
            if et == "finish":
                return True, "finish"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return False, "stream finished without finish event"


def read_cli_help_text(base_cmd: list[str]) -> str:
    try:
        cp = subprocess.run([*base_cmd, "-h"], text=True, capture_output=True, check=False)
        return (cp.stdout or "") + "\n" + (cp.stderr or "")
    except Exception:
        return ""


def detect_siliconfree_cli_args(help_text: str) -> list[str]:
    """Pick compatible SiliconFlowFree args based on current CLI help."""
    if "--siliconflowfree" in help_text:
        return ["--siliconflowfree"]
    if "--service" in help_text:
        return ["--service", "siliconflowfree"]
    return []


def translate_one_cli(base_cmd: list[str], pdf: Path, out_dir: Path, stream: bool, extra_args: list[str] | None = None) -> tuple[bool, str]:
    cmd = [*base_cmd]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend([str(pdf), "--output", str(out_dir)])
    if stream:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                log(f"[{pdf.name}] {line}")
                lines.append(line)
                if len(lines) > 120:
                    lines = lines[-120:]
        rc = proc.wait()
        return rc == 0, "\n".join(lines[-40:])
    cp = subprocess.run(cmd, text=True, capture_output=True)
    tail = (cp.stdout + "\n" + cp.stderr)[-2000:]
    return cp.returncode == 0, tail


def translated_pdf_exists(out_dir: Path, source_pdf: Path) -> bool:
    base = source_pdf.stem
    candidates = list(out_dir.glob(f"{base}*.pdf"))
    return len(candidates) > 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run cross-platform PDFMathTranslate-next pipeline")
    ap.add_argument("--input-file", action="append", default=[], help="single pdf; can repeat")
    ap.add_argument("--input-dir", action="append", default=[], help="folder containing pdf files; can repeat")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--include-glob", action="append", default=[], help="optional subset matcher for filenames/paths, e.g. '*A*.pdf' or '*2024*' ; can repeat")
    ap.add_argument("--threads", type=int, default=1, help="default=1; >1 runs concurrent files")
    ap.add_argument("--stream", action="store_true", help="stream progress output")
    ap.add_argument("--headless", action="store_true", help="hint for invisible run (script still runs in terminal)")
    ap.add_argument("--exe-path", default=None, help="absolute path to pdf2zh executable (required on Windows exe mode)")
    ap.add_argument("--config-path", default=None)
    ap.add_argument("--keep-existing-rate-limit", action="store_true", help="do not override qps/pool settings if present")
    ap.add_argument("--recursive", action="store_true", default=True)
    args = ap.parse_args()

    if args.threads < 1:
        raise ValueError("--threads must be >= 1")

    if not shutil.which(sys.executable):
        raise RuntimeError("python runtime not found")

    out_dir = ensure_output_dir(args.output_dir)
    pdfs = gather_pdfs(args.input_file, args.input_dir, include_globs=args.include_glob, recursive=args.recursive)
    if not pdfs:
        raise RuntimeError("no input pdf found (use --input-file and/or --input-dir)")

    # runtime check: prefer uv/CLI entrypoint, then explicit exe, then Python API
    exe_path = args.exe_path
    cli_cmd: list[str] | None = None

    detected_cli = detect_pdf2zh_cli()
    if detected_cli:
        cli_cmd = detected_cli
        log(f"[setup] detected pdf2zh cli: {cli_cmd[0]}")

    if exe_path:
        cli_cmd = [exe_path]
        log(f"[setup] using explicit exe-path: {exe_path}")

    use_api = False
    if not cli_cmd:
        ensure_python_package("pdf2zh-next")
        use_api = True

    # provider + config wiring
    config_path = get_pdf2zh_config_path(args.config_path)
    ensure_pdf2zh_config_exists(config_path)
    log(f"[setup] using existing config file (agent-managed): {config_path}")

    # translate
    log(f"[run] platform={platform.system()} cli_mode={bool(cli_cmd)} api_mode={use_api} files={len(pdfs)} threads={args.threads}")
    if args.headless:
        log("[run] headless=true (no extra UI from this script)")

    async def run_api_batch() -> tuple[bool, str]:
        # conservative: sequential by default; optionally allow simple parallel gather
        if args.threads == 1:
            for pdf in pdfs:
                ok, reason = await translate_one_api(pdf, out_dir, args.stream)
                if not ok:
                    return False, f"{pdf.name}: {reason}"
                if not translated_pdf_exists(out_dir, pdf):
                    return False, f"{pdf.name}: translation finished but output pdf not found"
            return True, "ok"

        sem = asyncio.Semaphore(args.threads)
        errors: list[str] = []

        async def worker(pdf: Path) -> None:
            nonlocal errors
            async with sem:
                if errors:
                    return
                ok, reason = await translate_one_api(pdf, out_dir, args.stream)
                if (not ok) and (not errors):
                    errors.append(f"{pdf.name}: {reason}")

        await asyncio.gather(*(worker(p) for p in pdfs))
        if errors:
            return False, errors[0]
        for p in pdfs:
            if not translated_pdf_exists(out_dir, p):
                return False, f"{p.name}: output pdf not found"
        return True, "ok"

    if use_api:
        ok, reason = asyncio.run(run_api_batch())
        if not ok:
            log(f"[error] translation stopped: {reason}")
            return 2
    else:
        help_text = read_cli_help_text(cli_cmd)
        cli_extra_args: list[str] = []

        # Default disable auto glossary extraction when supported
        if "--no-auto-extract-glossary" in help_text:
            cli_extra_args.append("--no-auto-extract-glossary")
            log("[setup] glossary extraction disabled via --no-auto-extract-glossary")

        for i, pdf in enumerate(pdfs, start=1):
            log(f"[run] ({i}/{len(pdfs)}) {pdf}")
            ok, reason = translate_one_cli(cli_cmd, pdf, out_dir, args.stream, extra_args=cli_extra_args)
            if not ok and ("Unsupported translation service" in reason):
                log("[setup] cli service unsupported, fallback to pdf2zh-next Python API mode")
                ensure_python_package("pdf2zh-next")
                ok, reason = asyncio.run(translate_one_api(pdf, out_dir, args.stream))

            if not ok:
                log(f"[error] translation stopped: {pdf.name}: {reason}")
                return 2
            if not translated_pdf_exists(out_dir, pdf):
                log(f"[error] translation stopped: {pdf.name}: output pdf not found")
                return 2

    log(f"[ok] all translations finished successfully. output={out_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        log(f"[fatal] {type(e).__name__}: {e}")
        raise
