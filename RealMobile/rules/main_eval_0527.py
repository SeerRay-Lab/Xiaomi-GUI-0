import json
import os
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from datetime import datetime
from tqdm import tqdm
from difflib import SequenceMatcher

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_rule_module(rule_id: int, rules_dir: str = "rules"):
    """动态加载指定ID的规则模块"""
    rule_file = os.path.join(rules_dir, f"{rule_id}.py")
    
    if not os.path.exists(rule_file):
        raise FileNotFoundError(f"规则文件不存在: {rule_file}")
    
    spec = importlib.util.spec_from_file_location(f"rule_{rule_id}", rule_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    return module

def normalize_text(text: str) -> str:
    """规范化文本用于比较"""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text

def load_summary_data(json_file: str = "rules/trajectory_summary_0515.json") -> Dict[int, str]:
    """
    加载summary文件中的数字ID的query（过滤掉a_开头的ID）
    
    Returns:
        {id: query} 字典，只包含数字ID
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        trajectories = data.get('trajectories', data.get('data', []))
    elif isinstance(data, list):
        trajectories = data
    else:
        raise ValueError(f"无法解析JSON文件格式")
    
    id_to_query = {}
    
    for item in trajectories:
        qid = item.get('id')
        query = normalize_text(item.get('query', ''))
        
        # 只处理数字ID（过滤掉a_开头的）
        if qid and query and isinstance(qid, int):
            id_to_query[qid] = query
    
    print(f"加载了 {len(id_to_query)} 个数字ID的query (ID范围: {min(id_to_query.keys())}-{max(id_to_query.keys())})")
    
    return id_to_query

def load_human_eval_order(csv_file: str = "rules/human_eval.csv") -> pd.DataFrame:
    """加载human_eval.csv获取sid和query的对应关系及顺序"""
    df = pd.read_csv(csv_file)
    order_df = df[['sid', 'query']].dropna().copy()
    order_df['sid'] = order_df['sid'].astype(int)
    print(f"加载了 {len(order_df)} 个任务顺序 (sid 1-{order_df['sid'].max()})")
    return order_df

def scan_model_trajectories(model_base_path: str) -> Dict[str, Dict[str, str]]:
    """
    扫描模型路径下的所有轨迹文件夹
    
    Returns:
        字典: {folder_name: {"path": full_path, "query": query_from_task_json}}
    """
    trajectories = {}
    
    if not os.path.exists(model_base_path):
        print(f"警告: 路径不存在 {model_base_path}")
        return trajectories
    
    for folder_name in os.listdir(model_base_path):
        folder_path = os.path.join(model_base_path, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
        
        task_json_path = os.path.join(folder_path, "task.json")
        if not os.path.exists(task_json_path):
            continue
        
        try:
            with open(task_json_path, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            query = normalize_text(task_data.get('query', ''))
            if query:
                trajectories[folder_name] = {
                    "path": folder_path,
                    "query": query
                }
        except Exception as e:
            print(f"  警告: 无法读取 {task_json_path}: {e}")
            continue
    
    return trajectories

def evaluate_trajectory_folder(folder_path: str, rule_id: int, rules_dir: str = "rules") -> Dict[str, Any]:
    """
    评估单个轨迹文件夹
    """
    try:
        rule_module = load_rule_module(rule_id, rules_dir)
        
        if hasattr(rule_module, 'evaluate_trajectory'):
            result = rule_module.evaluate_trajectory(path=folder_path)
        else:
            raise AttributeError(f"规则模块 {rule_id}.py 中没有 evaluate_trajectory 函数")
        
        score = result.get('total_score', 0)
        is_success = (score >= 1.0)
        
        return {
            "success": True,
            "score": score,
            "result": is_success,
            "details": result.get('details', []),
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "score": 0.0,
            "result": False
        }

def batch_evaluate_models(
    model_paths: List[str],
    summary_file: str = "rules/trajectory_summary_0515.json",
    human_eval_file: str = "rules/human_eval.csv",
    rules_dir: str = "rules",
    output_file: str = None
) -> pd.DataFrame:
    """
    批量评估多个模型路径下的所有轨迹
    先按id正常评测，最后按human_eval.csv中的query顺序输出
    """
    
    # 1. 加载summary数据（只包含数字ID）
    print("加载summary数据...")
    id_to_query = load_summary_data(summary_file)
    print(f"  需要评估的任务ID: {sorted(id_to_query.keys())}")
    
    # 2. 扫描所有模型路径
    print("\n扫描模型路径...")
    model_trajectories = {}
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        trajectories = scan_model_trajectories(model_path)
        model_trajectories[model_name] = trajectories
        print(f"  {model_name}: {len(trajectories)} 个轨迹文件夹")
    
    # 3. 建立query到模型信息的映射（一个query对应多个模型）
    print("\n建立query映射...")
    from collections import defaultdict
    query_to_models = defaultdict(dict)  # {query: {model_name: {folder, path}}}
    
    for model_name, trajectories in model_trajectories.items():
        for folder, info in trajectories.items():
            query = info['query']
            query_to_models[query][model_name] = {
                "folder": folder,
                "path": info['path']
            }
    
    # 4. 按id评估每个任务
    print("\n开始评估...")
    all_results = {}  # {id: {model_name: {result, score}}}
    
    for task_id, task_query in tqdm(id_to_query.items(), desc="评估进度"):
        all_results[task_id] = {
            "id": task_id,
            "query": task_query,
            "models": {}
        }
        
        # 查找该query对应的所有模型
        if task_query in query_to_models:
            for model_name, model_info in query_to_models[task_query].items():
                eval_result = evaluate_trajectory_folder(
                    model_info['path'], 
                    task_id, 
                    rules_dir
                )
                all_results[task_id]["models"][model_name] = {
                    "folder": model_info['folder'],
                    "path": model_info['path'],
                    "result": eval_result['result'],
                    "score": eval_result['score']
                }
        else:
            # 尝试模糊匹配
            best_match = None
            best_ratio = 0
            for q, models in query_to_models.items():
                ratio = SequenceMatcher(None, task_query, q).ratio()
                if ratio > best_ratio and ratio > 0.95:
                    best_ratio = ratio
                    best_match = (q, models)
            
            if best_match:
                q, models = best_match
                print(f"  模糊匹配: ID {task_id} (相似度 {best_ratio:.3f})")
                for model_name, model_info in models.items():
                    eval_result = evaluate_trajectory_folder(
                        model_info['path'], 
                        task_id, 
                        rules_dir
                    )
                    all_results[task_id]["models"][model_name] = {
                        "folder": model_info['folder'],
                        "path": model_info['path'],
                        "result": eval_result['result'],
                        "score": eval_result['score']
                    }
            else:
                print(f"  未匹配: ID {task_id}")
    
    # 5. 构建DataFrame（按id排序）
    print("\n构建结果表格...")
    rows = []
    for task_id in sorted(all_results.keys()):
        task_data = all_results[task_id]
        row = {
            "id": task_id,
            "query": task_data['query']
        }
        
        for model_path in model_paths:
            model_name = os.path.basename(model_path.rstrip('/'))
            if model_name in task_data['models']:
                model_info = task_data['models'][model_name]
                row[f"{model_name}_folder"] = model_info.get('folder', '')      # 添加folder
                row[f"{model_name}_path"] = model_info.get('path', '')          # 添加path
                row[f"{model_name}_result"] = model_info.get('result', False)
                row[f"{model_name}_score"] = model_info.get('score', 0.0)
            else:
                row[f"{model_name}_folder"] = ""      # 添加folder
                row[f"{model_name}_path"] = ""        # 添加path
                row[f"{model_name}_result"] = False
                row[f"{model_name}_score"] = 0.0
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # 6. 按照human_eval.csv的query顺序重新排列
    print("\n按human_eval顺序重排...")
    df_human = pd.read_csv(human_eval_file)
    df_human = df_human[['sid', 'query']].dropna()
    df_human['sid'] = df_human['sid'].astype(int)
    
    # 添加sid列
    sid_map = dict(zip(df_human['query'], df_human['sid']))
    df['sid'] = df['query'].map(sid_map)
    
    # 按human_eval的query顺序重排
    df = df.set_index('query').loc[df_human['query']].reset_index()
    
    # 调整列顺序：sid, id, query, 然后是各模型的 folder, path, result, score
    cols = ['sid', 'id', 'query']
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        cols.extend([f"{model_name}_folder", f"{model_name}_path", f"{model_name}_result", f"{model_name}_score"])
    df = df[cols]
    # 7. 保存结果
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"results/model_comparison_{timestamp}"
    
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else "results", exist_ok=True)
    
    # 保存Excel
    excel_file = f"{output_file}.xlsx"
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Results', index=False)
        
        # 统计汇总
        summary_data = []
        for model_path in model_paths:
            model_name = os.path.basename(model_path.rstrip('/'))
            if f"{model_name}_result" in df.columns:
                success_count = df[f"{model_name}_result"].sum()
                total_count = len(df)
                avg_score = df[f"{model_name}_score"].mean()
                summary_data.append({
                    "Model": model_name,
                    "Total Tasks": total_count,
                    "Success Count": success_count,
                    "Success Rate": f"{success_count/total_count*100:.2f}%",
                    "Average Score": f"{avg_score:.3f}"
                })
        
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"\n✓ Excel结果已保存: {excel_file}")
    
    # 保存CSV
    csv_file = f"{output_file}.csv"
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"✓ CSV结果已保存: {csv_file}")
    
    # 打印统计
    print("\n" + "="*100)
    print("统计汇总")
    print("="*100)
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        if f"{model_name}_result" in df.columns:
            success_count = df[f"{model_name}_result"].sum()
            total_count = len(df)
            print(f"{model_name}: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    return df

if __name__ == "__main__":
    
    # model_paths = [
    #     "/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview",
    # ]
    model_paths = [
        "/main/guiagent/xiaoaidata/BMK/mai-ui",
        "/main/guiagent/xiaoaidata/BMK/autoglm-phone",
        "/main/guiagent/xiaoaidata/BMK/step-gui",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3",
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview",
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228",
    ]
    
    df = batch_evaluate_models(
        model_paths=model_paths,
        human_eval_file="rules/human_eval.csv",  # 新增这个参数
        summary_file="rules/trajectory_summary_0515.json",
        rules_dir="rules",
        output_file="rules/rules_eval_0618"
    )