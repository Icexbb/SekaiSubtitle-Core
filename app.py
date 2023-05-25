import asyncio
import json
import os
import signal
from threading import Thread

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, WebSocketException
from fastapi.middleware.cors import CORSMiddleware

from lib.log import init_logging
from lib.process import SekaiJsonVideoProcess, ProcessConfig


class App(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SubtitleTaskList: dict[str, SekaiJsonVideoProcess] = {}
        self.SubtitleTaskThreads: dict[str, Thread] = {}
        # self.DownloadTaskList: dict[str, DownloadTask] = {}

    def create_subtitle_task(self, config: ProcessConfig):
        try:
            new_task = SekaiJsonVideoProcess(config)
            self.SubtitleTaskList[new_task.id] = new_task
        except Exception as e:
            raise e
        else:
            return new_task.id

    def get_subtitle_task(self, task_id):
        if task_id in self.SubtitleTaskList.keys():
            return self.SubtitleTaskList[task_id]
        else:
            raise KeyError

    def run_subtitle_task(self, task_id):
        task = self.get_subtitle_task(task_id)
        thread_run = Thread(target=task.run)
        self.SubtitleTaskThreads[task_id] = thread_run
        thread_run.daemon = True
        thread_run.start()

    def delete_subtitle_task(self, task_id):
        try:
            task = self.get_subtitle_task(task_id)
        except KeyError as e:
            raise e
        else:
            if task.processing:
                task.set_stop()
            del self.SubtitleTaskList[task_id]
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


@app.post("/subtitle/new")
async def create_task(
        config: ProcessConfig,
        runAfterCreate: bool = False
):
    try:
        task_id = app.create_subtitle_task(config)
    except Exception as e:
        print(e)
        raise HTTPException(400, {"success": False, "error": e.__repr__()})
    else:
        if runAfterCreate:
            app.run_subtitle_task(task_id=task_id)
        return {'success': True, "data": task_id}


@app.post('/subtitle/start/{task_id}')
async def start_task(task_id: str):
    try:
        task = app.get_subtitle_task(task_id)
        if task.processing:
            raise HTTPException(
                400, {"success": False, "error": f"Task {task_id} is Already Running"})
        else:
            app.run_subtitle_task(task_id=task_id)
            return {'success': True, "data": task_id}
    except KeyError:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/subtitle/stop/{task_id}')
async def stop_task(task_id: str):
    try:
        task = app.get_subtitle_task(task_id)
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
    except KeyError:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post("/subtitle/reload/{task_id}")
async def reload_task(task_id, runAfterCreate: bool = False):
    try:
        task = app.get_subtitle_task(task_id)
        config = task.config.copy()
        app.delete_subtitle_task(task_id)
        return await create_task(config, runAfterCreate)
    except KeyError:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.post('/subtitle/delete/{task_id}')
async def delete_task(task_id):
    try:
        app.delete_subtitle_task(task_id)
    except ValueError:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})
    else:
        return {"success": True, 'data': task_id}


@app.get("/subtitle/taskList")
async def task_list(running: bool = False):
    data = []
    for task_id in app.SubtitleTaskList.keys():
        if (running and app.get_subtitle_task(task_id).processing) or (not running):
            data.append(task_id)
    return {'success': True, "data": data}


async def subtitle_task_status():
    data = {
        task_id: 'processing' if app.get_subtitle_task(task_id).processing else "idle"
        for task_id in app.SubtitleTaskList.keys()
    }
    return {'success': True, "data": data}


@app.get("/subtitle/taskConfig/{task_id}")
async def subtitle_task_config(task_id):
    if task := app.get_subtitle_task(task_id):
        return {'success': True, "data": task.config.dict()}
    else:
        raise HTTPException(
            400, {"success": False, "error": f"Task {task_id} Does Not Exists"})


@app.get("/subtitle/videoInfo")
async def videoInfo(video_file: str):
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


@app.websocket('/subtitle/status/{task_id}')
async def ws_subtitle_status(websocket: WebSocket, task_id):
    await websocket.accept()
    try_time = 0
    while try_time < 10:
        task = app.get_subtitle_task(task_id)
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


@app.websocket('/subtitle/tasks')
async def websocket_tasks(websocket: WebSocket):
    await websocket.accept()
    try:
        data = None
        while True:
            recv = await websocket.receive_json()
            if recv.get("type") == "alive":
                new = (await subtitle_task_status())['data']
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


@app.websocket('/alive')
async def ws_alive(websocket: WebSocket):
    await websocket.accept()
    try:
        timeout_count = 0
        while True:
            try:
                recv = await asyncio.wait_for(websocket.receive_json(), 0.5)
                timeout_count = 0
            except asyncio.TimeoutError:
                timeout_count += 1
                await websocket.send_text(json.dumps({'type': "alive"}, ensure_ascii=False))
                if timeout_count >= 30:
                    break
            except WebSocketDisconnect:
                break
            else:
                if recv.get("type") == "alive":
                    await websocket.send_text(json.dumps({'type': "alive"}, ensure_ascii=False))
                else:
                    break
    finally:
        os.kill(os.getpid(), signal.SIGINT)


@app.on_event("shutdown")
async def shutdown():
    for task_id in list(app.SubtitleTaskList.keys()):
        app.delete_subtitle_task(task_id)


@app.on_event("startup")
async def startup_event():
    init_logging()
