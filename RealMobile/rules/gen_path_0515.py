import json
from pathlib import Path

def find_all_task_json_files(base_dirs):
    """遍历目录找到所有 task.json"""
    task_files = []
    for base_dir in base_dirs:
        base_path = Path(base_dir)
        if not base_path.exists():
            print(f"警告：目录 {base_dir} 不存在")
            continue
        for task_file in base_path.rglob("task.json"):
            task_files.append(task_file)
    return task_files

def load_trajectories(json_path):
    """加载 trajectories 列表"""
    if not json_path.exists():
        return []
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取 trajectories 数组
    if isinstance(data, dict) and 'trajectories' in data:
        return data['trajectories']
    elif isinstance(data, list):
        return data
    else:
        return []

def save_trajectories(json_path, trajectories):
    """保存 trajectories 列表"""
    output_data = {
        "total_count": len(trajectories),
        "trajectories": trajectories
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

def convert_0513_format():
    """转换 0513 格式并返回 trajectories"""
    with open('rules/trajectory_summary_0513.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取 trajectories
    if 'trajectories' in data:
        trajectories = data['trajectories']
    else:
        trajectories = data
    
    # 转换格式
    for item in trajectories:
        new_path_list = []
        
        if 'relative_path' in item:
            new_path_list.append({'path': item['relative_path'], 'tag': True})
            del item['relative_path']
        
        if 'path_list' in item:
            for path_item in item['path_list']:
                if 'relative_path' in path_item:
                    path_item['path'] = path_item['relative_path']
                    del path_item['relative_path']
                if 'is_ground' in path_item:
                    del path_item['is_ground']
                path_item['tag'] = True
                new_path_list.append(path_item)
            del item['path_list']
        
        if new_path_list:
            item['path_list'] = new_path_list
    
    return trajectories

def extract_from_task_file(task_file):
    """从 task.json 提取信息，如果 is_delete=True 则返回 None"""
    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if data.get('is_delete', False):
            return None
        
        query = data.get('query', '')
        if not query:
            return None
        
        relative_path = str(task_file.parent).replace("\\", "/")
        return {'query': query, 'path': relative_path}
    except:
        return None

def main():
    # 1. 获取转换后的 0513 数据
    trajectories = convert_0513_format()
    print(f"从 0513 加载 {len(trajectories)} 条轨迹")
    save_trajectories(Path('rules/trajectory_summary_0515_old.json'), trajectories)
    
    # 2. 获取最大 id
    max_id = 0
    for item in trajectories:
        if isinstance(item.get('id'), int):
            max_id = max(max_id, item['id'])
    
    # 3. 遍历三个目录，添加新轨迹
    base_dirs = ["BMK/second/", "BMK/third/", "BMK/fourth/"]
    task_files = find_all_task_json_files(base_dirs)
    print(f"找到 {len(task_files)} 个 task.json")
    
    # 建立 query 到轨迹的映射
    query_map = {item['query']: item for item in trajectories}
    
    for task_file in task_files:
        info = extract_from_task_file(task_file)
        if not info:
            continue
        
        query = info['query']
        path = info['path']
        
        if query in query_map:
            # query 存在，添加路径
            item = query_map[query]
            if 'path_list' not in item:
                item['path_list'] = []
            
            if not any(p.get('path') == path for p in item['path_list']):
                item['path_list'].append({'path': path, 'tag': True})
                print(f"添加路径: {query[:30]}...")
        else:
            # query 不存在，创建新轨迹
            max_id += 1
            new_item = {
                'id': max_id,
                'query': query,
                'path_list': [{'path': path, 'tag': True}]
            }
            trajectories.append(new_item)
            query_map[query] = new_item
            print(f"添加新轨迹: id={max_id}, {query[:30]}...")
    
    # 4. 保存
    save_trajectories(Path('rules/trajectory_summary_0515.json'), trajectories)
    print(f"\n完成！共 {len(trajectories)} 条轨迹，保存到 rules/trajectory_summary_0515.json")

if __name__ == "__main__":
    main()