"""Pipeline stage implementations for the ``qatta`` core package.

Each subpackage is one stage; every stage is a pure function over the
``QattaManifest`` (read/modify/write via :class:`qatta.core.pipeline.
PipelineOrchestrator`), so stage caching through ``completed_stages``
stays deterministic.
"""
