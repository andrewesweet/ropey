"""Tier 2 and Tier 3 catalogue at the tool boundary (issues #14–#19)."""

from __future__ import annotations

from conftest import blast_paths


class TestIntroduceParameter:
    """Issue #14."""

    def test_selected_expression_becomes_a_parameter_with_default(
        self, make_repo, call_tool
    ):
        source = "RATE = 1.2\n\ndef total(amount):\n    return amount * RATE\n"
        repo = make_repo({"tax.py": source})
        line = source.split("\n")[3]
        start = line.index("RATE")
        report = call_tool(
            "introduce_parameter",
            {
                "file": str(repo / "tax.py"),
                "start_line": 3,
                "start_character": start,
                "end_line": 3,
                "end_character": start + 4,
                "parameter_name": "rate",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "tax.py").read_text()
        assert "def total(amount, rate=RATE):" in text
        assert "return amount * rate" in text

    def test_invalid_selection_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo({"tax.py": "CONSTANT = 1.2\n"})
        report = call_tool(
            "introduce_parameter",
            {
                "file": str(repo / "tax.py"),
                "start_line": 0,
                "start_character": 11,
                "end_line": 0,
                "end_character": 14,
                "parameter_name": "rate",
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"


class TestEncapsulateField:
    """Issue #15."""

    ACCOUNT = (
        "class Account:\n"
        "    def __init__(self):\n"
        "        self.balance = 0\n"
    )
    USER = (
        "from account import Account\n"
        "acc = Account()\n"
        "acc.balance = 10\n"
        "print(acc.balance)\n"
    )

    def test_accesses_across_files_rewrite_to_getter_and_setter(
        self, make_repo, call_tool
    ):
        repo = make_repo({"account.py": self.ACCOUNT, "app.py": self.USER})
        report = call_tool(
            "encapsulate_field",
            {
                "file": str(repo / "account.py"),
                "line": 2,
                "character": 13,
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert blast_paths(report) >= {"account.py", "app.py"}
        account = (repo / "account.py").read_text()
        assert "def get_balance(self):" in account
        assert "def set_balance(self, value):" in account
        app = (repo / "app.py").read_text()
        assert "acc.set_balance(10)" in app
        assert "print(acc.get_balance())" in app

    def test_uncertain_accesses_surface(self, make_repo, call_tool):
        repo = make_repo(
            {
                "account.py": self.ACCOUNT,
                "dynamic.py": "def audit(obj):\n    return obj.balance\n",
            }
        )
        report = call_tool(
            "encapsulate_field",
            {
                "file": str(repo / "account.py"),
                "line": 2,
                "character": 13,
            },
        )
        assert report["status"] == "dry_run"
        assert any(
            o["path"] == "dynamic.py" for o in report["uncertain_occurrences"]
        )


class TestIntroduceFactory:
    """Issue #16."""

    def test_factory_created_and_instantiations_rewritten(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "shape.py": "class Circle:\n    pass\n",
                "app.py": "from shape import Circle\nc = Circle()\n",
            }
        )
        report = call_tool(
            "introduce_factory",
            {
                "file": str(repo / "shape.py"),
                "line": 0,
                "character": 6,
                "factory_name": "create",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        shape = (repo / "shape.py").read_text()
        assert "def create(" in shape
        assert "Circle.create()" in (repo / "app.py").read_text()

    def test_unrefactorable_target_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo({"mod.py": "value = 1\n"})
        report = call_tool(
            "introduce_factory",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "factory_name": "create",
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"


class TestMethodObject:
    """Issue #17."""

    def test_method_becomes_a_class_and_delegates(self, make_repo, call_tool):
        repo = make_repo(
            {
                "calc.py": (
                    "class Calculator:\n"
                    "    def compute(self, x):\n"
                    "        y = x * 2\n"
                    "        return y + 1\n"
                )
            }
        )
        report = call_tool(
            "method_object",
            {
                "file": str(repo / "calc.py"),
                "line": 1,
                "character": 8,
                "class_name": "Compute",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "calc.py").read_text()
        assert "class Compute(" in text
        assert "__call__" in text
        assert "Compute(self, x)()" in text

    def test_unrefactorable_target_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo({"mod.py": "value = 1\n"})
        report = call_tool(
            "method_object",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "class_name": "Thing",
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"


class TestLocalToField:
    """Issue #18."""

    def test_local_becomes_an_instance_field(self, make_repo, call_tool):
        repo = make_repo(
            {
                "order.py": (
                    "class Order:\n"
                    "    def place(self):\n"
                    "        total = 100\n"
                    "        return total\n"
                )
            }
        )
        report = call_tool(
            "local_to_field",
            {
                "file": str(repo / "order.py"),
                "line": 2,
                "character": 8,
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        text = (repo / "order.py").read_text()
        assert "self.total = 100" in text
        assert "return self.total" in text

    def test_non_local_target_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "value = 1\n"})
        report = call_tool(
            "local_to_field",
            {"file": str(repo / "mod.py"), "line": 0, "character": 0},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"


class TestUseFunction:
    """Issue #19."""

    def test_duplicated_logic_replaced_with_calls_across_files(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "lib.py": "def square(x):\n    return x ** 2\n",
                "app.py": "def area(side):\n    return side ** 2\n",
            }
        )
        report = call_tool(
            "use_function",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 4,
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        app = (repo / "app.py").read_text()
        assert "square(side)" in app

    def test_non_function_target_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo({"mod.py": "value = 1\n"})
        report = call_tool(
            "use_function",
            {"file": str(repo / "mod.py"), "line": 0, "character": 0},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "target-not-refactorable"
