"""
V26.3 - 任务管理器
用于管理正在运行的后台任务，支持取消
"""

import threading
import uuid
from typing import Dict, Any, Optional


class TaskManager:
    """
    任务管理器
    负责管理所有正在运行的任务，支持取消
    """

    def __init__(self):
        # 任务字典：task_id -> task_info
        self._tasks: Dict[str, Dict[str, Any]] = {}
        # 线程锁，保证线程安全
        self._lock = threading.Lock()

    def create_task(self, task_type: str) -> str:
        """
        创建一个新任务
        :param task_type: 任务类型（比如 "generate_outline"）
        :return: task_id
        """
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "status": "running",  # running / completed / failed / cancelled
                "progress": "初始化中...",  # V26.5: 当前进度
                "result": None,
                "error": None,
                "cancelled": False,
            }
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        :param task_id: 任务ID
        :return: 任务信息，如果不存在返回 None
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                # 返回一个副本，避免外部修改
                return dict(task)
            return None

    def cancel_task(self, task_id: str) -> bool:
        """
        取消一个任务
        :param task_id: 任务ID
        :return: 是否成功取消
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task["status"] == "running":
                task["cancelled"] = True
                task["status"] = "cancelled"
                return True
            return False

    def complete_task(self, task_id: str, result: Any):
        """
        标记任务为完成
        :param task_id: 任务ID
        :param result: 任务结果
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task["status"] == "running":
                task["status"] = "completed"
                task["result"] = result

    def fail_task(self, task_id: str, error: str):
        """
        标记任务为失败
        :param task_id: 任务ID
        :param error: 错误信息
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task["status"] == "running":
                task["status"] = "failed"
                task["error"] = error

    def is_cancelled(self, task_id: str) -> bool:
        """
        检查任务是否被取消（这个方法由后台任务在运行过程中调用）
        :param task_id: 任务ID
        :return: 是否被取消
        """
        with self._lock:
            task = self._tasks.get(task_id)
            return task["cancelled"] if task else False

    def update_progress(self, task_id: str, progress: str):
        """
        更新任务的进度（V26.5）
        :param task_id: 任务ID
        :param progress: 进度描述（比如 "检索中..."、"证据抽取中..."）
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task["status"] == "running":
                task["progress"] = progress

    def get_running_task(self) -> Optional[Dict[str, Any]]:
        """
        V26.5: 获取当前运行中的任务（用于刷新页面后恢复任务）
        :return: 运行中的任务，如果没有返回 None
        """
        with self._lock:
            for task in self._tasks.values():
                if task["status"] == "running":
                    return dict(task)
            return None

    def cleanup_old_tasks(self, max_count: int = 100):
        """
        清理旧任务，防止内存泄漏
        :param max_count: 最多保留多少个任务
        """
        with self._lock:
            if len(self._tasks) <= max_count:
                return
            # 按完成时间排序，删除旧的
            # 简单版本：直接删除最早的几个任务
            sorted_tasks = sorted(
                self._tasks.items(),
                key=lambda x: x[1].get("created_at", 0)
            )
            # 删除超过 max_count 的部分
            to_delete = len(self._tasks) - max_count
            for i in range(to_delete):
                del self._tasks[sorted_tasks[i][0]]


# 全局任务管理器实例
task_manager = TaskManager()
