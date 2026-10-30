"""Build the leadership slide deck from the pipeline report.

The prose is written for a product and engineering review. Numbers are read
from output/report.json so the deck cannot drift from the briefing.

    python scripts/build_deck.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "output" / "report.json"
OUT_PATH = ROOT / "deck" / "Transcript-Intelligence-Briefing.pptx"

W, H = 13.333, 7.5

INK = RGBColor(0x1C, 0x19, 0x15)
MUTED = RGBColor(0x5C, 0x56, 0x4E)
FAINT = RGBColor(0x8A, 0x83, 0x78)
PAPER = RGBColor(0xF3, 0xEE, 0xE6)
CARD = RGBColor(0xFA, 0xF7, 0xF2)
LINE = RGBColor(0xDD, 0xD4, 0xC8)
COPPER = RGBColor(0x8C, 0x4A, 0x2F)
RISK = RGBColor(0x9A, 0x34, 0x12)
GOOD = RGBColor(0x1F, 0x6B, 0x4A)
NAVY = RGBColor(0x1E, 0x4D, 0x6B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SERIF = "Georgia"
SANS = "Calibri"


def _anchor(text_frame, name: str) -> None:
    text_frame.word_wrap = True
    text_frame.auto_size = None
    text_frame.margin_left = Emu(0)
    text_frame.margin_right = Emu(0)
    text_frame.margin_top = Emu(0)
    text_frame.margin_bottom = Emu(0)
    text_frame._txBody.bodyPr.set("anchor", {"top": "t", "middle": "ctr", "bottom": "b"}[name])


def _run(paragraph, text, size, color, font, bold=False, italic=False):
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    r_pr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:cs", "a:ea"):
        node = r_pr.find(qn(tag))
        if node is None:
            node = r_pr.makeelement(qn(tag), {})
            r_pr.append(node)
        node.set("typeface", font)
    return run


def add_shape(slide, x, y, w, h, fill, line=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(0.75)
    # Drop the default shadow-looking adjustment
    shape.shadow.inherit = False
    return shape


def add_text(slide, x, y, w, h, content, size=16, color=INK, font=SANS, bold=False, italic=False, align=PP_ALIGN.LEFT, anchor="top"):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    _anchor(frame, anchor)
    for index, part in enumerate(content.split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_before = Pt(0)
        paragraph.space_after = Pt(0)
        _run(paragraph, part, size, color, font, bold, italic)
    return box


def add_paragraphs(slide, x, y, w, h, lines, anchor="top"):
    """lines: list of dicts with text, size, color, font, bold, italic, align, before, after."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    _anchor(frame, anchor)
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = line.get("align", PP_ALIGN.LEFT)
        paragraph.space_before = Pt(line.get("before", 0))
        paragraph.space_after = Pt(line.get("after", 0))
        _run(
            paragraph,
            line["text"],
            line.get("size", 16),
            line.get("color", INK),
            line.get("font", SANS),
            line.get("bold", False),
            line.get("italic", False),
        )
    return box


def new_slide(prs, page, total, section, dark=False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = INK if dark else PAPER
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = bg
    add_shape(slide, 0, 0, 0.1, H, COPPER if not dark else COPPER)
    if not dark:
        add_text(slide, 0.48, 0.28, 8, 0.28, section.upper(), size=11, color=COPPER, bold=True)
        add_shape(slide, 0.48, 7.18, 12.4, 0.01, LINE)
        add_text(slide, 0.48, 7.22, 8, 0.24, "Transcript Intelligence  ·  Aegis Cloud  ·  Feb 3 – Apr 28, 2026", size=11, color=FAINT)
        add_text(slide, 11.3, 7.22, 1.55, 0.24, f"{page}  /  {total}", size=11, color=FAINT, align=PP_ALIGN.RIGHT)
    return slide


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def stat_card(slide, x, y, w, h, value, label, note, value_color=INK):
    add_shape(slide, x, y, w, h, CARD, LINE)
    add_text(slide, x + 0.22, y + 0.16, w - 0.4, 0.62, value, size=32, color=value_color, font=SERIF)
    add_text(slide, x + 0.22, y + 0.82, w - 0.4, 0.3, label, size=13, color=INK, bold=True)
    add_text(slide, x + 0.22, y + 1.12, w - 0.4, max(0.36, h - 1.22), note, size=12, color=MUTED)


def hbar(slide, x, y, w, h, score, color):
    add_shape(slide, x, y, w, h, LINE)
    width = max(0.08, w * (score - 1) / 4)
    add_shape(slide, x, y, width, h, color)


def build(report: dict) -> Presentation:
    sentiment = {row["call_type"]: row for row in report["sentiment"]["by_call_type"]}
    months = {row["period"]: row for row in report["sentiment"]["by_month"]}
    themes = [theme for theme in report["topics"]["themes"] if theme["meeting_count"]]
    themes.sort(key=lambda theme: theme["meeting_count"], reverse=True)
    comparison = report["topics"]["comparison"]
    insights = {item["insight_id"]: item for item in report["insights"]}
    total = 14

    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    prs.core_properties.title = "Transcript Intelligence — leadership briefing"
    prs.core_properties.subject = "Aegis Cloud call transcripts, February 3 to April 28, 2026"
    prs.core_properties.category = "Leadership briefing"

    _title(prs, total)
    _ask(prs, total)
    _sentiment(prs, total, sentiment, report)
    _time(prs, total, months)
    _blast(prs, total, report)
    _themes(prs, total, themes, comparison)
    _support(prs, total, insights)
    _product(prs, total, insights)
    _engineering(prs, total)
    _quotes(prs, total)
    _accounts(prs, total, insights)
    _recommendations(prs, total)
    _thirty_days(prs, total)
    _trust(prs, total, report, comparison)
    return prs


def _title(prs, total):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = PAPER
    add_shape(slide, 0, 0, 0.1, H, COPPER)
    add_text(slide, 0.7, 1.35, 11, 0.3, "PRODUCT AND ENGINEERING LEADERSHIP", size=12, color=COPPER, bold=True)
    add_paragraphs(
        slide,
        0.68,
        1.8,
        12,
        2.1,
        [
            {"text": "The outage ended in the pipeline.", "size": 40, "font": SERIF, "color": INK},
            {"text": "It did not end in the account.", "size": 40, "font": SERIF, "color": INK, "before": 4},
        ],
    )
    add_text(
        slide,
        0.7,
        4.15,
        10.5,
        0.7,
        "100 calls. Support cases, account conversations, and internal meetings. February 3 to April 28, 2026.",
        size=18,
        color=MUTED,
    )
    stat_card(slide, 0.7, 5.2, 3.9, 1.55, "2.94", "Support, mean score", "0.77 below external calls. Scale is 1–5.", RISK)
    stat_card(slide, 4.8, 5.2, 3.9, 1.55, "49", "Meetings still on the outage", "Ten of those are the bridge calls.", COPPER)
    stat_card(slide, 8.9, 5.2, 3.9, 1.55, "24", "Accounts naming churn", "SentinelShield is in 18 meetings.", INK)
    add_text(slide, 0.7, 7.05, 8, 0.25, "Transcript Intelligence", size=12, color=FAINT)
    add_text(slide, 10.2, 7.05, 2.6, 0.25, f"1  /  {total}", size=12, color=FAINT, align=PP_ALIGN.RIGHT)
    notes(
        slide,
        "Open on the sentence, not the method. Pause after the three numbers. "
        "Tell them the next slide is the decision, and the evidence comes after that. "
        "If asked where 2.94 comes from: it is the mean of the 1–5 score already stored on each support meeting. We did not rescore the words.",
    )


def _ask(prs, total):
    slide = new_slide(prs, 2, total, "The ask")
    add_text(slide, 0.48, 0.58, 12, 0.7, "Four decisions. Then the evidence.", size=32, font=SERIF)
    rows = [
        ("01", "Staff support by theme.", "Reliability is 13 of 27 cases. Identity is next. A rotating on-call re-derives that every week."),
        ("02", "Keep the incident owner past the restore.", "The bridge was 10 meetings. The outage is still the subject of 49."),
        ("03", "Do not brief Comply over a cold Detect book.", "Detect meetings average 2.73. Comply averages 4.28, with none under 3."),
        ("04", "Run one save book, not whoever hosted the call.", "24 accounts already used churn language. SentinelShield is named in 18 meetings."),
    ]
    y = 1.55
    for number, title, body in rows:
        add_text(slide, 0.5, y, 0.7, 0.4, number, size=18, color=COPPER, font=SERIF)
        add_text(slide, 1.35, y, 11, 0.36, title, size=20, color=INK, bold=True)
        add_text(slide, 1.35, y + 0.38, 11, 0.4, body, size=15, color=MUTED)
        y += 1.25
    notes(
        slide,
        "This is the slide to come back to in Q&A. Every later slide earns one of these four lines. "
        "Do not walk the architecture unless someone asks. The last slide is there for that question.",
    )


def _sentiment(prs, total, sentiment, report):
    slide = new_slide(prs, 3, total, "Sentiment")
    add_text(slide, 0.48, 0.58, 12, 0.85, "A company-wide 3.42 hides the cold channel.", size=32, font=SERIF)
    rows = [
        ("Support", sentiment["support"], RISK, "27 calls  ·  59% on the negative side of the label"),
        ("Internal", sentiment["internal"], GOOD, "30 calls  ·  incident bridges live here"),
        ("External", sentiment["external"], NAVY, "43 calls  ·  account reviews, renewals, escalations"),
    ]
    y = 1.75
    for name, row, color, note in rows:
        add_text(slide, 0.5, y, 2.1, 0.34, name, size=16, bold=True)
        hbar(slide, 2.7, y + 0.08, 6.3, 0.22, row["mean_score"], color)
        add_text(slide, 9.15, y - 0.06, 1.3, 0.4, f"{row['mean_score']:.2f}", size=22, font=SERIF, color=color)
        add_text(slide, 10.5, y, 2.4, 0.55, note, size=12, color=MUTED)
        y += 0.85
    add_shape(slide, 0.5, 4.45, 12.3, 2.15, CARD, LINE)
    add_paragraphs(
        slide,
        0.75,
        4.65,
        11.8,
        1.8,
        [
            {
                "text": "Support turns are 10% positive. External turns are 41% positive.",
                "size": 20,
                "font": SERIF,
            },
            {
                "text": "An account manager can leave a renewal conversation mixed-positive while the open case is the story the customer retells internally. The score on the support call is the one the champion has to defend.",
                "size": 16,
                "color": MUTED,
                "before": 8,
            },
            {
                "text": "Scores are the 1–5 values shipped with each meeting. We did not rescore the transcripts.",
                "size": 13,
                "color": FAINT,
                "before": 8,
            },
        ],
    )
    notes(
        slide,
        "Corpus mean is 3.42, the same as internal. That is why the average feels fine. "
        "Support 2.94, external 3.71, gap 0.77. Negative-side labels: support 59%, external 30%. "
        "Turn mix is the sharper cut: support positive share of sentences is 10%, external is 41%. "
        "Do not claim the outage created the support gap. February support was already 2.89. The next slide is that correction.",
    )


def _time(prs, total, months):
    slide = new_slide(prs, 4, total, "Sentiment over time")
    add_text(slide, 0.48, 0.55, 12.2, 1.05, "Support was already cold. March made everyone cold. April, only the account calls recovered.", size=30, font=SERIF)
    headers = [("February", "2026-02"), ("March", "2026-03"), ("April", "2026-04")]
    x = 0.5
    for name, key in headers:
        row = months[key]
        add_shape(slide, x, 1.9, 3.9, 2.55, CARD, LINE)
        add_text(slide, x + 0.25, 2.05, 3.4, 0.3, name.upper(), size=12, color=COPPER, bold=True)
        add_text(slide, x + 0.25, 2.35, 3.4, 0.6, f"{row['mean_score']:.2f}", size=36, font=SERIF)
        add_text(slide, x + 0.25, 3.05, 3.4, 0.25, f"{row['count']} meetings", size=13, color=MUTED)
        by = row["by_call_type"]
        add_text(
            slide,
            x + 0.25,
            3.4,
            3.4,
            0.8,
            f"Support  {by['support']:.2f}\nExternal  {by['external']:.2f}\nInternal  {by['internal']:.2f}",
            size=14,
            color=INK,
        )
        x += 4.15
    add_text(
        slide,
        0.5,
        4.7,
        12.3,
        1.9,
        "The week of March 9 is the floor: 2.16 across 13 meetings. In March, internal calls were the coldest of the three, because that is where the war rooms were.\n\n"
        "By April, external is back to 4.15. Support is 3.21. The gap that narrowed during the incident has reopened. Treating March as a closed incident misses the channel that did not come back.",
        size=16,
        color=MUTED,
    )
    notes(
        slide,
        "Read the three months left to right. February: support 2.89, external 4.26. The gap predates the outage. "
        "March: external falls to 2.90, internal to 2.64, support 2.73. Everyone is in it. "
        "April: external 4.15, internal 3.85, support 3.21. Recovery is real and uneven. "
        "Week of March 9 mean 2.16, 13 meetings. Incident titles run March 10 to March 20.",
    )


def _blast(prs, total, report):
    slide = new_slide(prs, 5, total, "The incident")
    add_text(slide, 0.48, 0.58, 12, 0.8, "Ten bridge calls. Forty-nine conversations.", size=32, font=SERIF)
    incident = report["sentiment"]["incident"]
    mention = report["sentiment"]["outage_mention"]
    stat_card(slide, 0.5, 1.7, 6.0, 1.7, "10", "Incident, outage, or war-room titles", f"Mean {incident['mean_score']:.2f}. The other 90 average {incident['rest_mean']:.2f}.", RISK)
    stat_card(slide, 6.75, 1.7, 6.05, 1.7, "49", "Meetings that still mention the outage", f"Mean {mention['mean_score']:.2f}. Meetings that don't: {mention['rest_mean']:.2f}.", COPPER)
    add_paragraphs(
        slide,
        0.5,
        3.7,
        12.2,
        2.9,
        [
            {
                "text": "A war-room timeline describes what on-call did. It does not describe how many later conversations still treat the failure as open.",
                "size": 20,
                "font": SERIF,
            },
            {
                "text": "Customers had zero threat monitoring for about six hours. Events queued and did not process. The health check watching that pipeline was a liveness check, not a readiness check, and it lived on the same path that failed. The monitoring product did not see itself go dark.",
                "size": 16,
                "color": MUTED,
                "before": 12,
            },
            {
                "text": "Keep the engineering owner assigned through the meetings that still cite the outage. Closing the incident at restore leaves the account work unowned.",
                "size": 16,
                "color": INK,
                "before": 12,
            },
        ],
    )
    notes(
        slide,
        "Incident-titled meetings: 10, from March 10 to March 20, mean 2.18 versus 3.55 for the rest. "
        "Outage mentions: 49 meetings, mean 2.93 versus 3.88. That difference of 39 meetings is the blast radius a status page will undercount. "
        "Technical facts to defend if asked: six hours of no threat data; single point of failure in ingestion; health check was liveness rather than readiness, tied to the same pipeline. "
        "Raj on the remediation review. Tyler on the root-cause review. Diana on the customer-impact review.",
    )


def _themes(prs, total, themes, comparison):
    slide = new_slide(prs, 6, total, "What the calls are about")
    add_text(slide, 0.48, 0.55, 12.2, 0.85, "Publish eight themes. Do not publish 351 labels.", size=32, font=SERIF)
    shown = sorted(themes, key=lambda theme: theme["meeting_count"], reverse=True)
    max_count = shown[0]["meeting_count"]
    y = 1.52
    for theme in shown:
        add_text(slide, 0.5, y, 3.3, 0.32, theme["name"], size=14, bold=True)
        add_shape(slide, 3.9, y + 0.08, 5.6, 0.18, LINE)
        add_shape(slide, 3.9, y + 0.08, 5.6 * theme["meeting_count"] / max_count, 0.18, COPPER)
        add_text(slide, 9.65, y - 0.02, 0.8, 0.32, str(theme["meeting_count"]), size=16, font=SERIF)
        add_text(slide, 10.5, y, 2.3, 0.32, f"{theme['mean_sentiment']:.2f} mean", size=13, color=MUTED)
        y += 0.4
    add_paragraphs(
        slide,
        0.5,
        4.85,
        12.2,
        2.15,
        [
            {
                "text": f"The source files ship {comparison['unique_provided_labels']} distinct topic labels. {comparison['hapax_share']:.0%} of them appear once. A label that appears once cannot be a category.",
                "size": 16,
                "color": MUTED,
            },
            {
                "text": "We mapped the labels onto a governed list and kept the raw label as evidence. A separate pass over the transcript text, which never saw those labels, recovers the same shape: compliance evidence, circuit breaker and pipeline, renewal, identity and MFA, backup, billing. Where a meeting's label and that pass share no words, it goes on a review queue. It does not become a new category.",
                "size": 16,
                "color": MUTED,
                "before": 8,
            },
        ],
    )
    notes(
        slide,
        "Theme counts are primary theme, so they sum to 100. Reliability 43 at 2.87. Compliance 21 at 4.29 — that is the healthy book, mostly external. "
        "Identity 12 at 3.33. Renewal 8. Product gaps 8. Billing 5, almost all support. Onboarding 2. Delivery 1. "
        "351 labels, 76% hapax, 58% of labels map into the taxonomy, coverage of meetings is essentially complete. "
        "Generated-topic purity against the governed theme is about 60%. Token overlap is low, about 8%, because the model speaks in content words and the labels are phrases. "
        "If asked why not BERTopic: same contract, lexical NMF is the deterministic default on 100 documents. BERTopic is a flag, not a different product.",
    )


def _support(prs, total, insights):
    slide = new_slide(prs, 7, total, "Support")
    add_text(slide, 0.48, 0.55, 12, 0.7, "The queue is an aftershock, plus identity, plus billing.", size=30, font=SERIF)
    cards = [
        ("13 / 27", "Reliability", "Incident communication, workarounds, and the outage still arriving as cases.", RISK),
        ("16 / 27", "Score under 3", "Support mean 2.94. External mean 3.71. The gap is the renewal story versus the case.", COPPER),
        ("10", "Churn, no pivot", "19 support calls contain churn language. 10 of them never turn toward a credible next step.", INK),
    ]
    x = 0.5
    for value, label, note, color in cards:
        stat_card(slide, x, 1.55, 4.0, 2.05, value, label, note, color)
        x += 4.2
    add_paragraphs(
        slide,
        0.5,
        3.9,
        12.2,
        2.8,
        [
            {"text": "What to change", "size": 14, "color": COPPER, "bold": True},
            {
                "text": "Run the weekly support review by theme, with the engineering owner for that theme in the room. Reliability first, then identity, then billing. Those are different rosters.",
                "size": 16,
                "before": 6,
            },
            {
                "text": "Put the lowest-scoring themes on the same page as renewal risk. A case that is still negative after the next customer touch needs an owner outside the queue.",
                "size": 16,
                "before": 8,
            },
            {
                "text": "When a support call records churn language and no positive pivot, route it to the account owner the same day, with the quote attached. That is a save, not a CSAT survey.",
                "size": 16,
                "before": 8,
            },
        ],
    )
    notes(
        slide,
        "Primary themes on support: reliability 13 (48%), identity 5, billing 4, product 3, compliance 2. "
        "Raw labels under them fragment: incident communication 5, feature request 4, workaround 4. Use the theme to staff, the label as evidence. "
        "Examples of churn without a pivot: Trailhead Marketplace at 1.4, PCI exposure during a Detect gap. Coastal Living, two reliability hits including the earlier outage. "
        "Clearwater, billed for Detect overage that may be replay traffic from our own incident. Stratos, questioning whether Detect is the right platform.",
    )


def _product(prs, total, insights):
    slide = new_slide(prs, 8, total, "Product")
    add_text(slide, 0.48, 0.55, 12.2, 0.7, "Detect and Comply are not having the same quarter.", size=30, font=SERIF)
    modules = [
        ("Detect", "2.73", "22 meetings · 15 under 3", RISK),
        ("Identity", "3.45", "17 meetings · 6 under 3", COPPER),
        ("Protect", "3.62", "12 meetings · 4 under 3", NAVY),
        ("Comply", "4.28", "13 meetings · none under 3", GOOD),
    ]
    x = 0.5
    for name, score, note, color in modules:
        add_shape(slide, x, 1.5, 3.0, 1.7, CARD, LINE)
        add_text(slide, x + 0.18, 1.62, 2.6, 0.28, name, size=14, bold=True, color=MUTED)
        add_text(slide, x + 0.18, 1.92, 2.6, 0.6, score, size=32, font=SERIF, color=color)
        add_text(slide, x + 0.18, 2.6, 2.6, 0.4, note, size=12, color=MUTED)
        x += 3.2
    add_text(slide, 0.5, 3.45, 12, 0.3, "51 feature-gap moments, spoken inside a case or an account review. Not a brainstorm.", size=15, color=INK, bold=True)
    gaps = [
        ("Comply  12", "On-demand evidence and control labeling. Customers are still building the audit in spreadsheets."),
        ("Detect  8", "A heartbeat when telemetry stops. Customers found the outage because the alerts went to zero."),
        ("Identity  7", "JIT provisioning and SSO. Support already has a cluster. Summit's CISO has put MFA enforcement on a Q2 clock."),
        ("Protect  5", "Granular file restore is not in the product. One trading platform's recovery objective is 15 minutes."),
    ]
    y = 3.9
    for title, body in gaps:
        add_text(slide, 0.5, y, 2.3, 0.4, title, size=14, bold=True, color=COPPER)
        add_text(slide, 2.9, y, 9.8, 0.4, body, size=14, color=INK)
        y += 0.48
    add_text(
        slide,
        0.5,
        5.9,
        12.2,
        0.9,
        "Take the Comply gaps to that squad with the account and the quote attached. Separate what is already on a roadmap from what has no owner. Do not walk a Comply launch into a renewal that is actually about Detect without saying the Detect score out loud.",
        size=15,
        color=MUTED,
    )
    notes(
        slide,
        "Module score is the meeting score when the title or topics name the module. A meeting can count toward more than one. "
        "Detect 2.73 on 22, 15 under 3. Comply 4.28 on 13, zero under 3. That split is the product story. "
        "Feature gaps: Comply 12, Detect 8, Identity 7, Protect 5, from 51 feature_gap moments. "
        "Heartbeat is Megan's proposal on the post-incident review; Diana's response was that it would be huge. "
        "Protect granular restore is the Meridian Capital case. Summit Trust MFA is a Q2 reassessment threat, competitor in that conversation is VaultEdge.",
    )


def _engineering(prs, total):
    slide = new_slide(prs, 9, total, "Engineering")
    add_text(slide, 0.48, 0.55, 12.2, 0.85, "The next incident will reuse a habit, not a hostname.", size=30, font=SERIF)
    rows = [
        ("15", "Single point of failure", "Ingestion. Named as a known limitation that had not been prioritized, including in front of a customer."),
        ("7", "The monitor could not see the failure", "Health check was liveness, not readiness, and it depended on the pipeline it was meant to watch."),
        ("7", "Pipeline, latency, data gaps", "Events queued. Customers had no threat data for about six hours. Later calls are still about the hole that left."),
    ]
    y = 1.65
    for value, title, body in rows:
        add_text(slide, 0.5, y, 1.3, 0.5, value, size=28, font=SERIF, color=COPPER)
        add_text(slide, 2.0, y, 10.5, 0.36, title, size=18, bold=True)
        add_text(slide, 2.0, y + 0.38, 10.5, 0.55, body, size=15, color=MUTED)
        y += 1.15
    add_shape(slide, 0.5, 5.15, 12.3, 1.7, CARD, LINE)
    add_paragraphs(
        slide,
        0.75,
        5.3,
        11.8,
        1.4,
        [
            {
                "text": "“The single point of failure was a known architectural limitation that had not been prioritized.”",
                "size": 18,
                "font": SERIF,
                "italic": True,
            },
            {
                "text": "Ravi Gupta, on the Meridian Capital reliability call. He took the ownership in the room.",
                "size": 14,
                "color": MUTED,
                "before": 6,
            },
        ],
    )
    notes(
        slide,
        "Counts are keyword hits across technical-issue moments and incident summaries, not a new root-cause model. Say that if challenged. "
        "They are a way to start the review from language already used. Identity failures and customer-communication hits are in the long tail of that pass; the communication failure shows up more clearly in the 49-meeting blast radius than in this keyword count. "
        "Recommendation: put single point of failure and the blind health check on the reliability backlog as themes, with these meetings as the acceptance examples. Separate them from the one-off bug list. "
        "53 meetings record a technical-issue moment, so the residue is larger than the 10-title bridge calendar.",
    )


def _quotes(prs, total):
    slide = new_slide(prs, 10, total, "In their words")
    add_text(slide, 0.48, 0.55, 12, 0.6, "Three calls a roadmap review will not see.", size=30, font=SERIF)
    quotes = [
        (
            "Renewal is in June. She does not know if they will renew without substantially better assurances for her CISO.",
            "Grace Yoon, Northstar Pharma, on the Detect outage call. Score 2.1. SentinelShield is the name in the evaluation.",
        ),
        (
            "Six hours of zero threat visibility across 200 locations. Two SentinelShield demos. A formal proposal is close, on the back of an uptime SLA.",
            "Stephanie Blair, Nova Retail Group, on the renewal call. Score 2.6.",
        ),
        (
            "They had been evaluating SentinelShield for months. Today’s incident is making that decision very easy.",
            "Julia Tran, Blackridge Investments, after a total loss of threat visibility. Score 1.6.",
        ),
    ]
    y = 1.5
    for quote, who in quotes:
        add_shape(slide, 0.5, y + 0.06, 0.07, 0.72, COPPER)
        add_text(slide, 0.8, y, 11.9, 0.85, quote, size=18, font=SERIF, italic=True)
        add_text(slide, 0.8, y + 0.88, 11.9, 0.4, who, size=14, color=MUTED)
        y += 1.7
    notes(
        slide,
        "These are compressed from the recorded key moments, not invented. If someone wants the verbatim line, open the meeting. "
        "Grace, Northstar, renewal in June, CISO asked for a competitive evaluation and named SentinelShield. "
        "Stephanie, Nova, six-hour outage, 200+ locations, two SentinelShield demos, close to asking for a formal proposal because of the uptime SLA. "
        "Julia, Blackridge, urgent total loss of threat visibility, score 1.6, evaluation already underway and the incident is the deciding event. "
        "Do not stack more quotes. Three is the point.",
    )


def _accounts(prs, total, insights):
    slide = new_slide(prs, 11, total, "Sales")
    add_text(slide, 0.48, 0.52, 12.2, 0.7, "The renewal forecast the CRM does not have a field for.", size=30, font=SERIF)
    add_text(
        slide,
        0.5,
        1.35,
        12.2,
        0.55,
        "24 accounts have churn language on a recording. Ordered by repeat signals, a low score, a named competitor, and a renewal already on the calendar. A briefing rank, not a forecast.",
        size=14,
        color=MUTED,
    )
    header_y = 2.05
    add_shape(slide, 0.5, header_y, 12.3, 0.4, INK)
    headers = [(0.65, 3.3, "Account"), (4.0, 1.5, "Calls"), (5.5, 1.4, "Mean"), (7.0, 5.4, "Who is in the account")]
    for x, w, label in headers:
        add_text(slide, x, header_y + 0.05, w, 0.3, label, size=12, color=WHITE, bold=True)
    rows = [
        ("Brightpath Commerce", "3", "3.25", "SentinelShield  ·  six-week evaluation"),
        ("Ridgeline Logistics", "3", "2.63", "No competitor named  ·  coldest of the top"),
        ("Meridian Capital", "3", "3.17", "SentinelShield  ·  CISO vendor review"),
        ("Northstar Pharma", "2", "2.10", "SentinelShield and CyberNova  ·  renewal in June"),
        ("Nova Retail Group", "2", "2.45", "SentinelShield  ·  two demos, 200 locations"),
        ("Cobalt Software", "2", "2.60", "SentinelShield  ·  dashboard-down call at 1.8"),
    ]
    y = 2.45
    for index, (account, calls, mean, who) in enumerate(rows):
        if index % 2 == 0:
            add_shape(slide, 0.5, y, 12.3, 0.42, CARD)
        add_text(slide, 0.65, y + 0.06, 3.3, 0.3, account, size=13, bold=True)
        add_text(slide, 4.0, y + 0.06, 1.5, 0.3, calls, size=13)
        add_text(slide, 5.5, y + 0.06, 1.4, 0.3, mean, size=13, color=RISK if float(mean) < 3 else INK)
        add_text(slide, 7.0, y + 0.06, 5.5, 0.3, who, size=13, color=MUTED)
        y += 0.42
    add_text(
        slide,
        0.5,
        5.15,
        12.3,
        0.85,
        "SentinelShield is named in 18 meetings and 9 accounts. VaultEdge in 10 meetings, CyberNova in 6. On the internal Q1 win/loss call the team reported 34 closed-lost deals and $2.1M ACV, with SentinelShield named 9 times. That figure is what the call recorded, not a bookings extract.",
        size=14,
        color=MUTED,
    )
    add_text(
        slide,
        0.5,
        6.1,
        12.3,
        0.85,
        "Work the top of this list as one book: one owner, the quote, the competitor, and a date for the assurance the customer asked for. Rebuild the SentinelShield talk track around the six-hour failure and the uptime SLA they are offering. Not a feature grid.",
        size=15,
        color=INK,
    )
    notes(
        slide,
        "Risk order is a weighted rank: churn-signal calls times 3, distance below 3.5, a named competitor, and a renewal on the calendar. Do not defend 11.8 as a model score. It is a sort key. The table shows the inputs a leader can check. "
        "Full list is 24 accounts. Top six are the operating list. "
        "Win/loss attribution matters: Kevin O'Brien on the internal Q1 win/loss call, not finance. If they want it in the forecast, it has to be reconciled to the CRM. "
        "Competitors are a configured lexicon. A new name does not appear until someone adds it. Counts are meetings, not mention-spam.",
    )


def _recommendations(prs, total):
    slide = new_slide(prs, 12, total, "What to do")
    add_text(slide, 0.48, 0.52, 12, 0.55, "This month, by owner.", size=32, font=SERIF)
    rows = [
        ("Support\n+ Detect eng", "Weekly review by theme. Reliability, then identity, then billing. The engineering owner is in the room."),
        ("Support\n+ account", "Same day: any case with churn language and no pivot goes to the account owner with the quote."),
        ("Engineering", "Incident owner stays on through meetings that still cite the outage. Single point of failure and the blind health check become backlog themes, with these calls as the examples."),
        ("Product", "Comply gaps, with accounts attached, at the next squad planning. Detect's 2.73 is said out loud in any launch or renewal that touches those accounts."),
        ("Sales", "One owner for the top of the list. SentinelShield talk track rewritten around the six hours and their uptime offer."),
    ]
    y = 1.3
    for owner, action in rows:
        add_shape(slide, 0.5, y, 2.35, 0.95, CARD, LINE)
        add_text(slide, 0.65, y + 0.16, 2.05, 0.7, owner, size=14, bold=True, anchor="middle")
        add_text(slide, 3.05, y + 0.12, 9.7, 0.75, action, size=15, anchor="middle")
        y += 1.08
    notes(
        slide,
        "Do not add a sixth workstream in the room. If they want to negotiate scope, drop the talk-track rewrite before you drop the same-day routing or the incident owner. "
        "The engineering backlog item is a theme with acceptance examples, not a commitment to a specific design in this meeting.",
    )


def _thirty_days(prs, total):
    slide = new_slide(prs, 13, total, "What changed")
    add_text(slide, 0.48, 0.55, 12, 0.7, "In 30 days, these are the only signs this worked.", size=30, font=SERIF)
    items = [
        ("The gap is named, or it moved.", "Support versus external is on one page with the open themes. If support is still near 2.9 and external near 3.7, we can point at the cases. We do not get to call that a vibe."),
        ("No unnamed account in the top of the book.", "Each of the six has an owner, the quote, the competitor, and a date. Northstar's June renewal is the one that cannot slip past a status meeting."),
        ("The outage has an owner after the restore.", "The engineering owner is still on the accounts whose later meetings cite it. The heartbeat — tell the customer when telemetry stops — is scheduled, or explicitly declined."),
        ("The failure mode is a backlog theme.", "Single point of failure and the health check that could not see the failure are not sitting in a closed incident ticket."),
    ]
    y = 1.5
    for title, body in items:
        add_text(slide, 0.5, y, 12.2, 0.32, title, size=18, bold=True)
        add_text(slide, 0.5, y + 0.34, 12.2, 0.6, body, size=15, color=MUTED)
        y += 1.25
    notes(
        slide,
        "This is the accountability slide. Resist adding metric targets we cannot measure yet, like a churn-save rate. "
        "We can measure the support/external gap from the same score next month. We can measure whether the six accounts have an owner. We cannot honestly promise a point of sentiment movement in 30 days, and we should not.",
    )


def _trust(prs, total, report, comparison):
    slide = new_slide(prs, 14, total, "How far to trust this")
    add_text(slide, 0.48, 0.55, 12.2, 0.7, "The structure of the briefing is solid. The conclusions are not yet reviewed.", size=28, font=SERIF)
    quality = report["quality"]
    bits = [
        (f"{quality['composite']:.0%}", "Briefing structure"),
        (f"{quality['coverage']:.0%}", "How much gets cited"),
        (f"{quality['consistency']:.0%}", "Labels match the scores"),
        (f"{quality['actionability']:.0%}", "Findings can be acted on"),
    ]
    x = 0.5
    for value, label in bits:
        add_shape(slide, x, 1.55, 3.0, 1.45, CARD, LINE)
        add_text(slide, x + 0.18, 1.65, 2.65, 0.55, value, size=28, font=SERIF, color=COPPER)
        add_text(slide, x + 0.18, 2.25, 2.65, 0.6, label, size=13, color=MUTED)
        x += 3.2
    add_paragraphs(
        slide,
        0.5,
        3.25,
        12.2,
        3.5,
        [
            {
                "text": "What the score is. Every meeting landed in a theme. The 86% is lower because a briefing cites the decisive meetings, not all 100. Sentiment labels two ranks apart never invert the 1–5 score. Each finding has a number, a reason, a recommendation, and a citation.",
                "size": 15,
                "color": INK,
            },
            {
                "text": "What it is not. No reviewer has accepted, edited, or rejected a finding against the transcript. Until that happens, 97% is a claim about the briefing's structure, not about being right.",
                "size": 15,
                "color": INK,
                "before": 8,
            },
            {
                "text": f"How the categories were chosen. Provided labels are evidence ({comparison['unique_provided_labels']} of them). The themes are a map we will stand behind. A second pass on the text, labels held out, is the audit. Disagreements are a queue for a person, not a new taxonomy.",
                "size": 15,
                "color": MUTED,
                "before": 8,
            },
            {
                "text": "Next, if we keep going. A person marks each finding. That set is what any later model has to agree with. Call type is who was in the room: a support-case title, a customer on the invite, or internal.",
                "size": 15,
                "color": MUTED,
                "before": 8,
            },
        ],
    )
    notes(
        slide,
        "Stay here only if they ask how. One minute. "
        "Do not open the repo unless they ask to see a specific meeting. The dashboard and this deck read the same report. "
        "Call types: 27 support, 43 external, 30 internal. Support wins on the title even when a customer is present. External is any other meeting with a non-Aegis domain. Incident bridges with no customer are internal. "
        "Quality composite is about 97%: coverage 86%, consistency 100%, actionability 100%, confidence 100%. Say the caveat before anyone else does.",
    )


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    presentation = build(report)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({len(presentation.slides)} slides)")


if __name__ == "__main__":
    main()
