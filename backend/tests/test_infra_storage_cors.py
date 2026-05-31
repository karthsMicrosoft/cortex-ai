"""Round 31 — Azure Blob CORS guard rail.

Pins the contract that ``infra/main.bicep`` and ``infra/modules/storage.bicep``
declare a ``Microsoft.Storage/storageAccounts/blobServices`` resource with
CORS rules that allow GET/HEAD/OPTIONS from the configured frontend origin.

Why this exists: iOS Safari refuses to play SAS-signed audio from Azure
Blob Storage when the storage account has no CORS rules. wavesurfer.js
(MusicPlayer) sets ``crossOrigin="anonymous"`` on its underlying
``<audio>`` element AND uses ``fetch()`` to download the bytes for
waveform peaks. Without ``Access-Control-Allow-Origin`` from the Blob
endpoint, Safari blocks both paths.

We fix this by adding a ``blobServices/default`` resource with a CORS
rule on the storage account. This test ensures a future Bicep refactor
cannot silently re-break it.
"""

from pathlib import Path

import pytest

INFRA_ROOT = Path(__file__).resolve().parents[2] / "infra"
MAIN_BICEP = INFRA_ROOT / "main.bicep"
STORAGE_MODULE = INFRA_ROOT / "modules" / "storage.bicep"


def _read(path: Path) -> str:
    assert path.exists(), f"Expected file does not exist: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def main_bicep() -> str:
    return _read(MAIN_BICEP)


@pytest.fixture(scope="module")
def storage_module() -> str:
    return _read(STORAGE_MODULE)


class TestBlobServicesResourceExists:
    """Both bicep files declare a blobServices/default resource so CORS
    can be configured at the service level."""

    def test_main_bicep_declares_blob_services(self, main_bicep: str):
        assert "Microsoft.Storage/storageAccounts/blobServices" in main_bicep, (
            "infra/main.bicep must declare a blobServices resource so "
            "CORS rules survive a redeploy (Round 31, DECISIONS § 22aq)"
        )

    def test_storage_module_declares_blob_services(self, storage_module: str):
        assert "Microsoft.Storage/storageAccounts/blobServices" in storage_module, (
            "infra/modules/storage.bicep must declare a blobServices "
            "resource so CORS rules survive a redeploy (Round 31, "
            "DECISIONS § 22aq)"
        )


class TestCorsRulesInBicep:
    """The blobServices resource must carry corsRules with GET/HEAD/OPTIONS
    allowed for the frontend origin."""

    @pytest.mark.parametrize(
        "label,source_fixture",
        [("main", "main_bicep"), ("module", "storage_module")],
    )
    def test_corsRules_declared(self, label, source_fixture, request):
        src: str = request.getfixturevalue(source_fixture)
        assert "corsRules" in src, (
            f"{label} bicep must declare corsRules under blobServices "
            "properties.cors so iOS Safari can fetch audio cross-origin"
        )

    @pytest.mark.parametrize(
        "method", ["'GET'", "'HEAD'", "'OPTIONS'"],
    )
    def test_main_bicep_allows_required_methods(self, main_bicep: str, method: str):
        assert method in main_bicep, (
            f"infra/main.bicep CORS rule must allow {method} (preflight "
            "+ audio fetch). Removing any of these breaks iOS Safari "
            "playback."
        )

    @pytest.mark.parametrize(
        "method", ["'GET'", "'HEAD'", "'OPTIONS'"],
    )
    def test_storage_module_allows_required_methods(self, storage_module: str, method: str):
        assert method in storage_module, (
            f"infra/modules/storage.bicep CORS rule must allow {method}"
        )

    def test_main_bicep_uses_frontendOrigin(self, main_bicep: str):
        # The frontendOrigin Bicep param is the source of truth for the
        # SWA URL. CORS rules must reference it (not hardcode a URL) so
        # dev / staging / prod deploys all wire correctly.
        # Look for "frontendOrigin" appearing inside the allowedOrigins
        # block — a literal full URL would mean the rule is stuck to one
        # environment.
        cors_block = main_bicep.split("allowedOrigins", 1)
        assert len(cors_block) > 1, "main.bicep must have an allowedOrigins block"
        # First closing bracket after allowedOrigins[ — slice that fragment.
        fragment = cors_block[1].split("]", 1)[0]
        assert "frontendOrigin" in fragment, (
            "main.bicep CORS allowedOrigins must include the "
            "frontendOrigin parameter so the same template works across "
            "environments"
        )

    def test_storage_module_uses_frontendOrigin(self, storage_module: str):
        cors_block = storage_module.split("allowedOrigins", 1)
        assert len(cors_block) > 1, "storage.bicep must have an allowedOrigins block"
        fragment = cors_block[1].split("]", 1)[0]
        assert "frontendOrigin" in fragment, (
            "storage.bicep CORS allowedOrigins must include the "
            "frontendOrigin parameter"
        )

    def test_local_dev_origin_allowed(self, main_bicep: str):
        # localhost:5173 is the vite dev server — devs need to be able to
        # play audio while iterating locally.
        assert "http://localhost:5173" in main_bicep, (
            "CORS allowedOrigins should include http://localhost:5173 "
            "for the local vite dev server"
        )
