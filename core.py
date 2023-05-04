import asyncio
import json
from threading import Thread
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, WebSocketException
from subtitle.process import SekaiJsonVideoProcess, ProcessConfig


class App(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TaskList: dict[str, SekaiJsonVideoProcess] = {}
        self.TaskThreads: dict[str, Thread] = {}
        self.TaskLog: dict[str, list] = {}

    def create_task(self, config: ProcessConfig):
        try:
            new_task = SekaiJsonVideoProcess(config)
            self.TaskList[new_task.id] = new_task
        except Exception as e:
            raise e
        else:
            return new_task.id

    def get_task(self, task_id):
        return self.TaskList[task_id] if task_id in self.TaskList.keys() else None

    async def run_task(self, task_id):
        task = self.get_task(task_id)
        if not task:
            raise KeyError
        else:
            thread_run = Thread(target=task.run)
            self.TaskThreads[task_id] = thread_run
            thread_run.daemon = True
            thread_run.start()

    def delete_task(self, task_id):
        task = self.get_task(task_id)
        if not task:
            raise KeyError
        else:
            if task.processing:
                task.set_stop()
            del self.TaskList[task_id]
            return True


app = App()


@app.post("/new")
async def create_task(config: ProcessConfig, runAfterCreate: bool = False):
    try:
        task_id = app.create_task(config)
    except Exception as e:
        print(e)
        raise HTTPException(400, {"success": False, "error": e.__repr__()})
    else:
        if runAfterCreate:
            await app.run_task(task_id=task_id)
        return {'success': True, "data": task_id}


@app.post('/start/{task_id}')
async def start_task(task_id: str):
    if task := app.get_task(task_id):
        if task.processing:
            raise HTTPException(400, {"success": False, "error": f"Task {task_id} is Already Running"})
        else:
            await app.run_task(task_id=task_id)
            return {'success': True, "data": task_id}
    else:
        raise HTTPException(400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/stop/{task_id}')
async def stop_task(task_id: str):
    if task := app.get_task(task_id):
        if task.processing:
            task.set_stop()
            await asyncio.sleep(1)
            if not task.processing:
                return {"success": True, "data": task_id}
            else:
                raise HTTPException(400, {"success": False, "error": f"Task {task_id} Failed to Stop"})
        else:
            raise HTTPException(400, {"success": False, "error": f"Task {task_id} is Already Stopped"})

    else:
        raise HTTPException(400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post("/restart/{task_id}")
async def restart_task(task_id):
    if task := app.get_task(task_id):
        if task.processing:
            task.set_stop()
            await asyncio.sleep(1)
            if not task.processing:
                await app.run_task(task_id=task_id)
                return {'success': True, "data": task_id}


@app.post("/reload/{task_id}")
async def reload_task(task_id, runAfterCreate: bool = False):
    if task := app.get_task(task_id):
        config = task.config.copy()
        app.delete_task(task_id)
        await create_task(config, runAfterCreate)
    else:
        raise HTTPException(400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/delete/{task_id}')
async def delete_task(task_id):
    try:
        app.delete_task(task_id)
    except ValueError:
        raise HTTPException(400, {"success": False, "error": f"Task {task_id} Does Not Exists"})
    else:
        return {"success": True, 'data': task_id}


@app.get("/taskList")
async def task_list(running: bool = False):
    data = []
    for task_id in app.TaskList.keys():
        if (running and app.get_task(task_id).processing) or (not running):
            data.append(task_id)
    return {'success': True, "data": data}


@app.get("/taskStatus")
async def task_status():
    data = {
        task_id: 'processing' if app.get_task(task_id).processing else "idle"
        for task_id in app.TaskList.keys()
    }
    return {'success': True, "data": data}


@app.websocket('/status/{task_id}')
async def websocket_status(websocket: WebSocket, task_id):
    await websocket.accept()
    try_time = 0
    while try_time < 10:
        task = app.get_task(task_id)
        if task:
            try:
                while True:
                    recv = await websocket.receive_json()
                    if task.message_queue:
                        await websocket.send_text(
                            json.dumps(
                                {'type': "log", 'data': task.message_queue[(recv.get('request') or 0):]},
                                ensure_ascii=False
                            ))
                    else:
                        await websocket.send_text(json.dumps({'type': "alive"}, ensure_ascii=False))
            except WebSocketDisconnect:
                return
        else:
            try_time += 1
            await asyncio.sleep(1)
    if try_time == 10:
        raise WebSocketException(1003, "Task Doesn't Exist")


@app.websocket('/tasks')
async def websocket_tasks(websocket: WebSocket):
    await websocket.accept()
    try:
        data = None
        while True:
            recv = await websocket.receive_json()
            if recv.get("type") == "alive":
                new = (await task_status())['data']
                if data == new:
                    await websocket.send_text(json.dumps({'type': "alive"}, ensure_ascii=False))
                else:
                    await websocket.send_text(
                        json.dumps({'type': "tasks", 'data': new}, ensure_ascii=False))
                    data = new
            else:
                return
    except WebSocketDisconnect:
        return


@app.on_event("shutdown")
async def shutdown():
    for task_id in list(app.TaskList.keys()):
        app.delete_task(task_id)


@app.get("/shutdown")
async def close():
    await shutdown()
    exit(0)


if __name__ == '__main__':
    uvicorn.run(app, host="localhost", port=50000)  # , reload=True)
