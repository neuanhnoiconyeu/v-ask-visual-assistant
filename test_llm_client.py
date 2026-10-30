"""Mocked checks for the configured Nebius chat-completions model."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from config import NEBIUS_MODEL
from llm_client import answer, request_change_proposal


class NebiusModelTests(unittest.TestCase):
    def _mock_client(self, content: str = "Model response") -> tuple[Mock, Mock]:
        create = Mock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )
        )
        client = Mock()
        client.chat.completions.create = create
        return client, create

    def test_configured_model_is_used_for_chat_answers(self):
        client, create = self._mock_client()
        with patch("llm_client._client", return_value=client):
            self.assertEqual(answer([{"role": "user", "content": "Hello"}]), "Model response")

        self.assertEqual(NEBIUS_MODEL, "zai-org/GLM-5.3-Flash")
        self.assertEqual(create.call_args.kwargs["model"], NEBIUS_MODEL)

    def test_configured_model_is_used_for_change_proposals(self):
        client, create = self._mock_client('{"schema_version": 1, "files": []}')
        with patch("llm_client._client", return_value=client):
            request_change_proposal("Explain the change", "app.py:1-1\npass", {"app.py": "abc"})

        self.assertEqual(create.call_args.kwargs["model"], NEBIUS_MODEL)


if __name__ == "__main__":
    unittest.main()
