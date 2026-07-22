from memory_manager.context_manager import ConversationContextManager


def test_init_conv_isolates_history_from_request_contexts() -> None:
    request_contexts = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "existing message"}],
        }
    ]
    manager = ConversationContextManager()

    manager.init_conv("session-1", request_contexts, event=object())
    manager.add_message(
        "session-1",
        "user",
        "[Alice(42)]: current message",
    )

    plugin_history = manager.get_history("session-1")
    assert len(request_contexts) == 1
    assert len(plugin_history) == 2
    assert plugin_history is not request_contexts

    plugin_history[0]["content"][0]["text"] = "plugin-local change"
    assert request_contexts[0]["content"][0]["text"] == "existing message"
