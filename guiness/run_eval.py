# -*- coding: utf-8 -*-
"""
主入口脚本
"""
import os
import sys
import subprocess
import argparse
import logging
import json
import time
from datetime import datetime

from reporter.cli_reporter import (
    CliReporter,
    banner as _banner,
    fail as _fail,
    info as _info,
    kv as _kv,
    ok as _ok,
    progress_bar as _progress_bar,
    section as _section,
    warn as _warn,
    _C,
)


def check_and_install_dependencies():
    """在程序启动前自动检查并安装依赖项"""
    required_packages = {
        'yaml': 'PyYAML',
        'requests': 'requests',
        'PIL': 'Pillow',
        'uiautomator2': 'uiautomator2'
    }

    missing_packages = []
    for module_name, pip_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            missing_packages.append(pip_name)

    if missing_packages:
        _warn(f"缺失依赖: {', '.join(missing_packages)}，正在安装...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q"] + missing_packages,
                stdout=subprocess.DEVNULL
            )
            _ok("依赖安装完成")
        except subprocess.CalledProcessError:
            _fail(f"安装失败，请手动执行: pip install {' '.join(missing_packages)}")
            sys.exit(1)

from utils.config_loader import get_config, get_device_config, get_task_config
from core import build_components, build_runner, resolve_device_id

logging.basicConfig(level=logging.WARNING, format='%(name)s: %(message)s')
logger = logging.getLogger("Main")

def parse_args():
    parser = argparse.ArgumentParser(description="Online Evaluation System")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Only load structure, do not run test")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细调试日志")
    return parser.parse_args()

def load_jsonl(file_path):
    tasks = []
    if not os.path.exists(file_path):
        _fail(f"任务文件不存在: {file_path}")
        return tasks
        
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError as e:
                _warn(f"解析失败: {e}")
    return tasks

def main():
    check_and_install_dependencies()

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    _banner()
    
    # 1. 挂载配置
    try:
        config = get_config(args.config)
    except FileNotFoundError as e:
        _fail(f"无法启动: {e}")
        return
        
    if args.dry_run:
        _ok("Dry-run 通过，所有模块加载正常")
        return
        
    device_cfg = get_device_config()
    task_cfg = get_task_config()
    
    task_file = task_cfg.get("task_file")
    if not task_file:
        _fail("config.yaml 中未配置 task_file")
        return
        
    tasks = load_jsonl(task_file)
    if not tasks:
        _warn(f"任务文件为空: {task_file}")
        return

    _section("配置信息")
    model_name = config.get("model", {}).get("model_name", "unknown")
    _kv("配置文件", args.config)
    _kv("推理模型", model_name)
    _kv("任务文件", os.path.basename(task_file))
    _kv("任务数量", f"{len(tasks)} 条")
    _kv("最大步数", config.get("operation", {}).get("max_steps", 100))
        
    # 2. 初始化核心组件
    device_type = device_cfg.get("device_type", "phone")
    mode = device_cfg.get("mode", "usb")
    try:
        if mode == "wifi":
            device_id = resolve_device_id(device_cfg.get("wifi_endpoint", ""), mode="wifi")
        else:
            device_id = resolve_device_id(device_cfg.get("name", ""), mode="usb")
    except RuntimeError as e:
        _fail(str(e))
        return

    _section("初始化组件")

    _step_labels = {
        "正在连接 ADB 设备...": "ADB 控制器",
        "正在连接 WiFi 设备...": "WiFi 控制器",
        "正在初始化 UI 自动化服务...": "Uiautomator2",
        "正在配置推理客户端...": "推理客户端",
    }
    try:
        comps = build_components(
            device_id=device_id,
            device_type=device_type,
            model_config=config.get("model", {}),
            mode=mode,
            token=device_cfg.get("token", ""),
            on_progress=lambda msg: _ok(_step_labels.get(msg, msg)),
        )
    except Exception as e:
        _fail(f"组件初始化失败  →  {e}")
        return
    _ok("动作执行器")

    run_date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = os.path.join("data", "output", run_date_str)
    os.makedirs(output_dir, exist_ok=True)

    max_steps = config.get("operation", {}).get("max_steps", 100)
    runner = build_runner(
        components=comps,
        config=config,
        output_dir=output_dir,
        date_str=run_date_str,
        reporter=CliReporter(max_steps=max_steps),
    )
    _ok("Episode 引擎")

    _kv("设备", f"{device_id} ({device_type})")
    _kv("输出目录", os.path.abspath(output_dir))
    
    comps.backend.force_stop_all_known_apps(device_type)
    
    results_jsonl = os.path.join(output_dir, "results.jsonl")
    
    _section("执行评测任务")
    print()
    
    success_count = 0
    fail_count = 0
    total = len(tasks)
    t_start_all = time.time()
    
    for idx, task_data in enumerate(tasks):
        task_num = idx + 1
        query = task_data.get("query", "—")
        app = task_data.get("app", "")
        display_query = query if len(query) <= 40 else query[:37] + "..."
        
        print(f"  {_C.BOLD}[{task_num}/{total}]{_C.RESET} {display_query}")
        if app:
            print(f"        {_C.DIM}App: {app}{_C.RESET}")
        
        t_start = time.time()
        try:
            res = runner.run(task_data)
            elapsed = time.time() - t_start
            if res:
                with open(results_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
            steps_used = len(res.get("data", [])) if res else 0
            _ok(f"完成  {_C.DIM}{steps_used} 步 · {elapsed:.1f}s{_C.RESET}")
            success_count += 1
        except Exception as e:
            elapsed = time.time() - t_start
            _fail(f"异常  {_C.DIM}{elapsed:.1f}s{_C.RESET}  →  {e}")
            fail_count += 1
            logger.debug("Task execution exception", exc_info=True)
        
        print(f"        {_progress_bar(task_num, total)}")
        print()
    
    # ─── 完成总结 ───
    elapsed_all = time.time() - t_start_all
    minutes = int(elapsed_all // 60)
    seconds = int(elapsed_all % 60)
    
    abs_output = os.path.abspath(output_dir)
    review_port = config.get("review", {}).get("port", 5000)
    review_route = config.get("review", {}).get("route", "eval-review")
    
    print()
    print(f"  {_C.BOLD}{_C.GREEN}╔══════════════════════════════════════════╗{_C.RESET}")
    print(f"  {_C.BOLD}{_C.GREEN}║            评测完成                       ║{_C.RESET}")
    print(f"  {_C.BOLD}{_C.GREEN}╚══════════════════════════════════════════╝{_C.RESET}")
    print()
    _kv("成功 / 失败", f"{_C.GREEN}{success_count}{_C.RESET} / {_C.RED}{fail_count}{_C.RESET}")
    _kv("总耗时", f"{minutes}m {seconds}s")
    _kv("结果目录", abs_output)
    print()
    _info("启动 Review 服务查看结果:")
    print(f"    {_C.CYAN}cd review-tool && python server.py --data-dir {abs_output} --route {review_route} --port {review_port}{_C.RESET}")
    print(f"    {_C.DIM}打开: http://localhost:{review_port}/{review_route}{_C.RESET}")
    print()
            
if __name__ == "__main__":
    main()
