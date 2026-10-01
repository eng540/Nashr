from enum import StrEnum


class ProductionJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProductionJobItemStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProductionScope(StrEnum):
    SOURCE = "SOURCE"
    TOPIC = "TOPIC"
    SELECTION = "SELECTION"
