"""Turns a Report into a Teams Adaptive Card or a Markdown preview."""


def to_adaptive_card(report):
    body = [
        {"type": "TextBlock", "text": report.title, "size": "Large", "weight": "Bolder", "wrap": True},
        {"type": "TextBlock", "text": f"_{report.subtitle}_", "wrap": True, "spacing": "Small",
         "isSubtle": True},
    ]
    for i, section in enumerate(report.sections):
        items = [{"type": "TextBlock", "text": section.title, "weight": "Bolder", "size": "Medium",
                  "wrap": True, "color": "Accent"}]
        for line in section.lines:
            items.append({"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"})
        if section.facts:
            items.append({"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in section.facts]})
        body.append({
            "type": "Container",
            "style": "emphasis" if i % 2 == 0 else "default",
            "bleed": True,
            "spacing": "Medium",
            "items": items,
        })
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
    }
    return card


def to_teams_payload(report):
    """The message body a Teams 'post when a webhook request is received' workflow expects."""
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": to_adaptive_card(report),
        }],
    }


def to_markdown(report):
    out = [f"# {report.title}", "", f"_{report.subtitle}_", ""]
    for section in report.sections:
        out += [f"## {section.title}", ""]
        for line in section.lines:
            out += [line, ""]
        if section.facts:
            out += ["| | |", "|---|---|"]
            out += [f"| {k} | {v} |" for k, v in section.facts]
            out.append("")
    return "\n".join(out)
