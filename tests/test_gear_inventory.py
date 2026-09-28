"""Tests for inventory_audit.py — the report's gear against the inventory of record."""
import os
import re

import pytest

import inventory_audit
from inventory_audit import (
    OWNED_GEAR, BUY_OR_VERIFY, UNINVENTORIED, registry_findings, inventory_findings,
    audit, report_text, live_paragraphs, load_inventory, INVENTORY_PATH,
)

INVENTORY = load_inventory()


class TestRegistry:
    def test_every_registered_item_is_still_mentioned(self):
        assert [f for f in registry_findings() if f.startswith("registry:")] == []

    def test_every_gear_token_in_the_report_is_registered(self):
        assert [f for f in registry_findings() if f.startswith("unregistered:")] == []

    def test_buy_items_are_not_registered_as_owned(self):
        text = report_text()
        for label, pat, _ in BUY_OR_VERIFY:
            assert re.search(pat, text), f"buy/verify pattern {pat!r} no longer in the report ({label})"
            assert not any(re.search(m, pat) for _, m, _ in OWNED_GEAR)

    def test_no_pruned_names_in_the_report(self):
        """Items the inventory pruned on 2026-08-28 must not be named as owned."""
        text = report_text()
        for pruned in ("XPS", "Spinnie", "Thomas", "gold w/ red accents", "bank sinker"):
            assert pruned not in text, pruned


class TestInventoryLogic:
    SAMPLE = (
        "## Metal\n\n| Role | Name | Stock |\n|---|---|---|\n"
        "| The vertical spoon | \"the Kastmaster\" | **Acme Kastmaster ×6** |\n\n"
        "**Pruned on repack day (2026-08-28)** — the Bass Pro XPS ⅜ oz, the gold/red Thomas-class spoon.\n\n"
        "| The cold-water hair jig | \"the marabou\" | **marabou hair jigs ×9**. Hooks failed inspection 2026-08-28 |\n"
    )

    def test_pruned_paragraphs_are_dropped(self):
        live = "\n".join(live_paragraphs(self.SAMPLE))
        assert "Kastmaster ×6" in live and "XPS" not in live

    def test_pruned_item_is_flagged(self, monkeypatch):
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR",
                            [("XPS spoon", r"XPS", r"XPS")])
        findings = inventory_findings(self.SAMPLE)
        assert findings and findings[0].startswith("pruned:")

    def test_missing_item_is_flagged(self, monkeypatch):
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR",
                            [("unicorn", r"unicorn", r"unicorn")])
        findings = inventory_findings(self.SAMPLE)
        assert findings and findings[0].startswith("missing:")

    def test_buy_item_the_inventory_now_carries_is_flagged(self, monkeypatch):
        """The reverse drift: the report still says buy, the shelf says owned.
        This is what went unnoticed on 2026-09-28 until someone read both."""
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR", [])
        monkeypatch.setattr(inventory_audit, "BUY_OR_VERIFY",
                            [("a Kastmaster", r"Kastmaster", r"Kastmaster ×\d")])
        findings = inventory_findings(self.SAMPLE)
        assert findings and findings[0].startswith("bought:")

    def test_buy_item_still_unbought_is_silent(self, monkeypatch):
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR", [])
        monkeypatch.setattr(inventory_audit, "BUY_OR_VERIFY",
                            [("a dip net", r"dip net", r"dip net"),
                             ("uninventoried fly line", r"polyleader", None)])
        assert inventory_findings(self.SAMPLE) == []

    def test_bought_check_ignores_pruned_rows(self, monkeypatch):
        """A buy item that matches only a pruned paragraph is still unbought."""
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR", [])
        monkeypatch.setattr(inventory_audit, "BUY_OR_VERIFY",
                            [("the XPS spoon", r"XPS", r"XPS")])
        assert inventory_findings(self.SAMPLE) == []

    def test_failed_inspection_requires_gear_check_mention(self, monkeypatch):
        monkeypatch.setattr(inventory_audit, "OWNED_GEAR",
                            [("marabou", r"[Mm]arabou", r"marabou hair jigs")])
        monkeypatch.setattr(inventory_audit, "gear_check_text", lambda: "nothing about jigs")
        findings = inventory_findings(self.SAMPLE)
        assert findings and findings[0].startswith("inspect:")
        monkeypatch.setattr(inventory_audit, "gear_check_text", lambda: "Marabou jigs: file the hooks")
        assert inventory_findings(self.SAMPLE) == []


@pytest.mark.skipif(INVENTORY is None, reason=f"inventory of record not on this machine ({INVENTORY_PATH})")
class TestAgainstTheRealInventory:
    """Runs only where new-croton-fishing is checked out (Brian's workstation)."""

    def test_no_drift(self):
        findings = audit(INVENTORY)
        assert findings == [], "\n".join(findings)
