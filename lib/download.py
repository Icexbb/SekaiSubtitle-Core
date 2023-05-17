import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from lib import tools, constant


def update_source_ai():
    root = "https://api.pjsek.ai/database/master/"
    result = {
        "events.json": root + "events?$limit=1000",
        "cards.json": root + "cards?$limit=1000",
        "character2ds.json": root + "character2ds?$limit=1000",
        "unitStories.json": root + "unitStories?$limit=1000",
        "eventStories.json": root + "eventStories?$limit=1000",
        "cardEpisodes.json": root + "cardEpisodes?$limit=2000",
        "actionSets.json": root + "actionSets?$limit=3000",
        "specialStories.json": root + "specialStories?$limit=1000",
    }
    return result


def update_source_best():
    root = "https://sekai-world.github.io/sekai-master-db-diff/"
    result = {
        "events.json": root + "events.json",
        "cards.json": root + "cards.json",
        "character2ds.json": root + "character2ds.json",
        "unitStories.json": root + "unitStories.json",
        "eventStories.json": root + "eventStories.json",
        "cardEpisodes.json": root + "cardEpisodes.json",
        "actionSets.json": root + "actionSets.json",
        "specialStories.json": root + "specialStories.json",
    }
    return result


def download(url, path, proxy=None, timeout=None):
    try_time = 0
    while try_time <= 5:
        try:
            with httpx.Client(proxies={"http://": proxy, "https://": proxy} if proxy else None) as client:
                resp = client.request("GET", url, timeout=timeout if timeout else None)
                if resp.status_code == 200:
                    tools.save_json(path, resp.json())
                    return True
        except:
            try_time += 1
    return False


def download_list(source: Literal['best', 'ai'], proxy=None, timeout=None):
    source_list = update_source_ai() if source == "ai" else update_source_best()
    root = os.path.join(
        os.path.expanduser('~/Documents'), "SekaiSubtitle", "data", source, "tree")
    os.makedirs(root, exist_ok=True)
    success = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(download, source_list[file], os.path.join(root, file), proxy, timeout) for file in
                   source_list]
        for result in as_completed(futures):
            success += result.result()
            update_tree(root, source)
    return tools.read_json(os.path.join(root, "tree.json")), success == 8


def download_file(url, dir_name=None, proxy=None, timeout=None):
    parsed_url = urlparse(url)
    source = "best" if 'best' in parsed_url.hostname else "ai"
    filename = os.path.basename(parsed_url.path)
    if not dir_name:
        dir_name = os.path.join(
            os.path.expanduser('~/Documents'), "SekaiSubtitle", "data", source)
    path = os.path.join(dir_name, filename)
    return download(url, path, proxy, timeout), path


def update_tree(root, source):
    if os.path.exists(os.path.join(root, "character2ds.json")):
        character2ds = tools.read_json(os.path.join(root, "character2ds.json"))
    else:
        character2ds = {}
    if os.path.exists(os.path.join(root, "events.json")):
        events = tools.read_json(os.path.join(root, "events.json"))
    else:
        events = {}

    if os.path.exists(os.path.join(root, "cards.json")):
        cards = tools.read_json(os.path.join(root, "cards.json"))
    else:
        cards = {}

    if os.path.exists(os.path.join(root, "tree.json")):
        tree = tools.read_json(os.path.join(root, "tree.json"))
    else:
        tree = {}

    if os.path.exists(os.path.join(root, "cardEpisodes.json")) and cards:
        data = tools.read_json(os.path.join(root, "cardEpisodes.json"))
        tree['卡牌剧情'] = {}
        for ep in data:
            if "scenarioId" not in ep:
                continue
            card_id = ep['cardId']
            card = None
            for enu_card in cards:
                if enu_card['id'] == card_id:
                    card = enu_card
                    break
            if not card:
                continue
            chara = constant.chara_name[str(card['characterId'])]
            rarity = f"★{card['cardRarityType'][7:]}" if card['cardRarityType'][7:].isdigit() else "BD"
            prefix = card['prefix']
            section = "前篇" if ep['cardEpisodePartType'] == "first_part" else "后篇"
            if source == "ai":
                url = f"https://assets.pjsek.ai/file/pjsekai-assets/startapp/character/member/" \
                      f"{ep['assetbundleName']}/{ep['scenarioId']}.json"
            else:
                url = f"https://storage.sekai.best/sekai-assets/character/member/" \
                      f"{ep['assetbundleName']}_rip/{ep['scenarioId']}.asset"
            if chara in tree['卡牌剧情']:
                d = tree['卡牌剧情'][chara]
            else:
                d = {}
            d[f"{card_id} - {rarity} {prefix} {section}"] = url
            tree['卡牌剧情'][chara] = d

    if os.path.exists(os.path.join(root, "eventStories.json")) and events:
        data = tools.read_json(os.path.join(root, "eventStories.json"))
        tree['活动剧情'] = {}
        for item in data:
            try:
                ev_name = f"{item['eventId']:03d}:{events[item['eventId'] - 1]['name']}"
            except IndexError:
                ev_name = f"Event{item['eventId']:03d}"
            ev_ep = {}
            for ep in item["eventStoryEpisodes"]:
                if source == "best":
                    url = f"https://storage.sekai.best/sekai-assets/event_story/" \
                          f"{item['assetbundleName']}/scenario_rip/{ep['scenarioId']}.asset"
                else:
                    url = f"https://assets.pjsek.ai/file/pjsekai-assets/ondemand/event_story/" + \
                          f"{item['assetbundleName']}/scenario/{ep['scenarioId']}.json"
                ev_ep[f"{ep['episodeNo']}: {ep['title']}"] = url
            tree['活动剧情'][ev_name] = ev_ep

    if os.path.exists(os.path.join(root, "unitStories.json")):
        data = tools.read_json(os.path.join(root, "unitStories.json"))
        tree['主线剧情'] = {}
        for unit in data:
            for chapters in unit['chapters']:
                eps = {}
                for episodes in chapters["episodes"]:
                    key = f"{episodes['episodeNoLabel']}: {episodes['title']}"
                    if source == "ai":
                        url = "https://assets.pjsek.ai/file/pjsekai-assets/startapp/scenario/unitstory/" + \
                              f"{chapters['assetbundleName']}/{episodes['scenarioId']}.json"
                    else:
                        url = "https://storage.sekai.best/sekai-assets/scenario/unitstory/" \
                              f"{chapters['assetbundleName']}_rip/{episodes['scenarioId']}.asset"
                    eps[key] = url
                tree['主线剧情'][chapters['title']] = eps

    if os.path.exists(os.path.join(root, "actionSets.json")) and character2ds and events:
        data: list[dict] = tools.read_json(os.path.join(root, "actionSets.json"))
        tree['地图对话 - 地点筛选'] = {}
        tree['地图对话 - 人物筛选'] = {}
        tree['地图对话 - 活动追加'] = {}
        tree['地图对话 - 月度追加'] = {}
        as_count = 0
        as_count_sp = 0
        for ep in data:
            if (not ep.get("scenarioId")) or (not ep.get("actionSetType")):
                continue
            area: str = constant.areaDict[ep['areaId']]
            group: int = int(ep["id"] / 100)
            scenario_id: str = ep['scenarioId']
            chara_string: list[str] = []
            for cid in ep['characterIds']:
                for gc in character2ds:
                    if cid == gc['id']:
                        chara_string.append(constant.characterDict[gc['characterId'] - 1])
                        break
            chara: str = ",".join(chara_string)

            if ep.get("actionSetType") == "normal":
                as_count += 1
                as_id = f"{as_count:04d} - {chara} - id{ep['id']}"
            else:
                as_count_sp += 1
                as_id = f"S{as_count_sp:03d} - {chara} - id{ep['id']}"

            if source == "ai":
                url = f"https://assets.pjsek.ai/file/pjsekai-assets/startapp/scenario/actionset/" \
                      f"group{group}/{scenario_id}.json"
            else:
                url = f"https://storage.sekai.best/sekai-assets/scenario/actionset/" \
                      f"group{group}_rip/{scenario_id}.asset"

            if "monthly" in scenario_id:
                year = scenario_id.split("_")[1].removeprefix("monthly")[:2]
                month = scenario_id.split("_")[1].removeprefix("monthly")[2:]
                key = f"{year}年{month}月"
                d = tree['地图对话 - 月度追加'].get(key) or {}
                d[as_id] = url
                tree['地图对话 - 月度追加'][key] = d

            if "ev" in scenario_id:
                release_event_id = ep['releaseConditionId']
                if release_event_id > 100000:
                    release_event_id = int((release_event_id % 10000) / 100) + 1
                unit = constant.unit_dict[scenario_id.split("_")[2]]
                key = f"{release_event_id:03d}: {events[release_event_id - 1]['name']} - {unit}" \
                    if release_event_id < len(events) else f"{release_event_id}: 未知活动 - {unit}"
                d = tree['地图对话 - 活动追加'].get(key) or {}
                d[as_id] = url
                tree['地图对话 - 活动追加'][key] = d

            d = tree['地图对话 - 地点筛选'].get(area) or {}
            d[as_id] = url
            tree['地图对话 - 地点筛选'][area] = d

            for chara in chara_string:
                d = tree['地图对话 - 人物筛选'].get(chara) or {}
                d[as_id] = url
                tree['地图对话 - 人物筛选'][chara] = d

    if os.path.exists(os.path.join(root, "specialStories.json")):
        data = tools.read_json(os.path.join(root, "specialStories.json"))
        tree['特殊剧情'] = {}
        for period in data:
            title = period["title"]
            title_d = {}
            for ep in period['episodes']:
                ep_title = ep['title']
                if source == "best":
                    url = f"https://storage.sekai.best/sekai-assets/scenario/special/" \
                          f"{ep['assetbundleName']}_rip/{ep['scenarioId']}.asset"
                else:
                    url = f"https://assets.pjsek.ai/file/pjsekai-assets/startapp/scenario/special/" \
                          f"{ep['assetbundleName']}/{ep['scenarioId']}.json"
                title_d[ep_title] = url
            tree['特殊剧情'][title] = title_d
    if sum([bool(tree[key]) for key in tree.keys()]):
        os.makedirs(root, exist_ok=True)
        tools.save_json(os.path.join(root, "tree.json"), tree)
    return tree


class DownloadConfig(BaseModel):
    hash: str
    name: str
    url: str
    path: Optional[str] = None
    proxy: Optional[str] = None
    timeout: Optional[int] = None


class DownloadTask:
    def __init__(self, config: DownloadConfig):
        self.config = config
        self.hash = config.hash
        self.url = config.url
        self.name = config.name

        self.parsed_url = urlparse(self.url)
        self.source = "best" if 'best' in str(self.parsed_url.hostname) else "ai"
        self.filename = os.path.basename(self.parsed_url.path)

        self.dir = config.path or os.path.join(os.path.expanduser('~/Documents'), "SekaiSubtitle", "data", self.source)
        self.proxy = {"http://": config.proxy, "https://": config.proxy} if config.proxy else None
        self.timeout = config.timeout if config.timeout else None
        self.downloaded = False

    @property
    def fullpath(self):
        return os.path.join(self.dir, self.filename)

    @property
    def data(self):
        d = self.config.dict()
        d['fullpath'] = self.fullpath
        return d

    @property
    def exist(self):
        return os.path.exists(self.fullpath)

    def download(self):
        try_time = 0
        while try_time <= 5:
            try:
                with httpx.Client(proxies=self.proxy) as client:
                    resp = client.request("GET", self.url, timeout=self.timeout)
                    if resp.status_code == 200:
                        tools.save_json(os.path.join(self.dir, self.filename), resp.json())
                        self.downloaded = True
                        return True
            except Exception:
                try_time += 1
        return False

    def move(self, path):
        if self.exist:
            try:
                shutil.move(self.fullpath, path)
            except os.path.exists(os.path.join(path, self.filename)):
                os.remove(self.fullpath)
            finally:
                self.dir = path
                return True
        else:
            raise FileExistsError
