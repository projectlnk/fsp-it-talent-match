"""Freeze original field names, methods, actions and constraints across the redesign."""
import json
from pathlib import Path
from html.parser import HTMLParser
import pytest
ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = json.loads((ROOT / "tests/fixtures/working_form_contracts.json").read_text(encoding="utf-8"))

class Forms(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms = []; self.current = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.current = {"method": a.get("method", "get"), "action": a.get("action", ""), "fields": []}; self.forms.append(self.current)
        elif tag in ("input", "select", "textarea") and self.current is not None:
            self.current["fields"].append({k: a[k] for k in ("name", "type", "value", "required", "min", "max", "minlength", "maxlength") if k in a})
    def handle_endtag(self, tag):
        if tag == "form": self.current = None

@pytest.mark.parametrize("name", CONTRACTS)
def test_working_form_contract_unchanged(name):
    parser = Forms(); parser.feed((ROOT / "app/templates" / name).read_text(encoding="utf-8"))
    # Later features may add forms; preserve every original form exactly.
    original = CONTRACTS[name]
    actions = {(f['method'], f['action']) for f in original}
    assert [f for f in parser.forms if (f['method'], f['action']) in actions] == original
