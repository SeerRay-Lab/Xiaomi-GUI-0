import json
import os
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_rule_module(rule_id: int, rules_dir: str = "rules"):
    """
    动态加载指定ID的规则模块
    
    Args:
        rule_id: 规则ID (1-33)
        rules_dir: 规则文件所在目录
    
    Returns:
        加载的模块对象
    """
    rule_file = os.path.join(rules_dir, f"{rule_id}.py")
    
    if not os.path.exists(rule_file):
        raise FileNotFoundError(f"规则文件不存在: {rule_file}")
    
    # 动态加载模块
    spec = importlib.util.spec_from_file_location(f"rule_{rule_id}", rule_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    return module

def evaluate_single_path(rule_id: int, path: str, rules_dir: str = "rules") -> Dict[str, Any]:
    """
    评估单个路径
    
    Args:
        rule_id: 规则ID
        path: 轨迹路径
        rules_dir: 规则文件目录
    
    Returns:
        评估结果字典
    """
    try:
        # 加载对应的规则模块
        rule_module = load_rule_module(rule_id, rules_dir)
        
        # 调用评估函数
        if hasattr(rule_module, 'evaluate_trajectory'):
            result = rule_module.evaluate_trajectory(path=path)
        else:
            raise AttributeError(f"规则模块 {rule_id}.py 中没有 evaluate_trajectory 函数")
        
        return result
        
    except Exception as e:
        print(f"  ✗ 路径 {path} 评估失败: {str(e)}")
        return {
            "total_score": 0.0,
            "details": [],
            "rejection_reason": f"评估失败: {str(e)}",
            "error": str(e)
        }

def evaluate_trajectory_data(json_file: str = "rules/trajectory_data.json", 
                            rules_dir: str = "rules",
                            output_file: str = None) -> Dict[str, Any]:
    """
    评估轨迹数据（每个数据包含多个path）
    
    Args:
        json_file: 包含轨迹数据的JSON文件路径
        rules_dir: 规则文件目录
        output_file: 输出文件路径（不指定则自动生成）
    
    Returns:
        包含所有评估结果的字典
    """
    # 加载任务列表
    print(f"加载轨迹数据: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    trajectories = data.get('trajectories', data.get('data', []))
    total_tasks = len(trajectories)
    print(f"共找到 {total_tasks} 个任务")
    
    # 存储所有结果
    all_results = []
    
    # 依次评估每个任务的所有路径
    for idx, trajectory in enumerate(trajectories, 1):
        task_id = trajectory['id']
        task_query = trajectory['query']
        path_list = trajectory['path_list']
        
        print(f"\n{'='*60}")
        print(f"正在评估任务 [{idx}/{total_tasks}] ID {task_id}: {task_query}")
        print(f"共有 {len(path_list)} 条路径需要评估")
        print(f"{'='*60}")
        
        # 评估该任务的所有路径
        path_results = []
        scores_list = []
        success_list = []
        
        for path_idx, path_item in enumerate(path_list, 1):
            path = path_item['path']
            tag = path_item.get('tag', False)
            
            print(f"\n  评估路径 [{path_idx}/{len(path_list)}]: {path}")
            
            # 评估当前路径
            result = evaluate_single_path(task_id, path, rules_dir)
            
            score = result.get('total_score', 0)
            is_success = (score >= 1.0)  # 判断是否成功（得分是否为1.0）
            
            scores_list.append(score)
            success_list.append(is_success)
            
            path_results.append({
                'path': path,
                'tag': tag,
                'score': score,
                'is_success': is_success,
                'details': result.get('details', []),
                'rejection_reason': result.get('rejection_reason', ''),
                'error': result.get('error', None)
            })
            
            status = "✓" if is_success else "✗"
            print(f"    {status} 得分: {score:.2f}")
        
        # 计算统计信息
        avg_score = sum(scores_list) / len(scores_list) if scores_list else 0
        success_count = sum(success_list)
        
        # 存储该任务的完整结果
        task_result = {
            'id': task_id,
            'query': task_query,
            'total_paths': len(path_list),
            'scores_list': scores_list,
            'success_list': success_list,
            'success_count': success_count,
            'success_rate': success_count / len(path_list) if path_list else 0,
            'avg_score': avg_score,
            'path_results': path_results
        }
        
        all_results.append(task_result)
        
        # 打印该任务的汇总
        print(f"\n  📊 任务 {task_id} 汇总:")
        print(f"     分数列表: {[round(s, 2) for s in scores_list]}")
        print(f"     成功列表: {success_list}")
        print(f"     成功率: {success_count}/{len(path_list)} ({task_result['success_rate']*100:.1f}%)")
        print(f"     平均分: {avg_score:.2f}")
    
    # 总体统计
    total_paths = sum(r['total_paths'] for r in all_results)
    total_success = sum(r['success_count'] for r in all_results)
    all_scores = [score for r in all_results for score in r['scores_list']]
    
    summary = {
        "total_tasks": total_tasks,
        "total_paths": total_paths,
        "total_success": total_success,
        "total_success_rate": total_success / total_paths if total_paths > 0 else 0,
        "overall_avg_score": sum(all_scores) / len(all_scores) if all_scores else 0,
        "evaluation_time": datetime.now().isoformat()
    }
    
    # 准备输出数据
    output_data = {
        "summary": summary,
        "results": all_results
    }
    
    # 生成输出文件名
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"results/evaluation_results_{timestamp}"
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else "results", exist_ok=True)
    
    # 保存JSON结果
    json_output = f"{output_file}.json"
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ JSON结果已保存: {json_output}")
    
    # 打印总体统计
    print(f"\n{'='*60}")
    print("总体评估统计:")
    print(f"{'='*60}")
    print(f"总任务数: {total_tasks}")
    print(f"总路径数: {total_paths}")
    print(f"成功路径数: {total_success}")
    print(f"总体成功率: {summary['total_success_rate']*100:.2f}%")
    print(f"总体平均分: {summary['overall_avg_score']:.2f}")
    print(f"评估时间: {summary['evaluation_time']}")
    print(f"{'='*60}")
    
    # 打印每个任务的简化结果（你想要的格式）
    print_all_results_simple(all_results)
    
    return output_data

def print_all_results_simple(results: List[Dict[str, Any]]):
    """
    打印所有任务的简化结果，格式：id, [True, True, False, False]
    
    Args:
        results: 所有任务的评估结果列表
    """
    print("\n" + "="*80)
    print("简化结果列表 (ID: [成功列表])")
    print("="*80)
    
    for result in results:
        task_id = result['id']
        success_list = result['success_list']
        scores_list = result['scores_list']
        
        # 格式化输出
        success_str = str(success_list)
        scores_str = f"[{', '.join([f'{s:.2f}' for s in scores_list])}]"
        
        print(f"{task_id}: {success_str}")
        print(f"    分数: {scores_str}")
        print(f"    成功率: {result['success_count']}/{result['total_paths']} ({result['success_rate']*100:.1f}%)")
        print()
    
    print("="*80)

def print_detailed_results(results: List[Dict[str, Any]]):
    """
    打印详细结果（包含每个路径的详细信息）
    
    Args:
        results: 所有任务的评估结果列表
    """
    print("\n" + "="*80)
    print("详细评估结果")
    print("="*80)
    
    for result in results:
        print(f"\n{'='*60}")
        print(f"任务 ID: {result['id']}")
        print(f"Query: {result['query']}")
        print(f"{'='*60}")
        
        for idx, path_result in enumerate(result['path_results'], 1):
            print(f"\n路径 {idx}: {path_result['path']}")
            print(f"  Tag: {path_result['tag']}")
            print(f"  得分: {path_result['score']:.2f}")
            print(f"  成功: {'是' if path_result['is_success'] else '否'}")
            
            if path_result.get('rejection_reason'):
                print(f"  拒绝原因: {path_result['rejection_reason']}")
            elif path_result.get('error'):
                print(f"  错误: {path_result['error']}")
            else:
                # 打印每个规则的详细得分
                for detail in path_result.get('details', []):
                    print(f"    - {detail.get('rule')}: {'✓' if detail.get('satisfied') else '✗'} (得分: {detail.get('score')})")
                    if detail.get('evidence'):
                        evidence = detail.get('evidence')[:100]
                        print(f"      证据: {evidence}...")
        
        print(f"\n{'─'*40}")
        print(f"任务汇总:")
        print(f"  分数列表: {[round(s, 2) for s in result['scores_list']]}")
        print(f"  成功列表: {result['success_list']}")
        print(f"  成功率: {result['success_count']}/{result['total_paths']} ({result['success_rate']*100:.1f}%)")
        print(f"  平均分: {result['avg_score']:.2f}")

def generate_comparison_report(results: List[Dict[str, Any]], output_file: str = None):
    """
    生成对比报告，比较每个任务的多个path的表现
    
    Args:
        results: 所有任务的评估结果列表
        output_file: 输出文件路径
    """
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"comparison_report_{timestamp}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("轨迹对比评估报告\n")
        f.write("="*80 + "\n\n")
        
        for result in results:
            f.write(f"\n{'='*60}\n")
            f.write(f"任务 ID: {result['id']}\n")
            f.write(f"Query: {result['query']}\n")
            f.write(f"{'='*60}\n\n")
            
            f.write("路径对比:\n")
            f.write("-"*40 + "\n")
            
            for idx, path_result in enumerate(result['path_results'], 1):
                f.write(f"\n路径 {idx}: {path_result['path']}\n")
                f.write(f"  Tag: {path_result['tag']}\n")
                f.write(f"  得分: {path_result['score']:.2f}\n")
                f.write(f"  状态: {'成功' if path_result['is_success'] else '失败'}\n")
                
                if path_result.get('rejection_reason'):
                    f.write(f"  拒绝原因: {path_result['rejection_reason']}\n")
            
            f.write(f"\n任务汇总:\n")
            f.write(f"  分数列表: {[round(s, 2) for s in result['scores_list']]}\n")
            f.write(f"  成功列表: {result['success_list']}\n")
            f.write(f"  成功率: {result['success_count']}/{result['total_paths']} ({result['success_rate']*100:.1f}%)\n")
            f.write(f"  平均分: {result['avg_score']:.2f}\n")
            f.write("\n" + "─"*60 + "\n")
    
    print(f"✓ 对比报告已生成: {output_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='评估移动端任务轨迹（支持多路径）')
    parser.add_argument('--json', type=str, default='rules/trajectory_summary_0515.json',
                       help='轨迹数据JSON文件路径')
    parser.add_argument('--rules-dir', type=str, default='rules',
                       help='规则文件目录')
    parser.add_argument('--output', type=str, default=None,
                       help='输出文件前缀')
    parser.add_argument('--detailed', action='store_true',
                       help='打印详细结果')
    parser.add_argument('--report', action='store_true',
                       help='生成对比报告')
    
    args = parser.parse_args()
    
    # 执行评估
    results = evaluate_trajectory_data(
        json_file=args.json,
        rules_dir=args.rules_dir,
        output_file=args.output
    )
    
    # 打印详细结果（如果需要）
    if args.detailed:
        print_detailed_results(results['results'])
    
    # 生成对比报告（如果需要）
    if args.report:
        generate_comparison_report(results['results'])
    
    # 额外输出：按要求的简化格式
    print("\n" + "="*80)
    print("按要求格式输出 (ID: [成功列表]):")
    print("="*80)
    for result in results['results']:
        print(f"{result['id']}, {result['success_list']}")