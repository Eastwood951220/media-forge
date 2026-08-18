"""Agent runtime error classes and message mapping."""

from __future__ import annotations

from backend.app.modules.crawler.agent.constants import AGENT_MAX_ATTEMPTS


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


class AgentUpgradeRequiredError(AgentRuntimeError):
    """Raised when the agent protocol version is too low — extension must be upgraded."""

    def __init__(self, message: str = "Chrome Agent 版本过低，请升级扩展后重试") -> None:
        super().__init__(message)


class AgentClaimTimeoutError(AgentRuntimeError):
    """Raised when the claim phase times out — no agent picked up the item."""


class AgentExecutionTimeoutError(AgentRuntimeError):
    """Raised when the execution phase times out — agent took too long on a claimed task."""


AGENT_ERROR_MESSAGES: dict[str, str] = {
    # Connection / protocol
    "agent_connection_lost": "Agent 连接丢失",
    "agent_disconnect": "Agent 断开连接",
    "agent_timeout": "Agent 响应超时",
    "agent_handshake_failed": "Agent 握手失败",
    "upgrade_required": "需要更新 Agent 版本",
    "protocol_unsupported": "不支持的协议版本",
    # Claim / assignment
    "agent_claim_timeout": "Agent 未在 10 秒内领取任务",
    "agent_assignment_refused": "Agent 拒绝了任务分配",
    # Execution
    "agent_execution_timeout": "页面执行超时",
    "agent_work_failed": "任务执行失败",
    # Retries
    "work.requeued": "任务被 Agent 释放后重试",
    "work.failed": "任务达到最大尝试次数",
    # Crawl errors
    "parser_navigation_failed": "页面导航失败",
    "parser_empty_detail": "详情页内容为空",
    "parser_download_trigger_failed": "下载触发失败",
    "parser_unexpected_page": "页面类型不符合预期",
    "crawl_reached_page_limit": "达到页面爬取数量上限",
    "crawl_reached_page_urgent_limit": "达到紧急页面上限",
    "crawl_data_extraction_failed": "数据提取失败",
    "run_vm_stopped": "运行被中断",
}


def agent_error_message(reason: str) -> str:
    """Return a human-readable Chinese message for the given error reason code.

    Falls back to the raw reason string when there is no known mapping.
    """
    return AGENT_ERROR_MESSAGES.get(reason, reason)
