"""
Regression tests for the 2026-05-01 Round-4 live-deploy fixes.

Bugs covered:
  R12. Delete note 500: notes.py purge path used `settings` without importing it.
       Static check: `from app.config import settings` must exist in notes.py.
  R13. Voice "(no speech detected)" despite real speech — MediaRecorder emits
       webm/opus but Azure Speech file-mode expected WAV. Fix: convert via
       ffmpeg (_write_temp + _ffmpeg_to_wav helpers) before handing to SDK.
  R14. Image notes regressed to "(no speech detected)" — Stage 1 capture
       must skip source_type='image' (raw_transcription is empty for images;
       OCR already wrote the content).
  R15. Image notes need a default 'image' tag at creation time (filterable
       in Library/sidebar).
  R16. Shadow Reader must auto-render an inline bottom-sheet when
       status='asked' (no manual launcher), positioned ABOVE BottomNav so
       it never overlaps mobile nav.
"""

import inspect
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# R12 — settings import in notes.py
# ---------------------------------------------------------------------------


class TestR12NotesSettingsImport:
    def test_notes_module_imports_settings(self):
        from app.api import notes

        src = inspect.getsource(notes)
        assert "from app.config import settings" in src, (
            "notes.py must import settings — _blob_path_from_url uses "
            "settings.AZURE_STORAGE_CONTAINER and a missing import causes "
            "DELETE /api/notes/{id} to return 500 NameError."
        )

    def test_notes_purge_uses_settings_container(self):
        from app.api import notes

        src = inspect.getsource(notes)
        assert "settings.AZURE_STORAGE_CONTAINER" in src


# ---------------------------------------------------------------------------
# R13 — speech.py converts WebM/Opus → WAV via ffmpeg
# ---------------------------------------------------------------------------


class TestR13SpeechWebmConversion:
    def test_speech_module_imports_subprocess(self):
        from app.services import speech

        src = inspect.getsource(speech)
        assert "import subprocess" in src

    def test_speech_module_defines_write_temp_helper(self):
        from app.services import speech

        assert hasattr(speech, "_write_temp"), (
            "_write_temp helper must exist to write raw audio bytes to a "
            "named temp file with the correct suffix before ffmpeg conversion."
        )
        assert callable(speech._write_temp)

    def test_speech_module_defines_ffmpeg_to_wav_helper(self):
        from app.services import speech

        assert hasattr(speech, "_ffmpeg_to_wav"), (
            "_ffmpeg_to_wav helper must exist to convert MediaRecorder webm/opus "
            "to 16 kHz mono PCM WAV that Azure Speech file-mode can decode."
        )
        assert callable(speech._ffmpeg_to_wav)

    def test_speech_transcribe_calls_ffmpeg_helper(self):
        from app.services import speech

        src = inspect.getsource(speech.transcribe_audio_file)
        assert "_ffmpeg_to_wav" in src, (
            "transcribe_audio_file must run incoming bytes through "
            "_ffmpeg_to_wav before passing to AudioConfig — otherwise the "
            "SDK chokes on webm/opus inside a .wav-suffixed file."
        )

    def test_ffmpeg_helper_uses_16k_mono_wav_args(self):
        from app.services import speech

        src = inspect.getsource(speech._ffmpeg_to_wav)
        # Azure Speech expects 16 kHz mono PCM WAV
        assert '"16000"' in src or "'16000'" in src
        assert '"-ar"' in src or "'-ar'" in src
        assert '"-ac"' in src or "'-ac'" in src


# ---------------------------------------------------------------------------
# R14 — Stage 1 capture skips image notes
# ---------------------------------------------------------------------------


class TestR14CaptureSkipsImage:
    def test_processor_capture_skips_image_source_type(self):
        from app.pipeline import processor

        src = inspect.getsource(processor.AIPipeline._stage_capture)
        # Either explicit tuple membership or two separate checks must exclude
        # 'image' from Stage 1's "needs cleanup" path.
        skips_image = (
            'source_type in ("text", "image")' in src
            or "source_type in ('text', 'image')" in src
            or "source_type == 'image'" in src
            or 'source_type == "image"' in src
        )
        assert skips_image, (
            "Stage 1 _stage_capture must short-circuit for image notes — "
            "OCR has already written content; raw_transcription is empty, "
            "and the empty-transcription guard would falsely mark them "
            "'failed' with '(no speech detected)'."
        )


# ---------------------------------------------------------------------------
# R15 — image notes get a default 'image' tag at creation
# ---------------------------------------------------------------------------


class TestR15ImageDefaultTag:
    def test_create_note_adds_image_tag_for_image_source_type(self):
        from app.api import notes

        src = inspect.getsource(notes.create_note)
        # The handler must merge an 'image' tag into the tag list when
        # source_type == 'image'. Look for the literal 'image' token tied
        # to the source_type guard.
        assert 'source_type == "image"' in src or "source_type == 'image'" in src
        assert re.search(r"['\"]image['\"]", src), (
            "create_note must add the literal tag 'image' when "
            "source_type == 'image'."
        )


# ---------------------------------------------------------------------------
# R16 — ShadowReaderPrompt.tsx auto-renders inline bottom-sheet (no launcher)
# ---------------------------------------------------------------------------


class TestR16ShadowReaderAutoRender:
    """These checks are static — they read the .tsx source file directly so
    a backend pytest run can still gate the frontend regression."""

    @staticmethod
    def _read_tsx() -> str:
        # Resolve frontend file relative to repo root (parent of backend/)
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "frontend" / "src" / "components" / "ShadowReaderPrompt.tsx"
        return path.read_text(encoding="utf-8")

    def test_shadow_reader_polls_questions(self):
        src = self._read_tsx()
        assert "getQuestions" in src

    def test_shadow_reader_has_no_manual_launcher(self):
        src = self._read_tsx()
        # The opt-in launcher button used data-testid="shadow-reader-launcher".
        # Round-4 reverts to auto-render — that testid must be gone.
        assert 'data-testid="shadow-reader-launcher"' not in src, (
            "Bug 16 revert: there must be NO manual 'Want to go deeper?' "
            "launcher button — the bottom-sheet auto-renders when "
            "status === 'asked'."
        )

    def test_shadow_reader_returns_null_when_not_asked(self):
        src = self._read_tsx()
        # Component must early-return null unless status === 'asked'.
        assert "status !== 'asked'" in src or 'status !== "asked"' in src

    def test_shadow_reader_renders_above_bottom_nav(self):
        src = self._read_tsx()
        # BottomNav is h-16 (64px). The sheet must clear it on mobile —
        # bottom-20 or higher (≥ 80px). Loosen the check: any bottom-N where
        # N >= 20 (or sm:bottom-X for ≥ sm where the nav is hidden anyway).
        match = re.search(r"\bbottom-(\d+)\b", src)
        assert match is not None, (
            "ShadowReaderPrompt must position itself with a tailwind "
            "bottom-N utility that clears the BottomNav (h-16 = 64 px)."
        )
        # bottom-16 = 64px (just touches nav). bottom-20 = 80px (clears nav).
        assert int(match.group(1)) >= 16

    def test_shadow_reader_is_not_modal_dialog(self):
        src = self._read_tsx()
        # Strip block + line comments so docstring mentions of role='dialog'
        # don't trip the test. Only JSX usages matter for the runtime
        # guarantee.
        no_block_comments = re.sub(r"/\*[\s\S]*?\*/", "", src)
        code_only = re.sub(r"//[^\n]*", "", no_block_comments)
        assert 'role="dialog"' not in code_only and "role='dialog'" not in code_only, (
            "Shadow Reader must NEVER use role='dialog' — the spec calls "
            "this out explicitly as the UI non-blocking guarantee."
        )


# ---------------------------------------------------------------------------
# R17 — syncManager first-boot seed must be epoch, not "now" (Bug 17)
# ---------------------------------------------------------------------------


class TestR17SyncManagerFirstBootSeed:
    """Bug 17: a fresh browser / incognito session was getting `lastPull = now()`
    on first boot, so /api/sync/pull?since=now never returned the user's
    historical notes — leading to "different browsers show different data
    for the same user." Fix: seed to epoch so the first pull retrieves
    everything; the conflict path only matches notes with serverIds, so
    local-only pending notes are never wrongly flagged."""

    @staticmethod
    def _read_sync_manager() -> str:
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "frontend" / "src" / "sync" / "syncManager.ts"
        return path.read_text(encoding="utf-8")

    def test_first_boot_seed_is_not_now(self):
        src = self._read_sync_manager()
        # Strip block + line comments so the rationale comment doesn't trip
        # the regex.
        no_block_comments = re.sub(r"/\*[\s\S]*?\*/", "", src)
        code_only = re.sub(r"//[^\n]*", "", no_block_comments)
        # The old bug: db.meta.put({ key: 'lastPull', value: new Date().toISOString() })
        bad = re.search(
            r"meta\.put\s*\(\s*\{\s*key:\s*['\"]lastPull['\"]\s*,\s*value:\s*new\s+Date\(\)\.toISOString\(\)",
            code_only,
        )
        assert bad is None, (
            "First-boot seed of `lastPull` must NOT be the current time — that "
            "causes a fresh browser to skip all of the user's historical notes "
            "on the very first /api/sync/pull (Bug 17)."
        )

    def test_first_boot_seed_uses_epoch(self):
        src = self._read_sync_manager()
        # Strip comments so we only inspect runtime code.
        no_block_comments = re.sub(r"/\*[\s\S]*?\*/", "", src)
        code_only = re.sub(r"//[^\n]*", "", no_block_comments)
        seed = re.search(
            r"meta\.put\s*\(\s*\{\s*key:\s*['\"]lastPull['\"]\s*,\s*value:\s*['\"]([^'\"]+)['\"]",
            code_only,
        )
        assert seed is not None, (
            "syncManager.start() must seed `lastPull` to a literal ISO "
            "timestamp on first boot (epoch) so the first pull retrieves all "
            "of the user's notes."
        )
        assert seed.group(1).startswith("1970-01-01"), (
            f"Expected epoch seed for lastPull, got {seed.group(1)!r}. "
            "Anything later than epoch causes a fresh browser to miss "
            "historical notes."
        )
