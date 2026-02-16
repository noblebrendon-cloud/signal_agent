class StubProvider:
    def call(self, model: str, prompt: str) -> str:
        return f"[ok:{model}] {prompt[:60]}"
