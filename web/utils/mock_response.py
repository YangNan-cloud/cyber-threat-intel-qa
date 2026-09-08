def get_mock_response(question: str):
    """模拟后端返回，用于前端开发和演示"""
    return {
        "answer": "APT29（又称Cozy Bear）近期主要使用鱼叉式钓鱼攻击和CVE-2021-44228漏洞利用，针对政府机构和智库发起攻击。",
        "confidence": 0.87,
        "sources": [
            {"document": "360_APT_report_2025.md", "snippet": "APT29利用CVE-2021-44228...", "page": 3}
        ],
        "iocs": {
            "ip": ["192.168.1.1", "10.0.0.1"],
            "domain": ["evil-c2.net", "malware-cdn.com"],
            "hash": ["a1b2c3d4e5f6..."],
            "cve": ["CVE-2021-44228", "CVE-2024-12345"]
        },
        "threat_actors": [
            {"name": "APT29", "description": "俄罗斯背景的APT组织，又名Cozy Bear", "aliases": ["Cozy Bear"]}
        ]
    }