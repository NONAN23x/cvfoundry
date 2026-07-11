#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import uno
    from com.sun.star.awt.FontSlant import ITALIC, NONE
    from com.sun.star.beans import PropertyValue
    from com.sun.star.style.ParagraphAdjust import CENTER, LEFT
    from com.sun.star.style.TabAlign import RIGHT
except ImportError:
    uno = None
    ITALIC = 2
    NONE = 0
    CENTER = 3
    LEFT = 0
    RIGHT = 2

    class PropertyValue:  # type: ignore[no-redef]
        Name: str
        Value: Any

from artifact_names import final_pdf_filename
from cv_source import load_cv
from pdf_inspection import inspect_pdf, write_report
from resume_validation import validate_tailored_resume
from runtime_paths import ROOT


POLICY_PATH = ROOT / "config" / "resume-policy.json"
DEFAULT_CV_PATH = ROOT / "profiles" / "john-doe" / "CV.md"
FONT_DIR = ROOT / "assets" / "fonts"
ACCENT = 0x0D6E6E
INK = 0x434343
PIPELINE_LOCK_ENV = "JOBS_TAILORING_PIPELINE_LOCK"
DETERMINISTIC_DESCRIPTION = "Tailored professional resume"
PDF_EXPORT_OPTIONS = (
    ("UseTaggedPDF", True),
    ("PDFUACompliance", True),
    ("ExportBookmarks", True),
    ("IsSkipEmptyPages", True),
)


class GenerateResumeError(Exception):
    def __init__(self, stage: str, issues: list[str], exit_code: int) -> None:
        self.stage = stage
        self.issues = issues
        self.exit_code = exit_code
        super().__init__("\n".join(issues))


class ContentValidationError(GenerateResumeError):
    def __init__(self, stage: str, issues: list[str]) -> None:
        super().__init__(stage, issues, exit_code=2)


class LibreOfficeRuntimeError(GenerateResumeError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("libreoffice-runtime", issues, exit_code=3)


def require_uno() -> Any:
    if uno is None:
        raise LibreOfficeRuntimeError(
            [
                "LibreOffice Writer is unavailable: UNO Python bindings are unavailable in this Python environment. "
                "Use Docker for rendering or run with a Python that provides python3-uno."
            ]
        )
    return uno


def property_value(name: str, value: Any) -> PropertyValue:
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContentValidationError(
            "input-json",
            [f"Unable to read valid JSON from {path}: {error}"],
        ) from error
    if not isinstance(value, dict):
        raise ContentValidationError("input-json", [f"{path} must contain a JSON object."])
    return value


def cli_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": report["ok"],
        "pdfFileName": report.get("pdfFileName"),
        "pageCount": report.get("pageCount"),
        "summaryLineCount": report.get("summaryLineCount"),
        "bottomWhitespaceMm": report.get("bottomWhitespaceMm"),
        "issues": report.get("issues", []),
    }


def error_summary(error: GenerateResumeError) -> dict[str, Any]:
    return {"ok": False, "stage": error.stage, "issues": error.issues}


def build_url(value: str) -> str:
    return value if "://" in value else f"https://{value}"


def resume_title(data: dict[str, Any]) -> str:
    return f"{data['basics']['name']} Resume"


def resume_subject(data: dict[str, Any]) -> str:
    return f"{data['basics']['headline']} Resume"


def achievement_segments(item: dict[str, Any]) -> list[dict[str, Any]]:
    url = item.get("url")
    fallback = [{"text": item["text"]}]
    if url:
        fallback[0]["hyperlink"] = url
        fallback[0]["underline"] = True
    return fallback


def _hex_color(value: str) -> int:
    return int(value.lstrip("#"), 16)


def render_html(
    data: dict[str, Any],
    theme: dict[str, Any] | None = None,
    resume_config: dict[str, Any] | None = None,
) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    theme = theme or {
        "font": {"family": "Gelasio", "files": {"regular": str(FONT_DIR / "gelasio-regular.ttf")}},
        "colors": {"accent": "#0D6E6E", "ink": "#434343", "background": "#FFFFFF"},
        "typography": {"bodyPt": 10, "namePt": 20, "headlinePt": 12, "sectionPt": 10, "contactPt": 9},
        "geometry": {"topMarginMm": 7, "bottomMarginMm": 7, "leftMarginMm": 10, "rightMarginMm": 10},
        "spacing": {"comfortable": {"sectionBeforeMm": 4.2, "entryBeforeMm": 2.6}},
        "bullets": {"leftMarginMm": 2.5, "gapMm": 2.0},
    }
    resume_config = resume_config or {"document": {"pageSize": "A4"}}
    family = esc(theme["font"]["family"])
    regular_font = Path(theme["font"]["files"]["regular"]).resolve().as_uri()
    colors = theme["colors"]
    typography = theme["typography"]
    geometry = theme["geometry"]
    bullet_tokens = theme.get("bullets", {"leftMarginMm": 2.5, "gapMm": 2.0})
    page_size = resume_config["document"].get("pageSize", "A4").upper()
    page_width, page_height = ((210, 297) if page_size == "A4" else (215.9, 279.4))

    def raised_initials(value: str) -> str:
        return " ".join(
            f'<span class="raised-initial">{esc(word[:1])}</span>{esc(word[1:])}'
            for word in value.split()
        )

    def bullet_rows(items: list[dict[str, Any]]) -> str:
        return (
            '<ul class="bullet-list">'
            + "".join(
                f'<li class="bullet-row"><span class="bullet-copy">{esc(item["text"])}</span></li>'
                for item in items
            )
            + "</ul>"
        )

    def render_segments(segments: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for segment in segments:
            content = esc(segment["text"])
            if segment.get("italic"):
                content = f"<em>{content}</em>"
            if segment.get("hyperlink"):
                content = f'<a href="{esc(segment["hyperlink"])}">{content}</a>'
            parts.append(content)
        return "".join(parts)

    contact_fields = resume_config.get("header", {}).get(
        "contactFields", ["phone", "email", "linkedin", "github", "website"]
    )
    contact_parts_html: list[str] = []
    for field in contact_fields:
        value = data["basics"].get(field, "")
        if not value:
            continue
        if field == "email":
            contact_parts_html.append(
                f'<a href="mailto:{esc(value)}">{esc(value)}</a>'
            )
        elif field in {"linkedin", "github", "website"}:
            contact_parts_html.append(
                f'<a href="{esc(build_url(value))}">{esc(value)}</a>'
            )
        else:
            contact_parts_html.append(esc(value))
    contact = " | ".join(contact_parts_html)
    experience = "".join(
        f'<article><p class="item-header"><span><strong>{esc(item["role"])}</strong>'
        f' | <em>{esc(item["company"])}</em></span><span>{esc(item["dates"])}</span></p>'
        f"{bullet_rows(item['bullets'])}</article>"
        for item in data.get("experience", [])
    )
    projects = "".join(
        f'<article><p class="project-header"><strong>{esc(item["name"])}</strong>'
        f' | <em>{esc(item["stack"])}</em></p>'
        f"{bullet_rows(item['bullets'])}</article>"
        for item in data.get("projects", [])
    )
    certification_rows = []
    for item in data.get("certifications", []):
        prefix, separator, description = item["name"].partition(":")
        certification_rows.append(
            f'<p class="item-header"><span><strong>{esc(prefix + separator)}</strong>'
            f'{esc(description)} | <strong><em>{esc(item["issuer"])}</em></strong></span>'
            f'<span>{esc(item["date"])}</span></p>'
        )
    certifications = "".join(certification_rows)
    achievements = '<ul class="bullet-list">' + "".join(
        f'<li class="bullet-row"><span class="bullet-copy">{render_segments(achievement_segments(item))}</span></li>'
        for item in data.get("achievements", [])
    ) + "</ul>"
    skills = "".join(
        f"<p><strong>{esc(item['category'])}:</strong> {esc(', '.join(item['items']))}</p>"
        for item in data.get("technicalSkills", [])
    )
    education = data.get("education")
    blocks: dict[str, str] = {
        "experience": experience,
        "certifications": certifications,
        "projects": projects,
        "achievements": achievements,
        "technical-skills": skills,
    }
    if data.get("summary"):
        blocks["summary"] = f'<p>{esc(data["summary"])}</p>'
    if education:
        blocks["education"] = (
            f'<p class="item-header"><span><strong>{esc(education["institution"])}</strong> | {esc(education["location"])}</span>'
            f'<span>{esc(education["dates"])}</span></p>'
            f'<p class="item-header"><span>{esc(education["degree"])}</span><span>GPA: {esc(education["gpa"])}</span></p>'
        )
    titles = {
        "summary": "SUMMARY",
        "experience": "EXPERIENCE",
        "certifications": "CERTIFICATIONS",
        "projects": "PROJECTS",
        "achievements": "ACHIEVEMENTS",
        "education": "EDUCATION",
        "technical-skills": "TECHNICAL SKILLS",
    }
    for extra in data.get("extraSections", []):
        source_id = extra["sourceId"]
        titles[source_id] = str(extra["title"]).upper()
        if extra["type"] == "portfolio":
            blocks[source_id] = "".join(
                f'<article><p class="project-header"><strong>{esc(item.get("name", ""))}</strong>'
                f' | <em>{esc(item.get("stack", ""))}</em></p>{bullet_rows(item.get("bullets", []))}</article>'
                for item in extra["items"]
            )
        else:
            blocks[source_id] = bullet_rows(
                [{"text": item.get("text", "")} for item in extra["items"]]
            )
    default_order = [
        "summary", "experience", "certifications", "projects", "achievements",
        "education", "technical-skills",
    ]
    section_order = [
        section["sourceId"] for section in resume_config.get("sections", [])
    ] or default_order
    rendered_sections = "".join(
        f'<section data-resume-section="{esc(source_id)}"><h2>{raised_initials(titles[source_id])}</h2>{blocks[source_id]}</section>'
        for source_id in section_order
        if source_id in blocks and blocks[source_id]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{esc(data['basics']['name'])} Resume</title>
<style>
@font-face{{font-family:{family};src:url("{regular_font}")}}
*{{box-sizing:border-box}} body{{margin:0;background:#eef2f7;color:{colors['ink']};font:{typography['bodyPt']}pt/1 {family},serif}}
main{{width:{page_width}mm;min-height:{page_height}mm;margin:24px auto;padding:{geometry['topMarginMm']}mm {geometry['rightMarginMm']}mm {geometry['bottomMarginMm']}mm {geometry['leftMarginMm']}mm;background:{colors['background']}}}
header{{text-align:center}} h1{{margin:0;color:{colors['accent']};font-size:{typography['namePt']}pt}} .name-initial{{font-size:{typography['namePt'] + 2}pt}}
header p{{margin:1px 0}} .headline{{font-size:{typography['headlinePt']}pt}} .contact{{font-size:{typography['contactPt']}pt;white-space:nowrap}}
section{{margin-top:{theme['spacing']['comfortable']['sectionBeforeMm']}mm}} h2{{margin:0 0 4px;color:{colors['accent']};font-size:{typography['sectionPt']}pt;
border-bottom:1pt solid {colors['accent']};line-height:1}} .raised-initial{{font-size:{typography['sectionPt'] + 2}pt}}
p,ul,div{{margin:0}} .item-header{{display:flex;justify-content:space-between;gap:16px}}
.item-header>span:last-child{{font-weight:400;white-space:nowrap}} .project-header{{margin-top:7px}}
article+article{{margin-top:7px}} .bullet-list{{padding-left:{bullet_tokens['leftMarginMm'] + bullet_tokens['gapMm']}mm}} .bullet-row{{margin:0;white-space:nowrap}}
.bullet-copy{{display:inline}}
a,a:visited{{color:{colors['ink']};text-decoration-color:{colors['ink']}}} @page{{size:{page_size};margin:0}}
</style></head><body><main>
<header><h1>{" ".join(f'<span class="name-initial">{esc(word[:1])}</span>{esc(word[1:])}' for word in data["basics"]["name"].split())}</h1>
<p class="headline"><strong>{esc(data['basics']['headline'])}</strong></p>
<p class="contact">{contact}</p></header>
{rendered_sections}
</main></body></html>
"""


class WriterSession:
    def __init__(self, working_dir: Path, font_dirs: list[Path] | None = None) -> None:
        self.working_dir = working_dir
        self.profile = working_dir / f"libreoffice-profile-{uuid.uuid4().hex}"
        self.profile.mkdir()
        self.pipe_name = f"jobs_tailoring_{uuid.uuid4().hex}"
        self.process: subprocess.Popen[str] | None = None
        self.desktop = None
        self.environment = os.environ.copy()
        self.font_dirs = font_dirs or [FONT_DIR]

    def __enter__(self) -> "WriterSession":
        uno_module = require_uno()
        executable = shutil.which("libreoffice") or shutil.which("soffice")
        if not executable:
            raise LibreOfficeRuntimeError(["LibreOffice Writer is unavailable."])
        cache_dir = self.working_dir / "font-cache"
        cache_dir.mkdir()
        font_config = self.working_dir / "fonts.conf"
        font_config.write_text(
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            "<fontconfig>"
            "<dir>/usr/share/fonts</dir>"
            "<dir>/usr/local/share/fonts</dir>"
            + "".join(f"<dir>{path}</dir>" for path in self.font_dirs)
            + f"<cachedir>{cache_dir}</cachedir>"
            "</fontconfig>\n",
            encoding="utf8",
        )
        self.environment["FONTCONFIG_FILE"] = str(font_config)
        self.environment["SAL_FONTPATH"] = os.pathsep.join(str(path) for path in self.font_dirs)
        command = [
            executable,
            f"-env:UserInstallation={self.profile.resolve().as_uri()}",
            "--headless",
            f"--accept=pipe,name={self.pipe_name};urp;StarOffice.ComponentContext",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
        ]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment,
        )
        local_context = uno_module.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_context
        )
        remote_context = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise LibreOfficeRuntimeError(
                    [f"LibreOffice exited during startup: {(stderr or stdout).strip()}"]
                )
            try:
                remote_context = resolver.resolve(
                    f"uno:pipe,name={self.pipe_name};urp;StarOffice.ComponentContext"
                )
                break
            except Exception:
                time.sleep(0.1)
        if remote_context is None:
            raise LibreOfficeRuntimeError(["Timed out waiting for LibreOffice Writer."])
        self.desktop = remote_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", remote_context
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.desktop is not None:
            try:
                self.desktop.terminate()
            except Exception:
                pass
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.process.stdout is not None:
                self.process.stdout.close()
            if self.process.stderr is not None:
                self.process.stderr.close()


def _set_properties(target: Any, **properties: Any) -> None:
    for name, value in properties.items():
        try:
            setattr(target, name, value)
        except Exception as error:
            raise RuntimeError(f"Unable to set Writer property {name}: {error}") from error


def _tab_stop(position: int) -> Any:
    uno_module = require_uno()
    stop = uno_module.createUnoStruct("com.sun.star.style.TabStop")
    stop.Position = position
    stop.Alignment = RIGHT
    stop.DecimalChar = "."
    stop.FillChar = " "
    return stop


def export_pdf_with_libreoffice(
    odt_path: Path, pdf_path: Path, working_dir: Path, environment: dict[str, str]
) -> None:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise LibreOfficeRuntimeError(["LibreOffice Writer is unavailable."])
    profile = working_dir / f"pdf-export-profile-{uuid.uuid4().hex}"
    profile.mkdir()
    filter_options = json.dumps(
        {
            name: {"type": "boolean", "value": "true" if enabled else "false"}
            for name, enabled in PDF_EXPORT_OPTIONS
        },
        separators=(",", ":"),
    )
    result = subprocess.run(
        [
            executable,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            f"pdf:writer_pdf_Export:{filter_options}",
            "--outdir",
            str(working_dir),
            str(odt_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=environment,
    )
    generated_path = working_dir / f"{odt_path.stem}.pdf"
    if result.returncode != 0 or not generated_path.exists():
        raise LibreOfficeRuntimeError(
            [
                "LibreOffice PDF export failed: "
                + (result.stderr or result.stdout or "no diagnostic output").strip()
            ]
        )
    if generated_path != pdf_path:
        os.replace(generated_path, pdf_path)


class GenerationLock:
    def __init__(self, output_dir: Path) -> None:
        self.path = output_dir / ".generate.lock"
        self.fd: int | None = None

    def __enter__(self) -> "GenerationLock":
        if os.environ.get(PIPELINE_LOCK_ENV) == "1":
            return self
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise LibreOfficeRuntimeError(
                [f"Another resume generation is active in {self.path.parent}."]
            ) from error
        os.write(self.fd, f"pid={os.getpid()} started={time.time()}\n".encode("utf8"))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is not None:
            os.close(self.fd)
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def build_writer_document(
    session: WriterSession,
    data: dict[str, Any],
    odt_path: Path,
    theme: dict[str, Any] | None = None,
    resume_config: dict[str, Any] | None = None,
    spacing_level: str = "comfortable",
) -> None:
    theme = theme or {
        "font": {"family": "Gelasio"},
        "colors": {"accent": "#0D6E6E", "ink": "#434343"},
        "typography": {"bodyPt": 10, "namePt": 20, "headlinePt": 12, "sectionPt": 10, "contactPt": 9},
        "geometry": {"topMarginMm": 7, "bottomMarginMm": 7, "leftMarginMm": 10, "rightMarginMm": 10},
        "spacing": {"comfortable": {"sectionBeforeMm": 4.2, "entryBeforeMm": 2.6}},
        "bullets": {"leftMarginMm": 2.5, "gapMm": 2.0},
    }
    resume_config = resume_config or {"document": {"pageSize": "A4"}}
    font_family = theme["font"]["family"]
    accent = _hex_color(theme["colors"]["accent"])
    ink = _hex_color(theme["colors"]["ink"])
    type_tokens = theme["typography"]
    geometry = theme["geometry"]
    spacing = theme["spacing"].get(spacing_level, theme["spacing"]["comfortable"])
    bullet_tokens = theme.get("bullets", {"leftMarginMm": 2.5, "gapMm": 2.0})
    bullet_indent = int(
        (bullet_tokens["leftMarginMm"] + bullet_tokens["gapMm"]) * 100
    )
    bullet_gap = int(bullet_tokens["gapMm"] * 100)
    is_letter = resume_config["document"].get("pageSize", "A4").upper() == "LETTER"
    document = session.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    try:
        properties = document.DocumentProperties
        properties.Title = resume_title(data)
        properties.Subject = resume_subject(data)
        properties.Author = data["basics"]["name"]
        properties.Description = DETERMINISTIC_DESCRIPTION

        character_styles = document.StyleFamilies.getByName("CharacterStyles")
        for style_name in ("Internet link", "Visited Internet Link"):
            if character_styles.hasByName(style_name):
                link_style = character_styles.getByName(style_name)
                _set_properties(
                    link_style,
                    CharColor=ink,
                    CharUnderline=1,
                    CharUnderlineColor=ink,
                    CharWeight=100.0,
                    CharPosture=NONE,
                )

        page_styles = document.StyleFamilies.getByName("PageStyles")
        page_style_name = (
            "Default Page Style"
            if page_styles.hasByName("Default Page Style")
            else "Standard"
        )
        page_style = page_styles.getByName(page_style_name)
        _set_properties(
            page_style,
            Width=21590 if is_letter else 21000,
            Height=27940 if is_letter else 29700,
            IsLandscape=False,
            TopMargin=int(geometry["topMarginMm"] * 100),
            BottomMargin=int(geometry["bottomMarginMm"] * 100),
            LeftMargin=int(geometry["leftMarginMm"] * 100),
            RightMargin=int(geometry["rightMarginMm"] * 100),
            HeaderIsOn=False,
            FooterIsOn=False,
        )
        text = document.Text

        numbering_styles = document.StyleFamilies.getByName("NumberingStyles")
        list_style = numbering_styles.getByName("List 1")
        numbering_rules = list_style.NumberingRules
        level = list(numbering_rules.getByIndex(0))
        for prop in level:
            if prop.Name in {"IndentAt", "ListtabStopPosition"}:
                prop.Value = bullet_indent
            elif prop.Name == "FirstLineIndent":
                prop.Value = -bullet_gap
        uno_module = require_uno()
        uno_module.invoke(
            numbering_rules,
            "replaceByIndex",
            (0, uno_module.Any("[]com.sun.star.beans.PropertyValue", tuple(level))),
        )
        list_style.NumberingRules = numbering_rules

        def rich_paragraph(
            segments: list[dict[str, Any]],
            *,
            style: str = "Text body",
            size: float = 10.0,
            align: Any = LEFT,
            before: int = 0,
            after: int = 0,
            left_margin: int = 0,
            tabs: tuple[Any, ...] = (),
            hyperlink: str | None = None,
            numbering_style: str | None = None,
            bottom_border: bool = False,
            keep_with_next: bool = False,
            allow_split: bool = True,
        ) -> None:
            cursor = text.createTextCursorByRange(text.End)
            try:
                cursor.ParaStyleName = style
            except Exception:
                cursor.ParaStyleName = "Standard"
            _set_properties(
                cursor,
                ParaAdjust=align,
                ParaTopMargin=before,
                ParaBottomMargin=after,
                ParaLeftMargin=left_margin,
                ParaKeepTogether=keep_with_next,
                ParaSplit=allow_split,
                ParaLineSpacing=require_uno().createUnoStruct("com.sun.star.style.LineSpacing"),
            )
            cursor.ParaLineSpacing.Mode = 0
            cursor.ParaLineSpacing.Height = 100
            if tabs:
                cursor.ParaTabStops = tabs
            if numbering_style:
                cursor.NumberingStyleName = numbering_style
            else:
                cursor.NumberingStyleName = ""
            if bottom_border:
                border = require_uno().createUnoStruct("com.sun.star.table.BorderLine2")
                border.Color = accent
                border.OuterLineWidth = 35
                border.LineWidth = 35
                cursor.BottomBorder = border
                cursor.BottomBorderDistance = 35
            for segment in segments:
                content = str(segment["text"])
                segment_size = float(segment.get("size", size))
                hyperlink = str(segment.get("hyperlink", ""))
                _set_properties(
                    cursor,
                    CharFontName=font_family,
                    CharFontNameAsian=font_family,
                    CharHeight=segment_size,
                    CharHeightAsian=segment_size,
                    CharWeight=150.0 if segment.get("bold", False) else 100.0,
                    CharPosture=ITALIC if segment.get("italic", False) else NONE,
                    CharColor=int(segment.get("color", ink)),
                    CharUnderline=1 if segment.get("underline", False) else 0,
                    CharUnderlineColor=int(segment.get("underlineColor", ink)),
                    HyperLinkURL="",
                )
                text.insertString(cursor, content, False)
                if hyperlink:
                    cursor.goLeft(len(content), True)
                    cursor.HyperLinkURL = hyperlink
                    cursor.CharUnderline = 1
                    cursor.CharUnderlineColor = int(
                        segment.get("underlineColor", ink)
                    )
                    cursor.CharColor = int(segment.get("color", ink))
                    cursor.collapseToEnd()
            text.insertControlCharacter(cursor, 0, False)

        def paragraph(content: str, **options: Any) -> None:
            segment_keys = {
                "size",
                "bold",
                "italic",
                "color",
                "underline",
                "underlineColor",
                "hyperlink",
            }
            segment = {"text": content}
            for key in tuple(options):
                if key in segment_keys:
                    segment[key] = options.pop(key)
            rich_paragraph([segment], **options)

        name_segments: list[dict[str, Any]] = []
        for word_index, word in enumerate(data["basics"]["name"].split()):
            if word_index:
                name_segments.append(
                    {"text": " ", "size": type_tokens["namePt"], "bold": True, "color": accent}
                )
            name_segments.extend(
                [
                    {"text": word[:1], "size": type_tokens["namePt"] + 2, "bold": True, "color": accent},
                    {"text": word[1:], "size": type_tokens["namePt"], "bold": True, "color": accent},
                ]
            )
        rich_paragraph(name_segments, style="Title", align=CENTER)
        paragraph(
            data["basics"]["headline"],
            size=type_tokens["headlinePt"],
            bold=True,
            align=CENTER,
            before=0,
        )

        contact_cursor = text.createTextCursorByRange(text.End)
        _set_properties(
            contact_cursor,
            CharFontName=font_family,
            CharFontNameAsian=font_family,
            CharHeight=float(type_tokens["contactPt"]),
            CharHeightAsian=float(type_tokens["contactPt"]),
            CharColor=ink,
            CharWeight=100.0,
            ParaAdjust=CENTER,
            ParaTopMargin=10,
            ParaBottomMargin=0,
        )
        configured_contact_fields = resume_config.get("header", {}).get(
            "contactFields", ["phone", "email", "linkedin", "github", "website"]
        )
        contact_parts = []
        for field in configured_contact_fields:
            value = data["basics"].get(field, "")
            if not value:
                continue
            url = None
            if field == "email":
                url = f"mailto:{value}"
            elif field in {"linkedin", "github", "website"}:
                url = build_url(value)
            contact_parts.append((value, url))
        for index, (label, url) in enumerate(contact_parts):
            if index:
                contact_cursor.HyperLinkURL = ""
                contact_cursor.CharUnderline = 0
                text.insertString(contact_cursor, " | ", False)
            text.insertString(contact_cursor, label, False)
            if url:
                contact_cursor.goLeft(len(label), True)
                contact_cursor.HyperLinkURL = url
                contact_cursor.CharUnderline = 1
                contact_cursor.CharUnderlineColor = ink
                contact_cursor.CharColor = ink
                contact_cursor.CharWeight = 100.0
                contact_cursor.collapseToEnd()
        text.insertControlCharacter(contact_cursor, 0, False)

        def section(title: str) -> None:
            segments: list[dict[str, Any]] = []
            for word_index, word in enumerate(title.split()):
                if word_index:
                    segments.append(
                        {"text": " ", "size": type_tokens["sectionPt"], "bold": True, "color": accent}
                    )
                segments.extend(
                    [
                        {"text": word[:1], "size": type_tokens["sectionPt"] + 2, "bold": True, "color": accent},
                        {"text": word[1:], "size": type_tokens["sectionPt"], "bold": True, "color": accent},
                    ]
                )
            rich_paragraph(
                segments,
                style="Heading 1",
                before=int(spacing["sectionBeforeMm"] * 100),
                after=35,
                bottom_border=True,
                keep_with_next=True,
            )

        def split_header(
            left_segments: list[dict[str, Any]],
            right: str,
            before: int = int(spacing["entryBeforeMm"] * 100),
            keep_with_next: bool = False,
        ) -> None:
            rich_paragraph(
                [*left_segments, {"text": "\t"}, {"text": right, "size": type_tokens["bodyPt"]}],
                before=before,
                tabs=(_tab_stop(18800),),
                keep_with_next=keep_with_next,
                allow_split=False,
            )

        def list_item_segments(segments: list[dict[str, Any]]) -> None:
            rich_paragraph(
                [{**segment, "size": segment.get("size", type_tokens["bodyPt"])} for segment in segments],
                style="List 1",
                before=0,
                after=0,
                left_margin=bullet_indent,
                numbering_style="List 1",
                allow_split=False,
            )

        def list_item(content: str, url: str | None = None) -> None:
            segments: list[dict[str, Any]] = [{"text": content, "size": type_tokens["bodyPt"]}]
            if url:
                segments[0]["hyperlink"] = url
                segments[0]["underline"] = True
            list_item_segments(segments)

        def portfolio(title: str, items: list[dict[str, Any]]) -> None:
            section(title)
            for item in items:
                rich_paragraph(
                    [
                        {"text": item.get("name", ""), "size": type_tokens["bodyPt"], "bold": True},
                        {"text": " | ", "size": type_tokens["bodyPt"]},
                        {"text": item.get("stack", ""), "size": type_tokens["bodyPt"], "italic": True},
                    ],
                    before=int(spacing["entryBeforeMm"] * 100),
                    keep_with_next=True,
                    allow_split=False,
                )
                for bullet in item.get("bullets", []):
                    list_item(bullet["text"])

        extra_index = {item["sourceId"]: item for item in data.get("extraSections", [])}
        default_order = [
            "summary", "experience", "certifications", "projects", "achievements",
            "education", "technical-skills",
        ]
        configured_order = [
            item["sourceId"] for item in resume_config.get("sections", [])
        ] or default_order
        for source_id in configured_order:
            if source_id == "summary":
                section("SUMMARY")
                paragraph(data["summary"], size=type_tokens["bodyPt"])
            elif source_id == "experience":
                section("EXPERIENCE")
                for entry in data.get("experience", []):
                    split_header(
                        [
                            {"text": entry["role"], "size": type_tokens["bodyPt"], "bold": True},
                            {"text": " | ", "size": type_tokens["bodyPt"]},
                            {"text": entry["company"], "size": type_tokens["bodyPt"], "italic": True},
                        ], entry["dates"], keep_with_next=True,
                    )
                    for bullet in entry["bullets"]:
                        list_item(bullet["text"])
            elif source_id == "certifications":
                section("CERTIFICATIONS")
                for certification in data.get("certifications", []):
                    prefix, separator, description = certification["name"].partition(":")
                    split_header(
                        [
                            {"text": prefix + separator, "size": type_tokens["bodyPt"], "bold": True},
                            {"text": description, "size": type_tokens["bodyPt"]},
                            {"text": " | ", "size": type_tokens["bodyPt"]},
                            {"text": certification["issuer"], "size": type_tokens["bodyPt"], "bold": True, "italic": True},
                        ], certification["date"], before=0,
                    )
            elif source_id == "projects":
                portfolio("PROJECTS", data.get("projects", []))
            elif source_id == "achievements":
                section("ACHIEVEMENTS")
                for achievement in data.get("achievements", []):
                    list_item_segments(achievement_segments(achievement))
            elif source_id == "education" and data.get("education"):
                education = data["education"]
                section("EDUCATION")
                split_header(
                    [
                        {"text": education["institution"], "size": type_tokens["bodyPt"], "bold": True},
                        {"text": " | ", "size": type_tokens["bodyPt"]},
                        {"text": education["location"], "size": type_tokens["bodyPt"]},
                    ], education["dates"], before=0,
                )
                split_header(
                    [{"text": education["degree"], "size": type_tokens["bodyPt"]}],
                    f"GPA: {education['gpa']}", before=0,
                )
            elif source_id == "technical-skills":
                section("TECHNICAL SKILLS")
                for group in data.get("technicalSkills", []):
                    rich_paragraph(
                        [
                            {"text": f"{group['category']}:", "size": type_tokens["bodyPt"], "bold": True},
                            {"text": f" {', '.join(group['items'])}", "size": type_tokens["bodyPt"]},
                        ]
                    )
            elif source_id in extra_index:
                extra = extra_index[source_id]
                if extra["type"] == "portfolio":
                    portfolio(extra["title"].upper(), extra["items"])
                else:
                    section(extra["title"].upper())
                    for item in extra["items"]:
                        list_item(item.get("text", ""), item.get("url"))

        document.storeAsURL(
            odt_path.resolve().as_uri(),
            (
                property_value("FilterName", "writer8"),
                property_value("Overwrite", True),
            ),
        )
    finally:
        document.close(True)


def generate(
    input_json: Path,
    output_dir: Path,
    cv_path: Path,
    *,
    policy: dict[str, Any] | None = None,
    theme: dict[str, Any] | None = None,
    resume_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_pdf_filename = ""
    existing_report_path = output_dir / "layout-validation.json"
    if existing_report_path.exists():
        try:
            existing_report = load_json(existing_report_path)
            candidate = existing_report.get("pdfFileName", "")
            if (
                isinstance(candidate, str)
                and Path(candidate).name == candidate
                and candidate.lower().endswith(".pdf")
            ):
                previous_pdf_filename = candidate
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    with GenerationLock(output_dir):
        try:
            policy = policy or load_json(POLICY_PATH)
            cv = load_cv(cv_path)
        except Exception as error:
            if isinstance(error, GenerateResumeError):
                raise
            raise ContentValidationError("inputs", [str(error)]) from error
        tailored = load_json(input_json)
        issues = validate_tailored_resume(tailored, cv, policy)
        if issues:
            raise ContentValidationError("content-validation", issues)
        source_json = input_json.read_bytes()
        source_json_sha256 = hashlib.sha256(source_json).hexdigest()
        try:
            pdf_filename = final_pdf_filename(tailored)
        except ValueError as error:
            raise ContentValidationError("content-validation", [str(error)]) from error

        with tempfile.TemporaryDirectory(prefix=".resume-build-", dir=output_dir.parent) as temp_name:
            temp_dir = Path(temp_name)
            html_path = temp_dir / "tailored-resume.html"
            odt_path = temp_dir / "tailored-resume.odt"
            pdf_path = temp_dir / pdf_filename
            report_path = temp_dir / "layout-validation.json"
            html_path.write_text(
                render_html(tailored, theme=theme, resume_config=resume_config), encoding="utf8"
            )
            spacing_levels = ["comfortable"]
            if theme and "compact" in theme.get("spacing", {}):
                spacing_levels.append("compact")
            try:
                font_dirs = None
                if theme:
                    font_dirs = sorted(
                        {Path(value).parent for value in theme["font"]["files"].values()}
                    )
                report = None
                chosen_spacing = spacing_levels[-1]
                for spacing_level in spacing_levels:
                    with WriterSession(temp_dir, font_dirs=font_dirs) as session:
                        build_writer_document(
                            session,
                            tailored,
                            odt_path,
                            theme=theme,
                            resume_config=resume_config,
                            spacing_level=spacing_level,
                        )
                        writer_environment = session.environment.copy()
                    export_pdf_with_libreoffice(odt_path, pdf_path, temp_dir, writer_environment)
                    report = inspect_pdf(
                        pdf_path,
                        tailored,
                        policy,
                        source_json_sha256,
                        theme=theme,
                        resume_config=resume_config,
                    )
                    chosen_spacing = spacing_level
                    if report.get("pageCount", 0) <= policy.get("maxPages", 1):
                        break
            except GenerateResumeError:
                raise
            except Exception as error:
                raise LibreOfficeRuntimeError([f"LibreOffice export failed: {error}"]) from error
            assert report is not None
            report["spacingLevel"] = chosen_spacing
            report["sourceResumeConfigSha256"] = tailored.get("sourceResumeConfigSha256")
            report["sourceThemeSha256"] = tailored.get("sourceThemeSha256")
            report["pdfFileName"] = pdf_filename
            report["htmlSha256"] = hashlib.sha256(html_path.read_bytes()).hexdigest()
            report["odtSha256"] = hashlib.sha256(odt_path.read_bytes()).hexdigest()
            write_report(report_path, report)
            if not report["ok"]:
                failed_report = output_dir / "layout-validation.failed.json"
                shutil.copy2(report_path, failed_report)
                shutil.copy2(pdf_path, output_dir / f"{Path(pdf_filename).stem}.failed.pdf")
                raise ContentValidationError(
                    "pdf-validation",
                    [
                        f"Final PDF validation failed; see {failed_report}.",
                        *report["issues"],
                    ],
                )
            for source in (html_path, odt_path, pdf_path, report_path):
                os.replace(source, output_dir / source.name)
            obsolete_pdf_names = {"tailored-resume.pdf"}
            if previous_pdf_filename and previous_pdf_filename != pdf_filename:
                obsolete_pdf_names.add(previous_pdf_filename)
            for obsolete_name in obsolete_pdf_names:
                obsolete_path = output_dir / obsolete_name
                if obsolete_path.exists():
                    obsolete_path.unlink()
            for stale_name in (
                "layout-validation.failed.json",
                f"{Path(pdf_filename).stem}.failed.pdf",
            ):
                stale_path = output_dir / stale_name
                if stale_path.exists():
                    stale_path.unlink()
        return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate semantic HTML, editable ODT, and tagged PDF resume artifacts."
    )
    parser.add_argument("resume_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--cv", type=Path, default=DEFAULT_CV_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = generate(
            args.resume_json.resolve(), args.output_dir.resolve(), args.cv.resolve()
        )
    except GenerateResumeError as error:
        print(json.dumps(error_summary(error), separators=(",", ":")))
        return error.exit_code
    print(json.dumps(cli_summary(report), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
