from memory_manager.context_manager import ConversationContextManager


def test_init_conv_does_not_retain_event() -> None:
    manager = ConversationContextManager()
    manager.init_conv("session-1", [], persona_id="persona-1")

    conversation = manager.conversations["session-1"]
    assert conversation["persona_id"] == "persona-1"
    assert "event" not in conversation


def test_cache_is_bounded_by_lru() -> None:
    manager = ConversationContextManager(max_sessions=2, idle_ttl_seconds=0)
    manager.add_message("old", "user", "old")
    manager.add_message("new", "user", "new")
    manager.add_message("newer", "user", "newer")

    assert list(manager.conversations) == ["new", "newer"]


def test_idle_sessions_are_pruned_on_activity() -> None:
    manager = ConversationContextManager(idle_ttl_seconds=10)
    manager.add_message("stale", "user", "stale")
    manager.conversations["stale"]["last_activity_time"] -= 11

    manager.add_message("active", "user", "active")

    assert "stale" not in manager.conversations
    assert "active" in manager.conversations


def test_history_is_trimmed_to_latest_messages() -> None:
    manager = ConversationContextManager(max_history_messages=3)
    for index in range(5):
        manager.add_message("session-1", "user", str(index))

    history = manager.get_history("session-1")
    assert [item["content"] for item in history] == ["2", "3", "4"]


def test_existing_session_updates_persona_without_recopying_history() -> None:
    contexts = [{"role": "user", "content": "initial"}]
    manager = ConversationContextManager()
    manager.init_conv("session-1", contexts, persona_id="persona-1")
    initial_history = manager.get_history("session-1")

    manager.init_conv("session-1", [], persona_id="persona-2")

    assert manager.get_persona_id("session-1") == "persona-2"
    assert manager.get_history("session-1") is initial_history
