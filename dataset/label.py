import json
import re

input_file = "cti_200_dataset.jsonl"
output_file = "correct_pre_labeled.jsonl"

def annotate_text(text):
    labels = []
    
    # 1. 规则 1：匹配所有 CVE (CVE-YYYY-XXXXX)
    for m in re.finditer(r'CVE-\d{4}-\d{4,7}', text):
        labels.append([m.start(), m.end(), "CVE"])
        
    # 2. 规则 2：威胁手法 / 常见漏洞类型词库匹配 (Technique)
    technique_keywords = [
        "unsafe reflection vulnerability",
        "unsafe reflection",
        "missing authentication for critical function vulnerability",
        "missing authentication for critical function",
        "improper authentication vulnerability",
        "improper authentication",
        "execute arbitrary Java bytecode",
        "execute arbitrary code",
        "modify certain system configurations"
    ]
    for kw in technique_keywords:
        # 使用 ignorecase 匹配
        for m in re.finditer(re.escape(kw), text, re.IGNORECASE):
            labels.append([m.start(), m.end(), "Technique"])
            
    # 3. 规则 3：精准提取常见软件/受影响组件 (Software)
    # 先正则匹配 "affects xxx." 里的精确软件名
    affects_match = re.search(r'affects\s+([^.]+?)\.', text)
    if affects_match:
        software_name = affects_match.group(1).strip()
        # 将文中所有出现的该软件名全部打上标签
        if len(software_name) > 2:
            for m in re.finditer(re.escape(software_name), text):
                labels.append([m.start(), m.end(), "Software"])
                
    # 4. 去重与按起始位置排序 (防止标签重叠)
    # 简单的去重逻辑
    unique_labels = []
    for l in sorted(labels, key=lambda x: (x[0], x[1])):
        if l not in unique_labels:
            unique_labels.append(l)
            
    return unique_labels

# 执行重标
results = []
with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        item = json.loads(line)
        item["label"] = annotate_text(item["text"])
        results.append(item)

with open(output_file, "w", encoding="utf-8") as f:
    for res in results:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")

print(f"修正后的预标注已生成：{output_file}")