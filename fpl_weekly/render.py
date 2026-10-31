"""Turns a Report into a Teams Adaptive Card or a Markdown preview."""

ALIGN = {"left": "Left", "center": "Center", "right": "Right"}


def _text(text, **extra):
    block = {"type": "TextBlock", "text": text, "wrap": True}
    block.update(extra)
    return block


def _table_rows(table):
    """Adaptive Card 'table' built from ColumnSets (works on Teams desktop and mobile)."""
    n = len(table.rows[0]) if table.rows else len(table.headers or [])
    align = table.align or ["left"] * n
    widths = table.widths or ["stretch"] * n

    def row(cells, header=False):
        cols = []
        for i, cell in enumerate(cells):
            cols.append({
                "type": "Column",
                "width": widths[i],
                "items": [_text(cell or " ",
                                **({"horizontalAlignment": ALIGN[align[i]]} if align[i] != "left" else {}),
                                **({"weight": "Bolder", "isSubtle": True, "size": "Small"} if header else {}))],
            })
        return {"type": "ColumnSet", "columns": cols, "spacing": "Small"}

    out = []
    if table.headers:
        out.append(row(table.headers, header=True))
    for i, cells in enumerate(table.rows):
        r = row(cells)
        if i == 0 and table.headers:
            r["separator"] = True
        out.append(r)
    return out


def to_teaser_card(report, link):
    """Short card for Teams: headline, summary, key facts and a button to the full page."""
    body = [
        _text(f"{report.league_name.upper()}  ·  GAMEWEEK {report.gameweek}",
              size="Small", weight="Bolder", isSubtle=True),
        _text(report.headline, size="ExtraLarge", weight="Bolder", spacing="Small"),
        _text(report.standfirst, spacing="Small"),
    ]
    for i, (label, value) in enumerate(report.key_facts):
        body.append({
            "type": "ColumnSet", "spacing": "Medium" if i == 0 else "Small", "separator": i == 0,
            "columns": [
                {"type": "Column", "width": "stretch",
                 "items": [_text(label, isSubtle=True, size="Small", weight="Bolder")]},
                {"type": "Column", "width": "auto",
                 "items": [_text(value, weight="Bolder", horizontalAlignment="Right")]},
            ],
        })
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
        "actions": [{"type": "Action.OpenUrl", "title": "Read the full report", "url": link}],
    }


def to_adaptive_card(report):
    body = [
        _text(f"{report.league_name.upper()}  ·  GAMEWEEK {report.gameweek}",
              size="Small", weight="Bolder", isSubtle=True),
        _text(report.headline, size="ExtraLarge", weight="Bolder", spacing="Small"),
        _text(report.standfirst, spacing="Small"),
    ]
    for section in report.sections:
        items = [_text(section.title, size="Medium", weight="Bolder")]
        for p in section.paragraphs:
            items.append(_text(p, spacing="Small"))
        if section.table:
            items += _table_rows(section.table)
        for b in section.bullets:
            items.append(_text(f"•  {b}", spacing="Small"))
        body.append({"type": "Container", "separator": True, "spacing": "Large", "items": items})
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
    }


def to_teams_payload(report, link=None):
    """The message body a Teams 'post when a webhook request is received' workflow expects."""
    card = to_teaser_card(report, link) if link else to_adaptive_card(report)
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": card,
        }],
    }


def to_markdown(report):
    out = [f"{report.league_name.upper()} · GAMEWEEK {report.gameweek}", "",
           f"# {report.headline}", "", report.standfirst, ""]
    md_align = {"left": ":---", "center": ":---:", "right": "---:"}
    for section in report.sections:
        out += [f"## {section.title}", ""]
        for p in section.paragraphs:
            out += [p, ""]
        t = section.table
        if t and t.headers:
            align = t.align or ["left"] * len(t.headers)
            out.append("| " + " | ".join(t.headers) + " |")
            out.append("|" + "|".join(md_align[a] for a in align) + "|")
            out += ["| " + " | ".join(r) + " |" for r in t.rows]
            out.append("")
        elif t:
            out += [f"- **{r[0]}:** {r[1]}" for r in t.rows]
            out.append("")
        for b in section.bullets:
            out.append(f"- {b}")
        if section.bullets:
            out.append("")
    return "\n".join(out)
