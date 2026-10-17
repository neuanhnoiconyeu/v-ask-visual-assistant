"""Prompt definitions and input formatting for developer assistant modes."""
from __future__ import annotations


MODE_INSTRUCTIONS = {
    "General chat": "",
    "Explain Code": (
        "Explain the supplied code in the user's language. Describe its purpose, flow, "
        "important functions, dependencies, and relevant edge cases. Be specific and "
        "use short code excerpts when they help. Do not claim to have run the code."
    ),
    "Debug Assistant": (
        "Diagnose the supplied code and error message. Identify likely root causes, "
        "distinguish evidence from hypotheses, and suggest specific fixes with concise "
        "code snippets. Ask for missing details only when needed. Do not claim to have "
        "run the code or verified a fix."
    ),
    "Code Review": (
        "Review the supplied code for correctness, readability, maintainability, "
        "performance, and security. Prioritize actionable findings, explain their "
        "impact, and include file/line references when supplied. If no issues are "
        "apparent, say so without implying execution or exhaustive verification."
    ),
    "Generate Tests": (
        "Generate relevant tests for the supplied code. Follow any framework, "
        "version, and conventions provided by the user; otherwise infer them only "
        "from supplied project context and state assumptions. Cover normal behavior, "
        "boundaries, and important failures. Provide code and explain how to run it, "
        "but never claim the tests were executed or passed."
    ),
}


def build_developer_request(
    prompt: str, code: str = "", error_message: str = "", additional_context: str = ""
) -> str:
    """Combine the chat request and optional structured developer inputs."""
    sections = []
    if prompt.strip():
        sections.append(prompt.strip())
    if code.strip():
        sections.append("Code:\n```\n" + code.strip() + "\n```")
    if error_message.strip():
        sections.append("Error message:\n" + error_message.strip())
    if additional_context.strip():
        sections.append("Additional context:\n" + additional_context.strip())
    return "\n\n".join(sections)
