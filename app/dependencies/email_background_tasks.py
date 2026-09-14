from typing import Protocol

from fastapi import BackgroundTasks, Request

from app.services.email_jobs import EmailTaskScheduler


class EmailTaskLauncher(Protocol):
    async def start(self, job_id: int) -> None: ...


class FastAPIEmailTaskScheduler:
    def __init__(self, background_tasks: BackgroundTasks, manager: EmailTaskLauncher) -> None:
        self.background_tasks = background_tasks
        self.manager = manager

    def schedule(self, job_id: int) -> None:
        self.background_tasks.add_task(self.manager.start, job_id)


def get_email_task_scheduler(
    request: Request,
    background_tasks: BackgroundTasks,
) -> EmailTaskScheduler:
    manager: EmailTaskLauncher = request.app.state.email_background_task_manager
    return FastAPIEmailTaskScheduler(background_tasks, manager)
