def test_assistant_proto_importable_with_data_files():
    import assistant_proto as A

    assert A.SCHEMA_VERSION == 1 and "event.add" in A.SYSTEM_PROMPT
    assert A.json_schema()["properties"]["v"] == {"const": 1}
    assert A.rules.missing("event.add", {}, {}) == "set.rooms"
