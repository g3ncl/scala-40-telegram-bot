"""Tests for Telegram client and mock."""

from tests.conftest import MockTelegramClient


class TestMockTelegramClient:
    def test_send_message_records_call(self):
        mock = MockTelegramClient()
        result = mock.send_message("chat1", "hello")
        assert result["ok"]
        assert len(mock.calls) == 1
        assert mock.calls[0][0] == "send_message"
        assert mock.calls[0][1]["chat_id"] == "chat1"
        assert mock.calls[0][1]["text"] == "hello"

    def test_edit_message_records_call(self):
        mock = MockTelegramClient()
        mock.edit_message("chat1", 42, "updated")
        assert mock.last_call("edit_message")["message_id"] == 42

    def test_answer_callback_query_records(self):
        mock = MockTelegramClient()
        mock.answer_callback_query("cq1", text="ok")
        call = mock.last_call("answer_callback_query")
        assert call["callback_query_id"] == "cq1"
        assert call["text"] == "ok"

    def test_get_calls_filters(self):
        mock = MockTelegramClient()
        mock.send_message("c1", "a")
        mock.send_message("c2", "b")
        mock.edit_message("c1", 1, "x")
        assert len(mock.get_calls("send_message")) == 2
        assert len(mock.get_calls("edit_message")) == 1

    def test_last_call_empty(self):
        mock = MockTelegramClient()
        assert mock.last_call("send_message") is None

    def test_reply_markup_passed(self):
        mock = MockTelegramClient()
        kb = {"inline_keyboard": [[{"text": "Go", "callback_data": "go"}]]}
        mock.send_message("c1", "pick", reply_markup=kb)
        call = mock.last_call("send_message")
        assert call["reply_markup"] == kb
