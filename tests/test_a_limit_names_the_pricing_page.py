"""A run refused on a plan limit tells the agent where the plans are, tagged utm_source=mcp.

launch-drafts-1030/cli-cta.md: the site reads the source of a visit only from ?utm_source=
(not ?ref=), and a link passed on by an agent has no referrer. The API tags its own link
utm_source=api; read through this server it is ours. Any other failure carries no link, and
KAERIS_NO_CTA=1 turns it off. The link travels in the tool's error, never on stdout."""
import os
import sys
import json
import types
import tempfile
import unittest
from unittest import mock

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
from kaeris.client import KaerisError  # noqa: E402

LINK = "https://kaeris.dev/pricing.html?utm_source=mcp"
OVER_FILE = ("HTTP 400: File exceeds free tier (12,345 chars, max 10,000). Get a free API key at "
             "kaeris.dev/developer for up to 50,000 chars, or Pro for 100,000 chars.")
OVER_MONTH = ("HTTP 429: This run needs 320 characters (4 language(s) × the text in your file) and "
              "100 are left of your 600 this month. To raise it: "
              "https://kaeris.dev/pricing.html?utm_source=api, or a Lifetime (BYOK) key ...")
BROKEN = "HTTP 500: Translation failed, nothing was charged"


class RefusingClient:
    refusal = OVER_FILE

    def submit(self, *a, **k):
        raise KaerisError(self.refusal)

    def key_info(self):
        return {}


class _Base(unittest.TestCase):
    def setUp(self):
        self._real = s._client
        s._client = lambda *a, **k: RefusingClient()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("KAERIS_NO_CTA", None)

    def tearDown(self):
        s._client = self._real
        self._env.stop()

    def _error(self, refusal, tool="file"):
        RefusingClient.refusal = refusal
        with tempfile.TemporaryDirectory() as t:
            src = os.path.join(t, "en.json")
            with open(src, "w", encoding="utf-8") as f:
                json.dump({"a": "Hello"}, f)
            with self.assertRaises(Exception) as cm:
                if tool == "file":
                    s.kaeris_translate_file(src, ["de"], out_dir=t)
                elif tool == "only_new":
                    s.kaeris_translate_file(src, ["de"], out_dir=t, only_new=True)
                elif tool == "add":
                    s.kaeris_add_language(src, "de", out=t)
                else:
                    s.kaeris_translate({"a": "Hello"}, ["de"])
        return str(cm.exception)


class TestLimitLink(_Base):
    def test_every_translating_tool_names_the_pricing_page(self):
        for tool in ("file", "only_new", "add", "strings"):
            with self.subTest(tool=tool):
                msg = self._error(OVER_FILE, tool)
                self.assertIn("File exceeds free tier", msg)
                self.assertIn(LINK, msg)
                self.assertEqual(msg.count("kaeris.dev/pricing"), 1, msg)

    def test_the_apis_own_link_becomes_ours_and_is_not_repeated(self):
        msg = self._error(OVER_MONTH)
        self.assertNotIn("utm_source=api", msg)
        self.assertEqual(msg.count(LINK), 1, msg)

    def test_another_failure_has_no_link(self):
        msg = self._error(BROKEN)
        self.assertIn("Translation failed", msg)
        self.assertNotIn("utm_source", msg)

    def test_switched_off(self):
        os.environ["KAERIS_NO_CTA"] = "1"
        msg = self._error(OVER_FILE)
        self.assertIn("File exceeds free tier", msg)
        self.assertNotIn(LINK, msg)


if __name__ == "__main__":
    unittest.main()
