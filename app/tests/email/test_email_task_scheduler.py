from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.dependencies.email_background_tasks import FastAPIEmailTaskScheduler, get_email_task_scheduler


class FakeManager:
    async def start(self, _job_id: int) -> None:
        return None


def test_scheduler_registers_only_the_lightweight_manager_launcher() -> None:
    background_tasks = BackgroundTasks()
    manager = FakeManager()
    scheduler = FastAPIEmailTaskScheduler(background_tasks, manager)

    scheduler.schedule(41)

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func == manager.start
    assert task.args == (41,)


def test_dependency_uses_the_application_manager() -> None:
    background_tasks = BackgroundTasks()
    manager = FakeManager()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(email_background_task_manager=manager)))

    scheduler = get_email_task_scheduler(request, background_tasks)

    assert isinstance(scheduler, FastAPIEmailTaskScheduler)
    assert scheduler.manager is manager
