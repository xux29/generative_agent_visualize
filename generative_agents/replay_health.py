"""Health Simulation Replay Server

独立的健康模拟可视化服务器，不影响原有的 replay.py。

Usage:
    python replay_health.py

    # 在浏览器打开:
    # http://127.0.0.1:5001/?name=health-phone-addiction-init75_medium_20260130_162408
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request

# 健康模拟专用常量
frames_per_step = 60
file_movement = "movement.json"

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
    static_url_path="/static",
)


@app.route("/", methods=['GET'])
def index():
    name = request.args.get("name", "")          # 记录名称 (e.g., health-phone-addiction-init75_medium_xxx)
    step = int(request.args.get("step", 0))      # 回放起始步数
    speed = int(request.args.get("speed", 2))    # 回放速度（0~5）
    zoom = float(request.args.get("zoom", 0.0))  # 初始缩放比例（<=0 自动适配窗口）

    if len(name) < 1:
        # 显示可用的健康模拟列表
        return list_available_simulations()

    compressed_folder = f"results/compressed/{name}"
    replay_file = f"{compressed_folder}/{file_movement}"

    if not os.path.exists(replay_file):
        return f"""
        <h2>数据文件不存在</h2>
        <p>路径: {replay_file}</p>
        <p>请先运行 compress_health.py 生成数据：</p>
        <pre>python compress_health.py --list
python compress_health.py --scenario your-scenario</pre>
        <p><a href="/">返回列表</a></p>
        """

    with open(replay_file, "r", encoding="utf-8") as f:
        params = json.load(f)

    if step < 1:
        step = 1
    if step > 1:
        # 重新设置回放的起始时间
        t = datetime.fromisoformat(params["start_datetime"])
        dt = t + timedelta(minutes=params["stride"]*(step-1))
        params["start_datetime"] = dt.isoformat()
        step = (step-1) * frames_per_step + 1
        if step >= len(params["all_movement"]):
            step = len(params["all_movement"])-1

        # 重新设置Agent的初始位置
        for agent in params["persona_init_pos"].keys():
            persona_init_pos = params["persona_init_pos"]
            persona_step_pos = params["all_movement"][f"{step}"]
            if agent in persona_step_pos:
                persona_init_pos[agent] = persona_step_pos[agent]["movement"]

    if speed < 0:
        speed = 0
    elif speed > 5:
        speed = 5
    speed = 2 ** speed

    # 从movement.json获取agent列表
    agent_names = list(params.get("persona_init_pos", {}).keys())

    # 确保map_folder有默认值
    if "map_folder" not in params:
        params["map_folder"] = "village"

    return render_template(
        "index_health.html",
        persona_names=agent_names,
        step=step,
        play_speed=speed,
        zoom=zoom,
        **params
    )


def list_available_simulations():
    """列出所有可用的健康模拟数据"""
    compressed_dir = "results/compressed"
    simulations = []

    if os.path.exists(compressed_dir):
        for name in sorted(os.listdir(compressed_dir)):
            if name.startswith("health-"):
                path = os.path.join(compressed_dir, name)
                if os.path.isdir(path) and os.path.exists(os.path.join(path, file_movement)):
                    # 读取一些基本信息
                    try:
                        with open(os.path.join(path, file_movement), "r", encoding="utf-8") as f:
                            data = json.load(f)
                        agents = list(data.get("persona_init_pos", {}).keys())
                        steps = len([k for k in data.get("all_movement", {}).keys()
                                    if k not in ["description", "conversation"]])
                        simulations.append({
                            "name": name,
                            "agents": agents,
                            "steps": steps,
                            "map": data.get("map_folder", "village"),
                        })
                    except:
                        simulations.append({"name": name, "agents": [], "steps": 0, "map": "unknown"})

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>健康模拟可视化</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            h1 { color: #333; }
            .sim-list { list-style: none; padding: 0; }
            .sim-item {
                background: white;
                padding: 15px 20px;
                margin: 10px 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .sim-item a {
                font-size: 18px;
                color: #667eea;
                text-decoration: none;
                font-weight: bold;
            }
            .sim-item a:hover { text-decoration: underline; }
            .sim-meta { color: #666; font-size: 14px; margin-top: 5px; }
            .empty { color: #999; font-style: italic; }
            .help { background: #e8f4f8; padding: 15px; border-radius: 8px; margin-top: 20px; }
            pre { background: #333; color: #0f0; padding: 10px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>健康模拟可视化</h1>
    """

    if simulations:
        html += "<ul class='sim-list'>"
        for sim in simulations:
            html += f"""
            <li class='sim-item'>
                <a href="/?name={sim['name']}">{sim['name']}</a>
                <div class='sim-meta'>
                    地图: {sim['map']} |
                    角色: {', '.join(sim['agents']) if sim['agents'] else 'N/A'} |
                    帧数: {sim['steps']}
                </div>
            </li>
            """
        html += "</ul>"
    else:
        html += "<p class='empty'>暂无可用的健康模拟数据</p>"

    html += """
        <div class='help'>
            <h3>如何生成数据？</h3>
            <pre>
# 1. 运行健康模拟
python start_health_simulation_visual.py --scenario phone-addiction --days 45

# 2. 压缩数据
python compress_health.py --scenario phone-addiction

# 3. 刷新此页面查看
            </pre>
        </div>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    print("\n" + "="*60)
    print("健康模拟可视化服务器")
    print("="*60)
    print("访问地址: http://127.0.0.1:5001/")
    print("="*60 + "\n")
    app.run(debug=True, port=5001)
