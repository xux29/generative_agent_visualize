#!/usr/bin/env python3
"""
Tiled地图到空间树转换工具 (命令行版本)

用法:
    # 一键转换: Tiled -> Maze -> 空间树
    python tiled_to_maze.py convert -i input.json -o ./output/

    # 更新Agent空间数据
    python tiled_to_maze.py update-agents -t spatial_tree.json -a ./agents/
"""

import json
import os
from collections import defaultdict
import re
import xml.etree.ElementTree as ET
import argparse
import copy


def update_spatial_data_in_agents(spatial_tree_filepath, agents_base_folder_path, verbose=False):
    """
    Updates the 'spatial' data in agent.json files based on a spatial_tree.json file.
    """
    try:
        if verbose:
            print("开始更新Agent空间数据...")

        # Construct absolute paths if relative paths are given
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)

        if not os.path.isabs(spatial_tree_filepath):
            spatial_tree_filepath = os.path.join(project_root, spatial_tree_filepath)

        if not os.path.isabs(agents_base_folder_path):
            agents_base_folder_path = os.path.join(project_root, agents_base_folder_path)

        if verbose:
            print(f"读取空间树文件: {os.path.basename(spatial_tree_filepath)}")

        with open(spatial_tree_filepath, 'r', encoding='utf-8') as f:
            spatial_data_source = json.load(f)

        if 'spatial' not in spatial_data_source:
            error_msg = f"错误: 'spatial' 键未在 {spatial_tree_filepath} 中找到"
            print(error_msg)
            return False, error_msg

        new_spatial_info = spatial_data_source['spatial']

        if verbose:
            print("遍历Agent文件夹...")

        updated_files_count = 0
        skipped_files_count = 0
        error_files_count = 0
        total_agent_folders = [name for name in os.listdir(agents_base_folder_path) if os.path.isdir(os.path.join(agents_base_folder_path, name))]
        num_agent_folders = len(total_agent_folders)

        for i, agent_folder_name in enumerate(total_agent_folders):
            agent_folder_path = os.path.join(agents_base_folder_path, agent_folder_name)
            agent_json_path = os.path.join(agent_folder_path, 'agent.json')

            if verbose:
                print(f"处理Agent: {agent_folder_name} ({i+1}/{num_agent_folders})")

            if os.path.isfile(agent_json_path):
                try:
                    with open(agent_json_path, 'r', encoding='utf-8') as f:
                        agent_data = json.load(f)

                    agent_data['spatial'] = new_spatial_info

                    with open(agent_json_path, 'w', encoding='utf-8') as f:
                        json.dump(agent_data, f, ensure_ascii=False, indent=2)
                    if verbose:
                        print(f"  成功更新: {os.path.basename(agent_folder_name)}/agent.json")
                    updated_files_count += 1
                except json.JSONDecodeError:
                    error_msg = f"错误: 无法解码JSON {agent_json_path}. 跳过此文件."
                    print(error_msg)
                    error_files_count += 1
                    continue
                except Exception as e:
                    error_msg = f"读取/写入 {agent_json_path} 时出错: {e}. 跳过此文件."
                    print(error_msg)
                    error_files_count += 1
                    continue
            else:
                if verbose:
                    print(f"  警告: agent.json 未在 {agent_folder_path} 中找到")
                skipped_files_count += 1

        final_status_msg = f"Agent空间数据更新完成. 更新: {updated_files_count}, 跳过: {skipped_files_count}, 错误: {error_files_count}."
        print(final_status_msg)
        return True, final_status_msg

    except FileNotFoundError as e:
        error_msg = f"错误: 文件未找到 - {e}"
        print(error_msg)
        return False, error_msg
    except json.JSONDecodeError as e:
        error_msg = f"错误: JSON解码失败 - {e}"
        print(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"更新Agent空间数据时发生意外错误: {e}"
        print(error_msg)
        return False, error_msg


def convert_tiled_to_maze(tiled_filepath, maze_filepath, verbose=False):
    """
    将 JSON 地图文件转换为 maze.json 格式。
    """
    try:
        if verbose:
            print("正在读取Tiled文件...")

        with open(tiled_filepath, 'r', encoding='utf-8') as f:
            tiled_data = json.load(f)

        if verbose:
            print("正在创建基础Maze结构...")

        maze_data = {
            "world": "the Ville",
            "tile_size": tiled_data["tilewidth"],
            "size": [tiled_data["height"], tiled_data["width"]],
            "map": {
                "asset": "map",
                "tileset_groups": {
                    "group_1": []
                },
                "layers": [],
                "collision_tiles": [2843]
            },
            "camera": {
                "zoom_factor": 1,
                "zoom_range": [
                    0.5,
                    10,
                    0.01
                ]
            },
            "tile_address_keys": [
                "world",
                "sector",
                "arena",
                "game_object"
            ],
            "tiles": []
        }

        # 处理 tilesets
        if verbose:
            print("处理图块集...")

        tiled_dir = os.path.dirname(tiled_filepath)
        for tileset in tiled_data["tilesets"]:
            if "source" in tileset:
                # 处理外部 tileset
                tsj_path = os.path.join(tiled_dir, tileset["source"].replace("\\", "/"))
                try:
                    _, ext = os.path.splitext(tsj_path)
                    if ext.lower() == ".tsx":
                        try:
                            tree = ET.parse(tsj_path)
                        except ET.ParseError as parse_err:
                            raise ValueError(f"解析TSX tileset {tileset['source']} 失败: {parse_err}") from parse_err
                        image_elem = tree.getroot().find("image")
                        if image_elem is None or not image_elem.get("source"):
                            raise ValueError(f"TSX tileset {tileset['source']} 缺少 image source")
                        image_path = image_elem.get("source")
                    else:
                        with open(tsj_path, 'r', encoding='utf-8') as tsj_f:
                            external_tileset = json.load(tsj_f)
                        image_path = external_tileset.get("image")
                        if not image_path:
                            raise ValueError(f"External tileset {tileset['source']} missing 'image' key")
                    tileset_name = os.path.basename(image_path).split('.')[0]
                except FileNotFoundError:
                    source_basename = os.path.basename(tileset["source"])
                    tileset_name = os.path.splitext(source_basename)[0]
                    if verbose:
                        print(f"  警告: 未找到外部tileset {tsj_path}, 使用回退名称 {tileset_name}")
                except (json.JSONDecodeError, ValueError) as parse_error:
                    source_basename = os.path.basename(tileset["source"])
                    tileset_name = os.path.splitext(source_basename)[0]
                    if verbose:
                        print(f"  警告: 解析tileset {tileset['source']} 失败: {parse_error}, 使用回退名称 {tileset_name}")
            else:
                # 内部 tileset
                image_path = tileset.get("image")
                if not image_path:
                    raise ValueError("Tileset missing 'image' key")
                tileset_name = os.path.basename(image_path).split('.')[0]

            maze_data["map"]["tileset_groups"]["group_1"].append(tileset_name)

        # 分离不同类型的图层
        address_layers = []
        world_layer = None
        collision_layer = None

        if verbose:
            print("识别图层类型...")

        for layer in tiled_data["layers"]:
            # 识别原始命名的图层
            if layer["name"].startswith("sector-") or layer["name"].startswith("arena-") or layer["name"].startswith("object-"):
                address_layers.append(layer)
            # 增加对数字开头图层的识别
            elif layer["name"].startswith("1"):
                layer["address_type"] = "sector"
                address_layers.append(layer)
            elif layer["name"].startswith("2"):
                layer["address_type"] = "arena"
                address_layers.append(layer)
            elif layer["name"].startswith("3"):
                layer["address_type"] = "object"
                address_layers.append(layer)
            elif layer["name"] == "world-xy":
                world_layer = layer
            elif layer["name"] == "collisions":
                collision_layer = layer

        # 首先处理 address layers (sector-XXX, arena-XXX, object-XXX)
        if verbose:
            print("处理地址图层...")

        total_layers = len(address_layers)
        for idx, layer in enumerate(address_layers):
            if verbose:
                print(f"  处理图层 {layer['name']} ({idx+1}/{total_layers})...")

            maze_layer = {
                "name": layer["name"],
                "tileset_group": "group_1"
            }
            if "Foreground" in layer["name"]:
                maze_layer["depth"] = 2
            maze_data["map"]["layers"].append(maze_layer)

            layer_width = tiled_data["width"]
            layer_data = layer["data"]
            layer_name = layer["name"]

            address_name = layer_name

            address_type = None
            if layer_name.startswith("sector-"):
                address_type = "sector"
            elif layer_name.startswith("arena-"):
                address_type = "arena"
            elif layer_name.startswith("object-"):
                address_type = "game_object"
            elif "address_type" in layer:
                address_type = layer["address_type"]

            for index, tile_id in enumerate(layer_data):
                if tile_id != 0:
                    x = index % layer_width
                    y = index // layer_width
                    found_tile = False
                    for tile in maze_data["tiles"]:
                        if tile["coord"] == [x, y]:
                            if address_name not in tile["address"]:
                                tile["address"].append(address_name)
                            found_tile = True
                            break
                    if not found_tile:
                        new_tile_address = [address_name]
                        maze_data["tiles"].append({
                            "coord": [x, y],
                            "address": new_tile_address
                        })

        # 然后处理 world-xy layer
        if verbose:
            print("处理世界坐标图层...")

        if world_layer:
            maze_layer = {
                "name": world_layer["name"],
                "tileset_group": "group_1"
            }
            maze_data["map"]["layers"].append(maze_layer)

            layer_width = tiled_data["width"]
            layer_data = world_layer["data"]

            for index, tile_id in enumerate(layer_data):
                if tile_id != 0:
                    x = index % layer_width
                    y = index // layer_width
                    found_tile = False
                    for tile in maze_data["tiles"]:
                        if tile["coord"] == [x, y]:
                            found_tile = True
                            break
                    if not found_tile:
                        maze_data["tiles"].append({
                            "coord": [x, y],
                            "address": []
                        })


        # 最后处理碰撞图层
        if verbose:
            print("处理碰撞图层...")

        if collision_layer:
            maze_layer = {
                "name": collision_layer["name"],
                "tileset_group": "group_1",
                "depth": -1,
                "collision": {
                    "exclusion": [-1]
                }
            }
            maze_data["map"]["layers"].append(maze_layer)

            layer_width = tiled_data["width"]
            layer_data = collision_layer["data"]

            for index, tile_id in enumerate(layer_data):
                if tile_id != 0:
                    x = index % layer_width
                    y = index // layer_width
                    found_tile = False
                    for tile in maze_data["tiles"]:
                        if tile["coord"] == [x, y]:
                            tile["collision"] = True
                            found_tile = True
                            break
                    if not found_tile:
                        maze_data["tiles"].append({
                            "coord": [x, y],
                            "address": [],
                            "collision": True
                        })

        if verbose:
            print("写入Maze文件...")

        with open(maze_filepath, 'w', encoding='utf-8') as outfile:
            json.dump(maze_data, outfile, indent=4, ensure_ascii=False)

        if verbose:
            print("Maze文件创建完成!")

        return True, maze_data

    except Exception as e:
        print(f"错误: {str(e)}")
        return False, str(e)


def get_overlap_ratio(coords1, coords2):
    """计算两个坐标集合的重叠比例"""
    overlap = coords1.intersection(coords2)
    return len(overlap) / len(coords1)


def build_location_hierarchy(locations):
    hierarchy = {}
    processed = set()

    # 按数字前缀分组
    prefix_1_locations = {k: v for k, v in locations.items() if k.startswith("1")}
    prefix_2_locations = {k: v for k, v in locations.items() if k.startswith("2")}
    prefix_3_locations = {k: v for k, v in locations.items() if k.startswith("3")}

    # 构建层级关系
    for loc1_name, coords1 in prefix_1_locations.items():
        hierarchy[loc1_name] = {}
        processed.add(loc1_name)

        # 查找相交的2级区域
        for loc2_name, coords2 in prefix_2_locations.items():
            if loc2_name in processed:
                continue

            if len(coords1.intersection(coords2)) > 0:
                hierarchy[loc1_name][loc2_name] = []
                processed.add(loc2_name)

                # 查找相交的3级物体
                for loc3_name, coords3 in prefix_3_locations.items():
                    if loc3_name in processed:
                        continue

                    if len(coords2.intersection(coords3)) > 0:
                        hierarchy[loc1_name][loc2_name].append(loc3_name)
                        processed.add(loc3_name)

    return hierarchy


def convert_maze_to_tree(maze_data, verbose=False):
    """将迷宫数据转换为空间树结构

    Args:
        maze_data: 迷宫JSON数据
        verbose: 是否输出详细信息
    Returns:
        (bool, object) 转换成功与否及转换结果或错误信息
    """
    try:
        if verbose:
            print("开始创建空间树...")

        # 初始化空间树结构
        spatial_tree = {
            "spatial": {
                "address": {
                    "living_area": [maze_data["world"]]
                },
                "tree": {
                    maze_data["world"]: {}
                }
            }
        }

        if verbose:
            print("收集坐标地址信息...")

        # 用于存储每个坐标的地址信息
        coord_addresses = defaultdict(list)

        # 遍历所有地块,收集地址信息
        for tile in maze_data["tiles"]:
            if "address" in tile:
                coord = tuple(tile["coord"])
                coord_addresses[coord].extend(tile["address"])

        if verbose:
            print("分离地点和物体...")

        # 分离地点和物体
        locations = {}
        objects = defaultdict(list)

        for coord, addresses in coord_addresses.items():
            for addr in addresses:
                # 原始格式检查
                if addr.startswith("sector-") or addr.startswith("arena-"):
                    location_name = addr
                    if location_name not in locations:
                        locations[location_name] = set()
                    locations[location_name].add(coord)
                elif addr.startswith("object-"):
                    obj_name = addr
                    for loc_name, loc_coords in locations.items():
                        if coord in loc_coords:
                            objects[loc_name].append(obj_name)
                # 处理数字前缀的地址
                elif addr.startswith("1"):
                    location_name = addr
                    if location_name not in locations:
                        locations[location_name] = set()
                    locations[location_name].add(coord)
                elif addr.startswith("2"):
                    location_name = addr
                    if location_name not in locations:
                        locations[location_name] = set()
                    locations[location_name].add(coord)
                elif addr.startswith("3"):
                    obj_name = addr
                    for loc_name, loc_coords in locations.items():
                        if coord in loc_coords:
                            objects[loc_name].append(obj_name)

        if verbose:
            print("构建地点层级关系...")

        # 构建地点层级关系
        location_hierarchy = build_location_hierarchy(locations)

        if verbose:
            print("构建最终树结构...")

        # 构建最终的树结构
        def build_tree(hierarchy, objects):
            tree = {}
            for loc_name, children in hierarchy.items():
                base_name = loc_name
                if children:
                    tree[base_name] = build_tree(children, objects)
                else:
                    location_objects = list(set(objects[base_name]))
                    tree[base_name] = location_objects
            return tree

        # 构建树结构
        world_tree = spatial_tree["spatial"]["tree"][maze_data["world"]]
        world_tree.update(build_tree(location_hierarchy, objects))

        if verbose:
            print("空间树创建完成!")

        return True, spatial_tree
    except Exception as e:
        print(f"错误: {str(e)}")
        return False, str(e)


def remove_number_prefix(data):
    """
    移除JSON数据中的数字前缀

    Args:
        data: 要处理的数据（maze.json或spatial_tree.json）
    Returns:
        处理后的数据
    """
    if isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            if isinstance(key, str) and re.match(r'^[123]\w+', key):
                new_key = re.sub(r'^[123]', '', key)
                new_data[new_key] = remove_number_prefix(value)
            else:
                new_data[key] = remove_number_prefix(value)
        return new_data
    elif isinstance(data, list):
        new_data = []
        for item in data:
            if isinstance(item, str) and re.match(r'^[123]\w+', item):
                new_item = re.sub(r'^[123]', '', item)
                new_data.append(new_item)
            else:
                new_data.append(remove_number_prefix(item))
        return new_data
    else:
        return data


def create_simplified_tiled(tiled_data):
    """
    创建Tiled地图数据的简化版本，移除大型数据字段，减小文件体积

    Args:
        tiled_data: Tiled格式的地图数据
    Returns:
        简化后的数据
    """
    simplified_data = copy.deepcopy(tiled_data)

    # 移除layers中的data字段
    if "layers" in simplified_data:
        for layer in simplified_data["layers"]:
            if "data" in layer:
                del layer["data"]
                layer["__note__"] = "Data字段已被移除以减小文件体积，此文件仅用于参考"

    simplified_data["__simplified_note__"] = "此文件为简化版，已移除图层数据等大型字段。适合AI分析或修改。"

    return simplified_data


def run_conversion(tiled_file, output_dir, maze_filename="maze.json", tree_filename="spatial_tree.json",
                   remove_prefix=True, create_simplified=True, verbose=False):
    """
    执行完整的转换流程: Tiled -> Maze -> 空间树

    Args:
        tiled_file: Tiled导出的JSON文件路径
        output_dir: 输出目录
        maze_filename: Maze文件名
        tree_filename: 空间树文件名
        remove_prefix: 是否移除数字前缀
        create_simplified: 是否创建简约信息文件
        verbose: 是否输出详细信息
    Returns:
        bool: 转换是否成功
    """
    maze_file = os.path.join(output_dir, maze_filename)
    tree_file = os.path.join(output_dir, tree_filename)

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 读取Tiled文件
        if verbose:
            print("正在读取Tiled文件...")

        with open(tiled_file, 'r', encoding='utf-8') as f:
            tiled_data = json.load(f)

        # 创建简约信息文件
        if create_simplified:
            if verbose:
                print("创建Tiled地图简约信息文件...")

            file_name = os.path.splitext(os.path.basename(tiled_file))[0]
            simplified_tiled_path = os.path.join(output_dir, f"{file_name}_简约信息.json")

            simplified_tiled_data = create_simplified_tiled(tiled_data)

            with open(simplified_tiled_path, 'w', encoding='utf-8') as f:
                json.dump(simplified_tiled_data, f, indent=2, ensure_ascii=False)

            print(f"已保存Tiled地图简约信息文件: {simplified_tiled_path}")

        # Tiled转Maze
        print("======== 第一步: Tiled → Maze ========")

        success, maze_data = convert_tiled_to_maze(tiled_file, maze_file, verbose)

        if not success:
            print(f"转换失败: {maze_data}")
            return False

        print(f"成功: Tiled地图已转换为Maze文件 {maze_file}")

        # Maze转空间树
        print("======== 第二步: Maze → 空间树 ========")

        success, tree_data = convert_maze_to_tree(maze_data, verbose)

        if not success:
            print(f"转换失败: {tree_data}")
            return False

        # 移除数字前缀
        if remove_prefix:
            if verbose:
                print("正在移除数字前缀...")

            maze_data = remove_number_prefix(maze_data)
            tree_data = remove_number_prefix(tree_data)

            # 重新写入Maze文件
            with open(maze_file, 'w', encoding='utf-8') as f:
                json.dump(maze_data, f, indent=4, ensure_ascii=False)

        # 写入空间树文件
        with open(tree_file, 'w', encoding='utf-8') as f:
            json.dump(tree_data, f, indent=2, ensure_ascii=False)

        print(f"已保存文件: {maze_file} 和 {tree_file}")
        print("======== 转换完成 ========")

        return True

    except Exception as e:
        print(f"转换过程中发生错误: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Tiled地图到空间树转换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 一键转换 Tiled -> Maze -> 空间树
  python tiled_to_maze.py convert -i map.json -o ./output/

  # 转换并保留数字前缀
  python tiled_to_maze.py convert -i map.json -o ./output/ --keep-prefix

  # 更新Agent空间数据
  python tiled_to_maze.py update-agents -t spatial_tree.json -a ./agents/
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # convert 子命令
    convert_parser = subparsers.add_parser("convert", help="转换Tiled地图到Maze和空间树")
    convert_parser.add_argument("-i", "--input", required=True, help="Tiled导出的JSON文件路径")
    convert_parser.add_argument("-o", "--output", default=".", help="输出目录 (默认: 当前目录)")
    convert_parser.add_argument("--maze-name", default="maze.json", help="Maze文件名 (默认: maze.json)")
    convert_parser.add_argument("--tree-name", default="spatial_tree.json", help="空间树文件名 (默认: spatial_tree.json)")
    convert_parser.add_argument("--keep-prefix", action="store_true", help="保留数字前缀 (默认会移除)")
    convert_parser.add_argument("--no-simplified", action="store_true", help="不创建简约信息文件")
    convert_parser.add_argument("-v", "--verbose", action="store_true", help="输出详细信息")

    # update-agents 子命令
    update_parser = subparsers.add_parser("update-agents", help="更新Agent空间数据")
    update_parser.add_argument("-t", "--tree", required=True, help="spatial_tree.json文件路径")
    update_parser.add_argument("-a", "--agents", required=True, help="Agent文件夹路径")
    update_parser.add_argument("-v", "--verbose", action="store_true", help="输出详细信息")

    args = parser.parse_args()

    if args.command == "convert":
        success = run_conversion(
            tiled_file=args.input,
            output_dir=args.output,
            maze_filename=args.maze_name,
            tree_filename=args.tree_name,
            remove_prefix=not args.keep_prefix,
            create_simplified=not args.no_simplified,
            verbose=args.verbose
        )
        return 0 if success else 1

    elif args.command == "update-agents":
        success, _ = update_spatial_data_in_agents(
            spatial_tree_filepath=args.tree,
            agents_base_folder_path=args.agents,
            verbose=args.verbose
        )
        return 0 if success else 1

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    exit(main())
