from uuid import uuid4

from app.models.contracts import AgentMessage, AgentRole, RunRequest
from app.models.workflow import Plan, WorkflowTask


class CoordinatorAgent:
    async def plan(self, message: AgentMessage[RunRequest]) -> Plan:
        retrieval = tuple(
            WorkflowTask(
                task_id=uuid4(), agent=AgentRole.RETRIEVAL, source_id=source_id,
                objective=message.content.question,
            )
            for source_id in message.content.source_ids
        )
        analysis = WorkflowTask(
            task_id=uuid4(), agent=AgentRole.ANALYSIS,
            objective=f"Identify candidate evidence for: {message.content.question}",
            dependency_ids=tuple(task.task_id for task in retrieval),
        )
        verification = WorkflowTask(
            task_id=uuid4(), agent=AgentRole.VERIFICATION,
            objective="Check candidate references against the retrieved passages.",
            dependency_ids=(analysis.task_id, *analysis.dependency_ids),
        )
        synthesis = WorkflowTask(
            task_id=uuid4(), agent=AgentRole.SYNTHESIS,
            objective="Record the disposition of the assessed candidates.",
            dependency_ids=(verification.task_id,),
        )
        return Plan(tasks=(*retrieval, analysis, verification, synthesis))
