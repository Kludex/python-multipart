import atheris


class EnhancedDataProvider(atheris.FuzzedDataProvider):
    def ConsumeRandomBytes(self) -> bytes:
        return self.ConsumeBytes(self.ConsumeIntInRange(0, self.remaining_bytes()))

    def ConsumeRandomString(self) -> str:
        return self.ConsumeUnicodeNoSurrogates(self.ConsumeIntInRange(0, self.remaining_bytes()))
