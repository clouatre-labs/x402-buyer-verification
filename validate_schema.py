"""
Validate schema of experiment analysis.json files.

Checks that every experiments/*/analysis.json contains the required
top-level fields with correct scalar types, ISO date/timestamp formats,
enum values, token totals consistency, a well-formed scores object, and
that the `experiment` field matches the parent directory slug. Certain
fields are nullable (allowed to be null) while others must have values.

Usage:
    uv run python validate_schema.py [--self-test] [FILE ...]

With no FILE arguments, discovers and validates all
experiments/*/analysis.json files under the repository root.

Exits with 0 if all files pass validation, 1 if any validation fails.

Standard library only; no third-party imports.
"""

import datetime
import json
import math
import pathlib
import re
import shutil
import sys
import tempfile

# Top-level fields that are allowed to be null.
NULLABLE_TOP_FIELDS = {"issue", "orchestrator_session"}

# Run-record fields that are allowed to be null.
NULLABLE_RUN_FIELDS = {"bytes", "note"}

# Top-level fields required to be non-null strings.
STRING_TOP_FIELDS = [
    "schema_version",
    "title",
    "date",
    "model",
    "control_condition",
    "treatment_condition",
    "rubric_version",
    "repo_head",
    "experiment_start",
    "experiment_end",
    "analyzed_at",
    "statistical_test",
    "conclusion",
]

# Top-level fields required to be non-null integers (bool is not an int here).
INTEGER_TOP_FIELDS = ["n_per_group"]

# ISO date (YYYY-MM-DD) and ISO 8601 timestamp formats enforced on top fields.
DATE_TOP_FIELDS = ["date"]
TIMESTAMP_TOP_FIELDS = ["experiment_start", "experiment_end", "analyzed_at"]

REQUIRED_TOP_FIELDS = [
    "experiment",
    *STRING_TOP_FIELDS[:2],
    "issue",
    *STRING_TOP_FIELDS[2:],
    *INTEGER_TOP_FIELDS,
    "orchestrator_session",
    "runs",
    "scores",
    "pre_acknowledged_limitations",
]

REQUIRED_RUN_FIELDS = [
    "group",
    "session_id",
    "messages",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "wall_clock_seconds",
    "bytes",
    "note",
]

# Integer run-record fields (bool is not accepted as an integer).
INTEGER_RUN_FIELDS = ["messages", "input_tokens", "output_tokens", "total_tokens"]

# Number run-record fields (int or float).
NUMBER_RUN_FIELDS = ["wall_clock_seconds"]

ALLOWED_GROUPS = {"control", "treatment"}

# Record type discriminator: absent means "model-run" (original schema).
ALLOWED_RECORD_TYPES = {"model-run", "payment-run"}

# payment-run top-level: tool/SDK versions object (required string values).
REQUIRED_VERSION_KEYS = ["bun", "node", "x402_fetch", "x402_evm"]
OPTIONAL_VERSION_KEYS = ["anvil_fork_block", "anvil"]

# payment-run run-record fields.
HEX64_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
NULLABLE_PAYMENT_RUN_FIELDS = {"note", "receipt", "tx_hash"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")


def _reject_constant(name):
    """json.loads parse_constant hook: reject NaN/Infinity tokens."""
    raise ValueError(f"invalid JSON constant {name}")


def _load_json_strict(text):
    return json.loads(text, parse_constant=_reject_constant)


def _is_finite_number(value):
    """True for a non-bool int or float that is finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_timestamp(value):
    """Accept only full ISO 8601 timestamps with a UTC offset."""
    if not TIMESTAMP_RE.match(value):
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return False
    return True


def validate_top_level(data):
    """Check required keys, scalar types, and date/timestamp formats."""
    errors = []
    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            errors.append(f"missing top-level field {field}")
            continue
        value = data[field]
        if value is None and field not in NULLABLE_TOP_FIELDS:
            errors.append(f"top-level field {field} is null")
    for field in STRING_TOP_FIELDS:
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string")
    for field in INTEGER_TOP_FIELDS:
        if not _is_int(data.get(field)):
            errors.append(f"top-level field {field} is not an integer")
    for field in DATE_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not DATE_RE.match(value):
            errors.append(f"top-level field {field} is not an ISO date (YYYY-MM-DD)")
        elif isinstance(value, str):
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                errors.append(f"top-level field {field} is not a valid calendar date")
    for field in ("issue", "orchestrator_session"):
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string or null")
    for field in TIMESTAMP_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not _parse_timestamp(value):
            errors.append(f"top-level field {field} is not an ISO 8601 timestamp")
    limitations = data.get("pre_acknowledged_limitations")
    if limitations is not None:
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) for item in limitations
        ):
            errors.append(
                "top-level field pre_acknowledged_limitations is not an array of strings"
            )
    experiment = data.get("experiment")
    if experiment is not None and not isinstance(experiment, str):
        errors.append("top-level field experiment is not a string")
    return errors


def validate_runs(runs):
    """Check run record structure, enum values, and token totals."""
    errors = []
    if not isinstance(runs, dict):
        return [f"runs is not an object: {type(runs).__name__}"]
    for run_id, record in runs.items():
        if not isinstance(record, dict):
            errors.append(f"run {run_id} is not an object")
            continue
        for field in REQUIRED_RUN_FIELDS:
            if field not in record:
                errors.append(f"run {run_id} missing {field}")
            elif record[field] is None and field not in NULLABLE_RUN_FIELDS:
                errors.append(f"run {run_id} has null {field}")
        group = record.get("group")
        if group is not None and not isinstance(group, str):
            errors.append(f"run {run_id} group is not a string")
        elif group is not None and group not in ALLOWED_GROUPS:
            errors.append(
                f"run {run_id} group {group!r} not in {sorted(ALLOWED_GROUPS)}"
            )
        for field in INTEGER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_int(value):
                errors.append(f"run {run_id} field {field} is not an integer")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in NUMBER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_finite_number(value):
                errors.append(f"run {run_id} field {field} is not a finite number")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in ("session_id", "note"):
            if field in record and record[field] is not None and not isinstance(record[field], str):
                errors.append(f"run {run_id} field {field} is not a string or null")
        if "bytes" in record and record["bytes"] is not None and not _is_int(record["bytes"]):
            errors.append(f"run {run_id} field bytes is not an integer or null")
        elif "bytes" in record and record["bytes"] is not None and record["bytes"] < 0:
            errors.append(f"run {run_id} field bytes is negative")
        if (
            _is_int(record.get("input_tokens"))
            and _is_int(record.get("output_tokens"))
            and _is_int(record.get("total_tokens"))
            and record["input_tokens"] + record["output_tokens"] != record["total_tokens"]
        ):
            errors.append(f"run {run_id} total_tokens != input_tokens + output_tokens")
    return errors


def validate_scores(scores, runs):
    """Check the scores object shape: dict of run ID to dict."""
    errors = []
    if not isinstance(scores, dict):
        errors.append(f"scores is not an object: {type(scores).__name__}")
        return errors
    known = set(runs) if isinstance(runs, dict) else set()
    for run_id, entry in scores.items():
        if not isinstance(entry, dict):
            errors.append(f"scores[{run_id}] is not an object")
        if run_id not in known:
            errors.append(f"scores key {run_id} does not match any run ID")
    return errors


def validate_record_type(data):
    """Check the optional record_type discriminator."""
    errors = []
    value = data.get("record_type", "model-run")
    if not isinstance(value, str):
        errors.append("top-level field record_type is not a string")
    elif value not in ALLOWED_RECORD_TYPES:
        errors.append(
            f"top-level field record_type {value!r} not in {sorted(ALLOWED_RECORD_TYPES)}"
        )
    return errors


def validate_payment_top_level(data):
    """payment-run top-level extras: versions object and rpc_endpoints array."""
    errors = []
    versions = data.get("versions")
    if not isinstance(versions, dict):
        errors.append("top-level field versions is not an object")
    else:
        for key in REQUIRED_VERSION_KEYS:
            value = versions.get(key)
            if value is None:
                errors.append(f"versions is missing required key {key}")
            elif not isinstance(value, str):
                errors.append(f"versions[{key}] is not a string")
        for key in OPTIONAL_VERSION_KEYS:
            value = versions.get(key)
            if value is not None and not isinstance(value, str):
                errors.append(f"versions[{key}] is not a string or null")
    endpoints = data.get("rpc_endpoints")
    if not isinstance(endpoints, list) or not all(isinstance(e, str) for e in endpoints):
        errors.append("top-level field rpc_endpoints is not an array of strings")
    elif not endpoints:
        errors.append("top-level field rpc_endpoints is empty")
    return errors


def validate_payment_runs(runs):
    """Check payment-run record structure: settlement identity and receipt."""
    errors = []
    if not isinstance(runs, dict):
        return [f"runs is not an object: {type(runs).__name__}"]
    for run_id, record in runs.items():
        if not isinstance(record, dict):
            errors.append(f"run {run_id} is not an object")
            continue
        required = ["mode", "tx_hash", "payer", "pay_to", "amount_usdc", "receipt"]
        for field in required:
            if field not in record:
                errors.append(f"run {run_id} missing {field}")
        settled = record.get("settled")
        if not isinstance(settled, bool):
            errors.append(f"run {run_id} field settled is not a boolean")
            settled = None
        tx_hash = record.get("tx_hash")
        if tx_hash is not None and not isinstance(tx_hash, str):
            errors.append(f"run {run_id} field tx_hash is not a string or null")
        elif tx_hash is not None and not HEX64_RE.match(tx_hash):
            errors.append(f"run {run_id} field tx_hash is not a 0x-prefixed 32-byte hex hash")
        elif tx_hash is None and "tx_hash" in record and settled is not False:
            errors.append(
                f"run {run_id} has null tx_hash (allowed only when settled is false)"
            )
        for field in ("payer", "pay_to"):
            value = record.get(field)
            if value is None:
                errors.append(f"run {run_id} has null {field}")
            elif not isinstance(value, str):
                errors.append(f"run {run_id} field {field} is not a string")
            elif not ADDRESS_RE.match(value):
                errors.append(f"run {run_id} field {field} is not a 0x-prefixed 20-byte address")
        amount = record.get("amount_usdc")
        if amount is None:
            errors.append(f"run {run_id} has null amount_usdc")
        elif not _is_finite_number(amount):
            errors.append(f"run {run_id} field amount_usdc is not a finite number")
        elif amount < 0:
            errors.append(f"run {run_id} field amount_usdc is negative")
        receipt = record.get("receipt")
        if receipt is not None and not isinstance(receipt, dict):
            errors.append(f"run {run_id} field receipt is not an object or null")
        elif receipt is None and settled is True:
            errors.append(
                f"run {run_id} has null receipt (required when settled is true)"
            )
        mode = record.get("mode")
        if mode is not None and not isinstance(mode, str):
            errors.append(f"run {run_id} field mode is not a string")
        value = record.get("wall_clock_seconds")
        if "wall_clock_seconds" in record and value is not None:
            if not _is_finite_number(value):
                errors.append(f"run {run_id} field wall_clock_seconds is not a finite number")
            elif value < 0:
                errors.append(f"run {run_id} field wall_clock_seconds is negative")
        note = record.get("note")
        if note is not None and not isinstance(note, str):
            errors.append(f"run {run_id} field note is not a string or null")
    return errors


def validate_record(data, expected_slug=None):
    """Validate a full analysis.json record.

    If expected_slug is given, the `experiment` field must equal it.
    """
    if not isinstance(data, dict):
        return [f"top-level JSON value is not an object: {type(data).__name__}"]
    errors = validate_top_level(data)
    errors.extend(validate_record_type(data))
    record_type = data.get("record_type", "model-run")
    if record_type == "payment-run":
        errors.extend(validate_payment_top_level(data))
        errors.extend(validate_payment_runs(data.get("runs")))
    else:
        runs = data.get("runs")
        errors.extend(validate_runs(runs))
    errors.extend(validate_scores(data.get("scores"), data.get("runs")))
    if (
        expected_slug is not None
        and isinstance(data.get("experiment"), str)
        and data["experiment"] != expected_slug
    ):
        errors.append(
            f"experiment {data['experiment']!r} does not match directory slug {expected_slug!r}"
        )
    return errors


def validate_path(path):
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_record(data, expected_slug=pathlib.Path(path).parent.name)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


MINIMAL_VALID_RECORD = {
    "experiment": "exp-example",
    "schema_version": "1.0.0",
    "title": "Example Experiment",
    "issue": None,
    "date": "2026-01-01",
    "model": "model-under-test",
    "n_per_group": 5,
    "control_condition": "standard instructions",
    "treatment_condition": "modified instructions",
    "rubric_version": "rubric-v1",
    "orchestrator_session": None,
    "repo_head": "0000000000000000000000000000000000000000",
    "experiment_start": "2026-01-01T00:00:00Z",
    "experiment_end": "2026-01-01T01:00:00Z",
    "analyzed_at": "2026-01-02T00:00:00Z",
    "runs": {
        "control_1": {
            "group": "control",
            "session_id": "20260101_01",
            "messages": 10,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "wall_clock_seconds": 30,
            "bytes": 1024,
            "note": None,
        }
    },
    "scores": {"control_1": {"pass": True}},
    "statistical_test": "fisher-exact",
    "conclusion": "No effect observed.",
    "pre_acknowledged_limitations": ["small sample size"],
}


MINIMAL_VALID_PAYMENT_RECORD = {
    "experiment": "exp-payment",
    "schema_version": "1.0.0",
    "record_type": "payment-run",
    "title": "Example Payment Experiment",
    "issue": None,
    "date": "2026-01-01",
    "model": "none",
    "n_per_group": 1,
    "control_condition": "baseline decode",
    "treatment_condition": "paid settlement",
    "rubric_version": "rubric-v1",
    "orchestrator_session": None,
    "repo_head": "0000000000000000000000000000000000000000",
    "experiment_start": "2026-01-01T00:00:00Z",
    "experiment_end": "2026-01-01T01:00:00Z",
    "analyzed_at": "2026-01-02T00:00:00Z",
    "versions": {
        "bun": "1.4.0",
        "node": "26.13.0",
        "x402_fetch": "2.29.0",
        "x402_evm": "2.29.0",
        "anvil_fork_block": None,
    },
    "rpc_endpoints": ["https://mainnet.base.org", "https://base.publicnode.com"],
    "runs": {
        "run_1": {
            "mode": "happy-path",
            "settled": True,
            "tx_hash": "0x" + "c6e5" * 16,
            "payer": "0x" + "d0d4" * 10,
            "pay_to": "0x" + "1693" * 10,
            "amount_usdc": 0.01,
            "receipt": {"success": True, "transaction": "0x" + "c6e5" * 16},
            "wall_clock_seconds": 3.5,
            "note": None,
        }
    },
    "scores": {"run_1": {"pass": True}},
    "statistical_test": "descriptive-only",
    "conclusion": "Verification passed.",
    "pre_acknowledged_limitations": ["single settlement"],
}


def _mutated(**changes):
    record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = record
        for part in parts[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[parts[-1]]
        else:
            target[parts[-1]] = value
    return record


def _mutated_payment(**changes):
    record = _load_json_strict(json.dumps(MINIMAL_VALID_PAYMENT_RECORD))
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = record
        for part in parts[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[parts[-1]]
        else:
            target[parts[-1]] = value
    return record


class _Delete:
    pass


_DELETE = _Delete()


def _expect_errors(record, substring, label):
    errors = validate_record(record)
    if not any(substring in error for error in errors):
        print(f"self-test FAILED: {label} not caught: {errors}")
        return False
    return True


def self_test():
    if validate_record(MINIMAL_VALID_RECORD):
        print("self-test FAILED: minimal valid record reported errors")
        return False
    if validate_record(MINIMAL_VALID_RECORD, expected_slug="exp-example"):
        print("self-test FAILED: valid record with matching slug reported errors")
        return False
    cases = [
        (_mutated(title=_DELETE), "missing top-level field title", "missing required key"),
        (_mutated(title=42), "title is not a string", "wrong scalar type"),
        (_mutated(n_per_group=True), "n_per_group is not an integer", "bool not int"),
        (_mutated(n_per_group=1.5), "n_per_group is not an integer", "float not int"),
        (_mutated(date="2026-13-45"), "not a valid calendar date", "invalid date format"),
        (_mutated(date="not-a-date"), "not an ISO date", "non-date string"),
        (_mutated(date="2026-02-30"), "not a valid calendar date", "impossible calendar date"),
        (_mutated(analyzed_at="01/02/2026T00:00:00Z"), "not an ISO 8601 timestamp", "bad timestamp"),
        (
            _mutated(runs__control_1={"group": "placebo"}),
            "not in ['control', 'treatment']",
            "invalid group enum",
        ),
        (
            _mutated(runs__control_1__total_tokens=999),
            "total_tokens != input_tokens + output_tokens",
            "token totals mismatch",
        ),
        (
            _mutated(runs__control_1__messages="ten"),
            "messages is not an integer",
            "non-integer run field",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds="slow"),
            "wall_clock_seconds is not a finite number",
            "non-number wall clock",
        ),
        (
            _mutated(runs__control_1__group=_DELETE),
            "run control_1 missing group",
            "missing run field",
        ),
        (_mutated(scores=[]), "scores is not an object", "scores wrong container"),
        (
            _mutated(scores={"control_1": "pass"}),
            "scores[control_1] is not an object",
            "score entry not object",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}),
            "does not match any run ID",
            "unknown scores key",
        ),
        (
            _mutated(pre_acknowledged_limitations=[1, 2]),
            "not an array of strings",
            "non-string limitation",
        ),
        ([MINIMAL_VALID_RECORD], "not an object: list", "array top level"),
        ("not-an-object", "not an object: str", "scalar top level"),
        (
            _mutated(runs__control_1__group=[]),
            "run control_1 group is not a string",
            "non-hashable group value",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=True),
            "wall_clock_seconds is not a finite number",
            "boolean wall clock",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=-1.5),
            "wall_clock_seconds is negative",
            "negative wall clock",
        ),
        (
            _mutated(runs__control_1__input_tokens=-10),
            "input_tokens is negative",
            "negative input tokens",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}, runs={}),
            "scores key unknown-run does not match any run ID",
            "orphan score key with zero runs",
        ),
        (
            _mutated(runs__control_1__session_id=42),
            "session_id is not a string or null",
            "non-string session_id",
        ),
        (
            _mutated(runs__control_1__bytes="big"),
            "bytes is not an integer or null",
            "non-integer bytes",
        ),
        (
            _mutated(runs__control_1__note=3.14),
            "note is not a string or null",
            "non-string note",
        ),
        (
            _mutated(analyzed_at="2026-01-02T00:00:00"),
            "not an ISO 8601 timestamp",
            "naive timestamp without offset",
        ),
        (
            _mutated(analyzed_at="2026-01-02"),
            "not an ISO 8601 timestamp",
            "date-only timestamp",
        ),
    ]
    for record, substring, label in cases:
        if not _expect_errors(record, substring, label):
            return False
    nan_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    nan_record["runs"]["control_1"]["wall_clock_seconds"] = float("nan")
    if not _expect_errors(
        nan_record, "wall_clock_seconds is not a finite number", "NaN wall clock"
    ):
        return False
    inf_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    inf_record["runs"]["control_1"]["wall_clock_seconds"] = float("inf")
    if not _expect_errors(
        inf_record, "wall_clock_seconds is not a finite number", "Infinity wall clock"
    ):
        return False
    accepted = [
        (_mutated(issue=None), "null issue accepted"),
        (_mutated(orchestrator_session=None), "null orchestrator_session accepted"),
        (_mutated(runs__control_1__bytes=None), "null bytes accepted"),
        (_mutated(runs__control_1__note=None), "null note accepted"),
        (_mutated(analyzed_at="2026-01-02T00:00:00+00:00"), "offset timestamp accepted"),
    ]
    for record, label in accepted:
        if validate_record(record):
            print(f"self-test FAILED: {label}: {validate_record(record)}")
            return False
    slug_record = json.loads(json.dumps(MINIMAL_VALID_RECORD))
    slug_record["experiment"] = "exp-other"
    slug_errors = validate_record(slug_record, expected_slug="exp-example")
    if not any("does not match directory slug" in error for error in slug_errors):
        print(f"self-test FAILED: slug mismatch not caught: {slug_errors}")
        return False
    # Discovery mode: missing analysis.json must fail, empty experiments/ passes.
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        missing = base / "experiments" / "exp-missing"
        missing.mkdir(parents=True)
        present = base / "experiments" / "exp-present"
        present.mkdir()
        record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
        record["experiment"] = "exp-present"
        (present / "analysis.json").write_text(json.dumps(record))
        if validate_discovery(base):
            print("self-test FAILED: discovery accepted missing analysis.json")
            return False
        empty_base = pathlib.Path(tempfile.mkdtemp())
        try:
            (empty_base / "experiments").mkdir()
            if not validate_discovery(empty_base):
                print("self-test FAILED: discovery rejected empty experiments dir")
                return False
        finally:
            shutil.rmtree(empty_base)
    # payment-run branch: valid record, then edge cases.
    if validate_record(MINIMAL_VALID_PAYMENT_RECORD):
        print("self-test FAILED: minimal valid payment record reported errors")
        return False
    if validate_record(
        MINIMAL_VALID_PAYMENT_RECORD, expected_slug="exp-payment"
    ):
        print("self-test FAILED: valid payment record with matching slug reported errors")
        return False
    payment_cases = [
        (
            _mutated_payment(runs__run_1__tx_hash=_DELETE),
            "run run_1 missing tx_hash",
            "payment missing tx_hash",
        ),
        (
            _mutated_payment(runs__run_1__payer="0x1234"),
            "payer is not a 0x-prefixed 20-byte address",
            "payment non-hex payer",
        ),
        (
            _mutated_payment(runs__run_1__tx_hash=None),
            "null tx_hash (allowed only when settled is false)",
            "payment null tx_hash with settled true",
        ),
        (
            _mutated_payment(runs__run_1__pay_to="not-hex"),
            "pay_to is not a 0x-prefixed 20-byte address",
            "payment non-hex pay_to",
        ),
        (
            _mutated_payment(runs__run_1__amount_usdc="cheap"),
            "amount_usdc is not a finite number",
            "payment non-numeric amount",
        ),
        (
            _mutated_payment(runs__run_1__receipt=None),
            "null receipt (required when settled is true)",
            "payment null receipt when settled",
        ),
        (
            _mutated_payment(versions__bun=None),
            "versions is missing required key bun",
            "payment missing version key",
        ),
        (
            _mutated_payment(rpc_endpoints=[]),
            "rpc_endpoints is empty",
            "payment empty rpc endpoints",
        ),
        (
            _mutated(record_type="barter"),
            "record_type 'barter' not in",
            "unknown record_type",
        ),
        (
            _mutated_payment(runs__run_1__settled="yes"),
            "field settled is not a boolean",
            "payment non-boolean settled",
        ),
    ]
    for record, substring, label in payment_cases:
        if not _expect_errors(record, substring, label):
            return False
    unpaid_payment = _mutated_payment(
        record_type="payment-run",
        runs__run_1={
            "mode": "decode-only",
            "settled": False,
            "tx_hash": None,
            "payer": "0x" + "d0d4" * 10,
            "pay_to": "0x" + "1693" * 10,
            "amount_usdc": 0,
            "receipt": None,
            "wall_clock_seconds": 0.2,
            "note": "unpaid discovery iteration",
        },
    )
    if validate_record(unpaid_payment):
        print(f"self-test FAILED: unpaid payment run rejected: {validate_record(unpaid_payment)}")
        return False
    print(
        "self-test passed: valid record accepted, each rule rejects its invalid case, discovery flags missing analysis.json"
    )
    return True


def validate_discovery(base):
    experiments_dir = pathlib.Path(base) / "experiments"
    if not experiments_dir.is_dir():
        print("No experiments/ directory found; nothing to validate.")
        return True
    exp_dirs = sorted(
        d
        for d in experiments_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not exp_dirs:
        print("No experiments/* directories found; nothing to validate.")
        return True
    all_ok = True
    for exp_dir in exp_dirs:
        analysis = exp_dir / "analysis.json"
        if not analysis.is_file():
            print(f"Validation error: missing {analysis}")
            all_ok = False
            continue
        if not validate_path(analysis):
            all_ok = False
    return all_ok


def main():
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    file_args = [arg for arg in sys.argv[1:] if arg != "--self-test"]
    if file_args:
        all_ok = all(validate_path(pathlib.Path(arg)) for arg in file_args)
        sys.exit(0 if all_ok else 1)
    sys.exit(0 if validate_discovery(pathlib.Path(".").resolve()) else 1)


if __name__ == "__main__":
    main()
