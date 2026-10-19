"""Code-level guards for the vendor-desk agent (Problem 6).

They check the model's answer in Python after it replies, so they still work if a document fools the model:
- every reported fact must appear in the document's visible text (tools.visible_text)
- the decision must match the handbook's four purchasing checks, computed here from the reported facts
- the reason may not contain links, email addresses, or phone numbers

The handbook (data/shop_handbook.md) stays the single source of the rules: the approved list, the removed
and pending list, the max unit costs, and the lead-time and minimum-order limits are all read from it.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from models import VendorReport
from tools import DATA_DIR

UNKNOWN_VENDOR = "unknown (vendor name not shown in the document)"
CONTACT = re.compile(r"https?://|www\.|[\w.+-]+@[\w-]+\.[\w.-]+|\b\d{3}[-.\s)]\s?\d{3}[-.\s]\d{4}\b")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Rules:
    approved: dict[str, str]  # normalized name -> name as written in the handbook
    blocked: dict[str, str]   # normalized name -> status (removed or pending)
    max_cost: dict[str, float]  # SKU -> max unit cost
    max_lead_days: int
    max_min_order: int


def norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def _table_rows(section: str) -> list[list[str]]:
    rows = [line.strip().strip("|").split("|") for line in section.splitlines() if line.lstrip().startswith("|")]
    return [[cell.strip() for cell in row] for row in rows[2:]]  # skip header and --- row


@lru_cache
def load_rules() -> Rules:
    text = (DATA_DIR / "shop_handbook.md").read_text(encoding="utf-8").replace("\r", "")
    sections = {m.group(1): m.group(2) for m in re.finditer(r"^## (\d+)\.[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)}
    return Rules(
        approved={norm(row[1]): row[1] for row in _table_rows(sections["5"])},
        blocked={norm(row[0]): row[1] for row in _table_rows(sections["6"])},
        max_cost={row[0]: float(row[4].lstrip("$").replace(",", "")) for row in _table_rows(sections["9"])},
        max_lead_days=int(re.search(r"lead time is (\d+) days or less", sections["4"]).group(1)),
        max_min_order=int(re.search(r"minimum order is (\d+) units or less", sections["4"]).group(1)),
    )


def decide(vendor: str, sku: str | None, unit_price: float | None,
           lead_time_days: int | None, min_order: int | None) -> tuple[str, str]:
    """The handbook section 4 decision and a one-sentence reason naming the check that decided it."""
    r = load_rules()
    no = "do_not_recommend"
    v = norm(vendor or "")
    if vendor == UNKNOWN_VENDOR or not v:
        return no, "Fails the approved-vendor check: the document does not show who the vendor is."
    if v in r.blocked:
        return no, f"Fails the approved-vendor check: {vendor} is on the handbook's removed or pending vendor list."
    if v not in r.approved:
        return no, f"Fails the approved-vendor check: {vendor} is not on the approved vendor list."
    if sku is None or unit_price is None:
        missing = "SKU" if sku is None else "unit price"
        return no, f"Fails the price check: the document does not state the {missing}."
    if sku not in r.max_cost:
        return no, f"Fails the price check: {sku} is not in the product catalogue, so there is no max unit cost."
    if unit_price > r.max_cost[sku]:
        return no, f"Fails the price check: ${unit_price:.2f} is above the ${r.max_cost[sku]:.2f} max unit cost for {sku}."
    if lead_time_days is None:
        return no, "Fails the lead-time check: the document does not state a lead time."
    if lead_time_days > r.max_lead_days:
        return no, f"Fails the lead-time check: {lead_time_days} days is more than the {r.max_lead_days}-day limit."
    if min_order is None:
        return no, "Fails the minimum-order check: the document does not state a minimum order."
    if min_order > r.max_min_order:
        return no, f"Fails the minimum-order check: {min_order} units is more than the {r.max_min_order}-unit limit."
    return "recommend", (f"All four purchasing checks pass: approved vendor, ${unit_price:.2f} at or below the "
                         f"${r.max_cost[sku]:.2f} max unit cost, {lead_time_days}-day lead time, and {min_order}-unit minimum.")


def unverified_fields(report: VendorReport, visible: str) -> list[tuple[str, str]]:
    """Reported facts that do not appear in the document's visible text."""
    numbers = {float(n.replace(",", "")) for n in NUMBER.findall(visible)}
    low = visible.lower()
    problems = []
    if report.vendor != UNKNOWN_VENDOR and norm(report.vendor) not in norm(visible):
        problems.append(("vendor", f"vendor '{report.vendor}' does not appear in the visible document"))
    if report.sku is not None and report.sku.lower() not in low:
        problems.append(("sku", f"SKU {report.sku} does not appear in the visible document"))
    if report.unit_price is not None and report.unit_price not in numbers:
        problems.append(("unit_price", f"unit price {report.unit_price} does not appear in the visible document"))
    lead = report.lead_time_days
    if lead is not None and lead not in numbers and not (lead % 7 == 0 and lead / 7 in numbers and "week" in low):
        problems.append(("lead_time_days", f"lead time {lead} does not appear in the visible document"))
    if report.min_order is not None and report.min_order not in numbers:
        problems.append(("min_order", f"minimum order {report.min_order} does not appear in the visible document"))
    return problems


def check_report(report: VendorReport, visible: str) -> list[str]:
    """Everything wrong with an answer. An empty list means it passes."""
    problems = [msg for _, msg in unverified_fields(report, visible)]
    decision, reason = decide(report.vendor, report.sku, report.unit_price, report.lead_time_days, report.min_order)
    if report.decision != decision:
        problems.append(f"the decision must be {decision} for these facts ({reason})")
    if CONTACT.search(report.reason):
        problems.append("the reason contains a link, email address, or phone number")
    return problems


def fail_closed(report: VendorReport, visible: str) -> VendorReport:
    """Last resort after a retry: drop facts not in the visible document, then decide by code."""
    updates = {field: None for field, _ in unverified_fields(report, visible)}
    if "vendor" in updates:
        updates["vendor"] = UNKNOWN_VENDOR
    facts = report.model_copy(update=updates)
    decision, reason = decide(facts.vendor, facts.sku, facts.unit_price, facts.lead_time_days, facts.min_order)
    return facts.model_copy(update={"decision": decision, "reason": reason})
