class AgentRuntimeError(RuntimeError):
    """Base error for crawler agent runtime failures."""


class AgentUnavailableError(AgentRuntimeError):
    def __init__(self, message: str = "Chrome Agent 未在线，无法执行 JavDB Agent 爬取") -> None:
        super().__init__(message)


class AgentWorkTimeoutError(AgentRuntimeError):
    def __init__(self, message: str = "Chrome Agent 执行超时") -> None:
        super().__init__(message)


class AgentWorkFailedError(AgentRuntimeError):
    pass


class AgentWorkStopped(AgentRuntimeError):
    def __init__(self, message: str = "用户停止任务") -> None:
        super().__init__(message)
