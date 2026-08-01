"""A catalog candidate that is deliberately hidden in the selector test."""


class HiddenAdapter:
    def adapt(self, value: str) -> str:
        return value
