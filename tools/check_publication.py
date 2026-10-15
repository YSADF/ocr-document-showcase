"""Check an explicit public allowlist; optionally export only its reviewed files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "PUBLISH_MANIFEST.json"
IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache", "generated"}
PRIVATE_TREES = {"api", "ocr_engine", "pipeline", "services", "deploy", "model_zoo", "uploads"}
MODEL_SUFFIXES = {".onnx", ".safetensors", ".pth", ".pt", ".pdparams", ".pdiparams", ".pkl"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".txt", ".yml", ".yaml", ".example"}
LINK = re.compile(r'!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


def public_path(root: Path, value: str) -> Path:
    rel = PurePosixPath(value)
    if not value or rel.is_absolute() or ".." in rel.parts or "\\" in value or ":" in value:
        raise ValueError("Invalid public relative path")
    path = root.joinpath(*rel.parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Public files must not use symlinks or escape the package")
    return path


def check(root: Path = ROOT, manifest: dict | None = None) -> dict:
    root = root.resolve()
    if manifest is None:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    files = manifest["files"]
    errors = []
    total = 0
    for rel, spec in files.items():
        try:
            path = public_path(root, rel)
        except ValueError as exc:
            errors.append(f"{rel}: {exc}")
            continue
        parts = PurePosixPath(rel).parts
        if parts[0] in PRIVATE_TREES or path.suffix.lower() in MODEL_SUFFIXES:
            errors.append(f"{rel}: outside selected-code publication scope")
        if path.name.startswith('.env') and path.name != '.env.example':
            errors.append(f"{rel}: runtime environment files are private")
        if not path.is_file():
            errors.append(f"{rel}: missing")
            continue
        data = path.read_bytes()
        total += len(data)
        if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
            errors.append(f"{rel}: bytes/hash differ from the reviewed file")
        if len(data) > 10 * 1024 * 1024:
            errors.append(f"{rel}: exceeds the 10 MiB showcase file limit")
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith('.'):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"{rel}: expected UTF-8 text")
                continue
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                errors.append(f"{rel}: credential-shaped content; inspect privately")
            if path.suffix.lower() == ".md":
                for match in LINK.finditer(text):
                    target = match.group(1).strip("<>")
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc:
                        if parsed.scheme not in {"https", "http", "mailto"}:
                            errors.append(f"{rel}: unsupported/non-public link")
                        continue
                    target_path = unquote(parsed.path)
                    if not target_path:
                        continue
                    resolved = (path.parent / target_path).resolve()
                    if not resolved.is_relative_to(root) or not resolved.exists():
                        errors.append(f"{rel}: missing or private relative link: {target_path}")
    actual = {
        p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
        and not any(part in IGNORED for part in p.relative_to(root).parts)
    }
    for rel in sorted(actual - set(files) - {MANIFEST}):
        errors.append(f"{rel}: not in the explicit publication allowlist")
    provenance = root / 'CODE_PROVENANCE.json'
    if provenance.is_file():
        for row in json.loads(provenance.read_text(encoding='utf-8')):
            path = public_path(root, row['example'])
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != row['example_sha256']:
                errors.append(f"{row['example']}: provenance hash mismatch")
    return {"passed": not errors, "reviewed_files": len(files), "total_bytes": total,
            "scope": "Explicit selected-code package; automated checks do not establish redistribution rights",
            "errors": errors}


def export(root: Path, destination: Path) -> dict:
    manifest_bytes = (root / MANIFEST).read_bytes()
    manifest = json.loads(manifest_bytes)
    report = check(root, manifest)
    if not report['passed']:
        raise ValueError("Publication checks failed; nothing exported")
    root = root.resolve()
    destination = destination.resolve()
    if destination == root or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Export must be separate from the source package")
    if destination.exists():
        raise ValueError("Export destination must not already exist")
    files = manifest['files']
    destination.mkdir(parents=True, exist_ok=False)
    for rel, spec in files.items():
        src = public_path(root, rel)
        data = src.read_bytes()
        if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise ValueError(f'{rel}: source changed during export; destination is incomplete')
        dst = destination / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    (destination / MANIFEST).write_bytes(manifest_bytes)
    exported = check(destination)
    if not exported['passed']:
        raise ValueError('Exported package failed final verification')
    return exported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, help='New, separate directory; copy only reviewed files')
    args = parser.parse_args()
    try:
        result = export(ROOT, args.export) if args.export else check()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        result = {'passed': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
