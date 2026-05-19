import json
import unittest

from competitor_agents.llm_client import CustomLLMClient, extract_output_text, parse_json_object


class CustomLLMClientTest(unittest.TestCase):
    def test_extract_chat_completion_text(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": "{\"profiles\": [], \"comparison\": {}}"
                    }
                }
            ]
        }

        self.assertEqual(
            extract_output_text(response, "chat"),
            "{\"profiles\": [], \"comparison\": {}}",
        )

    def test_extract_responses_text(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "{\"report\": \"ok\"}",
                        }
                    ],
                }
            ]
        }

        self.assertEqual(extract_output_text(response, "responses"), "{\"report\": \"ok\"}")

    def test_parse_json_object_from_markdown_fence(self):
        parsed = parse_json_object("```json\n{\"report\": \"ok\"}\n```")
        self.assertEqual(parsed["report"], "ok")

    def test_chat_payload_shape(self):
        client = CustomLLMClient(
            api_url="http://localhost:9000/v1/chat/completions",
            model="my-model",
            api_format="chat",
        )
        payload = client._build_payload("sys", "user")

        self.assertEqual(payload["model"], "my-model")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["content"], "user")


if __name__ == "__main__":
    unittest.main()
