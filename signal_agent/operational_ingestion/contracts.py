from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from .models import (
    AcquisitionIntent,
    CapturedPage,
    Clock,
    CompletedRunReference,
)


class OperationalRequest(Protocol):
    @property
    def request_fingerprint(self) -> str: ...


class RemoteObservation(Protocol):
    @property
    def response_body(self) -> bytes: ...


class OperationalTransport(Protocol):
    def fetch(self, request: OperationalRequest) -> RemoteObservation: ...


class RemotePageSource(Protocol):
    def initial_request(self, intent: AcquisitionIntent) -> OperationalRequest: ...

    def assess_capture(self, capture: CapturedPage) -> CapturedPage: ...

    def next_request(self, page: CapturedPage) -> OperationalRequest | None: ...

    def assemble(self, pages: Sequence[CapturedPage], destination: Path) -> Path: ...


class GovernedProcessor(Protocol):
    def process(
        self,
        *,
        bounded_material_path: Path,
        governed_run_root: Path,
        clock: Clock,
    ) -> CompletedRunReference: ...


class FailureInjector(Protocol):
    def __call__(self, stage: str) -> None: ...
