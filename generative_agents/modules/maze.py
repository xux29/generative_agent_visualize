"""generative_agents.maze"""

import random
from itertools import product

from modules import utils
from modules.memory.event import Event


class Tile:
    def __init__(
        self,
        coord,
        world,
        address_keys,
        address=None,
        collision=False,
    ):
        # in order: world, sector, arena, game_object
        self.coord = coord
        self.address = [world]
        if address:
            self.address += address
        self.address_keys = address_keys
        self.address_map = dict(zip(address_keys[: len(self.address)], self.address))
        self.collision = collision
        self.event_cnt = 0
        self._events = {}
        if len(self.address) == 4:
            self.add_event(Event(self.address[-1], address=self.address))

    def abstract(self):
        address = ":".join(self.address)
        if self.collision:
            address += "(collision)"
        return {
            "coord[{},{}]".format(self.coord[0], self.coord[1]): address,
            "events": {k: str(v) for k, v in self.events.items()},
        }

    def __str__(self):
        return utils.dump_dict(self.abstract())

    def __eq__(self, other):
        if isinstance(other, Tile):
            return hash(self.coord) == hash(other.coord)
        return False

    def get_events(self):
        return self.events.values()

    def add_event(self, event):
        if isinstance(event, (tuple, list)):
            event = Event.from_list(event)
        if all(e != event for e in self._events.values()):
            self._events["e_" + str(self.event_cnt)] = event
            self.event_cnt += 1
        return event

    def remove_events(self, subject=None, event=None):
        r_events = {}
        for tag, eve in self._events.items():
            if subject and eve.subject == subject:
                r_events[tag] = eve
            if event and eve == event:
                r_events[tag] = eve
        for r_eve in r_events:
            self._events.pop(r_eve)
        return r_events

    def update_events(self, event, match="subject"):
        u_events = {}
        for tag, eve in self._events.items():
            if match == "subject" and eve.subject == event.subject:
                self._events[tag] = event
                u_events[tag] = event
        return u_events

    def has_address(self, key):
        return key in self.address_map

    def get_address(self, level=None, as_list=True):
        level = level or self.address_keys[-1]
        assert level in self.address_keys, "Can not find {} from {}".format(
            level, self.address_keys
        )
        pos = self.address_keys.index(level) + 1
        if as_list:
            return self.address[:pos]
        return ":".join(self.address[:pos])

    def get_addresses(self):
        addresses = []
        if len(self.address) > 1:
            addresses = [
                ":".join(self.address[:i]) for i in range(2, len(self.address) + 1)
            ]
        return addresses

    @property
    def events(self):
        return self._events

    @property
    def is_empty(self):
        return len(self.address) == 1 and not self._events


class Maze:
    def __init__(self, config, logger):
        # define tiles
        self.maze_height, self.maze_width = config["size"]
        self.tile_size = config["tile_size"]
        address_keys = config["tile_address_keys"]
        self.tiles = [
            [
                Tile((x, y), config["world"], address_keys)
                for x in range(self.maze_width)
            ]
            for y in range(self.maze_height)
        ]
        for tile in config["tiles"]:
            x, y = tile.pop("coord")
            self.tiles[y][x] = Tile((x, y), config["world"], address_keys, **tile)

        # define address
        self.address_tiles = dict()
        for i in range(self.maze_height):
            for j in range(self.maze_width):
                for add in self.tile_at([j, i]).get_addresses():
                    self.address_tiles.setdefault(add, set()).add((j, i))

        self.logger = logger

        # 健康管理扩展：锁定区域管理
        self.locked_areas = {}  # {address_str: {"locked": bool, "locked_by": agent_name}}

    def find_path(self, src_coord, dst_coord):
        map = [[0 for _ in range(self.maze_width)] for _ in range(self.maze_height)]
        frontier, visited = [src_coord], set()
        map[src_coord[1]][src_coord[0]] = 1
        while map[dst_coord[1]][dst_coord[0]] == 0:
            new_frontier = []
            for f in frontier:
                for c in self.get_around(f):
                    if (
                        0 < c[0] < self.maze_width - 1
                        and 0 < c[1] < self.maze_height - 1
                        and map[c[1]][c[0]] == 0
                        and c not in visited
                    ):
                        map[c[1]][c[0]] = map[f[1]][f[0]] + 1
                        new_frontier.append(c)
                        visited.add(c)
            frontier = new_frontier
        step = map[dst_coord[1]][dst_coord[0]]
        path = [dst_coord]
        while step > 1:
            for c in self.get_around(path[-1]):
                if map[c[1]][c[0]] == step - 1:
                    path.append(c)
                    break
            step -= 1
        return path[::-1]

    def tile_at(self, coord):
        return self.tiles[coord[1]][coord[0]]

    def update_obj(self, coord, obj_event):
        tile = self.tile_at(coord)
        if not tile.has_address("game_object"):
            return
        if obj_event.address != tile.get_address("game_object"):
            return
        addr = ":".join(obj_event.address)
        if addr not in self.address_tiles:
            return
        for c in self.address_tiles[addr]:
            self.tile_at(c).update_events(obj_event)

    def get_scope(self, coord, config):
        coords = []
        vision_r = config["vision_r"]
        if config["mode"] == "box":
            x_range = [
                max(coord[0] - vision_r, 0),
                min(coord[0] + vision_r + 1, self.maze_width),
            ]
            y_range = [
                max(coord[1] - vision_r, 0),
                min(coord[1] + vision_r + 1, self.maze_height),
            ]
            coords = list(product(list(range(*x_range)), list(range(*y_range))))
        return [self.tile_at(c) for c in coords]

    def get_around(self, coord, no_collision=True):
        coords = [
            (coord[0] - 1, coord[1]),
            (coord[0] + 1, coord[1]),
            (coord[0], coord[1] - 1),
            (coord[0], coord[1] + 1),
        ]
        if no_collision:
            coords = [c for c in coords if not self.tile_at(c).collision]
        return coords

    def get_address_tiles(self, address):
        addr = ":".join(address)
        if addr in self.address_tiles:
            return self.address_tiles[addr]
        return random.choice(list(self.address_tiles.values()))

    # ===== 健康管理扩展：区域锁定功能 =====

    def lock_area(self, address, locked_by="Manager"):
        """
        锁定一个区域（通过设置该区域所有 Tile 的 collision=True）

        Args:
            address: 地址列表或字符串，如 ["the Ville", "玫瑰酒吧", "酒吧", "厨房水槽"]
            locked_by: 锁定者名称

        Returns:
            bool: 是否成功锁定
        """
        if isinstance(address, list):
            addr_str = ":".join(address)
        else:
            addr_str = address

        if addr_str not in self.address_tiles:
            self.logger.warning(f"Cannot lock area '{addr_str}': address not found")
            return False

        # 记录锁定状态
        self.locked_areas[addr_str] = {
            "locked": True,
            "locked_by": locked_by,
            "original_collision_state": {}
        }

        # 设置该区域所有 Tile 为 collision
        tiles = self.address_tiles[addr_str]
        for coord in tiles:
            tile = self.tile_at(coord)
            # 保存原始碰撞状态
            self.locked_areas[addr_str]["original_collision_state"][coord] = tile.collision
            tile.collision = True

        self.logger.info(f"{locked_by} locked area '{addr_str}' ({len(tiles)} tiles)")
        return True

    def unlock_area(self, address, unlocked_by="Manager"):
        """
        解锁一个区域

        Args:
            address: 地址列表或字符串
            unlocked_by: 解锁者名称

        Returns:
            bool: 是否成功解锁
        """
        if isinstance(address, list):
            addr_str = ":".join(address)
        else:
            addr_str = address

        if addr_str not in self.locked_areas:
            self.logger.warning(f"Cannot unlock area '{addr_str}': not locked")
            return False

        lock_info = self.locked_areas[addr_str]

        # 恢复原始碰撞状态
        tiles = self.address_tiles.get(addr_str, set())
        for coord in tiles:
            tile = self.tile_at(coord)
            original_state = lock_info["original_collision_state"].get(coord, False)
            tile.collision = original_state

        # 移除锁定记录
        del self.locked_areas[addr_str]

        self.logger.info(f"{unlocked_by} unlocked area '{addr_str}' ({len(tiles)} tiles)")
        return True

    def is_area_locked(self, address):
        """
        检查区域是否被锁定

        Args:
            address: 地址列表或字符串

        Returns:
            bool: 是否被锁定
        """
        if isinstance(address, list):
            addr_str = ":".join(address)
        else:
            addr_str = address

        return addr_str in self.locked_areas and self.locked_areas[addr_str]["locked"]

    def get_locked_areas(self):
        """
        获取所有被锁定的区域

        Returns:
            dict: 锁定区域信息
        """
        return {
            addr: {
                "locked_by": info["locked_by"],
                "tile_count": len(self.address_tiles.get(addr, set()))
            }
            for addr, info in self.locked_areas.items()
            if info["locked"]
        }

    def can_agent_access(self, coord, agent_name=None):
        """
        检查 Agent 是否能访问某个坐标

        Args:
            coord: 坐标
            agent_name: Agent 名称（未来可扩展为特定 Agent 可以访问锁定区域）

        Returns:
            bool: 是否可访问
        """
        tile = self.tile_at(coord)

        # 如果 Tile 本身就是碰撞的（非锁定导致），不可访问
        if tile.collision:
            # 检查是否是被锁定导致的
            for addr_str, lock_info in self.locked_areas.items():
                if coord in lock_info.get("original_collision_state", {}):
                    # 这是被锁定的区域
                    # 未来可以扩展：特定 Agent（如 Manager）可以访问
                    if agent_name and agent_name == lock_info.get("locked_by"):
                        return True
                    return False

            # 不是锁定导致的碰撞，不可访问
            return False

        return True
