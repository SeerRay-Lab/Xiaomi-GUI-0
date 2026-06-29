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
def evaluate_single_id(
    task_id: int,
    model_paths: List[str],
    summary_file: str = "rules/trajectory_summary_0515.json",
    human_eval_file: str = "rules/human_eval.csv",
    rules_dir: str = "rules",
    output_file: str = None
) -> pd.DataFrame:
    """
    评估单个ID在所有模型下的结果
    
    Args:
        task_id: 要评估的任务ID
        model_paths: 模型路径列表
        summary_file: summary文件路径
        human_eval_file: human_eval文件路径
        rules_dir: 规则文件目录
        output_file: 输出文件路径（可选）
    
    Returns:
        包含该ID在所有模型下结果的DataFrame
    """
    
    # 1. 加载summary数据，获取该ID的query
    print(f"加载summary数据，查找ID {task_id}...")
    id_to_query = load_summary_data(summary_file)
    
    if task_id not in id_to_query:
        print(f"错误: ID {task_id} 不在summary文件中")
        return None
    
    task_query = id_to_query[task_id]
    print(f"找到ID {task_id}: {task_query[:80]}...")
    
    # 2. 加载human_eval获取sid
    print("\n加载human_eval...")
    df_human = pd.read_csv(human_eval_file)
    df_human = df_human[['sid', 'query']].dropna()
    df_human['sid'] = df_human['sid'].astype(int)
    sid_map = dict(zip(df_human['query'], df_human['sid']))
    sid = sid_map.get(task_query, task_id)
    print(f"对应的sid: {sid}")
    
    # 3. 扫描所有模型路径，查找该query对应的轨迹
    print("\n扫描模型路径...")
    model_results = {}
    
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        print(f"\n检查模型: {model_name}")
        
        trajectories = scan_model_trajectories(model_path)
        
        # 查找匹配的轨迹
        found = False
        for folder, info in trajectories.items():
            if info['query'] == task_query:
                print(f"  找到匹配轨迹: {folder}")
                
                # 评估该轨迹
                eval_result = evaluate_trajectory_folder(
                    info['path'], 
                    task_id, 
                    rules_dir
                )
                
                model_results[model_name] = {
                    "folder": folder,
                    "path": info['path'],
                    "result": eval_result['result'],
                    "score": eval_result['score'],
                    "success": eval_result['success'],
                    "error": eval_result.get('error')
                }
                found = True
                break
        
        if not found:
            print(f"  未找到匹配轨迹")
            model_results[model_name] = {
                "folder": "",
                "path": "",
                "result": False,
                "score": 0.0,
                "success": False,
                "error": "未找到对应轨迹"
            }
    
    # 4. 构建结果DataFrame
    print("\n构建结果表格...")
    rows = []
    
    row = {
        "sid": sid,
        "id": task_id,
        "query": task_query
    }
    
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        if model_name in model_results:
            result = model_results[model_name]
            row[f"{model_name}_folder"] = result.get('folder', '')
            row[f"{model_name}_path"] = result.get('path', '')
            row[f"{model_name}_result"] = result.get('result', False)
            row[f"{model_name}_score"] = result.get('score', 0.0)
            if result.get('error'):
                row[f"{model_name}_error"] = result.get('error')
        else:
            row[f"{model_name}_folder"] = ""
            row[f"{model_name}_path"] = ""
            row[f"{model_name}_result"] = False
            row[f"{model_name}_score"] = 0.0
    
    rows.append(row)
    df = pd.DataFrame(rows)
    
    # 5. 调整列顺序
    cols = ['sid', 'id', 'query']
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        cols.extend([f"{model_name}_folder", f"{model_name}_path", f"{model_name}_result", f"{model_name}_score"])
    df = df[cols]
    
    # 6. 保存结果（可选）
    if output_file:
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        
        excel_file = f"{output_file}_id_{task_id}.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Results', index=False)
        print(f"\n✓ 结果已保存: {excel_file}")
        
        csv_file = f"{output_file}_id_{task_id}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"✓ CSV结果已保存: {csv_file}")
    
    # 7. 打印结果
    print("\n" + "="*100)
    print(f"ID {task_id} (sid {sid}) 在各模型下的结果")
    print("="*100)
    print(f"Query: {task_query}")
    print("-"*100)
    
    for model_path in model_paths:
        model_name = os.path.basename(model_path.rstrip('/'))
        result = df.iloc[0][f"{model_name}_result"]
        score = df.iloc[0][f"{model_name}_score"]
        folder = df.iloc[0][f"{model_name}_folder"]
        status = "✓" if result else "✗"
        print(f"{model_name:40} {status}  result={result}, score={score:.2f}, folder={folder}")
    
    return df


def batch_evaluate_single_ids(
    task_ids: List[int],
    model_paths: List[str],
    summary_file: str = "rules/trajectory_summary_0515.json",
    human_eval_file: str = "rules/human_eval.csv",
    rules_dir: str = "rules",
    output_file: str = None
) -> pd.DataFrame:
    """
    批量评估多个ID在所有模型下的结果
    
    Args:
        task_ids: 要评估的任务ID列表
        其他参数同上
    """
    all_results = []
    
    for task_id in task_ids:
        print(f"\n{'='*100}")
        print(f"处理 ID {task_id}")
        print(f"{'='*100}")
        
        df_single = evaluate_single_id(
            task_id=task_id,
            model_paths=model_paths,
            summary_file=summary_file,
            human_eval_file=human_eval_file,
            rules_dir=rules_dir,
            output_file=output_file  # 每个ID单独保存
        )
        
        if df_single is not None:
            all_results.append(df_single)
    
    if all_results:
        df_combined = pd.concat(all_results, ignore_index=True)
        
        # 保存合并结果
        if output_file:
            combined_file = f"{output_file}_combined.xlsx"
            with pd.ExcelWriter(combined_file, engine='openpyxl') as writer:
                df_combined.to_excel(writer, sheet_name='Results', index=False)
            print(f"\n✓ 合并结果已保存: {combined_file}")
        
        return df_combined
    else:
        return None

def evaluate_single_id_with_paths(
    task_id: int,
    model_paths_dict: Dict[str, str],  # {model_name: folder_path}
    summary_file: str = "rules/trajectory_summary_0515.json",
    human_eval_file: str = "rules/human_eval.csv",
    rules_dir: str = "rules",
) -> pd.DataFrame:
    """
    使用指定的path评估单个ID在所有模型下的结果（不保存文件）
    
    Args:
        task_id: 要评估的任务ID
        model_paths_dict: 模型名称到轨迹文件夹路径的映射
        summary_file: summary文件路径
        human_eval_file: human_eval文件路径
        rules_dir: 规则文件目录
    
    Returns:
        包含该ID在所有模型下结果的DataFrame
    """
    
    # 1. 加载summary数据，获取该ID的query
    print(f"加载summary数据，查找ID {task_id}...")
    id_to_query = load_summary_data(summary_file)
    
    if task_id not in id_to_query:
        print(f"错误: ID {task_id} 不在summary文件中")
        return None
    
    task_query = id_to_query[task_id]
    print(f"找到ID {task_id}: {task_query[:80]}...")
    
    # 2. 加载human_eval获取sid
    print("\n加载human_eval...")
    df_human = pd.read_csv(human_eval_file)
    df_human = df_human[['sid', 'query']].dropna()
    df_human['sid'] = df_human['sid'].astype(int)
    sid_map = dict(zip(df_human['query'], df_human['sid']))
    sid = sid_map.get(task_query, task_id)
    print(f"对应的sid: {sid}")
    
    # 3. 直接使用提供的路径进行评估
    print("\n开始评估...")
    model_results = {}
    
    for model_name, folder_path in model_paths_dict.items():
        print(f"\n{'='*80}")
        print(f"评估模型: {model_name}")
        print(f"路径: {folder_path}")
        print(f"{'='*80}")
        
        # 检查路径是否存在
        if not os.path.exists(folder_path):
            print(f"❌ 路径不存在")
            model_results[model_name] = {
                "folder": os.path.basename(folder_path),
                "path": folder_path,
                "result": False,
                "score": 0.0,
                "success": False,
                "error": "路径不存在",
                "details": []
            }
            continue
        
        # 检查task.json是否存在
        task_json_path = os.path.join(folder_path, "task.json")
        if not os.path.exists(task_json_path):
            print(f"❌ task.json不存在")
            model_results[model_name] = {
                "folder": os.path.basename(folder_path),
                "path": folder_path,
                "result": False,
                "score": 0.0,
                "success": False,
                "error": "task.json不存在",
                "details": []
            }
            continue
        
        # 评估该轨迹
        eval_result = evaluate_trajectory_folder(
            folder_path, 
            task_id, 
            rules_dir
        )
        
        model_results[model_name] = {
            "folder": os.path.basename(folder_path),
            "path": folder_path,
            "result": eval_result['result'],
            "score": eval_result['score'],
            "success": eval_result['success'],
            "error": eval_result.get('error'),
            "details": eval_result.get('details', [])
        }
        
        # 打印详细结果
        status = "✅ 成功" if eval_result['result'] else "❌ 失败"
        print(f"\n总体结果: {status}")
        print(f"总分: {eval_result['score']:.2f}")
        
        # 打印每个规则的详细信息
        if eval_result.get('details'):
            print(f"\n详细规则得分:")
            for detail in eval_result['details']:
                rule_status = "✓" if detail.get('satisfied') else "✗"
                print(f"  {rule_status} {detail.get('rule', '')[:60]}: {detail.get('score', 0):.2f}")
                if detail.get('evidence'):
                    evidence = detail.get('evidence', '')[:100]
                    print(f"     证据: {evidence}...")
        
        if eval_result.get('error'):
            print(f"\n错误信息: {eval_result['error']}")
    
    # 4. 构建结果DataFrame
    print("\n" + "="*100)
    print(f"ID {task_id} (sid {sid}) 在各模型下的结果汇总")
    print("="*100)
    print(f"Query: {task_query}")
    print("-"*100)
    
    rows = []
    row = {
        "sid": sid,
        "id": task_id,
        "query": task_query
    }
    
    for model_name in model_paths_dict.keys():
        
        if model_name in model_results:
            result = model_results[model_name]
            row[f"{model_name}_result"] = result.get('result', False)
            row[f"{model_name}_score"] = result.get('score', 0.0)
            
            # 打印汇总行
            status = "✅" if result['result'] else "❌"
            print(f"{model_name:40} {status}  得分: {result['score']:.2f}  文件夹: {result['folder']}")
        else:
            row[f"{model_name}_result"] = False
            row[f"{model_name}_score"] = 0.0
            print(f"{model_name:40} ❌  得分: 0.00  文件夹: 未找到")
    
    rows.append(row)
    df = pd.DataFrame(rows)
    
    # 打印统计
    print("\n" + "="*100)
    print("统计汇总")
    print("="*100)
    success_count = sum(1 for m in model_results.values() if m.get('result', False))
    total_count = len(model_paths_dict)
    avg_score = sum(m.get('score', 0) for m in model_results.values()) / total_count if total_count > 0 else 0
    print(f"成功模型数: {success_count}/{total_count}")
    print(f"平均得分: {avg_score:.3f}")
    print(f"成功率: {success_count/total_count*100:.1f}%")
    
    return df

paths_dict={18 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/1fde5761", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/26381f26", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/fa25732a", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/6be5f4e5", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/5d685896", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a6ccce10", "/main/guiagent/xiaoaidata/BMK/mai-ui/d34af8e5", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/4a4d2f13", "/main/guiagent/xiaoaidata/BMK/step-gui/60f7d06c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/bd069dee", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/3b302529", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/7622c96b"], 
1 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/485b20d4", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/8fc6688e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/8c69cece", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/0721257a", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/44ba1d92", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/5d1f502f", "/main/guiagent/xiaoaidata/BMK/mai-ui/e6c30f68", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/2062207b", "/main/guiagent/xiaoaidata/BMK/step-gui/c60990c8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/b08320a9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/34d16b74", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f61d55a0"], 
30 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/c57d13f7", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/36195d7c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/cfe54e65", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/fc534899", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/435e5f43", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/fa2d4663", "/main/guiagent/xiaoaidata/BMK/mai-ui/eb7a39e2", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/534dfb7e", "/main/guiagent/xiaoaidata/BMK/step-gui/908fc15d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/cab3afbe", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/fab7bbd7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/71f62e00"], 
4 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/1077db0b", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/1f53a766", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/96c4fcb0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/8575662e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/16dbb7f8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/fcdbe580", "/main/guiagent/xiaoaidata/BMK/mai-ui/64f30e90", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/424a3174", "/main/guiagent/xiaoaidata/BMK/step-gui/3d723853", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/8639d8d6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/332cf2ff", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f43eeac8"], 
3 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/daff79d5", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/de3f81c8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/2227de9e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/45223dc9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/9c8488b7", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/dd5f7459", "/main/guiagent/xiaoaidata/BMK/mai-ui/869c779d", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/e64d1356", "/main/guiagent/xiaoaidata/BMK/step-gui/bae952cf", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/c8b228f3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/f8a097d8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e843c0de"], 
76 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6546df29", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/0c635584", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/40dd8c11", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/cda8a53a", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/11a20fec", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/5034bbeb", "/main/guiagent/xiaoaidata/BMK/mai-ui/eff69eba", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/98398ccb", "/main/guiagent/xiaoaidata/BMK/step-gui/a6e5cb59", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e7c96e21", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/bd42745d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/19eb6be6"], 
35 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/55b9529d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/49899f89", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/73675bab", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/f32d3c27", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/9d4aa00f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/402f7b0a", "/main/guiagent/xiaoaidata/BMK/mai-ui/5d8e66e2", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/123044f2", "/main/guiagent/xiaoaidata/BMK/step-gui/fc44454c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/621ebfe2", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/c989aaf8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/64b25593"], 
43 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/b3ef70cd", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/23d401db", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/0f5f371c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/f9c36a79", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e57a937d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ce27f3d6", "/main/guiagent/xiaoaidata/BMK/mai-ui/20c2c48f", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/9b5b89e8", "/main/guiagent/xiaoaidata/BMK/step-gui/2ada873e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/9ac05a8a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2291a837", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/55540f0f"], 
66 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/8c43f355", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/fde4e8b1", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/61cfe89b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/19320f3f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/f8aa19e1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/46875e47", "/main/guiagent/xiaoaidata/BMK/mai-ui/6466f1d8", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/2ee44ddd", "/main/guiagent/xiaoaidata/BMK/step-gui/73a1b6e9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/c6eaf707", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/0d0dbc86", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/d30e0884"], 
62 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6c831e46", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a4f795df", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/d4c02543", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/a515af8c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/aa67d807", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/3400c36a", "/main/guiagent/xiaoaidata/BMK/mai-ui/8c60ea62", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/0d6c09d0", "/main/guiagent/xiaoaidata/BMK/step-gui/da193c78", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/17604c45", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/758feae4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/0ad439a8"], 
46 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/891bcbf0", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/7f7eceea", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ebb084ef", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d1e2c7db", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/1e15b437", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/598cdb45", "/main/guiagent/xiaoaidata/BMK/mai-ui/a86dbab6", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/08207c32", "/main/guiagent/xiaoaidata/BMK/step-gui/7871b1ec", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/de68bd18", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/0f876f82", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/00516354"], 
5 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0fd75ef9", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/ced87024", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/fdf8ec8c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/0f4dcc3f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/533d8a0f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/999297f1", "/main/guiagent/xiaoaidata/BMK/mai-ui/804ff3b5", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ac650f1c", "/main/guiagent/xiaoaidata/BMK/step-gui/7518cfd6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/41033516", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/8d6fc404", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/284a3bf3"], 
15 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/2b1da8ae", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/c5c1ce9b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3c8754a9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/7540498c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/50ea8ed8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/199c27ed", "/main/guiagent/xiaoaidata/BMK/mai-ui/df84fb5b", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/671b2d9e", "/main/guiagent/xiaoaidata/BMK/step-gui/3c3ab482", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/13178cdf", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/46f8b3f3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/cb7759a6"], 
17 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/76df786b", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/ed441a67", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/58397727", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d83a52af", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/0f112f3b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ae59f21f", "/main/guiagent/xiaoaidata/BMK/mai-ui/6635700e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c45fb373", "/main/guiagent/xiaoaidata/BMK/step-gui/d682f927", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/a9c861c5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/1c3b2a8e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/5275b4cd"], 
24 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/7ba9223e", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a891013d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/c40f605e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/826bdc6c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/132ecaf6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ac299c4e", "/main/guiagent/xiaoaidata/BMK/mai-ui/2361f1da", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/356f07f7", "/main/guiagent/xiaoaidata/BMK/step-gui/c7a380c3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/145ad3a1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2e77e716", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/1b2492ea"], 
2 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/f1cf9d3a", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/aa08c38c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/8e049eb4", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/85170246", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/c784fd96", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/d1df7437", "/main/guiagent/xiaoaidata/BMK/mai-ui/7dbaccc3", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5c19705e", "/main/guiagent/xiaoaidata/BMK/step-gui/5aa6d36b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/331a0dd4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/54c182f9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c2c91b1d"], 
31 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0bf58045", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/fbdcdec1", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ca0e00d5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/eed481e5", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7e656326", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/e5a76658", "/main/guiagent/xiaoaidata/BMK/mai-ui/91346915", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c4233cb5", "/main/guiagent/xiaoaidata/BMK/step-gui/c8cb3443", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/4ccd6fd9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/6e9d2c76", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/cccc44c6"], 
29 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/acd61c73", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/38633880", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/cd3640a2", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/079d455a", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/c2edc707", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/99c95857", "/main/guiagent/xiaoaidata/BMK/mai-ui/29935946", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/59c2f3bd", "/main/guiagent/xiaoaidata/BMK/step-gui/0413f439", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/b8314670", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/1b933fc3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/d4bbe41c"], 
32 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/5d570803", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/03283636", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/50148c28", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/20b7c94e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/5f688551", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4066d41e", "/main/guiagent/xiaoaidata/BMK/mai-ui/5f51e57a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c76d54c4", "/main/guiagent/xiaoaidata/BMK/step-gui/034e13ca", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e7b6323f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/31983f0d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e5095620"], 
12 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/31853dc3", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/9e7150e7", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/6ae201d5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/fd5bf8c9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/a59083cf", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4a5d7f54", "/main/guiagent/xiaoaidata/BMK/mai-ui/56d4eec0", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/59b23dd7", "/main/guiagent/xiaoaidata/BMK/step-gui/bd5c508e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/83d1f2c4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/4bc1f8ff", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/50a317c9"], 
84 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/a3fba0dd", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/32c127f9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/d17763f9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/939bc5af", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7ccd1d28", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/6880a019", "/main/guiagent/xiaoaidata/BMK/mai-ui/568ee990", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/542fe89d", "/main/guiagent/xiaoaidata/BMK/step-gui/77d32fe0", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/eaeaa6f3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/83237ab6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/671046ea"], 
7 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/2de71336", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/c80ddf38", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/7b90c0e7", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/c60a07dc", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/334cef2c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/7a07847e", "/main/guiagent/xiaoaidata/BMK/mai-ui/7943c1a4", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/51e56b76", "/main/guiagent/xiaoaidata/BMK/step-gui/6b249135", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e82de2aa", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2f3bc88d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e12a8ab8"], 
69 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/5a365845", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/2c8dcbac", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/636474b8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/20b4e45e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/1aefbf6e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/69d47a4b", "/main/guiagent/xiaoaidata/BMK/mai-ui/2f462e3a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/9f4923e2", "/main/guiagent/xiaoaidata/BMK/step-gui/f18ea76d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/eadf3963", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/cbcccb01", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2142e619"], 
50 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/965e17c5", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/37cbdd5e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/cc4cac2e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d0703cf1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e8d7383d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/c6d26761", "/main/guiagent/xiaoaidata/BMK/mai-ui/d84a5d5d", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/f0c772f0", "/main/guiagent/xiaoaidata/BMK/step-gui/beb7b9d7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/2e5369b3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/d0ce003f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c5dc0980"], 
72 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6900e1f1", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/e527c5f3", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/c0ad82aa", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/8f63cacc", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/5dd6ebf1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/2a0efd57", "/main/guiagent/xiaoaidata/BMK/mai-ui/76c162e6", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/de8dc505", "/main/guiagent/xiaoaidata/BMK/step-gui/850be92f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/7d6ca087", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/20452a7d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e785a872"], 
6 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/23786bad", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f553e84c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/6ceb1707", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/886f810b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/8b54752f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/3df1a1c5", "/main/guiagent/xiaoaidata/BMK/mai-ui/8bf7162e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/26f9c72c", "/main/guiagent/xiaoaidata/BMK/step-gui/063af9b1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/a5e6d6c5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/3b775bb5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/05967ff9"], 
19 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/80d47109", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/6c5d284e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/a72d37fe", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ec0229e6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/092e6db0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/e8de6d5a", "/main/guiagent/xiaoaidata/BMK/mai-ui/f403b3b2", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/fed08dc3", "/main/guiagent/xiaoaidata/BMK/step-gui/77160815", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/4520b9a6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/57283773", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/4b34e375"], 
22 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/687351a0", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a14d0fff", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/2ebf6d79", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/96d1b584", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/65458332", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/aae12a08", "/main/guiagent/xiaoaidata/BMK/mai-ui/c7246090", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c69f1a3d", "/main/guiagent/xiaoaidata/BMK/step-gui/58378550", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/edf6474b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/d3a1bd40", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/a9a355c4"], 
8 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/839561b9", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/c8d36137", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/d8c587f7", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/94734a36", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/3f0213a5", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/8fe2f019", "/main/guiagent/xiaoaidata/BMK/mai-ui/836d11d7", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/9004c8d9", "/main/guiagent/xiaoaidata/BMK/step-gui/4b11a242", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/90f5dba7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/86bc6bb2", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f7a25429"], 
11 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/aad1fb85", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/2a4d6aa3", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/04b8e050", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/c704435c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/f61563dd", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/505a1214", "/main/guiagent/xiaoaidata/BMK/mai-ui/112d5f18", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/b92efe2f", "/main/guiagent/xiaoaidata/BMK/step-gui/a04d935d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/4f3c4acf", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/3c0f0181", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/5f86a475"], 
82 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/b5f17027", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/08dc1e2c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/7e2cb143", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/e4ddf2af", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/43cf3b93", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/184437f8", "/main/guiagent/xiaoaidata/BMK/mai-ui/8e0bcc50", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/17f96840", "/main/guiagent/xiaoaidata/BMK/step-gui/5b957fd8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/6feb55cb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/24aa83f2", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/40299aa8"], 
67 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/91e48004", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/0ebafe17", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/274736e0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ba09b708", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/850fb173", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/489354db", "/main/guiagent/xiaoaidata/BMK/mai-ui/7fc4e7b6", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/d579aea1", "/main/guiagent/xiaoaidata/BMK/step-gui/bffe2ae5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/720658b1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/660be101", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/735d0488"], 
21 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/8cba1106", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/4d922ea9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/345c0032", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/f369cbff", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7b7bc3ff", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/b9fc5c73", "/main/guiagent/xiaoaidata/BMK/mai-ui/c70f21e4", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/1edfcdb1", "/main/guiagent/xiaoaidata/BMK/step-gui/bb47182d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/ef259de9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7df56644", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/880195a5"], 
25 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/04d72762", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f30dfa3d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/d69a17e2", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/b67ae7bf", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b79bc113", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/9eecf987", "/main/guiagent/xiaoaidata/BMK/mai-ui/315d7434", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/cc9592e9", "/main/guiagent/xiaoaidata/BMK/step-gui/89e5c7eb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/f85fb9f5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/be6bdd52", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/22951ae5"], 
94 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/779135d5", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a70c34cc", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/dcc0fb02", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ed181ad5", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/0efc9b44", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/f3b5abd0", "/main/guiagent/xiaoaidata/BMK/mai-ui/c92cc112", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/71c966bb", "/main/guiagent/xiaoaidata/BMK/step-gui/98c7bb09", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/998e238e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/db4247ff", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/367bb2ff"], 
41 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/740c63e8", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/538d98c1", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/87da6925", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/98272dc6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/a486839e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4c5e570c", "/main/guiagent/xiaoaidata/BMK/mai-ui/5a5a3e6a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ed44b477", "/main/guiagent/xiaoaidata/BMK/step-gui/60c8ffd7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/15291a88", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/a2bc184b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/280be076"], 
95 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0eea19d0", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/56aef810", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/273af9c3", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/6088f823", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/06c804b4", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/46b3e297", "/main/guiagent/xiaoaidata/BMK/mai-ui/9897c3c2", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/7d3c3479", "/main/guiagent/xiaoaidata/BMK/step-gui/c8bc6500", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/138016d4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/4165e219", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/bba98bee"], 
89 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6cb87496", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/5c5ba3c8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3dc42b90", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/df2b4e95", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/f53093a0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/de4f517e", "/main/guiagent/xiaoaidata/BMK/mai-ui/c05d3496", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ac6ef807", "/main/guiagent/xiaoaidata/BMK/step-gui/735d18ff", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/b30dfed1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/b298c6e1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c21a0d61"], 
33 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/ec91f2f9", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/9c1938ef", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/580b1c86", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/cb92e16e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/468aa4b6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/3384c77e", "/main/guiagent/xiaoaidata/BMK/mai-ui/e55afc85", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/cceae37e", "/main/guiagent/xiaoaidata/BMK/step-gui/85e0624f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/37b2aeb1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/27856c8f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/7b82ba77"], 
16 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/cc072f9e", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/46e2df44", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/16709796", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/a5f5fdd4", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/5af40806", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/79039842", "/main/guiagent/xiaoaidata/BMK/mai-ui/7cd8cf35", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/416ec80b", "/main/guiagent/xiaoaidata/BMK/step-gui/13e1ee55", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e7e2c670", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/aafab30b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/36afbf4e"], 
65 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/48281323", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/5117ab58", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/64c5bb27", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/065f5008", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/a7220577", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/f882e0e1", "/main/guiagent/xiaoaidata/BMK/mai-ui/e46966d0", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/503f2a72", "/main/guiagent/xiaoaidata/BMK/step-gui/f89e8c4e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/d4c93e61", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/32414ca7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/30950d77"], 
58 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/793a2b99", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/becc7f78", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/78332aba", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/2f7cb4fa", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/dbc8a863", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/8ca89d43", "/main/guiagent/xiaoaidata/BMK/mai-ui/a3df1ce3", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c55b2c5a", "/main/guiagent/xiaoaidata/BMK/step-gui/09ed658c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e0bdffc1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/ccca6fbe", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/3097e7c2"], 
45 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/8a0cad43", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a0a67343", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3c6c4c43", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/2939cff2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/09a9b165", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/f66d514b", "/main/guiagent/xiaoaidata/BMK/mai-ui/44bcfc8a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/cfaf8706", "/main/guiagent/xiaoaidata/BMK/step-gui/bb97afbe", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e51ba7ad", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/dd10a4a4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2bd07c2b"], 
48 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/31e0031e", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/12f78d30", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/51d1844a", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/3aa515ab", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e53986b1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/cc92b185", "/main/guiagent/xiaoaidata/BMK/mai-ui/576df685", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/e1ca243f", "/main/guiagent/xiaoaidata/BMK/step-gui/bf0e1aee", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/3e8c5b1e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/c64cc7f4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/fd97f5e7"], 
64 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/be233ee2", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/9996ff4b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/7325adf5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/28fe4d40", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7cdc5d7f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/bc679e87", "/main/guiagent/xiaoaidata/BMK/mai-ui/0f662bbb", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5b56d43e", "/main/guiagent/xiaoaidata/BMK/step-gui/ee1ef8f7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/1e2f87a9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/1db0dfc8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/9b7d4853"], 
81 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/9249778d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/d15082a0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3be33ef4", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/9ea25f1c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/98c23280", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4d5b824f", "/main/guiagent/xiaoaidata/BMK/mai-ui/85979117", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/da32341f", "/main/guiagent/xiaoaidata/BMK/step-gui/671d61ec", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/83fa1636", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/c48a6bbd", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2643e13e"], 
97 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/7392f70f", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/fe139463", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/a85df4bd", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/8cc95cc8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/8e881619", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/0dcb75ee", "/main/guiagent/xiaoaidata/BMK/mai-ui/e193d0ef", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c4ff1ee5", "/main/guiagent/xiaoaidata/BMK/step-gui/77c17454", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/49fb0c3f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/f0043b2c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/600da696"], 
39 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/ce9be2e3", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f593dfd6", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/954641f0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/cb0aa367", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/713ff6d8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/bba5673b", "/main/guiagent/xiaoaidata/BMK/mai-ui/99cd5c88", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5c50aa06", "/main/guiagent/xiaoaidata/BMK/step-gui/804f9eb7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/036d41be", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/d52aad31", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e1f7e5b1"], 
27 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/e9cf3c70", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/1a419260", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/e5a260fa", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/abfb417d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/1c3f21c7", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/d482d6e2", "/main/guiagent/xiaoaidata/BMK/mai-ui/18dbcbeb", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/99316c9c", "/main/guiagent/xiaoaidata/BMK/step-gui/cbdc1d03", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/a7856f34", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/3b9f1254", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/dc4657ff"], 
77 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0f7ffc56", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/cdcd3ead", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/a84de3c6", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/56b93637", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e947087f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/72e8d9f9", "/main/guiagent/xiaoaidata/BMK/mai-ui/da791306", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/4184e7b0", "/main/guiagent/xiaoaidata/BMK/step-gui/ec5b7b00", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/22e267c1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/feae9a6b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/3c49ee86"], 
52 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/50cf7444", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/304ce7f8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b506ead9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/94f86636", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/9b487952", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ad60fbbc", "/main/guiagent/xiaoaidata/BMK/mai-ui/9263e63b", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/1f86d189", "/main/guiagent/xiaoaidata/BMK/step-gui/51ab5bf1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/87659e92", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/3044a963", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/28f5385b"], 
68 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/c20cb69f", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/38fc0bb2", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/09229805", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/9811578a", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b276cbe3", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4eef188b", "/main/guiagent/xiaoaidata/BMK/mai-ui/6309854b", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/37d0fbdb", "/main/guiagent/xiaoaidata/BMK/step-gui/011e7b00", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/9f751918", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/c1515d80", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2c768cc1"], 
42 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/9ddb93b0", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/6f7b37a3", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/20dc6ad5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/fd6d3083", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/f89b42ee", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/9a5688dd", "/main/guiagent/xiaoaidata/BMK/mai-ui/864d8f6a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/70648218", "/main/guiagent/xiaoaidata/BMK/step-gui/08a36299", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/f249aab1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/35e7a65e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/b219090c"], 
38 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/f7d68159", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/39623c5f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/e30d6749", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/8a47ab45", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/edc3bc4d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/9aa6ab96", "/main/guiagent/xiaoaidata/BMK/mai-ui/f9be7d07", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/da55f1e5", "/main/guiagent/xiaoaidata/BMK/step-gui/e2a21311", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/f0f2756c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/c39a841f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2e6364f8"], 
96 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/149876f7", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/d7e6603f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ed8b5d1f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/630efe46", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b09bc4ae", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/6a5113ce", "/main/guiagent/xiaoaidata/BMK/mai-ui/ebb33c0f", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/c38f920a", "/main/guiagent/xiaoaidata/BMK/step-gui/69dae4f4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/bd1fbc13", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7de11b4d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f799cd03"], 
70 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/e218e05b", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/b69b5637", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/49a2b67f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d4d3bc7d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b00b2ced", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/42a9f5fd", "/main/guiagent/xiaoaidata/BMK/mai-ui/9bdaba44", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/899cd590", "/main/guiagent/xiaoaidata/BMK/step-gui/8e7b115b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/a1b8fbc3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/ed9a0fb7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/4c54118c"], 
80 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6c343585", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/2d0b1a5b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/029dea0a", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/4c15aefb", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/295f3679", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/35d3cb02", "/main/guiagent/xiaoaidata/BMK/mai-ui/49c8aded", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/436375b0", "/main/guiagent/xiaoaidata/BMK/step-gui/58e60de2", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/d37a6e0a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/a73a68f4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/d152a6fa"], 
78 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0767aa47", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/6bcdd0d1", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/2e837a56", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/1392717c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/af4e4fd2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/2d4ed123", "/main/guiagent/xiaoaidata/BMK/mai-ui/896c6882", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/31db8b51", "/main/guiagent/xiaoaidata/BMK/step-gui/d818994f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/cbfc350a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/fc1da573", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/feff2e30"], 
10 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d09cbc60", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/bf5fdee0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/03601ed6", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/5cc095dd", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7ddf10f2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/6ba8c44a", "/main/guiagent/xiaoaidata/BMK/mai-ui/9be8a767", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/d5ba10ae", "/main/guiagent/xiaoaidata/BMK/step-gui/0087e4f6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/3ad00e54", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/664a5952", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/10935aa8"], 
56 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/1d4c343d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/716c305d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b97a0308", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/7a1102c8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/90a700ee", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/5ef2df82", "/main/guiagent/xiaoaidata/BMK/mai-ui/10e6e6a7", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/93911c13", "/main/guiagent/xiaoaidata/BMK/step-gui/2ed43e88", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/7a6c569e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/72d47cec", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/3306cff2"], 
55 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/67aaacc4", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/88927f5e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/c858c05b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/e952c5fa", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e62469ea", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/b533d69a", "/main/guiagent/xiaoaidata/BMK/mai-ui/970451dd", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/4d87b4a4", "/main/guiagent/xiaoaidata/BMK/step-gui/8493c028", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/d72d3852", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/4dac3dc8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f1309538"], 
54 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/0d6a3ebc", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/3867164a", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/2e5c2979", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/a0076fd9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/19503e8c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ce509f61", "/main/guiagent/xiaoaidata/BMK/mai-ui/71814a30", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/426b718d", "/main/guiagent/xiaoaidata/BMK/step-gui/fc2ade83", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/44c3a5fb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/ba364ed2", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/146b8355"], 
37 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/017abff6", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/0f10b98e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/3421e07e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/8f8c1a30", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b7125967", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/7204554e", "/main/guiagent/xiaoaidata/BMK/mai-ui/e4b96c6e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/8c545316", "/main/guiagent/xiaoaidata/BMK/step-gui/a3d82b51", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/61061b6f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/0e77f7a8", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c6effd9d"], 
60 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/3bab7b49", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/63119e9f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/e9c9b150", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/53019faa", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/3028a8c9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/1f7ac1b8", "/main/guiagent/xiaoaidata/BMK/mai-ui/ed9017e6", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/df0797b6", "/main/guiagent/xiaoaidata/BMK/step-gui/b90f7889", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/1c7f1a6d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2bb4db14", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/8da5e0d4"], 
90 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/35cbb8f1", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/fb17ef48", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/1ca4a348", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/9608e2e1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b5dc8edc", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/622a495f", "/main/guiagent/xiaoaidata/BMK/mai-ui/47cc96b7", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/61d9c0d3", "/main/guiagent/xiaoaidata/BMK/step-gui/31b8e36e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/6e30dcf9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/22ec0960", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/bdbc57bf"], 
85 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/3e9e7822", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/360c9054", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/0e8e07e2", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/beabef58", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/19f87794", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/9af72a05", "/main/guiagent/xiaoaidata/BMK/mai-ui/aa2bcf2e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/4662c2a5", "/main/guiagent/xiaoaidata/BMK/step-gui/0f753f16", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e58e4fbd", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/0bcaa764", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/311d9411"], 
61 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/e03db4e1", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f7c63655", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/65689725", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d9c14a6a", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/412e84dc", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/c094a981", "/main/guiagent/xiaoaidata/BMK/mai-ui/efb63005", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/49c95965", "/main/guiagent/xiaoaidata/BMK/step-gui/261977c7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/3dfa6914", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/ab7fd001", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/9d5de2f8"], 
34 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/212172bd", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f3012221", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/76b0b930", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/83943a46", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/0cc30f3e", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ec8e0f57", "/main/guiagent/xiaoaidata/BMK/mai-ui/548ff314", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/8c04190b", "/main/guiagent/xiaoaidata/BMK/step-gui/ffd7483f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e137df5b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7ea4b1c3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/4e245934"], 
13 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/92f45478", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/94794235", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/e390ce41", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/c711a464", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e0b9111c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/6a8012ad", "/main/guiagent/xiaoaidata/BMK/mai-ui/2a001e62", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/67d1a30a", "/main/guiagent/xiaoaidata/BMK/step-gui/b6773356", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/9289b368", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/cf5b4423", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/0c1f102b"], 
26 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/1d4bda9d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/db06065c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/4ee3df9c", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/a207ebe8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/8a2f5a39", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/bcf4b9f9", "/main/guiagent/xiaoaidata/BMK/mai-ui/84edaa07", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/28965144", "/main/guiagent/xiaoaidata/BMK/step-gui/878be902", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/54ce7517", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/f4f8ada6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/2448f9a9"], 
88 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/f98fe22b", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a18b0875", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b4f51516", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/748063a0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/accb058c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/4bfa787a", "/main/guiagent/xiaoaidata/BMK/mai-ui/f64dd754", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ce6d553f", "/main/guiagent/xiaoaidata/BMK/step-gui/5563a66d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/59cefe00", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/afd3c36a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/3cdeefb4"], 
100 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/dbf059f4", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/cbbd8ae6", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/cfdc954d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/71fd3053", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/da0c5f03", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/d41c6f3a", "/main/guiagent/xiaoaidata/BMK/mai-ui/ac444c26", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/fab302b6", "/main/guiagent/xiaoaidata/BMK/step-gui/f2206990", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/febec4e5", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/62644038", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/f756b3ed"], 
87 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d730a43f", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/cc076746", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/fe8f55b5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/814108c2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/7da77bf9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/bc2af583", "/main/guiagent/xiaoaidata/BMK/mai-ui/eb64dbd4", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/7c5f921a", "/main/guiagent/xiaoaidata/BMK/step-gui/734047eb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e303f70d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/56239319", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/547527fd"], 
93 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/80435e84", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/bbbf5497", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/98347e63", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d0cab620", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/c31fbbe3", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/3a55a7c5", "/main/guiagent/xiaoaidata/BMK/mai-ui/d0d8cce8", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/e55543bd", "/main/guiagent/xiaoaidata/BMK/step-gui/fa865154", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/4227ca3c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/91f813bc", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/e72e7ce7"], 
23 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d5b57946", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/d1c266e9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/d3755062", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/cd5e140c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/8f0561b6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/faae166e", "/main/guiagent/xiaoaidata/BMK/mai-ui/3aca2363", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/f43e6463", "/main/guiagent/xiaoaidata/BMK/step-gui/e1c8b7e0", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/fa704bf1", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/aecd6f56", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/8c646739"], 
40 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/c0cb372e", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f954a2b6", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ad45efee", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ec76dbbd", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/961332d9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/c8c1d2ee", "/main/guiagent/xiaoaidata/BMK/mai-ui/cefd6a8a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/a6ff4131", "/main/guiagent/xiaoaidata/BMK/step-gui/5418c5f3", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/9553820c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/b3a6df56", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/91ae2cfd"], 
53 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/35ebd5b0", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/76f50a81", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/4f78ab43", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/a9837bc0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/b7161d83", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/eecf41c0", "/main/guiagent/xiaoaidata/BMK/mai-ui/4e6682e3", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5cb86e5b", "/main/guiagent/xiaoaidata/BMK/step-gui/e44476ed", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/2d3a2f07", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/457bc375", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/0738fb90"], 
74 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/de67072d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/3447e9b7", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b9e07f3d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/6ed9546b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/d02aa0bd", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/92bb3465", "/main/guiagent/xiaoaidata/BMK/mai-ui/1647c97b", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/663c2cf6", "/main/guiagent/xiaoaidata/BMK/step-gui/ffe4325f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/5a8ea5ce", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/a5e545ae", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/550a5fe5"], 
63 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/91eeff95", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/c6dad23e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/19eab925", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/f0319294", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/e4273ca0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/28d830a1", "/main/guiagent/xiaoaidata/BMK/mai-ui/aee268e1", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/cfe58e27", "/main/guiagent/xiaoaidata/BMK/step-gui/ae57791e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/e6db414d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/f34f20ef", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/ef87bd38"], 
92 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/03b84a43", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/83755b3f", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ad454d62", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/0862883b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/28f761ca", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/88b265a2", "/main/guiagent/xiaoaidata/BMK/mai-ui/b5ce956c", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/3291f420", "/main/guiagent/xiaoaidata/BMK/step-gui/26ac8806", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/065cce28", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7cd0a02f", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/54f5679e"], 
99 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/cc52e4f8", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/ddfad1c8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/6c9f71b5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/fe02159f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/5df83e7b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/8665c818", "/main/guiagent/xiaoaidata/BMK/mai-ui/37310812", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/2175f437", "/main/guiagent/xiaoaidata/BMK/step-gui/c35ccd3d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/5b4508ef", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/716a724e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/ed7a7deb"], 
73 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/513bf2a2", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/52e8cec5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/5fa9a195", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/1177223f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/13c7b11d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/e6987e64", "/main/guiagent/xiaoaidata/BMK/mai-ui/e374a5fc", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/3fa2c80b", "/main/guiagent/xiaoaidata/BMK/step-gui/e3199456", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/23d79959", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/fe6bab21", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c9158720"], 
28 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/67e833f6", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/bc3fb429", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b56d10e5", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/bcaa39cb", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/499652c9", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/866d404f", "/main/guiagent/xiaoaidata/BMK/mai-ui/7b6762be", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/a0eca956", "/main/guiagent/xiaoaidata/BMK/step-gui/df931385", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/dbbe3abb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/01632016", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/1a7bb4b2"], 
14 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d0efd57e", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/234e0eba", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/a67df70e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/59750788", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/ce2f7fff", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a6c9f9df", "/main/guiagent/xiaoaidata/BMK/mai-ui/93b01b3e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/027b545e", "/main/guiagent/xiaoaidata/BMK/step-gui/a3269204", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/9234aba4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2f19dc24", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/320ef76f"], 
9 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/48b0b873", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/c28f610d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/e43fb020", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/80fc6fd3", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/0bee2827", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/11bdd05f", "/main/guiagent/xiaoaidata/BMK/mai-ui/884f837e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/72c5ac58", "/main/guiagent/xiaoaidata/BMK/step-gui/0fe2e7ce", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/892ddb2e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/532b9010", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/927c3a54"], 
44 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/75166477", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/e9c5609e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/169c1b90", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/9a51c6ce", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/4e1b1cca", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/3dc5b72d", "/main/guiagent/xiaoaidata/BMK/mai-ui/b4ba0fdf", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/80f6a03a", "/main/guiagent/xiaoaidata/BMK/step-gui/4e951450", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/58eb06ce", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/26904938", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/c0d18594"], 
49 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/a5d9a867", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/79504390", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/ac1ae381", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/d5ad1743", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/4c6b20ba", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/d10b68f7", "/main/guiagent/xiaoaidata/BMK/mai-ui/cfd30199", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ba78434d", "/main/guiagent/xiaoaidata/BMK/step-gui/2b9a6e10", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/17ccc71a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/fe8d2c2c", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/bee910a8"], 
91 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/92882aad", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/eafcd97d", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/9baecf4e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/42f052f7", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/a005d9c2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a03a5c71", "/main/guiagent/xiaoaidata/BMK/mai-ui/0ef7e512", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/655d7619", "/main/guiagent/xiaoaidata/BMK/step-gui/7ccb2249", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/ed6d1062", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/e89bf10d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/a4a9aa71"], 
57 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d9ce7cce", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/248113ec", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/1447c3d0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/bc92ef85", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/34e691cd", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/87f6a4f1", "/main/guiagent/xiaoaidata/BMK/mai-ui/d08966f3", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/b6f1a0db", "/main/guiagent/xiaoaidata/BMK/step-gui/396a29aa", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/34393779", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/13871751", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/43b08f32"], 
59 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/7973e716", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/23879a95", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/5d97fe59", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/1d4734e7", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/116dc1f8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/0d79b5ee", "/main/guiagent/xiaoaidata/BMK/mai-ui/197f7e27", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/4476164b", "/main/guiagent/xiaoaidata/BMK/step-gui/c9d8e5d9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/b2e1681e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/788d44b4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/b74230f4"], 
75 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/94759a88", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/628d9b2b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/df2df75e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/c2e3e85b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/d08579c8", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/04a279ab", "/main/guiagent/xiaoaidata/BMK/mai-ui/c1ab9978", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/cf66b4a8", "/main/guiagent/xiaoaidata/BMK/step-gui/a3691d92", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/b308b9ba", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/807b944d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/d068274d"], 
71 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/ee03a71d", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/61de3429", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/7d08e63a", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ae55090f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/6bed6ffa", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/ed4ba7a4", "/main/guiagent/xiaoaidata/BMK/mai-ui/f17f0909", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/562c69c9", "/main/guiagent/xiaoaidata/BMK/step-gui/e33b49d0", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/2a729d6a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/2c9dd1ba", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/51b509a6"], 
83 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6616bec2", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/5641574b", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/bbfc66e0", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/c12d65d2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/76c3561f", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/5b700ab1", "/main/guiagent/xiaoaidata/BMK/mai-ui/05029610", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/ce992c4d", "/main/guiagent/xiaoaidata/BMK/step-gui/f173bc6e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/4ba9b71d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7a04c575", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/3d6e4cba"], 
51 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/8d22e1f3", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/5d9d0fa9", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/c012e718", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/b60fb65d", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/91611ee4", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/19782096", "/main/guiagent/xiaoaidata/BMK/mai-ui/4a20c6f6", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/74899a8c", "/main/guiagent/xiaoaidata/BMK/step-gui/ee598523", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/3929d661", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/ee722a96", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/098a1484"], 
98 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/4337c072", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/727a5332", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/467ee532", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/26b7c79c", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/ee43caa6", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/5790b355", "/main/guiagent/xiaoaidata/BMK/mai-ui/b4a359ff", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/34c03de9", "/main/guiagent/xiaoaidata/BMK/step-gui/4182d80b", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/51438afa", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/f1711659", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/17fcb0a8"], 
36 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/34ff1033", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/28e94fbd", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/b262d87e", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/05276aa0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/22c728c0", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a59f590b", "/main/guiagent/xiaoaidata/BMK/mai-ui/3792cbac", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/775d42a1", "/main/guiagent/xiaoaidata/BMK/step-gui/0ecbee87", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/a20c2ea0", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/7a441093", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/9fd4ed49"], 
79 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/db859ef9", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/48763a57", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/7401b898", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/382292ae", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/4f6a68a2", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/35f34138", "/main/guiagent/xiaoaidata/BMK/mai-ui/b9b307f5", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/1ed6e550", "/main/guiagent/xiaoaidata/BMK/step-gui/94026fc7", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/76b07912", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/0b7f9947", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/873b5629"], 
20 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/d5d821cd", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/3d7a6a26", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/26bffab8", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/48699c50", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/6bc6545b", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a2c87c1f", "/main/guiagent/xiaoaidata/BMK/mai-ui/819b2f9a", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/f7ad49bd", "/main/guiagent/xiaoaidata/BMK/step-gui/0c023d9a", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/7d3090d4", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/15341820", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/332de863"], 
47 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/6091d424", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/f7b82933", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/118f4b88", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/17a39b28", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/8edc19a4", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/6d8333cd", "/main/guiagent/xiaoaidata/BMK/mai-ui/fad08d7e", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5dcc0e46", "/main/guiagent/xiaoaidata/BMK/step-gui/ae6c5fac", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/c57d2550", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/8a4543d6", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/539568ea"], 
86 :  ["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/f7d31edd", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a9e15578", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/a77a89dd", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/b45d99ca", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/c9d327c1", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/a53d367e", "/main/guiagent/xiaoaidata/BMK/mai-ui/40acc883", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/5c1ed6c3", "/main/guiagent/xiaoaidata/BMK/step-gui/db0c225d", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/35910ecb", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/371e7fc9", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/46e3b6f1"]}


if __name__ == "__main__":
    
    # model_paths = [
    #     "/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview",
    # ]
    model_paths = [
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview",
        "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7",
        "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215",
        "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228",
        "/main/guiagent/xiaoaidata/BMK/mai-ui",
        "/main/guiagent/xiaoaidata/BMK/autoglm-phone",
        "/main/guiagent/xiaoaidata/BMK/step-gui",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2",
        "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3",
    ]
    
    # df = batch_evaluate_models(
    #     model_paths=model_paths,
    #     human_eval_file="rules/human_eval.csv",  # 新增这个参数
    #     summary_file="rules/trajectory_summary_0515.json",
    #     rules_dir="rules",
    #     output_file="rules/rules_eval_0529"
    # )

    # # 评估单个ID
    # df = evaluate_single_id(
    #     task_id=1,
    #     model_paths=model_paths,
    #     #output_file="rules/single_id_result"
    # )
    # # 打印结果
    # if df is not None:
    #     print("\n" + "="*100)
    #     print("最终结果汇总")
    #     print("="*100)
    #     print(df.to_string())

    # # 评估多个ID
    # df = batch_evaluate_single_ids(
    #     task_ids=[2, 3, 4, 5, 6],
    #     model_paths=model_paths,
    #     #output_file="rules/multi_id_result"
    # )
    # # 打印结果
    # if df is not None:
    #     print("\n" + "="*100)
    #     print("最终结果汇总")
    #     print("="*100)
    #     print(df.to_string())
    
    # model_paths_dict = {
    #     "gemini-3.1-pro-preview": "/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/05276aa0",
    #     "gemini-3.1-flash-lite-preview": "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/05276aa0",
    #     "claude-opus-4-7": "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/05276aa0",
    #     "claude-opus-4-6": "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/05276aa0",
    #     "doubao-seed-2-0-pro-260215": "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/05276aa0",
    #     "doubao-seed-1-8-251228": "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/05276aa0",
    #     "mai-ui": "/main/guiagent/xiaoaidata/BMK/mai-ui/05276aa0",
    #     "autoglm-phone": "/main/guiagent/xiaoaidata/BMK/autoglm-phone/05276aa0",
    #     "step-gui": "/main/guiagent/xiaoaidata/BMK/step-gui/05276aa0",
    #     "MiGuiAgent-1": "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/05276aa0",
    #     "MiGuiAgent-2": "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/05276aa0",
    #     "MiGuiAgent-3": "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/05276aa0",
    # }
    
    name_list=["gemini-3.1-pro-preview","gemini-3.1-flash-lite-preview","claude-opus-4-7","claude-opus-4-6","doubao-seed-2-0-pro-260215","doubao-seed-1-8-251228",
    "mai-ui","autoglm-phone","step-gui","MiGuiAgent-1","MiGuiAgent-2","MiGuiAgent-3"]
    #paths_list=["/main/guiagent/xiaoaidata/BMK/gemini-3.1-pro-preview/779135d5", "/main/guiagent/xiaoaidata/BMK/gemini-3.1-flash-lite-preview/a70c34cc", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-7/dcc0fb02", "/main/guiagent/xiaoaidata/BMK/claude-opus-4-6/ed181ad5", "/main/guiagent/xiaoaidata/BMK/doubao-seed-2-0-pro-260215/0efc9b44", "/main/guiagent/xiaoaidata/BMK/doubao-seed-1-8-251228/f3b5abd0", "/main/guiagent/xiaoaidata/BMK/mai-ui/c92cc112", "/main/guiagent/xiaoaidata/BMK/autoglm-phone/71c966bb", "/main/guiagent/xiaoaidata/BMK/step-gui/98c7bb09", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-1/998e238e", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-2/db4247ff", "/main/guiagent/xiaoaidata/BMK/MiGuiAgent-3/367bb2ff",
    index=86
    paths_list=paths_dict[index]    
    model_paths_dict={}
    for idx in range(len(name_list)):
        model_paths_dict[name_list[idx]]=paths_list[idx]


    # 评估ID 36
    df = evaluate_single_id_with_paths(
        task_id=index,
        model_paths_dict=model_paths_dict,
    )
    
    # 如果需要查看DataFrame内容
    print("\n" + "="*100)
    print("DataFrame格式的结果")
    print("="*100)
    print(df.T)  # 转置显示，更方便查看

    import subprocess
    # 要下载的序号（从0开始，0是第一个）
    index_list=[6,7,8]
    paths = [paths_list[i] for i in index_list]
    print("index_list",index_list)
    print('paths',paths)
    remote_paths = ' '.join(paths)
    cmd = f'scp -r {remote_paths} wuqinzhuo@10.220.181.245:"D:/code/claude/BMK/sample/"'
    subprocess.run(cmd, shell=True)