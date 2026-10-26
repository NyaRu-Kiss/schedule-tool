import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

from llm import IntentParseError, OpenAICompatibleIntentParser, intent_parser_from_env


def completion(intent):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": json.dumps(intent)}}]}
    return response


class IntentParserTests(unittest.TestCase):
    def setUp(self):
        self.intent = {
            "title": "写周报", "date": "2040-10-10", "start_time": None,
            "duration_min": None, "reminder_requested": False, "reminder_minutes": None,
            "timezone": "Asia/Shanghai", "needs_clarification": False,
            "clarification_question": None,
        }

    def test_openai_compatible_request_uses_configured_model_and_schema(self):
        post = Mock(return_value=completion(self.intent))
        parser = OpenAICompatibleIntentParser("https://llm.test/v1/", "model-a", "secret", post=post)
        result = parser.parse("明天帮我安排写周报", timezone="Asia/Shanghai", today=date(2040, 10, 9))
        self.assertEqual(result, self.intent)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://llm.test/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "model-a")
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(json.loads(kwargs["json"]["messages"][1]["content"]), {
            "text": "明天帮我安排写周报", "timezone": "Asia/Shanghai", "today": "2040-10-09"})

    def test_ambiguity_is_returned_as_a_question(self):
        intent = dict(self.intent, needs_clarification=True,
                      clarification_question="你希望安排在哪一天？")
        parser = OpenAICompatibleIntentParser("https://llm.test/v1", "m", "k",
                                               post=Mock(return_value=completion(intent)))
        self.assertEqual(parser.parse("安排一下", timezone="UTC", today=date(2040, 1, 1)), intent)

    def test_invalid_schema_or_date_is_rejected(self):
        for intent in (dict(self.intent, extra="field"),
                       dict(self.intent, date="2040-02-31"),
                       dict(self.intent, needs_clarification=True, clarification_question=None),
                       dict(self.intent, duration_min=True)):
            parser = OpenAICompatibleIntentParser("https://llm.test/v1", "m", "k",
                                                   post=Mock(return_value=completion(intent)))
            with self.subTest(intent=intent), self.assertRaises(IntentParseError):
                parser.parse("x", timezone="UTC", today=date(2040, 1, 1))

    def test_environment_config_can_be_replaced_and_must_be_complete(self):
        post = Mock(return_value=completion(self.intent))
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_BASE_URL": "https://first.test/v1",
            "SCHEDULE_LLM_MODEL": "first", "SCHEDULE_LLM_API_KEY": "first-key"}, clear=True):
            first = intent_parser_from_env(post=post)
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_BASE_URL": "https://second.test/v1",
            "SCHEDULE_LLM_MODEL": "second", "SCHEDULE_LLM_API_KEY": "second-key"}, clear=True):
            second = intent_parser_from_env(post=post)
        first.parse("x", timezone="UTC", today=date(2040, 1, 1))
        second.parse("x", timezone="UTC", today=date(2040, 1, 1))
        self.assertEqual([call.args[0] for call in post.call_args_list], [
            "https://first.test/v1/chat/completions", "https://second.test/v1/chat/completions"])
        with patch.dict("os.environ", {"SCHEDULE_LLM_MODEL": "partial"}, clear=True):
            with self.assertRaises(IntentParseError):
                intent_parser_from_env(post=post)

    def test_deepseek_provider_uses_defaults_and_key(self):
        post = Mock(return_value=completion(self.intent))
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_PROVIDER": "deepseek",
            "SCHEDULE_LLM_API_KEY": "deepseek-key",
        }, clear=True):
            parser = intent_parser_from_env(post=post)
        parser.parse("安排写周报", timezone="Asia/Shanghai", today=date(2040, 10, 9))
        self.assertEqual(parser.provider, "deepseek")
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-chat")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer deepseek-key")

    def test_provider_can_switch_to_openai_or_custom(self):
        post = Mock(return_value=completion(self.intent))
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_PROVIDER": "openai", "SCHEDULE_LLM_API_KEY": "openai-key",
        }, clear=True):
            parser = intent_parser_from_env(post=post)
        self.assertEqual(parser.base_url, "https://api.openai.com/v1")
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_PROVIDER": "custom", "SCHEDULE_LLM_BASE_URL": "https://local.test/v1",
            "SCHEDULE_LLM_MODEL": "local-model", "SCHEDULE_LLM_API_KEY": "local-key",
        }, clear=True):
            parser = intent_parser_from_env(post=post)
        self.assertEqual((parser.provider, parser.base_url, parser.model),
                         ("custom", "https://local.test/v1", "local-model"))

    def test_unknown_provider_is_rejected(self):
        with patch.dict("os.environ", {
            "SCHEDULE_LLM_PROVIDER": "unknown", "SCHEDULE_LLM_API_KEY": "key",
        }, clear=True):
            with self.assertRaises(IntentParseError):
                intent_parser_from_env()

    def test_common_provider_aliases_and_omissions_are_normalized(self):
        response = completion({
            "title": "写周报", "date": "2040-10-10", "start_time": "14:00",
            "duration_min": 30, "reminder_min": 5,
            "needs_clarification": False, "clarification_question": None,
        })
        parser = OpenAICompatibleIntentParser("https://llm.test/v1", "m", "k",
                                             post=Mock(return_value=response))
        result = parser.parse("明天下午写周报并提醒", timezone="Asia/Shanghai", today=date(2040, 10, 9))
        self.assertEqual(result["reminder_minutes"], 5)
        self.assertTrue(result["reminder_requested"])
        self.assertEqual(result["timezone"], "Asia/Shanghai")


if __name__ == "__main__":
    unittest.main()
