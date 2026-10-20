"""Pipeline orchestration for the ``qatta`` core package.

Responsibilities (rule 2 of the architectural rules):
- Own the single ``qatta_manifest.json`` per project.
- Serialize/deserialize through :mod:`qatta.core.schema` strictly.
- Every stage reads and writes the manifest through the orchestrator.
- A stage whose name is already recorded in ``completed_stages`` is skipped
  unless ``force=True`` (artifact-based caching).
- Manifest writes are atomic (temp file + ``os.replace``) so a crash can
  never leave a half-written manifest.

Fail-closed policy (honest, no placeholders):
- This increment implements orchestration and duration probing only. It
  does NOT include stages that pretend to do work; transcription/candidate
  stages will be added in subsequent increments and must register through
  :meth:`PipelineOrchestrator.stage`.
- Cloud/YouTube backends are configuration values only; the orchestrator
  refuses to run a stage whose selected backend is gated (fail-closed).
"""

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from qatta.core.config import QattaSettings
from qatta.core.schema import QattaManifest


class PipelineError(Exception):
    """Raised with an honest, actionable message on pipeline failure."""


class PipelineOrchestrator:
    """Loads and atomically persists the manifest; runs/caches stages."""

    def __init__(
        self,
        project_id: str,
        source_path: str | Path | None = None,
        work_dir: str | Path | None = None,
        settings: QattaSettings | None = None,
    ):
        self.settings = settings or QattaSettings()
        self.project_id = project_id
        self.work_dir = (
            Path(work_dir) if work_dir else self.settings.manifest_path(project_id).parent
        )
        self.manifest_path = self.work_dir / "qatta_manifest.json"

        # Stage registry: name -> callable(manifest) -> manifest
        self._stage_functions: dict[str, Callable[[QattaManifest], QattaManifest]] = {}

        if self.manifest_path.is_file():
            self.manifest = self.load_manifest()
        else:
            if not source_path:
                raise PipelineError(
                    f"No manifest exists at {self.manifest_path} and no "
                    "source_path was provided; cannot initialize a project."
                )
            self.manifest = self._initialize_manifest(Path(source_path))
            self.save_manifest()

    # ------------------------------------------------------------------
    # Manifest persistence
    # ------------------------------------------------------------------
    @staticmethod
    def _require_ffprobe(timeout_s: float) -> str:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise PipelineError(
                "ffprobe was not found on PATH. Install ffmpeg/ffprobe to "
                "initialize Laqta projects (e.g. 'sudo dnf install ffmpeg' "
                "on Fedora)."
            )
        return ffprobe

    def _initialize_manifest(self, source_path: Path) -> QattaManifest:
        """Create a new manifest for a source media file (real ffprobe)."""
        if not source_path.is_file():
            raise PipelineError(f"Source media does not exist: {source_path}")
        duration = self.probe_duration_sec(source_path)
        return QattaManifest(
            project_id=self.project_id,
            source_path=str(source_path.resolve()),
            duration_sec=duration,
        )

    def probe_duration_sec(self, media_path: Path) -> float:
        """Real media duration via ffprobe (subprocess arg array, bounded)."""
        ffprobe = self._require_ffprobe(self.settings.ffprobe_timeout_seconds)
        try:
            # Fixed argv array, no shell, no untrusted interpolation
            # (path is a file location, never shell-parsed).
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(media_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.settings.ffprobe_timeout_seconds,
                check=True,
            )
            data = json.loads(proc.stdout)
            duration = float(data["format"]["duration"])
        except subprocess.TimeoutExpired as e:
            raise PipelineError(
                f"ffprobe timed out after {self.settings.ffprobe_timeout_seconds}s on {media_path}."
            ) from e
        except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError, ValueError) as e:
            raise PipelineError(
                f"ffprobe could not determine duration for {media_path}: {e}"
            ) from e
        if duration <= 0:
            raise PipelineError(f"ffprobe reported non-positive duration for {media_path}.")
        return duration

    def load_manifest(self) -> QattaManifest:
        """Strictly parse the persisted manifest (fail loudly on corruption)."""
        try:
            raw = self.manifest_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except OSError as e:
            raise PipelineError(f"Cannot read manifest at {self.manifest_path}: {e}") from e
        except json.JSONDecodeError as e:
            raise PipelineError(
                f"Manifest at {self.manifest_path} is not valid JSON (corrupted "
                "or hand-edited). Restore it from backup or delete it to "
                "restart the pipeline (source media is never touched)."
            ) from e

        version = data.get("schema_version", 1)
        if not isinstance(version, int) or version > 1:
            raise PipelineError(
                f"Manifest schema_version {version!r} at {self.manifest_path} "
                "is newer than this Laqta build understands (max 1)."
            )
        try:
            return QattaManifest.model_validate(data)
        except Exception as e:  # pydantic ValidationError
            raise PipelineError(
                f"Manifest at {self.manifest_path} failed strict validation: {e}"
            ) from e

    def save_manifest(self) -> Path:
        """Atomically persist the manifest (tmp file in same dir + replace)."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.manifest_path.with_name(f".{self.manifest_path.name}.tmp-{os.getpid()}")
        try:
            tmp_path.write_text(
                self.manifest.model_dump_json(),
                encoding="utf-8",
            )
            os.replace(tmp_path, self.manifest_path)
        except OSError as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise PipelineError(f"Failed to persist manifest at {self.manifest_path}: {e}") from e
        return self.manifest_path

    # ------------------------------------------------------------------
    # Stage registry and cached execution
    # ------------------------------------------------------------------
    def stage(
        self,
        name: str,
        fn: Callable[[QattaManifest], QattaManifest] | None = None,
    ) -> Callable:
        """Register (or use as decorator for) a pipeline stage function.

        The decorated callable receives the current manifest and must return
        a manifest. It may mutate fields on the manifest it receives and
        return it — the orchestrator revalidates strictly before persisting.
        """

        def wrapper(func: Callable[[QattaManifest], QattaManifest]):
            self._stage_functions[name] = func
            return func

        return wrapper(fn) if fn else wrapper

    # TODO(stage-types): prefer returning new manifest objects inside stages.
    def run_stage(self, name: str, force: bool = False) -> dict:
        """Run one registered stage with artifact caching.

        Returns an honest execution report:
          - ``{"stage": name, "executed": False}`` when the stage was already
            completed (and force=False) — the cached manifest on disk IS the
            artifact, no work is repeated.
          - ``{"stage": name, "executed": True}`` after running, validating
            and atomically persisting the updated manifest.
        """
        if name not in self._stage_functions:
            registered = (
                ", ".join(sorted(self._stage_functions))
                if self._stage_functions
                else "none — no stage has been implemented in this increment"
            )
            raise PipelineError(
                f"Stage '{name}' is not registered. Registered stages: {registered}."
            )

        if not force and name in self.manifest.completed_stages:
            return {"stage": name, "executed": False, "skipped_cached": True}

        fn = self._stage_functions[name]
        gated_backends = ("groq_api", "youtube_subs_first")
        backend_selected = self.settings.transcription_backend
        word_modes = ("transcribe", "transcript")
        if (
            any(marker in name for marker in word_modes)
            and backend_selected in gated_backends
            and not self.settings.cloud_backend_permitted(backend_selected)
        ):
            raise PipelineError(
                "Transcription backend "
                f"'{backend_selected}' is selected but not permitted: "
                "cloud/URL backends require explicit opt-in "
                "(QATTA_ALLOW_CLOUD_APIS=true + key, or "
                "QATTA_ENABLE_URL_INGESTION=true). Nothing left the "
                "device; no work was performed."
            )

        started = time.monotonic()
        updated = fn(self.manifest)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(updated, QattaManifest):
            raise PipelineError(
                f"Stage '{name}' returned {type(updated).__name__} instead of "
                "a QattaManifest; refusing to persist."
            )
        # MEASURED wall time per stage — honest benchmark data, surfaced
        # in the manifest (no derived performance claims are ever made).
        timings = dict(updated.stage_timings_ms)
        timings[name] = timings.get(name, 0) + elapsed_ms
        payload = updated.model_dump()
        payload["stage_timings_ms"] = timings
        updated = updated.model_validate(payload)
        if name not in updated.completed_stages:
            updated.completed_stages.append(name)
        # Fail-closed duplicate guard (schema also rejects duplicates).
        if len(updated.completed_stages) != len(set(updated.completed_stages)):
            raise PipelineError(f"Stage '{name}' produced duplicate completed_stages entries.")
        self.manifest = updated
        self.save_manifest()
        return {"stage": name, "executed": True}
