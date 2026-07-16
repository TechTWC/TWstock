class MarketDataError(Exception): pass
class SourceUnavailableError(MarketDataError): pass
class MalformedSourceError(MarketDataError): pass
class DataValidationError(MarketDataError): pass
class DuplicateTradeDateError(DataValidationError): pass
