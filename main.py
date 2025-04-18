import asyncio
import socket
import uuid
import sys
import io
import tempfile
import os
import subprocess
from datetime import datetime
from typing import TypedDict
from concurrent.futures import ThreadPoolExecutor

from pocketbase import PocketBase
from pocketbase.models.dtos import RealtimeEvent

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

executed_tasks = set()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()

def get_mac():
    node = uuid.getnode()
    if (node >> 40) & 1:
        return None
    return ':'.join(('%012x' % node)[i:i+2] for i in range(0, 12, 2)).upper()

def run_code_in_process(code, execution_id, timeout=30):
    """
    Запускает Python код в отдельном процессе.
    
    Args:
        code: строка с Python кодом
        execution_id: идентификатор выполнения (для имени файла)
        timeout: таймаут в секундах (по умолчанию 30 сек)
    
    Returns:
        Строка с объединенным выводом stdout и stderr
    """
    # Создаем временный файл с именем, основанным на ID выполнения
    temp_dir = tempfile.gettempdir()
    temp_filename = os.path.join(temp_dir, f"exec_{execution_id}.py")
    
    try:
        # Записываем код в файл
        with open(temp_filename, 'w', encoding='utf-8') as temp_file:
            temp_file.write(code)
        
        # Запускаем код в отдельном процессе
        process = subprocess.Popen(
            [sys.executable, temp_filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Получаем результаты с таймаутом
        stdout, stderr = process.communicate(timeout=timeout)
        
        stdout_str = stdout.decode('utf-8')
        stderr_str = stderr.decode('utf-8')
        
        # Формируем полный лог
        output = stdout_str
        if stderr_str:
            if output:
                output += "\n\n"
            output += f"Errors:\n{stderr_str}"
        
        if process.returncode != 0:
            output += f"\n\nProcess exited with code {process.returncode}"
            
        return output
    
    except subprocess.TimeoutExpired:
        # В случае таймаута принудительно завершаем процесс
        process.kill()
        return f"Execution timed out after {timeout} seconds."
    
    except Exception as e:
        return f"Error executing code: {str(e)}"
    
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            try:
                os.unlink(temp_filename)
            except:
                pass

class AgentService:
    def __init__(self, server_url: str, token: str):
        self.pb = PocketBase(server_url)
        self.token = token
        self.params = {"token": token}
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.computer = None
    
    async def initialize(self):
        self.computer = Computer(**(await self.pb.collection("computers").get_first({"params": self.params})))
        self_real_computer = {
            "ip": get_local_ip(),
            "mac": get_mac(),
            "status": 2,  # Online status
        }
        await self.pb.collection("computers").update(
            self.computer["id"], 
            self_real_computer, 
            {"params": self.params}
        )
        print(f"📟 Agent initialized for computer: {self.computer['name']} ({self.computer['ip']})")
    
    async def handle_execution(self, event: RealtimeEvent):
        execution = event["record"]
        execution_id = execution.get("id")
        
        if execution_id in executed_tasks:
            return
        
        executed_tasks.add(execution_id)
        
        if execution.get("completed"):
            return
        
        print(f"🚀 Executing task: {execution_id}")
        
        # Update execution to mark it as in progress
        await self.pb.collection("executions").update(
            execution_id,
            {"logs": "🔄 Execution started...\n"},
            {"params": self.params}
        )
        
        # Execute the code in a separate thread to avoid blocking the event loop
        code = execution.get("executable")
        
        # Run the execution in a thread pool as a separate process
        logs = await asyncio.get_event_loop().run_in_executor(
            self.executor, 
            run_code_in_process, 
            code,
            execution_id
        )
        
        # Format the final log
        final_logs = f"🔄 Execution started...\n\n{logs}"
        
        # Update the execution with results
        await self.pb.collection("executions").update(
            execution_id,
            {
                "logs": final_logs,
                "completed": True
            },
            {"params": self.params}
        )
        
        print(f"✅ Task completed: {execution_id}")
    
    async def run(self):
        try:
            print(f"🔌 Connecting to server and subscribing to executions...")
            
            # Subscribe to executions for this computer
            filter_query = f"computer.id=\"{self.computer['id']}\""
            subscription_params = {
                "headers": {},
                "params": {
                    "token": self.token, 
                    "filter": filter_query
                }
            }
            
            unsubscribe = await self.pb.collection("executions").subscribe_all(
                self.handle_execution, 
                subscription_params
            )
            
            print(f"✅ Subscription active. Waiting for executions...")
            
            # Keep the service running
            while True:
                await asyncio.sleep(60 * 60)  # Check every hour
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        finally:
            # Update computer status to offline
            if self.computer:
                await self.pb.collection("computers").update(
                    self.computer["id"], 
                    {"status": 0},  # Offline status
                    {"params": self.params}
                )
            
            # Unsubscribe if subscription is active
            if 'unsubscribe' in locals():
                try:
                    await unsubscribe()
                    print("🔌 Unsubscribed from executions")
                except Exception as e:
                    print(f"❌ Error unsubscribing: {e}")

async def main():
    SERVER_URL = "https://pb.control-hub.org"
    TOKEN = "rDbSpdxCYE1p"
    
    agent = AgentService(SERVER_URL, TOKEN)
    await agent.initialize()
    await agent.run()

if __name__ == "__main__":
    print("🚀 Starting execution agent...")
    asyncio.run(main())
