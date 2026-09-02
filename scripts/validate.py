#!/usr/bin/env python3
"""Линтер набора razryad-skills.

Проверяет то, что в CONTRACT.md можно проверить механически:
структуру папок, фронтматтер, обязательные секции, локальные ссылки,
самодостаточность, длину, тире и стоп-слова.

Запуск: python3 scripts/validate.py [--quiet]
Код выхода 0, если ошибок нет.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
TESTS = ROOT / "tests"

EXPECTED_SKILLS = [
    "razryad", "razryad-task", "razryad-prd", "razryad-spec", "razryad-proto",
    "razryad-data", "razryad-build", "razryad-accept", "razryad-ship",
    "razryad-effect", "razryad-demo", "razryad-retro",
]

REQUIRED_SECTIONS = [
    "## Что это / что не это",
    "## Как ведём себя",
    "## Шаг 0. Контекст",
    "## Шаги",
    "## Формат результата",
    "## Ворота",
    "## Дальше",
]

MAX_SKILL_LINES = 150
MAX_REF_LINES = 120
MAX_FRONTMATTER_CHARS = 1024
MIN_TRIGGERS = 4

DASHES = {"—": "длинное тире", "–": "среднее тире"}

# Слова, которых не должно быть ни в одном тексте набора: клиенты, участники, инфраструктура.
STOP_WORDS = [
    r"уралхим", r"нектарин", r"\bпсб\b", r"кабель\.?рф", r"cablestrade", r"cable\.ru",
    r"hantico", r"eregion", r"ai-uc\.site", r"ai-nectarin", r"бакин", r"185\.180\.",
    r"\bkaiten\b", r"cableisthebest", r"\bnec ии\b",
]

TEXT_GLOBS = ["skills/**/*.md", "tests/*.md", "examples/**/*.md", "README.md", "CONTRACT.md", "CHANGELOG.md"]

errors: list[str] = []
warnings: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def warn(path: Path, msg: str) -> None:
    warnings.append(f"{path.relative_to(ROOT)}: {msg}")


def parse_frontmatter(text: str, path: Path) -> dict | None:
    if not text.startswith("---\n"):
        err(path, "нет фронтматтера")
        return None
    end = text.find("\n---", 4)
    if end == -1:
        err(path, "фронтматтер не закрыт")
        return None
    block = text[4:end]
    if len(block) > MAX_FRONTMATTER_CHARS:
        err(path, f"фронтматтер {len(block)} символов, лимит {MAX_FRONTMATTER_CHARS}")
    fm: dict[str, str] = {}
    current = None
    for line in block.splitlines():
        m = re.match(r"^([a-zA-Z_-]+):\s*(.*)$", line)
        if m:
            current = m.group(1)
            fm[current] = m.group(2).strip()
        elif line.startswith(" "):
            sub = re.match(r"^\s+([a-zA-Z_-]+):\s*(.*)$", line)
            if sub:
                fm[sub.group(1)] = sub.group(2).strip()
            elif current:
                fm[current] = (fm[current] + " " + line.strip()).strip()
    return fm


def check_text_rules(path: Path, text: str) -> None:
    for ch, name in DASHES.items():
        for i, line in enumerate(text.splitlines(), 1):
            if ch in line:
                err(path, f"строка {i}: {name}")
    low = text.lower()
    for pat in STOP_WORDS:
        m = re.search(pat, low)
        if m:
            err(path, f"стоп-слово «{m.group(0)}»")


def check_links(path: Path, text: str, skill_dir: Path) -> None:
    for m in re.finditer(r"\]\(([^)]+)\)", text):
        target = m.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            err(path, f"ссылка на несуществующий файл: {target}")
            continue
        try:
            resolved.relative_to(skill_dir.resolve())
        except ValueError:
            err(path, f"ссылка выходит за папку скилла: {target}")


def check_skill(skill_dir: Path) -> None:
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        err(skill_dir, "нет SKILL.md")
        return
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > MAX_SKILL_LINES:
        err(skill_md, f"{len(lines)} строк, лимит {MAX_SKILL_LINES}")

    fm = parse_frontmatter(text, skill_md)
    if fm is not None:
        if fm.get("name") != name:
            err(skill_md, f"name «{fm.get('name')}» не равен имени папки «{name}»")
        desc = fm.get("description", "").strip('"').strip("'")
        if not desc.startswith("Use when"):
            err(skill_md, "description должен начинаться с «Use when»")
        triggers = re.findall(r"«[^»]+»", desc)
        if len(triggers) < MIN_TRIGGERS:
            err(skill_md, f"в description {len(triggers)} триггеров в «ёлочках», нужно не меньше {MIN_TRIGGERS}")
        if "Не используй для" not in desc:
            err(skill_md, "в description нет анти-маршрутизации «Не используй для …»")
        if "version" not in fm:
            err(skill_md, "нет metadata.version")

    for sec in REQUIRED_SECTIONS:
        if not re.search(rf"^{re.escape(sec)}\s*$", text, re.M):
            err(skill_md, f"нет секции «{sec}»")
    if not re.search(rf"^# {re.escape(name)}: ", text, re.M):
        err(skill_md, f"заголовок должен быть «# {name}: <вопрос>»")

    check_text_rules(skill_md, text)
    check_links(skill_md, text, skill_dir)

    for sub in ("references", "assets"):
        d = skill_dir / sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            t = f.read_text(encoding="utf-8")
            if sub == "references" and len(t.splitlines()) > MAX_REF_LINES:
                err(f, f"{len(t.splitlines())} строк, лимит {MAX_REF_LINES}")
            check_text_rules(f, t)
            check_links(f, t, skill_dir)

    evals = TESTS / f"{name}-evals.md"
    if not evals.exists():
        err(skill_dir, f"нет tests/{name}-evals.md")
    else:
        t = evals.read_text(encoding="utf-8")
        n = len(re.findall(r"^### \d+\.", t, re.M))
        if n < 3:
            err(evals, f"{n} сценариев, нужно не меньше 3")
        for field in ("Вход:", "Ожидаем:", "Провал:"):
            if field not in t:
                err(evals, f"в сценариях нет поля «{field}»")


def check_versions() -> None:
    versions = set()
    for d in SKILLS.iterdir():
        if not d.is_dir():
            continue
        fm = parse_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"), d / "SKILL.md") if (d / "SKILL.md").exists() else None
        if fm and "version" in fm:
            versions.add(fm["version"])
    if len(versions) > 1:
        errors.append(f"версии скиллов расходятся: {sorted(versions)}")


def main() -> int:
    quiet = "--quiet" in sys.argv
    present = sorted(d.name for d in SKILLS.iterdir() if d.is_dir()) if SKILLS.exists() else []
    for name in EXPECTED_SKILLS:
        if name not in present:
            warnings.append(f"skills/{name}: скилл ещё не создан")
    for name in present:
        if name not in EXPECTED_SKILLS:
            errors.append(f"skills/{name}: лишний скилл, нет в CONTRACT.md")
        check_skill(SKILLS / name)
    check_versions()

    for pattern in TEXT_GLOBS:
        for f in ROOT.glob(pattern):
            if "skills/" in str(f.relative_to(ROOT)).replace("\\", "/"):
                continue  # уже проверено
            check_text_rules(f, f.read_text(encoding="utf-8"))

    if not quiet:
        for w in warnings:
            print(f"предупреждение: {w}")
    for e in errors:
        print(f"ошибка: {e}")
    print(f"{len(present)} скиллов, {len(errors)} ошибок, {len(warnings)} предупреждений")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
