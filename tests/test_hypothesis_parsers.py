"""Property-based tests for claudechic manifest parsers.

Uses hypothesis to fuzz the guardrails, checks, workflows, and hints parsers
with random/malformed input. The goal: parsers should NEVER raise unhandled
exceptions — they should skip bad entries gracefully and return valid results.
"""

from __future__ import annotations

import string

from claudechic.checks.parsers import ChecksParser
from claudechic.guardrails.parsers import InjectionsParser, RulesParser
from claudechic.hints.parsers import HintsParser
from claudechic.workflows.parsers import PhasesParser
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary JSON-like values that YAML might produce
yaml_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=200),
    st.binary(max_size=50).map(lambda b: b.decode("utf-8", errors="replace")),
)

yaml_values = st.recursive(
    yaml_primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=30), children, max_size=8),
    ),
    max_leaves=20,
)

# Dicts that look vaguely like manifest entries (random keys/values)
random_manifest_entry = st.dictionaries(
    st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=20),
    yaml_values,
    min_size=0,
    max_size=10,
)

# Well-structured entries with some valid fields mixed with fuzz
rule_like_entry = st.fixed_dictionaries(
    {},
    optional={
        "id": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "trigger": st.one_of(
            st.text(max_size=50),
            st.lists(st.text(max_size=30), max_size=5),
            st.none(),
            st.integers(),
        ),
        "enforcement": st.one_of(
            st.sampled_from(["deny", "warn", "log", "invalid", "", None]),
            st.text(max_size=20),
        ),
        "detect": st.one_of(
            st.none(),
            st.text(max_size=50),
            st.dictionaries(st.text(max_size=20), st.text(max_size=50), max_size=3),
        ),
        "exclude_if_matches": st.one_of(st.none(), st.text(max_size=50)),
        "message": st.one_of(st.text(max_size=100), st.none(), st.integers()),
        "phases": st.one_of(
            st.none(),
            st.text(max_size=30),
            st.lists(st.text(max_size=30), max_size=3),
        ),
        "roles": st.one_of(st.none(), st.lists(st.text(max_size=20), max_size=3)),
    },
)

check_like_entry = st.fixed_dictionaries(
    {},
    optional={
        "id": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "type": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "params": st.one_of(
            st.none(),
            st.dictionaries(st.text(max_size=20), yaml_values, max_size=5),
            st.lists(st.text(max_size=10), max_size=3),  # wrong type
        ),
        "on_failure": st.one_of(
            st.none(),
            st.dictionaries(st.text(max_size=20), st.text(max_size=50), max_size=3),
            st.text(max_size=30),  # wrong type
        ),
        "when": st.one_of(
            st.none(),
            st.dictionaries(st.text(max_size=20), st.text(max_size=50), max_size=3),
            st.integers(),  # wrong type
        ),
    },
)

hint_like_entry = st.fixed_dictionaries(
    {},
    optional={
        "id": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "message": st.one_of(st.text(max_size=200), st.integers(), st.none()),
        "lifecycle": st.one_of(
            st.sampled_from(
                ["show-once", "show-until-resolved", "show-every-session", "cooldown"]
            ),
            st.text(max_size=30),
            st.none(),
            st.integers(),
        ),
        "cooldown_seconds": st.one_of(
            st.integers(min_value=-100, max_value=10000),
            st.none(),
            st.text(max_size=10),
            st.floats(),
        ),
        "phase": st.one_of(st.text(max_size=50), st.none(), st.integers()),
    },
)

phase_like_entry = st.fixed_dictionaries(
    {},
    optional={
        "id": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "file": st.one_of(st.text(max_size=50), st.integers(), st.none()),
        "advance_checks": st.one_of(
            st.none(),
            st.lists(random_manifest_entry, max_size=3),
            st.text(max_size=20),  # wrong type
        ),
        "hints": st.one_of(
            st.none(),
            st.lists(random_manifest_entry, max_size=3),
            st.text(max_size=20),  # wrong type
        ),
    },
)

# Namespaces
namespace_st = st.one_of(
    st.just("global"),
    st.text(alphabet=string.ascii_lowercase + "_-", min_size=1, max_size=30),
)

# Lists that may contain non-dict items (the parsers should handle this)
mixed_raw_list = st.lists(
    st.one_of(
        random_manifest_entry,
        st.text(max_size=50),
        st.integers(),
        st.none(),
        st.lists(st.text(max_size=10), max_size=3),
    ),
    max_size=10,
)

# ---------------------------------------------------------------------------
# Hypothesis settings
# ---------------------------------------------------------------------------

PARSER_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=5000,  # 5s per example
)

# ---------------------------------------------------------------------------
# Tests: RulesParser
# ---------------------------------------------------------------------------


class TestRulesParserHypothesis:
    """Property-based tests for RulesParser."""

    parser = RulesParser()

    @given(raw=mixed_raw_list, namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_input(self, raw, namespace):
        """RulesParser.parse should never raise on arbitrary input."""
        result = self.parser.parse(raw, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(rule_like_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_rule_like_input(self, entries, namespace):
        """RulesParser.parse should handle rule-shaped dicts gracefully."""
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(random_manifest_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_dicts(self, entries, namespace):
        """RulesParser.parse should handle random dicts without crashing."""
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(
        raw_id=st.text(max_size=50),
        trigger=st.text(min_size=1, max_size=50),
        namespace=namespace_st,
    )
    @PARSER_SETTINGS
    def test_edge_case_strings(self, raw_id, trigger, namespace):
        """Test edge-case string values for id and trigger fields."""
        entry = {"id": raw_id, "trigger": trigger, "enforcement": "deny"}
        result = self.parser.parse([entry], namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)
        # If rule was parsed, verify structure
        for rule in result:
            assert hasattr(rule, "id")
            assert hasattr(rule, "namespace")


# ---------------------------------------------------------------------------
# Tests: InjectionsParser
# ---------------------------------------------------------------------------


class TestInjectionsParserHypothesis:
    """Property-based tests for InjectionsParser."""

    parser = InjectionsParser()

    @given(raw=mixed_raw_list, namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_input(self, raw, namespace):
        result = self.parser.parse(raw, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(rule_like_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_rule_like_input(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: ChecksParser
# ---------------------------------------------------------------------------


class TestChecksParserHypothesis:
    """Property-based tests for ChecksParser."""

    parser = ChecksParser()

    @given(raw=mixed_raw_list, namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_input(self, raw, namespace):
        result = self.parser.parse(raw, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(check_like_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_check_like_input(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(random_manifest_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_dicts(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: HintsParser
# ---------------------------------------------------------------------------


class TestHintsParserHypothesis:
    """Property-based tests for HintsParser."""

    parser = HintsParser()

    @given(raw=mixed_raw_list, namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_input(self, raw, namespace):
        result = self.parser.parse(raw, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(hint_like_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_hint_like_input(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(random_manifest_entry, max_size=8), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_dicts(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(
        raw_id=st.text(alphabet=string.ascii_letters + "_-", min_size=1, max_size=30),
        message=st.text(min_size=1, max_size=100),
        lifecycle=st.sampled_from(
            ["show-once", "show-until-resolved", "show-every-session", "cooldown"]
        ),
        cooldown=st.integers(min_value=-1000, max_value=10000),
        namespace=namespace_st,
    )
    @PARSER_SETTINGS
    def test_valid_shaped_hints_never_crash(
        self, raw_id, message, lifecycle, cooldown, namespace
    ):
        """Even valid-looking hints with edge-case values should not crash."""
        entry = {
            "id": raw_id,
            "message": message,
            "lifecycle": lifecycle,
            "cooldown_seconds": cooldown,
        }
        result = self.parser.parse([entry], namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: PhasesParser
# ---------------------------------------------------------------------------


class TestPhasesParserHypothesis:
    """Property-based tests for PhasesParser."""

    parser = PhasesParser()

    @given(raw=mixed_raw_list, namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_input(self, raw, namespace):
        result = self.parser.parse(raw, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(phase_like_entry, max_size=5), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_phase_like_input(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(entries=st.lists(random_manifest_entry, max_size=5), namespace=namespace_st)
    @PARSER_SETTINGS
    def test_never_crashes_on_random_dicts(self, entries, namespace):
        result = self.parser.parse(entries, namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)

    @given(
        raw_id=st.text(alphabet=string.ascii_letters + "_-", min_size=1, max_size=30),
        namespace=namespace_st,
        num_checks=st.integers(min_value=0, max_value=5),
        num_hints=st.integers(min_value=0, max_value=5),
    )
    @PARSER_SETTINGS
    def test_phase_with_nested_structures(
        self, raw_id, namespace, num_checks, num_hints
    ):
        """Phase with advance_checks and hints lists of random dicts."""
        entry = {
            "id": raw_id,
            "file": raw_id,
            "advance_checks": [
                {"type": f"check-{i}", "param": "val"} for i in range(num_checks)
            ],
            "hints": [
                {"message": f"hint {i}", "lifecycle": "show-once"}
                for i in range(num_hints)
            ],
        }
        result = self.parser.parse([entry], namespace=namespace, source_path="<fuzz>")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: Regex edge cases (important for guardrails)
# ---------------------------------------------------------------------------


class TestRegexEdgeCases:
    """Test that invalid regex patterns in detect/exclude fields are handled."""

    rules_parser = RulesParser()
    injections_parser = InjectionsParser()

    @given(pattern=st.text(max_size=100))
    @PARSER_SETTINGS
    def test_rules_detect_bad_regex(self, pattern):
        """Invalid regex in detect.pattern should not crash the parser."""
        entry = {
            "id": "test_rule",
            "trigger": "PreToolUse/Bash",
            "enforcement": "deny",
            "detect": {"pattern": pattern, "field": "command"},
        }
        result = self.rules_parser.parse(
            [entry], namespace="test", source_path="<fuzz>"
        )
        assert isinstance(result, list)
        # Either parsed successfully (valid regex) or skipped (invalid regex)
        assert len(result) <= 1

    @given(pattern=st.text(max_size=100))
    @PARSER_SETTINGS
    def test_rules_exclude_bad_regex(self, pattern):
        """Invalid regex in exclude_if_matches should not crash."""
        entry = {
            "id": "test_rule",
            "trigger": "PreToolUse/Bash",
            "enforcement": "deny",
            "exclude_if_matches": pattern,
        }
        result = self.rules_parser.parse(
            [entry], namespace="test", source_path="<fuzz>"
        )
        assert isinstance(result, list)

    @given(pattern=st.text(max_size=100))
    @PARSER_SETTINGS
    def test_injections_detect_bad_regex(self, pattern):
        """Invalid regex in injection detect.pattern should not crash."""
        entry = {
            "id": "test_inj",
            "trigger": "PreToolUse/Bash",
            "detect": {"pattern": pattern},
        }
        result = self.injections_parser.parse(
            [entry], namespace="test", source_path="<fuzz>"
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: Return type invariants
# ---------------------------------------------------------------------------


class TestReturnTypeInvariants:
    """Verify structural invariants on successfully parsed objects."""

    @given(
        raw_id=st.text(alphabet=string.ascii_letters + "_", min_size=1, max_size=20),
        trigger=st.text(min_size=1, max_size=30),
        namespace=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=15),
    )
    @PARSER_SETTINGS
    def test_rule_id_is_namespace_qualified(self, raw_id, trigger, namespace):
        """Parsed Rule.id should always be namespace:raw_id."""
        entry = {"id": raw_id, "trigger": trigger, "enforcement": "deny"}
        results = RulesParser().parse(
            [entry], namespace=namespace, source_path="<fuzz>"
        )
        for rule in results:
            assert rule.id.startswith(f"{namespace}:"), (
                f"Expected namespace prefix, got {rule.id}"
            )

    @given(
        raw_id=st.text(alphabet=string.ascii_letters + "_", min_size=1, max_size=20),
        check_type=st.text(
            alphabet=string.ascii_lowercase + "-", min_size=1, max_size=20
        ),
        namespace=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=15),
    )
    @PARSER_SETTINGS
    def test_check_id_is_namespace_qualified(self, raw_id, check_type, namespace):
        """Parsed CheckDecl.id should always be namespace:raw_id."""
        entry = {"id": raw_id, "type": check_type, "params": {}}
        results = ChecksParser().parse(
            [entry], namespace=namespace, source_path="<fuzz>"
        )
        for check in results:
            assert check.id.startswith(f"{namespace}:"), (
                f"Expected namespace prefix, got {check.id}"
            )

    @given(
        raw_id=st.text(alphabet=string.ascii_letters + "_", min_size=1, max_size=20),
        message=st.text(min_size=1, max_size=100),
        namespace=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=15),
    )
    @PARSER_SETTINGS
    def test_hint_id_is_namespace_qualified(self, raw_id, message, namespace):
        """Parsed HintDecl.id should always be namespace:raw_id."""
        entry = {"id": raw_id, "message": message, "lifecycle": "show-once"}
        results = HintsParser().parse(
            [entry], namespace=namespace, source_path="<fuzz>"
        )
        for hint in results:
            assert hint.id.startswith(f"{namespace}:"), (
                f"Expected namespace prefix, got {hint.id}"
            )
