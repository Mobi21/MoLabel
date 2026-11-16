import yaml

from molabel.core.utils.round_trip_yaml import dump_yaml


def test_changing_one_alias_leaves_its_anchor_alone() -> None:
    previous = (
        "steps:\n- config: &inputs\n    source: data/a.jsonl\n- config: *inputs\n"
    )
    data = {
        "steps": [
            {"config": {"source": "data/a.jsonl"}},
            {"config": {"source": "data/b.jsonl"}},
        ]
    }

    assert yaml.safe_load(dump_yaml(data, previous)) == data


def test_a_key_removed_from_a_merged_mapping_stays_removed() -> None:
    previous = (
        "base: &base\n  source: data/a.jsonl\n  format: csv\nstep:\n  <<: *base\n"
    )
    data = {
        "base": {"source": "data/a.jsonl", "format": "csv"},
        "step": {"source": "data/a.jsonl"},
    }

    assert yaml.safe_load(dump_yaml(data, previous)) == data


def test_a_nested_boolean_changed_to_a_number_is_written() -> None:
    previous = "config:\n  batch_size: true\n"

    value = yaml.safe_load(dump_yaml({"config": {"batch_size": 1}}, previous))

    assert value["config"]["batch_size"] == 1
    assert type(value["config"]["batch_size"]) is int


def test_comments_survive_when_the_new_data_orders_keys_differently() -> None:
    previous = "# keep me\na: 1\nb: 2  # and me\n"
    data = {"b": 3, "a": 1}

    rendered = dump_yaml(data, previous)

    assert yaml.safe_load(rendered) == data
    assert "# keep me" in rendered
    assert "# and me" in rendered
