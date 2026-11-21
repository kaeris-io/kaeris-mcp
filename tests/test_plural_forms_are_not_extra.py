"""A plural form the target language needs is not an "extra/stale" key (P0.2.47, critic round 2).

kaeris 0.2.47 translate writes every CLDR form a language needs: Polish gets `items_few` and
`items_many` beside the English source's `items_one` / `items_other`. `kaeris check` reads them
as forms the file owes. `kaeris_status` and `kaeris_list_missing_keys` ran the bare key diff and
listed them under "extra" — which the tool's own description calls "extra/stale keys", and an
agent tidying a repository deletes those. The verdicts must be the CLI's.
"""
import json
import os
import sys
import tempfile
import types
import unittest

if "mcp.server.fastmcp" not in sys.modules:
    _fake = types.ModuleType("mcp.server.fastmcp")

    class _FastMCP:
        def __init__(self, *a, **k):
            pass

        def tool(self, *a, **k):
            def deco(fn):
                return fn
            return deco

        def run(self, *a, **k):
            pass

    _fake.FastMCP = _FastMCP
    sys.modules.setdefault("mcp", types.ModuleType("mcp"))
    sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
    sys.modules["mcp.server.fastmcp"] = _fake

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kaeris_mcp.server as s  # noqa: E402
from kaeris import check as chk  # noqa: E402

SOURCE = {"items_one": "{{count}} item", "items_other": "{{count}} items",
          "day": {"one": "One day", "other": "{{count}} days"}, "title": "Inbox"}
PL = {"items_one": "{{count}} element", "items_few": "{{count}} elementy",
      "items_many": "{{count}} elementów", "items_other": "{{count}} elementu",
      "day": {"one": "Jeden dzień", "few": "{{count}} dni", "many": "{{count}} dni",
              "other": "{{count}} dnia"}, "title": "Skrzynka"}
JA = {"items_other": "{{count}} 件", "day": {"other": "{{count}} 日"}, "title": "受信箱"}


def _write(d, name, obj):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


class PluralFormsAreOwedNotExtra(unittest.TestCase):
    def _mcp(self, lang, target):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "en.json", SOURCE)
            _write(d, f"{lang}.json", target)
            return s.kaeris_status(src, [lang]), s.kaeris_list_missing_keys(src, lang)

    def _cli(self, lang, target):
        return chk.check_locales(SOURCE, [lang], lambda _l: target, [])

    def test_polish_forms_are_not_extra(self):
        status, keys = self._mcp("pl", PL)
        self.assertEqual(status["extra"], {}, status)
        self.assertEqual(keys["extra"], [], keys)
        self.assertTrue(status["ok"], status)
        self.assertEqual(self._cli("pl", PL)["extra"], {})

    def test_japanese_without_one_is_complete(self):
        status, keys = self._mcp("ja", JA)
        self.assertEqual(status["missing"], {}, status)
        self.assertEqual(keys["missing"], [], keys)
        self.assertTrue(status["ok"], status)

    def test_a_polish_set_without_its_forms_is_the_clis_verdict(self):
        target = {"items_one": "{{count}} element", "items_other": "{{count}} elementów",
                  "day": {"one": "Jeden dzień", "other": "{{count}} dni"}, "title": "Skrzynka"}
        cli = self._cli("pl", target)
        status, _ = self._mcp("pl", target)
        self.assertEqual(status["ok"], cli["ok"], (status, cli))
        self.assertEqual(sorted(f["msg"] for f in status["faults"]),
                         sorted(f["msg"] for f in cli["faults"]))

    def test_list_missing_keys_names_the_forms_check_asks_for(self):
        """Critic round 3: kaeris_list_missing_keys dropped the plural faults. For a Polish file
        without few/many an agent read "nothing missing" while `kaeris check` failed. The faults
        come back as kaeris_status gives them: errors (RED in check) and warnings."""
        target = {"items_one": "{{count}} element", "items_other": "{{count}} elementów",
                  "day": {"one": "Jeden dzień", "other": "{{count}} dni"}, "title": "Skrzynka"}
        cli = self._cli("pl", target)
        _, keys = self._mcp("pl", target)
        self.assertEqual(keys["missing"], [], keys)
        said = keys["plural_faults"]
        self.assertEqual(sorted(f["msg"] for f in said if f["severity"] == "error"),
                         sorted(f["msg"] for f in cli["faults"]), (said, cli))
        self.assertTrue(any("items_few" in f["msg"] for f in said), said)
        self.assertTrue(any("day" in f["msg"] for f in said), said)
        self.assertEqual(keys["plural_fault_count"], len(said))

    def test_a_key_the_source_does_not_have_is_still_extra(self):
        status, _ = self._mcp("pl", dict(PL, old_banner="Stary baner"))
        self.assertEqual(status["extra"], {"pl": ["old_banner"]}, status)


class TheFloorIsAKaerisThatReadsPluralForms(unittest.TestCase):
    """Critic round 3: the package required kaeris>=0.2.39, and with kaeris 0.2.39–0.2.44 (no
    plural-set reading before 0.2.45) kaeris_status still called Polish items_few/items_many
    extra/stale (4 failed above on a 0.2.44 tree). The floor is 0.2.47: the public
    `check.plural_set_faults`, and the client that asks the server for every form (`plurals=cldr`)
    and merges a new form beside its siblings — the files kaeris_status then reads. Every place
    that installs kaeris says the same floor."""
    FLOOR = (0, 2, 47)
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _floors(self, rel):
        import re
        path = os.path.join(self.ROOT, rel)
        if not os.path.isfile(path):
            return None
        text = open(path, encoding="utf-8").read()
        return [tuple(int(x) for x in v.split(".")) for v in re.findall(r'"kaeris>=([0-9.]+)"', text)]

    def test_every_install_asks_for_0_2_47(self):
        for rel in ("pyproject.toml", "Dockerfile", os.path.join("bundle", "server", "main.py")):
            floors = self._floors(rel)
            if floors is None:
                continue          # the bundle lives only in the i18n_tool copy
            self.assertTrue(floors, rel)
            self.assertTrue(all(f == self.FLOOR for f in floors), (rel, floors))


if __name__ == "__main__":
    unittest.main()
