FAILURE_MESSAGES = {
    "extract": "Text extraction failed.",
    "merge": "PDF merge failed.",
    "compare": "Document comparison failed.",
    "extract_pages": "Page extraction failed.",
    "split": "PDF split failed.",
}


def job_failure_message(operation: str) -> str:
    return FAILURE_MESSAGES.get(operation, "Operation failed.")
