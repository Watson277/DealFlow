from typing import Any, TypedDict

from pydantic import BaseModel, ValidationError

MAX_VALIDATION_DETAILS = 20

# Never copy ValidationError.msg: custom validators and JSON parsing errors can
# embed model output there, even when include_input/include_context are false.
_SAFE_MESSAGES = {
    "missing": "Required field is missing.",
    "extra_forbidden": "Remove fields not defined in the JSON Schema.",
    "json_invalid": "Return one complete valid JSON object without Markdown fences.",
    "model_type": "Expected an object matching the JSON Schema.",
    "dict_type": "Expected a JSON object.",
    "list_type": "Expected a JSON array.",
    "string_type": "Expected a string.",
    "string_too_short": "String is shorter than the schema minimum length.",
    "string_too_long": "String exceeds the schema maximum length.",
    "bool_type": "Expected a boolean (true or false).",
    "bool_parsing": "Expected a boolean (true or false).",
    "int_type": "Expected an integer.",
    "int_parsing": "Expected an integer.",
    "int_from_float": "Expected an integer, not a fractional number.",
    "float_type": "Expected a number.",
    "float_parsing": "Expected a number.",
    "finite_number": "Expected a finite number.",
    "greater_than_equal": "Value must be at least the schema minimum.",
    "less_than_equal": "Value must not exceed the schema maximum.",
    "greater_than": "Value must exceed the schema exclusive minimum.",
    "less_than": "Value must be below the schema exclusive maximum.",
    "literal_error": "Use one of the allowed values in the JSON Schema.",
    "enum": "Use one of the allowed values in the JSON Schema.",
    "too_short": "Collection has fewer items than the schema permits.",
    "too_long": "Collection has more items than the schema permits.",
    "value_error": "A field or cross-field validation rule failed.",
}
_PAGE_RANGE_MESSAGE = "source_page_end must not precede source_page_start"


class ValidationIssue(TypedDict):
    loc: list[str | int]
    type: str
    msg: str


def _schema_field_names(schema: Any) -> set[str]:
    if isinstance(schema, list):
        return set().union(*(_schema_field_names(item) for item in schema))
    if not isinstance(schema, dict):
        return set()
    names = set(schema.get("properties", {}))
    for value in schema.values():
        names.update(_schema_field_names(value))
    return names


def validation_details(
    exc: ValidationError, output_model: type[BaseModel]
) -> list[ValidationIssue]:
    """Bounded diagnostics containing only trusted schema names and messages."""
    field_names = _schema_field_names(output_model.model_json_schema())
    details: list[ValidationIssue] = []
    for error in exc.errors(include_input=False, include_context=False, include_url=False)[
        :MAX_VALIDATION_DETAILS
    ]:
        error_type = error["type"]
        message = _SAFE_MESSAGES.get(error_type, "Value does not match the JSON Schema.")
        if error_type == "value_error" and error["msg"] == f"Value error, {_PAGE_RANGE_MESSAGE}":
            message = _PAGE_RANGE_MESSAGE
        # Extra keys and mapping keys originate in model output; they may contain
        # private document text. Only schema-defined field names can be logged.
        location: list[str | int] = [
            part if isinstance(part, int) or part in field_names else "<unknown_field>"
            for part in error["loc"]
        ]
        details.append(
            {
                "loc": location,
                "type": error_type if error_type in _SAFE_MESSAGES else "validation_error",
                "msg": message,
            }
        )
    return details
