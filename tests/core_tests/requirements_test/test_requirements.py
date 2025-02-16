import asyncio
import os
import unittest
from time import time
from unittest.mock import Mock, patch

import smart_kit
from core.basic_models.classifiers.basic_classifiers import ExternalClassifier
from core.basic_models.operators.operators import Operator
from core.basic_models.requirement.basic_requirements import Requirement, CompositeRequirement, AndRequirement, \
    OrRequirement, NotRequirement, RandomRequirement, TopicRequirement, TemplateRequirement, RollingRequirement, \
    TimeRequirement, DateTimeRequirement, IntersectionRequirement, ClassifierRequirement, FormFieldValueRequirement, \
    EnvironmentRequirement, CharacterIdRequirement, FeatureToggleRequirement
from core.basic_models.requirement.counter_requirements import CounterValueRequirement, CounterUpdateTimeRequirement
from core.basic_models.requirement.device_requirements import ChannelRequirement
from core.basic_models.requirement.user_text_requirements import AnySubstringInLoweredTextRequirement, \
    PhoneNumberNumberRequirement, NumInRangeRequirement, IntersectionWithTokensSetRequirement, \
    NormalizedTextInSetRequirement
from core.basic_models.variables.variables import Variables
from core.model.registered import registered_factories
from smart_kit.text_preprocessing.local_text_normalizer import LocalTextNormalizer
from smart_kit.utils.picklable_mock import PicklableMock


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def patch_get_app_config(mock_get_app_config):
    result = PicklableMock()
    sk_path = os.path.dirname(smart_kit.__file__)
    result.STATIC_PATH = os.path.join(sk_path, 'template/static')
    mock_get_app_config.return_value = result
    result.NORMALIZER = LocalTextNormalizer()
    result.ENVIRONMENT = "ift"
    mock_get_app_config.return_value = result


class MockRequirement(Requirement):
    def __init__(self, items=None, id=None):
        super().__init__(items, id)
        self.cond = items.get("cond") or False

    def _check(self, text_preprocessing_result, user, params=None):
        return self.cond


class TrueFalseRequirement(Requirement):
    def __init__(self, items=None, id=None):
        super().__init__(items, id)
        self.counter = 1

    def _check(self, text_preprocessing_result, user, params=None):
        self.counter += 1
        return self.counter % 2 == 0


class TrueCacheRequirement(Requirement):
    cache_result = True


class MockTextNormalizationResult:
    def __init__(self, normalized=None, number_of_numbers=None, currencies_number=None, tokens=None):
        number_of_numbers = number_of_numbers or 0
        currencies_number = currencies_number or 0
        if normalized:
            self.words_tokenized = list(token.get("text") for token in normalized)
            self.words_tokenized_set = set(self.words_tokenized)
        else:
            self.words_tokenized = list()
            self.words_tokenized_set = set()
        self.number_of_numbers = number_of_numbers
        self.currencies_number = currencies_number
        self.tokenized_elements_list = tokens


class MockAmountOperator:
    def __init__(self, items):
        self.amount = items["amount"]

    def compare(self, value):
        return value > self.amount


class MockOperator:
    def __init__(self, amount):
        self.amount = amount

    def compare(self, value):
        return value > self.amount


class EQMockOperator:
    def __init__(self, amount):
        self.amount = amount

    def compare(self, value):
        return value == self.amount


class RequirementTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        registered_factories[Requirement] = MockRequirement
        registered_factories[Operator] = MockAmountOperator

    @classmethod
    def tearDownClass(cls) -> None:
        registered_factories[Requirement] = Requirement
        registered_factories[Operator] = Operator

    def test_base(self):
        requirement = Requirement(None)
        assert requirement.check(None, None)

    def test_composite(self):
        requirement = CompositeRequirement({"requirements": [
            {"cond": True},
            {"cond": True}
        ]})
        self.assertTrue(requirement.check(None, None))

    def test_and_success(self):
        requirement = AndRequirement({"requirements": [
            {"cond": True},
            {"cond": True}
        ]})
        self.assertTrue(requirement.check(None, None))

    def test_and_fail(self):
        requirement = AndRequirement({"requirements": [
            {"cond": True},
            {"cond": False}
        ]})
        self.assertFalse(requirement.check(None, None))

    def test_or_success(self):
        requirement = OrRequirement({"requirements": [
            {"cond": True},
            {"cond": False}
        ]})
        self.assertTrue(requirement.check(None, None))

    def test_or_fail(self):
        requirement = OrRequirement({"requirements": [
            {"cond": False},
            {"cond": False}
        ]})
        self.assertFalse(requirement.check(None, None))

    def test_not_success(self):
        requirement = NotRequirement({"requirement": {"cond": False}})
        self.assertTrue(requirement.check(None, None))

    def test_not_fail(self):
        requirement = NotRequirement({"requirement": {"cond": True}})
        self.assertFalse(requirement.check(None, None))

    def test_channel_success(self):
        user = PicklableMock()
        message = Mock(channel="ch1")
        user.message = message
        requirement = ChannelRequirement({"channels": ["ch1"]})
        text_normalization_result = None
        self.assertTrue(requirement.check(text_normalization_result, user))

    def test_channel_fail(self):
        user = PicklableMock()
        message = Mock(channel="ch2")
        user.message = message
        requirement = ChannelRequirement({"channels": ["ch1"]})
        text_normalization_result = None
        self.assertFalse(requirement.check(text_normalization_result, user))

    def test_random_requirement_true(self):
        requirement = RandomRequirement({"percent": 100})
        self.assertTrue(requirement.check(None, None))

    def test_random_requirement_false(self):
        requirement = RandomRequirement({"percent": 0})
        self.assertFalse(requirement.check(None, None))

    def test_topic_requirement(self):
        requirement = TopicRequirement({"topics": ["test"]})
        requirement.cache_result = False
        user = PicklableMock()
        message = PicklableMock()
        message.topic_key = "test"
        user.message = message
        self.assertTrue(requirement.check(None, user))

    def test_counter_value_requirement(self):
        user = PicklableMock()
        counter = PicklableMock()
        counter.__gt__ = Mock(return_value=True)
        user.counters = {"test": counter}
        requirement = CounterValueRequirement({"operator": {"type": "equal", "amount": 2}, "key": "test"})
        self.assertTrue(requirement.check(None, user))

    def test_counter_time_requirement(self):
        user = PicklableMock()
        counter = PicklableMock()
        counter.update_time = int(time()) - 10
        user.counters = {"test": counter}
        requirement = CounterUpdateTimeRequirement({"operator": {"type": "more_or_equal", "amount": 5}, "key": "test"})
        self.assertTrue(requirement.check(None, user))

    def test_template_req_true(self):
        items = {
            "template": "{{ payload.message.strip() in payload.murexIds }}"
        }
        requirement = TemplateRequirement(items)
        params = {"payload": {
            "groupCode": "BROKER",
            "murexIds": ["AAA", "BBB"],
            "message": " BBB    "
        }}
        user = PicklableMock()
        user.parametrizer = PicklableMock()
        user.parametrizer.collect = Mock(return_value=params)
        self.assertTrue(requirement.check(None, user))

    def test_template_req_false(self):
        items = {
            "template": "{{ payload.groupCode == 'BROKER' }}"
        }
        requirement = TemplateRequirement(items)
        params = {"payload": {"groupCode": "BROKER1"}}
        user = PicklableMock()
        user.parametrizer = PicklableMock()
        user.parametrizer.collect = Mock(return_value=params)
        self.assertFalse(requirement.check(None, user))

    def test_template_req_raise(self):
        items = {
            "template": "{{ payload.groupCode }}"
        }
        requirement = TemplateRequirement(items)
        params = {"payload": {"groupCode": "BROKER1"}}
        user = PicklableMock()
        user.parametrizer = PicklableMock()
        user.parametrizer.collect = Mock(return_value=params)
        with self.assertRaises(TypeError):
            _ = requirement.check(None, user)

    def test_rolling_requirement_true(self):
        user = PicklableMock()
        user.id = "353454"
        requirement = RollingRequirement({"percent": 100})
        requirement.cache_result = False
        text_normalization_result = None
        self.assertTrue(requirement.check(text_normalization_result, user))

    def test_rolling_requirement_false(self):
        user = PicklableMock()
        user.id = "353454"
        requirement = RollingRequirement({"percent": 0})
        requirement.cache_result = False
        text_normalization_result = None
        self.assertFalse(requirement.check(text_normalization_result, user))

    def test_time_requirement_true(self):
        user = PicklableMock()
        user.id = "353454"
        user.message.payload = {
            "meta": {
                "time": {
                    "timestamp": 1610990255000,  # ~ 2021-01-18 17:17:35
                    "timezone_offset_sec": 1000000000,  # shouldn't affect
                }
            }
        }
        requirement = TimeRequirement(
            {
                "operator": {
                    "type": "more",
                    "amount": "17:00:00",
                }
            }
        )
        requirement.cache_result = False
        text_normalization_result = None
        self.assertTrue(requirement.check(text_normalization_result, user))

    def test_time_requirement_false(self):
        user = PicklableMock()
        user.id = "353454"
        user.message.payload = {
            "meta": {
                "time": {
                    "timestamp": 1610979455663,  # ~ 2021-01-18 17:17:35
                    "timezone_offset_sec": 1000000000,  # shouldn't affect
                }
            }
        }
        requirement = TimeRequirement(
            {
                "operator": {
                    "type": "more",
                    "amount": "18:00:00",
                }
            }
        )
        requirement.cache_result = False
        text_normalization_result = None
        self.assertFalse(requirement.check(text_normalization_result, user))

    def test_datetime_requirement_true(self):
        user = PicklableMock()
        user.id = "353454"
        user.message.payload = {
            "meta": {
                "time": {
                    "timestamp": 1610979455663,  # ~ 2021-01-18 17:17:35
                    "timezone_offset_sec": 1000000000,  # shouldn't affect
                }
            }
        }
        requirement = DateTimeRequirement(
            {
                "match_cron": "*/17 14-19 * * mon"
            }
        )
        requirement.cache_result = False
        text_normalization_result = None
        self.assertTrue(requirement.check(text_normalization_result, user))

    def test_datetime_requirement_false(self):
        user = PicklableMock()
        user.id = "353454"
        user.message.payload = {
            "meta": {
                "time": {
                    "timestamp": 1610979455663,  # ~ 2021-01-18 17:17:35
                    "timezone_offset_sec": 1000000000,  # shouldn't affect
                }
            }
        }
        requirement = DateTimeRequirement(
            {
                "match_cron": "* * * * 6,7"
            }
        )
        requirement.cache_result = False
        text_normalization_result = None
        self.assertFalse(requirement.check(text_normalization_result, user))

    @patch('smart_kit.configs.get_app_config')
    def test_intersection_requirement_true(self, mock_get_app_config):
        patch_get_app_config(mock_get_app_config)
        user = PicklableMock()
        requirement = IntersectionRequirement(
            {
                "phrases": [
                    'да',
                    'давай',
                    'хочу',
                ]
            }
        )
        requirement.cache_result = False
        text_normalization_result = PicklableMock()
        text_normalization_result.tokenized_elements_list_pymorphy = [
            {'lemma': 'я'},
            {'lemma': 'хотеть'},
        ]
        self.assertTrue(requirement.check(text_normalization_result, user))

    @patch('smart_kit.configs.get_app_config')
    def test_intersection_requirement_false(self, mock_get_app_config):
        patch_get_app_config(mock_get_app_config)
        user = PicklableMock()
        requirement = IntersectionRequirement(
            {
                "phrases": [
                    'да',
                    'давай',
                    'хочу',
                ]
            }
        )
        requirement.cache_result = False
        text_normalization_result = PicklableMock()
        text_normalization_result.tokenized_elements_list_pymorphy = [
            {'lemma': 'ни'},
            {'lemma': 'за'},
            {'lemma': 'что'},
        ]
        self.assertFalse(requirement.check(text_normalization_result, user))

    @patch.object(ExternalClassifier, "find_best_answer",
                  return_value=[{"answer": "нет", "score": 1.0, "other": False}])
    def test_classifier_requirement_true(self, mock_classifier_model):
        """Тест кейз проверяет что условие возвращает True, если результат классификации запроса относится к одной
        из указанных категорий, прошедших порог, но не равной классу other.
        """
        test_items = {
            "type": "classifier",
            "classifier": {"type": "external", "classifier": "hello_scenario_classifier"},
        }
        classifier_requirement = ClassifierRequirement(test_items)
        mock_user = PicklableMock()
        mock_user.descriptions = {"external_classifiers": ["read_book_or_not_classifier", "hello_scenario_classifier"]}
        result = classifier_requirement.check(PicklableMock(), mock_user)
        self.assertTrue(result)

    @patch.object(ExternalClassifier, "find_best_answer", return_value=[])
    def test_classifier_requirement_false(self, mock_classifier_model):
        """Тест кейз проверяет что условие возвращает False, если модель классификации не вернула ответ."""
        test_items = {
            "type": "classifier",
            "classifier": {"type": "external", "classifier": "hello_scenario_classifier"}
        }
        classifier_requirement = ClassifierRequirement(test_items)
        mock_user = PicklableMock()
        mock_user.descriptions = {"external_classifiers": ["read_book_or_not_classifier", "hello_scenario_classifier"]}
        result = classifier_requirement.check(PicklableMock(), mock_user)
        self.assertFalse(result)

    @patch.object(ExternalClassifier, "find_best_answer",
                  return_value=[{"answer": "other", "score": 1.0, "other": True}])
    def test_classifier_requirement_false_if_class_other(self, mock_classifier_model):
        """Тест кейз проверяет что условие возвращает False, если наиболее вероятный вариант есть класс other."""
        test_items = {
            "type": "classifier",
            "classifier": {"type": "external", "classifier": "hello_scenario_classifier"},
        }
        classifier_requirement = ClassifierRequirement(test_items)
        mock_user = PicklableMock()
        mock_user.descriptions = {"external_classifiers": ["read_book_or_not_classifier", "hello_scenario_classifier"]}
        result = classifier_requirement.check(PicklableMock(), mock_user)
        self.assertFalse(result)

    def test_form_field_value_requirement_true(self):
        """Тест кейз проверяет что условие возвращает True, т.к в
        форме form_name в поле form_field значение совпадает с переданным field_value.
        """
        form_name = "test_form"
        form_field = "test_field"
        field_value = "test_value"

        test_itmes = {"form_name": form_name, "field_name": form_field, "value": field_value}
        req_form_field_value = FormFieldValueRequirement(test_itmes)

        user = PicklableMock()
        user.forms = {form_name: PicklableMock()}
        user.forms[form_name].fields = {form_field: PicklableMock(), "value": field_value}
        user.forms[form_name].fields[form_field].value = field_value

        result = req_form_field_value.check(PicklableMock(), user)
        self.assertTrue(result)

    def test_form_field_value_requirement_false(self):
        """Тест кейз проверяет что условие возвращает False, т.к в
        форме form_name в поле form_field значение НЕ совпадает с переданным field_value.
        """
        form_name = "test_form"
        form_field = "test_field"
        field_value = "test_value"

        test_itmes = {"form_name": form_name, "field_name": form_field, "value": field_value}
        req_form_field_value = FormFieldValueRequirement(test_itmes)

        user = PicklableMock()
        user.forms = {form_name: PicklableMock()}
        user.forms[form_name].fields = {form_field: PicklableMock(), "value": "OTHER_TEST_VAL"}
        user.forms[form_name].fields[form_field].value = "OTHER_TEST_VAL"

        result = req_form_field_value.check(PicklableMock(), user)
        self.assertFalse(result)

    @patch("smart_kit.configs.get_app_config")
    def test_environment_requirement_true(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает True, т.к среда исполнения из числа values."""
        patch_get_app_config(mock_get_app_config)
        environment_req = EnvironmentRequirement({"values": ["ift", "uat"]})
        environment_req.cache_result = False
        self.assertTrue(environment_req.check(PicklableMock(), PicklableMock()))

    @patch("smart_kit.configs.get_app_config")
    def test_environment_requirement_false(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает False, т.к среда исполнения НЕ из числа values."""
        patch_get_app_config(mock_get_app_config)
        environment_req = EnvironmentRequirement({"values": ["uat", "pt"]})
        environment_req.cache_result = False
        self.assertFalse(environment_req.check(PicklableMock(), PicklableMock()))

    def test_any_substring_in_lowered_text_requirement_true(self):
        """Тест кейз проверяет что условие возвращает True, т.к нашлась подстрока из списка substrings, которая
        встречается в оригинальном тексте в нижнем регистре.
        """
        req = AnySubstringInLoweredTextRequirement({"substrings": ["искомая подстрока", "другое знанчение"]})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {"original_text": "КАКОЙ-ТО ТЕКСТ С ИСКОМАЯ ПОДСТРОКА"}
        result = req.check(text_preprocessing_result, PicklableMock())
        self.assertTrue(result)

    def test_any_substring_in_lowered_text_requirement_false(self):
        """Тест кейз проверяет что условие возвращает False, т.к НЕ нашлась ни одна подстрока из списка substrings,
        которая бы встречалась в оригинальном тексте в нижнем регистре.
        """
        req = AnySubstringInLoweredTextRequirement({"substrings": ["искомая подстрока", "другая подстрока"]})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {"original_text": "КАКОЙ-ТО ТЕКСТ"}
        result = req.check(text_preprocessing_result, PicklableMock())
        self.assertFalse(result)

    def test_num_in_range_requirement_true(self):
        """Тест кейз проверяет что условие возвращает True, т.к число находится в заданном диапазоне."""
        req = NumInRangeRequirement({"min_num": "5", "max_num": "10"})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.num_token_values = 7
        self.assertTrue(req.check(text_preprocessing_result, PicklableMock()))

    def test_num_in_range_requirement_false(self):
        """Тест кейз проверяет что условие возвращает False, т.к число НЕ находится в заданном диапазоне."""
        req = NumInRangeRequirement({"min_num": "5", "max_num": "10"})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.num_token_values = 20
        self.assertFalse(req.check(text_preprocessing_result, PicklableMock()))

    def test_phone_number_number_requirement_true(self):
        """Тест кейз проверяет что условие возвращает True, т.к кол-во номеров телефонов больше заданного."""
        req = PhoneNumberNumberRequirement({"operator": {"type": "more", "amount": 1}})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.get_token_values_by_type.return_value = ["89030478799", "89092534523"]
        self.assertTrue(req.check(text_preprocessing_result, PicklableMock()))

    def test_phone_number_number_requirement_false(self):
        """Тест кейз проверяет что условие возвращает False, т.к кол-во номеров телефонов НЕ больше заданного."""
        req = PhoneNumberNumberRequirement({"operator": {"type": "more", "amount": 10}})
        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.get_token_values_by_type.return_value = ["89030478799"]
        self.assertFalse(req.check(text_preprocessing_result, PicklableMock()))

    @patch("smart_kit.configs.get_app_config")
    def test_intersection_with_tokens_requirement_true(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает True, т.к хотя бы одно слово из нормализованного
        вида запроса входит в список слов input_words.
        """
        patch_get_app_config(mock_get_app_config)

        req = IntersectionWithTokensSetRequirement({"input_words": ["погода", "время"]})

        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {
            "tokenized_elements_list_pymorphy": [
                {
                    "text": "прогноз",
                    "grammem_info": {
                        "animacy": "inan",
                        "case": "acc",
                        "gender": "masc",
                        "number": "sing",
                        "raw_gram_info": "animacy=inan|case=acc|gender=masc|number=sing",
                        "part_of_speech": "NOUN"
                    },
                    "lemma": "прогноз"
                },
                {
                    "text": "погоды",
                    "grammem_info": {
                        "animacy": "inan",
                        "case": "gen",
                        "gender": "fem",
                        "number": "sing",
                        "raw_gram_info": "animacy=inan|case=gen|gender=fem|number=sing",
                        "part_of_speech": "NOUN"
                    },
                    "lemma": "погода"
                }
            ]}

        self.assertTrue(req.check(text_preprocessing_result, PicklableMock()))

    @patch("smart_kit.configs.get_app_config")
    def test_intersection_with_tokens_requirement_false(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает False, т.к ни одно слово из нормализованного
        вида запроса не входит в список слов input_words.
        """
        patch_get_app_config(mock_get_app_config)

        req = IntersectionWithTokensSetRequirement({"input_words": ["время"]})

        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {"tokenized_elements_list_pymorphy": [
            {"text": "прогноз", "grammem_info": {
                "animacy": "inan", "case": "acc", "gender": "masc", "number": "sing", "raw_gram_info":
                    "animacy=inan|case=acc|gender=masc|number=sing", "part_of_speech": "NOUN"}, "lemma": "прогноз"},
            {"text": "погоды", "grammem_info": {
                "animacy": "inan", "case": "gen", "gender": "fem", "number": "sing",
                "raw_gram_info": "animacy=inan|case=gen|gender=fem|number=sing",
                "part_of_speech": "NOUN"}, "lemma": "погода"}
        ]}

        self.assertFalse(req.check(text_preprocessing_result, PicklableMock()))

    @patch("smart_kit.configs.get_app_config")
    def test_normalized_text_in_set_requirement_true(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает True, т.к в нормализованном представлении
        запрос полностью совпадает с одной из нормализованных строк из input_words.
        """
        patch_get_app_config(mock_get_app_config)

        req = NormalizedTextInSetRequirement({"input_words": ["погода", "время"]})

        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {"normalized_text": "погода ."}

        self.assertTrue(req.check(text_preprocessing_result, PicklableMock()))

    @patch("smart_kit.configs.get_app_config")
    def test_normalized_text_in_set_requirement_false(self, mock_get_app_config):
        """Тест кейз проверяет что условие возвращает False, т.к в нормализованном представлении
        запрос НЕ совпадает ни с одной из нормализованных строк из input_words.
        """
        patch_get_app_config(mock_get_app_config)

        req = NormalizedTextInSetRequirement({"input_words": ["погода", "время"]})

        text_preprocessing_result = PicklableMock()
        text_preprocessing_result.raw = {"normalized_text": "хотеть узнать ."}

        self.assertFalse(req.check(text_preprocessing_result, PicklableMock()))

    def test_character_id_requirement_true(self):
        req = CharacterIdRequirement({"values": ["sber", "afina"]})
        req.cache_result = False
        user = Mock()
        user.message = Mock()
        user.message.payload = {"character": {"id": "sber", "name": "Сбер", "gender": "male"}}
        self.assertTrue(req.check(Mock(), user))

    def test_character_id_requirement_false(self):
        req = CharacterIdRequirement({"values": ["afina"]})
        req.cache_result = False
        user = Mock()
        user.message = Mock()
        user.message.payload = {"character": {"id": "sber", "name": "Сбер", "gender": "male"}}
        self.assertFalse(req.check(Mock(), user))

    def test_feature_toggle_check_requirement_true(self):
        req = FeatureToggleRequirement({"toggle_name": "test_true_toggle_name"})
        req.cache_result = False
        mock_user = Mock()
        mock_user.settings = {"template_settings": {"test_true_toggle_name": True}}
        self.assertTrue(req.check(Mock(), mock_user))

    def test_feature_toggle_check_requirement_false(self):
        req = FeatureToggleRequirement({"toggle_name": "test_false_toggle_name"})
        req.cache_result = False
        mock_user = Mock()
        mock_user.settings = {"template_settings": {"test_false_toggle_name": False}}
        self.assertFalse(req.check(Mock(), mock_user))

    def test_false_caching_different(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueFalseRequirement()
        requirement.cache_result = False
        text_normalization_result = None
        result1 = requirement.check(text_normalization_result, user)
        result2 = requirement.check(text_normalization_result, user)
        self.assertNotEqual(result1, result2)

    def test_true_caching_same(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueFalseRequirement()
        requirement.cache_result = True
        text_normalization_result = None
        result1 = requirement.check(text_normalization_result, user)
        result2 = requirement.check(text_normalization_result, user)
        self.assertEqual(result1, result2)

    def test_true_caching_one_call(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueFalseRequirement()
        requirement.cache_result = True
        requirement._check = Mock()
        text_normalization_result = None
        requirement.check(text_normalization_result, user)
        requirement.check(text_normalization_result, user)
        self.assertEqual(requirement._check.call_count, 1)

    def test_true_caching_one_call_for_two(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueFalseRequirement()
        requirement.cache_result = True
        requirement._check = Mock(return_value=1)
        requirement2 = TrueFalseRequirement()
        requirement2.cache_result = True
        requirement2._check = Mock(return_value=2)
        text_normalization_result = None
        res1 = requirement.check(text_normalization_result, user)
        res2 = requirement2.check(text_normalization_result, user)
        self.assertEqual(res1, res2)
        self.assertEqual(res2, 1)
        self.assertEqual(requirement._check.call_count, 1)
        self.assertEqual(requirement2._check.call_count, 0)

    def test_true_caching_one_call_for_two_with_same_items(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = MockRequirement({"cond": 1})
        requirement._check = Mock()
        requirement.cache_result = True
        requirement2 = MockRequirement({"cond": 1})
        requirement2._check = Mock()
        requirement2.cache_result = True
        text_normalization_result = None
        requirement.check(text_normalization_result, user)
        requirement2.check(text_normalization_result, user)
        self.assertEqual(requirement._check.call_count, 1)
        self.assertEqual(requirement2._check.call_count, 0)

    def test_true_caching_two_calls_for_two_with_different_items(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = MockRequirement({"cond": 1})
        requirement._check = Mock()
        requirement.cache_result = True
        requirement2 = MockRequirement({"cond": 1, "a": 1})
        requirement2._check = Mock()
        requirement2.cache_result = True
        text_normalization_result = None
        requirement.check(text_normalization_result, user)
        requirement2.check(text_normalization_result, user)
        self.assertEqual(requirement._check.call_count, 1)
        self.assertEqual(requirement2._check.call_count, 1)

    def test_caching_reassigning_caching(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueCacheRequirement({})
        requirement._check = Mock()
        text_normalization_result = None
        requirement.check(text_normalization_result, user)
        requirement.check(text_normalization_result, user)
        self.assertEqual(requirement._check.call_count, 1)
        requirement = TrueCacheRequirement({"cache_result": False})
        requirement._check = Mock()
        requirement.check(text_normalization_result, user)
        requirement.check(text_normalization_result, user)
        self.assertEqual(requirement._check.call_count, 2)

    def test_different_caching_different(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement = TrueFalseRequirement()
        requirement.cache_result = True
        requirement._check = Mock(return_value=1)
        requirement2 = TrueFalseRequirement()
        requirement2.cache_result = False
        requirement2._check = Mock(return_value=2)
        text_normalization_result = None
        res1 = requirement.check(text_normalization_result, user)
        res2 = requirement2.check(text_normalization_result, user)
        self.assertEqual(res1, 1)
        self.assertEqual(res2, 2)

    def test_different_caching_different_reversed(self):
        user = PicklableMock()
        user.message_vars = Variables(None, user, False)
        requirement2 = TrueFalseRequirement()
        requirement2.cache_result = False
        requirement2._check = Mock(return_value=2)
        requirement = TrueFalseRequirement()
        requirement.cache_result = True
        requirement._check = Mock(return_value=1)
        text_normalization_result = None
        res2 = requirement2.check(text_normalization_result, user)
        res1 = requirement.check(text_normalization_result, user)
        self.assertEqual(res1, 1)
        self.assertEqual(res2, 2)
