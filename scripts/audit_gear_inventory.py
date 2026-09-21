"""
Audit the fishing report's gear against the tackle inventory of record.

    uv run python scripts/audit_gear_inventory.py [path/to/tackle-inventory.md]

Exit 0 on a clean audit, 1 with findings, 2 when the inventory file is not
on this machine (the registry-only checks still run). The Croton repo can
call this after an inventory edit so drift surfaces the same day.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inventory_audit import INVENTORY_PATH, audit, load_inventory  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else INVENTORY_PATH
    inventory = load_inventory(path)
    findings = audit(inventory)
    for f in findings:
        print("DRIFT  " + f)
    if inventory is None:
        print(f"inventory not found at {path}; registry checks only")
        return 2 if not findings else 1
    print(f"gear audit: {len(findings)} finding{'' if len(findings) == 1 else 's'} against {path}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
