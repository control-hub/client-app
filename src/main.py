import asyncio
import subprocess
import socket
import uuid
import tempfile
import os
import traceback
# import locale

from typing import TypedDict, Dict, Set, Callable, Optional, Any

from pocketbase import PocketBase
from pocketbase.models.dtos import RealtimeEvent

from dotenv import load_dotenv

load_dotenv(override=True)

class Computer(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    ip: str
    mac: str
    name: str
    region: str
    status: str
    token: str
    updated: str
    created: str


class Execution(TypedDict):
    collectionId: str
    collectionName: str
    id: str
    completed: bool
    executable: str
    logs: str
    computer: str
    script: str
    user: str
    created: str
    updated: str


class NetworkUtils:
    @staticmethod
    def get_local_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        finally:
            s.close()

    @staticmethod
    def get_mac() -> Optional[str]:
        node = uuid.getnode()
        if (node >> 40) & 1:
            return None
        return ':'.join(('%012x' % node)[i:i+2] for i in range(0, 12, 2)).upper()


class CodeExecutor:
    @staticmethod
    async def execute_code(code: str, execution_id: str) -> str:
        return await CodeExecutor._run(code, execution_id)
        
    @staticmethod
    async def run_command(command: list[str]) -> dict:
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW
            )

            stdout_data, stderr_data = await process.communicate()

            output = stdout_data.decode("cp866", errors="replace") + "\n" + stderr_data.decode(
                "cp866", errors="replace"
            )

            return {
                "success": process.returncode == 0,
                "stdout": output,
                "code": process.returncode,
                "traceback": None
                if process.returncode == 0
                else f"Command exited with code {process.returncode}\n\n{output}",
            }

        except Exception:
            return {
                "success": False,
                "code": -1,
                "stdout": "",
                "traceback": "CONTROL HUB EXECUTION ERROR\n\n" + traceback.format_exc(),
            }

    @staticmethod
    async def _run(code: str, execution_id: str) -> str:
        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f"exec_{execution_id}.py")
        
        print(f"🔄 Executing code in temporary file: {temp_filename}")
        
        with open(temp_filename, 'w', encoding='utf-8') as temp_file:
            temp_file.write(code)
        
        # TODO: Replace print with a proper logging mechanismHello from here!
        result = await CodeExecutor.run_command(
            command=["python", temp_filename]
        )
        
        if os.path.exists(temp_filename):
            try:
                os.unlink(temp_filename)
            except Exception as e:
                print(f"Error deleting temporary file: {e}")

        return result["stdout"] if result["success"] else result["traceback"]

class DatabaseClient:
    def __init__(self, server_url: str, token: str):
        self.pb = PocketBase(server_url)
        self.token = token
        self.params = {"token": token}

    async def get_computer(self) -> Computer:
        return Computer(**(await self.pb.collection("computers").get_first({"params": self.params})))

    async def update_computer(self, computer_id: str, data: Dict[str, Any]) -> Computer:
        return Computer(**(await self.pb.collection("computers").update(
            computer_id, 
            data, 
            {"params": self.params}
        )))

    async def update_execution(self, execution_id: str, data: Dict[str, Any]) -> Execution:
        return await self.pb.collection("executions").update(
            execution_id,
            data,
            {"params": self.params}
        )

    async def subscribe_to_executions(
        self, 
        computer_id: str, 
        callback: Callable[[RealtimeEvent], Any]
    ):
        filter_query = f"computer.id=\"{computer_id}\""
        subscription_params = {
            "headers": {},
            "params": {
                "token": self.token, 
                "filter": filter_query
            }
        }
        
        return await self.pb.collection("executions").subscribe_all(
            callback, 
            subscription_params
        )


class ExecutionTracker:
    def __init__(self):
        self.executed_tasks: Set[str] = set()
        self.active_executions: Set[str] = set()
    
    def is_executed(self, execution_id: str) -> bool:
        return execution_id in self.executed_tasks
    
    def mark_executed(self, execution_id: str) -> None:
        self.executed_tasks.add(execution_id)
    
    def add_active(self, execution_id: str) -> bool:
        was_empty = len(self.active_executions) == 0
        self.active_executions.add(execution_id)
        return was_empty
    
    def remove_active(self, execution_id: str) -> bool:
        if execution_id in self.active_executions:
            self.active_executions.remove(execution_id)
        return len(self.active_executions) == 0
    
    def count_active(self) -> int:
        return len(self.active_executions)


class AgentService:
    def __init__(self, server_url: str, token: str):
        self.db_client = DatabaseClient(server_url, token)
        self.executor = CodeExecutor()
        self.tracker = ExecutionTracker()
        self.computer: Optional[Computer] = None
    
    async def initialize(self) -> None:
        self.computer = await self.db_client.get_computer()
        self_real_computer = {
            "ip": NetworkUtils.get_local_ip(),
            "mac": NetworkUtils.get_mac(),
            "status": 2,  # Idle
        }
        self.computer = await self.db_client.update_computer(
            self.computer["id"], 
            self_real_computer
        )
        
        print(f"📟 Agent initialized for computer: {self.computer['name']} ({self.computer['ip']})")
    
    async def update_computer_status(self, status: int) -> None:
        try:
            self.computer = await self.db_client.update_computer(
                self.computer["id"], 
                {"status": status}
            )
            print(f"💻 Computer status updated to: {status}")
        except Exception as e:
            print(f"❌ Failed to update computer status: {e}")
    
    async def handle_execution(self, event: RealtimeEvent) -> None:
        created = event["action"] == "create"
        if not created:
            return
        
        execution = event["record"]
        execution_id = execution.get("id")
        
        if self.tracker.is_executed(execution_id):
            return
        
        self.tracker.mark_executed(execution_id)
        
        if execution.get("completed"):
            return
        
        asyncio.create_task(self.process_execution(execution, execution_id))

    async def process_execution(self, execution: Dict[str, Any], execution_id: str) -> None:
        is_first_task = self.tracker.add_active(execution_id)
        
        if is_first_task:
            await self.update_computer_status(1)  # Running
        
        print(f"🚀 Executing task: {execution_id} (Active tasks: {self.tracker.count_active()})")
        
        await self.db_client.update_execution(
            execution_id,
            {"logs": "🔄 Execution started...\n"}
        )
        
        code = execution.get("executable")
        logs = await self.executor.execute_code(code, execution_id)
        
        await self.db_client.update_execution(
            execution_id,
            {
                "logs": logs,
                "completed": True
            }
        )
        
        is_last_task = self.tracker.remove_active(execution_id)
        
        if is_last_task:
            await self.update_computer_status(2)  # Idle
        
        print(f"✅ Task completed: {execution_id} (Remaining tasks: {self.tracker.count_active()})")
    
    async def run(self) -> None:
        try:
            print("🔌 Connecting to server and subscribing to executions...")
            
            unsubscribe = await self.db_client.subscribe_to_executions(
                self.computer["id"], 
                self.handle_execution
            )
            
            print("✅ Subscription active. Waiting for executions...")
            
            while True:
                await asyncio.sleep(60 * 60)  # Keep the service running
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        finally:
            if self.computer:
                await self.db_client.update_computer(
                    self.computer["id"], 
                    {"status": 0}  # Offline
                )
            
            if 'unsubscribe' in locals():
                try:
                    await unsubscribe()
                    print("🔌 Unsubscribed from executions")
                except Exception as e:
                    print(f"❌ Error unsubscribing: {e}")


async def main() -> None:
    SERVER_URL = "https://pb.control-hub.org"
    TOKEN = os.getenv("TOKEN")
    
    if not TOKEN:
        print("❌ ERROR: TOKEN environment variable is not set")
        return
    
    agent = AgentService(SERVER_URL, TOKEN)
    await agent.initialize()
    await agent.run()


if __name__ == "__main__":
    print("🚀 Starting execution agent...")
    asyncio.run(main())
