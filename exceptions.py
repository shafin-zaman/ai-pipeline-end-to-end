class PipelineError(Exception):
    def __init__(self, message: str, stage: str = "unknown"):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")
