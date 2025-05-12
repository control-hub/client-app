import copy
import sys
import os
import asyncio
import subprocess
import socket
import uuid
import tempfile
import traceback
import logging
import shutil
import time
import json
import httpx

from httpcore import ConnectError as HTTPCoreConnectError
from httpx import AsyncClient, Timeout
from pocketbase import PocketBase
from pocketbase.models.dtos import RealtimeEvent
from dotenv import load_dotenv
from typing import TypedDict, Dict, Set, Callable, Optional, Any, Tuple
from types import NoneType

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

load_dotenv(override=True)

DEBUG = os.getenv("DEBUG", "0") == "1"

app_path = os.getcwd()
python_executable = os.path.join(app_path, "python", "python.exe")

program_data = os.getenv("PROGRAMDATA")
logs_base = os.path.join(program_data, "ControlHub")
logs_path = os.path.join(logs_base, "logs")

os.makedirs(logs_path, exist_ok=True)

logger = logging.getLogger("control_hub")

logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

proc_handler = logging.FileHandler(
    os.path.join(logs_path, "process.log"), encoding="utf-8"
)
proc_handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
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

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pocketbase").setLevel(logging.WARNING)


def handle_uncaught_exception(exc_type, exc_value, exc_tb):
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


sys.excepthook = handle_uncaught_exception

asyncio.get_event_loop().set_exception_handler(
    lambda loop, context: logger.error(
        "Asyncio exception", exc_info=context.get("exception")
    )
)


class ComputerRecord(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    ip: str
    mac: str
    name: str
    data: dict | NoneType
    region: str
    status: str
    token: str
    updated: str
    created: str


class ExecutionRecord(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    duration: float
    status: str
    executable: str
    logs: str
    computer: str
    script: str
    user: str
    invisible: bool
    created: str
    updated: str


def replace_last_spaces(string: str):
    if string.endswith("\n\n"):
        string = string[:-2]
    elif string.endswith("\n"):
        string = string[:-1]

    return string


class NetworkUtils:
    @staticmethod
    async def get_local_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            logger.debug(f"Local IP: {ip}")
            return ip
        finally:
            s.close()

    @staticmethod
    async def get_mac_address() -> Optional[str]:
        node = uuid.getnode()
        if (node >> 40) & 1:
            logger.debug("MAC: None (random)")
            return None
        mac = ":".join(("%012x" % node)[i : i + 2] for i in range(0, 12, 2)).upper()
        logger.debug(f"MAC: {mac}")
        return mac


class CodeExecutor:
    @staticmethod
    async def execute_code(
        code: str, execution_id: str, additional_env: dict = {}
    ) -> Tuple[str, dict, bool]:
        logger.debug(f"Executing code for id {execution_id}: {code}")
        return await CodeExecutor._run(code, execution_id, additional_env)

    @staticmethod
    async def run_command(
        command: list[str], cwd: str = None, additional_env: dict = {}
    ) -> dict:
        logger.debug(f"Running command: {command} cwd: {cwd}")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
                cwd=cwd,
                env={
                    **os.environ,
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                    **additional_env,
                },
            )

            stdout_data, stderr_data = await process.communicate()
            output = (
                stdout_data.decode("utf-8", errors="replace")
                + "\n"
                + stderr_data.decode("utf-8", errors="replace")
            )

            logger.debug(f"Command output: {output} returncode: {process.returncode}")

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
            logger.debug(f"Run command exception: {tb}")
            return {
                "success": False,
                "code": -1,
                "stdout": "",
                "traceback": "EXECUTION ERROR\n\n" + tb,
            }

    @staticmethod
    async def _run(
        code: str,
        execution_id: str,
        additional_env: dict = {},
    ) -> Tuple[str, dict, bool]:
        temp_dir = tempfile.gettempdir()
        exec_dir = os.path.join(temp_dir, f"exec_{execution_id}")

        temp_filename = os.path.join(exec_dir, "script.py")

        logger.info(f"Executing in temp directory: {exec_dir}")
        os.makedirs(exec_dir, exist_ok=True)

        with open(temp_filename, "w", encoding="utf-8") as file:
            file.write(code)

        result = await CodeExecutor.run_command(
            [python_executable, temp_filename], exec_dir, additional_env
        )

        if result["success"]:
            logger.info(f"[{execution_id}] Success:\n{result['stdout']}")
        else:
            logger.error(f"[{execution_id}] Failure:\n{result['traceback']}")

        try:
            shutil.rmtree(exec_dir)
        except Exception as err:
            logger.error(f"Temp deletion error: {err}", exc_info=err)

        return (
            result["stdout"] if result["success"] else result["traceback"],
            result["success"],
        )


class DatabaseClient:
    def __init__(self, server_url: str, token: str):
        self.pb = PocketBase(server_url)
        timeout = Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        self.pb._inners.client = AsyncClient(base_url=server_url, timeout=timeout)
        self.token = token
        self.params = {"token": token}
        self.options = {"params": copy.deepcopy(self.params)}

    async def get_computer(self) -> ComputerRecord:
        data = await self.pb.collection("computers").get_first(
            copy.deepcopy(self.options)
        )
        logger.debug(f"Computer data: {data}")
        return ComputerRecord(**data)

    async def update_computer(
        self, computer_id: str, data: Dict[str, Any]
    ) -> ComputerRecord:
        updated = await self.pb.collection("computers").update(
            computer_id, data, copy.deepcopy(self.options)
        )
        logger.debug(f"Updated computer data: {updated}")
        return ComputerRecord(**updated)

    async def update_execution(
        self, execution_id: str, data: Dict[str, Any]
    ) -> ExecutionRecord:
        updated = await self.pb.collection("executions").update(
            execution_id, data, copy.deepcopy(self.options)
        )
        logger.debug(f"Updated execution data: {updated}")
        return ExecutionRecord(**updated)

    async def create_invisible_execution(
        self, computer: ComputerRecord
    ) -> ExecutionRecord:
        return ExecutionRecord(
            **await self.pb.collection("executions").create(
                {
                    "computer": computer["id"],
                    "invisible": True,
                    "executable": "pass",
                    "logs": "",
                    "status": 0,
                },
                copy.deepcopy(self.options),
            )
        )

    async def get_invisible_execution(
        self, computer: ComputerRecord
    ) -> Optional[ExecutionRecord]:
        try:
            invisible_execution = await self.pb.collection("executions").get_first(
                {"filter": "invisible=true", "params": copy.deepcopy(self.params)}
            )
            return ExecutionRecord(**invisible_execution)
        except Exception as err:
            logger.error("Invisible execution not found, creating one", exc_info=err)
            return await self.create_invisible_execution(computer)

    async def switch_invisible_execution(self, execution: ExecutionRecord):
        execution["status"] = str((int(execution["status"]) + 1) % 4)

        logger.info(f"Switching invisible execution to {execution['status']}")
        await self.pb.collection("executions").update(
            execution["id"],
            {"status": execution["status"]},
            copy.deepcopy(self.options),
        )

    async def check_computer_status(self, computer: ComputerRecord) -> ComputerRecord:
        actual_computer = await self.pb.collection("computers").get_one(
            computer["id"], copy.deepcopy(self.options)
        )

        if actual_computer["status"] == "0":
            actual_computer = await self.pb.collection("computers").update(
                actual_computer["id"], {"status": "2"}, copy.deepcopy(self.options)
            )

        return actual_computer

    async def subscribe_to_executions(
        self, computer_id: str, callback: Callable[[RealtimeEvent], Any]
    ):
        filter_query = f'computer.id="{computer_id}"'

        params = {
            "headers": {},
            "params": {"token": self.token, "filter": filter_query},
        }

        unsubscribe = await self.pb.collection("executions").subscribe_all(
            callback, copy.deepcopy(params)
        )

        logger.debug(f"Subscribed to executions for computer {computer_id}")

        return unsubscribe


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
        self.computer: Optional[ComputerRecord] = None
        self.invisible_execution: Optional[ExecutionRecord] = None

    async def initialize(self) -> None:
        self.computer = await self.db_client.get_computer()
        computer_data = {
            "ip": await NetworkUtils.get_local_ip(),
            "mac": await NetworkUtils.get_mac_address(),
            "status": "2",
        }

        logger.debug(f"Computer data: {self.computer}")

        self.computer = await self.db_client.update_computer(
            self.computer["id"], computer_data
        )

        logger.debug(f"Updated computer data: {self.computer}")

        self.invisible_execution = await self.db_client.get_invisible_execution(
            self.computer
        )

        logger.info(
            f"Initialized for: {self.computer['name']} ({self.computer['ip']}) with invisible_execution: {self.invisible_execution['id']}"
        )

    async def update_status(self, status: int) -> None:
        try:
            self.computer = await self.db_client.update_computer(
                self.computer["id"], {"status": status}
            )
            logger.info(f"Status updated: {status}")

        except Exception as err:
            logger.error(f"Status update failed: {err}", exc_info=err)

    async def handle_event(self, event: RealtimeEvent) -> None:
        logger.debug(f"Received event: {event}")
        if (
            event["action"] != "create"
            or event["record"].get("invisible")
            or event["record"]["computer"] != self.computer.get("id")
        ):
            return

        execution_record = event["record"]
        execution_id = execution_record.get("id")

        logger.debug(f"Processing execution: {execution_id}")

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
            execution_record.get("executable"),
            execution_id,
            {
                "CONTROLHUB": app_path,
                "EXECUTION_ID": execution_id,
                "COMPUTER_JSON": json.dumps(self.computer, ensure_ascii=True),
                "EXECUTION_START_TIME": str(start_time),
            },
        )

        duration = time.time() - start_time
        await self.db_client.update_execution(
            execution_id,
            {
                "logs": replace_last_spaces(logs),
                "completed": True,
                "status": "2" if succeeded else "3",
                "duration": duration,
            },
        )

        last = self.tracker.remove_active(execution_id)

        if last:
            await self.update_status(2)

        logger.debug(f"Task {execution_id} completed: {succeeded}")

        logger.info(
            f"Task completed: {execution_id} (Success: {succeeded}, Duration: {duration:.2f}s, Remaining: {self.tracker.active_count()})"
        )

    async def keep_alive(self) -> None:
        while True:
            logger.debug("Keeping alive...")
            await asyncio.sleep(60 * 4)  # 4 min.
            self.computer = await self.db_client.check_computer_status(self.computer)
            await self.db_client.switch_invisible_execution(self.invisible_execution)

    async def run(self) -> None:
        try:
            while True:
                try:
                    logger.info("Connecting...")
                    await self.initialize()

                    unsubscribe = await self.db_client.subscribe_to_executions(
                        self.computer["id"], self.handle_event
                    )

                    logger.info("Subscribed, waiting for tasks...")
                    await self.keep_alive()
                except (httpx.ConnectError, HTTPCoreConnectError) as err:
                    logger.warning(f"Realtime connection lost, retry in 20s: {err}")
                    await asyncio.sleep(20)
                except Exception as err:
                    logger.error(f"Connection error: {err}", exc_info=err)
                    await asyncio.sleep(20)
        finally:
            if self.computer:
                await self.update_status(0)
            if "unsubscribe" in locals():
                await unsubscribe()
                logger.info("Unsubscribed")


def upgrade_requirements():
    try:
        result = subprocess.run(
            [
                python_executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "-r",
                "requirements.txt",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=app_path,
        )
        logger.info(f"Pip upgrade output:\n{result.stdout}")
    except Exception as e:
        logger.error(f"Pip upgrade failed: {e}", exc_info=e)


async def main() -> None:
    SERVER_URL = os.getenv("CONTROLHUB_SERVER_URL", "https://pb.control-hub.org")
    TOKEN = os.getenv("TOKEN")

    if not TOKEN:
        logger.error("TOKEN not set")
        return

    agent = AgentService(SERVER_URL, TOKEN)
    asyncio.create_task(asyncio.to_thread(upgrade_requirements))

    while True:
        try:
            await agent.run()
        except Exception as err:
            logger.error(f"Agent error: {err}", exc_info=err)
            await asyncio.sleep(20)


if __name__ == "__main__":
    logger.info("Starting agent...")
    asyncio.run(main())
