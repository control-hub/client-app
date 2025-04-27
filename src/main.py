import sys
import os
import asyncio
import subprocess
import socket
import uuid
import tempfile
import traceback
import logging
import time

from httpx import AsyncClient
from pocketbase import PocketBase
from pocketbase.models.dtos import RealtimeEvent
from dotenv import load_dotenv
from typing import TypedDict, Dict, Set, Callable, Optional, Any, Tuple


if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    
load_dotenv(override=True)

app_path = os.getcwd()
python_executable = os.path.join(app_path, "python", "python.exe")

logs_path = os.path.join(app_path, "logs")

os.makedirs(logs_path, exist_ok=True)

logger = logging.getLogger("control_hub")
logger.setLevel(logging.INFO)

proc_handler = logging.FileHandler(
    os.path.join(logs_path, "process.log"), encoding="utf-8"
)
proc_handler.setLevel(logging.INFO)
proc_handler.addFilter(lambda record: record.levelno <= logging.INFO)

error_handler = logging.FileHandler(
    os.path.join(logs_path, "error.log"), encoding="utf-8"
)
error_handler.setLevel(logging.ERROR)

formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
proc_handler.setFormatter(formatter)
error_handler.setFormatter(formatter)

logger.addHandler(proc_handler)
logger.addHandler(error_handler)


def handle_uncaught_exception(exc_type, exc_value, exc_tb):
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


sys.excepthook = handle_uncaught_exception

asyncio.get_event_loop().set_exception_handler(
    lambda loop, context: logger.error(
        "Asyncio exception", exc_info=context.get("exception")
    )
)


class Computer(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    ip: str
    mac: str
    name: str
    region: str
    status: str # 0: offline, 1: online, 2: busy
    token: str
    updated: str
    created: str


class ExecutionRecord(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    duration: float
    status: str # 0: pending, 1: running, 2: success, 3: error
    executable: str
    logs: str
    computer: str
    script: str
    user: str
    created: str
    updated: str

class NetworkUtils:
    @staticmethod
    async def get_local_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    @staticmethod
    async def get_mac_address() -> Optional[str]:
        node = uuid.getnode()
        if (node >> 40) & 1:
            return None
        return ":".join(("%012x" % node)[i : i + 2] for i in range(0, 12, 2)).upper()


class CodeExecutor:
    @staticmethod
    async def execute_code(code: str, execution_id: str) -> Tuple[str, bool]:
        return await CodeExecutor._run(code, execution_id)

    @staticmethod
    async def run_command(command: list[str]) -> dict:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            stdout_data, stderr_data = await process.communicate()
            output = (
                stdout_data.decode("cp866", errors="replace")
                + "\n"
                + stderr_data.decode("cp866", errors="replace")
            )

            return {
                "success": process.returncode == 0,
                "stdout": output,
                "code": process.returncode,
                "traceback": None
                if process.returncode == 0
                else f"Exit {process.returncode}\n\n{output}",
            }

        except Exception:
            tb = traceback.format_exc()
            return {
                "success": False,
                "code": -1,
                "stdout": "",
                "traceback": "EXECUTION ERROR\n\n" + tb,
            }

    @staticmethod
    async def _run(code: str, execution_id: str) -> Tuple[str, bool]:
        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f"exec_{execution_id}.py")

        logger.info(f"Executing in temp file: {temp_filename}")

        with open(temp_filename, "w", encoding="utf-8") as file:
            file.write(code)

        result = await CodeExecutor.run_command([python_executable, temp_filename])

        if result["success"]:
            logger.info(f"[{execution_id}] Success:\n{result['stdout']}")
        else:
            logger.error(f"[{execution_id}] Failure:\n{result['traceback']}")

        try:
            os.unlink(temp_filename)
        except Exception as err:
            logger.error(f"Temp deletion error: {err}", exc_info=err)

        return (
            result["stdout"] if result["success"] else result["traceback"],
            result["success"],
        )


class DatabaseClient:
    def __init__(self, server_url: str, token: str):
        self.pb = PocketBase(server_url)
        self.pb._inners.client = AsyncClient(base_url=server_url, timeout=None)
        self.token = token
        self.params = {"token": token}

    async def get_computer(self) -> Computer:
        data = await self.pb.collection("computers").get_first(
            {"params": self.params}
        )
        return Computer(**data)

    async def update_computer(self, computer_id: str, data: Dict[str, Any]) -> Computer:
        updated = await self.pb.collection("computers").update(
            computer_id, data, {"params": self.params}
        )
        return Computer(**updated)

    async def update_execution(
        self, execution_id: str, data: Dict[str, Any]
    ) -> ExecutionRecord:
        updated = await self.pb.collection("executions").update(
            execution_id, data, {"params": self.params}
        )
        return ExecutionRecord(**updated)

    async def subscribe_to_executions(
        self, computer_id: str, callback: Callable[[RealtimeEvent], Any]
    ):
        filter_query = f'computer.id="{computer_id}"'
        params = {
            "headers": {},
            "params": {"token": self.token, "filter": filter_query},
        }
        return await self.pb.collection("executions").subscribe_all(
            callback, params
        )

    async def keep_alive(self) -> None:
        while True:
            await asyncio.sleep(50 * 60)
            await self.pb.realtime._transmit_subscriptions(force=True)


class ExecutionTracker:
    def __init__(self):
        self.executed: Set[str] = set()
        self.active: Set[str] = set()

    def already_executed(self, execution_id: str) -> bool:
        return execution_id in self.executed

    def mark_executed(self, execution_id: str) -> None:
        self.executed.add(execution_id)

    def add_active(self, execution_id: str) -> bool:
        first_task = not self.active
        self.active.add(execution_id)
        return first_task

    def remove_active(self, execution_id: str) -> bool:
        self.active.discard(execution_id)
        return not self.active

    def active_count(self) -> int:
        return len(self.active)


class AgentService:
    def __init__(self, server_url: str, token: str):
        self.db_client = DatabaseClient(server_url, token)
        self.executor = CodeExecutor()
        self.tracker = ExecutionTracker()
        self.computer: Optional[Computer] = None

    async def initialize(self) -> None:
        self.computer = await self.db_client.get_computer()
        computer_data = {
            "ip": await NetworkUtils.get_local_ip(),
            "mac": await NetworkUtils.get_mac_address(),
            "status": 2,
        }
        self.computer = await self.db_client.update_computer(
            self.computer["id"], computer_data
        )
        logger.info(f"Initialized for: {self.computer['name']} ({self.computer['ip']})")

    async def update_status(self, status: int) -> None:
        try:
            self.computer = await self.db_client.update_computer(
                self.computer["id"], {"status": status}
            )
            logger.info(f"Status updated: {status}")
        except Exception as err:
            logger.error(f"Status update failed: {err}", exc_info=err)

    async def handle_event(self, event: RealtimeEvent) -> None:
        if event["action"] != "create":
            return

        execution_record = event["record"]
        execution_id = execution_record.get("id")

        if self.tracker.already_executed(execution_id):
            return

        self.tracker.mark_executed(execution_id)

        if execution_record.get("completed"):
            return

        asyncio.create_task(self.process_execution(execution_record, execution_id))

    async def process_execution(
        self, execution_record: Dict[str, Any], execution_id: str
    ) -> None:
        first = self.tracker.add_active(execution_id)
        if first:
            await self.update_status(1)

        logger.info(
            f"Starting task: {execution_id} (Active: {self.tracker.active_count()})"
        )
        await self.db_client.update_execution(
            execution_id, {"logs": "Execution started...\n", "status": "1"}
        )

        start_time = time.time()
        logs, succeeded = await self.executor.execute_code(
            execution_record.get("executable"), execution_id
        )
        duration = time.time() - start_time

        await self.db_client.update_execution(
            execution_id,
            {
                "logs": logs,
                "completed": True,
                "status": "2" if succeeded else "3",
                "duration": duration,
            },
        )

        last = self.tracker.remove_active(execution_id)
        if last:
            await self.update_status(2)

        logger.info(
            f"Task completed: {execution_id} (Success: {succeeded}, Duration: {duration:.2f}s, Remaining: {self.tracker.active_count()})"
        )

    async def run(self) -> None:
        logger.info("Connecting...")
        unsubscribe = await self.db_client.subscribe_to_executions(
            self.computer["id"], self.handle_event
        )
        logger.info("Subscribed, waiting for tasks...")

        try:
            while True:
                await self.db_client.keep_alive()
        finally:
            if self.computer:
                await self.db_client.update_computer(self.computer["id"], {"status": 0})
            if "unsubscribe" in locals():
                await unsubscribe()
                logger.info("Unsubscribed")


async def main() -> None:
    SERVER_URL = "https://pb.control-hub.org"
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("TOKEN not set")
        return

    agent = AgentService(SERVER_URL, TOKEN)
    await agent.initialize()
    await agent.run()


if __name__ == "__main__":
    logger.info("Starting agent...")
    asyncio.run(main())
