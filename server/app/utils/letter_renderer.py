import re
from typing import List


def render_template(content: str, variables: dict) -> str:
    """
    Replace {{variable_name}} placeholders, then convert the plain-text
    letter format to styled HTML if the template doesn't already contain
    HTML markup.
    """
    def _sanitize(value: str) -> str:
        return (
            value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

    def replacer(match: re.Match) -> str:
        var_name = match.group(1).strip()
        value = variables.get(var_name, "")
        return _sanitize(str(value))

    rendered = re.sub(r"\{\{([^}]+)\}\}", replacer, content)

    # If already HTML, return as-is
    if re.search(r"<(p|h[1-6]|div|section|table)\b", rendered, re.IGNORECASE):
        return rendered

    return _plain_to_html(rendered)


def _plain_to_html(text: str) -> str:
    """Convert a structured plain-text letter to a fully styled HTML document."""
    LETTER_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Georgia, 'Times New Roman', serif; background: #f4f4f4; }
    .letter-page {
        background: #fff;
        max-width: 760px;
        margin: 0 auto;
        padding: 56px 64px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        color: #1a1a1a;
        font-size: 14px;
        line-height: 1.75;
    }
    .letterhead {
        border-bottom: 3px solid #1e3a5f;
        padding-bottom: 14px;
        margin-bottom: 28px;
        color: #1e3a5f;
        font-size: 13px;
        font-family: Arial, sans-serif;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .meta-block {
        margin-bottom: 24px;
        font-size: 13px;
        line-height: 1.9;
        color: #333;
    }
    .meta-block .label { color: #666; }
    .address-block {
        margin-bottom: 24px;
        font-size: 13px;
        line-height: 1.8;
        font-style: italic;
        color: #444;
    }
    .re-line {
        margin: 20px 0;
        font-weight: bold;
        font-size: 14px;
        color: #1e3a5f;
        border-left: 4px solid #FE017D;
        padding-left: 12px;
    }
    .salutation {
        margin: 20px 0 16px;
        font-size: 14px;
    }
    .section-header {
        font-size: 12px;
        font-family: Arial, sans-serif;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #1e3a5f;
        margin: 28px 0 10px;
        padding: 6px 0;
        border-bottom: 1px solid #dde3ec;
    }
    .body-para {
        margin-bottom: 14px;
        text-align: justify;
        hyphens: auto;
    }
    .signature-block {
        margin-top: 36px;
        padding-top: 16px;
        border-top: 1px solid #e0e0e0;
        font-size: 13px;
        line-height: 1.9;
    }
    .confidentiality {
        margin-top: 28px;
        padding-top: 12px;
        border-top: 1px dashed #ccc;
        font-size: 11px;
        color: #888;
        font-style: italic;
    }
    """

    lines = text.split('\n')
    sections = _group_sections(lines)
    html_parts = [f'<html><head><meta charset="utf-8"><style>{LETTER_CSS}</style></head><body><div class="letter-page">']

    for kind, content_lines in sections:
        block = '\n'.join(content_lines).strip()
        if not block:
            continue

        if kind == 'letterhead':
            html_parts.append(f'<div class="letterhead">{block}</div>')

        elif kind == 'meta':
            rows = []
            for l in content_lines:
                l = l.strip()
                if not l:
                    continue
                # "Date: ...", "Case Reference: ..." → label: value
                if ':' in l:
                    label, _, val = l.partition(':')
                    rows.append(f'<span class="label">{label}:</span> {val.strip()}')
                else:
                    rows.append(l)
            html_parts.append('<div class="meta-block">' + '<br>'.join(rows) + '</div>')

        elif kind == 'address':
            rows = [l.strip() for l in content_lines if l.strip()]
            html_parts.append('<div class="address-block">' + '<br>'.join(rows) + '</div>')

        elif kind == 're':
            html_parts.append(f'<p class="re-line">{block}</p>')

        elif kind == 'salutation':
            html_parts.append(f'<p class="salutation">{block}</p>')

        elif kind == 'section_header':
            html_parts.append(f'<div class="section-header">{block}</div>')

        elif kind == 'signature':
            rows = [l.strip() for l in content_lines if l.strip()]
            html_parts.append('<div class="signature-block">' + '<br>'.join(rows) + '</div>')

        elif kind == 'confidentiality':
            html_parts.append(f'<p class="confidentiality">{block}</p>')

        else:  # 'body'
            html_parts.append(f'<p class="body-para">{block}</p>')

    html_parts.append('</div></body></html>')
    return '\n'.join(html_parts)


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # All uppercase, no lowercase, at least 8 chars, no punctuation that breaks it
    if stripped.isupper() and len(stripped) >= 8 and stripped.replace(' ', '').replace('/', '').replace('&', '').isalpha():
        return True
    return False


def _group_sections(lines: List[str]) -> List[tuple]:
    """Group lines into semantic sections: letterhead, meta, address, re, salutation,
    section_header, body, signature, confidentiality."""
    sections = []
    i = 0
    n = len(lines)
    in_signature = False
    found_sincerely = False

    # Split the letter into line-groups (separated by blank lines)
    groups: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.strip() == '':
            if current:
                groups.append(current)
                current = []
        else:
            current.append(line)
    if current:
        groups.append(current)

    for gi, group in enumerate(groups):
        joined = '\n'.join(line.strip() for line in group)
        first = group[0].strip()
        last = groups[-1][0].strip() if groups else ''

        # [PLAN LETTERHEAD] or similar
        if first.startswith('[') and first.endswith(']'):
            sections.append(('letterhead', [first[1:-1]]))
            continue

        # Date / Case Reference block (typically first 2-3 lines after letterhead)
        if gi <= 2 and any(('Date:' in l or 'Case Reference:' in l or 'Case #' in l) for l in group):
            sections.append(('meta', group))
            continue

        # Provider address block (lines that look like a name/NPI)
        if gi <= 4 and any(('NPI:' in l or 'TIN:' in l) for l in group) and len(group) <= 5:
            sections.append(('address', group))
            continue

        # RE: subject line
        if first.upper().startswith('RE:'):
            sections.append(('re', group))
            continue

        # Salutation
        if first.startswith('Dear '):
            sections.append(('salutation', group))
            continue

        # Signature trigger
        if first in ('Sincerely,', 'Sincerely', 'Regards,', 'Regards'):
            found_sincerely = True
            sections.append(('signature', group))
            continue

        # Lines after "Sincerely" belong to signature block
        if found_sincerely and gi > 0:
            # Confidentiality notice (long italic line near the end)
            if len(group) == 1 and ('confidential' in first.lower() or 'intended solely' in first.lower()):
                sections.append(('confidentiality', group))
            else:
                sections.append(('signature', group))
            continue

        # ALL CAPS section header
        if len(group) == 1 and _is_section_header(first):
            sections.append(('section_header', group))
            continue

        # Everything else is body
        sections.append(('body', group))

    return sections


def extract_variables(content: str) -> List[str]:
    """Return a list of variable names found in {{...}} placeholders."""
    matches = re.findall(r"\{\{([^}]+)\}\}", content)
    return [m.strip() for m in matches]
