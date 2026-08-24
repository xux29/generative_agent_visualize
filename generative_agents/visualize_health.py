"""Health Simulation Visualization

This module provides visualization for health simulation results,
integrating with the existing replay system.

Usage:
    python visualize_health.py --scenario weight-loss
    python visualize_health.py --scenario phone-addiction --day 10
"""

import os
import sys
import json
import argparse
from pathlib import Path
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.health_mechanisms.editor_http import register_editor_routes


app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static"
)
register_editor_routes(app)


def load_simulation_data(scenario_name, result_path="results/health"):
    """Load all simulation data for a scenario"""
    scenario_path = Path(result_path) / scenario_name

    if not scenario_path.exists():
        return None

    data = {
        "scenario": scenario_name,
        "daily_logs": [],
        "report": None
    }

    # Load daily logs
    for log_file in sorted(scenario_path.glob("day_*.json")):
        with open(log_file, 'r', encoding='utf-8') as f:
            data["daily_logs"].append(json.load(f))

    # Load final report
    report_file = scenario_path / "final_report.json"
    if report_file.exists():
        with open(report_file, 'r', encoding='utf-8') as f:
            data["report"] = json.load(f)

    return data


@app.route("/")
def index():
    """Main page - list available scenarios"""
    result_path = Path("results/health")
    scenarios = []

    if result_path.exists():
        for scenario_dir in result_path.iterdir():
            if scenario_dir.is_dir():
                report_file = scenario_dir / "final_report.json"
                if report_file.exists():
                    with open(report_file, 'r', encoding='utf-8') as f:
                        report = json.load(f)
                        scenarios.append({
                            "name": scenario_dir.name,
                            "days": report.get("total_days", 0),
                            "avg_score": report.get("average_health_score", 0)
                        })

    return render_template("health_index.html", scenarios=scenarios)


@app.route("/api/scenarios")
def api_scenarios():
    """API: List all scenarios"""
    result_path = Path("results/health")
    scenarios = []

    if result_path.exists():
        for scenario_dir in result_path.iterdir():
            if scenario_dir.is_dir():
                scenarios.append(scenario_dir.name)

    return jsonify({"scenarios": scenarios})


@app.route("/api/scenario/<scenario_name>")
def api_scenario(scenario_name):
    """API: Get scenario data"""
    data = load_simulation_data(scenario_name)
    if data:
        return jsonify(data)
    else:
        return jsonify({"error": "Scenario not found"}), 404


@app.route("/api/scenario/<scenario_name>/day/<int:day>")
def api_day(scenario_name, day):
    """API: Get specific day data"""
    data = load_simulation_data(scenario_name)
    if not data:
        return jsonify({"error": "Scenario not found"}), 404

    for log in data["daily_logs"]:
        if log.get("day") == day:
            return jsonify(log)

    return jsonify({"error": f"Day {day} not found"}), 404


@app.route("/api/scenario/<scenario_name>/chart/health")
def api_health_chart(scenario_name):
    """API: Get health score chart data"""
    data = load_simulation_data(scenario_name)
    if not data or not data.get("report"):
        return jsonify({"error": "Data not available"}), 404

    report = data["report"]
    chart_data = {
        "labels": list(range(1, len(report["daily_health_scores"]) + 1)),
        "datasets": [{
            "label": "健康分",
            "data": report["daily_health_scores"],
            "borderColor": "rgb(75, 192, 192)",
            "tension": 0.1
        }]
    }

    return jsonify(chart_data)


@app.route("/api/scenario/<scenario_name>/chart/interventions")
def api_interventions_chart(scenario_name):
    """API: Get interventions chart data"""
    data = load_simulation_data(scenario_name)
    if not data or not data.get("report"):
        return jsonify({"error": "Data not available"}), 404

    report = data["report"]
    summary = report["intervention_summary"]

    chart_data = {
        "labels": ["观察 (L0)", "劝说 (L1)", "移除 (L2)", "锁定 (L3)"],
        "datasets": [{
            "label": "干预次数",
            "data": [
                summary["level_0"],
                summary["level_1"],
                summary["level_2"],
                summary["level_3"]
            ],
            "backgroundColor": [
                "rgba(75, 192, 192, 0.5)",
                "rgba(255, 206, 86, 0.5)",
                "rgba(255, 159, 64, 0.5)",
                "rgba(255, 99, 132, 0.5)"
            ]
        }]
    }

    return jsonify(chart_data)


@app.route("/scenario/<scenario_name>")
def scenario_detail(scenario_name):
    """Scenario detail page"""
    data = load_simulation_data(scenario_name)
    if not data:
        return "Scenario not found", 404

    return render_template("health_scenario.html", data=data)


@app.route("/scenario/<scenario_name>/timeline")
def scenario_timeline(scenario_name):
    """Timeline view for a scenario"""
    data = load_simulation_data(scenario_name)
    if not data:
        return "Scenario not found", 404

    return render_template("health_timeline.html", data=data)


def create_templates():
    """Create HTML templates if they don't exist"""
    template_dir = Path("frontend/templates")
    template_dir.mkdir(parents=True, exist_ok=True)

    # Health index template
    index_html = """<!DOCTYPE html>
<html>
<head>
    <title>健康管理模拟 - 场景列表</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .scenario-list { display: flex; flex-wrap: wrap; gap: 20px; }
        .scenario-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            min-width: 250px;
        }
        .scenario-card h3 { margin-top: 0; color: #2196F3; }
        .score { font-size: 24px; font-weight: bold; color: #4CAF50; }
        a { color: #2196F3; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>健康管理模拟系统</h1>
    <p><a href="/editor">机制编辑对话（AI）</a> · 改参数/机制走提案，批准后才落地</p>
    <div class="scenario-list">
        {% for s in scenarios %}
        <div class="scenario-card">
            <h3>{{ s.name }}</h3>
            <p>模拟天数: {{ s.days }}</p>
            <p>平均健康分: <span class="score">{{ "%.1f"|format(s.avg_score) }}</span> / 10</p>
            <p>
                <a href="/scenario/{{ s.name }}">查看详情</a> |
                <a href="/scenario/{{ s.name }}/timeline">时间线</a>
            </p>
        </div>
        {% endfor %}
    </div>
    {% if not scenarios %}
    <p>暂无模拟数据。请先运行模拟：</p>
    <pre>python start_health_simulation.py --scenario weight-loss --days 7</pre>
    {% endif %}
</body>
</html>"""

    # Scenario detail template
    scenario_html = """<!DOCTYPE html>
<html>
<head>
    <title>{{ data.scenario }} - 健康管理模拟</title>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .charts { display: flex; flex-wrap: wrap; gap: 20px; margin-top: 20px; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; flex: 1; min-width: 400px; }
        .summary { background: white; padding: 20px; border-radius: 8px; margin-top: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f5f5f5; }
        a { color: #2196F3; }
    </style>
</head>
<body>
    <h1>{{ data.scenario }} - 健康管理模拟报告</h1>
    <p><a href="/">← 返回列表</a></p>

    {% if data.report %}
    <div class="summary">
        <h2>总结</h2>
        <p><strong>被监督者:</strong> {{ data.report.target }}</p>
        <p><strong>监督者:</strong> {{ data.report.manager }}</p>
        <p><strong>总天数:</strong> {{ data.report.total_days }}</p>
        <p><strong>平均健康分:</strong> {{ "%.2f"|format(data.report.average_health_score) }} / 10</p>
    </div>

    <div class="charts">
        <div class="chart-container">
            <h3>每日健康分趋势</h3>
            <canvas id="healthChart"></canvas>
        </div>
        <div class="chart-container">
            <h3>干预策略分布</h3>
            <canvas id="interventionChart"></canvas>
        </div>
    </div>

    <div class="summary">
        <h2>每日记录</h2>
        <table>
            <tr>
                <th>天数</th>
                <th>健康分</th>
                <th>干预次数</th>
                <th>操作</th>
            </tr>
            {% for log in data.daily_logs %}
            <tr>
                <td>Day {{ log.day }}</td>
                <td>{{ log.health_score }}</td>
                <td>{{ log.interventions|length }}</td>
                <td><a href="/api/scenario/{{ data.scenario }}/day/{{ log.day }}">JSON</a></td>
            </tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}

    <script>
        // Health score chart
        fetch('/api/scenario/{{ data.scenario }}/chart/health')
            .then(res => res.json())
            .then(data => {
                new Chart(document.getElementById('healthChart'), {
                    type: 'line',
                    data: data,
                    options: {
                        scales: { y: { beginAtZero: true, max: 10 } }
                    }
                });
            });

        // Intervention chart
        fetch('/api/scenario/{{ data.scenario }}/chart/interventions')
            .then(res => res.json())
            .then(data => {
                new Chart(document.getElementById('interventionChart'), {
                    type: 'bar',
                    data: data
                });
            });
    </script>
</body>
</html>"""

    # Timeline template
    timeline_html = """<!DOCTYPE html>
<html>
<head>
    <title>{{ data.scenario }} - 时间线</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .timeline { max-width: 800px; margin: 0 auto; }
        .day { background: white; margin: 20px 0; padding: 20px; border-radius: 8px; }
        .day h3 { margin-top: 0; color: #2196F3; }
        .event { padding: 10px; margin: 5px 0; border-left: 3px solid #ccc; }
        .event.intention { border-color: #FF9800; }
        .event.intervention { border-color: #4CAF50; }
        .score { float: right; font-weight: bold; }
        .score.high { color: #4CAF50; }
        .score.mid { color: #FF9800; }
        .score.low { color: #F44336; }
        a { color: #2196F3; }
    </style>
</head>
<body>
    <h1>{{ data.scenario }} - 时间线视图</h1>
    <p><a href="/scenario/{{ data.scenario }}">← 返回报告</a></p>

    <div class="timeline">
        {% for log in data.daily_logs %}
        <div class="day">
            <h3>Day {{ log.day }}
                <span class="score {% if log.health_score >= 7 %}high{% elif log.health_score >= 4 %}mid{% else %}low{% endif %}">
                    健康分: {{ log.health_score }}/10
                </span>
            </h3>

            {% for event in log.events %}
            <div class="event intention">
                <strong>[{{ event.time }}]</strong> {{ event.agent }}: {{ event.content }}
                {% if event.inner_monologue %}
                <br><em>内心: {{ event.inner_monologue }}</em>
                {% endif %}
            </div>
            {% endfor %}

            {% for intervention in log.interventions %}
            <div class="event intervention">
                <strong>[{{ intervention.time }}]</strong>
                干预 Level {{ intervention.level }}: {{ intervention.action }}
                <br><em>原因: {{ intervention.reason }}</em>
            </div>
            {% endfor %}

            {% if log.reflection %}
            <div class="event">
                <strong>每日反思:</strong> {{ log.reflection.today_summary }}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>"""

    # Write templates
    (template_dir / "health_index.html").write_text(index_html, encoding='utf-8')
    (template_dir / "health_scenario.html").write_text(scenario_html, encoding='utf-8')
    (template_dir / "health_timeline.html").write_text(timeline_html, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="Health Simulation Visualization")
    parser.add_argument("--port", type=int, default=5001, help="Server port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")

    args = parser.parse_args()

    # Create templates
    create_templates()

    print(f"Starting health visualization server at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
