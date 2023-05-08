import os
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from threading import Thread
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, WebSocketException
from subtitle.process import SekaiJsonVideoProcess, ProcessConfig
import cv2


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


origins = [
    "http://localhost",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/new")
async def create_task(
    config: ProcessConfig,
    # payload: dict = Body(..., embed=True),
    runAfterCreate: bool = False
):
    # config = ProcessConfig(payload)
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
            raise HTTPException(
                400, {"success": False, "error": f"Task {task_id} is Already Running"})
        else:
            await app.run_task(task_id=task_id)
            return {'success': True, "data": task_id}
    else:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/stop/{task_id}')
async def stop_task(task_id: str):
    if task := app.get_task(task_id):
        if task.processing:
            task.set_stop()
            await asyncio.sleep(1)
            if not task.processing:
                return {"success": True, "data": task_id}
            else:
                raise HTTPException(
                    400, {"success": False, "error": f"Task {task_id} Failed to Stop"})
        else:
            raise HTTPException(
                400, {"success": False, "error": f"Task {task_id} is Already Stopped"})

    else:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


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
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/delete/{task_id}')
async def delete_task(task_id):
    try:
        app.delete_task(task_id)
    except ValueError:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})
    else:
        return {"success": True, 'data': task_id}


@app.get("/taskList")
async def task_list(running: bool = False):
    data = []
    for task_id in app.TaskList.keys():
        if (running and app.get_task(task_id).processing) or (not running):
            data.append(task_id)
    return {'success': True, "data": data}


# @app.get("/taskStatus")
async def task_status():
    data = {
        task_id: 'processing' if app.get_task(task_id).processing else "idle"
        for task_id in app.TaskList.keys()
    }
    for task_id in data:
        if data[task_id] == "idle":
            app.TaskThreads[task_id] = None
            del app.TaskThreads[task_id]
    return {'success': True, "data": data}


@app.get("/taskConfig/{task_id}")
async def task_config(task_id):
    if task := app.get_task(task_id):
        return {'success': True, "data": task.config.dict()}
    else:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.get("/videoInfo")
async def task_config(video_file: str):
    print(video_file)
    if os.path.exists(video_file):
        vc = cv2.VideoCapture(video_file)
        return {"success": True, "data": {
            "frameHeight": vc.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "frameWidth": vc.get(cv2.CAP_PROP_FRAME_WIDTH),
            "frameCount": vc.get(cv2.CAP_PROP_FRAME_COUNT),
            "videoFps": vc.get(cv2.CAP_PROP_FPS)
        }}
    else:
        raise HTTPException(
            400, {"success": False, "error": f"File {video_file} Does Not Exists"})


@app.get("/autoSelect")
async def auto_select(video_file: str, file_type: str):
    if os.path.exists(video_file):
        file_dir = os.path.dirname(video_file)
        file_base_name = os.path.basename(video_file)
        file_name, file_ext = os.path.splitext(file_base_name)
        dir_list = [file for file in os.listdir(file_dir)
                    if file.startswith(file_name) and (file_ext in ['.json', '.asset', '.yml', '.txt'])]
        json_file = sorted([file for file in dir_list if os.path.splitext(
            file_ext)[1].lower() in ['.asset', '.json']], reverse=True)
        translate_file = sorted([file for file in dir_list if os.path.splitext(
            file_ext)[1].lower() in ['.yml', '.txt']], reverse=True)
        return {
            "success": True, "data": {
                "json": json_file[0] if json_file else None,
                "translate": translate_file[0] if translate_file else None
            }}
    else:
        raise HTTPException(
            400, {"success": False, "error": f"File {video_file} Does Not Exists"})


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
                                {'type': "log", 'data': task.message_queue[(
                                    recv.get('request') or 0):]},
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
