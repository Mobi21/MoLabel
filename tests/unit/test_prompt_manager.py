"""Tests for prompt management and versioning (AG-013)."""

from __future__ import annotations

import pytest

from molabel.core.prompts.prompt_manager import (
    PromptImmutabilityError,
    PromptLayer,
    PromptLayerType,
    PromptManager,
    PromptTemplate,
)


@pytest.fixture()
def manager() -> PromptManager:
    return PromptManager()


@pytest.fixture()
def base_layer() -> PromptLayer:
    return PromptLayer(
        layer_type=PromptLayerType.base,
        name="system_prompt",
        content="You are a sentiment analysis agent.",
        priority=0,
    )


@pytest.fixture()
def rubric_layer() -> PromptLayer:
    return PromptLayer(
        layer_type=PromptLayerType.rubric,
        name="sentiment_rubric",
        content="Label each record as positive, negative, or neutral.",
        priority=0,
    )


@pytest.fixture()
def few_shot_layer() -> PromptLayer:
    return PromptLayer(
        layer_type=PromptLayerType.few_shot,
        name="examples",
        content='Example: "Great product!" -> positive',
        priority=0,
    )


class TestPromptTemplate:
    def test_content_hash_auto_computed(self, base_layer: PromptLayer) -> None:
        """Template auto-computes content hash and version on init."""
        template = PromptTemplate(name="test", layers=[base_layer])
        assert template.content_hash != ""
        assert template.version == template.content_hash[:12]

    def test_different_layers_different_hash(
        self, base_layer: PromptLayer, rubric_layer: PromptLayer
    ) -> None:
        """Different layer content produces different hashes."""
        t1 = PromptTemplate(name="t1", layers=[base_layer])
        t2 = PromptTemplate(name="t2", layers=[rubric_layer])
        assert t1.content_hash != t2.content_hash


class TestPromptManager:
    def test_create_template(
        self, manager: PromptManager, base_layer: PromptLayer
    ) -> None:
        """Creating a template registers it and sets version."""
        template = manager.create_template("my_prompt", [base_layer])
        assert template.name == "my_prompt"
        assert template.content_hash != ""
        assert template.version == template.content_hash[:12]
        assert len(template.version_history) == 1
        assert template.version_history[0].change_description == "Initial version"
        assert manager.get_template("my_prompt") is template

    def test_get_nonexistent_template(self, manager: PromptManager) -> None:
        """Getting a nonexistent template returns None."""
        assert manager.get_template("nope") is None

    def test_add_layer_updates_version(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Adding a layer changes the hash and version."""
        template = manager.create_template("p", [base_layer])
        old_hash = template.content_hash

        manager.add_layer("p", rubric_layer)
        assert template.content_hash != old_hash
        assert len(template.version_history) == 2

    def test_add_layer_to_used_template_raises(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Cannot add layers to a used template."""
        manager.create_template("p", [base_layer])
        manager.mark_used("p")

        with pytest.raises(PromptImmutabilityError):
            manager.add_layer("p", rubric_layer)

    def test_remove_layer(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Removing a layer changes the hash."""
        manager.create_template("p", [base_layer, rubric_layer])
        old_hash = manager.get_template("p").content_hash

        manager.remove_layer("p", "sentiment_rubric")
        assert manager.get_template("p").content_hash != old_hash
        assert len(manager.get_template("p").layers) == 1

    def test_remove_layer_from_used_raises(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Cannot remove layers from a used template."""
        manager.create_template("p", [base_layer, rubric_layer])
        manager.mark_used("p")

        with pytest.raises(PromptImmutabilityError):
            manager.remove_layer("p", "sentiment_rubric")

    def test_remove_nonexistent_layer_raises(
        self, manager: PromptManager, base_layer: PromptLayer
    ) -> None:
        """Removing a nonexistent layer raises KeyError."""
        manager.create_template("p", [base_layer])
        with pytest.raises(KeyError, match="not found in template"):
            manager.remove_layer("p", "nonexistent")

    def test_fork_template(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Forking creates an independent copy."""
        manager.create_template("original", [base_layer])
        manager.mark_used("original")

        forked = manager.fork_template(
            "original", "v2", additional_layers=[rubric_layer]
        )
        assert forked.name == "v2"
        assert forked.is_used is False
        assert len(forked.layers) == 2
        assert forked.content_hash != manager.get_template("original").content_hash

        # Forked version history references parent
        assert (
            forked.version_history[0].parent_hash
            == manager.get_template("original").content_hash
        )

    def test_fork_nonexistent_raises(self, manager: PromptManager) -> None:
        """Forking a nonexistent template raises KeyError."""
        with pytest.raises(KeyError):
            manager.fork_template("missing", "new")

    def test_compose_layer_order(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
        few_shot_layer: PromptLayer,
    ) -> None:
        """Composition follows base -> rubric -> few_shot -> patch order."""
        # Add in reverse order to test sorting
        manager.create_template("p", [few_shot_layer, rubric_layer, base_layer])
        composed = manager.compose("p")

        lines = composed.text.split("\n\n")
        assert "sentiment analysis agent" in lines[0]  # base first
        assert "positive, negative, or neutral" in lines[1]  # rubric second
        assert "Example:" in lines[2]  # few_shot third

    def test_compose_hash(
        self, manager: PromptManager, base_layer: PromptLayer
    ) -> None:
        """Composed prompt has its own content hash."""
        manager.create_template("p", [base_layer])
        composed = manager.compose("p")
        assert composed.content_hash != ""
        assert composed.source_template_name == "p"
        assert composed.layer_count == 1

    def test_compose_from_layers_directly(
        self, manager: PromptManager, base_layer: PromptLayer
    ) -> None:
        """Can compose directly from layers without a stored template."""
        composed = manager.compose_from_layers([base_layer])
        assert "sentiment analysis agent" in composed.text

    def test_yaml_round_trip(
        self,
        manager: PromptManager,
        base_layer: PromptLayer,
        rubric_layer: PromptLayer,
    ) -> None:
        """Serializing to YAML dict and loading back preserves the template."""
        manager.create_template(
            "original", [base_layer, rubric_layer], metadata={"task": "sentiment"}
        )
        yaml_data = manager.to_yaml_dict("original")

        # Load into a fresh manager
        manager2 = PromptManager()
        loaded = manager2.from_yaml_dict(yaml_data)

        assert loaded.name == "original"
        assert loaded.content_hash == manager.get_template("original").content_hash
        assert len(loaded.layers) == 2
        assert loaded.metadata == {"task": "sentiment"}

    def test_mark_used(self, manager: PromptManager, base_layer: PromptLayer) -> None:
        """Marking a template as used sets is_used flag."""
        manager.create_template("p", [base_layer])
        assert manager.get_template("p").is_used is False
        manager.mark_used("p")
        assert manager.get_template("p").is_used is True

    def test_mark_used_nonexistent_raises(self, manager: PromptManager) -> None:
        """Marking a nonexistent template raises KeyError."""
        with pytest.raises(KeyError):
            manager.mark_used("missing")

    def test_patch_layer_applied_last(self, manager: PromptManager) -> None:
        """Patch layers appear after all other types in composition."""
        layers = [
            PromptLayer(
                layer_type=PromptLayerType.patch,
                name="fix1",
                content="IMPORTANT: Do not label sarcasm as positive.",
            ),
            PromptLayer(
                layer_type=PromptLayerType.base,
                name="base",
                content="You are a labeling agent.",
            ),
        ]
        manager.create_template("p", layers)
        composed = manager.compose("p")
        parts = composed.text.split("\n\n")
        assert "labeling agent" in parts[0]
        assert "sarcasm" in parts[1]

    def test_templates_property(
        self, manager: PromptManager, base_layer: PromptLayer
    ) -> None:
        """The templates property returns a copy of all templates."""
        manager.create_template("a", [base_layer])
        manager.create_template("b", [base_layer])
        templates = manager.templates
        assert len(templates) == 2
        assert "a" in templates
        assert "b" in templates
