"""Tier 1 catalogue at the tool boundary (issues #7–#12)."""

from __future__ import annotations

from conftest import blast_paths, entry_for


class TestRenameOptions:
    """Issue #7: docstrings/comments and class-hierarchy options."""

    SOURCE = '''\
def greet():
    """greet says hi."""
    return "hi"  # greet is friendly

greet()
'''

    def test_docstring_and_comment_occurrences_only_when_asked(
        self, make_repo, call_tool
    ):
        repo = make_repo({"mod.py": self.SOURCE})
        args = {
            "file": str(repo / "mod.py"),
            "line": 0,
            "character": 4,
            "new_name": "salute",
            "apply": True,
        }
        without = make_repo({"mod.py": self.SOURCE}, name="without")
        args_without = dict(args, file=str(without / "mod.py"))
        call_tool("rename", args_without)
        text = (without / "mod.py").read_text()
        assert "def salute():" in text
        assert "greet says hi." in text  # untouched by default
        assert "# greet is friendly" in text

        call_tool("rename", dict(args, in_docstrings_and_comments=True))
        text = (repo / "mod.py").read_text()
        assert "def salute():" in text
        assert "salute says hi." in text
        assert "# salute is friendly" in text

    HIERARCHY = """\
class Base:
    def process(self):
        return 0

class Left(Base):
    def process(self):
        return 1

class Right(Base):
    def process(self):
        return 2
"""

    def test_hierarchy_option_renames_base_and_siblings(self, make_repo, call_tool):
        repo = make_repo({"shapes.py": self.HIERARCHY})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "shapes.py"),
                "line": 5,  # Left.process
                "character": 8,
                "new_name": "handle",
                "apply": True,
                "across_class_hierarchy": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "shapes.py").read_text()
        assert text.count("def handle(self):") == 3
        assert "def process" not in text

    def test_without_hierarchy_only_the_targeted_binding_changes(
        self, make_repo, call_tool
    ):
        repo = make_repo({"shapes.py": self.HIERARCHY})
        call_tool(
            "rename",
            {
                "file": str(repo / "shapes.py"),
                "line": 5,
                "character": 8,
                "new_name": "handle",
                "apply": True,
            },
        )
        text = (repo / "shapes.py").read_text()
        assert text.count("def handle(self):") == 1
        assert text.count("def process(self):") == 2


class TestMove:
    """Issue #8: global / method / whole-module moves."""

    def test_move_global_updates_definition_destination_and_importers(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "source.py": "def helper():\n    return 42\n",
                "dest.py": "",
                "app.py": "from source import helper\nprint(helper())\n",
            }
        )
        report = call_tool(
            "move",
            {
                "file": str(repo / "source.py"),
                "line": 0,
                "character": 4,
                "destination": str(repo / "dest.py"),
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert {"source.py", "dest.py", "app.py"} <= blast_paths(report)
        assert "def helper" not in (repo / "source.py").read_text()
        assert "def helper():" in (repo / "dest.py").read_text()
        app = (repo / "app.py").read_text()
        # rope may rewrite the importer as `import dest` + `dest.helper()`
        # or as a from-import; either way it must reference dest, not source.
        assert "dest" in app
        assert "helper" in app
        assert "from source import" not in app

    def test_move_method_to_attribute_class(self, make_repo, call_tool):
        repo = make_repo(
            {
                "shapes.py": (
                    "class Engine:\n"
                    "    pass\n"
                    "\n"
                    "class Car:\n"
                    "    def __init__(self):\n"
                    "        self.engine = Engine()\n"
                    "\n"
                    "    def start(self):\n"
                    "        return 'started'\n"
                )
            }
        )
        report = call_tool(
            "move",
            {
                "file": str(repo / "shapes.py"),
                "line": 7,
                "character": 8,
                "destination_attribute": "engine",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "shapes.py").read_text()
        engine_section = text[: text.index("class Car")]
        assert "def start(self):" in engine_section

    def test_move_whole_module_with_file_only_location(self, make_repo, call_tool):
        repo = make_repo(
            {
                "tools.py": "def util():\n    return 1\n",
                "pkg/__init__.py": "",
                "app.py": "import tools\nprint(tools.util())\n",
            }
        )
        report = call_tool(
            "move",
            {
                "file": str(repo / "tools.py"),
                "destination": str(repo / "pkg"),
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        moved = entry_for(report, "pkg/tools.py")
        assert moved["change_kind"] == "moved"
        assert moved["old_path"] == "tools.py"
        assert not (repo / "tools.py").exists()
        assert (repo / "pkg" / "tools.py").exists()
        assert "import pkg.tools" in (repo / "app.py").read_text()

    def test_module_to_package_conversion_surfaces_created_entries(
        self, make_repo, call_tool
    ):
        repo = make_repo({"single.py": "flag = True\n"})
        report = call_tool(
            "module_to_package",
            {"file": str(repo / "single.py"), "apply": True},
        )
        assert report["status"] == "applied"
        created = entry_for(report, "single")
        assert created["change_kind"] == "created"
        moved = entry_for(report, "single/__init__.py")
        assert moved["change_kind"] == "moved"
        assert moved["old_path"] == "single.py"
        assert (repo / "single" / "__init__.py").read_text() == "flag = True\n"

    def test_nonexistent_destination_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo({"source.py": "def helper():\n    return 1\n"})
        report = call_tool(
            "move",
            {
                "file": str(repo / "source.py"),
                "line": 0,
                "character": 4,
                "destination": str(repo / "nowhere.py"),
                "apply": True,
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "file-not-found"


class TestExtract:
    """Issue #9: extract method and extract variable from a Range."""

    CALC = """\
def price(amount, rate):
    base = amount * rate
    discounted = base * 0.9
    return discounted
"""

    def test_extract_method_infers_parameters_and_returns(
        self, make_repo, call_tool
    ):
        repo = make_repo({"calc.py": self.CALC})
        report = call_tool(
            "extract_method",
            {
                "file": str(repo / "calc.py"),
                "start_line": 1,
                "start_character": 4,
                "end_line": 2,
                "end_character": 28,
                "name": "apply_discount",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "calc.py").read_text()
        assert "def apply_discount(amount, rate):" in text
        assert "discounted = apply_discount(amount, rate)" in text
        assert "return discounted" in text

    def test_extract_variable_names_the_expression(self, make_repo, call_tool):
        repo = make_repo({"calc.py": "total = 10 * 3 + 5\n"})
        report = call_tool(
            "extract_variable",
            {
                "file": str(repo / "calc.py"),
                "start_line": 0,
                "start_character": 8,
                "end_line": 0,
                "end_character": 14,
                "name": "subtotal",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "calc.py").read_text()
        assert "subtotal = 10 * 3" in text
        assert "total = subtotal + 5" in text

    def test_invalid_range_is_a_structured_failure_with_reason(
        self, make_repo, call_tool
    ):
        repo = make_repo({"calc.py": self.CALC})
        report = call_tool(
            "extract_method",
            {
                "file": str(repo / "calc.py"),
                "start_line": 1,
                "start_character": 4,
                "end_line": 1,
                "end_character": 7,  # mid-token: "bas"
                "name": "broken",
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"
        assert report["failure"]["reason"]

    def test_range_honours_utf16_on_non_ascii_lines(self, make_repo, call_tool):
        source = 'label = "💚" + str(40 + 2)\n'
        repo = make_repo({"uni.py": source})
        expression = "40 + 2"
        prefix = source[: source.index(expression)]
        start = len(prefix.encode("utf-16-le")) // 2
        end = start + len(expression)
        report = call_tool(
            "extract_variable",
            {
                "file": str(repo / "uni.py"),
                "start_line": 0,
                "start_character": start,
                "end_line": 0,
                "end_character": end,
                "name": "answer",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "uni.py").read_text(encoding="utf-8")
        assert "answer = 40 + 2" in text
        assert 'label = "💚" + str(answer)' in text


class TestInline:
    """Issue #10: auto-dispatched inline of method / variable / parameter."""

    def test_inline_method_from_bare_position(self, make_repo, call_tool):
        repo = make_repo(
            {
                "lib.py": "def double(x):\n    return x * 2\n",
                "app.py": "from lib import double\nresult = double(21)\n",
            }
        )
        report = call_tool(
            "inline",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "result = 21 * 2" in (repo / "app.py").read_text()
        assert "def double" not in (repo / "lib.py").read_text()

    def test_inline_variable_from_bare_position(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "factor = 3\nresult = factor * 7\n"})
        report = call_tool(
            "inline",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "mod.py").read_text()
        assert "result = 3 * 7" in text
        assert "factor" not in text

    def test_inline_parameter_writes_default_into_call_sites(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "lib.py": "def shout(text, punctuation='!'):\n"
                "    return text + punctuation\n",
                "app.py": "from lib import shout\nprint(shout('hey'))\n",
            }
        )
        report = call_tool(
            "inline",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 16,  # the parameter name "punctuation"
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "shout('hey', '!')" in (repo / "app.py").read_text()

    def test_uninlinable_target_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "import os\nprint(os.sep)\n"})
        report = call_tool(
            "inline",
            {"file": str(repo / "mod.py"), "line": 0, "character": 7},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"

    def test_uncertain_occurrences_surface_for_inline(self, make_repo, call_tool):
        repo = make_repo(
            {
                "doc.py": (
                    "class Doc:\n"
                    "    def render(self):\n"
                    "        return 'x'\n"
                ),
                "dynamic.py": "def show(obj):\n    return obj.render()\n",
            }
        )
        report = call_tool(
            "inline",
            {
                "file": str(repo / "doc.py"),
                "line": 1,
                "character": 8,
            },
        )
        if report["status"] == "failure":
            # rope may refuse to inline a method with dynamic receivers;
            # that refusal must be structured, not a crash.
            assert report["failure"]["kind"]
        else:
            occurrences = report["uncertain_occurrences"]
            assert any(o["path"] == "dynamic.py" for o in occurrences)


class TestChangeSignature:
    """Issue #11: add / remove / reorder parameters across call sites."""

    LIB = "def connect(host, port):\n    return (host, port)\n"
    APP = "from lib import connect\nconn = connect('local', 8080)\n"

    def test_add_parameter_with_default(self, make_repo, call_tool):
        repo = make_repo({"lib.py": self.LIB, "app.py": self.APP})
        report = call_tool(
            "change_signature",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "operations": [
                    {"action": "add", "name": "timeout", "default": "30"}
                ],
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "def connect(host, port, timeout=30):" in (
            repo / "lib.py"
        ).read_text()
        assert "connect('local', 8080)" in (repo / "app.py").read_text()

    def test_remove_and_reorder_rewrite_call_sites_across_files(
        self, make_repo, call_tool
    ):
        repo = make_repo({"lib.py": self.LIB, "app.py": self.APP})
        report = call_tool(
            "change_signature",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "operations": [{"action": "reorder", "order": ["port", "host"]}],
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "def connect(port, host):" in (repo / "lib.py").read_text()
        assert "connect(8080, 'local')" in (repo / "app.py").read_text()

        report = call_tool(
            "change_signature",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "operations": [{"action": "remove", "name": "port"}],
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "def connect(host):" in (repo / "lib.py").read_text()
        assert "connect('local')" in (repo / "app.py").read_text()

    def test_uncertain_call_sites_surface(self, make_repo, call_tool):
        repo = make_repo(
            {
                "doc.py": (
                    "class Doc:\n"
                    "    def render(self, mode):\n"
                    "        return mode\n"
                ),
                "dynamic.py": "def show(obj):\n    return obj.render('x')\n",
            }
        )
        report = call_tool(
            "change_signature",
            {
                "file": str(repo / "doc.py"),
                "line": 1,
                "character": 8,
                "operations": [
                    {"action": "add", "name": "style", "default": "'plain'"}
                ],
            },
        )
        assert report["status"] == "dry_run"
        assert any(
            o["path"] == "dynamic.py" for o in report["uncertain_occurrences"]
        )

    def test_invalid_operation_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo({"lib.py": self.LIB})
        report = call_tool(
            "change_signature",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "operations": [{"action": "remove", "name": "no_such_param"}],
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-argument"
        assert "no_such_param" in report["failure"]["reason"]


class TestOrganizeImports:
    """Issue #12: sort, dedupe, expand stars, relative→absolute."""

    def test_unused_and_duplicate_imports_removed_and_sorted(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "mod.py": (
                    "import sys\n"
                    "import os\n"
                    "import os\n"
                    "import json\n"
                    "\n"
                    "print(os.sep, sys.argv)\n"
                )
            }
        )
        report = call_tool(
            "organize_imports",
            {"file": str(repo / "mod.py"), "apply": True},
        )
        assert report["status"] == "applied"
        text = (repo / "mod.py").read_text()
        assert text.count("import os") == 1
        assert "import json" not in text  # unused
        assert text.index("import os") < text.index("import sys")

    def test_star_import_expands_to_used_names(self, make_repo, call_tool):
        repo = make_repo(
            {
                "helpers.py": "def alpha():\n    pass\n\ndef beta():\n    pass\n",
                "mod.py": "from helpers import *\n\nalpha()\n",
            }
        )
        call_tool(
            "organize_imports",
            {
                "file": str(repo / "mod.py"),
                "mode": "expand_star_imports",
                "apply": True,
            },
        )
        call_tool("organize_imports", {"file": str(repo / "mod.py"), "apply": True})
        text = (repo / "mod.py").read_text()
        assert "from helpers import alpha" in text
        assert "*" not in text
        assert "beta" not in text

    def test_relative_imports_convert_to_absolute(self, make_repo, call_tool):
        repo = make_repo(
            {
                "pkg/__init__.py": "",
                "pkg/core.py": "value = 1\n",
                "pkg/use.py": "from . import core\nprint(core.value)\n",
            }
        )
        report = call_tool(
            "organize_imports",
            {
                "file": str(repo / "pkg" / "use.py"),
                "mode": "relatives_to_absolutes",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "pkg" / "use.py").read_text()
        assert "from pkg import core" in text

    def test_dry_run_previews_identically_to_live(self, make_repo, call_tool):
        files = {
            "mod.py": "import os\nimport os\nimport sys\n\nprint(os.sep, sys.argv)\n"
        }
        repo = make_repo(files)
        dry = call_tool("organize_imports", {"file": str(repo / "mod.py")})
        live = call_tool(
            "organize_imports", {"file": str(repo / "mod.py"), "apply": True}
        )
        assert dry["blast_radius"] == live["blast_radius"]
        assert dry["status"] == "dry_run" and live["status"] == "applied"
