"""Deterministic review samples.

The representative sample is a stratified draw from every meeting.
The challenging sample is the existing review queue, kept separate so its
accuracy is not treated as the accuracy of the book.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from src.review.schema import CALL_TYPE_ORDER, SAMPLE_SEED, SAMPLE_TARGET, THEME_IDS, THEME_NAMES


def allocate_theme_seats(counts: dict[str, int], target: int, order: tuple[str, ...] = THEME_IDS) -> dict[str, int]:
    """Reserve one seat per theme that has meetings, then give the rest by largest remainder.

    Ties on the fractional part follow the taxonomy order, which is stable.
    """

    present = [theme_id for theme_id in order if counts.get(theme_id, 0) > 0]
    total = sum(counts[theme_id] for theme_id in present)
    seats = min(target, total)
    if seats <= 0 or not present:
        return {}
    if seats >= total:
        return {theme_id: counts[theme_id] for theme_id in present}
    if seats < len(present):
        ranked = sorted(present, key=lambda theme_id: (-counts[theme_id], order.index(theme_id)))
        return {theme_id: 1 for theme_id in ranked[:seats]}
    extra = _largest_remainder(
        {theme_id: counts[theme_id] - 1 for theme_id in present},
        seats - len(present),
        present,
    )
    return {theme_id: min(counts[theme_id], 1 + extra.get(theme_id, 0)) for theme_id in present}


def build_review_sample(
    meetings: list[dict],
    queue: dict | None = None,
    *,
    seed: int = SAMPLE_SEED,
    target: int = SAMPLE_TARGET,
) -> dict:
    """Build the representative draw and the separate challenging-case list.

    `meetings` is the public report list: meeting_id, call_type, primary_theme.
    """

    population = [meeting for meeting in meetings if meeting.get("meeting_id") and meeting.get("primary_theme") in THEME_IDS]
    counts: dict[str, int] = {theme_id: 0 for theme_id in THEME_IDS}
    for meeting in population:
        counts[meeting["primary_theme"]] += 1
    allocation = allocate_theme_seats(counts, target)
    grouped: dict[tuple[str, str], list[str]] = {}
    for meeting in population:
        key = (meeting["primary_theme"], _call_type(meeting.get("call_type")))
        grouped.setdefault(key, []).append(meeting["meeting_id"])

    strata: list[dict] = []
    chosen: dict[str, dict] = {}
    for theme_id, seats in allocation.items():
        type_counts = {
            call_type: len(grouped.get((theme_id, call_type), []))
            for call_type in _call_order(grouped, theme_id)
        }
        type_seats = _largest_remainder(type_counts, seats, list(type_counts))
        for call_type, take in type_seats.items():
            members = sorted(grouped.get((theme_id, call_type), []))
            if take <= 0 or not members:
                continue
            picked = _choose(members, take, seed, theme_id, call_type)
            probability = take / len(members)
            strata.append(
                {
                    "theme": theme_id,
                    "theme_name": THEME_NAMES.get(theme_id, theme_id),
                    "call_type": call_type,
                    "population": len(members),
                    "sampled": len(picked),
                    "selection_probability": round(probability, 6),
                }
            )
            for meeting_id in picked:
                chosen[meeting_id] = {
                    "item_id": f"meeting:{meeting_id}",
                    "meeting_id": meeting_id,
                    "predicted_topic": theme_id,
                    "call_type": call_type,
                    "stratum_population": len(members),
                    "stratum_sampled": len(picked),
                "selection_probability": round(probability, 6),
                "sample_weight": round(len(members) / len(picked), 6),
                "stratum_basis": "predicted_primary_theme_and_call_type",
                "held_out_from_tuning": True,
            }

    chosen = _cover_call_types(chosen, grouped, seed)
    representative = [_record(item, "representative") for item in chosen.values()]
    representative.sort(key=lambda item: item["meeting_id"])

    challenging, overlap = _challenging_items(queue or {}, set(chosen))
    challenge_ids = {item["meeting_id"] for item in challenging}
    for item in representative:
        item["also_in_challenging"] = item["meeting_id"] in challenge_ids
    strata = _strata_from_chosen(representative)
    return {
        "version": 1,
        "seed": seed,
        "target": target,
        "task": "single_label",
        "taxonomy_version": "governed-themes-v1",
        "stratum_basis": "predicted_primary_theme_and_call_type",
        "held_out_from_tuning": True,
        "method": (
            "Representative sample: reserve one meeting for every predicted governed theme that occurs, "
            "then allocate the remaining seats by the largest-remainder method on (count - 1). "
            "Within a predicted theme, seats are split across support, external, and internal by the same method. "
            "These strata are the model's primary theme and the ingestion call type. They are not gold labels. "
            f"Meetings inside a stratum are drawn with random.Random seeded by {seed}, the theme, and the call type. "
            "Inclusion probability is stratum seats divided by stratum size. "
            "Corrected labels are not fed back into the topic model. "
            "Challenging cases are every meeting already on the review queue. "
            "That list is not a probability sample and is scored on its own."
        ),
        "population_meetings": len(population),
        "representative": {
            "role": "representative",
            "count": len(representative),
            "items": representative,
            "strata": strata,
            "coverage": _coverage(population, representative),
            "allocation": [
                {
                    "theme": theme_id,
                    "theme_name": THEME_NAMES.get(theme_id, theme_id),
                    "population": counts.get(theme_id, 0),
                    "sampled": sum(1 for item in representative if item["predicted_topic"] == theme_id),
                }
                for theme_id in THEME_IDS
                if counts.get(theme_id, 0)
            ],
        },
        "challenging": {
            "role": "challenging",
            "count": len(challenging),
            "bias": (
                "These meetings were queued because the theme margin was thin or the held-out topic shared no words "
                "with the supplied labels. Accuracy here is not the accuracy of a random meeting. "
                "Do not average it with the representative sample."
            ),
            "items": challenging,
        },
        "overlap_count": overlap,
        "pooling": (
            "Representative and challenging results are reported separately. "
            "A meeting can sit in both lists and still has one human decision. "
            "The two denominators are not added together."
        ),
    }


def write_review_sample(sample: dict, path: Path) -> None:
    from src.review.decisions import atomic_write_json

    atomic_write_json(path, sample)


def _largest_remainder(weights: dict[str, int], seats: int, order: list[str]) -> dict[str, int]:
    keys = [key for key in order if weights.get(key, 0) > 0]
    if seats <= 0 or not keys:
        return {key: 0 for key in order}
    total = sum(weights[key] for key in keys)
    seats = min(seats, total)
    if seats >= total:
        allocated = {key: weights.get(key, 0) for key in order}
        return allocated
    quotas = {key: seats * weights[key] / total for key in keys}
    allocated = {key: min(weights[key], math.floor(quotas[key])) for key in keys}
    left = seats - sum(allocated.values())
    ranked = sorted(
        keys,
        key=lambda key: (-(quotas[key] - math.floor(quotas[key])), order.index(key) if key in order else 0),
    )
    for key in ranked:
        if left <= 0:
            break
        if allocated[key] < weights[key]:
            allocated[key] += 1
            left -= 1
    for key in order:
        allocated.setdefault(key, 0)
    return allocated


def _choose(members: list[str], take: int, seed: int, theme_id: str, call_type: str) -> list[str]:
    ordered = sorted(members)
    if take >= len(ordered):
        return ordered
    rng = random.Random(f"{seed}|{theme_id}|{call_type}")
    return sorted(rng.sample(ordered, take))


def _cover_call_types(
    chosen: dict[str, dict],
    grouped: dict[tuple[str, str], list[str]],
    seed: int,
) -> dict[str, dict]:
    """If a call type exists and received no seat, move one seat to it.

    The donor is the stratum that can spare a seat, largest sampled count first,
    then theme order. The meeting swapped in is the first id from that call type
    under the same seed, so the repair stays deterministic.
    """

    population_types = {call_type for (_, call_type) in grouped if grouped[(_, call_type)]}
    selected_types = {item["call_type"] for item in chosen.values()}
    for call_type in CALL_TYPE_ORDER:
        if call_type not in population_types or call_type in selected_types:
            continue
        donors = [
            item
            for item in chosen.values()
            if item["stratum_sampled"] >= 2 and item["call_type"] != call_type
        ]
        if not donors:
            continue
        donors.sort(key=lambda item: (-item["stratum_sampled"], THEME_IDS.index(item["predicted_topic"]) if item["predicted_topic"] in THEME_IDS else 99, item["meeting_id"]))
        donor = donors[0]
        recipients = []
        for theme_id in THEME_IDS:
            members = sorted(grouped.get((theme_id, call_type), []))
            if members:
                recipients.append((theme_id, members))
        if not recipients:
            continue
        # Prefer the donor's theme when that theme has this call type.
        recipients.sort(key=lambda pair: (pair[0] != donor["predicted_topic"], THEME_IDS.index(pair[0])))
        theme_id, members = recipients[0]
        already = {item["meeting_id"] for item in chosen.values()}
        available = [meeting_id for meeting_id in members if meeting_id not in already]
        if not available:
            continue
        picked = _choose(available, 1, seed, theme_id, call_type)[0]
        removed_id = donor["meeting_id"]
        removed = chosen.pop(removed_id)
        # Recompute probabilities for the donor stratum and the recipient stratum.
        _retarget_stratum(chosen, removed["predicted_topic"], removed["call_type"], -1)
        probability_pool = len(members)
        # sampled count for the recipient stratum after the add
        recipient_sampled = sum(
            1
            for item in chosen.values()
            if item["predicted_topic"] == theme_id and item["call_type"] == call_type
        ) + 1
        chosen[picked] = {
            "item_id": f"meeting:{picked}",
            "meeting_id": picked,
            "predicted_topic": theme_id,
            "call_type": call_type,
            "stratum_population": probability_pool,
            "stratum_sampled": recipient_sampled,
            "selection_probability": round(recipient_sampled / probability_pool, 6),
            "sample_weight": round(probability_pool / recipient_sampled, 6),
            "stratum_basis": "predicted_primary_theme_and_call_type",
            "held_out_from_tuning": True,
        }
        for item in chosen.values():
            if item["predicted_topic"] == theme_id and item["call_type"] == call_type:
                item["stratum_sampled"] = recipient_sampled
                item["selection_probability"] = round(recipient_sampled / probability_pool, 6)
                item["sample_weight"] = round(probability_pool / recipient_sampled, 6)
        selected_types.add(call_type)
    return chosen


def _retarget_stratum(chosen: dict[str, dict], theme_id: str, call_type: str, delta: int) -> None:
    members = [
        item
        for item in chosen.values()
        if item["predicted_topic"] == theme_id and item["call_type"] == call_type
    ]
    if not members:
        return
    population = members[0]["stratum_population"]
    sampled = max(0, members[0]["stratum_sampled"] + delta)
    for item in members:
        item["stratum_sampled"] = sampled
        if sampled <= 0 or population <= 0:
            item["selection_probability"] = 0.0
            item["sample_weight"] = 0.0
        else:
            item["selection_probability"] = round(sampled / population, 6)
            item["sample_weight"] = round(population / sampled, 6)


def _challenging_items(queue: dict, representative_ids: set[str]) -> tuple[list[dict], int]:
    items: list[dict] = []
    overlap = 0
    for row in queue.get("items", []):
        if row.get("item_type") != "meeting_classification":
            continue
        meeting_id = row.get("meeting_id") or ""
        if not meeting_id:
            continue
        if meeting_id in representative_ids:
            overlap += 1
        items.append(
            {
                "item_id": row.get("item_id") or f"meeting:{meeting_id}",
                "meeting_id": meeting_id,
                "predicted_topic": row.get("predicted_theme") or "",
                "call_type": row.get("call_type") or "",
                "reasons": list(row.get("reasons") or []),
                "selection_probability": None,
                "sample_weight": None,
                "sample_role": "challenging",
                "also_in_representative": meeting_id in representative_ids,
                "stratum_basis": "review_queue_not_a_probability_sample",
                "held_out_from_tuning": True,
            }
        )
    items.sort(key=lambda item: item["meeting_id"])
    return items, overlap


def _coverage(population: list[dict], representative: list[dict]) -> dict:
    def _block(key: str, order: list[str]) -> list[dict]:
        pop: dict[str, int] = {name: 0 for name in order}
        got: dict[str, int] = {name: 0 for name in order}
        for meeting in population:
            name = meeting.get(key) or ""
            if name in pop:
                pop[name] += 1
        for item in representative:
            name = item.get("predicted_topic") if key == "primary_theme" else item.get("call_type")
            if name in got:
                got[name] += 1
        rows = []
        for name in order:
            if pop[name] == 0 and got[name] == 0:
                continue
            rows.append(
                {
                    "name": name,
                    "label": THEME_NAMES.get(name, name),
                    "population": pop[name],
                    "sampled": got[name],
                    "fraction": round(got[name] / pop[name], 6) if pop[name] else None,
                }
            )
        return rows

    return {
        "by_theme": _block("primary_theme", list(THEME_IDS)),
        "by_call_type": _block("call_type", list(CALL_TYPE_ORDER)),
    }


def _strata_from_chosen(items: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item["predicted_topic"], item["call_type"])
        seen[key] = {
            "theme": item["predicted_topic"],
            "theme_name": THEME_NAMES.get(item["predicted_topic"], item["predicted_topic"]),
            "call_type": item["call_type"],
            "population": item["stratum_population"],
            "sampled": item["stratum_sampled"],
            "selection_probability": item["selection_probability"],
        }
    rows = list(seen.values())
    rows.sort(
        key=lambda row: (
            THEME_IDS.index(row["theme"]) if row["theme"] in THEME_IDS else 99,
            CALL_TYPE_ORDER.index(row["call_type"]) if row["call_type"] in CALL_TYPE_ORDER else 99,
        )
    )
    return rows


def _record(item: dict, role: str) -> dict:
    row = dict(item)
    row["sample_role"] = role
    row["also_in_challenging"] = False
    return row


def _call_type(value: str | None) -> str:
    name = (value or "").strip().lower()
    if name in CALL_TYPE_ORDER:
        return name
    return name or "internal"


def _call_order(grouped: dict[tuple[str, str], list[str]], theme_id: str) -> list[str]:
    present = [call_type for call_type in CALL_TYPE_ORDER if grouped.get((theme_id, call_type))]
    extras = sorted(
        call_type
        for (theme, call_type) in grouped
        if theme == theme_id and call_type not in CALL_TYPE_ORDER
    )
    return present + extras


def load_sample(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
