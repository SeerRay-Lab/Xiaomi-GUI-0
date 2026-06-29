import os
import json
from pathlib import Path
import shutil

def extract_trajectory_info(base_dir, root_dir=None):
    """
    遍历目录，提取所有task.json中的query信息（过滤is_delete=True的）
    
    Args:
        base_dir: 基础目录路径，例如 "BMK/2026-04-29"
        root_dir: 相对路径的根目录，如果为None则使用base_dir的父目录的父目录
    
    Returns:
        list: 包含所有轨迹信息的列表
    """
    results = []
    id_counter = 1
    
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误：目录 {base_dir} 不存在")
        return results
    
    # 确定相对路径的根目录
    if root_dir is None:
        # 默认使用包含BMK的目录作为根目录
        # 假设路径是 .../BMK/2026-04-29，那么根目录就是 .../
        root_path = base_path.parent.parent
    else:
        root_path = Path(root_dir)
    
    print(f"相对路径根目录: {root_path.absolute()}")
    
    # 遍历所有task.json文件
    for task_file in base_path.rglob("task.json"):
        try:
            # 获取包含task.json的目录
            trajectory_dir = task_file.parent
            
            # 计算相对于根目录的路径
            relative_dir = trajectory_dir.relative_to(root_path)
            
            # 读取task.json文件
            with open(task_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查is_delete字段
            is_delete = data.get("is_delete", False)
            if is_delete:
                print(f"跳过已删除的轨迹: {relative_dir}")
                continue
            
            # 提取query字段
            query = data.get("query", "")
            
            # 添加到结果列表
            results.append({
                "id": id_counter,
                "query": query,
                "relative_path": str(relative_dir).replace("\\", "/")
            })
            
            id_counter += 1
            print(f"已处理: {relative_dir}")
            
        except ValueError as e:
            print(f"警告：路径计算错误 {task_file}: {e}")
        except json.JSONDecodeError as e:
            print(f"警告：无法解析JSON文件 {task_file}: {e}")
        except Exception as e:
            print(f"警告：处理文件 {task_file} 时出错: {e}")
    
    return results

def load_old_summary(old_file_path):
    """
    加载旧的summary文件
    
    Args:
        old_file_path: 旧的JSON文件路径
    
    Returns:
        dict: 旧的数据，如果文件不存在返回None
    """
    old_path = Path(old_file_path)
    if not old_path.exists():
        print(f"警告：旧文件 {old_file_path} 不存在")
        return None
    
    try:
        with open(old_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"成功加载旧文件，包含 {data.get('total_count', 0)} 条数据")
        return data
    except Exception as e:
        print(f"错误：读取旧文件失败 {old_file_path}: {e}")
        return None

def rename_py_file(old_id, new_id, rules_dir="rules"):
    """
    重命名rules目录下的.py文件
    
    Args:
        old_id: 旧的id
        new_id: 新的id（带a_前缀）
        rules_dir: rules目录路径
    
    Returns:
        bool: 是否成功
    """
    rules_path = Path(rules_dir)
    old_file = rules_path / f"{old_id}.py"
    new_file = rules_path / f"{new_id}.py"
    
    if old_file.exists():
        try:
            shutil.move(str(old_file), str(new_file))
            print(f"已重命名文件: {old_id}.py -> {new_id}.py")
            return True
        except Exception as e:
            print(f"错误：重命名文件失败 {old_file}: {e}")
            return False
    else:
        print(f"警告：文件不存在 {old_file}")
        return False

def get_next_available_id(used_ids, start=1):
    """获取下一个可用的ID（从start开始递增）"""
    next_id = start
    while next_id in used_ids:
        next_id += 1
    return next_id

def merge_summaries(new_results, old_summary, output_file, rules_dir="rules"):
    # 第一步：处理旧数据中存在的query（在新数据中也能找到的）
    old_query_map = {}
    old_items_list = []
    
    if old_summary:
        for item in old_summary.get("trajectories", []):
            old_items_list.append(item)
            old_query_map[item["query"]] = item
    
    # 创建新数据的query到路径的映射
    new_query_map = {item["query"]: item for item in new_results}
    
    # 存储最终结果
    merged_trajectories = []
    used_ids = set()  # 记录已被占用的数字ID
    
    # 第一步：处理旧数据中存在的query
    for old_item in old_items_list:
        if old_item["query"] in new_query_map:
            new_item = new_query_map[old_item["query"]]
            merged_item = {
                "id": old_item["id"],
                "query": old_item["query"],
                "relative_path": new_item["relative_path"]
            }
            # 如果路径不同，添加path_list
            if old_item["relative_path"] != new_item["relative_path"]:
                merged_item["path_list"] = [{
                    "relative_path": old_item["relative_path"],
                    "is_ground": "false"
                }]
            merged_trajectories.append(merged_item)
            used_ids.add(old_item["id"])
    
    # 第二步：处理旧数据中缺失的query（新数据中没有的）
    missing_items = []
    for old_item in old_items_list:
        if old_item["query"] not in new_query_map:
            new_id = f"a_{old_item['id']}"
            rename_py_file(old_item['id'], new_id, rules_dir)
            missing_items.append({
                "id": new_id,
                "query": old_item["query"],
                "relative_path": old_item["relative_path"]
            })
            print(f"补充缺失的query: '{old_item['query']}' (原id: {old_item['id']} -> 新id: {new_id})")
            # 注意：不添加到merged_trajectories，也不添加到used_ids
    
    # 第三步：处理新数据中全新的query（旧数据中没有的）
    next_id = 1
    for new_item in new_results:
        if new_item["query"] not in old_query_map:
            # 找到下一个可用的ID（跳过已被占用的）
            while next_id in used_ids:
                next_id += 1
            merged_trajectories.append({
                "id": next_id,
                "query": new_item["query"],
                "relative_path": new_item["relative_path"]
            })
            used_ids.add(next_id)
            next_id += 1
    
    # 第四步：按ID排序（数字从小到大）
    merged_trajectories.sort(key=lambda x: x["id"])
    
    # 第五步：将缺失的数据追加到末尾
    merged_trajectories.extend(missing_items)

    print("missing_items",missing_items)
    
    return {
        "total_count": len(merged_trajectories),
        "trajectories": merged_trajectories
    }

def save_results(results, output_file):
    """
    保存结果到JSON文件
    
    Args:
        results: 轨迹信息列表或合并后的数据
        output_file: 输出文件路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
    print(f"共处理了 {results['total_count']} 个轨迹")

def print_preview(results, num=3):
    """
    打印预览
    
    Args:
        results: 合并后的数据
        num: 预览数量
    """
    print("\n预览前{}条结果:".format(min(num, len(results['trajectories']))))
    print("-" * 50)
    for item in results['trajectories'][:num]:
        print(f"ID: {item['id']}")
        print(f"Query: {item['query']}")
        print(f"Path: {item['relative_path']}")
        if 'path_list' in item:
            print(f"额外路径列表: {item['path_list']}")
        print("-" * 50)

def main():
    # 配置路径
    base_directory = "BMK/first"
    old_summary_file = "rules/trajectory_summary_0506.json"
    output_file = "rules/trajectory_summary_0513.json"
    rules_directory = "rules"
    
    # 1. 提取新数据（过滤is_delete=True的）
    print("=" * 50)
    print("步骤1: 提取新数据")
    print("=" * 50)
    new_results = extract_trajectory_info(base_directory)
    
    if not new_results:
        print("未找到任何有效的task.json文件（非删除状态）")
        return
    
    # 2. 加载旧数据
    print("\n" + "=" * 50)
    print("步骤2: 加载旧数据")
    print("=" * 50)
    old_summary = load_old_summary(old_summary_file)
    
    # 3. 合并数据
    print("\n" + "=" * 50)
    print("步骤3: 合并数据")
    print("=" * 50)
    merged_data = merge_summaries(new_results, old_summary, output_file, rules_directory)
    
    # 4. 保存结果
    print("\n" + "=" * 50)
    print("步骤4: 保存结果")
    print("=" * 50)
    save_results(merged_data, output_file)
    
    # 5. 打印预览
    print_preview(merged_data, 5)
    
    # 统计信息
    print("\n" + "=" * 50)
    print("统计信息")
    print("=" * 50)
    new_count = len(new_results)
    old_count = old_summary.get('total_count', 0) if old_summary else 0
    merged_count = merged_data['total_count']
    
    # 统计有额外路径的数据条数
    extra_path_count = sum(1 for item in merged_data['trajectories'] if 'path_list' in item)
    
    print(f"新提取的有效数据（非删除）: {new_count} 条")
    print(f"旧数据总数: {old_count} 条")
    print(f"合并后总数: {merged_count} 条")
    print(f"包含额外路径的数据: {extra_path_count} 条")
    
    if old_summary and old_count > 0:
        missing_count = merged_count - new_count
        if missing_count > 0:
            print(f"补充的缺失数据: {missing_count} 条")
        else:
            print("所有旧数据都已包含在新数据中")

if __name__ == "__main__":
    main()