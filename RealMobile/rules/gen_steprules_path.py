import json
from pathlib import Path

def load_json_file(file_path):
    """
    加载JSON文件
    
    Args:
        file_path: JSON文件路径
    
    Returns:
        解析后的JSON数据
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return None
    except json.JSONDecodeError as e:
        print(f"错误：解析JSON文件 {file_path} 失败: {e}")
        return None

def merge_trajectory_and_rules(trajectory_file, rules_file, output_file):
    """
    合并轨迹数据和步骤规则
    
    Args:
        trajectory_file: 轨迹汇总文件路径
        rules_file: 步骤规则文件路径
        output_file: 输出文件路径
    """
    # 加载两个JSON文件
    trajectory_data = load_json_file(trajectory_file)
    rules_data = load_json_file(rules_file)
    
    if trajectory_data is None or rules_data is None:
        return
    
    # 提取轨迹信息，建立query到轨迹信息的映射
    trajectory_map = {}
    for traj in trajectory_data.get("trajectories", []):
        query = traj.get("query", "")
        if query:
            trajectory_map[query] = {
                "id": traj.get("id"),
                "path": traj.get("relative_path")
            }
    
    print(f"轨迹文件中共有 {len(trajectory_map)} 条不同的query")
    print(f"规则文件中共有 {len(rules_data)} 条规则")
    
    # 找出重合的query
    common_queries = set(trajectory_map.keys()) & set(rules_data.keys())
    print(f"\n重合的query数量: {len(common_queries)}")
    
    # 构建合并后的数据
    merged_results = []
    for query in sorted(common_queries):
        merged_results.append({
            "query": query,
            "id": trajectory_map[query]["id"],
            "path": trajectory_map[query]["path"],
            "steprules": rules_data[query]
        })
    
    # 保存结果
    output_data = {
        "total_count": len(merged_results),
        "merged_data": merged_results
    }
    
    # 确保输出目录存在
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
    print(f"共合并了 {len(merged_results)} 条记录")
    
    # 打印一些示例
    if merged_results:
        print("\n前3条合并结果示例:")
        print("-" * 80)
        for i, item in enumerate(merged_results[:3], 1):
            print(f"{i}. Query: {item['query']}")
            print(f"   ID: {item['id']}")
            print(f"   Path: {item['path']}")
            print(f"   StepRules类型: {type(item['steprules']).__name__}")
            if isinstance(item['steprules'], list):
                print(f"   规则数量: {len(item['steprules'])}")
            print("-" * 80)
    
    # 可选：输出只在轨迹文件中存在的query
    only_in_trajectory = set(trajectory_map.keys()) - set(rules_data.keys())
    if only_in_trajectory:
        print(f"\n只在轨迹文件中存在的query数量: {len(only_in_trajectory)}")
        print("前5个示例:", list(only_in_trajectory)[:5])
    
    # 可选：输出只在规则文件中存在的query
    only_in_rules = set(rules_data.keys()) - set(trajectory_map.keys())
    if only_in_rules:
        print(f"\n只在规则文件中存在的query数量: {len(only_in_rules)}")
        print("前5个示例:", list(only_in_rules)[:5])

def main():
    # 配置文件路径
    trajectory_file = "rules/trajectory_summary_0506.json"
    rules_file = "query_finegrainrule/query_30_steprules_0421_fix1.json"
    output_file = "rules/query_step_trajectory_0506.json"
    
    print("开始合并轨迹和规则数据...")
    print("=" * 60)
    
    merge_trajectory_and_rules(trajectory_file, rules_file, output_file)
    
    print("\n处理完成！")

if __name__ == "__main__":
    main()