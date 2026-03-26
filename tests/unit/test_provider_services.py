"""Tests for provider service layer (Step 2.B.6).

Verifies:
- Model profile CRUD operations.
- Runtime profile CRUD with routing mode validation.
- Model profile connectivity testing.
- Runtime profile model selection logic.
- API endpoint response models.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from molabel.core.services.model_profile_service import (
    ConnectivityTestResult,
    ModelProfileCreate,
    ModelProfileResponse,
    ModelProfileService,
    ModelProfileUpdate,
)
from molabel.core.services.runtime_profile_service import (
    RetryConfig,
    RoutingMode,
    RuntimeProfileCreate,
    RuntimeProfileResponse,
    RuntimeProfileService,
    RuntimeProfileUpdate,
)
from molabel.core.types import ProviderType

_WORKSPACE_ID = uuid4()


# ===================================================================
# Model profile service tests
# ===================================================================


class TestModelProfileService:
    def _make_service(self) -> ModelProfileService:
        return ModelProfileService()

    def _create_profile(
        self,
        service: ModelProfileService,
        slug: str = "test-profile",
        provider: str = ProviderType.openai_compatible,
    ) -> ModelProfileResponse:
        return service.create(
            ModelProfileCreate(
                model_profile_slug=slug,
                provider_type=provider,
                model_identifier="gpt-4o",
                transport="https",
                auth_ref="OPENAI_API_KEY",
                cost_per_input_token=2.5e-6,
                cost_per_output_token=10.0e-6,
            ),
            workspace_id=_WORKSPACE_ID,
        )

    def test_create_profile(self) -> None:
        service = self._make_service()
        profile = self._create_profile(service)
        assert profile.model_profile_slug == "test-profile"
        assert profile.provider_type == ProviderType.openai_compatible
        assert profile.model_identifier == "gpt-4o"
        assert profile.id is not None
        assert profile.created_at is not None

    def test_get_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        fetched = service.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.model_profile_slug == "test-profile"

    def test_get_nonexistent(self) -> None:
        service = self._make_service()
        assert service.get(uuid4()) is None

    def test_list_profiles(self) -> None:
        service = self._make_service()
        self._create_profile(service, "profile-1")
        self._create_profile(service, "profile-2")
        profiles = service.list_profiles(_WORKSPACE_ID)
        assert len(profiles) == 2

    def test_list_profiles_filter_by_type(self) -> None:
        service = self._make_service()
        self._create_profile(service, "openai-1", ProviderType.openai_compatible)
        self._create_profile(service, "ollama-1", ProviderType.ollama)
        profiles = service.list_profiles(
            _WORKSPACE_ID,
            provider_type=ProviderType.ollama,
        )
        assert len(profiles) == 1
        assert profiles[0].provider_type == ProviderType.ollama

    def test_list_profiles_empty_workspace(self) -> None:
        service = self._make_service()
        self._create_profile(service)
        profiles = service.list_profiles(uuid4())  # Different workspace
        assert len(profiles) == 0

    def test_update_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        updated = service.update(
            created.id,
            ModelProfileUpdate(model_identifier="gpt-4o-mini"),
        )
        assert updated is not None
        assert updated.model_identifier == "gpt-4o-mini"
        assert updated.model_profile_slug == "test-profile"
        assert updated.updated_at is not None
        assert updated.updated_at >= created.updated_at

    def test_update_nonexistent(self) -> None:
        service = self._make_service()
        result = service.update(
            uuid4(),
            ModelProfileUpdate(model_identifier="new"),
        )
        assert result is None

    def test_update_partial(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        updated = service.update(
            created.id,
            ModelProfileUpdate(context_window=128000),
        )
        assert updated is not None
        assert updated.context_window == 128000
        assert updated.model_identifier == "gpt-4o"  # Unchanged

    def test_delete_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        assert service.delete(created.id) is True
        assert service.get(created.id) is None

    def test_delete_nonexistent(self) -> None:
        service = self._make_service()
        assert service.delete(uuid4()) is False

    def test_test_connectivity_nonexistent(self) -> None:
        service = self._make_service()
        result = service.test_connectivity(uuid4())
        assert result.health.is_healthy is False
        assert "not found" in result.health.error

    def test_test_connectivity_ollama(self) -> None:
        """Test connectivity for an Ollama profile (won't actually connect)."""
        service = self._make_service()
        profile = service.create(
            ModelProfileCreate(
                model_profile_slug="local-ollama",
                provider_type=ProviderType.ollama,
                model_identifier="llama3.1",
                transport="http",
                base_url="http://localhost:99999",  # Won't connect
            ),
            workspace_id=_WORKSPACE_ID,
        )
        result = service.test_connectivity(profile.id)
        # Will fail because nothing is running on that port
        assert isinstance(result, ConnectivityTestResult)
        # Availability should be updated
        updated = service.get(profile.id)
        assert updated is not None
        assert updated.is_available is not None

    def test_response_model_fields(self) -> None:
        service = self._make_service()
        profile = service.create(
            ModelProfileCreate(
                model_profile_slug="full-profile",
                provider_type=ProviderType.anthropic,
                model_identifier="claude-sonnet-4-20250514",
                transport="https",
                auth_ref="ANTHROPIC_API_KEY",
                supports_structured_output=True,
                supports_tool_use=True,
                context_window=200000,
                cost_per_input_token=3.0e-6,
                cost_per_output_token=15.0e-6,
                capability_tags=["chat", "vision"],
                routing_metadata={"priority": 1},
            ),
            workspace_id=_WORKSPACE_ID,
        )
        assert profile.supports_structured_output is True
        assert profile.supports_tool_use is True
        assert profile.context_window == 200000
        assert profile.capability_tags == ["chat", "vision"]
        assert profile.routing_metadata == {"priority": 1}


# ===================================================================
# Runtime profile service tests
# ===================================================================


class TestRuntimeProfileService:
    def _make_service(self) -> RuntimeProfileService:
        return RuntimeProfileService()

    def _create_profile(
        self,
        service: RuntimeProfileService,
        slug: str = "default-runtime",
        mode: str = RoutingMode.cloud_preferred,
    ) -> RuntimeProfileResponse:
        return service.create(
            RuntimeProfileCreate(
                runtime_profile_slug=slug,
                mode=mode,
                max_concurrent_requests=5,
                timeout_seconds=120,
            ),
            workspace_id=_WORKSPACE_ID,
        )

    def test_create_profile(self) -> None:
        service = self._make_service()
        profile = self._create_profile(service)
        assert profile.runtime_profile_slug == "default-runtime"
        assert profile.mode == RoutingMode.cloud_preferred
        assert profile.max_concurrent_requests == 5
        assert profile.timeout_seconds == 120

    def test_create_with_all_modes(self) -> None:
        service = self._make_service()
        for mode in RoutingMode:
            profile = self._create_profile(service, f"rt-{mode}", mode)
            assert profile.mode == mode

    def test_create_invalid_mode(self) -> None:
        service = self._make_service()
        with pytest.raises(ValueError, match="Invalid routing mode"):
            service.create(
                RuntimeProfileCreate(
                    runtime_profile_slug="bad-mode",
                    mode="invalid_mode",
                ),
                workspace_id=_WORKSPACE_ID,
            )

    def test_get_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        fetched = service.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_nonexistent(self) -> None:
        service = self._make_service()
        assert service.get(uuid4()) is None

    def test_list_profiles(self) -> None:
        service = self._make_service()
        self._create_profile(service, "rt-1")
        self._create_profile(service, "rt-2")
        profiles = service.list_profiles(_WORKSPACE_ID)
        assert len(profiles) == 2

    def test_update_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        updated = service.update(
            created.id,
            RuntimeProfileUpdate(
                mode=RoutingMode.offline_preferred,
                max_concurrent_requests=10,
            ),
        )
        assert updated is not None
        assert updated.mode == RoutingMode.offline_preferred
        assert updated.max_concurrent_requests == 10
        assert updated.timeout_seconds == 120  # Unchanged

    def test_update_invalid_mode(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        with pytest.raises(ValueError, match="Invalid routing mode"):
            service.update(
                created.id,
                RuntimeProfileUpdate(mode="bad_mode"),
            )

    def test_update_nonexistent(self) -> None:
        service = self._make_service()
        assert service.update(uuid4(), RuntimeProfileUpdate()) is None

    def test_delete_profile(self) -> None:
        service = self._make_service()
        created = self._create_profile(service)
        assert service.delete(created.id) is True
        assert service.get(created.id) is None

    def test_delete_nonexistent(self) -> None:
        service = self._make_service()
        assert service.delete(uuid4()) is False

    def test_create_with_provider_priority(self) -> None:
        service = self._make_service()
        p1 = uuid4()
        p2 = uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="with-priority",
                mode=RoutingMode.hybrid,
                provider_priority=[p1, p2],
                fallback_model_profile_id=uuid4(),
            ),
            workspace_id=_WORKSPACE_ID,
        )
        assert profile.provider_priority is not None
        assert len(profile.provider_priority) == 2

    def test_create_with_retry_config(self) -> None:
        service = self._make_service()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="with-retry",
                mode=RoutingMode.cloud_preferred,
                retry_config={
                    "max_retries": 5,
                    "initial_delay_seconds": 2.0,
                },
            ),
            workspace_id=_WORKSPACE_ID,
        )
        assert profile.retry_config is not None
        assert profile.retry_config["max_retries"] == 5


# ===================================================================
# Retry config tests
# ===================================================================


class TestRetryConfig:
    def test_defaults(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay_seconds == 1.0
        assert config.backoff_multiplier == 2.0
        assert 429 in config.retry_on_status_codes

    def test_get_effective_retry_config_default(self) -> None:
        service = RuntimeProfileService()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="no-retry",
                mode=RoutingMode.cloud_preferred,
            ),
            workspace_id=_WORKSPACE_ID,
        )
        config = service.get_effective_retry_config(profile.id)
        assert config.max_retries == 3  # Default

    def test_get_effective_retry_config_custom(self) -> None:
        service = RuntimeProfileService()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="custom-retry",
                mode=RoutingMode.cloud_preferred,
                retry_config={
                    "max_retries": 5,
                    "initial_delay_seconds": 0.5,
                    "backoff_multiplier": 3.0,
                    "max_delay_seconds": 60.0,
                    "retry_on_status_codes": [429, 500],
                },
            ),
            workspace_id=_WORKSPACE_ID,
        )
        config = service.get_effective_retry_config(profile.id)
        assert config.max_retries == 5
        assert config.initial_delay_seconds == 0.5
        assert config.backoff_multiplier == 3.0


# ===================================================================
# Model selection (routing) tests
# ===================================================================


class TestModelSelection:
    def test_cloud_preferred_returns_first(self) -> None:
        service = RuntimeProfileService()
        p1, p2 = uuid4(), uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="cloud-pref",
                mode=RoutingMode.cloud_preferred,
                provider_priority=[p1, p2],
            ),
            workspace_id=_WORKSPACE_ID,
        )
        selected = service.select_model_profile(profile.id)
        assert selected == p1

    def test_hybrid_skips_unavailable(self) -> None:
        service = RuntimeProfileService()
        p1, p2, p3 = uuid4(), uuid4(), uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="hybrid",
                mode=RoutingMode.hybrid,
                provider_priority=[p1, p2, p3],
            ),
            workspace_id=_WORKSPACE_ID,
        )
        # p1 is unavailable
        available = {p1: False, p2: True, p3: True}
        selected = service.select_model_profile(
            profile.id, available_profiles=available
        )
        assert selected == p2

    def test_offline_preferred_uses_fallback(self) -> None:
        service = RuntimeProfileService()
        p1, fallback = uuid4(), uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="offline-fb",
                mode=RoutingMode.offline_preferred,
                provider_priority=[p1],
                fallback_model_profile_id=fallback,
            ),
            workspace_id=_WORKSPACE_ID,
        )
        available = {p1: False}
        selected = service.select_model_profile(
            profile.id, available_profiles=available
        )
        assert selected == fallback

    def test_no_priority_returns_fallback(self) -> None:
        service = RuntimeProfileService()
        fallback = uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="no-prio",
                mode=RoutingMode.cloud_preferred,
                fallback_model_profile_id=fallback,
            ),
            workspace_id=_WORKSPACE_ID,
        )
        selected = service.select_model_profile(profile.id)
        assert selected == fallback

    def test_no_priority_no_fallback_returns_none(self) -> None:
        service = RuntimeProfileService()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="empty",
                mode=RoutingMode.cloud_preferred,
            ),
            workspace_id=_WORKSPACE_ID,
        )
        selected = service.select_model_profile(profile.id)
        assert selected is None

    def test_nonexistent_profile_returns_none(self) -> None:
        service = RuntimeProfileService()
        assert service.select_model_profile(uuid4()) is None

    def test_local_only_returns_available(self) -> None:
        service = RuntimeProfileService()
        p1, p2 = uuid4(), uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="local-only",
                mode=RoutingMode.local_only,
                provider_priority=[p1, p2],
            ),
            workspace_id=_WORKSPACE_ID,
        )
        available = {p1: False, p2: True}
        selected = service.select_model_profile(
            profile.id, available_profiles=available
        )
        assert selected == p2

    def test_all_unavailable_returns_none(self) -> None:
        service = RuntimeProfileService()
        p1, p2 = uuid4(), uuid4()
        profile = service.create(
            RuntimeProfileCreate(
                runtime_profile_slug="all-down",
                mode=RoutingMode.hybrid,
                provider_priority=[p1, p2],
            ),
            workspace_id=_WORKSPACE_ID,
        )
        available = {p1: False, p2: False}
        selected = service.select_model_profile(
            profile.id, available_profiles=available
        )
        assert selected is None


# ===================================================================
# Routing mode enum tests
# ===================================================================


class TestRoutingMode:
    def test_all_modes_exist(self) -> None:
        expected = {
            "offline_preferred",
            "cloud_preferred",
            "hybrid",
            "local_only",
        }
        assert {m.value for m in RoutingMode} == expected

    def test_string_enum_values(self) -> None:
        assert RoutingMode.cloud_preferred == "cloud_preferred"
        assert RoutingMode.local_only == "local_only"
