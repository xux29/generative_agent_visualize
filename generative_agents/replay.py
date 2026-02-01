import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request

from compress import frames_per_step, file_movement

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
    static_url_path="/static",
)


@app.route("/", methods=['GET'])
def index():
    name = request.args.get("name", "")          # 记录名称
    step = int(request.args.get("step", 0))      # 回放起始步数
    speed = int(request.args.get("speed", 2))    # 回放速度（0~5）
    zoom = float(request.args.get("zoom", 0.8))  # 画面缩放比例

    if len(name) < 1:
        return f"Invalid name of the simulation: '{name}'"

    # 支持两种路径格式：
    # 1. 健康模拟: health-{scenario} -> results/compressed/health-{scenario}
    # 2. 普通模拟: {name} -> results/compressed/{name}
    compressed_folder = f"results/compressed/{name}"

    replay_file = f"{compressed_folder}/{file_movement}"
    if not os.path.exists(replay_file):
        return f"The data file doesn't exist: '{replay_file}'<br />Run compress.py to generate the data first."

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
            persona_init_pos[agent] = persona_step_pos[agent]["movement"]

    if speed < 0:
        speed = 0
    elif speed > 5:
        speed = 5
    speed = 2 ** speed

    # 从movement.json获取agent列表，而非使用硬编码的personas
    agent_names = list(params.get("persona_init_pos", {}).keys())

    # 确保map_folder有默认值
    if "map_folder" not in params:
        params["map_folder"] = "village"

    return render_template(
        "index.html",
        persona_names=agent_names,
        step=step,
        play_speed=speed,
        zoom=zoom,
        **params
    )


if __name__ == "__main__":
    app.run(debug=True)
