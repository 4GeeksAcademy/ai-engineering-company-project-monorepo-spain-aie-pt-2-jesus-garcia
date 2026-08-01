class IncidentAnalysisError(Exception):
    """Base error for the incidents analysis domain."""


class EmptyFileError(IncidentAnalysisError):
    """The uploaded file has no content."""


class InvalidFormatError(IncidentAnalysisError):
    """The uploaded file is not a valid CSV or lacks required columns."""


class NoAnalysisError(IncidentAnalysisError):
    """There is no previous analysis available for export."""
