import os
import json
from pathlib import Path

def extract_trajectory_info(base_dir, root_dir=None):
    """
    遍历目录，提取所有task.json中的query信息
    
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

def save_results(results, output_file):
    """
    保存结果到JSON文件
    
    Args:
        results: 轨迹信息列表
        output_file: 输出文件路径
    """
    output_data = {
        "total_count": len(results),
        "trajectories": results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
    print(f"共处理了 {len(results)} 个轨迹")

def main():
    # 配置路径
    base_directory = "BMK/first"
    output_file = "rules/trajectory_summary_0513.json"
    
    # 方式1：自动检测根目录（推荐）
    # 假设当前目录结构为：当前目录/BMK/2026-04-29/...
    results = extract_trajectory_info(base_directory)
    
    # 方式2：手动指定根目录
    # results = extract_trajectory_info(base_directory, root_dir=".")
    
    # 保存结果
    if results:
        save_results(results, output_file)
        
        # 打印前几个结果作为预览
        print("\n预览前3条结果:")
        print("-" * 50)
        for item in results[:3]:
            print(f"ID: {item['id']}")
            print(f"Query: {item['query']}")
            print(f"Path: {item['relative_path']}")
            print("-" * 50)
    else:
        print("未找到任何task.json文件")

if __name__ == "__main__":
    main()